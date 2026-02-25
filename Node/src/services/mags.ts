/**
 * Mags VM service — wrapper around @magpiecloud/mags v1.8.11+
 *
 * Key SDK methods used:
 *  - client.new(name, opts)             → create persistent VM, polls until running
 *  - client.exec(nameOrId, cmd, opts)   → run command via SSH on existing VM (handles chroot)
 *  - client.findJob(nameOrId)           → find running/sleeping job by name or workspace ID
 *  - client.url(nameOrId, port)         → enable HTTP access and return proxy URL
 *  - client.stop(nameOrId)              → terminate VM
 *
 * exec() is preferred over runAndWait() — it goes directly via SSH, no polling loop.
 * For multi-line scripts, base64-encode the payload yourself:
 *   const b64 = btoa(script); execOnWorkspace(name, `echo ${b64} | base64 -d | sh`)
 */

// @ts-ignore — CJS module, no bundled types
import MagsClient from "@magpiecloud/mags";


export interface MagsExecResult {
  exitCode: number;
  output: string;
  stderr: string;
}

function getClient() {
  const token = process.env.MAGS_API_TOKEN;
  if (!token) throw new Error("MAGS_API_TOKEN not set");
  return new MagsClient({ apiToken: token });
}

/**
 * Create a new persistent VM workspace.
 * Delegates polling to client.new() — resolves when VM is running.
 * Returns the workspaceId (= name) and jobId (request_id).
 */
export async function newWorkspace(name: string): Promise<{
  jobId: string;
  workspaceId: string;
}> {
  const client = getClient();
  const result = await client.new(name, {
    timeout: 120_000,
    pollInterval: 2000,
  });
  // workspace_id == name (passed as workspaceId to the underlying run() call)
  return { jobId: result.request_id as string, workspaceId: name };
}

/**
 * Execute a command on an existing persistent VM via SSH.
 * Uses client.exec() which handles SSH auth + chroot wrapping automatically.
 *
 * For multi-line scripts, pass them already base64-encoded:
 *   const b64 = btoa(script);
 *   await execOnWorkspace(name, `echo ${b64} | base64 -d | sh`);
 *
 * Retries up to 3 times on transient SSH connection failures.
 */
export async function execOnWorkspace(
  nameOrId: string,
  command: string,
  opts: { timeout?: number } = {}
): Promise<MagsExecResult> {
  const client = getClient();
  const timeout = opts.timeout ?? 300_000; // 5 min default

  let lastError: Error | null = null;
  for (let attempt = 0; attempt < 3; attempt++) {
    if (attempt > 0) await sleep(5000);

    try {
      const result = await client.exec(nameOrId, command, { timeout });
      return result as MagsExecResult;
    } catch (err) {
      lastError = err as Error;
      const msg = (lastError.message ?? "").toLowerCase();
      // Treat connection/SSH errors as transient
      if (
        msg.includes("no running") ||
        msg.includes("no vm") ||
        msg.includes("connection refused") ||
        msg.includes("ssh") ||
        msg.includes("not running") ||
        msg.includes("no job found")
      ) {
        continue;
      }
      throw err;
    }
  }

  throw lastError ?? new Error("exec failed after retries");
}

/**
 * Find a running or sleeping job by name or workspace ID.
 * Delegates to client.findJob() — no manual pagination needed.
 */
export async function findJob(nameOrId: string): Promise<{
  jobId: string;
  workspaceId: string;
  status: string;
} | null> {
  const client = getClient();
  const job = await client.findJob(nameOrId);
  if (!job) return null;
  return {
    jobId: (job.request_id ?? job.id ?? "") as string,
    workspaceId: (job.workspace_id ?? nameOrId) as string,
    status: job.status as string,
  };
}

/**
 * Enable HTTP access for a VM and return the public proxy URL.
 * Uses client.url() which calls enableAccess + constructs the URL.
 */
export async function enableHttpAccess(
  nameOrId: string,
  port = 8080
): Promise<string> {
  const client = getClient();
  const result = await client.url(nameOrId, port);
  const url = (result.url ?? result.proxy_url ?? "") as string;
  if (!url) throw new Error(`No URL returned for VM '${nameOrId}'`);
  return url;
}

/**
 * Stop a workspace VM.
 */
export async function stopWorkspace(nameOrId: string): Promise<void> {
  const client = getClient();
  await client.stop(nameOrId);
}

/**
 * Get raw job status from the API.
 */
export async function getJobStatus(nameOrId: string): Promise<{
  status: string;
  exit_code?: number;
  workspace_id?: string;
  [key: string]: unknown;
}> {
  const client = getClient();
  // status() expects a request_id; resolve via findJob if given a name
  const jobId = nameOrId.includes("-") && nameOrId.length >= 32
    ? nameOrId
    : (await findJob(nameOrId))?.jobId ?? nameOrId;
  return client.status(jobId);
}

// ── Internal helpers ──────────────────────────────────────────────

function sleep(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}
