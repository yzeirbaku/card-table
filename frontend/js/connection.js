// Server close codes that end the connection for good, with what to tell the player.
// null = use the reason the server sent. `forget` = the seat token is no good any more.
const FINAL = {
  4404: { message: 'No table with that code', forget: true },
  4410: { message: 'That table has closed', forget: true },
  4400: { message: null, forget: true },
  4409: { message: null, forget: true },
  4000: { message: 'This seat was opened somewhere else', forget: false },
};
const RETRY_MS = [500, 1000, 2000, 4000, 8000];

/** One player's WebSocket to a room: saves the seat token, reconnects after drops. */
export class RoomConnection {
  constructor({ code, store, urlFor, onWelcome, onState, onError, onReconnecting, onClosed,
    WebSocketImpl = globalThis.WebSocket, wait = setTimeout }) {
    Object.assign(this, { code, store, urlFor, onWelcome, onState, onError, onReconnecting, onClosed, WebSocketImpl, wait });
    this.stopped = false;
    this.attempt = 0;
    this.opened = false; // has any socket opened since connect()?
    this.ws = null;
  }

  connect() {
    const ws = new this.WebSocketImpl(this.urlFor(this.code, this.store.getName(), this.store.getToken(this.code)));
    this.ws = ws;
    ws.onopen = () => {
      this.opened = true;
      this.attempt = 0;
      this.onReconnecting(false);
    };
    ws.onmessage = (event) => this.handle(event.data);
    ws.onclose = (event) => {
      if (this.stopped || ws !== this.ws) return;
      const final = FINAL[event.code];
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
    if (msg.type === 'welcome') {
      this.store.setToken(this.code, msg.token);
      this.store.setCurrentRoom(this.code);
      this.onWelcome(msg.player_id);
    } else if (msg.type === 'state') {
      this.onState(msg);
    } else if (msg.type === 'error') {
      this.onError(msg.message);
    }
  }

  leave() {
    if (this.ws?.readyState === this.WebSocketImpl.OPEN) this.ws.send(JSON.stringify({ type: 'leave' }));
    this.close();
    this.forget();
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
