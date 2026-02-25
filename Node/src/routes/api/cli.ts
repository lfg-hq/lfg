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
import { projects } from "../../db/schema/projects.ts";
import { profiles } from "../../db/schema/users.ts";
import { eq, and } from "drizzle-orm";
import { emit } from "../../events/bus.ts";
import { parseJsonlEvents, extractSessionId, isStreamComplete } from "../../services/claude-cli.ts";
import { addLog, formatToolUse } from "../../services/ticket-logs.ts";

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

// ── POST /api/v1/cli/tasks/create/ ────────────────────────────────────

cliRouter.post("/tasks/create/", async (c) => {
  const body = await c.req.json<{
    ticket_id: string;
    tasks: Array<{
      description: string;
      status?: string;
    }>;
  }>();

  const { ticket_id, tasks } = body;
  if (!ticket_id || !Array.isArray(tasks) || tasks.length === 0) {
    return c.json({ error: "ticket_id and tasks array required" }, 400);
  }

  // Get max existing order
  const existingTasks = await db
    .select({ order: projectTodoLists.order })
    .from(projectTodoLists)
    .where(eq(projectTodoLists.ticketId, ticket_id));

  let nextOrder = existingTasks.length > 0
    ? Math.max(...existingTasks.map((t) => t.order)) + 1
    : 0;

  const created: Array<{ id: string; description: string }> = [];
  for (const task of tasks) {
    if (!task.description?.trim()) continue;
    const [row] = await db
      .insert(projectTodoLists)
      .values({
        ticketId: ticket_id,
        description: task.description.trim(),
        status: task.status ?? "pending",
        order: nextOrder++,
      })
      .returning();
    if (row) created.push({ id: row.id, description: row.description });
  }

  // Broadcast task update event
  emit({ type: "ticket.tasks_updated", ticketId: ticket_id, taskIds: created.map((t) => t.id) });

  return c.json({ created }, 201);
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

  // Also save the stack identifier to the project for future executions
  if (stackFields.framework || stackFields.language) {
    const stackLabel = stackFields.framework || stackFields.language || "";
    await db
      .update(projects)
      .set({ stack: stackLabel, updatedAt: new Date() })
      .where(eq(projects.id, ticket.projectId));
  }

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

// ── POST /api/v1/cli/output/ ──────────────────────────────────────────

/**
 * Receives pushed JSONL output chunks from the VM forwarder loop.
 * Decodes base64 data, parses JSONL events, logs to DB, broadcasts via WS.
 * When done=true, emits ticket.execution_finished event.
 */
cliRouter.post("/output/", async (c) => {
  let body: { ticket_id: string; data: string; done?: boolean; exit_code?: number };
  try {
    body = await c.req.json();
  } catch (err) {
    console.error("[cli/output] JSON parse error:", (err as Error).message);
    return c.json({ error: "Invalid JSON body" }, 400);
  }

  const { ticket_id, data, done, exit_code } = body;
  if (!ticket_id || !data) {
    return c.json({ error: "ticket_id and data required" }, 400);
  }

  // Look up ticket owner (userId) for WS broadcasting
  const [ticket] = await db
    .select({ id: projectTickets.id, projectId: projectTickets.projectId })
    .from(projectTickets)
    .where(eq(projectTickets.id, ticket_id))
    .limit(1);

  if (!ticket) return c.json({ error: "Ticket not found" }, 404);

  const [project] = await db
    .select({ ownerId: projects.ownerId })
    .from(projects)
    .where(eq(projects.id, ticket.projectId))
    .limit(1);

  const ownerId = project?.ownerId;

  // Decode base64 chunk
  let rawText: string;
  try {
    rawText = Buffer.from(data, "base64").toString("utf-8");
  } catch {
    return c.json({ error: "Invalid base64 data" }, 400);
  }

  // Parse JSONL events
  const events = parseJsonlEvents(rawText);

  if (events.length > 0) {
    // Extract session ID if present — save to sandbox
    const sessionId = extractSessionId(events);
    if (sessionId) {
      await db
        .update(sandboxes)
        .set({ cliSessionId: sessionId, updatedAt: new Date() })
        .where(eq(sandboxes.ticketId, ticket_id));
    }

    // Log each event to DB + WS
    for (const ev of events) {
      try {
        const msg = (ev as any).message;
        const content = Array.isArray(msg?.content) ? msg.content : [];

        if (ev.type === "assistant") {
          for (const block of content) {
            if (block.type === "text" && block.text?.trim()) {
              await addLog(ticket_id, block.text, "ai_response", ownerId);
            } else if (block.type === "tool_use" && block.name) {
              const toolMsg = formatToolUse(block.name, block.input ?? {});
              await addLog(ticket_id, toolMsg, "command", ownerId);
            }
          }
        } else if (ev.type === "user") {
          for (const block of content) {
            if (block.type === "tool_result") {
              // content can be a string or array of content blocks
              const text = typeof block.content === "string"
                ? block.content
                : Array.isArray(block.content)
                  ? block.content.map((b: any) => b.text ?? "").join("\n")
                  : "";
              if (text.length > 50) {
                await addLog(ticket_id, text.slice(0, 500), "command", ownerId);
              }
            }
          }
        } else if (ev.type === "result") {
          // Skip logging result text — same content already logged from the
          // final assistant message. Only log if it's an error subtype.
        } else if (ev.type === "error") {
          const errMsg = (ev as { type: "error"; error: string }).error;
          await addLog(ticket_id, `CLI error: ${errMsg}`, "cli_error", ownerId);
        }
      } catch (err) {
        console.error(`[cli/output] Error processing event type=${ev.type}:`, err);
      }
    }
  } else if (rawText.trim()) {
    // Non-JSONL text — log as cli_error (e.g. stderr output)
    await addLog(ticket_id, rawText.trim().slice(0, 1000), "cli_error", ownerId);
  }

  // If VM signals completion, emit the event
  if (done) {
    emit({
      type: "ticket.execution_finished",
      ticketId: ticket_id,
      status: exit_code === 0 ? "complete" : "failed",
      exitCode: exit_code,
    });
  }

  return c.json({ ok: true });
});
