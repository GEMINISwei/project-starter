FROM python:3.14-slim AS base

# 刻意不設 TZ, 容器維持 UTC (程式只認 UTC, 見 shared/time)。當地時間由瀏覽器轉換。

COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --frozen --no-cache

# 逐一列出而不是 `COPY . .`: tests/ 與未來的雜物不該進正式 image。
COPY main.py ./
COPY app/ ./app/
COPY modules/ ./modules/
COPY shared/ ./shared/
COPY scripts/ ./scripts/
# migrate service 用的就是這個 image, 漏掉的話 api 會永遠等不到 migration 成功。
COPY alembic.ini ./
COPY migrations/ ./migrations/

# 以非 root 執行。沒有掛主機目錄, uid 不必跟主機對齊。
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --no-create-home app \
    && chown -R app:app /app

USER app

ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "main.py"]
