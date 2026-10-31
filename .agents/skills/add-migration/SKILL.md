---
name: add-migration
description: 改了後端 model 的欄位、索引或約束，要新增或整理 Alembic migration 時使用。
---

# 新增 migration

完整說明在 [`extending/migrations.md`](../../../docs/extending/migrations.md)。

1. **先看能不能併進既有的那支**：找最近的 `v*` tag（含 prerelease，`git describe --tags --abbrev=0 --match 'v*'`）。
   - tag 之前就有的 migration 已經跑在主機上，**只能往前**，不可修改或刪除。
   - tag 之後新增、同一個功能的，可以併成一支，改完 `make db reset`。
   - 沒有任何 tag 時，所有 migration 都還沒發版。
2. **產生**：`make db migration "說明"`。
3. **讀過產出**：autogenerate 固定會漏三件事（NOT NULL 欄位沒有預設值或回填、改名被當成刪除加新增、
   不能在交易裡跑的 DDL），對照 [注意事項](../../../docs/extending/migrations.md#注意事項) 補上。
4. **檢查**：`make check integration`（model 與 migration 一致）與 `make check migrate`（已發版的沒被改）。
5. **schema 有變**：`make gen-types`，契約與前端型別兩份產出一起 commit。
6. 在 PR 描述的「檢查」提醒審查者：兩版之間多了 migration 就不能回滾
   （[說明](../../../docs/operations.md#回滾與-migration)）。
