import test from 'node:test';
import assert from 'node:assert/strict';
import { keyBytes, pushSupport } from '../js/push.js';

test('keyBytes decodes unpadded base64url', () => {
  const bytes = Uint8Array.from({ length: 65 }, (_, i) => (i * 7 + 250) % 256);
  const b64url = Buffer.from(bytes).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const out = keyBytes(b64url);
  assert.ok(out instanceof Uint8Array);
  assert.deepEqual([...out], [...bytes]);
});

const ANDROID = 'Mozilla/5.0 (Linux; Android 14; Pixel 8) Chrome/126.0 Mobile Safari/537.36';
const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Version/17.5 Mobile/15E148 Safari/604.1';

function env({ ua, push = true, sw = true, standalone, displayStandalone = false, permission = 'default' }) {
  return {
    navigator: { userAgent: ua, ...(sw ? { serviceWorker: {} } : {}), ...(standalone === undefined ? {} : { standalone }) },
    ...(push ? { PushManager: class {} } : {}),
    Notification: { permission },
    matchMedia: () => ({ matches: displayStandalone }),
  };
}

test('pushSupport: Android Chrome is ok', () => {
  assert.equal(pushSupport(env({ ua: ANDROID })), 'ok');
});

test('pushSupport: an iPhone Safari tab must be added to the home screen first', () => {
  assert.equal(pushSupport(env({ ua: IPHONE, push: false, standalone: false })), 'ios-browser');
});

const IPAD = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.5 Safari/605.1.15';

test('pushSupport: iPadOS Safari (a Mac user agent with a touch screen) gets the home screen hint', () => {
  const tab = env({ ua: IPAD, push: false, standalone: false });
  tab.navigator.maxTouchPoints = 5;
  assert.equal(pushSupport(tab), 'ios-browser');
  const mac = env({ ua: IPAD, push: false });
  mac.navigator.maxTouchPoints = 0;
  assert.equal(pushSupport(mac), 'unsupported');
});

test('pushSupport: the iPhone home-screen app is ok', () => {
  assert.equal(pushSupport(env({ ua: IPHONE, standalone: true })), 'ok');
});

test('pushSupport: denied permission is blocked', () => {
  assert.equal(pushSupport(env({ ua: ANDROID, permission: 'denied' })), 'blocked');
});

test('pushSupport: no service worker is unsupported', () => {
  assert.equal(pushSupport(env({ ua: 'Mozilla/5.0 (Windows NT 10.0) Chrome/126', sw: false, push: false })), 'unsupported');
});
