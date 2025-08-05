import logging
from typing import Optional, Dict, Type
from django.contrib.auth.models import User

from .base import BaseLLMProvider
from .anthropic import AnthropicProvider
from .openai_provider import OpenAIProvider
from .xai import XAIProvider
from .google import GoogleGeminiProvider

logger = logging.getLogger(__name__)


class LLMProviderFactory:
    """Factory class for creating LLM provider instances"""
    
    # Provider mapping
    _providers: Dict[str, Type[BaseLLMProvider]] = {
        'anthropic': AnthropicProvider,
        'openai': OpenAIProvider,
        'xai': XAIProvider,
        'google': GoogleGeminiProvider,
    }
    
    # Model to provider mapping
    _model_to_provider = {
        # Anthropic models
        'claude_4_sonnet': 'anthropic',
        'claude_4_opus': 'anthropic',
        'claude_3.5_sonnet': 'anthropic',
        
        # OpenAI models
        'gpt_4o': 'openai',
        'gpt_4.1': 'openai',
        'o3': 'openai',
        'o4-mini': 'openai',
        
        # XAI models
        'grok_4': 'xai',
        
        # Google models
        'gemini_2.5_pro': 'google',
        'gemini_2.5_flash': 'google',
        'gemini_2.5_flash_lite': 'google',
    }
    
    @classmethod
    def get_provider(cls, provider_name: Optional[str], selected_model: str, 
                    user: Optional[User] = None, conversation: Optional[any] = None, 
                    project: Optional[any] = None) -> BaseLLMProvider:
        """
        Get the appropriate LLM provider instance.
        
        Args:
            provider_name: Name of the provider (optional, can be inferred from model)
            selected_model: The model identifier
            user: The user making the request
            conversation: The conversation context
            project: The project context
            
        Returns:
            An instance of the appropriate LLM provider
        """
        # If provider_name not specified, infer from model
        if not provider_name:
            provider_name = cls._model_to_provider.get(selected_model)
            if not provider_name:
                logger.warning(f"Unknown model {selected_model}, defaulting to OpenAI provider")
                provider_name = 'openai'
        
        logger.info(f"Creating provider with provider_name: {provider_name}, selected_model: {selected_model}, user: {user}", 
                   extra={'easylogs_metadata': {'user_id': user.id if user else None}})
        
        # Get the provider class
        provider_class = cls._providers.get(provider_name)
        
        if provider_class:
            return provider_class(selected_model, user, conversation, project)
        else:
            logger.warning(f"Unknown provider {provider_name}, defaulting to OpenAI")
            return OpenAIProvider(selected_model, user, conversation, project)
    
    @classmethod
    def register_provider(cls, name: str, provider_class: Type[BaseLLMProvider]):
        """Register a new provider type"""
        cls._providers[name] = provider_class
    
    @classmethod
    def register_model(cls, model_name: str, provider_name: str):
        """Register a model to provider mapping"""
        cls._model_to_provider[model_name] = provider_name
    
    @classmethod
    def get_available_providers(cls) -> list:
        """Get list of available provider names"""
        return list(cls._providers.keys())
    
    @classmethod
    def get_available_models(cls) -> Dict[str, list]:
        """Get available models grouped by provider"""
        models_by_provider = {}
        for model, provider in cls._model_to_provider.items():
            if provider not in models_by_provider:
                models_by_provider[provider] = []
            models_by_provider[provider].append(model)
        return models_by_provider


# For backward compatibility, expose the factory method at module level
def get_provider(provider_name: Optional[str], selected_model: str, 
                user: Optional[User] = None, conversation: Optional[any] = None, 
                project: Optional[any] = None) -> BaseLLMProvider:
    """Convenience function to get provider using the factory"""
    return LLMProviderFactory.get_provider(provider_name, selected_model, user, conversation, project)