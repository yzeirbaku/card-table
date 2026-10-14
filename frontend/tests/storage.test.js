import test from 'node:test';
import assert from 'node:assert/strict';
import { createStore } from '../js/storage.js';

function memoryStorage(initial = {}) {
  const map = new Map(Object.entries(initial));
  return { getItem: (k) => (map.has(k) ? map.get(k) : null), setItem: (k, v) => map.set(k, String(v)) };
}

test('defaults when nothing is saved', () => {
  const store = createStore(memoryStorage());
  assert.equal(store.getName(), '');
  assert.deepEqual(store.getSettings(), { theme: 'classic', cardStyle: 'traditional' });
  assert.equal(store.getToken('ABCD'), null);
  assert.equal(store.getCurrentRoom(), null);
});

test('name and settings round-trip and survive a new store', () => {
  const storage = memoryStorage();
  const store = createStore(storage);
  store.setName('Yzeir');
  store.setSettings({ theme: 'kafeneio' });
  store.setSettings({ cardStyle: 'vintage' });
  const again = createStore(storage);
  assert.equal(again.getName(), 'Yzeir');
  assert.deepEqual(again.getSettings(), { theme: 'kafeneio', cardStyle: 'vintage' });
});

test('unknown theme or card style falls back to the default', () => {
  const store = createStore(memoryStorage({ 'card-table': JSON.stringify({ theme: 'neon', cardStyle: 'x' }) }));
  assert.deepEqual(store.getSettings(), { theme: 'classic', cardStyle: 'traditional' });
});

test('corrupted storage falls back to defaults', () => {
  const store = createStore(memoryStorage({ 'card-table': '{not json' }));
  assert.equal(store.getName(), '');
  store.setName('Ana');
  assert.equal(store.getName(), 'Ana');
});

test('tokens are kept per room and can be cleared', () => {
  const store = createStore(memoryStorage());
  store.setToken('ABCD', 't1');
  store.setToken('WXYZ', 't2');
  store.clearToken('ABCD');
  assert.equal(store.getToken('ABCD'), null);
  assert.equal(store.getToken('WXYZ'), 't2');
});

test('current room can be set and cleared', () => {
  const store = createStore(memoryStorage());
  store.setCurrentRoom('ABCD');
  assert.equal(store.getCurrentRoom(), 'ABCD');
  store.setCurrentRoom(null);
  assert.equal(store.getCurrentRoom(), null);
});
