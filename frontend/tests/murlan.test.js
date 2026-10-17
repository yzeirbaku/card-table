import test from 'node:test';
import assert from 'node:assert/strict';
import { cardImage, cardName, formatClock, keepHeld, placeLabel, seatGroups, sideName, toggleCard } from '../js/murlan.js';

test('card images', () => {
  assert.equal(cardImage('10H'), '/cards/10H.webp');
  assert.equal(cardImage('JC'), '/cards/JC.webp');
  assert.equal(cardImage('JB'), '/cards/joker-black.webp');
  assert.equal(cardImage('JR'), '/cards/joker-red.webp');
});

test('card images per card style: Vintage shares the Traditional pictures, Atlas and Modern have their own', () => {
  assert.equal(cardImage('KH', 'vintage'), '/cards/KH.webp');
  assert.equal(cardImage('KH', 'atlas'), '/cards/atlas/KH.webp');
  assert.equal(cardImage('JB', 'modern'), '/cards/modern/joker-black.webp');
});

test('card names', () => {
  assert.equal(cardName('10H'), '10♥');
  assert.equal(cardName('AS'), 'A♠');
  assert.equal(cardName('JC'), 'J♣');
  assert.equal(cardName('JB'), 'black joker');
  assert.equal(cardName('JR'), 'red joker');
});

test('tapping a card selects it, tapping again unselects it', () => {
  assert.deepEqual(toggleCard([], '3S'), ['3S']);
  assert.deepEqual(toggleCard(['3S', '4H'], '3S'), ['4H']);
});

test('cards that left the hand drop out of the selection', () => {
  assert.deepEqual(keepHeld(['3S', 'KH', '2C'], ['2C', '3S', '9D']), ['3S', '2C']);
});

test('pause clock', () => {
  assert.equal(formatClock(120), '2:00');
  assert.equal(formatClock(105), '1:45');
  assert.equal(formatClock(9.2), '0:10');
  assert.equal(formatClock(-3), '0:00');
});

test('seat groups: partners sit across in 4-player games', () => {
  assert.deepEqual(seatGroups(4), [[0, 2], [1, 3]]);
  assert.deepEqual(seatGroups(3), [[0, 1, 2]]);
  assert.deepEqual(seatGroups(2), [[0, 1]]);
});

test('side names and places', () => {
  assert.equal(sideName({ players: ['a', 'c'] }, { a: 'Ana', c: 'Cleo' }), 'Ana & Cleo');
  assert.equal(sideName({ players: ['b'] }, { b: 'Ben' }), 'Ben');
  assert.equal(placeLabel(0), '1st');
  assert.equal(placeLabel(3), '4th');
});
