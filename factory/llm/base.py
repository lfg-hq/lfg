import asyncio
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncGenerator
from django.contrib.auth.models import User
from channels.db import database_sync_to_async
from subscriptions.models import UserCredit

logger = logging.getLogger(__name__)


class BaseLLMProvider(ABC):
    """Base class for all LLM providers"""
    
    def __init__(self, selected_model: str, user: Optional[User] = None, 
                 conversation: Optional[Any] = None, project: Optional[Any] = None):
        self.selected_model = selected_model
        self.user = user
        self.conversation = conversation
        self.project = project
        self.client = None
        self.api_key = ''
        
        # Get user from conversation or project if not provided
        if not user:
            if conversation:
                self.user = conversation.user
            elif project:
                self.user = project.owner
                
        logger.info(f"{self.__class__.__name__} initialized with model: {selected_model}")
    
    @abstractmethod
    async def _ensure_client(self):
        """Ensure the client is initialized with API key"""
        pass
    
    @abstractmethod
    async def generate_stream(self, messages: List[Dict[str, Any]], 
                            project_id: Optional[int], 
                            conversation_id: Optional[int], 
                            tools: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        """Generate streaming response from the AI provider"""
        pass
    
    @abstractmethod
    def _convert_messages_to_provider_format(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert messages from standard format to provider-specific format"""
        pass
    
    @abstractmethod
    def _convert_tools_to_provider_format(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert tools from standard format to provider-specific format"""
        pass
    
    @database_sync_to_async
    def _get_api_key_from_db(self, user: User, provider_key: str) -> str:
        """Get API key from user's LLMApiKeys"""
        try:
            from accounts.models import LLMApiKeys
            llm_keys = LLMApiKeys.objects.get(user=user)
            return getattr(llm_keys, provider_key, '') or ''
        except LLMApiKeys.DoesNotExist:
            return ''
        except Exception as e:
            logger.warning(f"Could not fetch API key: {e}")
            return ''
    
    async def _process_stream_async(self, response_stream):
        """Process the response stream asynchronously by yielding control back to event loop"""
        for chunk in response_stream:
            yield chunk
            # Yield control back to the event loop periodically
            await asyncio.sleep(0)
    
    @database_sync_to_async
    def check_token_limits(self) -> tuple[bool, str, int]:
        """
        Check if user has enough tokens to make a request.
        Skip validation if user is using BYOK (Bring Your Own Key).

        Returns:
            tuple: (can_proceed, error_message, remaining_tokens)
        """
        if not self.user:
            return True, "", 0  # Allow if no user (shouldn't happen)

        try:
            # Check if user has BYOK API key configured for this provider
            has_byok = self._check_has_byok_key()

            if has_byok:
                logger.info(f"User {self.user.id} has BYOK API key configured. Skipping platform credit validation.")
                return True, "", 0  # Skip validation for BYOK users

            # User is using platform credits - validate limits
            user_credit, created = UserCredit.objects.get_or_create(user=self.user)

            # Check if user can use this model with platform-provided API key
            if not user_credit.can_use_platform_model(self.selected_model):
                return False, f"Platform only provides gpt-5-mini. Please add your own API key in settings to use {self.selected_model}.", 0

            # Check if user can use this model based on their subscription tier
            if not user_credit.can_use_model(self.selected_model):
                return False, f"Free tier users can only use gpt-5-mini model. Please upgrade to Pro to use {self.selected_model}.", 0

            # Check token limits
            remaining_tokens = user_credit.get_remaining_tokens()
            if remaining_tokens <= 0:
                if user_credit.is_free_tier:
                    return False, "You have reached your free tier limit of 100,000 tokens. Please upgrade to Pro for 300,000 tokens per month.", 0
                else:
                    return False, "You have reached your monthly token limit of 1,000,000 tokens. Additional tokens can be purchased.", 0

            return True, "", remaining_tokens

        except Exception as e:
            logger.error(f"Error checking token limits: {e}")
            return True, "", 0  # Allow on error to not block users

    def _check_has_byok_key(self) -> bool:
        """
        Check if user has BYOK API key configured for this provider.
        This is a synchronous method called from within database_sync_to_async context.
        """
        try:
            from accounts.models import LLMApiKeys

            # Determine provider name from class name
            provider_map = {
                'AnthropicProvider': 'anthropic_api_key',
                'OpenAIProvider': 'openai_api_key',
                'XAIProvider': 'xai_api_key',
                'GoogleGeminiProvider': 'google_api_key',
            }

            provider_key = provider_map.get(self.__class__.__name__)
            if not provider_key:
                logger.warning(f"Unknown provider class: {self.__class__.__name__}")
                return False

            llm_keys = LLMApiKeys.objects.get(user=self.user)
            api_key = getattr(llm_keys, provider_key, '') or ''

            has_key = bool(api_key)
            logger.info(f"BYOK check for {self.__class__.__name__}: {has_key}")
            return has_key

        except LLMApiKeys.DoesNotExist:
            return False
        except Exception as e:
            logger.warning(f"Could not check BYOK status: {e}")
            return False