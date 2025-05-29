import json
import asyncio
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings

# Set up logger
logger = logging.getLogger(__name__)

# Import everything we need at the module level
# These imports are safe now because django.setup() is called in asgi.py before imports
from django.contrib.auth.models import User
from chat.models import Conversation, Message, ChatFile, ModelSelection
from projects.models import ProjectChecklist
from chat.utils import AIProvider, get_system_prompt_developer, get_system_prompt_design, get_system_prompt_product

import os
import base64
import uuid
from django.core.files.base import ContentFile
from chat.models import ChatFile, AgentRole
from django.conf import settings
from chat.utils.ai_tools import tools_code, tools_product, tools_design

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """
        Handle WebSocket connection
        """
        try:
            # Get user from scope
            self.user = self.scope["user"]
            
            # Each user joins their own room based on their username
            if self.user.is_authenticated:
                self.room_name = f"chat_{self.user.username}"
            else:
                self.room_name = "chat_anonymous"
                logger.warning("User is not authenticated, using anonymous chat room")
            
            # Create a sanitized group name for the channel layer
            self.room_group_name = self.room_name.replace(" ", "_")
            
            # Accept connection
            await self.accept()
            logger.info(f"WebSocket connection accepted for user {self.user} in room {self.room_group_name}")
            
            # Initialize properties
            self.conversation = None
            self.active_generation_task = None
            self.should_stop_generation = False
            
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
            # Try to accept and send error
            try:
                await self.accept()
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': f"Connection error: {str(e)}"
                }))
            except Exception as inner_e:
                logger.error(f"Could not accept WebSocket connection: {str(inner_e)}")
    
    async def disconnect(self, close_code):
        """
        Handle WebSocket disconnection
        """
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
        # Create response data with all available properties
        response_data = {
            'type': 'ai_chunk',
            'chunk': event['chunk'],
            'is_final': event['is_final'],
            'conversation_id': event.get('conversation_id'),
            'provider': event.get('provider'),
            'project_id': event.get('project_id')
        }
        
        # Add notification data if present
        if event.get('is_notification'):
            logger.debug("NOTIFICATION BEING SENT TO CLIENT")
            logger.debug(f"Notification type: {event.get('notification_type', 'features')}")
            logger.debug(f"Is early notification: {event.get('early_notification', False)}")
            logger.debug(f"Function name: {event.get('function_name', '')}")
            logger.debug(f"Full event data: {event}")
            
            # Copy all notification-related fields to the response
            response_data['is_notification'] = True
            response_data['notification_type'] = event.get('notification_type', 'features')
            
            # Add early notification flag and function name if present
            if event.get('early_notification'):
                response_data['early_notification'] = True
                response_data['function_name'] = event.get('function_name', '')
        
        # Send the response to the client
        try:
            await self.send(text_data=json.dumps(response_data))
            logger.debug(f"Successfully sent {'notification' if event.get('is_notification') else 'chunk'} to client")
        except Exception as e:
            logger.error(f"Error sending response to client: {str(e)}")
    
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

        model_selection = await database_sync_to_async(ModelSelection.objects.get)(user=self.user)
        selected_model = model_selection.selected_model
        
        # Get the appropriate AI provider
        provider = AIProvider.get_provider(provider_name, selected_model)
        
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
                
                # Skip notification content from being added to the full response
                if isinstance(content, str) and (
                    (content.startswith("__NOTIFICATION__") and content.endswith("__NOTIFICATION__")) or
                    (content.startswith("{") and content.endswith("}") and "is_notification" in content)
                ):
                    logger.debug(f"Skipping notification content from full response: {content[:30]}...")
                    continue
                
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
            
            # Save the complete message
            await self.save_message('assistant', full_response)
            
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
        Process the AI provider's stream in an async-friendly way
        
        The AI provider's generate_stream method is now async, so we can call it directly.
        """
        logger.debug(f"Messages: {messages}")
        try:
            conversation_id = self.conversation.id if self.conversation else None
            
            # Stream content directly from the now-async provider
            async for content in provider.generate_stream(messages, project_id, conversation_id, tools):
                # Check if we should stop generation
                if self.should_stop_generation:
                    logger.debug("Stopping AI stream generation due to user request")
                    break
                
                # Check if this is a specially formatted notification string
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
                                'type': 'ai_chunk',
                                'chunk': '',  # No visible content
                                'is_final': False,
                                'is_notification': True,
                                'notification_type': notification_data.get('notification_type', 'features')
                            }
                            
                            # Add early notification flag and function name if present
                            if is_early:
                                notification_message['early_notification'] = True
                                notification_message['function_name'] = function_name
                            
                            # Send notification to client
                            if hasattr(self, 'using_groups') and self.using_groups:
                                await self.channel_layer.group_send(
                                    self.room_group_name,
                                    {
                                        'type': 'ai_response_chunk',
                                        **notification_message
                                    }
                                )
                            else:
                                await self.send(text_data=json.dumps(notification_message))
                            
                            # Skip yielding this chunk as text content
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
                                'type': 'ai_chunk',
                                'chunk': '',  # No visible content
                                'is_final': False,
                                'is_notification': True,
                                'notification_type': notification_data.get('notification_type', 'features')
                            }
                            
                            # Add early notification flag and function name if present
                            if is_early:
                                notification_message['early_notification'] = True
                                notification_message['function_name'] = function_name
                            
                            if hasattr(self, 'using_groups') and self.using_groups:
                                await self.channel_layer.group_send(
                                    self.room_group_name,
                                    {
                                        'type': 'ai_response_chunk',
                                        **notification_message
                                    }
                                )
                            else:
                                await self.send(text_data=json.dumps(notification_message))
                            continue  # Skip yielding this chunk as text
                        else:
                            logger.debug("This is NOT a notification (missing is_notification flag)")
                    except json.JSONDecodeError:
                        logger.debug("Not a valid JSON - treating as normal text")
                        # Not a valid JSON notification, treat as normal text
                        pass
                
                # Normal text chunk - yield it
                yield content
                
        except Exception as e:
            logger.error(f"Error in process_ai_stream: {str(e)}")
            yield f"Error generating response: {str(e)}"
    
    
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
                'timestamp': msg.created_at.isoformat()
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
        model_selection = await database_sync_to_async(ModelSelection.objects.get)(user=self.user)
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