/**
 * Claude Code CLI runner
 *
 * Manages Claude credentials in DB, copies them to Mags VMs,
 * and runs the Claude CLI with streaming JSONL output.
 *
 * Flow:
 *  1. Load credentials from DB
 *  2. Write prompt file, env file, runner script to VM via base64
 *  3. Inject credentials to /root/.claude/ + /home/claudeuser/.claude/
 *  4. Launch CLI as claudeuser via su (Claude refuses --dangerously-skip-permissions as root)
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
 * Copy user's Claude credentials into the VM at /root/.claude/.credentials.json.
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

  // Log credential details for debugging (never log the actual token)
  try {
    const parsed = JSON.parse(credentials);
    console.log(`[claude-cli] Injecting credentials for user ${userId}, len=${credentials.length}, hasAccessToken=${!!parsed.accessToken}, hasRefreshToken=${!!parsed.refreshToken}, expiresAt=${parsed.expiresAt ?? "n/a"}`);
  } catch {
    console.log("[claude-cli] Injecting credentials, length:", credentials.length, "(not valid JSON!)");
  }

  const b64 = Buffer.from(credentials).toString("base64");

  const script = `
mkdir -p /root/.claude
echo '${b64}' | base64 -d > /root/.claude/.credentials.json
chmod 600 /root/.claude/.credentials.json
# Also copy to claudeuser for CLI execution (Claude refuses --dangerously-skip-permissions as root)
id claudeuser >/dev/null 2>&1 || (adduser -D -s /bin/bash claudeuser 2>/dev/null || useradd -m -s /bin/bash claudeuser 2>/dev/null || true)
mkdir -p /home/claudeuser/.claude
cp /root/.claude/.credentials.json /home/claudeuser/.claude/.credentials.json
chown -R claudeuser:claudeuser /home/claudeuser/.claude
ls -la /root/.claude/.credentials.json /home/claudeuser/.claude/.credentials.json 2>&1
echo "credentials_injected"
`.trim();

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
      `export HOME=/root; export PATH=/root/node/current/bin:/root/.npm-global/bin:$PATH; ${CLAUDE_BIN} --version 2>&1 || echo "AUTH_FAILED"`,
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
 *  5. Ensure project dir exists
 *  6. Launch via nohup as root
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

  // Runner script content — runs as claudeuser (Claude CLI refuses --dangerously-skip-permissions as root)
  // The forwarder loop reads new bytes from the output file every 2s and POSTs them
  // to the server callback API, replacing server-side SSH polling.
  // NOTE: Logs written to project dir (JFS-persistent), NOT /tmp (overlay — wiped on sleep).
  const runnerContent = `#!/bin/bash
export HOME=/home/claudeuser
export PATH=/root/node/current/bin:/root/.npm-global/bin:\$PATH
export npm_config_prefix=/root/.npm-global
export NPM_CONFIG_PREFIX=/root/.npm-global
export NPM_CONFIG_CACHE=/root/.npm-cache
export npm_config_cache=/root/.npm-cache
source ${envFile}
cd ${WORKING_DIR}/${projectDirName}

# Log to project dir (persistent JFS), not /tmp (ephemeral overlay)
LOGDIR=${WORKING_DIR}/${projectDirName}/.lfg
mkdir -p \$LOGDIR

# Log env vars for debugging
echo "=== FORWARDER ===" > \$LOGDIR/forwarder_debug.log
echo "LFG_API_URL=\${LFG_API_URL}" >> \$LOGDIR/forwarder_debug.log
echo "LFG_TICKET_ID=\${LFG_TICKET_ID}" >> \$LOGDIR/forwarder_debug.log
echo "LFG_API_KEY_LEN=\$(echo -n \\"\${LFG_API_KEY}\\" | wc -c)" >> \$LOGDIR/forwarder_debug.log

# Run CLI in background, still writes to local file for debugging
${CLAUDE_BIN} -p "$(cat ${promptFile})" ${claudeArgsStr} > ${outputFile} 2>&1 &
CLI_PID=\$!

# Forwarder loop: read new bytes from output file, POST to server
FLOG=\$LOGDIR/forwarder_loop.log
echo "=== Forwarder started at \$(date) ===" > \$FLOG
echo "API_URL=\${LFG_API_URL}" >> \$FLOG
echo "TICKET_ID=\${LFG_TICKET_ID}" >> \$FLOG
echo "API_KEY_LEN=\$(echo -n \\"\${LFG_API_KEY}\\" | wc -c)" >> \$FLOG

OFFSET=0
LOOP_N=0
PAYLOAD_FILE=\$LOGDIR/curl_payload.json
while kill -0 \$CLI_PID 2>/dev/null; do
  sleep 2
  LOOP_N=\$((\$LOOP_N+1))
  CURSIZE=\$(wc -c < ${outputFile} 2>/dev/null || echo 0)
  if [ "\$CURSIZE" -gt "\$OFFSET" ]; then
    BYTES=\$((\$CURSIZE-\$OFFSET))
    CHUNK=\$(tail -c +\$((\$OFFSET+1)) ${outputFile} | head -c \$BYTES | base64 | tr -d '\\n')
    OFFSET=\$CURSIZE
    echo "[\$(date)] loop=\$LOOP_N bytes=\$BYTES offset=\$OFFSET" >> \$FLOG
    printf '{"ticket_id":"%s","data":"%s"}' "\${LFG_TICKET_ID}" "\$CHUNK" > \$PAYLOAD_FILE
    RESP=\$(curl -s -w "\\nHTTP_CODE=%{http_code}" -X POST "\${LFG_API_URL}/api/v1/cli/output/" \\
      -H "X-CLI-API-Key: \${LFG_API_KEY}" \\
      -H "Content-Type: application/json" \\
      -H "ngrok-skip-browser-warning: true" \\
      -d @\$PAYLOAD_FILE 2>&1) || true
    echo "  resp: \$RESP" >> \$FLOG
  fi
done

wait \$CLI_PID
CLAUDE_EXIT=\$?
echo "[\$(date)] CLI exited with code=\$CLAUDE_EXIT" >> \$FLOG

# Send any remaining output + done signal
CURSIZE=\$(wc -c < ${outputFile} 2>/dev/null || echo 0)
if [ "\$CURSIZE" -gt "\$OFFSET" ]; then
  BYTES=\$((\$CURSIZE-\$OFFSET))
  CHUNK=\$(tail -c +\$((\$OFFSET+1)) ${outputFile} | head -c \$BYTES | base64 | tr -d '\\n')
  echo "[\$(date)] final chunk bytes=\$BYTES done=true exit=\$CLAUDE_EXIT" >> \$FLOG
  printf '{"ticket_id":"%s","data":"%s","done":true,"exit_code":%d}' "\${LFG_TICKET_ID}" "\$CHUNK" \$CLAUDE_EXIT > \$PAYLOAD_FILE
  RESP=\$(curl -s -w "\\nHTTP_CODE=%{http_code}" -X POST "\${LFG_API_URL}/api/v1/cli/output/" \\
    -H "X-CLI-API-Key: \${LFG_API_KEY}" \\
    -H "Content-Type: application/json" \\
    -H "ngrok-skip-browser-warning: true" \\
    -d @\$PAYLOAD_FILE 2>&1) || true
  echo "  resp: \$RESP" >> \$FLOG
else
  echo "[\$(date)] no remaining data, sending done=true exit=\$CLAUDE_EXIT" >> \$FLOG
  printf '{"ticket_id":"%s","data":"","done":true,"exit_code":%d}' "\${LFG_TICKET_ID}" \$CLAUDE_EXIT > \$PAYLOAD_FILE
  RESP=\$(curl -s -w "\\nHTTP_CODE=%{http_code}" -X POST "\${LFG_API_URL}/api/v1/cli/output/" \\
    -H "X-CLI-API-Key: \${LFG_API_KEY}" \\
    -H "Content-Type: application/json" \\
    -H "ngrok-skip-browser-warning: true" \\
    -d @\$PAYLOAD_FILE 2>&1) || true
  echo "  resp: \$RESP" >> \$FLOG
fi
echo "=== Forwarder finished at \$(date) ===" >> \$FLOG

echo "" >> ${outputFile}
echo "___CLAUDE_EXIT_CODE=\$CLAUDE_EXIT" >> ${outputFile}
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
# Inject credentials from DB — root copy + claudeuser copy
mkdir -p /root/.claude
echo '${credsB64}' | base64 -d > /root/.claude/.credentials.json
id claudeuser >/dev/null 2>&1 || (adduser -D -s /bin/bash claudeuser 2>/dev/null || useradd -m -s /bin/bash claudeuser 2>/dev/null || true)
mkdir -p /home/claudeuser/.claude
cp /root/.claude/.credentials.json /home/claudeuser/.claude/.credentials.json
chown -R claudeuser:claudeuser /home/claudeuser/.claude
`;
  }

  // Single combined command: write all files + launch CLI as claudeuser
  const startCmd = `export HOME=/root
export PATH=/root/node/current/bin:/root/.npm-global/bin:\$PATH

# Write prompt and env files via base64
echo '${promptB64}' | base64 -d > ${promptFile}
echo '${envB64}' | base64 -d > ${envFile}
${dbCredsInject}
# Verify credentials exist
if [ ! -f /home/claudeuser/.claude/.credentials.json ]; then
    echo "ERROR: No credentials found for claudeuser"
    ls -la /home/claudeuser/.claude/ 2>&1 || echo "No .claude directory"
    exit 1
fi

# Verify claude binary exists
CLAUDE_BIN_PATH="${CLAUDE_BIN}"
if [ ! -x "\$CLAUDE_BIN_PATH" ]; then
    CLAUDE_BIN_PATH=\$(which claude 2>/dev/null || echo "${CLAUDE_BIN}")
    if [ ! -x "\$CLAUDE_BIN_PATH" ]; then
        echo "ERROR: Claude binary not found at ${CLAUDE_BIN}"
        exit 1
    fi
fi

# Ensure project dir exists and claudeuser can write to it
PROJ_DIR="${WORKING_DIR}/${projectDirName}"
mkdir -p "\$PROJ_DIR"
chown -R claudeuser:claudeuser "\$PROJ_DIR"
git config --global --add safe.directory "\$PROJ_DIR" 2>/dev/null || true

# Create output file + write runner script
touch ${outputFile}
chmod 666 ${outputFile}
echo '${runnerB64}' | base64 -d > ${runnerScript}
chmod 755 ${runnerScript}

# Make prompt/env files readable by claudeuser
chmod 644 ${promptFile} ${envFile}

# Start Claude CLI in background as claudeuser
nohup su -s /bin/bash claudeuser -c "bash ${runnerScript}" > /dev/null 2>&1 &
echo "___CLAUDE_BG_PID=\$!"
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

// ── Pre-flight Check ──────────────────────────────────────────────────

/**
 * Pre-flight: ensure credentials exist in DB and inject them into the VM.
 * Does NOT run `claude -p` (too slow, VM wake-up adds 10-30s).
 * Just verifies DB has credentials and injects them.
 */
/**
 * VM-first preflight check:
 *  1. Test if Claude CLI works on the VM (`claude -p "hello"`)
 *  2. If yes → continue (VM credentials are valid)
 *  3. If no → pull token from DB, inject into VM, test again
 *  4. If still no → flag user to reconnect
 */
export async function preflightCheck(
  workspaceId: string,
  userId: string
): Promise<{ ok: boolean; needsReconnect: boolean; error?: string }> {
  // Lightweight check: just ensure credentials exist on the VM.
  // Do NOT run `claude -p` — it takes 30-60s and often times out via execOnWorkspace.
  // If creds are bad, the actual ticket run will surface auth errors.

  console.log(`[claude-cli] preflight: checking credentials on VM ${workspaceId}...`);

  // Step 1: Check if creds file already exists on the VM
  try {
    const check = await execOnWorkspace(workspaceId,
      `if [ -f /root/.claude/.credentials.json ] && [ -s /root/.claude/.credentials.json ]; then echo CREDS_OK; else echo NO_CREDS; fi`,
      { timeout: 15_000 }
    );
    if (check.output.includes("CREDS_OK")) {
      console.log(`[claude-cli] preflight: credentials already on VM, proceeding`);
      return { ok: true, needsReconnect: false };
    }
  } catch (err) {
    console.log(`[claude-cli] preflight: VM check failed: ${err}`);
  }

  // Step 2: No creds on VM — inject from DB
  console.log(`[claude-cli] preflight: no credentials on VM, injecting from DB...`);
  const injected = await injectCredentials(workspaceId, userId);
  if (!injected) {
    return { ok: false, needsReconnect: true, error: "No valid Claude credentials in database. Please reconnect Claude Code in Settings." };
  }

  console.log(`[claude-cli] preflight: credentials injected, proceeding`);
  return { ok: true, needsReconnect: false };
}

// ── Lightweight Chat Runner ──────────────────────────────────────────

/**
 * Start Claude CLI for a chat message (lightweight — no user creation).
 * Assumes the VM is already set up from the initial ticket build.
 * Only writes prompt/env files and launches the CLI.
 */
export async function startClaudeCliChat(
  opts: ClaudeRunOptions
): Promise<ClaudeRunResult> {
  const ts = Date.now();
  const outputFile = opts.outputFile ?? `/tmp/claude_output_${ts}.jsonl`;
  const promptFile = `/tmp/claude_prompt_${ts}.txt`;
  const envFile = `/tmp/claude_env_${ts}.sh`;
  const runnerScript = `/tmp/claude_runner_${ts}.sh`;
  const maxTurns = opts.maxTurns ?? DEFAULT_MAX_TURNS;

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
  const projectDirName = opts.projectDir.replace(/^\/root\//, "").replace(/^\//, "");

  const envExports = Object.entries(opts.envVars ?? {})
    .map(([k, v]) => `export ${k}="${v}"`)
    .join("\n");

  // Runner script with push-based forwarder (same pattern as startClaudeCli)
  const runnerContent = `#!/bin/bash
export HOME=/home/claudeuser
export PATH=/root/node/current/bin:/root/.npm-global/bin:\$PATH
export npm_config_prefix=/root/.npm-global
export NPM_CONFIG_PREFIX=/root/.npm-global
export NPM_CONFIG_CACHE=/root/.npm-cache
export npm_config_cache=/root/.npm-cache
source ${envFile}
cd ${WORKING_DIR}/${projectDirName}

# Run CLI in background, still writes to local file for debugging
${CLAUDE_BIN} -p "$(cat ${promptFile})" ${claudeArgsStr} > ${outputFile} 2>&1 &
CLI_PID=\$!

# Forwarder loop: read new bytes from output file, POST to server
OFFSET=0
while kill -0 \$CLI_PID 2>/dev/null; do
  sleep 2
  CURSIZE=\$(wc -c < ${outputFile} 2>/dev/null || echo 0)
  if [ "\$CURSIZE" -gt "\$OFFSET" ]; then
    CHUNK=\$(tail -c +\$((\$OFFSET+1)) ${outputFile} | head -c \$((\$CURSIZE-\$OFFSET)) | base64 | tr -d '\\n')
    OFFSET=\$CURSIZE
    curl -s -X POST "\${LFG_API_URL}/api/v1/cli/output/" \\
      -H "X-CLI-API-Key: \${LFG_API_KEY}" \\
      -H "Content-Type: application/json" \\
      -H "ngrok-skip-browser-warning: true" \\
      -d "{\\"ticket_id\\":\\"\${LFG_TICKET_ID}\\",\\"data\\":\\"\$CHUNK\\"}" || true
  fi
done

wait \$CLI_PID
CLAUDE_EXIT=\$?

# Send any remaining output + done signal
CURSIZE=\$(wc -c < ${outputFile} 2>/dev/null || echo 0)
if [ "\$CURSIZE" -gt "\$OFFSET" ]; then
  CHUNK=\$(tail -c +\$((\$OFFSET+1)) ${outputFile} | head -c \$((\$CURSIZE-\$OFFSET)) | base64 | tr -d '\\n')
  curl -s -X POST "\${LFG_API_URL}/api/v1/cli/output/" \\
    -H "X-CLI-API-Key: \${LFG_API_KEY}" \\
    -H "Content-Type: application/json" \\
    -H "ngrok-skip-browser-warning: true" \\
    -d "{\\"ticket_id\\":\\"\${LFG_TICKET_ID}\\",\\"data\\":\\"\$CHUNK\\",\\"done\\":true,\\"exit_code\\":\$CLAUDE_EXIT}" || true
else
  curl -s -X POST "\${LFG_API_URL}/api/v1/cli/output/" \\
    -H "X-CLI-API-Key: \${LFG_API_KEY}" \\
    -H "Content-Type: application/json" \\
    -H "ngrok-skip-browser-warning: true" \\
    -d "{\\"ticket_id\\":\\"\${LFG_TICKET_ID}\\",\\"data\\":\\"\\",\\"done\\":true,\\"exit_code\\":\$CLAUDE_EXIT}" || true
fi

echo "" >> ${outputFile}
echo "___CLAUDE_EXIT_CODE=\$CLAUDE_EXIT" >> ${outputFile}
`;

  const promptB64 = Buffer.from(opts.prompt).toString("base64");
  const envB64 = Buffer.from(envExports).toString("base64");
  const runnerB64 = Buffer.from(runnerContent).toString("base64");

  // Inject credentials from DB (VM overlay may have reset)
  let dbCredsInject = "";
  const creds = await loadCredentials(opts.userId);
  if (creds) {
    const credsB64 = Buffer.from(creds).toString("base64");
    dbCredsInject = `
# Inject credentials from DB — root copy + claudeuser copy
mkdir -p /root/.claude
echo '${credsB64}' | base64 -d > /root/.claude/.credentials.json
id claudeuser >/dev/null 2>&1 || (adduser -D -s /bin/bash claudeuser 2>/dev/null || useradd -m -s /bin/bash claudeuser 2>/dev/null || true)
mkdir -p /home/claudeuser/.claude
cp /root/.claude/.credentials.json /home/claudeuser/.claude/.credentials.json
chown -R claudeuser:claudeuser /home/claudeuser/.claude
`;
  }

  const startCmd = `export HOME=/root
export PATH=/root/node/current/bin:/root/.npm-global/bin:\$PATH
echo '${promptB64}' | base64 -d > ${promptFile}
echo '${envB64}' | base64 -d > ${envFile}
echo '${runnerB64}' | base64 -d > ${runnerScript}
chmod 755 ${runnerScript}
${dbCredsInject}
touch ${outputFile}
chmod 666 ${outputFile}
chmod 644 ${promptFile} ${envFile}
# Ensure project dir writable by claudeuser
chown -R claudeuser:claudeuser ${WORKING_DIR}/${projectDirName} 2>/dev/null || true
nohup su -s /bin/bash claudeuser -c "bash ${runnerScript}" > /dev/null 2>&1 &
echo "___CLAUDE_BG_PID=\$!"
echo "CLAUDE_STARTED"
`;

  const startCmdB64 = Buffer.from(startCmd).toString("base64");
  const execCmd = `echo ${startCmdB64} | base64 -d | sh`;

  console.log(`[claude-cli] Starting chat CLI for workspace ${opts.workspaceId} (lightweight)`);
  console.log(`[claude-cli] chatCmd length=${startCmd.length}, b64 length=${startCmdB64.length}`);

  const result = await execOnWorkspace(
    opts.workspaceId,
    execCmd,
    { timeout: 30_000 }
  );

  console.log("[claude-cli] startClaudeCliChat output:", JSON.stringify(result.output.slice(0, 400)));
  if (result.output.includes("ERROR:")) {
    throw new Error("Chat CLI setup failed: " + result.output.slice(0, 500));
  }
  if (!result.output.includes("CLAUDE_STARTED")) {
    throw new Error("Chat CLI did not start. Output: " + result.output.slice(0, 500));
  }

  const pidMatch = result.output.match(/___CLAUDE_BG_PID=(\d+)/);
  const backgroundPid = pidMatch?.[1];
  console.log(`[claude-cli] Chat CLI started, pid=${backgroundPid}, outputFile=${outputFile}`);

  return { outputFile, backgroundPid };
}

/**
 * Save credentials back to DB from VM after a successful run.
 * Checks claudeuser's home first (CLI runs as claudeuser and may refresh tokens there),
 * then falls back to /root/.claude/.credentials.json.
 */
export async function saveCredentialsFromVm(
  workspaceId: string,
  userId: string
): Promise<boolean> {
  try {
    const result = await execOnWorkspace(
      workspaceId,
      `cat /home/claudeuser/.claude/.credentials.json 2>/dev/null || cat /root/.claude/.credentials.json 2>/dev/null || echo "__NO_CREDS__"`,
      { timeout: 15_000 }
    );
    const output = result.output.trim();
    if (output.includes("__NO_CREDS__") || !output.startsWith("{")) {
      console.log("[claude-cli] No credentials found on VM to save back");
      return false;
    }
    // Validate it's valid JSON
    JSON.parse(output);
    await saveCredentials(userId, output);
    console.log(`[claude-cli] Saved credentials back to DB for user ${userId}, len=${output.length}`);
    return true;
  } catch (err) {
    console.warn("[claude-cli] Failed to save credentials from VM:", (err as Error).message?.slice(0, 200));
    return false;
  }
}

/**
 * Mark Claude Code as disconnected in the user's profile.
 */
export async function markClaudeDisconnected(userId: string): Promise<void> {
  await db
    .update(profiles)
    .set({
      claudeCodeAuthenticated: false,
      updatedAt: new Date(),
    })
    .where(eq(profiles.userId, userId));
  console.log(`[claude-cli] Marked Claude Code as disconnected for user ${userId}`);
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
