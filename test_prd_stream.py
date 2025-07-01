#!/usr/bin/env python3
"""
Test script to verify PRD streaming functionality
Run this from the Django shell: python manage.py shell < test_prd_stream.py
"""

import asyncio
import json
from coding.utils.ai_functions import stream_prd_content
from channels.layers import get_channel_layer

async def test_prd_streaming():
    """Test the PRD streaming functionality"""
    
    # Replace with an actual project ID from your database
    project_id = 1  # Change this to a valid project ID
    
    print("Testing PRD streaming...")
    
    # Test chunk 1
    result1 = await stream_prd_content({
        "content_chunk": "# Product Requirements Document\n\n## Overview\n\nThis is a test PRD to verify streaming functionality.",
        "is_complete": False
    }, project_id)
    print(f"Result 1: {json.dumps(result1, indent=2)}")
    
    # Test chunk 2
    result2 = await stream_prd_content({
        "content_chunk": "\n\n## Goals\n\n1. Test streaming\n2. Verify real-time updates\n3. Ensure artifacts panel updates",
        "is_complete": False
    }, project_id)
    print(f"Result 2: {json.dumps(result2, indent=2)}")
    
    # Test completion
    result3 = await stream_prd_content({
        "content_chunk": "",
        "is_complete": True
    }, project_id)
    print(f"Result 3: {json.dumps(result3, indent=2)}")
    
    print("\nAll tests completed!")

# Run the test
if __name__ == "__main__":
    asyncio.run(test_prd_streaming())