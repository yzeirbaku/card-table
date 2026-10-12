import { endMatches, sourceGone, type Drag } from '../dragLogic';
import type { TableView } from '../../protocol';

const view: TableView = {
  version: 3,
  piles: [
    { id: 'deck', x: 0.5, y: 0.5, layout: 'stack', cards: [{ id: 'a', face_up: false }, { id: 'b', face_up: false }] },
  ],
  hand: [{ id: 'h', face_up: true, rank: 'A', suit: 'S' }],
};
const card = { id: 'b', face_up: false };
const fromDeck: Drag = { gesture: 'card', key: 'b', source: { kind: 'card', cardId: 'b', fromPileId: 'deck' }, card, settling: false };

test('only the gesture that started a drag can end it', () => {
  expect(endMatches(fromDeck, 'card', 'b')).toBe(true);
  expect(endMatches(fromDeck, 'card', 'other')).toBe(false); // second finger
  expect(endMatches(fromDeck, 'pile', 'b')).toBe(false);
  expect(endMatches(null, 'card', 'b')).toBe(false);
  expect(endMatches({ ...fromDeck, settling: true }, 'card', 'b')).toBe(false);
});

test('a drag whose source is still there is kept', () => {
  expect(sourceGone(fromDeck, view)).toBe(false);
  const hand: Drag = { ...fromDeck, key: 'h', source: { kind: 'card', cardId: 'h', fromPileId: null } };
  expect(sourceGone(hand, view)).toBe(false);
  const pile: Drag = { ...fromDeck, gesture: 'pile', key: 'deck', source: { kind: 'pile', pileId: 'deck' } };
  expect(sourceGone(pile, view)).toBe(false);
});

test('a drag whose source vanished is dropped', () => {
  const moved: TableView = { ...view, piles: [{ ...view.piles[0], cards: [{ id: 'a', face_up: false }] }] };
  expect(sourceGone(fromDeck, moved)).toBe(true);
  const empty: TableView = { ...view, piles: [], hand: [] };
  expect(sourceGone({ ...fromDeck, source: { kind: 'card', cardId: 'h', fromPileId: null } }, empty)).toBe(true);
  expect(sourceGone({ ...fromDeck, source: { kind: 'pile', pileId: 'deck' } }, empty)).toBe(true);
});

test('a pile drag is dropped when someone covers its top card', () => {
  const pileDrag: Drag = { gesture: 'card', key: 'b', source: { kind: 'pile', pileId: 'deck' }, card, settling: false };
  const covered: TableView = { ...view, piles: [{ ...view.piles[0], cards: [...view.piles[0].cards, { id: 'z', face_up: true, rank: 'K', suit: 'H' }] }] };
  expect(sourceGone(pileDrag, covered)).toBe(true);
});
