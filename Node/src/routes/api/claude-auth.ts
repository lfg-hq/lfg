/**
 * Claude Code CLI Connect API
 *
 * POST /api/v1/claude-auth/start          — create sandbox + start OAuth flow
 * POST /api/v1/claude-auth/submit-code    — submit OAuth code
 * GET  /api/v1/claude-auth/status         — check auth status from profile
 * POST /api/v1/claude-auth/disconnect     — wipe credentials
 */

import { Hono } from "hono";
import { requireAuth } from "../../auth/middleware.ts";
import { db } from "../../config/db.ts";
import { profiles } from "../../db/schema/users.ts";
import { sandboxes } from "../../db/schema/sandbox.ts";
import { eq, and } from "drizzle-orm";
import type { auth } from "../../auth/index.ts";
import {
  startClaudeAuth,
  submitAuthCode,
  checkAuthStatus,
  saveCredentialsToDB,
  loadCredentialsFromDB,
  generateAuthWorkspaceName,
} from "../../services/claude-auth.ts";
import { newWorkspace, execOnWorkspace, stopWorkspace } from "../../services/mags.ts";

type AuthEnv = {
  Variables: {
    user: typeof auth.$Infer.Session.user;
    session: typeof auth.$Infer.Session.session;
  };
};

const claudeAuthApi = new Hono<AuthEnv>();
claudeAuthApi.use("*", requireAuth);

// ── Helpers ───────────────────────────────────────────────────────────────

async function getAuthSandbox(userId: string) {
  const [row] = await db.select().from(sandboxes)
    .where(and(eq(sandboxes.userId, userId), eq(sandboxes.workspaceType, "claude_auth")))
    .orderBy(sandboxes.updatedAt)
    .limit(1);
  return row ?? null;
}

async function getOrCreateProfile(userId: string) {
  let [row] = await db.select().from(profiles).where(eq(profiles.userId, userId));
  if (!row) {
    [row] = await db.insert(profiles).values({ userId }).returning();
  }
  return row!;
}

// ── POST /start ───────────────────────────────────────────────────────────

claudeAuthApi.post("/start", async (c) => {
  const user = c.get("user");

  try {
    let sandbox = await getAuthSandbox(user.id);
    let wsName = "";

    // Try to reuse existing workspace
    if (sandbox?.magsWorkspaceId) {
      try {
        const test = await execOnWorkspace(sandbox.magsWorkspaceId, "echo WORKSPACE_OK", { timeout: 20_000 });
        if (test.exitCode === 0 && test.output.includes("WORKSPACE_OK")) {
          wsName = sandbox.magsWorkspaceId;
          await db.update(sandboxes).set({ status: "ready", updatedAt: new Date() })
            .where(eq(sandboxes.id, sandbox.id));
        } else {
          await db.update(sandboxes).set({ status: "error", updatedAt: new Date() })
            .where(eq(sandboxes.id, sandbox.id));
        }
      } catch {
        await db.update(sandboxes).set({ status: "error", updatedAt: new Date() })
          .where(eq(sandboxes.id, sandbox.id));
      }
    }

    // Create fresh workspace if we don't have a working one
    if (!wsName) {
      wsName = generateAuthWorkspaceName();
      const { jobId } = await newWorkspace(wsName);

      // Base workspace already has Claude CLI, Node, and expect pre-installed — no setup needed.
      if (sandbox) {
        await db.update(sandboxes)
          .set({ magsWorkspaceId: wsName, magsJobId: jobId, status: "ready", updatedAt: new Date() })
          .where(eq(sandboxes.id, sandbox.id));
      } else {
        const rows = await db.insert(sandboxes).values({
          userId: user.id,
          workspaceType: "claude_auth",
          magsWorkspaceId: wsName,
          magsJobId: jobId,
          status: "ready",
        }).returning();
        sandbox = rows[0] ?? null;
      }
    }

    // Clean up any stale processes
    await execOnWorkspace(wsName,
      "pkill -9 claude 2>/dev/null; pkill -9 expect 2>/dev/null; rm -f /tmp/claude_*.txt /tmp/claude_*.log 2>/dev/null; echo CLEANUP_DONE",
      { timeout: 15_000 }
    ).catch(() => {});

    // Try loading existing credentials from DB first (fast path)
    const profile = await getOrCreateProfile(user.id);
    if (profile.claudeCodeCredentials) {
      const loaded = await loadCredentialsFromDB(user.id, wsName);
      if (loaded) {
        const status = await checkAuthStatus(wsName);
        if (status.authenticated) {
          // Re-save credentials from VM — the CLI may have refreshed the access token
          await saveCredentialsToDB(wsName, user.id);
          return c.json({ status: "already_authenticated", message: "Claude Code is already authenticated" });
        }
      }
    }

    // Start the OAuth flow
    const result = await startClaudeAuth(wsName);
    console.log("[claude-auth/start] result:", result.status, result.error ?? "");

    if (result.status === "already_authenticated") {
      await saveCredentialsToDB(wsName, user.id);
    }

    return c.json(result);
  } catch (err) {
    console.error("[claude-auth/start]", err);
    return c.json({ status: "error", error: String(err) }, 500);
  }
});

// ── POST /submit-code ─────────────────────────────────────────────────────

claudeAuthApi.post("/submit-code", async (c) => {
  const user = c.get("user");

  try {
    const { code } = await c.req.json<{ code: string }>();
    if (!code?.trim()) return c.json({ status: "error", error: "Code is required" }, 400);

    const sandbox = await getAuthSandbox(user.id);
    if (!sandbox?.magsWorkspaceId) {
      return c.json({ status: "error", error: "No active auth session. Please start again." }, 400);
    }

    const wsName = sandbox.magsWorkspaceId;
    const result = await submitAuthCode(wsName, code.trim());

    if (result.status === "success") {
      // The expect script confirmed SUCCESS — trust it, save credentials directly.
      // Skipping checkAuthStatus (runs `claude -p "Hello"`) to avoid 30-60s delay.
      await saveCredentialsToDB(wsName, user.id);

      // Clear stale CLI sessions so next ticket run picks up fresh credentials
      await db.update(sandboxes)
        .set({ cliSessionId: null, updatedAt: new Date() })
        .where(and(eq(sandboxes.userId, user.id)));

      return c.json({ status: "success", message: "Claude Code authenticated successfully" });
    }

    return c.json(result);
  } catch (err) {
    console.error("[claude-auth/submit-code]", err);
    return c.json({ status: "error", error: String(err) }, 500);
  }
});

// ── GET /status ───────────────────────────────────────────────────────────

claudeAuthApi.get("/status", async (c) => {
  const user = c.get("user");
  const profile = await getOrCreateProfile(user.id);
  return c.json({
    authenticated: profile.claudeCodeAuthenticated ?? false,
    hasCredentials: !!profile.claudeCodeCredentials,
    cliApiKey: profile.cliApiKey ?? null,
  });
});

// ── POST /disconnect ──────────────────────────────────────────────────────

claudeAuthApi.post("/disconnect", async (c) => {
  const user = c.get("user");

  // Stop the auth sandbox VM if it exists
  const sandbox = await getAuthSandbox(user.id);
  if (sandbox?.magsWorkspaceId) {
    stopWorkspace(sandbox.magsWorkspaceId).catch(() => {});
    await db.delete(sandboxes).where(eq(sandboxes.id, sandbox.id));
  }

  await db.update(profiles)
    .set({
      claudeCodeAuthenticated: false,
      claudeCodeCredentials: null,
      claudeCodeCredentialsUpdatedAt: null,
      cliApiKey: null,
      updatedAt: new Date(),
    })
    .where(eq(profiles.userId, user.id));

  return c.json({ ok: true });
});

export default claudeAuthApi;
