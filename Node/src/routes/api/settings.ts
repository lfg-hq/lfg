import { Hono } from "hono";
import { requireAuth } from "../../auth/middleware.ts";
import { db } from "../../config/db.ts";
import { modelSelections, agentRoles } from "../../db/schema/chat.ts";
import { eq } from "drizzle-orm";
import { listModels } from "../../ai/provider.ts";
import type { auth } from "../../auth/index.ts";

type AuthEnv = {
  Variables: {
    user: typeof auth.$Infer.Session.user;
    session: typeof auth.$Infer.Session.session;
  };
};

const settings = new Hono<AuthEnv>();
settings.use("*", requireAuth);

// POST /api/settings/model  — { modelKey: string }
settings.post("/model", async (c) => {
  const user = c.get("user");
  const { modelKey } = await c.req.json<{ modelKey: string }>();

  if (!modelKey) return c.json({ error: "modelKey required" }, 400);

  // Validate against known models
  const known = listModels().find((m) => m.key === modelKey);
  if (!known) return c.json({ error: "Unknown model key" }, 400);

  await db
    .insert(modelSelections)
    .values({ userId: user.id, selectedModel: modelKey })
    .onConflictDoUpdate({
      target: modelSelections.userId,
      set: { selectedModel: modelKey, updatedAt: new Date() },
    });

  return c.json({ success: true, modelKey });
});

// POST /api/settings/role  — { role: string }
settings.post("/role", async (c) => {
  const user = c.get("user");
  const { role } = await c.req.json<{ role: string }>();

  const validRoles = ["product_analyst", "developer", "designer", "default"];
  if (!validRoles.includes(role)) {
    return c.json({ error: "Invalid role" }, 400);
  }

  await db
    .insert(agentRoles)
    .values({ userId: user.id, name: role })
    .onConflictDoUpdate({
      target: agentRoles.userId,
      set: { name: role, updatedAt: new Date() },
    });

  return c.json({ success: true, role });
});

// GET /api/settings/models — list available models
settings.get("/models", (c) => {
  return c.json({ models: listModels() });
});

// GET /api/settings/me — current user model + role selection
settings.get("/me", async (c) => {
  const user = c.get("user");

  const [modelSel, roleRow] = await Promise.all([
    db.select().from(modelSelections).where(eq(modelSelections.userId, user.id)).then((r) => r[0]),
    db.select().from(agentRoles).where(eq(agentRoles.userId, user.id)).then((r) => r[0]),
  ]);

  return c.json({
    modelKey: modelSel?.selectedModel ?? "claude_4.5_sonnet",
    role: roleRow?.name ?? "product_analyst",
    turboMode: roleRow?.turboMode ?? false,
  });
});

export default settings;
