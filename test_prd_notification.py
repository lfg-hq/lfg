#!/usr/bin/env python3
"""
Test the complete PRD streaming notification flow
Run from Django shell: python manage.py shell
"""

import asyncio
import json
from coding.utils.ai_providers import execute_tool_call

async def test_prd_streaming_notification():
    """Test that stream_prd_content creates proper notifications"""
    
    # Test data
    project_id = 1  # Change to a valid project ID
    conversation_id = None
    
    print("\n=== Testing PRD Streaming Notification Flow ===\n")
    
    # Test 1: Stream first chunk
    print("1. Testing first chunk...")
    tool_args = json.dumps({
        "content_chunk": "# Product Requirements Document\n\n## Overview\n\nThis is a test PRD.",
        "is_complete": False
    })
    
    result_content, notification_data, yielded_content = await execute_tool_call(
        "stream_prd_content", tool_args, project_id, conversation_id
    )
    
    print(f"   Result: {result_content}")
    print(f"   Notification data: {json.dumps(notification_data, indent=2)}")
    print(f"   Has content_chunk: {'content_chunk' in notification_data}")
    print(f"   Content chunk length: {len(notification_data.get('content_chunk', ''))}")
    
    # Test 2: Stream completion
    print("\n2. Testing completion...")
    tool_args = json.dumps({
        "content_chunk": "",
        "is_complete": True
    })
    
    result_content, notification_data, yielded_content = await execute_tool_call(
        "stream_prd_content", tool_args, project_id, conversation_id
    )
    
    print(f"   Result: {result_content}")
    print(f"   Notification data: {json.dumps(notification_data, indent=2)}")
    print(f"   Is complete: {notification_data.get('is_complete')}")
    
    print("\n=== Test Complete ===")

# Run the test
if __name__ == "__main__":
    asyncio.run(test_prd_streaming_notification())