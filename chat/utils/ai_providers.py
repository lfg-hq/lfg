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
from projects.utils.app_functions import app_functions
from chat.models import AgentRole, ModelSelection
from projects.models import Project
import traceback # Import traceback for better error logging

# Set up logger
logger = logging.getLogger(__name__)

class AIProvider:
    """Base class for AI providers"""
    
    @staticmethod
    def get_provider(provider_name, selected_model):
        """Factory method to get the appropriate provider"""
        providers = {
            'openai': lambda: OpenAIProvider(selected_model),
        }
        provider_factory = providers.get(provider_name)
        if provider_factory:
            return provider_factory()
        else:
            return OpenAIProvider(selected_model)  # Default fallback
    
    async def generate_stream(self, messages, project_id, conversation_id, tools):
        """Generate streaming response from the AI provider"""
        raise NotImplementedError("Subclasses must implement this method")


class OpenAIProvider(AIProvider):
    """OpenAI provider implementation"""
    
    def __init__(self, selected_model):

        logger.debug(f"Selected model: {selected_model}")

        openai_api_key = os.getenv('OPENAI_API_KEY') 
        anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')

        if selected_model == "gpt_4o":
            self.model = "gpt-4o"
            self.client = openai.OpenAI(api_key=openai_api_key)
        elif selected_model == "gpt_4.1":
            self.model = "gpt-4.1"
            self.client = openai.OpenAI(api_key=openai_api_key)
        elif selected_model == "claude_4_sonnet":
            self.model = "claude-sonnet-4-20250514"
            logger.debug(f"Selected model: {self.model}")
            self.client = openai.OpenAI(api_key=anthropic_api_key, base_url="https://api.anthropic.com/v1/")


    async def generate_stream(self, messages, project_id, conversation_id, tools):
        current_messages = list(messages) # Work on a copy

        while True: # Loop to handle potential multi-turn tool calls (though typically one round)
            try:
                params = {
                    "model": self.model,
                    "messages": current_messages,
                    "stream": True,
                    "tool_choice": "auto", 
                    "tools": tools
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
                
                # --- Process the stream from the API --- 
                # We need to wrap the stream iteration in a thread as well
                async for chunk in self._process_stream_async(response_stream):
                    delta = chunk.choices[0].delta if chunk.choices else None
                    finish_reason = chunk.choices[0].finish_reason if chunk.choices else None

                    if not delta: continue # Skip empty chunks

                    # --- Accumulate Text Content --- 
                    if delta.content:
                        yield delta.content # Stream text content immediately
                        if full_assistant_message["content"] is None:
                            full_assistant_message["content"] = "-"
                        full_assistant_message["content"] += delta.content

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
                                    notification_type = None
                                    if function_name == "extract_features":
                                        notification_type = "features"
                                    elif function_name == "extract_personas":
                                        notification_type = "personas"
                                    elif function_name == "start_server":
                                        notification_type = "start_server"
                                    elif function_name == "execute_command":
                                        notification_type = "execute_command"
                                    
                                    # Send early notification if it's an extraction function
                                    if notification_type:
                                        logger.debug(f"SENDING EARLY NOTIFICATION FOR {function_name}")
                                        # Create a notification with a special marker to make it clearly identifiable
                                        early_notification = {
                                            "is_notification": True,
                                            "notification_type": notification_type,
                                            "early_notification": True,
                                            "function_name": function_name,
                                            "notification_marker": "__NOTIFICATION__"  # Special marker
                                        }
                                        notification_json = json.dumps(early_notification)
                                        logger.debug(f"Early notification sent: {notification_json}")
                                        # Yield as a special formatted string that can be easily detected
                                        yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                                
                                if tool_call_chunk.function.arguments:
                                    current_tc["function"]["arguments"] += tool_call_chunk.function.arguments

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
                                
                                logger.debug(f"Executing Tool: {tool_call_name} (ID: {tool_call_id})")
                                logger.debug(f"Raw Args: {tool_call_args_str}")
                                
                                result_content = ""
                                notification_data = None
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
                                            
                                            # Format the explanation nicely with markdown
                                            formatted_explanation = f"\n\n{explanation}\n\n"
                                            
                                            # Add to the assistant message content
                                            if full_assistant_message.get("content", None) is None:
                                                logger.debug(f"Setting content to: {formatted_explanation}")
                                                full_assistant_message["content"] = formatted_explanation
                                            else:
                                                full_assistant_message["content"] += formatted_explanation
                                            
                                            # Yield the explanation immediately so it streams to the frontend
                                            yield "*"
                                    # Log the function call with clean arguments
                                    logger.debug(f"Calling app_functions with {tool_call_name}, {parsed_args}, {project_id}, {conversation_id}")
                                    
                                    # Execute the function with extensive logging and error handling
                                    # Run the potentially blocking app_functions in a thread
                                    try:
                                        tool_result = await asyncio.to_thread(
                                            app_functions, tool_call_name, parsed_args, project_id, conversation_id
                                        )
                                        logger.debug(f"app_functions call successful for {tool_call_name}")
                                    except Exception as func_error:
                                        logger.error(f"Error calling app_functions: {str(func_error)}")
                                        logger.error(f"Traceback: {traceback.format_exc()}")
                                        # Rethrow to be caught by the outer try-except
                                        raise

                                    logger.debug(f"Tool Result: {tool_result}")
                                    
                                    # Send special notification for extraction functions regardless of result
                                    if tool_call_name in ["extract_features", "extract_personas"]:
                                        notification_type = "features" if tool_call_name == "extract_features" else "personas"
                                        logger.debug(f"FORCING NOTIFICATION FOR {tool_call_name}")
                                        notification_data = {
                                            "is_notification": True,
                                            "notification_type": notification_type,
                                            "function_name": tool_call_name,
                                            "notification_marker": "__NOTIFICATION__"
                                        }
                                        logger.debug(f"Forced notification: {notification_data}")
                                    
                                    # Handle the case where tool_result is None
                                    if tool_result is None:
                                        result_content = "The function returned no result."
                                    # Handle the case where tool_result is a dict with notification data
                                    elif isinstance(tool_result, dict) and tool_result.get("is_notification") is True:
                                        # Set notification data to be yielded later
                                        logger.debug("NOTIFICATION DATA CREATED IN OPENAI PROVIDER")
                                        logger.debug(f"Tool result: {tool_result}")
                                        
                                        notification_data = {
                                            "is_notification": True,
                                            "notification_type": tool_result.get("notification_type", "features"),
                                            "notification_marker": "__NOTIFICATION__"  # Special marker
                                        }
                                        
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
                                
                                # Append tool result message
                                tool_results_messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call_id,
                                    "content": f"Tool call {tool_call_name}() completed. {result_content}."
                                })
                                
                                # If we have notification data, yield it to the consumer with the special format
                                if notification_data:
                                    logger.debug("YIELDING NOTIFICATION DATA TO CONSUMER")
                                    notification_json = json.dumps(notification_data)
                                    logger.debug(f"Notification JSON: {notification_json}")
                                    yield f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
                                
                            current_messages.extend(tool_results_messages) # Add tool results
                            # Continue the outer while loop to make the next API call
                            break # Break inner chunk loop
                        
                        elif finish_reason == "stop":
                            # Conversation finished naturally
                            return # Exit the generator completely
                        else:
                            # Handle other finish reasons if necessary (e.g., length, content_filter)
                            logger.warning(f"Unhandled finish reason: {finish_reason}")
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