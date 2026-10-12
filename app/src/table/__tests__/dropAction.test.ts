import { toAction } from '../dropAction';
import type { PileView } from '../../protocol';

const piles: PileView[] = [
  { id: 'deck', x: 0.5, y: 0.5, layout: 'stack', cards: [{ id: 'a', face_up: false }, { id: 'b', face_up: false }] },
  { id: 'one', x: 0.2, y: 0.2, layout: 'stack', cards: [{ id: 'c', face_up: true, rank: 'A', suit: 'S' }] },
];
const card = { kind: 'card' as const, cardId: 'b', fromPileId: 'deck' };
const deck = { kind: 'pile' as const, pileId: 'deck' };
const single = { kind: 'pile' as const, pileId: 'one' };

test('null target means no action', () => {
  expect(toAction(card, null, piles, 0)).toBeNull();
});

test('card drops', () => {
  expect(toAction(card, { kind: 'hand' }, piles, 2)).toEqual({ type: 'move_card', card_id: 'b', from_pile_id: 'deck', to: { kind: 'hand', index: 2 } });
  expect(toAction(card, { kind: 'player', playerId: 'ben' }, piles, 0)).toEqual({ type: 'move_card', card_id: 'b', from_pile_id: 'deck', to: { kind: 'player', player_id: 'ben' } });
  expect(toAction(card, { kind: 'pile', pileId: 'one' }, piles, 0)).toEqual({ type: 'move_card', card_id: 'b', from_pile_id: 'deck', to: { kind: 'pile', pile_id: 'one' } });
  expect(toAction(card, { kind: 'table', x: 0.1, y: 0.9 }, piles, 0)).toEqual({ type: 'move_card', card_id: 'b', from_pile_id: 'deck', to: { kind: 'table', x: 0.1, y: 0.9 } });
});

test('pile drops', () => {
  expect(toAction(deck, { kind: 'hand' }, piles, 0)).toEqual({ type: 'take_pile', pile_id: 'deck' });
  expect(toAction(deck, { kind: 'player', playerId: 'ben' }, piles, 0)).toBeNull();
  expect(toAction(deck, { kind: 'pile', pileId: 'one' }, piles, 0)).toEqual({ type: 'merge_pile', pile_id: 'deck', onto_pile_id: 'one' });
  expect(toAction(deck, { kind: 'table', x: 0.3, y: 0.4 }, piles, 0)).toEqual({ type: 'move_pile', pile_id: 'deck', x: 0.3, y: 0.4 });
});

test('a single-card pile behaves like its card for hand and players', () => {
  expect(toAction(single, { kind: 'hand' }, piles, 1)).toEqual({ type: 'move_card', card_id: 'c', from_pile_id: 'one', to: { kind: 'hand', index: 1 } });
  expect(toAction(single, { kind: 'player', playerId: 'ben' }, piles, 0)).toEqual({ type: 'move_card', card_id: 'c', from_pile_id: 'one', to: { kind: 'player', player_id: 'ben' } });
});

test('vanished pile means no action', () => {
  expect(toAction({ kind: 'pile', pileId: 'gone' }, { kind: 'hand' }, piles, 0)).toBeNull();
});

test('hand cards say they came from the hand', () => {
  const fromHand = { kind: 'card' as const, cardId: 'h', fromPileId: null };
  expect(toAction(fromHand, { kind: 'table', x: 0.5, y: 0.5 }, piles, 0)).toEqual({
    type: 'move_card', card_id: 'h', from_pile_id: null, to: { kind: 'table', x: 0.5, y: 0.5 },
  });
});
