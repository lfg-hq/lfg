"""
Token usage tracking functionality for AI providers.
Extracted from ai_providers.py to separate concerns.
"""
import logging
import asyncio
import json
from typing import Optional, Any, Tuple
import tiktoken

from accounts.models import TokenUsage
from projects.models import Project
from chat.models import Conversation
from subscriptions.models import UserCredit
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


async def track_token_usage(
    user: User,
    project: Optional[Project],
    conversation: Optional[Conversation],
    usage_data: Any,
    provider: str,
    model: str
) -> None:
    """
    Track token usage in the database - common function for all providers
    
    Args:
        user: The user making the request
        project: The project context (optional)
        conversation: The conversation context (optional)
        usage_data: Provider-specific usage data object
        provider: The AI provider name ('openai', 'anthropic', 'xai')
        model: The specific model used
    """
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
        
        # Update user credit token usage
        try:
            user_credit, created = await asyncio.to_thread(
                UserCredit.objects.get_or_create,
                user=user
            )
            
            # Update total and monthly token usage
            user_credit.total_tokens_used += total_tokens
            
            # Track free vs paid tokens
            if user_credit.is_free_tier:
                user_credit.free_tokens_used += total_tokens
            else:
                user_credit.paid_tokens_used += total_tokens
                user_credit.monthly_tokens_used += total_tokens
            
            await asyncio.to_thread(user_credit.save)
            logger.debug(f"Updated user credit token usage: total={user_credit.total_tokens_used}, monthly={user_credit.monthly_tokens_used}")
            
        except Exception as e:
            logger.error(f"Error updating user credit token usage: {e}")
        
    except Exception as e:
        logger.error(f"Error tracking token usage: {e}")


class TokenEstimator:
    """Base class for token estimation across different providers"""
    
    def estimate_tokens(self, messages: list, model: str, output_text: Optional[str] = None) -> Tuple[Optional[int], Optional[int]]:
        """
        Estimate token count for messages and output.
        
        Args:
            messages: List of message dictionaries
            model: The model name
            output_text: Optional output text to count tokens for
            
        Returns:
            Tuple of (input_tokens, output_tokens) or (None, None) if estimation fails
        """
        raise NotImplementedError("Subclasses must implement this method")


class OpenAITokenEstimator(TokenEstimator):
    """Token estimation for OpenAI models using tiktoken"""
    
    def estimate_tokens(self, messages: list, model: str, output_text: Optional[str] = None) -> Tuple[Optional[int], Optional[int]]:
        """Estimate token count for messages and output using tiktoken"""
        if not tiktoken:
            logger.warning("tiktoken not available, cannot estimate tokens")
            return None, None
            
        try:
            # Use the model-specific encoding or fall back to cl100k_base
            try:
                if model in ["gpt-4o", "gpt-4.1", "o3"]:
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


class AnthropicTokenEstimator(TokenEstimator):
    """Token estimation for Anthropic models"""
    
    def estimate_tokens(self, messages: list, model: str, output_text: Optional[str] = None) -> Tuple[Optional[int], Optional[int]]:
        """
        Estimate token count for Anthropic models.
        Note: This is a rough estimation as Anthropic doesn't provide tiktoken-like library.
        """
        try:
            input_chars = 0
            
            # Count characters in messages
            for message in messages:
                if message.get("content"):
                    if isinstance(message["content"], str):
                        input_chars += len(message["content"])
                    elif isinstance(message["content"], list):
                        # Handle content array format
                        for content_item in message["content"]:
                            if content_item.get("type") == "text":
                                input_chars += len(content_item.get("text", ""))
                
                # Count tool calls
                if message.get("tool_calls"):
                    for tool_call in message["tool_calls"]:
                        input_chars += len(json.dumps(tool_call))
            
            # Rough estimation: ~4 characters per token for Claude models
            input_tokens = input_chars // 4
            
            output_tokens = 0
            if output_text:
                output_tokens = len(output_text) // 4
            
            logger.info(f"Anthropic token estimation - Input: {input_tokens}, Output: {output_tokens}")
            return input_tokens, output_tokens
            
        except Exception as e:
            logger.error(f"Failed to estimate Anthropic tokens: {e}")
            return None, None


class XAITokenEstimator(OpenAITokenEstimator):
    """Token estimation for XAI models - uses same approach as OpenAI"""
    pass


def get_token_estimator(provider: str) -> TokenEstimator:
    """
    Factory function to get the appropriate token estimator for a provider.
    
    Args:
        provider: The provider name ('openai', 'anthropic', 'xai')
        
    Returns:
        TokenEstimator instance
    """
    estimators = {
        'openai': OpenAITokenEstimator,
        'anthropic': AnthropicTokenEstimator,
        'xai': XAITokenEstimator,
    }
    
    estimator_class = estimators.get(provider, OpenAITokenEstimator)
    return estimator_class()