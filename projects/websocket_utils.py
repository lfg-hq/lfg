"""
WebSocket utility functions for projects app.
"""
import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


def send_ticket_status_notification(ticket_id, status):
    """
    Send a WebSocket notification when a ticket status changes.

    Args:
        ticket_id: The ID of the ticket
        status: The new status of the ticket (e.g., 'done', 'in_progress', 'failed')
    """
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning("No channel layer configured, cannot send WebSocket notification")
            return

        group_name = f'ticket_logs_{ticket_id}'

        # Send the status update to all clients in the ticket's group
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'ticket_status_changed',
                'status': status,
                'ticket_id': ticket_id
            }
        )

        logger.info(f"Sent WebSocket notification for ticket {ticket_id} status change to: {status}")

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


async def async_send_ticket_status_notification(ticket_id, status):
    """
    Async version of send_ticket_status_notification.
    Use this when calling from async code.

    Args:
        ticket_id: The ID of the ticket
        status: The new status of the ticket
    """
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning("No channel layer configured, cannot send WebSocket notification")
            return

        group_name = f'ticket_logs_{ticket_id}'

        # Send the status update to all clients in the ticket's group
        await channel_layer.group_send(
            group_name,
            {
                'type': 'ticket_status_changed',
                'status': status,
                'ticket_id': ticket_id
            }
        )

        logger.info(f"Sent WebSocket notification for ticket {ticket_id} status change to: {status}")

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
