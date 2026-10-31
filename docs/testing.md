# 測試

```bash
make check test                             # 前後端全部（帶覆蓋率）
make check integration                      # 起拋棄式 PostgreSQL 跑 integration + alembic check
make check e2e                              # 起拋棄式的正式環境，用 Playwright 從瀏覽器跑過整條路
cd apps/api && uv run pytest tests/ -k xxx  # 只跑後端某些測試
cd apps/web && npm run test:watch           # 前端 watch 模式
```

## 測試放哪裡

**一律放該 app 的 `tests/`，與原始碼同構**：`tests/modules/users/` 對 `modules/users/`、
`tests/shared/auth/test_passwords.py` 對 `shared/auth/passwords.py`、
`tests/shared/access/permissions.test.ts` 對 `shared/access/permissions.ts`。
放在 `tests/` 以外的測試不會執行，也不會報錯；`tests/` 裡對不上原始碼目錄的子目錄由架構測試擋。

- **依賴專案啟用清單的測試**（註冊表、權限覆蓋、每張已註冊資料表的慣例）放後端 `tests/app/`、
  前端 `tests/` 根目錄或 `tests/config/`。
- **一個模組的測試只放在它自己的目錄**，不要在 `tests/modules/` 根目錄寫同時測好幾個模組的檔案：
  刪模組時是整包刪 `tests/modules/<name>/`，跨模組的測試會留下來並因為引用不到而失敗。
- **`tests/shared/` 不綁專案目前有的端點與權限**：測執行期行為時用與專案無關的路徑
  （例：`tests/shared/api/request.server.test.ts`），刪掉模組時這批測試才不會跟著壞。
- **從公開函式進入**，不直接測 `_` 開頭的私有函式：規則有兩個入口時，只測輔助函式證明不了
  兩邊都有套用（例：`tests/modules/users/test_service.py` 的停用規則）。

| 要 test-first | 不寫執行期測試 |
|---|---|
| `shared/**`（前後端） | 前端 `modules/*/actions.ts`（薄包裝，型別由 OpenAPI 擋） |
| 前端 `capabilities.ts`、`validation.ts`、`proxy.ts` | 前端 `modules/*/ui/*.tsx`（畫面組裝） |
| 後端 service、router、權限 | route adapter（由 `route-adapters.test.ts` 靜態守住） |

畫面裡真的有分支時，**抽進 `capabilities.ts` 再測**（例：`modules/users/capabilities.ts`）。
不要為了覆蓋率數字補測試。

**不寫的測試**（寫了只是維護成本，帶到新專案就是技術債）：

- 只驗框架或語言本身的行為：React 會渲染 children、`onClick` 會被呼叫、set 不會重複。
- 型別系統或啟動檢查已經保證的：必填欄位有沒有寫、回傳值是不是某個 enum、enum 與權限
  metadata 是否一一對應（`app.registry` 載入時就驗了）。
- 把常數再寫一次的：`assert UNLOGGED_PATHS == {"/health"}` 這類，改值就得同步改測試，
  卻擋不住任何錯；改測它造成的行為。
- 寫死專案目前內容的：「管理區是 `/admin/users`、`/admin/roles`」、「身分來源是 users 模組」。新增或移除
  模組時它會紅，但什麼都沒壞。從啟用清單推導（例：`tests/config/routes.test.ts`）。
- 同一個行為在另一層已經測過的：薄包裝（只是把 A 接到 B）不再各測一次。

## E2E（`e2e/`）

`make check e2e` 另起一套 compose 專案（`<專案>-e2e`，port 預設 3900，可用 `E2E_PORT` 換），
用**正式環境的 image 與 nginx 模板**，以 CLI 建一個隨機密碼的超管，跑完 Playwright 後連 volume 一起刪掉，
開發中的那套不受影響。第一次跑會下載 Chromium（幾百 MB），之後沿用。CI 是獨立的 `e2e` job，
與其他 job 平行跑；失敗時到該次執行的 Artifacts 下載 `playwright-report`，trace 用
`npx playwright show-trace <zip>` 打開。

**只放跨層的 smoke 測試**：proxy 導向、cookie 屬性、Server Action、權限導向、撤銷這類只有整套跑起來才看得到的行為。
畫面分支仍然抽進 `capabilities.ts` 用 vitest 測，不要寫成 E2E（慢，而且畫面一改就要跟著改）。

- 測試名稱與前端一樣用讀得通的中文句子，斷言也用中文文案（`locale: "zh-TW"`）。
- 選元素用 `getByRole`／`getByLabel`，不要用 class 或 DOM 結構。
- 等待用 `expect(...).toBeVisible()`／`toHaveURL()` 這類會自動重試的斷言，**不要寫固定的 sleep**；
  也刻意不開 retries，偶發失敗要修等待條件。
- API 沒有對外開放，測試資料只能從畫面建立，所以同一個檔案裡依序執行（`mode: "serial"`）。

## 寫法

- **後端單元測試**：`tests/modules/conftest.py` 的 `client` fixture 直接打 app，service 與資料表
  方法用 monkeypatch 換掉，不需要資料庫（例：`tests/modules/users/test_routes.py`）。
- **後端 integration 測試**：標 `@pytest.mark.integration`，用 `tests/integration.py` 的
  `require_postgres` 拿資料庫。本機沒資料庫時會 skip（`make check test` 結尾會提醒），
  CI 上 skip 視為失敗。
- **前端**：Vitest + Testing Library。`.server.ts` 一樣能測：`server-only` 在測試裡換成空模組，
  Next 的請求上下文（`cookies`、`headers`、`redirect`）用 `vi.mock` 換掉
  （例：`tests/shared/api/request.server.test.ts`）。

## 架構本身也有測試

| 守什麼 | 在哪 |
|---|---|
| 依賴方向、跨模組只走 public entry | 後端 import-linter（`pyproject.toml`）、前端 dependency-cruiser（`.dependency-cruiser.cjs`） |
| 模組內部用相對路徑、manifest 不用瀏覽器 API | ESLint（`eslint.config.mjs`） |
| client 不可引用 `.server` 檔 | Next.js build（每個 `.server` 檔都 `import "server-only"`） |
| 模組的檔案放置、不准水平分層、測試目錄與原始碼同構 | `apps/web/tests/architecture.test.ts`、`apps/api/tests/test_architecture.py` |
| 每個原始碼目錄都在依賴邊界的掃描範圍裡（`check:architecture`、`root_packages`） | 同上 |
| route adapter 是薄的、Next 特有 export 有接上 | `apps/web/tests/app/route-adapters.test.ts` |
| 路由清單與 `app/` 的頁面兩邊對得上、頁面放在對的區 | `apps/web/tests/config/routes.test.ts` |
| Next 有認到 `proxy.ts` | `make check build`（輸出要有 `ƒ Proxy (Middleware)`） |
| 寫 session cookie 的 action 回傳前經過 `withoutAccessToken` | `apps/web/tests/token-cookie-writers.test.ts` |
| 不用 `NEXT_PUBLIC_*` | `apps/web/tests/runtime-env.test.ts` |
| 後端錯誤不用裸的 `HTTPException` | ruff `TID251`（`pyproject.toml`） |
| 後端 service 回傳 pydantic model（不是 dict）並寫回傳型別 | `apps/api/tests/test_service_returns.py`、mypy `disallow_untyped_defs` |
| compose 只由 `scripts/lib/compose.sh` 呼叫 | `apps/api/tests/test_compose_usage.py` |
| 沒有未使用的匯出 | knip（`npm run check:deadcode`） |
| model 改了有寫 migration | `make check integration` |
| nginx 每個 location 都覆寫用戶端 IP、兩份模板都帶安全標頭 | `apps/api/tests/test_nginx_templates.py` |
| 容器 nginx 只信任私有網段、port 只綁 `127.0.0.1`、主機範例覆寫轉送標頭 | `apps/api/tests/test_nginx_trusted_proxy.py` |
| nginx 與 Next 的上傳上限一致 | `apps/web/tests/next.config.test.ts` |
| nginx 的模板變了 `make start` 會重建 nginx | `apps/api/tests/test_nginx_config_recreate.py` |
| `scripts/` 的 shell 寫法 | shellcheck（`make check lint`） |
| compose 展得開、用到的變數 `.env.example` 都有 | `docker compose config`（`make check lint`） |
| 契約與前端型別是最新的 | `make check contract`（只比對、不改檔） |
| 已發版的 migration 沒有被修改或刪除 | `make check migrate`（`apps/api/tests/test_migration_checks.py`） |
| 部署不會讓資料庫往回、整組都檢查過才部署 | `deploy.yml` 的 `migration-check`（`apps/api/tests/test_migration_checks.py`、`test_deploy_targets.py`） |
| GHCR 只清沒有標籤的版本、清完確認所有標籤都完整、刪除權限只給清理 | `deploy.yml` 的 `cleanup-ghcr`（`apps/api/tests/test_ghcr_cleanup.py`） |
| `make start` 先單獨跑 migrate，失敗不切換服務 | `apps/api/tests/test_stack_scripts.py` |
| api 開機時不寫資料，初始資料由 migrate 寫入 | `apps/api/tests/shared/test_platform.py`、`apps/api/tests/scripts/test_db.py` |
| `shared/` 用到的 CSS 變數都定義在 shared 裡 | `apps/web/tests/shared/ui/tokens.test.ts` |
| `APP_VERSION` 與 CHANGELOG 的版號一致 | `apps/api/tests/test_version.py` |
| 文件的相對連結與錨點有效、原始碼寫的 `docs/….md` 路徑存在、`extending/`、`features/` 與 ADR 都列在索引、`features/` 的開頭與結尾段落、ADR 的取代關係兩邊一致 | `apps/api/tests/test_docs.py`、`test_doc_features.py`、`test_doc_decisions.py`、`test_doc_decision_supersession.py` |
| skills 只有 `.agents/skills/` 一份、`.claude/skills` 是指向它的 symlink、內文不用某一家專屬的工具、只能手動呼叫的兩家設定一致 | `apps/api/tests/test_agent_skills.py` |
| hook 腳本擋下該擋的指令、不誤擋一般指令、`.claude/settings.json` 與 `.codex/hooks.json` 呼叫同樣的腳本 | `apps/api/tests/test_agent_hooks.py` |
| 實作開始後改測試檔要使用者同意、放行只對列出的檔案且有新 commit 就失效、agent 不能繞過確認自己放行 | `apps/api/tests/test_agent_test_guard.py` |
| AI agent 的 commit 帶寫到模型與版本的 `Co-authored-by`、Codex 執行的指令帶 `AI_AGENT` | `.githooks/commit-msg`（`apps/api/tests/test_githooks.py`） |
| PR 標題是 Conventional Commits、描述有摘要／驗證／檢查三段且不是模板原樣 | CI 的 `pr`（`.github/scripts/check-pr.sh`、`apps/api/tests/test_pr_checks.py`） |
| `make init dev` 擋下缺少 `python3` 3.9 以上、`.claude/skills` 不是 symlink，裝了 Codex 卻沒信任專案時提醒；`make init prod` 不做這些 | `apps/api/tests/test_init_agent_setup.py` |
| lock 檔與 `make gen-types` 的產出列在 `.ignore`（AI agent 的搜尋不撞進去） | `apps/api/tests/test_search_ignore.py` |

規則本身見 [`architecture.md`](architecture.md#強制依賴規則)。

## 改程式不改測試

理解需求後先把測試寫好，再開始實作。測試是需求的定義，實作期間改測試等於改需求，所以由人決定。
**單元測試、integration 與 `e2e/` 的 E2E 測試一律適用**，測試用的輔助檔與資料（例如 `e2e/tests/support.ts`、
測試沙盒要複製的檔案清單）也算測試檔：

1. 測試變紅時預設它是對的，先改實作讓它變綠。
2. 真的覺得測試要改（介面改名、斷言本來就寫錯、漏了情境要補）時，**先停下來說明**那個測試驗證的條件、
   沒過的原因，以及為什麼是測試而不是實作要改。
3. 得到同意後才動測試檔，並在 PR 描述寫明**原本那個斷言為什麼是錯的**。

AI agent 由 hook 強制這一條：分支相對 `origin/main` 已經改了 `apps/`、`e2e/` 底下的非測試檔案（實作開始了），
再改測試檔就會停下來等使用者同意（Claude 直接跳確認；Codex 由 agent 執行申請指令、跳確認）。
做法見 [`agent-hooks.md`](extending/agent-hooks.md#測試鎖定)。

紅燈階段用單項指令跑（`uv run pytest tests/ -k xxx`、`npm run test -- -t "名稱"`），
`make check` 要等實作完成、全部轉綠才會過。

## 驗收條件與測試名稱

PR 描述「驗證」段的每條驗收條件後面接一個測試名稱與結果。**寫不出測試名稱的那一條，就是動手前要先問清楚的地方。**

- 前端與 E2E：讀得通的中文句子（`未登入導向 /login`、`登出後其他已登入的裝置也會被登出`）
- 後端：`test_<動作>_<條件>_<結果>`（`test_get_users_without_permission_returns_403`）

驗收條件只寫在 PR，不另寫一份文件或 spec：PR 是動手前討論方向的地方，合併後留下來的是測試名稱，
它會跟著程式一起被執行，文件則會在下一次改動時悄悄過時。

覆蓋率門檻（`pyproject.toml` 的 `fail_under`、`vitest.config.ts` 的 `thresholds`）是**防退步的地板，
不是目標**。

