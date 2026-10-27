# 0007. 初始資料由 migrate 服務寫入，不用 Alembic 資料 migration

狀態：採用（2026-10-25）

## 背景

初始資料（系統角色等）常見的寫法有兩種：api 開機時寫入，或寫成 Alembic 的資料 migration。
開機時寫入會在多個行程同時啟動時互相競爭，失敗時服務也已經切換了。資料 migration 發版後不能再改，
而且不能 import model，系統角色的定義改了就得再疊一支。

## 決定

- 初始資料定義在 model class 的 `seed_data`，由 migrate 服務在 `alembic upgrade head` 之後寫入。
- api 開機時不寫任何資料。
- 設了 `seed_match_key` 的表每次 migrate 都依此 upsert，系統角色因此每次部署都會同步回模板的定義。

## 後果

- seed 失敗跟 migration 失敗一樣，會擋下部署，服務不會切換。
- 修改初始資料只要改 `seed_data`，不用疊 migration。
- api 加副本不受影響。
- 系統角色在資料庫裡的改動會在下次部署時被覆蓋，這是刻意的。

寫法見 [`extending.md`](../extending.md#初始資料seed)。
