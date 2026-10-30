import { fetchHeadToHead, fetchLeaderboard, fetchStats, login, logout, me, register } from './api.js';
import { openSheet, closeSheets } from './sheets.js';
import { initial, partnerLabel, rate, record, tagLine } from './stats-format.js';
import { showView, toast } from './ui.js';

// Accounts on the phone: the chip on the main screen, the Sign in sheet and the Profile page
// (your stats, the leaderboard, a friend's head-to-head). Guests never need any of it.

export function initAccount({ store }) {
  const chip = document.getElementById('btn-account');
  const nameInput = document.getElementById('name-input');
  const nameLabel = document.getElementById('name-label');
  const profile = document.getElementById('view-profile');

  /** The main screen as signed in or out: the chip, and the name you play under. */
  function sync() {
    const session = store.getSession();
    chip.querySelector('.chip-initial').hidden = !session;
    chip.querySelector('.chip-initial').textContent = session ? initial(session.username) : '';
    chip.querySelector('.chip-name').textContent = session ? session.username : 'Sign in';
    chip.classList.toggle('signed-in', Boolean(session));
    nameInput.readOnly = Boolean(session);
    nameInput.closest('.name-field').classList.toggle('signed-in', Boolean(session));
    nameLabel.textContent = session ? 'Playing as' : 'Your name';
    nameInput.value = session ? session.username : store.getName();
  }

  chip.addEventListener('click', () => {
    if (store.getSession()) openProfile();
    else openSignIn();
  });

  // ---- Sign in / New account ----

  const form = document.getElementById('account-form');
  const username = document.getElementById('account-username');
  const password = document.getElementById('account-password');
  const error = form.querySelector('.account-error');
  let mode = 'login';
  let busy = false;

  function setMode(next) {
    mode = next;
    const sheet = document.getElementById('sheet-account');
    for (const b of sheet.querySelectorAll('[data-mode]')) {
      b.classList.toggle('on', b.dataset.mode === mode);
      b.setAttribute('aria-pressed', String(b.dataset.mode === mode));
    }
    const label = mode === 'login' ? 'Sign in' : 'Make my account';
    sheet.querySelector('.sheet-title').textContent = mode === 'login' ? 'Sign in' : 'New account';
    form.querySelector('[type=submit]').textContent = label;
    password.autocomplete = mode === 'login' ? 'current-password' : 'new-password';
    username.placeholder = mode === 'login' ? 'Username' : 'Username (3-20 letters or digits)';
    password.placeholder = mode === 'login' ? 'Password' : 'Password (at least 8 characters)';
    error.hidden = true;
  }

  function openSignIn() {
    setMode('login');
    username.value = '';
    password.value = '';
    openSheet('sheet-account');
    username.focus();
  }

  document.getElementById('sheet-account').addEventListener('click', (event) => {
    const b = event.target.closest('[data-mode]');
    if (b) setMode(b.dataset.mode);
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (busy) return;
    busy = true;
    error.hidden = true;
    try {
      const signIn = mode === 'login' ? login : register;
      const session = await signIn(username.value.trim(), password.value);
      store.setSession(session);
      closeSheets();
      sync();
      toast(mode === 'login' ? `Signed in as ${session.username}` : `Welcome, ${session.username}`);
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
    } finally {
      busy = false;
    }
  });

  // ---- the Profile page ----

  let tab = 'stats';
  let board = 'solo';
  let leaderboard = null;
  let shownFor = null; // whose numbers the Stats and Players tabs hold
  let opened = 0; // the newest page opened; an older one's answer is dropped

  function showPane(name) {
    for (const pane of profile.querySelectorAll('.profile-pane')) pane.hidden = pane.dataset.pane !== name;
    profile.querySelector('.profile-tabs').hidden = name === 'player';
    for (const b of profile.querySelectorAll('[data-tab]')) {
      b.classList.toggle('on', b.dataset.tab === name);
      b.setAttribute('aria-selected', String(b.dataset.tab === name));
    }
  }

  function setHero(name, mine, tag) {
    for (const el of profile.querySelectorAll('.pc-initial')) el.textContent = initial(name);
    for (const el of profile.querySelectorAll('.pc-suit')) el.textContent = mine ? '♥' : '♠';
    profile.querySelector('.profile-card').classList.toggle('black', !mine);
    profile.querySelector('.profile-name').textContent = name;
    profile.querySelector('.profile-tag').textContent = tag;
  }

  async function openProfile(nextTab = 'stats') {
    const session = store.getSession();
    if (!session) return;
    const mine = ++opened;
    tab = nextTab;
    if (shownFor !== session.username) { // someone else's numbers must not show under this name
      for (const sel of ['.record-mine', '.partners', '.board']) profile.querySelector(sel).replaceChildren();
      profile.querySelector('.board-unranked').hidden = true;
      leaderboard = null;
    }
    setHero(session.username, true, '');
    showPane(tab);
    closeSheets();
    showView('profile');
    profile.scrollTop = 0;
    try {
      const [stats, boards] = await Promise.all([fetchStats(session.username), fetchLeaderboard()]);
      if (mine !== opened) return;
      leaderboard = boards;
      shownFor = session.username;
      setHero(stats.username, true, tagLine(stats));
      fillRecord(profile.querySelector('.record-mine'), stats);
      fillPartners(stats.partners);
      fillBoard();
    } catch (err) {
      if (mine === opened) toast(err.message);
    }
  }

  async function openPlayer(name) {
    const session = store.getSession();
    if (!session) return;
    const mine = ++opened;
    setHero(name, false, '');
    showPane('player');
    profile.scrollTop = 0;
    for (const sel of ['.versus', '.together', '.record-theirs']) profile.querySelector(sel).replaceChildren();
    try {
      const [stats, versus] = await Promise.all([fetchStats(name), fetchHeadToHead(session.username, name)]);
      if (mine !== opened) return;
      setHero(stats.username, false, tagLine(stats));
      profile.querySelector('.vs-title').textContent = `You vs ${stats.username}`;
      profile.querySelector('.their-title').textContent = `${stats.username}'s record`;
      fillRows(profile.querySelector('.versus'), [
        ['You won', String(versus.against.won)],
        [`${stats.username} won`, String(versus.against.lost)],
      ]);
      fillRows(profile.querySelector('.together'), [
        ['As partners', record(versus.together), rate(versus.together)],
      ]);
      fillRecord(profile.querySelector('.record-theirs'), stats);
    } catch (err) {
      if (mine === opened) toast(err.message);
    }
  }

  function fillRecord(table, stats) {
    const head = row(['', 'People', 'Computer', 'Total'], 'th');
    const line = (label, part) => row([label, record(part.people), record(part.computer), record(part.total)]);
    table.replaceChildren(head, line('Solo', stats.solo), line('Teams', stats.teams));
  }

  function fillPartners(partners) {
    const table = profile.querySelector('.partners');
    table.replaceChildren(...partners.map((p) => {
      const tr = row([partnerLabel(p), record(p), rate(p)]);
      tr.lastChild.className = 'muted';
      if (p.kind === 'user') linkRow(tr, p.name);
      return tr;
    }));
    profile.querySelector('.partners-empty').hidden = partners.length > 0;
  }

  function fillBoard() {
    const session = store.getSession();
    if (!leaderboard || !session) return;
    for (const b of profile.querySelectorAll('[data-board]')) {
      b.classList.toggle('on', b.dataset.board === board);
      b.setAttribute('aria-pressed', String(b.dataset.board === board));
    }
    const entries = leaderboard[board];
    const ranked = entries.filter((e) => e.ranked);
    const rest = entries.filter((e) => !e.ranked);
    const rows = ranked.map((e, i) => {
      const tr = row([String(i + 1), e.username, record(e), rate(e)]);
      tr.firstChild.className = 'rank';
      if (e.username === session.username) tr.classList.add('me');
      else linkRow(tr, e.username);
      return tr;
    });
    const table = profile.querySelector('.board');
    table.replaceChildren(...(rows.length ? [row(['', 'Player', 'W–L', 'Win %'], 'th'), ...rows] : []));
    const note = profile.querySelector('.board-unranked');
    note.replaceChildren();
    if (rest.length) {
      note.append(ranked.length ? 'Fewer than 5 games: ' : 'Nobody has 5 games yet: ');
      rest.forEach((e, i) => {
        if (i) note.append(', ');
        const name = document.createElement(e.username === session.username ? 'b' : 'button');
        name.textContent = `${e.username} ${record(e)}`;
        if (e.username !== session.username) {
          name.type = 'button';
          name.className = 'inline-link';
          name.addEventListener('click', () => openPlayer(e.username));
        }
        note.append(name);
      });
    } else if (!ranked.length) {
      note.textContent = 'No games against people yet';
    }
    note.hidden = !note.textContent;
  }

  function linkRow(tr, name) {
    tr.classList.add('link');
    tr.tabIndex = 0;
    tr.setAttribute('role', 'button');
    tr.addEventListener('click', () => openPlayer(name));
    tr.addEventListener('keydown', (event) => { if (event.key === 'Enter') openPlayer(name); });
  }

  profile.querySelector('.profile-tabs').addEventListener('click', (event) => {
    const b = event.target.closest('[data-tab]');
    if (!b) return;
    tab = b.dataset.tab;
    showPane(tab);
  });
  profile.querySelector('.seg').addEventListener('click', (event) => {
    const b = event.target.closest('[data-board]');
    if (!b) return;
    board = b.dataset.board;
    fillBoard();
  });
  document.getElementById('btn-profile-back').addEventListener('click', () => {
    if (!profile.querySelector('[data-pane="player"]').hidden) {
      openProfile(tab); // from a friend back to where you came from
    } else {
      opened += 1;
      showView('main');
    }
  });

  document.getElementById('btn-sign-out').addEventListener('click', () => {
    const session = store.getSession();
    store.clearSession();
    if (session) logout(session.token).catch(() => {}); // signed out here even if the server can't hear it
    opened += 1;
    sync();
    showView('main');
    toast('Signed out');
  });

  /** A session from before: check it still works. A network error keeps it (the server may just be away). */
  async function check() {
    const session = store.getSession();
    if (!session) return;
    const still = () => store.getSession()?.token === session.token; // not signed out or in again meanwhile
    try {
      const { username } = await me(session.token);
      if (still() && username !== session.username) store.setSession({ ...session, username });
    } catch (err) {
      if (still() && err.status === 401) store.clearSession();
    }
    sync();
  }

  sync();
  check();
  return { sync };
}

function row(cells, tag = 'td') {
  const tr = document.createElement('tr');
  for (const text of cells) {
    const cell = document.createElement(tag);
    cell.textContent = text;
    tr.append(cell);
  }
  return tr;
}

function fillRows(table, rows) {
  table.replaceChildren(...rows.map((cells) => {
    const tr = row(cells);
    if (cells.length > 2) tr.lastChild.className = 'muted';
    return tr;
  }));
}
