import type { ServerWebSocket } from "bun";
import type { WsData, WSIncoming, WsConnection } from "./types.ts";
import {
  registerConnection,
  unregisterConnection,
  getConnection,
  send,
} from "./connection-manager.ts";
import { handleStream } from "../ai/stream-handler.ts";
import { db } from "../config/db.ts";
import { messages, conversations } from "../db/schema/chat.ts";
import { eq, asc, desc } from "drizzle-orm";

const HEARTBEAT_INTERVAL_MS = 20_000;

// Active heartbeat timers by userId+sessionId
const heartbeatTimers = new Map<string, ReturnType<typeof setInterval>>();

export function onOpen(ws: ServerWebSocket<WsData>): void {
  const conn: WsConnection = {
    ws,
    userId: ws.data.userId,
    isStreaming: false,
    stopRequested: false,
  };

  registerConnection(conn);

  // Start heartbeat
  const key = `${ws.data.userId}:${ws.data.sessionId}`;
  const timer = setInterval(() => {
    try {
      ws.send(JSON.stringify({ type: "heartbeat" }));
    } catch {
      clearInterval(timer);
      heartbeatTimers.delete(key);
    }
  }, HEARTBEAT_INTERVAL_MS);
  heartbeatTimers.set(key, timer);
}

export function onClose(ws: ServerWebSocket<WsData>): void {
  // Stop heartbeat
  const key = `${ws.data.userId}:${ws.data.sessionId}`;
  const timer = heartbeatTimers.get(key);
  if (timer) {
    clearInterval(timer);
    heartbeatTimers.delete(key);
  }

  // Abort any in-flight generation
  const conn = getConnection(ws);
  if (conn?.abortController) {
    conn.abortController.abort();
  }

  unregisterConnection(ws);
}

export async function onMessage(ws: ServerWebSocket<WsData>, rawData: string | Buffer): Promise<void> {
  const conn = getConnection(ws);
  if (!conn) return;

  let msg: WSIncoming;
  try {
    msg = JSON.parse(rawData.toString()) as WSIncoming;
  } catch {
    send(ws, { type: "error", message: "Invalid JSON" });
    return;
  }

  if (msg.type === "heartbeat_ack") return;

  if (msg.type === "sync_state") {
    send(ws, {
      type: "sync_state_response",
      isStreaming: conn.isStreaming,
      conversationId: conn.conversationId,
    });
    return;
  }

  if (msg.type === "stop_generation") {
    conn.stopRequested = true;
    conn.abortController?.abort();
    send(ws, { type: "stop_confirmed" });
    return;
  }

  if (msg.type === "message") {
    const { message, conversation_id, project_id, turbo_mode, user_role } = msg;

    if (!message?.trim()) {
      send(ws, { type: "error", message: "Message cannot be empty" });
      return;
    }

    if (conn.isStreaming) {
      send(ws, { type: "error", message: "A response is already being generated" });
      return;
    }

    // Update conversation context — history is loaded by the client via REST API,
    // so we never send chat_history here (it would wipe the user's just-sent message).
    if (conversation_id) {
      conn.conversationId = conversation_id;
    }

    conn.projectId = project_id;
    conn.isStreaming = true;
    conn.stopRequested = false;
    conn.abortController = new AbortController();

    try {
      const result = await handleStream({
        ws,
        userId: conn.userId,
        userMessage: message,
        conversationId: conn.conversationId,
        projectId: conn.projectId,
        turboMode: turbo_mode,
        userRole: user_role,
        abortController: conn.abortController,
      });

      // Update connection with resolved conversationId
      conn.conversationId = result.conversationId;
    } finally {
      conn.isStreaming = false;
      conn.abortController = undefined;
    }
  }
}

async function sendHistory(ws: ServerWebSocket<WsData>, conversationId: string): Promise<void> {
  const rows = await db
    .select()
    .from(messages)
    .where(eq(messages.conversationId, conversationId))
    .orderBy(asc(messages.createdAt))
    .limit(50);

  send(ws, {
    type: "chat_history",
    messages: rows.map((m) => ({
      id: m.id,
      role: m.role as "user" | "assistant" | "system",
      content: m.content,
      createdAt: m.createdAt,
    })),
  });
}
