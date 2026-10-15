import test from 'node:test';
import assert from 'node:assert/strict';
import { shouldRotate } from '../js/orientation.js';

test('portrait phone gets rotated', () => assert.equal(shouldRotate(390, 844), true));
test('landscape phone does not', () => assert.equal(shouldRotate(844, 390), false));
test('square or desktop does not', () => {
  assert.equal(shouldRotate(800, 800), false);
  assert.equal(shouldRotate(1440, 900), false);
});
