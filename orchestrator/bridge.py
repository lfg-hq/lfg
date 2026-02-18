"""
Bridge between the existing ticket execution pipeline and the orchestrator.

When a ProjectTicket completes/fails through the old pipeline (AsyncTicketExecutor,
CLI endpoints), this module notifies the orchestrator so it can react —
e.g. report back to the user, dispatch follow-up tickets, etc.
"""
import logging

from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


def notify_orchestrator_ticket_status(ticket_id: int, status: str, summary: str = ""):
    """
    Notify the orchestrator that a ProjectTicket changed status.

    Called from:
      - tasks/task_definitions.py  (execute_ticket_chat_cli completion)
      - api/cli_endpoints.py       (CLI status callback)

    This is a sync function — safe to call from Django-Q workers or views.
    """
    try:
        from orchestrator.models import AgentRun
        from projects.models import ProjectTicket

        ticket = ProjectTicket.objects.select_related("project").get(id=ticket_id)

        # Find the most recent active AgentRun for this project
        active_run = (
            AgentRun.objects
            .filter(
                project=ticket.project,
                status__in=["executing", "waiting_on_user", "planning"],
            )
            .order_by("-created_at")
            .first()
        )

        if not active_run:
            logger.debug(
                f"No active orchestrator run for project {ticket.project_id} "
                f"— skipping notification for ticket #{ticket_id}"
            )
            return

        # Build a compact payload with key ticket info
        notes_tail = (ticket.notes or "")[-500:]  # last 500 chars of notes
        payload = {
            "ticket_id": ticket_id,
            "ticket_name": ticket.name,
            "status": status,
            "summary": summary or f"Ticket #{ticket_id} ({ticket.name}) is now {status}",
            "notes_tail": notes_tail,
            "queue_status": ticket.queue_status,
        }

        event_type = {
            "done": "project_ticket_completed",
            "completed": "project_ticket_completed",
            "failed": "project_ticket_failed",
            "blocked": "project_ticket_blocked",
        }.get(status, f"project_ticket_{status}")

        # Wake the orchestrator via Django-Q task
        from django_q.tasks import async_task
        async_task(
            "orchestrator.tasks.handle_orchestrator_event",
            str(active_run.id),
            event_type,
            payload,
            task_name=f"orch-bridge-{event_type}-ticket-{ticket_id}",
        )

        logger.info(
            f"[BRIDGE] Notified orchestrator run {active_run.id} "
            f"about ticket #{ticket_id} → {event_type}"
        )

    except Exception as e:
        # Never let the bridge crash the caller
        logger.error(f"[BRIDGE] Failed to notify orchestrator for ticket #{ticket_id}: {e}", exc_info=True)
