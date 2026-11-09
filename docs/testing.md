# 測試

```bash
make check test                             # 前後端單元測試（帶覆蓋率；後端平行跑，不含 integration）
make check integration                      # 起拋棄式 PostgreSQL 跑 integration + alembic check
make check e2e                              # 起拋棄式的正式環境，用 Playwright 從瀏覽器跑過整條路
make e2e test <檔案或目錄...>               # 開發中：在常駐的 dev 環境只跑指定的 spec（先 make e2e up）
cd apps/api && uv run pytest tests/ -k xxx  # 只跑後端某些測試
cd apps/web && npm run test:watch           # 前端 watch 模式
```

## 為什麼這樣設計

- **先寫測試，實作期間測試鎖定**：測試是需求的定義，實作期間改測試等於改需求，要由人決定
  （〈[改程式不改測試](#改程式不改測試)〉）。
- **驗收條件只寫在 PR，合併後留下測試名稱**：測試會跟著程式被執行，另寫的 spec 文件會悄悄過時
  （〈[驗收條件與測試名稱](#驗收條件與測試名稱)〉）。
- **測試與原始碼同構，一個模組的測試只放它自己的目錄**：刪模組時測試跟著整包刪；放錯地方的測試不會執行也不報錯，
  所以由架構測試擋（〈[測試放哪裡](#測試放哪裡)〉）。
- **只寫守得住行為的測試**：重寫常數、驗框架行為、寫死專案目前內容的測試只增加維護成本，帶到新專案就是技術債。
- **每個 PR 都跑正式環境的 E2E**：導向、cookie、Server Action 這類行為只有整套跑起來才看得到，壞了也不會報錯；
  開發中改用常駐的 dev 環境只跑相關的 spec（[starter/0009](starter/0009-e2e-strategy.md)）。
- **規則能寫成檢查就寫成檢查**：架構與流程的規則多半由測試守住，文件只留檢查不了的（〈[架構本身也有測試](#架構本身也有測試)〉）。

## 測試放哪裡

**一律放該 app 的 `tests/`，與原始碼同構**（`tests/modules/users/` 對 `modules/users/`、
`tests/shared/auth/test_passwords.py` 對 `shared/auth/passwords.py`）。`tests/` 以外的測試不會執行也不報錯；
對不上原始碼目錄的子目錄由架構測試擋。

- **依賴專案啟用清單的測試**（註冊表、權限覆蓋、每張已註冊資料表的慣例）放後端 `tests/app/`、
  前端 `tests/` 根目錄或 `tests/config/`。
- **一個模組的測試只放它自己的目錄**：刪模組是整包刪 `tests/modules/<name>/`，跨模組的測試會留下來因引用不到而失敗。
- **`tests/shared/` 不綁專案目前的端點與權限**，用與專案無關的路徑（`tests/shared/api/request.server.test.ts`），
  刪模組時才不會跟著壞。
- **從公開函式進入**，不直接測 `_` 開頭的函式：規則有兩個入口時，只測輔助函式證明不了兩邊都套用
  （`tests/modules/users/test_service.py` 的停用規則）。

| 要 test-first | 不寫執行期測試 |
|---|---|
| `shared/**`（前後端） | 前端 `modules/*/actions.ts`（薄包裝，型別由 OpenAPI 擋） |
| 前端 `capabilities.ts`、`validation.ts`、`proxy.ts` | 前端 `modules/*/ui/*.tsx`（畫面組裝） |
| 後端 service、router、權限 | route adapter（由 `route-adapters.test.ts` 靜態守住） |

畫面有分支時**抽進 `capabilities.ts` 再測**（`modules/users/capabilities.ts`）。不為覆蓋率數字補測試。

**不寫的測試**（只增加維護成本，帶到新專案就是技術債）：

- 只驗框架或語言的行為：React 會渲染 children、`onClick` 會被呼叫。
- 型別或啟動檢查已保證的：必填欄位、回傳值是某個 enum、enum 與權限 metadata 一一對應（`app.registry` 載入時驗）。
- 把常數再寫一次的（`assert UNLOGGED_PATHS == {"/health"}`）：改值就要同步改，卻擋不住錯；改測它造成的行為。
- 寫死專案目前內容的（「管理區是 `/admin/users`」）：增刪模組時紅了但沒東西壞。從啟用清單推導（`tests/config/routes.test.ts`）。
- 另一層已測過的：薄包裝不再各測一次。

## E2E（`e2e/`）

`make check e2e` 另起一套 compose 專案（`<專案>-e2e`，port 預設 3900，`E2E_PORT` 可換），用**正式環境的 image 與
nginx 模板**，以 CLI 建隨機密碼的超管，跑完 Playwright 連 volume 一起刪，不動開發中的那套。第一次會下載 Chromium
（幾百 MB）。CI 是獨立平行的 `e2e` job，依檔案分份（matrix 的 `shard`，`E2E_SHARD=<份號>/<總份數>` 轉成
Playwright 的 `--shard`），每份各起一套環境；每份在 Summary 記下 Playwright 本身的秒數。
份數這樣調：每份約 75 秒的固定成本（裝瀏覽器、建 image、起環境）一定要付，總時間約是「固定成本 ＋ 測試時間 ÷ 份數」，
所以一份的 Playwright 秒數接近固定成本時在 matrix 加一份。份數再多也降不到固定成本以下，那時改壓固定成本
（快取瀏覽器、image 只建一次再傳給各份），不加份數（為什麼分份而不加 worker 見
[starter/0009](starter/0009-e2e-strategy.md)）。失敗時到 Artifacts 下載 `playwright-report-<份號>`，
trace 用 `npx playwright show-trace <zip>` 打開。

**開發中用 `make e2e`，不必每次跑 `make check e2e`**（[理由](starter/0009-e2e-strategy.md)）：

| 指令 | 做什麼 |
|---|---|
| `make e2e up` | 起一套這個 checkout 專用的環境：**dev mode**，原始碼直接掛進容器，改了不必重建；已經起著就沿用 |
| `make e2e test <檔案或目錄...>` | 重設資料、重建超管、重啟 api（清掉記憶體裡的登入限流計數），再只跑那幾個 spec；沒給檔案時拒絕，整套用 `make check e2e` |
| `make e2e grep "名稱"` | 同上，只跑名稱符合的測試 |
| `make e2e down` | 拆掉這套環境，連資料一起刪；PR 合併後執行 |

- 每個 checkout（含 worktree）一套：專案名稱取自路徑，port（3901 起找空的）與隨機帳密記在 git 目錄的
  `e2e-stack.env`，不 commit，互不影響。
- 本機 Playwright 只輸出失敗摘要（`dot`）。
- dev 與正式 build 的差異要到 CI 才看得到（CI 的 `e2e` 用正式環境的 image）。
- 失敗時先讀 `e2e/test-results/` 裡該測試的 `error-context.md`，看不出才開 trace。由修的 agent 自己讀，不交給子代理。

**只放跨層的 smoke 測試**：proxy 導向、cookie 屬性、Server Action、權限導向、撤銷這類整套跑起來才看得到的行為。
畫面分支抽進 `capabilities.ts` 用 vitest 測，不寫成 E2E（慢，畫面一改就要跟著改）。

- 名稱用中文句子，斷言用中文文案（`locale: "zh-TW"`）。選元素用 `getByRole`／`getByLabel`，不用 class 或 DOM 結構。
- 用會自動重試的斷言等待（`toBeVisible()`、`toHaveURL()`），**不寫固定 sleep**；不開 retries，偶發失敗要修等待條件。
- **目錄依功能分**：`e2e/tests/<功能>/` 是使用者看得到的功能。有對應模組的用模組名稱（`users/`），停用模組時
  連同目錄一起刪；不屬於模組的照功能取名（`auth/` 登入與權限、`layout/` 版面）。不用技術分層或裝置當目錄。
  跨兩個以上功能的完整流程放 `journeys/`。只跑一個功能：`make e2e test auth/`。
- **一個檔案一條流程或一個子功能**：檔案之間平行（2 個 worker），同檔依序，整套才不會被最大的檔案拖住，
  之後拆 shard 也分得平均。
- **裝置交給 project**：`desktop`（Desktop Chrome）與 `mobile`（Pixel 7）。預設只跑 desktop：兩邊都跑時間加倍，
  同一 IP 的登入次數也加倍。手機上行為不同的（用到 720px 的版面切換或觸控專屬的處理）加 `{ tag: "@mobile" }`
  兩邊都跑，只有手機才有意義的加 `@mobile-only`。不在測試裡用 `test.use` 自己設 viewport。
- **共用準備，不共用結果**：可以共用帳號與登入狀態，不能用別的測試建的資料（一個失敗會連累一串、也不能單獨重跑）。
  建立的資料名稱帶 uuid。
- **登入狀態**：`auth.setup.ts` 讓超管從畫面登入一次並保存，其他測試預設載入；要從未登入開始的用
  `test.use({ storageState: SIGNED_OUT })`。同一 IP 的登入有上限、成功也不歸零（[限流](features/rate-limit.md)），
  所以只有驗證登入流程的測試從畫面登入。
- **帳號**：API 不對外開放，一般帳號用 `support.ts` 的 `createUser()` 從畫面建。每個 worker 共用的 `member`
  **只當身分用**：會登出、改密碼、改權限或停用的測試自己建一個（登出會撤銷該帳號所有裝置的 session）。
- **大功能的完整流程**寫成一到兩個旅程測試（`test.step` 走完整條路），其餘各自準備資料、只驗一個行為。

## 寫法

- **後端單元**：`tests/modules/conftest.py` 的 `client` fixture 直接打 app，service 與資料表方法用 monkeypatch 換掉，
  不需要資料庫（`tests/modules/users/test_routes.py`）。
- **後端 integration**：標 `@pytest.mark.integration`，用 `tests/integration.py` 的 `require_postgres`，
  由 `make check integration` 跑。`make check test` 排除有標記的測試，而且帶 `REQUIRE_INTEGRATION=1`：
  忘了標記、又去連資料庫的測試會失敗，不會被 skip 掉。直接跑 pytest 時本機沒資料庫就 skip。
- **前端**：Vitest + Testing Library。`.server.ts` 也能測：`server-only` 換成空模組，`cookies`、`headers`、`redirect`
  用 `vi.mock` 換掉（`tests/shared/api/request.server.test.ts`）。

## 架構本身也有測試

| 守什麼 | 在哪 |
|---|---|
| 依賴方向、跨模組只走 public entry | 後端 import-linter（`pyproject.toml`）、前端 dependency-cruiser（`.dependency-cruiser.cjs`） |
| 模組內部用相對路徑、manifest 不用瀏覽器 API | ESLint（`eslint.config.mjs`） |
| client 不可引用 `.server` 檔 | Next.js build（每個 `.server` 檔都 `import "server-only"`） |
| 模組的檔案放置、不准水平分層、測試目錄與原始碼同構 | `apps/web/tests/architecture.test.ts`、`apps/api/tests/test_architecture.py` |
| 後端 `public.py` 不轉出 ORM 類別或 `Table` | `apps/api/tests/test_architecture.py` |
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
| 文件的相對連結與錨點有效、原始碼寫的 `docs/….md` 路徑存在、`extending/`、`features/` 與 ADR 都列在索引、`features/` 的開頭與結尾段落、ADR 的取代關係兩邊一致、`starter/` 的段落固定且只寫現況、推翻的模板決定列在索引 | `apps/api/tests/test_docs.py`、`test_doc_features.py`、`test_doc_decisions.py`、`test_doc_decision_supersession.py`、`test_doc_starter.py` |
| skills 只有 `.agents/skills/` 一份、`.claude/skills` 是指向它的 symlink、內文不用某一家專屬的工具、只能手動呼叫的兩家設定一致 | `apps/api/tests/test_agent_skills.py` |
| hook 擋下確認點、不誤擋一般指令、`.claude/settings.json` 與 `.codex/hooks.json` 呼叫同樣的腳本 | `apps/api/tests/test_agent_hooks.py` |
| 實作開始後用改檔工具改測試檔要使用者同意、放行只對列出的檔案且有新 commit 就失效、不能自己寫放行 | `apps/api/tests/test_agent_test_guard.py` |
| 有開著的 PR 時開新分支要使用者同意、放行針對分支名稱 | `apps/api/tests/test_agent_one_pr.py` |
| 改防線檔案（hook、agent 設定、CI、檢查的設定）一律要使用者同意、清單裡的路徑都存在 | `apps/api/tests/test_agent_protected_files.py` |
| 沒有收尾前的 Stop hook、開工時提示現況、每個 hook 用 `PATH` 上的 `python3` 跑得起來 | `apps/api/tests/test_agent_session_hooks.py` |
| AI agent 的 commit 帶寫到模型與版本的 `Co-authored-by`、Codex 執行的指令帶 `AI_AGENT` | `.githooks/commit-msg`（`apps/api/tests/test_githooks.py`） |
| PR 標題是 Conventional Commits、描述有摘要／驗證／檢查三段且不是模板原樣 | CI 的 `pr`（`.github/scripts/check-pr.sh`、`apps/api/tests/test_pr_checks.py`） |
| 新增的抑制註解有理由 | CI 的 `pr`（`.github/scripts/check-pr-changes.py`、`apps/api/tests/test_pr_change_checks.py`） |
| `make init dev` 擋下缺少 `python3` 3.9 以上、`.claude/skills` 不是 symlink，裝了 Codex 卻沒信任專案時提醒；`make init prod` 不做這些 | `apps/api/tests/test_init_agent_setup.py` |
| lock 檔與 `make gen-types` 的產出列在 `.ignore`（AI agent 的搜尋不撞進去） | `apps/api/tests/test_search_ignore.py` |

規則本身見 [`architecture.md`](architecture.md#強制依賴規則)。

## 改程式不改測試

先寫測試再實作。測試是需求的定義，實作期間改測試等於改需求，由人決定。單元、integration、E2E 都適用，
輔助檔與資料（`e2e/tests/support.ts`、測試沙盒要複製的檔案清單）也算測試檔：

1. 測試變紅時預設它是對的，先改實作讓它變綠。
2. 真的覺得測試要改（介面改名、斷言本來就寫錯、漏了情境要補）時，**先停下來說明**那個測試驗證的條件、
   沒過的原因，以及為什麼是測試而不是實作要改。
3. 得到同意後才動測試檔，並在 PR 描述的「驗證」段寫一行：測試檔的路徑，同一行寫明**原本那個斷言為什麼是錯的**。

AI agent 這一側：實作開始後用改檔工具改測試檔，hook 會停下來等使用者同意；用 shell 改不攔，靠 agent 自律與
審查時看 diff 裡的測試檔（[做法](extending/agent-hooks.md#測試鎖定)）。

紅燈階段用單項指令跑（`uv run pytest tests/ -k xxx`、`npm run test -- -t "名稱"`、
`make check integration <測試檔>`）。完整的檢查只在 CI 跑，要等實作完成、全部轉綠才會過。

## 驗收條件與測試名稱

PR 描述「驗證」段的每條驗收條件後面接一個測試名稱與結果。**寫不出測試名稱的那一條，就是動手前要先問清楚的地方。**

- 前端與 E2E：讀得通的中文句子（`未登入導向 /login`、`登出後其他已登入的裝置也會被登出`）
- 後端：`test_<動作>_<條件>_<結果>`（`test_get_users_without_permission_returns_403`）

**只改 Markdown 的 PR**（界線同 CI 的 [docs 模式](workflow.md#提交與-ci)）沒有可執行的行為，驗收條件不接測試名稱，
改寫成可檢查的結果：哪個 CI job 通過、diff 裡看得到什麼（例：`api-test` 的連結檢查通過、`AGENTS.md` 與 skill
的說法一致）。一樣先給使用者確認；不寫測試，也不要為了湊測試名稱寫斷言文件內容的測試。
只要有一個非 `.md` 檔（設定、CI、相依），就照上面的規則。

AI agent 寫完驗收條件要**先列給使用者確認才寫測試**，方向已在對話談定也一樣：從「要做什麼」轉成「怎麼證明做到」
最容易漏情境、多加條件或擴大範圍。這時改幾行字就好，寫完才發現就是整個 PR 重來；測試鎖只保證測試沒被偷改，
保證不了一開始就寫對。

驗收條件只寫在 PR，不另寫 spec：合併後留下的是測試名稱，會跟著程式被執行，文件則會悄悄過時。

覆蓋率門檻（`pyproject.toml` 的 `fail_under`、`vitest.config.ts` 的 `thresholds`）是**防退步的地板，不是目標**。

