import { playDeal, stopDeal } from './deal.js';
import { button, div, face, span } from './dom.js';
import { cardName, keepHeld, placeLabel, sideName, toggleCard } from './murlan.js';
import { seatPositions } from './seats.js';
import { renderOverlay, renderReveal, stopCountdown } from './table-overlay.js';
import { toast } from './ui.js';

const FAN = 5; // card backs drawn per opponent: how many they really hold isn't shown
// How each play in a trick lies on the pile (offset x, offset y in px, turn in degrees), by its place in the trick.
const LIE = [[-3, 2, -7], [4, -2, 6], [-2, -3, -2], [3, 3, 9], [-4, 1, -4], [2, -2, 3], [-1, 3, -9], [4, 0, 4]];
const PILE_SHOWN = 4; // older plays are buried under these

let send = () => {};
let selected = []; // card codes picked in your hand
let current = null; // the last state drawn, to redraw the hand after a tap
let currentMe = null; // your player id in that state
let lastPhase = null; // the phase of the last render: a new phase starts with nothing selected
let lastRound = null; // the round of the last render: a new round starts with nothing selected
let waiting = false; // a move is out: ignore taps until the next state arrives
let hadEmptyHand = null; // whether the last render had no cards in your hand: cards arriving after that are a deal
let lastPlay; // the newest play on the pile at the last render (null: empty), so only a new one lands

/** Send a move once; further taps are ignored until the server answers with a state. */
function sendOnce(message) {
  if (waiting) return;
  if (send(message) !== false) waiting = true;
}

export function initTable({ onLeave, send: sendMessage }) {
  send = sendMessage;
  const menu = document.getElementById('table-menu');
  const menuButton = document.getElementById('btn-table-menu');
  menuButton.addEventListener('click', () => { menu.hidden = !menu.hidden; });
  document.addEventListener('pointerdown', (event) => { // a tap anywhere else closes the menu
    if (!menu.hidden && !menu.contains(event.target) && !menuButton.contains(event.target)) menu.hidden = true;
  });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') menu.hidden = true; });
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
  hadEmptyHand = null;
  lastPlay = undefined;
  stopDeal();
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
  currentMe = meId;
  const byId = Object.fromEntries(state.players.map((p) => [p.id, p]));
  const names = Object.fromEntries(game.seats.map((id) => [id, '?'])); // every seat has a name
  for (const p of state.players) names[p.id] = p.name;
  const seated = game.seats.map((id) => byId[id] ?? { id, name: '?', connected: false });
  document.querySelector('.seats').replaceChildren(
    ...seatPositions(seated, meId).map(({ player, position }) => seat(player, position, game)),
  );
  const me = byId[meId];
  document.querySelector('.seat-me').replaceChildren(...(me ? [plate(me, game)] : []));
  if (me && game.passed.includes(meId)) document.querySelector('.seat-me').append(span('Pass', 'bubble'));
  renderScores(game, names);
  const dealt = hadEmptyHand === true && game.hand.length > 0; // seen empty, now full: a new deal
  hadEmptyHand = game.hand.length === 0;
  renderPile(game, names);
  renderHand(game);
  renderActions(game, meId);
  document.querySelector('.turn-note').textContent = turnNote(game, meId, names);
  renderReveal(document.querySelector('.reveal'), game, names);
  renderOverlay(document.querySelector('.overlay'), game, meId, names, sendOnce);
  if (dealt) playDeal(seatPositions(seated, meId).map(({ position }) => position), game.hand.length);
}

function seat(player, position, game) {
  const el = div(`seat seat-${position}`);
  const backs = div('backs');
  const holding = ['swapping', 'playing'].includes(game.phase) && !game.places.includes(player.id);
  if (holding) for (let i = 0; i < FAN; i++) backs.append(div('card-back'));
  el.append(backs, plate(player, game));
  if (game.passed.includes(player.id)) el.append(span('Pass', 'bubble'));
  return el;
}

function plate(player, game) {
  const el = div(player.connected ? 'plate' : 'plate offline');
  el.classList.toggle('turn', game.turn === player.id);
  const place = game.places.indexOf(player.id);
  el.append(div('dot'), span(player.name));
  if (place >= 0) el.append(span(placeLabel(place), 'count'));
  return el;
}

function roundLabel(game) {
  if (!game.target) return 'Murlan';
  return game.phase === 'game_over' ? `Game over · Race to ${game.target}` : `Round ${game.round} · Race to ${game.target}`;
}

/** "Ana & Cleo 7 · 4 Ben & Dan" for two sides (scores in the middle), "Ana 7 · Ben 4 · Cleo 2" for more. */
function renderScores(game, names) {
  const parts = [];
  const two = game.sides.length === 2;
  game.sides.forEach((side, i) => {
    const score = document.createElement('b');
    score.textContent = String(side.score);
    const name = document.createTextNode(sideName(side, names));
    if (i > 0) parts.push(document.createTextNode(' · '));
    parts.push(...(two && i === 1 ? [score, name] : [name, score]));
  });
  document.querySelector('.scoreboard').replaceChildren(...parts);
  document.querySelector('.score-round').textContent = roundLabel(game);
}

/** The trick so far as a messy stack: each play a little turned on the one before, the newest on top. */
function renderPile(game, names) {
  const pile = document.querySelector('.pile');
  const top = game.pile.at(-1);
  const key = top ? `${game.round}:${game.pile.length}:${top.player_id}:${top.cards.join()}` : null;
  if (!top) {
    lastPlay = key;
    return pile.replaceChildren();
  }
  const start = Math.max(0, game.pile.length - PILE_SHOWN);
  const plays = game.pile.slice(start).map((play, j) => {
    const i = start + j; // where this play is in the trick, so it keeps the same lie as more land on it
    const [dx, dy, rot] = LIE[i % LIE.length];
    const cards = div(play === top && !game.pile_won ? 'pile-cards' : 'pile-cards under'); // a won trick is all dimmed
    cards.style.setProperty('--n', String(play.cards.length));
    cards.style.setProperty('--dx', `${dx}px`);
    cards.style.setProperty('--dy', `${dy}px`);
    cards.style.setProperty('--rot', `${rot}deg`);
    cards.append(...play.cards.map((code) => face(code)));
    return cards;
  });
  if (key !== lastPlay && lastPlay !== undefined) plays.at(-1).classList.add('landing');
  lastPlay = key;
  pile.replaceChildren(...plays, span(names[top.player_id] ?? '', 'pile-who'));
}

/** Cards can be picked on your turn, or when you have a card to give in the swap. */
function canPick(game, meId) {
  if (game.pause) return false;
  return (game.phase === 'playing' && game.turn === meId) || (game.swap?.choices.length ?? 0) > 0;
}

function renderHand(game) {
  selected = keepHeld(selected, game.hand);
  const choices = game.swap?.choices ?? [];
  const giving = choices.length > 0;
  if (giving) selected = selected.filter((c) => choices.includes(c)).slice(0, 1);
  const open = canPick(game, currentMe);
  if (!open) selected = [];
  const hand = document.querySelector('.hand');
  hand.classList.toggle('locked', !open);
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
  if (!canPick(game, currentMe)) return; // not your turn: cards stay put
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
  const play = document.getElementById('btn-play');
  play.hidden = !(myTurn || giving);
  play.textContent = giving ? 'Give' : 'Play';
  document.getElementById('btn-pass').hidden = !myTurn || leading(game);
}

/** Nothing to beat: the pile is empty, or it's a won trick left on show until this lead. */
function leading(game) {
  return game.pile.length === 0 || game.pile_won;
}

function turnNote(game, meId, names) {
  if (game.pause) return '';
  if (game.phase === 'swapping') {
    const { giver, receiver } = game.swap;
    if (giver !== meId) return `${names[giver]} is giving ${names[receiver]} a card…`;
    const loser = game.last_round.places.at(-1);
    return giver === loser ? `Give ${names[receiver]} your highest card` : `Give ${names[receiver]} a card back`;
  }
  if (game.phase === 'playing' && game.turn === meId && game.must_include) return `Include the ${cardName(game.must_include)}`;
  return ''; // whose turn it is shows on the players' names
}
