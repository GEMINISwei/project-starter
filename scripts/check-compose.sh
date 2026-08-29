#!/usr/bin/env bash
#
# 確認 compose 沒有安靜地錯：相對路徑、啟動順序、兩種部署模式的 image，以及 postgres 版本。
#
# compose 檔住在 infra/docker/，裡面的相對路徑（`../../apps/api`、`../../apps/web`）
# 靠 --project-directory 才會指對。解錯的時候 docker **不會報錯**：`compose config`
# 照樣通過，build context 與 bind mount 的來源目錄會被默默建立在錯的地方。
# 所以要有這支把「安靜地錯」變成「會紅的錯」。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

load_env
# **這一行不能省。** compose 的插值幾乎全是 `${VAR:?}`，少了 .env 的話 `config` 會整個
# 失敗，而底下的 check_paths 只看得到「路徑沒出現在輸出裡」，於是回報「路徑解析錯誤，
# 請檢查 --project-directory」—— 指向完全錯誤的方向。require_env 的訊息才指得回原因
#（「請確認 .env，或先執行 make init」），這也是其餘每一支碰 compose 的腳本的做法。
require_env COMPOSE_PROJECT_NAME

# 只解析一次再拿變數比對，不要 `config | grep` —— grep -qF 命中後會提早關掉 pipe，
# docker 收到 SIGPIPE 讓整條 pipeline 在 pipefail 下變成非 0，反而把「通過」判成「失敗」。
#
# **兩個 overlay 都要驗。** dev 的相對路徑比 prod 更多也更容易寫錯
# （六條原始碼 bind mount 加上整包掛進去的 `../../apps/web`），而 CI 的
# `dev compose config --quiet` 只驗語法，不看來源解析到哪裡 —— 那正是這支存在的理由。
check_paths() {
    local mode="$1" config="$2" path
    for path in apps/api apps/web infra/nginx; do
        grep -qF "$REPO_ROOT/$path" <<<"$config" && continue
        echo "${mode}：$path 的路徑解析錯誤，請檢查 --project-directory" >&2
        exit 1
    done
}

check_paths production "$(prod_compose config)"
check_paths development "$(dev_compose config)"

test ! -d "$COMPOSE_DIR/apps" \
    || { echo "infra/docker/apps 不該存在 —— 相對路徑解錯時 docker 會默默建立它" >&2; exit 1; }

# ── migrate 必須擋在 api 前面 ───────────────────────────────────────────────
#
# 這是整個部署鏈的核心保證：「新版程式碼配上舊資料結構」不可能出現。
# 有人把 depends_on 改掉、或給 migrate 一個會自動重啟的策略（那會讓失敗的 migration
# 無限重試而不是讓部署停住），這裡要紅。
#
# 用 `--format json` 而不是 yaml：python3 的 json 是內建的，yaml 不是 ——
# 本機沒裝 PyYAML 時 yaml 版本會在「檢查器自己壞了」與「設定壞了」之間分不出來。
assert_services() {
    python3 -c "
import sys, json
label = sys.argv[1]
cfg = json.load(sys.stdin)
api, migrate, web = (cfg['services'][name] for name in ('api', 'migrate', 'web'))

condition = api.get('depends_on', {}).get('migrate', {}).get('condition')
assert condition == 'service_completed_successfully', \
    f'{label}：api 必須等 migrate 成功結束，實際為 {condition!r}'
restart = migrate.get('restart')
assert restart in (None, 'no'), f'{label}：migrate 是一次性工作，不能自動重啟，實際為 {restart!r}'

# migrate 必須與 api 是**同一個 image 字串**，不是「內容一樣」。
# 兩者都走 \${API_IMAGE:-…} 之後，改了一邊忘了另一邊會讓 migration 跑在舊程式上 ——
# 而那正是整條依賴鏈想要排除的狀態，且完全沒有症狀。
assert api['image'] == migrate['image'], \
    f'{label}：migrate 的 image 必須與 api 相同，實際為 {api[\"image\"]!r} 與 {migrate[\"image\"]!r}'
assert api['image'] != web['image'], f'{label}：api 與 web 不該共用同一個 image'
print(f'{label}：api={api[\"image\"]} web={web[\"image\"]} pull_policy={api.get(\"pull_policy\")!r}')
" "$1"
}

# ── 兩種部署模式都要驗 ──────────────────────────────────────────────────────
#
# image 名稱走 `\${API_IMAGE:-<本機名稱>}` 一層變數，同時支援本機建置（make prod）
# 與 registry（make deploy）。只驗其中一種的話，另一種可以壞很久都沒人發現 ——
# 而發現的時機一定是有人正在部署。

# 預設（本機建置）：pull_policy 必須是 build，image 必須是本機名稱。
prod_compose config --format json | assert_services "prod／本機建置"
prod_compose config --format json | python3 -c "
import sys, json
api = json.load(sys.stdin)['services']['api']
assert api.get('pull_policy') == 'build', \
    f'沒有設 IMAGE_* 時應該就地建置，實際 pull_policy={api.get(\"pull_policy\")!r}'
assert '/' not in api['image'], f'預設不該指向 registry，實際 image={api[\"image\"]!r}'
"

# registry 模式：模擬 deploy.sh 匯出的三個變數，確認它們真的接得上。
# 這一步擋的是「deploy.sh 組出來的變數名稱與 compose 對不起來」——
# 那種錯不會讓 compose 報錯，只會讓它靜靜地退回本機建置的預設值。
API_IMAGE="example.registry/demo/api:checked" \
WEB_IMAGE="example.registry/demo/web:checked" \
IMAGE_PULL_POLICY=always \
    prod_compose config --format json | assert_services "prod／registry"

dev_compose config --format json | assert_services "dev"

# postgres 的版本**只有一份**：infra/docker/docker-compose.yml 的 image。
# 另外兩處都是從它衍生出來的：
#   .github/workflows/ci.yml   integration 測試用的那一份，job 裡 grep compose 取得
#   apps/api/Dockerfile        pg_dump／pg_restore（`postgresql-client-<major>`）
#
# 這裡守兩件事。
#
# 第一，ci.yml **不可以寫死一份 image**，要從 compose 讀。寫死的後果不是「跑錯版本」，
# 而是 dependabot 的升版 PR 永遠紅燈：它的 docker_compose 生態系只更新 compose，
# 看不到 `run:` 裡的字串，於是每次升 postgres 都要有人手動往它的分支補 commit。
#
# 第二，Dockerfile 的用戶端工具要與 server 的 **major** 相符 —— PostgreSQL 只要求這個
#（pg_dump 比 server 舊會直接拒絕連線：server version mismatch），而套件名本來就只帶
# major。這一處 dependabot 完全掃不到（它不是 image 也不是套件版本），所以要靠檢查器。
#
# 樣式一定要收到 `-alpine` 結尾：`postgres:5432` 這種連線埠也長得像 `postgres:<數字>`，
# 少了它，連線字串裡的埠號會被當成版本號。
readonly SERVER_IMAGE_PATTERN='postgres:[0-9]+\.[0-9]+-alpine'

if grep -qE "$SERVER_IMAGE_PATTERN" .github/workflows/ci.yml; then
    echo "ci.yml 不該寫死 postgres image —— 它要從 compose 讀（見該 step 的註解）：" >&2
    grep -nE "$SERVER_IMAGE_PATTERN" .github/workflows/ci.yml >&2
    exit 1
fi

server_image="$(grep -hoE "$SERVER_IMAGE_PATTERN" infra/docker/docker-compose.yml | sort -u)"
# 一個都沒抓到（或抓到兩個不同的）代表 compose 被改成別的寫法，而 ci.yml 的 grep 是
# 照同一個樣式取的 —— 那邊會拿到空字串然後當場失敗。這裡先擋，訊息比較看得懂。
if [ "$(echo "$server_image" | wc -l)" -ne 1 ] || [ -z "$server_image" ]; then
    echo "compose 裡的 postgres image 不是剛好一個：" >&2
    grep -nE 'image:.*postgres' infra/docker/docker-compose.yml >&2
    exit 1
fi

server_major="$(echo "${server_image#postgres:}" | cut -d. -f1)"
client_major="$(grep -hoE 'postgresql-client-[0-9]+' apps/api/Dockerfile \
    | sed 's/postgresql-client-//' | sort -u)"
if [ "$server_major" != "$client_major" ]; then
    echo "postgres major 不一致：server=${server_major}，用戶端工具=${client_major}" >&2
    grep -nE "$SERVER_IMAGE_PATTERN" infra/docker/docker-compose.yml >&2
    grep -nE 'postgresql-client-[0-9]+' apps/api/Dockerfile >&2
    exit 1
fi

echo "compose 路徑解析正確、migrate 擋在 api 前面、兩種部署模式的 image 都接得上"
echo "postgres 單一來源（${server_image}），ci.yml 從 compose 讀，用戶端工具 major ${client_major}"
