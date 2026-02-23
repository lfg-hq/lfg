import { Hono } from "hono";
import { requireAuth } from "../../auth/middleware.ts";
import { db } from "../../config/db.ts";
import { projects } from "../../db/schema/projects.ts";
import { ticketStages, projectTickets, ticketLogs } from "../../db/schema/tickets.ts";
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

export default ticketsApi;
