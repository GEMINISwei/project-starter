---
name: release
description: 發版：盤點相依與這一版的內容、make release 更新版號並開 PR、合併後經使用者同意才發布 release 觸發部署。只在使用者明確要求發版時使用。
disable-model-invocation: true
---

# 發版

步驟與 `make release` 會先檢查哪些事，見 [`operations.md`](../../../docs/operations.md) 的〈發版〉段落；
版號規則見 `AGENTS.md`〈改完之後〉的發版那一列。

## 發布一定要先問使用者

**發布 release 會直接部署到正式環境（或先行測試的組）。** 不論前面的步驟多順利、使用者之前說過什麼，
都要在發布前停下來：把 `preview.sh` 的輸出給使用者看，問「要發布嗎？」，**等使用者在這一輪明確回答要發布**
才執行 `publish.sh`。「開始發版」「好」「繼續」這類對前面步驟的同意都不算。沒得到答案就停在這裡回報，
不要自己判斷時機到了。

- 只用固定寫法 `.agents/skills/release/scripts/publish.sh <版號> [--prerelease]`，它會再跳一次確認。
  不要直接下 `gh release create/edit/delete` 或換寫法呼叫，hook 會擋下，被擋時照理由做，不要繞過。
- 把 pre-release 改成正式版也是發布（會部署到 `PUBLISH_TARGETS`），一樣要先問。
- 重新部署與回滾不在這個 skill 裡，由使用者自己觸發。

## 步驟

1. **盤點**，結果整理給使用者，問這次的範圍：
   - 相依：列出落後的套件與有沒有安全更新，問要不要先整批升級（[相依升級](../../../docs/workflow.md#相依升級)）。
     整批升級是另一個 PR，合併之後再回來發版。
   - CHANGELOG 有沒有漏：對照 `git log --format=%s <上一個 v* tag>..origin/main` 與 `[Unreleased]` 的條目，
     指出看起來有行為變更卻沒寫到的 commit。要補的話走一般的 PR。
   - migration：列出上一個 tag 之後新增的 migration（`git diff --name-only --diff-filter=A <tag>..origin/main -- apps/api/migrations/versions`）。
     有的話提醒：發出去之後就不能回滾到上一版；同一個功能的幾支可以先併成一支
     （[發版之前可以整理](../../../docs/extending/migrations.md#發版之前可以整理)）。
2. **建議版號**：依 `[Unreleased]` 的內容提一個版號（`1.0.0` 之前：有不相容的變更升 minor，其餘升 patch；
   之後照 SemVer），跟使用者確認版號，以及要不要先當 pre-release 給先行測試的組。
3. **`make release <版號>`**：在最新的 `main` 上執行。它只改 `APP_VERSION` 與 CHANGELOG，改完切到
   `chore/release-v<版號>` 分支；不要手動改其他版號。檢查沒過就停下來回報，不要繞過。
4. **開 PR**：給使用者看 diff，commit、push，開 PR，標題 `chore(release): v<版號>`，描述照三段寫。
   之後照 `watch-pr` 等 CI 與合併；合併由使用者做。
5. **合併之後先預覽**：`.agents/skills/release/scripts/preview.sh <版號> [--prerelease]`，
   它從 `origin/main` 算出要建的 tag、指向的 commit、會部署的組與 release 內文（取自 CHANGELOG），不改任何東西。
   沒過（例如 PR 還沒合併）就回報原因。
6. **問使用者要不要發布**（見上一節），同意了才執行 `publish.sh`，參數與預覽時相同。
7. **部署開始後**在背景等 Deploy workflow 跑完，回報每一套的結果。用了 pre-release 的話，提醒觀察沒問題後
   可以改成正式版：那時再從第 5 步（不帶 `--prerelease`）開始，一樣先問。
