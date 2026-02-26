/**
 * Codebase Query Tool
 *
 * Dispatches questions about the project's codebase to Claude Code CLI
 * running inside a persistent "preview" Mags VM with the repo cloned.
 * Supports follow-up questions via session continuity.
 */

import { tool, zodSchema } from "ai";
import { z } from "zod";
import { db } from "../../config/db.ts";
import { projects } from "../../db/schema/projects.ts";
import { sandboxes } from "../../db/schema/sandbox.ts";
import { githubTokens } from "../../db/schema/users.ts";
import {
  getOrCreatePreviewSandbox,
  queryCodebase as runCodebaseQuery,
} from "../../services/codebase-query.ts";
import { eq } from "drizzle-orm";

export const queryCodebase = tool({
  description:
    "Query the project's codebase to answer questions about code structure, " +
    "find implementations, understand patterns, or explore the repository. " +
    "Runs Claude Code on a VM with the full repo cloned. " +
    "Supports follow-up questions via session continuity. " +
    "Use this when the user asks about their code — how something works, " +
    "where something is defined, code architecture, etc.",
  inputSchema: zodSchema(
    z.object({
      projectId: z.string().describe("The project ID"),
      userId: z.string().describe("The user ID"),
      question: z
        .string()
        .describe("The question about the codebase"),
      branch: z
        .string()
        .optional()
        .describe(
          "Git branch to query. Default: current branch. Use 'lfg-agent' for agent changes."
        ),
    })
  ),
  execute: async ({ projectId, userId, question, branch }) => {
    // 1. Load project → get repoUrl
    const [project] = await db
      .select()
      .from(projects)
      .where(eq(projects.id, projectId))
      .limit(1);

    if (!project) return { error: "Project not found" };

    const repoUrl =
      project.repoUrl ??
      (project.repoOwner && project.repoName
        ? `https://github.com/${project.repoOwner}/${project.repoName}`
        : null);

    if (!repoUrl) {
      return {
        error:
          "No repository linked to this project. Connect a GitHub repo first.",
      };
    }

    // 2. Load GitHub token for user
    const [ghToken] = await db
      .select()
      .from(githubTokens)
      .where(eq(githubTokens.userId, userId))
      .limit(1);

    if (!ghToken?.accessToken) {
      return {
        error:
          "No GitHub token found. Connect GitHub in Settings to query the codebase.",
      };
    }

    // 3. Get or create preview sandbox
    let sandbox;
    try {
      sandbox = await getOrCreatePreviewSandbox(
        projectId,
        userId,
        repoUrl,
        ghToken.accessToken
      );
    } catch (err) {
      console.error(`[queryCodebase] Sandbox creation failed:`, err);
      return {
        error: `Failed to set up codebase sandbox: ${(err as Error).message?.slice(0, 200)}`,
      };
    }

    if (!sandbox.magsWorkspaceId) {
      return { error: "Sandbox created but no workspace ID" };
    }

    // 4. Run query
    const existingSessionId = sandbox.cliSessionId ?? undefined;
    let result;
    try {
      result = await runCodebaseQuery(
        sandbox.magsWorkspaceId,
        question,
        {
          branch,
          sessionId: existingSessionId,
          maxTurns: 10,
        }
      );
    } catch (err) {
      // If session is stale, retry without --resume
      const errMsg = String(err);
      if (
        existingSessionId &&
        (errMsg.includes("No conversation found") ||
          errMsg.includes("session"))
      ) {
        console.log(`[queryCodebase] Stale session, retrying without resume`);
        // Clear stale session ID
        await db
          .update(sandboxes)
          .set({ cliSessionId: null, updatedAt: new Date() })
          .where(eq(sandboxes.id, sandbox.id));

        result = await runCodebaseQuery(
          sandbox.magsWorkspaceId,
          question,
          { branch, maxTurns: 10 }
        );
      } else {
        console.error(`[queryCodebase] Query failed:`, err);
        return {
          error: `Codebase query failed: ${(err as Error).message?.slice(0, 300)}`,
        };
      }
    }

    // 5. Update session ID for follow-up queries
    if (result.sessionId) {
      await db
        .update(sandboxes)
        .set({ cliSessionId: result.sessionId, updatedAt: new Date() })
        .where(eq(sandboxes.id, sandbox.id));
    }

    // 6. Return answer
    return {
      answer: result.answer,
      branch: result.branch ?? branch ?? "default",
      sessionId: result.sessionId,
    };
  },
});
