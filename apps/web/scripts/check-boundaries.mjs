import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import ts from "typescript"

// `__dirname` 相對而不是 CWD 相對：這支腳本被 `npm run lint` 從 app 根呼叫，但也會被
// 從別處（編輯器、CI 的其他 working directory）直接執行。以 CWD 為基準時，換個目錄
// 執行不會報錯，只會掃到空集合然後印出「OK」—— 那是最糟的失敗方式。
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")

// src/ 拿掉之後 root 就是整個 app 根，底下同時住著 `node_modules/`、`.next/`、
// `coverage/`、`public/` 與這支腳本自己。所以用白名單而不是黑名單：黑名單漏一項
// 是掃進幾萬個 node_modules 檔案，白名單漏一項只是少檢查一個目錄。
//
// `tests/` 刻意不在名單裡：邊界規則守的是**產品程式碼**的依賴拓撲，測試本來就該直接
// 指進被測目標（`@/modules/items/capabilities` 不是 public entry）。這也讓兩邊同一套
// 規則 —— 後端 `tests/test_architecture.py` 的 `PACKAGE_DIRS` 同樣只有那三個原始碼目錄。
const SOURCE_DIRS = ["app", "config", "modules", "shared"]

// 根目錄的散檔也要掃：`proxy.ts` 是 Next 的慣例檔（Next 16 把 middleware.ts 改名成它），
// 未來的 instrumentation.ts 之類同理，那些檔案的跨層引用正是這裡要擋的。
// 只有建置設定不算應用程式碼 —— vitest.config.ts 想 import 什麼都合理。
// 注意這跟 `config/` 目錄無關：那是組裝根（要檢查），這裡排除的是 `*.config.ts` 這種
// 根目錄的建置設定散檔。同名只是巧合。
const CONFIG_FILE = /\.config\.[cm]?[jt]s$/

const extensions = new Set([".ts", ".tsx", ".mts"])
const errors = []

function filesIn(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(directory, entry.name)
    if (entry.isDirectory()) return filesIn(full)
    return extensions.has(path.extname(entry.name)) && !entry.name.endsWith(".d.ts") ? [full] : []
  })
}

/** 檢查對象：白名單的來源目錄（遞迴）＋ 根目錄的散檔（不遞迴）。 */
function sourceFiles() {
  const loose = fs.readdirSync(root, { withFileTypes: true })
    .filter((entry) =>
      entry.isFile()
      && extensions.has(path.extname(entry.name))
      && !entry.name.endsWith(".d.ts")
      && !CONFIG_FILE.test(entry.name))
    .map((entry) => path.join(root, entry.name))

  const inDirs = SOURCE_DIRS
    .filter((dir) => fs.existsSync(path.join(root, dir)))
    .flatMap((dir) => filesIn(path.join(root, dir)))

  return [...loose, ...inDirs]
}

function relative(file) { return path.relative(root, file).split(path.sep).join("/") }
function moduleName(file) {
  const match = relative(file).match(/^modules\/([^/]+)/)
  return match?.[1] ?? null
}
function targetPath(source, specifier) {
  if (specifier.startsWith("@/")) return specifier.slice(2)
  if (!specifier.startsWith(".")) return null
  return path.relative(root, path.resolve(path.dirname(source), specifier)).split(path.sep).join("/")
}
function targetHasUseServer(source, specifier) {
  const base = specifier.startsWith("@/")
    ? path.join(root, specifier.slice(2))
    : path.resolve(path.dirname(source), specifier)
  for (const suffix of ["", ".ts", ".tsx", "/index.ts", "/index.tsx"]) {
    const candidate = `${base}${suffix}`
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
      return fs.readFileSync(candidate, "utf8").trimStart().startsWith('"use server"')
    }
  }
  return false
}

/**
 * 檔案裡所有指向別的檔案的路徑。
 *
 * 三種語法都要收：`import … from`、`export … from`、以及動態 `import()`。
 * 只看 `import` 是不夠的 —— route adapter 與每個 public entry 用的都是 `export … from`，
 * 漏掉它等於邊界規則在最關鍵的那道接縫上完全失效。
 */
function moduleSpecifiers(sourceFile) {
  const specifiers = []

  function visit(node) {
    if (
      (ts.isImportDeclaration(node) || ts.isExportDeclaration(node))
      && node.moduleSpecifier
      && ts.isStringLiteral(node.moduleSpecifier)
    ) {
      specifiers.push(node.moduleSpecifier.text)
    } else if (
      ts.isCallExpression(node)
      && node.expression.kind === ts.SyntaxKind.ImportKeyword
      && node.arguments.length > 0
      && ts.isStringLiteral(node.arguments[0])
    ) {
      specifiers.push(node.arguments[0].text)
    }
    // 動態 import 可以藏在任何運算式裡，所以要走完整棵樹，不能只看頂層宣告。
    ts.forEachChild(node, visit)
  }

  visit(sourceFile)
  return specifiers
}

/**
 * module 對外只有這些檔案：`public.server`／`public.client` 給執行期用，`manifest` 給組裝用。
 *
 * 兩個 runtime 各一個檔，名字寫死而不是 `public.*`：後者會把誤建的 `public.internal.ts`
 * 也當成公開面，而那種檔案正是「公開面慢慢長大」的起點。
 */
function isPublicEntry(entry) {
  return entry === "manifest" || /^public\.(server|client)$/.test(entry)
}

/**
 * UI kit 的公開面只有 `@/shared/ui` 一個路徑。
 *
 * 唯一例外是這張全域樣式表：`global-error.tsx` 會在 root layout 之外渲染，
 * 拿不到 CSS module，所以 MessagePage 的樣式必須以全域 CSS 在 root layout 載入一次。
 */
const SHARED_UI_DEEP_IMPORT_ALLOWLIST = new Set([
  "app/layout.tsx|shared/ui/styles/message-page.css",
])

/**
 * module 的檔案放置規則 —— AGENTS.md 硬規則 6，以及「每個模組都要有 i18n」。
 *
 * 這是**依賴拓撲以外**的另一半。上面那些規則管的是「誰可以引用誰」，這條管的是
 * 「檔案該放哪」。少了它，新開一個 `modules/foo/components/` 會靜靜通過 lint 與 CI，
 * 直到有人 review 時剛好想起這條規則。
 *
 * 為什麼只允許 `ui/` 一層：一個模組通常十幾個檔案，多分一層要付的是「每次找東西
 * 都得先猜它被歸到哪一類」。理由與完整說明見 docs/architecture.md 的
 * 「Frontend module 介面」。
 */
/** 目錄名 —— 模組底下只能有 `ui/`，而 `ui/` 底下不再分層。兩種情況的訊息要分得開。 */
function nestedDirErrors(dir, moduleName, children) {
  const found = []
  for (const child of children) {
    if (!child.isDirectory()) continue
    if (child.name !== "ui") {
      found.push(`modules/${moduleName}/${child.name}/: 模組底下只能有 ui/，`
        + "資料與規則放模組根、畫面放 ui/（見 docs/architecture.md）")
      continue
    }
    // `ui/` 底下也不准再分層。少了這一段，把 `components/`／`hooks/` 塞進 ui/ 就繞過了
    // 整條規則 —— 而那跟直接開在模組根違反的是同一件事（每次找東西都得先猜分類）。
    for (const nested of fs.readdirSync(path.join(dir, "ui"), { withFileTypes: true })) {
      if (!nested.isDirectory()) continue
      found.push(`modules/${moduleName}/ui/${nested.name}/: ui/ 底下不再分層，`
        + "元件、只服務畫面的 hook 與 CSS module 平鋪在 ui/ 就好（見 docs/architecture.md）")
    }
  }
  return found
}

export function collectLayoutErrors(base) {
  const found = []
  const modulesDir = path.join(base, "modules")
  if (!fs.existsSync(modulesDir)) return found
  for (const entry of fs.readdirSync(modulesDir, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue
    const dir = path.join(modulesDir, entry.name)
    const children = fs.readdirSync(dir, { withFileTypes: true })
    found.push(...nestedDirErrors(dir, entry.name, children))
    const names = new Set(children.filter((child) => child.isFile()).map((child) => child.name))
    // 必備三件：manifest（組裝層要讀）、至少一個 public entry（沒有的話這個模組
    // 沒有對外的面）、i18n（每個使用者可見的字串都要有中英兩份，字串住擁有它的那一層）。
    if (!names.has("manifest.ts")) found.push(`modules/${entry.name}/: 缺 manifest.ts`)
    if (!names.has("i18n.ts")) found.push(`modules/${entry.name}/: 缺 i18n.ts`)
    if (![...names].some((name) => /^public\.(server|client)\.ts$/.test(name))) {
      found.push(`modules/${entry.name}/: 缺 public.server.ts 或 public.client.ts`)
    }
  }
  return found
}

errors.push(...collectLayoutErrors(root))

for (const file of sourceFiles()) {
  const sourceText = fs.readFileSync(file, "utf8")
  const sourceFile = ts.createSourceFile(file, sourceText, ts.ScriptTarget.Latest, true)
  const source = relative(file)
  const sourceModule = moduleName(file)
  const isComposition = /^(app|config)\//.test(source)
  const isClient = sourceText.trimStart().startsWith('"use client"')
  const isManifest = /^modules\/[^/]+\/manifest\.ts$/.test(source)

  if (isManifest) {
    if (isClient) errors.push(`${source}: manifest 不可標記為 client module`)
    if (/\b(window|document|navigator|localStorage|sessionStorage)\b/.test(sourceText)) {
      errors.push(`${source}: manifest 不可使用瀏覽器 API`)
    }
  }

  for (const specifier of moduleSpecifiers(sourceFile)) {
    if (isManifest && (/^(react|next)(\/|$)/.test(specifier) || specifier === "server-only" || specifier.includes(".server"))) {
      errors.push(`${source}: manifest 必須保持 edge-safe，實際引用 ${specifier}`)
    }

    const target = targetPath(file, specifier)
    if (!target) continue

    if (source.startsWith("shared/") && /^(modules|app|config)\//.test(target)) {
      errors.push(`${source}: shared 不可引用 ${target}`)
    }

    if (target.startsWith("modules/")) {
      const [, targetModule, ...rest] = target.split("/")
      const entry = rest.join("/")

      if (sourceModule && targetModule !== sourceModule && !isPublicEntry(entry)) {
        errors.push(`${source}: 跨模組只能引用 public entry，實際為 ${target}`)
      }

      // 模組內部一律相對路徑。同一個檔案有時 `./x`、有時 `@/modules/me/x` 時，
      // 「這是模組自己的東西還是別人的」要一路讀到路徑尾才知道；而搬動模組時，
      // 只有相對路徑會整包跟著走。
      if (sourceModule && targetModule === sourceModule && !specifier.startsWith(".")) {
        errors.push(`${source}: 模組內部請用相對路徑，實際為 ${specifier}`)
      }

      // 組裝層跟其他 module 一樣只能走公開面。少了這條，`app/` 的 route adapter 可以
      // 直接指進模組內部，module 的內部結構就不再能安全重整。
      if (isComposition && !isPublicEntry(entry)) {
        errors.push(`${source}: 組裝層只能引用 module 的 public entry 或 manifest，實際為 ${target}`)
      }
    }

    if (sourceModule && /^(app|config)\//.test(target)) {
      errors.push(`${source}: module 不可反向引用 composition layer ${target}`)
    }

    // UI kit 只有 `@/shared/ui` 一個入口。少了這條，`internals.ts` 與 `styles/**`
    // 會慢慢變成事實上的公開介面，UI kit 之後就再也不能安全調整內部結構。
    if (
      target.startsWith("shared/ui/")
      && !source.startsWith("shared/ui/")
      && !SHARED_UI_DEEP_IMPORT_ALLOWLIST.has(`${source}|${target}`)
    ) {
      errors.push(`${source}: shared/ui 只能整包從 "@/shared/ui" 引用，實際為 ${target}`)
    }

    if (isClient && target.includes(".server") && !targetHasUseServer(file, specifier)) {
      errors.push(`${source}: client 不可引用 server-only module ${target}`)
    }
  }
}

// 直接執行時才輸出與離開 —— 被 import 時（規則自己的測試）不可以把整個 process 帶走。
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (errors.length > 0) {
    console.error(errors.join("\n"))
    process.exit(1)
  }
  console.log("Frontend import boundaries OK")
}
