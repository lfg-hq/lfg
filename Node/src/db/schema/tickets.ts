import {
  sqliteTable,
  text,
  integer,
  real,
  index,
  uniqueIndex,
} from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";
import { users } from "./users.ts";
import { projects } from "./projects.ts";

// ── Ticket Stages ───────────────────────────────────────────────────

export const ticketStages = sqliteTable(
  "ticket_stage",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    projectId: text("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    name: text("name").notNull(),
    color: text("color").notNull().default("#6366f1"),
    order: integer("order").notNull().default(0),
    isDefault: integer("is_default", { mode: "boolean" }).notNull().default(false),
    isCompleted: integer("is_completed", { mode: "boolean" }).notNull().default(false),
    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  },
  (t) => [
    uniqueIndex("ts_project_name_unique").on(t.projectId, t.name),
    index("ts_project_order_idx").on(t.projectId, t.order),
  ]
);

// ── Project Tickets ─────────────────────────────────────────────────

export const projectTickets = sqliteTable(
  "project_ticket",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    projectId: text("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    name: text("name").notNull(),
    status: text("status").notNull().default("open"), // open | in_progress | review | done | failed | blocked
    stageId: text("stage_id").references(() => ticketStages.id, {
      onDelete: "set null",
    }),
    description: text("description").notNull(),
    priority: text("priority").notNull().default("Medium"), // High | Medium | Low
    role: text("role").notNull().default("user"), // agent | user

    // Enhanced details
    details: text("details", { mode: "json" }).default({}),
    uiRequirements: text("ui_requirements", { mode: "json" }).default({}),
    componentSpecs: text("component_specs", { mode: "json" }).default({}),
    acceptanceCriteria: text("acceptance_criteria", { mode: "json" }).default([]),
    dependencies: text("dependencies", { mode: "json" }).default([]),

    // Document references
    sourceDocumentId: text("source_document_id"), // FK to projectFiles
    conversationId: text("conversation_id"), // FK to conversations

    notes: text("notes").default(""),

    // Execution metadata
    complexity: text("complexity").notNull().default("medium"), // simple | medium | complex
    requiresWorktree: integer("requires_worktree", { mode: "boolean" }).notNull().default(true),

    // Git/GitHub metadata
    githubBranch: text("github_branch"),
    githubCommitSha: text("github_commit_sha"),
    githubPrUrl: text("github_pr_url"),
    githubPrNumber: integer("github_pr_number"),
    githubMergeStatus: text("github_merge_status"), // merged | conflict | failed | pending | pr_open | reverted
    githubMergeCommitSha: text("github_merge_commit_sha"),
    githubLastRevertSha: text("github_last_revert_sha"),
    githubRevertedAt: integer("github_reverted_at", { mode: "timestamp" }),
    githubRevertedById: text("github_reverted_by_id").references(
      () => users.id,
      { onDelete: "set null" }
    ),

    // Linear integration
    linearIssueId: text("linear_issue_id"),
    linearIssueUrl: text("linear_issue_url"),
    linearState: text("linear_state"),
    linearPriority: integer("linear_priority"),
    linearAssigneeId: text("linear_assignee_id"),
    linearSyncedAt: integer("linear_synced_at", { mode: "timestamp" }),
    linearSyncEnabled: integer("linear_sync_enabled", { mode: "boolean" }).notNull().default(true),

    // Queue status
    queueStatus: text("queue_status")
      .notNull()
      .default("none"), // none | queued | executing
    queuedAt: integer("queued_at", { mode: "timestamp" }),
    queueTaskId: text("queue_task_id"),

    // Execution time
    executionTimeSeconds: real("execution_time_seconds")
      .notNull()
      .default(0),
    lastExecutionAt: integer("last_execution_at", { mode: "timestamp" }),

    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  },
  (t) => [
    index("pt_project_idx").on(t.projectId),
    index("pt_stage_idx").on(t.stageId),
    index("pt_conv_idx").on(t.conversationId),
  ]
);

// ── Ticket Merge History ────────────────────────────────────────────

export const ticketMergeHistory = sqliteTable(
  "ticket_merge_history",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    ticketId: text("ticket_id")
      .notNull()
      .references(() => projectTickets.id, { onDelete: "cascade" }),
    action: text("action").notNull(), // merged | reverted
    mergeCommitSha: text("merge_commit_sha").notNull(),
    revertCommitSha: text("revert_commit_sha"),
    performedById: text("performed_by_id").references(() => users.id, {
      onDelete: "set null",
    }),
    filesChanged: text("files_changed", { mode: "json" }).default([]),
    linesAdded: integer("lines_added").notNull().default(0),
    linesRemoved: integer("lines_removed").notNull().default(0),
    commitMessage: text("commit_message").default(""),
    commitAuthor: text("commit_author").default(""),
    commitDate: integer("commit_date", { mode: "timestamp" }),
    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  },
  (t) => [
    index("tmh_ticket_idx").on(t.ticketId, t.createdAt),
    index("tmh_sha_idx").on(t.mergeCommitSha),
  ]
);

// ── Project Todo Lists ──────────────────────────────────────────────

export const projectTodoLists = sqliteTable(
  "project_todo_list",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    ticketId: text("ticket_id")
      .notNull()
      .references(() => projectTickets.id, { onDelete: "cascade" }),
    description: text("description").notNull(),
    status: text("status").notNull().default("pending"), // pending | in_progress | success | fail
    order: integer("order").notNull().default(0),
    cliTaskId: text("cli_task_id"),
    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  },
  (t) => [index("ptl_ticket_idx").on(t.ticketId)]
);

// ── Ticket Logs ─────────────────────────────────────────────────────

export const ticketLogs = sqliteTable(
  "ticket_log",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    ticketId: text("ticket_id")
      .notNull()
      .references(() => projectTickets.id, { onDelete: "cascade" }),
    taskId: text("task_id").references(() => projectTodoLists.id, {
      onDelete: "set null",
    }),
    logType: text("log_type").notNull().default("command"), // command | user_message | ai_response
    command: text("command").notNull(),
    explanation: text("explanation"),
    output: text("output"),
    exitCode: integer("exit_code"),
    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  },
  (t) => [
    index("tl_ticket_idx").on(t.ticketId),
    index("tl_task_idx").on(t.taskId),
    index("tl_type_idx").on(t.logType),
  ]
);

// ── Ticket Attachments ──────────────────────────────────────────────

export const projectTicketAttachments = sqliteTable(
  "project_ticket_attachment",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    ticketId: text("ticket_id")
      .notNull()
      .references(() => projectTickets.id, { onDelete: "cascade" }),
    uploadedById: text("uploaded_by_id").references(() => users.id, {
      onDelete: "set null",
    }),
    filePath: text("file_path").notNull(),
    originalFilename: text("original_filename").default(""),
    fileType: text("file_type").default(""),
    fileSize: integer("file_size").notNull().default(0),
    uploadedAt: integer("uploaded_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  },
  (t) => [index("pta_ticket_idx").on(t.ticketId)]
);
