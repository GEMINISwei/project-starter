# 安全性政策

## 回報漏洞

**請不要開公開的 issue 或 PR 來回報安全問題** —— 那等於在修好之前先把細節公開。

請走 GitHub 的私下回報：這個 repo 的 **Security** 分頁 → **Report a vulnerability**。
那個表單只有 repo 的維護者看得到，討論與修補都在私有的 advisory 裡進行，
修好之後才決定要不要公開。

回報時請盡量附上：受影響的版本或 commit、重現步驟、以及你認為的影響範圍。

## 支援範圍

只有 `main` 的最新狀態。這個專案沒有維護多條版本線，
修補一律往前推進，不回補舊版號。

## 這個 repo 附帶的安全機制

以下都已經接上，回報前可以先確認你發現的東西是不是已經被涵蓋：

- **相依套件的已知漏洞** —— `make audit`（npm + uv），CI 每週跑一次
- **相依更新** —— Dependabot，涵蓋 uv／npm／Dockerfile 基底映像／compose／GitHub Actions
- **原始碼掃描** —— CodeQL（default setup）
- **祕密外洩** —— secret scanning + push protection
- **建置來源** —— 發布的 image 附有 build provenance attestation，
  驗證方式見 [`docs/operations.md`](../docs/operations.md)

## 已知的邊界

這些是**刻意**沒有做的，不必回報（要討論的話開一般 issue）：

- image 層沒有 OS 套件的漏洞掃描
- 沒有 SBOM
- 發布的 image 沒有 inline provenance（證明存在 image 外面，見上一節）
