import json
import logging
import asyncio
import traceback
import openai
import tiktoken
from typing import List, Dict, Any, Optional, AsyncGenerator

from .base import BaseLLMProvider

# These imports will be handled during integration
# from development.utils.ai_providers import execute_tool_call, get_notification_type_for_tool, track_token_usage
# from development.utils.streaming_handlers import StreamingTagHandler, format_notification

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI provider implementation"""
    
    MODEL_MAPPING = {
        "gpt_4o": "gpt-4o",
        "gpt_4.1": "gpt-4.1",
        "o3": "o3",
        "o4-mini": "o4-mini",
    }
    
    def __init__(self, selected_model: str, user=None, conversation=None, project=None):
        super().__init__(selected_model, user, conversation, project)
        
        # Map model selection to actual model name
        self.model = self.MODEL_MAPPING.get(selected_model, "gpt-4o")
        if selected_model not in self.MODEL_MAPPING:
            logger.warning(f"Unknown model {selected_model}, defaulting to gpt-4o")
            
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
        if not tiktoken:
            logger.warning("tiktoken not available, cannot estimate tokens")
            return None, None
            
        try:
            # Use the model-specific encoding or fall back to cl100k_base
            try:
                if model == "gpt-4o" or model == "gpt-4.1" or model == "o3" or model == "o4-mini":
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
                if message.get("content"):
                    content_tokens = len(encoding.encode(message["content"]))
                    msg_tokens += content_tokens
                    logger.debug(f"Message {i} ({message.get('role')}): {content_tokens} content tokens")
                
                # Count tool calls if present
                if message.get("tool_calls"):
                    tool_tokens = 0
                    for tool_call in message["tool_calls"]:
                        # Estimate tokens for tool call structure
                        tool_tokens += 10  # Base overhead for tool call
                        if tool_call.get("function", {}).get("name"):
                            tool_tokens += len(encoding.encode(tool_call["function"]["name"]))
                        if tool_call.get("function", {}).get("arguments"):
                            tool_tokens += len(encoding.encode(tool_call["function"]["arguments"]))
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
    
    async def generate_stream(self, messages: List[Dict[str, Any]], 
                            project_id: Optional[int], 
                            conversation_id: Optional[int], 
                            tools: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        """Generate streaming response from OpenAI"""
        logger.info(f"OpenAI generate_stream called - Model: {self.model}, Messages: {len(messages)}, Tools: {len(tools) if tools else 0}")
        
        # Ensure client is initialized with API keys
        await self._ensure_client()
        
        # Check if client is initialized
        if not self.client:
            yield "Error: No OpenAI API key configured. Please add API key [here](/settings/)."
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
                async for chunk in self._process_stream_async(response_stream):
                    delta = chunk.choices[0].delta if chunk.choices else None
                    finish_reason = chunk.choices[0].finish_reason if chunk.choices else None
                    
                    # Check for usage information in the chunk
                    if hasattr(chunk, 'usage') and chunk.usage:
                        usage_data = chunk.usage
                        logger.info(f"Token usage received from OpenAI API: input={getattr(usage_data, 'prompt_tokens', 'N/A')}, output={getattr(usage_data, 'completion_tokens', 'N/A')}, total={getattr(usage_data, 'total_tokens', 'N/A')}")

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
                                    
                                    # Import will be fixed when integrating with main codebase
                                    from development.utils.ai_providers import get_notification_type_for_tool
                                    
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
                                
                                # Import will be fixed when integrating with main codebase
                                from development.utils.ai_providers import execute_tool_call
                                
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
                            
                            # Track token usage for tool calls
                            if user:
                                if usage_data:
                                    logger.info(f"Using API-provided token usage for tool calls")
                                    # Import will be fixed when integrating with main codebase
                                    from development.utils.ai_providers import track_token_usage
                                    await track_token_usage(
                                        user, project, conversation, usage_data, 'openai', self.model
                                    )
                                else:
                                    # Fallback: estimate tokens if usage data not available
                                    logger.warning("No usage data from OpenAI API for tool calls, using tiktoken estimation")
                                    estimated_input_tokens, estimated_output_tokens = self.estimate_tokens(
                                        current_messages, self.model, total_assistant_output
                                    )
                                    if estimated_input_tokens is not None:
                                        # Create a mock usage object for tracking
                                        class MockUsage:
                                            def __init__(self, input_tokens, output_tokens):
                                                self.prompt_tokens = input_tokens
                                                self.completion_tokens = output_tokens
                                                self.total_tokens = input_tokens + output_tokens
                                        
                                        mock_usage = MockUsage(estimated_input_tokens, estimated_output_tokens)
                                        logger.info(f"Tracking estimated tokens for tool calls")
                                        # Import will be fixed when integrating with main codebase
                                        from development.utils.ai_providers import track_token_usage
                                        await track_token_usage(
                                            user, project, conversation, mock_usage, 'openai', self.model
                                        )
                            
                            break # Break inner chunk loop
                        
                        elif finish_reason == "stop":
                            # Save any captured data
                            logger.info(f"[OPENAI] Stream finished, checking for captured files to save")
                            save_notifications = await tag_handler.save_captured_data(project_id)
                            logger.info(f"[OPENAI] Got {len(save_notifications)} save notifications")
                            for notification in save_notifications:
                                logger.info(f"[OPENAI] Yielding save notification: {notification}")
                                # Import will be fixed when integrating with main codebase
                                from development.utils.streaming_handlers import format_notification
                                formatted = format_notification(notification)
                                logger.info(f"[OPENAI] Formatted notification: {formatted[:100]}...")
                                yield formatted
                            
                            # Track token usage before exiting
                            if user:
                                if usage_data:
                                    logger.info(f"Using API-provided token usage on stop")
                                    # Import will be fixed when integrating with main codebase
                                    from development.utils.ai_providers import track_token_usage
                                    await track_token_usage(
                                        user, project, conversation, usage_data, 'openai', self.model
                                    )
                            return
                        else:
                            # Handle other finish reasons
                            logger.warning(f"Unhandled finish reason: {finish_reason}")
                            return
                
                # If the inner loop finished because of tool_calls, continue
                if finish_reason == "tool_calls":
                    continue
                else:
                    logger.warning("Stream ended unexpectedly.")
                    return

            except Exception as e:
                logger.error(f"Critical Error: {str(e)}\n{traceback.format_exc()}")
                yield f"Error with OpenAI stream: {str(e)}"
                return