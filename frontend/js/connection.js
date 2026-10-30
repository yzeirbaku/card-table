// Server close codes that end the connection for good, with what to tell the player.
// null = use the reason the server sent. `forget` = the seat token is no good any more.
const FINAL = {
  4404: { message: 'No table with that code', forget: true },
  4410: { message: 'That table has closed', forget: true },
  4400: { message: null, forget: true },
  4409: { message: null, forget: true },
  4000: { message: 'This seat was opened somewhere else', forget: false },
  4401: { message: 'You were signed out. Sign in again', forget: false, signedOut: true },
};
const RETRY_MS = [500, 1000, 2000, 4000, 8000];

/** One player's WebSocket to a room: saves the seat token, reconnects after drops. */
export class RoomConnection {
  constructor({ code, store, urlFor, onWelcome, onState, onError, onReconnecting, onClosed, onReaction = () => {},
    // Wrap setTimeout: a stored browser setTimeout called as a method throws "Illegal invocation".
    WebSocketImpl = globalThis.WebSocket, wait = (fn, ms) => setTimeout(fn, ms) }) {
    Object.assign(this, { code, store, urlFor, onWelcome, onState, onError, onReconnecting, onClosed, onReaction, WebSocketImpl, wait });
    this.stopped = false;
    this.attempt = 0;
    this.opened = false; // has any socket opened since connect()?
    this.ws = null;
  }

  connect() {
    const ws = new this.WebSocketImpl(this.url(this.store.getToken(this.code)));
    this.ws = ws;
    ws.onopen = () => {
      if (this.stopped || ws !== this.ws) return;
      this.opened = true;
      this.attempt = 0;
      this.onReconnecting(false);
    };
    ws.onmessage = (event) => {
      if (this.stopped || ws !== this.ws) return;
      this.handle(event.data);
    };
    ws.onclose = (event) => {
      if (this.stopped || ws !== this.ws) return;
      const final = FINAL[event.code];
      if (final?.signedOut) this.store.clearSession();
      if (final) return this.finish(final.message ?? (event.reason || 'Disconnected'), final.forget);
      if (!this.opened) return this.finish("Can't reach the server", false);
      this.onReconnecting(true);
      const delay = RETRY_MS[Math.min(this.attempt, RETRY_MS.length - 1)];
      this.attempt += 1;
      this.wait(() => { if (!this.stopped) this.connect(); }, delay);
    };
  }

  handle(data) {
    let msg;
    try {
      msg = JSON.parse(data);
    } catch {
      return;
    }
    if (!msg || typeof msg !== 'object') return;
    if (msg.type === 'welcome') {
      this.store.setToken(this.code, msg.token);
      this.store.setCurrentRoom(this.code);
      this.onWelcome(msg.player_id);
    } else if (msg.type === 'state') {
      this.onState(msg);
    } else if (msg.type === 'error') {
      this.onError(msg.message);
    } else if (msg.type === 'reaction') {
      this.onReaction(msg.player_id, msg.reaction);
    }
  }

  /** Send a message to the server; false if the socket isn't open right now. */
  send(message) {
    if (this.ws?.readyState !== this.WebSocketImpl.OPEN) return false;
    this.ws.send(JSON.stringify(message));
    return true;
  }

  /** Give up the seat for good. The server must hear it even if our socket isn't open right now. */
  leave() {
    const token = this.store.getToken(this.code); // read before forgetting
    const ws = this.ws;
    this.stopped = true; // also turns any pending retry into a no-op
    const sendLeave = (socket) => {
      socket.send(JSON.stringify({ type: 'leave' }));
      socket.close();
    };
    if (ws?.readyState === this.WebSocketImpl.OPEN) {
      sendLeave(ws);
    } else if (ws?.readyState === 0) {
      // Still connecting: keep this socket, say goodbye once it opens.
      ws.onmessage = null;
      ws.onclose = null;
      ws.onopen = () => sendLeave(ws);
    } else if (token) {
      // Closed, retry pending: open one last socket just to leave.
      const last = new this.WebSocketImpl(this.url(token));
      last.onopen = () => sendLeave(last);
      last.onmessage = () => {};
      last.onclose = () => {};
    }
    this.forget();
  }

  url(token) {
    return this.urlFor(this.code, this.store.getName(), token, this.store.getSession()?.token ?? null);
  }

  close() {
    this.stopped = true;
    this.ws?.close();
  }

  finish(message, forget) {
    this.stopped = true;
    if (forget) this.forget();
    this.onClosed(message);
  }

  forget() {
    this.store.clearToken(this.code);
    this.store.setCurrentRoom(null);
  }
}
