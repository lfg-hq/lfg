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

export interface GitPrResult {
  prNumber: number;
  prUrl: string;
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

# Ensure .lfg/ logs are not committed
if ! grep -q '.lfg/' .gitignore 2>/dev/null; then
  echo ".lfg/" >> .gitignore
fi

# Ensure we're on the feature branch (create if needed)
CURRENT=$(git branch --show-current 2>/dev/null || echo "")
if [ "$CURRENT" != "${featureBranch}" ]; then
  git checkout "${featureBranch}" 2>/dev/null || git checkout -b "${featureBranch}"
fi

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

// ── Merge feature → lfg-agent (direct push, no PR) ──────────────────

/**
 * Merge a feature branch into lfg-agent and push.
 * Runs on the VM via exec. No GitHub API / PR involved.
 */
export async function mergeToLfgAgent(opts: {
  workspaceId: string;
  projectDir: string;
  featureBranch: string;
  repoUrl: string;
  githubToken: string;
}): Promise<{ sha: string }> {
  const { workspaceId, projectDir, featureBranch, repoUrl, githubToken } = opts;
  const authUrl = repoUrl.replace("https://", `https://x-access-token:${githubToken}@`);

  const script = `
set -e
cd "${projectDir}"

git config user.email "ai@lfg.dev"
git config user.name "LFG AI"
git remote set-url origin "${authUrl}" 2>/dev/null || true

# Fetch latest
git fetch origin

# Checkout lfg-agent (create from main if doesn't exist)
if git rev-parse --verify origin/lfg-agent 2>/dev/null; then
  git checkout lfg-agent 2>/dev/null || git checkout -b lfg-agent origin/lfg-agent
  git reset --hard origin/lfg-agent
else
  git checkout main 2>/dev/null || git checkout -b main
  git checkout -b lfg-agent
fi

# Merge feature branch into lfg-agent
git merge ${featureBranch} -m "Merge ${featureBranch} into lfg-agent"

# Push lfg-agent
git push origin lfg-agent 2>&1

# Switch back to feature branch
git checkout ${featureBranch} 2>/dev/null || true

SHA=$(git rev-parse lfg-agent)
echo "MERGE_SHA:$SHA"
`;

  const scriptB64 = Buffer.from(script).toString("base64");
  const result = await execOnWorkspace(workspaceId, `echo ${scriptB64} | base64 -d | sh`, {
    timeout: 120_000,
  });

  const shaMatch = result.output.match(/MERGE_SHA:([a-f0-9]{40})/);
  if (!shaMatch) {
    throw new Error(`Merge to lfg-agent failed:\n${result.output}`);
  }

  return { sha: shaMatch[1]! };
}

// ── GitHub API Merge ──────────────────────────────────────────────────

/**
 * Create a PR via the GitHub REST API. Does NOT merge.
 * If a PR already exists for the same head→base, returns the existing one.
 */
export async function createPullRequest(opts: GitMergeOptions): Promise<GitPrResult> {
  const { repoOwner, repoName, featureBranch, targetBranch, title, body, githubToken } = opts;

  const baseApiUrl = `https://api.github.com/repos/${repoOwner}/${repoName}`;
  const headers = ghHeaders(githubToken);

  // Try to create PR
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

  if (prResp.ok) {
    const prData = await prResp.json() as { number: number; html_url: string };
    return { prNumber: prData.number, prUrl: prData.html_url };
  }

  // 422 = PR may already exist
  if (prResp.status === 422) {
    const searchResp = await fetch(
      `${baseApiUrl}/pulls?head=${repoOwner}:${featureBranch}&base=${targetBranch}&state=open`,
      { headers }
    );
    const existing = await searchResp.json() as Array<{ number: number; html_url: string }>;
    const first = existing[0];
    if (first) {
      return { prNumber: first.number, prUrl: first.html_url };
    }
  }

  throw new Error(`Failed to create PR: ${await prResp.text()}`);
}

/**
 * Merge an existing PR by number via the GitHub REST API.
 */
export async function mergePullRequest(opts: {
  repoOwner: string;
  repoName: string;
  prNumber: number;
  githubToken: string;
}): Promise<{ mergeCommitSha: string }> {
  const { repoOwner, repoName, prNumber, githubToken } = opts;
  const baseApiUrl = `https://api.github.com/repos/${repoOwner}/${repoName}`;
  const headers = ghHeaders(githubToken);

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
  return { mergeCommitSha: mergeData.sha ?? "" };
}

/**
 * Create a PR and merge it via the GitHub REST API (convenience wrapper).
 */
export async function mergeViaGitHub(opts: GitMergeOptions): Promise<GitMergeResult> {
  const { prNumber, prUrl } = await createPullRequest(opts);
  const { mergeCommitSha } = await mergePullRequest({
    repoOwner: opts.repoOwner,
    repoName: opts.repoName,
    prNumber,
    githubToken: opts.githubToken,
  });
  return { prNumber, prUrl, mergeCommitSha };
}

// ── Repo Creation ────────────────────────────────────────────────────

export interface CreateRepoOptions {
  repoName: string;
  description?: string;
  isPrivate?: boolean;
  githubToken: string;
}

export interface CreateRepoResult {
  owner: string;
  repoName: string;
  repoUrl: string;       // e.g. https://github.com/user/repo
  cloneUrl: string;       // e.g. https://github.com/user/repo.git
  created: boolean;       // true if newly created, false if already existed
}

/**
 * Create a new GitHub repository under the authenticated user's account.
 * If the repo already exists (HTTP 422), fetches the existing one instead.
 * Matches the Django implementation in tasks/task_definitions.py:get_or_create_github_repo().
 */
export async function createGitHubRepo(opts: CreateRepoOptions): Promise<CreateRepoResult> {
  const { repoName, description, isPrivate = true, githubToken } = opts;
  const headers = ghHeaders(githubToken);

  // Sanitize repo name: lowercase, spaces/underscores → hyphens
  const sanitizedName = repoName.toLowerCase().replace(/[\s_]+/g, "-").replace(/[^a-z0-9-]/g, "");

  // Try to create
  const createResp = await fetch("https://api.github.com/user/repos", {
    method: "POST",
    headers,
    body: JSON.stringify({
      name: sanitizedName,
      description: description ?? `LFG Project: ${repoName}`,
      private: isPrivate,
      auto_init: false,
    }),
  });

  if (createResp.ok) {
    const data = await createResp.json() as { owner: { login: string }; html_url: string; clone_url: string };
    return {
      owner: data.owner.login,
      repoName: sanitizedName,
      repoUrl: data.html_url,
      cloneUrl: data.clone_url,
      created: true,
    };
  }

  // 422 = repo already exists — fetch the existing one
  if (createResp.status === 422) {
    // Get authenticated user's login first
    const userResp = await fetch("https://api.github.com/user", { headers });
    if (!userResp.ok) throw new Error(`Failed to fetch GitHub user: ${userResp.status}`);
    const userData = await userResp.json() as { login: string };

    const repoResp = await fetch(`https://api.github.com/repos/${userData.login}/${sanitizedName}`, { headers });
    if (repoResp.ok) {
      const repoData = await repoResp.json() as { owner: { login: string }; html_url: string; clone_url: string };
      return {
        owner: repoData.owner.login,
        repoName: sanitizedName,
        repoUrl: repoData.html_url,
        cloneUrl: repoData.clone_url,
        created: false,
      };
    }
  }

  const errorText = await createResp.text();
  throw new Error(`Failed to create GitHub repo '${sanitizedName}': ${createResp.status} — ${errorText}`);
}

/**
 * Initialize a git repo on the workspace and push to GitHub.
 * Used when auto-creating a repo (empty repo, no clone needed).
 */
export async function initAndPushRepo(opts: {
  workspaceId: string;
  projectDir: string;
  repoUrl: string;
  branch: string;
  githubToken: string;
}): Promise<void> {
  const { workspaceId, projectDir, repoUrl, branch, githubToken } = opts;
  const authUrl = repoUrl.replace("https://", `https://x-access-token:${githubToken}@`);

  const script = `
set -e
cd "${projectDir}"

git init
git config user.email "ai@lfg.dev"
git config user.name "LFG AI"
git remote add origin "${authUrl}" 2>/dev/null || git remote set-url origin "${authUrl}"

# Ensure .lfg/ logs are excluded
echo ".lfg/" >> .gitignore 2>/dev/null || true

# Create initial commit so we have a branch to work with
echo "# Project created by LFG" > README.md
git add -A
git commit -m "Initial commit" --allow-empty

# Push main
git push -u origin HEAD:main 2>&1

# Create lfg-agent branch from main and push it
git checkout -b lfg-agent
git push -u origin lfg-agent 2>&1

echo "INIT_PUSH_OK"
`;

  const scriptB64 = Buffer.from(script).toString("base64");
  const result = await execOnWorkspace(workspaceId, `echo ${scriptB64} | base64 -d | sh`, {
    timeout: 60_000,
  });

  if (!result.output.includes("INIT_PUSH_OK")) {
    throw new Error(`Init+push failed:\n${result.output}`);
  }
}

// ── Helpers ──────────────────────────────────────────────────────────

function ghHeaders(token: string): Record<string, string> {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

export function featureBranchName(ticketId: string): string {
  return `feature/ticket-${ticketId}`;
}
