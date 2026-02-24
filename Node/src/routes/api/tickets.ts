import { Hono } from "hono";
import { requireAuth } from "../../auth/middleware.ts";
import { db } from "../../config/db.ts";
import { projects } from "../../db/schema/projects.ts";
import { ticketStages, projectTickets, ticketLogs, projectTodoLists } from "../../db/schema/tickets.ts";
import { sandboxes } from "../../db/schema/sandbox.ts";
import { conversations } from "../../db/schema/chat.ts";
import { eq, and, asc, desc } from "drizzle-orm";
import type { auth } from "../../auth/index.ts";

type AuthEnv = {
  Variables: {
    user: typeof auth.$Infer.Session.user;
    session: typeof auth.$Infer.Session.session;
  };
};

const ticketsApi = new Hono<AuthEnv>();
ticketsApi.use("*", requireAuth);

// Helper: resolve project by projectId (public UUID) and verify ownership
async function resolveProject(projectId: string, userId: string) {
  const [project] = await db
    .select()
    .from(projects)
    .where(and(eq(projects.projectId, projectId), eq(projects.ownerId, userId)));
  return project ?? null;
}

// ── GET /api/projects/:projectId/tickets ────────────────────────────
ticketsApi.get("/:projectId/tickets", async (c) => {
  const user = c.get("user");
  const { projectId } = c.req.param();

  const project = await resolveProject(projectId!, user.id);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const rows = await db
    .select()
    .from(projectTickets)
    .where(eq(projectTickets.projectId, project.id))
    .orderBy(asc(projectTickets.createdAt));

  return c.json({ tickets: rows });
});

// ── POST /api/projects/:projectId/tickets ────────────────────────────
ticketsApi.post("/:projectId/tickets", async (c) => {
  const user = c.get("user");
  const { projectId } = c.req.param();

  const project = await resolveProject(projectId!, user.id);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const body = await c.req.json<{
    name: string;
    description: string;
    priority?: string;
    stageId?: string;
    complexity?: string;
  }>();

  if (!body.name || !body.description) {
    return c.json({ error: "name and description are required" }, 400);
  }

  const [ticket] = await db
    .insert(projectTickets)
    .values({
      projectId: project.id,
      name: body.name,
      description: body.description,
      priority: body.priority ?? "Medium",
      stageId: body.stageId ?? null,
      complexity: body.complexity ?? "medium",
    })
    .returning();

  return c.json({ ticket }, 201);
});

// ── GET /api/projects/:projectId/tickets/:ticketId ───────────────────
ticketsApi.get("/:projectId/tickets/:ticketId", async (c) => {
  const user = c.get("user");
  const { projectId, ticketId } = c.req.param();

  const project = await resolveProject(projectId!, user.id);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const [ticket] = await db
    .select()
    .from(projectTickets)
    .where(and(eq(projectTickets.id, ticketId!), eq(projectTickets.projectId, project.id)));

  if (!ticket) return c.json({ error: "Ticket not found" }, 404);

  const logs = await db
    .select()
    .from(ticketLogs)
    .where(eq(ticketLogs.ticketId, ticket.id))
    .orderBy(desc(ticketLogs.createdAt))
    .limit(50);

  return c.json({ ticket, logs });
});

// ── PATCH /api/projects/:projectId/tickets/:ticketId ─────────────────
ticketsApi.patch("/:projectId/tickets/:ticketId", async (c) => {
  const user = c.get("user");
  const { projectId, ticketId } = c.req.param();

  const project = await resolveProject(projectId!, user.id);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const [existing] = await db
    .select({ id: projectTickets.id })
    .from(projectTickets)
    .where(and(eq(projectTickets.id, ticketId!), eq(projectTickets.projectId, project.id)));

  if (!existing) return c.json({ error: "Ticket not found" }, 404);

  const body = await c.req.json<Partial<{
    name: string;
    description: string;
    status: string;
    priority: string;
    stageId: string | null;
    complexity: string;
    queueStatus: string;
    notes: string;
  }>>();

  const updateData: Record<string, unknown> = { updatedAt: new Date() };
  if (body.name !== undefined) updateData.name = body.name;
  if (body.description !== undefined) updateData.description = body.description;
  if (body.status !== undefined) updateData.status = body.status;
  if (body.priority !== undefined) updateData.priority = body.priority;
  if ("stageId" in body) updateData.stageId = body.stageId;
  if (body.complexity !== undefined) updateData.complexity = body.complexity;
  if (body.queueStatus !== undefined) updateData.queueStatus = body.queueStatus;
  if (body.notes !== undefined) updateData.notes = body.notes;

  const [updated] = await db
    .update(projectTickets)
    .set(updateData)
    .where(eq(projectTickets.id, existing.id))
    .returning();

  return c.json({ ticket: updated });
});

// ── DELETE /api/projects/:projectId/tickets/:ticketId ────────────────
ticketsApi.delete("/:projectId/tickets/:ticketId", async (c) => {
  const user = c.get("user");
  const { projectId, ticketId } = c.req.param();

  const project = await resolveProject(projectId!, user.id);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const [existing] = await db
    .select({ id: projectTickets.id })
    .from(projectTickets)
    .where(and(eq(projectTickets.id, ticketId!), eq(projectTickets.projectId, project.id)));

  if (!existing) return c.json({ error: "Ticket not found" }, 404);

  await db.delete(projectTickets).where(eq(projectTickets.id, existing.id));
  return c.json({ success: true });
});

// ── GET /api/projects/:projectId/stages ──────────────────────────────
ticketsApi.get("/:projectId/stages", async (c) => {
  const user = c.get("user");
  const { projectId } = c.req.param();

  const project = await resolveProject(projectId!, user.id);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const rows = await db
    .select()
    .from(ticketStages)
    .where(eq(ticketStages.projectId, project.id))
    .orderBy(asc(ticketStages.order));

  return c.json({ stages: rows });
});

// ── PATCH /api/projects/:projectId/tickets/:ticketId/stage ────────────
ticketsApi.patch("/:projectId/tickets/:ticketId/stage", async (c) => {
  const user = c.get("user");
  const { projectId, ticketId } = c.req.param();

  const project = await resolveProject(projectId!, user.id);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const [existing] = await db
    .select({ id: projectTickets.id })
    .from(projectTickets)
    .where(and(eq(projectTickets.id, ticketId!), eq(projectTickets.projectId, project.id)));

  if (!existing) return c.json({ error: "Ticket not found" }, 404);

  const { stageId } = await c.req.json<{ stageId: string | null }>();

  const [updated] = await db
    .update(projectTickets)
    .set({ stageId: stageId ?? null, updatedAt: new Date() })
    .where(eq(projectTickets.id, existing.id))
    .returning();

  return c.json({ ticket: updated });
});

// ── GET /api/projects/:projectId/conversations/ ──────────────────────
ticketsApi.get("/:projectId/conversations", async (c) => {
  const user = c.get("user");
  const { projectId } = c.req.param();

  const project = await resolveProject(projectId, user.id);
  if (!project) return c.json([], 200);

  const convRows = await db
    .select()
    .from(conversations)
    .where(eq(conversations.projectId, project.projectId))
    .orderBy(desc(conversations.updatedAt));

  return c.json(
    convRows.map((c) => ({
      id: c.id,
      title: c.title ?? "Untitled",
      created_at: c.createdAt,
      updated_at: c.updatedAt,
    }))
  );
});

// Trailing slash variant
ticketsApi.get("/:projectId/conversations/", async (c) => {
  const user = c.get("user");
  const { projectId } = c.req.param();

  const project = await resolveProject(projectId, user.id);
  if (!project) return c.json([], 200);

  const convRows = await db
    .select()
    .from(conversations)
    .where(eq(conversations.projectId, project.projectId))
    .orderBy(desc(conversations.updatedAt));

  return c.json(
    convRows.map((c) => ({
      id: c.id,
      title: c.title ?? "Untitled",
      created_at: c.createdAt,
      updated_at: c.updatedAt,
    }))
  );
});

// ── GET /:projectId/tickets/:ticketId/logs ──────────────────────────
// Returns ticket execution logs (command + ai_response + user_message)

ticketsApi.get("/:projectId/tickets/:ticketId/logs", async (c) => {
  const user = c.get("user");
  const { projectId, ticketId } = c.req.param();

  const project = await resolveProject(projectId, user.id);
  if (!project) return c.json({ error: "Not found" }, 404);

  const logs = await db
    .select()
    .from(ticketLogs)
    .where(eq(ticketLogs.ticketId, ticketId))
    .orderBy(ticketLogs.createdAt)
    .limit(500);

  return c.json(logs.map((l) => ({
    id: l.id,
    type: l.logType,
    message: l.command,
    explanation: l.explanation,
    createdAt: l.createdAt,
  })));
});

// ── GET /:projectId/tickets/:ticketId/tasks ─────────────────────────

ticketsApi.get("/:projectId/tickets/:ticketId/tasks", async (c) => {
  const user = c.get("user");
  const { projectId, ticketId } = c.req.param();

  const project = await resolveProject(projectId, user.id);
  if (!project) return c.json({ error: "Not found" }, 404);

  const tasks = await db
    .select()
    .from(projectTodoLists)
    .where(eq(projectTodoLists.ticketId, ticketId))
    .orderBy(projectTodoLists.order);

  return c.json(tasks);
});

// ── POST /:projectId/tickets/:ticketId/chat ─────────────────────────
// User sends a chat message to the ticket agent

ticketsApi.post("/:projectId/tickets/:ticketId/chat", async (c) => {
  const user = c.get("user");
  const { projectId, ticketId } = c.req.param();

  const project = await resolveProject(projectId, user.id);
  if (!project) return c.json({ error: "Not found" }, 404);

  const body = await c.req.json<{ message: string }>();
  if (!body.message?.trim()) return c.json({ error: "message required" }, 400);

  // Log user message
  await db.insert(ticketLogs).values({
    ticketId,
    logType: "user_message",
    command: body.message,
  });

  // Dispatch to executor
  const { bus } = await import("../../events/bus.ts");
  bus.emit({ type: "ticket.chat_message", payload: { ticketId, message: body.message, sender: "user" } });

  return c.json({ ok: true });
});

// ── POST /:projectId/tickets/:ticketId/queue ────────────────────────
// Queue a ticket for execution

ticketsApi.post("/:projectId/tickets/:ticketId/queue", async (c) => {
  const user = c.get("user");
  const { projectId, ticketId } = c.req.param();

  const project = await resolveProject(projectId, user.id);
  if (!project) return c.json({ error: "Not found" }, 404);

  const body = await c.req.json<{ notes?: string }>().catch(() => ({} as { notes?: string }));

  const [ticket] = await db
    .select()
    .from(projectTickets)
    .where(and(eq(projectTickets.id, ticketId), eq(projectTickets.projectId, project.id)))
    .limit(1);

  if (!ticket) return c.json({ error: "Ticket not found" }, 404);

  await db
    .update(projectTickets)
    .set({ queueStatus: "queued", queuedAt: new Date(), updatedAt: new Date() })
    .where(eq(projectTickets.id, ticketId));

  const { bus } = await import("../../events/bus.ts");
  bus.emit({ type: "ticket.queued", payload: { ticketId, projectId: project.id, notes: body.notes } });

  return c.json({ ok: true });
});

// ── GET /:projectId/tickets/:ticketId/sandbox ───────────────────────
// Get sandbox info (preview URL, status, branch)

ticketsApi.get("/:projectId/tickets/:ticketId/sandbox", async (c) => {
  const user = c.get("user");
  const { projectId, ticketId } = c.req.param();

  const project = await resolveProject(projectId, user.id);
  if (!project) return c.json({ error: "Not found" }, 404);

  const [sandbox] = await db
    .select()
    .from(sandboxes)
    .where(and(eq(sandboxes.ticketId, ticketId), eq(sandboxes.workspaceType, "ticket")))
    .limit(1);

  if (!sandbox) return c.json(null);

  return c.json({
    id: sandbox.id,
    status: sandbox.status,
    previewUrl: sandbox.previewUrl,
    previewPort: sandbox.previewPort,
    currentBranch: sandbox.currentBranch,
    techStack: sandbox.techStack,
    cliSessionId: sandbox.cliSessionId ? "active" : null,
  });
});

// ── POST /:projectId/tickets/:ticketId/preview ──────────────────────
// Start/restart dev server

ticketsApi.post("/:projectId/tickets/:ticketId/preview", async (c) => {
  const user = c.get("user");
  const { projectId, ticketId } = c.req.param();

  const project = await resolveProject(projectId, user.id);
  if (!project) return c.json({ error: "Not found" }, 404);

  const [sandbox] = await db
    .select()
    .from(sandboxes)
    .where(and(eq(sandboxes.ticketId, ticketId), eq(sandboxes.workspaceType, "ticket")))
    .limit(1);

  if (!sandbox) return c.json({ error: "No sandbox found for this ticket" }, 404);

  const body = await c.req.json<{ action?: string }>().catch(() => ({} as { action?: string }));
  const action = body.action ?? "start";

  const { startDevServer, restartDevServer, stopDevServer } = await import("../../services/preview.ts");

  try {
    if (action === "stop") {
      await stopDevServer(sandbox.id);
      return c.json({ ok: true });
    }
    const result = action === "restart"
      ? await restartDevServer(sandbox.id)
      : await startDevServer(sandbox.id);
    return c.json(result);
  } catch (err) {
    return c.json({ error: String(err) }, 500);
  }
});

export default ticketsApi;
