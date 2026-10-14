import test from 'node:test';
import assert from 'node:assert/strict';
import { seatPositions } from '../js/seats.js';

const players = (...ids) => ids.map((id) => ({ id, name: id }));
const layout = (ps, me) => seatPositions(ps, me).map(({ player, position }) => [player.id, position]);

test('2 players: the other sits across', () => {
  assert.deepEqual(layout(players('a', 'b'), 'b'), [['a', 'top']]);
});

test('3 players: the next player sits on your left', () => {
  assert.deepEqual(layout(players('a', 'b', 'c'), 'a'), [['b', 'left'], ['c', 'right']]);
});

test('4 players, seen from the third seat', () => {
  assert.deepEqual(layout(players('a', 'b', 'c', 'd'), 'c'), [['d', 'left'], ['a', 'top'], ['b', 'right']]);
});

test('not seated: nobody to place', () => {
  assert.deepEqual(layout(players('a', 'b'), 'zz'), []);
});

test('more than 4 players is not supported', () => {
  assert.throws(() => seatPositions(players('a', 'b', 'c', 'd', 'e'), 'a'));
});
