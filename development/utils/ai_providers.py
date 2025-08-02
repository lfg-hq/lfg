"""
AI Provider utilities and core functions.

This module contains the core functions for AI provider interactions:
- track_token_usage: Track token usage for billing
- get_notification_type_for_tool: Determine notification types for tools
- map_notification_type_to_tab: Map notification types to UI tabs
- execute_tool_call: Execute AI tool calls
- get_ai_response: Get AI responses (non-streaming wrapper)

The actual provider implementations are in the factory.llm package.
"""

import json
import logging
import asyncio
import traceback
from typing import Optional, Dict, Any, Tuple, List
from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async

from development.utils.ai_functions import app_functions
from chat.models import Conversation
from projects.models import Project, ToolCallHistory
from accounts.models import TokenUsage, LLMApiKeys
from django.contrib.auth.models import User

# Import providers from factory
from factory.llm import LLMProviderFactory
from factory.llm.anthropic import AnthropicProvider
from factory.llm.openai_provider import OpenAIProvider
from factory.llm.xai import XAIProvider
from factory.llm.google import GoogleGeminiProvider

# Import FileHandler from factory utils
from factory.utils import FileHandler

# Set up logger
logger = logging.getLogger(__name__)

# Maximum tool output size (50KB)
MAX_TOOL_OUTPUT_SIZE = 50 * 1024


async def track_token_usage(user: Optional[User], project: Optional[Project], conversation: Optional[Conversation], 
                           usage_data: Any, provider: str, model: str) -> None:
    """Track token usage in the database - common function for all providers"""
    try:
        # Handle different attribute names for token counts
        if provider == 'anthropic':
            input_tokens = getattr(usage_data, 'input_tokens', 0)
            output_tokens = getattr(usage_data, 'output_tokens', 0)
            total_tokens = input_tokens + output_tokens
        elif provider == 'google':
            # Google Gemini usage format
            input_tokens = getattr(usage_data, 'prompt_token_count', 0)
            output_tokens = getattr(usage_data, 'candidates_token_count', 0)
            total_tokens = getattr(usage_data, 'total_token_count', 0)
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


def get_notification_type_for_tool(tool_name: str) -> Optional[str]:
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
        "stream_implementation_content": "file_stream",  # Stream implementation content to filebrowser tab
        "stream_prd_content": "file_stream",  # Stream PRD content to filebrowser tab
        "stream_document_content": "file_stream",  # Stream generic document content to filebrowser tab
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


def map_notification_type_to_tab(notification_type: str) -> str:
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
        "file_stream": "file_stream",  # Map file_stream to filebrowser tab
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


async def execute_tool_call(tool_call_name: str, tool_call_args_str: str, project_id: Optional[int], 
                           conversation_id: Optional[int]) -> Tuple[str, Optional[Dict], str]:
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
            
            # Special handling for file streaming
            if raw_notification_type == "file_stream":
                notification_data["content_chunk"] = tool_result.get("content_chunk", "")
                notification_data["is_complete"] = tool_result.get("is_complete", False)
                notification_data["file_type"] = tool_result.get("file_type", "")
                notification_data["file_name"] = tool_result.get("file_name", "")
                if "file_id" in tool_result:
                    notification_data["file_id"] = tool_result.get("file_id")
                    logger.info(f"FILE_STREAM: Including file_id {tool_result.get('file_id')} in notification")
                else:
                    logger.warning(f"FILE_STREAM: No file_id in tool_result. Keys: {list(tool_result.keys())}")
                logger.info(f"FILE_STREAM in notification handler: chunk_length={len(notification_data['content_chunk'])}, is_complete={notification_data['is_complete']}, file_type={notification_data.get('file_type', 'Not specified')}, file_name={notification_data.get('file_name', 'Not specified')}, file_id={notification_data.get('file_id', 'None')}")
            
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
                tool_args=parsed_args if 'parsed_args' in locals() else {},
                tool_result=result_content[:1000],  # Limit stored result size
                success=notification_data is None or isinstance(notification_data, dict)
            )
            logger.debug(f"Tool call history saved: {tool_history.id}")
            
    except Exception as save_error:
        logger.error(f"Failed to save tool call history: {save_error}")
        # Don't fail the tool execution if saving history fails
    
    return result_content, notification_data, yielded_content


async def get_ai_response(user_message: str, system_prompt: str, project_id: Optional[int], 
                          conversation_id: Optional[int], stream: bool = False, 
                          tools: Optional[List[Dict]] = None) -> Dict[str, Any]:
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
        from development.utils.ai_tools import tools_code
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
    """Base class for AI providers - compatibility wrapper for factory pattern"""
    
    @staticmethod
    def get_provider(provider_name: str, selected_model: str, user: Optional[User] = None, 
                    conversation: Optional[Conversation] = None, project: Optional[Project] = None):
        """Factory method to get the appropriate provider"""
        logger.info(f"Creating provider with provider_name: {provider_name}, selected_model: {selected_model}, user: {user}", 
                   extra={'easylogs_metadata': {'user_id': user.id if user else None}})
        
        # Use the factory to get the provider
        # Pass None as provider_name to let factory infer from model
        return LLMProviderFactory.get_provider(None, selected_model, user, conversation, project)
    
    async def generate_stream(self, messages: List[Dict], project_id: Optional[int], 
                            conversation_id: Optional[int], tools: Optional[List[Dict]]):
        """Generate streaming response from the AI provider"""
        raise NotImplementedError("Subclasses must implement this method")