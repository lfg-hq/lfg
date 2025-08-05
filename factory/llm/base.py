import asyncio
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncGenerator
from django.contrib.auth.models import User
from channels.db import database_sync_to_async

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