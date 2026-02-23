"""
Central Orchestrator Agent — streaming-first.

Event-driven: wakes when a user message arrives, a ticket completes/fails/blocks,
or the user answers a question.  Uses tool calls to coordinate work — it does NOT
implement tasks itself.

Text tokens are forwarded to the WebSocket as they arrive from the LLM so the
user sees real-time streaming.  For lfg_file tool calls, the ``content`` field
value is extracted from the streaming JSON arguments and forwarded as file_stream
notifications so the user sees the document being written in real time.
"""
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer

from orchestrator.models import AgentRun, TicketExecution
from orchestrator.llm import stream_orchestrator_llm
from orchestrator.prompts import ORCHESTRATOR_SYSTEM_PROMPT, get_orchestrator_tools
from orchestrator.tools import execute_orchestrator_tool

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 20

# Human-readable labels for tool-call notifications
_TOOL_LABELS = {
    # Orchestrator tools
    "triage_request": "Analyzing request",
    "knowledge_lookup": "Searching knowledge base",
    "check_pipeline_status": "Checking pipeline status",
    "create_plan": "Creating execution plan",
    "dispatch_ticket": "Dispatching ticket",
    "lfg_file": "Creating document",
    "ask_user": "Asking a question",
    "modify_plan": "Updating plan",
    # Product tools — project state
    "get_file_list": "Reading project files",
    "get_file_content": "Reading file content",
    "get_project_dashboard": "Loading project dashboard",
    "set_project_stack": "Setting project stack",
    # Product tools — documents
    "create_prd": "Creating PRD",
    "get_prd": "Reading PRD",
    "create_implementation": "Creating implementation plan",
    "get_implementation": "Reading implementation plan",
    "extract_features": "Extracting features",
    "extract_personas": "Extracting personas",
    # Product tools — tickets
    "create_tickets": "Creating tickets",
    "get_pending_tickets": "Checking pending tickets",
    "get_ticket_details": "Looking up ticket details",
    "update_ticket": "Updating ticket",
    "update_ticket_details": "Updating ticket details",
    "update_all_tickets": "Updating tickets",
    "queue_ticket_execution": "Queueing ticket execution",
    "schedule_tickets": "Scheduling tickets",
    "retry_ticket": "Retrying ticket",
    "send_ticket_message": "Messaging ticket agent",
    "get_ticket_execution_log": "Reading execution logs",
    # Product tools — codebase
    "search_existing_code": "Searching codebase",
    "get_codebase_summary": "Reading codebase summary",
    "ask_codebase": "Querying codebase",
    # Product tools — research
    "lookup_technology_specs": "Researching technology",
    # Product tools — preview
    "start_ticket_preview": "Starting ticket preview",
    "check_ticket_preview": "Checking ticket preview",
    # Product tools — environment & provisioning
    "set_env_var": "Setting environment variable",
    "provision_postgres_db": "Provisioning database",
    "get_project_env_vars": "Checking environment variables",
    "register_required_env_vars": "Registering required environment variables",
}

# Tools that should NOT show a tool activity indicator (internal/silent tools)
_SILENT_TOOLS = {"respond_to_user"}


class _LfgFileStreamTracker:
    """
    Extracts the ``content`` field value from streaming lfg_file JSON arguments.

    The LLM streams tool arguments as small JSON fragments via tool_delta events.
    This class accumulates those fragments, detects when the ``"content"`` field
    value begins, and yields new *unescaped* content characters on each ``feed()``
    call so they can be forwarded to the WebSocket in real time.
    """

    _ESCAPE = {
        '\\': '\\', '"': '"', 'n': '\n', 't': '\t',
        'r': '\r', '/': '/', 'b': '\b', 'f': '\f',
    }

    def __init__(self):
        self.buffer = ""
        self.content_started = False
        self.content_offset = 0   # index in buffer where content value starts
        self.sent_up_to = 0       # how far we've processed for streaming
        self.pending_backslash = False
        self.file_name: Optional[str] = None
        self.file_type: Optional[str] = None

    def feed(self, delta: str) -> str:
        """Feed a JSON argument delta.  Returns new unescaped content to stream."""
        self.buffer += delta

        if not self.content_started:
            # Look for the content field marker
            for marker in ('"content": "', '"content":"', '"content" : "'):
                idx = self.buffer.find(marker)
                if idx >= 0:
                    self.content_started = True
                    self.content_offset = idx + len(marker)
                    self.sent_up_to = self.content_offset
                    self._extract_metadata()
                    break
            if not self.content_started:
                return ""

        # Process new characters from sent_up_to to end of buffer
        out = []
        i = self.sent_up_to
        end = len(self.buffer)

        while i < end:
            ch = self.buffer[i]

            if self.pending_backslash:
                self.pending_backslash = False
                unescaped = self._ESCAPE.get(ch)
                if unescaped:
                    out.append(unescaped)
                elif ch == 'u' and i + 4 < end:
                    # \uXXXX unicode escape
                    hex_str = self.buffer[i + 1 : i + 5]
                    try:
                        out.append(chr(int(hex_str, 16)))
                    except ValueError:
                        out.append('\\u' + hex_str)
                    i += 4  # skip the 4 hex digits (loop increments by 1 more)
                elif ch == 'u':
                    # Incomplete unicode escape — wait for more data
                    self.sent_up_to = i - 1
                    return "".join(out)
                else:
                    out.append('\\')
                    out.append(ch)
                i += 1
                continue

            if ch == '\\':
                if i + 1 < end:
                    self.pending_backslash = True
                    i += 1
                    continue
                else:
                    # Backslash at end of buffer — wait for next delta
                    self.sent_up_to = i
                    return "".join(out)

            # Closing quote of the content value — stop
            if ch == '"':
                i += 1
                break

            out.append(ch)
            i += 1

        self.sent_up_to = i
        return "".join(out)

    def _extract_metadata(self):
        """Extract file_name and file_type from the JSON prefix before content."""
        prefix = self.buffer[: self.content_offset]
        for field, attr in (("name", "file_name"), ("file_type", "file_type")):
            for marker in (f'"{field}": "', f'"{field}":"'):
                idx = prefix.find(marker)
                if idx >= 0:
                    start = idx + len(marker)
                    end_q = prefix.find('"', start)
                    if end_q >= 0:
                        setattr(self, attr, prefix[start:end_q])
                        break


class OrchestratorAgent:
    """
    Maintains its own LLM conversation and uses tools to coordinate work.

    Public entry point:  ``await agent.handle_event(event_type, payload)``
    Streams text tokens directly to the WebSocket and returns user-facing
    messages produced by tool calls (questions, status updates, etc.).
    """

    def __init__(self, agent_run: AgentRun):
        self.agent_run = agent_run
        self.project = agent_run.project
        self.user = agent_run.user
        self.conversation = agent_run.conversation

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def handle_event(self, event_type: str, event_payload: dict) -> List[dict]:
        """
        Handle an event.  Text is streamed to the WebSocket in real time.

        Returns:
            Non-text user-facing messages (questions, status updates) that
            were produced by tool calls.  Text messages are already streamed.
        """
        # Extract provider info from payload (passed from consumer)
        provider_name = event_payload.pop("provider_name", None)
        selected_model = event_payload.pop("selected_model", None)

        # Resolve WebSocket group for streaming
        channel_layer = get_channel_layer()
        conversation_id = getattr(self.agent_run, "conversation_id", None)
        ws_group = f"conversation_{conversation_id}" if conversation_id else None

        # Build the event message
        context = await self._build_context()
        event_message = (
            f"{context}\n\n"
            f"EVENT: {event_type}\n"
            f"Payload: {json.dumps(event_payload, default=str)}"
        )

        # Load or initialise conversation history
        messages: list = list(self.agent_run.orchestrator_messages or [])
        if not messages or messages[0].get("role") != "system":
            messages.insert(0, {"role": "system", "content": ORCHESTRATOR_SYSTEM_PROMPT})
            chat_history = await self._load_chat_history()
            if chat_history:
                messages.insert(1, {
                    "role": "user",
                    "content": f"Recent conversation history for context:\n{chat_history}",
                })
                messages.insert(2, {
                    "role": "assistant",
                    "content": "Understood. I have the conversation context.",
                })

        messages.append({"role": "user", "content": event_message})

        all_tools = get_orchestrator_tools()

        # Collect non-text messages from tool calls (questions, status updates)
        user_messages: List[dict] = []
        # Track all streamed text for saving to conversation history
        all_streamed_text: List[str] = []

        # Agentic tool loop — REAL-TIME streaming.
        # Every round streams text_delta tokens directly to the WebSocket as
        # they arrive from the LLM.  Tool-call rounds typically produce little
        # or no user-facing text (just internal reasoning), so duplication is
        # avoided by breaking after respond_to_user is called.
        for _round in range(MAX_TOOL_ROUNDS):
            logger.info(f"[orchestrator] Round {_round} starting")

            # Stream tokens to the WebSocket in real time
            logger.info(f"[orchestrator] Round {_round}: calling LLM (stream_to_ws=True, ws_group={ws_group})")
            round_text, tool_calls, stop_reason = await self._stream_llm_round(
                messages, all_tools, self.user, provider_name, selected_model,
                channel_layer, ws_group,
            )

            if round_text:
                all_streamed_text.append(round_text)

            logger.info(
                f"[orchestrator] Round {_round}: text={len(round_text)} chars, "
                f"tool_calls={[tc['function']['name'] for tc in tool_calls]}"
            )

            # Build the assistant message for history
            assistant_msg: Dict[str, Any] = {"role": "assistant"}
            if tool_calls:
                content_blocks = []
                if round_text:
                    content_blocks.append({"type": "text", "text": round_text})
                for tc in tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": json.loads(tc["function"]["arguments"]),
                    })
                assistant_msg["content"] = content_blocks
            else:
                assistant_msg["content"] = round_text or ""
            messages.append(assistant_msg)

            # No tool calls = final response — already streamed live.
            if not tool_calls:
                break

            # Execute each tool call
            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                tool_args = json.loads(tc["function"]["arguments"])

                # Notify the user that a tool is being executed
                if channel_layer and ws_group and tool_name not in _SILENT_TOOLS:
                    label = _TOOL_LABELS.get(tool_name, tool_name.replace("_", " ").title())
                    await channel_layer.group_send(ws_group, {
                        "type": "agent_orchestrator_event",
                        "chunk": "",
                        "is_final": False,
                        "is_notification": True,
                        "notification_type": "orchestrator_tool_activity",
                        "tool_name": tool_name,
                        "tool_label": label,
                    })

                result, facing = await execute_orchestrator_tool(
                    tool_name, tool_args,
                    self.agent_run, self.project, self.user,
                )

                # Feed tool result back to the LLM
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": json.dumps(result, default=str),
                    }],
                })

                user_messages.extend(facing)

            # ask_user is terminal — break after executing it to avoid
            # the LLM going again and repeating itself.
            if any(tc["function"]["name"] == "ask_user" for tc in tool_calls):
                logger.info(
                    f"[orchestrator] Breaking after terminal tool in round {_round}"
                )
                break

        # Save streamed text as a conversation Message
        full_response_text = "\n\n".join(t for t in all_streamed_text if t.strip())
        logger.info(f"[orchestrator] Saving response: {len(full_response_text)} chars, rounds completed: {_round + 1}")
        await self._save_response_message(full_response_text)

        # Persist updated conversation history
        self.agent_run.orchestrator_messages = messages
        self.agent_run.updated_at = datetime.now()
        await sync_to_async(self.agent_run.save)(
            update_fields=["orchestrator_messages", "updated_at"]
        )

        return user_messages

    # ------------------------------------------------------------------
    # Streaming LLM round
    # ------------------------------------------------------------------

    async def _stream_llm_round(
        self,
        messages: list,
        tools: list,
        user,
        provider_name: Optional[str],
        selected_model: Optional[str],
        channel_layer,
        ws_group: Optional[str],
    ) -> tuple:
        """
        Run one LLM call.

        Text tokens are buffered locally — the caller (handle_event) decides
        whether to send them to the WebSocket based on whether the round
        produced tool calls.  lfg_file tool content is streamed live via
        file_stream notifications regardless.

        Returns:
            (full_text, tool_calls_list, stop_reason)
        """
        full_text_parts: List[str] = []
        tool_calls: List[dict] = []

        # Track lfg_file tool calls for live content streaming
        lfg_trackers: Dict[str, _LfgFileStreamTracker] = {}  # tool_id -> tracker

        async for event in stream_orchestrator_llm(
            messages, tools, user=user,
            provider_name=provider_name, selected_model=selected_model,
        ):
            etype = event["type"]

            if etype == "text_delta":
                text = event["text"]
                full_text_parts.append(text)

                # Stream text live to the WebSocket
                if channel_layer and ws_group:
                    await channel_layer.group_send(ws_group, {
                        "type": "agent_orchestrator_event",
                        "chunk": text,
                        "is_final": False,
                        "is_notification": True,
                        "notification_type": "orchestrator_text",
                    })

            elif etype == "tool_start":
                tool_id = event.get("id", "")
                tool_name = event.get("name", "")
                if tool_name == "lfg_file":
                    logger.info(f"[orchestrator] lfg_file tool_start — beginning live content stream (id={tool_id})")
                    lfg_trackers[tool_id] = _LfgFileStreamTracker()

            elif etype == "tool_delta":
                tool_id = event.get("id", "")
                tracker = lfg_trackers.get(tool_id)
                if tracker and channel_layer and ws_group:
                    delta = event.get("arguments_delta", "")
                    content_chunk = tracker.feed(delta)
                    if content_chunk:
                        await channel_layer.group_send(ws_group, {
                            "type": "ai_response_chunk",
                            "chunk": "",
                            "is_final": False,
                            "is_notification": True,
                            "notification_type": "file_stream",
                            "content_chunk": content_chunk,
                            "is_complete": False,
                            "file_name": tracker.file_name or "",
                            "file_type": tracker.file_type or "",
                        })

            elif etype == "tool_end":
                tool_id = event.get("id", "")
                tracker = lfg_trackers.pop(tool_id, None)
                if tracker and channel_layer and ws_group:
                    logger.info(
                        f"[orchestrator] lfg_file tool_end — sending stream-complete "
                        f"(file_name={tracker.file_name}, file_type={tracker.file_type})"
                    )
                    await channel_layer.group_send(ws_group, {
                        "type": "ai_response_chunk",
                        "chunk": "",
                        "is_final": False,
                        "is_notification": True,
                        "notification_type": "file_stream",
                        "content_chunk": "",
                        "is_complete": True,
                        "file_name": tracker.file_name or "",
                        "file_type": tracker.file_type or "",
                    })

            elif etype == "done":
                tool_calls = event.get("tool_calls", [])
                stop_reason = event.get("stop_reason", "stop")
                done_text = event.get("text", "")
                if not full_text_parts and done_text:
                    full_text_parts.append(done_text)
                return "".join(full_text_parts), tool_calls, stop_reason

        # If we exit without a done event (shouldn't happen), return what we have
        return "".join(full_text_parts), [], "stop"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _load_chat_history(self) -> str:
        """Load recent messages from the conversation for context."""
        if not self.conversation:
            return ""
        from chat.models import Message
        recent = await sync_to_async(
            lambda: list(
                Message.objects.filter(conversation=self.conversation)
                .order_by('-created_at')[:15]
            )
        )()
        recent.reverse()
        lines = []
        for msg in recent:
            content = (msg.content or "").strip()
            if not content:
                continue
            role = "User" if msg.role == "user" else "Assistant"
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    async def _save_response_message(self, text: str):
        """Save the orchestrator's user-facing response as a Message in the conversation."""
        if not self.conversation or not text.strip():
            return
        from chat.models import Message
        await sync_to_async(Message.objects.create)(
            conversation=self.conversation,
            role="assistant",
            content=text,
        )

    async def _build_context(self) -> str:
        """Build a compact context string with current orchestrator state."""
        executions = await sync_to_async(
            lambda: list(
                TicketExecution.objects.filter(agent_run=self.agent_run)
                .values("id", "title", "status", "sequence_number",
                        "blocked_reason", "result", "execution_type")
            )
        )()

        context = {
            "project_id": str(
                self.project.project_id
                if hasattr(self.project, "project_id") else self.project.id
            ),
            "run_status": self.agent_run.status,
            "run_type": self.agent_run.run_type,
            "ticket_executions": executions,
            "plan": self.agent_run.plan,
        }
        return f"Orchestrator state:\n```json\n{json.dumps(context, indent=2, default=str)}\n```"
