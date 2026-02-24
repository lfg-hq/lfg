/**
 * Claude Code CLI Authentication Service
 *
 * Ports the Django factory/claude_code_utils.py auth flow to TypeScript.
 *
 * Flow:
 *  1. startClaudeAuth(workspaceName)
 *     - Installs Node, Claude CLI, expect in a Mags VM
 *     - Runs an expect script that launches `claude` and captures the OAuth URL
 *     - Returns { status: 'pending', oauthUrl } or { status: 'already_authenticated' }
 *
 *  2. submitAuthCode(workspaceName, code)
 *     - Writes the code to /tmp/claude_code.txt inside the VM
 *     - The expect script picks it up and completes the OAuth flow
 *     - Polls /tmp/claude_status.txt until SUCCESS
 *
 *  3. checkAuthStatus(workspaceName)
 *     - Checks ~/.claude/.credentials.json exists and has accessToken
 *     - Optionally verifies by running claude -p "reply just the word Hello"
 *
 *  4. saveCredentialsToDB(workspaceName, userId)
 *     - Reads ~/.claude/.credentials.json from VM, stores in profiles table
 *
 *  5. loadCredentialsFromDB(userId, workspaceName)
 *     - Reads credentials from profiles table, writes to VM
 */

import { execOnWorkspace } from "./mags.ts";
import { db } from "../config/db.ts";
import { profiles } from "../db/schema/users.ts";
import { eq } from "drizzle-orm";

const NODE_VERSION = "20.18.0";
const NODE_DISTRO = "linux-x64";

/**
 * Shell script that provisions a fresh VM with Node + Claude CLI + expect.
 * NOTE: Run via execOnWorkspace() on a VM already created by client.new().
 * The VM stays alive via client.new() — no infinite loop needed here.
 * This script should complete and exit cleanly.
 */
export const CLAUDE_AUTH_SETUP_SCRIPT = `#!/bin/sh
set -eux

# Install system packages
apk update && apk add --no-cache curl xz git expect bash openssh-client

# Ensure PTYs are available (needed by expect for Claude CLI auth)
mkdir -p /dev/pts 2>/dev/null || true
mount -t devpts devpts /dev/pts 2>/dev/null || true

# Install Node.js ${NODE_VERSION}
cd /root && mkdir -p node && cd node
if [ ! -d node-v${NODE_VERSION}-${NODE_DISTRO} ]; then
    curl -fsSL https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-${NODE_DISTRO}.tar.xz -o node.tar.xz
    tar -xf node.tar.xz && rm node.tar.xz
    ln -sfn node-v${NODE_VERSION}-${NODE_DISTRO} current
fi
export PATH=/root/node/current/bin:\$PATH
mkdir -p /root/.npm-global /root/.npm-cache
npm config set prefix /root/.npm-global
npm config set cache /root/.npm-cache

# Install Claude CLI
npm install -g @anthropic-ai/claude-code

# Create non-root user for Claude --dangerously-skip-permissions
adduser -D -h /home/claudeuser -s /bin/bash claudeuser 2>/dev/null || true

echo "CLAUDE_AUTH_SETUP_COMPLETE"
`;

// ── Auth status check ─────────────────────────────────────────────────────

export interface AuthStatusResult {
  authenticated: boolean;
  message: string;
  sandboxTimeout?: boolean;
  tokenExpired?: boolean;
}

/**
 * Check if Claude Code is authenticated in the VM.
 * First does a cheap file check, then optionally runs `claude -p "..."` to verify.
 */
export async function checkAuthStatus(workspaceName: string): Promise<AuthStatusResult> {
  // Quick credentials check
  let quickOut: string;
  try {
    const r = await execOnWorkspace(workspaceName,
      `if [ -f ~/.claude/.credentials.json ] && [ -s ~/.claude/.credentials.json ]; then echo CREDS_EXIST; grep -q "accessToken" ~/.claude/.credentials.json 2>/dev/null && echo HAS_TOKEN; else echo NO_CREDS; fi`,
      { timeout: 20_000 }
    );
    quickOut = r.output;
  } catch {
    return { authenticated: false, message: "Sandbox unresponsive", sandboxTimeout: true };
  }

  if (quickOut.includes("NO_CREDS")) {
    return { authenticated: false, message: "No credentials found" };
  }

  if (!quickOut.includes("HAS_TOKEN")) {
    return { authenticated: false, message: "Credentials incomplete" };
  }

  // Verify token by running a quick claude prompt
  try {
    const r = await execOnWorkspace(workspaceName,
      `[ -f /etc/profile ] && . /etc/profile; [ -f ~/.profile ] && . ~/.profile; export PATH=/root/node/current/bin:/root/.npm-global/bin:$PATH; cd ~; timeout 12 claude -p "reply just the word Hello" 2>&1 | head -20`,
      { timeout: 20_000 }
    );
    const out = r.output.toLowerCase();

    if (r.exitCode === 0 && out.includes("hello")) {
      return { authenticated: true, message: "Claude Code is authenticated" };
    }

    // Timeout or killed — VM is slow but creds exist, assume authenticated
    if (out.includes("killed") || out.includes("timed out") || [137, 124].includes(r.exitCode)) {
      return { authenticated: true, message: "Credentials found (verification skipped due to timeout)" };
    }

    // Explicit auth errors
    if (out.includes("not logged in") || out.includes("authenticate") ||
        out.includes("oauth") || out.includes("expired") || out.includes("please run /login")) {
      // Remove stale credentials
      await execOnWorkspace(workspaceName, "rm -f ~/.claude/.credentials.json", { timeout: 10_000 }).catch(() => {});
      return { authenticated: false, message: "Token expired — please reconnect", tokenExpired: true };
    }

    // Non-zero but no explicit auth error — assume ok (transient issue)
    return { authenticated: true, message: "Credentials found (verification inconclusive)" };
  } catch {
    return { authenticated: true, message: "Credentials found (could not verify)" };
  }
}

// ── OAuth flow ────────────────────────────────────────────────────────────

export interface StartAuthResult {
  status: "already_authenticated" | "pending" | "error";
  oauthUrl?: string;
  message?: string;
  error?: string;
}

/**
 * Start the Claude OAuth flow on an existing VM.
 * Sets up expect script, runs it in background, polls for the OAuth URL.
 */
export async function startClaudeAuth(workspaceName: string): Promise<StartAuthResult> {
  // Check if already authenticated
  const authStatus = await checkAuthStatus(workspaceName);
  if (authStatus.authenticated) {
    return { status: "already_authenticated", message: "Claude Code is already authenticated" };
  }

  // Pre-compute base64 of wrapper + expect scripts.
  // Using template literals: $var without {} is just literal text in JS — safe for Tcl variables.
  // This avoids heredoc syntax which breaks over SSH exec.
  const wrapperScript = `#!/bin/sh
[ -f /etc/profile ] && . /etc/profile
[ -f ~/.profile ] && . ~/.profile
[ -f ~/.bashrc ] && . ~/.bashrc
export PATH=/root/node/current/bin:/root/.npm-global/bin:$PATH
export COLUMNS=2000
export TERM=dumb
exec claude "$@"
`;

  // Note: $CR, $i, $url, $f, $code, $expect_out are Tcl variables — they're literal in JS template literals
  // because JS only interpolates ${...} (with braces), not $name.
  const expectScript = `log_user 1
set timeout 300
set CR [format %c 13]

spawn /tmp/claude_wrapper.sh

expect {
    -re {\\.\\.\\.} {
        exp_continue
    }
    -re {trust the files|Yes, proceed|trust.*folder} {
        after 500
        send $CR
        exp_continue
    }
    -re {looks best|text style|style preference|output format|terminal} {
        after 500
        send $CR
        exp_continue
    }
    -re {Select an account|authenticate|login method|choose.*account|sign in} {
        after 500
        send $CR
        exp_continue
    }
    -re {(https://claude\\.ai/oauth[!-~]+)} {
        set url $expect_out(1,string)
        set f [open "/tmp/claude_url.txt" w]
        puts $f $url
        close $f
        exp_continue
    }
    -re {[Pp]aste.*code|[Ee]nter.*code|authorization code|[Cc]ode:} {
        puts "WAITING_FOR_CODE"
        for {set i 0} {$i < 300} {incr i} {
            if {[file exists "/tmp/claude_code.txt"]} {
                set f [open "/tmp/claude_code.txt" r]
                set code [string trim [read $f]]
                close $f
                file delete "/tmp/claude_code.txt"
                send -- "$code"
                after 500
                send $CR
                break
            }
            after 1000
        }
        exp_continue
    }
    -re {Login successful|Logged in as|successfully authenticated} {
        set f [open "/tmp/claude_status.txt" w]
        puts $f "SUCCESS"
        close $f
        after 1000
        send $CR
        exp_continue
    }
    -re {What can I help|help you with|How can I|Tips:} {
        if {![file exists "/tmp/claude_status.txt"]} {
            set f [open "/tmp/claude_status.txt" w]
            puts $f "ALREADY_AUTH"
            close $f
        }
        after 500
        send "/exit"
        send $CR
    }
    -re {[Ee]rror|[Ii]nvalid|expired|failed} {
        set f [open "/tmp/claude_status.txt" w]
        puts $f "ERROR"
        close $f
    }
    timeout {
        if {![file exists "/tmp/claude_status.txt"]} {
            set f [open "/tmp/claude_status.txt" w]
            puts $f "TIMEOUT"
            close $f
        }
    }
}
expect eof
`;

  const wrapperB64 = Buffer.from(wrapperScript).toString("base64");
  const expectB64 = Buffer.from(expectScript).toString("base64");

  // Setup: install expect, write wrapper + expect scripts via base64 (no heredocs over SSH)
  const setup = await execOnWorkspace(workspaceName,
    `[ -f /etc/profile ] && . /etc/profile; [ -f ~/.profile ] && . ~/.profile; [ -f ~/.bashrc ] && . ~/.bashrc; ` +
    `rm -f /tmp/claude_url.txt /tmp/claude_code.txt /tmp/claude_status.txt /tmp/claude_auth.exp; ` +
    `mkdir -p /dev/pts 2>/dev/null || true; ` +
    `mount -t devpts devpts /dev/pts 2>/dev/null || true; ` +
    `if ! command -v expect >/dev/null 2>&1; then apk add --no-cache expect >/dev/null 2>&1 || echo EXPECT_INSTALL_FAILED; fi; ` +
    `echo ${wrapperB64} | base64 -d > /tmp/claude_wrapper.sh && chmod +x /tmp/claude_wrapper.sh; ` +
    `echo ${expectB64} | base64 -d > /tmp/claude_auth.exp; ` +
    `echo SETUP_COMPLETE`,
    { timeout: 60_000 }
  );

  if (setup.output.includes("EXPECT_INSTALL_FAILED")) {
    return { status: "error", error: "Failed to install expect" };
  }
  if (!setup.output.includes("SETUP_COMPLETE")) {
    return { status: "error", error: `Setup failed: ${setup.output.slice(0, 200)}` };
  }

  // Start expect in background (single-line to avoid SSH exec newline issues)
  const bg = await execOnWorkspace(workspaceName,
    `[ -f /etc/profile ] && . /etc/profile; [ -f ~/.profile ] && . ~/.profile; export PATH=/root/node/current/bin:/root/.npm-global/bin:$PATH; nohup expect /tmp/claude_auth.exp > /tmp/claude_auth.log 2>&1 & echo "BG_PID=$!"`,
    { timeout: 30_000 }
  );

  if (!bg.output.includes("BG_PID=")) {
    return { status: "error", error: "Failed to start auth process" };
  }

  // Poll for URL (up to 90s, restart expect up to 3 times)
  let expectRestarts = 0;
  for (let i = 0; i < 90; i++) {
    await sleep(1000);

    const checkScript = `
if [ -f /tmp/claude_url.txt ]; then
    FILE_URL=$(cat /tmp/claude_url.txt)
    if [ \${#FILE_URL} -gt 100 ]; then
        echo URL_FOUND
        echo "$FILE_URL"
        exit 0
    else
        rm -f /tmp/claude_url.txt
    fi
fi
if [ -f /tmp/claude_status.txt ]; then
    echo STATUS_FOUND
    cat /tmp/claude_status.txt
    exit 0
fi
if [ -f /tmp/claude_auth.log ]; then
    URL=$(cat /tmp/claude_auth.log | tr -d '\n\r' | grep -oE 'https://claude[.]ai/oauth[A-Za-z0-9_.~:/?#@!$&()*+,;=%=-]+' | head -1)
    if [ -n "$URL" ] && [ \${#URL} -gt 100 ]; then
        echo "$URL" > /tmp/claude_url.txt
        echo URL_FOUND
        echo "$URL"
        exit 0
    fi
fi
echo WAITING
pgrep -x expect >/dev/null 2>&1 || echo NO_EXPECT_RUNNING
`;
    const check = await execOnWorkspace(workspaceName,
      b64script(checkScript),
      { timeout: 10_000 }
    ).catch(() => ({ output: "WAITING", exitCode: -1, stderr: "" }));

    if (check.output.includes("URL_FOUND")) {
      const lines = check.output.split("\n");
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith("https://claude.ai/oauth")) {
          return { status: "pending", oauthUrl: trimmed.replace(/[\x00-\x1f\x7f]/g, "") };
        }
      }
    }

    if (check.output.includes("STATUS_FOUND")) {
      if (check.output.includes("ALREADY_AUTH") || check.output.includes("SUCCESS")) {
        return { status: "already_authenticated", message: "Already authenticated" };
      }
      return { status: "error", error: "Authentication error" };
    }

    // Restart expect if it died
    if (check.output.includes("NO_EXPECT_RUNNING") && expectRestarts < 3) {
      expectRestarts++;
      await execOnWorkspace(workspaceName,
        `pkill -9 claude 2>/dev/null || true; pkill -9 expect 2>/dev/null || true; rm -f /tmp/claude_auth.log; sleep 2; [ -f /etc/profile ] && . /etc/profile; export PATH=/root/node/current/bin:/root/.npm-global/bin:$PATH; nohup expect /tmp/claude_auth.exp > /tmp/claude_auth.log 2>&1 & echo RESTARTED`,
        { timeout: 30_000 }
      ).catch(() => {});
      await sleep(3000);
    }
  }

  return { status: "error", error: "Timeout waiting for OAuth URL" };
}

// ── Submit code ───────────────────────────────────────────────────────────

export interface SubmitCodeResult {
  status: "success" | "error";
  message?: string;
  error?: string;
}

/**
 * Submit the OAuth code to the expect process running inside the VM.
 * Polls /tmp/claude_status.txt until SUCCESS (or timeout).
 */
export async function submitAuthCode(
  workspaceName: string,
  authCode: string
): Promise<SubmitCodeResult> {
  // Base64-encode the auth code to avoid shell quoting issues with special chars (#, =, _, etc.)
  const codeB64 = Buffer.from(authCode).toString("base64");
  const write = await execOnWorkspace(workspaceName,
    `echo ${codeB64} | base64 -d > /tmp/claude_code.txt && echo CODE_WRITTEN`,
    { timeout: 30_000 }
  );

  if (!write.output.includes("CODE_WRITTEN")) {
    return { status: "error", error: "Failed to write auth code" };
  }

  // Poll for completion
  for (let i = 0; i < 120; i++) {
    await sleep(1000);

    const check = await execOnWorkspace(workspaceName, `
if [ -f /tmp/claude_status.txt ]; then
    echo "STATUS_FOUND"
    cat /tmp/claude_status.txt
else
    echo "WAITING"
    pgrep -x expect >/dev/null 2>&1 && echo "EXPECT_RUNNING" || echo "EXPECT_DEAD"
fi
`, { timeout: 10_000 }).catch(() => ({ output: "WAITING", exitCode: -1, stderr: "" }));

    if (check.output.includes("STATUS_FOUND")) {
      if (check.output.includes("SUCCESS") || check.output.includes("ALREADY_AUTH")) {
        return { status: "success", message: "Authenticated successfully" };
      }
      if (check.output.includes("ERROR")) {
        return { status: "error", error: "Authentication failed — code may be invalid or expired" };
      }
      if (check.output.includes("TIMEOUT")) {
        return { status: "error", error: "Authentication timed out" };
      }
    }

    if (check.output.includes("EXPECT_DEAD")) {
      return { status: "error", error: "Authentication process died. Please start again." };
    }
  }

  return { status: "error", error: "Timeout waiting for authentication result" };
}

// ── Credential persistence ────────────────────────────────────────────────

/**
 * Read ~/.claude/.credentials.json from the VM and save it to the DB.
 */
export async function saveCredentialsToDB(
  workspaceName: string,
  userId: string
): Promise<boolean> {
  try {
    const r = await execOnWorkspace(workspaceName,
      "cat ~/.claude/.credentials.json 2>/dev/null",
      { timeout: 15_000 }
    );
    const creds = r.output.trim();
    if (!creds || r.exitCode !== 0) return false;

    // Validate JSON
    JSON.parse(creds);

    await db.update(profiles)
      .set({
        claudeCodeCredentials: creds,
        claudeCodeAuthenticated: true,
        claudeCodeCredentialsUpdatedAt: new Date(),
        updatedAt: new Date(),
      })
      .where(eq(profiles.userId, userId));

    return true;
  } catch {
    return false;
  }
}

/**
 * Write credentials from DB into the VM's ~/.claude/.credentials.json.
 */
export async function loadCredentialsFromDB(
  userId: string,
  workspaceName: string
): Promise<boolean> {
  try {
    const [row] = await db.select({ creds: profiles.claudeCodeCredentials })
      .from(profiles)
      .where(eq(profiles.userId, userId));

    if (!row?.creds) return false;

    const b64 = Buffer.from(row.creds).toString("base64");
    const r = await execOnWorkspace(workspaceName,
      `mkdir -p ~/.claude && echo ${b64} | base64 -d > ~/.claude/.credentials.json`,
      { timeout: 15_000 }
    );
    return r.exitCode === 0;
  } catch {
    return false;
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────

function sleep(ms: number) {
  return new Promise<void>((r) => setTimeout(r, ms));
}

/** Generate a unique workspace name for Claude auth sandboxes. */
export function generateAuthWorkspaceName(): string {
  return `claude-auth-${crypto.randomUUID().replace(/-/g, "").slice(0, 8)}`;
}

/**
 * Wrap a multi-line shell script as a single-line base64 exec command.
 * Avoids issues with newlines/heredocs over SSH exec.
 */
function b64script(script: string): string {
  return `echo ${Buffer.from(script).toString("base64")} | base64 -d | sh`;
}
