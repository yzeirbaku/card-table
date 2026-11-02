const base = () => window.BACKEND_URL;

async function request(path, options) {
  let res;
  try {
    res = await fetch(`${base()}${path}`, options);
  } catch {
    throw new Error("Can't reach the server");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(typeof data.detail === 'string' ? data.detail : 'Something went wrong');
    err.status = res.status;
    throw err;
  }
  return data;
}

let games = null; // asked once (at startup), so the New table sheet opens with the list in it

/** The games on offer. A failed request is asked again next time. */
export function fetchGames() {
  games ??= request('/games').catch((err) => {
    games = null;
    throw err;
  });
  return games;
}

export async function createRoom(game, players) {
  const { code } = await request('/rooms', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ game, players }),
  });
  return code;
}

/** signedIn: the socket's first message will be the session (never in the URL: URLs end up in logs). */
export function socketUrl(code, name, token, signedIn) {
  const url = new URL(`${base()}/rooms/${code}/ws`);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.searchParams.set('name', name);
  if (token) url.searchParams.set('token', token);
  if (signedIn) url.searchParams.set('signed_in', '1');
  return url.toString();
}

// ---- accounts: the session token goes as a bearer header (not a cookie: the backend is another site) ----

const json = (body) => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
const bearer = (token) => ({ headers: { Authorization: `Bearer ${token}` } });

/** Both return { token, username }: signing up also signs you in. */
export const register = (username, password) => request('/auth/register', json({ username, password }));
export const login = (username, password) => request('/auth/login', json({ username, password }));

export const logout = (token) => request('/auth/logout', { method: 'POST', ...bearer(token) });

/** { username } for a live session; an error with status 401 once it's gone. */
export const me = (token) => request('/me', bearer(token));

export const fetchStats = (username) => request(`/stats/${encodeURIComponent(username)}`);

/** { solo: [...], teams: [...] }, each entry { username, won, lost, ranked }. */
export const fetchLeaderboard = () => request('/leaderboard');

const part = encodeURIComponent;
const send = (method, token, body) => ({
  method,
  headers: { Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
  ...(body ? { body: JSON.stringify(body) } : {}),
});

// ---- friends: each call resolves to the overview { friends, incoming, outgoing } ----

export const fetchFriends = (token) => request('/friends', bearer(token));
/** The overview plus `result` (what the request turned into). */
export const requestFriend = (token, username) => request('/friends/requests', send('POST', token, { username }));
export const acceptFriend = (token, username) => request(`/friends/requests/${part(username)}/accept`, send('POST', token));
export const declineFriend = (token, username) => request(`/friends/requests/${part(username)}/decline`, send('POST', token));
export const cancelRequest = (token, username) => request(`/friends/requests/${part(username)}`, send('DELETE', token));
export const removeFriend = (token, username) => request(`/friends/${part(username)}`, send('DELETE', token));

// ---- invites ----

export const inviteFriend = (token, code, username) => request(`/rooms/${part(code)}/invite`, send('POST', token, { username }));
/** [{ from, game, players, code }] */
export const fetchInvites = (token) => request('/invites', bearer(token));
export const dismissInvite = (token, code) => request(`/invites/${part(code)}/dismiss`, send('POST', token));

// ---- push ----

/** { key } (base64url), or { key: null } when the server can't push. */
export const fetchPushKey = () => request('/push/key');
export const pushSubscribe = (token, subscription) => request('/push/subscribe', send('POST', token, { subscription }));
export const pushUnsubscribe = (endpoint) => request('/push/unsubscribe', json({ endpoint }));
/** { on } */
export const pushStatus = (token, endpoint) => request('/push/status', send('POST', token, { endpoint }));

/** From `username`'s side: { against: { won, lost }, together: { won, lost } }. */
export const fetchHeadToHead = (username, other) =>
  request(`/head-to-head/${encodeURIComponent(username)}?with=${encodeURIComponent(other)}`);
