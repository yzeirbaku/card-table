// Pure helpers for showing a Murlan game. No rules here: the server decides everything.

const SUITS = { S: '♠', H: '♥', D: '♦', C: '♣' };
const JOKER_FILES = { JB: 'joker-black', JR: 'joker-red' };
const PLACES = ['1st', '2nd', '3rd', '4th'];

/** Every card in the deck: 2-10, J, Q, K, A of each suit, and the two jokers. */
export const ALL_CARDS = [...'23456789', '10', ...'JQKA']
  .flatMap((rank) => Object.keys(SUITS).map((suit) => rank + suit))
  .concat(Object.keys(JOKER_FILES));

// Atlas and Modern have their own pictures; Vintage is Traditional's, aged in CSS.
const STYLE_DIRS = { atlas: 'atlas/', modern: 'modern/' };

/** Image for a card code such as "10H" or "JR", in a card style. */
export function cardImage(code, style = 'traditional') {
  return `/cards/${STYLE_DIRS[style] ?? ''}${JOKER_FILES[code] ?? code}.webp`;
}

/** "10♥", "red joker". */
export function cardName(code) {
  if (code === 'JB') return 'black joker';
  if (code === 'JR') return 'red joker';
  return code.slice(0, -1) + SUITS[code.slice(-1)];
}

/** Tap a card: select it, or unselect it if it was selected. */
export function toggleCard(selected, code) {
  return selected.includes(code) ? selected.filter((c) => c !== code) : [...selected, code];
}

/** Drop selected cards that are no longer in the hand (played, given away). */
export function keepHeld(selected, hand) {
  return selected.filter((c) => hand.includes(c));
}

/** 105 -> "1:45". */
export function formatClock(seconds) {
  const s = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/** Seats the way the lobby groups them: in 4-player games partners sit across (0+2, 1+3). */
export function seatGroups(seats) {
  if (seats === 4) return [[0, 2], [1, 3]];
  return [Array.from({ length: seats }, (_, i) => i)];
}

/** "Ana & Cleo" for a team, "Ben" for a single player. */
export function sideName(side, names) {
  return side.players.map((id) => names[id] ?? '?').join(' & ');
}

export function placeLabel(index) {
  return PLACES[index];
}
