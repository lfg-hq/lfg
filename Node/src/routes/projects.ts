import { Hono } from "hono";
import { requireAuth } from "../auth/middleware.ts";
import { db } from "../config/db.ts";
import {
  projects,
  projectEnvironmentVariables,
} from "../db/schema/projects.ts";
import { projectFiles, projectFileVersions } from "../db/schema/documents.ts";
import { conversations } from "../db/schema/chat.ts";
import { ticketStages, projectTickets } from "../db/schema/tickets.ts";
import { eq, and, desc, asc } from "drizzle-orm";
import { saveContent, getContent, deleteContent } from "../services/s3.ts";
import { ProjectListPage } from "../templates/pages/project-list.tsx";
import { ProjectDetailPage } from "../templates/pages/project-detail.tsx";
import { TicketsListPage } from "../templates/pages/tickets-list.tsx";
import type { auth } from "../auth/index.ts";

type AuthEnv = {
  Variables: {
    user: typeof auth.$Infer.Session.user;
    session: typeof auth.$Infer.Session.session;
  };
};

const DEFAULT_STAGES = [
  { name: "Backlog", color: "#6b7280", order: 0, isDefault: true, isCompleted: false },
  { name: "Todo", color: "#3b82f6", order: 1, isDefault: false, isCompleted: false },
  { name: "In Progress", color: "#f59e0b", order: 2, isDefault: false, isCompleted: false },
  { name: "In Review", color: "#8b5cf6", order: 3, isDefault: false, isCompleted: false },
  { name: "Done", color: "#22c55e", order: 4, isDefault: false, isCompleted: true },
];

async function createDefaultStages(projectId: string) {
  await db.insert(ticketStages).values(
    DEFAULT_STAGES.map((s) => ({ ...s, projectId }))
  );
}

const projectsRouter = new Hono<AuthEnv>();
projectsRouter.use("*", requireAuth);

// ── GET /projects — project list ────────────────────────────────────
projectsRouter.get("/projects", async (c) => {
  const user = c.get("user");

  const rows = await db
    .select()
    .from(projects)
    .where(eq(projects.ownerId, user.id))
    .orderBy(desc(projects.createdAt));

  return c.html(ProjectListPage({ user: { id: user.id, name: user.name, email: user.email }, projects: rows }));
});

// ── POST /projects/create — create project ──────────────────────────
projectsRouter.post("/projects/create", async (c) => {
  const user = c.get("user");
  const body = await c.req.parseBody();

  const name = (body["name"] as string | undefined)?.trim();
  const description = (body["description"] as string | undefined)?.trim() || null;
  const icon = (body["icon"] as string | undefined) ?? "📋";

  if (!name) {
    const rows = await db.select().from(projects).where(eq(projects.ownerId, user.id)).orderBy(desc(projects.createdAt));
    return c.html(
      ProjectListPage({ user: { id: user.id, name: user.name, email: user.email }, projects: rows, error: "Project name is required" }),
      422
    );
  }

  const [project] = await db
    .insert(projects)
    .values({ name, description: description ?? undefined, icon, ownerId: user.id })
    .returning();

  if (!project) return c.text("Failed to create project", 500);

  // Create default ticket stages
  await createDefaultStages(project.id);

  return c.redirect(`/projects/${project.projectId}`);
});

// ── GET /projects/:projectId — project detail ───────────────────────
projectsRouter.get("/projects/:projectId", async (c) => {
  const user = c.get("user");
  const { projectId } = c.req.param();
  if (!projectId) return c.text("Missing projectId", 400);

  const tab = c.req.query("tab") ?? "conversations";

  const [project] = await db
    .select()
    .from(projects)
    .where(and(eq(projects.projectId, projectId), eq(projects.ownerId, user.id)));

  if (!project) return c.text("Project not found", 404);

  const [convRows, stageRows, envRows] = await Promise.all([
    db.select().from(conversations)
      .where(eq(conversations.projectId, project.id))
      .orderBy(desc(conversations.updatedAt))
      .limit(50),
    db.select().from(ticketStages)
      .where(eq(ticketStages.projectId, project.id))
      .orderBy(asc(ticketStages.order)),
    db.select().from(projectEnvironmentVariables)
      .where(eq(projectEnvironmentVariables.projectId, project.id))
      .orderBy(asc(projectEnvironmentVariables.key)),
  ]);

  // Count tickets per stage
  const ticketRows = await db
    .select({ stageId: projectTickets.stageId })
    .from(projectTickets)
    .where(eq(projectTickets.projectId, project.id));

  const ticketCounts: Record<string, number> = {};
  for (const row of ticketRows) {
    if (row.stageId) ticketCounts[row.stageId] = (ticketCounts[row.stageId] ?? 0) + 1;
  }

  return c.html(
    ProjectDetailPage({
      user: { id: user.id, name: user.name, email: user.email },
      project: {
        id: project.id,
        projectId: project.projectId,
        name: project.name,
        icon: project.icon,
        status: project.status,
        description: project.description ?? null,
        stack: project.stack ?? null,
      },
      conversations: convRows,
      stages: stageRows,
      ticketCounts,
      envVars: envRows.map((e) => ({
        id: e.id,
        key: e.key,
        isSecret: e.isSecret,
        hasValue: e.hasValue,
        description: e.description ?? null,
      })),
      activeTab: tab,
    })
  );
});

// ── POST /projects/:projectId/update — update project ───────────────
projectsRouter.post("/projects/:projectId/update", async (c) => {
  const user = c.get("user");
  const { projectId } = c.req.param();
  if (!projectId) return c.text("Missing projectId", 400);

  const body = await c.req.parseBody();
  const name = (body["name"] as string | undefined)?.trim();
  const description = (body["description"] as string | undefined)?.trim() || null;
  const stack = (body["stack"] as string | undefined)?.trim() || null;

  if (!name) return c.redirect(`/projects/${projectId}?tab=settings&error=Name+required`);

  const [project] = await db
    .select({ id: projects.id })
    .from(projects)
    .where(and(eq(projects.projectId, projectId), eq(projects.ownerId, user.id)));

  if (!project) return c.text("Project not found", 404);

  await db
    .update(projects)
    .set({ name, description: description ?? undefined, stack: stack ?? undefined, updatedAt: new Date() })
    .where(eq(projects.id, project.id));

  return c.redirect(`/projects/${projectId}?tab=settings`);
});

// ── POST /projects/:projectId/delete — delete project ───────────────
projectsRouter.post("/projects/:projectId/delete", async (c) => {
  const user = c.get("user");
  const { projectId } = c.req.param();
  if (!projectId) return c.text("Missing projectId", 400);

  const [project] = await db
    .select({ id: projects.id })
    .from(projects)
    .where(and(eq(projects.projectId, projectId), eq(projects.ownerId, user.id)));

  if (!project) return c.text("Project not found", 404);

  await db.delete(projects).where(eq(projects.id, project.id));
  return c.redirect("/projects");
});

// ── GET /projects/:projectId/tickets — tickets kanban ───────────────
projectsRouter.get("/projects/:projectId/tickets", async (c) => {
  const user = c.get("user");
  const { projectId } = c.req.param();
  if (!projectId) return c.text("Missing projectId", 400);

  const [project] = await db
    .select()
    .from(projects)
    .where(and(eq(projects.projectId, projectId), eq(projects.ownerId, user.id)));

  if (!project) return c.text("Project not found", 404);

  const [stageRows, ticketRows] = await Promise.all([
    db.select().from(ticketStages)
      .where(eq(ticketStages.projectId, project.id))
      .orderBy(asc(ticketStages.order)),
    db.select({
      id: projectTickets.id,
      name: projectTickets.name,
      status: projectTickets.status,
      priority: projectTickets.priority,
      stageId: projectTickets.stageId,
      complexity: projectTickets.complexity,
      queueStatus: projectTickets.queueStatus,
      description: projectTickets.description,
    }).from(projectTickets)
      .where(eq(projectTickets.projectId, project.id))
      .orderBy(asc(projectTickets.createdAt)),
  ]);

  return c.html(
    TicketsListPage({
      user: { id: user.id, name: user.name, email: user.email },
      project: {
        id: project.id,
        projectId: project.projectId,
        name: project.name,
        icon: project.icon,
      },
      stages: stageRows,
      tickets: ticketRows,
    })
  );
});

// ── DELETE /projects/:projectId/api/checklist/:ticketId/delete ───────
projectsRouter.delete("/projects/:projectId/api/checklist/:ticketId/delete", async (c) => {
  const user = c.get("user");
  const { projectId, ticketId } = c.req.param();

  const [project] = await db
    .select()
    .from(projects)
    .where(and(eq(projects.projectId, projectId!), eq(projects.ownerId, user.id)));

  if (!project) return c.json({ error: "Project not found" }, 404);

  const result = await db.delete(projectTickets).where(
    and(eq(projectTickets.id, ticketId!), eq(projectTickets.projectId, project.id))
  );

  return c.json({ success: true, deleted: 1 });
});

// ── PATCH /projects/:projectId/api/checklist/:ticketId/stage — move ticket between stages
projectsRouter.patch("/projects/:projectId/api/checklist/:ticketId/stage", async (c) => {
  const user = c.get("user");
  const { projectId, ticketId } = c.req.param();
  const { stageId } = await c.req.json();

  const [project] = await db
    .select()
    .from(projects)
    .where(and(eq(projects.projectId, projectId!), eq(projects.ownerId, user.id)));

  if (!project) return c.json({ error: "Project not found" }, 404);

  await db.update(projectTickets).set({ stageId, updatedAt: new Date() }).where(
    and(eq(projectTickets.id, ticketId!), eq(projectTickets.projectId, project.id))
  );

  return c.json({ success: true });
});

// ── GET /projects/:projectId/api/checklist/:ticketId — get single ticket
projectsRouter.get("/projects/:projectId/api/checklist/:ticketId", async (c) => {
  const user = c.get("user");
  const { projectId, ticketId } = c.req.param();

  const [project] = await db
    .select()
    .from(projects)
    .where(and(eq(projects.projectId, projectId!), eq(projects.ownerId, user.id)));

  if (!project) return c.json({ error: "Project not found" }, 404);

  const [ticket] = await db.select().from(projectTickets).where(
    and(eq(projectTickets.id, ticketId!), eq(projectTickets.projectId, project.id))
  );

  if (!ticket) return c.json({ error: "Ticket not found" }, 404);

  return c.json({ ticket });
});

// ── Compat: GET /projects/:projectId/api/checklist ──────────────────
// artifacts-loader.js (Django-era) fetches this URL for the Task List tab.
// We return project tickets in a compatible format.
projectsRouter.get("/projects/:projectId/api/checklist", async (c) => {
  const user = c.get("user");
  const { projectId } = c.req.param();

  const [project] = await db
    .select()
    .from(projects)
    .where(and(eq(projects.projectId, projectId!), eq(projects.ownerId, user.id)));

  if (!project) return c.json({ tickets: [] });

  const [stageRows, ticketRows] = await Promise.all([
    db.select().from(ticketStages).where(eq(ticketStages.projectId, project.id)).orderBy(asc(ticketStages.order)),
    db.select().from(projectTickets).where(eq(projectTickets.projectId, project.id)).orderBy(asc(projectTickets.createdAt)),
  ]);

  const stageMap = Object.fromEntries(stageRows.map((s) => [s.id, s.name]));

  const tickets = ticketRows.map((t) => ({
    id: t.id,
    name: t.name,
    description: t.description,
    status: t.status ?? "open",
    priority: t.priority ?? "Medium",
    complexity: t.complexity ?? "medium",
    stage: stageMap[t.stageId ?? ""] ?? "Backlog",
    stage_id: t.stageId,
    queue_status: t.queueStatus,
    created_at: t.createdAt,
    updated_at: t.updatedAt,
  }));

  return c.json({ tickets });
});

// ── Compat: GET /projects/:projectId/api/files/browser ──────────────
// artifacts-loader.js (Django-era) fetches this URL for the Docs tab file list.
projectsRouter.get("/projects/:projectId/api/files/browser", async (c) => {
  const user = c.get("user");
  const { projectId } = c.req.param();

  const [project] = await db
    .select()
    .from(projects)
    .where(and(eq(projects.projectId, projectId!), eq(projects.ownerId, user.id)));

  if (!project) return c.json({ files: [], total: 0, pages: 1 });

  const fileRows = await db
    .select()
    .from(projectFiles)
    .where(eq(projectFiles.projectId, project.id))
    .orderBy(desc(projectFiles.updatedAt));

  const files = fileRows.map((f) => ({
    id: f.id,
    name: f.name,
    type: f.fileType,
    updated_at: f.updatedAt,
    created_at: f.createdAt,
  }));

  return c.json({ files, total: files.length, pages: 1, filters: { types: [...new Set(files.map((f) => f.type))] } });
});

// ── Compat: GET /projects/:projectId/api/files/:fileId/content ───────
// artifacts-loader.js viewFileContent() fetches this to display file in viewer.
projectsRouter.get("/projects/:projectId/api/files/:fileId/content", async (c) => {
  const { fileId } = c.req.param();

  const [file] = await db.select().from(projectFiles).where(eq(projectFiles.id, fileId!));
  if (!file) return c.json({ error: "File not found" }, 404);

  const content = await getContent(file.s3Key, file.content);
  return c.json({ id: file.id, name: file.name, type: file.fileType, content });
});

// ── Helper: resolve public projectId → internal project row ──────────
async function resolveProject(publicProjectId: string, ownerId: string) {
  const [project] = await db
    .select()
    .from(projects)
    .where(and(eq(projects.projectId, publicProjectId), eq(projects.ownerId, ownerId)));
  return project ?? null;
}

// ── Helper: save a version snapshot before overwriting content ────────
async function saveVersion(fileId: string, content: string, userId: string) {
  // Get max version number for this file
  const existing = await db
    .select({ versionNumber: projectFileVersions.versionNumber })
    .from(projectFileVersions)
    .where(eq(projectFileVersions.fileId, fileId))
    .orderBy(desc(projectFileVersions.versionNumber))
    .limit(1);
  const nextVersion = (existing[0]?.versionNumber ?? 0) + 1;
  await db.insert(projectFileVersions).values({
    fileId,
    versionNumber: nextVersion,
    content,
    createdById: userId,
    changeDescription: "Manual save",
  });
}

// ── POST /projects/:projectId/api/files — update file content ─────────
// artifacts-loader.js saveFileContent() calls this for non-prd/impl types.
// Also handles prd/implementation via type query param for uniformity.
projectsRouter.post("/projects/:projectId/api/files", async (c) => {
  const user = c.get("user");
  const { projectId } = c.req.param();

  const project = await resolveProject(projectId, user.id);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const type = c.req.query("type") ?? "";
  const name = c.req.query("name") ?? "";
  const body = await c.req.json() as { content?: string };
  const content = body.content ?? "";

  const [file] = await db
    .select()
    .from(projectFiles)
    .where(and(eq(projectFiles.projectId, project.id), eq(projectFiles.fileType, type), eq(projectFiles.name, name)));

  if (!file) return c.json({ error: "File not found" }, 404);

  const currentContent = await getContent(file.s3Key, file.content);
  await saveVersion(file.id, currentContent, user.id);

  const { s3Key, dbContent } = await saveContent(project.id, type, name, content);
  const [updated] = await db
    .update(projectFiles)
    .set({ content: dbContent, s3Key, updatedAt: new Date() })
    .where(eq(projectFiles.id, file.id))
    .returning();

  return c.json({ success: true, id: updated!.id, name: updated!.name, type: updated!.fileType });
});

// ── POST /projects/:projectId/api/prd — compat save for PRD files ─────
projectsRouter.post("/projects/:projectId/api/prd", async (c) => {
  const user = c.get("user");
  const { projectId } = c.req.param();

  const project = await resolveProject(projectId, user.id);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const prdName = c.req.query("prd_name") ?? "Main PRD";
  const body = await c.req.json() as { content?: string };
  const content = body.content ?? "";

  const [file] = await db
    .select()
    .from(projectFiles)
    .where(and(eq(projectFiles.projectId, project.id), eq(projectFiles.fileType, "prd"), eq(projectFiles.name, prdName)));

  if (!file) return c.json({ error: "PRD not found" }, 404);

  const currentContent = await getContent(file.s3Key, file.content);
  await saveVersion(file.id, currentContent, user.id);

  const { s3Key, dbContent } = await saveContent(project.id, "prd", prdName, content);
  await db.update(projectFiles).set({ content: dbContent, s3Key, updatedAt: new Date() }).where(eq(projectFiles.id, file.id));

  return c.json({ success: true, id: file.id, name: prdName, type: "prd" });
});

// ── POST /projects/:projectId/api/implementation — compat save ────────
projectsRouter.post("/projects/:projectId/api/implementation", async (c) => {
  const user = c.get("user");
  const { projectId } = c.req.param();

  const project = await resolveProject(projectId, user.id);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const body = await c.req.json() as { content?: string };
  const content = body.content ?? "";

  const [file] = await db
    .select()
    .from(projectFiles)
    .where(and(eq(projectFiles.projectId, project.id), eq(projectFiles.fileType, "implementation")))
    .orderBy(desc(projectFiles.updatedAt))
    .limit(1);

  if (!file) return c.json({ error: "Implementation not found" }, 404);

  const currentContent = await getContent(file.s3Key, file.content);
  await saveVersion(file.id, currentContent, user.id);

  const { s3Key, dbContent } = await saveContent(project.id, "implementation", file.name, content);
  await db.update(projectFiles).set({ content: dbContent, s3Key, updatedAt: new Date() }).where(eq(projectFiles.id, file.id));

  return c.json({ success: true, id: file.id, name: file.name, type: "implementation" });
});

// ── DELETE /projects/:projectId/api/files — delete by type+name ──────
// artifacts-loader.js deleteFile() calls this.
projectsRouter.delete("/projects/:projectId/api/files", async (c) => {
  const user = c.get("user");
  const { projectId } = c.req.param();

  const project = await resolveProject(projectId, user.id);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const type = c.req.query("type") ?? "";
  const name = c.req.query("name") ?? "";

  const [file] = await db
    .select()
    .from(projectFiles)
    .where(and(eq(projectFiles.projectId, project.id), eq(projectFiles.fileType, type), eq(projectFiles.name, name)));

  if (!file) return c.json({ error: "File not found" }, 404);

  await deleteContent(file.s3Key);
  await db.delete(projectFiles).where(eq(projectFiles.id, file.id));

  return c.json({ success: true });
});

// ── GET /projects/:projectId/api/files/:fileId/versions — list versions
projectsRouter.get("/projects/:projectId/api/files/:fileId/versions", async (c) => {
  const { fileId } = c.req.param();

  const versions = await db
    .select()
    .from(projectFileVersions)
    .where(eq(projectFileVersions.fileId, fileId!))
    .orderBy(desc(projectFileVersions.versionNumber));

  return c.json({ versions });
});

// ── GET /projects/:projectId/api/files/:fileId/versions/:versionNumber — fetch single version content
projectsRouter.get("/projects/:projectId/api/files/:fileId/versions/:versionNumber", async (c) => {
  const { fileId, versionNumber } = c.req.param();

  const [version] = await db
    .select()
    .from(projectFileVersions)
    .where(and(eq(projectFileVersions.fileId, fileId!), eq(projectFileVersions.versionNumber, Number(versionNumber))));

  if (!version) return c.json({ success: false, error: "Version not found" }, 404);

  const content = await getContent(null, version.content);
  return c.json({ success: true, version: { ...version, content } });
});

// ── POST /projects/:projectId/api/files/:fileId/versions/:versionId/restore
projectsRouter.post("/projects/:projectId/api/files/:fileId/versions/:versionNumber/restore", async (c) => {
  const user = c.get("user");
  const { fileId, versionNumber } = c.req.param();

  const [version] = await db
    .select()
    .from(projectFileVersions)
    .where(and(eq(projectFileVersions.fileId, fileId!), eq(projectFileVersions.versionNumber, Number(versionNumber))));

  if (!version) return c.json({ error: "Version not found" }, 404);

  const [file] = await db.select().from(projectFiles).where(eq(projectFiles.id, fileId!));
  if (!file) return c.json({ error: "File not found" }, 404);

  // Snapshot current content before restoring
  const currentContent = await getContent(file.s3Key, file.content);
  await saveVersion(fileId!, currentContent, user.id);

  // Save restored content (respects S3 if enabled)
  const { s3Key: newKey, dbContent: newContent } = await saveContent(file.projectId, file.fileType, file.name, version.content ?? "");
  await db.update(projectFiles).set({ content: newContent, s3Key: newKey, updatedAt: new Date() }).where(eq(projectFiles.id, fileId!));

  return c.json({ success: true, restoredVersion: version.versionNumber, message: `Restored to version ${version.versionNumber}` });
});

export default projectsRouter;
