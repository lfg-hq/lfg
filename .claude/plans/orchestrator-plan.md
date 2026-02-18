# LFG Agent Orchestrator: Implementation Plan

## Status Tracker

| Phase | Description | Status |
|-------|-------------|--------|
| **0** | Fix streaming smoothness (backend buffer + frontend batching) | DONE |
| **1** | Fix OpenAI web search | DONE |
| **2** | Create `orchestrator` app + models + migrations | DONE |
| **3** | Orchestrator LLM client (non-streaming) | DONE |
| **4** | Event bus (publish + channel broadcast) | DONE |
| **5** | Orchestrator agent + tools (iterative) | DONE |
| **6** | Worker tasks (adapt existing executors) | DONE |
| **7** | ChatConsumer routing | DONE |
| **8** | Frontend pipeline UI | DONE |

---

## Architecture Overview

Three layers:

1. **Central Agent (Orchestrator)** — LLM-powered agent that triages user requests, plans work, dispatches to workers, handles events, communicates with user. Runs as a persistent task (Django-Q), NOT inside the WebSocket consumer.

2. **Worker Agents** — Stateless tasks that execute specific tickets (research, code, document creation). Each worker runs its own agentic tool-calling loop. Workers communicate ONLY through the event bus back to the orchestrator.

3. **Event Bus + State Store** — Django models for persistent state + Redis pub/sub for real-time events + Django Channels for WebSocket delivery.

```
User (WebSocket) <-> ChatConsumer <-> Orchestrator Agent (Django-Q task)
                                          | (events)
                                    Worker Agents (Django-Q tasks)
                                          |
                                   Event Bus (Redis + DB)
```

---

## Phase 0: Fix Streaming Smoothness

### Problem
- Backend sends every token immediately via WebSocket — no batching
- Frontend re-parses entire accumulated markdown with `marked.parse()` on every chunk — O(n^2)
- DOM fully reconstructed + `scrollToBottom()` called on every word

### Solution
**Backend** (`chat/consumers.py`):
- Buffer chunks in `process_ai_stream()` — flush every ~50 chars or 100ms

**Frontend** (`static/js/chat.js`):
- `requestAnimationFrame` batching in `handleAIChunk()`
- Debounce `marked.parse()` to every 100-150ms
- Throttle `scrollToBottom()` to once per animation frame

### Key Files
- `chat/consumers.py` — lines 718-808 (`process_ai_stream()`)
- `static/js/chat.js` — lines 2159-2183 (`handleAIChunk()`)
- `factory/llm/base.py` — lines 72-80 (stream processing)

---

## Phase 1: Fix OpenAI Web Search

### Problem
- `factory/llm/openai_provider.py` uses Responses API with `{"type": "web_search_preview"}`
- Model compatibility issues (gpt-5-mini/gpt-5.2 may not support it)
- `reasoning: {effort: "medium"}` may conflict with web search
- No error handling — failures are silent

### Solution
- Look up current OpenAI Responses API docs
- Verify model compatibility
- Add error handling and logging
- Test with explicit search prompts

### Key Files
- `factory/llm/openai_provider.py` — lines 474-476, 483-502, 676-703

---

## Phase 2: Orchestrator Data Models

### New App: `orchestrator`

#### AgentRun
- Top-level container for an orchestrator session
- Fields: conversation (FK), project (FK), user (FK), trigger_message, run_type, plan (JSON), status, orchestrator_messages (JSON)
- run_type choices: direct_response, research, single_ticket, pipeline
- status choices: planning, executing, waiting_on_user, completed, failed, cancelled

#### TicketExecution
- Single unit of work dispatched to a worker
- Fields: agent_run (FK), ticket (FK to ProjectTicket, nullable), title, description, execution_type, status, sequence_number, depends_on (M2M self), worker_context (JSON), result (JSON), blocked_reason, blocked_question, user_response, celery_task_id (rename to django_q_task_id), worker_type
- execution_type choices: research, create_document, create_prd, code_implementation, code_review, test_writing, bug_fix, knowledge_lookup, user_task
- status choices: queued, ready, running, blocked, completed, failed, cancelled, skipped

#### AgentEvent
- Immutable event log / audit trail
- Fields: agent_run (FK), ticket_execution (FK nullable), event_type, payload (JSON), requires_user_action
- Event types: run_started, plan_created, ticket_dispatched, run_completed, run_failed, ticket_started, ticket_progress, ticket_completed, ticket_failed, ticket_blocked, user_question, user_response, etc.

#### EnvironmentConfig
- NOTE: May be redundant with existing `ProjectEnvironmentVariable` in projects/models.py
- Evaluate whether to extend existing model or create new

### Important Adjustments
- Use Django-Q task IDs, not Celery
- Link TicketExecution.ticket to existing ProjectTicket
- Reuse ProjectEnvironmentVariable if possible

---

## Phase 3: Orchestrator LLM Client

### File: `orchestrator/llm.py`
- Non-streaming Anthropic SDK client (orchestrator doesn't need streaming)
- Direct `client.messages.create()` calls
- Returns structured `{text, tool_calls, stop_reason, usage}`
- Uses user's API key or falls back to system key
- Converts tools to Anthropic format

---

## Phase 4: Event Bus

### File: `orchestrator/events.py`
- `publish_event()` function: persist to AgentEvent model + broadcast via Django Channels
- Broadcast to `orchestrator_{agent_run_id}` group
- Also broadcast to `conversation_{conversation_id}` group for WebSocket delivery
- Wire into existing channel layer infrastructure

---

## Phase 5: Orchestrator Agent + Tools

### File: `orchestrator/agent.py`

#### System Prompt
- Triage user requests (direct_response, research, single_ticket, pipeline)
- Coordinate workers, handle events, communicate with user
- NOT an implementation agent — plans, delegates, monitors

#### Tools (build incrementally)
1. First: `triage_request`, `respond_to_user` (get simple Q&A working)
2. Then: `create_plan`, `dispatch_ticket` (pipeline execution)
3. Then: `ask_user`, `check_pipeline_status` (interaction + monitoring)
4. Finally: `knowledge_lookup`, `update_env_config`, `route_bug`, `modify_plan`

#### Agent Loop
- Event-driven: wakes on new_user_message, ticket_completed, ticket_failed, ticket_blocked, user_response
- Max 30 tool rounds per event
- Persists orchestrator_messages for multi-turn reasoning

---

## Phase 6: Worker Tasks

### File: `orchestrator/tasks.py`
- Adapt to Django-Q (`async_task()`) instead of Celery
- Leverage existing `AsyncTicketExecutor` and `ExecutorService`
- Each worker: load ticket context -> build worker prompt -> run agentic LLM loop -> report results via event bus
- Workers report blockers via `__BLOCKED__` markers in response
- On completion, check and ready dependent tickets
- Notify orchestrator via `orchestrator_handle_event` task

---

## Phase 7: ChatConsumer Integration

### File: `chat/consumers.py` (MODIFY)
- Route messages through orchestrator instead of direct LLM calls
- Check for active orchestrator run (waiting_on_user)
- Create new AgentRun for new requests with project context
- Keep fallback for non-project conversations (direct AI response)
- Add `agent_orchestrator_event` handler for channel layer messages

---

## Phase 8: Frontend Pipeline UI

### New WebSocket message types
- `orchestrator_text` — normal text from orchestrator
- `orchestrator_question` — agent asking user a question (with options)
- `orchestrator_status_update` — pipeline status

### Pipeline status component
- Show ticket pipeline with status indicators
- Queued (gray), Ready (blue), Running (yellow/spinner), Blocked (orange), Completed (green), Failed (red)
- Sidebar panel or inline card in chat

---

## Codebase Context (Existing Infrastructure)

### Task Queue: Django-Q (NOT Celery)
- Config in `LFG/settings.py` Q_CLUSTER
- `tasks/task_manager.py` — TaskManager class
- `tasks/executor_service.py` — Redis-backed distributed executor
- `tasks/async_executor.py` — AsyncTicketExecutor with project-level serialization

### Existing Tool Sets (factory/ai_tools.py)
- `tools_product` (~28 tools) — project mgmt, PRD, tickets, search
- `tools_code` (~20 tools) — code execution focus
- `tools_builder` (~9 tools) — ticket execution (ssh, code_server, broadcast)
- `tools_turbo` (~3 tools) — quick MVP
- `tools_design` (~4 tools) — design preview
- `tools_instant` (~1 tool) — instant app

### Key Existing Tools (orchestrator-relevant)
- `create_tickets` — batch ticket creation
- `queue_ticket_execution` — queue for execution
- `schedule_tickets` — schedule with dependency awareness
- `get_ticket_execution_log` — read logs
- `retry_ticket` — retry failed
- `get_project_dashboard` — project state

### Data Models Already Available
- `ProjectTicket` — full status tracking, dependencies (JSON), acceptance criteria, execution logs
- `TicketLog` — command, user_message, ai_response
- `ProjectEnvironmentVariable` — encrypted env vars
- `Conversation` / `Message` — chat models
- `Sandbox` — mags workspace management
