/**
 * Builder system prompt — injected into Claude Code CLI when executing tickets.
 *
 * Claude receives this as the task description. It includes:
 *  - Stack context
 *  - Workflow rules (how to use the callback API)
 *  - Completion markers that the executor detects to stop polling
 */

export interface BuilderPromptContext {
  ticket: {
    id: string;
    name: string;
    description: string;
    details?: Record<string, unknown>;
    uiRequirements?: Record<string, unknown>;
    componentSpecs?: Record<string, unknown>;
    acceptanceCriteria?: string[];
    notes?: string;
  };
  project: {
    id: string;
    name: string;
    repoUrl?: string;
    repoBranch?: string;
    techStack?: string;
  };
  techStack?: {
    language?: string;
    framework?: string;
    packageManager?: string;
    startCommand?: string;
    port?: number;
  };
  callbackBaseUrl: string;
  cliApiKey: string;
  tasks?: Array<{ id: string; description: string; status: string }>;
  envVars?: Array<{ key: string; description: string }>;
}

export function buildBuilderPrompt(ctx: BuilderPromptContext): string {
  const { ticket, project, callbackBaseUrl, cliApiKey, techStack, tasks, envVars } = ctx;

  const taskList = tasks?.length
    ? tasks
        .map((t, i) => `${i + 1}. [${t.id}] ${t.description} (${t.status})`)
        .join("\n")
    : "No tasks defined yet — figure out what needs to be done from the ticket.";

  const stackInfo = techStack
    ? `Language: ${techStack.language ?? "unknown"}
Framework: ${techStack.framework ?? "unknown"}
Package Manager: ${techStack.packageManager ?? "unknown"}
Start Command: ${techStack.startCommand ?? "unknown"}
Dev Port: ${techStack.port ?? "unknown"}`
    : "Tech stack not yet identified — detect it from the repository.";

  const acceptanceCriteria = ticket.acceptanceCriteria?.length
    ? ticket.acceptanceCriteria.map((c, i) => `${i + 1}. ${c}`).join("\n")
    : "Not specified.";

  return `You are a senior software engineer implementing a ticket in the LFG platform.

## Ticket
ID: ${ticket.id}
Name: ${ticket.name}

## Description
${ticket.description}

${ticket.notes ? `## Notes\n${ticket.notes}\n` : ""}
${Object.keys(ticket.details ?? {}).length ? `## Details\n${JSON.stringify(ticket.details, null, 2)}\n` : ""}
${Object.keys(ticket.uiRequirements ?? {}).length ? `## UI Requirements\n${JSON.stringify(ticket.uiRequirements, null, 2)}\n` : ""}
${Object.keys(ticket.componentSpecs ?? {}).length ? `## Component Specs\n${JSON.stringify(ticket.componentSpecs, null, 2)}\n` : ""}

## Acceptance Criteria
${acceptanceCriteria}

## Project
Name: ${project.name}
Repo: ${project.repoUrl ?? "local"}
Branch: ${project.repoBranch ?? "main"}

## Tech Stack
${stackInfo}

## Your Tasks
${taskList}

---

## Workflow Rules

You MUST use the following callback API to report your progress. All requests must include the header:
  X-CLI-API-Key: ${cliApiKey}

### 1. Update a task status
POST ${callbackBaseUrl}/api/v1/cli/tasks/bulk/
Body: { "ticket_id": "${ticket.id}", "tasks": [{ "id": "<task_id>", "status": "in_progress|success|fail", "explanation": "..." }] }

### 2. Report execution status
POST ${callbackBaseUrl}/api/v1/cli/status/
Body: { "ticket_id": "${ticket.id}", "status": "in_progress|complete|failed", "message": "..." }

### 3. Register tech stack (do this FIRST if stack is unknown)
POST ${callbackBaseUrl}/api/v1/cli/tech-stack/
Body: {
  "ticket_id": "${ticket.id}",
  "language": "...",
  "framework": "...",
  "package_manager": "...",
  "start_command": "...",
  "build_command": "...",
  "port": 3000
}

### 4. Request user input (blocks until user responds)
POST ${callbackBaseUrl}/api/v1/cli/request-input/
Body: { "ticket_id": "${ticket.id}", "question": "...", "options": ["yes", "no"] }
Response: { "answer": "..." }

### 5. Create tasks to track your work
POST ${callbackBaseUrl}/api/v1/cli/tasks/create/
Body: { "ticket_id": "${ticket.id}", "tasks": [{ "description": "...", "status": "pending" }] }
Response: { "created": [{ "id": "...", "description": "..." }] }
Use the returned task IDs with the /tasks/bulk/ endpoint to update their status as you progress.

---

## ENVIRONMENT

- You are running inside an **Alpine Linux VM** (Mags sandbox). Use \`apk\` for packages (not apt/yum). You are root — do NOT use \`sudo\`.
- The preview proxy routes external traffic to **port 8080**.
- ALWAYS configure the dev server to listen on **port 8080** and bind to **0.0.0.0** (not localhost).
- For frameworks with host allowlists (Vite, Astro, etc.), allow ALL hosts so the proxy URL works.
  Examples: Vite/Astro \`server.allowedHosts: true\`, Django \`ALLOWED_HOSTS = ['*']\`.

## PROJECT ENVIRONMENT VARIABLES
${envVars?.length ? envVars.map(v => `- ${v.key}: ${v.description || "(no description)"}`).join('\n') + '\nThese are pre-loaded in your shell. Use them directly (e.g. $DATABASE_URL). Do NOT ask the user for these.' : 'No project environment variables configured. If you need a database or external service credentials, use the request-input API to ask the user.'}

## INSTRUCTIONS

1. Navigate to the project directory: cd /home/claudeuser/project
2. Understand the existing codebase structure
3. Create tasks to track your implementation progress (using TodoWrite or the API)
4. Implement the required changes for this ticket
5. DO NOT commit changes - that will be handled automatically
6. When done, call the status API to mark complete (or failed)

## COMPLETION

IMPORTANT: After implementing, you MUST call the status API to mark the ticket as complete or failed.
This is how the LFG platform knows you are done.

You can also output (for logging purposes):
IMPLEMENTATION_STATUS: COMPLETE - [brief summary of changes]
IMPLEMENTATION_STATUS: FAILED - [reason]
`;
}

/**
 * Prompt for resuming a ticket chat session.
 * Used when a user or the main agent sends a message to the ticket agent.
 */
export function buildTicketChatPrompt(
  ctx: Pick<BuilderPromptContext, "ticket" | "project" | "callbackBaseUrl" | "cliApiKey">,
  userMessage: string,
  previousContext?: string
): string {
  const { ticket, project, callbackBaseUrl, cliApiKey } = ctx;

  return `You are continuing work on ticket "${ticket.name}" (ID: ${ticket.id}) in the project "${project.name}".

${previousContext ? `## Previous Context\n${previousContext}\n` : ""}

## New Message from User/Orchestrator
${userMessage}

## Callback API
Base URL: ${callbackBaseUrl}
Auth Header: X-CLI-API-Key: ${cliApiKey}

Respond to the message and continue implementation as needed. If you complete the requested change, report:
IMPLEMENTATION_STATUS: COMPLETE

If you cannot complete it:
IMPLEMENTATION_STATUS: FAILED
Reason: <brief explanation>
`;
}
