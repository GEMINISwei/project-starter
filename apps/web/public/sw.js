// Service Worker：負責 Web Push，以及靜態資源的快取。
//
// **刻意不做完整離線**。這是一個登入後才有內容的應用，把 HTML 或 /api 回應快取起來，
// 等於把某個使用者的資料留在裝置上 —— 換人登入或登出後仍可能被讀到。這裡只快取
// 「不隨使用者變動」的靜態資源（Next.js 的 hashed bundle 與 app icon），
// 好處是重複載入變快，且沒有任何外洩風險。
//
// 若專案真的需要離線瀏覽，請在登出時明確清掉相關 cache，並只快取公開頁面。

// 改過快取策略就要一起 +1：activate 只會刪掉「名字不等於現行 STATIC_CACHE」的 cache，
// 版本號不動的話，用舊策略存進去的過期項目會原封不動地活下來。
const CACHE_VERSION = 'v1';
const STATIC_CACHE = `static-${CACHE_VERSION}`;

// public/ 底下的檔案：URL 固定、內容會隨改版變動，所以用 stale-while-revalidate ——
// 先給快取（快），同時在背景更新（下次就是新的）。不可以 cache-first，那會讓換過的
// icon 永遠換不掉。
const PUBLIC_ASSETS = ['/app-icon.png', '/app-icon-192.png', '/app-icon-512.png', '/favicon.ico'];

function isSameOrigin(url) {
  return url.origin === self.location.origin;
}

function isNextStatic(url) {
  return isSameOrigin(url) && url.pathname.startsWith('/_next/static/');
}

function isPublicAsset(url) {
  return isSameOrigin(url) && PUBLIC_ASSETS.includes(url.pathname);
}

// /_next/static 只有在 **production build** 才是內容雜湊命名。`next dev` 供應的是
// `chunks/app/(protected)/layout.js` 這種固定名字，內容每次重新編譯都會變 —— 對它
// cache-first 等於把某一代的 JS 永久凍結在瀏覽器裡。實際炸開的樣子是：Server Action
// 的 id 由 encryption key 加鹽而成，而 Next 在容器內跑時每次啟動都會重新亂數產生那把
// key（is-docker() → 沒有持久化儲存），所以 dev server 一重啟，全部 id 就換一輪。
// 這時舊 chunk 送出的是上一代的 id，伺服器查不到，就是
// 「Server Action "…" was not found on the server」。
//
// Next 自己已經把答案寫在回應標頭裡了（router-server.js）：
//   dev  → Cache-Control: no-cache, must-revalidate
//   prod → Cache-Control: public, max-age=31536000, immutable
// 所以判斷依據直接取 immutable，不要自己猜環境 —— dev 不會進快取，prod 照樣全速。
function isImmutable(response) {
  return (response.headers.get('Cache-Control') ?? '').includes('immutable');
}

async function cachePut(request, response) {
  const cache = await caches.open(STATIC_CACHE);
  await cache.put(request, response);
}

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      // 移除不屬於目前快取名稱的項目，避免供應過期資源。
      const names = await caches.keys();
      await Promise.all(
        names.filter((name) => name !== STATIC_CACHE).map((name) => caches.delete(name))
      );
      await self.clients.claim();
    })()
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;

  // 只處理下面兩類靜態資源；其餘（HTML、/api、跨網域）都不呼叫 respondWith，
  // 等於原封不動交給瀏覽器走網路。
  const url = new URL(request.url);

  if (isNextStatic(url)) {
    event.respondWith(
      (async () => {
        const cache = await caches.open(STATIC_CACHE);
        const cached = await cache.match(request);
        if (cached) return cached;

        const response = await fetch(request);
        // 只存 immutable 的回應。dev 的 chunk 因此永遠不進快取，重新編譯後拿到的一定是新的。
        if (response.ok && isImmutable(response)) {
          await cachePut(request, response.clone());
        }
        return response;
      })()
    );
    return;
  }

  if (isPublicAsset(url)) {
    event.respondWith(
      (async () => {
        const cache = await caches.open(STATIC_CACHE);
        const cached = await cache.match(request);

        const fetching = fetch(request)
          .then(async (response) => {
            if (response.ok) await cachePut(request, response.clone());
            return response;
          })
          // 離線或網路錯誤時，有快取就靠快取撐著；沒有就讓它照常失敗。
          .catch((error) => {
            if (cached) return cached;
            throw error;
          });

        if (!cached) return fetching;

        // 有快取就立刻回，背景更新用 waitUntil 保住，不然 SW 可能在 fetch 完成前就被停掉。
        event.waitUntil(fetching.catch(() => {}));
        return cached;
      })()
    );
  }
});

self.addEventListener('push', (event) => {
  const data = event.data?.json() ?? {};
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      const focused = clients.find((client) => client.focused || client.visibilityState === 'visible');
      if (focused) {
        focused.postMessage({ type: 'PUSH_NOTIFICATION', payload: data });
        return;
      }
      return self.registration.showNotification(data.title ?? '通知', {
        body: data.body ?? '',
        icon: '/app-icon.png',
        badge: '/app-icon.png',
        data: { url: data.url ?? '/' },
        tag: data.tag ?? 'default',
      });
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = event.notification.data?.url ?? '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window' }).then((clients) => {
      const existing = clients.find((client) => new URL(client.url).pathname === url);
      return existing ? existing.focus() : self.clients.openWindow(url);
    })
  );
});
