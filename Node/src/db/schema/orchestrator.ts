import {
  sqliteTable,
  text,
  integer,
  index,
} from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";
import { users } from "./users.ts";
import { projects } from "./projects.ts";

// ── Agent Runs ──────────────────────────────────────────────────────

export const agentRuns = sqliteTable(
  "agent_run",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    conversationId: text("conversation_id").notNull(), // FK to conversations
    projectId: text("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    userId: text("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),

    triggerMessage: text("trigger_message").notNull(),
    runType: text("run_type")
      .notNull()
      .default("direct_response"), // direct_response | research | single_ticket | pipeline
    plan: text("plan", { mode: "json" }).default({}),
    status: text("status").notNull().default("planning"), // planning | executing | waiting_on_user | completed | failed | cancelled
    orchestratorMessages: text("orchestrator_messages", { mode: "json" }).default([]),

    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    updatedAt: integer("updated_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    completedAt: integer("completed_at", { mode: "timestamp" }),
  },
  (t) => [
    index("ar_conv_status_idx").on(t.conversationId, t.status),
    index("ar_project_status_idx").on(t.projectId, t.status),
  ]
);

// ── Ticket Executions ───────────────────────────────────────────────

export const ticketExecutions = sqliteTable(
  "ticket_execution",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    agentRunId: text("agent_run_id")
      .notNull()
      .references(() => agentRuns.id, { onDelete: "cascade" }),
    ticketId: text("ticket_id"), // FK to projectTickets (set in relations)

    title: text("title").notNull(),
    description: text("description").notNull(),
    executionType: text("execution_type").notNull(), // research | create_document | create_prd | code_implementation | ...
    status: text("status").notNull().default("queued"), // queued | ready | running | blocked | completed | failed | cancelled | skipped
    sequenceNumber: integer("sequence_number").notNull().default(0),

    workerContext: text("worker_context", { mode: "json" }).default({}),
    result: text("result", { mode: "json" }),

    blockedReason: text("blocked_reason"),
    blockedQuestion: text("blocked_question"),
    userResponse: text("user_response"),

    taskId: text("task_id"),
    workerType: text("worker_type"),

    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
    startedAt: integer("started_at", { mode: "timestamp" }),
    completedAt: integer("completed_at", { mode: "timestamp" }),
  },
  (t) => [
    index("te_run_status_idx").on(t.agentRunId, t.status),
    index("te_status_seq_idx").on(t.status, t.sequenceNumber),
  ]
);

// ── Ticket Execution Dependencies (M2M) ─────────────────────────────

export const ticketExecutionDependencies = sqliteTable(
  "ticket_execution_dependency",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    executionId: text("execution_id")
      .notNull()
      .references(() => ticketExecutions.id, { onDelete: "cascade" }),
    dependsOnId: text("depends_on_id")
      .notNull()
      .references(() => ticketExecutions.id, { onDelete: "cascade" }),
  },
  (t) => [index("ted_exec_idx").on(t.executionId)]
);

// ── Agent Events ────────────────────────────────────────────────────

export const agentEvents = sqliteTable(
  "agent_event",
  {
    id: text("id")
      .primaryKey()
      .$defaultFn(() => crypto.randomUUID()),
    agentRunId: text("agent_run_id")
      .notNull()
      .references(() => agentRuns.id, { onDelete: "cascade" }),
    ticketExecutionId: text("ticket_execution_id").references(
      () => ticketExecutions.id,
      { onDelete: "set null" }
    ),

    eventType: text("event_type").notNull(),
    payload: text("payload", { mode: "json" }).default({}),
    requiresUserAction: integer("requires_user_action", { mode: "boolean" })
      .notNull()
      .default(false),

    createdAt: integer("created_at", { mode: "timestamp" }).notNull().default(sql`(unixepoch())`),
  },
  (t) => [
    index("ae_run_type_idx").on(t.agentRunId, t.eventType),
    index("ae_user_action_idx").on(t.requiresUserAction, t.createdAt),
  ]
);
