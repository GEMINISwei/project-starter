import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

/**
 * 樣式層的邊界檢查器 —— `check-boundaries.mjs` 的 CSS 對應物。
 *
 * **為什麼自己寫而不用 stylelint**：底下的規則沒有一條是 stylelint 的內建規則，
 * 全部得自己寫 plugin。而這個 repo 既有的形狀就是「自己寫一支 check-*，例外附理由」
 * （`check-boundaries.mjs`、`scripts/check-docs.sh`、`knip.ts`）。多一個相依與一份
 * 設定檔，換到的只是把同樣的邏輯搬進別人的外殼裡。
 *
 * 這支存在的理由是 Design System：token 是設計端的產出，會整批更新。沒有檢查器時，
 * 上游改個名字在 CSS 這一側是**靜靜失效**（`var()` 找不到變數不會報錯，只會沒有樣式），
 * 錯誤要等到有人用眼睛看到才會發現。有了它，換一批 token 就等於拿到一份完整的失效清單。
 */

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")

// 白名單而不是黑名單，理由同 check-boundaries.mjs：漏掉一項只是少檢查一個目錄，
// 黑名單漏一項則是掃進 node_modules。
const SOURCE_DIRS = ["app", "config", "modules", "shared"]

/**
  * 可以宣告全域 token 的檔案。這之外的 CSS 只能引用，不能定義調色盤。
  *
  * **`globals.css` 不在裡面。** 這個身分同時帶著「可寫裸色值」與
  * 「可用 `--ds-*`」的豁免，而 `globals.css` 自己的檔頭就寫「token 不住在這裡」——
  * 給它一個用不到的豁免，只是留一個之後有人會踩進去的洞。
  */
const TOKEN_FILE = /^app\/(themes\/[^/]+\.css|tokens\/(?:vendor\/[^/]+\/)?[^/]+\.css)$/

/**
 * 外部 Design System 的原生產出，原封不動落地的地方（見 `docs/design-system.md`）。
 *
 * 只認 `vendor/` 這一層而不是任意子目錄：TOKEN_FILE 的身分同時帶著「可以寫裸色值」的
 * 豁免，開放任意子目錄等於讓人隨手開一層就繞過規則 c。
 *
 * **一套 DS 一個目錄**（`vendor/<ds>/colors.css`）。導入第二套時 `colors.css` 會撞檔名，
 * 而「下次整批覆蓋」要能一套一套來 —— 平鋪的話兩套會混在一起，覆蓋時分不出誰是誰。
 */
const VENDOR_FILE = /^app\/tokens\/vendor\/[^/]+\/[^/]+\.css$/

/** vendor 的名字唯一可以被引用的地方 —— 對照表本身。 */
const ADAPTER_FILE = "app/tokens/primitives.css"

/**
 * 三層 token 的最底層：Design System 的原值，只有值、不帶用途。
 *
 * 除了 token 定義檔（那裡正是要把原值翻譯成語意的地方），任何檔案碰到它就是繞過了
 * 翻譯層 —— DS 換一批值時，那些呼叫點會被漏掉。
 */
const RAW_LAYER = /^--ds-/

/**
 * 允許的斷點。
 *
 * CSS 的 media query 吃不到 `var()`，所以斷點沒辦法變成真正的 token —— 這份清單
 * 就是它的替代品。要新增一個斷點請先問是不是真的需要：目前四個已經覆蓋
 * 手機／平板／桌機，隨手加值的下場是每個檔案各挑各的，響應式行為在檔案之間對不起來。
 */
const BREAKPOINTS = new Set(["480px", "720px", "721px", "1024px"])

/** 節奏類屬性 —— 這些的值構成整站的視覺韻律，必須走 token。 */
const RHYTHM = /^((?:padding|margin)(?:-[a-z]+)?|gap|row-gap|column-gap|top|right|bottom|left|inset|font-size|border|border-[a-z]+)$/

/**
 * 尺寸屬性 —— 值本身是元件多大，放行；但**它的算式裡仍然可能藏著間距**。
 *
 * `width: calc(100vw - 32px)` 的 `32px` 是視窗左右要留的白，不是元件寬度；
 * `width: min(100%, 560px)` 的 `560px` 才是。用屬性名分辨不出這兩者。
 */
const SIZE = /^(width|height|min-width|min-height|max-width|max-height|flex-basis)$/

/**
 * 與 `env(safe-area-*)` **相加**的 px：那是元件自己的尺寸，不是留白。
 *
 * `min-height: calc(60px + env(safe-area-inset-top))` 的 60px 是這個 header 本來的高度，
 * env() 只是把它往瀏海底下延伸。判斷前先把這種配對整段剝掉，兩種寫順序才會得到
 * 同一個答案 —— 只認運算子**後面**的 px 的話，`calc(60px + env(…))` 放行、
 * `calc(env(…) + 60px)` 會擋，同一件事寫法不同結果不同。
 */
const SAFE_AREA_SUM =
  /env\(safe-area-[^)]*\)\s*\+\s*-?[0-9.]+px|-?[0-9.]+px\s*\+\s*env\(safe-area-[^)]*\)/g

/**
 * 算式裡屬於「留白」的 px：以 `+`／`-` 參與運算的項（兩側都認），
 * 或與 `env(safe-area-*)` 並列在同一個 `max()`／`min()` 裡的下限。
 */
const SPACING_IN_EXPR = [
  /[+-]\s*(-?[0-9.]+)px/g,
  /(-?[0-9.]+)px\s*[+-]/g,
  /(?:max|min)\(\s*(-?[0-9.]+)px\s*,\s*env\(/g,
]

/**
 * 裸色值：hex、以及會直接帶進一個顏色的色彩函式。
 *
 * `oklch`／`lab`／`lch`／`color` 不是湊數的 —— 現在的 Design System 產出多半用它們，
 * 少一個，導入 DS 時上游的原始色值就會從那個縫隙繞過對照表混進語意層，
 * 而規則 c 全綠。`color-mix()` 刻意不在裡面：它的參數是 token，
 * 那正是文件要求的「要透明度請用 color-mix()」。
 */
const LITERAL_COLOR = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|lab|lch|color)\(/

/**
 * 光學微調的上限。
 *
 * 1–3px 的位移是**次網格**的調整：圖示與文字基線對齊、髮絲分隔線、由其他尺寸推導
 * 出來的置中。把它們硬套進 4px 網格會是 2–4 倍的變化。
 */
const OPTICAL_MAX = 3

/** `import styles from "./x.module.css"` —— 規則 f 與 h 都要靠它把識別字接回檔案。 */
const CSS_MODULE_IMPORT = /import\s+(\w+)\s+from\s*["']([^"']+\.module\.css)["']/g

/**
 * 宣告了但目前沒有人引用的 token。
 *
 * 每一條都要附理由，比照 `knip.ts` 與 `check-docs.sh` 的 ALLOW —— 沒有理由的例外
 * 會變成沒人敢動的永久設定。這裡刻意留空：token 是給下游用的公開面這種說法對
 * **顏色**不成立（下游改的是值，不是新增引用點），沒人用就是該刪。
 */
const UNUSED_TOKEN_ALLOWLIST = new Map()

/**
 * 語意層可以自己帶值、不必由 `--ds-*` 撐著的 token。
 *
 * 判準是**這個屬性該不該由設計端決定**。行高、字距、控制項高度都該由 DS 給，
 * 所以它們不在這裡；底下這幾個是應用程式自己的架構或數學常數，DS 換一套也不會變。
 * 每條都要附理由 —— 沒有理由的例外會變成沒人敢動的永久設定（同 knip.ts 的慣例）。
 */
const SEMANTIC_RAW_ALLOWLIST = new Map([
  ["--z-raised", "疊層順序是應用架構，不是 DS 提供的視覺屬性"],
  ["--z-dropdown", "同上"],
  ["--z-sticky", "同上"],
  ["--z-nav", "同上"],
  ["--z-overlay", "同上"],
  ["--z-toast", "同上"],
  ["--radius-round", "50% 是「畫成圓形」這個幾何事實，不是圓角刻度上的一階"],
])

/** 主題檔所在的目錄。規則 q 與 r 的守備範圍，也是「一份主題一個檔」這個慣例的落點。 */
const THEME_DIR = "app/themes"

/** 原始層與語意層的落點，vendor 也在底下。規則 s 的守備範圍。 */
const TOKEN_DIR = "app/tokens"

/**
 * 自帶 `<html>` 的進入點 —— 每一個都要**自己**載齊 token 與主題，規則 s 與 q 都對它們問話。
 *
 * `global-error.tsx` 會取代整個 root layout，所以 `layout.tsx` 的 CSS import 不在它的文件裡
 * 理由（為什麼是兩個而不是一個）在 `docs/design-system.md` 的「檢查器擋什麼」。
 *
 * `layout.tsx` 是必備的，`global-error.tsx` 不是；後者不存在時只是少一個要對的對象。
 */
const ROOT_LAYOUT = "app/layout.tsx"
const GLOBAL_ERROR = "app/global-error.tsx"
const ENTRY_POINTS = [ROOT_LAYOUT, GLOBAL_ERROR]

/**
 * 某個進入點 import 了 `./<dir>/` 底下的哪幾份 CSS（含副檔名）。檔案不存在時回 `null`。
 *
 * 行首錨定：沒有它，`// import "./themes/boutique.css"` 這種註解掉的 import 也會被算成
 * 「有接上」—— 那正是這兩條規則要抓的情況。
 */
function entryImports(base, entry, dir) {
  const file = path.join(base, entry)
  if (!fs.existsSync(file)) return null
  const pattern = new RegExp(String.raw`^\s*import\s+["']\./${dir}/([^"']+\.css)["']`, "gm")
  return new Set(matchAll(fs.readFileSync(file, "utf8"), pattern))
}

const CSS = /\.css$/
const TS = /\.(ts|tsx)$/

function walk(dir) {
  if (!fs.existsSync(dir)) return []
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name)
    return entry.isDirectory() ? walk(full) : [full]
  })
}

const QUOTES = "\"'`"
const DEPTH_DELTA = { "{": 1, "(": 1, "[": 1, "}": -1, ")": -1, "]": -1 }

/**
 * 從引號（含樣板字串）的起點跳到它的結尾之後。
 *
 * 引號裡的括號一律不計數 —— `${…}` 的右括號因此自動被跳過，`min(100%, ${w}px)`
 * 這種寫法才不會把物件的結尾算錯。
 */
function skipQuoted(text, start) {
  const quote = text[start]
  let index = start + 1
  while (index < text.length) {
    if (text[index] === "\\") index += 2
    else if (text[index] === quote) return index + 1
    else index += 1
  }
  return index
}

/** 區塊註解換成等量空白：hex 出現在註解裡是說明，不是違規，但行號要保持對得上。 */
function stripComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, (match) => match.replace(/[^\n]/g, " "))
}

/**
 * TS 的 `//` 行註解也要換成空白。
 *
 * CSS 沒有這種註解，但 TS 有，而且**一定要處理**：規則 t 掃的是 TSX 的 `style={{…}}`，
 * 註解掉的舊寫法會被報成違規。**假陽性比漏報更傷檢查器** —— 被誤報一次之後，
 * 下一次真的紅燈時第一反應會是「大概又是誤判」。
 *
 * **只認整行註解**（行首除了空白就是 `//`）。行尾註解刻意不處理，因為要正確判斷
 * 一個 `//` 是不是註解，得先認得正規式字面 —— `/^https?:\\/\\//` 的最後兩個字元就是 `//`，
 * 而那是再普通不過的寫法（這支檔案自己的規則 p 就是這樣寫的）。把它當註解起點會把
 * **整行後面抹掉**，於是同一行的 `styles.x` 消失，規則 f 報一個不存在的死碼。
 *
 * 代價是行尾註解裡的 `style={{…}}` 仍會被規則 t 誤報 —— 那比 URL 正規式罕見得多，
 * 而且真要寫正規式的詞法分析，成本遠高於它防到的錯。
 */
function stripLineComments(text) {
  return text.replace(/^[ \t]*\/\/[^\n]*/gm, (match) => " ".repeat(match.length))
}

function read(base, matcher) {
  return SOURCE_DIRS
    .flatMap((dir) => walk(path.join(base, dir)))
    .filter((file) => matcher.test(file))
    .map((file) => {
      const stripped = stripComments(fs.readFileSync(file, "utf8"))
      return {
        rel: path.relative(base, file).split(path.sep).join("/"),
        text: TS.test(file) ? stripLineComments(stripped) : stripped,
      }
    })
}

/** 把每個檔案攤成行，讓所有規則都能報出 `檔案:行號`。 */
function* eachLine(files) {
  for (const file of files) {
    const split = file.text.split("\n")
    for (let index = 0; index < split.length; index += 1) {
      yield { rel: file.rel, no: index + 1, text: split[index], isToken: TOKEN_FILE.test(file.rel) }
    }
  }
}

/**
 * 逐**宣告**攤開一份 CSS。
 *
 * 規則 k 與 u 都要看**完整的值**才判斷得出來，而值換行寫的多行宣告逐行看會整條漏掉
 * （`color-mix(in srgb, …` 之後折行是常見寫法）—— 漏掉的結果是規則安靜地對那一條失效。
 *
 * 同一行寫多條（`.a { --pad: 13px; --gap: 4px }`）也要收得到，理由同 `declarationsOf`：
 * 只認行首會讓那幾條靜靜不受檢查。
 */
/**
 * 一行裡的下一個自訂屬性宣告。引號段整段跳過 —— `content: "--fake: 99px"` 不是宣告。
 *
 * 這是 `(--[a-z][\w-]*)\s*:` 這條無錨點正規式的代價：它收得到同一行的第二條宣告
 * （那正是要它的理由），但也收得到字串裡的內容。假陽性比漏報更傷檢查器。
 */
function nextDeclaration(text) {
  let index = 0
  while (index < text.length) {
    const ch = text[index]
    if (QUOTES.includes(ch)) { index = skipQuoted(text, index); continue }
    const match = /^(--[a-z][\w-]*)\s*:/.exec(text.slice(index))
    if (match) return { token: match[1], after: index + match[0].length }
    index += 1
  }
  return null
}

function* eachDeclaration(file) {
  const lines = file.text.split("\n")
  let open = null
  for (let index = 0; index < lines.length; index += 1) {
    let rest = lines[index]
    while (rest.length > 0) {
      if (!open) {
        const start = nextDeclaration(rest)
        if (!start) break
        open = { token: start.token, no: index + 1, value: "" }
        rest = rest.slice(start.after)
        continue
      }
      const end = rest.search(/[;}]/)
      open.value += ` ${end === -1 ? rest : rest.slice(0, end)}`
      if (end === -1) { rest = ""; continue }
      yield open
      open = null
      rest = rest.slice(end + 1)
    }
  }
  if (open) yield open
}

function matchAll(text, pattern) {
  return [...text.matchAll(pattern)].map((match) => match[1])
}

// ---- 收集 ----------------------------------------------------------------

/**
 * 所有 `--x:` 宣告，分成三份：`global` 是這個 repo 自己的 token 檔宣告的、
 * `vendor` 是 DS 原生產出宣告的、`all` 是任何 CSS 宣告的。
 *
 * vendor 刻意不併進 `global`，規則 b 就自動對它豁免：上游給的是整套色票，
 * 用不到的階本來就會有，而修剪它等於放棄「下次整批覆蓋」——
 * 那正是 adapter 那一層換來的東西。
 */
function declarations(cssFiles) {
  const global = new Map()
  const vendor = new Map()
  const local = new Map()
  const all = new Set()
  const clashes = []
  for (const line of eachLine(cssFiles)) {
    const isVendor = VENDOR_FILE.test(line.rel)
    for (const token of matchAll(line.text, /(--[a-zA-Z0-9-]+)\s*:/g)) {
      all.add(token)
      if (!line.isToken) {
        if (!local.has(token)) local.set(token, new Set())
        local.get(token).add(line.rel)
        continue
      }
      const at = `${line.rel}:${line.no}`
      if (!isVendor) {
        if (!global.has(token)) global.set(token, at)
        continue
      }
      // 記住是哪一套 DS：同一套裡重複宣告是上游自己的事，兩套之間重複才是撞名。
      const dir = path.posix.dirname(line.rel)
      const seen = vendor.get(token)
      if (!seen) vendor.set(token, { at, dir })
      else if (seen.dir !== dir) clashes.push({ token, at, owner: seen.at })
    }
  }
  return { global, vendor, local, all, clashes }
}

/** 由 TSX 以行內樣式設定的自訂屬性（`--flex-*` 那一類），CSS 裡永遠不會有宣告。 */
function tokensSetFromJs(tsFiles) {
  const set = new Set()
  for (const file of tsFiles) {
    // 兩種來源：行內樣式的物件 key（`"--flex-gap": …`），以及 next/font 的
    // `variable: "--font-sans-loaded"` —— 後者的宣告在建置期產生的 CSS 裡，原始碼看不到。
    for (const token of matchAll(file.text, /["'](--[a-zA-Z0-9-]+)["']\s*:/g)) set.add(token)
    for (const token of matchAll(file.text, /variable:\s*["'](--[a-zA-Z0-9-]+)["']/g)) set.add(token)
  }
  return set
}

/**
 * 以樣板字串組出來的 token 前綴，例如 `spacing()` 的 `var(--space-${step})`。
 *
 * 這種呼叫點靜態上看不出實際的 token 名字，所以整個家族都當成「有人用」。
 * 放行的前提是**型別那一側擋得住**：`spacing()` 收的是 `SpaceStep` 聯集而不是
 * `number`，所以組不出不存在的階。用 `number` 的地方不該套這個豁免。
 */
function dynamicPrefixes(files) {
  const prefixes = new Set()
  for (const file of files) {
    for (const prefix of matchAll(file.text, /var\(\s*(--[a-zA-Z0-9-]*?)\$\{/g)) prefixes.add(prefix)
  }
  return prefixes
}

/** 所有 `var(--x)` 引用。CSS 與 TSX 都要收 —— global-error.tsx 只用行內樣式。 */
function references(files) {
  const found = []
  for (const line of eachLine(files)) {
    for (const match of line.text.matchAll(/var\(\s*(--[a-zA-Z0-9-]+)(.?)/g)) {
      if (match[2] === "$") continue
      found.push({ token: match[1], at: `${line.rel}:${line.no}`, rel: line.rel })
    }
  }
  return found
}

// ---- 規則 ----------------------------------------------------------------

/** a：引用的 token 必須有人宣告。b：宣告的 token 必須有人引用。 */
function checkTokenPairing(refs, declared, jsSet, dynamic, errors) {
  const known = new Set([...declared.all, ...jsSet])
  for (const ref of refs) {
    if (!known.has(ref.token)) {
      errors.push(`${ref.at}: 引用了沒有宣告過的 token ${ref.token}`)
    }
  }
  const used = new Set(refs.map((ref) => ref.token))
  const byPrefix = (token) => [...dynamic].some((prefix) => token.startsWith(prefix))
  for (const [token, at] of declared.global) {
    if (used.has(token) || byPrefix(token) || UNUSED_TOKEN_ALLOWLIST.has(token)) continue
    errors.push(`${at}: token ${token} 沒有任何人引用`)
  }
}

/** c：token 定義檔以外不可出現裸色值。要顏色請加 token，要透明度請用 color-mix()。 */
function checkLiteralColors(cssFiles, errors) {
  for (const line of eachLine(cssFiles)) {
    if (line.isToken) continue
    const literal = line.text.match(LITERAL_COLOR)
    if (literal) errors.push(`${line.rel}:${line.no}: 不可寫死色值 ${literal[0]}，請改用 token`)
  }
}

/** d：token 定義檔以外只能引用語意層。 */
function checkLayering(refs, errors) {
  for (const ref of refs) {
    if (TOKEN_FILE.test(ref.rel) || !RAW_LAYER.test(ref.token)) continue
    errors.push(`${ref.at}: ${ref.token} 是原始層，只能引用語意層的 token`)
  }
}

/**
 * v：元件層的自訂屬性不可跨檔引用。
 *
 * 規則 a 的「已宣告」是一個**不分檔案**的全域集合（`all` 在 `if (!line.isToken)` 之前
 * 就收了），所以任何模組 CSS 宣告的自訂屬性都能滿足任何其他檔案的 `var()`。
 * `shared/ui` 的 `page-header.module.css` 用了 `config/shell` 宣告的 `--sidebar-width`
 * 而全程沒有紅燈，就是這個機制 —— 那是硬規則 4（`shared/` 不可引用組裝層）在 CSS
 * 那一半的漏洞，而症狀是安靜的：kit 渲染在 `.shell` 之外時 `calc()` 解不出來，
 * 整條宣告被瀏覽器丟掉。
 *
 * 兩種合法寫法自動放行：**覆寫語意層 token**（那個名字在 token 檔也有宣告，
 * 所以 `declared.global` 擋掉），以及**由 TSX 行內樣式設定的 `--flex-*`**
 * （CSS 裡根本沒有宣告，不會進 `local`）。
 *
 * 跨檔共用的東西請升上語意層 —— `--layout-sidebar-width` 與
 * `--layout-bottom-nav-height` 就是這樣來的。
 */
function checkLocalTokenScope(refs, declared, errors) {
  for (const ref of refs) {
    const owners = declared.local.get(ref.token)
    if (!owners || declared.global.has(ref.token) || owners.has(ref.rel)) continue
    errors.push(`${ref.at}: ${ref.token} 宣告在 ${[...owners].join("、")}，`
      + "元件層的自訂屬性不可跨檔引用 —— 要跨檔共用請升上語意層")
  }
}

/**
 * e：`composes:` 不可跨出 UI kit。
 *
 * 這條補的是 AGENTS.md 硬規則 3 說「CSS 這一半沒人擋」的那個洞：TS 側的深引用被
 * check-boundaries.mjs 擋著，但 `composes: x from "…/shared/ui/styles/…"` 一樣會讓
 * kit 的 class 變成事實上的公開介面，而且不會有紅燈。
 */
function checkComposes(cssFiles, errors) {
  for (const line of eachLine(cssFiles)) {
    const target = line.text.match(/composes:[^;]*?from\s*["']([^"']+)["']/)
    if (!target) continue
    const resolved = path.posix.normalize(path.posix.join(path.posix.dirname(line.rel), target[1]))
    if (resolved.startsWith("shared/ui/styles/") && !line.rel.startsWith("shared/ui/styles/")) {
      errors.push(`${line.rel}:${line.no}: composes 不可跨出 UI kit，請在 kit 裡多包一個元件`)
    }
  }
}

/** import 路徑 → 專案相對路徑。`@/` 指向 app 根，其餘是相對於來源檔。 */
function resolveSpecifier(sourceRel, specifier) {
  if (specifier.startsWith("@/")) return specifier.slice(2)
  return path.posix.normalize(path.posix.join(path.posix.dirname(sourceRel), specifier))
}

/**
 * 每份 CSS module 各自被哪些 class 名字引用。
 *
 * **要按檔案分開統計**，不能把全部 TSX 的成員存取倒進同一個集合：那樣一來
 * `auth.module.css` 的 `.input` 會因為 `forms.tsx` 裡有 `styles.input` 而被當成有人用，
 * 死碼就查不出來了 —— 而那正是模組自己刻一份重複實作時會留下的痕跡。
 */
/** 某個 CSS module 的匯入識別字在這份 TSX 裡被存取到的 class 名字。 */
function styleKeysUsedIn(text, ident) {
  const access = new RegExp(
    `(?<![\\w./"'])${ident}\\.([A-Za-z][\\w]*)|(?<![\\w./"'])${ident}\\[["']([\\w-]+)["']\\]`, "g")
  return [...text.matchAll(access)].map((match) => match[1] ?? match[2])
}

/** CSS module 之間的 `composes:` 也算被取用的那一方有人用。 */
function addComposesUsage(cssFiles, used) {
  for (const file of cssFiles) {
    for (const line of file.text.split("\n")) {
      const composes = line.match(/composes:\s*([^;]*?)\s+from\s*["']([^"']+)["']/)
      if (!composes) continue
      const names = used.get(resolveSpecifier(file.rel, composes[2]))
      if (!names) continue
      for (const part of composes[1].split(/[\s,]+/)) if (part) names.add(part)
    }
  }
}

function classUsageByFile(cssFiles, tsFiles) {
  const used = new Map(cssFiles.map((file) => [file.rel, new Set()]))
  for (const file of tsFiles) {
    for (const [, ident, spec] of file.text.matchAll(CSS_MODULE_IMPORT)) {
      const names = used.get(resolveSpecifier(file.rel, spec))
      if (!names) continue
      for (const name of styleKeysUsedIn(file.text, ident)) names.add(name)
    }
  }
  addComposesUsage(cssFiles, used)
  return used
}

/** f：沒有任何 TSX 引用的 class 是死碼。只管 `*.module.css` —— 全域 CSS 沒有這種對應。 */
function checkDeadClasses(cssFiles, tsFiles, errors) {
  const used = classUsageByFile(cssFiles, tsFiles)
  for (const file of cssFiles) {
    if (!file.rel.endsWith(".module.css")) continue
    const names = used.get(file.rel) ?? new Set()
    for (const line of eachLine([file])) {
      const declared = line.text.match(/^\s*\.([a-zA-Z][a-zA-Z0-9_-]*)/)
      if (declared && !names.has(declared[1])) {
        errors.push(`${line.rel}:${line.no}: class .${declared[1]} 沒有任何 TSX 引用`)
      }
    }
  }
}

/**
 * h：TSX 用到的 `styles.x` 必須真的存在於它 import 的那份 CSS module。
 *
 * 這是規則 f 的反向，補的是**型別承諾了、CSS 沒實作**的漂移：`Button` 的 `color`
 * 聯集本來收 `"primary" | "warning"`，但 CSS 只有 `.buttonError`／`.buttonSuccess`，
 * 傳進去靜靜沒有效果。
 *
 * 只能靜態檢查，不能寫成執行期測試：Vitest 的 CSS module 是一個 proxy，任何 key 都會
 * 回傳一個編出來的 class 名字（`styles.totallyMadeUp` → `_totallyMadeUp_cd3e83`），
 * 所以測試分不出「class 存在」與「class 不存在」。
 *
 * 這也是 variant 對應要寫成 `Record<Variant, string>` 而不是就地 `&&` 串的理由：
 * Record 讓每一個 `styles.x` 都是靜態可見的字面，這條規則才看得到它們。
 */
function checkStyleKeys(cssFiles, tsFiles, errors) {
  const classes = new Map(cssFiles.map((file) =>
    [file.rel, new Set(matchAll(file.text, /\.([a-zA-Z][a-zA-Z0-9_-]*)/g))]))

  for (const file of tsFiles) {
    for (const [, ident, spec] of file.text.matchAll(CSS_MODULE_IMPORT)) {
      const target = resolveSpecifier(file.rel, spec)
      const known = classes.get(target)
      if (!known) continue
      for (const name of styleKeysUsedIn(file.text, ident)) {
        if (known.has(name)) continue
        errors.push(`${file.rel}: ${ident}.${name} 在 ${target} 裡沒有對應的 class`)
      }
    }
  }
}

/**
 * i：節奏類屬性不可出現裸 px；尺寸屬性的算式裡也一樣。
 *
 * 規則 c 擋的是顏色，這條擋的是尺寸。少了它，token 化過的檔案會慢慢長回字面量，
 * 而且因為看起來「跟旁邊那行一樣」而不會有人察覺。
 */
/**
 * 一份 CSS 裡的每一條宣告，含**跨行**與**同一行多條**兩種寫法。
 *
 * 兩種都要處理，而且都真的出現過：`.pageTitle { overflow: hidden; font-size: 18px }`
 * 是後者，`padding:` 之後把四個 `max(…, env(…))` 分行寫是前者。
 * 只比對行首會漏掉前者的續行 —— 續行上的字面量會完全不受檢查，而且不會有任何訊號。
 */
function declarationsOf(file) {
  const out = []
  const lines = file.text.split("\n")
  let open = null
  for (let index = 0; index < lines.length; index += 1) {
    if (lines[index].trim().startsWith("@")) { open = null; continue }
    let rest = lines[index]
    while (rest.length > 0) {
      if (open) {
        const end = rest.search(/[;}]/)
        open.value += ` ${end === -1 ? rest : rest.slice(0, end)}`
        if (end === -1) { rest = ""; continue }
        out.push(open); open = null; rest = rest.slice(end + 1)
      } else {
        const start = rest.match(/(?<!-)\b([a-z-]+)\s*:/)
        if (!start) break
        open = { prop: start[1], value: "", no: index + 1 }
        rest = rest.slice(start.index + start[0].length)
      }
    }
  }
  if (open) out.push(open)
  return out
}

/** 一個尺寸屬性的值裡，屬於留白的那些 px。 */
function spacingInExpression(value) {
  const withoutSafeArea = value.replace(SAFE_AREA_SUM, "")
  return SPACING_IN_EXPR.flatMap((pattern) => matchAll(withoutSafeArea, pattern))
}

/**
 * i：節奏類屬性不可出現裸 px；尺寸屬性的算式裡也一樣。
 *
 * 規則 c 擋的是顏色，這條擋的是尺寸。少了它，token 化過的檔案會慢慢長回字面量，
 * 而且因為看起來「跟旁邊那行一樣」而不會有人察覺。
 */
function checkLiteralSizes(cssFiles, errors) {
  for (const file of cssFiles) {
    if (TOKEN_FILE.test(file.rel)) continue
    for (const { prop, value, no } of declarationsOf(file)) {
      if (!RHYTHM.test(prop) && !SIZE.test(prop)) continue
      const found = RHYTHM.test(prop)
        ? matchAll(value, /(-?[0-9.]+)px/g)
        : spacingInExpression(value)
      for (const px of found) {
        if (Math.abs(Number(px)) <= OPTICAL_MAX) continue
        errors.push(`${file.rel}:${no}: ${prop} 不可寫死 ${px}px，請改用 token`)
      }
    }
  }
}

/**
 * i：自訂屬性的值也要走 token。
 *
 * `declarationsOf()` 抓屬性名的正規式帶著 `(?<!-)`，所以 `--sidebar-width: 216px`
 * 這種宣告**整條被跳過**；而規則 k 只掃 token 定義檔。兩件事加起來的結果是：
 * 任何模組 CSS 都可以寫 `--row-pad: 13px` 而完全不受檢查。
 * `--sidebar-width: 216px` 能在 `config/shell/shell.module.css` 住那麼久就是這樣。
 *
 * 不分 RHYTHM／SIZE：自訂屬性沒有屬性名可以看，而同一個變數可能兩種用途都有
 * （`--layout-sidebar-width` 是尺寸，但 `page-header` 拿它當留白算）。
 * 分不出來時取嚴的那一邊，光學豁免照舊。
 */
function checkCustomPropertySizes(cssFiles, errors) {
  for (const file of cssFiles) {
    if (TOKEN_FILE.test(file.rel)) continue
    for (const { token, no, value } of eachDeclaration(file)) {
      for (const px of matchAll(value, /(-?[0-9.]+)px/g)) {
        if (Math.abs(Number(px)) <= OPTICAL_MAX) continue
        errors.push(`${file.rel}:${no}: ${token} 不可寫死 ${px}px，請改用 token`)
      }
    }
  }
}

/**
 * j：`var()` 不能用前置負號取負。
 *
 * `margin: -var(--space-8)` 不是有效的 CSS —— 整條宣告會被瀏覽器**安靜丟掉**，
 * 負邊距就這樣消失，沒有任何錯誤訊息。正確寫法是 `calc(var(--space-8) * -1)`。
 */
function checkNegatedVars(cssFiles, errors) {
  for (const line of eachLine(cssFiles)) {
    if (!/-var\(/.test(line.text)) continue
    errors.push(`${line.rel}:${line.no}: 不能用 -var(…) 取負，請改成 calc(var(…) * -1)`)
  }
}

/**
 * k：語意層的 token 必須由 `--ds-*` 撐著。
 *
 * 語意層的工作是**把原始值對應到用途**，它自己帶值就等於把原始值藏在翻譯層裡：
 * Design System 到位時那些 token 沒有槽位可以接，只能直接改右手邊的字面量。
 * `check-boundaries.mjs` 保證依賴方向，這條保證 token 的分層方向。
 */
function checkSemanticLayering(cssFiles, errors) {
  for (const file of cssFiles) {
    if (!/^app\/(tokens\/semantic|themes\/)/.test(file.rel)) continue
    for (const declaration of eachDeclaration(file)) {
      if (SEMANTIC_RAW_ALLOWLIST.has(declaration.token)) continue
      if (declaration.value.includes("var(--ds-")) continue
      errors.push(
        `${file.rel}:${declaration.no}: ${declaration.token} 沒有由 --ds-* 撐著 —— 語意層不該自己帶值`)
    }
  }
}

/**
 * l：focus 外環要整條用 `var(--focus-ring)`，不可自己組。
 *
 * `0 0 0 3px var(--color-focus-ring)` 在每個檔案各寫一次的話 —— 顏色走了 token，
 * 但粗細與位移沒有，改粗細要改每一處，而漏掉的那處不會有任何訊號。
 * 這條擋的是「複製一份 focus 樣式」這個具體行為。
 */
function checkFocusRing(cssFiles, errors) {
  for (const line of eachLine(cssFiles)) {
    if (line.isToken || !line.text.includes("--color-focus-ring")) continue
    if (line.text.includes("var(--focus-ring)")) continue
    errors.push(`${line.rel}:${line.no}: focus 外環請整條用 var(--focus-ring)，不要自己組`)
  }
}

/**
 * JS 與 CSS 各存一份、而且必須相等的數字。
 *
 * 這種重複沒辦法消掉：lucide 的 `size` prop 與 `getBoundingClientRect` 的夾擠都發生在
 * JS 那一側，CSS 的自訂屬性餵不進去。能做的是**讓它變成可驗證的重複** ——
 * 兩邊漂掉時當場紅燈，而不是等到某次改了 CSS 才發現 JS 沒跟上。
 */
const JS_CSS_PAIRS = [
  {
    label: "ICON_SIZE",
    ts: [/ICON_SIZE = \{\s*sm:\s*(\d+),\s*md:\s*(\d+),\s*lg:\s*(\d+)/, "shared/ui/internals.ts"],
    css: [/--ds-size-icon-1:\s*(\d+)px[\s\S]*?--ds-size-icon-2:\s*(\d+)px[\s\S]*?--ds-size-icon-3:\s*(\d+)px/,
      "app/tokens/primitives.css"],
  },
  {
    label: "ActionMenu 的 DROPDOWN_WIDTH",
    ts: [/DROPDOWN_WIDTH = (\d+)/, "shared/ui/patterns/ActionMenu.tsx"],
    css: [/min-width:\s*(\d+)px/, "shared/ui/styles/action-menu.module.css"],
  },
]

/** m：JS 與 CSS 各一份的數字必須相等。 */
function checkJsCssPairs(base, errors) {
  for (const { label, ts, css } of JS_CSS_PAIRS) {
    const read = ([pattern, rel]) => {
      const file = path.join(base, rel)
      if (!fs.existsSync(file)) return null
      return fs.readFileSync(file, "utf8").match(pattern)?.slice(1) ?? null
    }
    // TS 那一側整個不存在＝這棵樹沒有 UI kit（測試的 fixture 就是這樣），跳過。
    // 但它存在卻對不出數字，就是有人改了宣告的寫法而讓規則失效 —— 那要擋。
    const inTs = read(ts)
    if (!inTs) continue
    const inCss = read(css)
    if (!inCss) {
      errors.push(`${label}：${css[1]} 裡找不到對應的宣告，規則 m 對它失效了`)
      continue
    }
    if (inTs.join() === inCss.join()) continue
    errors.push(`${label}：${ts[1]} 是 ${inTs.join("／")}，${css[1]} 是 ${inCss.join("／")} —— 兩邊必須相等`)
  }
}

/**
 * g：斷點必須在允許清單內。
 *
 * 掃 `@media` 到 `{` 的整段而不是逐行：條件換行寫時，逐行看會**整條漏掉** ——
 * 那個斷點於是可以是任意值，而且沒有任何訊號。行號報 `@media` 所在的那一行。
 */
function checkBreakpoints(cssFiles, errors) {
  for (const file of cssFiles) {
    const lineOf = lineIndex(file.text)
    for (const query of file.text.matchAll(/@media[^{]*/g)) {
      const widths = matchAll(query[0], /(?:min-width|max-width|width)\s*[:<>=]+\s*([\d.]+px)/g)
      for (const width of widths) {
        if (BREAKPOINTS.has(width)) continue
        errors.push(`${file.rel}:${lineOf(query.index)}: 斷點 ${width} 不在允許清單內`)
      }
    }
  }
}

/**
 * n：vendor 的名字只能在 `primitives.css` 對照。
 *
 * 這是規則 d 的對應物。規則 d 認的是 `--ds-` 前綴，而 vendor 的前綴由上游決定
 * （`--grape-500`、`--space-md`），所以模組 CSS 直接寫 `var(--grape-500)` 它擋不到，
 * 規則 a 還會放行 —— vendor 檔確實宣告過那個名字。少了這條，adapter 那一層是白做的：
 * DS 換一批值時，繞過對照表的呼叫點會被漏掉。
 *
 * 撞名的 token 交給規則 o 報**一次**就好。少了那個排除，vendor 一宣告 `--color-primary`，
 * 這條就會對每一個本來就合法的呼叫點各報一行 —— 十幾行噪音蓋掉唯一該修的那行。
 */
function checkVendorReferences(refs, declared, errors) {
  if (declared.vendor.size === 0) return
  for (const ref of refs) {
    if (!declared.vendor.has(ref.token) || declared.global.has(ref.token)) continue
    if (ref.rel === ADAPTER_FILE || VENDOR_FILE.test(ref.rel)) continue
    errors.push(`${ref.at}: ${ref.token} 是 vendor 的原生命名，只能在 ${ADAPTER_FILE} 對照`)
  }
}

/**
 * o：vendor 不可宣告這個 repo 已經有的名字。
 *
 * DS 的產出通常把原始值與語意混在同一份檔案裡（`--color-primary: var(--grape-500)`），
 * 那些語意名字會跟 `themes/*.css` 的撞在一起。兩邊都在 `:root`，**後載入者勝而且
 * 沒有任何紅燈** —— 主題整組被上游的值蓋掉，只有用眼睛看得出來。
 *
 * 兩套 DS 之間同理：都宣告 `--space-md` 時一樣是後載入者勝、一樣沒有紅燈。
 *
 * 範圍只有 vendor：每份主題各宣告一次同一組 `--color-*` 是刻意的（那是主題的介面，
 * 由規則 r 反過來要求），不能誤擋。
 */
function checkVendorCollisions(declared, errors) {
  for (const [token, { at }] of declared.vendor) {
    const owner = declared.global.get(token)
    if (!owner) continue
    errors.push(`${at}: ${token} 與 ${owner} 撞名 —— vendor 不可宣告這個 repo 已有的名字`)
  }
  for (const { token, at, owner } of declared.clashes) {
    errors.push(`${at}: ${token} 與 ${owner} 撞名 —— 兩套 DS 不可宣告同一個名字`)
  }
}

/**
 * p：CSS 不可用 `@import` 拉外部資源。
 *
 * 字型改走 `next/font` 是刻意的決定（理由在 `app/layout.tsx` 的字型註解：`@import`
 * 是 render-blocking 的第三方請求），而少了這一條**完全沒有人守**那個決定。
 * 外部 DS 的字型產出正好就長成 `@import url("https://fonts.googleapis.com/…")`，
 * 原封不動放進 vendor 就把首屏那個問題種回來了 —— 而它不是 token 宣告，
 * 其他每一條規則都看不到它。
 */
function checkExternalImports(cssFiles, errors) {
  for (const line of eachLine(cssFiles)) {
    if (!/@import\s+(?:url\(|["'](?:https?:|\/\/))/.test(line.text)) continue
    errors.push(
      `${line.rel}:${line.no}: 不可用 @import 拉外部資源 —— 字型請照 app/layout.tsx 的 next/font 寫法接`)
  }
}

/**
 * q：主題的三份清單必須一致。
 *
 * 一份主題要**三個地方都登記**才活著：`app/themes/` 的檔案、`app/layout.tsx` 的 import
 * （每份都載入，切換是 CSS 選擇器的事）、以及 `config/theme.ts` 的 `ThemeName`。
 * 少了任何一邊都**不會報錯**，只是 `data-theme="…"` 靜靜沒有作用。
 *
 * 導入外部 DS 時一定會踩到：一套 DS 色票通常只餵得飽一套主題，另一套要整份刪掉。
 */
function checkThemeLists(base, cssFiles, errors) {
  const configPath = path.join(base, "config/theme.ts")
  // 整個組裝層不存在＝這棵樹沒有 config/（測試的 fixture 多半如此），跳過。
  // 但它存在卻讀不出聯集，就是有人改了宣告的寫法而讓規則失效 —— 那要擋。
  if (!fs.existsSync(configPath)) return
  const union = fs.readFileSync(configPath, "utf8").match(/export type ThemeName\s*=\s*([^\n]+)/)
  if (!union) {
    errors.push("config/theme.ts 找不到 ThemeName 的宣告，規則 q 對它失效了")
    return
  }
  const declared = new Set(matchAll(union[1], /"([^"]+)"/g))
  const files = new Set(cssFiles
    .filter((file) => file.rel.startsWith(`${THEME_DIR}/`))
    .map((file) => path.basename(file.rel, ".css")))
  // root layout 不存在時仍然要報「缺 import」（它是必備的）；global-error 是選配，
  // 沒有那個檔就只是少一個要對的對象。
  const entries = ENTRY_POINTS
    .map((entry) => [entry, entryImports(base, entry, "themes")])
    .filter(([entry, imported]) => imported !== null || entry === ROOT_LAYOUT)
    .map(([entry, imported]) => [entry, imported ?? new Set()])
  const named = entries.flatMap(([, imported]) => [...imported].map((css) => css.replace(/\.css$/, "")))

  for (const name of new Set([...declared, ...files, ...named])) {
    const missing = []
    if (!declared.has(name)) missing.push("config/theme.ts 的 ThemeName")
    if (!files.has(name)) missing.push(`${THEME_DIR}/${name}.css`)
    for (const [entry, imported] of entries) {
      if (!imported.has(`${name}.css`)) missing.push(`${entry} 的 import`)
    }
    if (missing.length === 0) continue
    errors.push(`主題 ${name} 只登記了一半，缺：${missing.join("、")}`)
  }
}

/**
 * s：`app/tokens/` 底下的每份 CSS 都必須被 `app/layout.tsx` import。
 *
 * 這是規則 a 看不到的另一半。宣告是從**磁碟**收集的，所以一份 token 檔只要躺在目錄裡，
 * 它宣告的名字就算「有人宣告過」—— 即使沒有任何地方載入它。導入外部 DS 時整條路徑
 * 會全綠（檔案在、對照表指得到、主題也宣告齊了），瀏覽器裡卻是那組顏色整批消失。
 *
 * 只認 layout.tsx 的 import 一種接法。CSS 自己的相對 `@import` 也載得進來，但它必須排在
 * 所有規則之前，接錯位置整條會被安靜丟掉；而且載入順序會散進各個 token 檔，
 * 撞名時就沒有一個地方講得清楚誰先誰後。
 *
 * `app/themes/` 不在這裡：那一組由規則 q 一起管，它還要同時對上 `ThemeName`。
 */
function checkTokenFileLoading(base, cssFiles, errors) {
  const entries = ENTRY_POINTS
    .map((entry) => [entry, entryImports(base, entry, "tokens")])
    .filter(([, imported]) => imported !== null)
  // 一個進入點都沒有＝這棵樹沒有組裝層（測試的 fixture 多半如此），跳過。
  if (entries.length === 0) return
  for (const file of cssFiles) {
    if (!file.rel.startsWith(`${TOKEN_DIR}/`)) continue
    const name = file.rel.slice(TOKEN_DIR.length + 1)
    for (const [entry, imported] of entries) {
      if (imported.has(name)) continue
      errors.push(`${file.rel}: 沒有被 ${entry} import —— 檔案在、宣告也收得到，`
        + "但瀏覽器沒載到它，靠它撐著的 var() 會整批解不出來（那是沒有樣式，不是錯誤）")
    }
  }
}

/**
 * r：每份主題必須宣告同一組 `--color-*`。
 *
 * 這是**主題這個介面的保證**。`default.css` 宣告在 `:root`，其他主題宣告在
 * `:root[data-theme="…"]`，所以某份主題漏掉一個顏色時它不會失效 —— 它會**靜靜沿用
 * default 的值**，暖色主題裡出現一塊灰，而且沒有任何訊號。
 *
 * 反過來說，值要怎麼給是各主題自己的事：用哪條調色線、挑哪一階都不管。
 * 對齊只發生在名字這一層 —— 那正好是 `shared/ui` 認得的那一層。
 */
function checkThemeInterface(cssFiles, errors) {
  const themes = cssFiles.filter((file) => file.rel.startsWith(`${THEME_DIR}/`))
  if (themes.length < 2) return
  const declared = themes.map((file) => ({
    rel: file.rel,
    tokens: new Set([...eachDeclaration(file)]
      .map((declaration) => declaration.token)
      .filter((token) => token.startsWith("--color-"))),
  }))
  const contract = [...new Set(declared.flatMap((theme) => [...theme.tokens]))].sort()
  for (const theme of declared) {
    for (const token of contract) {
      if (theme.tokens.has(token)) continue
      errors.push(`${theme.rel}: 少宣告 ${token} —— 每份主題都要給同一組 --color-*，`
        + "少的那個會靜靜沿用別份主題的值")
    }
  }
}

/**
 * w：`color-scheme` 只能宣告在主題檔，而且每份主題都要宣告。
 *
 * 原生表單控制項與捲軸**只認這個屬性**，沒有任何 token 管得到它。它以前寫死在
 * `tokens/semantic.css` 的 `:root` —— 那等於把「這個 app 是深色的」擺在主題介面外面：
 * 換一份亮色主題時 `--color-*` 全部換掉了，`<select>` 與捲軸仍然是深的，
 * 而規則 r 只比對 `--color-*`，這件事不會有任何紅燈。
 *
 * 值刻意不驗：`light dark` 是合法且有意義的寫法（同一份主題支援兩軌），
 * 限成 light／dark 二選一等於先把那條路堵死。
 */
function checkColorScheme(cssFiles, errors) {
  for (const file of cssFiles) {
    const declared = /(?:^|[\s;{])color-scheme\s*:/.test(file.text)
    if (!file.rel.startsWith(`${THEME_DIR}/`)) {
      if (declared) {
        errors.push(`${file.rel}: color-scheme 只能宣告在 ${THEME_DIR}/ 底下 ——`
          + " 它是主題介面的一部分，不是全站常數")
      }
      continue
    }
    if (declared) continue
    errors.push(`${file.rel}: 沒有宣告 color-scheme —— 原生表單控制項與捲軸只認它，`
      + "少了這一行，換到這份主題時它們會維持上一份主題的明暗")
  }
}

/**
 * x：原始層的陰影不可自帶色值。
 *
 * `--ds-shadow-1: 0 1px 2px rgba(0, 0, 0, 0.05)` 把「陰影是黑的」鎖在原始層，
 * 而那是**亮色 UI 的假設** —— 深色底上的黑陰影等於沒有陰影。主題換不掉它：
 * `--color-*` 那組名字裡本來沒有陰影的槽位。幾何與濃度留在原始層，
 * 顏色走主題的 `--color-shadow`，語意層把兩者接起來。
 */
function checkShadowColors(cssFiles, errors) {
  for (const file of cssFiles) {
    if (!TOKEN_FILE.test(file.rel)) continue
    for (const { token, value, no } of eachDeclaration(file)) {
      if (!/^--ds-shadow-/.test(token) || !LITERAL_COLOR.test(value)) continue
      errors.push(`${file.rel}:${no}: ${token} 不可自帶色值 —— 陰影顏色由主題的`
        + " --color-shadow 決定，這裡只放幾何")
    }
  }
}

/** 每個索引落在第幾行。行號要靠絕對位置算，因為 `style={{…}}` 常常跨行。 */
function lineIndex(text) {
  const starts = [0]
  for (let index = 0; index < text.length; index += 1) {
    if (text[index] === "\n") starts.push(index + 1)
  }
  return (offset) => {
    let line = 0
    while (line + 1 < starts.length && starts[line + 1] <= offset) line += 1
    return line + 1
  }
}

/**
 * 從 `{{` 之後往前掃。`end` 是物件的右括號位置，`next` 是整段 JSX 運算式之後。
 *
 * 深度從 2 起算（`{{` 是 JSX 運算式加上物件本身），所以物件的右括號就是**第一次**
 * 掉回 1 的那個字元 —— 巢狀物件只會 2→3→2，不會經過 1。
 */
function scanStyleObject(text, start) {
  let depth = 2
  let index = start
  let end = -1
  while (index < text.length && depth > 0) {
    const ch = text[index]
    if (QUOTES.includes(ch)) { index = skipQuoted(text, index); continue }
    depth += DEPTH_DELTA[ch] ?? 0
    if (depth === 1 && end === -1) end = index
    index += 1
  }
  return { end: end === -1 ? index : end, next: index }
}

/** 一份 TSX 裡每個 `style={{…}}` 物件的內容與起始位置。 */
function inlineStyleBlocks(text) {
  const out = []
  const marker = /style=\{\{/g
  let match
  while ((match = marker.exec(text)) !== null) {
    const start = match.index + match[0].length
    const { end, next } = scanStyleObject(text, start)
    out.push({ start, text: text.slice(start, end) })
    marker.lastIndex = next
  }
  return out
}

/** 把一個物件字面量切成最外層的每一段。巢狀與引號裡的逗號不算分隔。 */
function topLevelEntries(text) {
  const out = []
  let depth = 0
  let from = 0
  let index = 0
  while (index < text.length) {
    const ch = text[index]
    if (QUOTES.includes(ch)) { index = skipQuoted(text, index); continue }
    if (ch === "," && depth === 0) { out.push({ text: text.slice(from, index), at: from }); from = index + 1 }
    else depth += DEPTH_DELTA[ch] ?? 0
    index += 1
  }
  out.push({ text: text.slice(from), at: from })
  return out
}

/** 一個行內樣式物件裡的每一條 `prop: value`。展開運算子與巢狀物件不算。 */
function inlineDeclarations(block) {
  return topLevelEntries(block.text).flatMap((entry) => {
    const split = entry.text.match(/^\s*(["']?)([A-Za-z][A-Za-z0-9]*)\1\s*:([\s\S]*)$/)
    return split ? [{ prop: split[2], value: split[3], at: block.start + entry.at }] : []
  })
}

/** `marginLeft` → `margin-left`。行內樣式是 camelCase，RHYTHM／SIZE 認的是 CSS 的寫法。 */
function kebabCase(prop) {
  return prop.replace(/[A-Z]/g, (upper) => `-${upper.toLowerCase()}`)
}

/**
 * 一條行內宣告裡違規的裸數字。
 *
 * JSX 的數字不帶單位（`padding: 24` 就是 24px），所以裸數字要單獨認一次，
 * 不能只找 `px`。屬性範圍與規則 i 共用 RHYTHM／SIZE。
 */
function inlineLiteralSizes(prop, value) {
  const name = kebabCase(prop)
  const bare = value.trim().match(/^-?[0-9.]+$/)
  const rhythm = bare ? [bare[0]] : matchAll(value, /(-?[0-9.]+)px/g)
  const found = RHYTHM.test(name)
    ? rhythm
    : (SIZE.test(name) ? spacingInExpression(value) : [])
  return found.filter((px) => Math.abs(Number(px)) > OPTICAL_MAX)
}

/**
 * t：行內樣式不可寫死色值與節奏類數字 —— 規則 c 與 i 的 TSX 對應物。
 *
 * 規則 c／i／j／l 的輸入都是 CSS 檔，所以 `style={{…}}` 一直是完整的盲區。
 * 這不是假想的漏洞：`app/global-error.tsx` 就用它繞過了 `--space-6`、`--control-height-md`
 * 與 `--border-width-hairline`，其中 `padding: "0 18px"` 甚至不在 4px 網格上。
 * 那一頁尤其不能漏 —— 它是兩個進入點之一，整份文件反覆在講它。
 *
 * 屬性範圍與規則 i **完全一致**。刻意不擴充：CSS 與 TSX 兩側認的屬性一旦不同，
 * 就變成同一條規則的兩份定義，而它們會各自飄。
 */
function checkInlineStyles(tsFiles, errors) {
  for (const file of tsFiles) {
    const lineOf = lineIndex(file.text)
    for (const block of inlineStyleBlocks(file.text)) {
      const color = block.text.match(LITERAL_COLOR)
      if (color) {
        errors.push(`${file.rel}:${lineOf(block.start)}: 行內樣式不可寫死色值 ${color[0]}，請改用 token`)
      }
      for (const { prop, value, at } of inlineDeclarations(block)) {
        for (const px of inlineLiteralSizes(prop, value)) {
          errors.push(`${file.rel}:${lineOf(at)}: 行內樣式的 ${prop} 不可寫死 ${px}px，請改用 token`)
        }
      }
    }
  }
}

const MANIFEST_FILE = "app/manifest.ts"

/** 把一個 token 的值一路解到字面值：`--color-bg-app` → `var(--ds-gray-950)` → `#0F1115`。 */
function resolveToken(token, values, depth = 0) {
  const value = values.get(token)
  if (value === undefined || depth > 10) return null
  const next = value.match(/^var\(\s*(--[\w-]+)\s*\)$/)
  return next ? resolveToken(next[1], values, depth + 1) : value
}

/**
 * 原始層與**指定那一份**主題的所有宣告。
 *
 * 其他主題不能一起收：每份主題都宣告同一組 `--color-*`，收進同一個 Map 會互相蓋掉，
 * 解出來的是最後掃到的那份，而不是 `DEFAULT_THEME` 那份。
 */
function themeValues(cssFiles, theme) {
  const values = new Map()
  for (const file of cssFiles) {
    const other = file.rel.startsWith(`${THEME_DIR}/`) && file.rel !== `${THEME_DIR}/${theme}.css`
    if (!TOKEN_FILE.test(file.rel) || other) continue
    for (const { token, value } of eachDeclaration(file)) {
      values.set(token, value.trim())
    }
  }
  return values
}

/** 規則 u 要比對的兩個字面值。整棵樹沒有 manifest 或組裝層時回 `null`（fixture 多半如此）。 */
function manifestThemeInputs(base) {
  const manifestPath = path.join(base, MANIFEST_FILE)
  const configPath = path.join(base, "config/theme.ts")
  if (!fs.existsSync(manifestPath) || !fs.existsSync(configPath)) return null
  const declared = fs.readFileSync(manifestPath, "utf8").match(/theme_color:\s*["']([^"']+)["']/)
  const theme = fs.readFileSync(configPath, "utf8").match(/DEFAULT_THEME[^=]*=\s*["']([^"']+)["']/)
  return { declared: declared?.[1], theme: theme?.[1] }
}

/**
 * u：PWA manifest 的 `theme_color` 必須等於預設主題的 `--color-bg-app`。
 *
 * 這是整個原始碼裡唯一一個 token 系統管不到的顏色：manifest 是 JSON，吃不到 `var()`，
 * 而它住在 `.ts` 裡，規則 c 掃不到。少了這條，導入 DS 換掉整組 `--color-*` 之後，
 * PWA 的啟動畫面與狀態列會維持舊底色 —— 而且沒有任何紅燈，只有裝了 App 的人看得到。
 */
function checkManifestThemeColor(base, cssFiles, errors) {
  const inputs = manifestThemeInputs(base)
  if (!inputs) return
  const { declared, theme } = inputs
  if (!declared || !theme) {
    errors.push(`${MANIFEST_FILE} 的 theme_color 或 config/theme.ts 的 DEFAULT_THEME 讀不出來，`
      + "規則 u 對它們失效了")
    return
  }
  const resolved = resolveToken("--color-bg-app", themeValues(cssFiles, theme))
  if (resolved && resolved.toLowerCase() === declared.toLowerCase()) return
  errors.push(resolved
    ? `${MANIFEST_FILE} 的 theme_color 是 ${declared}，`
      + `但 ${theme} 主題的 --color-bg-app 解出來是 ${resolved} —— 兩邊必須相等`
    : `規則 u 解不出 ${theme} 主題的 --color-bg-app，無法比對 ${MANIFEST_FILE} 的 theme_color`)
}

// ---- 進入點 --------------------------------------------------------------

export function collectTokenErrors(base) {
  const cssFiles = read(base, CSS)
  const tsFiles = read(base, TS)
  // 掃到空集合時「規則沒接上」與「全部通過」的輸出一模一樣。寧可誤報也不要安靜綠燈。
  if (cssFiles.length === 0) return [`${base}: 掃不到任何 CSS，檢查器沒有實際執行`]

  const errors = []
  const declared = declarations(cssFiles)
  const refs = references([...cssFiles, ...tsFiles])

  checkTokenPairing(refs, declared, tokensSetFromJs(tsFiles), dynamicPrefixes(tsFiles), errors)
  checkLiteralColors(cssFiles, errors)
  checkLayering(refs, errors)
  checkLocalTokenScope(refs, declared, errors)
  checkVendorReferences(refs, declared, errors)
  checkVendorCollisions(declared, errors)
  checkComposes(cssFiles, errors)
  checkDeadClasses(cssFiles, tsFiles, errors)
  checkBreakpoints(cssFiles, errors)
  checkStyleKeys(cssFiles, tsFiles, errors)
  checkLiteralSizes(cssFiles, errors)
  checkCustomPropertySizes(cssFiles, errors)
  checkNegatedVars(cssFiles, errors)
  checkSemanticLayering(cssFiles, errors)
  checkFocusRing(cssFiles, errors)
  checkJsCssPairs(base, errors)
  checkExternalImports(cssFiles, errors)
  checkThemeLists(base, cssFiles, errors)
  checkTokenFileLoading(base, cssFiles, errors)
  checkThemeInterface(cssFiles, errors)
  checkColorScheme(cssFiles, errors)
  checkShadowColors(cssFiles, errors)
  checkInlineStyles(tsFiles, errors)
  checkManifestThemeColor(base, cssFiles, errors)
  return errors
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const errors = collectTokenErrors(root)
  if (errors.length > 0) {
    console.error(errors.join("\n"))
    process.exit(1)
  }
  console.log("Frontend design tokens OK")
}
