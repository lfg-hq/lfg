import { Hono } from "hono";
import { and, desc, eq } from "drizzle-orm";
import { requireAuth } from "../../auth/middleware.ts";
import { db } from "../../config/db.ts";
import { instantApps } from "../../db/schema/instant.ts";
import { projects } from "../../db/schema/projects.ts";
import { sandboxes } from "../../db/schema/sandbox.ts";
import { execOnWorkspace } from "../../services/mags.ts";
import type { auth } from "../../auth/index.ts";

type AuthEnv = {
  Variables: {
    user: typeof auth.$Infer.Session.user;
    session: typeof auth.$Infer.Session.session;
  };
};

const instantApi = new Hono<AuthEnv>();
instantApi.use("*", requireAuth);

async function resolveProjectForUser(userId: string, publicProjectId: string) {
  const [project] = await db
    .select({ id: projects.id, projectId: projects.projectId })
    .from(projects)
    .where(and(eq(projects.projectId, publicProjectId), eq(projects.ownerId, userId)))
    .limit(1);
  return project ?? null;
}

async function getAppForUser(userId: string, appId: string, internalProjectId?: string) {
  const predicates = [eq(instantApps.userId, userId), eq(instantApps.appId, appId)];
  if (internalProjectId) predicates.push(eq(instantApps.projectId, internalProjectId));

  const [row] = await db
    .select({ app: instantApps, sandbox: sandboxes })
    .from(instantApps)
    .leftJoin(sandboxes, eq(instantApps.sandboxId, sandboxes.id))
    .where(and(...predicates))
    .limit(1);

  return row ?? null;
}

async function fetchWorkspaceLogs(workspaceId: string, offset: number) {
  const cmd =
    offset > 0
      ? `tail -c +${offset + 1} /home/claudeuser/project/dev.log 2>/dev/null || echo ''`
      : "tail -n 200 /home/claudeuser/project/dev.log 2>/dev/null || echo ''";
  const result = await execOnWorkspace(workspaceId, cmd, { timeout: 15_000 });
  const logs = result.output ?? "";
  return {
    logs,
    offset: offset + Buffer.byteLength(logs, "utf8"),
  };
}

async function rebuildWorkspace(workspaceId: string) {
  const cmd =
    "cd /home/claudeuser/project && (pkill -f 'next start' 2>/dev/null || true) && npm run build && nohup npm start -p 8080 -H 0.0.0.0 > dev.log 2>&1 &";
  await execOnWorkspace(workspaceId, cmd, { timeout: 180_000 });
}

// Standalone endpoints (must be declared before project-scoped dynamic segment)
instantApi.get("/apps/:appId/env", async (c) => {
  const user = c.get("user");
  const { appId } = c.req.param();
  const row = await getAppForUser(user.id, appId);
  if (!row) return c.json({ error: "Not found" }, 404);
  return c.json({ env_vars: (row.app.envVars as Record<string, string> | null) ?? {} });
});

instantApi.post("/apps/:appId/env", async (c) => {
  const user = c.get("user");
  const { appId } = c.req.param();
  const row = await getAppForUser(user.id, appId);
  if (!row) return c.json({ error: "Not found" }, 404);

  const body = await c.req
    .json<{ env_vars?: Record<string, string> }>()
    .catch(() => ({ env_vars: {} as Record<string, string> }));
  const envVars = body.env_vars ?? {};
  await db
    .update(instantApps)
    .set({ envVars, updatedAt: new Date() })
    .where(eq(instantApps.id, row.app.id));
  return c.json({ env_vars: envVars });
});

instantApi.get("/apps/:appId/logs", async (c) => {
  const user = c.get("user");
  const { appId } = c.req.param();
  const row = await getAppForUser(user.id, appId);
  if (!row) return c.json({ error: "Not found" }, 404);
  if (!row.sandbox?.magsWorkspaceId) return c.json({ logs: "", error: "No sandbox available" });

  const offset = parseInt(c.req.query("offset") ?? "0", 10) || 0;
  const payload = await fetchWorkspaceLogs(row.sandbox.magsWorkspaceId, offset);
  return c.json(payload);
});

instantApi.post("/apps/:appId/rebuild", async (c) => {
  const user = c.get("user");
  const { appId } = c.req.param();
  const row = await getAppForUser(user.id, appId);
  if (!row) return c.json({ error: "Not found" }, 404);
  if (!row.sandbox?.magsWorkspaceId) return c.json({ error: "No sandbox available" }, 400);

  await rebuildWorkspace(row.sandbox.magsWorkspaceId);
  return c.json({ status: "ok", message: "Rebuild started" });
});

// Project scoped
instantApi.get("/:projectId/apps", async (c) => {
  const user = c.get("user");
  const { projectId } = c.req.param();
  const project = await resolveProjectForUser(user.id, projectId);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const apps = await db
    .select()
    .from(instantApps)
    .where(and(eq(instantApps.userId, user.id), eq(instantApps.projectId, project.id)))
    .orderBy(desc(instantApps.createdAt));

  return c.json({
    apps: apps.map((app) => ({
      app_id: app.appId,
      name: app.name,
      description: (app.description ?? "").slice(0, 200),
      status: app.status,
      preview_url: app.previewUrl ?? "",
      created_at: app.createdAt,
    })),
  });
});

instantApi.get("/:projectId/apps/:appId/env", async (c) => {
  const user = c.get("user");
  const { projectId, appId } = c.req.param();
  const project = await resolveProjectForUser(user.id, projectId);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const row = await getAppForUser(user.id, appId, project.id);
  if (!row) return c.json({ error: "Not found" }, 404);
  return c.json({ env_vars: (row.app.envVars as Record<string, string> | null) ?? {} });
});

instantApi.post("/:projectId/apps/:appId/env", async (c) => {
  const user = c.get("user");
  const { projectId, appId } = c.req.param();
  const project = await resolveProjectForUser(user.id, projectId);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const row = await getAppForUser(user.id, appId, project.id);
  if (!row) return c.json({ error: "Not found" }, 404);

  const body = await c.req
    .json<{ env_vars?: Record<string, string> }>()
    .catch(() => ({ env_vars: {} as Record<string, string> }));
  const envVars = body.env_vars ?? {};
  await db
    .update(instantApps)
    .set({ envVars, updatedAt: new Date() })
    .where(eq(instantApps.id, row.app.id));

  return c.json({ env_vars: envVars });
});

instantApi.get("/:projectId/apps/:appId/logs", async (c) => {
  const user = c.get("user");
  const { projectId, appId } = c.req.param();
  const project = await resolveProjectForUser(user.id, projectId);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const row = await getAppForUser(user.id, appId, project.id);
  if (!row) return c.json({ error: "Not found" }, 404);
  if (!row.sandbox?.magsWorkspaceId) return c.json({ logs: "", error: "No sandbox available" });

  const offset = parseInt(c.req.query("offset") ?? "0", 10) || 0;
  const payload = await fetchWorkspaceLogs(row.sandbox.magsWorkspaceId, offset);
  return c.json(payload);
});

instantApi.post("/:projectId/apps/:appId/rebuild", async (c) => {
  const user = c.get("user");
  const { projectId, appId } = c.req.param();
  const project = await resolveProjectForUser(user.id, projectId);
  if (!project) return c.json({ error: "Project not found" }, 404);

  const row = await getAppForUser(user.id, appId, project.id);
  if (!row) return c.json({ error: "Not found" }, 404);
  if (!row.sandbox?.magsWorkspaceId) return c.json({ error: "No sandbox available" }, 400);

  await rebuildWorkspace(row.sandbox.magsWorkspaceId);
  return c.json({ status: "ok", message: "Rebuild started" });
});

export default instantApi;
