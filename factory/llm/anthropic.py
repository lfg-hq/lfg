import json
import logging
import asyncio
import traceback
import anthropic
from typing import List, Dict, Any, Optional, AsyncGenerator

from .base import BaseLLMProvider
from factory.llm_config import get_provider_model_mapping, get_default_model_key

# Import functions from ai_common and streaming_handlers
from factory.ai_common import execute_tool_call, get_notification_type_for_tool, track_token_usage
from factory.streaming_handlers import StreamingTagHandler, format_notification

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider implementation"""
    
    MODEL_MAPPING = get_provider_model_mapping("anthropic")
    DEFAULT_MODEL_KEY = get_default_model_key("anthropic") or "claude_4_sonnet"
    
    def __init__(self, selected_model: str, user=None, conversation=None, project=None):
        super().__init__(selected_model, user, conversation, project)
        
        # Map model selection to actual model name
        fallback_model = self.MODEL_MAPPING.get(self.DEFAULT_MODEL_KEY, "claude-sonnet-4-5-20250929")
        self.model = self.MODEL_MAPPING.get(selected_model, fallback_model)
        if selected_model not in self.MODEL_MAPPING:
            logger.warning(f"Unknown Anthropic model {selected_model}, defaulting to {self.DEFAULT_MODEL_KEY}")
        logger.debug(f"Using Claude model: {self.model}")
    
    async def _ensure_client(self):
        """Ensure the client is initialized with API key"""
        logger.debug(f"Ensuring client is initialized with API key for user: {self.user}")
        
        # Try to fetch API key from user profile if available
        if self.user:
            try:
                self.api_key = await self._get_api_key_from_db(self.user, 'anthropic_api_key')
                logger.info(f"Fetched Anthropic API key from user {self.user.id} profile")
            except Exception as e:
                logger.warning(f"Could not fetch Anthropic API key: {e}")
        
        # Initialize client
        if self.api_key:
            self.client = anthropic.AsyncAnthropic(api_key=self.api_key)
        else:
            logger.warning("No Anthropic API key found")
    
    def _convert_messages_to_provider_format(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert OpenAI format messages to Claude format"""
        claude_messages = []
        
        for msg in messages:
            role = msg["role"]
            
            if role == "system":
                # Claude handles system messages differently
                continue
            elif role == "assistant":
                claude_msg = {"role": "assistant", "content": []}
                if msg.get("content"):
                    claude_msg["content"].append({"type": "text", "text": msg["content"]})
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        claude_msg["content"].append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["function"]["name"],
                            "input": json.loads(tc["function"]["arguments"])
                        })
                claude_messages.append(claude_msg)
            elif role == "user":
                # Handle both string content and array content (for files)
                if isinstance(msg.get("content"), list):
                    # Content is already in array format (with files)
                    claude_msg = {"role": "user", "content": msg["content"]}
                else:
                    # Legacy string format
                    claude_msg = {"role": "user", "content": [{"type": "text", "text": msg["content"]}]}
                claude_messages.append(claude_msg)
            elif role == "tool":
                # Find the corresponding tool use in the previous assistant message
                tool_result = {
                    "type": "tool_result",
                    "tool_use_id": msg["tool_call_id"],
                    "content": msg["content"]
                }
                # Add to user message (Claude requires tool results in user messages)
                if claude_messages and claude_messages[-1]["role"] == "user":
                    claude_messages[-1]["content"].append(tool_result)
                else:
                    claude_messages.append({"role": "user", "content": [tool_result]})
        
        return claude_messages
    
    def _convert_tools_to_provider_format(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert OpenAI format tools to Claude format"""
        claude_tools = []
        seen_tool_names = set()
        
        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                tool_name = func["name"]
                
                # Skip duplicate tools
                if tool_name in seen_tool_names:
                    logger.warning(f"Skipping duplicate tool: {tool_name}")
                    continue
                
                seen_tool_names.add(tool_name)
                
                claude_tool = {
                    "name": tool_name,
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object", "properties": {}, "required": []})
                }
                claude_tools.append(claude_tool)
                
                # Log implementation-related tools
                if tool_name in ["save_implementation", "get_implementation"]:
                    logger.debug(f"[AnthropicProvider] Added {tool_name} to Claude tools with description: {func.get('description', '')[:100]}...")
        
        return claude_tools
    
    async def generate_stream(self, messages: List[Dict[str, Any]], 
                            project_id: Optional[int], 
                            conversation_id: Optional[int], 
                            tools: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        """Generate streaming response from Anthropic Claude"""
        # Check token limits before proceeding
        can_proceed, error_message, remaining_tokens = await self.check_token_limits()
        if not can_proceed:
            yield f"Error: {error_message}"
            return
        
        # Ensure client is initialized with API key
        logger.info("Generating stream for Anthropic provider")
        await self._ensure_client()
        
        # Check if client is initialized
        if not self.client:
            yield "Error: No Anthropic API key configured. Please add API key [here](/settings/)."
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

        # Tool round limiter to prevent infinite loops
        max_tool_rounds = 80  # Maximum number of tool-use iterations
        current_tool_round = 0

        while True: # Loop to handle potential multi-turn tool calls
            current_tool_round += 1

            # Check if we've exceeded max tool rounds
            if current_tool_round > max_tool_rounds:
                logger.error(f"Exceeded maximum tool rounds ({max_tool_rounds}). Breaking loop.")
                error_msg = f"⚠️ Maximum tool execution limit reached ({max_tool_rounds} rounds). Implementation may be incomplete."
                yield error_msg
                return

            logger.info(f"[ANTHROPIC] Starting tool round {current_tool_round}/{max_tool_rounds}")

            try:
                # Convert messages and tools to Claude format
                claude_messages = self._convert_messages_to_provider_format(current_messages)
                claude_tools = self._convert_tools_to_provider_format(tools)

                # Add web search tool using the correct format (only if not already present)
                tool_names = [tool.get('name') for tool in claude_tools]
                if 'web_search' not in tool_names:
                    web_search_tool = {
                        "type": "web_search_20250305",
                        "name": "web_search",
                        "max_uses": 5  # Optional: limit number of searches per request
                    }
                    claude_tools.append(web_search_tool)
                    logger.info("Added web_search_20250305 tool to Claude tools")
                else:
                    logger.debug("web_search tool already present, skipping addition")
                
                # Log available tools
                # logger.debug(f"Available tools for Claude: {[tool['name'] for tool in claude_tools]}")
                
                # Extract system message if present
                system_message = None
                for msg in current_messages:
                    if msg["role"] == "system":
                        system_message = msg["content"]
                        break
                
                # Log system message snippet to verify it contains implementation instructions
                if system_message:
                    logger.debug(f"System message snippet: {system_message[:200]}...")
                    if "save_implementation" in system_message:
                        logger.debug("System message contains save_implementation instructions")
                    if "get_implementation" in system_message:
                        logger.debug("System message contains get_implementation instructions")
                
                params = {
                    "model": self.model,
                    "messages": claude_messages,
                    "max_tokens": 8192,
                    "tools": claude_tools,
                    "tool_choice": {"type": "auto"}
                }

                # Add system message with prompt caching
                # Use array format with cache_control to enable caching
                if system_message:
                    params["system"] = [
                        {
                            "type": "text",
                            "text": system_message,
                            "cache_control": {"type": "ephemeral"}
                        }
                    ]
                
                logger.debug(f"Making Claude API call with {len(claude_messages)} messages.")
                logger.info(f"Claude model: {self.model} - web_search is built-in")
                
                # Variables for this specific API call
                tool_calls_requested = [] # Stores {id, function_name, function_args_str}
                full_assistant_message = {"role": "assistant", "content": None, "tool_calls": []} # To store the complete assistant turn
                agent_followup_messages: List[Dict[str, Any]] = []
                agent_followup_counter = 0
                continue_after_stop = False

                def append_assistant_text(text: Optional[str]):
                    if not text:
                        return
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
                current_tool_use = None
                current_tool_args = ""

                logger.debug("New Loop!!")
                
                # Output buffer to handle incomplete tags
                output_buffer = ""
                
                # --- Process the stream from the API --- 
                async with self.client.messages.stream(**params) as stream:
                    async for event in stream:
                        if event.type == "content_block_start":
                            if event.content_block.type == "text":
                                # Text content block started
                                pass
                            elif event.content_block.type == "tool_use":
                                # Tool use block started
                                logger.debug(f"Tool use started: {event.content_block.name}")

                                current_tool_use = {
                                    "id": event.content_block.id,
                                    "type": "function",
                                    "function": {
                                        "name": event.content_block.name,
                                        "arguments": ""
                                    }
                                }
                                current_tool_args = ""
                                
                                # Send early notification
                                function_name = event.content_block.name
                                notification_type = get_notification_type_for_tool(function_name)
                                
                                # Skip early notification for stream_prd_content and stream_implementation_content since we need the actual content
                                # if function_name not in ["stream_prd_content", "stream_implementation_content"]:
                                #     # Send early notification for other tool uses
                                #     logger.info(f"SENDING EARLY NOTIFICATION FOR {function_name}")
                                #     early_notification = {
                                #         "is_notification": True,
                                #         "notification_type": notification_type or "tool",
                                #         "early_notification": True,
                                #         "function_name": function_name,
                                #         "notification_marker": "__NOTIFICATION__"
                                #     }
                                #     notification_json = json.dumps(early_notification)
                                #     logger.info(f"Early notification JSON: {notification_json}")
                                #     yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                                # else:
                                #     logger.info(f"Skipping early notification for {function_name} - will send with content later")
                        
                        elif event.type == "content_block_delta":
                            if event.delta.type == "text_delta":
                                # Stream text content
                                text = event.delta.text
                                
                                # Process text through tag handler
                                output_text, notification, mode_message = await tag_handler.process_text_chunk(text, project_id)
                                
                                # Yield mode message if entering a special mode
                                if mode_message:
                                    yield mode_message
                                
                                # Yield notification if present
                                if notification:
                                    if isinstance(notification, dict):
                                        enqueue_agent_followup(notification.get("message_to_agent"))
                                    yield format_notification(notification)
                                
                                # Yield output text if present
                                if output_text:
                                    yield output_text
                                
                                # Check for immediate notifications to yield
                                immediate_notifications = tag_handler.get_immediate_notifications()
                                for immediate_notification in immediate_notifications:
                                    logger.info(f"[ANTHROPIC] Yielding immediate notification: {immediate_notification.get('notification_type')}")
                                    if isinstance(immediate_notification, dict):
                                        enqueue_agent_followup(immediate_notification.get("message_to_agent"))
                                    yield format_notification(immediate_notification)
                                
                                # Update the full assistant message
                                append_assistant_text(text)
                                
                                # Check if this might be web search results
                                if "search result" in text.lower() or "web search" in text.lower():
                                    logger.debug("Detected potential web search results in Claude's response")
                            
                            elif event.delta.type == "input_json_delta":
                                # Tool use arguments
                                if current_tool_use:
                                    current_tool_args += event.delta.partial_json
                                    
                        elif event.type == "content_block_stop":
                            if current_tool_use:
                                # Finalize tool use
                                current_tool_use["function"]["arguments"] = current_tool_args or "{}"
                                tool_calls_requested.append(current_tool_use)
                                current_tool_use = None
                                current_tool_args = ""
                        
                        elif event.type == "message_stop":
                            # Message completed
                            stop_reason = event.message.stop_reason
                            logger.debug(f"Stop Reason: {stop_reason}")
                            
                            # Track token usage if available
                            if hasattr(event.message, 'usage') and event.message.usage:
                                usage = event.message.usage

                                # Log prompt caching stats
                                cache_creation = getattr(usage, 'cache_creation_input_tokens', 0)
                                cache_read = getattr(usage, 'cache_read_input_tokens', 0)
                                input_tokens = getattr(usage, 'input_tokens', 0)
                                output_tokens = getattr(usage, 'output_tokens', 0)

                                if cache_creation > 0 or cache_read > 0:
                                    logger.info(f"[PROMPT CACHE] Cache creation: {cache_creation}, Cache read: {cache_read}, Regular input: {input_tokens}, Output: {output_tokens}")
                                    if cache_read > 0:
                                        savings_pct = (cache_read / (cache_read + input_tokens) * 100) if (cache_read + input_tokens) > 0 else 0
                                        logger.info(f"[PROMPT CACHE] Cache hit! Saved ~90% cost on {cache_read} tokens ({savings_pct:.1f}% of total input)")

                                if user:
                                    logger.info(f"Tracking token usage for Anthropic: input={input_tokens}, output={output_tokens}, cache_creation={cache_creation}, cache_read={cache_read}")
                                    await track_token_usage(
                                        user, project, conversation, event.message.usage, 'anthropic', self.model
                                    )
                                else:
                                    logger.warning(f"Cannot track token usage - no user available. Usage data: input={input_tokens}, output={output_tokens}")
                            else:
                                logger.debug("No usage data available in message_stop event")
                            
                            if stop_reason == "tool_use" and tool_calls_requested:
                                # Build the assistant message
                                full_assistant_message["tool_calls"] = tool_calls_requested
                                
                                # Remove the content field if it was just tool calls
                                if full_assistant_message["content"] is None:
                                    full_assistant_message.pop("content")
                                
                                # Append to the running conversation history
                                current_messages.append(full_assistant_message)
                                
                                # --- Execute Tools and Prepare Next Call --- 
                                tool_results_messages = []
                                
                                # Process all tool calls
                                if tool_calls_requested:
                                    # Execute tools in parallel
                                    tool_tasks = []
                                    for tool_call_to_execute in tool_calls_requested:
                                        task = self._execute_tool(
                                            tool_call_to_execute,
                                            project_id,
                                            conversation_id
                                        )
                                        tool_tasks.append(task)
                                    
                                    # Wait for all tools to complete
                                    tool_results = await asyncio.gather(*tool_tasks, return_exceptions=True)
                                    
                                    # Process results
                                    for tool_call_to_execute, result in zip(tool_calls_requested, tool_results):
                                        tool_call_id = tool_call_to_execute["id"]
                                        tool_call_name = tool_call_to_execute["function"]["name"]
                                        
                                        if isinstance(result, Exception):
                                            # Handle exception
                                            error_message = f"Error executing tool {tool_call_name}: {result}"
                                            logger.error(f"{error_message}\n{traceback.format_exc()}")
                                            result_content = f"Error: {error_message}"
                                            notification_data = None
                                        else:
                                            result_content, notification_data, yielded_content = result
                                            
                                            # Yield any content that needs to be streamed
                                            if yielded_content:
                                                if isinstance(yielded_content, (list, tuple)):
                                                    for chunk in yielded_content:
                                                        if chunk:
                                                            yield chunk
                                                else:
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
                                            notification_list = notification_data if isinstance(notification_data, list) else [notification_data]
                                            for notification in notification_list:
                                                if isinstance(notification, dict):
                                                    enqueue_agent_followup(notification.get("message_to_agent"))
                                                formatted = format_notification(notification)
                                                logger.debug(f"Notification JSON: {formatted}")
                                                yield formatted
                                
                                current_messages.extend(tool_results_messages)
                                # Continue the outer while loop to make the next API call
                                break
                            
                            elif stop_reason in ["end_turn", "stop_sequence", "max_tokens"]:
                                # Conversation finished naturally
                                logger.debug(f"[AnthropicProvider] Claude finished without using tools. Stop reason: {stop_reason}")
                                if full_assistant_message["content"]:
                                    logger.debug(f"[AnthropicProvider] Assistant response snippet: {full_assistant_message['content'][:100]}...")
                                
                                # Flush any remaining buffer content
                                flushed_output = tag_handler.flush_buffer()
                                if flushed_output:
                                    yield flushed_output
                                
                                # Check for any pending saves/edits first
                                logger.info(f"[ANTHROPIC] Checking for pending saves/edits")
                                pending_notifications = await tag_handler.check_and_save_pending_files()
                                logger.info(f"[ANTHROPIC] Got {len(pending_notifications)} pending notifications")
                                
                                # Check for unclosed files and force save them
                                unclosed_save = await tag_handler.force_save_unclosed_file(project_id)
                                if unclosed_save and unclosed_save.get("is_notification"):
                                    logger.warning(f"[ANTHROPIC] Forced save of unclosed file")
                                    pending_notifications.append(unclosed_save)
                                for notification in pending_notifications:
                                    logger.info(f"[ANTHROPIC] Yielding pending notification: {notification}")
                                    if isinstance(notification, dict):
                                        enqueue_agent_followup(notification.get("message_to_agent"))
                                    formatted = format_notification(notification)
                                    yield formatted
                                
                                # Save any captured data
                                logger.info(f"[ANTHROPIC] Stream finished, checking for captured files to save")
                                save_notifications = await tag_handler.save_captured_data(project_id)
                                logger.info(f"[ANTHROPIC] Got {len(save_notifications)} save notifications")
                                
                                # Also check for unclosed files here
                                unclosed_save2 = await tag_handler.force_save_unclosed_file(project_id)
                                if unclosed_save2 and unclosed_save2.get("is_notification"):
                                    logger.warning(f"[ANTHROPIC] Forced save of unclosed file at stream end")
                                    save_notifications.append(unclosed_save2)
                                for notification in save_notifications:
                                    logger.info(f"[ANTHROPIC] Yielding save notification: {notification}")
                                    # Log specific details about file_id
                                    if 'file_id' in notification:
                                        logger.info(f"[ANTHROPIC] NOTIFICATION HAS FILE_ID: {notification['file_id']}")
                                        logger.info(f"[ANTHROPIC] Notification type: {notification.get('notification_type')}")
                                    else:
                                        logger.warning(f"[ANTHROPIC] NO FILE_ID IN NOTIFICATION! Keys: {list(notification.keys())}")
                                    if isinstance(notification, dict):
                                        enqueue_agent_followup(notification.get("message_to_agent"))
                                    formatted = format_notification(notification)
                                    logger.info(f"[ANTHROPIC] Formatted notification: {formatted[:100]}...")
                                    logger.info(f"[ANTHROPIC] Full formatted notification: {formatted}")
                                    yield formatted
                                
                                if agent_followup_messages:
                                    logger.info("[ANTHROPIC] Continuing conversation to process agent follow-up messages")
                                    if full_assistant_message.get("content") or full_assistant_message.get("tool_calls"):
                                        current_messages.append({k: v for k, v in full_assistant_message.items() if v})
                                    current_messages.extend(agent_followup_messages)
                                    continue_after_stop = True
                                    break

                                return
                            else:
                                logger.warning(f"[AnthropicProvider] Unhandled stop reason: {stop_reason}")
                                return
                
                # If we broke out because we need a follow-up turn, restart loop
                if continue_after_stop:
                    continue

                # If we broke out of the inner loop due to tool_use, continue
                if tool_calls_requested:
                    continue
                else:
                    # Stream ended without tool calls
                    return

            except Exception as e:
                error_str = str(e)
                logger.error(f"Critical Error: {error_str}\n{traceback.format_exc()}")

                # Check if this is a 500 Internal Server Error
                if "500" in error_str or "Internal server error" in error_str or "InternalServerError" in error_str:
                    # For 500 errors, add retry logic with exponential backoff
                    if current_tool_round <= 3:  # Only retry on early rounds
                        retry_delay = 2 ** current_tool_round  # Exponential backoff: 2s, 4s, 8s
                        logger.warning(f"Anthropic API 500 error on round {current_tool_round}. Retrying in {retry_delay}s...")
                        yield f"⚠️ API error (500). Retrying in {retry_delay}s..."
                        await asyncio.sleep(retry_delay)
                        continue  # Retry the same round
                    else:
                        logger.error(f"Anthropic API 500 error persisted after {current_tool_round} rounds. Giving up.")
                        yield f"❌ Persistent API error (500). Please try again later."
                        # Signal the error to the caller
                        yield "__ERROR_500__"
                        return
                else:
                    # Non-retryable error
                    yield f"Error with Claude stream: {error_str}"
                    return

    async def _execute_tool(self, tool_call, project_id, conversation_id):
        """Execute a single tool call and return results"""
        tool_call_id = tool_call["id"]
        tool_call_name = tool_call["function"]["name"]
        tool_call_args_str = tool_call["function"]["arguments"]
        
        logger.debug(f"[AnthropicProvider] Tool Call ID: {tool_call_id}")
        logger.debug(f"[AnthropicProvider] Project ID: {project_id}, Conversation ID: {conversation_id}")
        
        # Log complete create_prd arguments before execution
        if tool_call_name == "create_prd":
            logger.info(f"[Anthropic] Executing create_prd with complete arguments: {tool_call_args_str}")
        
        # Use the shared execute_tool_call function
        result_content, notification_data, yielded_content = await execute_tool_call(
            tool_call_name, tool_call_args_str, project_id, conversation_id
        )
        
        return result_content, notification_data, yielded_content
