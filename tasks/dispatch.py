"""
Task Dispatch Utilities for the Async Executor.

Provides functions to:
- Queue tickets for execution
- Remove tickets from queue
- Get queue status and info
- Update ticket queue status in database

Usage:
    from tasks.dispatch import dispatch_tickets, remove_from_queue

    # Queue tickets
    dispatch_tickets(project_id=1, ticket_ids=[1, 2, 3], conversation_id=100)

    # Remove from queue
    remove_from_queue(project_id=1, ticket_id=2)
"""
import json
import logging
import redis
from typing import List, Dict, Any, Optional
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Redis keys
QUEUE_KEY = "lfg:ticket_execution_queue"
LOCK_PREFIX = "lfg:project_executing:"
CANCEL_FLAG_PREFIX = "lfg:ticket_cancelled:"

# Cache the Redis client
_redis_client = None


def get_redis_client() -> redis.Redis:
    """
    Get a Redis client for queue operations.

    Returns a cached connection for efficiency.
    """
    global _redis_client

    if _redis_client is None:
        redis_config = getattr(settings, 'Q_CLUSTER', {}).get('redis', {})

        _redis_client = redis.Redis(
            host=redis_config.get('host', 'localhost'),
            port=redis_config.get('port', 6379),
            db=redis_config.get('db', 0),
            password=redis_config.get('password'),
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True
        )

    return _redis_client


def dispatch_tickets(
    project_id: int,
    ticket_ids: List[int],
    conversation_id: Optional[int] = None
) -> bool:
    """
    Dispatch tickets for async execution.

    Pushes task to Redis queue and updates ticket statuses in database.

    Args:
        project_id: The project database ID
        ticket_ids: List of ticket IDs to execute (in order)
        conversation_id: Optional conversation ID for WebSocket notifications

    Returns:
        True if successfully queued, False on error
    """
    if not ticket_ids:
        logger.warning("[DISPATCH] No ticket_ids provided")
        return False

    client = get_redis_client()
    task_id = f"batch_{project_id}_{int(timezone.now().timestamp())}"

    task_data = {
        'project_id': project_id,
        'ticket_ids': ticket_ids,
        'conversation_id': conversation_id,
        'task_id': task_id,
        'queued_at': timezone.now().isoformat()
    }

    try:
        # Clear any stale cancellation flags for tickets being queued
        # This prevents "cancelled before execution" when re-queuing after a previous cancel
        for tid in ticket_ids:
            cancel_key = f"{CANCEL_FLAG_PREFIX}{tid}"
            client.delete(cancel_key)
        logger.info(f"[DISPATCH] Cleared cancellation flags for {len(ticket_ids)} tickets")

        # Push to Redis queue
        client.rpush(QUEUE_KEY, json.dumps(task_data))

        # Update ticket statuses in database
        from projects.models import ProjectTicket

        # Reset blocked/failed tickets to pending when re-queuing
        ProjectTicket.objects.filter(
            id__in=ticket_ids,
            status__in=['blocked', 'failed']
        ).update(status='pending')

        # Set queue status for all tickets
        ProjectTicket.objects.filter(id__in=ticket_ids).update(
            queue_status='queued',
            queued_at=timezone.now(),
            queue_task_id=task_id
        )

        # Send WebSocket notifications for each ticket
        from projects.websocket_utils import send_ticket_status_notification
        for ticket_id in ticket_ids:
            try:
                # Get current ticket status
                ticket = ProjectTicket.objects.filter(id=ticket_id).values('status').first()
                status = ticket['status'] if ticket else 'open'
                send_ticket_status_notification(ticket_id, status, queue_status='queued')
            except Exception as ws_error:
                logger.warning(f"[DISPATCH] Failed to send WebSocket notification for ticket {ticket_id}: {ws_error}")

        logger.info(
            f"[DISPATCH] Queued {len(ticket_ids)} tickets for project {project_id} "
            f"(task_id={task_id})"
        )
        return True

    except Exception as e:
        logger.error(f"[DISPATCH] Failed to queue tickets: {e}", exc_info=True)
        return False


def remove_from_queue(project_id: int, ticket_id: int) -> bool:
    """
    Remove a specific ticket from the queue.

    If the ticket is part of a batch, removes just that ticket from the batch.
    If it's the only ticket in the batch, removes the entire batch.

    Args:
        project_id: The project database ID
        ticket_id: The ticket ID to remove

    Returns:
        True if ticket was found and removed, False otherwise
    """
    client = get_redis_client()

    try:
        # Get all items in queue
        items = client.lrange(QUEUE_KEY, 0, -1)

        for item in items:
            data = json.loads(item)

            # Check if this task contains our ticket
            if (data.get('project_id') == project_id and
                ticket_id in data.get('ticket_ids', [])):

                # Remove this ticket from the batch
                data['ticket_ids'].remove(ticket_id)

                # Remove old item from queue
                client.lrem(QUEUE_KEY, 1, item)

                # Re-add if there are remaining tickets
                if data['ticket_ids']:
                    client.rpush(QUEUE_KEY, json.dumps(data))
                    logger.info(
                        f"[DISPATCH] Removed ticket #{ticket_id} from batch, "
                        f"{len(data['ticket_ids'])} remaining"
                    )
                else:
                    logger.info(
                        f"[DISPATCH] Removed ticket #{ticket_id}, batch now empty"
                    )

                # Update ticket status in database
                update_ticket_queue_status(ticket_id, 'none')

                return True

        logger.warning(
            f"[DISPATCH] Ticket #{ticket_id} not found in queue for project {project_id}"
        )
        return False

    except Exception as e:
        logger.error(f"[DISPATCH] Error removing from queue: {e}", exc_info=True)
        return False


def get_queue_length() -> int:
    """Get current number of batches in the queue."""
    try:
        client = get_redis_client()
        return client.llen(QUEUE_KEY)
    except Exception as e:
        logger.error(f"[DISPATCH] Error getting queue length: {e}")
        return 0


def get_total_queued_tickets() -> int:
    """Get total number of individual tickets across all batches."""
    try:
        client = get_redis_client()
        items = client.lrange(QUEUE_KEY, 0, -1)

        total = 0
        for item in items:
            data = json.loads(item)
            total += len(data.get('ticket_ids', []))

        return total
    except Exception as e:
        logger.error(f"[DISPATCH] Error counting tickets: {e}")
        return 0


def get_executing_projects() -> List[int]:
    """
    Get list of project IDs currently being executed.

    These are projects that have an active distributed lock.
    """
    try:
        client = get_redis_client()
        pattern = f"{LOCK_PREFIX}*"
        keys = list(client.scan_iter(match=pattern))
        return [int(k.replace(LOCK_PREFIX, '')) for k in keys]
    except Exception as e:
        logger.error(f"[DISPATCH] Error getting executing projects: {e}")
        return []


def get_project_queue_info(project_id: int) -> Dict[str, Any]:
    """
    Get queue information for a specific project.

    Args:
        project_id: The project database ID

    Returns:
        Dict with:
            - is_executing: True if project is currently being executed
            - queued_ticket_ids: List of ticket IDs waiting in queue
            - queue_position: Position in queue (1-indexed), or None if not queued
    """
    try:
        client = get_redis_client()

        # Check if project is currently executing
        lock_key = f"{LOCK_PREFIX}{project_id}"
        is_executing = bool(client.exists(lock_key))

        # Find queued tickets and position for this project
        queued_tickets = []
        queue_position = None

        items = client.lrange(QUEUE_KEY, 0, -1)
        for i, item in enumerate(items):
            data = json.loads(item)
            if data.get('project_id') == project_id:
                queued_tickets.extend(data.get('ticket_ids', []))
                if queue_position is None:
                    queue_position = i + 1  # 1-indexed

        return {
            'project_id': project_id,
            'is_executing': is_executing,
            'queued_ticket_ids': queued_tickets,
            'queue_position': queue_position,
            'total_queued': len(queued_tickets)
        }

    except Exception as e:
        logger.error(f"[DISPATCH] Error getting project queue info: {e}")
        return {
            'project_id': project_id,
            'is_executing': False,
            'queued_ticket_ids': [],
            'queue_position': None,
            'error': str(e)
        }


def get_queue_contents() -> List[Dict[str, Any]]:
    """
    Get full contents of the queue (for debugging/admin).

    Returns:
        List of task data dicts
    """
    try:
        client = get_redis_client()
        items = client.lrange(QUEUE_KEY, 0, -1)
        return [json.loads(item) for item in items]
    except Exception as e:
        logger.error(f"[DISPATCH] Error getting queue contents: {e}")
        return []


def clear_queue() -> int:
    """
    Clear all items from the queue (admin function).

    Returns:
        Number of items removed
    """
    try:
        client = get_redis_client()
        length = client.llen(QUEUE_KEY)
        client.delete(QUEUE_KEY)
        logger.warning(f"[DISPATCH] Cleared queue ({length} items)")
        return length
    except Exception as e:
        logger.error(f"[DISPATCH] Error clearing queue: {e}")
        return 0


def force_release_project_lock(project_id: int) -> bool:
    """
    Force release a project lock (admin function for stuck locks).

    Use with caution - only when sure no executor is actually running.

    Returns:
        True if lock was released, False if no lock existed
    """
    try:
        client = get_redis_client()
        lock_key = f"{LOCK_PREFIX}{project_id}"
        result = client.delete(lock_key)
        if result:
            logger.warning(f"[DISPATCH] Force released lock for project {project_id}")
        return bool(result)
    except Exception as e:
        logger.error(f"[DISPATCH] Error releasing lock: {e}")
        return False


def update_ticket_queue_status(
    ticket_id: int,
    status: str,
    task_id: Optional[str] = None,
    send_websocket: bool = True
):
    """
    Update a ticket's queue status in the database.

    Args:
        ticket_id: The ticket ID
        status: New status ('none', 'queued', 'executing')
        task_id: Optional task ID (for 'queued' status)
        send_websocket: Whether to send WebSocket notification (default: True)
    """
    try:
        from projects.models import ProjectTicket

        updates = {'queue_status': status}

        if status == 'queued':
            updates['queued_at'] = timezone.now()
            if task_id:
                updates['queue_task_id'] = task_id
        elif status == 'none':
            updates['queued_at'] = None
            updates['queue_task_id'] = None

        ProjectTicket.objects.filter(id=ticket_id).update(**updates)
        logger.debug(f"[DISPATCH] Updated ticket #{ticket_id} queue_status={status}")

        # Send WebSocket notification
        if send_websocket:
            try:
                from projects.websocket_utils import send_ticket_status_notification
                ticket = ProjectTicket.objects.filter(id=ticket_id).values('status').first()
                ticket_status = ticket['status'] if ticket else 'open'
                send_ticket_status_notification(ticket_id, ticket_status, queue_status=status)
            except Exception as ws_error:
                logger.warning(f"[DISPATCH] Failed to send WebSocket notification: {ws_error}")

    except Exception as e:
        logger.error(f"[DISPATCH] Error updating ticket status: {e}", exc_info=True)


async def update_ticket_queue_status_async(
    ticket_id: int,
    status: str,
    task_id: Optional[str] = None,
    send_websocket: bool = True
):
    """
    Async version of update_ticket_queue_status for use in async contexts.

    Args:
        ticket_id: The ticket ID
        status: New status ('none', 'queued', 'executing')
        task_id: Optional task ID (for 'queued' status)
        send_websocket: Whether to send WebSocket notification (default: True)
    """
    from asgiref.sync import sync_to_async

    @sync_to_async
    def _update():
        from projects.models import ProjectTicket

        updates = {'queue_status': status}

        if status == 'queued':
            updates['queued_at'] = timezone.now()
            if task_id:
                updates['queue_task_id'] = task_id
        elif status == 'none':
            updates['queued_at'] = None
            updates['queue_task_id'] = None

        ProjectTicket.objects.filter(id=ticket_id).update(**updates)
        logger.debug(f"[DISPATCH] Updated ticket #{ticket_id} queue_status={status}")

        # Send WebSocket notification
        if send_websocket:
            try:
                from projects.websocket_utils import send_ticket_status_notification
                ticket = ProjectTicket.objects.filter(id=ticket_id).values('status').first()
                ticket_status = ticket['status'] if ticket else 'open'
                send_ticket_status_notification(ticket_id, ticket_status, queue_status=status)
            except Exception as ws_error:
                logger.warning(f"[DISPATCH] Failed to send WebSocket notification: {ws_error}")

    try:
        await _update()
    except Exception as e:
        logger.error(f"[DISPATCH] Error updating ticket status (async): {e}", exc_info=True)


def get_executor_status() -> Dict[str, Any]:
    """
    Get overall executor status.

    Returns:
        Dict with queue stats and executing projects
    """
    return {
        'queue_length': get_queue_length(),
        'total_queued_tickets': get_total_queued_tickets(),
        'executing_projects': get_executing_projects(),
        'executing_count': len(get_executing_projects())
    }


def force_reset_ticket_queue_status(project_id: int, ticket_id: int) -> Dict[str, Any]:
    """
    Force reset a ticket's queue status, regardless of current state.

    Use this when a ticket is stuck in 'queued' or 'executing' state
    due to executor crash or other issues.

    This will:
    1. Set a cancellation flag to signal running threads to stop
    2. Remove the ticket from Redis queue if present
    3. Reset the ticket's queue_status to 'none' in database
    4. Optionally release project lock if no other tickets are executing

    Args:
        project_id: The project database ID
        ticket_id: The ticket ID to reset

    Returns:
        Dict with operation results
    """
    result = {
        'ticket_id': ticket_id,
        'cancellation_flag_set': False,
        'removed_from_redis': False,
        'db_status_reset': False,
        'lock_released': False,
        'error': None
    }

    try:
        client = get_redis_client()

        # Step 0: Set cancellation flag to signal running executor thread
        cancel_key = f"{CANCEL_FLAG_PREFIX}{ticket_id}"
        client.setex(cancel_key, 3600, "1")  # 1 hour TTL
        result['cancellation_flag_set'] = True
        logger.info(f"[DISPATCH] Set cancellation flag for ticket #{ticket_id}")

        # Step 1: Try to remove from Redis queue if present
        items = client.lrange(QUEUE_KEY, 0, -1)
        for item in items:
            data = json.loads(item)
            if (data.get('project_id') == project_id and
                ticket_id in data.get('ticket_ids', [])):

                # Remove ticket from batch
                data['ticket_ids'].remove(ticket_id)
                client.lrem(QUEUE_KEY, 1, item)

                # Re-add batch if other tickets remain
                if data['ticket_ids']:
                    client.rpush(QUEUE_KEY, json.dumps(data))

                result['removed_from_redis'] = True
                logger.info(f"[DISPATCH] Force removed ticket #{ticket_id} from Redis queue")
                break

        # Step 2: Reset database status
        from projects.models import ProjectTicket
        updated = ProjectTicket.objects.filter(id=ticket_id).update(
            queue_status='none',
            queued_at=None,
            queue_task_id=None
        )
        result['db_status_reset'] = updated > 0

        # Step 3: ALWAYS release project lock when force stopping
        # This allows new tickets to be queued immediately
        # The running thread will check cancellation flag and exit gracefully
        lock_key = f"{LOCK_PREFIX}{project_id}"
        if client.exists(lock_key):
            client.delete(lock_key)
            result['lock_released'] = True
            logger.info(f"[DISPATCH] Released project lock for project {project_id}")

        # Step 4: Send WebSocket notification about the cancellation
        try:
            from projects.websocket_utils import send_ticket_status_notification
            ticket = ProjectTicket.objects.filter(id=ticket_id).values('status').first()
            ticket_status = ticket['status'] if ticket else 'open'
            send_ticket_status_notification(ticket_id, ticket_status, queue_status='none')
        except Exception as ws_error:
            logger.warning(f"[DISPATCH] Failed to send WebSocket notification: {ws_error}")

        logger.info(
            f"[DISPATCH] Force reset ticket #{ticket_id}: "
            f"redis={result['removed_from_redis']}, db={result['db_status_reset']}, "
            f"lock={result['lock_released']}"
        )

    except Exception as e:
        logger.error(f"[DISPATCH] Error force resetting ticket: {e}", exc_info=True)
        result['error'] = str(e)

    return result


def set_ticket_cancellation_flag(ticket_id: int, ttl: int = 3600) -> bool:
    """
    Set a cancellation flag for a ticket.

    This flag can be checked by running executor threads to stop execution early.
    The flag expires after TTL seconds to prevent stale flags.

    Args:
        ticket_id: The ticket ID to cancel
        ttl: Time-to-live in seconds (default 1 hour)

    Returns:
        True if flag was set successfully
    """
    try:
        client = get_redis_client()
        key = f"{CANCEL_FLAG_PREFIX}{ticket_id}"
        client.setex(key, ttl, "1")
        logger.info(f"[DISPATCH] Set cancellation flag for ticket #{ticket_id}")
        return True
    except Exception as e:
        logger.error(f"[DISPATCH] Error setting cancellation flag: {e}")
        return False


def is_ticket_cancelled(ticket_id: int) -> bool:
    """
    Check if a ticket has been cancelled.

    This should be called periodically by executor threads to check
    if they should stop execution.

    Args:
        ticket_id: The ticket ID to check

    Returns:
        True if ticket has been cancelled
    """
    try:
        client = get_redis_client()
        key = f"{CANCEL_FLAG_PREFIX}{ticket_id}"
        return bool(client.exists(key))
    except Exception as e:
        logger.error(f"[DISPATCH] Error checking cancellation flag: {e}")
        return False


def clear_ticket_cancellation_flag(ticket_id: int) -> bool:
    """
    Clear a ticket's cancellation flag.

    Call this when a ticket execution completes normally.

    Args:
        ticket_id: The ticket ID

    Returns:
        True if flag was cleared
    """
    try:
        client = get_redis_client()
        key = f"{CANCEL_FLAG_PREFIX}{ticket_id}"
        client.delete(key)
        return True
    except Exception as e:
        logger.error(f"[DISPATCH] Error clearing cancellation flag: {e}")
        return False


# Redis key for ticket chat queue
CHAT_QUEUE_KEY = "lfg:ticket_chat_queue"


def dispatch_ticket_chat(
    ticket_id: int,
    project_id: int,
    conversation_id: int,
    message: str
) -> bool:
    """
    Dispatch a ticket chat message for processing with standard API method.

    Args:
        ticket_id: The ticket ID
        project_id: The project ID
        conversation_id: The conversation ID for WebSocket notifications
        message: The user's chat message

    Returns:
        True if successfully queued
    """
    client = get_redis_client()

    task_data = {
        'type': 'ticket_chat',
        'ticket_id': ticket_id,
        'project_id': project_id,
        'conversation_id': conversation_id,
        'message': message,
        'queued_at': timezone.now().isoformat()
    }

    try:
        client.rpush(CHAT_QUEUE_KEY, json.dumps(task_data))
        logger.info(f"[DISPATCH] Queued ticket chat: ticket={ticket_id}, mode=api")
        return True
    except Exception as e:
        logger.error(f"[DISPATCH] Failed to queue ticket chat: {e}")
        return False


def dispatch_ticket_chat_cli(
    ticket_id: int,
    project_id: int,
    conversation_id: int,
    message: str,
    session_id: str
) -> bool:
    """
    Dispatch a ticket chat message for processing with Claude CLI --resume.

    Args:
        ticket_id: The ticket ID
        project_id: The project ID
        conversation_id: The conversation ID for WebSocket notifications
        message: The user's chat message
        session_id: The Claude CLI session ID to resume

    Returns:
        True if successfully queued
    """
    client = get_redis_client()

    task_data = {
        'type': 'ticket_chat_cli',
        'ticket_id': ticket_id,
        'project_id': project_id,
        'conversation_id': conversation_id,
        'message': message,
        'session_id': session_id,
        'queued_at': timezone.now().isoformat()
    }

    try:
        client.rpush(CHAT_QUEUE_KEY, json.dumps(task_data))
        logger.info(f"[DISPATCH] Queued ticket chat CLI: ticket={ticket_id}, session={session_id[:20]}...")
        return True
    except Exception as e:
        logger.error(f"[DISPATCH] Failed to queue ticket chat CLI: {e}")
        return False
