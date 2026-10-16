import test from 'node:test';
import assert from 'node:assert/strict';
import { dragGroup, inside, isDrag, tableDelta } from '../js/drag.js';

test('a small wobble is still a tap', () => {
  assert.equal(isDrag(3, 4), false);
  assert.equal(isDrag(10, 0), false);
  assert.equal(isDrag(8, 8), true);
});

test('on a turned table a move down the screen is a move right on the table', () => {
  assert.deepEqual(tableDelta(5, 20, false), { x: 5, y: 20 });
  assert.deepEqual(tableDelta(5, 20, true), { x: 20, y: -5 });
});

test('inside a rect, edges included', () => {
  const rect = { left: 10, right: 50, top: 0, bottom: 30 };
  assert.equal(inside(rect, 10, 30), true);
  assert.equal(inside(rect, 30, 15), true);
  assert.equal(inside(rect, 51, 15), false);
  assert.equal(inside(rect, 30, -1), false);
});

test('dragging a picked card carries all your picks', () => {
  assert.deepEqual(dragGroup(['7H', '7S'], '7S', []), ['7H', '7S']);
});

test('dragging a card you had not picked adds it to your picks', () => {
  assert.deepEqual(dragGroup(['7H', '7S'], '7D', []), ['7H', '7S', '7D']);
  assert.deepEqual(dragGroup([], 'QC', []), ['QC']);
});

test('giving in the swap drags just that card, and only one you may give', () => {
  assert.deepEqual(dragGroup(['AS'], 'AH', ['AS', 'AH']), ['AH']);
  assert.equal(dragGroup([], '3C', ['AS']), null);
});
