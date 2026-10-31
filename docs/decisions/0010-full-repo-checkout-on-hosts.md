# 0010. 部署主機上 git clone 整份 repo

狀態：採用（2026-10-25）

## 背景

image 已經由 CI 建好推到 GHCR，常見的做法是主機上只放一份 compose 檔與 `.env`，拉 image 就啟動，
主機上沒有原始碼。

但這個專案的主機維運指令（`make backup`、`make db restore`、`make services`、`make start` 前的
migration 與 nginx 檢查）都寫在 `Makefile`、`scripts/` 與 `infra/` 裡，compose 檔與 nginx 模板也是從原始碼
bind mount 的。

## 決定

部署主機 `git clone` 整份 repo，checkout 要上線的那個 `v*` tag 再 `make start`。自動部署也是 SSH 進去
`git checkout` 同一個 tag 再拉 image（見 [`operations.md`](../operations.md#自動部署)）。

## 後果

- 主機上跟開發機用同一套指令，維運腳本與 compose 檔跟著版本走，不會出現「image 是新版、腳本是舊版」。
- 主機上有原始碼。`MODE=production` 時 `make start` 只認停在 `v<APP_VERSION>` tag 上的 checkout，
  避免在主機上 `git pull` 了 main 就上線一份沒發版的程式碼。
- 改成多副本或交給容器平台（Kubernetes 等）部署、主機上不再執行維運指令時，再重新檢討。
