// Minimal service worker so the app can be installed (no caching), plus push notifications.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});

function describe(payload) {
  if (payload.type === 'invite') {
    return {
      title: `${payload.from} invited you`,
      body: `${payload.game}, ${payload.players} players`,
      tag: `invite-${payload.code}`,
      url: `/?join=${encodeURIComponent(payload.code)}&from=${encodeURIComponent(payload.from)}`,
    };
  }
  return {
    title: `${payload.from} wants to be friends`,
    body: 'Tap to answer',
    tag: `request-${payload.from}`,
    url: '/?friends',
  };
}

async function showPush(payload) {
  const { title, body, tag, url } = describe(payload);
  await self.registration.showNotification(title, { body, tag, icon: '/icons/icon-192.png', data: { url } });
  const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
  for (const client of windows) client.postMessage({ type: 'push', payload, tag });
}

self.addEventListener('push', (event) => {
  let payload;
  try {
    payload = event.data.json();
  } catch {
    return;
  }
  event.waitUntil(showPush(payload));
});

async function openFromNotification(url) {
  const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
  if (windows.length === 0) return self.clients.openWindow(url);
  await windows[0].focus();
  windows[0].postMessage({ type: 'open', url });
}

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(openFromNotification(event.notification.data?.url ?? '/'));
});
