---
name: release
description: 發版：盤點相依、make release 更新版號與 CHANGELOG、在 GitHub 發布 release 觸發部署。只在使用者明確要求發版時使用。
disable-model-invocation: true
---

# 發版

步驟與 `make release` 會先檢查哪些事，見 [`operations.md`](../../../docs/operations.md) 的〈發版〉段落；
版號規則見 `AGENTS.md`〈改完之後〉的發版那一列。

1. **盤點相依**：列出落後的套件與有沒有安全更新，問使用者這次要不要整批升級
   （[相依升級](../../../docs/workflow.md#相依升級)）。
2. **確認版號**：跟使用者確認要發的版號，以及要不要先當 pre-release 給先行測試的組。
3. **`make release <版號>`**：只改 `APP_VERSION` 與 CHANGELOG，不要手動改其他版號。檢查沒過就停下來回報，
   不要繞過。
4. **給使用者看 diff**，同意後再 commit 與 push。
5. **在 GitHub 發布 release 會直接部署**：tag 填 `v<版號>`。這一步由使用者做，或使用者明確同意後才做。
6. 部署開始後在背景等 Deploy workflow 跑完，回報每一套的結果。
