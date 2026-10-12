import type { CardView, TableView } from '../protocol';
import type { DragSource } from './geometry';

/** `key` is the card id (card pan) or pile id (pile pan) of the gesture that started the drag. */
export type Drag = { gesture: 'card' | 'pile'; key: string; source: DragSource; card: CardView; settling: boolean };

/** Only the gesture that started an active drag may end it (ignores second fingers and late events). */
export function endMatches(d: Drag | null, kind: 'card' | 'pile', key: string): d is Drag {
  return d !== null && !d.settling && d.gesture === kind && d.key === key;
}

/** True when another player's action removed what's being dragged; its gesture may never end. */
export function sourceGone(d: Drag, view: TableView): boolean {
  const s = d.source;
  if (s.kind === 'pile') {
    // The gesture lives on the pile's top card; a new top card re-keys it.
    const pile = view.piles.find((p) => p.id === s.pileId);
    return !pile || pile.cards[pile.cards.length - 1].id !== d.card.id;
  }
  if (s.fromPileId === null) return !view.hand.some((c) => c.id === s.cardId);
  const pile = view.piles.find((p) => p.id === s.fromPileId);
  return !pile || pile.cards[pile.cards.length - 1].id !== s.cardId;
}
