import json
import logging
import asyncio
import traceback
import openai
from typing import List, Dict, Any, Optional, AsyncGenerator

from .base import BaseLLMProvider

# These imports will be handled during integration
# from development.utils.ai_providers import execute_tool_call, get_notification_type_for_tool, track_token_usage
# from development.utils.streaming_handlers import StreamingTagHandler, format_notification

logger = logging.getLogger(__name__)


class XAIProvider(BaseLLMProvider):
    """XAI (Grok) provider implementation using OpenAI-compatible interface"""
    
    MODEL_MAPPING = {
        "grok_4": "grok-4",
    }
    
    def __init__(self, selected_model: str, user=None, conversation=None, project=None):
        super().__init__(selected_model, user, conversation, project)
        
        # Map model selection to actual model name
        self.model = self.MODEL_MAPPING.get(selected_model, "grok-4")
        if selected_model not in self.MODEL_MAPPING:
            logger.warning(f"Unknown model {selected_model}, defaulting to grok-4")
            
        logger.info(f"Selected XAI model: {self.model}")
        
        # XAI API configuration
        self.base_url = "https://api.x.ai/v1"
    
    async def _ensure_client(self):
        """Ensure the client is initialized with API key"""
        # Try to fetch API key from user profile if available
        if self.user:
            try:
                self.api_key = await self._get_api_key_from_db(self.user, 'xai_api_key')
                logger.info(f"Fetched XAI API key from user {self.user.id} profile")
            except Exception as e:
                logger.warning(f"Could not fetch XAI API key: {e}")
        
        # Initialize client using OpenAI-compatible interface
        if self.api_key:
            self.client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
        else:
            logger.warning("No XAI API key found")
    
    def _convert_messages_to_provider_format(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """XAI uses OpenAI-compatible format, so just return as-is"""
        return messages
    
    def _convert_tools_to_provider_format(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """XAI uses OpenAI-compatible format, so just return as-is"""
        return tools
    
    async def generate_stream(self, messages: List[Dict[str, Any]], 
                            project_id: Optional[int], 
                            conversation_id: Optional[int], 
                            tools: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        """Generate streaming response from XAI Grok"""
        # Ensure client is initialized with API keys
        await self._ensure_client()
        
        # Check if client is initialized
        if not self.client:
            yield "Error: No XAI API key configured. Please add API key [here](/settings/)."
            return
            
        current_messages = list(messages) # Work on a copy
        
        # Get user and project/conversation for token tracking
        user = None
        project = None
        conversation = None
        
        try:
            if conversation_id:
                conversation = await asyncio.to_thread(
                    lambda: self.conversation.__class__.objects.select_related('user', 'project').get(id=conversation_id)
                )
                user = conversation.user
                project = conversation.project
            elif project_id:
                project = await asyncio.to_thread(
                    lambda: self.project.__class__.objects.select_related('owner').get(id=project_id)
                )
                user = project.owner
        except Exception as e:
            logger.warning(f"Could not get user/project/conversation for token tracking: {e}")

        # Import will be fixed when integrating with main codebase
        from development.utils.streaming_handlers import StreamingTagHandler
        
        # Initialize streaming tag handler
        tag_handler = StreamingTagHandler()
        
        # Buffer to capture ALL assistant output for accurate token counting
        total_assistant_output = ""

        while True: # Loop to handle potential multi-turn tool calls
            try:
                params = {
                    "model": self.model,
                    "messages": current_messages,
                    "stream": True,
                    "tool_choice": "auto", 
                    "tools": tools,
                    "stream_options": {"include_usage": True}  # Request usage info in stream
                }
                
                logger.debug(f"Making XAI API call with {len(current_messages)} messages.")
                
                # Run the blocking API call in a thread
                response_stream = await asyncio.to_thread(
                    self.client.chat.completions.create, **params
                )
                
                # Variables for this specific API call
                tool_calls_requested = [] # Stores {id, function_name, function_args_str}
                full_assistant_message = {"role": "assistant", "content": None, "tool_calls": []} # To store the complete assistant turn

                logger.debug("New Loop!!")
                
                # Variables for token tracking
                usage_data = None
                
                # --- Process the stream from the API --- 
                async for chunk in self._process_stream_async(response_stream):
                    delta = chunk.choices[0].delta if chunk.choices else None
                    finish_reason = chunk.choices[0].finish_reason if chunk.choices else None
                    
                    # Check for usage information in the chunk
                    if hasattr(chunk, 'usage') and chunk.usage:
                        usage_data = chunk.usage
                        logger.debug(f"Token usage received: {usage_data}")

                    if not delta and not usage_data: continue # Skip empty chunks

                    # --- Accumulate Text Content --- 
                    if delta.content:
                        text = delta.content
                        
                        # Capture ALL assistant output for token counting
                        total_assistant_output += text
                        logger.debug(f"Captured {len(text)} chars of assistant output, total: {len(total_assistant_output)}")
                        
                        # Process text through tag handler
                        output_text, notification, mode_message = tag_handler.process_text_chunk(text, project_id)
                        
                        # Yield mode message if entering a special mode
                        if mode_message:
                            yield mode_message
                        
                        # Import will be fixed when integrating with main codebase
                        from development.utils.streaming_handlers import format_notification
                        
                        # Yield notification if present
                        if notification:
                            yield format_notification(notification)
                        
                        # Yield output text if present
                        if output_text:
                            yield output_text
                            
                        if full_assistant_message["content"] is None:
                            full_assistant_message["content"] = ""
                        full_assistant_message["content"] += text

                    # --- Accumulate Tool Call Details --- 
                    if delta.tool_calls:
                        for tool_call_chunk in delta.tool_calls:
                            tc_index = tool_call_chunk.index
                            while len(tool_calls_requested) <= tc_index:
                                tool_calls_requested.append({"id": None, "type": "function", "function": {"name": None, "arguments": ""}})
                            
                            current_tc = tool_calls_requested[tc_index]
                            
                            if tool_call_chunk.id:
                                current_tc["id"] = tool_call_chunk.id
                            if tool_call_chunk.function:
                                if tool_call_chunk.function.name:
                                    function_name = tool_call_chunk.function.name
                                    current_tc["function"]["name"] = function_name
                                    
                                    # Import will be fixed when integrating with main codebase
                                    from development.utils.ai_providers import get_notification_type_for_tool
                                    
                                    # Determine notification type based on function name
                                    notification_type = get_notification_type_for_tool(function_name)
                                    
                                    # Skip early notification for stream functions
                                    if function_name not in ["stream_prd_content", "stream_implementation_content"]:
                                        logger.debug(f"SENDING EARLY NOTIFICATION FOR {function_name}")
                                        early_notification = {
                                            "is_notification": True,
                                            "notification_type": notification_type or "tool",
                                            "early_notification": True,
                                            "function_name": function_name,
                                            "notification_marker": "__NOTIFICATION__"
                                        }
                                        notification_json = json.dumps(early_notification)
                                        logger.debug(f"Early notification sent: {notification_json}")
                                        yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                                
                                if tool_call_chunk.function.arguments:
                                    current_tc["function"]["arguments"] += tool_call_chunk.function.arguments

                    # --- Check Finish Reason --- 
                    if finish_reason:
                        logger.debug(f"Finish Reason Detected: {finish_reason}")
                        
                        if finish_reason == "tool_calls":
                            # Finalize tool_calls_requested
                            for tc in tool_calls_requested:
                                if not tc["function"]["arguments"].strip():
                                    tc["function"]["arguments"] = "{}"

                            # Build the assistant message
                            full_assistant_message["tool_calls"] = tool_calls_requested

                            # Remove the content field if it was just tool calls
                            if full_assistant_message["content"] is None:
                                full_assistant_message.pop("content")

                            # Append to the running conversation history
                            current_messages.append(full_assistant_message)
                            
                            # --- Execute Tools and Prepare Next Call --- 
                            tool_results_messages = []
                            for tool_call_to_execute in tool_calls_requested:
                                tool_call_id = tool_call_to_execute["id"]
                                tool_call_name = tool_call_to_execute["function"]["name"]
                                tool_call_args_str = tool_call_to_execute["function"]["arguments"]
                                
                                logger.debug(f"XAI Provider - Tool Call ID: {tool_call_id}")
                                
                                # Import will be fixed when integrating with main codebase
                                from development.utils.ai_providers import execute_tool_call
                                
                                # Use the shared execute_tool_call function
                                result_content, notification_data, yielded_content = await execute_tool_call(
                                    tool_call_name, tool_call_args_str, project_id, conversation_id
                                )
                                
                                # Yield any content that needs to be streamed
                                if yielded_content:
                                    yield yielded_content
                                
                                # Append tool result message
                                tool_results_messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call_id,
                                    "content": f"Tool call {tool_call_name}() completed. {result_content}."
                                })
                                
                                # If we have notification data, yield it
                                if notification_data:
                                    logger.debug("YIELDING NOTIFICATION DATA TO CONSUMER")
                                    notification_json = json.dumps(notification_data)
                                    logger.debug(f"Notification JSON: {notification_json}")
                                    yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                                
                            current_messages.extend(tool_results_messages)
                            # Continue the outer while loop to make the next API call
                            break
                        
                        elif finish_reason == "stop":
                            # Conversation finished naturally
                            
                            # Flush any remaining buffer content
                            flushed_output = tag_handler.flush_buffer()
                            if flushed_output:
                                yield flushed_output
                            
                            # Save any captured data
                            logger.info(f"[XAI] Stream finished, checking for captured files to save")
                            save_notifications = await tag_handler.save_captured_data(project_id)
                            logger.info(f"[XAI] Got {len(save_notifications)} save notifications")
                            for notification in save_notifications:
                                logger.info(f"[XAI] Yielding save notification: {notification}")
                                # Import will be fixed when integrating with main codebase
                                from development.utils.streaming_handlers import format_notification
                                formatted = format_notification(notification)
                                logger.info(f"[XAI] Formatted notification: {formatted[:100]}...")
                                yield formatted
                            
                            # Track token usage before exiting
                            if usage_data and user:
                                # Import will be fixed when integrating with main codebase
                                from development.utils.ai_providers import track_token_usage
                                await track_token_usage(
                                    user, project, conversation, usage_data, 'xai', self.model
                                )
                            return
                        else:
                            logger.warning(f"Unhandled finish reason: {finish_reason}")
                            if usage_data and user:
                                # Import will be fixed when integrating with main codebase
                                from development.utils.ai_providers import track_token_usage
                                await track_token_usage(
                                    user, project, conversation, usage_data, 'xai', self.model
                                )
                            return
                
                # If the inner loop finished because of tool_calls, continue
                if finish_reason == "tool_calls":
                    continue
                else:
                    logger.warning("Stream ended unexpectedly.")
                    return

            except Exception as e:
                logger.error(f"Critical Error: {str(e)}\n{traceback.format_exc()}")
                yield f"Error with XAI stream: {str(e)}"
                return