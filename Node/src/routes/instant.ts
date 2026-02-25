import { Hono } from "hono";
import { and, desc, eq, isNull } from "drizzle-orm";
import { requireAuth } from "../auth/middleware.ts";
import { db } from "../config/db.ts";
import { projects } from "../db/schema/projects.ts";
import { modelSelections, agentRoles } from "../db/schema/chat.ts";
import { instantApps } from "../db/schema/instant.ts";
import { listModels, DEFAULT_MODEL_KEY } from "../ai/provider.ts";
import { InstantPage } from "../templates/pages/instant.tsx";
import type { auth } from "../auth/index.ts";

type AuthEnv = {
  Variables: {
    user: typeof auth.$Infer.Session.user;
    session: typeof auth.$Infer.Session.session;
  };
};

const instant = new Hono<AuthEnv>();
instant.use("*", requireAuth);
type InstantAppRow = typeof instantApps.$inferSelect;

async function getUserChatSettings(userId: string) {
  const [modelSel, roleRow] = await Promise.all([
    db.select().from(modelSelections).where(eq(modelSelections.userId, userId)).then((rows) => rows[0]),
    db.select().from(agentRoles).where(eq(agentRoles.userId, userId)).then((rows) => rows[0]),
  ]);
  return {
    modelKey: modelSel?.selectedModel ?? DEFAULT_MODEL_KEY,
    roleKey: roleRow?.name ?? "product_analyst",
  };
}

async function getProjectForUser(userId: string, publicProjectId: string) {
  const [project] = await db
    .select({ id: projects.id, projectId: projects.projectId, name: projects.name })
    .from(projects)
    .where(and(eq(projects.projectId, publicProjectId), eq(projects.ownerId, userId)))
    .limit(1);
  return project ?? null;
}

function toPageApp(app: InstantAppRow) {
  return {
    appId: app.appId,
    name: app.name,
    status: app.status,
    previewUrl: app.previewUrl,
    conversationId: app.conversationId,
  };
}

instant.get("/instant", async (c) => {
  const user = c.get("user");
  const settings = await getUserChatSettings(user.id);
  const apps = await db
    .select()
    .from(instantApps)
    .where(and(eq(instantApps.userId, user.id), isNull(instantApps.projectId)))
    .orderBy(desc(instantApps.createdAt));

  return c.html(
    InstantPage({
      user: { id: user.id, name: user.name, email: user.email ?? "" },
      standaloneMode: true,
      modelKey: settings.modelKey,
      roleKey: settings.roleKey,
      models: listModels().map((model) => ({
        key: model.key,
        providerLabel: model.providerLabel,
        requiresPro: model.requiresPro,
      })),
      currentApp: null,
      instantApps: apps.map(toPageApp),
    })
  );
});

instant.get("/instant/app/:appId", async (c) => {
  const user = c.get("user");
  const { appId } = c.req.param();
  const settings = await getUserChatSettings(user.id);

  const [currentApp, apps] = await Promise.all([
    db
      .select()
      .from(instantApps)
      .where(and(eq(instantApps.userId, user.id), eq(instantApps.appId, appId), isNull(instantApps.projectId)))
      .limit(1)
      .then((rows) => rows[0] ?? null),
    db
      .select()
      .from(instantApps)
      .where(and(eq(instantApps.userId, user.id), isNull(instantApps.projectId)))
      .orderBy(desc(instantApps.createdAt)),
  ]);

  if (!currentApp) return c.text("Instant app not found", 404);

  return c.html(
    InstantPage({
      user: { id: user.id, name: user.name, email: user.email ?? "" },
      standaloneMode: true,
      modelKey: settings.modelKey,
      roleKey: settings.roleKey,
      models: listModels().map((model) => ({
        key: model.key,
        providerLabel: model.providerLabel,
        requiresPro: model.requiresPro,
      })),
      currentApp: toPageApp(currentApp),
      instantApps: apps.map(toPageApp),
    })
  );
});

instant.get("/instant/project/:projectId", async (c) => {
  const user = c.get("user");
  const { projectId } = c.req.param();
  const project = await getProjectForUser(user.id, projectId);
  if (!project) return c.text("Project not found", 404);

  const settings = await getUserChatSettings(user.id);
  const apps = await db
    .select()
    .from(instantApps)
    .where(and(eq(instantApps.userId, user.id), eq(instantApps.projectId, project.id)))
    .orderBy(desc(instantApps.createdAt));

  return c.html(
    InstantPage({
      user: { id: user.id, name: user.name, email: user.email ?? "" },
      standaloneMode: false,
      projectId: project.projectId,
      projectName: project.name,
      modelKey: settings.modelKey,
      roleKey: settings.roleKey,
      models: listModels().map((model) => ({
        key: model.key,
        providerLabel: model.providerLabel,
        requiresPro: model.requiresPro,
      })),
      currentApp: null,
      instantApps: apps.map(toPageApp),
    })
  );
});

instant.get("/instant/project/:projectId/app/:appId", async (c) => {
  const user = c.get("user");
  const { projectId, appId } = c.req.param();
  const project = await getProjectForUser(user.id, projectId);
  if (!project) return c.text("Project not found", 404);

  const settings = await getUserChatSettings(user.id);
  const [currentApp, apps] = await Promise.all([
    db
      .select()
      .from(instantApps)
      .where(and(eq(instantApps.userId, user.id), eq(instantApps.projectId, project.id), eq(instantApps.appId, appId)))
      .limit(1)
      .then((rows) => rows[0] ?? null),
    db
      .select()
      .from(instantApps)
      .where(and(eq(instantApps.userId, user.id), eq(instantApps.projectId, project.id)))
      .orderBy(desc(instantApps.createdAt)),
  ]);

  if (!currentApp) return c.text("Instant app not found", 404);

  return c.html(
    InstantPage({
      user: { id: user.id, name: user.name, email: user.email ?? "" },
      standaloneMode: false,
      projectId: project.projectId,
      projectName: project.name,
      modelKey: settings.modelKey,
      roleKey: settings.roleKey,
      models: listModels().map((model) => ({
        key: model.key,
        providerLabel: model.providerLabel,
        requiresPro: model.requiresPro,
      })),
      currentApp: toPageApp(currentApp),
      instantApps: apps.map(toPageApp),
    })
  );
});

export default instant;
