import {
  sqliteTable,
  text,
  integer,
  index,
} from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";
import { users } from "./users.ts";

// ── Agent Roles ─────────────────────────────────────────────────────

export const agentRoles = sqliteTable("agent_role", {
  id: text("id")
    .primaryKey()
    .$defaultFn(() => crypto.randomUUID()),
  userId: text("user_id")
    .notNull()
    .unique()
    .references(() => users.id, { onDelete: "cascade" }),
  name: text("name").notNull().default("product_analyst"), // developer | designer | product_analyst | default
  turboMode: integer("turbo_mode", { mode: "boolean" }).notNull().default(false),
  createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
});

// ── Conversations ───────────────────────────────────────────────────

export const conversations = sqliteTable(
  "conversation",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    userId: text("user_id").references(() => users.id, {
      onDelete: "cascade",
    }),
    title: text("title"),
    projectId: text("project_id"), // FK set in relations (circular dep)
    designCanvasId: text("design_canvas_id"), // FK set in relations
    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  },
  (t) => [
    index("conv_user_idx").on(t.userId),
    index("conv_project_idx").on(t.projectId),
  ]
);

// ── Messages ────────────────────────────────────────────────────────

export const messages = sqliteTable(
  "message",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    conversationId: text("conversation_id")
      .notNull()
      .references(() => conversations.id, { onDelete: "cascade" }),
    role: text("role").notNull(), // user | assistant | system
    content: text("content").notNull(),
    contentIfFile: text("content_if_file", { mode: "json" }).default([]),
    userRole: text("user_role").default("default"),
    isPartial: integer("is_partial", { mode: "boolean" }).notNull().default(false),
    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    lastUpdated: integer("last_updated", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  },
  (t) => [
    index("msg_conv_created_idx").on(t.conversationId, t.createdAt),
    index("msg_conv_partial_idx").on(t.conversationId, t.isPartial),
  ]
);

// ── Chat Files ──────────────────────────────────────────────────────

export const chatFiles = sqliteTable(
  "chat_file",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    conversationId: text("conversation_id")
      .notNull()
      .references(() => conversations.id, { onDelete: "cascade" }),
    messageId: text("message_id").references(() => messages.id, {
      onDelete: "cascade",
    }),
    filePath: text("file_path").notNull(),
    originalFilename: text("original_filename").notNull(),
    fileType: text("file_type").default(""),
    fileSize: integer("file_size").notNull().default(0),
    uploadedAt: integer("uploaded_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  },
  (t) => [index("chatfile_conv_idx").on(t.conversationId)]
);

// ── Model Selections ────────────────────────────────────────────────

export const modelSelections = sqliteTable("model_selection", {
  id: text("id")
    .primaryKey()
    .$defaultFn(() => crypto.randomUUID()),
  userId: text("user_id")
    .notNull()
    .unique()
    .references(() => users.id, { onDelete: "cascade" }),
  selectedModel: text("selected_model")
    .notNull()
    .default("gpt-5-mini"),
  createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
});
