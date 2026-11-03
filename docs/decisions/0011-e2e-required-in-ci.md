# 0011. Playwright E2E 是 CI 與部署的必要檢查

狀態：採用（2026-10-25）

## 背景

E2E 要起一整套正式環境的 image 與 nginx，是 CI 裡最慢的一項。常見的取捨是只在本機或定時排程跑，
不擋 PR 合併與部署。

但 proxy 導向、cookie 屬性、Server Action、權限導向、撤銷 session 這些行為，只有整套跑起來才看得到，
單元測試與 build 都會綠燈（見 [`testing.md`](../testing.md#e2ee2e)）。

## 決定

`e2e` 是 CI 的一個 job，列在 `main` ruleset 的 required checks 裡。只放跨層的 smoke 測試，畫面分支仍然用 vitest 測。

要部署的 commit 一定通過包含它的整套 CI，但**不重複跑**：tag 指向的是合併進 `main` 的 commit，
它在 `main` 上已經跑過同一套 CI（push 觸發，或 push 沒觸發時手動補跑）而且成功，部署就沿用那次的結果；
查不到才在部署前跑一次。PR 上的 run 不算，它測的是 PR 的 head，不是 squash 之後的 commit。

## 後果

- 每個 PR 都多等 E2E 的時間，換到的是登入、導向、cookie 這類「壞了也不會報錯」的行為一定被跑過。
- 發版時同一個 commit 只在 PR 與 `main` 各跑一次，部署不再多等一輪。代價是回滾到舊 tag 時，沿用的是
  當時那份 `ci.yml` 的結果，不是現在這份；那個版本當時已經通過它自己的檢查，接受這個差異。
- E2E 刻意不開 retries，偶發失敗要修等待條件，不能靠重跑蓋過。
- E2E 的執行時間長到明顯拖慢合併時，先縮減測試範圍或平行化，不要移出 required checks。
