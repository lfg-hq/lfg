import json
import logging
import asyncio
import traceback
import openai
import tiktoken
from typing import List, Dict, Any, Optional, AsyncGenerator

from .base import BaseLLMProvider

# Import functions from ai_common and streaming_handlers
from factory.ai_common import execute_tool_call, get_notification_type_for_tool, track_token_usage
from factory.streaming_handlers import StreamingTagHandler, format_notification
from factory.token_tracking import UsageData

logger = logging.getLogger(__name__)

# Debug flag for enhanced token tracking logging
DEBUG_TOKEN_TRACKING = logger.isEnabledFor(logging.DEBUG)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI provider implementation"""
    
    MODEL_MAPPING = {
        "gpt-5": "gpt-5",
        "gpt-5-mini": "gpt-5-mini",
    }
    
    # Class-level metrics for tracking token usage success rates
    _usage_tracking_stats = {
        'api_success': 0,
        'api_failure': 0,
        'estimation_fallback': 0,
        'validation_failure': 0
    }
    
    def __init__(self, selected_model: str, user=None, conversation=None, project=None):
        super().__init__(selected_model, user, conversation, project)
        
        # Map model selection to actual model name
        self.model = self.MODEL_MAPPING.get(selected_model, "gpt-5-mini")
        if selected_model not in self.MODEL_MAPPING:
            logger.warning(f"Unknown model {selected_model}, defaulting to gpt-5-mini")
            
        logger.info(f"OpenAI Provider initialized with model: {self.model}")
    
    async def _ensure_client(self):
        """Ensure the client is initialized with API key"""
        # Try to fetch API key from user profile if available
        if self.user:
            try:
                self.api_key = await self._get_api_key_from_db(self.user, 'openai_api_key')
                logger.info(f"Fetched OpenAI API key from user {self.user.id} profile")
            except Exception as e:
                logger.warning(f"Could not fetch OpenAI API key: {e}")
        
        # Initialize client
        if self.api_key:
            self.client = openai.OpenAI(api_key=self.api_key)
        else:
            logger.warning("No OpenAI API key found")
    
    def _convert_messages_to_provider_format(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """OpenAI uses the standard format, so just return as-is"""
        return messages
    
    def _convert_tools_to_provider_format(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """OpenAI uses the standard format, so just return as-is"""
        return tools
    
    def estimate_tokens(self, messages, model=None, output_text=None):
        """Estimate token count for messages and output using tiktoken"""
        logger.debug(f"estimate_tokens called with {len(messages)} messages, model={model}, output_text length={len(output_text) if output_text else 0}")
        
        if not tiktoken:
            logger.warning("tiktoken not available, cannot estimate tokens")
            return None, None
            
        try:
            # Use the model-specific encoding or fall back to cl100k_base
            try:
                if model == "gpt-5" or model == "gpt-5-mini":
                    # Try to get encoding for gpt-4 (closest available)
                    encoding = tiktoken.encoding_for_model("gpt-4")
                else:
                    encoding = tiktoken.get_encoding("cl100k_base")
            except Exception:
                # Fallback to cl100k_base if model-specific encoding not found
                encoding = tiktoken.get_encoding("cl100k_base")
            
            input_tokens = 0
            
            # Count input tokens from messages
            logger.debug(f"Counting tokens for {len(messages)} messages")
            for i, message in enumerate(messages):
                msg_tokens = 0
                # Count role tokens (usually 3-4 tokens)
                msg_tokens += 4
                
                # Count content tokens
                content = message.get("content")
                if content and isinstance(content, str):
                    content_tokens = len(encoding.encode(content))
                    msg_tokens += content_tokens
                    logger.debug(f"Message {i} ({message.get('role')}): {content_tokens} content tokens")
                elif content:
                    # Handle non-string content (list, dict, etc.) by converting to string
                    logger.debug(f"Message {i} has non-string content of type {type(content)}, converting to string")
                    content_str = str(content) if content else ""
                    content_tokens = len(encoding.encode(content_str))
                    msg_tokens += content_tokens
                    logger.debug(f"Message {i} ({message.get('role')}): {content_tokens} content tokens (converted)")
                
                # Count tool calls if present
                if message.get("tool_calls"):
                    tool_tokens = 0
                    for tool_call in message["tool_calls"]:
                        # Estimate tokens for tool call structure
                        tool_tokens += 10  # Base overhead for tool call
                        func_name = tool_call.get("function", {}).get("name")
                        if func_name and isinstance(func_name, str):
                            tool_tokens += len(encoding.encode(func_name))
                        
                        func_args = tool_call.get("function", {}).get("arguments")
                        if func_args:
                            if isinstance(func_args, str):
                                tool_tokens += len(encoding.encode(func_args))
                            else:
                                # Convert non-string arguments to string
                                tool_tokens += len(encoding.encode(str(func_args)))
                    msg_tokens += tool_tokens
                    logger.debug(f"Message {i}: {tool_tokens} tool call tokens")
                
                # Count tool results
                if message.get("role") == "tool":
                    msg_tokens += 5  # Tool message overhead
                    
                input_tokens += msg_tokens
            
            # Add some overhead for formatting
            input_tokens += 10
            
            # Count output tokens if provided
            output_tokens = 0
            if output_text:
                output_tokens = len(encoding.encode(output_text))
                logger.debug(f"Output text length: {len(output_text)} chars, {output_tokens} tokens")
            
            logger.info(f"Token estimation complete - Input: {input_tokens}, Output: {output_tokens}, Total: {input_tokens + output_tokens}")
            return input_tokens, output_tokens
            
        except Exception as e:
            logger.error(f"Failed to estimate tokens: {e}", exc_info=True)
            return None, None
    
    def _extract_usage_from_chunk(self, chunk) -> Optional[Any]:
        """Extract usage data from a chunk, checking all possible locations"""
        try:
            # Check primary location
            if hasattr(chunk, 'usage') and chunk.usage:
                if DEBUG_TOKEN_TRACKING:
                    logger.debug(f"Found usage data in chunk.usage: {chunk.usage}")
                return chunk.usage
            
            # Check if usage might be in choices (some API versions)
            if hasattr(chunk, 'choices') and chunk.choices:
                for i, choice in enumerate(chunk.choices):
                    if hasattr(choice, 'usage') and choice.usage:
                        if DEBUG_TOKEN_TRACKING:
                            logger.debug(f"Found usage data in chunk.choices[{i}].usage: {choice.usage}")
                        return choice.usage
            
            # Check if usage is in the chunk directly as dict
            if isinstance(chunk, dict) and 'usage' in chunk:
                usage_data = chunk['usage']
                if usage_data:
                    if DEBUG_TOKEN_TRACKING:
                        logger.debug(f"Found usage data in chunk['usage']: {usage_data}")
                    return usage_data
            
            # Enhanced debugging for missing usage data
            if DEBUG_TOKEN_TRACKING:
                chunk_attrs = [attr for attr in dir(chunk) if not attr.startswith('_')]
                logger.debug(f"No usage data found in chunk. Available attributes: {chunk_attrs}")
                if hasattr(chunk, 'usage'):
                    logger.debug(f"chunk.usage exists but is: {repr(chunk.usage)}")
                
            return None
        except Exception as e:
            logger.debug(f"Error extracting usage from chunk: {e}")
            if DEBUG_TOKEN_TRACKING:
                logger.debug(f"Chunk type: {type(chunk)}, Chunk repr: {repr(chunk)[:200]}")
            return None
    
    def _validate_usage_data(self, usage_data) -> bool:
        """Validate that usage data has the expected attributes"""
        try:
            if not usage_data:
                return False
            
            required_attrs = ['prompt_tokens', 'completion_tokens']
            for attr in required_attrs:
                if not hasattr(usage_data, attr):
                    logger.debug(f"Usage data missing attribute: {attr}")
                    return False
                if getattr(usage_data, attr) is None:
                    logger.debug(f"Usage data attribute {attr} is None")
                    return False
            
            return True
        except Exception as e:
            logger.debug(f"Error validating usage data: {e}")
            return False
    
    async def _get_or_estimate_usage(self, messages: List[Dict[str, Any]], total_assistant_output: str, 
                                   usage_data: Optional[Any] = None) -> Optional[UsageData]:
        """Get usage data from API or estimate tokens as fallback"""
        try:
            # Try to use API-provided usage data first
            if usage_data and self._validate_usage_data(usage_data):
                logger.info(f"Using API-provided token usage: input={usage_data.prompt_tokens}, output={usage_data.completion_tokens}")
                self._usage_tracking_stats['api_success'] += 1
                return UsageData.from_openai(usage_data)
            elif usage_data:
                # Usage data exists but failed validation
                self._usage_tracking_stats['validation_failure'] += 1
                logger.warning(f"Usage data validation failed for: {usage_data}")
            else:
                # No usage data provided
                self._usage_tracking_stats['api_failure'] += 1
            
            # Fall back to estimation
            logger.warning("No valid usage data from OpenAI API, using tiktoken estimation")
            self._usage_tracking_stats['estimation_fallback'] += 1
            
            estimated_input_tokens, estimated_output_tokens = self.estimate_tokens(
                messages, self.model, total_assistant_output
            )
            
            if estimated_input_tokens is not None and estimated_output_tokens is not None:
                logger.info(f"Using estimated tokens: input={estimated_input_tokens}, output={estimated_output_tokens}")
                return UsageData.from_estimation(estimated_input_tokens, estimated_output_tokens)
            
            logger.error("Failed to estimate tokens")
            return None
            
        except Exception as e:
            logger.error(f"Error getting or estimating usage: {e}")
            return None
    
    async def _track_usage_if_available(self, user, project, conversation, 
                                      messages: List[Dict[str, Any]], total_assistant_output: str,
                                      usage_data: Optional[Any] = None) -> bool:
        """Track token usage if user is available, return True if successful"""
        if not user:
            logger.warning("Cannot track token usage - no user available")
            return False
        
        try:
            standardized_usage = await self._get_or_estimate_usage(messages, total_assistant_output, usage_data)
            if standardized_usage:
                await track_token_usage(user, project, conversation, standardized_usage, 'openai', self.model)
                logger.debug("Token usage tracked successfully")
                
                # Log tracking statistics periodically
                self._log_usage_tracking_stats()
                
                return True
            else:
                logger.error("Failed to get usage data for tracking")
                return False
        except Exception as e:
            logger.error(f"Failed to track token usage: {e}")
            return False
    
    @classmethod
    def get_usage_tracking_stats(cls) -> dict:
        """Get token usage tracking statistics"""
        return cls._usage_tracking_stats.copy()
    
    @classmethod
    def reset_usage_tracking_stats(cls):
        """Reset token usage tracking statistics"""
        cls._usage_tracking_stats = {
            'api_success': 0,
            'api_failure': 0,
            'estimation_fallback': 0,
            'validation_failure': 0
        }
    
    def _log_usage_tracking_stats(self):
        """Log current usage tracking statistics periodically"""
        stats = self._usage_tracking_stats
        total_requests = sum(stats.values())
        
        if total_requests > 0 and total_requests % 10 == 0:  # Log every 10 requests
            api_success_rate = (stats['api_success'] / total_requests) * 100
            logger.info(f"Token tracking stats (last {total_requests} requests): "
                       f"API success: {api_success_rate:.1f}%, "
                       f"Estimation fallback: {stats['estimation_fallback']}, "
                       f"Validation failures: {stats['validation_failure']}, "
                       f"API failures: {stats['api_failure']}")
    
    async def generate_stream(self, messages: List[Dict[str, Any]], 
                            project_id: Optional[int], 
                            conversation_id: Optional[int], 
                            tools: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        """Generate streaming response from OpenAI"""
        logger.info(f"OpenAI generate_stream called - Model: {self.model}, Messages: {len(messages)}, Tools: {len(tools) if tools else 0}")
        
        # Check token limits before proceeding
        can_proceed, error_message, remaining_tokens = await self.check_token_limits()
        if not can_proceed:
            yield f"Error: {error_message}"
            return
        
        # Ensure client is initialized with API keys
        await self._ensure_client()
        
        # Check if client is initialized
        if not self.client:
            yield "Error: No OpenAI API key configured. Please add API key [here](/settings/)."
            return
            
        current_messages = list(messages) # Work on a copy
        
        # Use the user, project, and conversation from the instance
        # These are already set in the __init__ method of the base class
        user = self.user
        project = self.project
        conversation = self.conversation
        
        # Log if user is available for token tracking
        if user:
            logger.debug(f"User available for token tracking: {user.id}")
        else:
            logger.warning("No user available for token tracking")

        
        # Initialize streaming tag handler
        tag_handler = StreamingTagHandler()
        
        # Buffer to capture ALL assistant output for accurate token counting
        total_assistant_output = ""

        logger.debug(f"Starting OpenAI stream generation loop")

        # Add web search tool
        search_tool = {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"}
                    },
                    "required": ["query"]
                }
            }
        }
        tools.append(search_tool)

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
                
                logger.debug(f"Making API call with {len(current_messages)} messages.")
                
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
                chunk_count = 0
                last_chunk = None
                async for chunk in self._process_stream_async(response_stream):
                    chunk_count += 1
                    last_chunk = chunk  # Keep track of last chunk
                    
                    # OpenAI sometimes sends empty choices array with usage data
                    delta = chunk.choices[0].delta if chunk.choices and len(chunk.choices) > 0 else None
                    finish_reason = chunk.choices[0].finish_reason if chunk.choices and len(chunk.choices) > 0 else None
                    
                    # Debug log every chunk to understand the structure
                    if chunk_count <= 3 or finish_reason:  # Log first 3 chunks and final chunk
                        logger.debug(f"Chunk {chunk_count}: choices={bool(chunk.choices)}, delta={bool(delta)}, finish_reason={finish_reason}, has_usage={hasattr(chunk, 'usage')}")
                    
                    # Check for usage information in the chunk using helper method
                    chunk_usage = self._extract_usage_from_chunk(chunk)
                    if chunk_usage:
                        usage_data = chunk_usage
                        logger.info(f"Token usage received from OpenAI API in chunk {chunk_count}: input={getattr(usage_data, 'prompt_tokens', 'N/A')}, output={getattr(usage_data, 'completion_tokens', 'N/A')}, total={getattr(usage_data, 'total_tokens', 'N/A')}")
                        if chunk_count <= 3 or finish_reason:  # Detailed logging for debugging
                            logger.debug(f"Usage data object: {usage_data}")
                            logger.debug(f"Usage data dir: {[attr for attr in dir(usage_data) if not attr.startswith('_')]}")
                    
                    # Debug logging for first few chunks and final chunk
                    if chunk_count <= 3 or finish_reason:
                        logger.debug(f"Chunk attributes: {[attr for attr in dir(chunk) if not attr.startswith('_')]}")

                    # Don't skip chunks that might contain only usage data
                    if not delta and not finish_reason and not chunk_usage: 
                        logger.debug(f"Skipping empty chunk {chunk_count}")
                        continue # Skip empty chunks

                    # --- Accumulate Text Content --- 
                    if delta.content:
                        text = delta.content
                        
                        # Capture ALL assistant output for token counting
                        total_assistant_output += text
                        logger.debug(f"Captured {len(text)} chars of assistant output, total: {len(total_assistant_output)}")
                        
                        # Process text through tag handler
                        logger.debug(f"[OPENAI] Calling process_text_chunk with project_id: {project_id}")
                        output_text, notification, mode_message = await tag_handler.process_text_chunk(text, project_id)
                        
                        # Yield mode message if entering a special mode
                        if mode_message:
                            yield mode_message
                        
                        
                        # Yield notification if present
                        if notification:
                            yield format_notification(notification)
                        
                        # Yield output text if present
                        if output_text:
                            yield output_text
                        
                        # Check for immediate notifications to yield
                        immediate_notifications = tag_handler.get_immediate_notifications()
                        if immediate_notifications:
                            logger.info(f"[OPENAI] Found {len(immediate_notifications)} immediate notifications")
                        for immediate_notification in immediate_notifications:
                            logger.info(f"[OPENAI] Yielding immediate notification: {immediate_notification.get('notification_type')}")
                            logger.info(f"[OPENAI] Full notification data: {immediate_notification}")
                            formatted = format_notification(immediate_notification)
                            logger.info(f"[OPENAI] Formatted notification: {formatted[:200]}...")
                            yield formatted
                        
                        # Update the full assistant message
                        if full_assistant_message["content"] is None:
                            full_assistant_message["content"] = ""
                        full_assistant_message["content"] += text

                    # --- Accumulate Tool Call Details --- 
                    if delta.tool_calls:
                        for tool_call_chunk in delta.tool_calls:
                            # Find or create the tool call entry
                            tc_index = tool_call_chunk.index
                            while len(tool_calls_requested) <= tc_index:
                                tool_calls_requested.append({"id": None, "type": "function", "function": {"name": None, "arguments": ""}})
                            
                            current_tc = tool_calls_requested[tc_index]
                            
                            if tool_call_chunk.id:
                                current_tc["id"] = tool_call_chunk.id
                            if tool_call_chunk.function:
                                if tool_call_chunk.function.name:
                                    # Send early notification as soon as we know the function name
                                    function_name = tool_call_chunk.function.name
                                    current_tc["function"]["name"] = function_name
                                    
                                    
                                    # Determine notification type based on function name
                                    notification_type = get_notification_type_for_tool(function_name)
                                    
                                    # Skip early notification for stream_prd_content and stream_implementation_content
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
                                        yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                                
                                if tool_call_chunk.function.arguments:
                                    current_tc["function"]["arguments"] += tool_call_chunk.function.arguments

                    # --- Check Finish Reason --- 
                    if finish_reason:
                        logger.debug(f"Finish Reason Detected: {finish_reason}")
                        
                        # Flush any remaining buffer content
                        flushed_output = tag_handler.flush_buffer()
                        if flushed_output:
                            yield flushed_output
                        
                        if finish_reason == "tool_calls":
                            # Process tool calls...
                            for tc in tool_calls_requested:
                                if not tc["function"]["arguments"].strip():
                                    tc["function"]["arguments"] = "{}"

                            full_assistant_message["tool_calls"] = tool_calls_requested

                            if full_assistant_message["content"] is None:
                                full_assistant_message.pop("content")

                            current_messages.append(full_assistant_message)
                            
                            # Execute tools
                            tool_results_messages = []
                            for tool_call_to_execute in tool_calls_requested:
                                tool_call_id = tool_call_to_execute["id"]
                                tool_call_name = tool_call_to_execute["function"]["name"]
                                tool_call_args_str = tool_call_to_execute["function"]["arguments"]
                                
                                logger.debug(f"OpenAI Provider - Tool Call ID: {tool_call_id}")
                                
                                
                                # Use the shared execute_tool_call function
                                result_content, notification_data, yielded_content = await execute_tool_call(
                                    tool_call_name, tool_call_args_str, project_id, conversation_id
                                )
                                
                                if yielded_content:
                                    yield yielded_content
                                
                                tool_results_messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call_id,
                                    "content": f"Tool call {tool_call_name}() completed. {result_content}."
                                })
                                
                                if notification_data:
                                    logger.debug("YIELDING NOTIFICATION DATA TO CONSUMER")
                                    notification_json = json.dumps(notification_data)
                                    yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                                
                            current_messages.extend(tool_results_messages)
                            
                            # Track token usage for tool calls using consolidated helper
                            await self._track_usage_if_available(
                                user, project, conversation, current_messages, total_assistant_output, usage_data
                            )
                            
                            break # Break inner chunk loop
                        
                        elif finish_reason == "stop":
                            # Don't return immediately - we need to check for usage data after loop
                            logger.debug("Finish reason is 'stop', will check for usage data after loop")
                            break  # Break inner loop to check for usage data
                        else:
                            # Handle other finish reasons
                            logger.warning(f"Unhandled finish reason: {finish_reason}")
                            return
                
                # After streaming completes, check last chunk for usage data
                if not usage_data and last_chunk:
                    last_chunk_usage = self._extract_usage_from_chunk(last_chunk)
                    if last_chunk_usage:
                        usage_data = last_chunk_usage
                        logger.info(f"Token usage found in last chunk: input={getattr(usage_data, 'prompt_tokens', 'N/A')}, output={getattr(usage_data, 'completion_tokens', 'N/A')}, total={getattr(usage_data, 'total_tokens', 'N/A')}")
                
                # If the inner loop finished because of tool_calls, continue
                if finish_reason == "tool_calls":
                    continue
                elif finish_reason == "stop":
                    # Handle normal completion
                    # Check for any pending saves/edits first
                    logger.info(f"[OPENAI] Checking for pending saves/edits")
                    pending_notifications = await tag_handler.check_and_save_pending_files()
                    logger.info(f"[OPENAI] Got {len(pending_notifications)} pending notifications")
                    
                    # Check for unclosed files and force save them
                    unclosed_save = await tag_handler.force_save_unclosed_file(project_id)
                    if unclosed_save and unclosed_save.get("is_notification"):
                        logger.warning(f"[OPENAI] Forced save of unclosed file")
                        pending_notifications.append(unclosed_save)
                    for notification in pending_notifications:
                        logger.info(f"[OPENAI] Yielding pending notification: {notification}")
                        formatted = format_notification(notification)
                        yield formatted
                    
                    # Save any captured data
                    logger.info(f"[OPENAI] Stream finished, checking for captured files to save")
                    save_notifications = await tag_handler.save_captured_data(project_id)
                    logger.info(f"[OPENAI] Got {len(save_notifications)} save notifications")
                    
                    # Also check for unclosed files here
                    unclosed_save2 = await tag_handler.force_save_unclosed_file(project_id)
                    if unclosed_save2 and unclosed_save2.get("is_notification"):
                        logger.warning(f"[OPENAI] Forced save of unclosed file at stream end")
                        save_notifications.append(unclosed_save2)
                    for notification in save_notifications:
                        logger.info(f"[OPENAI] Yielding save notification: {notification}")
                        formatted = format_notification(notification)
                        yield formatted
                    
                    # Track token usage using consolidated helper
                    await self._track_usage_if_available(
                        user, project, conversation, current_messages, total_assistant_output, usage_data
                    )
                    
                    return
                else:
                    # Final check for token usage tracking if we haven't tracked yet
                    await self._track_usage_if_available(
                        user, project, conversation, current_messages, total_assistant_output, usage_data
                    )
                    
                    logger.warning("Stream ended unexpectedly.")
                    return

            except Exception as e:
                logger.error(f"Critical Error: {str(e)}\n{traceback.format_exc()}")
                yield f"Error with OpenAI stream: {str(e)}"
                return