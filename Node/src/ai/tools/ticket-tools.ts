import { tool, zodSchema } from "ai";
import { z } from "zod";
import { db } from "../../config/db.ts";
import {
  projectTickets,
  ticketStages,
  ticketLogs,
  projectTodoLists,
} from "../../db/schema/tickets.ts";
import { eq, and } from "drizzle-orm";
import {
  emitTicketCreated,
  emitTicketUpdated,
  emitTicketStatusChanged,
  emitTicketQueued,
  emitTicketCommented,
} from "../../events/emitters.ts";

let _wsBroadcast: ((userId: string, data: object) => void) | null = null;
export function setTicketWsBroadcast(fn: (userId: string, data: object) => void) {
  _wsBroadcast = fn;
}

export const createTickets = tool({
  description: "Create one or more development tickets. Only call when the user explicitly asks to build/create tickets.",
  inputSchema: zodSchema(z.object({
    projectId: z.string(),
    userId: z.string().describe("User ID for real-time ticket streaming"),
    tickets: z.array(z.object({
      name: z.string().describe("Ticket title"),
      description: z.string(),
      acceptanceCriteria: z.array(z.string()).describe("2-3 clear acceptance criteria"),
      priority: z.enum(["High", "Medium", "Low"]).default("Medium"),
      complexity: z.enum(["simple", "medium", "complex"]).default("medium"),
      stageId: z.string().optional(),
      sourceDocumentId: z.string().optional(),
      notes: z.string().optional(),
    })),
  })),
  execute: async ({ projectId, userId, tickets }) => {
    const [backlog] = await db.select().from(ticketStages)
      .where(and(eq(ticketStages.projectId, projectId), eq(ticketStages.name, "Backlog")));

    const created: { id: string; name: string }[] = [];

    // Insert tickets one at a time and broadcast each immediately
    for (const t of tickets) {
      const [row] = await db.insert(projectTickets).values({
        projectId,
        name: t.name,
        description: t.description,
        acceptanceCriteria: t.acceptanceCriteria,
        priority: t.priority,
        complexity: t.complexity,
        stageId: t.stageId ?? backlog?.id ?? null,
        sourceDocumentId: t.sourceDocumentId ?? null,
        notes: t.notes ?? "",
      }).returning();

      emitTicketCreated({ projectId, ticketId: row!.id, ticketName: row!.name, priority: row!.priority, stageId: row!.stageId });

      // Stream ticket to client as it's created
      if (_wsBroadcast) {
        _wsBroadcast(userId, {
          type: "ai_chunk",
          is_notification: true,
          notification_type: "ticket_stream",
          ticket: {
            id: row!.id,
            name: row!.name,
            description: t.description,
            priority: t.priority,
            complexity: t.complexity,
            stage: backlog?.name ?? "Backlog",
          },
        });
      }

      created.push({ id: row!.id, name: row!.name });
    }

    return { created: created.length, tickets: created };
  },
});

export const getPendingTickets = tool({
  description: "Get all unfinished tickets for a project, grouped by stage.",
  inputSchema: zodSchema(z.object({
    projectId: z.string(),
    stageFilter: z.array(z.string()).optional(),
  })),
  execute: async ({ projectId, stageFilter }) => {
    const [stages, tickets] = await Promise.all([
      db.select().from(ticketStages).where(eq(ticketStages.projectId, projectId)).orderBy(ticketStages.order),
      db.select().from(projectTickets).where(eq(projectTickets.projectId, projectId)),
    ]);
    const filteredStages = stageFilter ? stages.filter((s) => stageFilter.includes(s.name)) : stages;
    return filteredStages.map((stage) => ({
      stageId: stage.id,
      stageName: stage.name,
      tickets: tickets.filter((t) => t.stageId === stage.id).map((t) => ({ id: t.id, name: t.name, priority: t.priority, complexity: t.complexity, status: t.status })),
    }));
  },
});

export const getTicketDetails = tool({
  description: "Get full details of a specific ticket including description, acceptance criteria, and logs.",
  inputSchema: zodSchema(z.object({ ticketId: z.string() })),
  execute: async ({ ticketId }) => {
    const [ticket] = await db.select().from(projectTickets).where(eq(projectTickets.id, ticketId));
    if (!ticket) return { found: false as const };
    const [logs, todos] = await Promise.all([
      db.select().from(ticketLogs).where(eq(ticketLogs.ticketId, ticketId)).orderBy(ticketLogs.createdAt),
      db.select().from(projectTodoLists).where(eq(projectTodoLists.ticketId, ticketId)).orderBy(projectTodoLists.order),
    ]);
    return {
      found: true as const,
      ticket,
      logs: logs.map((l) => ({ logType: l.logType, command: l.command, output: l.output, exitCode: l.exitCode, createdAt: l.createdAt })),
      todos: todos.map((t) => ({ id: t.id, description: t.description, status: t.status })),
    };
  },
});

export const updateTicket = tool({
  description: "Update the status or stage of a ticket.",
  inputSchema: zodSchema(z.object({
    ticketId: z.string(),
    status: z.enum(["open", "in_progress", "review", "done", "failed", "blocked"]).optional(),
    stageId: z.string().optional(),
    priority: z.enum(["High", "Medium", "Low"]).optional(),
  })),
  execute: async ({ ticketId, status, stageId, priority }) => {
    const [before] = await db.select({ status: projectTickets.status, projectId: projectTickets.projectId }).from(projectTickets).where(eq(projectTickets.id, ticketId));
    const u: Record<string, unknown> = { updatedAt: new Date() };
    if (status) u.status = status;
    if (stageId) u.stageId = stageId;
    if (priority) u.priority = priority;
    await db.update(projectTickets).set(u).where(eq(projectTickets.id, ticketId));
    const projectId = before?.projectId ?? "";
    if (status && before?.status !== status) {
      emitTicketStatusChanged({ ticketId, projectId, oldStatus: before?.status, newStatus: status });
    }
    if (stageId || priority) {
      emitTicketUpdated({ ticketId, projectId, changes: u });
    }
    return { success: true };
  },
});

export const updateTicketDetails = tool({
  description: "Update the description, acceptance criteria, or other details of a ticket.",
  inputSchema: zodSchema(z.object({
    ticketId: z.string(),
    name: z.string().optional(),
    description: z.string().optional(),
    acceptanceCriteria: z.array(z.string()).optional(),
    complexity: z.enum(["simple", "medium", "complex"]).optional(),
    notes: z.string().optional(),
  })),
  execute: async ({ ticketId, name, description, acceptanceCriteria, complexity, notes }) => {
    const u: Record<string, unknown> = { updatedAt: new Date() };
    if (name) u.name = name;
    if (description) u.description = description;
    if (acceptanceCriteria) u.acceptanceCriteria = acceptanceCriteria;
    if (complexity) u.complexity = complexity;
    if (notes != null) u.notes = notes;
    await db.update(projectTickets).set(u).where(eq(projectTickets.id, ticketId));
    return { success: true };
  },
});

export const updateAllTickets = tool({
  description: "Batch-update status or stage for multiple tickets.",
  inputSchema: zodSchema(z.object({
    updates: z.array(z.object({
      ticketId: z.string(),
      status: z.enum(["open", "in_progress", "review", "done", "failed", "blocked"]).optional(),
      stageId: z.string().optional(),
    })),
  })),
  execute: async ({ updates }) => {
    await Promise.all(updates.map(({ ticketId, status, stageId }) => {
      const u: Record<string, unknown> = { updatedAt: new Date() };
      if (status) u.status = status;
      if (stageId) u.stageId = stageId;
      return db.update(projectTickets).set(u).where(eq(projectTickets.id, ticketId));
    }));
    return { updated: updates.length };
  },
});

export const getNextTicket = tool({
  description: "Get the next open ticket to work on.",
  inputSchema: zodSchema(z.object({ projectId: z.string() })),
  execute: async ({ projectId }) => {
    const [next] = await db.select().from(projectTickets).where(and(eq(projectTickets.projectId, projectId), eq(projectTickets.status, "open"))).orderBy(projectTickets.createdAt).limit(1);
    if (!next) return { found: false as const };
    return { found: true as const, ticket: { id: next.id, name: next.name, description: next.description } };
  },
});

export const scheduleTickets = tool({
  description: "Provide a prioritized execution order for tickets.",
  inputSchema: zodSchema(z.object({
    projectId: z.string(),
    schedule: z.array(z.object({
      ticketId: z.string(),
      order: z.number(),
      rationale: z.string().optional(),
    })),
  })),
  execute: async ({ projectId: _projectId, schedule }) => {
    await Promise.all(schedule.map(({ ticketId, order, rationale }) =>
      db.update(projectTickets).set({ notes: rationale ? `[Order: ${order}] ${rationale}` : `[Order: ${order}]`, updatedAt: new Date() }).where(eq(projectTickets.id, ticketId))
    ));
    return { scheduled: schedule.length };
  },
});

export const retryTicket = tool({
  description: "Reset a failed ticket to open so it can be retried.",
  inputSchema: zodSchema(z.object({
    ticketId: z.string(),
    reason: z.string().optional(),
  })),
  execute: async ({ ticketId, reason }) => {
    await db.update(projectTickets).set({ status: "open", updatedAt: new Date() }).where(eq(projectTickets.id, ticketId));
    if (reason) {
      await db.insert(ticketLogs).values({ ticketId, logType: "user_message", command: `Retry: ${reason}`, explanation: reason });
    }
    return { success: true };
  },
});

export const sendTicketMessage = tool({
  description: "Send a message to the coding agent currently working on a ticket. If a Claude session is active, it resumes that session with the message. Otherwise it starts a new session with context.",
  inputSchema: zodSchema(z.object({
    ticketId: z.string(),
    message: z.string().describe("The instruction or question to send to the ticket agent"),
  })),
  execute: async ({ ticketId, message }) => {
    const [row] = await db.select({ projectId: projectTickets.projectId }).from(projectTickets).where(eq(projectTickets.id, ticketId));
    // Log the message first
    await db.insert(ticketLogs).values({ ticketId, logType: "user_message", command: message });
    emitTicketCommented({ ticketId, projectId: row?.projectId ?? "", message, logType: "user_message" });
    // Dispatch to ticket chat executor (picks up active session or starts new one)
    const { bus } = await import("../../events/bus.ts");
    bus.emit({ type: "ticket.chat_message", payload: { ticketId, message, sender: "orchestrator" } });
    return { success: true, note: "Message dispatched to ticket agent" };
  },
});

export const queueTicketExecution = tool({
  description: "Mark a ticket as queued for background execution by the coding agent.",
  inputSchema: zodSchema(z.object({
    ticketId: z.string(),
    notes: z.string().optional(),
  })),
  execute: async ({ ticketId, notes }) => {
    const [row] = await db.select({ projectId: projectTickets.projectId }).from(projectTickets).where(eq(projectTickets.id, ticketId));
    await db.update(projectTickets).set({ queueStatus: "queued", queuedAt: new Date(), notes: notes ?? undefined, updatedAt: new Date() }).where(eq(projectTickets.id, ticketId));
    await db.insert(ticketLogs).values({ ticketId, logType: "user_message", command: notes ? `Queued: ${notes}` : "Queued for execution" });
    emitTicketQueued({ ticketId, projectId: row?.projectId ?? "", notes });
    return { success: true };
  },
});
