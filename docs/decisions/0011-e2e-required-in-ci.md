# 0011. Playwright E2E 是 CI 與部署的必要檢查

狀態：採用（2026-10-25）

## 背景

E2E 要起一整套正式環境的 image 與 nginx，是 CI 裡最慢的一項。常見的取捨是只在本機或定時排程跑，
不擋 PR 合併與部署。

但 proxy 導向、cookie 屬性、Server Action、權限導向、撤銷 session 這些行為，只有整套跑起來才看得到，
單元測試與 build 都會綠燈（見 [`testing.md`](../testing.md#e2ee2e)）。

## 決定

`e2e` 是 CI 的一個 job，列在 `main` ruleset 的 required checks 裡；部署前重跑的 CI 也包含它，沒過不部署。
只放跨層的 smoke 測試，畫面分支仍然用 vitest 測。

## 後果

- 每個 PR 與每次部署都多等 E2E 的時間，換到的是登入、導向、cookie 這類「壞了也不會報錯」的行為一定被跑過。
- E2E 刻意不開 retries，偶發失敗要修等待條件，不能靠重跑蓋過。
- E2E 的執行時間長到明顯拖慢合併時，先縮減測試範圍或平行化，不要移出 required checks。
