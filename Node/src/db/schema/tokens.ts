import {
  sqliteTable,
  text,
  integer,
  real,
  index,
} from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";
import { users } from "./users.ts";

// ── Token Usage ─────────────────────────────────────────────────────

export const tokenUsage = sqliteTable(
  "token_usage",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    userId: text("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    projectId: text("project_id"), // FK to projects
    conversationId: text("conversation_id"), // FK to conversations
    provider: text("provider").notNull(), // openai | anthropic | xai | google
    model: text("model").notNull(),
    inputTokens: integer("input_tokens").notNull().default(0),
    outputTokens: integer("output_tokens").notNull().default(0),
    totalTokens: integer("total_tokens").notNull().default(0),
    timestamp: integer("timestamp", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    requestId: text("request_id"),
    cost: real("cost"),
  },
  (t) => [
    index("tu_user_ts_idx").on(t.userId, t.timestamp),
    index("tu_project_ts_idx").on(t.projectId, t.timestamp),
    index("tu_conv_ts_idx").on(t.conversationId, t.timestamp),
    index("tu_provider_model_idx").on(t.provider, t.model),
  ]
);
