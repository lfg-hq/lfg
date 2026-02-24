/**
 * Git service — runs git operations inside Mags VMs via execOnWorkspace.
 *
 * Phase 1 (setup):  clone/update repo, create feature branch
 * Phase 2 (commit): stage all changes, commit, push
 * Phase 3 (merge):  create PR or merge feature → lfg-agent via GitHub API
 */

import { execOnWorkspace } from "./mags.ts";

export interface GitSetupOptions {
  workspaceId: string;
  repoUrl: string;         // HTTPS with token embedded, or SSH URL
  branch: string;          // base branch to branch off (e.g. "main")
  featureBranch: string;   // e.g. "feature/ticket-<id>"
  projectDir: string;      // where to clone/use, e.g. /workspace/project
  githubToken?: string;
}

export interface GitCommitOptions {
  workspaceId: string;
  projectDir: string;
  commitMessage: string;
  authorName?: string;
  authorEmail?: string;
  featureBranch: string;
  repoUrl: string;
  githubToken?: string;
}

export interface GitMergeOptions {
  repoOwner: string;
  repoName: string;
  featureBranch: string;
  targetBranch: string;    // typically "lfg-agent"
  title: string;
  body?: string;
  githubToken: string;
}

export interface GitCommitResult {
  sha: string;
  branch: string;
}

export interface GitMergeResult {
  prNumber?: number;
  prUrl?: string;
  mergeCommitSha?: string;
}

// ── Setup ─────────────────────────────────────────────────────────────

/**
 * Clone the repo (or pull if already cloned) and create the feature branch.
 */
export async function setupRepo(opts: GitSetupOptions): Promise<void> {
  const { workspaceId, repoUrl, branch, featureBranch, projectDir, githubToken } = opts;

  // Build authenticated URL if token provided
  const authUrl = githubToken
    ? repoUrl.replace("https://", `https://x-access-token:${githubToken}@`)
    : repoUrl;

  const script = `
set -e
if [ -d "${projectDir}/.git" ]; then
  cd "${projectDir}"
  git fetch origin 2>&1
  git checkout ${branch} 2>&1
  git pull origin ${branch} 2>&1
else
  git clone "${authUrl}" "${projectDir}" 2>&1
  cd "${projectDir}"
fi

cd "${projectDir}"
git config user.email "agent@lfg.dev"
git config user.name "LFG Agent"

# Create or switch to feature branch
if git show-ref --verify --quiet refs/remotes/origin/${featureBranch}; then
  git checkout -b ${featureBranch} origin/${featureBranch} 2>/dev/null || git checkout ${featureBranch}
else
  git checkout -b ${featureBranch} 2>/dev/null || git checkout ${featureBranch}
fi

echo "GIT_SETUP_OK"
`;

  // exec() breaks with multi-line commands — base64-encode
  const scriptB64 = Buffer.from(script).toString("base64");
  const result = await execOnWorkspace(workspaceId, `echo ${scriptB64} | base64 -d | sh`, {
    timeout: 120_000,
  });

  if (!result.output.includes("GIT_SETUP_OK")) {
    throw new Error(`Git setup failed:\n${result.output}`);
  }
}

// ── Commit & Push ─────────────────────────────────────────────────────

/**
 * Stage all changes, commit, and push to origin.
 */
export async function commitAndPush(opts: GitCommitOptions): Promise<GitCommitResult> {
  const { workspaceId, projectDir, commitMessage, featureBranch, repoUrl, githubToken } = opts;

  const authorName = opts.authorName ?? "LFG Agent";
  const authorEmail = opts.authorEmail ?? "agent@lfg.dev";
  const msgB64 = Buffer.from(commitMessage).toString("base64");

  // Build authenticated remote URL
  const authUrl = githubToken
    ? repoUrl.replace("https://", `https://x-access-token:${githubToken}@`)
    : repoUrl;

  const script = `
set -e
cd "${projectDir}"

# Configure author
git config user.email "${authorEmail}"
git config user.name "${authorName}"

# Stage all changes (including untracked)
git add -A

# Check if there's anything to commit
if git diff --cached --quiet; then
  echo "NO_CHANGES"
  git rev-parse HEAD
  exit 0
fi

# Commit
COMMIT_MSG=$(echo ${msgB64} | base64 -d)
git commit -m "$COMMIT_MSG"

# Set remote with auth token
git remote set-url origin "${authUrl}" 2>/dev/null || true

# Push
git push origin ${featureBranch} --force-with-lease 2>&1 || git push origin ${featureBranch} 2>&1

SHA=$(git rev-parse HEAD)
echo "COMMIT_SHA:$SHA"
`;

  // exec() breaks with multi-line commands — base64-encode
  const scriptB64 = Buffer.from(script).toString("base64");
  const result = await execOnWorkspace(workspaceId, `echo ${scriptB64} | base64 -d | sh`, {
    timeout: 120_000,
  });

  const shaMatch = result.output.match(/COMMIT_SHA:([a-f0-9]{40})/);
  if (!shaMatch) {
    if (result.output.includes("NO_CHANGES")) {
      // Nothing to commit — get HEAD SHA
      const headResult = await execOnWorkspace(
        workspaceId,
        `cd "${projectDir}" && git rev-parse HEAD`,
        { timeout: 15_000 }
      );
      return { sha: headResult.output.trim(), branch: featureBranch };
    }
    throw new Error(`Commit/push failed:\n${result.output}`);
  }

  return { sha: shaMatch[1]!, branch: featureBranch };
}

// ── GitHub API Merge ──────────────────────────────────────────────────

/**
 * Create a PR and merge it via the GitHub REST API.
 * Falls back to direct branch merge if PR creation fails.
 */
export async function mergeViaGitHub(opts: GitMergeOptions): Promise<GitMergeResult> {
  const { repoOwner, repoName, featureBranch, targetBranch, title, body, githubToken } = opts;

  const baseApiUrl = `https://api.github.com/repos/${repoOwner}/${repoName}`;
  const headers = {
    Authorization: `Bearer ${githubToken}`,
    "Content-Type": "application/json",
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  };

  // 1. Create PR
  const prResp = await fetch(`${baseApiUrl}/pulls`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      title,
      body: body ?? "",
      head: featureBranch,
      base: targetBranch,
    }),
  });

  if (!prResp.ok && prResp.status !== 422) {
    throw new Error(`Failed to create PR: ${await prResp.text()}`);
  }

  const prData = (prResp.ok ? await prResp.json() : {}) as { number?: number; html_url?: string };

  const prNumber = prData.number;
  const prUrl = prData.html_url;

  if (!prNumber) {
    // PR may already exist — try to find it
    const searchResp = await fetch(
      `${baseApiUrl}/pulls?head=${repoOwner}:${featureBranch}&base=${targetBranch}&state=open`,
      { headers }
    );
    const existing = await searchResp.json() as Array<{ number: number; html_url: string }>;
    const first = existing[0];
    if (existing.length > 0 && first) {
      return mergeExistingPr(first.number, first.html_url, baseApiUrl, headers);
    }
    throw new Error("Could not create or find existing PR");
  }

  return mergeExistingPr(prNumber, prUrl ?? "", baseApiUrl, headers as Record<string, string>);
}

async function mergeExistingPr(
  prNumber: number,
  prUrl: string,
  baseApiUrl: string,
  headers: Record<string, string>
): Promise<GitMergeResult> {
  // Merge the PR
  const mergeResp = await fetch(`${baseApiUrl}/pulls/${prNumber}/merge`, {
    method: "PUT",
    headers,
    body: JSON.stringify({
      merge_method: "squash",
      commit_title: `feat: ticket implementation (#${prNumber})`,
    }),
  });

  if (!mergeResp.ok) {
    throw new Error(`Failed to merge PR #${prNumber}: ${await mergeResp.text()}`);
  }

  const mergeData = await mergeResp.json() as { sha?: string };

  return {
    prNumber,
    prUrl,
    mergeCommitSha: mergeData.sha,
  };
}

// ── Helpers ──────────────────────────────────────────────────────────

export function featureBranchName(ticketId: string): string {
  return `feature/ticket-${ticketId}`;
}
