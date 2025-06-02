import json
import asyncio
import logging
import os
import base64
import uuid
from datetime import datetime
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from chat.models import (
    Conversation, 
    Message,
    ChatFile,
    ModelSelection,
    AgentRole
)
from projects.models import ProjectChecklist
from coding.utils import (
    AIProvider,
    get_system_prompt_developer,
    get_system_prompt_design, 
    get_system_prompt_product
)
from coding.utils.ai_tools import tools_code, tools_product, tools_design

# Set up logger
logger = logging.getLogger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.heartbeat_task = None
        self.connection_alive = True
        self.conversation = None
        self.active_generation_task = None
        self.should_stop_generation = False
        self.user = None
        self.room_name = None
        self.room_group_name = None
        self.using_groups = False
        
    async def connect(self):
        """Handle WebSocket connection"""
        connection_accepted = False
        
        try:
            # Get user from scope and ensure it's properly resolved
            lazy_user = self.scope["user"]
            
            # Convert UserLazyObject to actual User instance
            if hasattr(lazy_user, '_wrapped') and hasattr(lazy_user, '_setup'):
                if lazy_user.is_authenticated:
                    User = get_user_model()
                    self.user = await database_sync_to_async(User.objects.get)(pk=lazy_user.pk)
                else:
                    self.user = lazy_user
            else:
                self.user = lazy_user
            
            # Set up room name based on user
            if self.user.is_authenticated:
                self.room_name = f"chat_{self.user.username}"
            else:
                self.room_name = "chat_anonymous"
                logger.warning("User is not authenticated, using anonymous chat room")
            
            # Create sanitized group name for channel layer
            import re
            self.room_group_name = re.sub(r'[^a-zA-Z0-9._-]', '_', self.room_name)
            
            # Accept connection
            await self.accept()
            connection_accepted = True
            self.connection_alive = True
            logger.info(f"WebSocket connection accepted for user {self.user} in room {self.room_group_name}")
            
            # Start heartbeat to keep connection alive
            self.heartbeat_task = asyncio.create_task(self._heartbeat())
            
            # Try to join room group
            try:
                await self.channel_layer.group_add(
                    self.room_group_name,
                    self.channel_name
                )
                logger.info(f"User {self.user} added to group {self.room_group_name}")
                self.using_groups = True
            except Exception as group_error:
                logger.error(f"Error adding to channel group: {str(group_error)}")
                self.using_groups = False
            
            # Load chat history if conversation_id is provided
            query_string = self.scope.get('query_string', b'').decode()
            query_params = dict(param.split('=') for param in query_string.split('&') if '=' in param)
            conversation_id = query_params.get('conversation_id')
            
            if conversation_id:
                self.conversation = await self.get_conversation(conversation_id)
                if self.conversation:
                    messages = await self.get_chat_history()
                    await self.send(text_data=json.dumps({
                        'type': 'chat_history',
                        'messages': messages
                    }))
            
        except Exception as e:
            logger.error(f"Error in WebSocket connect: {str(e)}")
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
                try:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': f"Connection error: {str(e)}"
                    }))
                except Exception as inner_e:
                    logger.error(f"Could not send error message: {str(inner_e)}")
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        self.connection_alive = False
        
        # Cancel heartbeat
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Cancel active generation
        if self.active_generation_task and not self.active_generation_task.done():
            self.should_stop_generation = True
            # Don't force cancel, let it finish gracefully
        
        # Leave channel group
        try:
            if hasattr(self, 'using_groups') and self.using_groups:
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
                logger.info(f"User {self.user} removed from group {self.room_group_name}")
        except Exception as e:
            logger.error(f"Error during disconnect: {str(e)}")
    
    async def _heartbeat(self):
        """Send periodic heartbeat to keep connection alive"""
        while self.connection_alive:
            try:
                # Only send heartbeat if connection is still open
                if self.connection_alive and hasattr(self, 'channel_name'):
                    await self.send(text_data=json.dumps({
                        'type': 'heartbeat',
                        'timestamp': datetime.now().isoformat()
                    }))
                await asyncio.sleep(30)  # Send heartbeat every 30 seconds
            except asyncio.CancelledError:
                logger.info("Heartbeat task cancelled")
                break
            except Exception as e:
                if "Unexpected ASGI message" in str(e) or "websocket.close" in str(e):
                    logger.info("WebSocket closed, stopping heartbeat")
                else:
                    logger.error(f"Heartbeat error: {e}")
                break
    
    async def receive(self, text_data):
        """Receive message from WebSocket"""
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type', 'message')
            
            if message_type == 'message':
                await self._handle_message(text_data_json)
            elif message_type == 'stop_generation':
                await self._handle_stop_generation(text_data_json)
            elif message_type == 'heartbeat_ack':
                # Client acknowledged heartbeat
                pass
            
        except Exception as e:
            logger.error(f"Error processing received message: {str(e)}")
            await self.send_error(f"Error processing message: {str(e)}")
    
    async def _handle_message(self, data):
        """Handle incoming chat message"""
        user_message = data.get('message', '')
        conversation_id = data.get('conversation_id')
        project_id = data.get('project_id')
        file_data = data.get('file')
        user_role = data.get('user_role')
        
        # Validate input
        if not user_message and not file_data:
            await self.send_error("Message cannot be empty")
            return
        
        # Get or create conversation
        if conversation_id and not self.conversation:
            self.conversation = await self.get_conversation(conversation_id)
        
        if not self.conversation:
            if not project_id:
                await self.send_error("A project ID is required to create a conversation")
                return
            
            conversation_title = user_message[:50] if user_message else f"File: {file_data.get('name', 'Untitled')}"
            self.conversation = await self.create_conversation(conversation_title, project_id)
            
            if not self.conversation:
                await self.send_error("Failed to create conversation. Please check your project ID.")
                return
        
        # Handle file uploads
        if not user_message and file_data:
            user_message = f"[Shared a file: {file_data.get('name', 'file')}]"
        
        # Save message
        if file_data:
            logger.debug(f"Processing file data: {file_data}")
            message = await self.save_message_with_file('user', user_message, file_data)
        else:
            message = await self.save_message('user', user_message)
        
        if not message:
            await self.send_error("Failed to save message")
            return
        
        # Reset stop flag and start generation
        self.should_stop_generation = False
        provider_name = settings.AI_PROVIDER_DEFAULT
        
        # Cancel any existing generation task
        if self.active_generation_task and not self.active_generation_task.done():
            self.should_stop_generation = True
            await asyncio.sleep(0.1)  # Give it time to stop
        
        # Start new generation task
        self.active_generation_task = asyncio.create_task(
            self.generate_ai_response(user_message, provider_name, project_id, user_role)
        )
    
    async def _handle_stop_generation(self, data):
        """Handle stop generation request"""
        conversation_id = data.get('conversation_id')
        
        # Set flag to stop generation
        self.should_stop_generation = True
        
        # Log stop request
        logger.debug(f"Stop generation requested for conversation {conversation_id}")
        
        # Save an indicator that generation was stopped
        if self.conversation:
            await self.save_message('system', '*Generation stopped by user*')
        
        # Send stop confirmation to client
        await self.send(text_data=json.dumps({
            'type': 'stop_confirmed'
        }))
    
    async def generate_ai_response(self, user_message, provider_name, project_id=None, user_role=None):
        """Generate response from AI with improved streaming and error handling"""
        full_response = ""
        chunk_buffer = ""
        
        try:
            # Send typing indicator
            await self._send_chunk('', is_final=False, is_typing=True)
            
            # Get conversation history
            messages = await self.get_messages_for_ai()
            
            # Get user's agent role
            logger.debug(f"User Role: {user_role}")
            agent_role, created = await database_sync_to_async(AgentRole.objects.get_or_create)(
                user=self.user,
                defaults={'name': 'product_analyst'}
            )
            logger.debug(f"Agent Role: {agent_role.name}")
            user_role = agent_role.name
            
            # Select appropriate system prompt and tools
            if user_role == "designer":
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
                    "content": system_prompt
                })
            
            # Get model selection
            try:
                model_selection = await database_sync_to_async(ModelSelection.objects.get)(user=self.user)
                selected_model = model_selection.selected_model
            except ModelSelection.DoesNotExist:
                model_selection = await database_sync_to_async(ModelSelection.objects.create)(
                    user=self.user,
                    selected_model='claude_4_sonnet'
                )
                selected_model = model_selection.selected_model
            
            # Get AI provider
            provider = AIProvider.get_provider(provider_name, selected_model)
            
            logger.debug(f"Using provider: {provider_name}, model: {selected_model}")
            logger.debug(f"Project ID: {project_id}, Conversation ID: {self.conversation.id if self.conversation else None}")
            
            # Process the stream
            async for message in self.process_ai_stream(provider, messages, project_id, tools):
                if not self.connection_alive:
                    logger.warning("Connection closed, stopping generation")
                    break
                
                if self.should_stop_generation:
                    stop_message = "\n\n*Generation stopped by user*"
                    await self._send_chunk(stop_message, is_final=False)
                    full_response += stop_message
                    break
                
                # Handle different message types
                if isinstance(message, dict):
                    message_type = message.get('type')
                    
                    if message_type == 'content':
                        content = message.get('content', '')
                        full_response += content
                        chunk_buffer += content
                        
                        # Send chunks in batches
                        if len(chunk_buffer) >= 100:
                            await self._send_chunk(chunk_buffer, is_final=False)
                            chunk_buffer = ""
                            await asyncio.sleep(0.01)
                    
                    elif message_type == 'notification':
                        await self._handle_notification(message)
                    
                    elif message_type == 'error':
                        await self._handle_stream_error(message)
                else:
                    # Legacy string content
                    content = str(message)
                    full_response += content
                    chunk_buffer += content
                    
                    if len(chunk_buffer) >= 100:
                        await self._send_chunk(chunk_buffer, is_final=False)
                        chunk_buffer = ""
                        await asyncio.sleep(0.01)
            
            # Send any remaining content
            if chunk_buffer:
                await self._send_chunk(chunk_buffer, is_final=False)
            
            # Save complete message if not stopped and has content
            if not self.should_stop_generation and full_response.strip():
                await self.save_message_validated('assistant', full_response)
            
            # Update conversation title if needed
            if self.conversation and (not self.conversation.title or self.conversation.title == str(self.conversation.id)):
                await self.generate_title_with_ai(user_message, full_response)
            
            # Send completion signal
            await self._send_completion_signal()
            
        except asyncio.CancelledError:
            logger.info("Generation task cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in generate_ai_response: {str(e)}")
            await self._handle_generation_error(e)
        finally:
            self.active_generation_task = None
    
    async def process_ai_stream(self, provider, messages, project_id, tools):
        """Process AI stream with improved message handling"""
        try:
            conversation_id = self.conversation.id if self.conversation else None
            
            async for message in provider.generate_stream(messages, project_id, conversation_id, tools):
                if self.should_stop_generation:
                    logger.debug("Stopping AI stream generation due to user request")
                    break
                
                yield message
                
        except Exception as e:
            logger.error(f"Error in process_ai_stream: {str(e)}")
            yield {'type': 'error', 'error': str(e)}
    
    async def _send_chunk(self, content, is_final=False, is_typing=False):
        """Send a chunk with error handling and retry logic"""
        if not self.connection_alive:
            logger.warning("Attempted to send chunk but connection is closed")
            return
            
        max_retries = 3
        retry_delay = 0.1
        
        for attempt in range(max_retries):
            try:
                message = {
                    'type': 'ai_chunk',
                    'chunk': content,
                    'is_final': is_final
                }
                
                if is_typing:
                    message['is_typing'] = True
                
                if hasattr(self, 'using_groups') and self.using_groups:
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {'type': 'ai_response_chunk', **message}
                    )
                else:
                    await self.send(text_data=json.dumps(message))
                
                return  # Success
                
            except Exception as e:
                if "websocket.close" in str(e) or "Unexpected ASGI message" in str(e):
                    logger.warning("WebSocket closed, cannot send chunk")
                    self.connection_alive = False
                    return
                    
                logger.error(f"Error sending chunk (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                else:
                    raise
    
    async def _handle_notification(self, notification):
        """Handle notification messages"""
        notification_message = {
            'type': 'ai_chunk',
            'chunk': '',
            'is_final': False,
            'is_notification': True,
            'notification_type': notification.get('notification_type'),
            'early_notification': notification.get('early_notification', False),
            'function_name': notification.get('function_name', ''),
            'message': notification.get('message', '')
        }
        
        if hasattr(self, 'using_groups') and self.using_groups:
            await self.channel_layer.group_send(
                self.room_group_name,
                {'type': 'ai_response_chunk', **notification_message}
            )
        else:
            await self.send(text_data=json.dumps(notification_message))
    
    async def _handle_stream_error(self, error_data):
        """Handle errors from the stream"""
        error_message = error_data.get('error', 'Unknown error occurred')
        logger.error(f"Stream error: {error_message}")
        
        # Send error to client
        await self.send_error(f"AI Error: {error_message}")
    
    async def _send_completion_signal(self):
        """Send completion signal to client"""
        try:
            project_id = await self.get_project_id() if self.conversation else None
            
            completion_message = {
                'type': 'ai_chunk',
                'chunk': '',
                'is_final': True,
                'conversation_id': self.conversation.id if self.conversation else None,
                'project_id': project_id
            }
            
            if hasattr(self, 'using_groups') and self.using_groups:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {'type': 'ai_response_chunk', **completion_message}
                )
            else:
                await self.send(text_data=json.dumps(completion_message))
                
        except Exception as e:
            logger.error(f"Error sending completion signal: {str(e)}")
    
    async def _handle_generation_error(self, error):
        """Handle errors during generation"""
        error_message = f"Sorry, I encountered an error: {str(error)}"
        
        # Save error message
        await self.save_message('assistant', error_message)
        
        # Send error to client
        try:
            if hasattr(self, 'using_groups') and self.using_groups:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'message': error_message,
                        'sender': 'assistant'
                    }
                )
            else:
                await self.send(text_data=json.dumps({
                    'type': 'message',
                    'message': error_message,
                    'sender': 'assistant'
                }))
        except Exception as inner_e:
            logger.error(f"Error sending error message: {str(inner_e)}")
    
    # WebSocket message handlers
    async def chat_message(self, event):
        """Send message to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['message'],
            'sender': event['sender']
        }))
    
    async def ai_response_chunk(self, event):
        """Send AI response chunk to WebSocket"""
        response_data = {
            'type': 'ai_chunk',
            'chunk': event.get('chunk', ''),
            'is_final': event.get('is_final', False),
            'conversation_id': event.get('conversation_id'),
            'provider': event.get('provider'),
            'project_id': event.get('project_id')
        }
        
        # Add notification data if present
        if event.get('is_notification'):
            response_data.update({
                'is_notification': True,
                'notification_type': event.get('notification_type', 'features'),
                'early_notification': event.get('early_notification', False),
                'function_name': event.get('function_name', ''),
                'message': event.get('message', '')
            })
        
        # Add typing indicator if present
        if event.get('is_typing'):
            response_data['is_typing'] = True
        
        try:
            await self.send(text_data=json.dumps(response_data))
        except Exception as e:
            logger.error(f"Error sending response to client: {str(e)}")
    
    async def ai_chunk(self, event):
        """
        Handler for ai_chunk messages - redirect to ai_response_chunk
        This handles the case where ai_chunk messages are sent to the channel layer
        """
        logger.warning("ai_chunk message received on channel layer - redirecting to ai_response_chunk")
        await self.ai_response_chunk(event)
    
    async def send_error(self, error_message):
        """Send error message to WebSocket"""
        if not self.connection_alive:
            logger.warning("Attempted to send error but connection is closed")
            return
            
        try:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': error_message
            }))
        except Exception as e:
            if "websocket.close" in str(e) or "Unexpected ASGI message" in str(e):
                logger.warning("WebSocket closed, cannot send error message")
            else:
                logger.error(f"Error sending error message to client: {str(e)}")
    
    # Database operations
    @database_sync_to_async
    def get_conversation(self, conversation_id):
        """Get conversation by ID"""
        try:
            return Conversation.objects.get(id=conversation_id, user=self.user)
        except Conversation.DoesNotExist:
            return None
    
    @database_sync_to_async
    def create_conversation(self, title, project_id=None):
        """Create a new conversation"""
        if not project_id:
            logger.warning("Cannot create conversation without project_id")
            return None
            
        conversation = Conversation.objects.create(
            user=self.user,
            title=title
        )
        
        try:
            from projects.models import Project
            project = Project.objects.get(id=project_id, owner=self.user)
            conversation.project = project
            conversation.save()
            logger.debug(f"Set project reference for conversation {conversation.id} to project {project_id}")
        except Exception as e:
            conversation.delete()
            logger.error(f"Error setting project reference: {str(e)}")
            return None
                
        return conversation
    
    @database_sync_to_async
    def update_conversation_title(self, title):
        """Update the conversation title"""
        if self.conversation:
            self.conversation.title = title
            self.conversation.save()
    
    @database_sync_to_async
    def save_message(self, role, content):
        """Save message to database"""
        if self.conversation:
            return Message.objects.create(
                conversation=self.conversation,
                role=role,
                content=content
            )
        return None
    
    async def save_message_validated(self, role, content):
        """Save message with validation"""
        if not content or not content.strip():
            logger.warning(f"Attempted to save empty {role} message")
            return None
        
        # Truncate extremely long messages
        max_length = 50000
        if len(content) > max_length:
            logger.warning(f"Truncating {role} message from {len(content)} to {max_length} characters")
            content = content[:max_length] + "\n\n[Message truncated due to length]"
        
        return await self.save_message(role, content)
    
    @database_sync_to_async
    def save_message_with_file(self, role, content, file_data):
        """Save message to database with file data"""
        file_id = file_data.get('id')
        
        try:
            file_obj = ChatFile.objects.get(id=file_id)
            
            # Construct the full file path
            full_file_path = os.path.join(settings.MEDIA_ROOT, str(file_obj.file))
            
            # Read the file content if it exists
            if os.path.exists(full_file_path):
                with open(full_file_path, 'rb') as f:
                    base64_content = base64.b64encode(f.read()).decode('utf-8')
            else:
                logger.error(f"File not found at path: {full_file_path}")
                base64_content = None

            # Construct data URI
            data_uri = f"data:{file_obj.file_type};base64,{base64_content}"

            content_if_file = [
                {"type": "text", "text": content},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": data_uri
                    }
                }
            ]

            if self.conversation:
                return Message.objects.create(
                    conversation=self.conversation,
                    role=role,
                    content_if_file=content_if_file
                )
        except ChatFile.DoesNotExist:
            logger.error(f"ChatFile with id {file_id} does not exist")
        except Exception as e:
            logger.error(f"Error saving message with file: {str(e)}")
        
        return None
    
    @database_sync_to_async
    def get_messages_for_ai(self):
        """Get messages for AI processing"""
        if not self.conversation:
            return []
            
        messages = Message.objects.filter(conversation=self.conversation).order_by('-created_at')[:8]
        messages = reversed(list(messages))
        
        return [
            {"role": msg.role, "content": msg.content if msg.content is not None and msg.content != "" else msg.content_if_file}
            for msg in messages
        ]
    
    @database_sync_to_async
    def get_chat_history(self):
        """Get chat history for the current conversation"""
        if not self.conversation:
            return []
            
        messages = Message.objects.filter(conversation=self.conversation).order_by('created_at')
        return [
            {
                'role': msg.role,
                'content': msg.content if msg.content is not None and msg.content != "" else msg.content_if_file,
                'timestamp': msg.created_at.isoformat()
            } for msg in messages
        ]
    
    @database_sync_to_async
    def get_project_id(self):
        """Get project ID if conversation is linked to a project"""
        if self.conversation and self.conversation.project:
            return self.conversation.project.id
        return None
    
    @database_sync_to_async
    def save_file_reference(self, file_data):
        """Save file reference to database"""
        if not self.conversation:
            return None
            
        try:
            # Extract file metadata
            original_filename = file_data.get('name', 'unnamed_file')
            file_type = file_data.get('type', 'application/octet-stream')
            file_size = file_data.get('size', 0)
            
            # Create placeholder file
            placeholder_path = os.path.join('file_storage', str(self.conversation.id))
            os.makedirs(os.path.join(settings.MEDIA_ROOT, placeholder_path), exist_ok=True)
            
            file_obj = ChatFile.objects.create(
                conversation=self.conversation,
                original_filename=original_filename,
                file_type=file_type,
                file_size=file_size,
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
        """Generate a conversation title using AI"""
        provider_name = settings.AI_PROVIDER_DEFAULT
        
        try:
            model_selection = await database_sync_to_async(ModelSelection.objects.get)(user=self.user)
            selected_model = model_selection.selected_model
        except ModelSelection.DoesNotExist:
            model_selection = await database_sync_to_async(ModelSelection.objects.create)(
                user=self.user,
                selected_model='claude_4_sonnet'
            )
            selected_model = model_selection.selected_model
        
        provider = AIProvider.get_provider(provider_name, selected_model)
        
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
            project_id = await self.get_project_id() if self.conversation else None
            tools = []  # No tools needed for title generation
            
            # Generate title
            title = ""
            async for message in self.process_ai_stream(provider, title_prompt, project_id, tools):
                if isinstance(message, dict) and message.get('type') == 'content':
                    title += message.get('content', '')
                elif isinstance(message, str):
                    title += message
                    
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