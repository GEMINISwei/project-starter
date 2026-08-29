# API 契約

`openapi.json` 是後端對外承諾的介面，也是前端 entity 型別的**唯一來源**。

```text
apps/api/modules/*/schema.py + app/permissions.py
        │  make gen-types（第一步：export_openapi.py）
        ▼
contracts/openapi.json                              ← 契約本體，要 commit
        │  make gen-types（第二步：openapi-typescript）
        ▼
apps/web/shared/api/generated/schema.d.ts           ← 產出物，也要 commit
        │  re-export
        ▼
apps/web/shared/api/entities.ts                     ← 跨模組共用的 entity 來源
```

## 為什麼這份 JSON 要進版控

為了讓**「後端動了對外介面」在 code review 當下就看得見** —— 一個 `schema.py` 的改動會不會
影響呼叫端，看 diff 裡有沒有 `contracts/openapi.json` 最直接。把它當成中繼檔忽略掉的話，
這件事只有 CI 的 `api-types-up-to-date` job 會講，而那時 PR 已經寫完了。

代價是每次改 schema 都會多一個檔案的 diff。這是刻意付的。

## 什麼時候要重產

改過任何 `schema.py`、`app/permissions.py`，或任何會進 OpenAPI 的 docstring 之後：

```bash
make gen-types
```

不跑的話 CI 的 `api-types-up-to-date` job 會紅燈，而且前端拿到的是舊型別 ——
錯誤會從編譯期延到執行期。

## 為什麼不是 `packages/`

`packages/` 保留給真正跨 app 可重用的 **library**（有自己的 package.json、被多個 app import）。
這裡放的是一份資料檔加上它的產生規則，不是 library。目前這個 repo 還沒有任何東西
符合 `packages/` 的條件，所以那個目錄刻意不存在 —— 空資料夾只會招來「順手放點東西進去」。

## 出現第二份契約時

目前這裡只有一份契約，也刻意不先開 `openapi/` 之類的子目錄把它包起來（理由同上一節）。
真正防止這裡變亂的是下面這幾條規則，不是目錄結構。

**什麼夠格放進來**：由某一端產生、被另一端消費、而且**有自動產生規則**的資料檔。
手寫的型別不算（所以 `WsEvent` 信封留在 `entities.ts`，見下一節）；
有自己 `package.json` 的可重用 library 也不算（那是 `packages/` 的事）。

**怎麼命名**：以**協定／傳輸層**區分，不要以「api」區分 —— 這裡的東西全部都是 api，
`api-` 這個前綴不帶任何資訊。所以 WebSocket 的正式規格叫 `ws-asyncapi.json`，
不叫 `api-asyncapi.json`；HTTP 這份就維持 `openapi.json`。

**平鋪優先**：一份契約一個檔就放平層，名字自帶區分就夠了。只有當**單一**契約需要多個檔
（spec + 專屬的產生腳本 + 自己的說明）才開子目錄 —— 而且那時要連 `openapi.json` 一起搬進去，
不要一半平鋪一半巢狀。

**要改路徑的話**，真正的路徑只有一個地方：`scripts/lib/common.sh` 的 `CONTRACT` 與 `WEB_SCHEMA`。
改那兩行就好，`gen-types` 的兩個步驟都從它們展開。

改完之後**一定要跑一次 `make gen-types`**。原因是路徑打錯屬於「安靜地錯」那一類：

- `export_openapi.py` 刻意不建立上層目錄，所以目錄部分打錯會當場失敗。
- 但檔名打錯仍會寫成功，只是落在別的地方。這種情況 CI 的 `api-types-up-to-date` job **看不見** ——
  它比對的是原本那兩個檔，而它們沒被動到，`git diff --exit-code` 反而是綠的。
  所以 `gen-types` 跑完會自動叫一次 `make check-contracts`，用「有沒有未進版控的產出物」
  把它抓出來。同樣的招數也用在 compose 的路徑上（`scripts/check-compose.sh`）。

剩下的是文件與檢查器裡的指路，不影響行為但會誤導人：

- `.github/workflows/ci.yml` 的 `api-types-up-to-date` job：`git diff` 的路徑與錯誤訊息
- `.gitignore` 那段註解 —— 它點名這個路徑，是防止有人把它加回忽略清單的守衛
- `docs/extending.md`、`AGENTS.md` 裡的指路
- `apps/web/package.json` **不該**出現 `gen-types` script（那裡有一段 `//scripts` 說明為什麼）
- `CHANGELOG.template.md` 已發布版本的條目**不要改**，那是當時的紀錄

## 這裡刻意**沒有**的東西

`WsEvent`（WebSocket 訊息的信封格式）不在這份契約裡。WebSocket 訊息不經過 HTTP，
所以永遠不會進 OpenAPI，`make gen-types` 幫不上忙。它是手寫在
`apps/web/shared/api/entities.ts`。

**但「不能從 OpenAPI 產生」不等於「不能被檢查」。**
`apps/web/tests/shared/api/ws-event-contract.test.ts` 會讀後端的
`modules/realtime/schema.py`，比對兩邊的欄位名 —— 改了一邊沒改另一邊會紅燈。
它只比對**欄位名**，型別仍然靠人（那需要一個 Python 型別解析器，成本遠高於它防到的錯）。

這是「讓重複變成**可驗證**的重複」在這個 repo 的第三次應用，另外兩次都在
`check-tokens.mjs`：`ICON_SIZE`／`DROPDOWN_WIDTH` 的 JS／CSS 成對數字，
以及 PWA manifest 的 `theme_color` 對主題底色。
