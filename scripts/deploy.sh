#!/usr/bin/env bash
#
# 以 production 模式部署 registry 上已建好的 image（不在主機上建置）。
#
# 用法：make deploy（用 .env 的 IMAGE_TAG）或 bash scripts/deploy.sh <tag>（CD 走這條）。
#
# 與 `make prod` 的分工：
#   make prod    在主機上就地建置。模板出廠的預設路徑，沒接 CI/CD 也能用。
#   make deploy  拉 CI 建好並驗過的 image。上線的東西與 CI 綠燈的是同一份 digest，
#                而且回滾就是換一個 tag 再跑一次，不必重建。
#
# 為什麼不把兩者合成一支：合起來的話「這次到底有沒有重建」取決於環境變數有沒有設，
# 而那正是部署時最不該用猜的一件事。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

load_env
require_env COMPOSE_PROJECT_NAME

# 不用 require_env 帶 IMAGE_REGISTRY：它的通用訊息是「請確認 .env，或先執行 make init」，
# 而這個變數**出廠就是空的**（模板預設走本機建置）。照那句話去跑 make init 只會更困惑。
if [ -z "${IMAGE_REGISTRY:-}" ]; then
    echo "IMAGE_REGISTRY 未設定。要用 registry 部署請在 .env 填入前綴" >&2
    echo "（例如 ghcr.io/<owner>/<repo>，見 docs/operations.md）；" >&2
    echo "只想在這台主機上就地建置的話請改用 make prod。" >&2
    exit 1
fi

# 參數優先於 .env：CD 部署的是某一個特定 tag，不該受主機上那份 .env 的殘值影響。
tag="${1:-${IMAGE_TAG:-}}"
if [ -z "$tag" ]; then
    echo "沒有指定 image tag。請給參數（bash scripts/deploy.sh v1.2.3）或在 .env 設 IMAGE_TAG。" >&2
    exit 1
fi

# 這三個變數只在這支腳本的生命週期裡存在，不寫回 .env ——
# 「這次部署用哪個 tag」是一次性的參數，留在檔案裡只會變成下一個人踩的過期狀態。
API_IMAGE="$IMAGE_REGISTRY/api:$tag"
WEB_IMAGE="$IMAGE_REGISTRY/web:$tag"
export API_IMAGE WEB_IMAGE
export IMAGE_PULL_POLICY=always

echo "部署 $API_IMAGE 與 $WEB_IMAGE"

# 先 pull 再 up：pull 失敗（tag 打錯、沒登入 registry）要在動到正在運行的服務**之前**
# 就停住。合在 `up` 裡的話，compose 會先把舊容器收掉才發現拉不到 image。
prod_compose pull

# `--no-build` 是這支腳本與 prod.sh 的關鍵差異：沒有它，image 拉不到時 compose 會
# 安靜地改用 build context 就地建一份 —— 那就完全繞過了「部署 CI 驗過的那一份」。
prod_compose up -d --no-build --remove-orphans

# `up -d` 在容器建立之後就回來了，**不等 healthcheck 通過**。少了下面這段，一個開機就失敗、
# 不斷重啟的版本會被回報成「部署成功」。
#
# 這段放在腳本裡而不是 CD 的一個步驟：`deploy.yml` 靠這支的結束碼決定要不要回滾，而回滾本身
# 也是再跑一次這支 —— 驗證寫在這裡，兩條路徑（含手動跑的）才會用到同一份判準。
wait_healthy() {
    local container="$1" status
    # 30 × 10 秒 = 5 分鐘。web 的 start_period 是 20 秒（見 docker-compose.yml），
    # 留這麼多是因為 migrate 可能還在跑 —— api 要等它成功結束才起得來。
    for _ in $(seq 1 30); do
        status="$(docker inspect --format '{{.State.Health.Status}}' "$container" 2>/dev/null || echo missing)"
        case "$status" in
            healthy) echo "$container 已 healthy"; return 0 ;;
            # 容器不存在跟「還沒健康」是兩回事：前者再等下去也不會變好。
            missing) echo "$container 不存在，部署沒有成功" >&2; return 1 ;;
        esac
        sleep 10
    done
    echo "$container 未能在 5 分鐘內變成 healthy" >&2
    return 1
}

wait_healthy "$COMPOSE_PROJECT_NAME-web"

# healthcheck 探的是**容器內**的 127.0.0.1:3000（見 docker-compose.yml 的 web），
# 繞過了 nginx 與 port 綁定。而那一段正是每次部署都會跟著換的東西：nginx 模板是從
# 工作樹 bind mount 進去的。所以「容器健康」與「外面真的連得到」要分開驗。
smoke_test() {
    if ! command -v curl >/dev/null 2>&1; then
        # 不是硬性錯誤：這只是多一層驗證，沒有 curl 的主機不該因此不能部署。
        echo "找不到 curl，略過對外連通性檢查" >&2
        return 0
    fi
    if ! curl -fsS -o /dev/null --max-time 10 "http://127.0.0.1:$SYSTEM_PORT/healthz"; then
        echo "nginx 對外沒有回應（http://127.0.0.1:$SYSTEM_PORT/healthz）" >&2
        return 1
    fi
    echo "對外連通性 OK"
}

smoke_test

# **記錄「驗證過的版本」，不是「工作樹 checkout 到哪」。**
#
# CD 回滾需要一個「已知是好的」標的，而 `git rev-parse HEAD` 只說得出上次 checkout 到哪：一次
# 部署失敗、回滾也沒跑成功的話，HEAD 就停在壞掉的那一版，下一次部署會把它當成回滾標的。
#
# 這幾行寫在健康檢查與連通性都通過**之後**，所以檔案裡的必定是真的服務過的版本。用檔案而不是
# 問正在跑的容器：最需要知道「上一個好版本」的時刻，正是現在的容器不對勁的時候。
commit="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
{
    echo "DEPLOYED_COMMIT=$commit"
    echo "DEPLOYED_TAG=$tag"
    echo "DEPLOYED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$REPO_ROOT/.deployed"

echo "已記錄部署版本：${commit}（${tag}）"
