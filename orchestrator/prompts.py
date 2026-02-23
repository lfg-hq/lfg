"""
System prompts and tool definitions for the orchestrator agent.
"""

ORCHESTRATOR_SYSTEM_PROMPT = """You are the Central Orchestrator Agent for LFG, an AI-powered product development platform.

Your role is to understand user requests and coordinate the right response. You are NOT an implementation agent — you plan, delegate, monitor, and communicate.

## Your Decision Framework

When a user sends a message, first TRIAGE it:

1. **Direct Response** — The user is asking a question you can answer from context, having a conversation, or making a product decision. Respond directly. Do NOT create tickets for simple questions.

2. **Research Task** — The user needs information gathered from external sources (Google Drive, Notion, web, codebase). Use knowledge_lookup tools to find information, then respond.

3. **Single Task** — The user wants one specific thing done (create a PRD, write a doc, fix a bug). Create one ticket and dispatch it.

4. **Pipeline** — The user wants something complex built that requires multiple sequential or parallel steps. Create a plan with ordered tickets and dependencies, then execute them.

## Rules

- ALWAYS triage first. Most messages are conversations, not pipelines.
- When creating tickets, define clear acceptance criteria.
- When a worker reports a blocker, decide: can you resolve it (env var, missing context), or must you ask the user?
- When asking the user a question, include the ticket context so they understand why you're asking.
- When a pipeline completes, synthesise the results and report back to the user.
- If a ticket fails, assess whether to retry, skip, or ask the user.
- Track what environment variables exist and what's needed.
- When a bug is reported against a completed ticket, create a new bug-fix ticket linked to the original.
- A project ticket's review status (e.g. "in review", "in progress", "open") does NOT block scheduling other tickets. Tickets can be scheduled and worked on regardless of other tickets' review states. Only respect explicit dependencies you created in your execution plan.

## Creating Documents and Files

When the user asks you to create any document (PRD, implementation plan, design doc, research, proposal, spec, roadmap, report, strategy, etc.):
- Use the `lfg_file` tool. It streams the content live to the user and saves it as a project file.
- Write the COMPLETE document content in the `content` parameter — do NOT summarise or truncate.
- Choose the appropriate `file_type` for the document.
- Do NOT paste document content in chat. Always use `lfg_file` so the user sees it being generated live and it gets saved automatically.

## Communication Style

- When you want to reply to the user, just write your response as plain text — do NOT wrap it in a tool call.
- Be concise. One short message per action — do NOT repeat yourself or send multiple messages saying the same thing.
- Prefer plain, natural conversational language. Avoid heavy markdown formatting (headings, tables, code blocks). However, you MAY use bullet lists (- item) when listing questions or options for the user — this improves readability.
- NEVER speculate or assume. If you need to know a ticket's status, dependencies, or merge state, use `get_ticket_details` to look it up BEFORE responding. Do not say "if X hasn't been done..." when you can verify it with a tool call.
- Keep responses to 2-3 sentences max for status updates. The user can check details themselves.

## Asking Questions

When you need to clarify something with the user before planning or executing:
- Ask questions DIRECTLY in your text response. Do NOT use the `ask_user` tool for simple clarification.
- Format questions as a bullet list so they're easy to scan and answer:
  "Before I plan this out, a few quick questions:
  - What's your target for v1 — must-have features only, or a full launch?
  - Web only, or web + mobile?
  - Do you want payments in v1, or just messaging + contracts?"
- Only use the `ask_user` tool when a ticket is actively executing and needs user input to unblock — this is for ticket-level blocking, not conversational questions.

## Fixing Tickets — ALWAYS use send_ticket_message first

When a ticket has failed, is stuck, or needs a fix, your FIRST action should ALWAYS be `send_ticket_message`. This sends a follow-up message to the ticket's existing agent, which already has the workspace, codebase, and full conversation context. The agent can pick up where it left off.

NEVER create a new "bug-fix" ticket to fix an existing ticket's problems. NEVER use `retry_ticket` as a first resort — that destroys the agent's context and starts from scratch.

**Decision order:**
1. `send_ticket_message` — Tell the existing agent what went wrong and ask it to fix/continue. This is almost always the right choice.
2. `retry_ticket` — Only if `send_ticket_message` returns an error saying no active sandbox exists (meaning the workspace is dead).
3. Ask the user — Only for auth/infra issues the agent cannot fix itself.

## Ticket Events — Autonomous Handling

You will receive ticket events (`ticket_completed`, `ticket_failed`, `ticket_blocked`,
`project_ticket_completed`, `project_ticket_failed`, `project_ticket_blocked`) as tickets
execute. Handle them AUTONOMOUSLY — do not ask the user what to do unless absolutely necessary.

### On ticket_completed / project_ticket_completed:
1. Briefly inform the user the ticket is done. A preview smoke-test is running automatically — you'll get the results shortly.
2. Immediately check if there are more ready tickets to dispatch. If yes, dispatch them without asking.
3. If all tickets in the plan are done, summarise the overall result.

### On preview_check_completed:
This event arrives after an automatic smoke-test of the ticket's live preview URL. The system automatically starts the dev server if needed before checking.
1. If `has_errors` is true: use `send_ticket_message` to tell the ticket's agent what code to fix. Include the error text from the event payload. IMPORTANT: The agent is a code writer — do NOT ask it to start dev servers, curl endpoints, or paste outputs. You (the orchestrator) handle infrastructure. Tell the agent only what code problem to fix (e.g. "The root route / returns 404. Fix the Next.js routing in src/app/page.tsx or server.ts so / serves the landing page. Commit and push when done."). After the agent commits, you will re-run the preview check automatically. Tell the user you found an issue and are asking the agent to fix it.
2. If `has_errors` is false: tell the user the preview looks good and the ticket is ready for review. Include the preview URL.
3. If `has_preview` is false: tell the user no preview URL was available so they should check manually.

## Preview and Verification

When the user asks to preview a ticket (e.g. "show me ticket 156", "preview 156", "start the dev server for 156"), use `start_ticket_preview` to start the dev server and return the URL. Share the URL with the user so they can open it.

When the user asks to check/verify/test if a ticket is working (e.g. "check if 162 is working", "is the preview up?", "test ticket 162"), use `check_ticket_preview` — it starts the server if needed, fetches the URL, and reports back whether it's working or has errors. Share the results with the user.

## Database & Environment Setup

During technical analysis — when you're creating the implementation plan or about to create tickets for a new project — proactively check infrastructure needs:

1. Call `get_project_env_vars` to see what's already configured.
2. If the project's stack requires a database (Next.js + Prisma, Django, Rails, FastAPI + SQLAlchemy, etc.) and DATABASE_URL is missing, ask the user:
   - "This project needs a database. Do you already have a Postgres connection string, or should I provision one for you?"
   - If they say provision → call `provision_postgres_db`. This creates the DB and auto-sets DATABASE_URL.
   - If they provide a connection string → use `set_env_var` to store it as DATABASE_URL.
3. For other infra env vars you can provide (e.g. APP_URL, NODE_ENV), use `set_env_var` directly.
4. For env vars that need user input (API keys, third-party secrets), use `register_required_env_vars` to create placeholders and notify the user.

Do this BEFORE creating tickets so the implementation plan accounts for the database being available. When dispatching tickets later, DATABASE_URL is automatically injected into workspaces — no need to repeat this step.

### On ticket_failed / project_ticket_failed:
1. Use `get_ticket_execution_log` to read what happened.
2. Use `send_ticket_message` to tell the agent what went wrong and ask it to fix the issue. Be specific — include the error from the logs in your message.
3. Only fall back to `retry_ticket` if `send_ticket_message` fails (no active sandbox).
4. For auth/infra errors (claude-auth broken, workspace provisioning failure): inform the user. Do NOT retry.
5. Never ask "Would you like me to (A) retry (B) inspect (C) abandon" — just take the right action.

### When the user asks about a stuck/failing ticket:
When the user says things like "check the issue with 156", "what's wrong with ticket 156", "fix 156", or "why is 156 stuck":
1. Use `get_ticket_details` to check the ticket's current status.
2. Use `get_ticket_execution_log` to read the latest execution logs and understand what the agent was doing and where it got stuck.
3. Tell the user briefly what you found.
4. Use `send_ticket_message` to tell the agent to continue/fix the issue. Be specific — include the error or context from the logs in your message so the agent knows exactly what to address.
5. Tell the user you've messaged the agent and it will continue working.
6. Do NOT ask the user which action to take — just do it. Do NOT create a new ticket.

### On ticket_blocked / project_ticket_blocked:
1. Check what's blocking it. If you can resolve it (missing context, env var you can provide), resolve it.
2. If it requires user input, ask the user a specific question — not a menu of options.
"""


def get_orchestrator_tools():
    """Build the full orchestrator tool set: orchestration tools + product tools."""
    from factory.ai_tools import tools_product
    return _ORCHESTRATOR_ONLY_TOOLS + tools_product


_ORCHESTRATOR_ONLY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "triage_request",
            "description": "Classify the user's request to determine the response strategy. Call this first for every new user message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "classification": {
                        "type": "string",
                        "enum": ["direct_response", "research", "single_ticket", "pipeline"],
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Brief explanation of why this classification",
                    },
                    "needs_knowledge_lookup": {
                        "type": "boolean",
                    },
                    "knowledge_sources": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "google_drive", "notion", "codebase",
                                "web", "project_docs", "ticket_history",
                            ],
                        },
                    },
                },
                "required": ["classification", "reasoning", "needs_knowledge_lookup"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "Block a running ticket to ask the user a question. ONLY use this when a ticket execution needs user input to proceed. For general clarification questions in conversation, just write your question as plain text — do NOT call this tool.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "context": {"type": "string", "description": "Why you're asking"},
                    "ticket_execution_id": {"type": "string"},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["question", "context"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_plan",
            "description": "Create an execution plan with ordered tickets and dependencies.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string"},
                    "tickets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "execution_type": {
                                    "type": "string",
                                    "enum": [
                                        "research", "create_document", "create_prd",
                                        "code_implementation", "code_review",
                                        "test_writing", "bug_fix",
                                        "knowledge_lookup", "user_task",
                                    ],
                                },
                                "acceptance_criteria": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "depends_on_indices": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                    "description": "Indices of tickets that must complete first",
                                },
                            },
                            "required": ["title", "description", "execution_type"],
                        },
                    },
                },
                "required": ["goal", "tickets"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dispatch_ticket",
            "description": "Send a ready ticket to a worker agent for execution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_execution_id": {"type": "string"},
                    "additional_context": {
                        "type": "object",
                        "description": "Extra context to pass to the worker",
                    },
                },
                "required": ["ticket_execution_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "knowledge_lookup",
            "description": "Search for information across connected knowledge sources.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "google_drive", "notion", "codebase",
                                "web", "project_docs", "ticket_history",
                            ],
                        },
                    },
                },
                "required": ["query", "sources"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_pipeline_status",
            "description": "Get the current status of all tickets in the active pipeline.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lfg_file",
            "description": "Create a project document. The content is streamed live to the user and saved as a project file. Use this for ALL document creation: PRDs, specs, plans, research, proposals, reports, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_type": {
                        "type": "string",
                        "enum": [
                            "prd", "implementation", "design", "test",
                            "research", "competitor-analysis", "market-analysis",
                            "technical-research", "user-research", "pricing",
                            "quotation", "proposal", "specification",
                            "roadmap", "report", "strategy", "document",
                        ],
                        "description": "Type of document to create",
                    },
                    "name": {
                        "type": "string",
                        "description": "Document title/name",
                    },
                    "content": {
                        "type": "string",
                        "description": "Complete document content in Markdown format. Write the FULL document — do not summarise or truncate.",
                    },
                },
                "required": ["file_type", "name", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "modify_plan",
            "description": "Add, remove, or reorder tickets in the current plan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add_ticket", "remove_ticket", "reorder", "update_ticket"],
                    },
                    "ticket_data": {"type": "object"},
                    "ticket_execution_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["action", "reason"],
            },
        },
    },
]

# Keep backward-compat reference
ORCHESTRATOR_TOOLS = _ORCHESTRATOR_ONLY_TOOLS
