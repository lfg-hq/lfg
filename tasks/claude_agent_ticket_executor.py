"""
Claude Agent SDK implementation for ticket execution.
This module replaces the original execute_ticket_implementation function
with a version that uses the Claude Agent SDK for better control and reliability.
"""

import asyncio
import json
import logging
import time
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

from django.db import transaction
from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer

# Claude Agent SDK imports
from claude_agent_sdk import (
    query,
    ClaudeSDKClient,
    ClaudeAgentOptions,
    tool,
    create_sdk_mcp_server,
    AssistantMessage,
    UserMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock
)

from projects.models import ProjectTicket, Project, ProjectFile
from factory.ai_functions import new_dev_sandbox_tool, _fetch_workspace, get_magpie_client, _slugify_project_name, MAGPIE_BOOTSTRAP_SCRIPT
from development.models import MagpieWorkspace

logger = logging.getLogger(__name__)


class TicketExecutor:
    """
    Claude Agent SDK based ticket executor.
    Handles the implementation of project tickets using AI assistance.
    """

    def __init__(self, conversation_id: Optional[int] = None):
        self.conversation_id = conversation_id
        self.workspace_id = None
        self.project = None
        self.ticket = None

    def broadcast_notification(self, payload: Dict[str, Any]) -> None:
        """Send real-time notification via WebSocket."""
        if not self.conversation_id:
            return

        channel_layer = get_channel_layer()
        if not channel_layer:
            return

        event = {
            'type': 'ai_response_chunk',
            'chunk': '',
            'is_final': False,
            'conversation_id': self.conversation_id,
        }
        event.update(payload)
        event.setdefault('is_notification', True)
        event.setdefault('notification_marker', "__NOTIFICATION__")

        try:
            async_to_sync(channel_layer.group_send)(
                f"conversation_{self.conversation_id}",
                event
            )
        except Exception as exc:
            logger.error(f"Failed to broadcast notification: {exc}")

    def broadcast_chat_message(self, role: str, content: str, is_streaming: bool = False) -> None:
        """Send chat message to the ticket chat UI via WebSocket."""
        if not self.conversation_id or not self.ticket:
            return

        channel_layer = get_channel_layer()
        if not channel_layer:
            return

        event = {
            'type': 'ticket_chat_message',
            'ticket_id': self.ticket.id,
            'role': role,
            'content': content,
            'is_streaming': is_streaming,
        }

        try:
            async_to_sync(channel_layer.group_send)(
                f"conversation_{self.conversation_id}",
                event
            )
        except Exception as exc:
            logger.error(f"Failed to broadcast chat message: {exc}")

    async def get_project_context(self) -> str:
        """Fetch project documentation (PRD and implementation docs)."""
        project_context = ""

        try:
            # Fetch PRD files
            prd_files = await sync_to_async(list)(
                ProjectFile.objects.filter(
                    project=self.project,
                    file_type='prd',
                    is_active=True
                ).order_by('-updated_at')[:2]
            )

            # Fetch implementation files
            impl_files = await sync_to_async(list)(
                ProjectFile.objects.filter(
                    project=self.project,
                    file_type='implementation',
                    is_active=True
                ).order_by('-updated_at')[:2]
            )

            if prd_files or impl_files:
                project_context = "\n\n📋 PROJECT DOCUMENTATION:\n"

                for prd in prd_files:
                    project_context += f"\n--- PRD: {prd.name} ---\n"
                    project_context += prd.file_content[:5000]
                    if len(prd.file_content) > 5000:
                        project_context += "\n...(truncated for brevity)\n"
                    project_context += "\n"

                for impl in impl_files:
                    project_context += f"\n--- Technical Implementation: {impl.name} ---\n"
                    project_context += impl.file_content[:5000]
                    if len(impl.file_content) > 5000:
                        project_context += "\n...(truncated for brevity)\n"
                    project_context += "\n"

                logger.info(f"Added project context: {len(prd_files)} PRDs, {len(impl_files)} impl docs")

        except Exception as e:
            logger.warning(f"Could not fetch project documentation: {str(e)}")

        return project_context

    def create_implementation_prompt(self, ticket: ProjectTicket, workspace_id: str, project_context: str) -> str:
        """Create the implementation prompt for the AI."""

        # Check for previous attempt context
        previous_attempt_context = ""
        if ticket.notes and "RETRYABLE ERROR" in ticket.notes:
            previous_attempt_context = f"""
⚠️ RETRY CONTEXT: This ticket was attempted before but failed due to an API error.
Previous attempt notes:
{ticket.notes}

IMPORTANT: Before doing ANY work:
1. Check what files already exist
2. Check what was already installed
3. Continue from where the previous attempt left off
4. DO NOT redo work that's already complete
"""

        return f"""
You are implementing ticket #{ticket.id}: {ticket.name}

TICKET DESCRIPTION:
{ticket.description}

PROJECT PATH: /workspace/nextjs-app
{project_context}
{previous_attempt_context}

REQUIRED FINAL MESSAGE FORMAT:
After completing the ticket requirements, you MUST write:

✅ Success case: "IMPLEMENTATION_STATUS: COMPLETE - [brief summary of what you did]"
❌ Failure case: "IMPLEMENTATION_STATUS: FAILED - [reason]"

Remember:
- ALWAYS check workspace state first (ls, cat package.json)
- This is an EXISTING project - don't recreate it
- Focus ONLY on the ticket requirements
- Don't redo work that's already complete
- Make minimal, targeted changes
"""

    async def execute_ticket(
        self,
        ticket_id: int,
        project_id: int,
        max_execution_time: int = 300
    ) -> Dict[str, Any]:
        """
        Execute a single ticket implementation using Claude Agent SDK.

        Args:
            ticket_id: The ID of the ProjectTicket
            project_id: The ID of the project
            max_execution_time: Maximum execution time in seconds (default: 300s/5min)

        Returns:
            Dict with execution results and status
        """
        start_time = time.time()

        try:
            # 1. GET TICKET AND PROJECT
            self.ticket = await sync_to_async(ProjectTicket.objects.get)(id=ticket_id)
            self.project = await sync_to_async(Project.objects.get)(id=project_id)

            # 2. CHECK IF ALREADY COMPLETED
            if self.ticket.status == 'done':
                logger.info(f"Ticket #{ticket_id} already completed, skipping")
                return {
                    "status": "success",
                    "ticket_id": ticket_id,
                    "message": "Already completed",
                    "skipped": True
                }

            # 3. UPDATE STATUS TO IN-PROGRESS
            self.ticket.status = 'in_progress'
            await sync_to_async(self.ticket.save)(update_fields=['status'])
            logger.info(f"Starting ticket #{ticket_id}: {self.ticket.name}")

            # 4. BROADCAST START
            self.broadcast_notification({
                'is_notification': True,
                'notification_type': 'toolhistory',
                'function_name': 'ticket_execution',
                'status': 'in_progress',
                'message': f"Working on ticket #{self.ticket.id}: {self.ticket.name}",
                'ticket_id': self.ticket.id,
                'ticket_name': self.ticket.name,
                'refresh_checklist': True
            })

            # 5. GET OR CREATE WORKSPACE
            workspace = await _fetch_workspace(project=self.project, conversation_id=self.conversation_id)

            if not workspace:
                # Create new Magpie workspace
                try:
                    client = get_magpie_client()
                    project_name = self.project.provided_name or self.project.name
                    slug = _slugify_project_name(project_name)
                    workspace_name = f"{slug}-{self.project.id}"

                    vm_handle = await asyncio.to_thread(
                        client.jobs.create_persistent_vm,
                        name=workspace_name,
                        script=MAGPIE_BOOTSTRAP_SCRIPT,
                        stateful=True,
                        workspace_size_gb=10,
                        vcpus=2,
                        memory_mb=2048,
                        register_proxy=True,
                        proxy_port=3000,
                        poll_timeout=180,
                        poll_interval=5,
                    )
                    logger.info(f"[MAGPIE][CREATE] vm_handle: {vm_handle}")

                    run_id = vm_handle.request_id
                    workspace_identifier = run_id
                    ipv6 = vm_handle.ip_address
                    proxy_url = vm_handle.proxy_url

                    if not ipv6:
                        raise Exception(f"VM provisioning timed out - no IP address received")

                    workspace = await asyncio.to_thread(
                        MagpieWorkspace.objects.create,
                        project=self.project,
                        conversation_id=str(self.conversation_id) if self.conversation_id else None,
                        job_id=run_id,
                        workspace_id=workspace_identifier,
                        status='ready',
                        ipv6_address=ipv6,
                        project_path='/workspace',
                        proxy_url=proxy_url,
                        metadata={'project_name': project_name}
                    )
                    logger.info(f"[MAGPIE][READY] Workspace ready: {workspace.workspace_id}, IP: {ipv6}, Proxy: {proxy_url}")
                except Exception as e:
                    raise Exception(f"Workspace provisioning failed: {str(e)}")

            self.workspace_id = workspace.workspace_id
            logger.info(f"Workspace ready: {self.workspace_id}")

            # 5b. SETUP DEV SANDBOX
            sandbox_result = await new_dev_sandbox_tool(
                {'workspace_id': self.workspace_id},
                self.project.project_id,
                self.conversation_id
            )

            if sandbox_result.get('status') == 'failed':
                raise Exception(f"Dev sandbox setup failed: {sandbox_result.get('message_to_agent')}")

            # 6. FETCH PROJECT DOCUMENTATION
            project_context = await self.get_project_context()

            # 7. CREATE IMPLEMENTATION PROMPT
            implementation_prompt = self.create_implementation_prompt(
                self.ticket,
                self.workspace_id,
                project_context
            )

            # 8. EXECUTE WITH CLAUDE AGENT SDK
            logger.info("Calling Claude Agent SDK for implementation...")

            # Define the system prompt
            system_prompt = """
You are an expert developer working on an EXISTING codebase. You implement tickets with surgical precision.

FUNDAMENTAL PRINCIPLE: You are working on an EXISTING PROJECT. Every ticket is a TARGETED change to this existing codebase.

🔍 MANDATORY FIRST STEP - ALWAYS CHECK STATE:
Before EVERY ticket implementation, you MUST:
1. Make sure the parent folder is /workspace/nextjs-app/
2. Read the codebase using `ls -la` and `cat` and `grep` (see what exists and read the code)
3. Assess what already exists vs what needs to be done
4. This is NOT optional - you MUST check before doing any work!

Before working on the ticket, check if tasklist exists for this ticket. If not then create the tasks using manage_ticket_tasks().
You will work off these tasklist. Whenever the task is completed, update the task status.

YOUR APPROACH (Like Claude Code):
1. CHECK FIRST: Always check workspace state before making changes
2. UNDERSTAND: Read and analyze existing code when the ticket involves modifications
3. MINIMAL CHANGES: Make ONLY the changes required by the ticket
4. PRESERVE EXISTING: Never recreate files or structures that already exist
5. TARGETED FIXES: For bugs, fix only the specific issue; for features, add only what's needed
6. SKIP TESTING: Just make sure the files are there, then run the project and let the user know.

Plan once. No loops. No tests. No builds. Minimal edits.

Phases: ANALYZE → APPLY → RUN → REPORT. No going backwards.

1. In the planning phase, understand and list all the libraries that need to be installed. Install them at once.
2. Understand all the files that need to be created at once. Create them in a single command.
3. Understand all the edits that need to be made. Make the edits in a single command.
4. Run the app (npm run dev), and check for errors. Use the tool `run_code_server`.
5. Do not build the project, and do not attempt to test the project or verify the files.

STRICT RULES:
1. Complete implementation in ≤50 tool calls
2. CHECK workspace state before making changes
3. READ before you WRITE when modifying existing functionality
4. Write COMPLETE production code (no TODOs/placeholders)
5. ALWAYS end with: "IMPLEMENTATION_STATUS: COMPLETE - [specific changes made]" or "IMPLEMENTATION_STATUS: FAILED - [reason]"
6. The status message is MANDATORY - you must provide it after tools finish

DO NOT:
- Recreate the entire project or application structure
- Create files that already exist without checking first
- Install dependencies that are already installed
- Make changes unrelated to the ticket
- Run build commands (too slow)
- Continue without giving final status

REMEMBER: Always check state first, then make surgical changes. You're a precision surgeon, not a bulldozer.
"""

            # Configure agent options
            agent_options = ClaudeAgentOptions(
                system_prompt=system_prompt,
                allowed_tools=["*"],  # Allow all tools
                permission_mode="auto",  # Auto-approve tool usage
                timeout=max_execution_time * 1000,  # Convert to milliseconds
            )

            # Execute the query using Claude Agent SDK with streaming
            # Note: For now, we'll use the regular query method
            # In the future, we can implement streaming via the SDK

            # Send initial message to chat UI
            self.broadcast_chat_message('assistant', '', is_streaming=True)

            response = await query(
                prompt=implementation_prompt,
                options=agent_options
            )

            # Process the response and stream to chat
            content = ""
            if hasattr(response, 'content'):
                for block in response.content:
                    if isinstance(block, TextBlock):
                        content += block.text
                        # Stream each text block to the chat UI
                        self.broadcast_chat_message('assistant', content, is_streaming=True)

            # Send final message
            self.broadcast_chat_message('assistant', content, is_streaming=False)

            execution_time = time.time() - start_time

            logger.info(f"AI response received. Time: {execution_time:.2f}s")
            logger.info(f"AI response content preview: {content[:200] if content else 'Empty'}")

            # 9. CHECK COMPLETION STATUS
            completed = 'IMPLEMENTATION_STATUS: COMPLETE' in content
            failed = 'IMPLEMENTATION_STATUS: FAILED' in content

            if not completed and not failed:
                logger.warning(f"No explicit completion status found in AI response")
                failed = True
                logger.error("Marking as FAILED due to missing explicit completion status")

            # 10. EXTRACT IMPLEMENTATION DETAILS
            files_created = re.findall(r'cat > (/workspace/nextjs-app/[\w\-\./]+)', content)
            deps_installed = re.findall(r'npm install ([\w\-\s@/]+)', content)
            dependencies = []
            for dep_string in deps_installed:
                dependencies.extend(dep_string.split())

            logger.info(f"Files created: {len(files_created)}, Dependencies: {len(dependencies)}")

            # 11. UPDATE TICKET BASED ON RESULT
            if completed and not failed:
                # SUCCESS!
                self.ticket.status = 'done'
                self.ticket.notes = f"""
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] IMPLEMENTATION COMPLETED
Time: {execution_time:.2f} seconds
Files created: {len(files_created)}
Dependencies: {', '.join(set(dependencies))}
Workspace: {self.workspace_id}
Status: ✓ Complete
"""
                await sync_to_async(self.ticket.save)(update_fields=['status', 'notes'])

                self.broadcast_notification({
                    'is_notification': True,
                    'notification_type': 'toolhistory',
                    'function_name': 'ticket_execution',
                    'status': 'completed',
                    'message': f"✓ Completed ticket #{self.ticket.id}: {self.ticket.name}",
                    'ticket_id': self.ticket.id,
                    'ticket_name': self.ticket.name,
                    'refresh_checklist': True
                })

                return {
                    "status": "success",
                    "ticket_id": ticket_id,
                    "ticket_name": self.ticket.name,
                    "message": f"Ticket completed in {execution_time:.2f}s",
                    "execution_time": f"{execution_time:.2f}s",
                    "files_created": files_created,
                    "dependencies": list(set(dependencies)),
                    "workspace_id": self.workspace_id,
                    "completion_time": datetime.now().isoformat()
                }
            else:
                # FAILED OR INCOMPLETE
                error_match = re.search(r'IMPLEMENTATION_STATUS: FAILED - (.+)', content)
                if error_match:
                    error_reason = error_match.group(1)
                elif not content or len(content) < 100:
                    error_reason = "AI response was empty or incomplete. Possible API timeout or error."
                else:
                    error_reason = "No explicit completion status provided. AI may have exceeded tool limit or stopped unexpectedly."

                self.ticket.status = 'failed'
                self.ticket.notes = f"""
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] IMPLEMENTATION FAILED
Time: {execution_time:.2f} seconds
Files attempted: {len(files_created)}
Error: {error_reason}
Workspace: {self.workspace_id}
Manual intervention required
"""
                await sync_to_async(self.ticket.save)(update_fields=['status', 'notes'])

                self.broadcast_notification({
                    'is_notification': True,
                    'notification_type': 'toolhistory',
                    'function_name': 'ticket_execution',
                    'status': 'failed',
                    'message': f"✗ Failed ticket #{self.ticket.id}: {error_reason}",
                    'ticket_id': self.ticket.id,
                    'ticket_name': self.ticket.name,
                    'refresh_checklist': True
                })

                return {
                    "status": "failed",
                    "ticket_id": ticket_id,
                    "ticket_name": self.ticket.name,
                    "error": error_reason,
                    "execution_time": f"{execution_time:.2f}s",
                    "workspace_id": self.workspace_id,
                    "requires_manual_intervention": True
                }

        except Exception as e:
            # EXCEPTION HANDLING
            execution_time = time.time() - start_time
            error_msg = str(e)
            logger.error(f"Critical error in ticket {ticket_id}: {error_msg}", exc_info=True)

            # Determine if this is a retryable error
            is_retryable = any(indicator in error_msg.lower() for indicator in [
                '500', 'internal server error', 'timeout', 'connection', 'api error'
            ])

            if self.ticket:
                # For retryable errors, keep status as in_progress for retry
                if is_retryable and execution_time < max_execution_time:
                    self.ticket.status = 'in_progress'
                    self.ticket.notes = f"""
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] RETRYABLE ERROR (will retry)
Error: {error_msg}
Time: {execution_time:.2f}s
Workspace: {self.workspace_id or 'N/A'}
"""
                    logger.info(f"Marking ticket #{ticket_id} for retry due to retryable error")
                else:
                    # Non-retryable or already timed out
                    self.ticket.status = 'failed'
                    self.ticket.notes = f"""
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] FATAL ERROR
Error: {error_msg}
Time: {execution_time:.2f}s
Workspace: {self.workspace_id or 'N/A'}
Retryable: {is_retryable}
Manual intervention required
"""

                await sync_to_async(self.ticket.save)(update_fields=['status', 'notes'])

                self.broadcast_notification({
                    'is_notification': True,
                    'notification_type': 'toolhistory',
                    'function_name': 'ticket_execution',
                    'status': 'failed' if not is_retryable else 'error',
                    'message': f"✗ Ticket #{self.ticket.id} error: {error_msg[:100]}",
                    'ticket_id': self.ticket.id,
                    'ticket_name': self.ticket.name if self.ticket else 'Unknown',
                    'refresh_checklist': True
                })

            # Re-raise retryable errors for retry mechanism
            if is_retryable and execution_time < max_execution_time:
                raise

            return {
                "status": "error",
                "ticket_id": ticket_id,
                "error": error_msg,
                "workspace_id": self.workspace_id,
                "execution_time": f"{execution_time:.2f}s",
                "retryable": is_retryable
            }


# Synchronous wrapper for Django-Q compatibility
def execute_ticket_implementation_claude_sdk(
    ticket_id: int,
    project_id: int,
    conversation_id: int,
    max_execution_time: int = 300
) -> Dict[str, Any]:
    """
    Synchronous wrapper for the Claude SDK ticket executor.
    This function can be called from Django-Q tasks.

    Args:
        ticket_id: The ID of the ProjectTicket
        project_id: The ID of the project
        conversation_id: The ID of the conversation
        max_execution_time: Maximum execution time in seconds

    Returns:
        Dict with execution results and status
    """
    executor = TicketExecutor(conversation_id)

    # Run the async function in a new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(
            executor.execute_ticket(ticket_id, project_id, max_execution_time)
        )
        return result
    finally:
        loop.close()


# Batch execution function
async def batch_execute_tickets_claude_sdk(
    ticket_ids: List[int],
    project_id: int,
    conversation_id: int
) -> Dict[str, Any]:
    """
    Execute multiple tickets in sequence using Claude SDK.

    Args:
        ticket_ids: List of ticket IDs to execute
        project_id: The project ID
        conversation_id: The conversation ID

    Returns:
        Dict with batch execution results
    """
    executor = TicketExecutor(conversation_id)
    results = []

    executor.broadcast_notification({
        'is_notification': True,
        'notification_type': 'toolhistory',
        'function_name': 'ticket_execution_queue',
        'status': 'queued',
        'message': f"Starting background execution for {len(ticket_ids)} tickets.",
        'refresh_checklist': bool(ticket_ids)
    })

    for index, ticket_id in enumerate(ticket_ids, start=1):
        executor.broadcast_notification({
            'is_notification': True,
            'notification_type': 'toolhistory',
            'function_name': 'ticket_execution_queue',
            'status': 'in_progress',
            'message': f"Executing ticket {index}/{len(ticket_ids)} (#{ticket_id}).",
            'ticket_id': ticket_id,
            'refresh_checklist': True
        })

        result = await executor.execute_ticket(ticket_id, project_id)
        results.append(result)

        executor.broadcast_notification({
            'is_notification': True,
            'notification_type': 'toolhistory',
            'function_name': 'ticket_execution_queue',
            'status': result.get('status'),
            'message': f"Ticket #{ticket_id} finished with status: {result.get('status')}",
            'ticket_id': ticket_id,
            'refresh_checklist': True
        })

        if result.get("status") == "error":
            break

    failed_tickets = len([r for r in results if r.get("status") in {"error", "failed", "timeout"}])
    executor.broadcast_notification({
        'is_notification': True,
        'notification_type': 'toolhistory',
        'function_name': 'ticket_execution_queue',
        'status': 'completed' if failed_tickets == 0 else 'partial',
        'message': f"Ticket execution batch finished. Success: {len([r for r in results if r.get('status') == 'success'])}, Issues: {failed_tickets}.",
        'refresh_checklist': True
    })

    return {
        "batch_status": "completed" if failed_tickets == 0 else "partial",
        "total_tickets": len(ticket_ids),
        "completed_tickets": len([r for r in results if r.get("status") == "success"]),
        "failed_tickets": failed_tickets,
        "results": results
    }


# Synchronous wrapper for batch execution
def batch_execute_tickets_claude_sdk_sync(
    ticket_ids: List[int],
    project_id: int,
    conversation_id: int
) -> Dict[str, Any]:
    """
    Synchronous wrapper for batch ticket execution using Claude SDK.

    Args:
        ticket_ids: List of ticket IDs to execute
        project_id: The project ID
        conversation_id: The conversation ID

    Returns:
        Dict with batch execution results
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(
            batch_execute_tickets_claude_sdk(ticket_ids, project_id, conversation_id)
        )
        return result
    finally:
        loop.close()


# Export the main function as a drop-in replacement
execute_ticket_implementation = execute_ticket_implementation_claude_sdk
batch_execute_tickets = batch_execute_tickets_claude_sdk_sync