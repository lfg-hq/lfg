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
from django.urls import reverse
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
        self.pending_message = None
        self.auto_save_task = None
        self.last_save_time = None
        self.message_save_lock = asyncio.Lock()  # Lock to prevent concurrent message saves
    async def connect(self):
        """
        Handle WebSocket connection
        """
        connection_accepted = False
        
        try:
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
            
            # Each user joins their own room based on their username
            if self.user.is_authenticated:
                self.room_name = f"chat_{self.user.username}"
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
            query_string = self.scope.get('query_string', b'').decode()
            query_params = dict(param.split('=') for param in query_string.split('&') if '=' in param)
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
        except Exception as e:
            logger.error(f"Error during disconnect: {str(e)}")
    
    async def receive(self, text_data):
        """
        Receive message from WebSocket
        """
        try:
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
                user_role = text_data_json.get('user_role')  # Get user role if present
                # file_id = text_data_json.get('file_id')  # Get file_id if present

                

                # logger.debug(f"File ID: {file_data.get('id')}")
                
                # Check if we have either a message or file data
                if not user_message and not file_data:
                    await self.send_error("Message cannot be empty")
                    return
                
                # Get or create conversation
                if conversation_id and not self.conversation:
                    self.conversation = await self.get_conversation(conversation_id)
                
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
                    self.generate_ai_response(user_message, provider_name, project_id, user_role)
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
                    await self.save_message('system', '*Generation stopped by user*')
                
                # Send stop confirmation to client
                await self.send(text_data=json.dumps({
                    'type': 'stop_confirmed'
                }))
                
                # Log stop request
                logger.debug(f"Stop generation requested for conversation {conversation_id}")
            
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
    
    async def ai_response_chunk(self, event):
        """
        Send AI response chunk to WebSocket
        """
        logger.info(f"ai_response_chunk received event: {event}")
        
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
        notification_fields = ['is_notification', 'notification_type', 'early_notification', 'function_name', 'content_chunk', 'is_complete']
        for field in notification_fields:
            if field in event:
                response_data[field] = event[field]
                logger.info(f"Adding notification field {field}: {event[field]}")
        
        # Send the response to the client
        try:
            logger.info(f"FINAL response_data being sent: {response_data}")
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
                await self.send(text_data=json.dumps({
                    'type': 'heartbeat',
                    'timestamp': datetime.now().isoformat()
                }))
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                break
    
    async def generate_ai_response(self, user_message, provider_name, project_id=None, user_role=None):
        """
        Generate response from AI
        """
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

        logger.debug(f"Agent Role: {agent_role.name}")
        user_role = agent_role.name

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
                # "content": await get_system_prompt()
                "content": system_prompt
            })

        try:
            model_selection = await database_sync_to_async(ModelSelection.objects.get)(user=self.user)
            selected_model = model_selection.selected_model
        except ModelSelection.DoesNotExist:
            # Create a default model selection if none exists
            model_selection = await database_sync_to_async(ModelSelection.objects.create)(
                user=self.user,
                selected_model='claude_4_sonnet'
            )
            selected_model = model_selection.selected_model

        if selected_model == "claude_4_sonnet":
            provider_name = "anthropic"
        else:
            provider_name = "openai"
        
        # Get the appropriate AI provider
        print(f"\n\n\nCreating provider with user: {self.user} (type: {type(self.user)})")
        provider = AIProvider.get_provider(provider_name, selected_model, user=self.user)
        
        # Debug log to verify settings
        logger.debug(f"Using provider: {provider_name}")
        logger.debug(f"Project ID: {project_id}")
        logger.debug(f"Conversation ID: {self.conversation.id if self.conversation else None}")
        logger.debug(f"Message count: {len(messages)}")
        
        try:
            # Generate streaming response
            full_response = ""
            
            # Process the stream in an async context
            async for content in self.process_ai_stream(provider, messages, project_id, tools):
                logger.debug(f"Content from process_ai_stream: {content[:100] if isinstance(content, str) else content}")
                
                # Check if generation should stop
                if self.should_stop_generation:
                    # Add a note to the response that generation was stopped
                    stop_message = "\n\n*Generation stopped by user*"
                    
                    # Send the stop message as the final chunk
                    try:
                        if hasattr(self, 'using_groups') and self.using_groups:
                            await self.channel_layer.group_send(
                                self.room_group_name,
                                {
                                    'type': 'ai_response_chunk',
                                    'chunk': stop_message,
                                    'is_final': False
                                }
                            )
                        else:
                            await self.send(text_data=json.dumps({
                                'type': 'ai_chunk',
                                'chunk': stop_message,
                                'is_final': False
                            }))
                    except Exception as e:
                        logger.error(f"Error sending stop message chunk: {str(e)}")
                    
                    # Add the stop message to the full response
                    full_response += stop_message
                    
                    # Break out of the loop
                    break
                
                # Check if this is a notification
                if isinstance(content, str) and content.startswith("__NOTIFICATION__") and content.endswith("__NOTIFICATION__"):
                    # Parse and send notification
                    try:
                        notification_json = content[len("__NOTIFICATION__"):-len("__NOTIFICATION__")]
                        notification_data = json.loads(notification_json)
                        logger.info(f"NOTIFICATION DETECTED in generate_ai_response: {notification_data}")
                        
                        # Send notification to client
                        notification_message = {
                            'chunk': '',
                            'is_final': False,
                            'is_notification': True,
                            'notification_type': notification_data.get('notification_type', 'features'),
                            'early_notification': notification_data.get('early_notification', False),
                            'function_name': notification_data.get('function_name', '')
                        }
                        
                        # Add additional fields for prd_stream notifications
                        if notification_data.get('notification_type') == 'prd_stream':
                            notification_message['content_chunk'] = notification_data.get('content_chunk', '')
                            notification_message['is_complete'] = notification_data.get('is_complete', False)
                            
                            # CONSOLE OUTPUT FOR PRD STREAMING
                            print("\n" + "="*80)
                            print(f"🟣 PRD STREAM IN WEBSOCKET CONSUMER")
                            print(f"📅 Time: {datetime.now().isoformat()}")
                            print(f"📏 Content Length: {len(notification_data.get('content_chunk', ''))} chars")
                            print(f"✅ Complete: {notification_data.get('is_complete', False)}")
                            if notification_data.get('content_chunk'):
                                content_preview = notification_data['content_chunk'][:200]
                                print(f"📝 Content: {content_preview}{'...' if len(notification_data['content_chunk']) > 200 else ''}")
                            print("="*80 + "\n")
                        
                        logger.info(f"SENDING NOTIFICATION MESSAGE: {notification_message}")
                        
                        if hasattr(self, 'using_groups') and self.using_groups:
                            logger.info(f"Sending via group to {self.room_group_name}")
                            # Create complete message for group send
                            group_message = {
                                'type': 'ai_response_chunk',
                                'chunk': '',
                                'is_final': False,
                                'is_notification': True,
                                'notification_type': notification_data.get('notification_type', 'features'),
                                'early_notification': notification_data.get('early_notification', False),
                                'function_name': notification_data.get('function_name', '')
                            }
                            
                            # Add additional fields for prd_stream notifications
                            if notification_data.get('notification_type') == 'prd_stream':
                                group_message['content_chunk'] = notification_data.get('content_chunk', '')
                                group_message['is_complete'] = notification_data.get('is_complete', False)
                            logger.info(f"Group message being sent: {group_message}")
                            await self.channel_layer.group_send(self.room_group_name, group_message)
                        else:
                            logger.info("Sending directly via WebSocket")
                            await self.send(text_data=json.dumps({
                                'type': 'ai_chunk',
                                **notification_message
                            }))
                        
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
                
                # Send each chunk to the client
                try:
                    if hasattr(self, 'using_groups') and self.using_groups:
                        await self.channel_layer.group_send(
                            self.room_group_name,
                            {
                                'type': 'ai_response_chunk',
                                'chunk': content,
                                'is_final': False
                            }
                        )
                    else:
                        await self.send(text_data=json.dumps({
                            'type': 'ai_chunk',
                            'chunk': content,
                            'is_final': False
                        }))
                except Exception as e:
                    logger.error(f"Error sending AI chunk: {str(e)}")
                
                # Small delay to simulate natural typing
                await asyncio.sleep(0.03)
            
            # Finalize any partial message or save the complete message
            await self.finalize_streaming_message(full_response)
            
            # Update conversation title if it's new
            if self.conversation and (not self.conversation.title or self.conversation.title == str(self.conversation.id)):
                # Use AI to generate a title based on first messages
                await self.generate_title_with_ai(user_message, full_response)
            
            # Get project_id if conversation is linked to a project
            if not project_id and self.conversation:
                project_id = await self.get_project_id()
                
            # Send message complete signal
            try:
                # Only send the final message if generation wasn't stopped
                # This prevents empty messages from being created after stopping
                if not self.should_stop_generation:
                    if hasattr(self, 'using_groups') and self.using_groups:
                        await self.channel_layer.group_send(
                            self.room_group_name,
                            {
                                'type': 'ai_response_chunk',
                                'chunk': '',
                                'is_final': True,
                                'conversation_id': self.conversation.id if self.conversation else None,
                                'provider': provider_name,
                                'project_id': project_id
                            }
                        )
                    else:
                        await self.send(text_data=json.dumps({
                            'type': 'ai_chunk',
                            'chunk': '',
                            'is_final': True,
                            'conversation_id': self.conversation.id if self.conversation else None,
                            'provider': provider_name,
                            'project_id': project_id
                        }))
                else:
                    # For stopped generation, just send conversation metadata without creating a new message
                    if hasattr(self, 'using_groups') and self.using_groups:
                        await self.channel_layer.group_send(
                            self.room_group_name,
                            {
                                'type': 'ai_response_chunk',
                                'chunk': None,  # Using None instead of empty string to distinguish
                                'is_final': True,
                                'conversation_id': self.conversation.id if self.conversation else None,
                                'provider': provider_name,
                                'project_id': project_id
                            }
                        )
                    else:
                        await self.send(text_data=json.dumps({
                            'type': 'ai_chunk',
                            'chunk': None,  # Using None instead of empty string to distinguish
                            'is_final': True,
                            'conversation_id': self.conversation.id if self.conversation else None,
                            'provider': provider_name,
                            'project_id': project_id
                        }))
            except Exception as e:
                logger.error(f"Error sending completion signal: {str(e)}")
            
            # Clear the active task reference
            self.active_generation_task = None
            
        except Exception as e:
            error_message = f"Sorry, I encountered an error: {str(e)}"
            await self.save_message('assistant', error_message)
            
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
                await self.send_error(error_message)
            
            # Clear the active task reference
            self.active_generation_task = None
    
    async def process_ai_stream(self, provider, messages, project_id, tools):
        """
        Enhanced process_ai_stream with auto-save
        """
        logger.debug(f"Messages: {messages}")
        try:
            conversation_id = self.conversation.id if self.conversation else None
            
            # Initialize message accumulator for auto-save
            accumulated_content = ""
            last_save_length = 0
            save_threshold = 100  # Save every 100 characters (reduced from 500)
            
            # Stream content directly from the now-async provider
            async for content in provider.generate_stream(messages, project_id, conversation_id, tools):
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
                        logger.debug("DETECTED SPECIALLY FORMATTED NOTIFICATION")
                        logger.debug(f"Notification JSON: {notification_json}")
                        
                        notification_data = json.loads(notification_json)
                        logger.debug(f"Parsed notification: {notification_data}")
                        
                        # Verify this is a notification
                        if notification_data.get('is_notification') and notification_data.get('notification_marker') == "__NOTIFICATION__":
                            logger.debug("Valid notification confirmed!")
                            
                            # Check if this is an early notification
                            is_early = notification_data.get('early_notification', False)
                            function_name = notification_data.get('function_name', '')
                            logger.debug(f"Is early notification: {is_early}")
                            logger.debug(f"Function name: {function_name}")
                            
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
                
                # Store as pending message for disconnect handling
                self.pending_message = accumulated_content
                
                # Auto-save periodically during streaming
                if len(accumulated_content) - last_save_length >= save_threshold:
                    logger.info(f"[STREAM] Calling auto_save_streaming_message at position {len(accumulated_content)}")
                    await self.auto_save_streaming_message(accumulated_content)
                    last_save_length = len(accumulated_content)
                
                # Yield the content for streaming
                yield content
                
        except Exception as e:
            logger.error(f"Error in process_ai_stream: {str(e)}")
            error_message = str(e)
            
            # Check for missing API key attributes
            if "'AnthropicProvider' object has no attribute 'anthropic_api_key'" in error_message:
                error_message = "No Anthropic API key configured. Please add API key here http://localhost:8000/accounts/integrations/."
            elif "'OpenAIProvider' object has no attribute 'openai_api_key'" in error_message:
                error_message = "No OpenAI API key configured. Please add API key here http://localhost:8000/accounts/integrations/."
            
            yield f"Error generating response: {error_message}"
        finally:
            # Don't clear pending_message here - it's needed for disconnect handling
            pass
    
    
    async def send_error(self, error_message):
        """
        Send error message to WebSocket
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': error_message
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
            
        conversation = Conversation.objects.create(
            user=self.user,
            title=title
        )
        
        # Set project reference if provided
        try:
            from projects.models import Project
            project = Project.objects.get(id=project_id, owner=self.user)
            conversation.project = project
            conversation.save()
            logger.debug(f"Set project reference for conversation {conversation.id} to project {project_id}")
        except Exception as e:
            # If we can't find the project, delete the conversation we just created
            conversation.delete()
            logger.error(f"Error setting project reference: {str(e)}")
            return None
                
        return conversation
    
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

        file_obj = ChatFile.objects.get(id=file_id)

        # Construct the full file path by joining MEDIA_ROOT with the relative file path
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
            return Message.objects.create(
                conversation=self.conversation,
                role=role,
                content_if_file=content_if_file
            )
        return None
        

    @database_sync_to_async
    def get_messages_for_ai(self):
        """
        Get messages for AI processing
        """
        if not self.conversation:
            return []
            
        messages = Message.objects.filter(conversation=self.conversation).order_by('-created_at')[:10]
        messages = reversed(list(messages))  # Convert to list and reverse
        # logger.debug(f"\n\n Messages: {messages}")
        return [
            {"role": msg.role, "content": msg.content if msg.content is not None and msg.content != "" else msg.content_if_file}
            for msg in messages
        ]
    
    @database_sync_to_async
    def get_chat_history(self):
        """
        Get chat history for the current conversation
        """
        if not self.conversation:
            return []
            
        messages = Message.objects.filter(conversation=self.conversation).order_by('created_at')
        return [
            {
                'role': msg.role,
                'content': msg.content if msg.content is not None or msg.content != "" else msg.content_if_file,
                'timestamp': msg.created_at.isoformat(),
                'is_partial': msg.is_partial  # Include partial status
            } for msg in messages
        ]
    
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
            print(f"\n\n\nBefore model selection: {self.user}")
            model_selection = await database_sync_to_async(ModelSelection.objects.get)(user=self.user)
            print(f"\n\n\nModel selection: {model_selection}")
            selected_model = model_selection.selected_model
            print(f"\n\n\nSelected model... #3: {selected_model}")
        except ModelSelection.DoesNotExist:
            # Create a default model selection if none exists
            model_selection = await database_sync_to_async(ModelSelection.objects.create)(
                user=self.user,
                selected_model='claude_4_sonnet'
            )
            selected_model = model_selection.selected_model

        if selected_model == "claude_4_sonnet":
            provider_name = "anthropic"
        else:
            provider_name = "openai"
        
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
            # Get project_id if available
            project_id = await self.get_project_id() if self.conversation else None
            
            # Use empty tools list for title generation (no function calls needed)
            tools = []
            
            # Generate title non-streaming
            title = ""
            async for content in self.process_ai_stream(provider, title_prompt, project_id, tools):
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
                await self.finalize_message()
                logger.info(f"Force saved message on disconnect: {len(self.pending_message)} chars")
            except Exception as e:
                logger.error(f"Error force saving message: {e}")
    
    async def auto_save_streaming_message(self, content):
        """Auto-save streaming AI message to prevent loss on disconnect"""
        logger.info(f"[AUTO_SAVE] Starting auto_save_streaming_message for conversation {self.conversation.id if self.conversation else 'None'}, content length: {len(content)}")
        
        if self.conversation:
            try:
                # Check if we already have a partial message for this conversation
                last_message = await database_sync_to_async(
                    lambda: Message.objects.filter(
                        conversation=self.conversation,
                        role='assistant',
                        is_partial=True
                    ).order_by('-created_at').first()
                )()
                
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
        """Finalize the streaming message - convert partial to complete"""
        logger.info(f"[FINALIZE] Starting finalize_streaming_message for conversation {self.conversation.id if self.conversation else 'None'}, content length: {len(full_content)}")
        
        if self.conversation and full_content:
            try:
                # Find any partial message
                partial_message = await database_sync_to_async(
                    lambda: Message.objects.filter(
                        conversation=self.conversation,
                        role='assistant',
                        is_partial=True
                    ).order_by('-created_at').first()
                )()
                
                logger.info(f"[FINALIZE] Found partial message ID: {partial_message.id if partial_message else 'None'}")
                
                if partial_message:
                    # Update and finalize the partial message
                    logger.info(f"[FINALIZE] Updating final message")
                    partial_message.content = full_content
                    partial_message.is_partial = False
                    await database_sync_to_async(partial_message.save)()
                    logger.debug(f"Finalized streaming message: {len(full_content)} chars")
                else:
                    # No partial message exists, create a complete one
                    logger.info(f"[FINALIZE] Creating final message")
                    await self.save_message('assistant', full_content)
                    logger.debug(f"Created final message (no partial found): {len(full_content)} chars")
                
                # Clear the pending message to prevent duplicate saves on disconnect
                self.pending_message = None
                    
            except Exception as e:
                logger.error(f"Error finalizing streaming message: {e}")
                # Fallback to regular save
                await self.save_message('assistant', full_content)
                # Clear pending message even in error case
                self.pending_message = None 