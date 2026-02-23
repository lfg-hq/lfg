import type { ServerWebSocket } from "bun";
import type { WsData, WsConnection, WSOutgoing } from "./types.ts";

// Maps userId → Set of active connections (one user can have multiple tabs)
const connectionsByUser = new Map<string, Set<WsConnection>>();

// Maps ws object → connection (for fast lookup in message handlers)
const connectionsByWs = new WeakMap<ServerWebSocket<WsData>, WsConnection>();

export function registerConnection(conn: WsConnection): void {
  let set = connectionsByUser.get(conn.userId);
  if (!set) {
    set = new Set();
    connectionsByUser.set(conn.userId, set);
  }
  set.add(conn);
  connectionsByWs.set(conn.ws, conn);
}

export function unregisterConnection(ws: ServerWebSocket<WsData>): void {
  const conn = connectionsByWs.get(ws);
  if (!conn) return;

  connectionsByWs.delete(ws);
  const set = connectionsByUser.get(conn.userId);
  if (set) {
    set.delete(conn);
    if (set.size === 0) connectionsByUser.delete(conn.userId);
  }
}

export function getConnection(ws: ServerWebSocket<WsData>): WsConnection | undefined {
  return connectionsByWs.get(ws);
}

/** Send a message to all connections for a user */
export function broadcastToUser(userId: string, data: WSOutgoing | object): void {
  const set = connectionsByUser.get(userId);
  if (!set) return;
  const text = JSON.stringify(data);
  for (const conn of set) {
    try {
      conn.ws.send(text);
    } catch {
      // Connection may have closed — will be cleaned up on disconnect
    }
  }
}

/** Send to a single ws connection */
export function send(ws: ServerWebSocket<WsData>, data: WSOutgoing | object): void {
  try {
    ws.send(JSON.stringify(data));
  } catch {
    // ignore send errors on closed sockets
  }
}
