import os
import json
import openai
import requests
import anthropic
import logging
import asyncio
from django.conf import settings
from google import genai
from google.genai.types import (
    FunctionDeclaration,
    GenerateContentConfig,
    HttpOptions,
    Tool,
)
from asgiref.sync import sync_to_async
from coding.utils.ai_functions import app_functions
from chat.models import AgentRole, ModelSelection, Conversation
from projects.models import Project, ToolCallHistory
from accounts.models import TokenUsage, Profile
from django.contrib.auth.models import User
import traceback # Import traceback for better error logging
from channels.db import database_sync_to_async
from coding.utils.ai_tools import tools_ticket

# Set up logger
logger = logging.getLogger(__name__)

# Maximum tool output size (50KB)
MAX_TOOL_OUTPUT_SIZE = 50 * 1024


def get_notification_type_for_tool(tool_name):
    """
    Determine the notification type based on the tool/function name.
    
    Args:
        tool_name: The name of the tool/function being called
        
    Returns:
        str or None: The notification type if the tool should trigger a notification, None otherwise
    """

    print(f"\n\\n\n\n\n\nGetting notification type for tool: {tool_name}")
    
    notification_mappings = {
        "extract_features": "checklist",  # Features tab is commented out, use checklist
        "extract_personas": "checklist",  # Personas tab is commented out, use checklist
        "save_features": "checklist",
        "save_personas": "checklist",
        "get_features": "checklist",
        "get_personas": "checklist",
        "create_prd": "prd",
        "get_prd": "prd",
        "stream_implementation_content": "implementation_stream",  # Stream implementation content to implementation tab
        "stream_prd_content": "prd_stream",  # Stream PRD content to PRD tab
        "start_server": "apps",  # Server starts should show in apps/preview tab
        "execute_command": "toolhistory",  # Show command execution in tool history
        "save_implementation": "implementation",
        "get_implementation": "implementation",
        "update_implementation": "implementation",
        "create_implementation": "implementation",
        "design_schema": "implementation",  # Design tab is commented out, use implementation
        "generate_tickets": "checklist",  # Tickets tab is commented out, use checklist
        "checklist_tickets": "checklist",
        "create_tickets": "checklist",  # Add this mapping
        "update_ticket": "checklist",
        "get_next_ticket": "checklist",
        "get_pending_tickets": "checklist",  # Add this mapping
        "implement_ticket": "implementation",  # Implementation tasks go to implementation tab
        "save_project_name": "toolhistory",  # Project name saving goes to tool history
        "get_project_name": "toolhistory"  # Project name retrieval goes to tool history
    }
    
    # Default to toolhistory if no specific mapping exists
    return notification_mappings.get(tool_name, "toolhistory")

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
        print(f"\n\n\n\n\nNotification type: {notification_type}")
        
        # For stream_prd_content and stream_implementation_content, skip forcing notification if it already has notification data
        if tool_call_name in ["stream_prd_content", "stream_implementation_content"] and isinstance(tool_result, dict) and tool_result.get("is_notification"):
            # Use the notification data from the tool result itself
            logger.info(f"{tool_call_name} already has notification data, not forcing")
        elif notification_type and tool_call_name in [
            "extract_features", "extract_personas", "save_features", "save_personas",
            "get_features", "get_personas", "create_prd", "get_prd",
            "save_implementation", "get_implementation", "update_implementation", "create_implementation",
            "execute_command", "start_server", "design_schema", "generate_tickets",
            "checklist_tickets", "update_ticket", "get_next_ticket", "implement_ticket",
            "save_project_name", "get_project_name"  # Add project name functions
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
                logger.info(f"PRD_STREAM in notification handler: chunk_length={len(notification_data['content_chunk'])}, is_complete={notification_data['is_complete']}")
            elif raw_notification_type == "implementation_stream":
                notification_data["content_chunk"] = tool_result.get("content_chunk", "")
                notification_data["is_complete"] = tool_result.get("is_complete", False)
                logger.info(f"IMPLEMENTATION_STREAM in notification handler: chunk_length={len(notification_data['content_chunk'])}, is_complete={notification_data['is_complete']}")
            
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
        print(f"\n\n\nCreating provider with provider_name: {provider_name}, selected_model: {selected_model}, user: {user}")
        providers = {
            'openai': lambda: OpenAIProvider(selected_model, user, conversation, project),
            'anthropic': lambda: AnthropicProvider(selected_model, user, conversation, project),
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
        # self.openai_api_key = os.getenv('OPENAI_API_KEY', '')

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

        print(f"\n\n\nSelected model: {self.model}")
        
        # Client will be initialized in async method
        self.client = None
    
    @database_sync_to_async
    def _get_openai_key(self, user):
        """Get user profile synchronously"""
        profile = Profile.objects.get(user=user)
        if profile.openai_api_key:
            return profile.openai_api_key
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


    async def generate_stream(self, messages, project_id, conversation_id, tools):
        # Ensure client is initialized with API keys
        await self._ensure_client()
        
        # Check if client is initialized
        if not self.client:
            yield "Error: No OpenAI API key configured. Please add API key here http://localhost:8000/accounts/integrations/."
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

        prd_data = ""
        implementation_data = ""
        ticket_data = ""  # Buffer for current ticket being parsed
        current_mode = ""
        buffer = ""  # Buffer to handle split tags

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
                # Add detailed logging of the messages before the call
                # try:
                #     logger.debug(f"Messages content:\n{json.dumps(current_messages, indent=2)}")
                # except Exception as log_e:
                #     logger.error(f"Error logging messages: {log_e}") # Handle potential logging errors
                
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
                
                # Output buffer to handle incomplete tags
                output_buffer = ""
                
                # --- Process the stream from the API --- 
                # We need to wrap the stream iteration in a thread as well
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
                        
                        # Add to buffer for tag detection
                        buffer += text
                        
                        # Check for complete tags in buffer
                        if "<lfg-prd>" in buffer and current_mode != "prd":
                            current_mode = "prd"
                            print("\n\n[PRD MODE ACTIVATED - OpenAI]")
                            # Clear buffer up to and including the tag
                            tag_pos = buffer.find("<lfg-prd>")
                            remaining_buffer = buffer[tag_pos + len("<lfg-prd>"):]
                            # Clean any leading '>' and whitespace from remaining buffer
                            remaining_buffer = remaining_buffer.lstrip()
                            if remaining_buffer.startswith('>'):
                                remaining_buffer = remaining_buffer[1:].lstrip()
                            # Reset prd data and capture any remaining content
                            prd_data = remaining_buffer
                            buffer = ""  # Clear the buffer since we've processed it
                            
                            # Show loading indicator in chat
                            yield "\n\n*Generating PRD... (check the PRD tab for live updates)*\n\n"
                        
                        if "</lfg-prd>" in buffer and current_mode == "prd":
                            current_mode = ""
                            print("\n\n[PRD MODE DEACTIVATED - OpenAI]")
                            # Find where the closing tag starts in the buffer
                            tag_pos = buffer.find("</lfg-prd>")
                            # Check if we've captured part of the closing tag in prd_data
                            # by looking for incomplete tag patterns at the end
                            incomplete_patterns = ["<", "</", "</l", "</lf", "</lfg", "</lfg-", "</lfg-p", "</lfg-pr", "</lfg-prd"]
                            for pattern in reversed(incomplete_patterns):
                                if prd_data.endswith(pattern):
                                    prd_data = prd_data[:-len(pattern)]
                                    break
                            # Clear buffer up to and including the tag
                            buffer = buffer[tag_pos + len("</lfg-prd>"):]
                            
                            # Send completion notification for PRD stream
                            prd_complete_notification = {
                                "is_notification": True,
                                "notification_type": "prd_stream",
                                "content_chunk": "",
                                "is_complete": True,
                                "notification_marker": "__NOTIFICATION__"
                            }
                            notification_json = json.dumps(prd_complete_notification)
                            yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                        
                        if "<lfg-plan>" in buffer and current_mode != "implementation":
                            current_mode = "implementation"
                            print("\n\n[IMPLEMENTATION MODE ACTIVATED - OpenAI]")
                            # Clear buffer up to and including the tag
                            tag_pos = buffer.find("<lfg-plan>")
                            remaining_buffer = buffer[tag_pos + len("<lfg-plan>"):]
                            # Clean any leading '>' and whitespace from remaining buffer
                            remaining_buffer = remaining_buffer.lstrip()
                            if remaining_buffer.startswith('>'):
                                remaining_buffer = remaining_buffer[1:].lstrip()
                            # Reset implementation data and capture any remaining content
                            implementation_data = remaining_buffer
                            buffer = ""  # Clear the buffer since we've processed it
                            
                            # Show loading indicator in chat
                            yield "\n\n*Generating implementation plan... (check the Implementation tab for live updates)*\n\n"
                        
                        if "</lfg-plan>" in buffer and current_mode == "implementation":
                            current_mode = ""
                            print("\n\n[IMPLEMENTATION MODE DEACTIVATED - OpenAI]")
                            # Find where the closing tag starts in the buffer
                            tag_pos = buffer.find("</lfg-plan>")
                            # Check if we've captured part of the closing tag in implementation_data
                            # by looking for incomplete tag patterns at the end
                            incomplete_patterns = ["<", "</", "</l", "</lf", "</lfg", "</lfg-", "</lfg-p", "</lfg-pl", "</lfg-pla", "</lfg-plan"]
                            for pattern in reversed(incomplete_patterns):
                                if implementation_data.endswith(pattern):
                                    implementation_data = implementation_data[:-len(pattern)]
                                    break
                            # Clear buffer up to and including the tag
                            buffer = buffer[tag_pos + len("</lfg-plan>"):]
                            
                            # Send completion notification for implementation stream
                            implementation_complete_notification = {
                                "is_notification": True,
                                "notification_type": "implementation_stream",
                                "content_chunk": "",
                                "is_complete": True,
                                "notification_marker": "__NOTIFICATION__"
                            }
                            notification_json = json.dumps(implementation_complete_notification)
                            yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                        
                        # Check for ticket tags
                        if "<lfg-ticket>" in buffer and current_mode != "ticket":
                            current_mode = "ticket"
                            print("\n\n[TICKET MODE ACTIVATED - OpenAI]")
                            # Clear buffer up to and including the tag
                            tag_pos = buffer.find("<lfg-ticket>")
                            remaining_buffer = buffer[tag_pos + len("<lfg-ticket>"):]
                            # Clean any leading '>' and whitespace from remaining buffer
                            remaining_buffer = remaining_buffer.lstrip()
                            if remaining_buffer.startswith('>'):
                                remaining_buffer = remaining_buffer[1:].lstrip()
                            # Reset ticket data and capture any remaining content
                            ticket_data = remaining_buffer
                            buffer = ""  # Clear the buffer since we've processed it
                        
                        if "</lfg-ticket>" in buffer and current_mode == "ticket":
                            current_mode = ""
                            print("\n\n[TICKET MODE DEACTIVATED - OpenAI]")
                            # Find where the closing tag starts in the buffer
                            tag_pos = buffer.find("</lfg-ticket>")
                            # Check if we've captured part of the closing tag in ticket_data
                            # by looking for incomplete tag patterns at the end
                            incomplete_patterns = ["<", "</", "</l", "</lf", "</lfg", "</lfg-", "</lfg-t", "</lfg-ti", "</lfg-tic", "</lfg-tick", "</lfg-ticke", "</lfg-ticket"]
                            for pattern in reversed(incomplete_patterns):
                                if ticket_data.endswith(pattern):
                                    ticket_data = ticket_data[:-len(pattern)]
                                    break
                            # Clear buffer up to and including the tag
                            buffer = buffer[tag_pos + len("</lfg-ticket>"):]
                            
                            # Parse and save the ticket
                            try:
                                # Import the save function
                                from coding.utils.ai_functions import save_ticket_from_stream
                                
                                # Clean ticket data before parsing
                                cleaned_ticket_data = ticket_data.strip()
                                # Remove any leading '>' that might have slipped through
                                if cleaned_ticket_data.startswith('>'):
                                    cleaned_ticket_data = cleaned_ticket_data[1:].strip()
                                
                                # Parse the JSON ticket data
                                ticket_json = json.loads(cleaned_ticket_data)
                                
                                # Save the ticket to database
                                save_result = await save_ticket_from_stream(ticket_json, project_id)
                                logger.info(f"OpenAI Ticket save result: {save_result}")
                                
                                # Yield notification if save was successful
                                if save_result.get("is_notification"):
                                    notification_json = json.dumps(save_result)
                                    yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                            except json.JSONDecodeError as e:
                                logger.error(f"Error parsing ticket JSON from OpenAI stream: {str(e)}")
                                logger.error(f"Ticket data was: {ticket_data}")
                            except Exception as e:
                                logger.error(f"Error saving ticket from OpenAI stream: {str(e)}")
                        
                        # Keep buffer size reasonable (only need enough for tag detection)
                        if len(buffer) > 100 and "<lfg-prd" not in buffer and "</lfg-prd" not in buffer and "<lfg-plan" not in buffer and "</lfg-plan" not in buffer and "<lfg-ticket" not in buffer and "</lfg-ticket" not in buffer:
                            buffer = buffer[-50:]  # Keep last 50 chars
                        
                        if current_mode == "prd":
                            # Skip the closing '>' of the tag if it's the first character and prd_data is empty
                            if prd_data == "" and text.startswith('>'):
                                text = text[1:]
                            prd_data += text
                            print(f"\n\n\n[CAPTURING PRD DATA - OpenAI]: {text}")
                            
                            # Stream PRD content to the panel
                            prd_stream_notification = {
                                "is_notification": True,
                                "notification_type": "prd_stream",
                                "content_chunk": text,
                                "is_complete": False,
                                "notification_marker": "__NOTIFICATION__"
                            }
                            notification_json = json.dumps(prd_stream_notification)
                            yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                        elif current_mode == "implementation":
                            # Skip the closing '>' of the tag if it's the first character and implementation_data is empty
                            if implementation_data == "" and text.startswith('>'):
                                text = text[1:]
                            implementation_data += text
                            # print(f"\n\n\n[CAPTURING IMPLEMENTATION DATA - OpenAI]: {text}")
                            
                            # Stream implementation content to the panel
                            implementation_stream_notification = {
                                "is_notification": True,
                                "notification_type": "implementation_stream",
                                "content_chunk": text,
                                "is_complete": False,
                                "notification_marker": "__NOTIFICATION__"
                            }
                            notification_json = json.dumps(implementation_stream_notification)
                            yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                        elif current_mode == "ticket":
                            # Skip the closing '>' of the tag if it's the first character and ticket_data is empty
                            if ticket_data == "" and text.startswith('>'):
                                text = text[1:]
                                print(f"[SKIPPING '>' - OpenAI] Remaining text: {repr(text)}")
                            # Also check if ticket_data only contains whitespace and we're getting '>'
                            elif ticket_data.strip() == "" and text.strip().startswith('>'):
                                text = text.lstrip()
                                if text.startswith('>'):
                                    text = text[1:]
                                print(f"[SKIPPING '>' after whitespace - OpenAI] Remaining text: {repr(text)}")
                            ticket_data += text
                            print(f"\n\n\n[CAPTURING TICKET DATA - OpenAI]: {repr(text)}")
                            print(f"[TICKET DATA SO FAR - OpenAI]: {repr(ticket_data[:100])}...")
                        
                        # Handle buffering to prevent incomplete tags from being sent
                        if current_mode not in ["prd", "implementation", "ticket"]:
                            # Add text to output buffer
                            output_buffer += text
                            
                            # Check if we have a complete tag or potential incomplete tag
                            # Look for potential start of PRD, implementation, or ticket tag
                            if any(output_buffer.endswith(prefix) for prefix in ['<', '<l', '<lf', '<lfg', '<lfg-', '<lfg-p', '<lfg-pr', '<lfg-prd', '<lfg-pl', '<lfg-pla', '<lfg-plan', '<lfg-t', '<lfg-ti', '<lfg-tic', '<lfg-tick', '<lfg-ticke', '<lfg-ticket']):
                                # Hold back - might be incomplete tag
                                pass
                            else:
                                # Safe to yield everything in buffer
                                if output_buffer:
                                    yield output_buffer
                                    output_buffer = ""
                            
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
                                    
                                    # Skip early notification for stream_prd_content and stream_implementation_content since we need the actual content
                                    if function_name not in ["stream_prd_content", "stream_implementation_content"]:
                                        # Send early notification for other functions
                                        logger.debug(f"SENDING EARLY NOTIFICATION FOR {function_name}")
                                        # Create a notification with a special marker to make it clearly identifiable
                                        early_notification = {
                                            "is_notification": True,
                                            "notification_type": notification_type or "tool",
                                            "early_notification": True,
                                            "function_name": function_name,
                                            "notification_marker": "__NOTIFICATION__"  # Special marker
                                        }
                                        notification_json = json.dumps(early_notification)
                                        logger.debug(f"Early notification sent: {notification_json}")
                                        # Yield as a special formatted string that can be easily detected
                                        yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                                    else:
                                        logger.debug(f"Skipping early notification for {function_name} - will send with content later")
                                
                                if tool_call_chunk.function.arguments:
                                    current_tc["function"]["arguments"] += tool_call_chunk.function.arguments
                                    # Stream create_prd arguments to console as they arrive
                                    if current_tc["function"]["name"] == "create_prd":
                                        logger.info(f"[OpenAI] create_prd argument chunk: {tool_call_chunk.function.arguments}")

                    # --- Check Finish Reason --- 
                    if finish_reason:
                        # Log the finish reason as soon as it's detected
                        logger.debug(f"Finish Reason Detected: {finish_reason}")
                        
                        if finish_reason == "tool_calls":
                            # ── 1. Final-ise tool_calls_requested ────────────────────────────
                            for tc in tool_calls_requested:
                                # If the model never emitted arguments (or only whitespace),
                                # replace the empty string with a valid empty-object JSON
                                if not tc["function"]["arguments"].strip():
                                    tc["function"]["arguments"] = "{}"

                            # ── 2. Build the assistant message ───────────────────────────────
                            full_assistant_message["tool_calls"] = tool_calls_requested

                            # Remove the content field if it was just tool calls
                            if full_assistant_message["content"] is None:
                                full_assistant_message.pop("content")

                            # ── 3. Append to the running conversation history ────────────────
                            current_messages.append(full_assistant_message)
                            
                            # --- Execute Tools and Prepare Next Call --- 
                            tool_results_messages = []
                            for tool_call_to_execute in tool_calls_requested:
                                tool_call_id = tool_call_to_execute["id"]
                                tool_call_name = tool_call_to_execute["function"]["name"]
                                tool_call_args_str = tool_call_to_execute["function"]["arguments"]
                                
                                logger.debug(f"OpenAI Provider - Tool Call ID: {tool_call_id}")
                                
                                # Log complete create_prd arguments before execution
                                if tool_call_name == "create_prd":
                                    logger.info(f"[OpenAI] Executing create_prd with complete arguments: {tool_call_args_str}")
                                
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
                                
                                # If we have notification data, yield it to the consumer with the special format
                                if notification_data:
                                    logger.debug("YIELDING NOTIFICATION DATA TO CONSUMER")
                                    logger.debug(f"Notification data type: {notification_data.get('notification_type')}")
                                    if notification_data.get('notification_type') == 'prd':
                                        logger.info(f"PRD STREAM NOTIFICATION: chunk_length={len(notification_data.get('content_chunk', ''))}, is_complete={notification_data.get('is_complete')}")
                                    notification_json = json.dumps(notification_data)
                                    logger.debug(f"Notification JSON: {notification_json}")
                                    yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                                
                            current_messages.extend(tool_results_messages) # Add tool results
                            # Continue the outer while loop to make the next API call
                            break # Break inner chunk loop
                        
                        elif finish_reason == "stop":
                            # Conversation finished naturally
                            
                            # Flush any remaining buffered output
                            if output_buffer and current_mode not in ["prd", "implementation", "ticket"]:
                                yield output_buffer
                                output_buffer = ""
                            
                            # Save captured PRD data if available
                            if prd_data and project_id:
                                print(f"\n\n[FINAL PRD DATA CAPTURED - OpenAI]:\n{prd_data}\n")
                                print(f"[PRD DATA LENGTH - OpenAI]: {len(prd_data)} characters")
                                
                                # Import the save function
                                from coding.utils.ai_functions import save_prd_from_stream
                                
                                # Save the PRD to database
                                try:
                                    save_result = await save_prd_from_stream(prd_data, project_id)
                                    logger.info(f"OpenAI PRD save result: {save_result}")
                                    
                                    # Yield notification if save was successful
                                    if save_result.get("is_notification"):
                                        notification_json = json.dumps(save_result)
                                        yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                                except Exception as e:
                                    logger.error(f"Error saving PRD from OpenAI stream: {str(e)}")
                            
                            # Save captured implementation data if available
                            if implementation_data and project_id:
                                print(f"\n\n[FINAL IMPLEMENTATION DATA CAPTURED - OpenAI]:\n{implementation_data}\n")
                                print(f"[IMPLEMENTATION DATA LENGTH - OpenAI]: {len(implementation_data)} characters")
                                
                                # Import the save function
                                from coding.utils.ai_functions import save_implementation_from_stream
                                
                                # Save the implementation to database
                                try:
                                    save_result = await save_implementation_from_stream(implementation_data, project_id)
                                    logger.info(f"OpenAI Implementation save result: {save_result}")
                                    
                                    # Yield notification if save was successful
                                    if save_result.get("is_notification"):
                                        notification_json = json.dumps(save_result)
                                        yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                                except Exception as e:
                                    logger.error(f"Error saving implementation from OpenAI stream: {str(e)}")
                            
                            # Track token usage before exiting
                            if usage_data and user:
                                await self._track_token_usage(
                                    user, project, conversation, usage_data
                                )
                            return # Exit the generator completely
                        else:
                            # Handle other finish reasons if necessary (e.g., length, content_filter)
                            logger.warning(f"Unhandled finish reason: {finish_reason}")
                            # Track token usage before exiting
                            if usage_data and user:
                                await self._track_token_usage(
                                    user, project, conversation, usage_data
                                )
                            return # Exit generator
                
                # If the inner loop finished because of tool_calls, the outer loop continues
                if finish_reason == "tool_calls":
                    continue # Go to next iteration of the while True loop for the next API call
                else:
                     # If the loop finished without a finish_reason (shouldn't happen with stream=True)
                     # or if finish_reason was something else unexpected that didn't return/continue
                     logger.warning("Stream ended unexpectedly.")
                     return # Exit generator

            except Exception as e:
                logger.error(f"Critical Error: {str(e)}\n{traceback.format_exc()}")
                yield f"Error with OpenAI stream: {str(e)}"
                return # Exit generator on critical error


    async def _process_stream_async(self, response_stream):
        """
        Process the response stream asynchronously by yielding control back to event loop
        """
        for chunk in response_stream:
            yield chunk
            # Yield control back to the event loop periodically
            await asyncio.sleep(0)
    
    async def _track_token_usage(self, user, project, conversation, usage_data):
        """Track token usage in the database"""
        try:
            # Determine provider based on the client base URL
            provider = 'openai'
            if hasattr(self.client, 'base_url') and 'anthropic' in str(self.client.base_url):
                provider = 'anthropic'
            
            # Create token usage record
            token_usage = TokenUsage(
                user=user,
                project=project,
                conversation=conversation,
                provider=provider,
                model=self.model,
                input_tokens=getattr(usage_data, 'prompt_tokens', 0),
                output_tokens=getattr(usage_data, 'completion_tokens', 0),
                total_tokens=getattr(usage_data, 'total_tokens', 0)
            )
            
            # Calculate cost
            token_usage.calculate_cost()
            
            # Save asynchronously
            await asyncio.to_thread(token_usage.save)
            
            logger.debug(f"Token usage tracked: {token_usage}")
            
        except Exception as e:
            logger.error(f"Error tracking token usage: {e}")


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

        print(f"\n\n\nUser: {user}")
        
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
        profile = Profile.objects.get(user=user)
        if profile.anthropic_api_key:
            return profile.anthropic_api_key
        return ""

    async def _ensure_client(self):
        """Ensure the client is initialized with API key"""
        print(f"\n\n\nEnsuring client is initialized with API key for user: {self.user}")
        
        # Try to fetch API key from user profile if available and not already set
        if self.user:
            try:
                print(f"\n\n\nUser exists: {self.user} (ID: {self.user.id})")
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
        
        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                claude_tool = {
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object", "properties": {}, "required": []})
                }
                claude_tools.append(claude_tool)
                
                # Log implementation-related tools
                if func["name"] in ["save_implementation", "get_implementation"]:
                    logger.debug(f"[AnthropicProvider] Added {func['name']} to Claude tools with description: {func.get('description', '')[:100]}...")
        
        return claude_tools

    async def generate_stream(self, messages, project_id, conversation_id, tools):
        # Ensure client is initialized with API key
        print(f"\n\n\nGenerating stream for user ")
        await self._ensure_client()
        
        # Check if client is initialized
        if not self.client:
            yield "Error: No Anthropic API key configured. Please add API key here http://localhost:8000/accounts/integrations/."
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
            
        prd_data = ""
        implementation_data = ""
        ticket_data = ""  # Buffer for current ticket being parsed
        current_mode = ""
        buffer = ""  # Buffer to handle split tags

        while True: # Loop to handle potential multi-turn tool calls
            try:
                # Convert messages and tools to Claude format
                claude_messages = self._convert_messages_to_claude_format(current_messages)
                claude_tools = self._convert_tools_to_claude_format(tools)

                # Add web search tool using the correct format
                web_search_tool = {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": 5  # Optional: limit number of searches per request
                }
                claude_tools.append(web_search_tool)
                logger.info("Added web_search_20250305 tool to Claude tools")
                
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
                                print(f"\n\n\nEvent delta: {event.delta}")
                                # Stream text content
                                text = event.delta.text
                                
                                # Add to buffer for tag detection
                                buffer += text
                                
                                # Check for complete tags in buffer
                                if "<lfg-prd>" in buffer and current_mode != "prd":
                                    current_mode = "prd"
                                    print("\n\n[PRD MODE ACTIVATED]")
                                    # Clear buffer up to and including the tag
                                    tag_pos = buffer.find("<lfg-prd>")
                                    remaining_buffer = buffer[tag_pos + len("<lfg-prd>"):]
                                    # Clean any leading '>' and whitespace from remaining buffer
                                    remaining_buffer = remaining_buffer.lstrip()
                                    if remaining_buffer.startswith('>'):
                                        remaining_buffer = remaining_buffer[1:].lstrip()
                                    # Reset prd data and capture any remaining content
                                    prd_data = remaining_buffer
                                    buffer = ""  # Clear the buffer since we've processed it
                                    
                                    # Show loading indicator in chat
                                    yield "\n\n*Generating PRD... (check the PRD tab for live updates)*\n\n"
                                
                                if "</lfg-prd>" in buffer and current_mode == "prd":
                                    current_mode = ""
                                    print("\n\n[PRD MODE DEACTIVATED]")
                                    # Find where the closing tag starts in the buffer
                                    tag_pos = buffer.find("</lfg-prd>")
                                    # Check if we've captured part of the closing tag in prd_data
                                    # by looking for incomplete tag patterns at the end
                                    incomplete_patterns = ["<", "</", "</l", "</lf", "</lfg", "</lfg-", "</lfg-p", "</lfg-pr", "</lfg-prd"]
                                    for pattern in reversed(incomplete_patterns):
                                        if prd_data.endswith(pattern):
                                            prd_data = prd_data[:-len(pattern)]
                                            break
                                    # Clear buffer up to and including the tag
                                    buffer = buffer[tag_pos + len("</lfg-prd>"):]
                                    
                                    # Send completion notification for PRD stream
                                    prd_complete_notification = {
                                        "is_notification": True,
                                        "notification_type": "prd_stream",
                                        "content_chunk": "",
                                        "is_complete": True,
                                        "notification_marker": "__NOTIFICATION__"
                                    }
                                    notification_json = json.dumps(prd_complete_notification)
                                    yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                                
                                if "<lfg-plan>" in buffer and current_mode != "implementation":
                                    current_mode = "implementation"
                                    print("\n\n[IMPLEMENTATION MODE ACTIVATED]")
                                    # Clear buffer up to and including the tag
                                    tag_pos = buffer.find("<lfg-plan>")
                                    remaining_buffer = buffer[tag_pos + len("<lfg-plan>"):]
                                    # Clean any leading '>' and whitespace from remaining buffer
                                    remaining_buffer = remaining_buffer.lstrip()
                                    if remaining_buffer.startswith('>'):
                                        remaining_buffer = remaining_buffer[1:].lstrip()
                                    # Reset implementation data and capture any remaining content
                                    implementation_data = remaining_buffer
                                    buffer = ""  # Clear the buffer since we've processed it
                                    
                                    # Show loading indicator in chat
                                    yield "\n\n*Generating implementation plan... (check the Implementation tab for live updates)*\n\n"
                                
                                if "</lfg-plan>" in buffer and current_mode == "implementation":
                                    current_mode = ""
                                    print("\n\n[IMPLEMENTATION MODE DEACTIVATED]")
                                    # Find where the closing tag starts in the buffer
                                    tag_pos = buffer.find("</lfg-plan>")
                                    # Check if we've captured part of the closing tag in implementation_data
                                    # by looking for incomplete tag patterns at the end
                                    incomplete_patterns = ["<", "</", "</l", "</lf", "</lfg", "</lfg-", "</lfg-p", "</lfg-pl", "</lfg-pla", "</lfg-plan"]
                                    for pattern in reversed(incomplete_patterns):
                                        if implementation_data.endswith(pattern):
                                            implementation_data = implementation_data[:-len(pattern)]
                                            break
                                    # Clear buffer up to and including the tag
                                    buffer = buffer[tag_pos + len("</lfg-plan>"):]
                                    
                                    # Send completion notification for implementation stream
                                    implementation_complete_notification = {
                                        "is_notification": True,
                                        "notification_type": "implementation_stream",
                                        "content_chunk": "",
                                        "is_complete": True,
                                        "notification_marker": "__NOTIFICATION__"
                                    }
                                    notification_json = json.dumps(implementation_complete_notification)
                                    yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                                
                                # Check for ticket tags
                                if "<lfg-ticket>" in buffer and current_mode != "ticket":
                                    current_mode = "ticket"
                                    print("\n\n[TICKET MODE ACTIVATED]")
                                    # Clear buffer up to and including the tag
                                    tag_pos = buffer.find("<lfg-ticket>")
                                    remaining_buffer = buffer[tag_pos + len("<lfg-ticket>"):]
                                    # Clean any leading '>' and whitespace from remaining buffer
                                    remaining_buffer = remaining_buffer.lstrip()
                                    if remaining_buffer.startswith('>'):
                                        remaining_buffer = remaining_buffer[1:].lstrip()
                                    # Reset ticket data and capture any remaining content
                                    ticket_data = remaining_buffer
                                    buffer = ""  # Clear the buffer since we've processed it
                                
                                if "</lfg-ticket>" in buffer and current_mode == "ticket":
                                    current_mode = ""
                                    print("\n\n[TICKET MODE DEACTIVATED]")
                                    # Find where the closing tag starts in the buffer
                                    tag_pos = buffer.find("</lfg-ticket>")
                                    # Check if we've captured part of the closing tag in ticket_data
                                    # by looking for incomplete tag patterns at the end
                                    incomplete_patterns = ["<", "</", "</l", "</lf", "</lfg", "</lfg-", "</lfg-t", "</lfg-ti", "</lfg-tic", "</lfg-tick", "</lfg-ticke", "</lfg-ticket"]
                                    for pattern in reversed(incomplete_patterns):
                                        if ticket_data.endswith(pattern):
                                            ticket_data = ticket_data[:-len(pattern)]
                                            break
                                    # Clear buffer up to and including the tag
                                    buffer = buffer[tag_pos + len("</lfg-ticket>"):]
                                    
                                    # Parse and save the ticket
                                    try:
                                        # Import the save function
                                        from coding.utils.ai_functions import save_ticket_from_stream
                                        
                                        # Clean ticket data before parsing
                                        cleaned_ticket_data = ticket_data.strip()
                                        # Remove any leading '>' that might have slipped through
                                        if cleaned_ticket_data.startswith('>'):
                                            cleaned_ticket_data = cleaned_ticket_data[1:].strip()
                                        
                                        # Parse the JSON ticket data
                                        ticket_json = json.loads(cleaned_ticket_data)
                                        
                                        # Save the ticket to database
                                        save_result = await save_ticket_from_stream(ticket_json, project_id)
                                        logger.info(f"Anthropic Ticket save result: {save_result}")
                                        
                                        # Yield notification if save was successful
                                        if save_result.get("is_notification"):
                                            notification_json = json.dumps(save_result)
                                            yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                                    except json.JSONDecodeError as e:
                                        logger.error(f"Error parsing ticket JSON from Anthropic stream: {str(e)}")
                                        logger.error(f"Ticket data was: {ticket_data}")
                                    except Exception as e:
                                        logger.error(f"Error saving ticket from Anthropic stream: {str(e)}")
                                
                                # Keep buffer size reasonable (only need enough for tag detection)
                                if len(buffer) > 100 and "<lfg-prd" not in buffer \
                                    and "</lfg-prd" not in buffer \
                                    and "<lfg-plan" not in buffer \
                                    and "</lfg-plan" not in buffer \
                                    and "<lfg-ticket" not in buffer \
                                    and "</lfg-ticket" not in buffer:
                                    buffer = buffer[-50:]  # Keep last 50 chars
                                
                                # print(f"\n\nCurrent mode: {current_mode}, Buffer tail: {buffer[-20:]}")
                                
                                if current_mode == "prd":
                                    # Skip the closing '>' of the tag if it's the first character and prd_data is empty
                                    if prd_data == "" and text.startswith('>'):
                                        text = text[1:]
                                    prd_data += text
                                    print(f"\n\n\n[CAPTURING PRD DATA]: {text}")
                                    
                                    # Stream PRD content to the panel
                                    prd_stream_notification = {
                                        "is_notification": True,
                                        "notification_type": "prd_stream",
                                        "content_chunk": text,
                                        "is_complete": False,
                                        "notification_marker": "__NOTIFICATION__"
                                    }
                                    notification_json = json.dumps(prd_stream_notification)
                                    yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                                elif current_mode == "implementation":
                                    # Skip the closing '>' of the tag if it's the first character and implementation_data is empty
                                    if implementation_data == "" and text.startswith('>'):
                                        text = text[1:]
                                    implementation_data += text
                                    print(f"\n\n\n[CAPTURING IMPLEMENTATION DATA]: {text}")
                                    
                                    # Stream implementation content to the panel
                                    implementation_stream_notification = {
                                        "is_notification": True,
                                        "notification_type": "implementation_stream",
                                        "content_chunk": text,
                                        "is_complete": False,
                                        "notification_marker": "__NOTIFICATION__"
                                    }
                                    notification_json = json.dumps(implementation_stream_notification)
                                    yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                                elif current_mode == "ticket":
                                    # Skip the closing '>' of the tag if it's the first character and ticket_data is empty
                                    if ticket_data == "" and text.startswith('>'):
                                        text = text[1:]
                                    ticket_data += text
                                    print(f"\n\n\n[CAPTURING TICKET DATA]: {text}")
                                
                                # Handle buffering to prevent incomplete tags from being sent
                                if current_mode not in ["prd", "implementation", "ticket"]:
                                    # Add text to output buffer
                                    output_buffer += text
                                    
                                    # Check if we have a complete tag or potential incomplete tag
                                    # Look for potential start of PRD, implementation, or ticket tag
                                    if any(output_buffer.endswith(prefix) for prefix in ['<', '<l', '<lf', '<lfg', '<lfg-', '<lfg-p', '<lfg-pr', '<lfg-prd', '<lfg-pl', '<lfg-pla', '<lfg-plan', '<lfg-t', '<lfg-ti', '<lfg-tic', '<lfg-tick', '<lfg-ticke', '<lfg-ticket']):
                                        # Hold back - might be incomplete tag
                                        pass
                                    else:
                                        # Safe to yield everything in buffer
                                        if output_buffer:
                                            yield output_buffer
                                            output_buffer = ""
                                    
                                if full_assistant_message["content"] is None:
                                    full_assistant_message["content"] = ""
                                full_assistant_message["content"] += text
                                
                                # Check if this might be web search results
                                if "search result" in text.lower() or "web search" in text.lower():
                                    logger.debug("Detected potential web search results in Claude's response")
                            elif event.delta.type == "input_json_delta":
                                # Accumulate tool arguments
                                if current_tool_use:
                                    print(f"\n\n\nCurrent tool use: {current_tool_use}")
                                    current_tool_args += event.delta.partial_json
                                    print(f"\n\n\nCurrent tool args: {current_tool_args}")
                                    # Stream create_prd arguments to console as they arrive
                                    if current_tool_use["function"]["name"] == "create_prd":
                                        print(f"[Anthropic] create_prd argument chunk: {event.delta.partial_json}")
                        
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
                                await self._track_token_usage(
                                    user, project, conversation, event.message.usage
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
                                
                                # Flush any remaining buffered output
                                if output_buffer and current_mode not in ["prd", "implementation", "ticket"]:
                                    yield output_buffer
                                    output_buffer = ""
                                
                                # Save captured PRD data if available
                                if prd_data and project_id:
                                    print(f"\n\n[FINAL PRD DATA CAPTURED]:\n{prd_data}\n")
                                    print(f"[PRD DATA LENGTH]: {len(prd_data)} characters")
                                    
                                    # Import the save function
                                    from coding.utils.ai_functions import save_prd_from_stream
                                    
                                    # Save the PRD to database
                                    try:
                                        save_result = await save_prd_from_stream(prd_data, project_id)
                                        logger.info(f"PRD save result: {save_result}")
                                        
                                        # Yield notification if save was successful
                                        if save_result.get("is_notification"):
                                            notification_json = json.dumps(save_result)
                                            yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                                    except Exception as e:
                                        logger.error(f"Error saving PRD from stream: {str(e)}")
                                
                                # Save captured implementation data if available
                                if implementation_data and project_id:
                                    print(f"\n\n[FINAL IMPLEMENTATION DATA CAPTURED]:\n{implementation_data}\n")
                                    print(f"[IMPLEMENTATION DATA LENGTH]: {len(implementation_data)} characters")
                                    
                                    # Import the save function
                                    from coding.utils.ai_functions import save_implementation_from_stream
                                    
                                    # Save the implementation to database
                                    try:
                                        save_result = await save_implementation_from_stream(implementation_data, project_id)
                                        logger.info(f"Implementation save result: {save_result}")
                                        
                                        # Yield notification if save was successful
                                        if save_result.get("is_notification"):
                                            notification_json = json.dumps(save_result)
                                            yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                                    except Exception as e:
                                        logger.error(f"Error saving implementation from stream: {str(e)}")
                                
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
    
    async def _track_token_usage(self, user, project, conversation, usage_data):
        """Track token usage in the database"""
        try:
            # Create token usage record for Anthropic
            token_usage = TokenUsage(
                user=user,
                project=project,
                conversation=conversation,
                provider='anthropic',
                model=self.model,
                input_tokens=getattr(usage_data, 'input_tokens', 0),
                output_tokens=getattr(usage_data, 'output_tokens', 0),
                total_tokens=getattr(usage_data, 'input_tokens', 0) + getattr(usage_data, 'output_tokens', 0)
            )
            
            # Calculate cost
            token_usage.calculate_cost()
            
            # Save asynchronously
            await asyncio.to_thread(token_usage.save)
            
            logger.debug(f"Anthropic token usage tracked: {token_usage}")
            
        except Exception as e:
            logger.error(f"Error tracking Anthropic token usage: {e}")