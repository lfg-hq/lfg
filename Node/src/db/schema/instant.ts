import { sqliteTable, text, integer, index, uniqueIndex } from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";
import { users } from "./users.ts";
import { projects } from "./projects.ts";
import { sandboxes } from "./sandbox.ts";
import { conversations } from "./chat.ts";

export const instantApps = sqliteTable(
  "instant_app",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    appId: text("app_id")
      .notNull()
      .unique()
      .$defaultFn(() => crypto.randomUUID()),
    name: text("name").notNull(),
    description: text("description"),
    status: text("status").notNull().default("gathering"), // gathering | building | running | stopped | error
    requirements: text("requirements"),
    envVars: text("env_vars", { mode: "json" })
      .$type<Record<string, string>>()
      .default(sql`'{}'`),
    previewUrl: text("preview_url"),
    metadata: text("metadata", { mode: "json" })
      .$type<Record<string, unknown>>()
      .default(sql`'{}'`),

    projectId: text("project_id").references(() => projects.id, { onDelete: "cascade" }),
    userId: text("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    sandboxId: text("sandbox_id").references(() => sandboxes.id, { onDelete: "set null" }),
    conversationId: text("conversation_id").references(() => conversations.id, { onDelete: "set null" }),

    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  },
  (t) => [
    index("instant_user_idx").on(t.userId),
    index("instant_project_idx").on(t.projectId),
    index("instant_status_idx").on(t.status),
    uniqueIndex("instant_app_id_unique").on(t.appId),
    uniqueIndex("instant_sandbox_unique").on(t.sandboxId),
    uniqueIndex("instant_conversation_unique").on(t.conversationId),
  ]
);
