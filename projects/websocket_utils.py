"""
WebSocket utility functions for projects app.
"""
import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


def send_ticket_status_notification(ticket_id, status, queue_status=None):
    """
    Send a WebSocket notification when a ticket status changes.

    Args:
        ticket_id: The ID of the ticket
        status: The new status of the ticket (e.g., 'done', 'in_progress', 'failed')
        queue_status: Optional queue status ('none', 'queued', 'executing')
    """
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning("No channel layer configured, cannot send WebSocket notification")
            return

        group_name = f'ticket_logs_{ticket_id}'

        message = {
            'type': 'ticket_status_changed',
            'status': status,
            'ticket_id': ticket_id
        }
        if queue_status is not None:
            message['queue_status'] = queue_status

        # Send the status update to all clients in the ticket's group
        async_to_sync(channel_layer.group_send)(group_name, message)

        logger.info(f"Sent WebSocket notification for ticket {ticket_id} status change to: {status}, queue_status: {queue_status}")

    except Exception as e:
        logger.error(f"Error sending WebSocket notification for ticket {ticket_id}: {e}")


def send_ticket_log_notification(ticket_id, log_data):
    """
    Send a WebSocket notification when a new ticket log is created.

    Args:
        ticket_id: The ID of the ticket
        log_data: Dictionary containing log information:
            - id: Log ID
            - command: The command that was executed
            - explanation: Explanation of the command (optional)
            - output: Command output (optional)
            - exit_code: Exit code (optional)
            - created_at: Timestamp (ISO format string)
    """
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning("No channel layer configured, cannot send WebSocket notification")
            return

        group_name = f'ticket_logs_{ticket_id}'

        # Send the log data to all clients in the ticket's group
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'ticket_log_created',
                'log_data': log_data
            }
        )

        logger.info(f"Sent WebSocket notification for new log on ticket {ticket_id}: log_id={log_data.get('id')}")

    except Exception as e:
        logger.error(f"Error sending WebSocket notification for ticket {ticket_id}: {e}")


async def async_send_ticket_status_notification(ticket_id, status, queue_status=None):
    """
    Async version of send_ticket_status_notification.
    Use this when calling from async code.

    Args:
        ticket_id: The ID of the ticket
        status: The new status of the ticket
        queue_status: Optional queue status ('none', 'queued', 'executing')
    """
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning("No channel layer configured, cannot send WebSocket notification")
            return

        group_name = f'ticket_logs_{ticket_id}'

        message = {
            'type': 'ticket_status_changed',
            'status': status,
            'ticket_id': ticket_id
        }
        if queue_status is not None:
            message['queue_status'] = queue_status

        # Send the status update to all clients in the ticket's group
        await channel_layer.group_send(group_name, message)

        logger.info(f"Sent WebSocket notification for ticket {ticket_id} status change to: {status}, queue_status: {queue_status}")

    except Exception as e:
        logger.error(f"Error sending WebSocket notification for ticket {ticket_id}: {e}")


async def async_send_ticket_log_notification(ticket_id, log_data):
    """
    Async version of send_ticket_log_notification.
    Use this when calling from async code.

    Args:
        ticket_id: The ID of the ticket
        log_data: Dictionary containing log information
    """
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning("No channel layer configured, cannot send WebSocket notification")
            return

        group_name = f'ticket_logs_{ticket_id}'

        # Send the log data to all clients in the ticket's group
        await channel_layer.group_send(
            group_name,
            {
                'type': 'ticket_log_created',
                'log_data': log_data
            }
        )

        logger.info(f"Sent WebSocket notification for new log on ticket {ticket_id}: log_id={log_data.get('id')}")

    except Exception as e:
        logger.error(f"Error sending WebSocket notification for ticket {ticket_id}: {e}")


# Workspace Setup Progress Steps
WORKSPACE_STEPS = {
    'checking_workspace': {'order': 1, 'label': 'Checking workspace'},
    'switching_branch': {'order': 2, 'label': 'Switching branch'},
    'downloading_dependencies': {'order': 3, 'label': 'Installing dependencies'},
    'clearing_cache': {'order': 4, 'label': 'Clearing cache'},
    'starting_server': {'order': 5, 'label': 'Starting dev server'},
    'assigning_proxy': {'order': 6, 'label': 'Assigning proxy URL'},
    'complete': {'order': 7, 'label': 'Complete'},
    'error': {'order': -1, 'label': 'Error'},
}


def send_workspace_progress(project_id, step, message=None, progress=None, error=None, extra_data=None):
    """
    Send a WebSocket notification for workspace setup progress.

    Args:
        project_id: The project ID (string UUID)
        step: One of WORKSPACE_STEPS keys
        message: Optional custom message
        progress: Optional progress percentage (0-100)
        error: Optional error message if step failed
        extra_data: Optional dict with additional data (branch name, url, etc.)
    """
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning("No channel layer configured, cannot send workspace progress notification")
            return

        # Group name for workspace progress updates
        group_name = f'workspace_progress_{project_id}'

        step_info = WORKSPACE_STEPS.get(step, {'order': 0, 'label': step})

        payload = {
            'type': 'workspace_progress_update',
            'project_id': str(project_id),
            'step': step,
            'step_label': step_info['label'],
            'step_order': step_info['order'],
            'total_steps': len(WORKSPACE_STEPS) - 2,  # Exclude 'complete' and 'error'
            'message': message or step_info['label'],
            'progress': progress,
            'error': error,
            'extra_data': extra_data or {},
        }

        async_to_sync(channel_layer.group_send)(group_name, payload)

        logger.info(f"[WORKSPACE_PROGRESS] project={project_id} step={step} message={message}")

    except Exception as e:
        logger.error(f"Error sending workspace progress notification: {e}")


async def async_send_workspace_progress(project_id, step, message=None, progress=None, error=None, extra_data=None):
    """
    Async version of send_workspace_progress.

    Args:
        project_id: The project ID (string UUID)
        step: One of WORKSPACE_STEPS keys
        message: Optional custom message
        progress: Optional progress percentage (0-100)
        error: Optional error message if step failed
        extra_data: Optional dict with additional data
    """
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning("No channel layer configured, cannot send workspace progress notification")
            return

        group_name = f'workspace_progress_{project_id}'

        step_info = WORKSPACE_STEPS.get(step, {'order': 0, 'label': step})

        payload = {
            'type': 'workspace_progress_update',
            'project_id': str(project_id),
            'step': step,
            'step_label': step_info['label'],
            'step_order': step_info['order'],
            'total_steps': len(WORKSPACE_STEPS) - 2,
            'message': message or step_info['label'],
            'progress': progress,
            'error': error,
            'extra_data': extra_data or {},
        }

        await channel_layer.group_send(group_name, payload)

        logger.info(f"[WORKSPACE_PROGRESS] project={project_id} step={step} message={message}")

    except Exception as e:
        logger.error(f"Error sending workspace progress notification: {e}")
