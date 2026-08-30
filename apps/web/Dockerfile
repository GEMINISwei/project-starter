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

# NEXT_SERVER_ACTIONS_ENCRYPTION_KEY 在 Next 裡同時扛兩個角色，而**兩個角色的需求相反**：
#
#   1. build 期：它是 Server Action id 的 hash salt。`next build` 會把它寫進
#      .next/server/server-reference-manifest.json，而 id 是由它 salt 出來的 ——
#      換一把就換一整組 id，使用者開著沒重載的分頁會拿到
#      「Server Action ... was not found on the server」。**所以它要穩定。**
#      而它**不需要保密**：那些 id 本來就在 client bundle 裡，任何使用者都讀得到。
#
#   2. 執行期：它是閉包參數的 AES-GCM 加解密金鑰
#      （next/dist/server/app-render/encryption-utils.js 的 getActionEncryptionKey）。
#      **所以它要保密，而且要能輪替。**
#
# 兩個角色綁在同一個值上，結果是**秘密被烤進 image**：manifest 跟著 .next 進 prod stage，
# 任何拿得到這個 image 的人都讀得出正式環境的金鑰。BuildKit 的 `--mount=type=secret`
# 擋得住 layer metadata（docker history），但擋不住「建置程式自己把值寫進產物」。
#
# 所以這裡只給角色 1 用的**公開常數**（解開來就是 public-action-id-salt-not-secret），
# 角色 2 由執行期的環境變數提供 —— getActionEncryptionKey 的實作是
# `process.env.NEXT_SERVER_ACTIONS_ENCRYPTION_KEY || manifest.encryptionKey`，
# 環境變數優先，所以 manifest 裡這一把永遠不會被拿來加密任何東西。
# 注入點在 infra/docker/docker-compose.yml 的 web `environment:`，
# 「忘了注入」由 apps/web/instrumentation.ts 在開機時擋下來。
#
# 實測過的四件事（不要憑讀碼推翻，那已經錯過一次）：
#   - 金鑰確實在 manifest 的 encryptionKey 欄位裡，跟著 image 走。
#   - 執行期環境變數優先於 manifest。
#   - **同一份原始碼、兩把不同的 build 金鑰 → action id 清單不同**，所以它真的是 salt。
#   - build 期用 X、執行期用 Y 跑一整套 prod stack，Server Action 正常運作。
#
# 不再需要 BuildKit secret：這個值是公開的，沒有東西要藏。
ARG NEXT_ACTIONS_ID_SALT="cHVibGljLWFjdGlvbi1pZC1zYWx0LW5vdC1zZWNyZXQ="
RUN NEXT_SERVER_ACTIONS_ENCRYPTION_KEY="$NEXT_ACTIONS_ID_SALT" npm run build

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
