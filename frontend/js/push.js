import { fetchPushKey, pushStatus, pushSubscribe, pushUnsubscribe } from './api.js';

/**
 * 'ok', 'ios-browser' (an iPhone or iPad tab: it has to be added to the home screen first),
 * 'unsupported', or 'blocked' (notifications denied in the browser's settings).
 */
export function pushSupport(env = globalThis) {
  const nav = env.navigator ?? {};
  const hasPush = Boolean(env.PushManager);
  if (/iPhone|iPad/.test(nav.userAgent ?? '') && !hasPush) {
    const standalone = nav.standalone === true || Boolean(env.matchMedia?.('(display-mode: standalone)').matches);
    if (!standalone) return 'ios-browser';
  }
  if (!nav.serviceWorker || !hasPush || !env.Notification) return 'unsupported';
  if (env.Notification.permission === 'denied') return 'blocked';
  return 'ok';
}

/** The server's VAPID key (base64url) as the bytes subscribe() wants. */
export function keyBytes(base64url) {
  const padded = base64url.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(base64url.length / 4) * 4, '=');
  const raw = atob(padded);
  return Uint8Array.from(raw, (ch) => ch.charCodeAt(0));
}

async function currentSubscription() {
  const registration = await navigator.serviceWorker.ready;
  return registration.pushManager.getSubscription();
}

/** True when this browser has a subscription and the server has it filed under this session. */
export async function pushIsOn(token) {
  const subscription = await currentSubscription();
  if (!subscription) return false;
  return (await pushStatus(token, subscription.endpoint)).on;
}

/** Asks permission, subscribes and tells the server. False when permission isn't granted. */
export async function turnPushOn(token) {
  if ((await Notification.requestPermission()) !== 'granted') return false;
  const { key } = await fetchPushKey();
  if (!key) return false;
  const registration = await navigator.serviceWorker.ready;
  const subscription =
    (await registration.pushManager.getSubscription()) ??
    (await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key) }));
  await pushSubscribe(token, subscription.toJSON());
  return true;
}

/** Unsubscribes in the browser, then on the server; best effort on both. */
export async function turnPushOff() {
  let endpoint = null;
  try {
    const subscription = await currentSubscription();
    if (subscription) {
      endpoint = subscription.endpoint;
      await subscription.unsubscribe();
    }
  } catch {
    // nothing more to do in the browser
  }
  if (!endpoint) return;
  try {
    await pushUnsubscribe(endpoint);
  } catch {
    // the server drops a dead endpoint on its own
  }
}
