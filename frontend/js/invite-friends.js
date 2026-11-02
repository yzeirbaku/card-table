import { fetchFriends, inviteFriend } from './api.js';
import { inviteRows } from './social.js';
import { openSheet } from './sheets.js';
import { toast } from './ui.js';

const EMPTY = "You haven't added any friends yet. Add them in your Profile, under Friends, or share the table code.";

/** The Invite friends sheet at a lobby: a row per friend, Invite or Here. `open(state)` shows it;
 *  `update(state)` re-renders it for each new lobby state while it is open. */
export function initInviteFriends({ store, gameName }) {
  const sheet = document.getElementById('sheet-invite');
  const sub = sheet.querySelector('.invite-sub');
  const list = sheet.querySelector('.friend-list');
  let friends = [];
  let loaded = false;
  let current = null;
  let invited = new Set(); // lowercase names invited while this sheet has been open

  const key = (name) => name.toLowerCase();

  function render() {
    if (!current) return;
    const free = current.room.seats - current.players.length;
    sub.textContent = loaded && friends.length === 0
      ? EMPTY
      : `${gameName(current.room.game)} · ${free} ${free === 1 ? 'seat' : 'seats'} free. They get a notification.`;
    list.replaceChildren(...inviteRows(friends, current).map(({ name, here }) => {
      const row = document.createElement('div');
      row.className = 'friend-row';
      const ring = document.createElement('span');
      ring.className = 'ring';
      ring.textContent = name.charAt(0).toUpperCase();
      const who = document.createElement('span');
      who.className = 'who';
      who.textContent = name;
      row.append(ring, who);
      if (here) {
        const tag = document.createElement('span');
        tag.className = 'row-tag';
        tag.textContent = 'Here';
        row.append(tag);
      } else if (invited.has(key(name))) {
        const done = document.createElement('button');
        done.type = 'button';
        done.className = 'row-btn done';
        done.disabled = true;
        done.textContent = 'Invited ✓';
        row.append(done);
      } else {
        const go = document.createElement('button');
        go.type = 'button';
        go.className = 'row-btn go';
        go.textContent = 'Invite';
        go.addEventListener('click', () => invite(name, go));
        row.append(go);
      }
      return row;
    }));
  }

  async function invite(name, btn) {
    const session = store.getSession();
    if (!session || !current) return;
    btn.disabled = true;
    try {
      await inviteFriend(session.token, current.code, name);
      invited.add(key(name));
      render();
    } catch (err) {
      btn.disabled = false;
      toast(err.message);
    }
  }

  return {
    async open(state) {
      const session = store.getSession();
      if (!session) return;
      current = state;
      invited = new Set();
      friends = [];
      loaded = false;
      render();
      openSheet('sheet-invite');
      try {
        const overview = await fetchFriends(session.token);
        friends = overview.friends;
        loaded = true;
        render();
      } catch (err) {
        toast(err.message);
      }
    },
    update(state) {
      current = state;
      if (!sheet.hidden) render();
    },
  };
}
