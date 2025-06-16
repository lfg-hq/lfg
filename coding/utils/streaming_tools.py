"""
Streaming tool implementations that can yield content during execution
"""
import json
import logging
from coding.utils.ai_providers import AIProvider
from coding.utils.ai_tools import tools_ticket
from coding.utils.task_prompt import get_task_implementaion_developer

logger = logging.getLogger(__name__)


async def stream_ticket_implementation(config, project_id, conversation_id):
    """
    Stream the implementation of a ticket
    This is an async generator that yields content as it's generated
    """
    try:
        ticket_id = config.get('ticket_id')
        ticket_name = config.get('ticket_name')
        project_name = config.get('project_name')
        requires_worktree = config.get('requires_worktree', False)
        ticket_details = config.get('ticket_details', {})
        
        # Build the implementation prompt
        user_message = f"""
You are implementing ticket #{ticket_id}: {ticket_name}
Project Name: {project_name}
Requires Worktree: {requires_worktree}

**Full Ticket Details:**
{json.dumps(ticket_details, indent=2)}

**Implementation Instructions:**
1. Setup ticket tracking and worktree (if required) using execute_command
2. Get project context using get_prd() and get_implementation()
3. Project will be implemented in the project directory: ~/LFG/workspace/{project_name}
4. Write all files using git patch format with execute_command (see examples in your prompt)
5. Update .gitignore if needed
6. Follow UI/UX requirements precisely
7. Run tests using execute_command
8. Commit with: git commit -m "Implement ticket {ticket_id}: {ticket_name}"

**Important:**
- Use git patch format for ALL file creation/modification
- Always use execute_command() for shell operations
- Focus only on this ticket's scope
- Provide detailed explanations of what you're doing at each step

Begin implementation now.
"""
        
        # Create messages list
        messages = [
            {"role": "system", "content": await get_task_implementaion_developer()},
            {"role": "user", "content": user_message}
        ]
        
        # Get the provider
        provider = AIProvider.get_provider("anthropic", "claude_4_sonnet")
        
        # Stream the implementation
        async for chunk in provider.generate_stream(messages, project_id, conversation_id, tools_ticket):
            yield chunk
            
    except Exception as e:
        logger.error(f"Error in stream_ticket_implementation: {str(e)}")
        yield f"\n\nError during implementation: {str(e)}\n"


# Registry of streaming tools
STREAMING_TOOLS = {
    "implement_ticket": stream_ticket_implementation
}


async def handle_streaming_tool(tool_name, config, project_id, conversation_id):
    """
    Handle execution of a streaming tool
    Returns an async generator that yields content
    """
    if tool_name not in STREAMING_TOOLS:
        raise ValueError(f"Unknown streaming tool: {tool_name}")
        
    handler = STREAMING_TOOLS[tool_name]
    async for chunk in handler(config, project_id, conversation_id):
        yield chunk