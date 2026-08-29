import { expect, test } from "@playwright/test"

/**
 * **範例模組的 e2e。整包刪 items 時這個檔案一起刪**
 * （清單見 docs/architecture.md 的「移除 module」）。
 *
 * 它守兩條這個 repo 裡最沒人測到的接縫，兩條都是「型別由後端產生、前端消費」的架構
 * 才有的縫 —— `api-types-up-to-date` job 證明兩邊的**型別**對得上，
 * 證明不了兩邊的**行為**接得起來：
 *
 *   接縫三：WebSocket 事件真的從後端流到前端畫面。後端測過事件與訊息、前端測過
 *           窮盡處理，中間那段沒有任何測試。
 *   接縫四：跨前後端的 i18n。切成英文之後，**後端送來的**那句話要跟著變 ——
 *           斷言的文字（`Created item “…”`）只有後端產得出來，前端字典裡沒有這一句
 *           （見 apps/api/modules/items/service.py 的 ITEM_CREATED_MESSAGE）。
 */

const ITEM_NAME = `e2e-item-${Date.now()}`

test("建立項目後，列表出現它，而且收得到後端送來的 WebSocket 通知", async ({ page }) => {
  await page.goto("/items")

  await page.getByRole("button", { name: "新增項目" }).click()
  await page.getByLabel("名稱").fill(ITEM_NAME)
  await page.getByRole("button", { name: "建立" }).click()

  // 列表刷新（Server Action 帶 refresh）。**要指名表格欄位**，不能用裸的
  // `getByText(ITEM_NAME)` —— 下面那則 toast 的文字也含項目名稱，兩者同時在畫面上時
  // 會命中兩個元素而觸發 strict mode violation。誰先到是 Server Action 與 WebSocket
  // 的競態：headless 夠快，斷言通常在 toast 之前就跑完，所以這個雷平常不會炸。
  await expect(page.getByRole("cell", { name: ITEM_NAME })).toBeVisible()

  // WebSocket 那條路：訊息由後端組好（含項目名稱）再推過來。
  await expect(page.getByText(`已建立項目「${ITEM_NAME}」`)).toBeVisible()
})

test("切成英文之後，後端送來的通知文字跟著變成英文", async ({ page }) => {
  // 語系選單是原生 select，ariaLabel 是「顯示語言」（modules/settings/ui/LanguageSettings.tsx）。
  await page.goto("/settings")
  await page.getByLabel("顯示語言").selectOption("en")
  await expect(page.getByLabel("Display language")).toBeVisible()

  await page.goto("/items")
  await page.getByRole("button", { name: "New item" }).click()

  const englishItem = `${ITEM_NAME}-en`
  await page.getByLabel("Name").fill(englishItem)
  await page.getByRole("button", { name: "Create" }).click()

  // 這句話前端字典裡沒有 —— 它只可能來自後端的 ITEM_CREATED_MESSAGE。
  // 語系沒有傳到後端、或後端沒有走 resolve_text 時，這裡會看到中文而失敗。
  await expect(page.getByText(`Created item “${englishItem}”`)).toBeVisible()
})
