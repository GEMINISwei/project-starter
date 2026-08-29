FROM python:3.14-slim AS base

ENV TZ=Asia/Taipei
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /bin/uv

# pg_dump／pg_restore 給 `make backup` / `make restore` 用。
#
# **major 版本必須與 infra/docker/docker-compose.yml 的 postgres 服務一致**：pg_dump
# 比 server 舊時會直接拒絕連線（"server version mismatch"），而那要等到有人真的跑
# `make backup` 才會出現 —— image 建得起來、服務也跑得好好的。這一條由
# `make check-compose` 擋（它比對三處的 major：這裡、compose、ci.yml）。
#
# 走 Debian 自己的套件庫，**不是**另外掛 PGDG 的來源：`python:3.14-slim` 目前的底層是
# Debian 13 (trixie)，而 trixie 內建的正好就是 postgresql-client-17。掛 PGDG 要多帶
# GPG key 與一份 sources.list，而且來源那行的 codename 必須跟著 base image 走 ——
# 寫死一個（例如 bookworm）在 base image 跳版之後會去裝另一個 Debian 版本的套件，
# 症狀是 libldap 之類的相依「no choices」，訊息完全看不出是 codename 寫錯。
#
# 代價：這等於押在「base image 的 Debian 剛好出我們要的 major」。要升 postgres major 而
# Debian 還沒跟上時，這一行會在 build 當下就失敗（很吵，不會靜靜裝到錯的版本），
# 那時再改掛 PGDG 的 `$VERSION_CODENAME-pgdg` 來源。
#
# 也**不要**從官方 postgres image `COPY` binary 過來：那個 image 是 alpine（musl），
# 抄到 debian-slim 上連 loader 都找不到，症狀是 `no such file or directory`
#（而檔案明明就在）。
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-17 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --frozen --no-cache

# 逐一列出而不是 `COPY . .`：image 裡只該有跑得起服務的東西。`tests/` 沒有被
# .dockerignore 擋掉，一句 `COPY . .` 會把它連同未來新增的任何雜物一起帶進正式 image。
COPY main.py ./
COPY app/ ./app/
COPY modules/ ./modules/
COPY shared/ ./shared/
COPY scripts/ ./scripts/

# 以非 root 執行：這個程序只需要讀自己的檔案、監聽 8000、寫 /tmp（備份的暫存檔）。
# 沒有掛任何主機目錄進來，所以 uid 不需要跟主機使用者對齊，1000 只是個慣例值。
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --no-create-home app \
    && chown -R app:app /app

USER app

ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "main.py"]
