import json
import logging
import asyncio
import traceback
from typing import List, Dict, Any, Optional, AsyncGenerator
from google import genai
from google.genai.types import (
    FunctionDeclaration,
    GenerateContentConfig,
    ThinkingConfig,
    Tool,
)

from .base import BaseLLMProvider

# Import functions from ai_common and streaming_handlers
from development.utils.ai_common import execute_tool_call, get_notification_type_for_tool, track_token_usage
from development.utils.streaming_handlers import StreamingTagHandler, format_notification

logger = logging.getLogger(__name__)


class GoogleGeminiProvider(BaseLLMProvider):
    """Google Gemini provider implementation"""
    
    MODEL_MAPPING = {
        "gemini_2.5_pro": "models/gemini-2.5-pro",
        "gemini_2.5_flash": "models/gemini-2.5-flash",
        "gemini_2.5_flash_lite": "models/gemini-2.5-flash-lite",
    }
    
    def __init__(self, selected_model: str, user=None, conversation=None, project=None):
        super().__init__(selected_model, user, conversation, project)
        
        # Map model selection to actual model name
        self.model = self.MODEL_MAPPING.get(selected_model, "models/gemini-2.5-pro")
        if selected_model not in self.MODEL_MAPPING:
            logger.warning(f"Unknown model {selected_model}, defaulting to gemini-2.5-pro")
            
        logger.info(f"Google Gemini Provider initialized with model: {self.model}")
    
    async def _ensure_client(self):
        """Ensure the client is initialized with API key"""
        # Try to fetch API key from user profile if available
        if self.user:
            try:
                self.api_key = await self._get_api_key_from_db(self.user, 'google_api_key')
                logger.info(f"Fetched Google API key from user {self.user.id} profile")
            except Exception as e:
                logger.warning(f"Could not fetch Google API key: {e}")
        
        # Initialize client
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            logger.warning("No Google API key found")
    
    def _convert_messages_to_provider_format(self, messages: List[Dict[str, Any]]) -> tuple:
        """Convert messages to Google Gemini format
        Returns: (system_instruction, contents)
        """
        system_instruction = ""
        contents = []
        
        for msg in messages:
            role = msg["role"]
            
            if role == "system":
                # Google Gemini handles system messages as system_instruction
                system_instruction = msg["content"]
            elif role == "assistant":
                # Convert assistant messages
                parts = []
                if msg.get("content"):
                    parts.append({"text": msg["content"]})
                
                # Handle tool calls
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        parts.append({
                            "function_call": {
                                "name": tc["function"]["name"],
                                "args": json.loads(tc["function"]["arguments"])
                            }
                        })
                
                if parts:
                    contents.append({"role": "model", "parts": parts})
                    
            elif role == "user":
                # Handle both string content and array content (for files)
                parts = []
                
                if isinstance(msg.get("content"), list):
                    # Content is already in array format (with files)
                    for item in msg["content"]:
                        if item.get("type") == "text":
                            parts.append({"text": item["text"]})
                        elif item.get("type") == "image":
                            # Handle image content
                            if item.get("source", {}).get("type") == "base64":
                                parts.append({
                                    "inline_data": {
                                        "mime_type": item["source"].get("media_type", "image/jpeg"),
                                        "data": item["source"]["data"]
                                    }
                                })
                else:
                    # Legacy string format
                    parts.append({"text": msg["content"]})
                
                contents.append({"role": "user", "parts": parts})
                
            elif role == "tool":
                # Convert tool results
                contents.append({
                    "role": "function",
                    "parts": [{
                        "function_response": {
                            "name": msg.get("name", ""),  # Tool name should be in the message
                            "response": {"result": msg["content"]}
                        }
                    }]
                })
        
        return system_instruction, contents
    
    def _convert_tools_to_provider_format(self, tools: List[Dict[str, Any]]) -> List[Tool]:
        """Convert OpenAI format tools to Google Gemini format"""
        gemini_tools = []
        seen_tool_names = set()  # Track tool names to prevent duplicates
        
        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                
                # Convert parameters to Gemini format
                # Google Gemini requires specific format for array types
                parameters = func.get("parameters", {})
                
                # Process properties to fix array types and other incompatibilities
                if "properties" in parameters:
                    fixed_properties = {}
                    for prop_name, prop_def in parameters["properties"].items():
                        # Check if property has oneOf (like get_file_content)
                        if "oneOf" in prop_def:
                            # Simplify oneOf to just use array type
                            # Look for array option in oneOf
                            array_option = None
                            for option in prop_def["oneOf"]:
                                if option.get("type") == "array":
                                    array_option = option
                                    break
                            
                            if array_option:
                                # Use the array option as the simplified type
                                fixed_prop = {
                                    "type": "array",
                                    "items": array_option.get("items", {"type": "integer"}),
                                    "description": prop_def.get("description", "List of values")
                                }
                                if "maxItems" in array_option:
                                    fixed_prop["maxItems"] = array_option["maxItems"]
                            else:
                                # Fall back to the first option
                                fixed_prop = prop_def["oneOf"][0] if prop_def["oneOf"] else {"type": "string"}
                                if "description" in prop_def:
                                    fixed_prop["description"] = prop_def["description"]
                            
                            fixed_properties[prop_name] = fixed_prop
                        elif prop_def.get("type") == "array":
                            # For arrays, Google expects simpler format
                            # Remove any complex structures that might cause validation errors
                            items = prop_def.get("items", {"type": "string"})
                            
                            # If items is a list (like oneOf), simplify it
                            if isinstance(items, list):
                                # Take the first item type as the simple type
                                items = items[0] if items else {"type": "string"}
                            
                            fixed_prop = {
                                "type": "array",
                                "items": items
                            }
                            
                            # Add description if present
                            if "description" in prop_def:
                                fixed_prop["description"] = prop_def["description"]
                            
                            fixed_properties[prop_name] = fixed_prop
                        else:
                            # Copy other properties as-is
                            fixed_properties[prop_name] = prop_def
                    
                    parameters["properties"] = fixed_properties
                
                # Skip duplicate tools
                tool_name = func["name"]
                if tool_name in seen_tool_names:
                    logger.warning(f"Skipping duplicate tool: {tool_name}")
                    continue
                
                seen_tool_names.add(tool_name)
                
                # Create FunctionDeclaration
                try:
                    function_declaration = FunctionDeclaration(
                        name=tool_name,
                        description=func.get("description", ""),
                        parameters=parameters
                    )
                    
                    # Create Tool with the function
                    gemini_tool = Tool(function_declarations=[function_declaration])
                    gemini_tools.append(gemini_tool)
                except Exception as e:
                    logger.warning(f"Failed to convert tool {tool_name}: {e}")
                    # Skip tools that fail validation
                    continue
        
        return gemini_tools
    
    async def generate_stream(self, messages: List[Dict[str, Any]], 
                            project_id: Optional[int], 
                            conversation_id: Optional[int], 
                            tools: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        """Generate streaming response from Google Gemini"""
        logger.info(f"Google Gemini generate_stream called - Model: {self.model}, Messages: {len(messages)}, Tools: {len(tools) if tools else 0}")
        
        # Ensure client is initialized with API keys
        await self._ensure_client()
        
        # Check if client is initialized
        if not self.client:
            yield "Error: No Google API key configured. Please add API key [here](/settings/)."
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
        
        # Add web search tool if not already present
        web_search_exists = any(
            tool.get("function", {}).get("name") == "web_search" 
            for tool in tools 
            if tool.get("type") == "function"
        )
        
        if not web_search_exists:
            search_tool = {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for current information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query"
                            }
                        },
                        "required": ["query"]
                    }
                }
            }
            tools.append(search_tool)
            logger.info("Added web_search tool to Google Gemini tools")

        while True: # Loop to handle potential multi-turn tool calls
            try:
                # Convert messages and tools to Gemini format
                system_instruction, contents = self._convert_messages_to_provider_format(current_messages)
                gemini_tools = self._convert_tools_to_provider_format(tools)
                
                # Create configuration
                if gemini_tools:
                    logger.info(f"Using {len(gemini_tools)} function calling tools")
                    config = GenerateContentConfig(
                        temperature=0.7,
                        top_p=0.95,
                        top_k=40,
                        max_output_tokens=8192,
                        system_instruction=system_instruction if system_instruction else None,
                        tools=gemini_tools,
                        thinking_config=ThinkingConfig(
                            include_thoughts=False 
                        )
                    )
                else:
                    logger.info("No tools configured for this request")
                    config = GenerateContentConfig(
                        temperature=0.7,
                        top_p=0.95,
                        top_k=40,
                        max_output_tokens=8192,
                        system_instruction=system_instruction if system_instruction else None,
                        thinking_config=ThinkingConfig(
                            include_thoughts=False 
                        )
                    )
                
                logger.debug(f"Making Gemini API call with {len(contents)} messages.")
                
                # Variables for this specific API call
                tool_calls_requested = [] # Stores tool call info
                full_assistant_message = {"role": "assistant", "content": "", "tool_calls": []}
                usage_metadata = None  # Store usage metadata from response
                
                # Generate streaming response
                try:
                    response_stream = await asyncio.to_thread(
                        self.client.models.generate_content_stream,
                        model=self.model,
                        contents=contents,
                        config=config
                    )
                except Exception as e:
                    logger.error(f"Error creating stream: {e}")
                    yield f"Error creating Google Gemini stream: {str(e)}"
                    return
                
                # Process the stream
                async for chunk in self._process_gemini_stream_async(response_stream):
                        # Check for usage metadata in chunk
                        if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                            usage_metadata = chunk.usage_metadata
                            logger.debug(f"Google Gemini usage metadata captured: {usage_metadata}")
                        
                        # Check if chunk has text
                        if hasattr(chunk, 'text') and chunk.text:
                            text = chunk.text
                            
                            # Process text through tag handler
                            output_text, notification, mode_message = tag_handler.process_text_chunk(text, project_id)
                            
                            # Yield mode message if entering a special mode
                            if mode_message:
                                yield mode_message
                            
                            # Yield notification if present
                            if notification:
                                yield format_notification(notification)
                            
                            # Yield output text if present
                            if output_text:
                                yield output_text
                            
                            # Update the full assistant message with original text (for context)
                            full_assistant_message["content"] += text
                        
                        # Check for function calls
                        if hasattr(chunk, 'candidates') and chunk.candidates:
                            for candidate in chunk.candidates:
                                if hasattr(candidate, 'content') and candidate.content and hasattr(candidate.content, 'parts'):
                                    for part in candidate.content.parts:
                                        if hasattr(part, 'function_call') and part.function_call:
                                            fc = part.function_call
                                            # Check if function_call has required attributes
                                            if not hasattr(fc, 'name') or not fc.name:
                                                logger.warning("Function call missing name attribute")
                                                continue
                                            
                                            # Extract arguments safely
                                            args = {}
                                            if hasattr(fc, 'args'):
                                                args = fc.args if fc.args else {}
                                            
                                            tool_call = {
                                                "id": f"call_{len(tool_calls_requested)}",
                                                "type": "function",
                                                "function": {
                                                    "name": fc.name,
                                                    "arguments": json.dumps(args)
                                                }
                                            }
                                            tool_calls_requested.append(tool_call)
                                            
                                            # Send early notification
                                            
                                            notification_type = get_notification_type_for_tool(fc.name)
                                            if fc.name not in ["stream_prd_content", "stream_implementation_content"]:
                                                logger.debug(f"SENDING EARLY NOTIFICATION FOR {fc.name}")
                                                early_notification = {
                                                    "is_notification": True,
                                                    "notification_type": notification_type or "tool",
                                                    "early_notification": True,
                                                    "function_name": fc.name,
                                                    "notification_marker": "__NOTIFICATION__"
                                                }
                                                notification_json = json.dumps(early_notification)
                                                yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                
                # After stream completes, check if we have tool calls to execute
                if tool_calls_requested:
                    # Update assistant message with tool calls
                    full_assistant_message["tool_calls"] = tool_calls_requested
                    if not full_assistant_message["content"]:
                        full_assistant_message.pop("content")
                    
                    current_messages.append(full_assistant_message)
                    
                    # Execute tools
                    tool_results_messages = []
                    for tool_call in tool_calls_requested:
                        tool_call_id = tool_call["id"]
                        tool_call_name = tool_call["function"]["name"]
                        tool_call_args_str = tool_call["function"]["arguments"]
                        
                        logger.debug(f"Google Gemini Provider - Tool Call: {tool_call_name}")
                        
                        
                        # Execute the tool
                        result_content, notification_data, yielded_content = await execute_tool_call(
                            tool_call_name, tool_call_args_str, project_id, conversation_id
                        )
                        
                        if yielded_content:
                            yield yielded_content
                        
                        # Add tool result message
                        tool_results_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "name": tool_call_name,  # Gemini needs the function name
                            "content": f"Tool call {tool_call_name}() completed. {result_content}."
                        })
                        
                        if notification_data:
                            logger.debug("YIELDING NOTIFICATION DATA TO CONSUMER")
                            notification_json = json.dumps(notification_data)
                            yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                    
                    current_messages.extend(tool_results_messages)
                    # Continue the loop for next iteration
                    continue
                else:
                    # No tool calls, conversation finished
                    
                    # Flush any remaining buffer content
                    flushed_output = tag_handler.flush_buffer()
                    if flushed_output:
                        yield flushed_output
                    
                    # Check for any pending saves/edits first
                    logger.info(f"[GEMINI] Checking for pending saves/edits")
                    pending_notifications = await tag_handler.check_and_save_pending_files()
                    logger.info(f"[GEMINI] Got {len(pending_notifications)} pending notifications")
                    for notification in pending_notifications:
                        logger.info(f"[GEMINI] Yielding pending notification: {notification}")
                        formatted = format_notification(notification)
                        yield formatted
                    
                    # Save any captured data
                    logger.info(f"[GEMINI] Stream finished, checking for captured files to save")
                    save_notifications = await tag_handler.save_captured_data(project_id)
                    logger.info(f"[GEMINI] Got {len(save_notifications)} save notifications")
                    for notification in save_notifications:
                        logger.info(f"[GEMINI] Yielding save notification: {notification}")
                        formatted = format_notification(notification)
                        yield formatted
                    
                    # Track token usage if available
                    # Google Gemini provides token counts in the response
                    if user and usage_metadata:
                        try:
                            logger.info(f"Tracking token usage for Google Gemini: input={getattr(usage_metadata, 'prompt_token_count', 0)}, output={getattr(usage_metadata, 'candidates_token_count', 0)}, total={getattr(usage_metadata, 'total_token_count', 0)}")
                            await track_token_usage(
                                user, project, conversation, usage_metadata, 'google', self.model
                            )
                        except Exception as e:
                            logger.error(f"Error tracking Google Gemini token usage: {e}")
                    elif user:
                        logger.warning("No usage metadata captured from Google Gemini stream")
                    
                    return

            except Exception as e:
                logger.error(f"Critical Error: {str(e)}\n{traceback.format_exc()}")
                yield f"Error with Google Gemini stream: {str(e)}"
                return
    
    def _safe_stream_wrapper(self, response_stream):
        """Wrap the response stream to handle JSON decode errors"""
        try:
            for chunk in response_stream:
                yield chunk
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in stream: {e}")
            # Return a special error chunk
            class ErrorChunk:
                def __init__(self):
                    self.text = None
                    self.candidates = []
                    self.usage_metadata = None
                    self.error = str(e)
            yield ErrorChunk()
        except Exception as e:
            logger.error(f"Error in stream: {e}")
            raise
    
    async def _process_gemini_stream_async(self, response_stream):
        """Process the Gemini response stream asynchronously"""
        # Wrap the stream to handle JSON decode errors
        safe_stream = self._safe_stream_wrapper(response_stream)
        
        for chunk in safe_stream:
            # Check if this is our error chunk
            if hasattr(chunk, 'error'):
                logger.warning(f"Skipping error chunk: {chunk.error}")
                continue
                
            yield chunk
            # Yield control back to the event loop periodically
            await asyncio.sleep(0)