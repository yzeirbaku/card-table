// A hand thrown in: when someone gives up, their cards fly face up from their seat (yours from
// your hand) and land all over the table, where they stay until the round is over.

import { place } from './deal.js';
import { face } from './dom.js';

const FLIGHT_MS = 800; // one card's flight (the CSS animation's length)
const STAGGER_MS = 35; // between two cards leaving the hand

let flights = new Map(); // player id -> { at, from } for a throw seen happening
let seen = null; // who had thrown at the last render (null: nothing drawn yet, so nothing flies)

export function resetThrows() {
  flights = new Map();
  seen = null;
}

/** Call before the table is redrawn, while the thrower's cards are still where they were. */
export function noteThrows(thrown, meId) {
  const ids = Object.keys(thrown);
  if (seen !== null) {
    const table = document.querySelector('.table');
    for (const id of ids) {
      if (seen.has(id)) continue;
      const fromEl = id === meId
        ? document.querySelector('.hand')
        : document.querySelector(`.seats .plate[data-player="${CSS.escape(id)}"]`)?.closest('.seat');
      flights.set(id, { at: performance.now(), from: fromEl ? place(fromEl, table) : null });
    }
  }
  seen = new Set(ids);
}

/** Draw every thrown card where it lies; one still in flight picks up where it was. */
export function renderThrown(thrown) {
  const now = performance.now();
  document.querySelector('.thrown-layer').replaceChildren(...Object.entries(thrown).flatMap(([id, cards]) => {
    const flight = flights.get(id);
    return cards.map((code, i) => {
      const el = face(code, 'thrown-card');
      const spot = spotFor(id, code);
      el.style.left = `${spot.x}%`;
      el.style.top = `${spot.y}%`;
      el.style.rotate = `${spot.turn}deg`;
      const since = flight ? now - flight.at - i * STAGGER_MS : Infinity;
      if (flight?.from && since < FLIGHT_MS) {
        el.classList.add('flying');
        el.style.setProperty('--from-x', `${flight.from.x}px`);
        el.style.setProperty('--from-y', `${flight.from.y}px`);
        el.style.setProperty('--since', `${-since}ms`); // positive: still waiting its turn to leave
      }
      return el;
    });
  }));
}

/** Where a thrown card lands: messy, but the same spot on every redraw and every screen. */
function spotFor(playerId, code) {
  let h = 2166136261;
  for (const ch of `${playerId}|${code}`) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  const next = () => {
    h = Math.imul(h ^ (h >>> 15), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    return ((h ^= h >>> 16) >>> 0) / 4294967296;
  };
  return { x: 12 + next() * 76, y: 24 + next() * 44, turn: Math.round(next() * 300 - 150) };
}
