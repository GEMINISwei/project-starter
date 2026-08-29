"""靜態守衛：送到使用者眼前的 WS／推播文字不可以是寫死的字串。

`docs/extending.md`〈不是錯誤的文字一樣要雙語〉寫的是慣例（這些欄位要走
`LangText` + `resolve_text()`），而 `Permission`／`WsEventType`／`Language` 各自
有測試或型別系統在守，只有這一條沒有。這支測試補上那個缺口，涵蓋兩個會帶自由文字
到使用者眼前的呼叫點：`WsEvent.message` 與 `NotificationPayload.title`／`.body`。
"""

import ast
from pathlib import Path

SRC = Path(__file__).parents[1]

# 欄位對照：`WsEvent` 承載文字的欄位是 `message`；`NotificationPayload` 是 `title`/`body`。
# 只抓這兩個建構子，不是通用規則 —— 其餘會送到使用者眼前的文字（HTTP 錯誤訊息）已經由
# `LangException`／`resolve_text()` 的呼叫慣例與 mypy 對 `LangText` 必填欄位的檢查擋著。
TARGETS = {
    "WsEvent": ("message",),
    "NotificationPayload": ("title", "body"),
}


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _violations(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fields = TARGETS.get(_call_name(node) or "")
        if not fields:
            continue
        for kw in node.keywords:
            # 字面字串（`ast.Constant`）或 f-string（`ast.JoinedStr`）判定違規；
            # 呼叫（如 `resolve_text(...)`）或屬性/名稱引用（如 `body.title`，透傳
            # 使用者自己打的字，見 extending.md 決策表）放行 —— 只抓「圖方便寫死字串」
            # 這一種樣態，不驗證語意層面的雙語完整性。
            if kw.arg in fields and isinstance(kw.value, (ast.Constant, ast.JoinedStr)):
                yield f"{path.relative_to(SRC)}:{node.lineno} {_call_name(node)}({kw.arg}=...)"


def test_ws_and_push_user_facing_text_are_not_literal_strings():
    violations = [v for path in (SRC / "modules").rglob("*.py") for v in _violations(path)]
    assert violations == []
