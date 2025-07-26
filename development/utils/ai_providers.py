import os
import json
import openai
import requests
import anthropic
import logging
import asyncio
import re
from django.conf import settings
from google import genai
from google.genai.types import (
    FunctionDeclaration,
    GenerateContentConfig,
    HttpOptions,
    Tool,
)
from asgiref.sync import sync_to_async
from development.utils.ai_functions import app_functions
from chat.models import AgentRole, ModelSelection, Conversation
from projects.models import Project, ToolCallHistory
from accounts.models import TokenUsage, Profile, LLMApiKeys
from django.contrib.auth.models import User
import traceback # Import traceback for better error logging
from channels.db import database_sync_to_async
from development.utils.ai_tools import tools_ticket
from development.utils.streaming_handlers import StreamingTagHandler, format_notification

import tiktoken


# Set up logger
logger = logging.getLogger(__name__)

# Maximum tool output size (50KB)
MAX_TOOL_OUTPUT_SIZE = 50 * 1024


async def track_token_usage(user, project, conversation, usage_data, provider, model):
    """Track token usage in the database - common function for all providers"""
    try:
        # Handle different attribute names for token counts
        if provider == 'anthropic':
            input_tokens = getattr(usage_data, 'input_tokens', 0)
            output_tokens = getattr(usage_data, 'output_tokens', 0)
            total_tokens = input_tokens + output_tokens
        else:
            # OpenAI and XAI use the same attribute names
            input_tokens = getattr(usage_data, 'prompt_tokens', 0)
            output_tokens = getattr(usage_data, 'completion_tokens', 0)
            total_tokens = getattr(usage_data, 'total_tokens', 0)
        
        logger.info(f"Tracking token usage - Provider: {provider}, Model: {model}, Input: {input_tokens}, Output: {output_tokens}, Total: {total_tokens}")
        
        # Create token usage record
        token_usage = TokenUsage(
            user=user,
            project=project,
            conversation=conversation,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens
        )
        
        # Calculate cost
        token_usage.calculate_cost()
        
        # Save asynchronously
        await asyncio.to_thread(token_usage.save)
        
        logger.debug(f"Token usage tracked: {token_usage}")
        
    except Exception as e:
        logger.error(f"Error tracking token usage: {e}")


def get_notification_type_for_tool(tool_name):
    """
    Determine the notification type based on the tool/function name.
    
    Args:
        tool_name: The name of the tool/function being called
        
    Returns:
        str or None: The notification type if the tool should trigger a notification, None otherwise
    """

    logger.debug(f"Getting notification type for tool: {tool_name}")
    
    # Read operations that should NOT trigger any notifications
    read_operations = {
        "get_features",
        "get_personas", 
        "get_prd",
        "get_implementation",
        "get_next_ticket",
        "get_pending_tickets",
        "get_project_name"
    }
    
    # Return None for read operations to prevent any notification
    if tool_name in read_operations:
        return None
    
    notification_mappings = {
        "extract_features": "checklist",  # Features tab is commented out, use checklist
        "extract_personas": "checklist",  # Personas tab is commented out, use checklist
        "save_features": "checklist",
        "save_personas": "checklist",
        "create_prd": "prd",
        "stream_implementation_content": "implementation_stream",  # Stream implementation content to implementation tab
        "stream_prd_content": "prd_stream",  # Stream PRD content to PRD tab
        "start_server": "apps",  # Server starts should show in apps/preview tab
        "execute_command": "toolhistory",  # Show command execution in tool history
        "save_implementation": "implementation",
        "update_implementation": "implementation",
        "create_implementation": "implementation",
        "design_schema": "implementation",  # Design tab is commented out, use implementation
        "generate_tickets": "checklist",  # Tickets tab is commented out, use checklist
        "checklist_tickets": "checklist",
        "create_tickets": "checklist",  # Add this mapping
        "update_ticket": "checklist",
        "implement_ticket": "implementation",  # Implementation tasks go to implementation tab
        "save_project_name": "toolhistory",  # Project name saving goes to tool history
    }
    
    # Default to None (no notification) instead of toolhistory
    return notification_mappings.get(tool_name, None)

def map_notification_type_to_tab(notification_type):
    """
    Map custom notification types to valid tab names.
    This handles cases where functions return custom notification types.
    
    Args:
        notification_type: The notification type from the tool result
        
    Returns:
        str: A valid tab name
    """
    # Valid tabs from the HTML template
    valid_tabs = ["prd", "implementation", "checklist", "apps", "toolhistory", "codebase"]
    
    # Map custom notification types to valid tabs
    custom_mappings = {
        "features": "checklist",
        "personas": "checklist",
        "design_schema": "implementation",
        "create_tickets": "checklist",
        "get_pending_tickets": "checklist",
        "command_error": "toolhistory",
        "project_name_saved": "toolhistory",
        "prd_stream": "prd_stream",  # Map prd_stream to prd tab
        "implementation_stream": "implementation_stream",  # Map implementation_stream to implementation tab
        # Add more custom mappings as needed
    }
    
    # If it's already a valid tab, return it
    if notification_type in valid_tabs:
        return notification_type
    
    # Check custom mappings
    if notification_type in custom_mappings:
        return custom_mappings[notification_type]
    
    # Default to toolhistory for unknown types
    logger.warning(f"Unknown notification type '{notification_type}', defaulting to toolhistory")
    return "toolhistory"

async def execute_tool_call(tool_call_name, tool_call_args_str, project_id, conversation_id):
    """
    Execute a tool call and return the results.
    
    Args:
        tool_call_name: The name of the tool/function to execute
        tool_call_args_str: The JSON string of arguments for the tool
        project_id: The project ID
        conversation_id: The conversation ID
        
    Returns:
        tuple: (result_content, notification_data, yielded_content)
            - result_content: The string result to return to the model
            - notification_data: Dict with notification data or None
            - yielded_content: Content to yield immediately (e.g., "*" for explanations)
    """
    logger.debug(f"Executing Tool: {tool_call_name}")
    logger.debug(f"Raw Args: {tool_call_args_str}")
    
    # Note: web_search is handled by Claude through the web_search_20250305 tool type
    # and results are included in Claude's response content automatically
    
    result_content = ""
    notification_data = None
    yielded_content = ""
    
    try:
        # Handle empty arguments string by defaulting to an empty object
        if not tool_call_args_str.strip():
            parsed_args = {}
            logger.debug("Empty arguments string, defaulting to empty object")
        else:
            parsed_args = json.loads(tool_call_args_str)
            # Check for both possible spellings of "explanation"
            explanation = parsed_args.get("explanation", parsed_args.get("explaination", ""))
            
            if explanation:
                logger.debug(f"Found explanation: {explanation}")
                # Return the actual explanation to be yielded with formatting
                # Add a newline before and after for better readability
                yielded_content = f"\n*{explanation}*\n"
                
                # Limit the size of yielded content
                if len(yielded_content) > MAX_TOOL_OUTPUT_SIZE:
                    truncated_size = len(yielded_content) - MAX_TOOL_OUTPUT_SIZE
                    yielded_content = yielded_content[:MAX_TOOL_OUTPUT_SIZE] + f"\n\n... [Explanation truncated - {truncated_size} characters removed]*\n"
        
        # Log the function call with clean arguments
        logger.debug(f"Calling app_functions with {tool_call_name}, {parsed_args}, {project_id}, {conversation_id}")
        
        # Execute the function
        try:
            tool_result = await app_functions(
                tool_call_name, parsed_args, project_id, conversation_id
            )
            logger.debug(f"app_functions call successful for {tool_call_name}")
        except Exception as func_error:
            logger.error(f"Error calling app_functions: {str(func_error)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

        logger.debug(f"Tool Result: {tool_result}")
        
        # Send special notification for extraction functions regardless of result
        notification_type = get_notification_type_for_tool(tool_call_name)
        logger.debug(f"Notification type: {notification_type}")
        
        # For stream_prd_content and stream_implementation_content, skip forcing notification if it already has notification data
        if tool_call_name in ["stream_prd_content", "stream_implementation_content"] and isinstance(tool_result, dict) and tool_result.get("is_notification"):
            # Use the notification data from the tool result itself
            logger.info(f"{tool_call_name} already has notification data, not forcing")
        elif notification_type and tool_call_name in [
            "extract_features", "extract_personas", "save_features", "save_personas",
            "create_prd",
            "save_implementation", "update_implementation", "create_implementation",
            "execute_command", "start_server", "design_schema", "generate_tickets",
            "checklist_tickets", "update_ticket", "implement_ticket",
            "save_project_name"
        ]:
            logger.debug(f"FORCING NOTIFICATION FOR {tool_call_name}")
            # Ensure notification type is mapped to a valid tab
            mapped_notification_type = map_notification_type_to_tab(notification_type)
            notification_data = {
                "is_notification": True,
                "notification_type": mapped_notification_type,
                "function_name": tool_call_name,
                "notification_marker": "__NOTIFICATION__"
            }
            
            logger.debug(f"Forced notification: {notification_data}")
        
        # Handle the tool result
        if tool_result is None:
            result_content = "The function returned no result."
        elif isinstance(tool_result, dict) and tool_result.get("is_notification") is True:
            # Set notification data to be yielded later
            logger.debug("NOTIFICATION DATA CREATED IN TOOL EXECUTION")
            logger.debug(f"Tool result: {tool_result}")
            
            # Map the notification type to a valid tab
            raw_notification_type = tool_result.get("notification_type", "toolhistory")
            mapped_notification_type = map_notification_type_to_tab(raw_notification_type)
            
            notification_data = {
                "is_notification": True,
                "notification_type": mapped_notification_type,
                "notification_marker": "__NOTIFICATION__"
            }
            
            # Special handling for PRD and Implementation streaming
            if raw_notification_type == "prd_stream":
                notification_data["content_chunk"] = tool_result.get("content_chunk", "")
                notification_data["is_complete"] = tool_result.get("is_complete", False)
                if "prd_name" in tool_result:
                    notification_data["prd_name"] = tool_result.get("prd_name")
                if "file_id" in tool_result:
                    notification_data["file_id"] = tool_result.get("file_id")
                    logger.info(f"PRD_STREAM: Including file_id {tool_result.get('file_id')} in notification")
                else:
                    logger.warning(f"PRD_STREAM: No file_id in tool_result. Keys: {list(tool_result.keys())}")
                logger.info(f"PRD_STREAM in notification handler: chunk_length={len(notification_data['content_chunk'])}, is_complete={notification_data['is_complete']}, prd_name={notification_data.get('prd_name', 'Not specified')}, file_id={notification_data.get('file_id', 'None')}")
            elif raw_notification_type == "implementation_stream":
                notification_data["content_chunk"] = tool_result.get("content_chunk", "")
                notification_data["is_complete"] = tool_result.get("is_complete", False)
                if "file_id" in tool_result:
                    notification_data["file_id"] = tool_result.get("file_id")
                    logger.info(f"IMPLEMENTATION_STREAM: Including file_id {tool_result.get('file_id')} in notification")
                else:
                    logger.warning(f"IMPLEMENTATION_STREAM: No file_id in tool_result. Keys: {list(tool_result.keys())}")
                logger.info(f"IMPLEMENTATION_STREAM in notification handler: chunk_length={len(notification_data['content_chunk'])}, is_complete={notification_data['is_complete']}, file_id={notification_data.get('file_id', 'None')}")
            
            logger.debug(f"Notification data to be yielded: {notification_data}")
            
            # Use the message_to_agent as the result content
            result_content = str(tool_result.get("message_to_agent", ""))
        else:
            # Normal case without notification or when tool_result is a string
            if isinstance(tool_result, str):
                result_content = tool_result
            elif isinstance(tool_result, dict):
                result_content = str(tool_result.get("message_to_agent", ""))
            else:
                # If tool_result is neither a string nor a dict
                result_content = str(tool_result) if tool_result is not None else ""
        
        # Limit the size of the result content
        if len(result_content) > MAX_TOOL_OUTPUT_SIZE:
            truncated_size = len(result_content) - MAX_TOOL_OUTPUT_SIZE
            result_content = result_content[:MAX_TOOL_OUTPUT_SIZE] + f"\n\n... [Output truncated - {truncated_size} characters removed]"
            logger.warning(f"Tool output truncated from {len(result_content) + truncated_size} to {MAX_TOOL_OUTPUT_SIZE} characters")
        
        logger.debug(f"Tool Success. Result: {result_content}")
        
    except json.JSONDecodeError as e:
        error_message = f"Failed to parse JSON arguments: {e}. Args: {tool_call_args_str}"
        logger.error(error_message)
        result_content = f"Error: {error_message}"
        notification_data = None
    except Exception as e:
        error_message = f"Error executing tool {tool_call_name}: {e}"
        logger.error(f"{error_message}\n{traceback.format_exc()}")
        result_content = f"Error: {error_message}"
        notification_data = None
    
    # Save the tool call history to database
    try:
        # Get the project and conversation objects
        project = await asyncio.to_thread(Project.objects.get, id=project_id) if project_id else None
        conversation = await asyncio.to_thread(Conversation.objects.get, id=conversation_id) if conversation_id else None
        
        if project:
            # Get the latest message from the conversation if available
            message = None
            if conversation:
                try:
                    message = await asyncio.to_thread(
                        lambda: conversation.messages.filter(role='assistant').order_by('-created_at').first()
                    )
                except:
                    pass
            
            # Create the tool call history record
            tool_history = await asyncio.to_thread(
                ToolCallHistory.objects.create,
                project=project,
                conversation=conversation,
                message=message,
                tool_name=tool_call_name,
                tool_input=parsed_args if 'parsed_args' in locals() else {},
                generated_content=result_content,
                content_type='text',
                metadata={
                    'notification_data': notification_data,
                    'yielded_content': yielded_content,
                    'has_error': 'Error:' in result_content
                }
            )
            logger.debug(f"Tool call history saved: {tool_history.id}")
    except Exception as save_error:
        logger.error(f"Failed to save tool call history: {save_error}")
        # Don't fail the tool execution if saving history fails
    
    return result_content, notification_data, yielded_content

async def get_ai_response(user_message, system_prompt, project_id, conversation_id, stream=False, tools=None):
    """
    Non-streaming wrapper for AI providers to be used in task implementations.
    Collects the full response from streaming providers and returns it as a complete response.
    
    Args:
        user_message: The user's message content
        system_prompt: The system prompt for the AI
        project_id: The project ID
        conversation_id: The conversation ID
        stream: Whether to return streaming (not used, kept for compatibility)
        tools: List of tools available to the AI
        
    Returns:
        Dict containing the AI response with content and tool_calls
    """
    if tools is None:
        from coding.utils.ai_tools import tools_code
        tools = tools_code
    
    # Create messages list
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    
    # Get the conversation or project to extract the user
    conversation = None
    project = None
    user = None
    
    try:
        if conversation_id:
            conversation = await asyncio.to_thread(
                Conversation.objects.select_related('user', 'project').get,
                id=conversation_id
            )
            user = conversation.user
            project = conversation.project
        elif project_id:
            project = await asyncio.to_thread(
                Project.objects.select_related('owner').get,
                id=project_id
            )
            user = project.owner
    except Exception as e:
        logger.warning(f"Could not get user/conversation/project: {e}")
    
    # Get the default provider (can be enhanced later to support provider selection)
    provider = AIProvider.get_provider("anthropic", "claude_4_sonnet", user, conversation, project)
    
    # Collect the streaming response
    full_content = ""
    tool_calls = []
    
    try:
        async for chunk in provider.generate_stream(messages, project_id, conversation_id, tools):
            # Skip notification chunks
            if isinstance(chunk, str) and ("__NOTIFICATION__" in chunk):
                continue
            full_content += chunk
        
        # Note: The provider.generate_stream already handles tool calls internally
        # and executes them. The tool calls are not returned in the stream,
        # they are executed automatically within the stream processing.
        
        return {
            "content": full_content,
            "tool_calls": tool_calls  # Will be empty since tools are auto-executed
        }
        
    except Exception as e:
        logger.error(f"Error in get_ai_response: {str(e)}")
        return {
            "content": f"Error generating AI response: {str(e)}",
            "tool_calls": []
        }

class AIProvider:
    """Base class for AI providers"""
    
    @staticmethod
    def get_provider(provider_name, selected_model, user=None, conversation=None, project=None):
        """Factory method to get the appropriate provider"""
        logger.info(f"Creating provider with provider_name: {provider_name}, selected_model: {selected_model}, user: {user}", extra={'easylogs_metadata': {'user_id': user.id if user else None}})
        providers = {
            'openai': lambda: OpenAIProvider(selected_model, user, conversation, project),
            'anthropic': lambda: AnthropicProvider(selected_model, user, conversation, project),
            'xai': lambda: XAIProvider(selected_model, user, conversation, project),
        }
        provider_factory = providers.get(provider_name)
        if provider_factory:
            return provider_factory()
        else:
            return OpenAIProvider(selected_model, user, conversation, project)  # Default fallback
    
    async def generate_stream(self, messages, project_id, conversation_id, tools):
        """Generate streaming response from the AI provider"""
        raise NotImplementedError("Subclasses must implement this method")


class OpenAIProvider(AIProvider):
    """OpenAI provider implementation"""
    
    def __init__(self, selected_model, user=None, conversation=None, project=None):

        logger.debug(f"Selected model: {selected_model}")
        
        # Get user from conversation or project if not provided
        if not user:
            if conversation:
                user = conversation.user
            elif project:
                user = project.owner
        
        # Store user and model info for async profile fetching
        self.user = user
        self.selected_model = selected_model
        self.openai_api_key = ''  # Initialize to empty string

        if selected_model == "gpt_4o":
            self.model = "gpt-4o"
        elif selected_model == "gpt_4.1":
            self.model = "gpt-4.1"
        elif selected_model == "o3":
            self.model = "o3"
        else:
            # Default to gpt-4o if unknown model
            self.model = "gpt-4o"
            logger.warning(f"Unknown model {selected_model}, defaulting to gpt-4o")

        logger.info(f"OpenAI Provider initialized with model: {self.model}")
        
        # Client will be initialized in async method
        self.client = None
    
    @database_sync_to_async
    def _get_openai_key(self, user):
        """Get user profile synchronously"""
        try:
            llm_keys = LLMApiKeys.objects.get(user=user)
            if llm_keys.openai_api_key:
                return llm_keys.openai_api_key
        except LLMApiKeys.DoesNotExist:
            pass
        return ""

    async def _ensure_client(self):
        """Ensure the client is initialized with API key"""
        
        # Try to fetch API key from user profile if available and not already set
        if self.user:
            try:
                self.openai_api_key = await self._get_openai_key(self.user)
                logger.info(f"Fetched OpenAI API key from user {self.user.id} profile")
            except Profile.DoesNotExist:
                logger.warning(f"Profile does not exist for user {self.user.id}")
            except Exception as e:
                logger.warning(f"Could not fetch OpenAI API key from user profile for user {self.user.id}: {e}")
        
        # Initialize client
        if self.openai_api_key:
            self.client = openai.OpenAI(api_key=self.openai_api_key)
        else:
            logger.warning("No OpenAI API key found")

    def estimate_tokens(self, messages, model=None, output_text=None):
        """Estimate token count for messages and output using tiktoken"""
        if not tiktoken:
            logger.warning("tiktoken not available, cannot estimate tokens")
            return None, None
            
        try:
            # Use the model-specific encoding or fall back to cl100k_base
            try:
                if model == "gpt-4o" or model == "gpt-4.1" or model == "o3":
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

    async def generate_stream(self, messages, project_id, conversation_id, tools):
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
                    Conversation.objects.select_related('user', 'project').get,
                    id=conversation_id
                )
                user = conversation.user
                project = conversation.project
            elif project_id:
                project = await asyncio.to_thread(
                    Project.objects.select_related('owner').get,
                    id=project_id
                )
                user = project.owner
        except Exception as e:
            logger.warning(f"Could not get user/project/conversation for token tracking: {e}")

        # Initialize streaming tag handler
        tag_handler = StreamingTagHandler()
        
        # Buffer to capture ALL assistant output for accurate token counting
        total_assistant_output = ""

        logger.debug(f"Starting OpenAI stream generation loop")

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

        while True: # Loop to handle potential multi-turn tool calls (though typically one round)
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
                    # logger.debug(f"Chunk received: {chunk}")  # Too verbose, commented out
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
                            
                            # Track token usage for tool calls
                            if user:
                                if usage_data:
                                    logger.info(f"Using API-provided token usage for tool calls - Input: {getattr(usage_data, 'prompt_tokens', 'N/A')}, Output: {getattr(usage_data, 'completion_tokens', 'N/A')}, Total: {getattr(usage_data, 'total_tokens', 'N/A')}")
                                    await track_token_usage(
                                        user, project, conversation, usage_data, 'openai', self.model
                                    )
                                else:
                                    # Fallback: estimate tokens if usage data not available
                                    logger.warning("No usage data from OpenAI API for tool calls, using tiktoken estimation")
                                    logger.info(f"Total assistant output captured: {len(total_assistant_output)} characters")
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
                                        logger.info(f"Tracking estimated tokens for tool calls - Input: {estimated_input_tokens}, Output: {estimated_output_tokens}, Total: {estimated_input_tokens + estimated_output_tokens}")
                                        await track_token_usage(
                                            user, project, conversation, mock_usage, 'openai', self.model
                                        )
                                    else:
                                        logger.error("Failed to estimate tokens for tool calls")
                            
                            break # Break inner chunk loop
                        
                        elif finish_reason == "stop":
                            # Save any captured data
                            logger.info(f"[OPENAI] Stream finished, checking for captured files to save")
                            save_notifications = await tag_handler.save_captured_data(project_id)
                            logger.info(f"[OPENAI] Got {len(save_notifications)} save notifications")
                            for notification in save_notifications:
                                logger.info(f"[OPENAI] Yielding save notification: {notification}")
                                # Log specific details about file_id
                                if 'file_id' in notification:
                                    logger.info(f"[OPENAI] NOTIFICATION HAS FILE_ID: {notification['file_id']}")
                                    logger.info(f"[OPENAI] Notification type: {notification.get('notification_type')}")
                                else:
                                    logger.warning(f"[OPENAI] NO FILE_ID IN NOTIFICATION! Keys: {list(notification.keys())}")
                                formatted = format_notification(notification)
                                logger.info(f"[OPENAI] Formatted notification: {formatted[:100]}...")
                                logger.info(f"[OPENAI] Full formatted notification: {formatted}")
                                yield formatted
                            
                            # Track token usage before exiting
                            if user:
                                if usage_data:
                                    logger.info(f"Using API-provided token usage on stop - Input: {getattr(usage_data, 'prompt_tokens', 'N/A')}, Output: {getattr(usage_data, 'completion_tokens', 'N/A')}, Total: {getattr(usage_data, 'total_tokens', 'N/A')}")
                                    await track_token_usage(
                                        user, project, conversation, usage_data, 'openai', self.model
                                    )
                                else:
                                    # Fallback: estimate tokens if usage data not available
                                    logger.warning("No usage data from OpenAI API on stop, using tiktoken estimation")
                                    logger.info(f"Total assistant output captured: {len(total_assistant_output)} characters")
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
                                        logger.info(f"Tracking estimated tokens on stop - Input: {estimated_input_tokens}, Output: {estimated_output_tokens}, Total: {estimated_input_tokens + estimated_output_tokens}")
                                        await track_token_usage(
                                            user, project, conversation, mock_usage, 'openai', self.model
                                        )
                                    else:
                                        logger.error("Failed to estimate tokens on stop")
                            return
                        else:
                            # Handle other finish reasons
                            logger.warning(f"Unhandled finish reason: {finish_reason}")
                            if user:
                                if usage_data:
                                    await track_token_usage(
                                        user, project, conversation, usage_data, 'openai', self.model
                                    )
                                else:
                                    # Fallback: estimate tokens if usage data not available
                                    logger.warning(f"No usage data from OpenAI API for finish reason '{finish_reason}', using tiktoken estimation")
                                    logger.info(f"Total assistant output captured: {len(total_assistant_output)} characters")
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
                                        logger.info(f"Tracking estimated tokens for {finish_reason} - Input: {estimated_input_tokens}, Output: {estimated_output_tokens}, Total: {estimated_input_tokens + estimated_output_tokens}")
                                        await track_token_usage(
                                            user, project, conversation, mock_usage, 'openai', self.model
                                        )
                                    else:
                                        logger.error(f"Failed to estimate tokens for finish reason '{finish_reason}'")
                            return
                
                # If the inner loop finished because of tool_calls, continue
                if finish_reason == "tool_calls":
                    continue
                else:
                    logger.warning("Stream ended unexpectedly.")
                    # Try to track whatever usage we have
                    if user:
                        if usage_data:
                            await track_token_usage(
                                user, project, conversation, usage_data, 'openai', self.model
                            )
                        else:
                            # Fallback: estimate tokens for unexpected ending
                            logger.warning("No usage data from OpenAI API for unexpected stream end, using tiktoken estimation")
                            logger.info(f"Total assistant output captured: {len(total_assistant_output)} characters")
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
                                logger.info(f"Tracking estimated tokens for unexpected end - Input: {estimated_input_tokens}, Output: {estimated_output_tokens}, Total: {estimated_input_tokens + estimated_output_tokens}")
                                await track_token_usage(
                                    user, project, conversation, mock_usage, 'openai', self.model
                                )
                            else:
                                logger.error("Failed to estimate tokens for unexpected stream end")
                    return

            except Exception as e:
                logger.error(f"Critical Error: {str(e)}\n{traceback.format_exc()}")
                yield f"Error with OpenAI stream: {str(e)}"
                return
            
    async def _process_stream_async(self, response_stream):
        """
        Process the response stream asynchronously by yielding control back to event loop
        """
        for chunk in response_stream:
            yield chunk
            # Yield control back to the event loop periodically
            await asyncio.sleep(0)    
 

class XAIProvider(AIProvider):
    """XAI (Grok) provider implementation"""
    
    def __init__(self, selected_model, user=None, conversation=None, project=None):
        logger.debug(f"Selected model: {selected_model}")
        
        # Get user from conversation or project if not provided
        if not user:
            if conversation:
                user = conversation.user
            elif project:
                user = project.owner
        
        # Store user and model info for async profile fetching
        self.user = user
        self.selected_model = selected_model
        
        # Map XAI model names
        if selected_model == "grok_4":
            self.model = "grok-4"
        else:
            # Default to grok-4
            self.model = "grok-4"
            logger.warning(f"Unknown model {selected_model}, defaulting to grok-4")
        
        logger.info(f"Selected XAI model: {self.model}")
        
        # Client will be initialized in async method
        self.client = None
        self.base_url = "https://api.x.ai/v1"
    
    @database_sync_to_async
    def _get_xai_key(self, user):
        """Get user profile synchronously"""
        try:
            llm_keys = LLMApiKeys.objects.get(user=user)
            # Note: Using xai_api_key field
            # If this is incorrect, the field name should be updated in the LLMApiKeys model
            if hasattr(llm_keys, 'xai_api_key') and llm_keys.xai_api_key:
                return llm_keys.xai_api_key
        except LLMApiKeys.DoesNotExist:
            pass
        return ""
    
    async def _ensure_client(self):
        """Ensure the client is initialized with API key"""
        
        # Try to fetch API key from user profile if available
        if self.user:
            try:
                self.xai_api_key = await self._get_xai_key(self.user)
                logger.info(f"Fetched XAI API key from user {self.user.id} profile")
            except Profile.DoesNotExist:
                logger.warning(f"Profile does not exist for user {self.user.id}")
            except Exception as e:
                logger.warning(f"Could not fetch XAI API key from user profile for user {self.user.id}: {e}")
        
        # Initialize client using OpenAI-compatible interface
        if self.xai_api_key:
            self.client = openai.OpenAI(
                api_key=self.xai_api_key,
                base_url=self.base_url
            )
        else:
            logger.warning("No XAI API key found")
    
    async def generate_stream(self, messages, project_id, conversation_id, tools):
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
                    Conversation.objects.select_related('user', 'project').get,
                    id=conversation_id
                )
                user = conversation.user
                project = conversation.project
            elif project_id:
                project = await asyncio.to_thread(
                    Project.objects.select_related('owner').get,
                    id=project_id
                )
                user = project.owner
        except Exception as e:
            logger.warning(f"Could not get user/project/conversation for token tracking: {e}")

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
                                # Log specific details about file_id
                                if 'file_id' in notification:
                                    logger.info(f"[XAI] NOTIFICATION HAS FILE_ID: {notification['file_id']}")
                                    logger.info(f"[XAI] Notification type: {notification.get('notification_type')}")
                                else:
                                    logger.warning(f"[XAI] NO FILE_ID IN NOTIFICATION! Keys: {list(notification.keys())}")
                                formatted = format_notification(notification)
                                logger.info(f"[XAI] Formatted notification: {formatted[:100]}...")
                                logger.info(f"[XAI] Full formatted notification: {formatted}")
                                yield formatted
                            
                            # Track token usage before exiting
                            if usage_data and user:
                                await track_token_usage(
                                    user, project, conversation, usage_data, 'xai', self.model
                                )
                            return
                        else:
                            logger.warning(f"Unhandled finish reason: {finish_reason}")
                            if usage_data and user:
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
                logger.error(f"Critical Error: {str(e)}\\n{traceback.format_exc()}")
                yield f"Error with XAI stream: {str(e)}"
                return

    async def _process_stream_async(self, response_stream):
        """Process the response stream asynchronously by yielding control back to event loop"""
        for chunk in response_stream:
            yield chunk
            await asyncio.sleep(0)
    


class AnthropicProvider(AIProvider):
    """Anthropic Claude provider implementation"""
    
    def __init__(self, selected_model, user=None, conversation=None, project=None):
        logger.debug(f"Selected model: {selected_model}")
        
        # Get user from conversation or project if not provided
        if not user:
            if conversation:
                user = conversation.user
            elif project:
                user = project.owner
        
        # Store user for async profile fetching
        self.user = user

        logger.info(f"Anthropic provider initialized for user: {user}", extra={'easylogs_metadata': {'user_id': user.id if user else None}})
        
        self.anthropic_api_key = ''
        
        if selected_model == "claude_4_sonnet":
            self.model = "claude-sonnet-4-20250514"
        elif selected_model == "claude_4_opus":
            self.model = "claude-opus-4-20250514"
        elif selected_model == "claude_3.5_sonnet":
            self.model = "claude-3-5-sonnet-20241022"
        else:
            # Default to claude-4-sonnet
            self.model = "claude-sonnet-4-20250514"
            
        logger.debug(f"Using Claude model: {self.model}")
        
        # Client will be initialized in async method
        self.client = None
    
    @database_sync_to_async
    def _get_anthropic_key(self, user):
        """Get user profile synchronously"""
        try:
            llm_keys = LLMApiKeys.objects.get(user=user)
            if llm_keys.anthropic_api_key:
                return llm_keys.anthropic_api_key
        except LLMApiKeys.DoesNotExist:
            pass
        return ""

    async def _ensure_client(self):
        """Ensure the client is initialized with API key"""
        logger.debug(f"Ensuring client is initialized with API key for user: {self.user}")
        
        # Try to fetch API key from user profile if available and not already set
        if self.user:
            try:
                logger.debug(f"User exists: {self.user} (ID: {self.user.id})")
                self.anthropic_api_key = await self._get_anthropic_key(self.user)
                logger.info(f"Fetched Anthropic API key from user {self.user.id} profile")

            except Profile.DoesNotExist:
                logger.warning(f"Profile does not exist for user {self.user.id}")
            except Exception as e:
                logger.warning(f"Could not fetch Anthropic API key from user profile for user {self.user.id}: {e}")
        
        # Initialize client
        if self.anthropic_api_key:
            self.client = anthropic.AsyncAnthropic(api_key=self.anthropic_api_key)
        else:
            logger.warning("No Anthropic API key found")

    def _convert_messages_to_claude_format(self, messages):
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

    def _convert_tools_to_claude_format(self, tools):
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


    async def generate_stream(self, messages, project_id, conversation_id, tools):
        # Ensure client is initialized with API key
        logger.info("Generating stream for Anthropic provider")
        await self._ensure_client()
        
        # Check if client is initialized
        if not self.client:
            yield "Error: No Anthropic API key configured. Please add API key [here](/settings/)."
            return
            
        current_messages = list(messages) # Work on a copy
        
        # Get user and project/conversation for token tracking
        user = None
        project = None
        conversation = None
        
        try:
            if conversation_id:
                conversation = await asyncio.to_thread(
                    Conversation.objects.select_related('user', 'project').get,
                    id=conversation_id
                )
                user = conversation.user
                project = conversation.project
            elif project_id:
                project = await asyncio.to_thread(
                    Project.objects.select_related('owner').get,
                    id=project_id
                )
                user = project.owner
        except Exception as e:
            logger.warning(f"Could not get user/project/conversation for token tracking: {e}")
            
        # Initialize streaming tag handler
        tag_handler = StreamingTagHandler()

        while True: # Loop to handle potential multi-turn tool calls
            try:
                # Convert messages and tools to Claude format
                claude_messages = self._convert_messages_to_claude_format(current_messages)
                claude_tools = self._convert_tools_to_claude_format(tools)

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
                logger.debug(f"Available tools for Claude: {[tool['name'] for tool in claude_tools]}")
                
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
                
                if system_message:
                    params["system"] = system_message
                
                logger.debug(f"Making Claude API call with {len(claude_messages)} messages.")
                logger.info(f"Claude model: {self.model} - web_search is built-in for Claude Sonnet 4")
                
                # Variables for this specific API call
                tool_calls_requested = [] # Stores {id, function_name, function_args_str}
                full_assistant_message = {"role": "assistant", "content": None, "tool_calls": []} # To store the complete assistant turn
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
                                if function_name not in ["stream_prd_content", "stream_implementation_content"]:
                                    # Send early notification for other tool uses
                                    logger.info(f"SENDING EARLY NOTIFICATION FOR {function_name}")
                                    early_notification = {
                                        "is_notification": True,
                                        "notification_type": notification_type or "tool",
                                        "early_notification": True,
                                        "function_name": function_name,
                                        "notification_marker": "__NOTIFICATION__"
                                    }
                                    notification_json = json.dumps(early_notification)
                                    logger.info(f"Early notification JSON: {notification_json}")
                                    yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                                else:
                                    logger.info(f"Skipping early notification for {function_name} - will send with content later")
                        
                        elif event.type == "content_block_delta":
                            if event.delta.type == "text_delta":
                                # Stream text content
                                text = event.delta.text
                                
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
                                
                                # Update the full assistant message
                                if full_assistant_message["content"] is None:
                                    full_assistant_message["content"] = ""
                                full_assistant_message["content"] += text
                                
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
                            if hasattr(event.message, 'usage') and event.message.usage and user:
                                await track_token_usage(
                                    user, project, conversation, event.message.usage, 'anthropic', self.model
                                )
                            
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
                            
                            elif stop_reason in ["end_turn", "stop_sequence", "max_tokens"]:
                                # Conversation finished naturally
                                logger.debug(f"[AnthropicProvider] Claude finished without using tools. Stop reason: {stop_reason}")
                                if full_assistant_message["content"]:
                                    logger.debug(f"[AnthropicProvider] Assistant response snippet: {full_assistant_message['content'][:100]}...")
                                
                                # Flush any remaining buffer content
                                flushed_output = tag_handler.flush_buffer()
                                if flushed_output:
                                    yield flushed_output
                                
                                # Save any captured data
                                logger.info(f"[ANTHROPIC] Stream finished, checking for captured files to save")
                                save_notifications = await tag_handler.save_captured_data(project_id)
                                logger.info(f"[ANTHROPIC] Got {len(save_notifications)} save notifications")
                                for notification in save_notifications:
                                    logger.info(f"[ANTHROPIC] Yielding save notification: {notification}")
                                    # Log specific details about file_id
                                    if 'file_id' in notification:
                                        logger.info(f"[ANTHROPIC] NOTIFICATION HAS FILE_ID: {notification['file_id']}")
                                        logger.info(f"[ANTHROPIC] Notification type: {notification.get('notification_type')}")
                                    else:
                                        logger.warning(f"[ANTHROPIC] NO FILE_ID IN NOTIFICATION! Keys: {list(notification.keys())}")
                                    formatted = format_notification(notification)
                                    logger.info(f"[ANTHROPIC] Formatted notification: {formatted[:100]}...")
                                    logger.info(f"[ANTHROPIC] Full formatted notification: {formatted}")
                                    yield formatted
                                
                                return
                            else:
                                logger.warning(f"[AnthropicProvider] Unhandled stop reason: {stop_reason}")
                                return
                
                # If we broke out of the inner loop due to tool_use, continue
                if tool_calls_requested:
                    continue
                else:
                    # Stream ended without tool calls
                    return

            except Exception as e:
                logger.error(f"Critical Error: {str(e)}\n{traceback.format_exc()}")
                yield f"Error with Claude stream: {str(e)}"
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


class FileHandler:
    """Factory class for handling file uploads and parsing across different AI providers"""
    
    def __init__(self, provider_name, user=None):
        self.provider_name = provider_name.lower()
        self.user = user
        self.supported_formats = self._get_supported_formats()
    
    def _get_supported_formats(self):
        """Get supported file formats for each provider"""
        formats = {
            'anthropic': {
                'images': ['.jpg', '.jpeg', '.png', '.gif', '.webp'],
                'documents': ['.pdf', '.csv', '.txt', '.md', '.docx', '.xlsx'],
                'audio': ['.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm'],  # Supported by transcription
                'max_size_mb': 100,  # Reasonable limit
                'methods': ['base64', 'file_id']
            },
            'openai': {
                'images': ['.jpg', '.jpeg', '.png', '.gif', '.webp'],
                'documents': ['.pdf'],  # PDFs supported by GPT-4o models
                'audio': ['.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm'],  # Whisper supported formats
                'max_size_mb': 32,  # PDF limit
                'max_audio_mb': 25,  # Whisper API limit
                'max_images': 10,
                'methods': ['base64', 'url']
            },
            'xai': {
                'images': ['.jpg', '.jpeg', '.png', '.gif', '.webp'],
                'documents': [],  # Limited document support currently
                'audio': ['.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm'],  # Can use OpenAI Whisper
                'max_size_mb': 20,  # Conservative estimate
                'methods': ['base64', 'url']
            }
        }
        return formats.get(self.provider_name, formats['openai'])
    
    def is_supported_file(self, filename):
        """Check if a file type is supported by the provider"""
        ext = os.path.splitext(filename)[1].lower()
        supported = self.supported_formats
        return ext in supported['images'] + supported['documents'] + supported.get('audio', [])
    
    def get_file_category(self, filename):
        """Determine if file is an image, document, or audio"""
        ext = os.path.splitext(filename)[1].lower()
        if ext in self.supported_formats['images']:
            return 'image'
        elif ext in self.supported_formats['documents']:
            return 'document'
        elif ext in self.supported_formats.get('audio', []):
            return 'audio'
        return None
    
    async def prepare_file_for_provider(self, chat_file, storage):
        """Prepare a file for sending to the AI provider"""
        try:
            filename = chat_file.original_filename
            file_category = self.get_file_category(filename)
            
            if not file_category:
                raise ValueError(f"Unsupported file type for {self.provider_name}: {filename}")
            
            # Get file content
            file_content = await self._get_file_content(chat_file, storage)
            
            # Handle audio files specially - they need transcription
            if file_category == 'audio':
                return await self._prepare_audio_file(chat_file, file_content)
            
            # Prepare based on provider for non-audio files
            if self.provider_name == 'anthropic':
                return await self._prepare_anthropic_file(chat_file, file_content, file_category)
            elif self.provider_name == 'openai':
                return await self._prepare_openai_file(chat_file, file_content, file_category)
            elif self.provider_name == 'xai':
                return await self._prepare_xai_file(chat_file, file_content, file_category)
            else:
                raise ValueError(f"Unknown provider: {self.provider_name}")
                
        except Exception as e:
            logger.error(f"Error preparing file for {self.provider_name}: {str(e)}")
            raise
    
    async def _get_file_content(self, chat_file, storage):
        """Get file content from storage"""
        try:
            # Open file from storage using sync_to_async
            from asgiref.sync import sync_to_async
            
            @sync_to_async
            def read_file():
                file_obj = storage._open(chat_file.file.name, 'rb')
                content = file_obj.read()
                if hasattr(file_obj, 'close'):
                    file_obj.close()
                return content
            
            return await read_file()
        except Exception as e:
            logger.error(f"Error reading file content: {str(e)}")
            raise
    
    async def _prepare_anthropic_file(self, chat_file, content, category):
        """Prepare file for Anthropic Claude API"""
        import base64
        
        if category == 'image':
            # Use base64 for images
            base64_content = base64.b64encode(content).decode('utf-8')
            media_type = chat_file.file_type or 'image/jpeg'
            
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64_content
                }
            }
        else:
            # For documents (PDF), use base64 encoding
            base64_content = base64.b64encode(content).decode('utf-8')
            
            return {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": chat_file.file_type or "application/pdf",
                    "data": base64_content
                },
                "title": chat_file.original_filename
            }
    
    async def _prepare_openai_file(self, chat_file, content, category):
        """Prepare file for OpenAI API"""
        import base64
        
        if category in ['image', 'document']:
            # Use base64 for both images and PDFs
            base64_content = base64.b64encode(content).decode('utf-8')
            media_type = chat_file.file_type or ('image/jpeg' if category == 'image' else 'application/pdf')
            
            return {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{media_type};base64,{base64_content}"
                }
            }
        
        raise ValueError(f"Unsupported file category for OpenAI: {category}")
    
    async def _prepare_xai_file(self, chat_file, content, category):
        """Prepare file for XAI Grok API (OpenAI-compatible)"""
        # XAI uses the same format as OpenAI
        return await self._prepare_openai_file(chat_file, content, category)
    
    async def _prepare_audio_file(self, chat_file, content):
        """Prepare audio file by transcribing it using OpenAI Whisper"""
        try:
            # Import OpenAI client
            from openai import OpenAI
            from asgiref.sync import sync_to_async
            
            # Get OpenAI API key from user profile or settings
            @sync_to_async
            def get_openai_api_key():
                # Try to get from user profile first
                if hasattr(self, 'user') and self.user:
                    try:
                        from accounts.models import Profile
                        profile = Profile.objects.get(user=self.user)
                        if profile.openai_api_key:
                            return profile.openai_api_key
                    except:
                        pass
                
                # Fallback to settings
                return getattr(settings, 'OPENAI_API_KEY', None)
            
            api_key = await get_openai_api_key()
            if not api_key:
                raise ValueError("OpenAI API key not found for audio transcription")
            
            # Create OpenAI client
            client = OpenAI(api_key=api_key)
            
            # Create a temporary file for the audio content
            import tempfile
            import aiofiles
            
            # Get file extension
            ext = os.path.splitext(chat_file.original_filename)[1].lower()
            
            # Create temporary file with proper extension
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
                tmp_file.write(content)
                tmp_file_path = tmp_file.name
            
            try:
                # Transcribe using Whisper API
                @sync_to_async
                def transcribe_audio():
                    with open(tmp_file_path, 'rb') as audio_file:
                        transcript = client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            response_format="text"
                        )
                    return transcript
                
                transcription = await transcribe_audio()
                
                # Track audio transcription usage
                await self._track_audio_transcription_usage(chat_file, content)
                
                # Format the transcription as a text message
                return {
                    "type": "text",
                    "text": f"[Audio Transcription of {chat_file.original_filename}]:\n\n{transcription}"
                }
                
            finally:
                # Clean up temporary file
                try:
                    os.unlink(tmp_file_path)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Error transcribing audio file: {str(e)}")
            # Return error message instead of raising
            return {
                "type": "text",
                "text": f"[Error transcribing audio file {chat_file.original_filename}: {str(e)}]"
            }
    
    async def _track_audio_transcription_usage(self, chat_file, content):
        """Track audio transcription usage for billing"""
        try:
            from asgiref.sync import sync_to_async
            from accounts.models import TokenUsage
            
            # Calculate audio duration in seconds (approximate based on file size)
            # Average audio bitrate: 128 kbps = 16 KB/s
            file_size_kb = len(content) / 1024
            duration_seconds = file_size_kb / 16  # Rough estimate
            duration_minutes = max(1, int(duration_seconds / 60))  # Minimum 1 minute
            
            # OpenAI Whisper costs $0.006 per minute
            cost = duration_minutes * 0.006
            
            @sync_to_async
            def save_usage():
                if self.user:
                    # Create a token usage record for transcription
                    usage = TokenUsage(
                        user=self.user,
                        provider='openai',
                        model='whisper-1',
                        input_tokens=0,  # Whisper doesn't use tokens
                        output_tokens=0,
                        total_tokens=0,
                        cost=cost,
                        conversation=getattr(chat_file, 'conversation', None),
                        project=getattr(chat_file.conversation, 'project', None) if hasattr(chat_file, 'conversation') else None
                    )
                    usage.save()
                    
                    logger.info(f"Tracked audio transcription: {duration_minutes} minutes, cost: ${cost:.4f}")
            
            await save_usage()
            
        except Exception as e:
            logger.error(f"Error tracking audio transcription usage: {e}")
    
    def format_file_message(self, file_data, text_content=None):
        """Format file data into a message structure for the provider"""
        if self.provider_name == 'anthropic':
            # Anthropic supports mixing text and files in content array
            content = []
            if text_content:
                content.append({"type": "text", "text": text_content})
            content.append(file_data)
            return content
        
        elif self.provider_name in ['openai', 'xai']:
            # OpenAI/XAI require separate content entries
            content = []
            if text_content:
                content.append({"type": "text", "text": text_content})
            content.append(file_data)
            return content
        
        else:
            raise ValueError(f"Unknown provider: {self.provider_name}")
    
    @staticmethod
    def get_handler(provider_name, user=None):
        """Factory method to get a FileHandler instance"""
        return FileHandler(provider_name, user)
    
