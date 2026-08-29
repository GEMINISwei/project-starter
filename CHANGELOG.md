# 變更紀錄

**這一份是你的專案的**，模板不會再動它 —— 模板自己的紀錄在
[`CHANGELOG.template.md`](CHANGELOG.template.md)，同步時那一份會被整份覆蓋過來，
這一份不會有衝突。兩份分開的理由寫在那一份的檔頭。

（模板 repo 裡這份是空的，那是刻意的：它是給下游用的種子檔。模板自己的條目
一律寫進 `CHANGELOG.template.md`，CI 的 `pr-checks` 會擋下寫錯地方的 PR。）

格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版號採
[語意化版本](https://semver.org/lang/zh-TW/)。日常條目累積在 `## [Unreleased]`，
發版時把那個標題改名成版號與日期，並在上面補一個新的空 `## [Unreleased]` ——
`make check-version` 會確認它與 `apps/api/app/config.py` 的 `APP_VERSION` 對得上
（還沒發過第一版、底下一個版號標題都沒有時，它會直接略過）。

## [Unreleased]
