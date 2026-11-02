import { dismissInvite, fetchInvites } from './api.js';
import { closeSheets, openSheet } from './sheets.js';
import { toast } from './ui.js';

/** The envelope on the main screen and its Invites sheet: the invites waiting for you, Join or ✕.
 *  `refresh()` asks the server again; signed out (or none waiting) the envelope is hidden. */
export function initInvites({ store, onJoin }) {
  const button = document.getElementById('btn-invites');
  const badge = button.querySelector('.badge');
  const sheet = document.getElementById('sheet-invites');
  const list = sheet.querySelector('.friend-list');
  let invites = [];
  let asked = 0; // the newest request; an older one's answer is dropped

  function show(next) {
    invites = next;
    button.hidden = invites.length === 0;
    badge.textContent = String(invites.length);
    if (sheet.hidden) return;
    if (invites.length === 0) closeSheets();
    else render();
  }

  function render() {
    list.replaceChildren(...invites.map((invite) => {
      const row = document.createElement('div');
      row.className = 'friend-row';
      const ring = document.createElement('span');
      ring.className = 'ring';
      ring.textContent = invite.from.charAt(0).toUpperCase();
      const who = document.createElement('span');
      who.className = 'who';
      who.textContent = invite.from;
      const what = document.createElement('small');
      what.textContent = `${invite.game} · ${invite.players} players`;
      who.append(what);
      const x = document.createElement('button');
      x.type = 'button';
      x.className = 'row-x';
      x.textContent = '✕';
      x.setAttribute('aria-label', `Dismiss ${invite.from}'s invite`);
      x.addEventListener('click', () => dismiss(invite.code, x));
      const join = document.createElement('button');
      join.type = 'button';
      join.className = 'row-btn go';
      join.textContent = 'Join';
      join.addEventListener('click', () => {
        closeSheets();
        onJoin(invite.code, invite.from);
      });
      row.append(ring, who, x, join);
      return row;
    }));
  }

  async function refresh() {
    const mine = ++asked;
    const session = store.getSession();
    if (!session) {
      show([]);
      return;
    }
    try {
      const next = await fetchInvites(session.token);
      if (mine === asked) show(next);
    } catch {
      // quietly keep what shows: this runs in the background, often while the server is away
    }
  }

  async function dismiss(code, btn) {
    const session = store.getSession();
    if (!session) return;
    btn.disabled = true;
    try {
      await dismissInvite(session.token, code);
      asked += 1; // an answer still on its way may hold this invite
      show(invites.filter((invite) => invite.code !== code));
    } catch (err) {
      btn.disabled = false;
      toast(err.message);
    }
  }

  button.addEventListener('click', () => {
    render();
    openSheet('sheet-invites');
  });

  return { refresh };
}
