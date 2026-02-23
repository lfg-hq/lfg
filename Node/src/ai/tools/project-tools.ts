import { tool, zodSchema } from "ai";
import { z } from "zod";
import { db } from "../../config/db.ts";
import { projects } from "../../db/schema/projects.ts";
import { projectFiles } from "../../db/schema/documents.ts";
import { projectTickets } from "../../db/schema/tickets.ts";
import { eq } from "drizzle-orm";

export const getProjectDashboard = tool({
  description:
    "Get a comprehensive overview of the current project state — stack, saved files (PRDs, specs, etc.), and ticket counts. Call this as the first action whenever a user describes or asks about their project.",
  inputSchema: zodSchema(z.object({
    projectId: z.string().describe("The project ID"),
  })),
  execute: async ({ projectId }) => {
    const [project] = await db.select().from(projects).where(eq(projects.id, projectId));
    if (!project) return { error: "Project not found" };

    const [files, tickets] = await Promise.all([
      db
        .select({ id: projectFiles.id, name: projectFiles.name, fileType: projectFiles.fileType, updatedAt: projectFiles.updatedAt })
        .from(projectFiles)
        .where(eq(projectFiles.projectId, projectId)),
      db
        .select({ id: projectTickets.id, status: projectTickets.status })
        .from(projectTickets)
        .where(eq(projectTickets.projectId, projectId)),
    ]);

    const ticketCounts = tickets.reduce((acc, t) => {
      acc[t.status] = (acc[t.status] ?? 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    return {
      project: {
        id: project.id,
        name: project.name,
        description: project.description,
        status: project.status,
        stack: project.stack,
      },
      files: files.map((f) => ({ id: f.id, name: f.name, fileType: f.fileType, updatedAt: f.updatedAt })),
      ticketCounts,
    };
  },
});

export const setProjectStack = tool({
  description:
    "Set or update the tech stack for a project. Call this after confirming the stack with the user.",
  inputSchema: zodSchema(z.object({
    projectId: z.string(),
    stack: z.string().describe("Tech stack description, e.g. 'Next.js 15, Drizzle ORM, PostgreSQL, Vercel'"),
  })),
  execute: async ({ projectId, stack }) => {
    await db.update(projects).set({ stack, updatedAt: new Date() }).where(eq(projects.id, projectId));
    return { success: true, stack };
  },
});

export const captureProjectName = tool({
  description: "Update the project name based on user input or AI suggestion.",
  inputSchema: zodSchema(z.object({
    projectId: z.string(),
    name: z.string().describe("The new project name"),
  })),
  execute: async ({ projectId, name }) => {
    await db.update(projects).set({ name, updatedAt: new Date() }).where(eq(projects.id, projectId));
    return { success: true, name };
  },
});
