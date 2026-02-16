import json
import asyncio
import logging
import os
import base64
import uuid
from datetime import datetime
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.urls import reverse
from django.db import close_old_connections
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed
from chat.models import (
    Conversation,
    Message,
    ChatFile,
    ModelSelection,
    AgentRole
)
from projects.models import ProjectTicket
from factory.ai_providers import AIProvider
from factory.ai_providers import FileHandler
from factory.prompts import get_system_turbo_mode, \
                                    get_system_prompt_product, \
                                    get_system_prompt_design, \
                                    get_system_prompt_developer, \
                                    get_system_instant_mode
from factory.ai_tools import tools_code, tools_product, tools_design, tools_turbo, tools_instant
from chat.storage import ChatFileStorage
from factory.llm_config import get_model_provider_map

# Set up logger
logger = logging.getLogger(__name__)

MODEL_TO_PROVIDER = get_model_provider_map()


async def async_send_ticket_log_notification(ticket_id, log_data):
    """Backward-compatible async helper for legacy imports from chat.consumers."""
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning("No channel layer configured, cannot send ticket log notification")
            return

        await channel_layer.group_send(
            f'ticket_logs_{ticket_id}',
            {
                'type': 'ticket_log_created',
                'log_data': log_data
            }
        )
    except Exception as e:
        logger.error(f"Error sending ticket log notification for ticket {ticket_id}: {e}")


class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.heartbeat_task = None
        self.pending_message = None
        self.auto_save_task = None
        self.last_save_time = None
        self.message_save_lock = asyncio.Lock()  # Lock to prevent concurrent message saves
        self.conversation_group_name = None
    async def connect(self):
        """
        Handle WebSocket connection
        """
        connection_accepted = False

        try:
            # Clean up any stale database connections before starting
            await database_sync_to_async(close_old_connections)()

            # Get user from scope and ensure it's properly resolved
            lazy_user = self.scope["user"]
            
            # Convert UserLazyObject to actual User instance to avoid database field errors
            if hasattr(lazy_user, '_wrapped') and hasattr(lazy_user, '_setup'):
                # This is a LazyObject, force evaluation
                if lazy_user.is_authenticated:
                    # Get the actual user instance from database
                    User = get_user_model()
                    self.user = await database_sync_to_async(User.objects.get)(pk=lazy_user.pk)
                else:
                    self.user = lazy_user
            else:
                # Already a proper User instance
                self.user = lazy_user
            
            # Get project_id and token from query string if available
            query_string = self.scope.get('query_string', b'').decode()
            query_params = dict(param.split('=') for param in query_string.split('&') if '=' in param)
            project_id = query_params.get('project_id')
            token = query_params.get('token')

            if (not getattr(self.user, 'is_authenticated', False) or not self.user) and token:
                jwt_auth = JWTAuthentication()
                try:
                    validated_token = jwt_auth.get_validated_token(token)
                    self.user = await database_sync_to_async(jwt_auth.get_user)(validated_token)
                except (InvalidToken, AuthenticationFailed) as token_error:
                    logger.warning(f"Invalid JWT token provided for WebSocket connection: {token_error}")
                    self.user = lazy_user
                except Exception as token_error:
                    logger.error(f"Unexpected error validating JWT token: {token_error}")
                    self.user = lazy_user
            
            # Each user joins their own room based on their email and project_id
            if self.user.is_authenticated:
                email_safe = self.user.email.replace('@', '_at_').replace('.', '_')
                if project_id:
                    self.room_name = f"chat_{email_safe}_{project_id}"
                else:
                    self.room_name = f"chat_{email_safe}"
            else:
                self.room_name = "chat_anonymous"
                logger.warning("User is not authenticated, using anonymous chat room")
            
            # Create a sanitized group name for the channel layer
            # Django Channels group names can only contain ASCII alphanumerics, hyphens, underscores, or periods
            import re
            # Replace any invalid characters with underscores
            self.room_group_name = re.sub(r'[^a-zA-Z0-9._-]', '_', self.room_name)
            
            # Accept connection
            await self.accept()
            connection_accepted = True
            logger.info(f"WebSocket connection accepted for user {self.user} in room {self.room_group_name}")
            
            # Initialize properties
            self.conversation = None
            self.active_generation_task = None
            self.should_stop_generation = False
            
            # Start heartbeat after successful connection
            self.heartbeat_task = asyncio.create_task(self.heartbeat_loop())
            
            try:
                # Join room group
                await self.channel_layer.group_add(
                    self.room_group_name,
                    self.channel_name
                )
                logger.info(f"User {self.user} added to group {self.room_group_name}")
                self.using_groups = True
            except Exception as group_error:
                logger.error(f"Error adding to channel group: {str(group_error)}")
                self.using_groups = False
            
            # Load chat history if conversation_id is provided in query string
            conversation_id = query_params.get('conversation_id')
            
            if conversation_id:
                # Get existing conversation
                self.conversation = await self.get_conversation(conversation_id)
                
                # Send chat history to client
                if self.conversation:
                    messages = await self.get_chat_history()
                    await self.send(text_data=json.dumps({
                        'type': 'chat_history',
                        'messages': messages
                    }))
                    await self.join_conversation_group(self.conversation.id)
            
        except Exception as e:
            logger.error(f"Error in WebSocket connect: {str(e)}")
            # Only try to accept and send error if we haven't already accepted
            if not connection_accepted:
                try:
                    await self.accept()
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': f"Connection error: {str(e)}"
                    }))
                except Exception as inner_e:
                    logger.error(f"Could not accept WebSocket connection: {str(inner_e)}")
            else:
                # Connection already accepted, just send error
                try:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': f"Connection error: {str(e)}"
                    }))
                except Exception as inner_e:
                    logger.error(f"Could not send error message: {str(inner_e)}")
    
    async def disconnect(self, close_code):
        """
        Handle WebSocket disconnection
        """
        # Cancel heartbeat task
        if self.heartbeat_task:
            self.heartbeat_task.cancel()

        # Cancel any active generation task
        if hasattr(self, 'active_generation_task') and self.active_generation_task and not self.active_generation_task.done():
            self.should_stop_generation = True
            # Give it a moment to stop gracefully
            try:
                await asyncio.wait_for(self.active_generation_task, timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning("Active generation task did not stop gracefully")

        # Save any pending AI message
        if self.pending_message:
            await self.force_save_message()

        try:
            if hasattr(self, 'using_groups') and self.using_groups:
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
                logger.info(f"User {self.user} removed from group {self.room_group_name}")
            if self.conversation_group_name:
                await self.channel_layer.group_discard(
                    self.conversation_group_name,
                    self.channel_name
                )
                logger.info(f"User {self.user} removed from conversation group {self.conversation_group_name}")
        except Exception as e:
            logger.error(f"Error during disconnect: {str(e)}")
        finally:
            # CRITICAL: Close database connections to prevent leaks
            await database_sync_to_async(close_old_connections)()
    
    async def receive(self, text_data):
        """
        Receive message from WebSocket
        """
        try:
            # Periodically close stale connections
            await database_sync_to_async(close_old_connections)()

            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type', 'message')

            logger.info(f"=== RECEIVED WebSocket message ===")
            logger.info(f"Message type: {message_type}")
            logger.info(f"Full message: {text_data_json}")
            
            # Handle heartbeat acknowledgment
            if message_type == 'heartbeat_ack':
                return
                
            # Test notification sending
            if message_type == 'test_notification':
                logger.info("TEST NOTIFICATION REQUESTED")
                test_notification = {
                    'type': 'ai_chunk',
                    'chunk': '',
                    'is_final': False,
                    'is_notification': True,
                    'notification_type': 'features',
                    'early_notification': True,
                    'function_name': 'extract_features'
                }
                await self.send(text_data=json.dumps(test_notification))
                logger.info(f"Test notification sent: {test_notification}")
                return
                
            # Test execute_command notification
            if message_type == 'test_execute_command':
                logger.info("TEST EXECUTE_COMMAND NOTIFICATION REQUESTED")
                
                # Send early notification first
                early_notification = {
                    'type': 'ai_chunk',
                    'chunk': '',
                    'is_final': False,
                    'is_notification': True,
                    'notification_type': 'execute_command',
                    'early_notification': True,
                    'function_name': 'execute_command'
                }
                await self.send(text_data=json.dumps(early_notification))
                logger.info(f"Early execute_command notification sent: {early_notification}")
                
                # Wait a bit
                await asyncio.sleep(0.5)
                
                # Send some command output
                output_chunk = {
                    'type': 'ai_chunk',
                    'chunk': 'Command output: Successfully executed command\n',
                    'is_final': False
                }
                await self.send(text_data=json.dumps(output_chunk))
                
                # Send completion notification
                completion_notification = {
                    'type': 'ai_chunk',
                    'chunk': '',
                    'is_final': False,
                    'is_notification': True,
                    'notification_type': 'command_output',
                    'early_notification': False,
                    'function_name': 'execute_command'
                }
                await self.send(text_data=json.dumps(completion_notification))
                logger.info(f"Completion notification sent: {completion_notification}")
                return
                
            if message_type == 'message':
                user_message = text_data_json.get('message', '')
                conversation_id = text_data_json.get('conversation_id')
                project_id = text_data_json.get('project_id')
                file_data = text_data_json.get('file')  # Get file data if present
                mentioned_files = text_data_json.get('mentioned_files', {})  # Get mentioned files
                user_role = text_data_json.get('user_role')  # Get user role if present
                turbo_mode = text_data_json.get('turbo_mode', False)  # Get turbo mode state
                instant_mode = text_data_json.get('instant_mode', False)  # Get instant mode state
                canvas_id = text_data_json.get('canvas_id')  # Get canvas ID for design features
                logger.info(f"[receive] Message received - canvas_id: {canvas_id}, turbo_mode: {turbo_mode}, instant_mode: {instant_mode}")
                # file_id = text_data_json.get('file_id')  # Get file_id if present

                

                # logger.debug(f"File ID: {file_data.get('id')}")
                
                # Check if we have either a message or file data
                if not user_message and not file_data:
                    await self.send_error("Message cannot be empty")
                    return
                
                # Get or create conversation
                if conversation_id and not self.conversation:
                    self.conversation = await self.get_conversation(conversation_id)
                elif not conversation_id and self.conversation:
                    # Client explicitly sent no conversation_id (e.g. "New Chat")
                    # Reset so a new conversation is created
                    self.conversation = None

                if not self.conversation:
                    # Require a project_id to create a conversation
                    if not project_id:
                        await self.send_error("A project ID is required to create a conversation")
                        return
                    
                    # If message is empty but there's a file, use the filename as the title
                    conversation_title = user_message[:50] if user_message else f"File: {file_data.get('name', 'Untitled')}"
                    self.conversation = await self.create_conversation(conversation_title, project_id)
                    
                    # Check if conversation was created
                    if not self.conversation:
                        await self.send_error("Failed to create conversation. Please check your project ID.")
                        return
                    await self.join_conversation_group(self.conversation.id)
                else:
                    await self.join_conversation_group(self.conversation.id)
                
                # If the message is empty but there's a file, use a placeholder message
                if not user_message and file_data:
                    user_message = f"[Shared a file: {file_data.get('name', 'file')}]"
                
                
                
                # If file data is provided, save file reference
                if file_data:
                    logger.debug(f"Processing file data: {file_data}")
                    # file_info = await self.save_file_reference(file_data)
                    # if file_info:
                    #     logger.debug(f"File saved: {file_info['original_filename']}")
                    message = await self.save_message_with_file('user', user_message, file_data)

                else:
                    # Save user message
                    message = await self.save_message('user', user_message)
                
                # Reset stop flag
                self.should_stop_generation = False
                
                provider_name = settings.AI_PROVIDER_DEFAULT
                # Generate AI response in background task
                # Store the task so we can cancel it if needed
                self.active_generation_task = asyncio.create_task(
                    self.generate_ai_response(user_message, provider_name, project_id, user_role, turbo_mode, mentioned_files, canvas_id, instant_mode)
                )
            
            elif message_type == 'stop_generation':
                # Handle stop generation request
                conversation_id = text_data_json.get('conversation_id')
                
                # Set flag to stop generation
                self.should_stop_generation = True
                
                # Cancel the active task if it exists
                if self.active_generation_task and not self.active_generation_task.done():
                    logger.debug(f"Canceling active generation task for conversation {conversation_id}")
                    # We don't actually cancel the task as it may be in the middle of stream processing
                    # Instead, we set a flag that will be checked during stream processing
                
                # Save an indicator that generation was stopped
                if self.conversation:
                    await self.save_message('assistant', '*Generation stopped by user*')
                
                # Send stop confirmation to client
                await self.send(text_data=json.dumps({
                    'type': 'stop_confirmed'
                }))
                
            elif message_type == 'sync_state':
                # Handle state synchronization request
                conversation_id = text_data_json.get('conversation_id')
                
                # Check if we have an active generation task
                is_streaming = (
                    hasattr(self, 'active_generation_task') and 
                    self.active_generation_task and 
                    not self.active_generation_task.done()
                )
                
                # Send current state back to client
                await self.send(text_data=json.dumps({
                    'type': 'sync_state_response',
                    'is_streaming': is_streaming,
                    'conversation_id': conversation_id
                }))
                
                logger.debug(f"Sent sync state response: is_streaming={is_streaming}")
            
        except Exception as e:
            logger.error(f"Error processing received message: {str(e)}")
            await self.send_error(f"Error processing message: {str(e)}")
    
    async def chat_message(self, event):
        """
        Send message to WebSocket
        """
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['message'],
            'sender': event['sender']
        }))
    
    async def token_update_notification(self, event):
        """
        Send token usage update notification to WebSocket
        """
        await self.send(text_data=json.dumps({
            'type': 'token_usage_updated'
        }))
    
    async def ai_response_chunk(self, event):
        """
        Send AI response chunk to WebSocket
        """
        # logger.info(f"ai_response_chunk received event: {event}")
        
        # Create response data with all available properties
        response_data = {
            'type': 'ai_chunk',
            'chunk': event.get('chunk', ''),
            'is_final': event.get('is_final', False),
            'conversation_id': event.get('conversation_id'),
            'provider': event.get('provider'),
            'project_id': event.get('project_id')
        }
        
        # Check all possible notification fields
        notification_fields = ['is_notification', 'notification_type', 'early_notification', 'function_name', 'content_chunk', 'is_complete', 'file_id', 'file_name', 'file_type', 'prd_name', 'project_id', 'app_url', 'workspace_id', 'port']
        for field in notification_fields:
            if field in event:
                response_data[field] = event[field]
                # logger.info(f"Adding notification field {field}: {event[field]}")
                # Special logging for file_id
                if field == 'file_id':
                    logger.info(f"[AI_RESPONSE_CHUNK] Including file_id in response: {event[field]}")
        
        # Send the response to the client
        try:
            # logger.info(f"FINAL response_data being sent: {response_data}")
            await self.send(text_data=json.dumps(response_data))
            logger.info(f"Successfully sent {'notification' if response_data.get('is_notification') else 'chunk'} to client")
        except Exception as e:
            logger.error(f"Error sending response to client: {str(e)}")
    
    async def ai_chunk(self, event):
        """
        Temporary handler for ai_chunk messages - redirect to ai_response_chunk
        This method handles cases where ai_chunk messages accidentally get sent to the channel layer
        """
        logger.warning("ai_chunk message received on channel layer - this should use ai_response_chunk instead")
        # Redirect to the proper handler
        await self.ai_response_chunk(event)

    async def ticket_chat_message(self, event):
        """
        Send ticket chat message to WebSocket
        """
        logger.info(f"ticket_chat_message received: ticket_id={event.get('ticket_id')}, role={event.get('role')}")

        response_data = {
            'type': 'ticket_chat',
            'ticket_id': event.get('ticket_id'),
            'role': event.get('role'),
            'content': event.get('content', ''),
            'is_streaming': event.get('is_streaming', False)
        }

        try:
            await self.send(text_data=json.dumps(response_data))
            logger.info(f"Successfully sent ticket chat message to client")
        except Exception as e:
            logger.error(f"Error sending ticket chat message to client: {str(e)}")

    async def tool_progress_update(self, event):
        """
        Send tool progress update to WebSocket
        """
        await self.send(text_data=json.dumps({
            'type': 'tool_progress',
            'tool_name': event.get('tool_name'),
            'message': event.get('message'),
            'progress_percentage': event.get('progress_percentage'),
            'is_progress': True
        }))
    
    async def heartbeat_loop(self):
        """Send periodic heartbeat messages to keep connection alive"""
        while True:
            try:
                await asyncio.sleep(20)  # Send heartbeat every 20 seconds (reduced from 30)
                
                # Check if we're currently streaming
                is_streaming = (
                    hasattr(self, 'active_generation_task') and 
                    self.active_generation_task and 
                    not self.active_generation_task.done()
                )
                
                await self.send(text_data=json.dumps({
                    'type': 'heartbeat',
                    'timestamp': datetime.now().isoformat(),
                    'during_operation': is_streaming
                }))
                
                # If streaming, send more frequent heartbeats
                if is_streaming:
                    await asyncio.sleep(5)  # More frequent during streaming
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                break

    async def join_conversation_group(self, conversation_id):
        if not conversation_id or not hasattr(self, 'channel_layer') or not self.channel_layer:
            return
        group_name = f"conversation_{conversation_id}"
        if self.conversation_group_name == group_name:
            return
        try:
            if self.conversation_group_name:
                await self.channel_layer.group_discard(
                    self.conversation_group_name,
                    self.channel_name
                )
            await self.channel_layer.group_add(
                group_name,
                self.channel_name
            )
            self.conversation_group_name = group_name
            logger.info(f"User {self.user} joined conversation group {group_name}")
        except Exception as e:
            logger.error(f"Error joining conversation group {group_name}: {e}")
    
    async def generate_ai_response(self, user_message, provider_name, project_id=None, user_role=None, turbo_mode=False, mentioned_files=None, canvas_id=None, instant_mode=False):
        """
        Generate response from AI
        """
        # Store canvas_id for tool execution using context variable
        from factory.tool_execution import set_current_canvas_id
        self.canvas_id = canvas_id
        set_current_canvas_id(canvas_id)
        logger.info(f"[generate_ai_response] Setting canvas_id: {canvas_id}")

        # Also update conversation's design_canvas if canvas_id is provided
        if canvas_id and self.conversation:
            try:
                from projects.models import DesignCanvas
                canvas = await database_sync_to_async(
                    lambda: DesignCanvas.objects.filter(id=canvas_id).first()
                )()
                if canvas:
                    self.conversation.design_canvas = canvas
                    await database_sync_to_async(self.conversation.save)()
            except Exception as e:
                logger.warning(f"Could not link canvas to conversation: {e}")
        try:
            # Clean up stale connections at the start of AI generation
            await database_sync_to_async(close_old_connections)()
        except Exception as e:
            logger.error(f"Error closing old connections: {e}")

        # Send typing indicator
        try:
            if hasattr(self, 'using_groups') and self.using_groups:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'ai_response_chunk',
                        'chunk': '',
                        'is_final': False
                    }
                )
            else:
                await self.send(text_data=json.dumps({
                    'type': 'ai_chunk',
                    'chunk': '',
                    'is_final': False
                }))
        except Exception as e:
            logger.error(f"Error sending typing indicator: {str(e)}")
        
        # Get conversation history
        messages = await self.get_messages_for_ai()

        logger.debug(f"User Role: {user_role}")

        agent_role, created = await database_sync_to_async(AgentRole.objects.get_or_create)(
            user=self.user,
            defaults={'name': 'product_analyst'}
        )
        
        # Update turbo mode state in the agent role
        if agent_role.turbo_mode != turbo_mode:
            agent_role.turbo_mode = turbo_mode
            await database_sync_to_async(agent_role.save)()

        logger.debug(f"Agent Role: {agent_role.name}, Turbo Mode: {agent_role.turbo_mode}")
        user_role = agent_role.name

        # Check if instant mode is enabled first
        if instant_mode:
            logger.info(f"INSTANT MODE ENABLED for user {self.user.username}")
            system_prompt = await get_system_instant_mode()
            tools = tools_instant
        # Check if turbo mode is enabled
        elif agent_role.turbo_mode:
            logger.info(f"TURBO MODE ENABLED for user {self.user.username}")
            system_prompt = await get_system_turbo_mode()
            tools = tools_turbo  # Use product tools for turbo mode (includes create_tickets)
        elif user_role == "designer":
            system_prompt = await get_system_prompt_design()
            tools = tools_design
        elif user_role == "product_analyst":
            system_prompt = await get_system_prompt_product()
            tools = tools_product
        else:
            system_prompt = await get_system_prompt_developer()
            tools = tools_code
        # Add system message if not present
        if not any(msg["role"] == "system" for msg in messages):
            messages.insert(0, {
                "role": "system",
                # "content": await get_system_prompt()
                "content": system_prompt
            })

        # Inject existing designs context for design-related agents
        if canvas_id and (user_role in ["designer", "product_analyst"] or (agent_role and agent_role.turbo_mode)):
            existing_designs_context = await self.get_existing_designs_context(canvas_id)
            if existing_designs_context:
                # Add design context after system message
                messages.insert(1, {
                    "role": "system",
                    "content": existing_designs_context
                })
                logger.debug(f"Injected existing designs context for canvas {canvas_id}")

        try:
            model_selection = await database_sync_to_async(ModelSelection.objects.get)(user=self.user)
            selected_model = model_selection.selected_model
        except ModelSelection.DoesNotExist:
            # Create a default model selection if none exists
            model_selection = await database_sync_to_async(ModelSelection.objects.create)(
                user=self.user,
                selected_model=ModelSelection.DEFAULT_MODEL_KEY
            )
            selected_model = model_selection.selected_model

        provider_name = MODEL_TO_PROVIDER.get(selected_model, 'openai')
        
        # Get the project object if project_id is provided
        project = None
        if project_id:
            try:
                from projects.models import Project
                project = await database_sync_to_async(
                    lambda: Project.objects.get(project_id=project_id, owner=self.user)
                )()
            except Exception as e:
                logger.warning(f"Could not get project with id {project_id}: {e}")
        
        # Get the appropriate AI provider
        logger.debug(f"Creating provider with user: {self.user} (type: {type(self.user)}), conversation: {self.conversation}, project: {project}", 
                    extra={'easylogs_metadata': {'user_id': self.user.id if self.user else None}})
        provider = AIProvider.get_provider(provider_name, selected_model, user=self.user, conversation=self.conversation, project=project)
        
        # Debug log to verify settings
        logger.debug(f"Using provider: {provider_name}")
        logger.debug(f"Project ID: {project_id}")
        logger.debug(f"Conversation ID: {self.conversation.id if self.conversation else None}")
        logger.debug(f"Message count: {len(messages)}")
        
        try:
            # Generate streaming response
            full_response = ""

            # Process the stream in an async context - yield instantly for smoothest streaming
            async for content in self.process_ai_stream(provider, messages, project_id, tools, mentioned_files):
                
                # Check if generation should stop
                if self.should_stop_generation:
                    # Send stop message immediately
                    try:
                        await self.send(text_data=json.dumps({
                            'type': 'ai_chunk',
                            'chunk': "\n\n*Generation stopped by user*",
                            'is_final': False
                        }))
                    except Exception as e:
                        logger.error(f"Error sending stop message: {str(e)}")
                    
                    # Add the stop message to the full response
                    full_response += "\n\n*Generation stopped by user*"
                    
                    # Break out of the loop
                    break
                
                # Check if this is a notification
                if isinstance(content, str) and content.startswith("__NOTIFICATION__") and content.endswith("__NOTIFICATION__"):
                    # Parse and send notification
                    try:
                        notification_json = content[len("__NOTIFICATION__"):-len("__NOTIFICATION__")]
                        notification_data = json.loads(notification_json)
                        
                        # Send notification to client
                        notification_message = {
                            'chunk': '',
                            'is_final': False,
                            'is_notification': True,
                            'notification_type': notification_data.get('notification_type', 'features'),
                            'early_notification': notification_data.get('early_notification', False),
                            'function_name': notification_data.get('function_name', '')
                        }
                        
                        # Pass through file_id and related fields if present (for all notification types)
                        if notification_data.get('file_id'):
                            notification_message['file_id'] = notification_data.get('file_id')
                            notification_message['file_name'] = notification_data.get('file_name', '')
                            notification_message['file_type'] = notification_data.get('file_type', '')

                        # Pass through project_id if present
                        if notification_data.get('project_id'):
                            notification_message['project_id'] = notification_data.get('project_id')
                        
                        # Add additional fields for file_stream notifications
                        if notification_data.get('notification_type') == 'file_stream':
                            notification_message['content_chunk'] = notification_data.get('content_chunk', '')
                            notification_message['is_complete'] = notification_data.get('is_complete', False)
                            notification_message['file_type'] = notification_data.get('file_type', '')
                            notification_message['file_name'] = notification_data.get('file_name', '')
                            if notification_data.get('file_id'):
                                notification_message['file_id'] = notification_data.get('file_id')
                        
                        # Send notification directly via WebSocket (lower latency)
                        ws_message = {
                            'type': 'ai_chunk',
                            **notification_message
                        }
                        await self.send(text_data=json.dumps(ws_message))
                        
                        # Continue without adding to full_response
                        continue
                    except Exception as e:
                        logger.error(f"Error processing notification in generate_ai_response: {e}")
                        # Fall through to normal processing if error
                
                # Skip other notification formats from being added to the full response
                if isinstance(content, str) and content.startswith("{") and content.endswith("}"):
                    try:
                        data = json.loads(content)
                        if data.get('is_notification'):
                            logger.debug(f"Skipping JSON notification from full response")
                            continue
                    except:
                        pass  # Not JSON, treat as normal content
                
                full_response += content

                # Send chunk instantly - no batching for smoothest streaming
                try:
                    await self.send(text_data=json.dumps({
                        'type': 'ai_chunk',
                        'chunk': content,
                        'is_final': False
                    }))
                except Exception as e:
                    logger.error(f"Error sending AI chunk: {str(e)}")

            # Finalize any partial message or save the complete message
            if full_response:
                await self.finalize_streaming_message(full_response)
            
            # Update conversation title if it's new
            if self.conversation and (not self.conversation.title or self.conversation.title == str(self.conversation.id)):
                # Use AI to generate a title based on first messages
                try:
                    await self.generate_title_with_ai(user_message, full_response)
                except Exception as title_error:
                    logger.error(f"Error generating title: {title_error}")
                    # Fallback to simple title
                    await self.update_conversation_title(user_message[:50] if user_message else "New Conversation")
            
            # Get project_id if conversation is linked to a project
            if not project_id and self.conversation:
                project_id = await self.get_project_id()
                
            # Send message complete signal (direct send for lower latency)
            try:
                # Only send the final message if generation wasn't stopped
                if not self.should_stop_generation:
                    await self.send(text_data=json.dumps({
                        'type': 'ai_chunk',
                        'chunk': '',
                        'is_final': True,
                        'conversation_id': self.conversation.id if self.conversation else None,
                        'provider': provider_name,
                        'project_id': project_id
                    }))

                    # Send token usage update notification
                    await self.send(text_data=json.dumps({
                        'type': 'token_usage_updated'
                    }))
                else:
                    # For stopped generation, just send conversation metadata
                    await self.send(text_data=json.dumps({
                        'type': 'ai_chunk',
                        'chunk': None,
                        'is_final': True,
                        'conversation_id': self.conversation.id if self.conversation else None,
                        'provider': provider_name,
                        'project_id': project_id
                    }))
            except Exception as e:
                logger.error(f"Error sending completion signal: {str(e)}")
            
            # Clear the active task reference
            self.active_generation_task = None

            # Clean up database connections after generation completes
            await database_sync_to_async(close_old_connections)()

        except Exception as e:
            error_message = f"Sorry, I encountered an error: {str(e)}"
            # Only try to save error message if we have a conversation
            if self.conversation:
                try:
                    await self.save_message('assistant', error_message)
                except Exception as save_error:
                    logger.error(f"Error saving error message: {save_error}")
            
            try:
                # First send the error message as a chunk (direct send for lower latency)
                await self.send(text_data=json.dumps({
                    'type': 'ai_chunk',
                    'chunk': error_message,
                    'is_final': False
                }))

                # Then send the final signal to reset UI state
                await self.send(text_data=json.dumps({
                    'type': 'ai_chunk',
                    'chunk': '',
                    'is_final': True,
                    'conversation_id': self.conversation.id if self.conversation else None,
                    'provider': provider_name,
                    'project_id': project_id
                }))
            except Exception as inner_e:
                logger.error(f"Error sending error message: {str(inner_e)}")
                await self.send_error(error_message)
            
            # Clear the active task reference
            self.active_generation_task = None
    
    async def process_ai_stream(self, provider, messages, project_id, tools, mentioned_files=None):
        """
        Enhanced process_ai_stream with auto-save and file handling
        """
        logger.debug(f"Messages: {messages}")
        try:
            conversation_id = self.conversation.id if self.conversation else None
            
            # Process messages to handle files
            processed_messages = await self.prepare_messages_with_files(provider, messages)
            
            # Add mentioned files content to messages if any
            if mentioned_files:
                # Create a context message with file contents
                file_context_parts = []
                for file_id, file_info in mentioned_files.items():
                    file_name = file_info.get('name', 'Unknown')
                    file_content = file_info.get('content', '')
                    file_context_parts.append(f"=== File: {file_name} ===\n{file_content}\n")
                
                if file_context_parts:
                    # Add file context as a system message at the beginning
                    file_context_message = {
                        "role": "system",
                        "content": f"The user has referenced the following files in their message:\n\n{''.join(file_context_parts)}"
                    }
                    # Insert after the main system prompt (if exists)
                    if processed_messages and processed_messages[0].get('role') == 'system':
                        processed_messages.insert(1, file_context_message)
                    else:
                        processed_messages.insert(0, file_context_message)
            
            # Accumulate content - we save only after streaming completes for best performance
            accumulated_content = ""
            
            # Stream content directly from the now-async provider
            async for content in provider.generate_stream(processed_messages, project_id, conversation_id, tools):
                # Check if we should stop generation
                if self.should_stop_generation:
                    logger.debug("Stopping AI stream generation due to user request")
                    break
                    
                # Skip notification content from being saved to database
                # Check if this is a specially formatted notification string FIRST
                if isinstance(content, str) and content.startswith("__NOTIFICATION__") and content.endswith("__NOTIFICATION__"):
                    try:
                        # Extract the JSON between the markers
                        notification_json = content[len("__NOTIFICATION__"):-len("__NOTIFICATION__")]
                        # logger.debug("DETECTED SPECIALLY FORMATTED NOTIFICATION")
                        # logger.debug(f"Notification JSON: {notification_json}")
                        
                        notification_data = json.loads(notification_json)
                        # logger.debug(f"Parsed notification: {notification_data}")
                        
                        # Verify this is a notification
                        if notification_data.get('is_notification') and notification_data.get('notification_marker') == "__NOTIFICATION__":
                            # Check if this is an early notification
                            is_early = notification_data.get('early_notification', False)
                            function_name = notification_data.get('function_name', '')
                            # logger.debug(f"Is early notification: {is_early}")
                            # logger.debug(f"Function name: {function_name}")
                            
                            # Create notification message to send to client
                            notification_message = {
                                'chunk': '',  # No visible content
                                'is_final': False,
                                'is_notification': True,
                                'notification_type': notification_data.get('notification_type', 'features')
                            }
                            
                            # Add early notification flag and function name if present
                            if is_early:
                                notification_message['early_notification'] = True
                                notification_message['function_name'] = function_name
                            
                            # Pass through file_id and related fields for save notifications
                            if notification_data.get('file_id'):
                                notification_message['file_id'] = notification_data.get('file_id')
                                notification_message['file_name'] = notification_data.get('file_name', '')
                                notification_message['file_type'] = notification_data.get('file_type', '')
                                logger.info(f"[CONSUMER] Processing save notification with file_id: {notification_data.get('file_id')}, type: {notification_data.get('notification_type')}")
                            
                            # Yield the notification string so it can be handled in generate_ai_response
                            yield content
                            continue
                    except json.JSONDecodeError as e:
                        logger.error(f"Error parsing notification JSON: {e}")
                        # Continue to normal processing if JSON parsing fails
                    except Exception as e:
                        logger.error(f"Error processing notification: {e}")
                        # Continue to normal processing if there's any other error
                
                
                # Also still keep the old JSON detection method for backward compatibility
                # Check if this is a notification JSON
                elif isinstance(content, str) and content.startswith('{') and content.endswith('}'):
                    try:
                        logger.debug("POTENTIAL NOTIFICATION JSON DETECTED")
                        logger.debug(f"Raw chunk: {content}")
                        
                        notification_data = json.loads(content)
                        logger.debug(f"Parsed JSON: {notification_data}")
                        
                        if 'is_notification' in notification_data and notification_data['is_notification']:
                            logger.debug("This IS a valid notification!")
                            logger.debug(f"Notification type: {notification_data.get('notification_type', 'features')}")
                            
                            # Check if this is an early notification
                            is_early = notification_data.get('early_notification', False)
                            function_name = notification_data.get('function_name', '')
                            logger.debug(f"Is early notification__ 11: {is_early}")
                            logger.debug(f"Function name for early notification: {function_name}")
                            
                            # This is a notification - send it as a special message
                            notification_message = {
                                'chunk': '',  # No visible content
                                'is_final': False,
                                'is_notification': True,
                                'notification_type': notification_data.get('notification_type', 'features')
                            }
                            
                            # Add early notification flag and function name if present
                            if is_early:
                                notification_message['early_notification'] = True
                                notification_message['function_name'] = function_name
                            
                            # Yield the JSON notification as a string so it can be handled in generate_ai_response
                            yield content
                            continue  # Skip normal processing
                        else:
                            logger.debug("This is NOT a notification (missing is_notification flag)")
                    except json.JSONDecodeError:
                        logger.debug("Not a valid JSON - treating as normal text")
                        # Not a valid JSON notification, treat as normal text
                        pass
                
                # Normal text chunk - accumulate and yield it
                accumulated_content += content
                
                # Store as pending message for disconnect handling (saved only at end)
                self.pending_message = accumulated_content

                # Yield the content for streaming
                yield content
                
        except Exception as e:
            import traceback
            logger.error(f"Error in process_ai_stream: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            error_message = str(e)
            
            # Check for missing API key attributes
            if "'AnthropicProvider' object has no attribute 'anthropic_api_key'" in error_message:
                error_message = "No Anthropic API key configured. Please add API key [here](/settings/)."
            elif "'OpenAIProvider' object has no attribute 'openai_api_key'" in error_message:
                error_message = "No OpenAI API key configured. Please add API key [here](/settings/)."
            elif "'XAIProvider' object has no attribute 'xai_api_key'" in error_message:
                error_message = "No XAI API key configured. Please add API key [here](/settings/)."
            
            yield f"Error generating response: {error_message}"
        finally:
            # Don't clear pending_message here - it's needed for disconnect handling
            pass
    
    
    async def send_error(self, error_message):
        """
        Send error message to WebSocket
        """
        try:
            # First send error as a message chunk
            await self.send(text_data=json.dumps({
                'type': 'ai_chunk',
                'chunk': error_message,
                'is_final': False
            }))
            
            # Then send final signal to reset UI
            await self.send(text_data=json.dumps({
                'type': 'ai_chunk',
                'chunk': '',
                'is_final': True
            }))
        except Exception as e:
            logger.error(f"Error sending error message to client: {str(e)}")
    
    @database_sync_to_async
    def get_conversation(self, conversation_id):
        """
        Get conversation by ID
        """
        try:
            return Conversation.objects.get(id=conversation_id, user=self.user)
        except Conversation.DoesNotExist:
            return None
    
    @database_sync_to_async
    def create_conversation(self, title, project_id=None):
        """
        Create a new conversation
        """
        # Only create conversation if project_id is provided
        if not project_id:
            logger.warning("Cannot create conversation without project_id")
            return None
            
        try:
            from projects.models import Project
            project = Project.objects.select_related('owner').get(project_id=project_id)

            # Check access
            if not project.can_user_access(self.user):
                logger.warning(
                    "User %s attempted to access project %s without permission",
                    getattr(self.user, 'email', self.user),
                    project_id
                )
                return None

            conversation = Conversation.objects.create(
                user=self.user,
                title=title,
                project=project
            )

            logger.debug(
                "Created conversation %s for user %s attached to project %s",
                conversation.id,
                getattr(self.user, 'email', self.user),
                project_id
            )

            return conversation

        except Project.DoesNotExist:
            logger.error(f"Project not found for project_id={project_id}")
            return None
        except Exception as exc:
            logger.error(f"Unexpected error creating conversation: {exc}")
            return None
    
    @database_sync_to_async
    def update_conversation_title(self, title):
        """
        Update the conversation title
        """
        if self.conversation:
            self.conversation.title = title
            self.conversation.save()
    
    @database_sync_to_async
    def save_message(self, role, content):
        """
        Save message to database
        """
        # Note: file_data handling should be done at the async level, not here
        # The caller should use: await self.save_file_reference(file_data)
        # We don't try to process file_data inside this sync function

        if self.conversation:
            return Message.objects.create(
                conversation=self.conversation,
                role=role,
                content=content
            )
        return None
    
    @database_sync_to_async
    def save_message_with_file(self, role, content, file_data):
        """
        Save message to database with file data
        """
        # Note: file_data handling should be done at the async level, not here
        # The caller should use: await self.save_file_reference(file_data)
        # We don't try to process file_data inside this sync function

        file_id = file_data.get('id')

        # Validate file_id exists
        if not file_id:
            logger.error(f"No file_id provided in file_data: {file_data}")
            # Fall back to saving message without file
            if self.conversation:
                return Message.objects.create(
                    conversation=self.conversation,
                    role=role,
                    content=content
                )
            return None

        try:
            file_obj = ChatFile.objects.get(id=file_id)
        except ChatFile.DoesNotExist:
            logger.error(f"ChatFile with id={file_id} does not exist")
            # Fall back to saving message without file
            if self.conversation:
                return Message.objects.create(
                    conversation=self.conversation,
                    role=role,
                    content=content
                )
            return None

        # Construct the full file path by joining MEDIA_ROOT with the relative file path
        full_file_path = os.path.join(settings.MEDIA_ROOT, str(file_obj.file))
        
        # Check if it's an audio file
        is_audio = file_obj.file_type and 'audio' in file_obj.file_type.lower()
        
        if is_audio:
            # For audio files, store file reference without base64 encoding
            content_if_file = {
                "type": "audio_file",
                "file_id": file_obj.id,
                "filename": file_obj.original_filename,
                "file_type": file_obj.file_type,
                "transcription": content  # The transcription is stored in content
            }
        else:
            # Read the file content if it exists (for images/documents)
            if os.path.exists(full_file_path):
                with open(full_file_path, 'rb') as f:
                    base64_content = base64.b64encode(f.read()).decode('utf-8')
            else:
                logger.error(f"File not found at path: {full_file_path}")
                base64_content = None

            # Construct data URI
            data_uri = f"data:{file_obj.file_type};base64,{base64_content}"
            # logger.debug(f"\n\n\n\nData URI: {data_uri}")

            content_if_file = [
                {"type": "text", "text": content},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": data_uri
                    }
                }
            ]

        # logger.debug(f"\n\n\n\nContent if file: {content_if_file}")

        if self.conversation:
            # Create the message
            message = Message.objects.create(
                conversation=self.conversation,
                role=role,
                content=content,
                content_if_file=content_if_file
            )
            # Link the file to the message
            file_obj.message = message
            file_obj.save()
            return message
        return None
        

    async def prepare_messages_with_files(self, provider, messages):
        """
        Prepare messages with file attachments for the specific AI provider
        """
        # First check if any messages have files
        has_files = any('files' in msg and msg['files'] for msg in messages)
        
        # If no files, ensure messages are properly formatted
        if not has_files:
            # Return a clean copy of messages to avoid any Django model references
            return [
                {
                    "role": msg["role"],
                    "content": msg["content"]
                }
                for msg in messages
            ]
        
        # Get provider name from the provider instance
        provider_name = provider.__class__.__name__.replace('Provider', '').lower()
        
        # Get file handler for the provider with user context
        file_handler = FileHandler.get_handler(provider_name, self.user)
        
        # Get storage instance
        storage = ChatFileStorage()
        
        processed_messages = []
        
        for message in messages:
            # If message has files, process them
            if 'files' in message and message['files']:
                # Get the actual file objects
                file_ids = [f['id'] for f in message['files']]
                
                @database_sync_to_async
                def get_chat_files(ids):
                    return list(ChatFile.objects.filter(id__in=ids))
                
                chat_files = await get_chat_files(file_ids)
                
                # Process files based on provider
                if provider_name == 'anthropic':
                    # Anthropic supports mixed content
                    content_parts = []
                    
                    # Add text content if present
                    if message['content']:
                        content_parts.append({
                            "type": "text",
                            "text": message['content']
                        })
                    
                    # Add file content
                    for chat_file in chat_files:
                        try:
                            file_data = await file_handler.prepare_file_for_provider(chat_file, storage)
                            content_parts.append(file_data)
                        except Exception as e:
                            logger.error(f"Error preparing file {chat_file.original_filename}: {e}")
                            # Add error message to content
                            content_parts.append({
                                "type": "text",
                                "text": f"[Error loading file: {chat_file.original_filename}]"
                            })
                    
                    processed_messages.append({
                        "role": message['role'],
                        "content": content_parts
                    })
                
                else:  # OpenAI and XAI
                    # For OpenAI/XAI, we need to structure differently
                    content_parts = []
                    
                    # Add text content
                    if message['content']:
                        content_parts.append({
                            "type": "text",
                            "text": message['content']
                        })
                    
                    # Add file content
                    for chat_file in chat_files:
                        try:
                            file_data = await file_handler.prepare_file_for_provider(chat_file, storage)
                            content_parts.append(file_data)
                        except Exception as e:
                            logger.error(f"Error preparing file {chat_file.original_filename}: {e}")
                            # Add error message
                            content_parts.append({
                                "type": "text", 
                                "text": f"[Error loading file: {chat_file.original_filename}]"
                            })
                    
                    processed_messages.append({
                        "role": message['role'],
                        "content": content_parts
                    })
            else:
                # No files, use message as-is
                processed_messages.append({
                    "role": message['role'],
                    "content": message['content']
                })
        
        return processed_messages
    
    @database_sync_to_async
    def get_messages_for_ai(self):
        """
        Get messages for AI processing with file attachments
        """
        if not self.conversation:
            return []
            
        messages = Message.objects.filter(conversation=self.conversation).prefetch_related('files').order_by('-created_at')[:20]
        messages = reversed(list(messages))  # Convert to list and reverse
        
        formatted_messages = []
        for msg in messages:
            # Start with basic message structure
            message_data = {
                "role": msg.role,
                "content": msg.content if msg.content else ""
            }
            
            # Check if message has files attached
            files = list(msg.files.all())
            if files:
                # For user messages with files, we'll need to format content based on provider
                # This will be handled later when we actually send to the provider
                message_data["files"] = [
                    {
                        "id": file.id,
                        "filename": file.original_filename,
                        "file_type": file.file_type,
                        "file_size": file.file_size
                    }
                    for file in files
                ]
            
            formatted_messages.append(message_data)
        
        return formatted_messages

    @database_sync_to_async
    def get_existing_designs_context(self, canvas_id):
        """
        Get existing designs from the canvas to provide context to AI.
        This allows AI to modify existing designs instead of recreating them.
        """
        if not canvas_id or not self.conversation:
            return None

        try:
            from projects.models import DesignCanvas, ProjectDesignFeature

            # Get the canvas
            canvas = DesignCanvas.objects.filter(id=canvas_id).first()
            if not canvas:
                return None

            # Get feature positions from canvas - keys are like "feature_id_page_id"
            feature_positions = canvas.feature_positions or {}
            if not feature_positions:
                return None

            # Extract unique feature IDs from positions
            feature_ids = set()
            for key in feature_positions.keys():
                parts = key.split('_')
                if len(parts) >= 2:
                    try:
                        feature_ids.add(int(parts[0]))
                    except ValueError:
                        continue

            if not feature_ids:
                return None

            # Get the design features
            design_features = ProjectDesignFeature.objects.filter(
                id__in=feature_ids,
                project=canvas.project
            )

            if not design_features.exists():
                return None

            # Build context string
            context_parts = []
            context_parts.append("## EXISTING DESIGNS ON CURRENT CANVAS")
            context_parts.append("The following designs already exist on the user's current canvas. When the user asks for modifications, update these existing designs rather than creating new ones.\n")

            for feature in design_features:
                context_parts.append(f"### Feature: {feature.feature_name} (ID: {feature.id})")
                context_parts.append(f"Description: {feature.feature_description or 'No description'}")

                # Include CSS style summary
                css_style = feature.css_style or ''
                if css_style:
                    # Include first 500 chars of CSS to show style context
                    css_preview = css_style[:500] + ('...' if len(css_style) > 500 else '')
                    context_parts.append(f"CSS Style Preview:\n```css\n{css_preview}\n```")

                # Common elements
                common_elements = feature.common_elements or []
                if common_elements:
                    context_parts.append(f"Common Elements ({len(common_elements)}):")
                    for elem in common_elements:
                        elem_type = elem.get('element_type', 'unknown')
                        elem_id = elem.get('element_id', 'unknown')
                        elem_html = elem.get('html_content', '')
                        # Show a preview of the element
                        html_preview = elem_html[:300] + ('...' if len(elem_html) > 300 else '') if elem_html else 'No content'
                        context_parts.append(f"  - {elem_type} (element_id: {elem_id})")
                        context_parts.append(f"    ```html\n    {html_preview}\n    ```")

                # List pages with HTML previews
                pages = feature.pages or []
                if pages:
                    context_parts.append(f"Pages ({len(pages)}):")
                    for page in pages:
                        page_id = page.get('page_id', 'unknown')
                        page_name = page.get('page_name', 'Unnamed')
                        page_type = page.get('page_type', 'screen')
                        html_content = page.get('html_content', '')
                        navigates_to = page.get('navigates_to', [])

                        context_parts.append(f"  - {page_name} (page_id: {page_id}, type: {page_type})")
                        if navigates_to:
                            context_parts.append(f"    Navigation: {', '.join(str(n) for n in navigates_to[:5])}")

                        # Include HTML preview for understanding the page content
                        if html_content:
                            # Get first 400 chars to show structure
                            html_preview = html_content[:400] + ('...' if len(html_content) > 400 else '')
                            context_parts.append(f"    HTML Preview:\n    ```html\n    {html_preview}\n    ```")

                context_parts.append("")  # Empty line between features

            context_parts.append("\n## MODIFICATION INSTRUCTIONS")
            context_parts.append("When the user asks for changes to existing designs:")
            context_parts.append("1. Use the SAME feature_name to update an existing feature (this will update, not create)")
            context_parts.append("2. Keep the SAME page_id values to maintain page identity")
            context_parts.append("3. Preserve the CSS style unless specifically asked to change it")
            context_parts.append("4. Only modify the specific elements the user mentions")
            context_parts.append("5. Keep common elements (header, footer, sidebar) unless asked to change them")
            context_parts.append("\nDo NOT create new designs from scratch when modifications are requested.")

            return "\n".join(context_parts)

        except Exception as e:
            logger.error(f"Error getting existing designs context: {e}")
            return None

    @database_sync_to_async
    def get_chat_history(self):
        """
        Get chat history for the current conversation
        """
        if not self.conversation:
            return []
            
        messages = Message.objects.filter(conversation=self.conversation).order_by('created_at')
        history = []
        
        for msg in messages:
            message_data = {
                'role': msg.role,
                'content': msg.content if msg.content else '',
                'timestamp': msg.created_at.isoformat(),
                'is_partial': msg.is_partial  # Include partial status
            }
            
            # Check if there's file data attached
            if msg.content_if_file:
                # Check if it's an audio file (new format)
                if isinstance(msg.content_if_file, dict) and msg.content_if_file.get('type') == 'audio_file':
                    message_data['audio_file'] = {
                        'file_id': msg.content_if_file.get('file_id'),
                        'filename': msg.content_if_file.get('filename'),
                        'transcription': msg.content_if_file.get('transcription', '')
                    }
                    # For audio messages, clear the content to avoid duplication
                    message_data['content'] = ''
                # Legacy format for other files
                else:
                    message_data['content_if_file'] = msg.content_if_file
                    
            history.append(message_data)
            
        return history
    
    @database_sync_to_async
    def get_project_id(self):
        """
        Get project ID if conversation is linked to a project
        """
        if self.conversation and self.conversation.project:
            return self.conversation.project.id
        return None
    
    @database_sync_to_async
    def save_file_reference(self, file_data):
        """
        Save file reference to database
        """
        if not self.conversation:
            return None
            
        try:
            # Extract file metadata from the file_data object
            original_filename = file_data.get('name', 'unnamed_file')
            file_type = file_data.get('type', 'application/octet-stream')
            file_size = file_data.get('size', 0)
            
            # Check for content, but don't expect it in normal operation
            # The WebSocket message typically only contains file metadata, not the actual content
            file_content = file_data.get('content')
            logger.debug(f"File content: {file_content}")
            if file_content:
                # This branch is only for when content is actually included
                # Decode base64 data if it's included
                file_base64_content = base64.b64decode(file_content)
                logger.debug(f"File base64 content: {file_base64_content}")
                logger.debug("File content was included and decoded")
            else:
                # This is the expected normal path - file content is uploaded separately
                logger.debug(f"Saving file reference for {original_filename} (content will be uploaded separately)")
            
            # Create a placeholder file as we don't have the actual content yet
            # The real file would be uploaded through the REST API
            placeholder_path = os.path.join('file_storage', str(self.conversation.id))
            os.makedirs(os.path.join(settings.MEDIA_ROOT, placeholder_path), exist_ok=True)
            
            file_obj = ChatFile.objects.create(
                conversation=self.conversation,
                original_filename=original_filename,
                file_type=file_type,
                file_size=file_size,
                # We'll set an empty file as a placeholder
                file=ContentFile(b'', name=f"{uuid.uuid4()}.bin")
            )
            
            return {
                'id': file_obj.id,
                'original_filename': file_obj.original_filename,
                'file_type': file_obj.file_type,
                'file_size': file_obj.file_size
            }
            
        except Exception as e:
            logger.error(f"Error saving file reference: {str(e)}")
            return None
    
    async def generate_title_with_ai(self, user_message, ai_response):
        """
        Generate a conversation title using AI based on the first user message and AI response
        """
        # Use the same provider as the chat
        provider_name = settings.AI_PROVIDER_DEFAULT
        
        # Get model selection for the user
        try:
            logger.debug(f"Before model selection: {self.user}", extra={'easylogs_metadata': {'user_id': self.user.id if self.user else None}})
            model_selection = await database_sync_to_async(ModelSelection.objects.get)(user=self.user)
            logger.debug(f"Model selection: {model_selection}", extra={'easylogs_metadata': {'user_id': self.user.id if self.user else None}})
            selected_model = model_selection.selected_model
            logger.debug(f"Selected model... #3: {selected_model}", extra={'easylogs_metadata': {'user_id': self.user.id if self.user else None}})
        except ModelSelection.DoesNotExist:
            # Create a default model selection if none exists
            model_selection = await database_sync_to_async(ModelSelection.objects.create)(
                user=self.user,
                selected_model=ModelSelection.DEFAULT_MODEL_KEY
            )
            selected_model = model_selection.selected_model

        provider_name = MODEL_TO_PROVIDER.get(selected_model, 'openai')
        
        provider = AIProvider.get_provider(provider_name, selected_model, user=self.user, conversation=self.conversation)
        
        # Create a special prompt for title generation
        title_prompt = [
            {
                "role": "system",
                "content": "Generate a short, concise title (maximum 50 characters) that summarizes this conversation. The title should capture the main topic or purpose of the discussion. Only respond with the title text, no additional commentary or formatting."
            },
            {
                "role": "user", 
                "content": f"User: {user_message[:200]}...\nAI: {ai_response[:200]}..."
            }
        ]
        
        try:
            # Get project_id if available
            project_id = await self.get_project_id() if self.conversation else None
            
            # Use empty tools list for title generation (no function calls needed)
            tools = []
            
            # Generate title without file processing
            title = ""
            # Skip file processing for title generation by calling provider directly
            async for content in provider.generate_stream(title_prompt, project_id, self.conversation.id if self.conversation else None, tools):
                if isinstance(content, str) and not content.startswith("__NOTIFICATION__"):
                    title += content
                
            # Clean and truncate the generated title
            title = title.strip()
            if len(title) > 50:
                title = title[:47] + "..."
                
            # Update the conversation title
            await self.update_conversation_title(title)
            logger.debug(f"Generated title for conversation {self.conversation.id}: {title}")
            
        except Exception as e:
            logger.error(f"Error generating title: {str(e)}")
            # Fallback to original behavior
            await self.update_conversation_title(user_message[:50])
    
    async def auto_save_partial_message(self):
        """Auto-save partial AI message"""
        if self.pending_message and self.conversation:
            try:
                # Check if we already have a partial message
                last_message = await database_sync_to_async(
                    lambda: Message.objects.filter(
                        conversation=self.conversation,
                        role='assistant',
                        is_partial=True
                    ).order_by('-created_at').first()
                )()
                
                if last_message:
                    # Update existing partial message
                    last_message.content = self.pending_message
                    await database_sync_to_async(last_message.save)()
                    logger.debug(f"Updated partial message: {len(self.pending_message)} chars")
                else:
                    # Create new partial message
                    await database_sync_to_async(Message.objects.create)(
                        conversation=self.conversation,
                        role='assistant',
                        content=self.pending_message,
                        is_partial=True
                    )
                    logger.debug(f"Created new partial message: {len(self.pending_message)} chars")
                    
            except Exception as e:
                logger.error(f"Error auto-saving partial message: {e}")
    
    async def finalize_message(self):
        """Finalize the partial message"""
        if self.pending_message and self.conversation:
            try:
                # Find the partial message
                last_message = await database_sync_to_async(
                    lambda: Message.objects.filter(
                        conversation=self.conversation,
                        role='assistant',
                        is_partial=True
                    ).order_by('-created_at').first()
                )()
                
                if last_message:
                    # Finalize it
                    last_message.content = self.pending_message
                    last_message.is_partial = False
                    await database_sync_to_async(last_message.save)()
                    logger.debug(f"Finalized message: {len(self.pending_message)} chars")
                else:
                    # Create as final message if no partial exists
                    await self.save_message('assistant', self.pending_message)
                    logger.debug(f"Created final message: {len(self.pending_message)} chars")
                    
            except Exception as e:
                logger.error(f"Error finalizing message: {e}")
    
    async def force_save_message(self):
        """Force save the pending message (used on disconnect)"""
        if self.pending_message and self.conversation:
            try:
                await self.save_message('assistant', self.pending_message)
                logger.info(f"Force saved message on disconnect: {len(self.pending_message)} chars")
                self.pending_message = None
            except Exception as e:
                logger.error(f"Error force saving message: {e}")
    
    async def auto_save_streaming_message(self, content):
        """Auto-save streaming AI message to prevent loss on disconnect"""
        logger.info(f"[AUTO_SAVE] Starting auto_save_streaming_message for conversation {self.conversation.id if self.conversation else 'None'}, content length: {len(content)}")
        
        if self.conversation:
            try:
                # Check if we already have a partial message for this conversation
                @database_sync_to_async
                def get_partial_message():
                    return Message.objects.filter(
                        conversation=self.conversation,
                        role='assistant',
                        is_partial=True
                    ).order_by('-created_at').first()
                
                last_message = await get_partial_message()
                
                logger.info(f"[AUTO_SAVE] Found existing partial message ID: {last_message.id if last_message else 'None'}")
                
                if last_message:
                    # Update existing partial message
                    logger.info(f"[AUTO_SAVE] Updating partial message")
                    last_message.content = content
                    await database_sync_to_async(last_message.save)()
                    logger.debug(f"Updated partial streaming message: {len(content)} chars")
                else:
                    # Create new partial message
                    logger.info(f"[AUTO_SAVE] Creating partial message")
                    await database_sync_to_async(Message.objects.create)(
                        conversation=self.conversation,
                        role='assistant',
                        content=content,
                        is_partial=True
                    )
                    logger.debug(f"Created new partial streaming message: {len(content)} chars")
                    
            except Exception as e:
                logger.error(f"Error auto-saving streaming message: {e}")
    
    async def finalize_streaming_message(self, full_content):
        """Save the complete AI response after streaming finishes"""
        if self.conversation and full_content:
            try:
                await self.save_message('assistant', full_content)
                # Clear the pending message to prevent duplicate saves on disconnect
                self.pending_message = None
            except Exception as e:
                logger.error(f"Error saving streaming message: {e}")
                self.pending_message = None 
