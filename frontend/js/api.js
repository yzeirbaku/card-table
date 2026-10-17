const base = () => window.BACKEND_URL;

async function request(path, options) {
  let res;
  try {
    res = await fetch(`${base()}${path}`, options);
  } catch {
    throw new Error("Can't reach the server");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Something went wrong');
  return data;
}

export const fetchGames = () => request('/games');

export async function createRoom(game, players) {
  const { code } = await request('/rooms', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ game, players }),
  });
  return code;
}

export function socketUrl(code, name, token) {
  const url = new URL(`${base()}/rooms/${code}/ws`);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.searchParams.set('name', name);
  if (token) url.searchParams.set('token', token);
  return url.toString();
}
