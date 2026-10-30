import test from 'node:test';
import assert from 'node:assert/strict';
import { initial, partnerLabel, rate, record, tagLine } from '../js/stats-format.js';

const wl = (won, lost) => ({ won, lost });
const stats = (solo, teams) => ({
  username: 'Sebi',
  solo: { people: wl(0, 0), computer: wl(0, 0), total: solo },
  teams: { people: wl(0, 0), computer: wl(0, 0), total: teams },
  partners: [],
});

test('a record reads wins–losses', () => {
  assert.equal(record(wl(12, 9)), '12–9');
  assert.equal(record(wl(0, 0)), '0–0');
});

test('the win rate rounds, and is a dash with no games', () => {
  assert.equal(rate(wl(2, 1)), '67%');
  assert.equal(rate(wl(6, 2)), '75%');
  assert.equal(rate(wl(0, 0)), '–');
});

test('the tag line adds solo and teams', () => {
  assert.equal(tagLine(stats(wl(32, 13), wl(19, 8))), '51 wins · 21 losses · 71%');
  assert.equal(tagLine(stats(wl(1, 0), wl(0, 0))), '1 win · 0 losses · 100%');
  assert.equal(tagLine(stats(wl(0, 1), wl(0, 0))), '0 wins · 1 loss · 0%');
  assert.equal(tagLine(stats(wl(0, 0), wl(0, 0))), 'No games yet');
});

test('the initial is the first letter, capitalised', () => {
  assert.equal(initial('sebi'), 'S');
  assert.equal(initial('_x'), '_');
  assert.equal(initial(''), '?');
});

test('partners read as names, a computer or a guest', () => {
  assert.equal(partnerLabel({ kind: 'user', name: 'Arben' }), 'Arben');
  assert.equal(partnerLabel({ kind: 'computer' }), 'a computer');
  assert.equal(partnerLabel({ kind: 'guest' }), 'a guest');
});
