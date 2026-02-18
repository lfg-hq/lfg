"""
Event publishing for the orchestrator.

Persists events to AgentEvent model and broadcasts via Django Channels
for real-time WebSocket delivery to the user.
"""
import json
import logging

from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer

from orchestrator.models import AgentEvent

logger = logging.getLogger(__name__)


async def publish_event(
    agent_run,
    event_type: str,
    payload: dict,
    requires_user_action: bool = False,
    ticket_execution=None,
):
    """
    Publish an event: persist to DB and broadcast via Django Channels.

    Args:
        agent_run: The AgentRun instance this event belongs to.
        event_type: One of AgentEvent.EVENT_TYPE_CHOICES values.
        payload: Arbitrary JSON-serialisable dict with event details.
        requires_user_action: If True, the UI should prompt the user.
        ticket_execution: Optional TicketExecution instance (or its UUID).
    """
    # Resolve ticket_execution to an instance if a string/UUID was passed
    te_instance = None
    if ticket_execution:
        if isinstance(ticket_execution, str):
            from orchestrator.models import TicketExecution
            try:
                te_instance = await sync_to_async(
                    TicketExecution.objects.get
                )(id=ticket_execution)
            except TicketExecution.DoesNotExist:
                logger.warning(f"TicketExecution {ticket_execution} not found for event")
        else:
            te_instance = ticket_execution

    # Persist to DB
    event = await sync_to_async(AgentEvent.objects.create)(
        agent_run=agent_run,
        event_type=event_type,
        payload=payload,
        requires_user_action=requires_user_action,
        ticket_execution=te_instance,
    )

    # Broadcast via Django Channels
    channel_layer = get_channel_layer()
    if not channel_layer:
        return event

    event_msg = {
        "event_type": event_type,
        "payload": payload,
        "requires_user_action": requires_user_action,
        "event_id": str(event.id),
        "ticket_execution_id": str(te_instance.id) if te_instance else None,
    }

    # Broadcast to the orchestrator-specific group (for internal listeners)
    orchestrator_group = f"orchestrator_{agent_run.id}"
    try:
        await channel_layer.group_send(orchestrator_group, {
            "type": "orchestrator_event",
            **event_msg,
        })
    except Exception as e:
        logger.error(f"Error broadcasting to orchestrator group: {e}")

    # Broadcast to the conversation group (for WebSocket delivery to user)
    conversation_id = getattr(agent_run, 'conversation_id', None)
    if conversation_id:
        conversation_group = f"conversation_{conversation_id}"
        try:
            await channel_layer.group_send(conversation_group, {
                "type": "agent_orchestrator_event",
                **event_msg,
            })
        except Exception as e:
            logger.error(f"Error broadcasting to conversation group: {e}")

    return event
