import { copyText } from './clipboard.js';
import { div, span } from './dom.js';
import { seatGroups } from './murlan.js';

let send = () => {};

export function initLobby({ onLeave, send: sendMessage }) {
  send = sendMessage;
  const copyButton = document.getElementById('btn-copy');
  copyButton.addEventListener('click', async () => {
    const ok = await copyText(document.querySelector('.lobby-code').textContent);
    copyButton.textContent = ok ? 'Copied ✓' : 'Tap the code';
    setTimeout(() => { copyButton.textContent = 'Copy'; }, 1500);
  });
  document.getElementById('btn-lobby-leave').addEventListener('click', onLeave);
}

/** Before the first state arrives: show the code so it can be shared right away. */
export function showLobbyLoading(code) {
  document.querySelector('.lobby-game').textContent = '';
  document.querySelector('.lobby-code').textContent = code;
  document.querySelector('.lobby-count').textContent = 'Connecting…';
  document.querySelector('.lobby-groups').replaceChildren();
  document.querySelector('.lobby-unseated').textContent = '';
}

export function renderLobby(state, meId, gameName) {
  const { seats } = state.room;
  const bySeat = Array(seats).fill(null);
  for (const p of state.players) if (p.seat !== null) bySeat[p.seat] = p;
  document.querySelector('.lobby-game').textContent = gameName;
  document.querySelector('.lobby-code').textContent = state.code;
  document.querySelector('.lobby-count').textContent = `${bySeat.filter(Boolean).length}/${seats} seated`;

  const teams = seats === 4; // partners sit across, so picking a seat picks your partner
  const groups = document.querySelector('.lobby-groups');
  groups.classList.toggle('teams', teams);
  groups.replaceChildren(...seatGroups(seats).map((group, i) => {
    const team = div('lobby-team');
    if (teams) team.append(span(`Team ${i + 1}`, 'team-label'));
    const list = document.createElement('ul');
    list.className = 'lobby-seats';
    list.append(...group.map((seat) => seatTile(seat, bySeat[seat], meId)));
    team.append(list);
    return team;
  }));

  const waiting = state.players.filter((p) => p.seat === null).map((p) => (p.id === meId ? 'you' : p.name));
  document.querySelector('.lobby-unseated').textContent = waiting.length ? `Not seated yet: ${waiting.join(', ')}` : '';
}

function seatTile(seat, player, meId) {
  const row = document.createElement('li');
  const avatar = span('', 'avatar');
  const name = span('');
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
  return row;
}
