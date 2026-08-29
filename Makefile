# 這裡只做「指令名稱 → 腳本」的對應，沒有任何實作。
#
# 為什麼：Makefile 的 recipe 是每行獨立的 shell，多行邏輯要靠 `\` 續行、shell 變數要寫成
# `$$`，漏一個跳脫產生的錯往往只在特定輸入下才出現。把實作放在一般 shell 腳本裡，
# 除了好寫好讀，也讓每個指令都能不經 make 直接執行（CI、編輯器 task、容器內都用得上）。
#
# 新增指令 = 加一支 scripts/<name>.sh（記得 chmod +x）並把 <name> 加進 TARGETS。
# 共用的 compose 旗標、.env 載入、確認提示在 scripts/lib/。

TARGETS = init remote sync setup dev prod deploy down logs psql \
          reset backup restore migrate create-superuser \
          gen-types lint typecheck test build check e2e \
          check-acceptance check-ci check-compose check-contracts check-docs \
          check-env check-nginx check-shell check-test-edits check-version audit

.DEFAULT_GOAL := help

.PHONY: help $(TARGETS)

help:
	@./scripts/help.sh $(TARGETS)

$(TARGETS):
	@./scripts/$@.sh
