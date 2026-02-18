"""
Django-Q task entry points for the orchestrator.

These are invoked by Django-Q workers and bridge sync → async.
"""
import asyncio
import json
import logging

logger = logging.getLogger(__name__)


def handle_orchestrator_event(agent_run_id: str, event_type: str, payload: dict):
    """
    Wake the orchestrator to handle an event (ticket completed, failed, etc.).

    Called as a Django-Q task from workers and the ChatConsumer.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            _handle_event_async(agent_run_id, event_type, payload)
        )
    finally:
        loop.close()


async def _handle_event_async(agent_run_id, event_type, payload):
    from asgiref.sync import sync_to_async
    from orchestrator.models import AgentRun
    from orchestrator.agent import OrchestratorAgent
    from channels.layers import get_channel_layer

    agent_run = await sync_to_async(
        lambda: AgentRun.objects.select_related(
            "project", "user", "conversation"
        ).get(id=agent_run_id)
    )()

    channel_layer = get_channel_layer()
    conversation_id = getattr(agent_run, "conversation_id", None)

    logger.info(f"[tasks] Starting orchestrator for agent_run={agent_run_id}, event={event_type}, conversation={conversation_id}")

    try:
        orchestrator = OrchestratorAgent(agent_run)
        # handle_event() now streams text directly to the WebSocket.
        # It only returns non-text messages (questions, status updates).
        user_messages = await orchestrator.handle_event(event_type, payload)
        logger.info(f"[tasks] handle_event returned {len(user_messages)} user_messages")
    except Exception as e:
        logger.error(f"Orchestrator agent error: {e}", exc_info=True)
        # Agent didn't stream anything — send error directly
        user_messages = [{"type": "error", "content": f"Sorry, I encountered an error: {e}"}]
        if agent_run.conversation_id:
            from chat.models import Message
            await sync_to_async(Message.objects.create)(
                conversation_id=conversation_id,
                role="assistant",
                content=f"Sorry, I encountered an error: {e}",
            )

    if channel_layer and conversation_id:
        group = f"conversation_{conversation_id}"

        # Send only non-text messages (questions, status updates).
        # Text is already streamed directly by the agent via text_delta events.
        for msg in user_messages:
            msg_type = msg.get("type", "text")
            content = msg.get("content", "")

            if msg_type == "text":
                # Skip — already streamed by agent.py via text_delta
                continue

            await channel_layer.group_send(group, {
                "type": "agent_orchestrator_event",
                "chunk": content,
                "is_final": False,
                "is_notification": True,
                "notification_type": f"orchestrator_{msg_type}",
            })

        # Final signal
        logger.info(f"[tasks] Sending is_final signal to {group}")
        await channel_layer.group_send(group, {
            "type": "agent_orchestrator_event",
            "chunk": "",
            "is_final": True,
            "conversation_id": conversation_id,
        })

    return {"messages_sent": len(user_messages)}
