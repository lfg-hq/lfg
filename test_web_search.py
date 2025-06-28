#!/usr/bin/env python3
"""
Test script to verify web search functionality in LFG Agent
"""

import asyncio
import sys
import os

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')

# Setup Django
import django
django.setup()

from coding.utils.ai_providers import AnthropicProvider

async def test_web_search():
    """Test if Claude can use web search"""
    print("Testing web search functionality...")
    
    # Create a simple test message that should trigger web search
    messages = [
        {"role": "system", "content": "You are a helpful assistant. Use web search when needed to answer questions about current events."},
        {"role": "user", "content": "What is the world's tallest building as of 2025? Please search for current information."}
    ]
    
    # Create provider instance (using None for user/project/conversation for testing)
    provider = AnthropicProvider("claude_4_sonnet", user=None, conversation=None, project=None)
    
    # Generate response
    print("\nSending request to Claude...")
    print("-" * 50)
    
    full_response = ""
    try:
        async for chunk in provider.generate_stream(messages, None, None, []):
            if isinstance(chunk, str) and "__NOTIFICATION__" not in chunk:
                print(chunk, end='', flush=True)
                full_response += chunk
    except Exception as e:
        print(f"\nError: {e}")
        return
    
    print("\n" + "-" * 50)
    print("\nTest complete!")
    
    # Check if the response mentions search or current information
    if "search" in full_response.lower() or "2025" in full_response.lower():
        print("✅ Web search appears to be working - Claude provided current information")
    else:
        print("❌ Web search may not be working - Claude did not provide current information")

if __name__ == "__main__":
    asyncio.run(test_web_search())