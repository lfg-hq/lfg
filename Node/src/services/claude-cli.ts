/**
 * Claude Code CLI runner
 *
 * Manages Claude credentials in DB, copies them to Mags VMs,
 * and runs the Claude CLI with streaming JSONL output.
 *
 * Flow (matching Django's claude_code_utils.py):
 *  1. Load credentials from DB
 *  2. Write prompt file, env file, runner script to VM via base64
 *  3. Create claudeuser, copy credentials, setup project dir symlink
 *  4. Launch CLI via nohup su -s /bin/bash claudeuser
 *  5. Poll output file with byte offset + alive check
 */

import { db } from "../config/db.ts";
import { profiles } from "../db/schema/users.ts";
import { execOnWorkspace } from "./mags.ts";
import { eq } from "drizzle-orm";

export interface ClaudeRunOptions {
  workspaceId: string;
  prompt: string;
  projectDir: string;         // e.g. "project" (relative to /root)
  sessionId?: string;          // resume an existing Claude session
  maxTurns?: number;
  outputFile?: string;
  userId: string;
  envVars?: Record<string, string>; // LFG env vars to inject
}

export interface ClaudeRunResult {
  outputFile: string;
  sessionId?: string;
  backgroundPid?: string;
}

export interface PollResult {
  data: string;
  newOffset: number;
  alive: boolean;
}

const CLAUDE_USER = "claudeuser";
const CLAUDE_HOME = `/home/${CLAUDE_USER}`;
const CLAUDE_BIN = "/usr/local/bin/claude";
const WORKING_DIR = "/root";
const DEFAULT_MAX_TURNS = 80;

// ── Credentials ───────────────────────────────────────────────────────

/**
 * Load Claude Code credentials from DB for a user.
 * Returns the raw credentials JSON string.
 */
export async function loadCredentials(userId: string): Promise<string | null> {
  const [profile] = await db
    .select()
    .from(profiles)
    .where(eq(profiles.userId, userId))
    .limit(1);

  return profile?.claudeCodeCredentials ?? null;
}

/**
 * Save updated Claude credentials back to DB after a session.
 */
export async function saveCredentials(
  userId: string,
  configJson: string
): Promise<void> {
  await db
    .update(profiles)
    .set({
      claudeCodeCredentials: configJson,
      claudeCodeCredentialsUpdatedAt: new Date(),
      updatedAt: new Date(),
    })
    .where(eq(profiles.userId, userId));
}

// ── VM Auth Setup ─────────────────────────────────────────────────────

/**
 * Copy user's Claude credentials into the VM.
 * Writes to /root/.claude/.credentials.json (exec runs as root)
 * and copies to /home/claudeuser/.claude/.credentials.json.
 */
export async function injectCredentials(
  workspaceId: string,
  userId: string
): Promise<boolean> {
  const credentials = await loadCredentials(userId);
  if (!credentials) {
    console.log("[claude-cli] No credentials in DB for user", userId);
    return false;
  }

  console.log("[claude-cli] Injecting credentials, length:", credentials.length);

  const b64 = Buffer.from(credentials).toString("base64");

  const script = `
mkdir -p /root/.claude
echo '${b64}' | base64 -d > /root/.claude/.credentials.json
chmod 600 /root/.claude/.credentials.json
mkdir -p ${CLAUDE_HOME}/.claude
cp /root/.claude/.credentials.json ${CLAUDE_HOME}/.claude/.credentials.json
chown -R 1000:1000 ${CLAUDE_HOME}/.claude 2>/dev/null || true
chmod 600 ${CLAUDE_HOME}/.claude/.credentials.json
ls -la ${CLAUDE_HOME}/.claude/.credentials.json 2>&1
echo "credentials_injected"
`.trim();

  // exec() breaks with multi-line commands — base64-encode
  const scriptB64 = Buffer.from(script).toString("base64");
  const result = await execOnWorkspace(workspaceId, `echo ${scriptB64} | base64 -d | sh`);
  console.log("[claude-cli] inject result:", result.output.slice(0, 300));
  return result.output.includes("credentials_injected");
}

/**
 * Check if Claude auth is valid in the VM.
 */
export async function checkClaudeAuth(workspaceId: string): Promise<boolean> {
  try {
    const result = await execOnWorkspace(
      workspaceId,
      `su -s /bin/sh ${CLAUDE_USER} -c "${CLAUDE_BIN} --version" 2>&1 || echo "AUTH_FAILED"`,
      { timeout: 30_000 }
    );
    return (
      !result.output.includes("AUTH_FAILED") &&
      !result.output.includes("not logged in") &&
      result.exitCode === 0
    );
  } catch {
    return false;
  }
}

// ── CLI Runner ────────────────────────────────────────────────────────

/**
 * Start the Claude CLI in the VM (non-blocking, runs in background).
 *
 * Matching Django's run_claude_cli():
 *  1. Write prompt to /tmp/claude_prompt_{ts}.txt
 *  2. Write env exports to /tmp/claude_env_{ts}.sh
 *  3. Write runner script to /tmp/claude_runner_{ts}.sh
 *  4. Inject DB credentials into /root/.claude/.credentials.json
 *  5. Create claudeuser, copy creds, setup project dir symlink
 *  6. Launch via nohup su -s /bin/bash claudeuser
 */
export async function startClaudeCli(
  opts: ClaudeRunOptions
): Promise<ClaudeRunResult> {
  const ts = Date.now();
  const outputFile = opts.outputFile ?? `/tmp/claude_output_${ts}.jsonl`;
  const promptFile = `/tmp/claude_prompt_${ts}.txt`;
  const envFile = `/tmp/claude_env_${ts}.sh`;
  const runnerScript = `/tmp/claude_runner_${ts}.sh`;
  const maxTurns = opts.maxTurns ?? DEFAULT_MAX_TURNS;

  // Build claude args
  const claudeArgs: string[] = [
    "--output-format stream-json",
    "--verbose",
    "--dangerously-skip-permissions",
    `--max-turns ${maxTurns}`,
  ];
  if (opts.sessionId) {
    claudeArgs.push(`--resume "${opts.sessionId}"`);
  }
  const claudeArgsStr = claudeArgs.join(" ");

  // Relative project dir name (e.g. "project")
  const projectDirName = opts.projectDir.replace(/^\/root\//, "").replace(/^\//, "");

  // Build env exports
  const envExports = Object.entries(opts.envVars ?? {})
    .map(([k, v]) => `export ${k}="${v}"`)
    .join("\n");

  // Runner script content — runs as claudeuser
  const runnerContent = `#!/bin/bash
export HOME=${CLAUDE_HOME}
export PATH=/root/node/current/bin:/root/.npm-global/bin:$PATH
export npm_config_prefix=/root/.npm-global
export NPM_CONFIG_PREFIX=/root/.npm-global
export NPM_CONFIG_CACHE=${CLAUDE_HOME}/.npm
export npm_config_cache=${CLAUDE_HOME}/.npm
umask 000
source ${envFile}
cd ${CLAUDE_HOME}
${CLAUDE_BIN} -p "$(cat ${promptFile})" ${claudeArgsStr} > ${outputFile} 2>&1
CLAUDE_EXIT=$?
echo "" >> ${outputFile}
echo "___CLAUDE_EXIT_CODE=$CLAUDE_EXIT" >> ${outputFile}
`;

  // Base64-encode all payloads
  const promptB64 = Buffer.from(opts.prompt).toString("base64");
  const envB64 = Buffer.from(envExports).toString("base64");
  const runnerB64 = Buffer.from(runnerContent).toString("base64");

  // Also inject credentials inline (avoids overlay reset losing them)
  let dbCredsInject = "";
  const creds = await loadCredentials(opts.userId);
  if (creds) {
    const credsB64 = Buffer.from(creds).toString("base64");
    dbCredsInject = `
# Inject credentials from DB
mkdir -p /root/.claude
echo '${credsB64}' | base64 -d > /root/.claude/.credentials.json
`;
  }

  // Single combined command: write all files + setup user + launch Claude
  const startCmd = `export HOME=/root

# Write prompt and env files via base64
echo '${promptB64}' | base64 -d > ${promptFile}
echo '${envB64}' | base64 -d > ${envFile}
${dbCredsInject}
# Verify credentials exist
if [ ! -f /root/.claude/.credentials.json ]; then
    echo "ERROR: No credentials found at /root/.claude"
    ls -la /root/.claude/ 2>&1 || echo "No .claude directory"
    exit 1
fi

# Verify claude binary exists
CLAUDE_BIN_PATH="${CLAUDE_BIN}"
if [ ! -x "$CLAUDE_BIN_PATH" ]; then
    # Try finding it
    CLAUDE_BIN_PATH=$(which claude 2>/dev/null || echo "${CLAUDE_BIN}")
    if [ ! -x "$CLAUDE_BIN_PATH" ]; then
        echo "ERROR: Claude binary not found at ${CLAUDE_BIN}"
        exit 1
    fi
fi

# Setup non-root user for Claude CLI
CLAUDE_USER=${CLAUDE_USER}
CLAUDE_HOME_DIR=${CLAUDE_HOME}
id $CLAUDE_USER >/dev/null 2>&1 || adduser -D -h $CLAUDE_HOME_DIR -s /bin/bash $CLAUDE_USER

# Copy credential files
mkdir -p $CLAUDE_HOME_DIR/.claude
for f in .credentials.json settings.json statsig.json; do
    [ -f /root/.claude/$f ] && cp /root/.claude/$f $CLAUDE_HOME_DIR/.claude/$f
done
chown -R $CLAUDE_USER:$CLAUDE_USER $CLAUDE_HOME_DIR/.claude

# Set permissions
chmod o+rx /root 2>/dev/null || true

# Create project dir under claudeuser's HOME and symlink from /root
PROJ_DIR="${WORKING_DIR}/${projectDirName}"
CLAUDE_PROJ="$CLAUDE_HOME_DIR/${projectDirName}"
mkdir -p "$CLAUDE_PROJ"
# If /root/project is a real directory (not a symlink), copy its contents first
if [ -d "$PROJ_DIR" ] && [ ! -L "$PROJ_DIR" ]; then
    cp -a "$PROJ_DIR/." "$CLAUDE_PROJ/" 2>/dev/null || true
fi
chown -R $CLAUDE_USER:$CLAUDE_USER "$CLAUDE_PROJ"
# Symlink /root/project -> /home/claudeuser/project so root-level git commands still work
rm -rf "$PROJ_DIR" 2>/dev/null || true
ln -sf "$CLAUDE_PROJ" "$PROJ_DIR"
# Mark both paths as safe for git
git config --global --add safe.directory "$CLAUDE_PROJ" 2>/dev/null || true
git config --global --add safe.directory "$PROJ_DIR" 2>/dev/null || true
su -s /bin/sh $CLAUDE_USER -c "git config --global --add safe.directory $CLAUDE_PROJ" 2>/dev/null || true
su -s /bin/sh $CLAUDE_USER -c "git config --global --add safe.directory $PROJ_DIR" 2>/dev/null || true
mkdir -p $CLAUDE_HOME_DIR/.npm
chown -R $CLAUDE_USER:$CLAUDE_USER $CLAUDE_HOME_DIR/.npm
chmod 666 ${promptFile} 2>/dev/null || true
chmod 644 ${envFile} 2>/dev/null || true
chmod o+rx /root/node /root/node/current /root/node/current/bin /root/node/current/lib 2>/dev/null || true
chmod o+rx /root/node/current/bin/* 2>/dev/null || true
chmod o+rx $(dirname $CLAUDE_BIN_PATH) $CLAUDE_BIN_PATH 2>/dev/null || true
chown -R $CLAUDE_USER:$CLAUDE_USER /root/.npm-global 2>/dev/null || chmod -R o+rwx /root/.npm-global 2>/dev/null || true
chmod -R o+rwx /root/.npm-cache 2>/dev/null || true

# Create output file + write runner script
touch ${outputFile}
chmod 666 ${outputFile}
echo '${runnerB64}' | base64 -d > ${runnerScript}
chmod 755 ${runnerScript}

# Start Claude CLI in background
nohup su -s /bin/bash $CLAUDE_USER -c "bash ${runnerScript}" > /dev/null 2>&1 &
echo "___CLAUDE_BG_PID=$!"
echo "CLAUDE_STARTED"
`;

  // Sanity check: verify exec works on this workspace
  const sanity = await execOnWorkspace(opts.workspaceId, 'echo EXEC_OK', { timeout: 15_000 });
  console.log(`[claude-cli] Sanity check: output="${sanity.output.trim()}", exitCode=${sanity.exitCode}`);

  // exec() breaks with multi-line commands — base64-encode the whole script
  const startCmdB64 = Buffer.from(startCmd).toString("base64");
  const execCmd = `echo ${startCmdB64} | base64 -d | sh`;

  console.log(`[claude-cli] Starting CLI for workspace ${opts.workspaceId}, projectDir=${projectDirName}`);
  console.log(`[claude-cli] startCmd length=${startCmd.length}, b64 length=${startCmdB64.length}, execCmd length=${execCmd.length}`);

  const result = await execOnWorkspace(
    opts.workspaceId,
    execCmd,
    { timeout: 60_000 }
  );

  console.log("[claude-cli] startClaudeCli output:", JSON.stringify(result.output.slice(0, 800)));
  console.log("[claude-cli] startClaudeCli stderr:", JSON.stringify((result.stderr ?? "").slice(0, 500)));
  console.log("[claude-cli] startClaudeCli exitCode:", result.exitCode);

  if (result.output.includes("ERROR:")) {
    throw new Error("CLI setup failed: " + result.output.slice(0, 500));
  }

  if (!result.output.includes("CLAUDE_STARTED")) {
    throw new Error("CLI did not start. Output: " + result.output.slice(0, 500));
  }

  const pidMatch = result.output.match(/___CLAUDE_BG_PID=(\d+)/);
  const backgroundPid = pidMatch?.[1];

  console.log(`[claude-cli] CLI started, pid=${backgroundPid}, outputFile=${outputFile}`);

  return {
    outputFile,
    backgroundPid,
  };
}

// ── Output Polling ───────────────────────────────────────────────────

/**
 * Poll the JSONL output file from byte offset.
 * Also checks if the background process is still alive.
 * Matches Django's polling approach with __MAGS_POLL_BOUNDARY__.
 */
export async function pollOutput(
  workspaceId: string,
  outputFile: string,
  offset: number,
  backgroundPid?: string
): Promise<PollResult> {
  const pidCheck = backgroundPid
    ? `ALIVE=$(kill -0 ${backgroundPid} 2>/dev/null && echo "yes" || echo "no")`
    : `ALIVE="unknown"`;

  const cmd = `
CURSIZE=$(wc -c < "${outputFile}" 2>/dev/null || echo 0)
NEWBYTES=$((CURSIZE - ${offset}))
if [ "$NEWBYTES" -gt 0 ]; then
    tail -c +${offset + 1} "${outputFile}" | head -c $NEWBYTES
fi
${pidCheck}
printf '\\n__MAGS_POLL_BOUNDARY__\\nSIZE=%s ALIVE=%s\\n' "$CURSIZE" "$ALIVE"
`.trim();

  // exec() breaks with multi-line commands — base64-encode
  const cmdB64 = Buffer.from(cmd).toString("base64");
  const result = await execOnWorkspace(workspaceId, `echo ${cmdB64} | base64 -d | sh`, { timeout: 15_000 });
  const output = result.output;

  // Split on boundary
  const boundaryIdx = output.indexOf("__MAGS_POLL_BOUNDARY__");
  let data = "";
  let newOffset = offset;
  let alive = true;

  if (boundaryIdx >= 0) {
    data = output.slice(0, boundaryIdx).replace(/\n$/, "");
    const meta = output.slice(boundaryIdx);
    const sizeMatch = meta.match(/SIZE=(\d+)/);
    const aliveMatch = meta.match(/ALIVE=(\w+)/);
    if (sizeMatch?.[1]) newOffset = parseInt(sizeMatch[1], 10);
    if (aliveMatch?.[1]) alive = aliveMatch[1] === "yes" || aliveMatch[1] === "unknown";
  } else {
    // Fallback: no boundary found, use raw output
    data = output;
    newOffset = offset + Buffer.byteLength(data, "utf8");
  }

  return { data, newOffset, alive };
}

// ── JSONL Parser ──────────────────────────────────────────────────────

export type ClaudeJsonEvent =
  | { type: "system"; subtype: "init"; session_id: string }
  | { type: "assistant"; message: { content: Array<{ type: string; text?: string; name?: string; input?: Record<string, unknown> }> } }
  | { type: "user"; message: { content: Array<{ type: string; content?: string }> } }
  | { type: "result"; subtype: string; result?: string }
  | { type: "error"; error: string };

/**
 * Parse JSONL stream data into structured events.
 * Handles partial lines and concatenated JSON objects.
 */
export function parseJsonlEvents(data: string): ClaudeJsonEvent[] {
  const events: ClaudeJsonEvent[] = [];

  for (const line of data.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    // Skip non-JSON lines (e.g. ___CLAUDE_EXIT_CODE=0)
    if (!trimmed.startsWith("{")) continue;

    try {
      const parsed = JSON.parse(trimmed);
      events.push(parsed as ClaudeJsonEvent);
    } catch {
      // partial line or non-JSON — skip
    }
  }

  return events;
}

/**
 * Extract session_id from the init event in JSONL output.
 */
export function extractSessionId(events: ClaudeJsonEvent[]): string | null {
  for (const e of events) {
    if (
      e.type === "system" &&
      (e as { type: "system"; subtype: string; session_id: string }).subtype === "init"
    ) {
      return (e as { type: "system"; subtype: string; session_id: string }).session_id ?? null;
    }
  }
  return null;
}

/**
 * Check if the JSONL stream signals completion.
 */
export function isStreamComplete(events: ClaudeJsonEvent[]): boolean {
  return events.some((e) => e.type === "result" || e.type === "error");
}

/**
 * Detect a stale session error.
 */
export function isStaleSession(events: ClaudeJsonEvent[]): boolean {
  return events.some(
    (e) =>
      e.type === "error" &&
      (e as { type: "error"; error: string }).error?.includes(
        "No conversation found with session ID"
      )
  );
}

/**
 * Check raw output for exit code marker written by runner script.
 */
export function extractExitCode(allOutput: string): number | null {
  const match = allOutput.match(/___CLAUDE_EXIT_CODE=(\d+)/);
  return match?.[1] ? parseInt(match[1], 10) : null;
}

/**
 * Check raw output for auth errors.
 */
export function hasAuthError(output: string): boolean {
  const markers = [
    "oauth token has expired",
    "authentication_error",
    "please run /login",
    "not logged in",
  ];
  const lower = output.toLowerCase();
  return markers.some((m) => lower.includes(m));
}
