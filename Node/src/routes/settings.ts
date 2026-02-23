import { Hono } from "hono";
import { requireAuth } from "../auth/middleware.ts";
import { db } from "../config/db.ts";
import { llmApiKeys } from "../db/schema/users.ts";
import { eq } from "drizzle-orm";
import { SettingsPage } from "../templates/pages/settings.tsx";
import type { auth } from "../auth/index.ts";

type AuthEnv = {
  Variables: {
    user: typeof auth.$Infer.Session.user;
    session: typeof auth.$Infer.Session.session;
  };
};

const settingsRouter = new Hono<AuthEnv>();
settingsRouter.use("*", requireAuth);

async function getOrCreateApiKeys(userId: string) {
  let [row] = await db.select().from(llmApiKeys).where(eq(llmApiKeys.userId, userId));
  if (!row) {
    [row] = await db.insert(llmApiKeys).values({ userId }).returning();
  }
  return row!;
}

// GET /settings
settingsRouter.get("/settings", async (c) => {
  const user = c.get("user");
  const keys = await getOrCreateApiKeys(user.id);
  return c.html(
    SettingsPage({
      user: { id: user.id, name: user.name, email: user.email },
      apiKeys: {
        openai: !!keys.openaiApiKey,
        anthropic: !!keys.anthropicApiKey,
        google: !!keys.googleApiKey,
        xai: !!keys.xaiApiKey,
        usePersonalKeys: keys.usePersonalLlmKeys,
      },
    })
  );
});

// POST /settings/save-key
settingsRouter.post("/settings/save-key", async (c) => {
  const user = c.get("user");
  const body = await c.req.parseBody();
  const provider = body["provider"] as string;
  const key = (body["key"] as string | undefined)?.trim();

  if (!key) return c.redirect("/settings?error=Key+cannot+be+empty");

  const fieldMap: Record<string, string> = {
    openai: "openaiApiKey",
    anthropic: "anthropicApiKey",
    google: "googleApiKey",
    xai: "xaiApiKey",
  };
  const field = fieldMap[provider];
  if (!field) return c.redirect("/settings?error=Unknown+provider");

  await db
    .insert(llmApiKeys)
    .values({ userId: user.id, [field]: key })
    .onConflictDoUpdate({
      target: llmApiKeys.userId,
      set: { [field]: key },
    });

  return c.redirect("/settings?success=Key+saved");
});

// POST /settings/remove-key
settingsRouter.post("/settings/remove-key", async (c) => {
  const user = c.get("user");
  const body = await c.req.parseBody();
  const provider = body["provider"] as string;

  const fieldMap: Record<string, Record<string, null>> = {
    openai: { openaiApiKey: null },
    anthropic: { anthropicApiKey: null },
    google: { googleApiKey: null },
    xai: { xaiApiKey: null },
  };
  const updateFields = fieldMap[provider];
  if (!updateFields) return c.redirect("/settings?error=Unknown+provider");

  await db.update(llmApiKeys).set(updateFields as any).where(eq(llmApiKeys.userId, user.id));
  return c.redirect("/settings?success=Key+removed");
});

// POST /settings/toggle-byok
settingsRouter.post("/settings/toggle-byok", async (c) => {
  const user = c.get("user");
  const body = await c.req.parseBody();
  const enabled = body["enabled"] === "on";

  await db
    .insert(llmApiKeys)
    .values({ userId: user.id, usePersonalLlmKeys: enabled })
    .onConflictDoUpdate({
      target: llmApiKeys.userId,
      set: { usePersonalLlmKeys: enabled },
    });

  return c.redirect("/settings");
});

export default settingsRouter;
