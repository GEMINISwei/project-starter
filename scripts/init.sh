#!/usr/bin/env bash
#
# 互動式建立 .env，並做完首次 clone 之後該做的事。
#
# 產生的祕密一律用 openssl，不用 $RANDOM 那類 —— 這些值直接決定 JWT 與 Server Action 的
# 簽章強度。
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .env ]; then
    echo ".env 已存在，跳過"
else
    printf '請輸入初始化資訊\n'

    while :; do
        printf '專案名稱 [my-app]: '
        read -r compose_project_name
        compose_project_name="${compose_project_name:-my-app}"
        case "$compose_project_name" in
            ''|[!a-z0-9]*|*[!a-z0-9_-]*)
                echo "專案名稱須以小寫英文字母或數字開頭，且只能包含小寫英文字母、數字、-、_" ;;
            *) break ;;
        esac
    done

    while :; do
        printf '系統名稱 [My App]: '
        read -r system_name
        system_name="${system_name:-My App}"
        case "$system_name" in
            *\'*) echo "系統名稱不可包含單引號" ;;
            *) break ;;
        esac
    done

    while :; do
        printf '系統 Port [3000]: '
        read -r system_port
        system_port="${system_port:-3000}"
        case "$system_port" in
            *[!0-9]*|'') echo "Port 必須是 1 到 65535 的整數" ;;
            *)
                if [ "$system_port" -ge 1 ] && [ "$system_port" -le 65535 ]; then break; fi
                echo "Port 必須是 1 到 65535 的整數" ;;
        esac
    done

    while :; do
        printf '資料庫帳號 [admin]: '
        read -r postgres_user
        postgres_user="${postgres_user:-admin}"
        case "$postgres_user" in
            *[!A-Za-z0-9._~-]*) echo "資料庫帳號只能包含英文字母、數字、.、_、~、-" ;;
            *) break ;;
        esac
    done

    while :; do
        # 字元集限制不是美觀問題：這個值會被插進 compose 的
        # `postgresql+asyncpg://user:pass@host/db`，而 `@`、`:`、`/` 之類的字元會把
        # 那個 URL 切在錯的地方 —— 症狀是「認證失敗」，看不出跟密碼裡的字元有關。
        printf '資料庫密碼（必填）：'
        read -r postgres_password
        case "$postgres_password" in
            ''|*[!A-Za-z0-9._~-]*)
                echo "資料庫密碼不可為空，且只能包含英文字母、數字、.、_、~、-" ;;
            *) break ;;
        esac
    done

    # 資料庫名稱跟著專案名走，不另外問 —— 一個 compose 專案就是一個資料庫。
    postgres_db="$compose_project_name"

    jwt_secret_key="$(openssl rand -hex 32)"
    register_key="$(openssl rand -hex 32)"
    next_actions_key="$(openssl rand -base64 32)"

    # VAPID 是 P-256 的 EC 金鑰對，且 Web Push 規格要的是 base64url（無 padding）的
    # 原始位元組，不是 PEM：私鑰取 PKCS#8 DER，公鑰取未壓縮點格式的最後 65 bytes。
    vapid_private_pem="$(openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 2>/dev/null)"
    vapid_private_key="$(echo "$vapid_private_pem" | openssl pkcs8 -topk8 -nocrypt -outform DER 2>/dev/null | base64 | tr '+/' '-_' | tr -d '\n=')"
    vapid_public_key="$(echo "$vapid_private_pem" | openssl ec -pubout -outform DER 2>/dev/null | tail -c 65 | base64 | tr '+/' '-_' | tr -d '\n=')"

    cat > .env <<EOF
# ── Project ──────────────────────────────────────────────────────────────────
COMPOSE_PROJECT_NAME=$compose_project_name
SYSTEM_NAME=$system_name
SYSTEM_PORT=$system_port

# ── PostgreSQL ────────────────────────────────────────────────────────────────
POSTGRES_USER=$postgres_user
POSTGRES_PASSWORD=$postgres_password
POSTGRES_DB=$postgres_db

# ── Auth ──────────────────────────────────────────────────────────────────────
JWT_SECRET_KEY=$jwt_secret_key
EXPIRE_HOURS=8
TOKEN_VERSION=1

# ── App ───────────────────────────────────────────────────────────────────────
# 建立第一個超級管理者用，整個部署只能成功一次，之後可留空。
# 要再新增超級管理者請用 \`make create-superuser\`。
REGISTER_KEY=$register_key
UPLOAD_SIZE_LIMIT=1mb

# Server Action id 的 hash salt，留空會讓舊分頁的 Server Action 失效。
# 修改後必須重新 build。
NEXT_SERVER_ACTIONS_ENCRYPTION_KEY=$next_actions_key

# ── Push（VAPID）────────────────────────────────────────────────────────────
VAPID_PRIVATE_KEY=$vapid_private_key
VAPID_PUBLIC_KEY=$vapid_public_key
VAPID_SUBJECT=mailto:admin@example.com

# ── Deploy（選用）─────────────────────────────────────────────────────────────
# 留空 = 不使用 registry，\`make prod\` 在主機上就地建置（模板出廠的行為）。
# 接上 CI/CD 之後填 registry 前綴與要部署的 tag，改用 \`make deploy\`。
IMAGE_REGISTRY=
IMAGE_TAG=
EOF

    echo ".env 已依輸入設定建立"
fi

if [ -e .git ]; then
    echo "Git 已初始化，跳過"
else
    git init -q -b main
    git add .
    git commit -q -m "initial commit"
    # 走到這一支代表不是 clone 來的（clone 會帶著 .git）。這樣開出來的歷史與模板沒有共同
    # 祖先，日後 `git merge template/main` 會直接以 refusing to merge unrelated histories
    # 失敗 —— 而那要到第一次同步才會發現，那時專案已經長出來了。所以在這裡就講。
    echo "已建立全新的 git 歷史（與模板沒有共同祖先）"
    echo "若這是從模板開出來的專案、日後要拉模板更新，請改用 git clone 開案（見 README）"
fi

register_key="$(sed -n 's/^REGISTER_KEY=//p' .env)"
if [ -n "$register_key" ]; then
    echo "註冊代碼（首次於 /signup 建立超級管理者用）：$register_key"
else
    echo "註冊代碼已清空，請用 make create-superuser 建立超級管理者"
fi

# 這裡刻意不問遠端網址：本機開發測試常常不想綁任何儲存庫，而這一步跑完就該能 make dev。
if ! git remote | grep -q .; then
    echo "尚未綁定任何 git remote，需要時執行 make remote"
fi
