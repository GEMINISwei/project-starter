# 變更紀錄

版本對應 `apps/api/app/config.py` 的 `APP_VERSION`。格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)。

## [Unreleased]

- migration 合併回單一的初始結構（拿掉 `system_state`），既有的資料庫要 `make db reset` 重建。
- 移除網頁上的 `/signup` 與 `REGISTER_KEY`：超級管理者只能用 `make db superuser` 建立。`.env` 的 `REGISTER_KEY` 可以刪掉。

## [0.0.1]

- 初始專案：FastAPI + Next.js 全端模板，含認證、使用者與角色權限、中英雙語、Alembic migration。
