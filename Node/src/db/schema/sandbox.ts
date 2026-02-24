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
import { projectTickets } from "./tickets.ts";

// ── Sandboxes (Mags VM Workspaces) ──────────────────────────────────

export const sandboxes = sqliteTable(
  "sandbox",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),

    // Ownership
    projectId: text("project_id").references(() => projects.id, {
      onDelete: "set null",
    }),
    userId: text("user_id").references(() => users.id, {
      onDelete: "set null",
    }),
    ticketId: text("ticket_id").references(() => projectTickets.id, {
      onDelete: "set null",
    }),

    // Mags VM identifiers
    // magsWorkspaceId is the human-readable name used when creating the VM
    // e.g. "{ticketId}-{uuid8}" — also used as the workspace_id for subsequent runs
    magsWorkspaceId: text("mags_workspace_id").unique(),
    // The request_id returned when the persistent workspace was first created
    magsJobId: text("mags_job_id"),
    // Base workspace ID used as the snapshot to clone from
    magsBaseWorkspaceId: text("mags_base_workspace_id"),

    workspaceType: text("workspace_type").notNull().default("ticket"), // ticket | claude_auth

    // Lifecycle
    status: text("status").notNull().default("ready"), // ready | stopped | error | sleeping

    // Claude Code CLI session for resuming
    cliSessionId: text("cli_session_id"),

    // HTTP preview URL (set after enableUrl() call for dev server)
    previewUrl: text("preview_url"),
    previewPort: integer("preview_port"),

    // Git state
    currentBranch: text("current_branch"),

    // Last exec output tail offset (for polling)
    outputOffset: integer("output_offset").notNull().default(0),

    // Tech stack / run commands (captured by builder)
    techStack: text("tech_stack", { mode: "json" }).$type<{
      language?: string;
      framework?: string;
      packageManager?: string;
      startCommand?: string;
      buildCommand?: string;
      port?: number;
    }>(),

    createdAt: integer("created_at", { mode: "timestamp" })
      .notNull()
      .default(sql`(unixepoch())`),
    updatedAt: integer("updated_at", { mode: "timestamp" })
      .notNull()
      .default(sql`(unixepoch())`),
  },
  (t) => [
    index("sb_project_idx").on(t.projectId),
    index("sb_ticket_idx").on(t.ticketId),
    index("sb_user_idx").on(t.userId),
    uniqueIndex("sb_mags_ws_idx").on(t.magsWorkspaceId),
  ]
);

// ── Server Logs ──────────────────────────────────────────────────────
// Rolling log entries from the dev server running inside the sandbox

export const serverLogs = sqliteTable(
  "server_log",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    sandboxId: text("sandbox_id")
      .notNull()
      .references(() => sandboxes.id, { onDelete: "cascade" }),
    ticketId: text("ticket_id").references(() => projectTickets.id, {
      onDelete: "cascade",
    }),
    level: text("level").notNull().default("info"), // info | error | warn | stdout
    message: text("message").notNull(),
    createdAt: integer("created_at", { mode: "timestamp" })
      .notNull()
      .default(sql`(unixepoch())`),
  },
  (t) => [
    index("sl_sandbox_idx").on(t.sandboxId, t.createdAt),
    index("sl_ticket_idx").on(t.ticketId, t.createdAt),
  ]
);
