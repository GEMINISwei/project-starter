# 變更紀錄

版本對應 `apps/api/app/config.py` 的 `APP_VERSION`。格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)。

## [Unreleased]

## [0.0.1]

- 初始專案：FastAPI + Next.js 全端模板，含認證、使用者與角色權限、中英雙語、Alembic migration。
- 部署：發布 release 自動部署，執行名稱顯示版號與組別（`Deploy v<版號> (<組別>)`／手動觸發為 `Redeploy v<版號> (<組別>)`）。
- 備份：部署前自動備份，檔名帶版號（`<專案>_v<版號>_<日期>_<時間>.dump`）；`make db restore` 只接受與目前版本一致的備份。
- `make version` 顯示目前的版本；`make release <版號>` 更新版號與變更紀錄。
