"""
Common AI provider utilities that can be imported by both ai_providers and factory.llm modules.
This module contains shared functions to avoid circular imports.
"""

# Re-export commonly used functions from other modules to maintain backward compatibility
from factory.tool_execution import (
    execute_tool_call,
    get_notification_type_for_tool,
    map_notification_type_to_tab,
    MAX_TOOL_OUTPUT_SIZE
)

from factory.token_tracking import track_token_usage