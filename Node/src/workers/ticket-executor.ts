/**
 * Ticket Executor Worker
 *
 * Subscribes to `ticket.queued` events and runs the full execution flow
 * (matching Django's execute_ticket_with_claude_cli):
 *
 * Step 1: Load ticket + project + user data
 * Step 2: Find or create Mags sandbox (probe existing, fallback to fresh)
 * Step 3: Setup git repo, checkout feature branch
 * Step 4: Verify Claude auth (credentials from DB)
 * Step 5: Build prompt with project context + LFG API integration
 * Step 6: Start Claude CLI via runner script (nohup, claudeuser)
 * Step 7: Poll JSONL output, forward logs via WS in real-time
 * Step 8: On completion: commit, push, update ticket status
 *
 * Also handles ticket.chat_message events for session-resume chat.
 */

import { db } from "../config/db.ts";
import { projectTickets, projectTodoLists, ticketLogs } from "../db/schema/tickets.ts";
import { projects } from "../db/schema/projects.ts";
import { profiles, githubTokens } from "../db/schema/users.ts";
import { sandboxes } from "../db/schema/sandbox.ts";
import { bus, emit } from "../events/bus.ts";
import {
  newWorkspace,
  execOnWorkspace,
} from "../services/mags.ts";
import {
  startClaudeCli,
  pollOutput,
  parseJsonlEvents,
  extractSessionId,
  isStreamComplete,
  isStaleSession,
  extractExitCode,
  hasAuthError,
  type PollResult,
} from "../services/claude-cli.ts";
import {
  commitAndPush,
} from "../services/git.ts";
import {
  buildBuilderPrompt,
  buildTicketChatPrompt,
} from "../ai/prompts/builder.ts";
import { broadcastToUser } from "../ws/connection-manager.ts";
import { eq, and } from "drizzle-orm";

const CALLBACK_BASE_URL = process.env.APP_URL ?? "http://localhost:3000";
const POLL_INTERVAL_MS = 5_000;
const MAX_POLL_DURATION_MS = 45 * 60 * 1000; // 45 minutes
const MAX_SSH_FAILURES = 5;
const WORKING_DIR = "/root";
const CLAUDE_HOME = "/home/claudeuser";

// ── Subscriber Setup ──────────────────────────────────────────────────

export function startTicketWorker() {
  bus.on("ticket.queued", async (event) => {
    const { ticketId } = event.payload;
    try {
      await executeTicket(ticketId);
    } catch (err) {
      console.error(`[ticket-executor] Failed for ticket ${ticketId}:`, err);
      await markTicketFailed(ticketId, String(err));
    }
  });

  bus.on("ticket.chat_message", async (event) => {
    const { ticketId, message, sender } = event.payload;
    try {
      await executeTicketChat(ticketId, message, sender);
    } catch (err) {
      console.error(`[ticket-executor] Chat failed for ticket ${ticketId}:`, err);
    }
  });

  console.log("[ticket-executor] Worker started");
}

// ── Main Executor ─────────────────────────────────────────────────────

async function executeTicket(ticketId: string): Promise<void> {
  const startTime = Date.now();

  // ── Step 1: Load data ───────────────────────────────────────────────
  console.log(`[ticket-executor] Step 1: Loading data for ticket ${ticketId}`);
  const [ticket] = await db
    .select()
    .from(projectTickets)
    .where(eq(projectTickets.id, ticketId))
    .limit(1);

  if (!ticket) throw new Error(`Ticket ${ticketId} not found`);

  const [project] = await db
    .select()
    .from(projects)
    .where(eq(projects.id, ticket.projectId))
    .limit(1);

  if (!project) throw new Error(`Project ${ticket.projectId} not found`);

  const ownerId = project.ownerId;

  const [profile] = await db
    .select()
    .from(profiles)
    .where(eq(profiles.userId, ownerId))
    .limit(1);

  const [ghToken] = await db
    .select()
    .from(githubTokens)
    .where(eq(githubTokens.userId, ownerId))
    .limit(1);

  const githubToken = ghToken?.accessToken;
  const cliApiKey = profile?.cliApiKey ?? "";

  // Warn if no GitHub — code will be lost on VM restart
  if (!githubToken) {
    console.warn(`[ticket-executor] ⚠️ No GitHub token for user ${ownerId} — code won't be persisted!`);
    await addLog(ticketId, "⚠️ GitHub not connected — code will NOT be saved to a repository. Connect GitHub in Settings to persist your work.", "command", ownerId);
  }

  // Load tasks
  const tasks = await db
    .select()
    .from(projectTodoLists)
    .where(eq(projectTodoLists.ticketId, ticketId));

  // Mark ticket as executing
  await db
    .update(projectTickets)
    .set({ status: "in_progress", queueStatus: "executing", updatedAt: new Date() })
    .where(eq(projectTickets.id, ticketId));

  // Project dir name (relative, e.g. "project")
  const projectDirName = "project"; // Default, matching Django stack_config

  // Feature branch name matching Django
  const featureBranch = `feature/ticket-${ticketId}`;

  // ── Step 2: Find or create sandbox ─────────────────────────────────
  console.log(`[ticket-executor] Step 2: Setting up workspace`);
  let sandboxRow = await findExistingSandbox(ticketId);
  let isReuse = !!sandboxRow;
  let workspaceId = sandboxRow?.magsWorkspaceId ?? null;

  if (isReuse && workspaceId) {
    // Probe existing workspace
    await addLog(ticketId, "Reconnecting to existing sandbox...", "command", ownerId);
    console.log(`[ticket-executor] Probing existing workspace: ${workspaceId}`);
    try {
      const probe = await execOnWorkspace(workspaceId, 'echo "WORKSPACE_READY"', { timeout: 60_000 });
      if (!probe.output.includes("WORKSPACE_READY")) {
        console.log(`[ticket-executor] Probe failed, creating fresh workspace`);
        isReuse = false;
        workspaceId = null;
        // Delete stale sandbox record
        if (sandboxRow) {
          await db.delete(sandboxes).where(eq(sandboxes.id, sandboxRow.id));
        }
        sandboxRow = null;
      }
    } catch {
      console.log(`[ticket-executor] Probe threw, creating fresh workspace`);
      isReuse = false;
      workspaceId = null;
      if (sandboxRow) {
        await db.delete(sandboxes).where(eq(sandboxes.id, sandboxRow.id));
      }
      sandboxRow = null;
    }
  }

  if (!workspaceId) {
    const workspaceName = `${ticketId.slice(0, 8)}-${crypto.randomUUID().slice(0, 8)}`;
    await addLog(ticketId, "Creating VM workspace...", "command", ownerId);
    console.log(`[ticket-executor] Creating new workspace: ${workspaceName}`);

    const { jobId, workspaceId: wsId } = await newWorkspace(workspaceName);
    workspaceId = wsId;

    // Wait for VM to boot
    await sleep(8_000);

    const created = await db
      .insert(sandboxes)
      .values({
        projectId: ticket.projectId,
        userId: ownerId,
        ticketId,
        magsWorkspaceId: wsId,
        magsJobId: jobId,
        workspaceType: "ticket",
        status: "ready",
      })
      .returning();

    sandboxRow = (created[0] as any) ?? null;
  }

  if (!sandboxRow || !workspaceId) throw new Error("Failed to create or find sandbox");
  const sandbox = sandboxRow;

  emit({ type: "ticket.execution_started", ticketId, sandboxId: sandbox.id });

  // ── Step 3: Setup git repo ──────────────────────────────────────────
  console.log(`[ticket-executor] Step 3: Setting up git`);
  let gitSetupError: string | null = null;

  // Extract GitHub owner/repo from project.stack or repoUrl
  const repoUrl = extractRepoUrl(project.stack ?? "");
  let githubOwner: string | null = null;
  let githubRepo: string | null = null;

  if (repoUrl) {
    const ghMatch = repoUrl.match(/github\.com\/([^/]+)\/([^/.]+)/);
    if (ghMatch) {
      githubOwner = ghMatch[1] ?? null;
      githubRepo = ghMatch[2] ?? null;
    }
  }

  if (githubOwner && githubRepo && githubToken) {
    await addLog(ticketId, `Setting up repo: ${githubOwner}/${githubRepo}`, "command", ownerId);
    console.log(`[ticket-executor] Git setup: ${githubOwner}/${githubRepo}, branch: ${featureBranch}`);

    const gitSetupScript = `
cd ${WORKING_DIR}

if [ -d "${projectDirName}/.git" ]; then
    echo "REPO_EXISTS"
    cd ${projectDirName}
    git fetch origin
    git reset --hard HEAD 2>/dev/null || true
    git clean -fd 2>/dev/null || true
elif [ -d "${projectDirName}" ] && [ "$(ls -A ${projectDirName} 2>/dev/null)" ]; then
    echo "INIT_EXISTING_DIR"
    cd ${projectDirName}
    git init
    git remote add origin https://${githubToken}@github.com/${githubOwner}/${githubRepo}.git 2>/dev/null || \
        git remote set-url origin https://${githubToken}@github.com/${githubOwner}/${githubRepo}.git
    git fetch origin
else
    echo "CLONING_REPO"
    rm -rf ${projectDirName}
    git clone https://${githubToken}@github.com/${githubOwner}/${githubRepo}.git ${projectDirName}
    cd ${projectDirName}
fi

# Checkout feature branch — always branch from lfg-agent if creating new
if git rev-parse --verify ${featureBranch} 2>/dev/null; then
    git checkout ${featureBranch}
    if git rev-parse --verify origin/${featureBranch} 2>/dev/null; then
        git reset --hard origin/${featureBranch}
    fi
else
    git checkout -b ${featureBranch} origin/${featureBranch} 2>/dev/null || \
        (git fetch origin lfg-agent 2>/dev/null && git checkout -b ${featureBranch} origin/lfg-agent 2>/dev/null) || \
        echo "BRANCH_ERROR"
fi
git pull origin ${featureBranch} 2>/dev/null || echo "PULL_SKIPPED"

git config user.email "ai@lfg.dev"
git config user.name "LFG AI"

echo "GIT_SETUP_COMPLETE"
pwd
git branch --show-current
`.trim();

    try {
      // exec() breaks with multi-line scripts — base64-encode
      const gitScriptB64 = Buffer.from(gitSetupScript).toString("base64");
      const gitResult = await execOnWorkspace(workspaceId, `echo ${gitScriptB64} | base64 -d | sh`, { timeout: 120_000 });
      console.log(`[ticket-executor] Git setup output:`, gitResult.output.slice(0, 300));

      if (gitResult.output.includes("GIT_SETUP_COMPLETE")) {
        console.log(`[ticket-executor] Git setup complete, branch: ${featureBranch}`);
        // Save branch name to ticket
        if (!ticket.githubBranch) {
          await db
            .update(projectTickets)
            .set({ githubBranch: featureBranch, githubMergeStatus: "pending", updatedAt: new Date() })
            .where(eq(projectTickets.id, ticketId));
        }
      } else {
        gitSetupError = `Git setup issue: ${gitResult.output.slice(0, 200)}`;
        console.warn(`[ticket-executor] ${gitSetupError}`);
      }
    } catch (err) {
      gitSetupError = `Git setup failed: ${err}`;
      console.error(`[ticket-executor] ${gitSetupError}`);
    }
  } else {
    // No repo — just ensure project dir exists
    await execOnWorkspace(workspaceId, `mkdir -p "${WORKING_DIR}/${projectDirName}"`, {
      timeout: 15_000,
    });
    console.log(`[ticket-executor] No GitHub repo linked — skipping git setup`);
    await addLog(ticketId, "No GitHub repo linked — starting fresh project", "command", ownerId);
  }

  // ── Step 4: Credentials are injected inline by startClaudeCli ──────
  console.log(`[ticket-executor] Step 4: Credentials will be injected by CLI launcher`);
  await addLog(ticketId, "Injecting Claude credentials...", "command", ownerId);

  // ── Step 5: Build prompt + env vars ────────────────────────────────
  console.log(`[ticket-executor] Step 5: Building prompt`);

  // Build git error context
  let gitErrorContext = "";
  if (gitSetupError && gitSetupError !== "No GitHub repo configured or missing token") {
    gitErrorContext = `
⚠️ GIT SETUP ISSUE DETECTED:
${gitSetupError}

Before implementing, fix the git issue:
1. Check: cd ${CLAUDE_HOME}/${projectDirName} && git status
2. Resolve any conflicts or uncommitted changes
3. Checkout the correct branch: git checkout ${featureBranch}
`;
  }

  // Check for existing session — resume with short prompt
  const existingSessionId = sandbox.cliSessionId ?? undefined;

  let prompt: string;
  if (existingSessionId) {
    console.log(`[ticket-executor] Resuming session ${existingSessionId.slice(0, 20)}...`);
    await addLog(ticketId, "Resuming existing Claude session...", "command", ownerId);
    prompt = `Continue implementing ticket #${ticket.id}: ${ticket.name}\n\n` +
      `The user clicked 'Continue' to resume execution. ` +
      `Check the current state of the project at ${CLAUDE_HOME}/${projectDirName}, ` +
      `review what has already been done, and continue implementing any remaining work. ` +
      `When done, call the status API to mark the ticket complete.`;
  } else {
    prompt = buildBuilderPrompt({
      ticket: {
        id: ticket.id,
        name: ticket.name,
        description: ticket.description,
        details: (ticket.details as Record<string, unknown>) ?? {},
        uiRequirements: (ticket.uiRequirements as Record<string, unknown>) ?? {},
        componentSpecs: (ticket.componentSpecs as Record<string, unknown>) ?? {},
        acceptanceCriteria: (ticket.acceptanceCriteria as string[]) ?? [],
        notes: ticket.notes ?? "",
      },
      project: {
        id: project.id,
        name: project.name,
        repoUrl: repoUrl ?? undefined,
      },
      callbackBaseUrl: CALLBACK_BASE_URL,
      cliApiKey,
      tasks: tasks.map((t) => ({
        id: t.id,
        description: t.description,
        status: t.status,
      })),
    });

    // Append git error context and project path info
    prompt += `\n\nPROJECT PATH: ${CLAUDE_HOME}/${projectDirName}\n`;
    if (gitErrorContext) prompt += gitErrorContext;
  }

  // LFG env vars passed to the runner script
  const envVars: Record<string, string> = {
    LFG_API_URL: CALLBACK_BASE_URL,
    LFG_API_KEY: cliApiKey,
    LFG_TICKET_ID: ticket.id,
    LFG_PROJECT_ID: project.id,
  };

  // ── Step 6: Start Claude CLI ──────────────────────────────────────
  console.log(`[ticket-executor] Step 6: Starting Claude CLI`);
  await addLog(ticketId, "Starting Claude Code CLI...", "command", ownerId);

  let cliResult;
  try {
    cliResult = await startClaudeCli({
      workspaceId,
      prompt,
      projectDir: projectDirName,
      sessionId: existingSessionId,
      userId: ownerId,
      envVars,
    });
  } catch (err) {
    const msg = `startClaudeCli failed: ${err}`;
    console.error(`[ticket-executor] ${msg}`);
    await addLog(ticketId, msg, "command", ownerId);
    throw err;
  }

  const { outputFile, backgroundPid } = cliResult;
  console.log(`[ticket-executor] CLI started, pid=${backgroundPid}, file=${outputFile}`);
  await addLog(ticketId, `CLI started (pid ${backgroundPid ?? "unknown"})`, "command", ownerId);

  // ── Step 7: Poll JSONL output ───────────────────────────────────────
  let offset = 0;
  let sessionId: string | undefined = existingSessionId;
  let completed = false;
  let implementationStatus: "complete" | "failed" | null = null;
  let pollCount = 0;
  let emptyPollCount = 0;
  let consecutiveSshFailures = 0;
  let allOutput = "";

  const deadline = Date.now() + MAX_POLL_DURATION_MS;

  while (Date.now() < deadline && !completed) {
    await sleep(POLL_INTERVAL_MS);
    pollCount++;

    let pollResult: PollResult;
    try {
      pollResult = await pollOutput(workspaceId, outputFile, offset, backgroundPid);
      consecutiveSshFailures = 0;
    } catch (err) {
      consecutiveSshFailures++;
      console.error(`[ticket-executor] Poll error #${consecutiveSshFailures}:`, err);
      if (consecutiveSshFailures >= MAX_SSH_FAILURES) {
        await addLog(ticketId, `Too many SSH failures (${MAX_SSH_FAILURES}), aborting`, "command", ownerId);
        break;
      }
      continue;
    }

    const { data, newOffset, alive } = pollResult;

    if (!data.trim()) {
      emptyPollCount++;
      if (emptyPollCount % 12 === 0) {
        console.log(`[ticket-executor] Poll #${pollCount}: ${emptyPollCount} empty polls, alive=${alive}`);
        await addLog(ticketId, `Waiting for CLI output... (${emptyPollCount * 5}s elapsed)`, "command", ownerId);
      }
      // If process is dead and output is empty, it may have crashed
      if (!alive && emptyPollCount > 3) {
        console.log(`[ticket-executor] Process dead with no output, ending poll`);
        await addLog(ticketId, "CLI process ended without output", "command", ownerId);
        break;
      }
      continue;
    }

    emptyPollCount = 0;
    offset = newOffset;
    allOutput += data;
    console.log(`[ticket-executor] Poll #${pollCount}: got ${data.length} bytes, offset=${offset}, alive=${alive}`);

    // Parse events
    const events = parseJsonlEvents(data);
    if (events.length > 0) {
      console.log(`[ticket-executor] Parsed ${events.length} events: ${events.map(e => e.type).join(", ")}`);
    }

    // Extract session ID
    if (!sessionId) {
      sessionId = extractSessionId(events) ?? undefined;
      if (sessionId) {
        console.log(`[ticket-executor] Got session ID: ${sessionId}`);
        await db
          .update(sandboxes)
          .set({ cliSessionId: sessionId, updatedAt: new Date() })
          .where(eq(sandboxes.id, sandbox.id));
      }
    }

    // Log events to DB + WS
    for (const ev of events) {
      if (ev.type === "assistant") {
        for (const block of ev.message.content) {
          if (block.type === "text" && block.text) {
            await addLog(ticketId, block.text, "ai_response", ownerId);
          } else if (block.type === "tool_use" && block.name) {
            // Format tool use like Django does
            const toolMsg = formatToolUse(block.name, block.input ?? {});
            await addLog(ticketId, toolMsg, "command", ownerId);
          }
        }
      } else if (ev.type === "user") {
        // Tool results — log significant ones
        for (const block of ev.message.content) {
          if (block.type === "tool_result" && block.content && block.content.length > 50) {
            await addLog(ticketId, block.content.slice(0, 500), "command", ownerId);
          }
        }
      } else if (ev.type === "error") {
        const errMsg = (ev as { type: "error"; error: string }).error;
        console.error(`[ticket-executor] CLI error event:`, errMsg);
        await addLog(ticketId, `CLI error: ${errMsg}`, "command", ownerId);
      }
    }

    // Check for completion
    if (data.includes("IMPLEMENTATION_STATUS: COMPLETE") || allOutput.includes("IMPLEMENTATION_STATUS: COMPLETE")) {
      implementationStatus = "complete";
      completed = true;
    } else if (data.includes("IMPLEMENTATION_STATUS: FAILED") || allOutput.includes("IMPLEMENTATION_STATUS: FAILED")) {
      implementationStatus = "failed";
      completed = true;
    } else if (isStreamComplete(events)) {
      // result event found — treat as complete
      implementationStatus = "complete";
      completed = true;
    }

    // If process died, do one more read then stop
    if (!alive && !completed) {
      await sleep(3000);
      try {
        const finalPoll = await pollOutput(workspaceId, outputFile, offset, backgroundPid);
        if (finalPoll.data.trim()) {
          allOutput += finalPoll.data;
          const finalEvents = parseJsonlEvents(finalPoll.data);
          for (const ev of finalEvents) {
            if (ev.type === "assistant") {
              for (const block of ev.message.content) {
                if (block.type === "text" && block.text) {
                  await addLog(ticketId, block.text, "ai_response", ownerId);
                }
              }
            }
          }
          if (finalPoll.data.includes("IMPLEMENTATION_STATUS: COMPLETE")) {
            implementationStatus = "complete";
          } else if (finalPoll.data.includes("IMPLEMENTATION_STATUS: FAILED")) {
            implementationStatus = "failed";
          }
        }
      } catch { /* ignore */ }

      // Check exit code
      const exitCode = extractExitCode(allOutput);
      if (exitCode === 0 && !implementationStatus) {
        implementationStatus = "complete";
      }
      completed = true;
    }
  }

  console.log(`[ticket-executor] Polling finished: completed=${completed}, status=${implementationStatus}, polls=${pollCount}`);

  if (!completed) {
    implementationStatus = "failed";
    await addLog(ticketId, "Execution timed out", "command", ownerId);
  }

  // Check for auth errors
  if (hasAuthError(allOutput)) {
    console.error(`[ticket-executor] Auth error detected in output`);
    await addLog(ticketId, "Claude authentication error — please reconnect in Settings", "command", ownerId);
    implementationStatus = "failed";
  }

  // ── Step 8: Commit & finalize ───────────────────────────────────────
  const durationMs = Date.now() - startTime;

  if (implementationStatus === "complete" && githubOwner && githubRepo && githubToken) {
    try {
      await addLog(ticketId, "Committing changes...", "command", ownerId);
      const { sha } = await commitAndPush({
        workspaceId,
        projectDir: `${CLAUDE_HOME}/${projectDirName}`,
        commitMessage: `feat: ${ticket.name}`,
        featureBranch,
        repoUrl: `https://github.com/${githubOwner}/${githubRepo}.git`,
        githubToken,
      });

      await db
        .update(projectTickets)
        .set({
          githubBranch: featureBranch,
          githubCommitSha: sha,
          updatedAt: new Date(),
        })
        .where(eq(projectTickets.id, ticketId));
    } catch (err) {
      await addLog(ticketId, `Git commit failed: ${err}`, "command", ownerId);
    }
  }

  if (implementationStatus === "complete") {
    await db
      .update(projectTickets)
      .set({
        status: "review",
        queueStatus: "none",
        executionTimeSeconds: durationMs / 1000,
        lastExecutionAt: new Date(),
        updatedAt: new Date(),
      })
      .where(eq(projectTickets.id, ticketId));
    await addLog(ticketId, "Ticket implementation complete!", "command", ownerId);
  } else {
    await markTicketFailed(ticketId, "Implementation did not complete", ownerId);
  }

  // Save session ID for future resume
  if (sessionId && sandbox) {
    await db
      .update(sandboxes)
      .set({ cliSessionId: sessionId, updatedAt: new Date() })
      .where(eq(sandboxes.id, sandbox.id));
  }

  emit({
    type: "ticket.execution_finished",
    ticketId,
    status: implementationStatus ?? "failed",
    durationMs,
  });
}

// ── Chat Resume Executor ──────────────────────────────────────────────

async function executeTicketChat(
  ticketId: string,
  message: string,
  sender: string
): Promise<void> {
  const [ticket] = await db
    .select()
    .from(projectTickets)
    .where(eq(projectTickets.id, ticketId))
    .limit(1);

  if (!ticket) throw new Error(`Ticket ${ticketId} not found`);

  const [project] = await db
    .select()
    .from(projects)
    .where(eq(projects.id, ticket.projectId))
    .limit(1);

  const ownerId = project!.ownerId;

  const [profile] = await db
    .select()
    .from(profiles)
    .where(eq(profiles.userId, ownerId))
    .limit(1);

  const cliApiKey = profile?.cliApiKey ?? "";

  const sandbox = await findExistingSandbox(ticketId);
  if (!sandbox?.magsWorkspaceId) {
    await addLog(ticketId, "No active sandbox for ticket chat", "command", ownerId);
    return;
  }

  const workspaceId = sandbox.magsWorkspaceId;
  const projectDirName = "project";
  let sessionId = sandbox.cliSessionId ?? undefined;

  const prompt = buildTicketChatPrompt(
    {
      ticket: { id: ticket.id, name: ticket.name, description: ticket.description },
      project: { id: project!.id, name: project!.name },
      callbackBaseUrl: CALLBACK_BASE_URL,
      cliApiKey,
    },
    message
  );

  const envVars: Record<string, string> = {
    LFG_API_URL: CALLBACK_BASE_URL,
    LFG_API_KEY: cliApiKey,
    LFG_TICKET_ID: ticket.id,
    LFG_PROJECT_ID: project!.id,
  };

  console.log(`[ticket-executor] Chat: starting CLI for ticket ${ticketId}, workspace ${workspaceId}, session=${sessionId ?? 'none'}`);

  const { outputFile, backgroundPid } = await startClaudeCli({
    workspaceId,
    prompt,
    projectDir: projectDirName,
    sessionId,
    userId: ownerId,
    envVars,
  });

  console.log(`[ticket-executor] Chat: CLI started, pid=${backgroundPid}, output=${outputFile}`);

  // Poll cycle for chat
  let offset = 0;
  const deadline = Date.now() + 10 * 60 * 1000;
  let completed = false;
  let allOutput = "";

  while (Date.now() < deadline && !completed) {
    await sleep(POLL_INTERVAL_MS);

    let pollResult: PollResult;
    try {
      pollResult = await pollOutput(workspaceId, outputFile, offset, backgroundPid);
    } catch (pollErr) {
      console.warn(`[ticket-executor] Chat poll error:`, pollErr);
      continue;
    }

    const { data, newOffset, alive } = pollResult;

    if (!data.trim()) {
      if (!alive) break;
      continue;
    }

    offset = newOffset;
    allOutput += data;

    const events = parseJsonlEvents(data);
    console.log(`[ticket-executor] Chat: parsed ${events.length} events, types: [${events.map(e => e.type).join(', ')}], dataLen=${data.length}`);

    // Stale session — retry without resume
    if (isStaleSession(events) && sessionId) {
      console.log(`[ticket-executor] Chat: stale session detected, retrying without resume`);
      sessionId = undefined;
      await db
        .update(sandboxes)
        .set({ cliSessionId: null, updatedAt: new Date() })
        .where(eq(sandboxes.id, sandbox.id));

      const retry = await startClaudeCli({
        workspaceId,
        prompt,
        projectDir: projectDirName,
        sessionId: undefined,
        userId: ownerId,
        envVars,
      });
      // IMPORTANT: use the NEW output file and pid from the retry
      Object.assign({ outputFile: retry.outputFile, backgroundPid: retry.backgroundPid });
      offset = 0;
      allOutput = "";
      continue;
    }

    // Log events to DB + WS (same as main executor)
    for (const ev of events) {
      if (ev.type === "assistant") {
        for (const block of (ev as any).message?.content ?? []) {
          if (block.type === "text" && block.text) {
            console.log(`[ticket-executor] Chat: logging ai_response, len=${block.text.length}`);
            await addLog(ticketId, block.text, "ai_response", ownerId);
          } else if (block.type === "tool_use" && block.name) {
            const toolMsg = formatToolUse(block.name, block.input ?? {});
            await addLog(ticketId, toolMsg, "command", ownerId);
          }
        }
      } else if (ev.type === "user") {
        for (const block of (ev as any).message?.content ?? []) {
          if (block.type === "tool_result" && block.content && block.content.length > 50) {
            await addLog(ticketId, block.content.slice(0, 500), "command", ownerId);
          }
        }
      } else if (ev.type === "result") {
        // Result event — may contain final text
        const result = ev as any;
        if (result.result) {
          console.log(`[ticket-executor] Chat: result event, text len=${result.result.length}`);
          await addLog(ticketId, result.result, "ai_response", ownerId);
        }
      } else if (ev.type === "error") {
        const errMsg = (ev as { type: "error"; error: string }).error;
        console.error(`[ticket-executor] Chat CLI error event:`, errMsg);
        await addLog(ticketId, `CLI error: ${errMsg}`, "command", ownerId);
      }
    }

    if (isStreamComplete(events) || data.includes("IMPLEMENTATION_STATUS:")) {
      completed = true;
    }

    if (!alive) {
      console.log(`[ticket-executor] Chat: CLI process no longer alive`);
      break;
    }
  }

  console.log(`[ticket-executor] Chat: poll loop ended, completed=${completed}, outputLength=${allOutput.length}`);
}

// ── Helpers ───────────────────────────────────────────────────────────

async function findExistingSandbox(ticketId: string) {
  const result = await db
    .select()
    .from(sandboxes)
    .where(
      and(
        eq(sandboxes.ticketId, ticketId),
        eq(sandboxes.workspaceType, "ticket")
      )
    )
    .limit(1);
  return result[0] ?? null;
}

async function addLog(
  ticketId: string,
  message: string,
  logType: "command" | "ai_response" | "user_message",
  userId?: string
) {
  const [inserted] = await db.insert(ticketLogs).values({
    ticketId,
    logType,
    command: message.slice(0, 2000),
  }).returning();

  // Push to frontend via WebSocket
  if (userId) {
    broadcastToUser(userId, {
      type: "ticket_log",
      ticketId,
      log: {
        id: inserted?.id,
        type: logType,
        message: message.slice(0, 2000),
        createdAt: inserted?.createdAt ?? new Date().toISOString(),
      },
    });
  }
}

async function markTicketFailed(ticketId: string, reason: string, userId?: string) {
  await db
    .update(projectTickets)
    .set({
      status: "failed",
      queueStatus: "none",
      updatedAt: new Date(),
    })
    .where(eq(projectTickets.id, ticketId));

  await addLog(ticketId, `Execution failed: ${reason}`, "command", userId);
}

/**
 * Format a tool_use block for log display, matching Django's approach.
 */
function formatToolUse(name: string, input: Record<string, unknown>): string {
  switch (name) {
    case "Bash":
      return `$ ${(input.command as string) ?? ""}`.slice(0, 500);
    case "Read":
      return `📄 Read: ${input.file_path ?? ""}`;
    case "Write":
      return `✏️ Write: ${input.file_path ?? ""}`;
    case "Edit":
      return `✏️ Edit: ${input.file_path ?? ""}`;
    case "Grep":
    case "Glob":
      return `🔍 ${name}: ${input.pattern ?? ""}`;
    case "TodoWrite":
      return `📋 TodoWrite: updating tasks`;
    default:
      return `🔧 ${name}`;
  }
}

function extractRepoUrl(stack: string): string | null {
  const match = stack.match(/https?:\/\/[^\s]+\.git|https?:\/\/github\.com\/[^\s]+/);
  return match?.[0] ?? null;
}

function sleep(ms: number) {
  return new Promise<void>((r) => setTimeout(r, ms));
}
