# 變更紀錄

版本對應 `apps/api/app/config.py` 的 `APP_VERSION`。格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)。

## [Unreleased]

- 自動部署支援多套系統：一個 GitHub environment 就是一套系統，依名稱前綴分組（`production`、
  `production-*` 是 production 組），建好 environment 就會被納入，不必改 workflow。
- 發布時要部署的組改由 repo Variables 決定：正式版看 `PUBLISH_TARGETS`，pre-release 看
  `PRE_RELEASE_TARGETS`（多組用空格分開），沒設定就失敗、不部署。pre-release 改成正式版時會部署到
  `PUBLISH_TARGETS` 的組，可以先給先行測試的組，再用同一個 tag 上正式版。
- Run workflow 新增 `target`，可以一次把既有的 tag 部署到多組（空格分開）。
- 依序部署，一套失敗不會中斷其他套；執行頁面的 Summary 列出每套的結果、失敗的步驟與這次沒有部署的組。
- image 改標組名（`:production`、`:staging`），不再標 `latest`；不同組部署不同版本時不會互相覆蓋。
- 主機上的 GHCR 登入改用每次部署自己的暫存 `DOCKER_CONFIG`，同主機的多套系統不會互相登出，
  也不再登出主機上手動登入的 GHCR。
- 部署前檢查 environment 的必填 secrets，缺了就在連主機前停下並列出缺少的項目。

## [0.0.1]

- 初始專案：FastAPI + Next.js 全端模板，含認證、使用者與角色權限、中英雙語、Alembic migration。
