"""
AI Provider utilities and core functions.

This module contains the AIProvider class and get_ai_response function.
Common functions like track_token_usage, execute_tool_call, etc. are in ai_common.py
to avoid circular imports.

The actual provider implementations are in the factory.llm package.
"""

import logging
import asyncio
from typing import Optional, Dict, Any, List
from django.contrib.auth.models import User

from chat.models import Conversation, ModelSelection
from projects.models import Project

# Import shared functions from ai_common to avoid circular imports
from factory.ai_common import (
    track_token_usage,
    get_notification_type_for_tool,
    map_notification_type_to_tab,
    execute_tool_call,
    MAX_TOOL_OUTPUT_SIZE
)

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


async def _get_selected_model_for_user(user: Optional[User]) -> str:
    """Return the user's selected model or default."""
    default_model = ModelSelection.DEFAULT_MODEL_KEY
    if not user:
        return default_model
    try:
        model_selection = await asyncio.to_thread(ModelSelection.objects.get, user=user)
        return model_selection.selected_model
    except ModelSelection.DoesNotExist:
        try:
            model_selection = await asyncio.to_thread(
                ModelSelection.objects.create,
                user=user,
                selected_model=default_model
            )
            return model_selection.selected_model
        except Exception as create_error:
            logger.warning(f"Could not create default model selection for user {user.id}: {create_error}")
    except Exception as selection_error:
        logger.warning(f"Could not load model selection for user {user.id}: {selection_error}")
    return default_model

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
        from factory.ai_tools import tools_code
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
    except Exception as e:
        logger.warning(f"Could not get user/conversation from conversation_id {conversation_id}: {e}")

    # If we couldn't get user from conversation, try project
    if not user and project_id:
        try:
            # Try to get project by UUID (project_id field) or database ID
            if isinstance(project_id, str) and len(project_id) > 10:
                # Looks like a UUID
                project = await asyncio.to_thread(
                    Project.objects.select_related('owner').get,
                    project_id=project_id
                )
            else:
                # Looks like a database ID
                project = await asyncio.to_thread(
                    Project.objects.select_related('owner').get,
                    id=project_id
                )
            user = project.owner
            logger.info(f"Retrieved user {user.id} from project {project_id}")
        except Exception as e:
            logger.warning(f"Could not get user/project from project_id {project_id}: {e}")
    
    # Determine which model/provider to use for this user
    selected_model = await _get_selected_model_for_user(user)
    provider = AIProvider.get_provider(None, selected_model, user, conversation, project)
    
    # Collect the streaming response
    full_content = ""
    tool_calls = []
    has_500_error = False

    try:
        async for chunk in provider.generate_stream(messages, project_id, conversation_id, tools):
            # Check for error markers
            if isinstance(chunk, str) and "__ERROR_500__" in chunk:
                has_500_error = True
                continue
            # Skip notification chunks
            if isinstance(chunk, str) and ("__NOTIFICATION__" in chunk):
                continue
            full_content += chunk

        # Note: The provider.generate_stream already handles tool calls internally
        # and executes them. The tool calls are not returned in the stream,
        # they are executed automatically within the stream processing.

        return {
            "content": full_content,
            "tool_calls": tool_calls,  # Will be empty since tools are auto-executed
            "error": has_500_error,
            "error_message": "Anthropic API returned 500 Internal Server Error" if has_500_error else None
        }
        
    except Exception as e:
        logger.error(f"Error in get_ai_response: {str(e)}")
        return {
            "content": f"Error generating AI response: {str(e)}",
            "tool_calls": [],
            "error": True,
            "error_message": str(e)
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
