#!/usr/bin/env bash
#
# migration 只往前: 回滾只換程式, 資料庫永遠不往回。
#
#   check_released_migrations <versions 目錄>        已發版的 migration 不可修改或刪除 (make check migrate)
#   check_migration_direction <versions 目錄> <rev>  主機資料庫的 revision 要在這一版的 migration 裡 (deploy.yml)
#   list_migration_revisions <versions 目錄>         這一版所有 migration 的 revision, 一行一個
#
# 不讀 .env、不碰容器: make check 與 deploy.yml 的 runner 都直接 source 這一支。
# 要能在 macOS 內建的 bash 3.2 跑, 理由同 .github/scripts/deploy-targets.sh。

# 和目前 commit 往回最近的 `v*` tag 比對 (未 commit 的改動也算)。還沒有任何 tag 時略過:
# 發 0.0.1 前資料庫會 reset, 結構變更可以直接併回初始 migration。
check_released_migrations() {
    local versions="$1" tag changed path
    if ! tag="$(git describe --tags --abbrev=0 --match 'v*' 2> /dev/null)"; then
        echo "還沒有 release tag，略過已發版 migration 的檢查"
        return 0
    fi
    # 只有新增 (A) 是允許的: 修改、刪除、改名都是在改寫已經跑在某台主機上的歷史。
    changed="$(git diff --name-status "${tag}" -- "${versions}" | awk '$1 != "A" { print $NF }')"
    if [ -n "${changed}" ]; then
        echo "已隨 ${tag} 發出去的 migration 不能修改或刪除：" >&2
        while IFS= read -r path; do echo "  ${path}"; done <<< "${changed}" >&2
        echo "要改結構請新增一支 migration：make db migration \"說明\"" >&2
        return 1
    fi
    echo "已發版的 migration 沒有被改寫（比對 ${tag}）"
}

# 每支 migration 都有一行 `revision: str = '<id>'` (alembic 的 script.py.mako 產生)。
list_migration_revisions() {
    local versions="$1"
    sed -n "s/^revision[^=]*= *['\"]\([^'\"]*\)['\"].*/\1/p" "${versions}"/*.py
}

# 資料庫的 revision 不在這一版的 migration 裡, 就是資料庫比較新 (回滾) 或兩邊分岔: 舊版的
# `alembic upgrade head` 會找不到它而失敗。migration 只有一條線 (tests/test_migrations.py 守),
# 所以在裡面就代表一樣或較舊, 部署時往前跑即可。空字串是全新主機。
check_migration_direction() {
    local versions="$1" db_revision="$2"
    if [ -z "${db_revision}" ]; then
        echo "資料庫還沒有跑過 migration，放行"
        return 0
    fi
    if list_migration_revisions "${versions}" | grep -qx "${db_revision}"; then
        echo "資料庫的 revision ${db_revision} 在這一版的 migration 裡，放行"
        return 0
    fi
    {
        echo "資料庫的 revision ${db_revision} 比要部署的這一版新（或兩邊分岔），不能部署："
        echo "migration 只往前，兩版之間多了 migration 就不能回滾。可以："
        echo "  - 往前修：修好之後發一個新版本"
        echo "  - 還原部署前的備份：在主機上 make db restore（會失去備份之後的資料）"
    } >&2
    return 1
}
