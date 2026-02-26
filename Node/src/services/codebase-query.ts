/**
 * Codebase Query Service
 *
 * Uses a "preview" sandbox (persistent Mags VM with the repo cloned)
 * and Claude Code CLI to answer questions about the user's codebase.
 *
 * Flow:
 *  1. Find or create a preview sandbox for the project
 *  2. Clone repo (all branches) into /root/git-review/ if not already there
 *  3. Run `claude -p "<question>" --output-format json --max-turns 10`
 *  4. Parse JSON output → extract answer + session_id
 *  5. Save session_id on sandbox for follow-up queries
 */

import { db } from "../config/db.ts";
import { sandboxes } from "../db/schema/sandbox.ts";
import { projects } from "../db/schema/projects.ts";
import { githubTokens } from "../db/schema/users.ts";
import {
  newWorkspace,
  execOnWorkspace,
  stopWorkspace,
} from "./mags.ts";
import { injectCredentials, loadCredentials } from "./claude-cli.ts";
import { CLAUDE_AUTH_SETUP_SCRIPT } from "./claude-auth.ts";
import { eq, and } from "drizzle-orm";

const REVIEW_DIR = "/root/git-review";
const CLAUDE_BIN = "/usr/local/bin/claude";

export interface QueryCodebaseResult {
  answer: string;
  sessionId?: string;
  branch?: string;
}

// ── Helpers ───────────────────────────────────────────────────────────

function b64script(script: string): string {
  return `echo ${Buffer.from(script).toString("base64")} | base64 -d | sh`;
}

function sleep(ms: number) {
  return new Promise<void>((r) => setTimeout(r, ms));
}

// ── Get or Create Preview Sandbox ─────────────────────────────────────

export async function getOrCreatePreviewSandbox(
  projectId: string,
  userId: string,
  repoUrl: string,
  githubToken: string
): Promise<typeof sandboxes.$inferSelect> {
  // 1. Check for existing preview sandbox
  const [existing] = await db
    .select()
    .from(sandboxes)
    .where(
      and(
        eq(sandboxes.projectId, projectId),
        eq(sandboxes.workspaceType, "preview")
      )
    )
    .limit(1);

  if (existing?.magsWorkspaceId) {
    // Probe VM to see if it's alive
    try {
      const probe = await execOnWorkspace(
        existing.magsWorkspaceId,
        "echo ALIVE",
        { timeout: 15_000 }
      );
      if (probe.output.includes("ALIVE")) {
        // VM is alive — update repo
        console.log(`[codebase-query] Existing preview sandbox alive: ${existing.magsWorkspaceId}`);
        await refreshPreviewRepo(existing.magsWorkspaceId);
        return existing;
      }
    } catch {
      // Dead VM — fall through to create new
      console.log(`[codebase-query] Preview sandbox dead, will recreate: ${existing.magsWorkspaceId}`);
    }

    // Clean up dead sandbox record
    try {
      await stopWorkspace(existing.magsWorkspaceId).catch(() => {});
    } catch { /* ignore */ }
    await db.delete(sandboxes).where(eq(sandboxes.id, existing.id));
  }

  // 2. Create new preview sandbox
  const workspaceName = `preview-${projectId.slice(0, 8)}-${crypto.randomUUID().slice(0, 8)}`;
  console.log(`[codebase-query] Creating preview sandbox: ${workspaceName}`);

  const { jobId, workspaceId } = await newWorkspace(workspaceName);

  // Wait for VM to boot
  await sleep(10_000);

  // 3. Run init script: install packages + Node + Claude CLI + clone repo
  const authUrl = repoUrl.replace(
    "https://",
    `https://x-access-token:${githubToken}@`
  );

  const initScript = `
set -e

# Install system packages
apk update && apk add --no-cache curl xz git bash openssh-client

# Install Node.js
cd /root && mkdir -p node && cd node
if [ ! -d node-v20.18.0-linux-x64 ]; then
    curl -fsSL https://nodejs.org/dist/v20.18.0/node-v20.18.0-linux-x64.tar.xz -o node.tar.xz
    tar -xf node.tar.xz && rm node.tar.xz
    ln -sfn node-v20.18.0-linux-x64 current
fi
export PATH=/root/node/current/bin:$PATH
mkdir -p /root/.npm-global /root/.npm-cache
npm config set prefix /root/.npm-global
npm config set cache /root/.npm-cache

# Install Claude CLI
npm install -g @anthropic-ai/claude-code

# Clone repo with all branches
git clone "${authUrl}" ${REVIEW_DIR}
cd ${REVIEW_DIR}
git fetch --all

echo "PREVIEW_INIT_COMPLETE"
`.trim();

  const initResult = await execOnWorkspace(
    workspaceId,
    b64script(initScript),
    { timeout: 300_000 }
  );

  if (!initResult.output.includes("PREVIEW_INIT_COMPLETE")) {
    throw new Error(
      `Preview sandbox init failed: ${initResult.output.slice(0, 500)}`
    );
  }

  console.log(`[codebase-query] Preview sandbox initialized: ${workspaceId}`);

  // 4. Inject Claude credentials
  const injected = await injectCredentials(workspaceId, userId);
  if (!injected) {
    console.warn(`[codebase-query] Could not inject credentials — queries may fail`);
  }

  // 5. Insert sandbox record
  const [row] = await db
    .insert(sandboxes)
    .values({
      projectId,
      userId,
      magsWorkspaceId: workspaceId,
      magsJobId: jobId,
      workspaceType: "preview",
      status: "ready",
    })
    .returning();

  return row!;
}

// ── Query Codebase ────────────────────────────────────────────────────

export async function queryCodebase(
  workspaceId: string,
  question: string,
  opts?: {
    branch?: string;
    sessionId?: string;
    maxTurns?: number;
  }
): Promise<QueryCodebaseResult> {
  const branch = opts?.branch;
  const sessionId = opts?.sessionId;
  const maxTurns = opts?.maxTurns ?? 10;

  // Checkout branch if specified
  if (branch) {
    const checkoutScript = `
cd ${REVIEW_DIR}
git checkout ${branch} 2>/dev/null || git checkout -b ${branch} origin/${branch} 2>/dev/null || echo "BRANCH_CHECKOUT_FAILED"
echo "BRANCH_READY"
`.trim();

    const checkoutResult = await execOnWorkspace(
      workspaceId,
      b64script(checkoutScript),
      { timeout: 30_000 }
    );

    if (checkoutResult.output.includes("BRANCH_CHECKOUT_FAILED") && !checkoutResult.output.includes("BRANCH_READY")) {
      console.warn(`[codebase-query] Branch checkout issue: ${checkoutResult.output.slice(0, 200)}`);
    }
  }

  // Build the claude command
  const questionB64 = Buffer.from(question).toString("base64");

  const runScript = `
export HOME=/root
export PATH=/root/node/current/bin:/root/.npm-global/bin:$PATH
cd ${REVIEW_DIR}

QUESTION=$(echo '${questionB64}' | base64 -d)

${CLAUDE_BIN} -p "$QUESTION" \\
  --output-format json \\
  --max-turns ${maxTurns} \\
  --dangerously-skip-permissions \\
  ${sessionId ? `--resume "${sessionId}"` : ""} \\
  2>&1
`.trim();

  console.log(`[codebase-query] Running query on ${workspaceId}, branch=${branch ?? "current"}, session=${sessionId ?? "new"}`);

  const result = await execOnWorkspace(
    workspaceId,
    b64script(runScript),
    { timeout: 180_000 }
  );

  const output = result.output.trim();
  console.log(`[codebase-query] Raw output length: ${output.length}, exitCode: ${result.exitCode}`);

  // Parse JSON output
  return parseClaudeJsonOutput(output, branch);
}

// ── Refresh Preview Repo ──────────────────────────────────────────────

export async function refreshPreviewRepo(workspaceId: string): Promise<void> {
  const result = await execOnWorkspace(
    workspaceId,
    `cd ${REVIEW_DIR} && git fetch --all 2>&1 && echo FETCH_OK`,
    { timeout: 60_000 }
  );

  if (!result.output.includes("FETCH_OK")) {
    console.warn(`[codebase-query] git fetch issue: ${result.output.slice(0, 200)}`);
  }
}

// ── Parse Claude JSON Output ──────────────────────────────────────────

function parseClaudeJsonOutput(
  output: string,
  branch?: string
): QueryCodebaseResult {
  // --output-format json produces a single JSON object (not JSONL).
  // It may also have extra stderr lines before/after the JSON.
  // Try to find and parse the JSON object.

  let parsed: any = null;

  // Try parsing the entire output as JSON first
  try {
    parsed = JSON.parse(output);
  } catch {
    // Try to extract JSON from within the output
    const jsonStart = output.indexOf("{");
    const jsonEnd = output.lastIndexOf("}");
    if (jsonStart >= 0 && jsonEnd > jsonStart) {
      try {
        parsed = JSON.parse(output.slice(jsonStart, jsonEnd + 1));
      } catch {
        // Fall through to raw text fallback
      }
    }
  }

  if (parsed) {
    // JSON format output: { result, session_id, ... }
    const answer = parsed.result ?? parsed.text ?? "";
    const newSessionId = parsed.session_id ?? undefined;

    return {
      answer: answer || extractFallbackAnswer(output),
      sessionId: newSessionId,
      branch,
    };
  }

  // If JSON parsing fails, try JSONL (multiple JSON objects, one per line)
  const lines = output.split("\n");
  let answer = "";
  let newSessionId: string | undefined;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("{")) continue;
    try {
      const event = JSON.parse(trimmed);
      // Extract session_id from init event
      if (event.type === "system" && event.subtype === "init" && event.session_id) {
        newSessionId = event.session_id;
      }
      // Extract answer from result event
      if (event.type === "result" && event.result) {
        answer = event.result;
      }
      // Extract text from assistant messages
      if (event.type === "assistant" && event.message?.content) {
        for (const block of event.message.content) {
          if (block.type === "text" && block.text) {
            answer = block.text; // Keep last assistant text
          }
        }
      }
    } catch {
      // Skip unparseable lines
    }
  }

  return {
    answer: answer || extractFallbackAnswer(output),
    sessionId: newSessionId,
    branch,
  };
}

/**
 * If all parsing fails, return the raw output trimmed as the answer.
 */
function extractFallbackAnswer(output: string): string {
  // Strip obvious noise lines
  const lines = output.split("\n").filter((l) => {
    const t = l.trim();
    return (
      t &&
      !t.startsWith("╭") &&
      !t.startsWith("╰") &&
      !t.startsWith("│") &&
      !t.startsWith("Loading")
    );
  });
  return lines.join("\n").trim().slice(0, 5000) || "No answer returned from codebase query.";
}
