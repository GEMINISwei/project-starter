/**
 * UI kit 原語的行為契約: 每個模組都在用它們, 改壞的影響是全站的。
 *
 * 釘住的是**不寫出來就會被當成隨意細節**的那些決定 —— 按鈕預設 `type="button"`、
 * 數字輸入在元件內夾取範圍、勾選框回報 boolean 而不是字串、Modal 開啟時把焦點移進去。
 * 這些每一條被改掉都不會有任何檢查器抱怨, 但會在某個表單上安靜地壞掉。
 *
 * 斷言一律從**使用者看得到/操作得到的東西**下手 (文字、角色、輸入框標籤),
 * 不戳 class name 或內部 state: 後者會在改樣式時假性失敗, 卻抓不到真正的行為退化。
 * 新增 kit 元件時照這個方式寫。
 */

import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import {
  Button, Container, Flex, Form, Modal, SelectInput, TextInput,
} from "@/shared/ui"

describe("Button", () => {

  it("預設 type 是 button，避免在表單裡誤觸送出", () => {
    // 這是實務上很常見的 bug: 把按鈕放進 <form> 卻沒設 type, 一按就整頁送出。
    render(<Button>取消</Button>)

    expect(screen.getByRole("button", { name: "取消" })).toHaveAttribute("type", "button")
  })

  it("form prop 讓按鈕能送出版面上別處的表單", () => {
    // 頁尾操作列的儲存鈕不在 <form> 內, 靠 form="<id>" 關聯。
    render(<Button type="submit" form="role-edit-form">儲存</Button>)

    expect(screen.getByRole("button", { name: "儲存" })).toHaveAttribute("form", "role-edit-form")
  })
})

describe("Flex 的版面契約", () => {
  // 這一組**刻意**斷言 style 屬性, 是本檔案「只測使用者看得到的東西」的例外。
  //
  // 理由: 版面規則住在 CSS (`:where(.flex)`), 元件只負責把有帶的 prop 換成 `--flex-*`。
  // 「沒帶的 prop 不可以吐出值」是這個分工的**契約**而不是實作細節 —— 一旦破壞,
  // 呼叫端用 className 設的 justify-content (例如 pagination.tsx 的 `.paginationButtons`)
  // 就會被預設值蓋掉, 而畫面只是稍微歪掉, 沒有任何測試會紅。
  it("沒帶的 prop 不會寫進 style，呼叫端的 class 才蓋得過預設", () => {
    render(<Flex gap={2}>內容</Flex>)
    const style = screen.getByText("內容").getAttribute("style") ?? ""

    expect(style).toContain("--flex-gap: var(--space-2)")
    expect(style).not.toContain("--flex-justify")
    expect(style).not.toContain("--flex-align")
    expect(style).not.toContain("--flex-width")
  })

  it("間距換算成刻度的 token，而不是寫死的 px", () => {
    // 刻度的單一事實來源是 shared/ui/styles/tokens.css 的 --space-*; 這裡寫死 px 就會和 CSS 漂掉。
    render(<Flex gap={4}>內容</Flex>)

    expect(screen.getByText("內容").getAttribute("style")).toContain("var(--space-4)")
  })
})

describe("Container", () => {

  it("as 可以換成語意標籤", () => {
    // 不用 main 當例子: 受保護區的 main 地標由外殼提供 (見 docs/architecture.md)。
    render(<Container as="section">內容</Container>)

    expect(screen.getByText("內容").tagName).toBe("SECTION")
  })
})

describe("TextInput", () => {
  it("label 會和輸入框關聯，讀螢幕與測試都能靠標籤找到它", () => {
    render(<TextInput label="暱稱" />)

    expect(screen.getByLabelText(/暱稱/)).toBeInTheDocument()
  })

  it("輸入時把當前值傳給 onChange", async () => {
    const onChange = vi.fn()
    render(<TextInput label="帳號" onChange={onChange} />)

    await userEvent.type(screen.getByLabelText(/帳號/), "abc")

    expect(onChange).toHaveBeenCalledTimes(3)
    expect(onChange).toHaveBeenLastCalledWith("abc")
  })

  it("required 會在畫面上標示必填", () => {
    render(<TextInput label="密碼" required />)

    expect(screen.getByLabelText(/密碼/)).toBeRequired()
  })

  it("欄位錯誤會顯示並標記輸入框", () => {
    render(<TextInput label="密碼" error="至少 8 個字元" />)

    expect(screen.getByText("至少 8 個字元")).toHaveAttribute("role", "alert")
    expect(screen.getByLabelText(/密碼/)).toHaveAttribute("aria-invalid", "true")
  })
})

describe("欄位標籤", () => {
  it("必填欄位的標籤帶星號，選填的不帶", () => {
    render(
      <>
        <TextInput label="帳號" required />
        <SelectInput label="語系" options={[{ value: "zh", label: "中文" }]} />
      </>,
    )

    expect(screen.getByText("帳號").textContent).toBe("帳號*")
    expect(screen.getByText("語系").textContent).toBe("語系")
  })
})

describe("Modal", () => {
  it("關閉時不渲染內容", () => {
    render(<Modal title="測試" open={false}>內容</Modal>)

    expect(screen.queryByText("內容")).not.toBeInTheDocument()
  })

  it("按 Escape 會要求關閉", async () => {
    const onOpenChange = vi.fn()
    render(<Modal title="測試" open onOpenChange={onOpenChange}>內容</Modal>)

    await userEvent.keyboard("{Escape}")

    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it("開啟時焦點會移進對話框", () => {
    render(<Modal title="測試" open onOpenChange={() => {}}>內容</Modal>)

    const dialog = screen.getByRole("dialog")
    expect(dialog.contains(document.activeElement)).toBe(true)
  })
})

describe("Form", () => {
  it("送出時呼叫 onSubmit", async () => {
    const onSubmit = vi.fn((event: React.FormEvent) => event.preventDefault())
    render(
      <Form onSubmit={onSubmit}>
        <Button type="submit">送出</Button>
      </Form>,
    )

    await userEvent.click(screen.getByRole("button", { name: "送出" }))

    expect(onSubmit).toHaveBeenCalled()
  })

  it("帶 id 讓表單外的按鈕能以 form=<id> 觸發送出", () => {
    // FormPageShell 的送出鈕在表單外面, 靠這個 id 接回來; 沒有 id 就永遠送不出去。
    render(<Form id="edit-form"><TextInput label="名稱" /></Form>)

    expect(document.getElementById("edit-form")?.tagName).toBe("FORM")
  })
})
