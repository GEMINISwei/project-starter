# 0008. 部署主機上 git clone 整份 repo

狀態：採用（2026-10-25）

## 背景

image 由 CI 推到 GHCR，主流做法是主機只放 compose 檔與 `.env`。但這個專案的維運指令（`make backup`、
`make db restore`、`make services`、`make start` 前的檢查）寫在 `Makefile`、`scripts/`、`infra/`，
compose 檔與 nginx 模板也從原始碼 bind mount。

## 決定

主機 `git clone` 整份 repo，checkout 要上線的 `v*` tag 再 `make start`；自動部署也是 SSH 進去 checkout 同一個 tag
再拉 image（見 [`operations.md`](../operations.md#自動部署)）。

## 後果

- 主機與開發機用同一套指令，腳本跟著版本走。
- `MODE=production` 時 `make start` 只認停在 `v<APP_VERSION>` tag 的 checkout，避免上線沒發版的程式碼。
- 改用多副本或容器平台、主機不再執行維運指令時重新檢討。
