"""建立超級管理者: 第一次的 signup, 以及 CLI 補建。

這兩條是**僅有的**能產生超級管理者的路徑 (一般的建立使用者永遠不行, 見
`service.validate_role_ids`), 所以和一般的使用者管理分開放, 一眼看得出邊界。

「最多一次」由 `system_state` 的唯一約束保證 (latch, 見 `bootstrap_model.py`), 不是靠查詢
「目前有沒有超級管理者」—— 那種查法會讓兩個同時送達的 signup 都成功。
"""

import secrets

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.roles.public import RoleTable
from shared.auth import passwords
from shared.db.table import is_unique_violation
from shared.db.transaction import transaction
from shared.http.errors import LangException

from .bootstrap_model import SUPER_ADMIN_BOOTSTRAP_KEY, SystemStateTable
from .errors import UserError
from .model import UserTable
from .schema import SignupRequest, SignupResponse, SuperAdminCreate, UserOperate


async def bootstrap_available(expected_key: str) -> bool:
    """signup 這條路徑現在還開著嗎?

    兩個條件都要成立: `REGISTER_KEY` 有設定, 而且還沒有人完成過 bootstrap。
    這只是給前端決定要不要顯示表單用的**提示**, 真正的把關在 `signup_user`。
    """
    if not expected_key:
        return False
    return not await SystemStateTable.exists(SUPER_ADMIN_BOOTSTRAP_KEY)


async def signup_user(form_data: SignupRequest, expected_key: str) -> SignupResponse:
    """建立**第一個**超級管理者。整個部署生命週期內只能成功一次。

    latch 與使用者在同一個 transaction 裡建立, 因此併發請求最多只有一個成功;
    若使用者建立失敗, latch 也會一起回滾。
    """
    # 空字串檢查必須在比對之前: 否則空設定值會讓「不填邀請碼」剛好通過。
    # compare_digest 避免時間差洩漏。
    if not expected_key or not secrets.compare_digest(form_data.register_key, expected_key):
        raise LangException(400, UserError.REGISTER_KEY_MISMATCH)

    # 不是併發防護 (仲裁者是 latch 的唯一鍵), 只是避免在注定失敗的請求上白算 bcrypt。
    if await SystemStateTable.exists(SUPER_ADMIN_BOOTSTRAP_KEY):
        raise LangException(409, UserError.BOOTSTRAP_ALREADY_COMPLETED)

    try:
        return SignupResponse.model_validate(
            await _create_super_admin(form_data, latch_required=True)
        )
    except IntegrityError as exc:
        if not is_unique_violation(exc):
            raise
        # 可能撞到 latch 或 username。重查狀態而不解析約束名稱 (那是 schema 細節)。
        if await SystemStateTable.exists(SUPER_ADMIN_BOOTSTRAP_KEY):
            raise LangException(409, UserError.BOOTSTRAP_ALREADY_COMPLETED) from exc
        raise LangException(409, UserError.USERNAME_EXISTS) from exc


async def create_super_admin(form_data: SuperAdminCreate) -> UserOperate:
    """由 CLI 建立超級管理者 (見 `scripts/db.py create-superuser`)。

    **刻意不接在任何 router 上, 也不應該接。** 它是唯一繞過 `validate_role_ids` 的路徑,
    授權模型是「呼叫者已經有伺服器的 shell 存取權」; 接上 HTTP 就變成完全不同的授權模型。

    與 `signup_user` 不同: 沒有 latch 檢查 (可以建第二、第三個), 但會**補寫** latch ——
    否則用 CLI 完成初始化之後 `/signup` 會一直開著。
    """
    try:
        return UserOperate.model_validate(
            await _create_super_admin(form_data, latch_required=False)
        )
    except IntegrityError as exc:
        if not is_unique_violation(exc):
            raise
        # CLI 序列執行, 只可能撞到 username。
        raise LangException(409, UserError.USERNAME_EXISTS) from exc


async def _create_super_admin(
    form_data: SignupRequest | SuperAdminCreate, *, latch_required: bool
) -> dict:
    """在同一個 transaction 裡寫 latch 與超級管理者帳號。

    `latch_required=True` (signup) 時 latch 一律新增, 已存在就撞唯一約束失敗;
    `False` (CLI) 時只在還沒有 latch 時補寫。
    """
    if await UserTable.find_detail_by_username(username=form_data.username):
        raise LangException(409, UserError.USERNAME_EXISTS)

    role_ids = [await RoleTable.get_super_admin_role_id()]
    # bcrypt 要在進入 transaction 之前算完, 否則交易會多持有鎖 100–300ms。
    password_hash = await passwords.hash_password_async(form_data.password)

    async with transaction() as session:
        if latch_required or not await SystemStateTable.exists(
            SUPER_ADMIN_BOOTSTRAP_KEY, session=session
        ):
            await _write_latch(form_data.username, session)
        return await UserTable.create(
            data={
                "username": form_data.username,
                "nickname": form_data.nickname,
                "password": password_hash,
                "role_ids": role_ids,
            },
            session=session,
        )


async def _write_latch(username: str, session: AsyncSession) -> None:
    await SystemStateTable.create(
        data={"key": SUPER_ADMIN_BOOTSTRAP_KEY, "value": {"username": username}},
        session=session,
    )
