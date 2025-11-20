"""
Task Definitions

Add your custom task functions here. Each task function should:
1. Accept the necessary parameters
2. Return a dictionary with the result
3. Handle exceptions appropriately
4. Use logging for debugging

Example structure:

def your_task_function(param1: str, param2: int) -> dict:
    '''
    Your task description.
    
    Args:
        param1: Description of parameter 1
        param2: Description of parameter 2
        
    Returns:
        Dict with task result
    '''
    import logging
    import time
    
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Starting task with {param1} and {param2}")
        
        # Your task logic here
        time.sleep(1)  # Simulate work
        
        result = {
            'status': 'success',
            'param1': param1,
            'param2': param2,
            'completed_at': time.time()
        }
        
        logger.info(f"Task completed: {result}")
        return result
        
    except Exception as e:
        error_msg = f"Task failed: {str(e)}"
        logger.error(error_msg)
        return {'status': 'error', 'error': error_msg}
"""

# Add your task functions below this line

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
import os
from contextvars import ContextVar

from channels.layers import get_channel_layer
from django.conf import settings
from django.db import transaction
from asgiref.sync import sync_to_async, async_to_sync

from projects.models import ProjectTicket, Project
from factory.ai_providers import get_ai_response
from factory.ai_functions import new_dev_sandbox_tool, _fetch_workspace, get_magpie_client, _slugify_project_name, MAGPIE_BOOTSTRAP_SCRIPT
from factory.prompts.builder_prompt import get_system_builder_mode
from factory.ai_tools import tools_builder
from development.models import MagpieWorkspace
import time

# Context variables to store execution context
current_ticket_id: ContextVar[Optional[int]] = ContextVar('current_ticket_id', default=None)
current_workspace_id: ContextVar[Optional[str]] = ContextVar('current_workspace_id', default=None)

logger = logging.getLogger(__name__)


def broadcast_ticket_notification(conversation_id: Optional[int], payload: Dict[str, Any]) -> None:
    if not conversation_id:
        return
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    event = {
        'type': 'ai_response_chunk',
        'chunk': '',
        'is_final': False,
        'conversation_id': conversation_id,
    }
    event.update(payload)
    event.setdefault('is_notification', True)
    event.setdefault('notification_marker', "__NOTIFICATION__")
    try:
        async_to_sync(channel_layer.group_send)(f"conversation_{conversation_id}", event)
    except Exception as exc:
        logger.error(f"Failed to broadcast ticket notification: {exc}")


def simple_test_task_for_debugging(message: str, delay: int = 1) -> dict:
    """
    A simple test task to verify Django-Q functionality without complex operations.
    This helps isolate the timer issue from the complex ticket implementation logic.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Simple test task started: {message}")
    
    try:
        # Simulate some work without complex Django operations
        time.sleep(delay)
        
        result = {
            'status': 'success',
            'message': message,
            'timestamp': time.time(),
            'delay': delay,
            'worker_info': {
                'process_id': os.getpid(),
                'working_directory': os.getcwd()
            }
        }
        
        logger.info(f"Simple test task completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error in simple test task: {str(e)}")
        return {
            'status': 'error',
            'message': str(e),
            'timestamp': time.time()
        }


def safe_execute_ticket_implementation(ticket_id: int, project_id: int, conversation_id: int) -> Dict[str, Any]:
    """
    A safer version of execute_ticket_implementation that reduces complexity to prevent timer issues.
    This version does minimal operations and delegates complex work to synchronous mode.
    """
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Starting SAFE implementation of ticket {ticket_id}")
        
        # Simple task simulation for now
        time.sleep(2)  # Simulate work
        
        # Update ticket status with minimal Django operations
        from projects.models import ProjectTicket
        
        ticket = ProjectTicket.objects.get(id=ticket_id)
        ticket.status = 'done'  # Mark as done when execution completes
        ticket.save()
        
        logger.info(f"Successfully completed SAFE implementation of ticket {ticket_id}")
        
        return {
            "status": "success",
            "ticket_id": ticket_id,
            "message": f"SAFE implementation completed for ticket {ticket_id}",
            "completion_time": datetime.now().isoformat(),
            "worker_info": {
                "process_id": os.getpid(),
                "working_directory": os.getcwd()
            }
        }
        
    except Exception as e:
        logger.error(f"Error in SAFE ticket implementation {ticket_id}: {str(e)}")
        
        return {
            "status": "error",
            "ticket_id": ticket_id,
            "error": str(e),
            "completion_time": datetime.now().isoformat()
        }

import json
import time
import logging
from datetime import datetime
from typing import Dict, Any, List
from django.db import models
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


def execute_ticket_implementation(ticket_id: int, project_id: int, conversation_id: int, max_execution_time: int = 600) -> Dict[str, Any]:
    """
    Execute a single ticket implementation - streamlined version with timeout protection.
    Works like Claude Code CLI - fast, efficient, limited tool rounds.

    Args:
        ticket_id: The ID of the ProjectTicket ticket
        project_id: The ID of the project
        conversation_id: The ID of the conversation
        max_execution_time: Maximum execution time in seconds (default: 300s/5min)

    Returns:
        Dict with execution results and status
    """
    # Set the current ticket_id in context for tool functions to access
    current_ticket_id.set(ticket_id)
    logger.info(f"\n{'='*80}\n[TASK START] Ticket #{ticket_id} | Project #{project_id} | Conv #{conversation_id}\n{'='*80}")

    start_time = time.time()
    workspace_id = None

    try:
        logger.info(f"\n[STEP 1/10] Fetching ticket and project data...")
        # 1. GET TICKET AND PROJECT
        ticket = ProjectTicket.objects.get(id=ticket_id)
        project = Project.objects.get(id=project_id)
        logger.info(f"[STEP 1/10] ✓ Ticket: '{ticket.name}' | Project: '{project.name}'")

        logger.info(f"\n[STEP 2/10] Checking if ticket already completed...")
        # 2. CHECK IF ALREADY COMPLETED (prevent duplicate execution on retry)
        if ticket.status == 'done':
            logger.info(f"[STEP 2/10] ⊘ Ticket already completed, skipping")
            return {
                "status": "success",
                "ticket_id": ticket_id,
                "message": "Already completed",
                "skipped": True
            }
        logger.info(f"[STEP 2/10] ✓ Ticket status: {ticket.status}, proceeding...")

        logger.info(f"\n[STEP 3/10] Updating ticket status to in_progress...")
        # 3. UPDATE STATUS TO IN-PROGRESS
        ticket.status = 'in_progress'
        ticket.save(update_fields=['status'])
        logger.info(f"[STEP 3/10] ✓ Ticket #{ticket_id} marked as in_progress")
        
        # 4. BROADCAST START
        broadcast_ticket_notification(conversation_id, {
            'is_notification': True,
            'notification_type': 'toolhistory',
            'function_name': 'ticket_execution',
            'status': 'in_progress',
            'message': f"Working on ticket #{ticket.id}: {ticket.name}",
            'ticket_id': ticket.id,
            'ticket_name': ticket.name,
            'refresh_checklist': True
        })

        logger.info(f"\n[STEP 4/10] Broadcasting start notification...")

        logger.info(f"\n[STEP 5/10] Fetching or creating workspace...")
        # 5. GET OR CREATE WORKSPACE
        workspace = async_to_sync(_fetch_workspace)(project=project, conversation_id=conversation_id)

        if not workspace:
            logger.info(f"[STEP 5/10] No existing workspace found, creating new one...")
            # Create new Magpie workspace
            try:
                client = get_magpie_client()
                project_name = project.provided_name or project.name
                slug = _slugify_project_name(project_name)
                workspace_name = f"{slug}-{project.id}"

                response = client.jobs.create(
                    name=workspace_name,
                    script=MAGPIE_BOOTSTRAP_SCRIPT,
                    persist=True,
                    ip_lease=True,
                    stateful=True,
                    workspace_size_gb=10,
                    vcpus=2,
                    memory_mb=2048,
                )
                logger.info(f"[MAGPIE][CREATE] job response: {response}")

                run_id = response.get("request_id")
                workspace_identifier = run_id

                workspace = MagpieWorkspace.objects.create(
                    project=project,
                    conversation_id=str(conversation_id) if conversation_id else None,
                    job_id=run_id,
                    workspace_id=workspace_identifier,
                    status='provisioning',
                    metadata={'project_name': project_name}
                )

                # Wait for VM to be ready with IP address (polls internally)
                logger.info(f"[MAGPIE][POLL] Waiting for VM to be ready with IP address...")
                vm_info = client.jobs.get_vm_info(run_id, poll_timeout=120, poll_interval=5)

                ipv6 = vm_info.get("ip_address")
                if not ipv6:
                    raise Exception(f"VM provisioning timed out - no IP address received")

                workspace.mark_ready(ipv6=ipv6, project_path='/workspace')
                logger.info(f"[MAGPIE][READY] Workspace ready: {workspace.workspace_id}, IP: {ipv6}")
            except Exception as e:
                raise Exception(f"Workspace provisioning failed: {str(e)}")

        workspace_id = workspace.workspace_id
        logger.info(f"[STEP 5/10] ✓ Workspace ready: {workspace_id}")

        # Set workspace_id in context so tools can access it
        current_workspace_id.set(workspace_id)
        logger.info(f"[STEP 5/10] ✓ Set workspace_id in context: {workspace_id}")

        logger.info(f"\n[STEP 6/10] Setting up dev sandbox...")
        # 5b. SETUP DEV SANDBOX (only if not already initialized)
        workspace_metadata = workspace.metadata or {}
        if not workspace_metadata.get('sandbox_initialized'):
            logger.info(f"[STEP 6/10] Initializing dev sandbox for workspace {workspace_id}...")
            sandbox_result = async_to_sync(new_dev_sandbox_tool)(
                {'workspace_id': workspace_id},
                project.project_id,
                conversation_id
            )

            if sandbox_result.get('status') == 'failed':
                raise Exception(f"Dev sandbox setup failed: {sandbox_result.get('message_to_agent')}")
            logger.info(f"[STEP 6/10] ✓ Dev sandbox initialized")
        else:
            logger.info(f"[STEP 6/10] ⊘ Skipping - dev sandbox already initialized")

        logger.info(f"\n[STEP 7/10] Fetching project documentation...")
        # 6. FETCH PROJECT DOCUMENTATION (PRD & Implementation)
        project_context = ""
        try:
            from projects.models import ProjectFile

            # Fetch PRD files
            prd_files = ProjectFile.objects.filter(
                project=project,
                file_type='prd',
                is_active=True
            ).order_by('-updated_at')[:2]  # Get up to 2 most recent PRDs

            # Fetch implementation files
            impl_files = ProjectFile.objects.filter(
                project=project,
                file_type='implementation',
                is_active=True
            ).order_by('-updated_at')[:2]  # Get up to 2 most recent implementation docs

            if prd_files or impl_files:
                project_context = "\n\n📋 PROJECT DOCUMENTATION:\n"

                for prd in prd_files:
                    project_context += f"\n--- PRD: {prd.name} ---\n"
                    project_context += prd.file_content[:5000]  # Limit to 5000 chars per file
                    if len(prd.file_content) > 5000:
                        project_context += "\n...(truncated for brevity)\n"
                    project_context += "\n"

                for impl in impl_files:
                    project_context += f"\n--- Technical Implementation: {impl.name} ---\n"
                    project_context += impl.file_content[:5000]  # Limit to 5000 chars per file
                    if len(impl.file_content) > 5000:
                        project_context += "\n...(truncated for brevity)\n"
                    project_context += "\n"

                logger.info(f"[STEP 7/10] ✓ Added {len(prd_files)} PRDs, {len(impl_files)} implementation docs to context")
            else:
                logger.info(f"[STEP 7/10] ⊘ No project documentation found")
        except Exception as e:
            logger.warning(f"[STEP 7/10] ⚠ Could not fetch project documentation: {str(e)}")

        implementation_prompt = f"""
You are implementing ticket #{ticket.id}: {ticket.name}

TICKET DESCRIPTION:
{ticket.description}

PROJECT PATH: nextjs-app
{project_context}

✅ Success case: "IMPLEMENTATION_STATUS: COMPLETE - [brief summary of what you did]"
❌ Failure case: "IMPLEMENTATION_STATUS: FAILED - [reason]"
"""
        system_prompt = """
You are expert developer assigned to work on a development ticket. You will follow these steps

1. Check if the ticket has todolist. If no, then create new todo list. If todos exist, then continue from pending ones. 
2. Build the todolist one by one, and complete the project in minimal shell commands. Mandatory. 

3. Start by checking the agent.md file. Note you will keep update all the important changes to agents.md
You can check the status of the project using shell commands. Batch multiple checks in a single command.
eg. ls -la && cat .... && grep ....  cat ....
Keep the checks to minimum and don't loop around. Usually agent.md will have all the information.

4. Create all the required files to complete the tasks
5. Install the libraries

6. Mark the todo as done when it is completed

🎯 COMPLETION CRITERIA:
- Project runs with npm run dev (Do no build the Project)
- All the todos are completed
- Todos are marked done

DO NOT verify extensively or test in loops.
You can skip writing explainer documentation.

Note: whenever a TODO item is completed, make sure to mark the TODO as done.

End with: "IMPLEMENTATION_STATUS: COMPLETE - [specific changes made]" or "IMPLEMENTATION_STATUS: FAILED - [reason]"
        """

        logger.info(f"\n[STEP 8/10] Calling AI for ticket implementation...")
        logger.info(f"[STEP 8/10] Max execution time: {max_execution_time}s | Elapsed: {time.time() - start_time:.1f}s")
        # 8. CALL AI WITH TIMEOUT PROTECTION

        # Wrap AI call with timeout check
        ai_call_start = time.time()
        try:
            ai_response = async_to_sync(get_ai_response)(
                user_message=implementation_prompt,
                system_prompt=system_prompt,
                project_id=project.project_id,  # Use UUID, not database ID
                conversation_id=conversation_id,
                stream=False,
                tools=tools_builder
            )
            ai_call_duration = time.time() - ai_call_start
            logger.info(f"[STEP 8/10] ✓ AI call completed in {ai_call_duration:.1f}s")
        except Exception as ai_error:
            # Handle API errors (500s, timeouts, etc.) - no retry, just fail
            logger.error(f"[STEP 8/10] ✗ AI call failed: {str(ai_error)}")
            raise Exception(f"AI API error: {str(ai_error)}")

        content = ai_response.get('content', '') if ai_response else ''
        execution_time = time.time() - start_time

        # Log the AI response for debugging
        logger.info(f"[STEP 8/10] AI response length: {len(content)} chars")
        logger.info(f"[STEP 8/10] Total elapsed time: {execution_time:.1f}s")

        # Check if AI response indicates an error (500, overloaded, etc.)
        has_api_error = ai_response.get('error') if ai_response else False
        error_message = ai_response.get('error_message', '') if ai_response else ''

        # Check for timeout
        if execution_time > max_execution_time:
            raise Exception(f"Execution timeout after {execution_time:.2f}s (max: {max_execution_time}s)")

        # If there was an API error, treat as failed
        if has_api_error:
            raise Exception(f"AI API error during execution: {error_message}")

        logger.info(f"\n[STEP 9/10] Checking AI completion status...")
        # 8. CHECK COMPLETION STATUS (with fallback detection)
        completed = 'IMPLEMENTATION_STATUS: COMPLETE' in content
        failed = 'IMPLEMENTATION_STATUS: FAILED' in content

        # Fallback: If no explicit status, ticket is NOT complete
        # Only mark as complete if there's an explicit success status
        if not completed and not failed:
            logger.warning(f"[STEP 9/10] ⚠ No explicit completion status found in AI response")
            logger.warning(f"[STEP 9/10] Content length: {len(content)} chars")
            # ALWAYS mark as failed if no explicit completion status
            # The AI MUST provide explicit status - anything else is incomplete
            failed = True
            logger.error("[STEP 9/10] ✗ Marking as FAILED - AI must end with IMPLEMENTATION_STATUS")

        logger.info(f"[STEP 9/10] Status check - Completed: {completed} | Failed: {failed} | Time: {execution_time:.1f}s")
        
        # 9. EXTRACT WHAT WAS DONE (for logging)
        import re
        files_created = re.findall(r'cat > (nextjs-app/[\w\-\./]+)', content)
        deps_installed = re.findall(r'npm install ([\w\-\s@/]+)', content)
        dependencies = []
        for dep_string in deps_installed:
            dependencies.extend(dep_string.split())

        # Count tool executions from content
        tool_calls_count = content.count('ssh_command') + content.count('Tool call')
        logger.info(f"Estimated tool calls: {tool_calls_count}, Files created: {len(files_created)}, Dependencies: {len(dependencies)}")

        logger.info(f"\n[STEP 10/10] Updating ticket status and saving results...")
        # 10. UPDATE TICKET BASED ON RESULT
        if completed and not failed:
            # SUCCESS!
            logger.info(f"[STEP 10/10] ✓ SUCCESS - Marking ticket as done")
            ticket.status = 'done'
            ticket.notes = f"""
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] IMPLEMENTATION COMPLETED
Time: {execution_time:.2f} seconds
Files created: {len(files_created)}
Dependencies: {', '.join(set(dependencies))}
Status: ✓ Complete
"""
            ticket.save(update_fields=['status', 'notes'])
            
            broadcast_ticket_notification(conversation_id, {
                'is_notification': True,
                'notification_type': 'toolhistory',
                'function_name': 'ticket_execution',
                'status': 'completed',
                'message': f"✓ Completed ticket #{ticket.id}: {ticket.name}",
                'ticket_id': ticket.id,
                'ticket_name': ticket.name,
                'refresh_checklist': True
            })

            logger.info(f"[STEP 10/10] ✓ Task completed successfully in {execution_time:.1f}s")
            logger.info(f"{'='*80}\n[TASK END] SUCCESS - Ticket #{ticket_id}\n{'='*80}\n")

            return {
                "status": "success",
                "ticket_id": ticket_id,
                "ticket_name": ticket.name,
                "message": f"Ticket completed in {execution_time:.2f}s",
                "execution_time": f"{execution_time:.2f}s",
                "files_created": files_created,
                "dependencies": list(set(dependencies)),
                "workspace_id": workspace_id,
                "completion_time": datetime.now().isoformat()
            }
        else:
            # FAILED OR INCOMPLETE
            logger.warning(f"[STEP 10/10] ✗ FAILED - Marking ticket as failed")
            error_match = re.search(r'IMPLEMENTATION_STATUS: FAILED - (.+)', content)
            if error_match:
                error_reason = error_match.group(1)
            elif not content or len(content) < 100:
                error_reason = "AI response was empty or incomplete. Possible API timeout or error."
            else:
                error_reason = "No explicit completion status provided. AI may have exceeded tool limit or stopped unexpectedly."

            ticket.status = 'failed'
            ticket.notes = f"""
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] IMPLEMENTATION FAILED
Time: {execution_time:.2f} seconds
Tool calls: ~{tool_calls_count}
Files attempted: {len(files_created)}
Error: {error_reason}
Workspace: {workspace_id}
Manual intervention required
"""
            ticket.save(update_fields=['status', 'notes'])
            
            broadcast_ticket_notification(conversation_id, {
                'is_notification': True,
                'notification_type': 'toolhistory',
                'function_name': 'ticket_execution',
                'status': 'failed',
                'message': f"✗ Failed ticket #{ticket.id}: {error_reason}",
                'ticket_id': ticket.id,
                'ticket_name': ticket.name,
                'refresh_checklist': True
            })

            logger.info(f"{'='*80}\n[TASK END] FAILED - Ticket #{ticket_id}\n{'='*80}\n")

            return {
                "status": "failed",
                "ticket_id": ticket_id,
                "ticket_name": ticket.name,
                "error": error_reason,
                "execution_time": f"{execution_time:.2f}s",
                "workspace_id": workspace_id,
                "requires_manual_intervention": True
            }

    except Exception as e:
        # EXCEPTION HANDLING - NO RETRIES
        execution_time = time.time() - start_time
        error_msg = str(e)
        logger.error(f"\n{'='*80}\n[EXCEPTION] Critical error in ticket {ticket_id}\n{'='*80}")
        logger.error(f"Error: {error_msg}", exc_info=True)
        logger.error(f"Elapsed time: {execution_time:.1f}s")

        if 'ticket' in locals():
            # Mark ticket as failed - no retry logic
            ticket.status = 'failed'
            ticket.notes = f"""
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] EXECUTION FAILED
Error: {error_msg}
Time: {execution_time:.2f}s
Workspace: {workspace_id or 'N/A'}
Manual intervention required
"""
            ticket.save(update_fields=['status', 'notes'])

            broadcast_ticket_notification(conversation_id, {
                'is_notification': True,
                'notification_type': 'toolhistory',
                'function_name': 'ticket_execution',
                'status': 'failed',
                'message': f"✗ Ticket #{ticket.id} error: {error_msg[:100]}",
                'ticket_id': ticket.id,
                'ticket_name': ticket.name,
                'refresh_checklist': True
            })

        # Return error without re-raising (prevents Django-Q retry loops)
        logger.error(f"{'='*80}\n[TASK END] ERROR - Ticket #{ticket_id}\n{'='*80}\n")
        return {
            "status": "error",
            "ticket_id": ticket_id,
            "error": error_msg,
            "workspace_id": workspace_id,
            "execution_time": f"{execution_time:.2f}s"
        }

def batch_execute_tickets(ticket_ids: List[int], project_id: int, conversation_id: int) -> Dict[str, Any]:
    """
    Execute multiple tickets in sequence.
    
    This is useful when tickets have dependencies and need to be executed
    in a specific order.
    
    Args:
        ticket_ids: List of ticket IDs to execute
        project_id: The project ID
        conversation_id: The conversation ID
        
    Returns:
        Dict with batch execution results
    """
    results = []

    broadcast_ticket_notification(conversation_id, {
        'is_notification': True,
        'notification_type': 'toolhistory',
        'function_name': 'ticket_execution_queue',
        'status': 'queued',
        'message': f"Starting background execution for {len(ticket_ids)} tickets.",
        'refresh_checklist': bool(ticket_ids)
    })
    
    for index, ticket_id in enumerate(ticket_ids, start=1):
        broadcast_ticket_notification(conversation_id, {
            'is_notification': True,
            'notification_type': 'toolhistory',
            'function_name': 'ticket_execution_queue',
            'status': 'in_progress',
            'message': f"Executing ticket {index}/{len(ticket_ids)} (#{ticket_id}).",
            'ticket_id': ticket_id,
            'refresh_checklist': True
        })

        result = execute_ticket_implementation(ticket_id, project_id, conversation_id)
        results.append(result)

        broadcast_ticket_notification(conversation_id, {
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
    broadcast_ticket_notification(conversation_id, {
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


def ensure_workspace_and_execute(ticket_ids: List[int], project_db_id: int, conversation_id: Optional[int]) -> Dict[str, Any]:
    try:
        project = Project.objects.get(id=project_db_id)
    except Project.DoesNotExist:
        return {
            "status": "error",
            "message": f"Project with id {project_db_id} does not exist"
        }

    broadcast_ticket_notification(conversation_id, {
        'is_notification': True,
        'notification_type': 'toolhistory',
        'function_name': 'ticket_execution_queue',
        'status': 'queued',
        'message': "Ensuring Magpie workspace is available...",
        'refresh_checklist': bool(ticket_ids)
    })

    # Get or create workspace
    workspace = None
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        workspace = loop.run_until_complete(_fetch_workspace(project=project, conversation_id=conversation_id))

        if not workspace:
            # Create new Magpie workspace
            try:
                client = get_magpie_client()
                project_name = project.provided_name or project.name
                slug = _slugify_project_name(project_name)
                workspace_name = f"{slug}-{project.id}"

                response = client.jobs.create(
                    name=workspace_name,
                    script=MAGPIE_BOOTSTRAP_SCRIPT,
                    persist=True,
                    ip_lease=True,
                    stateful=True,
                    workspace_size_gb=10,
                    vcpus=2,
                    memory_mb=2048,
                )
                logger.info(f"[MAGPIE][CREATE] job response: {response}")

                run_id = response.get("request_id")
                workspace_identifier = run_id

                workspace = MagpieWorkspace.objects.create(
                    project=project,
                    conversation_id=str(conversation_id) if conversation_id else None,
                    job_id=run_id,
                    workspace_id=workspace_identifier,
                    status='provisioning',
                    metadata={'project_name': project_name}
                )

                # Wait for VM to be ready with IP address (polls internally)
                logger.info(f"[MAGPIE][POLL] Waiting for VM to be ready with IP address...")
                vm_info = client.jobs.get_vm_info(run_id, poll_timeout=120, poll_interval=5)

                ipv6 = vm_info.get("ip_address")
                if not ipv6:
                    raise Exception(f"VM provisioning timed out - no IP address received")

                workspace.mark_ready(ipv6=ipv6, project_path='/workspace')
                logger.info(f"[MAGPIE][READY] Workspace ready: {workspace.workspace_id}, IP: {ipv6}")
            except Exception as e:
                broadcast_ticket_notification(conversation_id, {
                    'is_notification': True,
                    'notification_type': 'toolhistory',
                    'function_name': 'ticket_execution_queue',
                    'status': 'failed',
                    'message': f"Workspace provisioning failed: {str(e)}",
                    'refresh_checklist': False
                })
                return {
                    "status": "error",
                    "message": f"Workspace provisioning failed: {str(e)}"
                }

        # Setup dev sandbox
        sandbox_result = loop.run_until_complete(
            new_dev_sandbox_tool(
                {'workspace_id': workspace.workspace_id},
                project.project_id,
                conversation_id
            )
        )
    finally:
        asyncio.set_event_loop(None)
        loop.close()

    if isinstance(sandbox_result, dict) and sandbox_result.get('status') == 'failed':
        broadcast_ticket_notification(conversation_id, {
            'is_notification': True,
            'notification_type': 'toolhistory',
            'function_name': 'ticket_execution_queue',
            'status': 'failed',
            'message': f"Dev sandbox setup failed: {sandbox_result.get('message_to_agent') or sandbox_result.get('message')}",
            'refresh_checklist': False
        })
        return {
            "status": "error",
            "message": sandbox_result.get('message_to_agent') or sandbox_result.get('message') or 'Dev sandbox setup failed'
        }

    broadcast_ticket_notification(conversation_id, {
        'is_notification': True,
        'notification_type': 'toolhistory',
        'function_name': 'ticket_execution_queue',
        'status': 'completed',
        'message': "Workspace ready. Beginning ticket execution...",
        'refresh_checklist': False
    })

    return batch_execute_tickets(ticket_ids, project_db_id, conversation_id)


def check_ticket_dependencies(ticket_id: int) -> bool:
    """
    Check if all dependencies for a ticket are completed.
    
    Args:
        ticket_id: The ticket ID to check
        
    Returns:
        bool: True if all dependencies are met, False otherwise
    """
    from projects.models import ProjectTicket
    
    try:
        ticket = ProjectTicket.objects.get(id=ticket_id)
        
        # For now, we'll implement a simple priority-based dependency
        # High priority tickets should be done before medium/low
        if ticket.priority.lower() in ['medium', 'low']:
            # Check if there are any high priority tickets still pending
            high_priority_pending = ProjectTicket.objects.filter(
                project=ticket.project,
                status='open',
                priority='High',
                role='agent'
            ).exists()
            
            if high_priority_pending:
                return False
        
        return True
        
    except ProjectTicket.DoesNotExist:
        return False


def monitor_ticket_progress(project_id: int) -> Dict[str, Any]:
    """
    Monitor the progress of all tickets in a project.
    
    Args:
        project_id: The project ID
        
    Returns:
        Dict with project ticket statistics
    """
    from projects.models import ProjectTicket
    
    tickets = ProjectTicket.objects.filter(project_id=project_id)
    
    stats = {
        "total_tickets": tickets.count(),
        "open_tickets": tickets.filter(status='open').count(),
        "in_progress_tickets": tickets.filter(status='in_progress').count(),
        "done_tickets": tickets.filter(status='done').count(),
        "failed_tickets": tickets.filter(status='failed').count(),
        "agent_tickets": tickets.filter(role='agent').count(),
        "user_tickets": tickets.filter(role='user').count(),
        "by_priority": {
            "high": tickets.filter(priority='High').count(),
            "medium": tickets.filter(priority='Medium').count(),
            "low": tickets.filter(priority='Low').count()
        }
    }
    
    return stats


def parallel_ticket_executor(project_id: int, conversation_id: int, max_workers: int = 3) -> Dict[str, Any]:
    """
    Execute multiple independent tickets in parallel using Django-Q.
    
    This function identifies tickets that can be run in parallel (no dependencies)
    and queues them for concurrent execution.
    
    Args:
        project_id: The project ID
        conversation_id: The conversation ID
        max_workers: Maximum number of parallel workers
        
    Returns:
        Dict with parallel execution status
    """
    from projects.models import ProjectTicket
    from tasks.task_manager import TaskManager
    
    task_manager = TaskManager()
    
    try:
        # Get all open tickets that can be executed by agents
        open_tickets = ProjectTicket.objects.filter(
            project_id=project_id,
            status='open',
            role='agent'
        ).order_by('priority', 'id')
        
        # Group tickets by priority for parallel execution
        high_priority = []
        medium_priority = []
        low_priority = []
        
        for ticket in open_tickets:
            if ticket.priority == 'High':
                high_priority.append(ticket.id)
            elif ticket.priority == 'Medium':
                medium_priority.append(ticket.id)
            else:
                low_priority.append(ticket.id)
        
        queued_tasks = []
        
        # Queue high priority tickets first (in parallel)
        for ticket_id in high_priority[:max_workers]:
            task_id = task_manager.publish_task(
                'tasks.task_definitions.execute_ticket_implementation',
                ticket_id, project_id, conversation_id,  # Pass args directly
                task_name=f'Ticket_{ticket_id}_High_Priority',
                group=f'project_{project_id}_high'
            )
            queued_tasks.append({
                'ticket_id': ticket_id,
                'task_id': task_id,
                'priority': 'High'
            })
        
        # Queue medium priority tickets (after high priority completes)
        for ticket_id in medium_priority[:max_workers]:
            if check_ticket_dependencies(ticket_id):
                task_id = task_manager.publish_task(
                    'tasks.task_definitions.execute_ticket_implementation',
                    ticket_id, project_id, conversation_id,  # Pass args directly
                    task_name=f'Ticket_{ticket_id}_Medium_Priority',
                    group=f'project_{project_id}_medium'
                )
                queued_tasks.append({
                    'ticket_id': ticket_id,
                    'task_id': task_id,
                    'priority': 'Medium'
                })
        
        return {
            "status": "success",
            "queued_tasks": queued_tasks,
            "total_queued": len(queued_tasks),
            "message": f"Queued {len(queued_tasks)} tickets for parallel execution"
        }
        
    except Exception as e:
        logger.error(f"Error in parallel ticket executor: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "queued_tasks": []
        } 
