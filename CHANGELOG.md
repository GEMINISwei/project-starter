# 變更紀錄

版本對應 `apps/api/app/config.py` 的 `APP_VERSION`。格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)。

## [Unreleased]

- 新增 `GET /api/system/version`（需登入），設定頁的系統版本改從後端取得，不再讀 web 的 `package.json`。
- OpenAPI 的 `info.version` 改為獨立的 `CONTRACT_VERSION`，發版不再讓契約檔跟著變。
- 移除根目錄的 `VERSION`：跟 git tag 對齊的只剩 `APP_VERSION` 與 CHANGELOG，`make release` 只改這兩處；
  `pyproject.toml`、`package.json` 與 lock 檔的版號不再跟著發版。
- 部署的 image 一律標成 `latest`，部署成功後清掉這個 repo 被取代的舊 image。
- 全新主機可以直接用 Publish 做第一次部署，不必先在主機上 `make prod`：部署前的備份在連資料 volume
  都沒有時略過（`make db backup allow-fresh`），有 volume 但資料庫沒在跑時仍然中止。

## [0.0.1]

- 初始專案：FastAPI + Next.js 全端模板，含認證、使用者與角色權限、中英雙語、Alembic migration。
