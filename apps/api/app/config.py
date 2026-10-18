import sys
from typing import Literal

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# `make init` 以 `openssl rand -hex 32` 產生, 長度為 64。設下限避免有人手動填入弱金鑰。
MIN_JWT_SECRET_LENGTH = 32

# 產品版號: 跟 git tag (`v<版號>`) 與 CHANGELOG 對齊, 前端經 `GET /api/system/version` 顯示。
# 不要手動改, 用 `make release <版號>` (與 CHANGELOG 一致由 tests/test_version.py 擋)。
APP_VERSION = "0.0.1"


class AppEnv(BaseSettings):
    model_config = SettingsConfigDict(
        alias_generator=lambda x: x.upper(),
        populate_by_name=True,
        env_file_encoding="utf-8",
    )

    # ---- 必填 ----
    # 不要給預設值: 缺少時要在啟動當下就失敗 (空的金鑰會簽出任何人都能偽造的 token)。
    project_name: str = Field(min_length=1)
    # 必須是 asyncpg 的 driver URL。裸的 `postgresql://` 的症狀是看不出原因的
    # `ModuleNotFoundError: psycopg2`, 所以在這裡就擋。
    postgres_url: str = Field(min_length=1, pattern=r"^postgresql\+asyncpg://")
    jwt_secret_key: str = Field(min_length=MIN_JWT_SECRET_LENGTH)
    # 前端以同一個值算 cookie 的 maxAge, 兩邊必須一致 (compose 也是 `:?` 必填)。給預設值
    # 的話, 漏設時後端照樣啟動、簽出的 token 壽命跟 cookie 對不上, 而且沒有任何錯誤。
    expire_hours: int = Field(ge=1)

    # ---- 選填 ----
    mode: Literal["development", "production"] = "development"
    # 不要放寬成 str: 設成 `none` 會讓未簽名的 token 通過驗證。
    jwt_algorithm: Literal["HS256"] = "HS256"
    # 要強制全站重新登入時 +1 (與 APP_VERSION 脫鉤)。
    token_version: str = "1"  # noqa: S105 —— 這是版本計數器, 名字裡的 token 讓 bandit 誤判成密碼


def _load_env() -> AppEnv:
    try:
        # 必填欄位由 pydantic-settings 從環境變數帶入, 不是呼叫端傳的; 型別檢查器看不到這層。
        return AppEnv()  # type: ignore[call-arg]
    except ValidationError as exc:
        details = "\n".join(
            f"  - {'.'.join(str(loc) for loc in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        print(f"[config] 環境變數設定錯誤，服務無法啟動：\n{details}", file=sys.stderr)
        raise SystemExit(1) from exc


env = _load_env()
