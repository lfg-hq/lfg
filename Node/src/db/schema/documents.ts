import {
  sqliteTable,
  text,
  integer,
  index,
  uniqueIndex,
} from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";
import { users } from "./users.ts";
import { projects } from "./projects.ts";

// ── Project Files ───────────────────────────────────────────────────

export const projectFiles = sqliteTable(
  "project_file",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    projectId: text("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    name: text("name").notNull(),
    fileType: text("file_type").notNull(), // prd | implementation | design | test | other
    content: text("content"),
    s3Key: text("s3_key"),
    isActive: integer("is_active", { mode: "boolean" }).notNull().default(true),
    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  },
  (t) => [
    uniqueIndex("pf_project_name_type_unique").on(
      t.projectId,
      t.name,
      t.fileType
    ),
    index("pf_project_type_idx").on(t.projectId, t.fileType),
  ]
);

// ── Project File Versions ───────────────────────────────────────────

export const projectFileVersions = sqliteTable(
  "project_file_version",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    fileId: text("file_id")
      .notNull()
      .references(() => projectFiles.id, { onDelete: "cascade" }),
    versionNumber: integer("version_number").notNull(),
    content: text("content").notNull(),
    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    createdById: text("created_by_id").references(() => users.id, {
      onDelete: "set null",
    }),
    changeDescription: text("change_description"),
  },
  (t) => [
    uniqueIndex("pfv_file_version_unique").on(t.fileId, t.versionNumber),
    index("pfv_file_idx").on(t.fileId),
  ]
);

// ── Tool Call History ───────────────────────────────────────────────

export const toolCallHistory = sqliteTable(
  "tool_call_history",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    projectId: text("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    conversationId: text("conversation_id"),
    messageId: text("message_id"),
    toolName: text("tool_name").notNull(),
    toolInput: text("tool_input", { mode: "json" }).default({}),
    generatedContent: text("generated_content").notNull(),
    contentType: text("content_type")
      .notNull()
      .default("text"),
    metadata: text("metadata", { mode: "json" }).default({}),
    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  },
  (t) => [
    index("tch_project_idx").on(t.projectId),
    index("tch_project_tool_idx").on(t.projectId, t.toolName),
    index("tch_conv_idx").on(t.conversationId),
  ]
);
