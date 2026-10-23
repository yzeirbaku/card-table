import { div, span } from './dom.js';

/** The emoji a player can throw: [id the server knows, emoji, the bits that fly off it]. */
export const REACTIONS = [
  ['shocked', '😮', ['!', '!']],
  ['laughing', '😂', ['ha', 'ha']],
  ['angry', '😠', ['', '']], // two puffs of steam
  ['asleep', '😴', ['z', 'z', 'z']],
  ['catan', '💩', []], // "Catan cards": a bad hand. Plays as CATAN across the whole table, not over the name
  ['clap', '👏', []], // plays as a picture and BRAVO, BRAVO! across the whole table, not over the name
  ['please', '🙏', ['pls']],
];
const REACTION_MS = 2800; // how long one plays (the CSS animations' length)
const BY_ID = Object.fromEntries(REACTIONS.map(([id, emoji, bits]) => [id, { emoji, bits }]));
const BRAVO_PIC = 'reactions/bravo.png';
new Image().src = BRAVO_PIC; // fetched up front, so the first 👏 doesn't play before its picture is in

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
  for (const sel of ['.catan', '.bravo']) {
    clearTimeout(stampTimers[sel]);
    const el = document.querySelector(sel);
    if (el) el.hidden = true;
  }
}

const stampTimers = {};

/** Play a whole-table stamp: fill it, then restart its animations. A new one starts it over. */
function stamp(sel, ...children) {
  const el = document.querySelector(sel);
  if (!el) return;
  el.replaceChildren(...children);
  el.hidden = true;
  void el.offsetWidth; // restart the animations
  el.hidden = false;
  clearTimeout(stampTimers[sel]);
  stampTimers[sel] = setTimeout(() => { el.hidden = true; }, REACTION_MS);
}

/** Someone sent 💩: "Yzeir has CATAN cards" stamped across the whole table, for everyone.
 *  `who` is "Yzeir has" or "You have". */
export function stampCatan(who) {
  const letters = div('catan-word');
  letters.append(...[...'CATAN'].map((letter) => span(letter)));
  stamp('.catan', span(who, 'catan-who'), letters, span('cards', 'catan-cards'));
}

/** Someone sent 👏: the picture pops up over the table with BRAVO, BRAVO!, for everyone. */
export function stampBravo() {
  const picture = document.createElement('img');
  picture.className = 'bravo-pic';
  picture.src = BRAVO_PIC;
  picture.alt = '';
  const words = div('bravo-words');
  words.append(span('BRAVO,'), span('BRAVO!'));
  stamp('.bravo', picture, words);
}
