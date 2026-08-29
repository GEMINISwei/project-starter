import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { MessagePage, MessagePageButton, MessagePageLink } from "@/shared/ui/feedback/MessagePage"
import RouteLoading from "@/shared/ui/feedback/RouteLoading"
import ActionMenu from "@/shared/ui/patterns/ActionMenu"
import FilterDialog, { useStatusFilterOptions } from "@/shared/ui/patterns/FilterDialog"
import ListTableCard from "@/shared/ui/patterns/ListTableCard"
import PageHeader from "@/shared/ui/patterns/PageHeader"
import StatusBadge from "@/shared/ui/patterns/StatusBadge"
import TableRow from "@/shared/ui/patterns/TableRow"

const routerPush = vi.fn()

vi.mock("next/navigation", () => ({
  usePathname: () => "/records",
  useRouter: () => ({ push: routerPush }),
  useSearchParams: () => new URLSearchParams("cursor=old&seq=3"),
}))

describe("shared list patterns", () => {
  beforeEach(() => routerPush.mockReset())

  it("ActionMenu 過濾空項目並執行所選動作", async () => {
    const action = vi.fn()
    render(<ActionMenu items={[null, false, { label: "編輯", onClick: action }]} />)

    await userEvent.click(screen.getByRole("button", { name: "操作選單" }))
    await userEvent.click(screen.getByRole("menuitem", { name: "編輯" }))

    expect(action).toHaveBeenCalledOnce()
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })

  it("FilterDialog 正規化輸入並導向篩選網址", async () => {
    const onClose = vi.fn()
    // 狀態選項現在是 hook（label 跟著語系走），所以在元件裡取用。
    // 沒有 LocaleProvider 時 useLocale 回預設語系，這裡拿到的就是中文標籤。
    function Subject() {
      return (
        <FilterDialog
          title="篩選"
          open
          onClose={onClose}
          fields={[
            { name: "name", label: "名稱", type: "text" },
            { name: "is_disabled", label: "狀態", type: "select", options: useStatusFilterOptions() },
          ]}
          initialValues={{ name: "", is_disabled: "" }}
        />
      )
    }
    render(<Subject />)

    await userEvent.type(screen.getByLabelText("名稱"), "  demo  ")
    await userEvent.selectOptions(screen.getByLabelText("狀態"), "true")
    await userEvent.click(screen.getByRole("button", { name: "篩選" }))

    expect(routerPush).toHaveBeenCalledWith("/records?name=demo&is_disabled=true")
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("列表外殼顯示欄名、資料與空狀態", () => {
    const { rerender } = render(
      <ListTableCard headers={["名稱"]} isEmpty={false} emptyText="沒有資料">
        <TableRow><td>範例</td></TableRow>
      </ListTableCard>,
    )
    // TableRow 存在的理由就是這個 class：窄螢幕時把表格列轉成卡片。模組不再自己
    // import UI kit 的樣式檔，所以這裡是唯一還會發現「class 掉了」的地方。
    expect(screen.getByRole("row", { name: "範例" }).className).toBeTruthy()
    expect(screen.getByRole("columnheader", { name: "名稱" })).toBeInTheDocument()
    expect(screen.getByText("範例")).toBeInTheDocument()

    rerender(<ListTableCard headers={["名稱"]} isEmpty emptyText="沒有資料">{null}</ListTableCard>)
    expect(screen.getByText("沒有資料")).toBeInTheDocument()
  })

  it("頁首、狀態與回饋元件保留可存取文字", async () => {
    const action = vi.fn()
    const { rerender } = render(
      <PageHeader
        title="項目"
        subtitle="管理項目"
        actions={<button type="button">新增</button>}
        mobileActions={[{ label: "新增", onClick: action }]}
      />,
    )
    expect(screen.getByRole("heading", { name: "項目" })).toBeInTheDocument()
    expect(screen.getByText("管理項目")).toBeInTheDocument()

    rerender(<StatusBadge label="啟用" variant="success" />)
    const badge = screen.getByText("啟用")
    expect(badge).toBeInTheDocument()
    expect(badge.className.trim().split(/\s+/)).toHaveLength(2)

    rerender(
      <MessagePage title="找不到" description="此頁不存在">
        <MessagePageButton onClick={action}>重試</MessagePageButton>
        <MessagePageLink href="/">首頁</MessagePageLink>
      </MessagePage>,
    )
    await userEvent.click(screen.getByRole("button", { name: "重試" }))
    expect(action).toHaveBeenCalledOnce()
    expect(screen.getByRole("link", { name: "首頁" })).toHaveAttribute("href", "/")

    rerender(<MessagePage title="發生錯誤" description="請稍後再試" inline />)
    expect(screen.getByRole("main")).toHaveClass("message-page", "message-page--inline")

    rerender(<RouteLoading text="讀取資料" />)
    expect(screen.getByText("讀取資料")).toBeInTheDocument()
  })
})
