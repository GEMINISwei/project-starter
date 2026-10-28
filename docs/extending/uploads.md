# 上傳檔案

上傳的檔案（圖片、影片、文件）一律存在 api 的 **`/app/uploads/<模組>/`** 底下，例如
`/app/uploads/products/`。那裡掛的是 uploads volume，`make backup` 備份的就是它
（見 [`operations.md`](../operations.md#備份與還原)）。

- **存到別的路徑不會有任何錯誤**：上傳、讀取都正常，但容器一重建檔案就消失，備份裡也不會有。
- 一個模組一個子目錄，不要每個模組開自己的 volume：多一個 volume 就要多改一次 compose 與備份腳本。
- 資料庫裡存**相對於 `/app/uploads` 的路徑**（`products/<id>.jpg`），不存絕對路徑：之後換掛載點或改用
  物件儲存時，資料不用跟著改。
- 檔名由後端產生（例如 id），不要直接用使用者給的檔名：可能撞名，也可能帶 `../`。

## 大小上限

整個請求（檔案加上其他欄位）**固定上限 16MB**，不開放設定：nginx 的 `client_max_body_size` 與 Next 的
`serverActions.bodySizeLimit` 都是這個值（`apps/web/tests/next.config.test.ts` 確保兩邊一致）。
它只是防護用的天花板，超過時使用者只會看到一般錯誤，**看不到說明**。所以每個上傳功能都要自己決定上限：

- **上限寫成功能裡的常數**（例如大頭貼 2MB），不要做成環境變數。
- **以後端的檢查為準**：超過時回傳 `LangText` 錯誤訊息（見〈[語系](i18n.md)〉）。
- **前端送出前也檢查一次**：選了檔案就比對大小，不必等整個檔案傳完才被拒絕。
- 功能的上限要**小於 16MB**，並預留其他欄位與 multipart 編碼的空間。

**需要超過 16MB 的檔案（影片、大型壓縮檔）時，不要把天花板調高**：Server Action 會把整個 body 讀進
web 容器的記憶體，轉送到後端時又多一份，而正式環境的 web 只有 512MB。這時改用串流上傳（在 nginx
為該端點開一條專屬 location 直接轉到 api），或用物件儲存的 presigned URL 讓瀏覽器直傳。

前面有主機的 reverse proxy 時，它的 `client_max_body_size` 不能小於 16MB（nginx 預設只有 1MB），
否則超過的請求在主機那層就被擋下。
