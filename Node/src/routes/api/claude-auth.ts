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
    const t0 = Date.now();
    const log = (msg: string) => console.log(`[claude-auth/start +${Date.now() - t0}ms] ${msg}`);

    // Stop any old auth workspace and always create a fresh one
    let sandbox = await getAuthSandbox(user.id);
    if (sandbox?.magsWorkspaceId) {
      log(`stopping old workspace ${sandbox.magsWorkspaceId}...`);
      stopWorkspace(sandbox.magsWorkspaceId).catch(() => {});
    }

    const wsName = generateAuthWorkspaceName();
    log(`creating fresh workspace: ${wsName}...`);
    const { jobId } = await newWorkspace(wsName);
    log(`workspace created: jobId=${jobId}`);

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

    // Try existing credentials (fast path — if user already connected before)
    const profile = await getOrCreateProfile(user.id);
    if (profile.claudeCodeCredentials) {
      log("found existing credentials in DB, injecting to VM...");
      await loadCredentialsFromDB(user.id, wsName);
      log("credentials injected, testing claude -p...");

      const testResult = await execOnWorkspace(wsName,
        `export HOME=/root; export PATH=/root/node/current/bin:/root/.npm-global/bin:$PATH; claude -p "return hello" --max-turns 1 2>&1 | head -20`,
        { timeout: 10_000 }
      ).catch((e) => {
        log(`claude -p threw: ${e}`);
        return { output: "", exitCode: -1, stderr: String(e) };
      });

      const testOut = testResult.output.toLowerCase();
      log(`CLI test: exit=${testResult.exitCode}, output="${testResult.output.slice(0, 200)}"`);

      if (testResult.exitCode === 0 && testOut.includes("hello") && !testOut.includes("error") && !testOut.includes("expired") && !testOut.includes("401")) {
        await saveCredentialsToDB(wsName, user.id);
        log("CLI works! returning already_authenticated");
        return c.json({ status: "already_authenticated", message: "Claude Code is already authenticated" });
      }

      // CLI doesn't work — wipe cred files (keep .claude dir for trust/settings)
      log("CLI test failed, wiping credential files for fresh OAuth");
      await execOnWorkspace(wsName,
        "rm -f /root/.claude/.credentials.json /home/claudeuser/.claude/.credentials.json 2>/dev/null; echo CLEARED",
        { timeout: 8_000 }
      ).catch(() => {});
    } else {
      log("no credentials in DB, going straight to OAuth");
    }

    // Start OAuth flow — credentials are wiped, Claude will show login prompt
    log("starting OAuth flow via startClaudeAuth...");
    const result = await startClaudeAuth(wsName, { skipCredCheck: true });
    log(`OAuth result: status=${result.status}, error=${result.error ?? "none"}`);

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
