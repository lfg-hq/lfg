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


# ---------------------------------------------------------------------------
# Preview smoke-test (runs in Q worker, non-blocking)
# ---------------------------------------------------------------------------

# Error patterns to scan for in HTML responses
_PREVIEW_ERROR_PATTERNS = [
    'Build Error',
    'Failed to compile',
    'Internal Server Error',
    'Unhandled Runtime Error',
    'Module not found',
    'SyntaxError',
    'TypeError',
    'ReferenceError',
    'Cannot find module',
    'ENOENT',
    'INTERNAL_SERVER_ERROR',
    'Application error',
    'This page could not be found',
]


def check_ticket_preview(ticket_id: int):
    """
    Fetch a ticket's preview URL and check for obvious errors.

    Publishes a 'preview_check_completed' event with the results so the
    orchestrator can react (e.g. send_ticket_message to fix errors).

    Runs as a Django-Q task — never blocks the orchestrator.
    """
    import requests as http_requests
    from projects.models import ProjectTicket
    from development.models import Sandbox
    from orchestrator.events import publish_ticket_event_sync

    try:
        ticket = ProjectTicket.objects.get(id=ticket_id)
        project = ticket.project
    except ProjectTicket.DoesNotExist:
        logger.warning(f"[preview-check] Ticket {ticket_id} not found")
        return

    # Find preview URL — ticket sandbox first, then any project sandbox
    proxy_url = None

    ticket_sandbox = Sandbox.objects.filter(
        mags_workspace_id__startswith=f'{ticket_id}-',
        workspace_type='ticket',
        proxy_url__isnull=False,
    ).exclude(proxy_url='').order_by('-updated_at').first()

    if ticket_sandbox:
        proxy_url = ticket_sandbox.proxy_url
    else:
        project_sandbox = Sandbox.objects.filter(
            project=project,
            proxy_url__isnull=False,
        ).exclude(proxy_url='').order_by('-updated_at').first()
        if project_sandbox:
            proxy_url = project_sandbox.proxy_url

    if not proxy_url:
        # No existing preview URL — try starting the dev server
        logger.info(f"[preview-check] No preview URL for ticket {ticket_id}, attempting to start dev server")
        try:
            from api.dev_server import start_dev_server_core
            user = project.owner
            result = start_dev_server_core(ticket, user)
            if result.get('success'):
                proxy_url = result.get('url')
                logger.info(f"[preview-check] Dev server started, got URL: {proxy_url}")
            else:
                error = result.get('error', 'unknown')
                logger.warning(f"[preview-check] Dev server failed to start: {error}")
                publish_ticket_event_sync(ticket_id, 'preview_check_completed', {
                    'ticket_id': ticket_id,
                    'ticket_title': ticket.name,
                    'has_preview': False,
                    'has_errors': True,
                    'errors': [f"Dev server failed to start: {error}"],
                })
                return
        except Exception as e:
            logger.error(f"[preview-check] Error starting dev server for ticket {ticket_id}: {e}", exc_info=True)
            publish_ticket_event_sync(ticket_id, 'preview_check_completed', {
                'ticket_id': ticket_id,
                'ticket_title': ticket.name,
                'has_preview': False,
                'has_errors': True,
                'errors': [f"Error starting dev server: {str(e)[:200]}"],
            })
            return

    if not proxy_url:
        # Still no URL after attempting server start (shouldn't happen, but be safe)
        logger.info(f"[preview-check] Still no preview URL for ticket {ticket_id}")
        publish_ticket_event_sync(ticket_id, 'preview_check_completed', {
            'ticket_id': ticket_id,
            'ticket_title': ticket.name,
            'has_preview': False,
            'message': 'No preview URL available for this ticket.',
        })
        return

    # Fetch the URL
    logger.info(f"[preview-check] Checking {proxy_url} for ticket {ticket_id}")
    errors = []
    status_code = None
    page_snippet = ''

    try:
        resp = http_requests.get(proxy_url, timeout=15, allow_redirects=True)
        status_code = resp.status_code
        body = resp.text[:10000]  # Cap at 10k chars for scanning
        page_snippet = body[:500]

        # Check HTTP status
        if status_code >= 500:
            errors.append(f"HTTP {status_code} server error")
        elif status_code >= 400:
            errors.append(f"HTTP {status_code} client error")

        # Scan body for error patterns
        for pattern in _PREVIEW_ERROR_PATTERNS:
            if pattern.lower() in body.lower():
                # Extract a snippet around the match for context
                idx = body.lower().index(pattern.lower())
                start = max(0, idx - 50)
                end = min(len(body), idx + len(pattern) + 200)
                snippet = body[start:end].strip()
                # Clean up HTML tags for readability
                import re
                snippet = re.sub(r'<[^>]+>', ' ', snippet)
                snippet = re.sub(r'\s+', ' ', snippet).strip()
                errors.append(f"{pattern}: ...{snippet}...")
                break  # One pattern match is enough context

    except http_requests.Timeout:
        errors.append("Preview URL timed out (15s)")
    except http_requests.ConnectionError:
        errors.append("Could not connect to preview URL")
    except Exception as e:
        errors.append(f"Error fetching preview: {str(e)[:200]}")

    has_errors = len(errors) > 0
    logger.info(f"[preview-check] Ticket {ticket_id}: status={status_code}, errors={len(errors)}")

    publish_ticket_event_sync(ticket_id, 'preview_check_completed', {
        'ticket_id': ticket_id,
        'ticket_title': ticket.name,
        'has_preview': True,
        'url': proxy_url,
        'status_code': status_code,
        'has_errors': has_errors,
        'errors': errors,
        'page_snippet': page_snippet[:300],
    })
