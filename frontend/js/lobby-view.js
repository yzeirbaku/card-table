import { copyText } from './clipboard.js';

export function initLobby({ onLeave }) {
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
  document.querySelector('.lobby-seats').replaceChildren();
}

export function renderLobby(state, meId, gameName) {
  const { seats } = state.room;
  document.querySelector('.lobby-game').textContent = gameName;
  document.querySelector('.lobby-code').textContent = state.code;
  document.querySelector('.lobby-count').textContent = `${state.players.length}/${seats} players`;
  const rows = [];
  for (let i = 0; i < seats; i++) {
    const player = state.players[i];
    const row = document.createElement('li');
    const avatar = document.createElement('span');
    avatar.className = 'avatar';
    const name = document.createElement('span');
    if (player) {
      avatar.textContent = player.name.charAt(0).toUpperCase();
      name.textContent = player.id === meId ? `${player.name} (you)` : player.name;
      row.className = player.connected ? 'taken' : 'taken offline';
    } else {
      name.textContent = 'waiting…';
      row.className = 'open';
    }
    row.append(avatar, name);
    rows.push(row);
  }
  document.querySelector('.lobby-seats').replaceChildren(...rows);
}
