// The end of a round, shown before anything else. First the final cards stay on the pile
// for a moment, so everyone sees how it ended; then the table dims, a crown sits over the
// winner, a gold banner names them, and the points rise next to the scores. A round's
// spotlight goes after a few seconds; a won game's stays until someone taps.

import { sideName } from './murlan.js';

const HOLD_MS = 2500; // the final cards alone on the pile, before the result
const ROUND_MS = 3200;

let shown; // the last result already shown (undefined: nothing drawn yet, so don't replay one)
let shownResult = null; // that result without the game-over flag, to tell new points from old
let active = null; // { crowned: [player ids], text, tag, why, game: bool, points, pile, holding: bool } while the spotlight is up
let timer = null;

export function resetSpotlight() {
  shown = undefined;
  shownResult = null;
  active = null;
  clearTimeout(timer);
}

/** Whether the spotlight is up, so the overlay waits. */
export function spotlightOn() {
  return active !== null;
}

/** Players who get a crown right now. */
export function crowned(playerId) {
  return lit() && active.crowned.includes(playerId);
}

/** Points each side just won, while the spotlight is up (else nothing). */
export function gains() {
  return lit() ? active.points : null;
}

/** The round's final trick, kept on the pile while the spotlight is up (else nothing). */
export function finalPile() {
  return active?.pile ?? null;
}

/** The hands thrown in during the round that just ended ({ player id: cards }), or null. */
export function finalThrown() {
  return active?.thrown ?? null;
}

/** Past the moment for the final cards: the result is showing. */
function lit() {
  return active !== null && !active.holding;
}

/**
 * Start the spotlight when a new round result arrives. `redraw` repaints the table when it ends.
 * Call once per render, before drawing anything that depends on it.
 */
export function updateSpotlight(game, names, redraw) {
  const result = game.last_round;
  const over = game.phase === 'game_over';
  if (active?.game && !over) active = null; // play again or shuffle: the old game's banner goes
  const resultKey = result ? `${game.round}:${result.places.join()}:${game.sides.map((s) => s.score).join()}` : null;
  const key = resultKey && `${resultKey}:${over}`;
  const fresh = resultKey !== shownResult; // new points, not just the game ending on old ones
  shownResult = resultKey;
  if (shown === undefined || key === null || key === shown) {
    shown = key;
    return;
  }
  shown = key;
  const points = fresh ? result.points : null;
  const pile = fresh && result.pile?.length ? result.pile : null; // new cards: show them first
  const thrown = fresh && Object.keys(result.thrown ?? {}).length ? result.thrown : null; // and any hand thrown in
  clearTimeout(timer);
  const sideOf = (id) => game.sides.find((side) => side.players.includes(id));
  if (over) {
    const side = game.winner_side === null ? null : game.sides[game.winner_side];
    const many = side && side.players.length > 1;
    const others = game.clinched ? game.sides.find((s) => s !== side) : null; // won early: they can't catch up
    active = {
      crowned: side ? side.players : [],
      text: side ? `${sideName(side, names)} ${many ? 'win' : 'wins'} the game!` : "It's a draw",
      tag: others ? `Decided early · ${side.score}–${others.score}` : null,
      why: others ? `${sideName(others, names)} can't reach ${game.target} first` : null,
      game: true,
      points,
      pile,
      thrown,
      holding: pile !== null || thrown !== null,
    };
    hold(redraw, () => {}); // then stays until a tap
    return;
  }
  const winner = result.places[0];
  const side = sideOf(winner);
  const tie = result.points.length === 2 && result.points[0] === result.points[1]; // 4 players, 3–3: nobody won it
  active = {
    crowned: tie ? [] : [winner],
    text: tie ? `Tie round · ${result.points[0]}–${result.points[1]}` : `${sideName(side, names)} ${side.players.length > 1 ? 'win' : 'wins'} the round`,
    tag: null,
    why: null,
    game: false,
    points,
    pile,
    thrown,
    holding: pile !== null || thrown !== null,
  };
  const spot = active;
  hold(redraw, () => {
    timer = setTimeout(() => {
      if (active !== spot) return;
      active = null;
      redraw();
    }, ROUND_MS);
  });
}

/** Keep the final cards alone for a moment (if there are any), then show the result and go on. */
function hold(redraw, next) {
  const spot = active;
  if (!spot.holding) return next();
  timer = setTimeout(() => {
    if (active !== spot) return; // gone meanwhile (play again, table left)
    spot.holding = false;
    redraw();
    next();
  }, HOLD_MS);
}

/** Draw the shade and banner (or clear them). `redraw` repaints after a tap ends a game's spotlight. */
export function renderSpotlight(redraw) {
  const table = document.querySelector('.table');
  const shade = document.querySelector('.spot-shade');
  const ribbon = document.querySelector('.ribbon');
  const on = lit();
  table.classList.toggle('spotlight', on);
  shade.hidden = !on;
  ribbon.hidden = !on;
  if (!on) return;
  ribbon.classList.toggle('big', active.game);
  ribbon.querySelector('.ribbon-text').textContent = active.text;
  for (const [cls, value] of [['.ribbon-tag', active.tag], ['.ribbon-why', active.why]]) {
    const el = ribbon.querySelector(cls);
    el.textContent = value ?? '';
    el.hidden = !value;
  }
  ribbon.querySelector('.ribbon-hint').hidden = !active.game;
  shade.onclick = ribbon.onclick = active.game ? () => { active = null; redraw(); } : null;
}
