import { initAccount } from './account.js';
import { fetchGames, socketUrl } from './api.js';
import { RoomConnection } from './connection.js';
import { stopDeal } from './deal.js';
import { useCardStyle } from './dom.js';
import { initInviteFriends } from './invite-friends.js';
import { initInvites } from './invites.js';
import { initLobby, renderLobby, showLobbyLoading, stopStart } from './lobby-view.js';
import { initMain, openJoin } from './main-view.js';
import { shouldRotate } from './orientation.js';
import { closeSheets } from './sheets.js';
import { inviteAction, joinQuestion, readLaunch } from './social.js';
import { createStore } from './storage.js';
import { initTable, moveRejected, reacted, renderTable, resetTable, showEnded } from './table-view.js';
import { stopCountdown } from './table-overlay.js';
import { askConfirm, onViewShown, setReconnecting, showView, syncTableRotated, toast } from './ui.js';

const store = createStore();
const gameNames = {};
let connection = null;
let meId = null;
let heldLobby = null; // the lobby state waiting behind the "X left the table" popup
let account = null;
let invites = null;
let lastRoom = null; // the room part of the last state at this table: is a game on?
let pendingInvite = null; // { code, from } tapped while resuming a table: asked about once its first state is in

function applySettings({ theme, cardStyle }) {
  // classList, not className: keep other body classes such as table-rotated.
  for (const c of [...document.body.classList]) if (/^(theme|cards)-/.test(c)) document.body.classList.remove(c);
  document.body.classList.add(`theme-${theme}`, `cards-${cardStyle}`);
  useCardStyle(cardStyle);
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
  lastRoom = state.room;
  if (pendingInvite) setTimeout(runPendingInvite); // after this state is on screen
  if (state.room.status === 'playing') {
    if (heldLobby) resetTable(); // a new game started behind the "X left" popup
    heldLobby = null;
    stopStart();
    if (!document.getElementById('sheet-rules').hidden || !document.getElementById('sheet-invite').hidden) closeSheets(); // read or invited in the lobby; the game has started
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
  invite.update(state);
}

function enterRoom(code, { resume = false, game = null } = {}) {
  connection?.close();
  heldLobby = null;
  lastRoom = null;
  resetTable();
  meId = null;
  if (resume) {
    showView(null); // no lobby flash: the first state picks lobby or table
  } else {
    showLobbyLoading(code, game);
    showView('lobby');
  }
  connection = new RoomConnection({
    code,
    store,
    urlFor: socketUrl,
    onWelcome: (id) => { meId = id; },
    onState: render,
    onError: (message) => { moveRejected(); toast(message); },
    onReaction: reacted,
    onReconnecting: setReconnecting,
    onClosed: (message) => {
      connection = null;
      heldLobby = null;
      lastRoom = null;
      stopCountdown();
      resetTable();
      setReconnecting(false);
      closeSheets(); // How to play, opened in the lobby
      account.sync(); // a 4401 close has just signed this phone out
      showView('main');
      toast(message);
      runPendingInvite(); // the table being resumed is gone: nothing to ask about any more
    },
  });
  connection.connect();
}

function leaveRoom() {
  connection?.leave();
  connection = null;
  heldLobby = null;
  lastRoom = null;
  stopCountdown();
  stopStart();
  resetTable();
  setReconnecting(false);
  closeSheets();
  showView('main');
}

/** An invite tapped (in the app or in a notification): sign in first, stay, join, or ask before leaving a table. */
async function goToInvite(code, from) {
  const action = inviteAction({ signedIn: Boolean(store.getSession()), currentCode: connection?.code ?? null, target: code });
  if (action === 'signin') {
    if (connection) return; // a guest at a table: the Join sheet belongs to the main screen
    closeSheets();
    showView('main');
    openJoin(code);
  } else if (action === 'join') {
    enterRoom(code);
  } else if (action === 'ask') {
    const playing = lastRoom?.status === 'playing';
    const go = await askConfirm(joinQuestion({ from, playing, game: lastRoom ? gameName(lastRoom.game) : '' }));
    if (!go || connection?.code === code) return;
    leaveRoom();
    enterRoom(code);
  }
}

function runPendingInvite() {
  const invite = pendingInvite;
  pendingInvite = null;
  if (invite) goToInvite(invite.code, invite.from);
}

/** What the page was opened for (?join=CODE&from=Name, ?friends). Resuming a table, the invite waits for its first state. */
function launch({ join, from, friends }) {
  if (friends && !connection) account.openProfile('friends'); // not over a table: that would hide it without leaving
  if (!join) return;
  if (connection && !lastRoom) pendingInvite = { code: join, from };
  else goToInvite(join, from);
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
// A long press at the table opens no menu (Android's "open image", the desktop right-click one).
document.getElementById('view-table').addEventListener('contextmenu', (event) => event.preventDefault());

applySettings(store.getSettings());
initMain({ store, enterRoom, applySettings });
account = initAccount({ store, onSessionChange: () => invites?.refresh() });
invites = initInvites({ store, onJoin: goToInvite });
onViewShown((name) => { if (name === 'main') invites.refresh(); });
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') { invites.refresh(); account.refreshFriends(); } });
const invite = initInviteFriends({ store, gameName });
initLobby({ onLeave: leaveRoom, send, signedIn: () => Boolean(store.getSession()), onInvite: (state) => state && invite.open(state) });
initTable({ onLeave: leaveRoom, send });
document.getElementById('sheet-backdrop').addEventListener('click', closeSheets);
addEventListener('resize', updateRotation);
// iOS, turning the phone back upright: a page scrolled in landscape keeps a stale offset for taps even once it fits,
// so buttons such as the account chip stop answering. Writing the scroll back makes it re-measure. Only on a turn
// (the width changes; a keyboard only changes the height), and again once the turned layout has settled.
let lastWidth = innerWidth;
function resetScroll() {
  if (scrollX || scrollY) scrollTo(0, 0);
  for (const view of document.querySelectorAll('.view:not([hidden])')) {
    if (view.scrollHeight <= view.clientHeight) view.scrollTop = 0;
  }
}
addEventListener('resize', () => {
  if (innerWidth === lastWidth) return;
  lastWidth = innerWidth;
  resetScroll();
  setTimeout(resetScroll, 300);
});
updateRotation();

fetchGames()
  .then((games) => { for (const g of games) gameNames[g.id] = g.name; })
  .catch(() => {}); // names fall back to the id; the New table sheet reports errors itself

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/service-worker.js').catch(() => {});
  navigator.serviceWorker.addEventListener('message', (event) => {
    const msg = event.data;
    if (msg?.type === 'open' && typeof msg.url === 'string') {
      launch(readLaunch(new URL(msg.url, location.origin).search));
    } else if (msg?.type === 'push') {
      invites.refresh();
      if (msg.tag?.startsWith('request-')) account.refreshFriends();
      const onMain = !document.getElementById('view-main').hidden && document.visibilityState === 'visible';
      // the envelope shows an invite; a friend request has no sign on this screen yet, so its notification stays
      if (onMain && msg.tag?.startsWith('invite-')) closeNotifications(msg.tag);
    }
  });
}

function closeNotifications(tag) {
  navigator.serviceWorker.ready
    .then((registration) => registration.getNotifications({ tag }))
    .then((shown) => { for (const n of shown) n.close(); })
    .catch(() => {});
}

// Back to the table you were at (reload, app reopened, phone slept), then whatever the page was opened for.
const launched = readLaunch(location.search);
if (location.search) history.replaceState(null, '', '/');
const current = store.getCurrentRoom();
if (current && store.getToken(current)) enterRoom(current, { resume: true });
launch(launched);
if (!connection) invites.refresh(); // the main screen is up without showView having run
