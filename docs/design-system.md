# 設計 token 與樣式層

樣式怎麼分層、token 住在哪、什麼東西由檢查器擋。**依賴邊界與 UI kit 的介面規則**在
[`architecture.md`](architecture.md)，**新增頁面的步驟**在 [`extending.md`](extending.md)，
這裡只講 token 與 CSS。

這一層的存在理由是**換得起**：設計端（Claude Design 之類的 Design System）會整批更新
token，而 CSS 的 `var()` 找不到變數時**不會報錯，只會沒有樣式**。所以規則的重點不是
「好看」，而是讓上游一改，這邊立刻拿得到一份完整的失效清單。

## 三層 token

| 層 | 檔案 | 誰說了算 | 內容 |
|---|---|---|---|
| 原始值 | `apps/web/app/tokens/primitives.css` | **設計端**（接外部 DS 時變成對照表，見下面「導入外部 Design System」） | `--ds-*`：色票、間距、字級、圓角、陰影、動態。只有值，沒有用途 |
| 語意 | `apps/web/app/tokens/semantic.css`、`apps/web/app/themes/*.css` | **名字由模板定，值由專案定** | `--color-*`、`--space-*`、`--fs-*`、`--z-*`…：把原始值對應到用途 |
| 元件 | 各 `*.module.css` 自己 | 元件作者 | 只服務單一元件的變數，就近宣告 |

中間那列的分工是整個設計的重點：`shared/ui` 的樣式只認語意層的那組**名字**，
所以換一套色票＝只改右手邊的對應，UI kit 一行不用動；而改名字會讓 UI kit 的樣式
當場掉一半（`check:tokens` 規則 a 會擋下來）。

分成三層是為了讓「DS 換一批值」只動最底層與中間層的對照，**各 CSS module 的呼叫點
一行不用改**。所以：

- **語意層的名字照用途取，不照長相取**（`--fs-base` 而不是 `--fs-15`）。名字一旦帶了
  值的資訊，換值時連名字都要改，這一層就白做了。
- **原始層只有 token 定義檔可以引用**。模組或 UI kit 直接用 `--ds-*` 等於繞過對照表，
  換值時會被漏掉 —— 規則 d 會擋。

顏色住在 `themes/*.css` 而不是 `semantic.css`：它是唯一會隨主題變動的類別。

## 主題：一份，深色

**這個模板只有一份主題 `default`，色調是深色的灰／靛藍，而且沒有明暗兩軌。**
每個 `--color-*` 只有一個值；`app/tokens/semantic.css` 的 `color-scheme` 固定成 `dark`。

`color-scheme` 不能省 —— 原生表單控制項與捲軸只認它。少了它，深色底上的 `<select>`
與捲軸會維持亮色，那是最容易漏掉的一半。

**沒有 `light-dark()`，也沒有 `data-scheme` 切換。** 一個 token 兩個值的寫法只在
「同一份主題要支援明暗」時才需要；這裡不支援。**要第二種色調就是多一份主題**
（見下一節），那樣兩套色票各自完整、也各自看得出來。

主題機制本身留著：`<html data-theme="…">` 由 `apps/web/config/theme.ts` 的 `DEFAULT_THEME`
決定，清單目前只有一個成員。留著它是因為**導入外部 DS 的整套流程就是「多一份主題」**——
機制在，導入時只要加檔案，不必先把機制裝回來。

**可讀性由測試釘住**（[`tests/app/themes/contrast.test.ts`](../apps/web/tests/app/themes/contrast.test.ts)）：
它把 token 的 `var()` 與 `color-mix()` 解析成實際色值再算 WCAG 對比 —— 文字要 4.5:1，
控制項邊界與 focus 外環要 3:1。**`app/themes/` 底下每多一份主題就多跑一輪同一組門檻**，
所以導入 DS 的新主題一放進去就被涵蓋，不必記得補測試。

**一種文字對一種表面各問一次**，不是只問最常見的那一組。深色底上表面愈亮對比愈緊，
所以同一種文字在不同表面上的差距可以跨過門檻：輔助文字對 `--color-surface-card` 是
4.57:1（過），疊在 `--color-surface-raised` 上就是 4.17:1（不過）。四種表面都要問。
深色底最容易出事的正是這幾處（把輔助文字調暗一階、把邊框調淡一階，看起來都「比較精緻」，
然後就低於門檻了），所以**換色票時先跑它**，不要只靠眼睛。

這也是為什麼主題把「連結與強調用的品牌色」（`--color-primary`）與「實心按鈕的底色」
（`--color-action-primary`）分成兩個 token：深色底上好看的亮靛藍撐不起白字，
實心行動要更深的兩階才過得了 4.5:1。

## 主題是一個介面

`shared/ui` 與所有模組的 CSS 只認 `--color-*` 這組名字。**一份主題就是那組名字的一份
實作** —— 用哪條調色線、每個顏色挑哪一階，是那份主題自己的事。

介面的定義檔是 [`app/themes/default.css`](../apps/web/app/themes/default.css)：
它宣告的那組 `--color-*` 就是契約本身。這裡不抄一份名單 —— 抄了就會漂。

**加一份主題＝複製那個檔案，選擇器改成 `:root[data-theme="<名字>"]`，只換右手邊**，
再把名字登記到 `config/theme.ts` 的 `ThemeName`、**兩個進入點**（`app/layout.tsx` 與
`app/global-error.tsx`）的 import，以及 `DEFAULT_THEME`。三條保證都有檢查器：

| 保證 | 漏了會怎樣 |
|---|---|
| 每份主題宣告**同一組** `--color-*` | 少的那個會**靜靜沿用 `default` 的值**（`default` 宣告在 `:root`，其他主題在 `:root[data-theme]`）—— 新主題裡出現一塊舊色 |
| 值由 `--ds-*` 撐著，不自己帶值 | 原始值藏進主題層，DS 到位時那個顏色沒有槽位可接 |
| 檔案、`ThemeName`、**兩個進入點**的 import 一致 | `data-theme` 靜靜沒有作用；只漏了 global-error 的話，錯誤頁會安靜地維持原本的配色 |

**調色線不是介面。** 多一份主題就多一條調色線，兩條線的階數**不必對齊** ——
DS 的色票本來就不會照著這裡的階數走，硬要求對齊只會逼新主題去遷就舊主題的階。
新主題也可以在同一個 token 裡混用兩條線的階。對齊只發生在名字這一層。

## 檢查器擋什麼

`npm run check:tokens`（`apps/web/scripts/check-tokens.mjs`，已掛在 `npm run lint` 裡）。
它是 `check-boundaries.mjs` 的 CSS 對應物，測試在 `apps/web/tests/scripts/check-tokens.test.ts`。

| | 規則 |
|---|---|
| a | `var(--x)` 引用的 token 必須有人宣告 —— 擋幽靈 token（有 fallback 也一樣擋） |
| b | token 定義檔宣告的 token 必須有人引用 —— 擋死 token |
| c | token 定義檔以外不可出現裸色值（hex／`rgb()`／`hsl()`／`oklch()` 那一組色彩函式） |
| d | token 定義檔以外只能引用語意層，不可碰 `--ds-*` |
| e | `composes:` 不可跨出 `shared/ui/styles/` |
| f | `*.module.css` 的 class 必須有 TSX 引用 —— 擋死 CSS |
| g | media query 的斷點必須在允許清單內 |
| h | TSX 的 `styles.x` 必須真的存在於它 import 的那份 CSS module |
| i | 節奏類屬性（間距、字級、圓角、邊框）不可寫死 px；尺寸屬性的算式裡也一樣 |
| j | 不可用 `-var(…)` 取負 —— 那是無效 CSS，整條宣告會被安靜丟掉 |
| k | 語意層的 token 必須由 `--ds-*` 撐著，不可自己帶值 |
| l | focus 外環要整條用 `var(--focus-ring)`，不可自己組 |
| m | JS 與 CSS 各存一份的數字（`ICON_SIZE`、`DROPDOWN_WIDTH`）必須相等 |
| n | vendor 的原生命名只能在 `app/tokens/primitives.css` 對照 |
| o | vendor 不可宣告這個 repo、或另一套 DS 已有的 token 名字 |
| p | CSS 不可用 `@import` 拉外部資源（字型走 `next/font`） |
| q | `ThemeName`、`app/themes/*.css`、**每個進入點**的 import 必須是同一組 |
| r | 每份主題都要宣告同一組 `--color-*` |
| s | `app/tokens/` 底下的每份 CSS 都要被**每個進入點** import —— 擋沒接上的 token 檔 |
| t | 行內樣式（`style={{…}}`）不可寫死色值與節奏類數字 —— 規則 c 與 i 的 TSX 對應物 |
| u | PWA manifest 的 `theme_color` 必須等於預設主題的 `--color-bg-app` |
| v | 元件層的自訂屬性只能在宣告它的那個檔案裡引用 —— 要跨檔共用請升上語意層 |

**字母只是這張表的行把手**，給這份文件、`check-tokens.mjs` 與它的測試互相指路用 ——
那三個檔案裡表就在眼前。**其他任何地方要提某條規則，請直接敘述它擋什麼**，不要寫字母：
讀的人手邊沒有這張表，而且檢查器回報違規時也從不印字母。

**規則 t 與 u 守的是 CSS 以外的兩個出口。** 規則 c 與 i 的輸入都是 `.css`，所以顏色與尺寸
有兩條路可以繞出去：

- **`style={{…}}`**（規則 t）—— `style={{ padding: 24, minHeight: 44 }}` 在 TSX 裡是合法的，
  而且完全不經過 CSS 那一側的任何規則。屬性範圍與規則 i **完全一致**，刻意不擴充：
  兩側認的屬性一旦不同，就是同一條規則的兩份定義。
- **`app/manifest.ts` 的 `theme_color`**（規則 u）—— PWA manifest 是 JSON，吃不到 `var()`，
  所以那個顏色只能是字面值。導入 DS 換掉整組 `--color-*` 之後它不會跟著動，
  而症狀只出現在裝了 App 的人的啟動畫面與狀態列上。規則 u 把 `--color-bg-app` 的
  `var()` 鏈解到字面值再比對。

**規則 v 守的是分層在 CSS 那一半。** 規則 a 的「有沒有人宣告過」是一個**不分檔案**的
全域集合，所以任何模組 CSS 宣告的自訂屬性，都能滿足任何其他檔案的 `var()`。
少了它，`shared/ui` 的 CSS 可以用著 `config/shell` 宣告的 `--sidebar-width` 而全程沒有紅燈
—— 那是硬規則 4（`shared/` 不可引用組裝層）在 CSS 這一側的漏洞，而症狀是安靜的：
kit 渲染在 `.shell` 之外時 `calc()` 解不出來，整條宣告被瀏覽器丟掉。
**要跨檔共用就升上語意層**（`--layout-sidebar-width`、`--layout-bottom-nav-height`
都是這樣來的）；元件層的自訂屬性留在自己的檔案裡。

規則 i 也管**自訂屬性的值**。少了這一半，`--row-pad: 13px` 兩條規則都碰不到：抓宣告的
正規式刻意跳過 `--` 開頭的名字，而規則 k 只掃 token 定義檔。

`app/globals.css` **不是** token 定義檔。那個身分同時帶著「可寫裸色值」與
「可用 `--ds-*`」的豁免，而它只放無 class 元素的預設值、不宣告任何 token ——
白送一個用不到的豁免，只是留一個之後有人會踩進去的洞。

**「進入點」是兩個，不是一個**（規則 q 與 s 都對兩個問話）：`app/layout.tsx` 與
`app/global-error.tsx`。後者**取代**整個 root layout，所以 layout 的 CSS import 不會出現在
它的文件裡 —— 少了哪一份，錯誤頁上靠它撐著的 `var()` 就解不出來，而錯誤頁正是最不會
有人在日常開發中看到的一頁。

**為什麼自己寫而不用 stylelint**：這幾條沒有一條是 stylelint 的內建規則，全部得自己寫
plugin；而這個 repo 的形狀本來就是「自己寫一支 `check-*`，例外附理由」
（`check-boundaries.mjs`、`scripts/check-docs.sh`、`knip.ts`）。

規則 h 是**型別承諾了、CSS 沒實作**那類漂移的唯一防線，而且**只能靜態檢查**：Vitest 的
CSS module 是一個 proxy，任何 key 都會回傳一個編出來的 class 名字
（`styles.totallyMadeUp` → `_totallyMadeUp_cd3e83`），所以執行期測試分不出 class 在不在。
這也是 variant 對應要寫成 `Record<Variant, string>` 而不是 `variant === "x" && styles.x`
布林串的理由：Record 讓每一個 `styles.x` 都是靜態可見的字面，規則 h 才看得到。

## 寫 CSS 時

- **顏色一律用 token。**要「某個顏色加透明度」時用 `color-mix()`，不要把 hex 手動展開成
  `rgba()` —— 展開之後那個值就跟主題脫鉤了。
- **間距用 `--space-*`，`Flex` 的 `gap` 用階號**（`gap={4}` → `--space-4`）。階號是
  `SpaceStep` 聯集而不是 `number`：`gap={7}` 沒有對應的 token，收成 `number` 的話它會
  靜靜變成 0。
- **要負值寫 `calc(var(--space-8) * -1)`，不要寫 `-var(--space-8)`** —— 後者是無效 CSS，
  瀏覽器會把整條宣告丟掉而不報錯（規則 j 在擋）。
- **疊層一律用 `--z-*`**，不要就地寫數字：兩個元件各就地寫一個 1000，誰蓋在誰上面
  就全靠載入順序決定。
- **裸 px 由規則 i 擋著**，範圍是**節奏類屬性**：間距（`padding`／`margin`／`gap`／
  `top`／`right`／`bottom`／`left`）、`font-size`、`border-radius`、`border` 系列。
  值不在刻度上時，四捨五入到 4px 網格，**平手取大**（`10 → 12`、`14 → 16`、`22 → 24`）
  —— 取大而不取小，是因為變緊容易讓文字擠壓、觸控目標縮小，變鬆最多只是多佔空間。

- **`width`／`height`／`min-*`／`max-*` 的值本身放行**，因為那是**元件自己的尺寸**
  （textarea 最小高度 104px、空狀態 180px、對話框上界 560px），多半只用一次；硬要它們走全域
  token，換到的是二十幾個單一用途的變數，那是雜訊不是設計系統。真的跨檔案共用的尺寸
  已經各自有 token：控制項高度 `--control-height-*`、底部導覽 `--layout-bottom-nav-height`、
  版面寬度 `--container-*`。

  **但它們的算式裡仍然要檢查。** `width: calc(100vw - 32px)` 的 `32px` 是視窗左右要留的白，
  不是元件寬度；`width: min(100%, 560px)` 的 `560px` 才是。判準是**這個 px 在算式裡的角色**：
  以 `+`／`-` 參與運算、或與 `env(safe-area-*)` 並列當下限的，是留白，要走 token；
  單獨當上界的，是尺寸，放行。只看屬性名會把這兩者混為一談。

  **例外是與 `env(safe-area-*)` 相加的那一項**：`min-height: calc(60px + env(safe-area-inset-top))`
  的 `60px` 是這個元件本來的高度，env() 只是把它往瀏海底下延伸 —— 那是尺寸，放行。
  這一條要**兩種寫順序都成立**：`calc(60px + env(…))` 與 `calc(env(…) + 60px)` 是同一件事，
  只認其中一種的話就是同一件事寫法不同結果不同，而那種規則沒有人會信。

  **不要為了讓算式過關而硬造 token。** 上面那個 60px 只用一次，收成全域 token 正好是
  這一段開頭在反對的事。

- **3px 以下豁免**。1–3px 是**次網格**的光學調整：圖示與文字基線對齊、髮絲分隔線、
  由其他尺寸推導出來的置中（設定頁的 toggle 把手是 `(24 - 20) / 2 = 2px`）。
  把它們套進 4px 網格會是 2–4 倍的變化 —— 那不是正規化，是把原本對齊的東西弄歪。

  **推導出來的值要在註解裡寫出算式。** 上面那個 2px 是從 24 與 20 推導來的：把手尺寸一改，
  偏移不會跟著動，留白就變成不對稱的 3／1。檢查器擋不到它（它落在這一條的豁免範圍內），
  而 1px 的不對稱要用眼睛才看得出來。寫下算式至少讓下一個改尺寸的人有機會發現。

## 圖示尺寸有兩套機制，各有適用時機

- **尺寸會隨斷點變的**（側欄、底部導覽的導覽圖示）留在 CSS：
  `.navLink svg { width: var(--size-icon-lg) }`。media query 改得動 CSS，改不動 prop。
- **其餘一律用 kit 匯出的 `ICON_SIZE`**：`<Plus size={ICON_SIZE.md} />`。

第二種是不得已的重複：lucide 的 `size` prop 產生 `<svg width height>`，
那是 JS 那一側的值，CSS 的自訂屬性餵不進去。所以刻度在 `shared/ui/internals.ts`
再宣告一份，**由規則 m 保證兩邊的數字相等** —— 讓它變成可驗證的重複，
而不是會漂的重複。`ActionMenu` 的 `DROPDOWN_WIDTH` 與 CSS 的 `min-width` 是同一種情況，
也在規則 m 的守備範圍。

要新增這類 JS／CSS 成對的數字，在 `check-tokens.mjs` 的 `JS_CSS_PAIRS` 加一筆。

## 一個視覺概念只能有一份實作

這是 Design System 導入時**最花錢的一條**，而且沒有檢查器擋得住 —— 只能靠 review。

一個模組在自己的 CSS 裡刻一份輸入框，「輸入框長什麼樣」就定義在兩個地方；再多兩個模組
就是四個。DS 改一次樣式要改四處，而漏掉的那處不會有任何訊號 —— 那正是使用者會在某個
角落看到「這個下拉的圓角跟別的不一樣」的來源。

**模組缺的東西要補進 kit，不要在模組裡另刻。** kit 的 `TextInput` 有
`icon`／`trailing`／`size` 就是這樣來的：登入頁需要前置圖示與密碼顯示切換，那是 kit 真的
缺的東西，補進去之後所有用到的地方共用同一份樣式。

判斷方式很簡單：**如果你正在模組的 CSS 裡寫 `border`／`border-radius`／`height`
去做一個輸入框或按鈕，那就是走錯路了。**

## 加一個元件到 UI kit

1. 元件檔放 `apps/web/shared/ui/`（版面原語）或 `shared/ui/patterns/`（版面樣板）；
   樣式進 `shared/ui/styles/` 既有的那幾份 domain 樣式表，不要一個元件開一個檔。
2. 有 state 或事件就**另開檔案**，不要在 `primitives.tsx` 上加 `"use client"` ——
   那會把所有版面元件都拖進 client bundle（理由見 [`architecture.md`](architecture.md)）。
3. 從 `shared/ui/index.ts` 具名匯出。那是 UI kit 唯一的公開面。
4. variant 對應寫成 `Record<Variant, string>`（見上面規則 h）。
5. 使用者看得到的字串放 `shared/ui/i18n.ts`。

需要 kit 裡某個 class 時，**在 kit 裡多包一個元件**，不要 `composes:` 它的 CSS module
（`TableRow` 就是這樣來的）。樣式一旦外流，UI kit 就再也不能安全調整內部結構。

## 導入外部 Design System

**這個模板出廠沒有導入任何 DS** —— `primitives.css` 全是字面值，只有一份 `default` 主題。
底下是導入時要遵守的流程。

**導入一套 DS＝多一份主題。** 內建的 `default` 一行不動，隨時切得回去；要導入第二套 DS
也只是把同一套步驟再走一次。

**不要整份覆蓋 `primitives.css`** —— DS 的產出有自己的命名，覆蓋掉之後語意層的
`var(--ds-*)` 會整批落空，而落空在 CSS 這一側是沒有樣式、不是錯誤。

```
app/tokens/primitives.css   目前全是字面值；導入時多一條調色線，值指向 vendor
app/tokens/vendor/<ds>/     DS 原生產出，一套一個目錄，整批可覆蓋
app/themes/default.css      內建：深色灰／靛 ← 介面的定義檔
app/themes/<ds>.css         導入的：同一組 --color-*，值指到新那條線
```

`primitives.css` 的角色沒變（原始層的落地處），只是多一條線、值的來源從字面量換成
`var()`。**保留 `--ds-*` 這組名字**換到的是「下次 DS 更新只要覆蓋 `vendor/<ds>/` 那幾檔」；
把 DS 的名字直接鋪進主題層則是每次更新都要重對一次。

### 步驟

| | 做什麼 | 漏了會怎樣 |
|---|---|---|
| 1 | DS 的 **token 檔**放進 `app/tokens/vendor/<ds>/`，並照下面「落地前要先處理的四件事」清乾淨 | 撞到這個 repo 或另一套 DS 已有的名字，會被擋下來 |
| 2 | **每一份 vendor 檔都在兩個進入點各加一行 import**（`app/layout.tsx` 與 `app/global-error.tsx`） | 檔案在、宣告也收得到，但瀏覽器沒載到它 —— 靠它撐著的 `var()` 會整批解不出來（規則 s） |
| 3 | `primitives.css` 加一條調色線（`--ds-<名字>-*`），值指向 vendor | vendor 的名字出現在對照表以外，會被擋下來 |
| 4 | 複製 `app/themes/default.css` 成 `app/themes/<ds>.css`，選擇器改 `:root[data-theme="<ds>"]`，只換右手邊 | 少宣告哪個顏色會被逐行列出來 |
| 5 | 登記新主題：`ThemeName`、兩個進入點的**主題** import（與第 2 步的 vendor import 是兩回事）、`DEFAULT_THEME` | 不一致會被擋下來 |
| 6 | 把 `app/manifest.ts` 的 `theme_color` 改成新主題 `--color-bg-app` 的字面值 | 規則 u 會擋 —— 漏了的話 PWA 的啟動畫面與狀態列維持舊底色，只有裝了 App 的人看得到 |
| 7 | `cd apps/web && npm run check:tokens` | —— |
| 8 | `npx vitest run tests/app/themes` | 新主題的對比度沒過門檻會在這裡擋下來 —— 它對 `app/themes/` 底下**每一份**主題都套同一組 WCAG 門檻 |
| 9 | **確認值沒有被改到**：用小腳本把 `primitives.css` 的 `var()` 鏈解析回 vendor，和改動前的字面值逐一比對 | **沒有檢查器。** 導入若是「把手抄的值正名成 vendor」，這份輸出應該全空；有差異就是抄錯或對錯階 |
| 10 | **確認鏈路真的進了 bundle**：`npm run build` 之後 grep `.next/static/css/*.css` | **沒有檢查器。** 規則 s 守的是「有沒有 import」，這一步守的是「打包後有沒有真的在那裡」——要同時找得到 `--ds-<你的階>:var(--<上游的名字>)` 與上游那個名字的宣告 |

第 3 步不必自己算要哪幾階：先做第 4 步，`var(--ds-…)` 指到還沒宣告的階時會被報
「引用了沒有宣告過的 token」，那份輸出就是這條線還缺的階。

**順序不必安排，但「有沒有接上」要顧。** CSS 自訂屬性是整份樣式表讀完才代換的，跨檔引用
跟先後無關（先後只在兩邊宣告同一個名字時才有意義，而那個有檢查器擋）。反過來，漏掉第 2 步
不會有任何症狀傳到其他規則上：宣告是從磁碟收集的，檔案躺在那裡就算數 ——
所以那一步自己要有一條規則守。

### 只收 token 定義檔，而且多半只收顏色

DS 專案通常長這樣：`tokens/`（色彩、排版、間距、陰影、動態）、`components/`（JSX 或 HTML）、
`ui_kits/`、`guidelines/`。**只收 `tokens/`**：元件缺什麼要補進 UI kit
（見上面「一個視覺概念只能有一份實作」），而上游的元件樣式表會夾帶它自己的斷點與字型 `@import`。

`tokens/` 裡面也要挑。判準是**這一份帶進來的是值，還是只是撞名**：

- **顏色一定收** —— 那是換皮的本體。
- **間距／字級／圓角／陰影／動態，若上游的值與這裡已經一致，就不要收。** DS 的**原始**名
  往往正好是這個 repo 的**語意**名（`--fs-base`、`--space-4`、`--radius-md`、`--shadow-sm`、
  `--ease-standard`），收進來只會整組撞名，換不到任何資訊。
- **值真的不同時才收**，並照第 3 步在對照表裡吸收差異。

**已知限制**：只收顏色，代表 DS 之後若調整間距或字級刻度，這裡**沒有落點也不會有紅燈**，
要人工比對。這是刻意的取捨 —— 比起讓二十幾個撞名的 token 進來，一年比對一次比較便宜。

### 字體不走 vendor

DS 的字體產出多半是 `@import url("https://fonts.googleapis.com/…")`，或是裸的字體名
（`--font-body: 'Inter', …`）。兩種這裡都不能用 —— 字型走 `next/font`，理由在
`app/layout.tsx` 的字型註解。**只取字體的名字**，照那裡現有的寫法加一份；
DS 的字體檔不要放進 vendor，放了會被規則 p 擋下來。

### 落地前要先處理的四件事

- **語意名字要從 vendor 檔拿掉。** DS 產出通常把原始值與語意混在同一份
  （`--color-primary: var(--grape-500)`），而 `--color-*` 是主題層的名字。
  兩份都宣告在 `:root` 時後載入者勝，主題會被整組蓋掉而**沒有任何紅燈** ——
  檢查器就是為了這個多一條撞名規則。實際會撞的通常是這幾類：`--focus-ring`、
  `--surface-*`、`--text-*`、`--border-*`、`--success-*`／`--warning-*`／`--danger-*`／`--info-*`。
- **排版的合寫要拆開。** DS 常把字重、字級、行高、字體擠成一個值
  （`--text-body: 400 15px/1.5 var(--font-body)`），這裡是四個獨立的軸
  （`--fs-*`、`--fw-*`、`--lh-*`、`--font-*`）。合寫沒有槽位可以接，只能手拆。
- **刻度不對齊在對照那一層解決。** DS 給幾階、這裡有幾階，不會剛好一樣（中性色尤其常見）。
  在 `primitives.css` 決定「我的第 3 階＝它的第 2 階」就好，
  **不要去改語意層的階號**：那組名字是 UI kit 的樣式在認的。
- **一次性 token 不要接進來**（`--card-pad`、`--row-pad-y` 那類）。那是 DS 端某個元件的
  內部值，接進原始層之後沒人知道它服務誰，也就沒人敢動它。

**已知限制：對比測試只讀得懂 hex。** 它的解析器支援 hex、單層 `var()` 與這個 repo 用的那種
`color-mix()`，遇到 `oklch()`／`lab()` 會**直接拋錯**（不是安靜跳過，所以不會假綠燈，
但會是一次硬失敗）。上游給的是那類色彩函式時，在 `primitives.css` 落地成 hex，
或把解析器補到看得懂它。

vendor 的名字只能出現在 `primitives.css`。少了那條限制，模組 CSS 直接寫
`var(--grape-500)` 不會有任何人擋 —— 分層規則認的是 `--ds-` 前綴，而 vendor 的前綴
由上游決定。

### 這個模板是單一深色色調，而 DS 多半只給亮色

上游的色票是照著它自己的畫面挑的，**通常只有一組亮色**。所以導入時最花時間的不是接線，
是**把缺的那一半推導出來**：表面要幾階、文字要幾階、品牌色在深色底上要不要提亮。
（量級大約是：表面補 5 階、文字補 4 階、品牌補 3 階。）

**推導出來的階留在 `primitives.css`，不要寫進 vendor** —— 下次上游更新是整批覆蓋那個目錄，
寫進去會被沖掉。在 `primitives.css` 裡讓它們自成一段並註明「上游沒有給」，
下一個人才知道哪些能被覆蓋、哪些是我們自己的。

### 跨主題共用的東西不要接到單一 DS

狀態色（success／warning／danger／info）在這個 repo **不隨 `data-theme` 變**，
`default` 主題也在用。把它接到某一套 DS 的 vendor 上，等於讓內建主題也依賴那套 DS ——
那套一旦被刪掉或換掉，內建主題跟著壞。**值可以照抄，來源要留在自己這一側。**

### 導入完成前的驗證

把 `check:tokens` 當進度表用，它會照這個順序把問題交給你：

| 訊息 | 意思 |
|---|---|
| 規則 o 逐條列出撞名 | vendor 檔還留著語意別名，回去刪 |
| 規則 a「引用了沒有宣告過的 token」 | 對照表還缺這幾階 |
| 規則 s 指名某個進入點 | 有一份 vendor 檔只接了一半（多半是漏了 `global-error.tsx`） |
| 規則 q「主題 X 只登記了一半」 | `ThemeName`／主題檔／兩個進入點的 import 對不齊 |
| 規則 b 列出沒人用的 `--ds-*` | 舊主題移除後留下的死階，那份輸出就是刪除清單 |

步驟 9 與 10 沒有檢查器，所以它們才排進步驟表 —— 寫在散文裡的「記得做一下」每次都會被跳過。

導入完成後**有三處文件會變成不實敘述，而且沒有任何檢查器看得到**：這一節開頭那句
「這個模板出廠沒有導入任何 DS」、[`TEMPLATE.md`](../TEMPLATE.md) §3 的視覺敘述，
以及 [`CHANGELOG.md`](../CHANGELOG.md)（要記一筆：主題名稱、
`DEFAULT_THEME` 改了沒）。


## 加一類新 token

DS 給了這裡還沒有槽位的東西（模糊、外框、更多動態階）時，三層都要動：
原始層放值（`--ds-*`）、語意層取一個**照用途**的名字、然後才是呼叫點。

**要同一次改動就有呼叫點。** 「先把槽位加好，之後再用」會被死 token 規則擋下來 ——
那條規則的存在理由就是「沒人用的 token 就是該刪」，它分不出「還沒用」與「不再用」。
所以順序是：先確定哪個 CSS 要用它，三層一起加。

只服務單一元件的變數不要走這條路，就近宣告在那個 `*.module.css` 裡就好
（見上面的三層表格）。

## 用這份模板開專案時

視覺是開案時就該決定的事，步驟在 [`TEMPLATE.md`](../TEMPLATE.md) 的「決定視覺」。
token 檔開案之後就完全是你的，改名、換色票、整套換掉都可以 —— 唯一的限制是
`shared/ui` 的 CSS 只認語意層那組名字，改名的話要一起改（`npm run check:tokens` 會逐行指出來）。

## 斷點：唯一不能做成 token 的類別

CSS 的 media query **不接受 `var()`**，所以斷點沒辦法走三層。替代方案是
`check-tokens.mjs` 的 `BREAKPOINTS` 允許清單 —— **那份清單就是斷點的單一事實來源**。

DS 換一組斷點時要做兩件事，而且**只有第一件有檢查器**：

1. 改允許清單 → 規則 g 會擋住任何清單外的值
2. 手動改掉每一個 media query → **沒有檢查器能確認你改乾淨了**

第 2 步沒有任何檢查器守得住（跟「一個視覺概念只能有一份實作」同一類），導入 DS 換斷點時要自己排進工作項。
