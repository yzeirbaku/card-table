// The end of a round, shown before anything else: the table dims, a crown sits over the
// winner, a gold banner names them, and the points rise next to the scores. A round's
// spotlight goes after a few seconds; a won game's stays until someone taps.

import { sideName } from './murlan.js';

const ROUND_MS = 3200;

let shown; // the last result already shown (undefined: nothing drawn yet, so don't replay one)
let active = null; // { crowned: [player ids], text, game: bool } while the spotlight is up
let timer = null;

export function resetSpotlight() {
  shown = undefined;
  active = null;
  clearTimeout(timer);
}

/** Whether the spotlight is up, so the overlay waits. */
export function spotlightOn() {
  return active !== null;
}

/** Players who get a crown right now. */
export function crowned(playerId) {
  return active !== null && active.crowned.includes(playerId);
}

/** Points each side just won, while the spotlight is up (else nothing). */
export function gains(game) {
  return active && game.last_round ? game.last_round.points : null;
}

/**
 * Start the spotlight when a new round result arrives. `redraw` repaints the table when it ends.
 * Call once per render, before drawing anything that depends on it.
 */
export function updateSpotlight(game, names, redraw) {
  const result = game.last_round;
  const over = game.phase === 'game_over';
  const key = result ? `${game.round}:${result.places.join()}:${game.sides.map((s) => s.score).join()}:${over}` : null;
  if (shown === undefined || key === null || key === shown) {
    shown = key;
    return;
  }
  shown = key;
  clearTimeout(timer);
  const sideOf = (id) => game.sides.find((side) => side.players.includes(id));
  if (over) {
    const side = game.winner_side === null ? null : game.sides[game.winner_side];
    const many = side && side.players.length > 1;
    active = {
      crowned: side ? side.players : [],
      text: side ? `${sideName(side, names)} ${many ? 'win' : 'wins'} the game!` : "It's a draw",
      game: true,
    };
    return; // stays until a tap
  }
  const winner = result.places[0];
  const side = sideOf(winner);
  active = {
    crowned: [winner],
    text: `${sideName(side, names)} ${side.players.length > 1 ? 'win' : 'wins'} the round`,
    game: false,
  };
  timer = setTimeout(() => {
    active = null;
    redraw();
  }, ROUND_MS);
}

/** Draw the shade and banner (or clear them). `redraw` repaints after a tap ends a game's spotlight. */
export function renderSpotlight(redraw) {
  const table = document.querySelector('.table');
  const shade = document.querySelector('.spot-shade');
  const ribbon = document.querySelector('.ribbon');
  table.classList.toggle('spotlight', active !== null);
  shade.hidden = active === null;
  ribbon.hidden = active === null;
  if (!active) return;
  ribbon.classList.toggle('big', active.game);
  ribbon.querySelector('.ribbon-text').textContent = active.text;
  ribbon.querySelector('.ribbon-hint').hidden = !active.game;
  shade.onclick = ribbon.onclick = active.game ? () => { active = null; redraw(); } : null;
}
