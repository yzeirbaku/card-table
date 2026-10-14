import { fetchGames, socketUrl } from './api.js';
import { RoomConnection } from './connection.js';
import { initLobby, renderLobby, showLobbyLoading } from './lobby-view.js';
import { initMain } from './main-view.js';
import { shouldRotate } from './orientation.js';
import { closeSheets } from './sheets.js';
import { createStore } from './storage.js';
import { initTable, renderTable } from './table-view.js';
import { setReconnecting, showView, syncTableRotated, toast } from './ui.js';

const store = createStore();
const gameNames = {};
let connection = null;
let meId = null;

function applySettings({ theme, cardStyle }) {
  // classList, not className: keep other body classes such as table-rotated.
  for (const c of [...document.body.classList]) if (/^(theme|cards)-/.test(c)) document.body.classList.remove(c);
  document.body.classList.add(`theme-${theme}`, `cards-${cardStyle}`);
}

function gameName(id) {
  return gameNames[id] ?? id.charAt(0).toUpperCase() + id.slice(1);
}

function send(message) {
  if (!connection?.send(message)) toast('Not connected right now');
}

function render(state) {
  if (state.room.status === 'playing') {
    showView('table');
    renderTable(state, meId);
  } else {
    showView('lobby');
    renderLobby(state, meId, gameName(state.room.game));
  }
}

function enterRoom(code, { resume = false } = {}) {
  connection?.close();
  meId = null;
  if (resume) {
    showView(null); // no lobby flash: the first state picks lobby or table
  } else {
    showLobbyLoading(code);
    showView('lobby');
  }
  connection = new RoomConnection({
    code,
    store,
    urlFor: socketUrl,
    onWelcome: (id) => { meId = id; },
    onState: render,
    onError: toast,
    onReconnecting: setReconnecting,
    onClosed: (message) => {
      connection = null;
      setReconnecting(false);
      showView('main');
      toast(message);
    },
  });
  connection.connect();
}

function leaveRoom() {
  connection?.leave();
  connection = null;
  setReconnecting(false);
  showView('main');
}

function updateRotation() {
  document.getElementById('view-table').classList.toggle('rotated', shouldRotate(innerWidth, innerHeight));
  syncTableRotated();
}

applySettings(store.getSettings());
initMain({ store, enterRoom, applySettings });
initLobby({ onLeave: leaveRoom, send });
initTable({ onLeave: leaveRoom, send });
document.getElementById('sheet-backdrop').addEventListener('click', closeSheets);
addEventListener('resize', updateRotation);
updateRotation();

fetchGames()
  .then((games) => { for (const g of games) gameNames[g.id] = g.name; })
  .catch(() => {}); // names fall back to the id; the New table sheet reports errors itself

if ('serviceWorker' in navigator) navigator.serviceWorker.register('/service-worker.js').catch(() => {});

// Back to the table you were at (reload, app reopened, phone slept).
const current = store.getCurrentRoom();
if (current && store.getToken(current)) enterRoom(current, { resume: true });
