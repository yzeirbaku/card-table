import { copyText } from './clipboard.js';
import { button, div, span } from './dom.js';
import { seatGroups } from './murlan.js';
import { fillRules, hasRules } from './rules.js';
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
  copyButton.addEventListener('click', async () => {
    const ok = await copyText(document.querySelector('.lobby-code').textContent);
    const show = (i) => [...copyButton.children].forEach((label, j) => label.classList.toggle('on', i === j));
    show(ok ? 1 : 2); // labels: Copy, Copied ✓, Tap the code
    setTimeout(() => show(0), 1500);
  });
  document.getElementById('btn-lobby-leave').addEventListener('click', onLeave);
  for (const b of document.querySelectorAll('.lobby-level [data-level]')) {
    b.addEventListener('click', () => send({ type: 'set_level', level: b.dataset.level }));
  }
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
  document.querySelector('.lobby-count').textContent = `${bySeat.filter(Boolean).length}/${seats} seated`;

  const teams = seats === 4; // partners sit across, so picking a seat picks your partner
  const creator = state.players.some((p) => p.id === meId && p.is_creator);
  const seating = { meId, creator, canAdd: creator && state.room.computer_seats_left > 0 }; // computers: the creator's call
  showLevel(state, creator);
  const groups = document.querySelector('.lobby-groups');
  groups.classList.toggle('teams', teams);
  groups.replaceChildren(...seatGroups(seats).map((group, i) => {
    const team = div('lobby-team');
    if (teams) team.append(span(`Team ${i + 1}`, 'team-label'));
    const list = document.createElement('ul');
    list.className = 'lobby-seats';
    list.append(...group.map((seat) => seatTile(seat, bySeat[seat], seating)));
    team.append(list);
    return team;
  }));

  const waiting = state.players.filter((p) => p.seat === null).map((p) => (p.id === meId ? 'you' : p.connected ? p.name : `${p.name} (offline)`));
  document.querySelector('.lobby-unseated').textContent = waiting.length ? `Not seated yet: ${waiting.join(', ')}` : '';
  showStart(state.room.starting_in);
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
}

function seatTile(seat, player, { meId, creator, canAdd }) {
  const row = document.createElement('li');
  const avatar = span('', 'avatar');
  const name = span('');
  if (player?.computer) {
    avatar.textContent = '🤖';
    avatar.setAttribute('aria-label', 'computer player');
    name.textContent = player.name;
    row.className = 'taken computer';
    row.append(avatar, name);
    if (creator) {
      const remove = button('✕', () => send({ type: 'remove_computer', seat }), 'seat-remove');
      remove.setAttribute('aria-label', `Take ${player.name} off the table`);
      row.append(remove);
    }
    return row;
  }
  if (player) {
    avatar.textContent = player.name.charAt(0).toUpperCase();
    name.textContent = player.id === meId ? `${player.name} (you)` : player.name;
    row.className = player.connected ? 'taken' : 'taken offline';
    if (player.id === meId) row.classList.add('me');
  } else {
    name.textContent = 'Tap to sit';
    row.className = 'open';
    row.tabIndex = 0;
    row.setAttribute('role', 'button');
    row.addEventListener('click', () => send({ type: 'sit', seat }));
    row.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); send({ type: 'sit', seat }); }
    });
  }
  row.append(avatar, name);
  if (!player && canAdd) {
    const add = button('+ 🤖 Computer', (e) => { e.stopPropagation(); send({ type: 'add_computer', seat }); }, 'seat-add');
    add.addEventListener('keydown', (e) => e.stopPropagation()); // Enter on it adds, it doesn't sit you
    add.setAttribute('aria-label', 'Add a computer player here');
    row.append(add);
  }
  return row;
}
