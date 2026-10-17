# 變更紀錄

版本對應 `apps/api/app/config.py` 的 `APP_VERSION`。格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)。

## [Unreleased]

- 手動觸發的部署（回滾、補跑）執行名稱改為 `Redeploy v<版號> (<組別>)`。

## [0.0.3]

- Deploy 的執行名稱改為顯示 `Publish`／`Pre-Release`，不再顯示 Variable 名稱。
- 備份檔名帶上版號：`<專案>_v<版號>_<日期>_<時間>.dump`；部署改為在 checkout 新 tag 之前備份，版號才是當時線上的版本。
- 新增 `make version`，顯示目前的版本。
- `make db restore` 只列出、也只接受與 `make version` 一致的備份，清單顯示 `編號) v<版號> <日期> <時間>`，不帶路徑。

## [0.0.2]

- README 精簡：移除首次登入步驟與指令清單（細節以 `docs/` 為準）。

## [0.0.1]

- 初始專案：FastAPI + Next.js 全端模板，含認證、使用者與角色權限、中英雙語、Alembic migration。
