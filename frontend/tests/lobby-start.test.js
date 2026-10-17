import test from 'node:test';
import assert from 'node:assert/strict';
import { startNumber } from '../js/lobby-view.js';

test('the start countdown shows 3, 2, 1 and holds 1 until the game starts', () => {
  assert.equal(startNumber(3000), 3);
  assert.equal(startNumber(2001), 3);
  assert.equal(startNumber(2000), 2);
  assert.equal(startNumber(999), 1);
  assert.equal(startNumber(0), 1);
  assert.equal(startNumber(-250), 1);
});
