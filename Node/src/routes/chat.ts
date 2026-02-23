import { Hono } from "hono";
import { requireAuth } from "../auth/middleware.ts";
import { db } from "../config/db.ts";
import { projects } from "../db/schema/projects.ts";
import { modelSelections, agentRoles } from "../db/schema/chat.ts";
import { eq } from "drizzle-orm";
import { listModels, DEFAULT_MODEL_KEY } from "../ai/provider.ts";
import { ChatPage } from "../templates/pages/chat.tsx";
import type { auth } from "../auth/index.ts";

type AuthEnv = {
  Variables: {
    user: typeof auth.$Infer.Session.user;
    session: typeof auth.$Infer.Session.session;
  };
};

const chat = new Hono<AuthEnv>();
chat.use("*", requireAuth);

// GET /chat/project/:projectId
// GET /chat/project/:projectId/conversation/:conversationId
async function handleChatPage(c: import("hono").Context, conversationId?: string) {
  const user = c.get("user");
  const { projectId } = c.req.param();

  if (!projectId) return c.text("Missing projectId", 400);

  const [project] = await db
    .select({ id: projects.id, name: projects.name })
    .from(projects)
    .where(eq(projects.projectId, projectId));

  if (!project) {
    return c.text("Project not found", 404);
  }

  const [modelSel, roleRow] = await Promise.all([
    db.select().from(modelSelections).where(eq(modelSelections.userId, user.id)).then((r) => r[0]),
    db.select().from(agentRoles).where(eq(agentRoles.userId, user.id)).then((r) => r[0]),
  ]);

  const models = listModels().map((m) => ({
    key: m.key,
    providerLabel: m.providerLabel,
    requiresPro: m.requiresPro,
  }));

  return c.html(
    ChatPage({
      user: { id: user.id, name: user.name, email: user.email ?? "" },
      projectId,
      projectName: project.name,
      conversationId,
      modelKey: modelSel?.selectedModel ?? DEFAULT_MODEL_KEY,
      roleKey: roleRow?.name ?? "product_analyst",
      models,
    })
  );
}

chat.get("/chat/project/:projectId", (c) => handleChatPage(c));
chat.get("/chat/project/:projectId/conversation/:conversationId", (c) => {
  const { conversationId } = c.req.param();
  return handleChatPage(c, conversationId);
});

export default chat;
