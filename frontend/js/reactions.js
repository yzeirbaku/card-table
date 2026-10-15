import { span } from './dom.js';

/** The emoji a player can throw: [id the server knows, emoji, the bits that fly off it]. */
export const REACTIONS = [
  ['shocked', '😮', ['!', '!']],
  ['laughing', '😂', ['ha', 'ha']],
  ['angry', '😠', ['', '']], // two puffs of steam
  ['asleep', '😴', ['z', 'z', 'z']],
];
const REACTION_MS = 2800; // how long one plays (the CSS animations' length)
const BY_ID = Object.fromEntries(REACTIONS.map(([id, emoji, bits]) => [id, { emoji, bits }]));

let showing = new Map(); // player id -> { kind, at } while their reaction plays

/** Someone reacted: `paint(playerId)` shows it over their name, and again once it has played, without it. */
export function addReaction(playerId, kind, paint) {
  if (!BY_ID[kind]) return;
  const entry = { kind, at: performance.now() };
  showing.set(playerId, entry);
  setTimeout(() => {
    if (showing.get(playerId) !== entry) return; // a newer one took its place
    showing.delete(playerId);
    paint(playerId);
  }, REACTION_MS);
  paint(playerId);
}

/** The reaction playing over this player's name, or null. A redraw picks it up where it was. */
export function reactionEl(playerId) {
  const entry = showing.get(playerId);
  if (!entry) return null;
  const { emoji, bits } = BY_ID[entry.kind];
  const el = span('', `reaction reaction-${entry.kind}`);
  el.setAttribute('aria-hidden', 'true');
  el.style.setProperty('--since', `${-(performance.now() - entry.at)}ms`);
  el.append(span(emoji, 'reaction-face'), ...bits.map((bit, i) => span(bit, `reaction-bit b${i + 1}`)));
  return el;
}

export function resetReactions() {
  showing = new Map();
}
