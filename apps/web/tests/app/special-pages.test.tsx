import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import ProtectedErrorBoundary from "@/app/(protected)/error"
import ErrorBoundary from "@/app/error"
import NotFoundView from "@/app/not-found-view"

describe("App Router 特殊頁面", () => {
  it("root 與 protected error 都能觸發 reset，且 protected error 使用 inline 版型", async () => {
    const rootReset = vi.fn()
    const protectedReset = vi.fn()
    const error = new Error("test")
    const { rerender } = render(<ErrorBoundary error={error} reset={rootReset} />)

    expect(screen.getByRole("main")).toHaveClass("message-page")
    expect(screen.getByRole("main")).not.toHaveClass("message-page--inline")
    await userEvent.click(screen.getByRole("button", { name: "重新載入" }))
    expect(rootReset).toHaveBeenCalledOnce()

    rerender(<ProtectedErrorBoundary error={error} reset={protectedReset} />)
    expect(screen.getByRole("main")).toHaveClass("message-page", "message-page--inline")
    await userEvent.click(screen.getByRole("button", { name: "重新載入" }))
    expect(protectedReset).toHaveBeenCalledOnce()
  })

  // not-found.tsx 是 Server Component（要有 generateMetadata），畫面本體拆在
  // not-found-view.tsx，所以這裡測的是後者。
  it("not-found 保留自訂訊息與首頁連結", () => {
    render(<NotFoundView />)

    expect(screen.getByRole("heading", { name: "找不到頁面" })).toBeInTheDocument()
    expect(screen.getByText("這個網址不存在，或是內容已經被移除。")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "回首頁" })).toHaveAttribute("href", "/")
  })
})
