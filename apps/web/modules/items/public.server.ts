/**
 * items 模組的 Server 公開面。
 *
 * 頁面一律以**具名**方式轉出（而不是 `export { default }`）：一個模組可能有多個頁面，
 * 具名之後不必為第二個頁面另開一個 public entry，`app/` 的 route adapter 也永遠只需要
 * 認得這一個檔案。
 *
 * props 型別也要轉出：route adapter 是薄 wrapper，靠這個型別接住 Next 傳進來的 props
 * 再原封不動往下傳，不必把 searchParams 的形狀在兩個地方各寫一次。
 */

export { default as ItemsPage, generateMetadata as generateItemsMetadata } from "./page.server"
export type { ItemsPageProps } from "./page.server"
