import { tool, zodSchema } from "ai";
import { z } from "zod";

let _wsBroadcast: ((userId: string, data: object) => void) | null = null;
export function setWsBroadcast(fn: (userId: string, data: object) => void) {
  _wsBroadcast = fn;
}

export const broadcastToUser = tool({
  description: "Send a real-time notification or UI update to the user via WebSocket.",
  inputSchema: zodSchema(z.object({
    userId: z.string(),
    type: z.string(),
    message: z.string(),
    data: z.record(z.string(), z.unknown()).optional(),
  })),
  execute: async ({ userId, type, message, data }) => {
    if (_wsBroadcast) _wsBroadcast(userId, { type, message, ...(data ?? {}) });
    return { sent: true };
  },
});

export const lookupTechnologySpecs = tool({
  description: "Look up documentation or best practices for a technology before recommending it.",
  inputSchema: zodSchema(z.object({
    technology: z.string().describe("Technology name e.g. 'Next.js 15', 'Drizzle ORM'"),
    query: z.string().describe("What to look up e.g. 'setup guide', 'authentication patterns'"),
  })),
  execute: async ({ technology, query }) => {
    return {
      technology,
      query,
      note: "Web search not available in this environment. Use training knowledge and recommend the user verify against official docs.",
    };
  },
});
