// ── WebSocket message types (matches existing chat.js format) ─────────────────

export type WSIncoming =
  | { type: "message"; message: string; conversation_id?: string; project_id?: string; turbo_mode?: boolean; user_role?: string }
  | { type: "stop_generation"; conversation_id?: string }
  | { type: "heartbeat_ack" }
  | { type: "sync_state"; conversation_id?: string };

export type WSOutgoing =
  | { type: "ai_chunk"; chunk: string; isFinal: boolean; conversationId?: string; projectId?: string; isNotification?: boolean; notificationType?: string; functionName?: string; contentChunk?: string; isComplete?: boolean; fileId?: string; fileName?: string; fileType?: string }
  | { type: "chat_history"; messages: ChatHistoryMessage[] }
  | { type: "heartbeat" }
  | { type: "stop_confirmed" }
  | { type: "sync_state_response"; isStreaming: boolean; conversationId?: string }
  | { type: "error"; message: string }
  | { type: "token_usage_updated" }
  | { type: "document_stream"; documentType: string; name?: string; content: string; isFinal: boolean }
  | { type: "conversation_created"; conversationId: string };

export interface ChatHistoryMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt: Date | null;
}

// Per-connection state
export interface WsConnection {
  ws: import("bun").ServerWebSocket<WsData>;
  userId: string;
  conversationId?: string;
  projectId?: string;
  isStreaming: boolean;
  stopRequested: boolean;
  abortController?: AbortController;
}

// Data stored on the Bun WebSocket object
export interface WsData {
  sessionId: string;
  userId: string;
}
