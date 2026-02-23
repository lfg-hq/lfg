"""
Orchestrator tool implementations.

Each tool returns:
    (result_for_llm: dict, user_facing_messages: list)

result_for_llm goes back into the orchestrator's conversation.
user_facing_messages get streamed to the user via WebSocket.
"""
import json
import logging
from datetime import datetime
from typing import Tuple, List, Dict, Any

from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer

from orchestrator.models import AgentRun, TicketExecution, AgentEvent
from orchestrator.events import publish_event

logger = logging.getLogger(__name__)


async def execute_orchestrator_tool(
    tool_name: str,
    tool_args: dict,
    agent_run: AgentRun,
    project,
    user,
) -> Tuple[dict, List[dict]]:
    """Route tool calls to their implementations."""

    handlers = {
        "triage_request": handle_triage,
        "respond_to_user": handle_respond_to_user,
        "ask_user": handle_ask_user,
        "create_plan": handle_create_plan,
        "dispatch_ticket": handle_dispatch_ticket,
        "knowledge_lookup": handle_knowledge_lookup,
        "check_pipeline_status": handle_check_pipeline_status,
        "modify_plan": handle_modify_plan,
        "lfg_file": handle_lfg_file,
    }

    handler = handlers.get(tool_name)
    if not handler:
        # Fall through to existing product tool executor
        return await _execute_product_tool(tool_name, tool_args, agent_run, project)

    try:
        return await handler(tool_args, agent_run, project, user)
    except Exception as e:
        logger.error(f"Error executing orchestrator tool {tool_name}: {e}", exc_info=True)
        return {"error": str(e)}, []


async def _execute_product_tool(tool_name, tool_args, agent_run, project):
    """Execute an existing product tool (get_project_dashboard, get_ticket_details, etc.)."""
    try:
        from factory.tool_execution import execute_tool_call

        # Resolve project_id (UUID string)
        project_id = str(getattr(project, "project_id", None) or getattr(project, "id", None))
        conversation_id = getattr(agent_run, "conversation_id", None)

        result_content, notification_data, yielded_chunks = await execute_tool_call(
            tool_name,
            json.dumps(tool_args),
            project_id,
            conversation_id,
        )

        return {"result": result_content}, []
    except Exception as e:
        logger.error(f"Error executing product tool {tool_name}: {e}", exc_info=True)
        return {"error": str(e)}, []


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

async def handle_triage(args, agent_run, project, user):
    classification = args["classification"]
    agent_run.run_type = classification
    agent_run.status = "executing"
    await sync_to_async(agent_run.save)(update_fields=["run_type", "status", "updated_at"])

    await publish_event(agent_run, "run_started", {
        "classification": classification,
        "reasoning": args.get("reasoning", ""),
    })

    return {
        "status": "triaged",
        "classification": classification,
        "instruction": f"Request classified as '{classification}'. Proceed accordingly.",
    }, []


async def handle_respond_to_user(args, agent_run, project, user):
    message = args["message"]
    user_messages = [{"type": "text", "content": message}]

    if args.get("include_status"):
        status = await _get_pipeline_status(agent_run)
        user_messages.append({"type": "status_update", "content": status})

    # If this is a direct response (not part of an ongoing pipeline), mark run completed
    if agent_run.run_type in ("direct_response", None, ""):
        agent_run.status = "completed"
        await sync_to_async(agent_run.save)(update_fields=["status", "updated_at"])

    return {"status": "sent"}, user_messages


async def handle_ask_user(args, agent_run, project, user):
    ticket_id = args.get("ticket_execution_id")

    if ticket_id:
        ticket = await sync_to_async(TicketExecution.objects.get)(id=ticket_id)
        ticket.status = "blocked"
        ticket.blocked_reason = "Waiting for user response"
        ticket.blocked_question = args["question"]
        await sync_to_async(ticket.save)(
            update_fields=["status", "blocked_reason", "blocked_question"]
        )

    agent_run.status = "waiting_on_user"
    await sync_to_async(agent_run.save)(update_fields=["status", "updated_at"])

    await publish_event(
        agent_run, "user_question",
        {
            "question": args["question"],
            "context": args["context"],
            "ticket_execution_id": ticket_id,
            "options": args.get("options", []),
        },
        requires_user_action=True,
        ticket_execution=ticket_id,
    )

    return {"status": "question_sent", "waiting": True}, [{
        "type": "question",
        "content": args["question"],
        "context": args["context"],
        "options": args.get("options", []),
        "ticket_execution_id": ticket_id,
    }]


async def handle_create_plan(args, agent_run, project, user):
    tickets_data = args["tickets"]
    created_tickets = []

    for i, td in enumerate(tickets_data):
        ticket = await sync_to_async(TicketExecution.objects.create)(
            agent_run=agent_run,
            title=td["title"],
            description=td["description"],
            execution_type=td["execution_type"],
            sequence_number=i,
            worker_context={
                "acceptance_criteria": td.get("acceptance_criteria", []),
            },
            status="queued",
        )
        created_tickets.append({
            "id": str(ticket.id),
            "title": ticket.title,
            "index": i,
            "depends_on_indices": td.get("depends_on_indices", []),
        })

    # Second pass — wire up dependencies
    for info in created_tickets:
        dep_indices = info.get("depends_on_indices", [])
        if dep_indices:
            ticket = await sync_to_async(TicketExecution.objects.get)(id=info["id"])
            for dep_idx in dep_indices:
                if 0 <= dep_idx < len(created_tickets):
                    dep = await sync_to_async(TicketExecution.objects.get)(
                        id=created_tickets[dep_idx]["id"]
                    )
                    await sync_to_async(ticket.depends_on.add)(dep)

    # Mark tickets with no deps as "ready"
    for info in created_tickets:
        if not info.get("depends_on_indices"):
            ticket = await sync_to_async(TicketExecution.objects.get)(id=info["id"])
            ticket.status = "ready"
            await sync_to_async(ticket.save)(update_fields=["status"])

    agent_run.plan = {"goal": args["goal"], "tickets": created_tickets}
    agent_run.status = "executing"
    await sync_to_async(agent_run.save)(update_fields=["plan", "status", "updated_at"])

    await publish_event(agent_run, "plan_created", {
        "goal": args["goal"],
        "ticket_count": len(created_tickets),
        "tickets": created_tickets,
    })

    # User-facing summary
    lines = [f"**Plan created: {args['goal']}**\n"]
    for t in created_tickets:
        deps = t.get("depends_on_indices", [])
        dep_str = f" (after #{', #'.join(str(d + 1) for d in deps)})" if deps else ""
        lines.append(f"  {t['index'] + 1}. {t['title']}{dep_str}")

    return {
        "status": "plan_created",
        "tickets": created_tickets,
        "ready_tickets": [
            t["id"] for t in created_tickets if not t.get("depends_on_indices")
        ],
    }, [{"type": "text", "content": "\n".join(lines)}]


async def handle_dispatch_ticket(args, agent_run, project, user):
    ticket_id = args["ticket_execution_id"]
    # LLM may pass a TicketExecution UUID or a ProjectTicket integer ID — handle both
    try:
        ticket = await sync_to_async(TicketExecution.objects.get)(id=ticket_id)
    except (TicketExecution.DoesNotExist, Exception):
        # Fall back: look up by ProjectTicket FK
        ticket = await sync_to_async(
            TicketExecution.objects.filter(ticket_id=ticket_id).first
        )()
        if not ticket:
            return {"error": f"No TicketExecution found for ID '{ticket_id}'"}, []

    if ticket.status != "ready":
        return {"error": f"Ticket is not ready (status: {ticket.status})"}, []

    # Gather results from completed dependencies
    dep_results = {}
    dependencies = await sync_to_async(
        lambda: list(
            ticket.depends_on.filter(status="completed").values("id", "title", "result")
        )
    )()
    for dep in dependencies:
        dep_results[str(dep["id"])] = dep["result"]

    worker_context = {
        **ticket.worker_context,
        "dependency_results": dep_results,
        "additional_context": args.get("additional_context", {}),
        "project_id": str(
            project.project_id if hasattr(project, "project_id") else project.id
        ),
        "agent_run_id": str(agent_run.id),
    }

    ticket.status = "running"
    ticket.started_at = datetime.now()
    ticket.worker_context = worker_context
    await sync_to_async(ticket.save)(
        update_fields=["status", "started_at", "worker_context"]
    )

    # Dispatch to Django-Q
    from django_q.tasks import async_task
    q_task_id = await sync_to_async(async_task)(
        "orchestrator.workers.execute_ticket",
        str(ticket.id),
        task_name=f"ticket-{ticket.id}",
    )

    ticket.task_id = str(q_task_id)
    await sync_to_async(ticket.save)(update_fields=["task_id"])

    await publish_event(
        agent_run, "ticket_dispatched",
        {
            "ticket_execution_id": str(ticket.id),
            "title": ticket.title,
            "execution_type": ticket.execution_type,
        },
        ticket_execution=ticket,
    )

    return {
        "status": "dispatched",
        "ticket_id": str(ticket.id),
    }, [{"type": "text", "content": f"Dispatching: **{ticket.title}**..."}]


async def handle_knowledge_lookup(args, agent_run, project, user):
    query = args["query"]
    sources = args["sources"]
    results = {}

    for source in sources:
        if source == "project_docs":
            from projects.models import ProjectFile
            docs = await sync_to_async(
                lambda: list(
                    ProjectFile.objects.filter(project=project)
                    .values("id", "name", "file_type")[:10]
                )
            )()
            results["project_docs"] = docs

        elif source == "ticket_history":
            from projects.models import ProjectTicket
            tickets = await sync_to_async(
                lambda: list(
                    ProjectTicket.objects.filter(project=project)
                    .values("id", "name", "description", "status")[:20]
                )
            )()
            results["ticket_history"] = tickets

        elif source == "codebase":
            try:
                from codebase_index.models import CodebaseFile
                files = await sync_to_async(
                    lambda: list(
                        CodebaseFile.objects.filter(
                            project=project, content__icontains=query[:100]
                        ).values("file_path", "content")[:10]
                    )
                )()
                results["codebase"] = files
            except Exception:
                results["codebase"] = []

        elif source in ("google_drive", "notion"):
            results[source] = {"status": "not_implemented"}

        elif source == "web":
            results["web"] = {"status": "delegated", "note": "Use worker agent for web search"}

    return {"results": results, "query": query, "sources_searched": sources}, []


async def handle_check_pipeline_status(args, agent_run, project, user):
    status = await _get_pipeline_status(agent_run)
    return status, []


async def handle_modify_plan(args, agent_run, project, user):
    return {
        "status": "plan_modified",
        "action": args["action"],
        "reason": args["reason"],
    }, []


async def handle_lfg_file(args, agent_run, project, user):
    """
    Save a document as a ProjectFile.

    Content has already been streamed live to the user during the LLM round
    via tool_delta interception in _stream_llm_round().  This handler only
    persists the file and sends the saved notification so the frontend
    updates its file browser.
    """
    file_type = args["file_type"]
    file_name = args["name"]
    content = args["content"]

    project_id = str(
        getattr(project, "project_id", None) or getattr(project, "id", None)
    )
    conversation_id = getattr(agent_run, "conversation_id", None)
    channel_layer = get_channel_layer()

    # Save the file
    logger.info(f"[lfg_file] Saving file: type={file_type}, name={file_name}, size={len(content)}")
    from factory.ai_functions import save_file_from_stream
    save_result = await save_file_from_stream(content, project_id, file_type, file_name)
    logger.info(f"[lfg_file] Save result: {save_result.get('notification_type')}, file_id={save_result.get('file_id')}")

    # Send saved notification so frontend updates the file browser
    if channel_layer and conversation_id and save_result.get("is_notification"):
        group = f"conversation_{conversation_id}"
        await channel_layer.group_send(group, {
            "type": "ai_response_chunk",
            "chunk": "",
            "is_final": False,
            "conversation_id": conversation_id,
            **save_result,
        })

    return {
        "status": "file_created",
        "file_name": file_name,
        "file_type": file_type,
        "message": f"Document '{file_name}' has been created and saved. The user can already see it in the artifacts panel. Just say the document is ready — do NOT mention any IDs or repeat the content.",
    }, []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_pipeline_status(agent_run) -> dict:
    executions = await sync_to_async(
        lambda: list(
            TicketExecution.objects.filter(agent_run=agent_run)
            .order_by("sequence_number")
            .values(
                "id", "title", "status", "sequence_number",
                "blocked_reason", "execution_type",
                "started_at", "completed_at",
            )
        )
    )()

    return {
        "run_status": agent_run.status,
        "total_tickets": len(executions),
        "completed": sum(1 for e in executions if e["status"] == "completed"),
        "running": sum(1 for e in executions if e["status"] == "running"),
        "blocked": sum(1 for e in executions if e["status"] == "blocked"),
        "queued": sum(1 for e in executions if e["status"] in ("queued", "ready")),
        "tickets": executions,
    }
