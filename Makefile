# 這裡只做「指令名稱 → 腳本」的對應, 實作在 scripts/<指令>.sh (可以不經 make 直接執行)。
#
# 同性質的操作是同一個指令的子指令: `make db backup`、`make dev logs api`。
# 新增指令 = 加一支 scripts/<name>.sh (記得 chmod +x) 並把 <name> 加進 TARGETS;
# 新增子指令 = 改那支腳本的 case, Makefile 不用動。

TARGETS = init dev prod db check gen-types release version

.DEFAULT_GOAL := help
.PHONY: help $(TARGETS)

# 第一個字是已知指令時, 後面的字全部當成它的參數 (`make db restore backups/x.dump`)。
# make 預設會把它們當成要建置的目標, 所以要接住它們、什麼都不做:
#   - 每個字一條明確的空規則並標成 phony: 參數剛好是存在的檔案時, make 才不會多印一行
#     `is up to date` (phony 目標不走萬用規則, 所以明確規則省不掉)。
#   - 萬用規則 `%:` 接住帶空白的引號參數 (`make db migration "add user phone"`),
#     那在 make 眼裡是一個含空白的目標名, 逐字宣告接不住。
# 只在第一個字是已知指令時才這樣做 —— 打錯字的 `make dve` 仍然要報錯;
# 子指令打錯 (`make db psqll`) 則交給腳本印出用法。
ifneq ($(filter $(firstword $(MAKECMDGOALS)),$(TARGETS)),)
  CMD_ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  ifneq ($(CMD_ARGS),)
    .PHONY: $(CMD_ARGS)
    $(eval $(CMD_ARGS):;@:)
  endif
%:
	@:
endif

help:
	@./scripts/help.sh $(TARGETS)

$(TARGETS):
	@./scripts/$@.sh $(CMD_ARGS)
