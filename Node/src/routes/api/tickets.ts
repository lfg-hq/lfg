import { Hono } from "hono";
import { requireAuth } from "../../auth/middleware.ts";
import { db } from "../../config/db.ts";
import { projects } from "../../db/schema/projects.ts";
import { ticketStages, projectTickets, ticketLogs, projectTodoLists, ticketMergeHistory } from "../../db/schema/tickets.ts";
import { githubTokens } from "../../db/schema/users.ts";
import { sandboxes } from "../../db/schema/sandbox.ts";
import { conversations } from "../../db/schema/chat.ts";
import { eq, and, asc, desc, max } from "drizzle-orm";
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

// ── POST /:projectId/tickets/:ticketId/tasks ────────────────────────
// Create task(s) for a ticket

ticketsApi.post("/:projectId/tickets/:ticketId/tasks", async (c) => {
  const user = c.get("user");
  const { projectId, ticketId } = c.req.param();

  const project = await resolveProject(projectId, user.id);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const [ticket] = await db
    .select({ id: projectTickets.id })
    .from(projectTickets)
    .where(and(eq(projectTickets.id, ticketId), eq(projectTickets.projectId, project.id)));

  if (!ticket) return c.json({ error: "Ticket not found" }, 404);

  const body = await c.req.json<{
    tasks: Array<{ description: string; order?: number }>;
  }>();

  if (!Array.isArray(body.tasks) || body.tasks.length === 0) {
    return c.json({ error: "tasks array is required" }, 400);
  }

  // Get max existing order
  const [maxRow] = await db
    .select({ maxOrder: max(projectTodoLists.order) })
    .from(projectTodoLists)
    .where(eq(projectTodoLists.ticketId, ticketId));

  let nextOrder = (maxRow?.maxOrder ?? -1) + 1;

  const created = [];
  for (const task of body.tasks) {
    if (!task.description?.trim()) continue;
    const order = task.order ?? nextOrder++;
    const [row] = await db
      .insert(projectTodoLists)
      .values({
        ticketId,
        description: task.description.trim(),
        status: "pending",
        order,
      })
      .returning();
    if (row) created.push({ id: row.id, description: row.description, status: row.status, order: row.order });
  }

  // Emit event
  const { emit } = await import("../../events/bus.ts");
  emit({ type: "ticket.tasks_updated", ticketId, taskIds: created.map((t) => t.id) });

  return c.json({ created }, 201);
});

// ── PATCH /:projectId/tickets/:ticketId/tasks/:taskId ───────────────

ticketsApi.patch("/:projectId/tickets/:ticketId/tasks/:taskId", async (c) => {
  const user = c.get("user");
  const { projectId, ticketId, taskId } = c.req.param();

  const project = await resolveProject(projectId, user.id);
  if (!project) return c.json({ error: "Project not found" }, 404);

  // Verify ticket belongs to project
  const [ticket] = await db
    .select({ id: projectTickets.id })
    .from(projectTickets)
    .where(and(eq(projectTickets.id, ticketId), eq(projectTickets.projectId, project.id)));

  if (!ticket) return c.json({ error: "Ticket not found" }, 404);

  const [existing] = await db
    .select({ id: projectTodoLists.id })
    .from(projectTodoLists)
    .where(and(eq(projectTodoLists.id, taskId), eq(projectTodoLists.ticketId, ticketId)));

  if (!existing) return c.json({ error: "Task not found" }, 404);

  const body = await c.req.json<Partial<{ description: string; status: string; order: number }>>();
  const updateData: Record<string, unknown> = { updatedAt: new Date() };
  if (body.description !== undefined) updateData.description = body.description;
  if (body.status !== undefined) updateData.status = body.status;
  if (body.order !== undefined) updateData.order = body.order;

  const [updated] = await db
    .update(projectTodoLists)
    .set(updateData)
    .where(eq(projectTodoLists.id, taskId))
    .returning();

  return c.json({ task: updated });
});

// ── DELETE /:projectId/tickets/:ticketId/tasks/:taskId ──────────────

ticketsApi.delete("/:projectId/tickets/:ticketId/tasks/:taskId", async (c) => {
  const user = c.get("user");
  const { projectId, ticketId, taskId } = c.req.param();

  const project = await resolveProject(projectId, user.id);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const [ticket] = await db
    .select({ id: projectTickets.id })
    .from(projectTickets)
    .where(and(eq(projectTickets.id, ticketId), eq(projectTickets.projectId, project.id)));

  if (!ticket) return c.json({ error: "Ticket not found" }, 404);

  const [existing] = await db
    .select({ id: projectTodoLists.id })
    .from(projectTodoLists)
    .where(and(eq(projectTodoLists.id, taskId), eq(projectTodoLists.ticketId, ticketId)));

  if (!existing) return c.json({ error: "Task not found" }, 404);

  await db.delete(projectTodoLists).where(eq(projectTodoLists.id, taskId));
  return c.json({ success: true });
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

// ── POST /:projectId/tickets/:ticketId/git/create-pr ────────────────
// Create a GitHub PR for the ticket's feature branch

ticketsApi.post("/:projectId/tickets/:ticketId/git/create-pr", async (c) => {
  const user = c.get("user");
  const { projectId, ticketId } = c.req.param();

  const project = await resolveProject(projectId, user.id);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const [ticket] = await db
    .select()
    .from(projectTickets)
    .where(and(eq(projectTickets.id, ticketId), eq(projectTickets.projectId, project.id)));

  if (!ticket) return c.json({ error: "Ticket not found" }, 404);
  if (!ticket.githubBranch) return c.json({ error: "No branch found for this ticket" }, 400);

  // Get GitHub token
  const [ghToken] = await db
    .select()
    .from(githubTokens)
    .where(eq(githubTokens.userId, user.id))
    .limit(1);

  if (!ghToken?.accessToken) return c.json({ error: "GitHub not connected" }, 400);

  // Extract owner/repo from project stack
  const repoUrl = getProjectRepo(project);
  if (!repoUrl) return c.json({ error: "No GitHub repo configured for this project" }, 400);

  const [, repoOwner, repoName] = repoUrl;

  const { createPullRequest } = await import("../../services/git.ts");

  try {
    const { prNumber, prUrl } = await createPullRequest({
      repoOwner: repoOwner!,
      repoName: repoName!,
      featureBranch: ticket.githubBranch,
      targetBranch: "lfg-agent",
      title: `feat: ${ticket.name}`,
      body: `Automated PR for ticket: ${ticket.name}`,
      githubToken: ghToken.accessToken,
    });

    await db
      .update(projectTickets)
      .set({
        githubPrUrl: prUrl,
        githubPrNumber: prNumber,
        githubMergeStatus: "pr_open",
        updatedAt: new Date(),
      })
      .where(eq(projectTickets.id, ticketId));

    return c.json({ prNumber, prUrl });
  } catch (err) {
    return c.json({ error: `PR creation failed: ${err}` }, 500);
  }
});

// ── POST /:projectId/tickets/:ticketId/git/merge ────────────────────
// Merge the ticket's open PR

ticketsApi.post("/:projectId/tickets/:ticketId/git/merge", async (c) => {
  const user = c.get("user");
  const { projectId, ticketId } = c.req.param();

  const project = await resolveProject(projectId, user.id);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const [ticket] = await db
    .select()
    .from(projectTickets)
    .where(and(eq(projectTickets.id, ticketId), eq(projectTickets.projectId, project.id)));

  if (!ticket) return c.json({ error: "Ticket not found" }, 404);
  if (!ticket.githubPrNumber) return c.json({ error: "No PR found for this ticket" }, 400);

  // Get GitHub token
  const [ghToken] = await db
    .select()
    .from(githubTokens)
    .where(eq(githubTokens.userId, user.id))
    .limit(1);

  if (!ghToken?.accessToken) return c.json({ error: "GitHub not connected" }, 400);

  // Extract owner/repo
  const repoUrl = getProjectRepo(project);
  if (!repoUrl) return c.json({ error: "No GitHub repo configured" }, 400);

  const [, repoOwner, repoName] = repoUrl;

  const { mergePullRequest } = await import("../../services/git.ts");

  try {
    const { mergeCommitSha } = await mergePullRequest({
      repoOwner: repoOwner!,
      repoName: repoName!,
      prNumber: ticket.githubPrNumber,
      githubToken: ghToken.accessToken,
    });

    await db
      .update(projectTickets)
      .set({
        githubMergeStatus: "merged",
        githubMergeCommitSha: mergeCommitSha,
        updatedAt: new Date(),
      })
      .where(eq(projectTickets.id, ticketId));

    // Record merge history
    await db.insert(ticketMergeHistory).values({
      ticketId,
      action: "merged",
      mergeCommitSha,
      performedById: user.id,
      commitMessage: `feat: ${ticket.name}`,
    });

    return c.json({ mergeCommitSha });
  } catch (err) {
    await db
      .update(projectTickets)
      .set({ githubMergeStatus: "failed", updatedAt: new Date() })
      .where(eq(projectTickets.id, ticketId));

    return c.json({ error: `Merge failed: ${err}` }, 500);
  }
});

// ── POST /:projectId/tickets/:ticketId/git/push ─────────────────────
// Manually commit + push the sandbox code to GitHub

ticketsApi.post("/:projectId/tickets/:ticketId/git/push", async (c) => {
  const user = c.get("user");
  const { projectId, ticketId } = c.req.param();

  const project = await resolveProject(projectId, user.id);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const [ticket] = await db
    .select()
    .from(projectTickets)
    .where(and(eq(projectTickets.id, ticketId), eq(projectTickets.projectId, project.id)));

  if (!ticket) return c.json({ error: "Ticket not found" }, 404);

  // Get GitHub token
  const [ghToken] = await db
    .select()
    .from(githubTokens)
    .where(eq(githubTokens.userId, user.id))
    .limit(1);

  if (!ghToken?.accessToken) return c.json({ error: "GitHub not connected. Connect GitHub in Settings." }, 400);

  // Extract owner/repo
  const repoUrl = getProjectRepo(project);
  if (!repoUrl) return c.json({ error: "No GitHub repo configured for this project" }, 400);

  const [, repoOwner, repoName] = repoUrl;

  // Find sandbox
  const [sandbox] = await db
    .select()
    .from(sandboxes)
    .where(and(eq(sandboxes.ticketId, ticketId), eq(sandboxes.workspaceType, "ticket")))
    .limit(1);

  if (!sandbox?.magsWorkspaceId) {
    return c.json({ error: "No active sandbox. Build the ticket first." }, 400);
  }

  const { commitAndPush, createPullRequest } = await import("../../services/git.ts");

  const featureBranch = ticket.githubBranch ?? `feature/ticket-${ticketId}`;

  try {
    const { sha } = await commitAndPush({
      workspaceId: sandbox.magsWorkspaceId,
      projectDir: "/root/project",
      commitMessage: `update: ${ticket.name}`,
      featureBranch,
      repoUrl: `https://github.com/${repoOwner}/${repoName}.git`,
      githubToken: ghToken.accessToken,
    });

    await db
      .update(projectTickets)
      .set({
        githubBranch: featureBranch,
        githubCommitSha: sha,
        updatedAt: new Date(),
      })
      .where(eq(projectTickets.id, ticketId));

    // Merge feature branch → lfg-agent (direct push)
    let mergeStatus = ticket.githubMergeStatus;
    try {
      const { mergeToLfgAgent } = await import("../../services/git.ts");
      const { sha: mergeSha } = await mergeToLfgAgent({
        workspaceId: sandbox.magsWorkspaceId,
        projectDir: "/root/project",
        featureBranch,
        repoUrl: `https://github.com/${repoOwner}/${repoName}.git`,
        githubToken: ghToken.accessToken,
      });
      mergeStatus = "merged";
      await db
        .update(projectTickets)
        .set({ githubMergeStatus: "merged", updatedAt: new Date() })
        .where(eq(projectTickets.id, ticketId));
    } catch (mergeErr) {
      console.warn(`[tickets] Merge to lfg-agent failed during push:`, mergeErr);
    }

    return c.json({ sha, branch: featureBranch, mergeStatus });
  } catch (err) {
    return c.json({ error: `Push failed: ${err}` }, 500);
  }
});

// ── Helpers ──────────────────────────────────────────────────────────

/**
 * Extract repo owner/name from project fields, falling back to parsing stack text.
 * Returns a regex match array [full, owner, name] or null.
 */
function getProjectRepo(project: { repoOwner?: string | null; repoName?: string | null; repoUrl?: string | null; stack?: string | null }) {
  if (project.repoOwner && project.repoName) {
    return [`https://github.com/${project.repoOwner}/${project.repoName}`, project.repoOwner, project.repoName];
  }
  const url = project.repoUrl ?? project.stack ?? "";
  return url.match(/https?:\/\/github\.com\/([^/]+)\/([^/.]+)/);
}

export default ticketsApi;
