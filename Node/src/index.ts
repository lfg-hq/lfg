import { Hono } from "hono";
import { logger } from "hono/logger";
import { trimTrailingSlash } from "hono/trailing-slash";
import { serveStatic } from "hono/bun";
import { env } from "./config/env.ts";
import landing from "./routes/landing.ts";
import authRoutes from "./routes/auth.ts";
import chatRoutes from "./routes/chat.ts";
import projectsRoutes from "./routes/projects.ts";
import settingsRoutes from "./routes/settings.ts";
import filesApi from "./routes/api/files.ts";
import settingsApi from "./routes/api/settings.ts";
import ticketsApi from "./routes/api/tickets.ts";
import conversationsApi from "./routes/api/conversations.ts";
import { cliRouter } from "./routes/api/cli.ts";
import claudeAuthApi from "./routes/api/claude-auth.ts";
import { auth } from "./auth/index.ts";
import { startTicketWorker } from "./workers/ticket-executor.ts";
import { db } from "./config/db.ts";
import { agentRoles, modelSelections } from "./db/schema/chat.ts";
import { eq } from "drizzle-orm";
import { onOpen, onClose, onMessage } from "./ws/chat-handler.ts";
import type { WsData } from "./ws/types.ts";

const app = new Hono();

// ── Trim trailing slashes (Django-compat: chat.js calls /api/foo/:id/) ──
app.use(trimTrailingSlash());

// ── Request logging ──────────────────────────────────────────────────
app.use("*", logger());

// ── Static files ────────────────────────────────────────────────────
app.use("/public/*", serveStatic({ root: "./" }));
app.use("/uploads/*", serveStatic({ root: "./" }));

// ── Health check ────────────────────────────────────────────────────
app.get("/health", (c) => c.json({ status: "ok" }));

// ── Routes ──────────────────────────────────────────────────────────
app.route("/", authRoutes);
app.route("/", landing);
app.route("/", chatRoutes);
app.route("/", projectsRoutes);
app.route("/", settingsRoutes);
app.route("/api/files", filesApi);
app.route("/api/settings", settingsApi);
app.route("/api/projects", ticketsApi);
app.route("/api/conversations", conversationsApi);
app.route("/api/v1/cli", cliRouter);
app.route("/api/v1/claude-auth", claudeAuthApi);

// ── Django-compat stubs ──────────────────────────────────────────────
// chat.js calls /accounts/agent-settings/ for turbo mode + role state
app.get("/accounts/agent-settings/", async (c) => {
  const session = await auth.api.getSession({ headers: c.req.raw.headers });
  if (!session?.user) return c.json({ success: false }, 401);

  const [roleRow, modelRow] = await Promise.all([
    db.select().from(agentRoles).where(eq(agentRoles.userId, session.user.id)).then((r) => r[0]),
    db.select().from(modelSelections).where(eq(modelSelections.userId, session.user.id)).then((r) => r[0]),
  ]);

  return c.json({
    success: true,
    turbo_mode: roleRow?.turboMode ?? false,
    agent_role: roleRow?.name ?? "product_analyst",
    model_key: modelRow?.selectedModel ?? "claude_4.5_sonnet",
  });
});

// ── WebSocket upgrade handler ────────────────────────────────────────
// Bun.serve handles WS upgrades outside Hono. We intercept /ws/chat here
// by using a custom fetch that tries the WS upgrade first.
async function handleFetch(req: Request, server: import("bun").Server<WsData>): Promise<Response> {
  const url = new URL(req.url);

  // Better Auth — handle before Hono to avoid sub-router middleware conflicts
  if (url.pathname.startsWith("/api/auth/")) {
    console.log(`[auth] ${req.method} ${url.pathname}`);
    return auth.handler(req);
  }

  if (url.pathname === "/ws/chat" || url.pathname === "/ws/chat/") {
    const session = await auth.api.getSession({ headers: req.headers });
    if (!session?.user) {
      return new Response("Unauthorized", { status: 401 });
    }

    const sessionId = session.session.id;
    const userId = session.user.id;

    const upgraded = server.upgrade(req, {
      data: { sessionId, userId },
    });

    if (upgraded) return undefined as unknown as Response;
    return new Response("WebSocket upgrade failed", { status: 500 });
  }

  return app.fetch(req);
}

// ── Start background workers ─────────────────────────────────────────
startTicketWorker();

// ── Start server ────────────────────────────────────────────────────
console.log(`Starting LFG on port ${env.PORT} (${env.NODE_ENV})`);

export default {
  port: env.PORT,

  // Long-running endpoints (Mags VM provisioning, Claude CLI install) can take
  // 60-300s. Disable Bun's default 10s idle timeout.
  idleTimeout: 0,

  fetch: handleFetch,

  websocket: {
    open: onOpen,
    close: onClose,
    message: onMessage,
  },
};
