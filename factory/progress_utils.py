import asyncio
import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)

async def send_tool_progress(conversation_id, tool_name, progress_message, progress_percentage=None):
    """
    Send progress updates for tool execution through WebSocket
    
    Args:
        conversation_id: ID of the current conversation
        tool_name: Name of the tool being executed
        progress_message: Human-readable progress message
        progress_percentage: Optional percentage (0-100) for progress bar
    """
    channel_layer = get_channel_layer()
    if channel_layer and conversation_id:
        try:
            # Get the user from the conversation to determine the correct room group
            from chat.models import Conversation
            from asgiref.sync import sync_to_async
            
            conversation = await sync_to_async(
                lambda: Conversation.objects.select_related('user').get(id=conversation_id)
            )()
            
            if conversation and conversation.user:
                # Match the format in ChatConsumer: chat_{username}
                room_name = f"chat_{conversation.user.username}"
                # Sanitize the room name as done in ChatConsumer
                import re
                room_group_name = re.sub(r'[^a-zA-Z0-9._-]', '_', room_name)
                
                logger.debug(f"Sending tool progress to room: {room_group_name}")
                
                progress_data = {
                    'type': 'tool_progress',
                    'tool_name': tool_name,
                    'message': progress_message,
                    'progress_percentage': progress_percentage,
                    'is_progress': True
                }
                
                await channel_layer.group_send(
                    room_group_name,
                    {
                        'type': 'tool_progress_update',
                        **progress_data
                    }
                )
                logger.debug(f"Tool progress sent successfully: {tool_name} - {progress_message}")
            else:
                logger.error(f"Could not find user for conversation {conversation_id}")
        except Exception as e:
            logger.error(f"Error sending tool progress: {e}")

# Synchronous wrapper for non-async contexts
def send_tool_progress_sync(conversation_id, tool_name, progress_message, progress_percentage=None):
    """Synchronous wrapper for send_tool_progress"""
    async_to_sync(send_tool_progress)(
        conversation_id, tool_name, progress_message, progress_percentage
    )