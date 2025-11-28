import json
import logging
import asyncio
import traceback
import openai
import tiktoken
import os
from typing import List, Dict, Any, Optional, AsyncGenerator

from .base import BaseLLMProvider
from factory.llm_config import get_provider_model_mapping, get_default_model_key
from channels.db import database_sync_to_async

# Import functions from ai_common and streaming_handlers
from factory.ai_common import execute_tool_call, get_notification_type_for_tool, track_token_usage
from factory.streaming_handlers import StreamingTagHandler, format_notification
from factory.token_tracking import UsageData

logger = logging.getLogger(__name__)

# Debug flag for enhanced token tracking logging
DEBUG_TOKEN_TRACKING = logger.isEnabledFor(logging.DEBUG)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI provider implementation"""
    
    MODEL_MAPPING = get_provider_model_mapping("openai")
    DEFAULT_MODEL_KEY = get_default_model_key("openai") or "gpt-5-mini"
    
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
        fallback_model = self.MODEL_MAPPING.get(self.DEFAULT_MODEL_KEY, "gpt-5-mini")
        self.model = self.MODEL_MAPPING.get(selected_model, fallback_model)
        if selected_model not in self.MODEL_MAPPING:
            logger.warning(f"Unknown OpenAI model {selected_model}, defaulting to {self.DEFAULT_MODEL_KEY}")
            
        logger.info(f"OpenAI Provider initialized with model: {self.model}")
    
    async def _can_use_platform_model(self):
        """Check if user can use platform-provided API key for the current model"""
        if not self.user:
            return False
        
        try:
            from subscriptions.models import UserCredit
            user_credit, created = await database_sync_to_async(UserCredit.objects.get_or_create)(user=self.user)
            
            # Use the subscription model's platform access logic
            return user_credit.can_use_platform_model(self.model)
            
        except Exception as e:
            logger.error(f"Error checking platform model access: {e}")
            return False
    
    async def _ensure_client(self):
        """Ensure the client is initialized with API key"""
        # Try to fetch API key from user profile if available
        if self.user:
            try:
                self.api_key = await self._get_api_key_from_db(self.user, 'openai_api_key')
                if self.api_key:
                    logger.info(f"Using user-provided OpenAI API key for user {self.user.id}")
            except Exception as e:
                logger.warning(f"Could not fetch OpenAI API key: {e}")
        
        # Fallback to platform API key if no user key found or preference disabled
        if not self.api_key:
            platform_openai_key = os.getenv('OPENAI_API_KEY')
            if platform_openai_key:
                # Check if user can use platform-provided models
                if await self._can_use_platform_model():
                    self.api_key = platform_openai_key
                    logger.info(f"Using platform-provided OpenAI API key for model {self.model}")
                else:
                    logger.info(f"User cannot use platform key for model {self.model}, requires own API key")
            else:
                logger.warning("No platform OpenAI API key found in environment")
        
        # Initialize client
        if self.api_key:
            self.client = openai.OpenAI(api_key=self.api_key)
        else:
            logger.warning("No OpenAI API key available (neither user nor platform)")
    
    def _convert_messages_to_provider_format(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """OpenAI uses the standard format, so just return as-is"""
        return messages
    
    def _convert_tools_to_provider_format(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert tools to OpenAI Responses API format.

        The Responses API expects tools with name, description, and parameters
        at the top level, not nested inside a 'function' object.
        """
        converted_tools = []
        for tool in tools:
            if tool.get("type") == "function" and "function" in tool:
                # Convert from old Chat Completions format to new Responses API format
                func_def = tool["function"]
                converted_tool = {
                    "type": "function",
                    "name": func_def.get("name"),
                    "description": func_def.get("description", ""),
                    "parameters": func_def.get("parameters", {"type": "object", "properties": {}})
                }
                converted_tools.append(converted_tool)
            elif tool.get("type") == "function" and "name" in tool:
                # Already in the correct Responses API format
                converted_tools.append(tool)
            else:
                # Pass through other tool types as-is
                converted_tools.append(tool)
        return converted_tools
    
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
        """Validate that usage data has the expected attributes.

        Supports both Chat Completions format (prompt_tokens/completion_tokens)
        and Responses API format (input_tokens/output_tokens).
        """
        try:
            if not usage_data:
                return False

            # Check for Chat Completions format
            has_chat_format = (
                hasattr(usage_data, 'prompt_tokens') and
                hasattr(usage_data, 'completion_tokens') and
                getattr(usage_data, 'prompt_tokens') is not None and
                getattr(usage_data, 'completion_tokens') is not None
            )

            # Check for Responses API format
            has_responses_format = (
                hasattr(usage_data, 'input_tokens') and
                hasattr(usage_data, 'output_tokens') and
                getattr(usage_data, 'input_tokens') is not None and
                getattr(usage_data, 'output_tokens') is not None
            )

            if has_chat_format or has_responses_format:
                return True

            logger.debug(f"Usage data missing required attributes. Has: {[a for a in dir(usage_data) if not a.startswith('_')]}")
            return False
        except Exception as e:
            logger.debug(f"Error validating usage data: {e}")
            return False
    
    async def _get_or_estimate_usage(self, messages: List[Dict[str, Any]], total_assistant_output: str,
                                   usage_data: Optional[Any] = None) -> Optional[UsageData]:
        """Get usage data from API or estimate tokens as fallback"""
        try:
            # Try to use API-provided usage data first
            if usage_data and self._validate_usage_data(usage_data):
                # Handle both Chat Completions and Responses API formats
                input_tokens = getattr(usage_data, 'input_tokens', None) or getattr(usage_data, 'prompt_tokens', 0)
                output_tokens = getattr(usage_data, 'output_tokens', None) or getattr(usage_data, 'completion_tokens', 0)
                logger.info(f"Using API-provided token usage: input={input_tokens}, output={output_tokens}")
                self._usage_tracking_stats['api_success'] += 1
                # Create UsageData with normalized values
                return UsageData(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens
                )
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
            if self.model == 'gpt-5-mini':
                yield "Error: Platform OpenAI API key not available. Please contact support."
            else:
                yield f"Error: {self.model} requires your own OpenAI API key. Please add API key [here](/settings/) to use advanced models."
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

        # Convert tools to Responses API format
        converted_tools = self._convert_tools_to_provider_format(tools)

        # Add OpenAI's built-in web search tool (Responses API native)
        # This provides real-time web search capabilities without custom implementation
        converted_tools.append({"type": "web_search_preview"})

        while True: # Loop to handle potential multi-turn tool calls
            try:
                params = {
                    "model": self.model,
                    "input": current_messages,
                    "stream": True,
                    "tool_choice": "auto",
                    "tools": converted_tools,
                    # Note: Responses API doesn't support stream_options - usage is estimated via tiktoken
                }
                
                logger.debug(f"Making API call with {len(current_messages)} messages.")
                
                # Run the blocking API call in a thread
                response_stream = await asyncio.to_thread(
                    self.client.responses.create, **params
                )
                
                # Variables for this specific API call
                tool_calls_requested = [] # Stores {id, function_name, function_args_str}
                full_assistant_message = {"role": "assistant", "content": None, "tool_calls": []} # To store the complete assistant turn
                agent_followup_messages = []  # Messages we need to feed back to the model
                agent_followup_counter = 0

                def append_assistant_text(text: Optional[str]):
                    nonlocal total_assistant_output
                    if not text:
                        return
                    total_assistant_output += text
                    if full_assistant_message["content"] is None:
                        full_assistant_message["content"] = ""
                    full_assistant_message["content"] += text

                def enqueue_agent_followup(message_text: Optional[str]):
                    nonlocal agent_followup_counter
                    if not message_text:
                        return
                    agent_followup_counter += 1
                    agent_followup_messages.append({
                        "role": "system",
                        "content": message_text
                    })

                logger.debug("New Loop!!")
                
                # Variables for token tracking
                usage_data = None
                finish_reason = None

                # Track current function call being built (Responses API sends one at a time)
                current_function_call = {"id": None, "name": None, "arguments": ""}

                # --- Process the stream from the API (Responses API event-based) ---
                event_count = 0
                async for event in self._process_stream_async(response_stream):
                    event_count += 1
                    event_type = getattr(event, 'type', None)

                    # Debug log events
                    if event_count <= 5:
                        logger.debug(f"Event {event_count}: type={event_type}")

                    # Handle different Responses API event types
                    if event_type == 'response.output_text.delta':
                        # Text content delta
                        text = getattr(event, 'delta', '')
                        if text:
                            append_assistant_text(text)
                            logger.debug(f"Captured {len(text)} chars of assistant output, total: {len(total_assistant_output)}")

                            # Process text through tag handler
                            logger.debug(f"[OPENAI] Calling process_text_chunk with project_id: {project_id}")
                            output_text, notification, mode_message = await tag_handler.process_text_chunk(text, project_id)

                            # Yield mode message if entering a special mode
                            if mode_message:
                                yield mode_message

                            # Yield notification if present
                            if notification:
                                if isinstance(notification, dict):
                                    message_to_agent = notification.get("message_to_agent")
                                    if message_to_agent:
                                        enqueue_agent_followup(message_to_agent)
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
                                if isinstance(immediate_notification, dict):
                                    message_to_agent = immediate_notification.get("message_to_agent")
                                    if message_to_agent:
                                        enqueue_agent_followup(message_to_agent)
                                formatted = format_notification(immediate_notification)
                                yield formatted

                    elif event_type == 'response.output_item.added':
                        # New output item added - could be text or function_call
                        item = getattr(event, 'item', None)
                        if item:
                            item_type = getattr(item, 'type', None)
                            if item_type == 'function_call':
                                # Start of a new function call
                                current_function_call = {
                                    "id": getattr(item, 'call_id', None) or getattr(item, 'id', None),
                                    "name": getattr(item, 'name', None),
                                    "arguments": ""
                                }
                                if current_function_call["name"]:
                                    function_name = current_function_call["name"]
                                    # Send early notification
                                    notification_type = get_notification_type_for_tool(function_name)
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

                    elif event_type == 'response.function_call_arguments.delta':
                        # Function call arguments delta
                        delta = getattr(event, 'delta', '')
                        if delta:
                            current_function_call["arguments"] += delta

                    elif event_type == 'response.function_call_arguments.done':
                        # Function call arguments complete - add to tool_calls_requested
                        if current_function_call["name"]:
                            tool_calls_requested.append({
                                "id": current_function_call["id"],
                                "type": "function",
                                "function": {
                                    "name": current_function_call["name"],
                                    "arguments": current_function_call["arguments"] or "{}"
                                }
                            })
                            logger.debug(f"Function call complete: {current_function_call['name']}")

                    elif event_type == 'response.completed':
                        # Response completed - extract usage and determine finish reason
                        response_obj = getattr(event, 'response', None)
                        if response_obj:
                            # Extract usage data
                            usage_obj = getattr(response_obj, 'usage', None)
                            if usage_obj:
                                usage_data = usage_obj
                                logger.info(f"Token usage from response.completed: input={getattr(usage_data, 'input_tokens', 'N/A')}, output={getattr(usage_data, 'output_tokens', 'N/A')}")

                            # Determine finish reason from output
                            output = getattr(response_obj, 'output', [])
                            if output:
                                for item in output:
                                    if getattr(item, 'type', None) == 'function_call':
                                        finish_reason = "tool_calls"
                                        break
                            if not finish_reason:
                                finish_reason = "stop"
                        else:
                            finish_reason = "stop"

                        logger.debug(f"Response completed, finish_reason={finish_reason}")

                        # Flush any remaining buffer content
                        flushed_output = tag_handler.flush_buffer()
                        if flushed_output:
                            yield flushed_output

                        break  # Exit the event loop

                    elif event_type in ('response.created', 'response.in_progress', 'response.output_item.done',
                                       'response.content_part.added', 'response.content_part.done',
                                       'response.output_text.done'):
                        # Informational events - just log them
                        logger.debug(f"Received event: {event_type}")
                        continue

                    elif event_type and event_type.startswith('response.web_search_call'):
                        # Web search events from built-in web_search_preview tool
                        # These are handled automatically by OpenAI - just send notification to UI
                        if event_type == 'response.web_search_call.in_progress':
                            logger.info("[OPENAI] Web search in progress")
                            # Send notification that web search is happening
                            search_notification = {
                                "is_notification": True,
                                "notification_type": "web_search",
                                "early_notification": True,
                                "function_name": "web_search",
                                "notification_marker": "__NOTIFICATION__"
                            }
                            yield f"__NOTIFICATION__{json.dumps(search_notification)}__NOTIFICATION__"
                        elif event_type == 'response.web_search_call.completed':
                            logger.info("[OPENAI] Web search completed")
                            # Send completion notification to remove spinner
                            complete_notification = {
                                "is_notification": True,
                                "notification_type": "web_search",
                                "early_notification": False,
                                "function_name": "web_search",
                                "notification_marker": "__NOTIFICATION__"
                            }
                            yield f"__NOTIFICATION__{json.dumps(complete_notification)}__NOTIFICATION__"
                        else:
                            logger.debug(f"Web search event: {event_type}")
                        continue

                # --- Handle finish reason after event loop ---
                if finish_reason == "tool_calls" and tool_calls_requested:
                    # Process tool calls
                    full_assistant_message["tool_calls"] = tool_calls_requested
                    if full_assistant_message["content"] is None:
                        full_assistant_message.pop("content", None)

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
                            if isinstance(yielded_content, (list, tuple)):
                                for chunk in yielded_content:
                                    if chunk:
                                        yield chunk
                            else:
                                yield yielded_content

                        # Responses API uses function_call_output format
                        tool_results_messages.append({
                            "type": "function_call_output",
                            "call_id": tool_call_id,
                            "output": f"Tool call {tool_call_name}() completed. {result_content}."
                        })

                        if notification_data:
                            logger.debug("YIELDING NOTIFICATION DATA TO CONSUMER")
                            notification_list = notification_data if isinstance(notification_data, list) else [notification_data]
                            for notification in notification_list:
                                notification_json = json.dumps(notification)
                                yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"

                    current_messages.extend(tool_results_messages)

                    # Track token usage for tool calls
                    await self._track_usage_if_available(
                        user, project, conversation, current_messages, total_assistant_output, usage_data
                    )

                    # Continue the loop to process tool results
                    continue
                
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
                        if isinstance(notification, dict):
                            enqueue_agent_followup(notification.get("message_to_agent"))
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
                        if isinstance(notification, dict):
                            enqueue_agent_followup(notification.get("message_to_agent"))
                        formatted = format_notification(notification)
                        yield formatted
                    
                    if agent_followup_messages:
                        logger.info("[OPENAI] Agent follow-up messages detected; continuing conversation for handoff")
                        if full_assistant_message.get("content") or full_assistant_message.get("tool_calls"):
                            current_messages.append({k: v for k, v in full_assistant_message.items() if v})
                        current_messages.extend(agent_followup_messages)
                        continue

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
