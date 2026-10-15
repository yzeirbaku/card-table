import { flyIn, playDeal, stopDeal } from './deal.js';
import { button, div, face, span } from './dom.js';
import { cardName, keepHeld, placeLabel, sideName, toggleCard } from './murlan.js';
import { seatPositions } from './seats.js';
import { crowned, gains, renderSpotlight, resetSpotlight, spotlightOn, updateSpotlight } from './spotlight.js';
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
let lastPassed = []; // the passes (pile + player) at the last render, so only a new Pass pops in

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
  const ask = document.getElementById('leave-confirm');
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    menu.hidden = true;
    if (ask.hidden) return;
    showLeaveConfirm(false);
    menuButton.focus();
  });
  document.getElementById('btn-table-leave').addEventListener('click', () => {
    menu.hidden = true;
    const game = current?.game;
    if (!game || game.phase === 'game_over') return onLeave(); // nothing to end
    showLeaveConfirm(true);
    document.getElementById('btn-leave-stay').focus();
  });
  document.getElementById('btn-leave-stay').addEventListener('click', () => {
    showLeaveConfirm(false);
    menuButton.focus();
  });
  document.getElementById('btn-leave-go').addEventListener('click', () => {
    showLeaveConfirm(false);
    onLeave();
  });
  ask.addEventListener('click', (event) => { // tap outside: stay
    if (event.target !== ask) return;
    showLeaveConfirm(false);
    menuButton.focus();
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

/** The leave popup; while it's up, the rest of the table can't be tabbed to or tapped. */
function showLeaveConfirm(open) {
  const ask = document.getElementById('leave-confirm');
  ask.hidden = !open;
  for (const el of document.querySelector('.table').children) if (el !== ask) el.inert = open;
}

/** Forget the selection and the remembered phase and round (table left or no game). */
export function resetTable() {
  selected = [];
  lastPhase = null;
  lastRound = null;
  hadEmptyHand = null;
  lastPlay = undefined;
  lastPassed = [];
  resetSpotlight();
  showLeaveConfirm(false);
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
  if (game.phase === 'game_over' && !document.getElementById('leave-confirm').hidden) { // leaving no longer ends anything
    showLeaveConfirm(false);
    document.getElementById('btn-table-menu').focus();
  }
  if (game.phase !== lastPhase || game.round !== lastRound) selected = [];
  lastPhase = game.phase;
  lastRound = game.round;
  current = state;
  currentMe = meId;
  const byId = Object.fromEntries(state.players.map((p) => [p.id, p]));
  const names = Object.fromEntries(game.seats.map((id) => [id, '?'])); // every seat has a name
  for (const p of state.players) names[p.id] = p.name;
  updateSpotlight(game, names, () => { if (current) renderTable(current, currentMe); });
  const seated = game.seats.map((id) => byId[id] ?? { id, name: '?', connected: false });
  // A pass is new if this player hadn't passed on this pile; nothing pops on the first render.
  const passes = game.passed.map((id) => `${pileKey(game)}|${id}`);
  const newPasses = lastPlay === undefined ? [] : game.passed.filter((id, i) => !lastPassed.includes(passes[i]));
  lastPassed = passes;
  const seatEls = new Map(); // player id -> their seat, where their plays come from
  document.querySelector('.seats').replaceChildren(...seatPositions(seated, meId).map(({ player, position }) => {
    const el = seat(player, position, game, newPasses);
    seatEls.set(player.id, el);
    return el;
  }));
  seatEls.set(meId, document.querySelector('.hand')); // yours come from your hand
  const me = byId[meId];
  document.querySelector('.seat-me').replaceChildren(...(me ? [plate(me, game)] : []));
  document.querySelector('.seat-me').classList.toggle('spot-winner', crowned(meId));
  if (me && game.passed.includes(meId)) document.querySelector('.seat-me').append(passStamp(newPasses.includes(meId)));
  renderScores(game, names);
  const dealt = hadEmptyHand === true && game.hand.length > 0; // seen empty, now full: a new deal
  hadEmptyHand = game.hand.length === 0;
  renderPile(game, names, seatEls);
  renderHand(game);
  renderActions(game, meId);
  document.querySelector('.turn-note').textContent = turnNote(game, meId, names);
  renderReveal(document.querySelector('.reveal'), game, names);
  const overlay = document.querySelector('.overlay');
  if (spotlightOn()) overlay.hidden = true; // what comes next waits for the spotlight
  else renderOverlay(overlay, game, meId, names, sendOnce);
  renderSpotlight(() => { if (current) renderTable(current, currentMe); });
  if (dealt) playDeal(seatPositions(seated, meId).map(({ position }) => position), game.hand.length);
}

/** A PASS stamp across a player's cards (above your name for you); it lands when the pass is new. */
function passStamp(fresh) {
  return span('PASS', fresh ? 'stamp landing' : 'stamp');
}

function seat(player, position, game, newPasses) {
  const el = div(`seat seat-${position}`);
  const backs = div('backs');
  const holding = ['swapping', 'playing'].includes(game.phase) && !game.places.includes(player.id);
  if (holding) for (let i = 0; i < FAN; i++) backs.append(div('card-back'));
  el.append(backs, plate(player, game));
  el.classList.toggle('spot-winner', crowned(player.id));
  if (game.passed.includes(player.id)) {
    el.classList.add('passed'); // their cards grey out under the stamp
    backs.append(passStamp(newPasses.includes(player.id)));
  }
  return el;
}

function plate(player, game) {
  const el = div(player.connected ? 'plate' : 'plate offline');
  el.classList.toggle('turn', game.turn === player.id);
  const place = game.places.indexOf(player.id);
  el.append(div('dot'), span(player.name));
  if (crowned(player.id)) el.append(span('♛', 'crown'));
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
    const won = gains(game)?.[i];
    if (won) { // the points this round just added, rising under the score
      const gain = document.createElement('i');
      gain.className = 'gain';
      gain.textContent = `+${won}`;
      score.append(gain);
    }
    const name = document.createTextNode(sideName(side, names));
    if (i > 0) parts.push(document.createTextNode(' · '));
    parts.push(...(two && i === 1 ? [score, name] : [name, score]));
  });
  document.querySelector('.scoreboard').replaceChildren(...parts);
  document.querySelector('.score-round').textContent = roundLabel(game);
}

/** Names the newest play on the pile (null: empty), to tell a new play from a redraw. */
function pileKey(game) {
  const top = game.pile.at(-1);
  return top ? `${game.round}:${game.pile.length}:${top.player_id}:${top.cards.join()}` : null;
}

/** The trick so far as a messy stack: each play a little turned on the one before, the newest on top. */
function renderPile(game, names, seatEls) {
  const pile = document.querySelector('.pile');
  const top = game.pile.at(-1);
  const key = pileKey(game);
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
    cards.style.setProperty('--rot', `${play.cards.length >= 5 ? rot / 3 : rot}deg`); // long plays lie flatter
    cards.append(...play.cards.map((code) => face(code)));
    return cards;
  });
  const landed = key !== lastPlay && lastPlay !== undefined;
  lastPlay = key;
  pile.replaceChildren(...plays, span(names[top.player_id] ?? '', 'pile-who'));
  if (landed) flyIn(plays.at(-1), seatEls.get(top.player_id)); // slides in from whoever played it
}

/** Your cards are in play on your turn, or when you have a card to give in the swap. */
function yourMove(game, meId) {
  return (game.phase === 'playing' && game.turn === meId) || (game.swap?.choices.length ?? 0) > 0;
}

function renderHand(game) {
  selected = keepHeld(selected, game.hand);
  const choices = game.swap?.choices ?? [];
  const giving = choices.length > 0;
  if (giving) selected = selected.filter((c) => choices.includes(c)).slice(0, 1);
  const mine = yourMove(game, currentMe);
  if (!mine) selected = []; // a pause keeps what you picked; it only stops new taps
  const locked = !mine || Boolean(game.pause);
  const hand = document.querySelector('.hand');
  hand.classList.toggle('locked', locked);
  hand.style.setProperty('--n', String(game.hand.length));
  hand.replaceChildren(...game.hand.map((code) => {
    const card = button('', () => pick(code), 'hand-card');
    card.setAttribute('aria-label', cardName(code));
    if (locked) card.setAttribute('aria-disabled', 'true');
    card.classList.toggle('selected', selected.includes(code));
    card.classList.toggle('dim', giving && !choices.includes(code));
    card.append(face(code));
    return card;
  }));
}

function pick(code) {
  const game = current.game;
  if (!yourMove(game, currentMe) || game.pause) return; // not your turn: cards stay put
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
