import { copyText } from './clipboard.js';
import { button, div, span } from './dom.js';
import { fillRules, hasRules } from './rules.js';
import { lobbySpots } from './seats.js';
import { openSheet } from './sheets.js';

let send = () => {};
let lobbyGame = null; // the room's game id, for How to play
let startTimer = null; // ticks the 3 · 2 · 1 while every seat is taken
let startShown = null; // the number on screen

/** The number to show with `ms` left before the game: 3, 2, 1, and 1 until it starts. */
export function startNumber(ms) {
  return Math.max(1, Math.ceil(ms / 1000));
}

export function initLobby({ onLeave, send: sendMessage }) {
  send = sendMessage;
  const copyButton = document.getElementById('btn-copy');
  const copy = async () => {
    getSelection()?.removeAllRanges(); // the click selected the code (user-select: all): it needn't stay blue
    const ok = await copyText(document.querySelector('.lobby-code').textContent);
    const labels = [...copyButton.querySelector('.plaque-sub').children];
    const show = (i) => labels.forEach((label, j) => label.classList.toggle('on', i === j));
    show(ok ? 1 : 2); // labels: Tap to copy, Copied ✓, Select the code
    setTimeout(() => show(0), 1500);
  };
  copyButton.addEventListener('click', copy);
  copyButton.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); copy(); }
  });
  document.getElementById('btn-lobby-leave').addEventListener('click', onLeave);
  for (const b of document.querySelectorAll('.lobby-level [data-level]')) {
    b.addEventListener('click', () => send({ type: 'set_level', level: b.dataset.level }));
  }
  const pills = document.querySelector('.lobby-level .pills');
  new ResizeObserver(() => placePill(pills)).observe(pills); // the buttons grow on a big screen
  document.getElementById('btn-lobby-rules').addEventListener('click', () => {
    const sheet = document.getElementById('sheet-rules');
    fillRules(sheet.querySelector('.rules-body'), lobbyGame);
    openSheet('sheet-rules');
    sheet.scrollTop = 0;
  });
}

/** Before the first state arrives: show the code so it can be shared right away, and the game
 *  (`{ id, name }`) if we know it already (we just created the table). */
export function showLobbyLoading(code, game = null) {
  lobbyGame = game?.id ?? null;
  document.querySelector('.lobby-game').textContent = game?.name ?? '';
  document.getElementById('btn-lobby-rules').style.visibility = game && hasRules(game.id) ? '' : 'hidden'; // keeps its place: nothing jumps when it shows
  document.querySelector('.lobby-code').textContent = code;
  document.querySelector('.lobby-count').textContent = 'Connecting…';
  document.querySelector('.lobby-count-sub').hidden = true;
  document.querySelector('.lobby-groups').replaceChildren();
  document.querySelector('.lobby-unseated').textContent = '';
  showStart(null);
}

export function renderLobby(state, meId, gameName) {
  const { seats } = state.room;
  const bySeat = Array(seats).fill(null);
  for (const p of state.players) if (p.seat !== null) bySeat[p.seat] = p;
  document.querySelector('.lobby-game').textContent = gameName;
  lobbyGame = state.room.game;
  document.getElementById('btn-lobby-rules').style.visibility = hasRules(lobbyGame) ? '' : 'hidden';
  document.querySelector('.lobby-code').textContent = state.code;
  document.querySelector('.lobby-count').textContent = `${bySeat.filter(Boolean).length} / ${seats}`;
  document.querySelector('.lobby-count-sub').hidden = false;

  const creator = state.players.some((p) => p.id === meId && p.is_creator);
  const seating = { meId, creator, canAdd: creator && state.room.computer_seats_left > 0 }; // computers: the creator's call
  showLevel(state, creator);
  // Round the table as you'll sit at it: you at the bottom, the others clockwise from your left.
  const mine = state.players.find((p) => p.id === meId)?.seat ?? null;
  const spots = lobbySpots(seats, mine);
  document.querySelector('.lobby-groups').replaceChildren(...bySeat.map((player, seat) => seatSpot(seat, player, spots[seat], seating)));

  const waiting = state.players.filter((p) => p.seat === null).map((p) => (p.id === meId ? 'you' : p.connected ? p.name : `${p.name} (offline)`));
  document.querySelector('.lobby-unseated').textContent = waiting.length ? `Not seated yet: ${waiting.join(', ')}` : '';
  showStart(state.room.starting_in);
}

/** How well the computers play: everyone sees it while there are computers, or could be; the creator sets it. */
function showLevel(state, creator) {
  const row = document.querySelector('.lobby-level');
  row.hidden = state.room.computer_seats_left === 0 && !state.players.some((p) => p.computer);
  for (const b of row.querySelectorAll('[data-level]')) {
    const on = b.dataset.level === state.room.level;
    b.classList.toggle('on', on);
    b.setAttribute('aria-pressed', String(on));
    b.disabled = !creator;
  }
  placePill(row.querySelector('.pills'));
}

/** The gold pill slides (and stretches) to the chosen level; the first time it just appears there. */
function placePill(group) {
  const pill = group.querySelector('.pill-ind');
  const on = group.querySelector('button.on');
  if (!on || group.closest('[hidden]')) return;
  if (on.offsetWidth === 0) { // not laid out yet (the lobby is just being shown)
    requestAnimationFrame(() => placePill(group));
    return;
  }
  const first = !pill.classList.contains('ready');
  if (first) pill.style.transition = 'none';
  pill.style.transform = `translateX(${on.offsetLeft}px)`;
  pill.style.width = `${on.offsetWidth}px`;
  if (first) {
    void pill.offsetHeight;
    pill.style.transition = '';
    pill.classList.add('ready');
  }
}

/** One chair round the table: tap an empty one to sit; the creator adds (+ 🤖) and removes (✕) computers. */
function seatSpot(seat, player, spot, { meId, creator, canAdd }) {
  const el = div(`lobby-seat spot-${spot}`);
  if (!player) {
    el.classList.add('open');
    const sit = button('Sit', () => send({ type: 'sit', seat }), 'ring');
    sit.setAttribute('aria-label', 'Sit here');
    el.append(sit);
    if (canAdd) {
      const add = button('+ 🤖', () => send({ type: 'add_computer', seat }), 'seat-add');
      add.setAttribute('aria-label', 'Add a computer player here');
      el.append(add);
    }
    return el;
  }
  const ring = span(player.computer ? '🤖' : player.name.charAt(0).toUpperCase(), 'ring');
  const label = span('', 'seat-name');
  label.append(span(player.id === meId ? `${player.name} (you)` : player.name));
  if (player.computer) {
    el.classList.add('computer');
    ring.setAttribute('aria-label', 'computer player');
    if (creator) {
      const remove = button('✕', () => send({ type: 'remove_computer', seat }), 'seat-remove');
      remove.setAttribute('aria-label', `Take ${player.name} off the table`);
      label.append(remove);
    }
  } else if (!player.connected) {
    el.classList.add('offline');
  }
  if (player.id === meId) el.classList.add('me');
  el.append(ring, label);
  return el;
}

/** Every seat taken: count down to the game the server starts `seconds` from now; null hides it. */
function showStart(seconds) {
  const box = document.querySelector('.lobby-start');
  clearInterval(startTimer);
  startTimer = null;
  if (seconds === null || seconds === undefined) {
    box.hidden = true;
    startShown = null;
    return;
  }
  const until = performance.now() + seconds * 1000;
  const num = box.querySelector('.lobby-start-num');
  const tick = () => {
    const n = startNumber(until - performance.now());
    if (n === startShown) return;
    startShown = n;
    num.textContent = String(n);
    num.style.animation = 'none'; // restart the pop for each number
    void num.offsetWidth;
    num.style.animation = '';
  };
  box.hidden = false;
  tick();
  startTimer = setInterval(tick, 100);
}

/** The game has started (or the lobby is gone): no countdown left running. */
export function stopStart() {
  showStart(null);
}
