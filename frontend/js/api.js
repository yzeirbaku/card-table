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

export function socketUrl(code, name, token, session) {
  const url = new URL(`${base()}/rooms/${code}/ws`);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.searchParams.set('name', name);
  if (token) url.searchParams.set('token', token);
  if (session) url.searchParams.set('session', session);
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
