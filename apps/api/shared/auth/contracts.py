"""`shared/` 對外部世界的型別契約。

`shared/` 是 domain-agnostic 的基礎層，刻意**不** import `app.*` 或 `modules.*`
（那樣會讓它綁死在這個專案的 domain 上，也讓測試沒辦法替換）。它需要的東西是由
`app/server.py` 掛在 `app.state` 上、於執行期注入的。

用 Protocol 明確列出 shared 需要的環境設定欄位，讓 `app.state` 的執行期注入也能
接受型別檢查。擴充環境設定時，只要 `app.config.AppEnv` 仍滿足這個 Protocol，shared
不需要跟著調整。
"""

from typing import Any, Literal, NotRequired, Protocol, TypedDict


class AppEnvProtocol(Protocol):
    """`shared/` 用得到的環境設定欄位子集（由 `app.config.AppEnv` 滿足）。"""

    project_name: str
    jwt_secret_key: str
    # 收窄成 Literal 而非 str：簽章演算法是 shared 這一層的安全決策，不是 domain 設定。
    # 寫在契約上，「這個模版只簽 HS256」就從註解變成型別檢查會擋的事實。
    jwt_algorithm: Literal["HS256"]
    expire_hours: int
    token_version: str


class PermissionResolverProtocol(Protocol):
    """把使用者持有的權限展開成「含依賴」的完整集合。"""

    def expand(self, permissions: set[Any]) -> set[Any]: ...


class TokenSubject(TypedDict):
    """簽發 token 時**唯一**需要知道的身分資訊。

    刻意比 `CurrentUser` 窄：`create_token()` 不該因為使用者資料多了或少了某個欄位而受影響，
    而呼叫端（含測試）也不必為了簽一張 token 湊出一整個使用者。
    """

    username: str
    auth_version: int


class CurrentUser(TokenSubject):
    """認證流程會讀到的使用者欄位。

    標成 TypedDict 而不是裸 `dict`（同 `shared/auth/tokens.py` 的 `TokenData`）：
    `current_user["auth_version"]`、`["permissions"]`、`["id"]` 是全專案出現最多次的字串索引，
    裸 dict 會讓它們完全不受 mypy 檢查 —— Document 改個欄位名不會有任何靜態錯誤，
    到執行期才變成 `KeyError` → 500。

    **這裡只列認證與授權真的會用到的欄位**，不是 users 這個 collection 的完整形狀。
    `total=True` 的欄位就是「身分來源**必須**提供」的契約：少給一個，提供 resolver 的那個
    module 會在型別檢查時就被擋下來（見 `modules/users/manifest.py`）。
    模組自己的欄位仍然可以存在，TypedDict 不禁止多餘的鍵。
    """

    # `username` 與 `auth_version` 由 TokenSubject 提供，不在這裡重複。
    id: str
    nickname: str
    permissions: list[str]
    is_disabled: bool
    #: 只有明確要求時才會帶上（`find_detail_by_username(include_password=True)`），
    #: 所以標成 NotRequired —— 一般的認證路徑拿到的 dict 裡沒有這個鍵。
    password: NotRequired[str]


class CurrentUserResolver(Protocol):
    """以 username 取得目前使用者（含展開後的 permissions），找不到回傳 None。"""

    async def __call__(self, username: str) -> CurrentUser | None: ...
