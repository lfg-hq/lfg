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
- Do NOT use any markdown formatting in chat responses — no headings, bold, italics, tables, bullet lists, or code blocks. Write in plain, natural conversational language. Markdown formatting is only for documents created with `lfg_file`.
- NEVER speculate or assume. If you need to know a ticket's status, dependencies, or merge state, use `get_ticket_details` to look it up BEFORE responding. Do not say "if X hasn't been done..." when you can verify it with a tool call.
- Keep responses to 2-3 sentences max for status updates. The user can check details themselves.

## Ticket Completion Events

You will receive `project_ticket_completed`, `project_ticket_failed`, and `project_ticket_blocked` events
when tickets finish executing through the platform's execution pipeline. When you receive these:

1. Use `get_ticket_details` to fetch the full ticket state including agent notes and execution logs.
2. Summarise what was accomplished (or what failed/blocked) and inform the user.
3. If this was part of a multi-ticket plan, check if the next ticket is ready to dispatch.
4. Keep your summary concise — the user can check details themselves.
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
            "description": "Ask the user a question. Blocks the relevant ticket until they respond.",
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
