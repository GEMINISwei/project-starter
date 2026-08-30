import sys
from typing import Literal

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# `make init` 以 `openssl rand -hex 32` 產生，長度為 64。設下限避免有人手動填入弱金鑰。
MIN_JWT_SECRET_LENGTH = 32

# 顯示在 OpenAPI 上的 API 版本，同時是這個 repo 的版本（見 CHANGELOG.md）。
# 用這個模板開新專案時它是**那個專案自己的產品版號**，記得跟 CHANGELOG 一起重設。
# 刻意是常數而不是環境變數：沒有任何部署流程會設它，掛在 AppEnv 上只會讓人以為改 .env 有用。
#
# **升版時只改這一份**，不要去對齊 `package.json` 與 `pyproject.toml` 的 `version`（那是套件
# 欄位，兩個套件都 private，與這裡無關）。要一起改的是 `CHANGELOG.md` 最新條目的版號，
# 以及發版的 git tag（必須是 `v<這個值>`）—— 三者由 `make check-version` 守著。
APP_VERSION = "0.0.1"


class AppEnv(BaseSettings):
    model_config = SettingsConfigDict(
        alias_generator=lambda x: x.upper(),
        populate_by_name=True,
        env_file_encoding="utf-8",
    )

    # ---- 必填 ----
    # 不要給這幾項預設值：缺少時要在啟動當下就失敗。空的 jwt_secret_key 會讓服務正常起來，
    # 卻簽出任何人都能偽造的 token。
    project_name: str = Field(min_length=1)
    # 必須是 asyncpg 的 driver URL（`postgresql+asyncpg://…`）。裸的 `postgresql://`
    # 會被 SQLAlchemy 解成同步的 psycopg 方言，而那個套件不在相依裡 ——
    # 症狀是啟動時 `ModuleNotFoundError: psycopg2`，看起來跟連線設定毫無關係。
    # 因此在這裡就擋，而不是等 create_async_engine 去解析。
    postgres_url: str = Field(min_length=1, pattern=r"^postgresql\+asyncpg://")
    jwt_secret_key: str = Field(min_length=MIN_JWT_SECRET_LENGTH)

    # ---- 選填 ----
    mode: Literal["development", "production"] = "development"
    # 不要放寬成 str 或改由環境變數指定：這個值直接餵給 jwt.encode/decode 的 algorithm，設成
    # `none` 會讓未簽名的 token 通過驗證。要換演算法請直接改這一行。
    jwt_algorithm: Literal["HS256"] = "HS256"
    expire_hours: int = Field(default=1, ge=1)
    # 只用來決定「既有 token 是否全部失效」，與 APP_VERSION 脫鉤：
    # 要強制全站重新登入時才把這個值 +1，改版本號不會踢掉所有使用者。
    token_version: str = "1"  # noqa: S105 —— 這是版本計數器，名字裡的 token 讓 bandit 誤判成密碼
    # 空字串代表停用「以系統密碼註冊超級管理者」的路徑（見 modules.users.service.signup_user）。
    register_key: str = ""
    # 空字串代表不啟用 Web Push；NotificationDispatcher 會靜默略過。
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_subject: str = ""


def _load_env() -> AppEnv:
    try:
        # 必填欄位由 pydantic-settings 從環境變數帶入，不是呼叫端傳的；型別檢查器看不到這層。
        return AppEnv()  # type: ignore[call-arg]
    except ValidationError as exc:
        details = "\n".join(
            f"  - {'.'.join(str(loc) for loc in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        print(f"[config] 環境變數設定錯誤，服務無法啟動：\n{details}", file=sys.stderr)
        raise SystemExit(1) from exc


env = _load_env()
