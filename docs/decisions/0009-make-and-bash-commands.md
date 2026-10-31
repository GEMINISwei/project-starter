# 0009. 指令介面用 Makefile 加 bash 腳本

狀態：採用（2026-10-25）

## 背景

專案的日常操作（啟動、資料庫、檢查、備份、發版）需要一個統一的入口。常見的做法是 just、Taskfile 這類
task runner，或把指令寫進 `package.json` 的 scripts、用 Python 寫一個 CLI。

這些指令同時要在開發機、CI 與部署主機上跑。部署主機刻意只裝 Docker、`make`、`openssl`
（見 [`operations.md`](../operations.md#生產部署)），不裝 Node 與 uv。

## 決定

`Makefile` 只做「指令名稱 → `scripts/<指令>.sh`」的對應，實作全部寫在 bash 腳本裡，腳本也能不經 `make`
直接執行。同性質的操作是同一個指令的子指令（`make db restore`）。

`AGENTS.md` 與文件維持高密度的規則寫法，新成員（人或 AI agent）照規則走，不靠口頭傳承。

## 後果

- 三種環境都不用額外安裝工具，`make help` 就是指令清單。
- bash 容易寫出隱性的錯，所以 `make check lint` 用 shellcheck 擋，腳本的行為也有測試
  （例：`apps/api/tests/test_stack_scripts.py`）。
- 原生 Windows 不能直接跑（要透過 WSL）。團隊需要在原生 Windows 上開發，或腳本的邏輯複雜到
  bash 難以維護時，再重新檢討。
