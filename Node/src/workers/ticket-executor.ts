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
 * Step 6: Start Claude CLI via runner script (nohup, root)
 * Step 7: Wait for completion (VM pushes output to /api/v1/cli/output/)
 * Step 8: On completion: commit, push, update ticket status
 *
 * Also handles ticket.chat_message events for session-resume chat.
 */

import { db } from "../config/db.ts";
import { projectTickets, projectTodoLists } from "../db/schema/tickets.ts";
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
  startClaudeCliChat,
  preflightCheck,
  saveCredentialsFromVm,
  markClaudeDisconnected,
} from "../services/claude-cli.ts";
import {
  commitAndPush,
  mergeToLfgAgent,
  createGitHubRepo,
  initAndPushRepo,
} from "../services/git.ts";
import {
  buildBuilderPrompt,
  buildTicketChatPrompt,
} from "../ai/prompts/builder.ts";
import { addLog } from "../services/ticket-logs.ts";
import { broadcastToUser } from "../ws/connection-manager.ts";
import { eq, and } from "drizzle-orm";

const CALLBACK_BASE_URL = process.env.APP_URL ?? "http://localhost:3000";
const MAX_WAIT_DURATION_MS = 45 * 60 * 1000; // 45 minutes
const CHAT_MAX_WAIT_DURATION_MS = 10 * 60 * 1000; // 10 minutes
const WORKING_DIR = "/root";

// ── Subscriber Setup ──────────────────────────────────────────────────

export async function startTicketWorker() {
  // Reset any tickets stuck in executing state from a previous crash
  await db
    .update(projectTickets)
    .set({ queueStatus: "none", updatedAt: new Date() })
    .where(eq(projectTickets.queueStatus, "executing"));

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

  // Auto-generate CLI API key if missing (required for callback auth)
  let cliApiKey = profile?.cliApiKey ?? "";
  if (!cliApiKey) {
    cliApiKey = `lfg_cli_${crypto.randomUUID().replace(/-/g, "")}`;
    await db
      .insert(profiles)
      .values({ userId: ownerId, cliApiKey })
      .onConflictDoUpdate({ target: profiles.userId, set: { cliApiKey, updatedAt: new Date() } });
    console.log(`[ticket-executor] Auto-generated CLI API key for user ${ownerId}`);
  }

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

  // Extract GitHub owner/repo from project fields or fallback to stack text
  let githubOwner: string | null = project.repoOwner ?? null;
  let githubRepo: string | null = project.repoName ?? null;
  const repoUrl = project.repoUrl ?? extractRepoUrl(project.stack ?? "");

  if (!githubOwner || !githubRepo) {
    if (repoUrl) {
      const ghMatch = repoUrl.match(/github\.com\/([^/]+)\/([^/.]+)/);
      if (ghMatch) {
        githubOwner = ghMatch[1] ?? null;
        githubRepo = ghMatch[2] ?? null;
      }
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

# Ensure lfg-agent branch exists (create from main/default if not)
if ! git rev-parse --verify origin/lfg-agent 2>/dev/null; then
    echo "CREATING_LFG_AGENT_BRANCH"
    DEFAULT_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo "main")
    git checkout "$DEFAULT_BRANCH" 2>/dev/null || git checkout main 2>/dev/null || true
    git checkout -b lfg-agent
    git push -u origin lfg-agent 2>&1
fi

# Checkout feature branch — always branch from lfg-agent if creating new
if git rev-parse --verify origin/${featureBranch} 2>/dev/null; then
    echo "FEATURE_BRANCH_EXISTS_REMOTE"
    git checkout ${featureBranch} 2>/dev/null || git checkout -b ${featureBranch} origin/${featureBranch}
    git reset --hard origin/${featureBranch}
elif git rev-parse --verify ${featureBranch} 2>/dev/null; then
    echo "FEATURE_BRANCH_EXISTS_LOCAL"
    git checkout ${featureBranch}
else
    echo "CREATING_FEATURE_BRANCH"
    git checkout origin/lfg-agent 2>/dev/null || git checkout lfg-agent 2>/dev/null || true
    git checkout -b ${featureBranch}
fi

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
  } else if (githubToken) {
    // No repo linked — auto-create one on GitHub (matching Django behavior)
    const repoName = project.providedName || project.name;
    await addLog(ticketId, `Creating GitHub repository: ${repoName}...`, "command", ownerId);
    console.log(`[ticket-executor] No repo linked — auto-creating GitHub repo: ${repoName}`);

    try {
      const repoResult = await createGitHubRepo({
        repoName,
        description: `LFG Project: ${project.name}`,
        isPrivate: true,
        githubToken,
      });

      githubOwner = repoResult.owner;
      githubRepo = repoResult.repoName;

      // Save repo info to project so future executions find it
      await db.update(projects).set({
        repoUrl: repoResult.repoUrl,
        repoOwner: repoResult.owner,
        repoName: repoResult.repoName,
        updatedAt: new Date(),
      }).where(eq(projects.id, project.id));

      await addLog(
        ticketId,
        repoResult.created
          ? `Created repo: ${githubOwner}/${githubRepo}`
          : `Using existing repo: ${githubOwner}/${githubRepo}`,
        "command",
        ownerId
      );

      // Ensure project dir exists, init git, push initial commit
      await execOnWorkspace(workspaceId, `mkdir -p "${WORKING_DIR}/${projectDirName}"`, {
        timeout: 15_000,
      });

      await initAndPushRepo({
        workspaceId,
        projectDir: `${WORKING_DIR}/${projectDirName}`,
        repoUrl: repoResult.repoUrl,
        branch: "main",
        githubToken,
      });

      // Create the feature branch from lfg-agent (initAndPushRepo leaves us on lfg-agent)
      const branchScript = `
cd "${WORKING_DIR}/${projectDirName}"
git checkout lfg-agent 2>/dev/null || true
git checkout -b ${featureBranch}
echo "BRANCH_CREATED"
`.trim();
      const branchB64 = Buffer.from(branchScript).toString("base64");
      await execOnWorkspace(workspaceId, `echo ${branchB64} | base64 -d | sh`, { timeout: 30_000 });

      // Save branch name to ticket
      await db
        .update(projectTickets)
        .set({ githubBranch: featureBranch, githubMergeStatus: "pending", updatedAt: new Date() })
        .where(eq(projectTickets.id, ticketId));

      console.log(`[ticket-executor] Auto-created repo and set up branch: ${featureBranch}`);
    } catch (err) {
      console.error(`[ticket-executor] Auto-create repo failed:`, err);
      await addLog(ticketId, `Failed to create GitHub repo: ${err}`, "command", ownerId);
      // Fall through — continue without git
      githubOwner = null;
      githubRepo = null;
      await execOnWorkspace(workspaceId, `mkdir -p "${WORKING_DIR}/${projectDirName}"`, {
        timeout: 15_000,
      });
    }
  } else {
    // No GitHub token at all — just ensure project dir exists
    await execOnWorkspace(workspaceId, `mkdir -p "${WORKING_DIR}/${projectDirName}"`, {
      timeout: 15_000,
    });
    console.log(`[ticket-executor] No GitHub token — skipping git setup`);
    await addLog(ticketId, "No GitHub token — code will not be persisted to a repository", "command", ownerId);
  }

  // ── Step 4: Refresh + inject credentials ────────────────────────────
  console.log(`[ticket-executor] Step 4: Refreshing credentials from auth sandbox`);
  await refreshCredentialsFromAuthSandbox(ownerId);
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
1. Check: cd ${WORKING_DIR}/${projectDirName} && git status
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
      `Check the current state of the project at ${WORKING_DIR}/${projectDirName}, ` +
      `review what has already been done, and continue implementing any remaining work. ` +
      `When done, call the status API to mark the ticket complete.`;
  } else {
    // Load saved tech stack from sandbox (agent may have reported it in a previous run)
    const savedTechStack = sandbox.techStack as {
      language?: string;
      framework?: string;
      packageManager?: string;
      startCommand?: string;
      buildCommand?: string;
      port?: number;
    } | null;

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
        techStack: project.stack || undefined,
      },
      techStack: savedTechStack ?? undefined,
      callbackBaseUrl: CALLBACK_BASE_URL,
      cliApiKey,
      tasks: tasks.map((t) => ({
        id: t.id,
        description: t.description,
        status: t.status,
      })),
    });

    // Append git error context and project path info
    prompt += `\n\nPROJECT PATH: ${WORKING_DIR}/${projectDirName}\n`;
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

  // ── Debug: Check forwarder connectivity after a few seconds ─────
  setTimeout(async () => {
    try {
      const debugResult = await execOnWorkspace(workspaceId, `cat /tmp/forwarder_debug.log 2>/dev/null || echo "NO_DEBUG_LOG"`, { timeout: 15_000 });
      console.log(`[ticket-executor] FORWARDER DEBUG:\n${debugResult.output}`);
      if (debugResult.output.includes("NO_DEBUG_LOG")) {
        console.log(`[ticket-executor] Runner script hasn't written debug log yet — may still be starting`);
      }
    } catch (err) {
      console.log(`[ticket-executor] Could not read debug log:`, err);
    }
  }, 5_000);

  // ── Step 7: Wait for completion via push-based output streaming ─────
  // The VM's runner script pushes JSONL output to POST /api/v1/cli/output/
  // which handles all log parsing, DB inserts, and WS broadcasting.
  // The executor just waits for the ticket.execution_finished event.
  console.log(`[ticket-executor] Waiting for VM to push output via callback API...`);

  const waitResult = await waitForCompletion(ticketId, MAX_WAIT_DURATION_MS);

  let implementationStatus: "complete" | "failed" | null = null;
  if (waitResult.status === "complete") {
    implementationStatus = "complete";
  } else if (waitResult.status === "failed") {
    implementationStatus = "failed";
  } else {
    // timeout
    implementationStatus = "failed";
    await addLog(ticketId, "Execution timed out (45 minutes)", "command", ownerId);
  }

  console.log(`[ticket-executor] Wait finished: status=${waitResult.status}, exitCode=${waitResult.exitCode}`);

  // ── Step 8: Commit & finalize ───────────────────────────────────────
  const durationMs = Date.now() - startTime;

  if (implementationStatus === "complete" && githubOwner && githubRepo && githubToken) {
    try {
      await addLog(ticketId, "Committing changes...", "command", ownerId);
      const { sha } = await commitAndPush({
        workspaceId,
        projectDir: `${WORKING_DIR}/${projectDirName}`,
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

      // Merge feature branch → lfg-agent (direct push, no PR)
      try {
        await addLog(ticketId, "Merging to lfg-agent...", "command", ownerId);
        const { sha: mergeSha } = await mergeToLfgAgent({
          workspaceId,
          projectDir: `${WORKING_DIR}/${projectDirName}`,
          featureBranch,
          repoUrl: `https://github.com/${githubOwner}/${githubRepo}.git`,
          githubToken,
        });
        await db
          .update(projectTickets)
          .set({
            githubMergeStatus: "merged",
            updatedAt: new Date(),
          })
          .where(eq(projectTickets.id, ticketId));
        await addLog(ticketId, `Merged to lfg-agent (${mergeSha.slice(0, 7)})`, "command", ownerId);
      } catch (mergeErr) {
        console.warn(`[ticket-executor] Merge to lfg-agent failed:`, mergeErr);
        await addLog(ticketId, `Merge to lfg-agent failed: ${mergeErr}`, "command", ownerId);
      }
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
    broadcastToUser(ownerId, { type: "ticket_status", ticketId, status: "review", queueStatus: "none" });
  } else {
    await markTicketFailed(ticketId, "Implementation did not complete", ownerId);
    broadcastToUser(ownerId, { type: "ticket_status", ticketId, status: "failed", queueStatus: "none" });
  }

  // Session ID is now saved by the /api/v1/cli/output/ endpoint
  // when it receives the init event from the JSONL stream.

  // Save credentials back to DB (may have been refreshed during the run)
  if (sandbox?.magsWorkspaceId) {
    await saveCredentialsFromVm(sandbox.magsWorkspaceId, ownerId);
  }
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
    await addLog(ticketId, "No active sandbox for this ticket. Please build the ticket first.", "command", ownerId);
    return;
  }

  const workspaceId = sandbox.magsWorkspaceId;
  const projectDirName = "project";
  let sessionId = sandbox.cliSessionId ?? undefined;

  // Refresh credentials from auth sandbox (may have been auto-refreshed)
  await refreshCredentialsFromAuthSandbox(ownerId);

  // Pre-flight: verify Claude CLI is working
  console.log(`[ticket-executor] Chat: running pre-flight check on workspace ${workspaceId}`);
  const preflight = await preflightCheck(workspaceId, ownerId);
  if (!preflight.ok) {
    console.error(`[ticket-executor] Chat: pre-flight failed:`, preflight.error);
    const errorMsg = preflight.error ?? "Claude CLI is not connected. Please connect Claude Code in Settings.";
    // Mark as disconnected in DB so Settings page shows correct status
    if (preflight.needsReconnect) {
      await markClaudeDisconnected(ownerId);
    }
    // Log as cli_error type so frontend can style it differently
    await addLog(ticketId, errorMsg, "cli_error", ownerId);
    return;
  }
  console.log(`[ticket-executor] Chat: pre-flight passed`);

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

  // Use lightweight chat launcher (no user creation, just prompt + launch)
  const { outputFile, backgroundPid } = await startClaudeCliChat({
    workspaceId,
    prompt,
    projectDir: projectDirName,
    sessionId,
    userId: ownerId,
    envVars,
  });

  console.log(`[ticket-executor] Chat: CLI started, pid=${backgroundPid}, output=${outputFile}`);

  // Wait for completion via push-based output streaming
  // The VM's runner script pushes JSONL output to POST /api/v1/cli/output/
  const waitResult = await waitForCompletion(ticketId, CHAT_MAX_WAIT_DURATION_MS);
  console.log(`[ticket-executor] Chat: wait finished, status=${waitResult.status}, exitCode=${waitResult.exitCode}`);

  // ── Commit + push changes made during chat ──────────────────────────
  const [ghToken] = await db
    .select()
    .from(githubTokens)
    .where(eq(githubTokens.userId, ownerId))
    .limit(1);

  const githubToken = ghToken?.accessToken;

  let chatGhOwner: string | null = project!.repoOwner ?? null;
  let chatGhRepo: string | null = project!.repoName ?? null;
  const chatRepoUrl = project!.repoUrl ?? extractRepoUrl(project!.stack ?? "");

  if (!chatGhOwner || !chatGhRepo) {
    if (chatRepoUrl) {
      const ghMatch = chatRepoUrl.match(/github\.com\/([^/]+)\/([^/.]+)/);
      if (ghMatch) {
        chatGhOwner = ghMatch[1] ?? null;
        chatGhRepo = ghMatch[2] ?? null;
      }
    }
  }

  if (chatGhOwner && chatGhRepo && githubToken) {
    const featureBranch = ticket.githubBranch ?? `feature/ticket-${ticketId}`;
    try {
      await addLog(ticketId, "Committing chat changes...", "command", ownerId);
      const { sha } = await commitAndPush({
        workspaceId,
        projectDir: `${WORKING_DIR}/${projectDirName}`,
        commitMessage: `update: ${ticket.name} (chat)`,
        featureBranch,
        repoUrl: `https://github.com/${chatGhOwner}/${chatGhRepo}.git`,
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

      await addLog(ticketId, `Pushed commit ${sha.slice(0, 7)} to ${featureBranch}`, "command", ownerId);

      // Merge feature branch → lfg-agent (direct push)
      try {
        const { sha: mergeSha } = await mergeToLfgAgent({
          workspaceId: sandbox.magsWorkspaceId!,
          projectDir: `${WORKING_DIR}/${projectDirName}`,
          featureBranch,
          repoUrl: `https://github.com/${chatGhOwner}/${chatGhRepo}.git`,
          githubToken,
        });
        await db
          .update(projectTickets)
          .set({ githubMergeStatus: "merged", updatedAt: new Date() })
          .where(eq(projectTickets.id, ticketId));
        await addLog(ticketId, `Merged to lfg-agent (${mergeSha.slice(0, 7)})`, "command", ownerId);
      } catch (mergeErr) {
        console.warn(`[ticket-executor] Chat: merge to lfg-agent failed:`, mergeErr);
        await addLog(ticketId, `Merge to lfg-agent failed: ${mergeErr}`, "command", ownerId);
      }
    } catch (err) {
      // commitAndPush returns NO_CHANGES gracefully, so this is a real error
      const errMsg = String(err);
      if (!errMsg.includes("NO_CHANGES")) {
        console.warn(`[ticket-executor] Chat: commit+push failed:`, err);
        await addLog(ticketId, `Git commit failed: ${err}`, "command", ownerId);
      }
    }
  }

  // Save credentials back to DB after chat
  await saveCredentialsFromVm(workspaceId, ownerId);
}

// ── Helpers ───────────────────────────────────────────────────────────

/**
 * Wait for a ticket's execution to finish via the event bus.
 * The VM pushes output to /api/v1/cli/output/ which emits
 * ticket.execution_finished when done=true is received.
 * Returns when the event fires or when timeout is reached.
 */
function waitForCompletion(
  ticketId: string,
  timeoutMs: number
): Promise<{ status: "complete" | "failed" | "timeout"; exitCode?: number }> {
  return new Promise((resolve) => {
    const timeout = setTimeout(() => {
      cleanup();
      resolve({ status: "timeout" });
    }, timeoutMs);

    const handler = (event: any) => {
      if (event.payload.ticketId !== ticketId) return;
      cleanup();
      resolve({
        status: event.payload.exitCode === 0 ? "complete" : "failed",
        exitCode: event.payload.exitCode,
      });
    };

    const cleanup = () => {
      clearTimeout(timeout);
      bus.off("ticket.execution_finished", handler);
    };

    bus.on("ticket.execution_finished", handler);
  });
}

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

/**
 * Try to refresh DB credentials from the auth sandbox.
 * The auth sandbox may have auto-refreshed tokens that the DB doesn't have.
 * This is a best-effort operation — if the auth sandbox is unavailable, we continue with DB creds.
 */
async function refreshCredentialsFromAuthSandbox(userId: string): Promise<void> {
  try {
    // Find the user's auth sandbox
    const [authSandbox] = await db.select().from(sandboxes)
      .where(and(eq(sandboxes.userId, userId), eq(sandboxes.workspaceType, "claude_auth")))
      .limit(1);

    if (!authSandbox?.magsWorkspaceId) return;

    // Try to read fresh credentials from the auth sandbox
    const { saveCredentialsFromVm: saveCreds } = await import("../services/claude-cli.ts");
    const saved = await saveCreds(authSandbox.magsWorkspaceId, userId);
    if (saved) {
      console.log(`[ticket-executor] Refreshed credentials from auth sandbox ${authSandbox.magsWorkspaceId}`);
    }
  } catch (err) {
    // Auth sandbox might be sleeping/unavailable — that's fine, continue with DB creds
    console.log(`[ticket-executor] Could not refresh from auth sandbox: ${(err as Error).message?.slice(0, 100)}`);
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

function extractRepoUrl(stack: string): string | null {
  const match = stack.match(/https?:\/\/[^\s]+\.git|https?:\/\/github\.com\/[^\s]+/);
  return match?.[0] ?? null;
}

function sleep(ms: number) {
  return new Promise<void>((r) => setTimeout(r, ms));
}
