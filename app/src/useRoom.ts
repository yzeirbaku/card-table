import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';
import { wsUrl } from './config';
import type { Action, PlayerView, ServerMessage, TableView } from './protocol';
import { clearSeat, loadSeat, saveSeat } from './seat';

export type RoomStatus = 'connecting' | 'open' | 'reconnecting' | 'closed';

/** Close codes after which retrying is pointless (see backend/app/main.py). */
const isFatalClose = (code: number) => code === 4000 || (code >= 4400 && code < 4500);

export function useRoom(code: string, name: string) {
  const [playerId, setPlayerId] = useState<string | null>(null);
  const [players, setPlayers] = useState<PlayerView[]>([]);
  const [view, setView] = useState<TableView | null>(null);
  const [status, setStatus] = useState<RoomStatus>('connecting');
  const [fatal, setFatal] = useState<string | null>(null);
  const [lastError, setLastError] = useState<{ message: string; at: number } | null>(null);

  const socket = useRef<WebSocket | null>(null);
  const attempt = useRef(0);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stopped = useRef(false);

  const connect = useCallback(async () => {
    if (stopped.current) return;
    if (retryTimer.current) {
      clearTimeout(retryTimer.current);
      retryTimer.current = null;
    }
    const token = await loadSeat(code);
    if (stopped.current) return;
    const query = `name=${encodeURIComponent(name)}${token ? `&token=${encodeURIComponent(token)}` : ''}`;
    const ws = new WebSocket(wsUrl(`/rooms/${code}/ws?${query}`));
    socket.current = ws;

    ws.onopen = () => {
      attempt.current = 0;
      setStatus('open');
    };
    ws.onmessage = (event) => {
      const msg = JSON.parse(String(event.data)) as ServerMessage;
      if (msg.type === 'welcome') {
        setPlayerId(msg.player_id);
        void saveSeat(code, msg.token);
      } else if (msg.type === 'state') {
        setPlayers(msg.players);
        setView(msg.view);
      } else {
        setLastError({ message: msg.message, at: Date.now() });
      }
    };
    ws.onclose = (event) => {
      if (socket.current !== ws) return; // a newer connection replaced this one
      socket.current = null;
      if (stopped.current) return;
      if (isFatalClose(event.code)) {
        setFatal(event.reason || 'Disconnected from the room');
        setStatus('closed');
        return;
      }
      setStatus('reconnecting');
      const delay = Math.min(1000 * 2 ** attempt.current, 10_000);
      attempt.current += 1;
      retryTimer.current = setTimeout(() => void connect(), delay);
    };
  }, [code, name]);

  useEffect(() => {
    stopped.current = false;
    void connect();
    // Phones drop sockets when locked; reconnect as soon as we're back.
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active' && socket.current === null && !stopped.current) {
        attempt.current = 0;
        void connect();
      }
    });
    return () => {
      stopped.current = true;
      sub.remove();
      if (retryTimer.current) clearTimeout(retryTimer.current);
      socket.current?.close();
      socket.current = null;
    };
  }, [connect]);

  const send = useCallback((action: Action) => {
    const ws = socket.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'action', action }));
    } else {
      setLastError({ message: 'Not connected - reconnecting…', at: Date.now() });
    }
  }, []);

  const leave = useCallback(() => {
    stopped.current = true;
    const ws = socket.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'leave' }));
    ws?.close();
    socket.current = null;
    void clearSeat(code);
  }, [code]);

  return { playerId, players, view, status, fatal, lastError, send, leave };
}
