import {
  cardSize, contains, fanStep, handIndexAt, handStep, pileRect, resolveDrop, toTableFraction,
  type Regions,
} from '../geometry';
import type { PileView } from '../../protocol';

const table = { x: 10, y: 100, width: 360, height: 400 };
const card = { width: 60, height: 84 };
const pile = (id: string, x: number, y: number, n = 1, layout: 'stack' | 'fan' = 'stack'): PileView => ({
  id, x, y, layout, cards: Array.from({ length: n }, (_, i) => ({ id: `${id}-${i}`, face_up: false })),
});
const regions: Regions = {
  table,
  hand: { x: 0, y: 520, width: 380, height: 110 },
  avatars: [
    { playerId: 'me', rect: { x: 0, y: 50, width: 80, height: 40 } },
    { playerId: 'ben', rect: { x: 90, y: 50, width: 80, height: 40 } },
  ],
};

test('contains is inclusive', () => {
  expect(contains(table, { x: 10, y: 100 })).toBe(true);
  expect(contains(table, { x: 9, y: 100 })).toBe(false);
});

test('cardSize scales with table width within bounds', () => {
  expect(cardSize(360)).toEqual({ width: 60, height: 84 });
  expect(cardSize(1000).width).toBe(64);
  expect(cardSize(100).width).toBe(40);
});

test('fanStep is 0 for stacks and keeps a fan on the table', () => {
  expect(fanStep(pile('a', 0.5, 0.5, 5), 360, card)).toBe(0);
  expect(fanStep(pile('a', 0.2, 0.5, 3, 'fan'), 360, card)).toBeCloseTo(60 * 0.28);
  const wide = pile('a', 0.5, 0.5, 52, 'fan');
  const step = fanStep(wide, 360, card);
  expect(0.5 * 360 - 30 + 60 + step * 51).toBeLessThanOrEqual(360 + 0.001);
});

test('pileRect is centred on the pile position in window coordinates', () => {
  expect(pileRect(pile('a', 0.5, 0.5), table, card)).toEqual({ x: 160, y: 258, width: 60, height: 84 });
});

test('toTableFraction keeps the card fully on the table', () => {
  expect(toTableFraction({ x: 190, y: 300 }, table, card)).toEqual({ x: 0.5, y: 0.5 });
  const corner = toTableFraction({ x: 0, y: 0 }, table, card);
  expect(corner.x).toBeCloseTo(30 / 360);
  expect(corner.y).toBeCloseTo(42 / 400);
});

test('hand layout and index', () => {
  expect(handStep(1, 380, card)).toBe(0);
  expect(handStep(3, 380, card)).toBe(54); // 0.9 * 60 fits
  expect(handStep(40, 380, card)).toBeCloseTo((380 - 16 - 60) / 39);
  const hand = regions.hand;
  expect(handIndexAt(0, 3, hand, card)).toBe(0);
  expect(handIndexAt(8 + 30 + 54, 3, hand, card)).toBe(1);
  expect(handIndexAt(9999, 3, hand, card)).toBe(2);
  expect(handIndexAt(50, 1, hand, card)).toBe(0);
});

describe('resolveDrop', () => {
  const piles = [pile('deck', 0.5, 0.5, 40), pile('other', 0.2, 0.2, 1)];
  const fromDeck = { kind: 'card' as const, cardId: 'deck-39', fromPileId: 'deck' };

  test('hand region wins', () => {
    expect(resolveDrop({ x: 100, y: 560 }, fromDeck, regions, piles, 'me', card)).toEqual({ kind: 'hand' });
  });
  test('other players avatar, never your own', () => {
    expect(resolveDrop({ x: 120, y: 70 }, fromDeck, regions, piles, 'me', card)).toEqual({ kind: 'player', playerId: 'ben' });
    expect(resolveDrop({ x: 20, y: 70 }, fromDeck, regions, piles, 'me', card)).toBeNull();
  });
  test('onto another pile', () => {
    const p = { x: 10 + 0.2 * 360, y: 100 + 0.2 * 400 };
    expect(resolveDrop(p, fromDeck, regions, piles, 'me', card)).toEqual({ kind: 'pile', pileId: 'other' });
  });
  test('card dropped back on its own pile cancels', () => {
    expect(resolveDrop({ x: 190, y: 300 }, fromDeck, regions, piles, 'me', card)).toBeNull();
  });
  test('pile dragged over itself moves instead', () => {
    const t = resolveDrop({ x: 200, y: 310 }, { kind: 'pile', pileId: 'deck' }, regions, piles, 'me', card);
    expect(t?.kind).toBe('table');
  });
  test('empty table spot', () => {
    expect(resolveDrop({ x: 300, y: 450 }, fromDeck, regions, piles, 'me', card)).toEqual({
      kind: 'table', x: (300 - 10) / 360, y: (450 - 100) / 400,
    });
  });
  test('outside everything cancels', () => {
    expect(resolveDrop({ x: 500, y: 10 }, fromDeck, regions, piles, 'me', card)).toBeNull();
  });
});
