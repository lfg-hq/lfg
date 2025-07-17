#!/usr/bin/env python
"""
Test script to verify OpenAI token tracking with fallback estimation
"""

import os
import sys
import django

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LFG.settings')
django.setup()

from development.utils.ai_providers import OpenAIProvider

def test_token_estimation():
    """Test the token estimation method"""
    
    # Create an OpenAI provider instance
    provider = OpenAIProvider("gpt_4o")
    
    # Test messages
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you doing today? Can you help me with some Python programming?"},
        {"role": "assistant", "content": "Hello! I'm doing well, thank you for asking. I'd be happy to help you with Python programming. What specific topic or problem would you like assistance with?"},
        {"role": "user", "content": "I need help understanding decorators in Python. Can you explain how they work?"}
    ]
    
    # Test token estimation
    estimated_tokens = provider.estimate_tokens(messages, "gpt-4o")
    
    if estimated_tokens:
        print(f"✅ Token estimation successful!")
        print(f"   Estimated tokens for {len(messages)} messages: {estimated_tokens}")
        
        # Test with tool calls
        messages_with_tools = messages + [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"location": "San Francisco", "unit": "celsius"}'
                        }
                    }
                ]
            },
            {
                "role": "tool",
                "tool_call_id": "call_123",
                "content": "The weather in San Francisco is 22°C and sunny."
            }
        ]
        
        estimated_with_tools = provider.estimate_tokens(messages_with_tools, "gpt-4o")
        print(f"   Estimated tokens with tool calls: {estimated_with_tools}")
        
    else:
        print("❌ Token estimation failed (returned None)")
        print("   This might be because tiktoken is not installed yet")

if __name__ == "__main__":
    print("Testing OpenAI token estimation fallback...")
    test_token_estimation()