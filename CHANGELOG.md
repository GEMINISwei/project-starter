# 變更紀錄

版本對應 `apps/api/app/config.py` 的 `APP_VERSION`。格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)。

## [Unreleased]

- 移除網頁上的 `/signup` 與 `REGISTER_KEY`：超級管理者只能用 `make db superuser` 建立。既有部署可以從 `.env` 刪掉 `REGISTER_KEY`，`system_state` 資料表由 migration 移除。

## [0.0.1]

- 初始專案：FastAPI + Next.js 全端模板，含認證、使用者與角色權限、中英雙語、Alembic migration。
