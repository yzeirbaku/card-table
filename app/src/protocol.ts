// Mirror of backend/app/engine/protocol.py and views.py. Keep in sync.

export type Suit = 'S' | 'H' | 'D' | 'C';

/** rank/suit are present only when the card is visible to you. */
export type CardView = { id: string; face_up: boolean; rank?: string; suit?: Suit | null };

export type Layout = 'stack' | 'fan';

export type PileView = { id: string; x: number; y: number; layout: Layout; cards: CardView[] };

export type TableView = { version: number; piles: PileView[]; hand: CardView[] };

export type PlayerView = {
  id: string;
  name: string;
  connected: boolean;
  is_host: boolean;
  hand_count: number;
};

export type Destination =
  | { kind: 'pile'; pile_id: string }
  | { kind: 'table'; x: number; y: number }
  | { kind: 'hand'; index?: number }
  | { kind: 'player'; player_id: string };

export type Action =
  | { type: 'move_card'; card_id: string; to: Destination; face_up?: boolean; from_pile_id?: string | null }
  | { type: 'flip_card'; card_id: string }
  | { type: 'move_pile'; pile_id: string; x: number; y: number }
  | { type: 'merge_pile'; pile_id: string; onto_pile_id: string }
  | { type: 'shuffle'; pile_id: string }
  | { type: 'flip_pile'; pile_id: string }
  | { type: 'set_layout'; pile_id: string; layout: Layout }
  | { type: 'deal'; pile_id: string; count: number }
  | { type: 'take_pile'; pile_id: string }
  | { type: 'gather' }
  | { type: 'new_deck'; jokers: number };

export type ServerMessage =
  | { type: 'welcome'; player_id: string; token: string; code: string }
  | { type: 'state'; code: string; players: PlayerView[]; view: TableView }
  | { type: 'error'; message: string };
