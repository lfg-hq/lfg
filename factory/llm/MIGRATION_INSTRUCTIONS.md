# Migration Instructions for LLM Factory Pattern

## Overview

This document provides step-by-step instructions for migrating from the current monolithic `ai_providers.py` to the new factory pattern implementation.

## Step 1: Backup Current Implementation

```bash
cp development/utils/ai_providers.py development/utils/ai_providers.py.backup
```

## Step 2: Update ai_providers.py

Replace the provider classes in `development/utils/ai_providers.py` with the following:

```python
# Remove the OpenAIProvider, XAIProvider, and AnthropicProvider class definitions

# Add at the top of the file:
from factory.llm import LLMProviderFactory

# Update the AIProvider class:
class AIProvider:
    """Base class for AI providers"""
    
    @staticmethod
    def get_provider(provider_name, selected_model, user=None, conversation=None, project=None):
        """Factory method to get the appropriate provider"""
        return LLMProviderFactory.get_provider(provider_name, selected_model, user, conversation, project)
```

## Step 3: Keep Shared Functions

The following functions should remain in `ai_providers.py`:
- `track_token_usage()`
- `get_notification_type_for_tool()`
- `map_notification_type_to_tab()`
- `execute_tool_call()`
- `get_ai_response()`

## Step 4: Update Factory Provider Imports

Update each provider file in `factory/llm/` to fix the imports:

```bash
# For each provider file (anthropic.py, openai_provider.py, xai.py, google.py)
# Remove the comment markers from the import lines
```

## Step 5: Database Migration

```bash
# Create migration for the new google_api_key field
python manage.py makemigrations accounts

# Apply the migration
python manage.py migrate
```

## Step 6: Update Settings UI

Add Google API key field to the settings page where users manage their API keys.

## Step 7: Test the Integration

Test each provider to ensure they work correctly:

```python
# Test script
from factory.llm import LLMProviderFactory

# Test each provider
providers = ['anthropic', 'openai', 'xai', 'google']
models = {
    'anthropic': 'claude_4_sonnet',
    'openai': 'gpt_4o',
    'xai': 'grok_4',
    'google': 'gemini_2.5_pro'
}

for provider_name in providers:
    model = models[provider_name]
    provider = LLMProviderFactory.get_provider(provider_name, model)
    print(f"{provider_name}: {provider.__class__.__name__}")
```

## Step 8: Update Documentation

Update any documentation that references the old provider implementation to reflect the new factory pattern.

## Benefits of This Migration

1. **Modularity**: Each provider is in its own file
2. **Maintainability**: Easier to update individual providers
3. **Extensibility**: Simple to add new providers
4. **Testing**: Easier to unit test individual providers
5. **Code Organization**: Cleaner separation of concerns

## Rollback Plan

If issues arise:

```bash
# Restore the backup
cp development/utils/ai_providers.py.backup development/utils/ai_providers.py

# Revert the database migration
python manage.py migrate accounts <previous_migration_number>
```