import { acceptFriend, cancelRequest, declineFriend, fetchFriends, removeFriend, requestFriend } from './api.js';
import { pushIsOn, pushSupport, turnPushOff, turnPushOn } from './push.js';
import { initial } from './stats-format.js';
import { toast } from './ui.js';

// The Friends tab on the Profile page: notifications, add by username, requests, friends, sent.

const EMPTY = { friends: [], incoming: [], outgoing: [] };

const NOTE = {
  'ios-browser': ['📲', 'Add Card Table to your Home Screen to get them: Share, then Add to Home Screen.'],
  blocked: ['🔕', "Blocked for this app in your phone's settings. Allow them there, then come back."],
  unsupported: ['🔕', "This browser can't show notifications"],
};

export function initFriends({ store, openPlayer, onChange }) {
  const pane = document.querySelector('#view-profile [data-pane="friends"]');
  const badge = document.querySelector('#view-profile [data-tab="friends"] .count-badge');
  const notif = pane.querySelector('.notif-box');
  const form = pane.querySelector('.add-friend');
  const input = form.querySelector('input');
  let current = EMPTY;
  let drawn = 0; // the newest notifications row being worked out; an older answer is dropped

  const actions = {
    request: requestFriend,
    accept: acceptFriend,
    decline: declineFriend,
    cancel: cancelRequest,
    remove: removeFriend,
  };

  function overview() {
    return current;
  }

  function apply(next) {
    current = { friends: next.friends, incoming: next.incoming, outgoing: next.outgoing };
    render();
    onChange();
  }

  /** Fetches the overview; a phone with no session has none. Quiet on errors: it runs in the background. */
  async function load() {
    const session = store.getSession();
    if (!session) {
      apply(EMPTY);
      return;
    }
    try {
      const next = await fetchFriends(session.token);
      if (store.getSession()?.token === session.token) apply(next);
    } catch {
      // keep what we had; the next load tries again
    }
  }

  /** One request, then the new overview. True when the server took it. */
  async function act(kind, name) {
    const session = store.getSession();
    if (!session) return false;
    try {
      const result = await actions[kind](session.token, name);
      if (store.getSession()?.token !== session.token) return false;
      apply(result);
      if (kind === 'request') {
        toast(result.result === 'accepted' ? `You and ${name} are friends now` : `Request sent to ${name}`);
      }
      return true;
    } catch (err) {
      toast(err.message);
      return false;
    }
  }

  function render() {
    const { friends, incoming, outgoing } = current;
    badge.textContent = String(incoming.length);
    badge.hidden = incoming.length === 0;
    fillList('incoming', incoming, (entry) => [
      button('Decline', 'row-btn quiet', () => act('decline', entry.username)),
      button('Accept', 'row-btn go', () => act('accept', entry.username)),
    ]);
    fillList('friends', friends, (entry, _who, rowEl) => {
      rowEl.classList.add('link');
      rowEl.tabIndex = 0;
      rowEl.setAttribute('role', 'button');
      rowEl.addEventListener('click', () => openPlayer(entry.username));
      rowEl.addEventListener('keydown', (event) => { if (event.key === 'Enter') openPlayer(entry.username); });
      const chev = document.createElement('span');
      chev.className = 'chev';
      chev.textContent = '›';
      return [chev];
    });
    fillList('outgoing', outgoing, (entry, who) => {
      const small = document.createElement('small');
      small.textContent = 'Waiting for an answer';
      who.append(small);
      return [button('Cancel', 'row-btn quiet', () => act('cancel', entry.username))];
    });
    renderNotif();
  }

  function fillList(key, entries, extras) {
    pane.querySelector(`[data-list-title="${key}"]`).hidden = entries.length === 0;
    const list = pane.querySelector(`[data-list="${key}"]`);
    list.hidden = entries.length === 0;
    list.replaceChildren(...entries.map((entry) => {
      const rowEl = document.createElement('div');
      rowEl.className = 'friend-row';
      const ring = document.createElement('span');
      ring.className = 'ring';
      ring.textContent = initial(entry.username);
      const who = document.createElement('span');
      who.className = 'who';
      who.append(entry.username);
      rowEl.append(ring, who, ...extras(entry, who, rowEl));
      return rowEl;
    }));
  }

  function setNotif({ bell, text, on = false, action = null }) {
    notif.classList.toggle('on', on);
    notif.querySelector('.bell').textContent = bell;
    notif.querySelector('.notif-text').textContent = text;
    const btn = notif.querySelector('.row-btn');
    btn.hidden = !action;
    if (action) {
      btn.textContent = action.label;
      btn.className = `row-btn${action.go ? ' go' : ''}`;
      btn.onclick = action.run;
    }
  }

  async function renderNotif() {
    const session = store.getSession();
    const mine = ++drawn;
    const support = pushSupport();
    if (!session || support !== 'ok') {
      const [bell, text] = NOTE[support] ?? NOTE.unsupported;
      setNotif({ bell, text });
      return;
    }
    const on = await pushIsOn(session.token).catch(() => false);
    if (mine !== drawn) return;
    if (on) {
      setNotif({
        bell: '🔔', text: 'On for this phone', on: true,
        action: { label: 'Turn off', go: false, run: async () => { await turnPushOff(); renderNotif(); } },
      });
    } else {
      setNotif({
        bell: '🔔', text: 'Off on this phone',
        action: {
          label: 'Turn on', go: true,
          run: async () => {
            try {
              await turnPushOn(session.token);
            } catch (err) {
              toast(err.message);
            }
            renderNotif();
          },
        },
      });
    }
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const name = input.value.trim();
    if (!name) return;
    if (await act('request', name)) input.value = '';
  });

  return { load, overview, render, act };
}

function button(label, className, run) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = className;
  b.textContent = label;
  b.addEventListener('click', (event) => {
    event.stopPropagation();
    run();
  });
  return b;
}
