# 給 AI agent 的專案指引

這是給 AI agent 的**唯一**指引（不另設 `CLAUDE.md`）。只寫無法從程式碼推導的規則，細節見：
[`architecture.md`](docs/architecture.md)（依賴規則、模組介面）、
[`development.md`](docs/development.md)（指令、測試、風格）、
[`extending.md`](docs/extending.md)（新增模組／權限／migration／i18n）、
[`operations.md`](docs/operations.md)（部署、Session、限流）。

## 硬規則（`make check` 會擋）

1. **跨模組只走 public entry**：前端 `public.server.ts`／`public.client.ts`，後端 `public.py`。組裝層也一樣。
2. **`shared/` 不可引用 `modules/` 或組裝層，也不可認識業務**：不寫具體的業務端點與 entity，
   `tests/shared/` 不碰 `app`／`modules`。shared 要能整包複製到別的專案（`make check portable` 擋，
   [說明](docs/architecture.md#shared-的可移植性)）。
3. **模組內部一律相對路徑**，`@/` 只用於跨層。
4. **UI kit 只從 `@/shared/ui` 匯入**，不可指進子路徑。需要 kit 的樣式時在 kit 裡多包一個元件。
5. **前端模組**：模組根放資料與規則，`ui/` 放畫面，不要開 `components/`、`hooks/`、`utils/`。
   必備 `manifest.ts`、`i18n.ts` 與至少一個 public entry。
6. **後端 service 回傳建構好的 pydantic model**（不是 dict），而且一定要寫回傳型別註記。

完整規則見 [`architecture.md`](docs/architecture.md#強制依賴規則)。

## 寫程式

- **開發流程：Feature Branch → Draft PR → Incremental Commits → Code Review → Squash Merge**。
  不直接 push `main`；PR 標題用 Conventional Commits，因為 squash 後它就是 `main` 的 commit
  （[說明](docs/development.md#開發流程)）。
- **PR 描述固定三段：摘要、驗證（成功失敗都寫）、檢查（給審查者的 checkbox）**。
  `gh pr create --body` 會跳過 [`PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md)，
  自己帶內文時也照這三段；之後推新 commit 要回頭補摘要與驗證。
- **每個 commit 最後加 `Co-authored-by: <產品> <模型與版本> <email>`**（例：`Claude Opus 5.5 <noreply@anthropic.com>`），
  email 用工具官方的值，沒有時用 `noreply@<廠商網域>`（[說明](docs/development.md#ai-協作的共同作者)）。
- **動手前先寫驗收條件，每條對應一個測試名稱**；寫不出測試名稱的那條就是要先問清楚的地方
  （[說明](docs/development.md#驗收條件與測試名稱)）。
- **先寫測試，寫好才開始實作**，不要邊寫功能邊改測試。`actions.ts` 與 `ui/*.tsx` 不寫執行期測試；
  畫面有分支時抽進 `capabilities.ts` 再測。不要為了覆蓋率數字補測試。
- **測試放該 app 的 `tests/`，與原始碼同構**（架構測試擋），一個模組的測試只放它自己的目錄。
  放在 `tests/` 以外不會執行也不會報錯。
- **實作期間測試檔鎖定**：測試變紅時預設它是對的，改實作讓它變綠。要動測試檔（改斷言、刪測試、
  補新測試）之前，先向使用者說明那個測試驗證的條件與沒過的原因，**得到同意才改**
  （[說明](docs/development.md#改程式不改測試)）。
- **CSS 只用設計變數**（名字與預設值在 `shared/ui/styles/tokens.css`，專案在 `app/theme.css` 覆寫），
  不寫死色值或尺寸（`style={{…}}` 也一樣）。
- **使用者看得到的字串都要中英兩份**，放在擁有它那一層的 `i18n.ts`（[說明](docs/extending.md#語系i18n)）。
- 不留未使用的匯出（knip 擋）；行長、函式長度、複雜度有上限（lint 擋）。
- 註解寫**為什麼**，不寫做了什麼；演進過程寫進 commit message。
- **程式碼裡的註解與 docstring 用半形標點**（`, : ; ( )`，後面空一格），全形的會被編輯器標成易混淆字元。
  字串與 Markdown 維持全形（[說明](docs/development.md#註解與文件)）。

## 改完之後

| 改了什麼 | 要做 |
|---|---|
| 任何程式碼 | `make check` |
| model 的欄位、索引、約束 | `make db migration "說明"`，讀過產出，再 `make check integration` |
| 跟資料庫互動的後端程式 | `make check integration`（`make check` 裡 integration 會 skip） |
| 後端 schema、權限、語系 | `make gen-types`，兩份產出一起 commit |
| 發版（跟 tag 對齊的只有 `APP_VERSION` 與 CHANGELOG） | `make release <版號>`，不要手動改；`package.json`、`pyproject.toml`、lock 檔與 OpenAPI 的 `info.version` 不跟發版（[說明](docs/operations.md#自動部署)） |
| 環境變數 | `.env.example`、compose、讀取端（後端 `app/config.py`／前端 `shared/runtime/`）；要詢問或自動產生的才動 `scripts/init.sh`（[說明](docs/development.md#環境變數的同步點)） |
| nginx 模板 | 每個 `proxy_pass` 的 location 都要 `include` `snippets/proxy-headers.conf`（測試會擋） |
| 行為有變 | `CHANGELOG.md` 的 `## [Unreleased]` 留一筆 |

相依升級遇到 peer 阻擋時停在最新的相容版並寫下移除條件，不要 `--force`／`--legacy-peer-deps`。

## 漏了不會報錯的地方

- **route adapter 要逐一轉接 Next 特有的 export**（`generateMetadata` 等），漏掉沒有錯誤訊息：

  ```tsx
  import { XPage, generateXMetadata, type XPageProps } from "@/modules/x/public.server"
  export const generateMetadata = generateXMetadata
  export default function Page(props: XPageProps) { return <XPage {...props} /> }
  ```

- **新增有導覽的模組**：漏了 `config/routes.ts` 的 `ENABLED_MODULES` → 沒有導覽也沒有 proxy 保護；
  漏了 route adapter → 側欄連結 404；放錯區（`(user)/`／`admin/`）→ 套到錯的外殼（測試會擋）。
- **`Permission` 與 `Language` 刻意中央化**，不要改成動態組裝。`/languages/` 端點是為了讓 enum
  進 OpenAPI，看起來沒人呼叫也不能刪。
- **權限的顯示標籤與分類只寫在後端**（各模組 `permissions.py` 的 `PermissionSpec`），前端不另存一份。
- **route function、pydantic model、enum 的 docstring 會進公開 API 文件**，內部說明寫在一般註解。
- **Server Action 的回傳值會送進瀏覽器**：簽發 token 的 action 回傳前要經過 `withoutAccessToken`。
- **上傳的檔案存在 `/app/uploads/<模組>/`**：存到別的路徑不會報錯，但重建容器就消失、`make backup` 也備份不到
  （[說明](docs/extending.md#上傳檔案)）。
- **上傳的請求固定上限 16MB，不開放設定**：超過時使用者只看到一般錯誤，所以每個上傳功能要自己定上限，
  後端回傳 `LangText` 錯誤、前端送出前先檢查；需要更大的檔案時改用串流或直傳，不要調高上限
  （[說明](docs/extending.md#大小上限)）。
- **後端直接送到畫面的文字**也要走 `LangText` + `resolve_text()`。
- **不要用 `NEXT_PUBLIC_*` 放部署設定**（build 時就烤死），執行期設定走 `shared/runtime/`。
- **compose 的 nginx 信任主機 reverse proxy 送來的 `X-Real-IP` 與 `X-Forwarded-Proto`**：port 只能綁 `127.0.0.1`（例外只有開發機的 `make start lan`），
  主機那層要覆寫這兩個標頭，少了任何一邊，限流與 cookie 的 `Secure` 都會出錯，而且不會報錯
  （[說明](docs/operations.md#主機的-reverse-proxy)）。
- **`apps/web/proxy.ts` 不能搬**，放錯位置路由保護會安靜消失；`npm run build` 輸出要有 `ƒ Proxy (Middleware)`。
- **新增原始碼目錄**要加進 `apps/web/package.json` 的 `check:architecture`（掃描目錄）與
  `apps/api/pyproject.toml` 的 `root_packages`，否則那一層不受邊界規則管。
- **compose 旗標不要自己組**，一律用 `scripts/lib/compose.sh`。
- **新增 make 指令**要加 `scripts/<name>.sh` 並把名稱加進 Makefile 的 `TARGETS`。
