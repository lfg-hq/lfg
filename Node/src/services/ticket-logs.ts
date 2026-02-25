/**
 * Shared ticket logging utilities.
 *
 * Extracted from ticket-executor.ts so both the executor worker and the
 * CLI callback API can insert logs + broadcast to the frontend via WS.
 */

import { db } from "../config/db.ts";
import { ticketLogs } from "../db/schema/tickets.ts";
import { broadcastToUser } from "../ws/connection-manager.ts";

/**
 * Insert a log row for a ticket and broadcast it to the owner via WebSocket.
 */
export async function addLog(
  ticketId: string,
  message: string,
  logType: "command" | "ai_response" | "user_message" | "cli_error",
  userId?: string
) {
  const [inserted] = await db.insert(ticketLogs).values({
    ticketId,
    logType,
    command: message.slice(0, 2000),
  }).returning();

  if (userId) {
    broadcastToUser(userId, {
      type: "ticket_log",
      ticketId,
      log: {
        id: inserted?.id,
        type: logType,
        message: message.slice(0, 2000),
        createdAt: inserted?.createdAt ?? new Date().toISOString(),
      },
    });
  }
}

/**
 * Format a tool_use block for log display, matching Django's approach.
 */
export function formatToolUse(name: string, input: Record<string, unknown>): string {
  switch (name) {
    case "Bash":
      return `$ ${(input.command as string) ?? ""}`.slice(0, 500);
    case "Read":
      return `📄 Read: ${input.file_path ?? ""}`;
    case "Write":
      return `✏️ Write: ${input.file_path ?? ""}`;
    case "Edit":
      return `✏️ Edit: ${input.file_path ?? ""}`;
    case "Grep":
    case "Glob":
      return `🔍 ${name}: ${input.pattern ?? ""}`;
    case "TodoWrite":
      return `📋 TodoWrite: updating tasks`;
    default:
      return `🔧 ${name}`;
  }
}
