"""
Worker functions for Django-Q.

Each function executes a single TicketExecution using the existing
LLM + tool infrastructure, then publishes completion/failure events
back to the orchestrator.
"""
import json
import logging
from datetime import datetime

from orchestrator.models import TicketExecution
from orchestrator.events import publish_event

logger = logging.getLogger(__name__)


def execute_ticket(ticket_execution_id: str):
    """
    Django-Q entry point.  Runs synchronously (Django-Q workers are sync).
    Wraps the async implementation.
    """
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_execute_ticket_async(ticket_execution_id))
    except Exception as e:
        logger.error(f"Ticket execution failed: {e}", exc_info=True)
        loop.run_until_complete(_mark_failed(ticket_execution_id, str(e)))
        raise
    finally:
        loop.close()


async def _execute_ticket_async(ticket_execution_id: str):
    from asgiref.sync import sync_to_async

    ticket = await sync_to_async(
        lambda: TicketExecution.objects.select_related(
            "agent_run", "agent_run__project", "agent_run__user",
            "agent_run__conversation",
        ).get(id=ticket_execution_id)
    )()

    agent_run = ticket.agent_run

    await publish_event(agent_run, "ticket_started", {
        "ticket_execution_id": str(ticket.id),
        "title": ticket.title,
        "execution_type": ticket.execution_type,
    }, ticket_execution=ticket)

    try:
        # Build worker prompt
        system_prompt = _build_worker_prompt(ticket)
        task_message = _build_task_message(ticket)

        # Use the streaming LLM but consume all events to get the final result
        from orchestrator.llm import stream_orchestrator_llm
        tools = _get_worker_tools(ticket.execution_type)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task_message},
        ]

        # Consume the stream to get the final "done" event
        content = ""
        async for event in stream_orchestrator_llm(messages, tools, user=agent_run.user):
            if event["type"] == "done":
                content = event.get("text", "")
                break

        # Check for blocker markers
        if "__BLOCKED__" in content:
            blocked_info = _extract_blocked_info(content)
            ticket.status = "blocked"
            ticket.blocked_reason = blocked_info.get("reason", "Unknown")
            ticket.blocked_question = blocked_info.get("question")
            await sync_to_async(ticket.save)(
                update_fields=["status", "blocked_reason", "blocked_question"]
            )
            await publish_event(agent_run, "ticket_blocked", {
                "ticket_execution_id": str(ticket.id),
                "title": ticket.title,
                "reason": ticket.blocked_reason,
            }, ticket_execution=ticket)

            # Wake orchestrator
            _notify_orchestrator(agent_run, "ticket_blocked", {
                "ticket_execution_id": str(ticket.id),
            })
            return {"status": "blocked"}

        # Success
        ticket.status = "completed"
        ticket.completed_at = datetime.now()
        ticket.result = {"content": content[:10000]}
        await sync_to_async(ticket.save)(
            update_fields=["status", "completed_at", "result"]
        )

        await _ready_dependents(ticket)

        await publish_event(agent_run, "ticket_completed", {
            "ticket_execution_id": str(ticket.id),
            "title": ticket.title,
            "result_summary": content[:500],
        }, ticket_execution=ticket)

        _notify_orchestrator(agent_run, "ticket_completed", {
            "ticket_execution_id": str(ticket.id),
            "title": ticket.title,
        })

        return {"status": "completed", "ticket_id": str(ticket.id)}

    except Exception as e:
        logger.error(f"Worker failed on ticket {ticket.id}: {e}", exc_info=True)
        ticket.status = "failed"
        ticket.result = {"error": str(e)}
        await sync_to_async(ticket.save)(update_fields=["status", "result"])

        await publish_event(agent_run, "ticket_failed", {
            "ticket_execution_id": str(ticket.id),
            "error": str(e),
        }, ticket_execution=ticket)

        _notify_orchestrator(agent_run, "ticket_failed", {
            "ticket_execution_id": str(ticket.id),
            "error": str(e),
        })
        raise


def _notify_orchestrator(agent_run, event_type, payload):
    """Queue an orchestrator wake-up via Django-Q."""
    from django_q.tasks import async_task
    async_task(
        "orchestrator.tasks.handle_orchestrator_event",
        str(agent_run.id), event_type, payload,
        task_name=f"orch-{event_type}-{agent_run.id}",
    )


async def _ready_dependents(completed_ticket):
    """After a ticket completes, mark dependent tickets as ready if all deps are done."""
    from asgiref.sync import sync_to_async

    dependents = await sync_to_async(
        lambda: list(completed_ticket.blocks.filter(status="queued"))
    )()

    for dep in dependents:
        all_done = await sync_to_async(
            lambda t=dep: not t.depends_on.exclude(status="completed").exists()
        )()
        if all_done:
            dep.status = "ready"
            await sync_to_async(dep.save)(update_fields=["status"])
            logger.info(f"Ticket {dep.id} ({dep.title}) is now ready")


async def _mark_failed(ticket_execution_id, error):
    from asgiref.sync import sync_to_async
    ticket = await sync_to_async(TicketExecution.objects.get)(id=ticket_execution_id)
    ticket.status = "failed"
    ticket.result = {"error": error}
    await sync_to_async(ticket.save)(update_fields=["status", "result"])


def _build_worker_prompt(ticket):
    ctx = ticket.worker_context or {}
    return f"""You are a worker agent executing a specific task.

Ticket: {ticket.title}
Type: {ticket.execution_type}
Description: {ticket.description}

Context from prior work:
{json.dumps(ctx.get('dependency_results', {}), indent=2, default=str)}

Acceptance Criteria:
{json.dumps(ctx.get('acceptance_criteria', []), indent=2)}

RULES:
- Complete this task thoroughly.
- If you encounter a blocker, include __BLOCKED__{{"reason": "...", "question": "..."}}__BLOCKED__ in your response.
- Be thorough but focused — only work on this specific ticket.
"""


def _build_task_message(ticket):
    additional = (ticket.worker_context or {}).get("additional_context", {})
    return (
        f"Execute this ticket now:\n\n"
        f"Title: {ticket.title}\n"
        f"Description: {ticket.description}\n\n"
        f"Additional context: {json.dumps(additional, indent=2, default=str)}\n\n"
        f"Begin working on this task."
    )


def _get_worker_tools(execution_type):
    """Return the appropriate tool set for the execution type."""
    # Return empty for now — workers will use orchestrator LLM without
    # custom tools initially.  Wire in factory/ai_tools.py tool sets
    # when ready for full agentic worker loops.
    return []


def _extract_blocked_info(content):
    import re
    match = re.search(r'__BLOCKED__(.+?)__BLOCKED__', content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return {"reason": match.group(1)}
    return {"reason": "Unknown blocker"}
