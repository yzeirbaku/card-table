import test from 'node:test';
import assert from 'node:assert/strict';
import { RoomConnection } from '../js/connection.js';
import { createStore } from '../js/storage.js';

class FakeSocket {
  static OPEN = 1;
  static all = [];
  constructor(url) {
    this.url = url;
    this.sent = [];
    this.readyState = 0;
    FakeSocket.all.push(this);
  }
  send(data) { this.sent.push(JSON.parse(data)); }
  close() { this.readyState = 3; }
  // test helpers
  open() { this.readyState = 1; this.onopen?.(); }
  message(msg) { this.onmessage?.({ data: JSON.stringify(msg) }); }
  drop(code, reason = '') { this.readyState = 3; this.onclose?.({ code, reason }); }
}

function memoryStorage() {
  const map = new Map();
  return { getItem: (k) => (map.has(k) ? map.get(k) : null), setItem: (k, v) => map.set(k, String(v)) };
}

function setup({ deferWait = false } = {}) {
  FakeSocket.all = [];
  const store = createStore(memoryStorage());
  store.setName('Ana');
  const events = [];
  const delays = [];
  const pending = [];
  const conn = new RoomConnection({
    code: 'ABCD',
    store,
    urlFor: (code, name, token) => `ws://test/${code}?name=${name}&token=${token ?? ''}`,
    onWelcome: (id) => events.push(['welcome', id]),
    onState: (msg) => events.push(['state', msg.code]),
    onError: (m) => events.push(['error', m]),
    onReaction: (id, kind) => events.push(['reaction', id, kind]),
    onReconnecting: (on) => events.push(['reconnecting', on]),
    onClosed: (m) => events.push(['closed', m]),
    WebSocketImpl: FakeSocket,
    wait: (fn, ms) => { delays.push(ms); if (deferWait) pending.push(fn); else fn(); },
  });
  conn.connect();
  return { conn, store, events, delays, pending, socket: () => FakeSocket.all.at(-1) };
}

test('welcome saves the seat token and current room', () => {
  const { store, events, socket } = setup();
  socket().open();
  socket().message({ type: 'welcome', player_id: 'p1', token: 'tok', code: 'ABCD' });
  assert.equal(store.getToken('ABCD'), 'tok');
  assert.equal(store.getCurrentRoom(), 'ABCD');
  assert.deepEqual(events.at(-1), ['welcome', 'p1']);
});

test('state and error messages are passed on; garbage is ignored', () => {
  const { events, socket } = setup();
  socket().open();
  socket().onmessage({ data: '{not json' });
  socket().message({ type: 'state', code: 'ABCD' });
  socket().message({ type: 'error', message: 'Nope' });
  assert.deepEqual(events.slice(-2), [['state', 'ABCD'], ['error', 'Nope']]);
});

test('reactions are passed on with who sent them', () => {
  const { events, socket } = setup();
  socket().open();
  socket().message({ type: 'reaction', player_id: 'p2', reaction: 'asleep' });
  assert.deepEqual(events.at(-1), ['reaction', 'p2', 'asleep']);
});

test('network drop reconnects with the saved token', () => {
  const { events, delays, socket } = setup();
  socket().open();
  socket().message({ type: 'welcome', player_id: 'p1', token: 'tok', code: 'ABCD' });
  socket().drop(1006);
  assert.equal(FakeSocket.all.length, 2);
  assert.match(socket().url, /token=tok/);
  assert.deepEqual(delays, [500]);
  assert.deepEqual(events.at(-1), ['reconnecting', true]);
  socket().open();
  assert.deepEqual(events.at(-1), ['reconnecting', false]);
});

test('reconnect backs off and resets after a successful open', () => {
  const { delays, socket } = setup();
  socket().open();
  socket().drop(1006); // retry 1 (never opens)
  socket().drop(1006); // retry 2
  socket().drop(1006); // retry 3
  socket().open();
  socket().drop(1006);
  assert.deepEqual(delays, [500, 1000, 2000, 500]);
});

test('room not found is final and forgets the seat', () => {
  const { store, events, socket } = setup();
  store.setToken('ABCD', 'old');
  store.setCurrentRoom('ABCD');
  socket().drop(4404, 'Room not found');
  assert.equal(FakeSocket.all.length, 1);
  assert.equal(store.getToken('ABCD'), null);
  assert.equal(store.getCurrentRoom(), null);
  assert.deepEqual(events.at(-1), ['closed', 'No table with that code']);
});

test("full room shows the server's reason", () => {
  const { events, socket } = setup();
  socket().drop(4409, 'This table is full');
  assert.deepEqual(events.at(-1), ['closed', 'This table is full']);
});

test('seat opened elsewhere stops without forgetting the seat', () => {
  const { store, events, socket } = setup();
  socket().open();
  socket().message({ type: 'welcome', player_id: 'p1', token: 'tok', code: 'ABCD' });
  socket().drop(4000, 'Opened on another connection');
  assert.equal(FakeSocket.all.length, 1);
  assert.equal(store.getToken('ABCD'), 'tok');
  assert.deepEqual(events.at(-1), ['closed', 'This seat was opened somewhere else']);
});

test('never connecting gives up with a message and keeps the token', () => {
  const { store, events, socket } = setup();
  store.setToken('ABCD', 'tok');
  socket().drop(1006);
  assert.equal(FakeSocket.all.length, 1);
  assert.equal(store.getToken('ABCD'), 'tok');
  assert.deepEqual(events.at(-1), ['closed', "Can't reach the server"]);
});

test('leave sends leave, forgets the seat and does not reconnect', () => {
  const { conn, store, socket } = setup();
  socket().open();
  socket().message({ type: 'welcome', player_id: 'p1', token: 'tok', code: 'ABCD' });
  const ws = socket();
  conn.leave();
  ws.drop(1000);
  assert.deepEqual(ws.sent, [{ type: 'leave' }]);
  assert.equal(FakeSocket.all.length, 1);
  assert.equal(store.getToken('ABCD'), null);
  assert.equal(store.getCurrentRoom(), null);
});

test('leave while connecting sends leave once the socket opens', () => {
  const { conn, store, events, socket } = setup();
  store.setToken('ABCD', 'tok');
  const ws = socket();
  conn.leave();
  assert.deepEqual(ws.sent, []);
  ws.open();
  assert.deepEqual(ws.sent, [{ type: 'leave' }]);
  assert.equal(FakeSocket.all.length, 1);
  assert.equal(store.getToken('ABCD'), null);
  assert.deepEqual(events, []);
});

test('leave while a retry is pending opens a socket with the old token and leaves', () => {
  const { conn, store, events, pending, socket } = setup({ deferWait: true });
  socket().open();
  socket().message({ type: 'welcome', player_id: 'p1', token: 'tok', code: 'ABCD' });
  socket().drop(1006);
  assert.equal(pending.length, 1);
  const before = events.length;
  conn.leave();
  assert.equal(FakeSocket.all.length, 2);
  const last = socket();
  assert.match(last.url, /token=tok/);
  last.open();
  assert.deepEqual(last.sent, [{ type: 'leave' }]);
  last.message({ type: 'state', code: 'ABCD' });
  last.drop(1000);
  pending[0]();
  assert.equal(FakeSocket.all.length, 2);
  assert.equal(store.getToken('ABCD'), null);
  assert.equal(store.getCurrentRoom(), null);
  assert.equal(events.length, before);
});

test('no callbacks reach the app after leave', () => {
  const { conn, events, socket } = setup();
  socket().open();
  const ws = socket();
  conn.leave();
  const before = events.length;
  ws.message({ type: 'state', code: 'ABCD' });
  ws.message({ type: 'welcome', player_id: 'p1', token: 'x', code: 'ABCD' });
  assert.equal(events.length, before);
});

test('close stops quietly and keeps the seat', () => {
  const { conn, store, events, socket } = setup();
  socket().open();
  socket().message({ type: 'welcome', player_id: 'p1', token: 'tok', code: 'ABCD' });
  const before = events.length;
  const ws = socket();
  conn.close();
  ws.drop(1000);
  assert.equal(FakeSocket.all.length, 1);
  assert.equal(store.getToken('ABCD'), 'tok');
  assert.equal(events.length, before);
});

test('non-object frames are ignored', () => {
  const { events, socket } = setup();
  socket().open();
  socket().onmessage({ data: 'null' });
  socket().onmessage({ data: '42' });
  socket().message({ type: 'state', code: 'ABCD' });
  assert.deepEqual(events.slice(1), [['state', 'ABCD']]);
});

test('send goes out only while the socket is open', () => {
  const { conn, socket } = setup();
  assert.equal(conn.send({ type: 'sit', seat: 1 }), false);
  socket().open();
  assert.equal(conn.send({ type: 'sit', seat: 1 }), true);
  assert.deepEqual(socket().sent.at(-1), { type: 'sit', seat: 1 });
});

test('signed in, the URL only says so and the session goes as the first message', () => {
  FakeSocket.all = [];
  const store = createStore(memoryStorage());
  store.setSession({ token: 'sess', username: 'Ana' });
  const urls = [];
  const conn = new RoomConnection({
    code: 'ABCD', store, WebSocketImpl: FakeSocket,
    urlFor: (...args) => { urls.push(args); return 'ws://test'; },
    onWelcome() {}, onState() {}, onError() {}, onReconnecting() {}, onClosed() {},
  });
  conn.connect();
  assert.deepEqual(urls[0], ['ABCD', '', null, true]);
  assert.ok(!JSON.stringify(urls).includes('sess')); // URLs end up in logs
  FakeSocket.all[0].open();
  assert.deepEqual(FakeSocket.all[0].sent[0], { type: 'session', session: 'sess' });
});

test('the leave-only socket goes without the session', () => {
  FakeSocket.all = [];
  const store = createStore(memoryStorage());
  store.setSession({ token: 'sess', username: 'Ana' });
  store.setToken('ABCD', 'seat');
  const urls = [];
  const conn = new RoomConnection({
    code: 'ABCD', store, WebSocketImpl: FakeSocket, wait: () => {},
    urlFor: (...args) => { urls.push(args); return 'ws://test'; },
    onWelcome() {}, onState() {}, onError() {}, onReconnecting() {}, onClosed() {},
  });
  conn.connect();
  FakeSocket.all[0].open();
  FakeSocket.all[0].drop(1006); // dropped: a retry is pending
  conn.leave();
  const last = FakeSocket.all.at(-1);
  assert.deepEqual(urls.at(-1), ['ABCD', '', 'seat', false]);
  last.open();
  assert.deepEqual(last.sent, [{ type: 'leave' }]);
});

test('4401 signs out and does not retry', () => {
  const { store, events, socket } = setup();
  store.setSession({ token: 'sess', username: 'Ana' });
  socket().open();
  socket().drop(4401, 'Signed out');
  assert.equal(store.getSession(), null);
  assert.deepEqual(events.filter((e) => e[0] === 'closed'), [['closed', 'You were signed out. Sign in again']]);
  assert.equal(FakeSocket.all.length, 1);
});
