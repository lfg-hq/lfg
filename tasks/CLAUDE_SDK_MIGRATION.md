# Claude Agent SDK Migration Guide

## Overview
This document outlines the migration from the original `execute_ticket_implementation()` function to the new Claude Agent SDK-based implementation.

## Key Improvements

### 1. **Better AI Control**
- Uses the Claude Agent SDK for structured agent interactions
- More reliable tool execution and response handling
- Built-in timeout management and error recovery

### 2. **Cleaner Architecture**
- Separated concerns with `TicketExecutor` class
- Async-first design with sync wrappers for compatibility
- Better separation of AI interaction from business logic

### 3. **Enhanced Error Handling**
- Structured error types and retry logic
- Better API error detection and recovery
- Preserved retryable error mechanism

## Installation

Add the Claude Agent SDK to your requirements:

```bash
pip install claude-agent-sdk
```

Or add to `requirements.txt`:
```
claude-agent-sdk>=1.0.0
```

## Migration Steps

### 1. Update Django-Q Task Definitions

Replace the import in any files that reference the ticket executor:

```python
# OLD
from tasks.task_definitions import execute_ticket_implementation

# NEW
from tasks.claude_agent_ticket_executor import execute_ticket_implementation_claude_sdk as execute_ticket_implementation
```

### 2. Update Task Manager Calls

If you're using the task manager to queue ticket executions, update the function reference:

```python
# OLD
task_manager.publish_task(
    'tasks.task_definitions.execute_ticket_implementation',
    ticket_id, project_id, conversation_id
)

# NEW
task_manager.publish_task(
    'tasks.claude_agent_ticket_executor.execute_ticket_implementation_claude_sdk',
    ticket_id, project_id, conversation_id
)
```

### 3. Batch Execution Updates

For batch ticket execution:

```python
# OLD
from tasks.task_definitions import batch_execute_tickets

# NEW
from tasks.claude_agent_ticket_executor import batch_execute_tickets_claude_sdk_sync as batch_execute_tickets
```

## API Compatibility

The new implementation maintains 100% API compatibility with the original function:

### Function Signatures (Unchanged)

```python
def execute_ticket_implementation_claude_sdk(
    ticket_id: int,
    project_id: int,
    conversation_id: int,
    max_execution_time: int = 300
) -> Dict[str, Any]

def batch_execute_tickets_claude_sdk_sync(
    ticket_ids: List[int],
    project_id: int,
    conversation_id: int
) -> Dict[str, Any]
```

### Return Values (Unchanged)

Success response:
```python
{
    "status": "success",
    "ticket_id": ticket_id,
    "ticket_name": ticket.name,
    "message": f"Ticket completed in {execution_time:.2f}s",
    "execution_time": f"{execution_time:.2f}s",
    "files_created": [...],
    "dependencies": [...],
    "workspace_id": workspace_id,
    "completion_time": datetime.now().isoformat()
}
```

Error/Failed response:
```python
{
    "status": "failed" | "error",
    "ticket_id": ticket_id,
    "error": error_reason,
    "execution_time": f"{execution_time:.2f}s",
    "workspace_id": workspace_id,
    "retryable": is_retryable
}
```

## Testing the Migration

### 1. Unit Test

Create a test ticket and execute it:

```python
from tasks.claude_agent_ticket_executor import execute_ticket_implementation_claude_sdk

# Test execution
result = execute_ticket_implementation_claude_sdk(
    ticket_id=1,
    project_id=1,
    conversation_id=1,
    max_execution_time=60
)

print(f"Execution result: {result}")
```

### 2. Integration Test

Test with your existing Django-Q setup:

```python
from tasks.task_manager import TaskManager

task_manager = TaskManager()
task_id = task_manager.publish_task(
    'tasks.claude_agent_ticket_executor.execute_ticket_implementation_claude_sdk',
    ticket_id,
    project_id,
    conversation_id,
    task_name=f'Ticket_{ticket_id}_Test'
)
```

## Rollback Plan

If you need to rollback to the original implementation:

1. Keep the original `task_definitions.py` file unchanged
2. Update imports back to the original module
3. No database changes are required

## Configuration

The Claude Agent SDK uses the following environment variables (if needed):

```bash
# Optional: Override default Claude API settings
export CLAUDE_API_KEY="your-api-key"  # If different from your existing setup
export CLAUDE_API_URL="https://api.anthropic.com"  # If using a proxy
```

## Monitoring

The new implementation preserves all existing logging:

```python
# Logs are written to the same logger
logger = logging.getLogger(__name__)
```

Monitor these log patterns:
- "Starting ticket #X: [name]"
- "Workspace ready: [id]"
- "AI response received. Time: X.XXs"
- "Completed ticket #X" or "Failed ticket #X"

## Performance Considerations

1. **Async Execution**: The new implementation is async-native, which may improve performance for I/O-bound operations
2. **SDK Overhead**: The Claude Agent SDK adds minimal overhead compared to direct API calls
3. **Timeout Handling**: More robust timeout handling prevents hanging executions

## Support

For issues with the migration:
1. Check the logs for detailed error messages
2. Verify the Claude Agent SDK is properly installed
3. Ensure all imports are updated correctly
4. Test with a simple ticket first before running batch operations

## Future Enhancements

With the Claude Agent SDK, you can now easily add:
- Custom tool definitions specific to your project
- Hook-based permission systems
- MCP server integrations
- Real-time streaming of AI responses
- Session-based conversations for multi-turn interactions