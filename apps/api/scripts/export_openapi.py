"""匯出 OpenAPI schema 至 JSON 檔，供前端產生 TypeScript 型別。

用法：
  python scripts/export_openapi.py [輸出路徑]     # 預設 ./openapi.json

刻意「不」透過 HTTP 抓 `/openapi.json`：`create_app()` 只組裝路由與 schema，資料庫連線是在
lifespan 才建立的，因此這支腳本不需要跑起資料庫也不需要跑起 uvicorn。CI 上可以直接執行。

必填環境變數（`app.config` 在 import 當下就驗證）在這裡填假值即可 —— 這些值不會進入
OpenAPI 輸出，只是為了讓 `app.config` 通過驗證。唯一的例外是 PROJECT_NAME，它會成為
OpenAPI 的 `info.title`，所以要讓呼叫端能覆寫，避免產生的型別檔隨環境變動。
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 必須在任何 `app.*` 被 import 之前設好（理由同 tests/conftest.py）。
os.environ.setdefault("PROJECT_NAME", "openapi-export")
os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://localhost/openapi-export")
os.environ.setdefault("JWT_SECRET_KEY", "openapi_export_placeholder_secret_key_32b")
os.environ.setdefault("MODE", "development")

from app.server import create_app


def main() -> None:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")

    # 刻意**不**建立上層目錄（不要改成 `mkdir(parents=True, exist_ok=True)`）：呼叫端把路徑
    # 打錯時，那樣會默默生出一個新目錄、把契約寫進去 —— 而 CI 的 drift job 比對的是原本那個
    # 檔（沒被動到，所以是綠的），最該被擋下來的錯反而完全沒有訊號。
    # 契約目錄本來就進版控，正常情況下必定存在，所以「不存在」只會是路徑錯了。
    if not output.parent.is_dir():
        sys.exit(f"輸出目錄不存在：{output.parent}（請檢查傳入的路徑，本腳本刻意不自動建立目錄）")

    schema = create_app().openapi()

    # sort_keys 讓輸出穩定：CI 靠 `git diff --exit-code` 判斷型別檔是否過期，
    # 只要有一次 key 順序飄動就會產生假警報。
    output.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"OpenAPI schema 已寫入 {output}（{len(schema.get('paths', {}))} 個路徑）")


if __name__ == "__main__":
    main()
