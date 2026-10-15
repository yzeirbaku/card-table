import { fetchGames, socketUrl } from './api.js';
import { RoomConnection } from './connection.js';
import { stopDeal } from './deal.js';
import { initLobby, renderLobby, showLobbyLoading } from './lobby-view.js';
import { initMain } from './main-view.js';
import { shouldRotate } from './orientation.js';
import { closeSheets } from './sheets.js';
import { createStore } from './storage.js';
import { initTable, moveRejected, renderTable, resetTable, showEnded } from './table-view.js';
import { stopCountdown } from './table-overlay.js';
import { setReconnecting, showView, syncTableRotated, toast } from './ui.js';

const store = createStore();
const gameNames = {};
let connection = null;
let meId = null;
let heldLobby = null; // the lobby state waiting behind the "X left the table" popup

function applySettings({ theme, cardStyle }) {
  // classList, not className: keep other body classes such as table-rotated.
  for (const c of [...document.body.classList]) if (/^(theme|cards)-/.test(c)) document.body.classList.remove(c);
  document.body.classList.add(`theme-${theme}`, `cards-${cardStyle}`);
}

function gameName(id) {
  return gameNames[id] ?? id.charAt(0).toUpperCase() + id.slice(1);
}

function send(message) {
  const sent = Boolean(connection?.send(message));
  if (!sent) toast('Not connected right now');
  return sent;
}

function render(state) {
  if (state.room.status === 'playing') {
    if (heldLobby) resetTable(); // a new game started behind the "X left" popup
    heldLobby = null;
    showView('table');
    renderTable(state, meId);
    return;
  }
  stopCountdown();
  const atTable = !document.getElementById('view-table').hidden;
  if (heldLobby || (atTable && state.room.ended_by)) { // someone left: say so before the lobby
    if (!heldLobby) showEnded(state.room.ended_by, () => showLobby(heldLobby));
    heldLobby = state; // the lobby, as it is when they tap
    return;
  }
  showLobby(state);
}

function showLobby(state) {
  heldLobby = null;
  stopCountdown();
  resetTable();
  showView('lobby');
  renderLobby(state, meId, gameName(state.room.game));
}

function enterRoom(code, { resume = false } = {}) {
  connection?.close();
  heldLobby = null;
  resetTable();
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
    onError: (message) => { moveRejected(); toast(message); },
    onReconnecting: setReconnecting,
    onClosed: (message) => {
      connection = null;
      heldLobby = null;
      stopCountdown();
      resetTable();
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
  heldLobby = null;
  stopCountdown();
  resetTable();
  setReconnecting(false);
  showView('main');
}

function updateRotation() {
  const table = document.getElementById('view-table');
  const rotated = shouldRotate(innerWidth, innerHeight);
  if (rotated !== table.classList.contains('rotated')) stopDeal(); // the deal's positions no longer hold
  table.classList.toggle('rotated', rotated);
  syncTableRotated();
}

// iOS Safari ignores user-scalable=no: stop pinch zoom by hand. Two fingers never scroll here anyway.
for (const type of ['gesturestart', 'gesturechange']) document.addEventListener(type, (event) => event.preventDefault());
document.addEventListener('touchmove', (event) => { if (event.touches.length > 1) event.preventDefault(); }, { passive: false });

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
