import { button, div, face, span } from './dom.js';
import { cardName, keepHeld, placeLabel, sideName, toggleCard } from './murlan.js';
import { seatPositions } from './seats.js';
import { renderOverlay, renderReveal, stopCountdown } from './table-overlay.js';
import { toast } from './ui.js';

const MAX_BACKS = 7; // card backs drawn per opponent; the count shows the real number

let send = () => {};
let selected = []; // card codes picked in your hand
let current = null; // the last state drawn, to redraw the hand after a tap
let lastPhase = null;
let lastRound = null; // and the round: a new one starts with nothing selected // the phase of the last render: a new phase starts with nothing selected
let waiting = false; // a move is out: ignore taps until the next state arrives

/** Send a move once; further taps are ignored until the server answers with a state. */
function sendOnce(message) {
  if (waiting) return;
  if (send(message) !== false) waiting = true;
}

export function initTable({ onLeave, send: sendMessage }) {
  send = sendMessage;
  const menu = document.getElementById('table-menu');
  document.getElementById('btn-table-menu').addEventListener('click', () => { menu.hidden = !menu.hidden; });
  document.getElementById('btn-table-leave').addEventListener('click', () => {
    menu.hidden = true;
    const game = current?.game;
    if (game && game.phase !== 'game_over' && !confirm('Leave the table? This ends the game for everyone.')) return;
    onLeave();
  });
  document.getElementById('btn-play').addEventListener('click', () => {
    const game = current?.game;
    if (!game) return;
    if (game.phase === 'swapping') {
      if (selected.length !== 1) return toast('Pick the card to give');
      sendOnce({ type: 'action', action: { type: 'give', card: selected[0] } });
    } else {
      if (!selected.length) return toast('Pick the cards to play');
      sendOnce({ type: 'action', action: { type: 'play', cards: selected } });
    }
  });
  document.getElementById('btn-pass').addEventListener('click', () => {
    sendOnce({ type: 'action', action: { type: 'pass' } });
  });
}

/** Forget the selection and the remembered phase and round (table left or no game). */
export function resetTable() {
  selected = [];
  lastPhase = null;
  lastRound = null;
}

export function renderTable(state, meId) {
  const game = state.game;
  waiting = false;
  if (!game) {
    stopCountdown();
    resetTable();
    return;
  }
  if (game.phase !== lastPhase || game.round !== lastRound) selected = [];
  lastPhase = game.phase;
  lastRound = game.round;
  current = state;
  const byId = Object.fromEntries(state.players.map((p) => [p.id, p]));
  const names = Object.fromEntries(game.seats.map((id) => [id, '?'])); // every seat has a name
  for (const p of state.players) names[p.id] = p.name;
  const seated = game.seats.map((id) => byId[id] ?? { id, name: '?', connected: false });
  document.querySelector('.seats').replaceChildren(
    ...seatPositions(seated, meId).map(({ player, position }) => seat(player, position, game)),
  );
  const me = byId[meId];
  document.querySelector('.seat-me').replaceChildren(...(me ? [plate(me, game)] : []));
  renderScores(game, names);
  renderPile(game, names);
  renderHand(game);
  renderActions(game, meId);
  document.querySelector('.turn-note').textContent = turnNote(game, meId, names);
  renderReveal(document.querySelector('.reveal'), game, names);
  renderOverlay(document.querySelector('.overlay'), game, meId, names, sendOnce);
}

function seat(player, position, game) {
  const el = div(`seat seat-${position}`);
  const backs = div('backs');
  const count = game.counts[player.id] ?? 0;
  for (let i = 0; i < Math.min(count, MAX_BACKS); i++) backs.append(div('card-back'));
  el.append(backs, plate(player, game));
  if (game.passed.includes(player.id)) el.append(span('Pass', 'bubble'));
  return el;
}

function plate(player, game) {
  const el = div(player.connected ? 'plate' : 'plate offline');
  el.classList.toggle('turn', game.turn === player.id);
  const place = game.places.indexOf(player.id);
  el.append(div('dot'), span(player.name),
    span(place >= 0 ? placeLabel(place) : String(game.counts[player.id] ?? 0), 'count'));
  return el;
}

function scoreHead(game) {
  if (!game.target) return 'Murlan';
  return game.phase === 'game_over' ? `Game over · to ${game.target}` : `Round ${game.round} · to ${game.target}`;
}

function renderScores(game, names) {
  const head = span(scoreHead(game), 'score-head');
  const rows = game.sides.map((side) => {
    const row = div('score-row');
    row.append(span(sideName(side, names)), span(String(side.score), 'score'));
    return row;
  });
  document.querySelector('.scoreboard').replaceChildren(head, ...rows);
}

function renderPile(game, names) {
  const pile = document.querySelector('.pile');
  const top = game.pile.at(-1);
  if (!top) return pile.replaceChildren();
  const cards = div('pile-cards');
  cards.style.setProperty('--n', String(top.cards.length));
  cards.append(...top.cards.map((code) => face(code)));
  pile.replaceChildren(cards, span(names[top.player_id] ?? '', 'pile-who'));
}

function renderHand(game) {
  selected = keepHeld(selected, game.hand);
  const choices = game.swap?.choices ?? [];
  const giving = choices.length > 0;
  if (giving) selected = selected.filter((c) => choices.includes(c)).slice(0, 1);
  const hand = document.querySelector('.hand');
  hand.style.setProperty('--n', String(game.hand.length));
  hand.replaceChildren(...game.hand.map((code) => {
    const card = button('', () => pick(code), 'hand-card');
    card.setAttribute('aria-label', cardName(code));
    card.classList.toggle('selected', selected.includes(code));
    card.classList.toggle('dim', giving && !choices.includes(code));
    card.append(face(code));
    return card;
  }));
}

function pick(code) {
  const game = current.game;
  const choices = game.swap?.choices ?? [];
  if (choices.length) {
    if (!choices.includes(code)) return;
    selected = selected[0] === code ? [] : [code]; // giving: one card at a time
  } else {
    selected = toggleCard(selected, code);
  }
  renderHand(game);
}

function renderActions(game, meId) {
  const paused = Boolean(game.pause);
  const myTurn = !paused && game.phase === 'playing' && game.turn === meId;
  const giving = !paused && (game.swap?.choices.length ?? 0) > 0;
  document.querySelector('.actions').hidden = !(myTurn || giving);
  document.getElementById('btn-play').textContent = giving ? 'Give' : 'Play';
  document.getElementById('btn-pass').hidden = !myTurn || game.pile.length === 0;
}

function turnNote(game, meId, names) {
  if (game.pause) return '';
  if (game.phase === 'swapping') {
    const { giver, receiver } = game.swap;
    if (giver !== meId) return `${names[giver]} is giving ${names[receiver]} a card…`;
    const loser = game.last_round.places.at(-1);
    return giver === loser ? `Give ${names[receiver]} your highest card` : `Give ${names[receiver]} a card back`;
  }
  if (game.phase !== 'playing') return '';
  if (game.turn !== meId) return `${names[game.turn]}'s turn`;
  if (game.must_include) return `Your lead: include the ${cardName(game.must_include)}`;
  return game.pile.length ? 'Your turn: beat it or pass' : 'Your lead';
}
