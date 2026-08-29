# 與 apps/web/.nvmrc 同步（Dockerfile 讀不到那份檔案，這是唯一一處要手動跟上的）。
# 跟 .nvmrc 一樣只寫 major，才會持續吃到 24.x 的修補版；下限與理由見 package.json 的 `//engines`。
ARG NODE_VERSION=24

# ---- deps stage ----
FROM node:${NODE_VERSION}-slim AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

# ---- dev stage ----
FROM node:${NODE_VERSION}-slim AS dev
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
CMD ["npm", "run", "dev"]

# ---- builder stage ----
FROM node:${NODE_VERSION}-slim AS builder
# 這裡只剩 UPLOAD_SIZE_LIMIT 一個 build 期設定。
# SYSTEM_NAME／EXPIRE_HOURS／VAPID_PUBLIC_KEY 都已經改成執行期注入
# （見 apps/web/shared/runtime/config.ts）—— 烤進 image 的話同一份 image 就只能
# 服務一個環境，而主機 .env 與 image 的不一致完全沒有症狀。
#
# `bodySizeLimit` 是 Next 序列化進 .next/required-server-files.json 的設定，
# standalone 執行期不會重新求值 next.config.ts，所以它結構上移不掉。
# 對應的執行期比對在 apps/web/instrumentation.ts。
ARG UPLOAD_SIZE_LIMIT
ENV UPLOAD_SIZE_LIMIT=$UPLOAD_SIZE_LIMIT
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_SERVER_ACTIONS_ENCRYPTION_KEY 是 Server Action id 的 hash salt，**只有這一步需要**：
# `next build` 會把它寫進 .next/server/server-reference-manifest.json，執行期
# （encryption-utils.js 的 getActionEncryptionKey）直接讀那份 manifest，所以 prod stage
# 不必也不該再設一次 —— 多一個來源只會多一種「.env 改了但沒重建」的不一致。
#
# 不設的話 Next 每次 build 都會亂數產生一把（build/index.js 的
# "Generate a random encryption key for this build"；在容器內 is-docker() 會讓它找不到
# 可持久化的位置），所有 action id 隨之改變，使用者開著沒重載的分頁就會拿到
# 「Server Action ... was not found on the server」。
#
# 用 BuildKit secret 而不是 ARG/ENV：後者會把金鑰留在 image 的 layer metadata 裡
# （`docker history` 直接看得到），BuildKit 也會為此固定噴 SecretsUsedInArgOrEnv 警告。
# secret 只在這一行的執行期間掛載成檔案，不進任何 layer。
#
# required=true 讓「忘了給 secret」直接 build 失敗，而不是靜靜地退回隨機金鑰；
# 額外的空值檢查則擋掉「有給但給了空字串」—— 兩者都會讓 id 變回不可重現，
# 而那種壞法要等到使用者踩到 404 才會被發現。
RUN --mount=type=secret,id=next_actions_key,required=true \
    key="$(cat /run/secrets/next_actions_key)"; \
    if [ -z "$key" ]; then \
        echo "NEXT_SERVER_ACTIONS_ENCRYPTION_KEY 不可為空，請執行 make init 產生 .env" >&2; \
        exit 1; \
    fi; \
    NEXT_SERVER_ACTIONS_ENCRYPTION_KEY="$key" npm run build

# ---- prod stage (standalone) ----
FROM node:${NODE_VERSION}-slim AS prod
ENV NODE_ENV=production
# Next.js standalone 的 server.js 是 `const hostname = process.env.HOSTNAME || '0.0.0.0'`，
# 而 Docker 一定會把 HOSTNAME 設成容器 ID，所以那個 '0.0.0.0' 的預設值在容器裡永遠用不到 ——
# 服務只會綁在容器 ID 解析出的 eth0 位址上，127.0.0.1 沒有任何東西在聽。
# 結果是 compose 的 healthcheck（打 127.0.0.1:3000/healthz）永遠不會通過，frontend 一直是
# unhealthy，依賴它的 nginx 因此永遠起不來。明確覆寫成 0.0.0.0 才是真正的「監聽全部介面」。
ENV HOSTNAME=0.0.0.0
WORKDIR /app
# node 映像檔內建的非 root 使用者。以 root 跑服務等於在容器被打穿時直接送出最高權限，
# 而這個程序只需要讀自己的檔案 + 監聽 3000，完全不需要 root。
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public
USER node
CMD ["node", "server.js"]
