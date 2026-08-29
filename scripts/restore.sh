#!/usr/bin/env bash
#
# 從 ./backups/ 互動式選擇備份並還原。
#
# 在 api 容器內執行，需先 make dev 或 make prod 啟動環境。
# migration 沒有 rollback（見 apps/api/scripts/migrations/_example.py），
# 出事時的退路就是這支配上 backup.sh。
#
# 容器看不到 ./backups/（沒有 bind mount，理由見 backup.sh），所以備份檔走 stdin。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

load_env
require_env COMPOSE_PROJECT_NAME

# 用命令替換而不是 `find … | grep -q`：grep -q 命中後會提早關閉 pipe，find 收到 SIGPIPE
# 就讓整條 pipeline 在 pipefail 下變成非 0 —— 「有備份」會被判成「沒備份」。
if [ -z "$(find backups -maxdepth 1 -type f -name '*.dump' -print -quit 2>/dev/null)" ]; then
    echo "尚無可用備份，請先執行 make backup" >&2
    exit 1
fi

echo "可用備份："
find backups -maxdepth 1 -type f -name '*.dump' -print | sort | sed 's|^backups/|  |'
printf '請輸入要還原的備份檔名：'
read -r backup

# 貼整條路徑進來也接受，一律取檔名 —— 傳進容器的是「檔名」（db.py 用它確認這確實是自己
# 產生的備份），主機的路徑前綴帶進去只會讓那段解析失敗。
backup_name="${backup##*/}"
backup_path="backups/$backup_name"
if [ -z "$backup_name" ] || [ ! -f "$backup_path" ]; then
    echo "找不到備份檔：$backup_name" >&2
    exit 1
fi

# 變數一律用 ${} 包起來：後面緊接全形標點時，bash 會把那幾個 byte 一起吃進變數名，
# 在 `set -u` 下變成 unbound variable。全形字在這個 repo 的訊息裡到處都是，很容易再犯。
confirm "現有資料將被覆蓋，確定要還原資料庫自 ${backup_name}？"

db_cli_stdin restore "$backup_name" < "$backup_path"
