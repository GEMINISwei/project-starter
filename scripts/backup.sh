#!/usr/bin/env bash
#
# 備份目前資料庫到 ./backups/。
#
# 在 api 容器內執行，需先 make dev 或 make prod 啟動環境。
#
# 容器裡**沒有掛任何主機目錄**：db.py 把備份寫到容器內的暫存目錄，這支腳本再串流出來。
# 用 bind mount 的話 docker 會在容器啟動時就默默建立主機的 backups/，
# 於是每個新專案一開始就多一個從沒備份過的空目錄。所以 ./backups/ 的建立時機
# 刻意放在這裡 —— pg_dump 成功之後才建。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

load_env
require_env COMPOSE_PROJECT_NAME

# db.py 的 backup 把備份檔在容器裡的完整路徑印在 stdout，訊息走 stderr
# （見 apps/api/scripts/db.py 的模組 docstring）。失敗時 set -e 直接中止，
# 不會走到下面的 mkdir —— 這就是「有備份才有目錄」的實作。
remote_path="$(db_cli backup)"
name="${remote_path##*/}"

mkdir -p backups

# 先寫 .part 再 rename：串流中斷時，backups/ 裡不該留下一個看起來像備份、
# 實際上被截斷的 .dump —— 那比沒有備份更危險，因為它會在還原演練時才爆。
# 取出後把整個暫存目錄刪掉（db.py 用 mkdtemp 建的，一次備份一個目錄）。
if docker exec "${COMPOSE_PROJECT_NAME}-api" \
        sh -c "cat '$remote_path' && rm -rf \"\$(dirname '$remote_path')\"" > "backups/$name.part"; then
    mv "backups/$name.part" "backups/$name"
    echo "備份完成：backups/$name"
else
    rm -f "backups/$name.part"
    # 這次備份是這個目錄唯一的存在理由，失敗就不要留下它。非空時 rmdir 會失敗，正好。
    rmdir backups 2>/dev/null || true
    echo "備份檔取出失敗" >&2
    exit 1
fi
