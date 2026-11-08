# 0006. 初始資料由 migrate 服務寫入，不用 Alembic 資料 migration

狀態：採用（2026-10-25）

## 背景

常見寫法是 api 開機時寫入，或寫成資料 migration。前者在多行程同時啟動時會競爭，失敗時服務已經切換；
後者發版後不能改，也不能 import model，定義一改就要再疊一支。

## 決定

- 初始資料定義在 model 的 `seed_data`，migrate 服務在 `alembic upgrade head` 之後寫入；api 開機不寫資料。
- 設了 `seed_match_key` 的表每次 migrate 都 upsert，系統角色每次部署都同步回模板的定義。

## 後果

- seed 失敗跟 migration 失敗一樣擋下部署。
- 改初始資料只改 `seed_data`，不疊 migration。
- 系統角色在資料庫裡的改動會在下次部署被覆蓋，這是刻意的。

寫法見 [`extending/seed.md`](../extending/seed.md)。
