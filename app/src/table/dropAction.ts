import type { Action, PileView } from '../protocol';
import type { DragSource, DropTarget } from './geometry';

/** Translate a finished drag into the action to send, or null to snap back. */
export function toAction(
  source: DragSource,
  target: DropTarget,
  piles: PileView[],
  handIndex: number,
): Action | null {
  if (!target) return null;

  if (source.kind === 'card') {
    const card_id = source.cardId;
    switch (target.kind) {
      case 'hand':
        return { type: 'move_card', card_id, to: { kind: 'hand', index: handIndex } };
      case 'player':
        return { type: 'move_card', card_id, to: { kind: 'player', player_id: target.playerId } };
      case 'pile':
        return { type: 'move_card', card_id, to: { kind: 'pile', pile_id: target.pileId } };
      case 'table':
        return { type: 'move_card', card_id, to: { kind: 'table', x: target.x, y: target.y } };
    }
  }

  const pile = piles.find((p) => p.id === source.pileId);
  if (!pile) return null;
  // Dragging a lone card is a pile drag; for hand/player it should act like the card.
  const lone = pile.cards.length === 1 ? pile.cards[0].id : null;
  switch (target.kind) {
    case 'hand':
      return lone
        ? { type: 'move_card', card_id: lone, to: { kind: 'hand', index: handIndex } }
        : { type: 'take_pile', pile_id: pile.id };
    case 'player':
      return lone ? { type: 'move_card', card_id: lone, to: { kind: 'player', player_id: target.playerId } } : null;
    case 'pile':
      return { type: 'merge_pile', pile_id: pile.id, onto_pile_id: target.pileId };
    case 'table':
      return { type: 'move_pile', pile_id: pile.id, x: target.x, y: target.y };
  }
}
