import { flyIn, playDeal, stopDeal } from './deal.js';
import { cancelDrag, dragGroup, initDrag, justDropped, settleDropped } from './drag.js';
import { button, div, face, span } from './dom.js';
import { bombName, brokenBomb, cardName, keepHeld, placeLabel, sideName, toggleCard } from './murlan.js';
import { seatPositions } from './seats.js';
import { crowned, finalPile, finalThrown, gains, renderSpotlight, resetSpotlight, spotlightOn, updateSpotlight } from './spotlight.js';
import { addReaction, REACTIONS, reactionEl, resetReactions, stampCatan } from './reactions.js';
import { fillRules } from './rules.js';
import { noteThrows, renderThrown, resetThrows } from './throw.js';
import { renderOverlay, renderReveal, stopCountdown } from './table-overlay.js';
import { toast } from './ui.js';

const FAN = 5; // card backs drawn per opponent: how many they really hold isn't shown
// How each play in a trick lies on the pile (offset x, offset y in px, turn in degrees), by its place in the trick.
const LIE = [[-3, 2, -7], [4, -2, 6], [-2, -3, -2], [3, 3, 9], [-4, 1, -4], [2, -2, 3], [-1, 3, -9], [4, 0, 4]];
const PILE_SHOWN = 4; // older plays are buried under these
const RECEIVED_MS = 3600; // a card given to you in the swap stands up this long (the CSS animation's length)
const OUT_MS = 2600; // "Ana is out · 1st" shows this long (the CSS animation's length)
const SHAKE_MS = 520; // a bomb landing shakes the table this long (the CSS animation's length)
const CATAN_LANDS_MS = 380; // the 💩 stamp: its last letter lands and the table jumps
const LUCKY_MS = 4000; // "Four 2s. Act natural." shows this long (the CSS animation's length)

let send = () => {};
let selected = []; // card codes picked in your hand
let lastHand = []; // your cards at the last render, to spot the one you were just given
let received = null; // { code, at } the card given to you in the swap, while it stands up
let seenOut = null; // { round, places } who was out at the last render, to spot someone going out
let outNote = null; // { id, place, at } someone just went out and play goes on, while that shows
let current = null; // the last state drawn, to redraw the hand after a tap
let currentMe = null; // your player id in that state
let lastPhase = null; // the phase of the last render: a new phase starts with nothing selected
let lastRound = null; // the round of the last render: a new round starts with nothing selected
let waiting = false; // a move is out: ignore taps until the game changes, the server says no, or a few seconds pass
let waitingOn = null; // the game as it was when the move went out
let waitTimer = null;
const WAIT_MS = 4000; // a move lost on a dropped connection doesn't lock you out
let hadEmptyHand = null; // whether the last render had no cards in your hand: cards arriving after that are a deal
let lastPlay; // the newest play on the pile at the last render (null: empty), so only a new one lands
let lastPassed = []; // the passes (pile + player) at the last render, so only a new Pass pops in
let picking = false; // the reaction picker over your name is open
let pickedFrom = '.plate'; // what opened it, your name or the react button: where the keyboard goes back to

/** Draw the last state again (the spotlight ending); a move that's still out stays out. */
function redraw() {
  if (current) renderTable(current, currentMe);
}

function stopWaiting() {
  waiting = false;
  waitingOn = null;
  clearTimeout(waitTimer);
}

/** Send a move once; further taps are ignored until it's answered (another player's news doesn't count). */
function sendOnce(message) {
  if (waiting) return;
  if (send(message) === false) return;
  waiting = true;
  waitingOn = JSON.stringify(current?.game ?? null);
  clearTimeout(waitTimer);
  waitTimer = setTimeout(() => {
    stopWaiting();
    settleDropped();
  }, WAIT_MS);
}

/** Play (or give) the cards picked: Play, or a drop on the pile. */
function playSelected() {
  const game = current?.game;
  if (!game) return;
  if (game.phase === 'swapping') {
    if (selected.length !== 1) return toast('Pick the card to give');
    sendOnce({ type: 'action', action: { type: 'give', card: selected[0] } });
  } else {
    if (game.can_play === false) return; // (an older server doesn't say)
    if (!selected.length) return toast('Pick the cards to play');
    const bomb = brokenBomb(selected, game.bombs);
    if (bomb) return askAboutBomb(bomb);
    sendOnce({ type: 'action', action: { type: 'play', cards: selected } });
  }
}

/** The cards picked use some of a bomb but not all of it: make sure that's meant. */
function askAboutBomb(bomb) {
  document.getElementById('bomb-text').textContent = `You hold ${bombName(bomb)}. Play these cards anyway?`;
  showModal(document.getElementById('bomb-confirm'), true);
  document.getElementById('btn-bomb-keep').focus();
}

/** A card in your hand starts moving: the cards that go with it, now picked (null: they can't move now). */
function dragStart(code) {
  const game = current?.game;
  if (!game || waiting || !yourMove(game, currentMe) || game.pause) return null;
  if (game.phase === 'playing' && game.can_play === false) return null; // nothing you hold can go down
  const group = dragGroup(selected, code, game.swap?.choices ?? []);
  if (!group) return null;
  selected = group;
  for (const el of document.querySelectorAll('.hand .hand-card')) el.classList.toggle('selected', selected.includes(el.dataset.code)); // in place: a redraw would drop the drag
  renderActions(game, currentMe);
  return group;
}

/** Someone at the table reacted (yours too, as it comes back from the server). */
export function reacted(playerId, kind) {
  if (!current) return;
  if (kind !== 'catan') return addReaction(playerId, kind, paintReaction);
  const name = current.players.find((p) => p.id === playerId)?.name;
  stampCatan(playerId === currentMe ? 'You have' : `${name ?? 'Someone'} has`);
  clearTimeout(reacted.shake);
  reacted.shake = setTimeout(() => { if (current) shakeTable(); }, CATAN_LANDS_MS); // as the N lands
}

/** Put a player's reaction (or none) on their plate in place: a full redraw would swallow taps on the cards. */
function paintReaction(playerId) {
  for (const el of document.querySelectorAll('.table .plate')) {
    if (el.dataset.player !== playerId) continue;
    el.querySelector('.reaction')?.remove();
    const reaction = reactionEl(playerId);
    if (reaction) el.append(reaction);
  }
}

/** Open or close the picker over your name in place, for the same reason. */
function setPicking(open) {
  if (picking === open) return;
  picking = open;
  const seatMe = document.querySelector('.seat-me');
  seatMe.querySelector('.react-picker')?.remove();
  for (const el of seatMe.querySelectorAll('.plate, .react-btn')) el.setAttribute('aria-expanded', String(open));
  if (open) seatMe.append(reactionPicker());
}

/** The server turned a move down: taps work again. */
export function moveRejected() {
  stopWaiting();
  settleDropped();
}

export function initTable({ onLeave, send: sendMessage }) {
  send = sendMessage;
  const menu = document.getElementById('table-menu');
  const menuButton = document.getElementById('btn-table-menu');
  menuButton.addEventListener('click', () => { menu.hidden = !menu.hidden; });
  const seatMe = document.querySelector('.seat-me');
  document.addEventListener('pointerdown', (event) => { // a tap anywhere else closes the menu and the picker
    if (!menu.hidden && !menu.contains(event.target) && !menuButton.contains(event.target)) menu.hidden = true;
    if (picking && !seatMe.contains(event.target)) setPicking(false);
  });
  seatMe.addEventListener('click', (event) => { // tap your name, or the react button beside it, to react
    const choice = event.target.closest('[data-reaction]');
    const opener = event.target.closest('.plate, .react-btn');
    if (choice) {
      send({ type: 'react', reaction: choice.dataset.reaction });
      setPicking(false);
      if (event.detail === 0) seatMe.querySelector(pickedFrom)?.focus(); // from the keyboard: back to what opened it
    } else if (opener) {
      pickedFrom = opener.matches('.react-btn') ? '.react-btn' : '.plate';
      setPicking(!picking);
      if (event.detail === 0) seatMe.querySelector('[data-reaction]')?.focus();
    }
  });
  seatMe.addEventListener('keydown', (event) => {
    if (!['Enter', ' '].includes(event.key) || !event.target.matches('.plate')) return;
    event.preventDefault();
    event.target.click();
  });
  const ask = document.getElementById('leave-confirm');
  const rules = document.getElementById('rules-dialog');
  const closeRules = () => {
    showModal(rules, false);
    menuButton.focus();
  };
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    menu.hidden = true;
    if (picking) {
      setPicking(false);
      if (seatMe.contains(document.activeElement)) seatMe.querySelector(pickedFrom)?.focus();
    }
    if (!rules.hidden) return closeRules();
    if (ask.hidden) return;
    showLeaveConfirm(false);
    menuButton.focus();
  });
  initFullscreen(menu);
  document.getElementById('btn-table-rules').addEventListener('click', () => {
    menu.hidden = true;
    fillRules(rules.querySelector('.rules-body'), current?.room?.game);
    showModal(rules, true);
    document.getElementById('btn-rules-close').focus();
  });
  document.getElementById('btn-rules-close').addEventListener('click', closeRules);
  rules.addEventListener('click', (event) => { if (event.target === rules) closeRules(); }); // tap outside
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
  document.getElementById('btn-play').addEventListener('click', playSelected);
  initDrag(document.querySelector('.hand'), document.querySelector('.play-area'), {
    start: dragStart,
    drop: () => {
      playSelected();
      if (!waiting) settleDropped(); // it never went out
    },
  });
  document.getElementById('btn-pass').addEventListener('click', () => {
    sendOnce({ type: 'action', action: { type: 'pass' } });
  });
  document.getElementById('btn-clear').addEventListener('click', () => { // changed your mind: nothing picked
    selected = [];
    renderHand(current.game);
    renderActions(current.game, currentMe);
  });
  const giveUp = document.getElementById('giveup-confirm');
  const stay = () => {
    showModal(giveUp, false);
    document.getElementById('btn-giveup').focus();
  };
  document.getElementById('btn-giveup').addEventListener('click', () => {
    if (!current?.game) return;
    giveUpText(current);
    showModal(giveUp, true);
    document.getElementById('btn-giveup-stay').focus();
  });
  document.getElementById('btn-giveup-stay').addEventListener('click', stay);
  document.getElementById('btn-giveup-go').addEventListener('click', () => {
    showModal(giveUp, false);
    send({ type: 'action', action: { type: 'give_up' } }); // not held back by a move still out: you meant it
  });
  giveUp.addEventListener('click', (event) => { if (event.target === giveUp) stay(); }); // tap outside: keep playing
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !giveUp.hidden) stay(); });
  const bombAsk = document.getElementById('bomb-confirm');
  const keep = () => {
    showModal(bombAsk, false);
    document.getElementById('btn-play').focus();
  };
  document.getElementById('btn-bomb-keep').addEventListener('click', keep);
  document.getElementById('btn-bomb-play').addEventListener('click', () => {
    showModal(bombAsk, false);
    if (current?.game?.phase === 'playing') sendOnce({ type: 'action', action: { type: 'play', cards: selected } });
  });
  bombAsk.addEventListener('click', (event) => { if (event.target === bombAsk) keep(); }); // tap outside: keep it
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !bombAsk.hidden) keep(); });
}

/** What giving up would mean right now, in the popup (kept up to date while it's open). */
function giveUpText(state) {
  const game = state.game;
  const thrown = game.thrown ?? {};
  const stillIn = game.seats.filter((id) => id !== currentMe && !game.places.includes(id) && !(id in thrown));
  const name = (id) => state.players.find((p) => p.id === id)?.name ?? 'The other player';
  let text = Object.keys(thrown).length ? 'You finish behind everyone still playing. The others play on.' : 'You take last place. The others play on.';
  if (stillIn.length === 1) text = game.seats.length === 2 ? `${name(stillIn[0])} wins the round.` : `The round ends here, with ${name(stillIn[0])} ahead of you.`;
  document.getElementById('giveup-text').textContent = text;
}

/** In a browser tab that allows it, ☰ → Full screen hides the address bar. The installed app is full screen already. */
function initFullscreen(menu) {
  const button = document.getElementById('btn-fullscreen');
  const installed = matchMedia('(display-mode: fullscreen), (display-mode: standalone)').matches;
  button.hidden = installed || !document.fullscreenEnabled;
  button.addEventListener('click', () => {
    menu.hidden = true;
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else document.documentElement.requestFullscreen({ navigationUI: 'hide' }).catch(() => toast('Full screen isn’t available here'));
  });
  document.addEventListener('fullscreenchange', () => {
    button.textContent = document.fullscreenElement ? 'Exit full screen' : 'Full screen';
  });
}

/** A popup on the table; while one is up, the rest of the table can't be tabbed to or tapped. */
function showModal(dialog, open) {
  dialog.hidden = !open;
  const up = document.querySelector('.table > .confirm:not([hidden])');
  for (const el of document.querySelector('.table').children) el.inert = up !== null && el !== up;
}

function showLeaveConfirm(open) {
  const others = current?.players?.some((p) => p.id !== currentMe && !p.computer && p.seat !== null);
  document.getElementById('leave-text').textContent = others ? 'This ends the game for everyone.' : 'This ends the game.';
  showModal(document.getElementById('leave-confirm'), open);
}

/** Someone left: say who, and that the game is over, before going back to the lobby (`onDone`). */
export function showEnded(name, onDone) {
  const over = current?.game?.phase === 'game_over';
  const notice = document.getElementById('ended-notice');
  stopDeal();
  resetSpotlight(); // its timer would redraw the old game behind the popup
  resetReactions();
  showLeaveConfirm(false);
  showModal(document.getElementById('rules-dialog'), false);
  showModal(document.getElementById('giveup-confirm'), false);
  showModal(document.getElementById('bomb-confirm'), false);
  document.getElementById('table-menu').hidden = true;
  document.getElementById('ended-title').textContent = `${name} left the table`;
  document.getElementById('ended-text').textContent = over ? 'Everyone goes back to the lobby.' : 'The game has ended. Everyone goes back to the lobby.';
  showModal(notice, true);
  const ok = document.getElementById('btn-ended-ok');
  ok.onclick = () => {
    showModal(notice, false);
    onDone();
  };
  ok.focus();
}

/** Forget the selection and the remembered phase and round (table left or no game). */
export function resetTable() {
  selected = [];
  lastHand = [];
  received = null;
  seenOut = null;
  outNote = null;
  lastPhase = null;
  lastRound = null;
  hadEmptyHand = null;
  lastPlay = undefined;
  lastPassed = [];
  picking = false;
  resetReactions();
  resetSpotlight();
  stopWaiting();
  showLeaveConfirm(false);
  showModal(document.getElementById('rules-dialog'), false);
  showModal(document.getElementById('giveup-confirm'), false);
  showModal(document.getElementById('bomb-confirm'), false);
  showModal(document.getElementById('ended-notice'), false);
  resetThrows();
  stopDeal();
  document.querySelector('.lucky').hidden = true;
}

export function renderTable(state, meId) {
  const game = state.game;
  if (!game || JSON.stringify(game) !== waitingOn) stopWaiting();
  if (!game) {
    stopCountdown();
    resetTable();
    return;
  }
  if (game.phase === 'game_over' && !document.getElementById('leave-confirm').hidden) { // leaving no longer ends anything
    showLeaveConfirm(false);
    document.getElementById('btn-table-menu').focus();
  }
  const canGiveUp = game.phase === 'playing' && !game.pause && game.turn === meId && game.hand.length > 0; // only on your turn
  if (!document.getElementById('giveup-confirm').hidden) {
    if (canGiveUp) giveUpText(state); // someone went out or gave up meanwhile
    else showModal(document.getElementById('giveup-confirm'), false); // too late now
  }
  if (game.phase !== lastPhase || game.round !== lastRound) selected = [];
  lastPhase = game.phase;
  lastRound = game.round;
  current = state;
  currentMe = meId;
  const byId = Object.fromEntries(state.players.map((p) => [p.id, p]));
  const names = Object.fromEntries(game.seats.map((id) => [id, '?'])); // every seat has a name
  for (const p of state.players) names[p.id] = p.name;
  updateSpotlight(game, names, redraw);
  noteGoingOut(game);
  const seated = game.seats.map((id) => byId[id] ?? { id, name: '?', connected: false });
  // A pass is new if this player hadn't passed on this pile; nothing pops on the first render.
  const passes = game.passed.map((id) => `${pileKey(game)}|${id}`);
  const newPasses = lastPlay === undefined ? [] : game.passed.filter((id, i) => !lastPassed.includes(passes[i]));
  lastPassed = passes;
  const seatEls = new Map(); // player id -> their seat, where their plays come from
  const final = finalPile(); // the round just ended: its last cards (and who went out) stay a while
  // While they do, the medals of those who went out stay too, until the next round is dealt.
  const dealing = ['swapping', 'playing'].includes(game.phase);
  const endThrown = finalThrown(); // a hand thrown in that round stays where it landed too
  const seen = (final || endThrown) && !dealing
    ? { ...game, places: game.last_round.places.slice(0, game.last_round.out), thrown: endThrown ?? {} }
    : { ...game, thrown: game.thrown ?? {} };
  noteThrows(seen.thrown, meId); // before the hand and seats are redrawn: a new throw flies from there
  renderThrown(seen.thrown);
  document.querySelector('.seats').replaceChildren(...seatPositions(seated, meId).map(({ player, position }) => {
    const el = seat(player, position, seen, newPasses);
    seatEls.set(player.id, el);
    return el;
  }));
  seatEls.set(meId, document.querySelector('.hand')); // yours come from your hand
  const me = byId[meId];
  const seatMe = document.querySelector('.seat-me');
  const active = seatMe.contains(document.activeElement) ? document.activeElement : null;
  const focused = active && (active.dataset.reaction ? `[data-reaction="${active.dataset.reaction}"]` : active.matches('.react-btn') ? '.react-btn' : '.plate');
  seatMe.replaceChildren(...(me ? myPlate(me, seen) : []));
  if (focused) seatMe.querySelector(focused)?.focus(); // keyboard focus survives the redraw
  document.querySelector('.my-row').classList.toggle('spot-winner', crowned(meId));
  if (me && game.passed.includes(meId)) document.querySelector('.seat-me').append(passStamp(newPasses.includes(meId)));
  if (me && meId in seen.thrown) document.querySelector('.seat-me').append(span('Gave up', 'gave-up-tag'));
  renderScores(game, names);
  const dealt = hadEmptyHand === true && game.hand.length > 0; // seen empty, now full: a new deal
  hadEmptyHand = game.hand.length === 0;
  renderPile(final ? { ...game, pile: final, pile_won: false, round: game.round - 1 } : game, names, seatEls); // its own round: no second landing
  renderHand(game);
  renderActions(game, meId);
  document.querySelector('.turn-note').textContent = turnNote(game, meId, names);
  renderReveal(document.querySelector('.reveal'), game, names);
  renderOutNote(names, meId);
  const overlay = document.querySelector('.overlay');
  if (spotlightOn()) overlay.hidden = true; // what comes next waits for the spotlight
  else renderOverlay(overlay, game, meId, names, sendOnce);
  renderSpotlight(redraw);
  if (dealt) {
    playDeal(seatPositions(seated, meId).map(({ position }) => position), game.hand.length)
      .then(() => { if (game.lucky) showLucky(game.round); });
  }
}

/** Dealt all four 2s: a word for you alone, once the cards are in your hand. */
function showLucky(round) {
  if (current?.game?.round !== round) return;
  const el = document.querySelector('.lucky');
  el.hidden = false;
  clearTimeout(showLucky.timer);
  showLucky.timer = setTimeout(() => { el.hidden = true; }, LUCKY_MS);
}

/** A bomb landed: the table jumps. */
function shakeTable() {
  const table = document.querySelector('.table');
  table.classList.remove('shake');
  void table.offsetWidth; // restart the animation when bombs land back to back
  table.classList.add('shake');
  clearTimeout(shakeTable.timer);
  shakeTable.timer = setTimeout(() => table.classList.remove('shake'), SHAKE_MS);
}

/** A PASS stamp across a player's cards (above your name for you); it lands when the pass is new. */
function passStamp(fresh) {
  return span('PASS', fresh ? 'stamp landing' : 'stamp');
}

function seat(player, position, game, newPasses) {
  const el = div(`seat seat-${position}`);
  const backs = div('backs');
  const gaveUp = player.id in game.thrown;
  const holding = ['swapping', 'playing'].includes(game.phase) && !game.places.includes(player.id) && !gaveUp;
  if (holding) for (let i = 0; i < FAN; i++) backs.append(div('card-back'));
  const place = game.places.indexOf(player.id);
  if (place >= 0) { // out: a medal where their cards were, all round
    backs.append(span(placeLabel(place), 'medal'));
    el.classList.add('out');
  }
  if (gaveUp) {
    backs.append(span('Gave up', 'gave-up-tag'));
    el.classList.add('out');
  }
  el.append(backs, plate(player, game, place < 0));
  el.classList.toggle('spot-winner', crowned(player.id));
  if (game.passed.includes(player.id)) {
    el.classList.add('passed'); // their cards grey out under the stamp
    backs.append(passStamp(newPasses.includes(player.id)));
  }
  return el;
}

/** A player's name plate; `showPlace`: their finishing place after the name (not when a medal shows it). */
function plate(player, game, showPlace = true) {
  const el = div(player.connected ? 'plate' : 'plate offline');
  el.classList.toggle('turn', game.turn === player.id);
  const place = game.places.indexOf(player.id);
  el.dataset.player = player.id;
  el.append(div('dot'));
  if (player.computer) el.append(span('🤖', 'bot-mark')); // everyone can tell a computer player
  el.append(span(player.name, 'name'));
  if (crowned(player.id)) el.append(span('♛', 'crown'));
  if (place >= 0 && showPlace) el.append(span(placeLabel(place), 'count'));
  const reaction = reactionEl(player.id);
  if (reaction) el.append(reaction);
  return el;
}

/** Your plate and the react button beside it, either of which you tap for the reaction picker, and the picker while it's open. */
function myPlate(me, game) {
  const el = plate(me, game);
  el.classList.add('mine');
  el.tabIndex = 0;
  el.setAttribute('role', 'button');
  el.setAttribute('aria-label', `${me.name}: react`);
  el.setAttribute('aria-expanded', String(picking));
  const react = button('😊', () => {}, 'react-btn');
  react.setAttribute('aria-label', 'React');
  react.setAttribute('aria-expanded', String(picking));
  return picking ? [el, react, reactionPicker()] : [el, react];
}

function reactionPicker() {
  const picker = div('react-picker');
  for (const [kind, emoji] of REACTIONS) {
    const choice = button(emoji, () => {}, 'react-choice');
    choice.dataset.reaction = kind;
    choice.setAttribute('aria-label', kind);
    picker.append(choice);
  }
  return picker;
}

/** Someone just went out and the round goes on: note it for a moment. Nothing pops on the first render. */
function noteGoingOut(game) {
  const before = seenOut;
  seenOut = { round: game.round, places: game.places.length };
  if (game.phase !== 'playing' || (before && before.round !== game.round)) outNote = null; // the round's over: play doesn't go on
  if (!before || before.round !== game.round || game.places.length <= before.places || game.phase !== 'playing') return;
  const note = { id: game.places.at(-1), place: game.places.length - 1, at: performance.now() };
  outNote = note;
  setTimeout(() => { if (outNote === note) { outNote = null; redraw(); } }, OUT_MS);
}

/** "Ana is out · 1st / Play goes on" over the pile; a redraw picks the fade up where it was. */
function renderOutNote(names, meId) {
  const el = document.querySelector('.out-note');
  el.hidden = outNote === null;
  if (!outNote) return;
  const who = outNote.id === meId ? "You're out" : `${names[outNote.id]} is out`;
  el.querySelector('.out-note-text').textContent = `${who} · ${placeLabel(outNote.place)}`;
  el.style.setProperty('--since', `${-(performance.now() - outNote.at)}ms`);
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
    const won = gains()?.[i];
    if (won) { // the points this round just added, rising under the score
      const gain = document.createElement('i');
      gain.className = 'gain';
      gain.textContent = `+${won}`;
      score.append(gain);
    }
    const name = span(sideName(side, names));
    if (i > 0) parts.push(span('·', 'sep'));
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
  const dropped = top.player_id === currentMe && justDropped(); // you put it there yourself
  if (landed && !dropped) flyIn(plays.at(-1), seatEls.get(top.player_id)); // slides in from whoever played it
  if (landed && top.kind === 'bomb') shakeTable();
}

/** Your cards are in play on your turn, or when you have a card to give in the swap. */
function yourMove(game, meId) {
  return (game.phase === 'playing' && game.turn === meId && !game.reveal) || (game.swap?.choices.length ?? 0) > 0; // play waits till the cards that are up go
}

function renderHand(game) {
  // One card more than before, and not a deal: it was given to you in the swap.
  const gained = game.hand.filter((code) => !lastHand.includes(code));
  if (lastHand.length && gained.length === 1 && game.hand.length === lastHand.length + 1) {
    received = { code: gained[0], at: performance.now() };
    const mine = received;
    setTimeout(() => { if (received === mine) { received = null; redraw(); } }, RECEIVED_MS); // back in line, the lift gone
  }
  lastHand = [...game.hand];
  const since = received && performance.now() - received.at;
  if (since >= RECEIVED_MS) received = null;
  selected = keepHeld(selected, game.hand);
  const choices = game.swap?.choices ?? [];
  const giving = choices.length > 0;
  if (giving) selected = selected.filter((c) => choices.includes(c)).slice(0, 1);
  const mine = yourMove(game, currentMe);
  if (!mine) selected = []; // a pause keeps what you picked; it only stops new taps
  const locked = !mine || Boolean(game.pause);
  const hand = document.querySelector('.hand');
  cancelDrag();
  hand.classList.toggle('locked', locked);
  hand.style.setProperty('--n', String(game.hand.length));
  hand.replaceChildren(...game.hand.map((code) => {
    const card = button('', () => pick(code), 'hand-card');
    card.setAttribute('aria-label', cardName(code));
    card.dataset.code = code;
    if (locked) card.setAttribute('aria-disabled', 'true');
    card.classList.toggle('selected', selected.includes(code));
    card.classList.toggle('dim', giving && !choices.includes(code));
    if (received?.code === code && !selected.includes(code)) { // picked: it lifts as a pick instead // stands up, then settles; a redraw picks the motion up where it was
      card.classList.add('received');
      card.style.setProperty('--since', `${-since}ms`);
    }
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
  renderActions(game, currentMe); // Clear wakes up or greys out
}

function renderActions(game, meId) {
  const paused = Boolean(game.pause);
  const myTurn = !paused && !game.reveal && game.phase === 'playing' && game.turn === meId;
  const giving = !paused && (game.swap?.choices.length ?? 0) > 0;
  const play = document.getElementById('btn-play');
  play.hidden = !(myTurn || giving);
  play.textContent = giving ? 'Give' : 'Play';
  play.disabled = myTurn && game.can_play === false; // nothing you hold beats the pile: Pass is the move
  const bombAsk = document.getElementById('bomb-confirm');
  if (!myTurn && !bombAsk.hidden) showModal(bombAsk, false); // the moment passed (a pause, a drop)
  const pass = document.getElementById('btn-pass'); // there with Play, greyed out when you can't pass
  pass.hidden = play.hidden;
  pass.disabled = !myTurn || leading(game) || (selected.length > 0 && game.can_play !== false); // cards picked: you mean to play (Clear, then Pass)
  const clear = document.getElementById('btn-clear');
  clear.hidden = play.hidden;
  clear.disabled = selected.length === 0;
  document.getElementById('btn-giveup').hidden = !(myTurn && game.hand.length > 0); // only on your turn
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
