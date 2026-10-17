import test from 'node:test';
import assert from 'node:assert/strict';
import { bombName, brokenBomb, cardImage, cardName, formatClock, keepHeld, placeLabel, sideName, toggleCard } from '../js/murlan.js';

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

test('side names and places', () => {
  assert.equal(sideName({ players: ['a', 'c'] }, { a: 'Ana', c: 'Cleo' }), 'Ana & Cleo');
  assert.equal(sideName({ players: ['b'] }, { b: 'Ben' }), 'Ben');
  assert.equal(placeLabel(0), '1st');
  assert.equal(placeLabel(3), '4th');
});

test('a play that uses some but not all of a bomb breaks it up', () => {
  const bombs = [['3S', '3H', '3D', '3C'], ['AS', 'AH', 'AD', 'AC']];
  assert.deepEqual(brokenBomb(['3S'], bombs), bombs[0]);
  assert.deepEqual(brokenBomb(['AS', 'AH', '5D'], bombs), bombs[1]);
  assert.equal(brokenBomb(['3S', '3H', '3D', '3C'], bombs), null); // the whole bomb
  assert.equal(brokenBomb(['5D', 'JR'], bombs), null);
  assert.equal(brokenBomb(['3S']), null); // an older server sends no bombs
});

test('bomb names', () => {
  assert.equal(bombName(['3S', '3H', '3D', '3C']), 'all four 3s');
  assert.equal(bombName(['10S', '10H', '10D', '10C']), 'all four 10s');
  assert.equal(bombName(['AS', 'AH', 'AD', 'AC']), 'all four aces');
});
