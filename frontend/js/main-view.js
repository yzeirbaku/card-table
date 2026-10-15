import { fetchGames, createRoom } from './api.js';
import { canReadClipboard } from './clipboard.js';
import { cleanCode, isCompleteCode } from './code.js';
import { openSheet, closeSheets } from './sheets.js';
import { toast } from './ui.js';

const MAX_NAME = 20;

export function initMain({ store, enterRoom, applySettings }) {
  const nameInput = document.getElementById('name-input');
  nameInput.value = store.getName();
  nameInput.addEventListener('input', () => store.setName(nameInput.value.trim()));

  const hasName = () => {
    const name = nameInput.value.trim();
    if (name.length >= 1 && name.length <= MAX_NAME) return true;
    toast('Enter your name first');
    nameInput.focus();
    return false;
  };

  // New table: pick game, then player count, then the room is created.
  let gamesRequest = 0; // the newest games fetch; an older one's answer is dropped
  document.getElementById('btn-new').addEventListener('click', async () => {
    if (!hasName()) return;
    showStep('game');
    openSheet('sheet-new');
    const list = document.getElementById('game-list');
    list.replaceChildren();
    const mine = ++gamesRequest;
    const stale = () => mine !== gamesRequest || document.getElementById('sheet-new').hidden; // closed, or tapped again
    try {
      const games = await fetchGames();
      if (stale()) return;
      list.replaceChildren(...games.map((game) => choice(game.name, () => pickPlayers(game))));
    } catch (err) {
      if (stale()) return;
      closeSheets();
      toast(err.message);
    }
  });

  function pickPlayers(game) {
    showStep('players');
    const counts = [];
    for (let n = game.min_players; n <= game.max_players; n++) counts.push(choice(String(n), () => create(game, n)));
    document.getElementById('player-counts').replaceChildren(...counts);
  }

  let creating = false;
  async function create(game, players) {
    if (creating) return; // ignore double taps while the request is in flight
    creating = true;
    try {
      const code = await createRoom(game.id, players);
      closeSheets();
      enterRoom(code);
    } catch (err) {
      toast(err.message);
    } finally {
      creating = false;
    }
  }

  function showStep(step) {
    document.querySelectorAll('#sheet-new .sheet-step').forEach((el) => { el.hidden = el.dataset.step !== step; });
    document.querySelector('#sheet-new .sheet-title').textContent = step === 'game' ? 'Pick a game' : 'Players';
  }

  // Join: one code box, optional Paste button.
  const codeInput = document.getElementById('join-code');
  document.getElementById('btn-join').addEventListener('click', () => {
    if (!hasName()) return;
    codeInput.value = '';
    document.getElementById('btn-paste').hidden = !canReadClipboard();
    openSheet('sheet-join');
    codeInput.focus();
  });
  codeInput.addEventListener('input', () => { codeInput.value = cleanCode(codeInput.value); });
  document.getElementById('btn-paste').addEventListener('click', async () => {
    try {
      codeInput.value = cleanCode(await navigator.clipboard.readText());
    } catch {
      toast('Paste the code into the box');
    }
  });
  document.getElementById('join-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const code = cleanCode(codeInput.value);
    if (!isCompleteCode(code)) {
      toast('Codes are 4 letters');
      return;
    }
    closeSheets();
    enterRoom(code);
  });

  document.getElementById('btn-rules').addEventListener('click', () => {
    openSheet('sheet-rules');
    document.getElementById('sheet-rules').scrollTop = 0;
  });

  // Settings: theme + card style, applied immediately.
  document.getElementById('btn-settings').addEventListener('click', () => {
    markSettings(store.getSettings());
    openSheet('sheet-settings');
  });
  const change = (patch) => {
    store.setSettings(patch);
    const settings = store.getSettings();
    applySettings(settings);
    markSettings(settings);
  };
  document.getElementById('theme-swatches').addEventListener('click', (event) => {
    const button = event.target.closest('[data-theme]');
    if (button) change({ theme: button.dataset.theme });
  });
  document.getElementById('card-styles').addEventListener('click', (event) => {
    const button = event.target.closest('[data-cards]');
    if (button) change({ cardStyle: button.dataset.cards });
  });
}

function markSettings({ theme, cardStyle }) {
  for (const b of document.querySelectorAll('[data-theme]')) {
    b.classList.toggle('on', b.dataset.theme === theme);
    b.setAttribute('aria-pressed', String(b.dataset.theme === theme));
  }
  for (const b of document.querySelectorAll('[data-cards]')) {
    b.classList.toggle('on', b.dataset.cards === cardStyle);
    b.setAttribute('aria-pressed', String(b.dataset.cards === cardStyle));
  }
}

function choice(label, onClick) {
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = label;
  button.addEventListener('click', onClick);
  return button;
}
