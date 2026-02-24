/**
 * CLI Callback API
 *
 * Endpoints called by Claude Code CLI running inside Mags VMs.
 * Auth: X-CLI-API-Key header matched against profiles.cliApiKey.
 *
 * POST /api/v1/cli/tasks/bulk/          — update todo task statuses
 * POST /api/v1/cli/status/              — update ticket execution status
 * POST /api/v1/cli/tech-stack/          — register detected tech stack
 * POST /api/v1/cli/request-input/       — ask user a question (returns answer)
 * POST /api/v1/cli/ticket-chat/         — receive chat message for ticket agent
 */

import { Hono } from "hono";
import { db } from "../../config/db.ts";
import { projectTickets, projectTodoLists, ticketLogs } from "../../db/schema/tickets.ts";
import { sandboxes } from "../../db/schema/sandbox.ts";
import { profiles } from "../../db/schema/users.ts";
import { eq, and } from "drizzle-orm";
import { emit } from "../../events/bus.ts";

export const cliRouter = new Hono();

// ── Auth middleware ───────────────────────────────────────────────────

cliRouter.use("*", async (c, next) => {
  const apiKey = c.req.header("X-CLI-API-Key");
  if (!apiKey) {
    return c.json({ error: "Missing X-CLI-API-Key header" }, 401);
  }

  // Look up the profile that owns this key
  const [profile] = await db
    .select()
    .from(profiles)
    .where(eq(profiles.cliApiKey, apiKey))
    .limit(1);

  if (!profile) {
    return c.json({ error: "Invalid API key" }, 401);
  }

  await next();
});

// ── POST /api/v1/cli/tasks/bulk/ ──────────────────────────────────────

cliRouter.post("/tasks/bulk/", async (c) => {
  const body = await c.req.json<{
    ticket_id: string;
    tasks: Array<{
      id: string;
      status: string;
      explanation?: string;
    }>;
  }>();

  const { ticket_id, tasks } = body;
  if (!ticket_id || !Array.isArray(tasks)) {
    return c.json({ error: "ticket_id and tasks required" }, 400);
  }

  const updated: string[] = [];
  for (const task of tasks) {
    if (!task.id || !task.status) continue;

    await db
      .update(projectTodoLists)
      .set({
        status: task.status,
        updatedAt: new Date(),
      })
      .where(
        and(
          eq(projectTodoLists.id, task.id),
          eq(projectTodoLists.ticketId, ticket_id)
        )
      );

    updated.push(task.id);
  }

  // Broadcast task update event
  emit({ type: "ticket.tasks_updated", ticketId: ticket_id, taskIds: updated });

  return c.json({ updated });
});

// ── POST /api/v1/cli/status/ ──────────────────────────────────────────

cliRouter.post("/status/", async (c) => {
  const body = await c.req.json<{
    ticket_id: string;
    status: string;   // in_progress | complete | failed
    message?: string;
  }>();

  const { ticket_id, status, message } = body;
  if (!ticket_id || !status) {
    return c.json({ error: "ticket_id and status required" }, 400);
  }

  // Map CLI status to ticket status
  const ticketStatus =
    status === "complete" ? "done" :
    status === "failed" ? "failed" :
    "in_progress";

  await db
    .update(projectTickets)
    .set({
      status: ticketStatus,
      queueStatus: status === "in_progress" ? "executing" : "none",
      updatedAt: new Date(),
    })
    .where(eq(projectTickets.id, ticket_id));

  // Log status message
  if (message) {
    await db.insert(ticketLogs).values({
      ticketId: ticket_id,
      logType: "command",
      command: `Status: ${status}`,
      explanation: message,
    });
  }

  emit({
    type: "ticket.status_changed",
    ticketId: ticket_id,
    status: ticketStatus,
    message,
  });

  return c.json({ ok: true });
});

// ── POST /api/v1/cli/tech-stack/ ─────────────────────────────────────

cliRouter.post("/tech-stack/", async (c) => {
  const body = await c.req.json<{
    ticket_id: string;
    language?: string;
    framework?: string;
    package_manager?: string;
    start_command?: string;
    build_command?: string;
    port?: number;
  }>();

  const { ticket_id, ...stackFields } = body;
  if (!ticket_id) {
    return c.json({ error: "ticket_id required" }, 400);
  }

  // Get the ticket to find its sandbox
  const [ticket] = await db
    .select()
    .from(projectTickets)
    .where(eq(projectTickets.id, ticket_id))
    .limit(1);

  if (!ticket) return c.json({ error: "Ticket not found" }, 404);

  // Update sandbox tech stack
  const techStack = {
    language: stackFields.language,
    framework: stackFields.framework,
    packageManager: stackFields.package_manager,
    startCommand: stackFields.start_command,
    buildCommand: stackFields.build_command,
    port: stackFields.port,
  };

  await db
    .update(sandboxes)
    .set({ techStack, updatedAt: new Date() })
    .where(eq(sandboxes.ticketId, ticket_id));

  return c.json({ ok: true });
});

// ── POST /api/v1/cli/request-input/ ──────────────────────────────────

/**
 * The CLI blocks here waiting for the user to respond.
 * We emit a WS event to the user and long-poll for the answer.
 * Timeout: 5 minutes.
 */
cliRouter.post("/request-input/", async (c) => {
  const body = await c.req.json<{
    ticket_id: string;
    question: string;
    options?: string[];
  }>();

  const { ticket_id, question, options } = body;
  if (!ticket_id || !question) {
    return c.json({ error: "ticket_id and question required" }, 400);
  }

  // Emit WS event so the UI can show the question to the user
  emit({
    type: "ticket.input_requested",
    ticketId: ticket_id,
    question,
    options,
  });

  // Log the request
  await db.insert(ticketLogs).values({
    ticketId: ticket_id,
    logType: "command",
    command: "Waiting for user input",
    explanation: question,
  });

  // Long-poll for answer stored via the ticket-chat endpoint
  // Max wait: 5 minutes (300s)
  const deadline = Date.now() + 300_000;
  while (Date.now() < deadline) {
    const [ticket] = await db
      .select({ inputResponse: projectTickets.notes })
      .from(projectTickets)
      .where(eq(projectTickets.id, ticket_id))
      .limit(1);

    // Check if user responded (we'll store the answer in a special field)
    // For now use a simple marker pattern in notes — TODO: dedicated field
    const notes = ticket?.inputResponse ?? "";
    const marker = `INPUT_RESPONSE:${ticket_id}:`;
    const idx = notes.lastIndexOf(marker);
    if (idx !== -1) {
      const answer = notes.slice(idx + marker.length).split("\n")[0];
      // Clear the marker
      await db
        .update(projectTickets)
        .set({ notes: notes.slice(0, idx).trim(), updatedAt: new Date() })
        .where(eq(projectTickets.id, ticket_id));
      return c.json({ answer });
    }

    await new Promise((r) => setTimeout(r, 3000));
  }

  return c.json({ answer: "timeout — no response" }, 408);
});

// ── POST /api/v1/cli/ticket-chat/ ────────────────────────────────────

/**
 * Called when a user/orchestrator sends a message to the ticket agent.
 * Stores the message as a log entry and triggers executeTicketChat().
 */
cliRouter.post("/ticket-chat/", async (c) => {
  const body = await c.req.json<{
    ticket_id: string;
    message: string;
    sender?: string; // "user" | "orchestrator"
  }>();

  const { ticket_id, message, sender = "user" } = body;
  if (!ticket_id || !message) {
    return c.json({ error: "ticket_id and message required" }, 400);
  }

  await db.insert(ticketLogs).values({
    ticketId: ticket_id,
    logType: "user_message",
    command: message,
    explanation: `Message from ${sender}`,
  });

  // Trigger the chat executor (fire-and-forget)
  emit({ type: "ticket.chat_message", ticketId: ticket_id, message, sender });

  return c.json({ ok: true });
});
