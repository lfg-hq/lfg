import { and, desc, eq } from "drizzle-orm";
import { db } from "../config/db.ts";
import { instantApps } from "../db/schema/instant.ts";
import { messages } from "../db/schema/chat.ts";
import { sandboxes } from "../db/schema/sandbox.ts";
import { broadcastToUser } from "../ws/connection-manager.ts";
import { enableHttpAccess, execOnWorkspace, newWorkspace } from "./mags.ts";
import {
  extractExitCode,
  extractSessionId,
  hasAuthError,
  isStreamComplete,
  parseJsonlEvents,
  pollOutput,
  startClaudeCli,
  type ClaudeJsonEvent,
} from "./claude-cli.ts";

const PROJECT_DIR = "project";
const CLAUDE_PROJECT_DIR = "/home/claudeuser/project";
const BUILD_TIMEOUT_MS = 45 * 60 * 1000;
const POLL_INTERVAL_MS = 5_000;
const activeBuilds = new Set<string>();

export interface CreateInstantAppInput {
  userId: string;
  projectId?: string;
  conversationId: string;
  name: string;
  requirements: string;
  envVars?: Record<string, string>;
}

export interface InstantStatusResult {
  appId: string;
  appName: string;
  status: string;
  previewUrl: string;
  message: string;
}

function sleep(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

function sanitizeAppName(name: string): string {
  return (name || "instant-app")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64) || "instant-app";
}

async function appendSystemNotice(conversationId: string, content: Record<string, unknown>) {
  await db.insert(messages).values({
    conversationId,
    role: "system",
    content: JSON.stringify(content),
  });
}

async function broadcastInstantStatus(params: {
  userId: string;
  conversationId?: string | null;
  appId: string;
  status: string;
  message: string;
  previewUrl?: string;
  appName?: string;
}) {
  const { userId, conversationId, appId, status, message, previewUrl, appName } = params;

  const isRunning = status === "running";
  broadcastToUser(userId, {
    type: "ai_chunk",
    chunk: "",
    is_final: false,
    is_notification: true,
    notification_type: isRunning ? "instant_app_ready" : "instant_app_status",
    instant_app_id: appId,
    instant_app_status: status,
    message,
    preview_url: previewUrl ?? "",
    app_name: appName ?? "",
  });

  if (conversationId) {
    await appendSystemNotice(conversationId, {
      type: "instant_build_notice",
      instant_app_id: appId,
      status,
      message,
      preview_url: previewUrl ?? "",
      app_name: appName ?? "",
    });
  }
}

async function broadcastEnvVarRequest(params: {
  userId: string;
  conversationId: string;
  key: string;
  description: string;
  required: boolean;
  appId: string;
}) {
  const payload = {
    key: params.key,
    description: params.description,
    required: params.required,
    app_id: params.appId,
  };

  broadcastToUser(params.userId, {
    type: "ai_chunk",
    chunk: "",
    is_final: false,
    is_notification: true,
    notification_type: "env_var_request",
    data: payload,
  });

  await appendSystemNotice(params.conversationId, {
    type: "env_var_request",
    ...payload,
  });
}

function extractProgress(events: ClaudeJsonEvent[]): string | null {
  for (const event of events) {
    if (event.type !== "assistant") continue;
    const blocks = event.message?.content ?? [];
    for (const block of blocks) {
      if (block.type === "tool_use" && block.name) {
        const toolInput = block.input ?? {};
        if (typeof toolInput.file_path === "string") {
          return `${block.name}: ${toolInput.file_path}`;
        }
        if (typeof toolInput.command === "string") {
          return `${block.name}: ${toolInput.command.slice(0, 90)}`;
        }
        return `Running: ${block.name}`;
      }
      if (block.type === "text" && block.text?.trim()) {
        return `Agent: ${block.text.trim().slice(0, 160)}`;
      }
    }
  }
  return null;
}

async function ensureSandboxForApp(appId: string) {
  const [row] = await db
    .select({ app: instantApps, sandbox: sandboxes })
    .from(instantApps)
    .leftJoin(sandboxes, eq(instantApps.sandboxId, sandboxes.id))
    .where(eq(instantApps.id, appId))
    .limit(1);

  if (!row) return null;
  if (row.sandbox?.magsWorkspaceId) {
    return { app: row.app, sandbox: row.sandbox };
  }

  const workspaceName = `instant-${row.app.appId.slice(0, 8)}-${crypto.randomUUID().slice(0, 8)}`;
  const { jobId, workspaceId } = await newWorkspace(workspaceName);

  const [sandbox] = await db
    .insert(sandboxes)
    .values({
      projectId: row.app.projectId ?? null,
      userId: row.app.userId,
      magsWorkspaceId: workspaceId,
      magsJobId: jobId,
      workspaceType: "instant",
      status: "ready",
      previewPort: 8080,
      updatedAt: new Date(),
    })
    .returning();

  await db
    .update(instantApps)
    .set({ sandboxId: sandbox!.id, updatedAt: new Date() })
    .where(eq(instantApps.id, row.app.id));

  return { app: row.app, sandbox: sandbox! };
}

async function checkLocalServer(workspaceId: string): Promise<boolean> {
  try {
    const res = await execOnWorkspace(
      workspaceId,
      "curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/ 2>/dev/null || echo 000",
      { timeout: 15_000 }
    );
    const code = (res.output || "").trim().split(/\s+/).pop() || "000";
    return code !== "000";
  } catch {
    return false;
  }
}

async function runInstantBuild(appId: string, feedback?: string) {
  if (activeBuilds.has(appId)) return;
  activeBuilds.add(appId);

  try {
    const initial = await ensureSandboxForApp(appId);
    if (!initial) return;

    let app = initial.app;
    let sandbox = initial.sandbox;
    const workspaceId = sandbox.magsWorkspaceId!;
    const appName = app.name;

    await db
      .update(instantApps)
      .set({ status: "building", updatedAt: new Date() })
      .where(eq(instantApps.id, appId));

    await broadcastInstantStatus({
      userId: app.userId,
      conversationId: app.conversationId,
      appId: app.appId,
      appName,
      status: "building",
      message: `Provisioning sandbox for ${appName}...`,
    });

    const shouldContinue = !!feedback && !!sandbox.cliSessionId;
    const prompt = shouldContinue
      ? `The user wants changes to the running app.

## Feedback / New Requirements
${feedback}

## Instructions
1. Apply the requested changes to the existing project at ${CLAUDE_PROJECT_DIR}
2. Ensure the app is running on port 8080
3. If needed, restart: cd ${CLAUDE_PROJECT_DIR} && npm run build && npm start -p 8080 -H 0.0.0.0 > dev.log 2>&1 &`
      : `You are building a full-stack web application.

## App: ${appName}

## Requirements
${app.requirements ?? ""}

## ENVIRONMENT
- You are running inside a cloud sandbox (Mags VM). The preview proxy routes external traffic to port 8080.
- ALWAYS configure the server to listen on port 8080 and bind to 0.0.0.0.

## Instructions
1. Create a new Next.js project: npx create-next-app@latest ${PROJECT_DIR} --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --use-npm --yes
2. cd ${CLAUDE_PROJECT_DIR}
3. Install Drizzle + SQLite: npm install drizzle-orm better-sqlite3 && npm install -D drizzle-kit @types/better-sqlite3
4. Init shadcn/ui: npx shadcn@latest init -y -d
5. Implement all requirements above.
6. Build/start production server: cd ${CLAUDE_PROJECT_DIR} && npm run build && npm start -p 8080 -H 0.0.0.0 > dev.log 2>&1 &

IMPORTANT: The app must be accessible on port 8080 and logs must go to dev.log.`;

    await broadcastInstantStatus({
      userId: app.userId,
      conversationId: app.conversationId,
      appId: app.appId,
      appName,
      status: "building",
      message: shouldContinue
        ? `Applying your changes to ${appName}...`
        : `Claude Code is building ${appName}...`,
    });

    const cli = await startClaudeCli({
      workspaceId,
      prompt,
      projectDir: PROJECT_DIR,
      sessionId: shouldContinue ? sandbox.cliSessionId ?? undefined : undefined,
      maxTurns: 120,
      userId: app.userId,
      envVars: (app.envVars as Record<string, string> | null) ?? {},
    });

    let offset = 0;
    let allOutput = "";
    let sessionId = sandbox.cliSessionId ?? undefined;
    let completed = false;
    let lastProgressAt = 0;
    const deadline = Date.now() + BUILD_TIMEOUT_MS;

    while (Date.now() < deadline && !completed) {
      await sleep(POLL_INTERVAL_MS);
      const poll = await pollOutput(workspaceId, cli.outputFile, offset, cli.backgroundPid);
      offset = poll.newOffset;
      if (!poll.data) {
        if (!poll.alive && allOutput.includes("___CLAUDE_EXIT_CODE")) {
          break;
        }
        continue;
      }

      allOutput += poll.data;
      const events = parseJsonlEvents(poll.data);

      if (!sessionId) {
        const extracted = extractSessionId(events);
        if (extracted) {
          sessionId = extracted;
          await db
            .update(sandboxes)
            .set({ cliSessionId: extracted, updatedAt: new Date() })
            .where(eq(sandboxes.id, sandbox.id));
        }
      }

      if (Date.now() - lastProgressAt > 5_000) {
        const progress = extractProgress(events);
        if (progress) {
          lastProgressAt = Date.now();
          await broadcastInstantStatus({
            userId: app.userId,
            conversationId: app.conversationId,
            appId: app.appId,
            appName,
            status: "building",
            message: progress,
          });
        }
      }

      if (isStreamComplete(events)) {
        completed = true;
      }
    }

    const exitCode = extractExitCode(allOutput);
    if (hasAuthError(allOutput)) {
      throw new Error("Claude Code authentication failed. Reconnect in Settings.");
    }
    if (exitCode !== null && exitCode !== 0) {
      throw new Error(`Claude CLI failed with exit code ${exitCode}`);
    }

    let previewUrl = app.previewUrl ?? sandbox.previewUrl ?? "";
    if (!previewUrl) {
      previewUrl = await enableHttpAccess(workspaceId, 8080);
    }

    const isLive = await checkLocalServer(workspaceId);
    if (!isLive) {
      throw new Error("Build finished but server is not responding on port 8080.");
    }

    await db
      .update(instantApps)
      .set({
        status: "running",
        previewUrl,
        updatedAt: new Date(),
      })
      .where(eq(instantApps.id, appId));

    await db
      .update(sandboxes)
      .set({
        status: "ready",
        previewUrl,
        previewPort: 8080,
        updatedAt: new Date(),
      })
      .where(eq(sandboxes.id, sandbox.id));

    await broadcastInstantStatus({
      userId: app.userId,
      conversationId: app.conversationId,
      appId: app.appId,
      appName,
      status: "running",
      message: `${appName} is live!`,
      previewUrl,
    });
  } catch (error) {
    const [app] = await db.select().from(instantApps).where(eq(instantApps.id, appId)).limit(1);
    if (app) {
      await db
        .update(instantApps)
        .set({
          status: "error",
          metadata: {
            ...((app.metadata as Record<string, unknown> | null) ?? {}),
            error: String(error),
          },
          updatedAt: new Date(),
        })
        .where(eq(instantApps.id, app.id));

      await broadcastInstantStatus({
        userId: app.userId,
        conversationId: app.conversationId,
        appId: app.appId,
        appName: app.name,
        status: "error",
        message: `Error building ${app.name}: ${String(error)}`,
      });
    }
  } finally {
    activeBuilds.delete(appId);
  }
}

export async function createOrContinueInstantApp(input: CreateInstantAppInput) {
  const normalizedName = sanitizeAppName(input.name);
  const [existing] = await db
    .select()
    .from(instantApps)
    .where(
      and(
        eq(instantApps.userId, input.userId),
        eq(instantApps.conversationId, input.conversationId)
      )
    )
    .orderBy(desc(instantApps.createdAt))
    .limit(1);

  if (existing) {
    await db
      .update(instantApps)
      .set({
        name: normalizedName,
        description: input.requirements.slice(0, 500),
        requirements: input.requirements,
        envVars: input.envVars ?? ((existing.envVars as Record<string, string>) ?? {}),
        status: "building",
        updatedAt: new Date(),
      })
      .where(eq(instantApps.id, existing.id));

    void runInstantBuild(existing.id, input.requirements);

    return {
      appId: existing.appId,
      appName: normalizedName,
      status: "building",
      continued: true,
    };
  }

  const [app] = await db
    .insert(instantApps)
    .values({
      name: normalizedName,
      description: input.requirements.slice(0, 500),
      requirements: input.requirements,
      envVars: input.envVars ?? {},
      status: "building",
      projectId: input.projectId ?? null,
      userId: input.userId,
      conversationId: input.conversationId,
    })
    .returning();

  if (app) {
    void runInstantBuild(app.id);
  }

  return {
    appId: app!.appId,
    appName: app!.name,
    status: "building",
    continued: false,
  };
}

export async function getInstantAppStatus(params: {
  userId: string;
  conversationId: string;
  restartServer?: boolean;
}): Promise<InstantStatusResult | null> {
  const [row] = await db
    .select({ app: instantApps, sandbox: sandboxes })
    .from(instantApps)
    .leftJoin(sandboxes, eq(instantApps.sandboxId, sandboxes.id))
    .where(
      and(
        eq(instantApps.userId, params.userId),
        eq(instantApps.conversationId, params.conversationId)
      )
    )
    .orderBy(desc(instantApps.createdAt))
    .limit(1);

  if (!row) return null;

  const app = row.app;
  const sandbox = row.sandbox;
  let status = app.status;
  let previewUrl = app.previewUrl ?? "";

  if (!sandbox?.magsWorkspaceId) {
    return {
      appId: app.appId,
      appName: app.name,
      status,
      previewUrl: "",
      message: `${app.name} status: ${status}`,
    };
  }

  if (params.restartServer) {
    const rebuildCmd =
      "cd /home/claudeuser/project && (pkill -f 'next start' 2>/dev/null || true) && npm run build && nohup npm start -p 8080 -H 0.0.0.0 > dev.log 2>&1 &";
    await execOnWorkspace(sandbox.magsWorkspaceId, rebuildCmd, { timeout: 180_000 });
    await sleep(3_000);
  }

  if (!previewUrl || params.restartServer) {
    previewUrl = await enableHttpAccess(sandbox.magsWorkspaceId, 8080);
  }

  const live = await checkLocalServer(sandbox.magsWorkspaceId);
  if (live) status = "running";

  await db
    .update(instantApps)
    .set({
      status,
      previewUrl: live ? previewUrl : app.previewUrl,
      updatedAt: new Date(),
    })
    .where(eq(instantApps.id, app.id));

  if (live) {
    await db
      .update(sandboxes)
      .set({
        previewUrl,
        previewPort: 8080,
        status: "ready",
        updatedAt: new Date(),
      })
      .where(eq(sandboxes.id, sandbox.id));
  }

  await broadcastInstantStatus({
    userId: params.userId,
    conversationId: app.conversationId,
    appId: app.appId,
    appName: app.name,
    status,
    message: live ? `${app.name} is live!` : `${app.name} status: ${status}`,
    previewUrl: live ? previewUrl : "",
  });

  return {
    appId: app.appId,
    appName: app.name,
    status,
    previewUrl: live ? previewUrl : "",
    message: live ? `${app.name} is live!` : `${app.name} status: ${status}`,
  };
}

export async function requestInstantEnvVariable(params: {
  userId: string;
  conversationId: string;
  key: string;
  description: string;
  required?: boolean;
}) {
  const [app] = await db
    .select()
    .from(instantApps)
    .where(
      and(
        eq(instantApps.userId, params.userId),
        eq(instantApps.conversationId, params.conversationId)
      )
    )
    .orderBy(desc(instantApps.createdAt))
    .limit(1);

  if (!app) return { sent: false, reason: "No instant app for this conversation." };

  await broadcastEnvVarRequest({
    userId: params.userId,
    conversationId: params.conversationId,
    key: params.key,
    description: params.description,
    required: params.required !== false,
    appId: app.appId,
  });
  return { sent: true, appId: app.appId };
}

export async function getInstantAppForConversation(userId: string, conversationId: string) {
  const [app] = await db
    .select()
    .from(instantApps)
    .where(and(eq(instantApps.userId, userId), eq(instantApps.conversationId, conversationId)))
    .orderBy(desc(instantApps.createdAt))
    .limit(1);
  return app ?? null;
}

export async function askInstantSandboxQuestion(params: {
  userId: string;
  conversationId: string;
  question: string;
}) {
  const [row] = await db
    .select({ app: instantApps, sandbox: sandboxes })
    .from(instantApps)
    .leftJoin(sandboxes, eq(instantApps.sandboxId, sandboxes.id))
    .where(
      and(
        eq(instantApps.userId, params.userId),
        eq(instantApps.conversationId, params.conversationId)
      )
    )
    .orderBy(desc(instantApps.createdAt))
    .limit(1);

  if (!row?.sandbox?.magsWorkspaceId) {
    return { answer: "No sandbox is available yet for this app." };
  }

  // Lightweight sandbox introspection fallback.
  const cmd = `cd /home/claudeuser/project && (ls -la && echo "\\nQuestion: ${params.question.replace(/"/g, '\\"')}" )`;
  const result = await execOnWorkspace(row.sandbox.magsWorkspaceId, cmd, { timeout: 30_000 });
  return { answer: result.output.slice(0, 4000) };
}
