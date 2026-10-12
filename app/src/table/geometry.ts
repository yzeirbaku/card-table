import type { Layout } from '../protocol';

export type Rect = { x: number; y: number; width: number; height: number };
export type Point = { x: number; y: number };
export type Size = { width: number; height: number };
export type Regions = { table: Rect; hand: Rect; avatars: { playerId: string; rect: Rect }[] };

/** fromPileId null = dragging a card from your own hand. */
export type DragSource =
  | { kind: 'card'; cardId: string; fromPileId: string | null }
  | { kind: 'pile'; pileId: string };

export type DropTarget =
  | { kind: 'hand' }
  | { kind: 'player'; playerId: string }
  | { kind: 'pile'; pileId: string }
  | { kind: 'table'; x: number; y: number }
  | null;

type PileShape = { id: string; x: number; y: number; layout: Layout; cards: unknown[] };

export const HAND_PADDING = 8;
export const HAND_TOP = 12;

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export function contains(r: Rect, p: Point): boolean {
  return p.x >= r.x && p.x <= r.x + r.width && p.y >= r.y && p.y <= r.y + r.height;
}

export function cardSize(tableWidth: number): Size {
  const width = Math.round(clamp(tableWidth / 6, 40, 64));
  return { width, height: Math.round(width * 1.4) };
}

/** Horizontal offset between fanned cards, shrunk so the fan stays on the table. */
export function fanStep(pile: PileShape, tableWidth: number, card: Size): number {
  if (pile.layout !== 'fan' || pile.cards.length < 2) return 0;
  const left = pile.x * tableWidth - card.width / 2;
  const room = tableWidth - left - card.width;
  return clamp(room / (pile.cards.length - 1), 2, card.width * 0.28);
}

/** Pile bounds relative to the table's top-left corner. (x, y) is the first card's centre. */
export function pileOffset(pile: PileShape, table: Size, card: Size): Rect {
  const step = fanStep(pile, table.width, card);
  return {
    x: pile.x * table.width - card.width / 2,
    y: pile.y * table.height - card.height / 2,
    width: card.width + step * Math.max(0, pile.cards.length - 1),
    height: card.height,
  };
}

export function pileRect(pile: PileShape, table: Rect, card: Size): Rect {
  const o = pileOffset(pile, table, card);
  return { ...o, x: o.x + table.x, y: o.y + table.y };
}

export function toTableFraction(p: Point, table: Rect, card: Size): Point {
  const hx = card.width / 2 / table.width;
  const hy = card.height / 2 / table.height;
  return {
    x: clamp((p.x - table.x) / table.width, hx, 1 - hx),
    y: clamp((p.y - table.y) / table.height, hy, 1 - hy),
  };
}

export function handStep(count: number, handWidth: number, card: Size): number {
  if (count < 2) return 0;
  return Math.min(card.width * 0.9, (handWidth - 2 * HAND_PADDING - card.width) / (count - 1));
}

/** Which of `count` hand slots the point is over. */
export function handIndexAt(px: number, count: number, hand: Rect, card: Size): number {
  if (count < 2) return 0;
  const step = handStep(count, hand.width, card);
  const i = Math.round((px - hand.x - HAND_PADDING - card.width / 2) / step);
  return clamp(i, 0, count - 1);
}

export function resolveDrop(
  p: Point,
  source: DragSource,
  regions: Regions,
  piles: PileShape[],
  selfId: string | null,
  card: Size,
): DropTarget {
  if (contains(regions.hand, p)) return { kind: 'hand' };
  const avatar = regions.avatars.find((a) => contains(a.rect, p));
  if (avatar) return avatar.playerId === selfId ? null : { kind: 'player', playerId: avatar.playerId };
  if (!contains(regions.table, p)) return null;
  // Later piles render on top, so hit-test from the end.
  for (let i = piles.length - 1; i >= 0; i--) {
    const pile = piles[i];
    if (source.kind === 'pile' && pile.id === source.pileId) continue;
    if (contains(pileRect(pile, regions.table, card), p)) {
      if (source.kind === 'card' && pile.id === source.fromPileId) return null;
      return { kind: 'pile', pileId: pile.id };
    }
  }
  const f = toTableFraction(p, regions.table, card);
  return { kind: 'table', x: f.x, y: f.y };
}
