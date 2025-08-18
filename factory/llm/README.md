# LLM Provider Factory Pattern

This directory contains a refactored implementation of the LLM providers using a factory pattern. This makes it easier to add new providers and maintain the codebase.

## Structure

- `base.py` - Base class for all LLM providers
- `anthropic.py` - Anthropic Claude provider implementation
- `openai_provider.py` - OpenAI provider implementation
- `xai.py` - XAI (Grok) provider implementation
- `google.py` - Google Gemini provider implementation (NEW)
- `__init__.py` - Factory class for creating provider instances

## Integration Instructions

To integrate this factory pattern into the main codebase:

### 1. Update development/utils/ai_providers.py

Replace the existing provider classes with imports from the factory:

```python
# At the top of the file, add:
from factory.llm import LLMProviderFactory, get_provider

# Replace the AIProvider.get_provider method with:
class AIProvider:
    @staticmethod
    def get_provider(provider_name, selected_model, user=None, conversation=None, project=None):
        """Factory method to get the appropriate provider"""
        return get_provider(provider_name, selected_model, user, conversation, project)
```

### 2. Move shared utilities

The following functions should remain in `ai_providers.py` as they are shared across providers:
- `track_token_usage()`
- `get_notification_type_for_tool()`
- `map_notification_type_to_tab()`
- `execute_tool_call()`

### 3. Update imports in provider files

Each provider file currently has placeholder imports that need to be updated:

```python
# Replace the placeholder imports with:
from factory.ai_common import execute_tool_call, get_notification_type_for_tool, track_token_usage
from factory.streaming_handlers import StreamingTagHandler, format_notification
```

### 4. Database Migration

Run the following command to create a migration for the new google_api_key field:

```bash
python manage.py makemigrations accounts
python manage.py migrate
```

### 5. Add Google Gemini Support to Frontend

The HTML template has already been updated to include Google Gemini models. You may need to update:
- `/static/js/model-handler.js` - Add display names for the new models
- Settings page to allow users to input their Google API key

## Adding New Providers

To add a new provider:

1. Create a new file in `factory/llm/<provider_name>.py`
2. Inherit from `BaseLLMProvider`
3. Implement the required methods
4. Register the provider in `__init__.py`:
   ```python
   from .<provider_name> import NewProvider
   
   # In LLMProviderFactory._providers:
   'new_provider': NewProvider,
   
   # In LLMProviderFactory._model_to_provider:
   'new_model_name': 'new_provider',
   ```

## Google Gemini Models

The following Google Gemini models are now supported:
- `gemini_2.5_pro` - Gemini 2.5 Pro (Most capable)
- `gemini_2.5_flash` - Gemini 2.5 Flash (Fast and efficient)
- `gemini_2.5_flash_lite` - Gemini 2.5 Flash Lite (Lightweight)

Users need to obtain a Google API key from [Google AI Studio](https://aistudio.google.com/) and add it to their profile settings.