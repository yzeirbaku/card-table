import test from 'node:test';
import assert from 'node:assert/strict';
import { appSize, shouldRotate } from '../js/orientation.js';

test('portrait phone gets rotated', () => assert.equal(shouldRotate(390, 844), true));
test('landscape phone does not', () => assert.equal(shouldRotate(844, 390), false));
test('a browser tab uses its viewport', () => {
  assert.deepEqual(appSize({ standalone: false, innerWidth: 390, innerHeight: 700, screenWidth: 393, screenHeight: 852 }), { width: 390, height: 700 });
});
test('an iPhone home-screen app reaching under the status bar fills the whole screen, either way up', () => {
  assert.deepEqual(appSize({ standalone: true, innerWidth: 393, innerHeight: 793, screenWidth: 393, screenHeight: 852 }), { width: 393, height: 852 });
  assert.deepEqual(appSize({ standalone: true, innerWidth: 852, innerHeight: 393, screenWidth: 393, screenHeight: 852 }), { width: 852, height: 393 });
  assert.deepEqual(appSize({ standalone: true, innerWidth: 793, innerHeight: 393, screenWidth: 393, screenHeight: 852 }), { width: 852, height: 393 });
});

test('square or desktop does not', () => {
  assert.equal(shouldRotate(800, 800), false);
  assert.equal(shouldRotate(1440, 900), false);
});
