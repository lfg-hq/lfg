# LFG Chat Orchestrator — Architecture

## Overview

The Chat Orchestrator transforms LFG's chat from a simple request-response loop into an **agent-mode** system. Every project conversation routes through a central orchestrator agent that triages requests, coordinates workers, and manages multi-step pipelines.

All responses stream in real time — chat text streams token-by-token and document content streams live to the artifacts panel as the LLM generates it.

---

## System Architecture

```
                                   LFG Chat Orchestrator
 ___________________________________________________________________________________________
|                                                                                           |
|   Browser (WebSocket)                                                                     |
|       |                                                                                   |
|       v                                                                                   |
|   +-----------------+     +---------------------------+                                   |
|   |  ChatConsumer   |---->|   OrchestratorAgent       |  (in-process, same ASGI worker)   |
|   |  (WebSocket)    |     |   (Agentic Loop)          |                                   |
|   |                 |<----|                           |                                   |
|   +-----------------+     |  1. Triage request        |                                   |
|       ^                   |  2. Stream LLM response   |                                   |
|       |                   |  3. Execute tools         |                                   |
|       |                   |  4. Stream file content    |                                   |
|       |                   +---------------------------+                                   |
|       |                         |           |                                             |
|       |                         v           v                                             |
|       |                   +--------+  +--------+                                          |
|       |                   | Event  |  |  LLM   |                                          |
|       |                   |  Bus   |  | Client |  (Streaming async generators)             |
|       |                   +--------+  +--------+                                          |
|       |                       |       (OpenAI / Anthropic / Google)                        |
|       |                       |                                                           |
|       |   +-------------------+-------------------+                                       |
|       |   |                                       |                                       |
|       |   v                                       v                                       |
|       |  +-------------------+    +-------------------+                                   |
|       |  |   Django-Q        |    |  Redis Channels   |                                   |
|       |  |   Workers         |    |  (group_send)     |                                   |
|       |  |                   |    +-------------------+                                   |
|       |  |  execute_ticket() |          |                                                 |
|       |  +-------------------+          |                                                 |
|       |         |                       |                                                 |
|       |         v                       |                                                 |
|       |  +-------------------+          |                                                 |
|       |  | Bridge: notify    |----------+                                                 |
|       |  | orchestrator      |  (ticket_completed events)                                 |
|       +--| ticket_status()   |                                                            |
|          +-------------------+                                                            |
|___________________________________________________________________________________________|
```

---

## Streaming Architecture

The orchestrator streams content in two ways:

### 1. Chat Text Streaming (text_delta → WebSocket)

```
LLM generates tokens
    |
    v  (async generator yields text_delta events)
_stream_llm_round()
    |
    v  channel_layer.group_send()
agent_orchestrator_event handler in ChatConsumer
    |
    v  WebSocket send
Browser: handleOrchestratorNotification('orchestrator_text')
    |
    v
Append to .orchestrator-streaming bubble
```

- Text tokens stream live as `orchestrator_text` notifications
- Frontend tracks the active bubble with `.orchestrator-streaming` class
- Class cleaned up on `is_final` or `stop_confirmed`
- Text from tool-call rounds streams to the same bubble (no duplicate bubbles)

### 2. Document Content Streaming (lfg_file tool_delta → artifacts panel)

```
LLM calls lfg_file(file_type, name, content="...")
    |
    v  tool_delta events contain JSON argument fragments
_stream_llm_round() intercepts tool_start/tool_delta/tool_end
    |
    v  _LfgFileStreamTracker extracts + unescapes content field
    |
    v  channel_layer.group_send() as file_stream notification
ai_response_chunk handler in ChatConsumer
    |
    v  WebSocket send
Browser: ArtifactsLoader.streamDocumentContent()
    |
    v
Document renders live in artifacts panel
```

- `_LfgFileStreamTracker` accumulates JSON fragments and detects the `"content": "` field
- Content is JSON-unescaped (handles `\n`, `\"`, `\\`, `\uXXXX`) and streamed in real time
- `file_name` and `file_type` extracted from JSON prefix before content starts
- On `tool_end`, sends `is_complete: true` notification
- `handle_lfg_file()` in tools.py only saves the file (no fake streaming)

### In-Process Execution

User messages run the orchestrator **in the same ASGI process** via `asyncio.create_task()`:

```
ChatConsumer._try_orchestrator_route()
    |
    v  asyncio.create_task(self._run_orchestrator(...))
    |
    v  OrchestratorAgent.handle_event()  (same process)
    |
    v  channel_layer.group_send()  (InMemoryChannelLayer works!)
    |
    v  ChatConsumer.agent_orchestrator_event()  (same process)
    |
    v  WebSocket send
```

This avoids the cross-process InMemoryChannelLayer limitation in development.
Ticket completion events still go through Django-Q → Redis Channels (works with RedisChannelLayer in production).

### Stop Generation

```
User clicks Stop
    |
    v  WebSocket: {type: "stop_generation"}
ChatConsumer.receive()
    |
    v  self.active_generation_task.cancel()
    |
    v  asyncio.CancelledError propagates through:
       handle_event() → _stream_llm_round() → LLM stream generator
    |
    v  HTTP connection to LLM provider terminated
    |
    v  _run_orchestrator catches CancelledError, sends is_final
    |
    v  Frontend: removes .orchestrator-streaming, cleans up UI
```

---

## Request Lifecycle

```
User types message in chat
         |
         v
+------------------+
| 1. ChatConsumer  |  WebSocket handler receives message
|    receive()     |  Saves user message to Message table
+------------------+
         |
         v
+------------------+
| 2. Route Check   |  Is this a project conversation?
|                  |  (not turbo/instant/canvas mode)
+------------------+
         |
    Yes  |  No --> Direct AI response (legacy flow)
         v
+------------------+
| 3. Orchestrator  |  Check for active AgentRun
|    Route         |  - Active run? Reuse it
|                  |  - No active run? Create new AgentRun
|                  |  asyncio.create_task(_run_orchestrator)
+------------------+
         |
         v  (in-process)
+------------------+
| 4. Orchestrator  |  Loads chat history + run context
|    Agent         |  Enters agentic tool loop (max 20 rounds)
|    handle_event()|  LLM decides what tools to call
|                  |  Text streams live to WebSocket
+------------------+
         |
         v
+------------------+
| 5. Tool          |  triage_request --> classify intent
|    Execution     |  create_plan --> build ticket pipeline
|                  |  dispatch_ticket --> run worker
|                  |  lfg_file --> content streamed live, then saved
|                  |  ask_user --> block & question
+------------------+
         |
         v
+------------------+
| 6. Response      |  Save assistant message to DB
|    Delivery      |  Send is_final signal
|                  |  Clean up streaming state
+------------------+
```

---

## Data Model

```
+------------------+       +--------------------+       +------------------+
|    AgentRun      |       |  TicketExecution    |       |   AgentEvent     |
|  (Session)       |1----*>|  (Work Unit)        |1----*>|  (Audit Log)     |
+------------------+       +--------------------+       +------------------+
| id (UUID)        |       | id (UUID)           |       | id (UUID)        |
| conversation FK  |       | agent_run FK        |       | agent_run FK     |
| project FK       |       | ticket FK (optional)|       | ticket_exec FK   |
| user FK          |       | title               |       | event_type       |
| trigger_message  |       | description         |       | payload (JSON)   |
| run_type         |       | execution_type      |       | requires_user    |
| status           |       | status              |       | created_at       |
| plan (JSON)      |       | sequence_number     |       +------------------+
| orchestrator_    |       | depends_on (M2M)    |
|   messages (JSON)|       | worker_context JSON |
| created_at       |       | result (JSON)       |
| completed_at     |       | blocked_reason      |
+------------------+       | task_id (Django-Q)  |
                           | started_at          |
                           | completed_at        |
                           +--------------------+
                                  |    ^
                                  |    | depends_on
                                  +----+ (self M2M)
```

### Status Flows

**AgentRun:**
```
planning --> executing --> completed
                |
                +--> waiting_on_user --> executing (on user response)
                |
                +--> failed
                +--> cancelled
```

**TicketExecution:**
```
queued --> ready --> running --> completed
                      |
                      +--> blocked --> ready (on user response)
                      |
                      +--> failed
                      +--> cancelled / skipped
```

---

## Orchestrator Agent — Tool Loop

The orchestrator uses an **agentic tool-calling loop**. The LLM decides what to do by calling tools. Text responses are written as plain text (not wrapped in tool calls).

```
                    +------------------+
                    |  Build Context   |
                    |  + Chat History  |
                    +--------+---------+
                             |
                             v
                    +------------------+
              +---->|  Call LLM        |
              |     |  (streaming)     |
              |     +--------+---------+
              |              |
              |     +--------+---------+
              |     | Tool calls?      |
              |     +--------+---------+
              |         |          |
              |    Yes  |          | No --> Text already streamed live
              |         v
              |  +------------------+
              |  | Execute Tool(s)  |
              |  | Feed result back |
              +--+  to LLM         |
                 +------------------+

Max 20 rounds per event
Terminal tools: ask_user (breaks loop)
```

### Available Tools

| Tool | Purpose | Side Effects |
|------|---------|-------------|
| `triage_request` | Classify intent (direct/research/single/pipeline) | Sets run_type + status |
| `ask_user` | Ask user a question | Sets status=waiting_on_user, breaks loop |
| `create_plan` | Build ticket pipeline with dependencies | Creates TicketExecution records |
| `dispatch_ticket` | Start a ticket worker | Enqueues Django-Q task |
| `lfg_file` | Create a project document (content streams live) | Saves ProjectFile |
| `knowledge_lookup` | Search docs/codebase/tickets | Read-only |
| `check_pipeline_status` | Get ticket status summary | Read-only |
| `modify_plan` | Add/remove/update tickets | Modifies TicketExecution records |

---

## Multi-Provider LLM Client

The orchestrator uses a streaming-first LLM client. All providers use async generators that yield events.

```
stream_orchestrator_llm()  (orchestrator/llm.py)
    |
    v  _resolve_model(provider, model) --> actual model ID
    |
    v  _STREAM_PROVIDER_MAP routing:
       anthropic --> _stream_anthropic()  (native Anthropic SDK)
       openai ----> _stream_openai()     (native OpenAI SDK)
       google ----> _stream_google()     (Gemini via OpenAI-compat)
       xai -------> _stream_openai()     (xAI via OpenAI SDK)
```

### Event Types Yielded

```python
{"type": "text_delta",  "text": "..."}           # Text token
{"type": "tool_start",  "id": "...", "name": "..."} # Tool call begins
{"type": "tool_delta",  "id": "...", "arguments_delta": "..."} # JSON fragment
{"type": "tool_end",    "id": "..."}              # Tool call ends
{"type": "done",        "text": str, "tool_calls": list, "stop_reason": str}
```

### Message Format Translation

Internal format uses Anthropic-style messages. For OpenAI/Google, messages are converted by `_convert_to_openai_messages()`.

---

## Event Bus

Events serve two purposes: **audit trail** (DB) and **real-time delivery** (Channels).

```
publish_event(agent_run, event_type, payload)
         |
         +----> AgentEvent.objects.create()     [Persistent audit log]
         |
         +----> channel_layer.group_send()
                  |
                  +----> orchestrator_{run_id}   [Internal: orchestrator listeners]
                  |
                  +----> conversation_{conv_id}  [External: user's WebSocket]
```

### Event Types

| Category | Events |
|----------|--------|
| **Orchestrator** | run_started, plan_created, ticket_dispatched, run_completed, run_failed |
| **Worker** | ticket_started, ticket_progress, ticket_completed, ticket_failed, ticket_blocked |
| **Bridge** | project_ticket_completed, project_ticket_failed, project_ticket_blocked |
| **Interaction** | user_question, user_response |

### Ticket Completion Flow

```
Worker: execute_ticket() completes
    |
    v
orchestrator/workers.py: publish_event("ticket_completed")
    |
    v  _notify_orchestrator()
    |
    v  Django-Q: handle_orchestrator_event()
    |
    v  OrchestratorAgent.handle_event("ticket_completed", payload)
    |
    v  LLM reads event, decides next action (dispatch next ticket, inform user, etc.)
    |
    v  Response streamed to user via Redis Channels
```

### Legacy Pipeline Bridge

```
AsyncTicketExecutor or CLI endpoint
    |
    v
orchestrator/bridge.py: notify_orchestrator_ticket_status()
    |
    v  Find active AgentRun for project
    |
    v  Django-Q: handle_orchestrator_event(run_id, "project_ticket_completed", ...)
    |
    v  OrchestratorAgent.handle_event()
```

---

## Worker Execution

Workers are stateless tasks that execute individual tickets.

```
dispatch_ticket()  (orchestrator tool)
    |
    v  Django-Q async_task()
execute_ticket()  (workers.py)
    |
    v
1. Load ticket + dependency results
2. Build prompt (title, description, acceptance criteria)
3. Call LLM
4. Check for blockers (__BLOCKED__ marker)
    |
    +----> completed --> publish_event + _notify_orchestrator
    +----> blocked ----> publish_event + _notify_orchestrator
    +----> failed -----> publish_event + _notify_orchestrator
```

### Dependency Resolution

```
Ticket A (no deps) ----> ready ----> running ----> completed
                                                       |
Ticket B (depends on A) ----> queued -----> ready -----+
                                              |
Ticket C (depends on A) ----> queued -----> ready -----+
                                                       |
Ticket D (depends on B,C) ----> queued (waits for both B and C)
```

---

## Testing

### Management Command: send_event

Send test events to the orchestrator event bus:

```bash
# List orchestrator runs
python manage.py send_event --list-runs

# Send event to a specific project's orchestrator
python manage.py send_event --project <project-uuid>

# Direct event
python manage.py send_event --project <uuid> --type ticket_completed \
    --payload '{"title": "Build login page"}'
```

---

## Key Files

| File | Purpose |
|------|---------|
| `chat/consumers.py` | WebSocket handler, in-process orchestrator execution, stop handling |
| `orchestrator/agent.py` | OrchestratorAgent, streaming tool loop, _LfgFileStreamTracker |
| `orchestrator/llm.py` | Multi-provider streaming LLM client (async generators) |
| `orchestrator/tools.py` | Tool handler implementations |
| `orchestrator/prompts.py` | System prompt + tool definitions |
| `orchestrator/tasks.py` | Django-Q task entry points (ticket completion events) |
| `orchestrator/workers.py` | Ticket execution workers |
| `orchestrator/events.py` | Event publishing (DB + Channels) |
| `orchestrator/bridge.py` | Legacy pipeline → orchestrator bridge |
| `orchestrator/models.py` | AgentRun, TicketExecution, AgentEvent |
| `static/js/chat.js` | Frontend: streaming text, file_stream, question cards, stop handling |

---

## Configuration

- **In-Process Orchestrator**: User messages run via `asyncio.create_task` in ASGI process
- **Task Queue**: Django-Q with Redis broker for ticket execution and completion events
- **Channel Layer**: Redis-backed Django Channels (`USE_REDIS_CHANNELS=True` required for cross-process)
- **LLM Models**: Configured in `config/llm_models.json`
- **API Keys**: User-specific in `accounts.LLMApiKeys`, platform fallback via env vars
