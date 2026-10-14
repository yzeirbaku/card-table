import test from 'node:test';
import assert from 'node:assert/strict';
import { cleanCode, isCompleteCode } from '../js/code.js';

test('cleanCode uppercases and drops spaces and symbols', () => {
  assert.equal(cleanCode(' kq mz '), 'KQMZ');
  assert.equal(cleanCode('k-q.m z'), 'KQMZ');
});

test('cleanCode drops digits and caps the length at 4', () => {
  assert.equal(cleanCode('k7qm'), 'KQM');
  assert.equal(cleanCode('KQMZX'), 'KQMZ');
});

test('isCompleteCode needs exactly four letters', () => {
  assert.equal(isCompleteCode('KQMZ'), true);
  assert.equal(isCompleteCode('KQM'), false);
  assert.equal(isCompleteCode(''), false);
});
