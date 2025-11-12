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
from datetime import datetime
from typing import Dict, Any, Optional, List
import os

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import transaction
from asgiref.sync import sync_to_async, async_to_sync

from projects.models import ProjectChecklist, Project
from factory.ai_providers import get_ai_response
from factory.ai_functions import provision_vibe_workspace_tool
from factory.prompts.builder_prompt import get_system_builder_mode
from factory.ai_tools import tools_builder
import time

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
        from projects.models import ProjectChecklist
        
        ticket = ProjectChecklist.objects.get(id=ticket_id)
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


def execute_ticket_implementation(ticket_id: int, project_id: int, conversation_id: int, max_execution_time: int = 300) -> Dict[str, Any]:
    """
    Execute a single ticket implementation - streamlined version with timeout protection.
    Works like Claude Code CLI - fast, efficient, limited tool rounds.

    Args:
        ticket_id: The ID of the ProjectChecklist ticket
        project_id: The ID of the project
        conversation_id: The ID of the conversation
        max_execution_time: Maximum execution time in seconds (default: 300s/5min)

    Returns:
        Dict with execution results and status
    """
    start_time = time.time()
    workspace_id = None

    try:
        # 1. GET TICKET AND PROJECT
        ticket = ProjectChecklist.objects.get(id=ticket_id)
        project = Project.objects.get(id=project_id)

        # 2. CHECK IF ALREADY COMPLETED (prevent duplicate execution on retry)
        if ticket.status == 'done':
            logger.info(f"Ticket #{ticket_id} already completed, skipping")
            return {
                "status": "success",
                "ticket_id": ticket_id,
                "message": "Already completed",
                "skipped": True
            }

        # 3. UPDATE STATUS TO IN-PROGRESS
        ticket.status = 'in_progress'
        ticket.save(update_fields=['status'])
        logger.info(f"Starting ticket #{ticket_id}: {ticket.name}")
        
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

        # 5. GET WORKSPACE
        workspace_result = async_to_sync(provision_vibe_workspace_tool)(
            {
                'project_name': project.provided_name or project.name,
                'summary': project.description or 'Ticket implementation workspace'
            },
            project.project_id,
            conversation_id
        )

        if workspace_result.get('status') == 'failed':
            raise Exception(f"Workspace provisioning failed: {workspace_result.get('message_to_agent')}")

        workspace_id = workspace_result.get('workspace_id')
        logger.info(f"Workspace ready: {workspace_id}")

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

                logger.info(f"Added project documentation to context: {len(prd_files)} PRDs, {len(impl_files)} implementation docs")
        except Exception as e:
            logger.warning(f"Could not fetch project documentation: {str(e)}")

        # 7. EXECUTE IMPLEMENTATION WITH LIMITED TOOL ROUNDS
        # Check if ticket has notes from a previous failed attempt
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

        implementation_prompt = f"""
You are implementing ticket #{ticket.id}: {ticket.name}

TICKET DESCRIPTION:
{ticket.description}

WORKSPACE: {workspace_id}
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
- Maximum 100 tool calls
"""

        system_prompt = """
You are an expert developer working on assigned tickets. You will implement tickets with surgical precision.

Remember that you are working on an existing project, and every ticket is a TARGETED change on the existing codebase.

🔍 MANDATORY FIRST STEP - ALWAYS CHECK STATE:
Before EVERY ticket implementation, you MUST:
1. Make sure the parent folder is /workspace/nextjs-app/
1. Read the codebase using `ls -la` and `cat` and `grep` (see what exists and read the code)
3. Assess what already exists vs what needs to be done
4. This is NOT optional - you MUST check before doing any work!

Plan once. No loops. No tests. No builds. Minimal edits.

Phases: ANALYZE → APPLY → RUN → REPORT. No going backwards.

1. In the planning phase, understand and list all the libraries that need to be installed. Install them at once.
2. Understand all the files that need to be created at once. Create them in a single command. 
3. Understand all the edits that need to be made. Make the edits in a single command.
4. Run the app (npm run dev), and check for errors. 
5. If errors, then fix them and hand over control. 
6. Do not attempt to build the project (no npm build). Just the `npm run dev` and leave it at that, so that the user can test it.

Remember that there is another QA agent which can test and fix for any issues. 

IMPORTANT: 
- You can read multiple files in a single command
- Identify and create multiple files in a single command. This will help save the tool calls. 
- If required, then edit multiple files in a single command

End with: "IMPLEMENTATION_STATUS: COMPLETE - [specific changes made]" or "IMPLEMENTATION_STATUS: FAILED - [reason]"
"""

        # System prompt with strict completion requirements
        system_prompt_ = """
You are an expert developer working on an EXISTING codebase. You implement tickets with surgical precision.

FUNDAMENTAL PRINCIPLE: You are working on an EXISTING PROJECT. Every ticket is a TARGETED change to this existing codebase.

🔍 MANDATORY FIRST STEP - ALWAYS CHECK STATE:
Before EVERY ticket implementation, you MUST:
1. Make sure the parent folder is /workspace/nextjs-app/
1. Read the codebase using `ls -la` and `cat` and `grep` (see what exists and read the code)
3. Assess what already exists vs what needs to be done
4. This is NOT optional - you MUST check before doing any work!

YOUR APPROACH (Like Claude Code):
1. CHECK FIRST: Always check workspace state before making changes
2. UNDERSTAND: Read and analyze existing code when the ticket involves modifications
3. MINIMAL CHANGES: Make ONLY the changes required by the ticket
4. PRESERVE EXISTING: Never recreate files or structures that already exist
5. TARGETED FIXES: For bugs, fix only the specific issue; for features, add only what's needed
6. SKIP TESTING: Just make sure the files are there, then run the project and let the user know. 
    Another testing agent will check and confirm the results

Do not keep repeating the process

1. Read code 
2. Install all the needed packages
3. Create code as needed: write new files or edit existing ones. Make sure to create all the files first
4. Run the code. If any errors, fix them. Them run the code and hand over.
5. End with: "IMPLEMENTATION_STATUS: COMPLETE - [specific changes made]" or "IMPLEMENTATION_STATUS: FAILED - [reason]"
6. The status message is MANDATORY - you must provide it after tools finish

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

Very simple flow:
1. Read and analysis requirements
2. Install the libraries
3. Create files: if required create multiple files at once. Make sure to batch multiple files together to save time. 
4. Run and check for errors
5. Then hand over control.
6. Don't overcomplicate and keep checking and testing for things.

Run the server and hand over controll
"""

        # 8. CALL AI WITH TIMEOUT PROTECTION
        logger.info("Calling AI for implementation...")

        # Wrap AI call with timeout check
        try:
            ai_response = async_to_sync(get_ai_response)(
                user_message=implementation_prompt,
                system_prompt=system_prompt,
                project_id=project.project_id,  # Use UUID, not database ID
                conversation_id=conversation_id,
                stream=False,
                tools=tools_builder
            )
        except Exception as ai_error:
            # Handle API errors (500s, timeouts, etc.)
            logger.error(f"AI call failed: {str(ai_error)}")
            if "500" in str(ai_error) or "Internal server error" in str(ai_error):
                raise Exception(f"Anthropic API error (500): {str(ai_error)}. Will retry.")
            raise

        content = ai_response.get('content', '') if ai_response else ''
        execution_time = time.time() - start_time

        # Log the AI response for debugging
        logger.info(f"AI response keys: {ai_response.keys() if ai_response else 'None'}")
        logger.info(f"AI response content preview: {content[:200] if content else 'Empty'}")

        # Check if AI response indicates an error (500, overloaded, etc.)
        has_api_error = ai_response.get('error') if ai_response else False
        error_message = ai_response.get('error_message', '') if ai_response else ''

        # Check for timeout
        if execution_time > max_execution_time:
            raise Exception(f"Execution timeout after {execution_time:.2f}s (max: {max_execution_time}s)")

        # If there was an API error, treat as failed
        if has_api_error:
            raise Exception(f"AI API error during execution: {error_message}")

        # 8. CHECK COMPLETION STATUS (with fallback detection)
        completed = 'IMPLEMENTATION_STATUS: COMPLETE' in content
        failed = 'IMPLEMENTATION_STATUS: FAILED' in content

        # Fallback: If no explicit status, ticket is NOT complete
        # Only mark as complete if there's an explicit success status
        if not completed and not failed:
            logger.warning(f"No explicit completion status found in AI response. Content length: {len(content)}")
            # ALWAYS mark as failed if no explicit completion status
            # The AI MUST provide explicit status - anything else is incomplete
            failed = True
            logger.error("Marking as FAILED due to missing explicit completion status. AI must end with IMPLEMENTATION_STATUS.")

        logger.info(f"AI response received. Completed: {completed}, Failed: {failed}, Time: {execution_time:.2f}s")
        
        # 9. EXTRACT WHAT WAS DONE (for logging)
        import re
        files_created = re.findall(r'cat > (/workspace/nextjs-app/[\w\-\./]+)', content)
        deps_installed = re.findall(r'npm install ([\w\-\s@/]+)', content)
        dependencies = []
        for dep_string in deps_installed:
            dependencies.extend(dep_string.split())

        # Count tool executions from content
        tool_calls_count = content.count('ssh_command') + content.count('Tool call')
        logger.info(f"Estimated tool calls: {tool_calls_count}, Files created: {len(files_created)}, Dependencies: {len(dependencies)}")

        # 10. UPDATE TICKET BASED ON RESULT
        if completed and not failed:
            # SUCCESS!
            ticket.status = 'done'
            ticket.notes = f"""
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] IMPLEMENTATION COMPLETED
Time: {execution_time:.2f} seconds
Files created: {len(files_created)}
Dependencies: {', '.join(set(dependencies))}
Workspace: {workspace_id}
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
        # EXCEPTION HANDLING
        execution_time = time.time() - start_time
        error_msg = str(e)
        logger.error(f"Critical error in ticket {ticket_id}: {error_msg}", exc_info=True)

        # Determine if this is a retryable error
        is_retryable = any(indicator in error_msg.lower() for indicator in [
            '500', 'internal server error', 'timeout', 'connection', 'api error'
        ])

        if 'ticket' in locals():
            # For retryable errors, keep status as in_progress for Django-Q retry
            if is_retryable and execution_time < max_execution_time:
                ticket.status = 'in_progress'
                ticket.notes = f"""
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] RETRYABLE ERROR (will retry)
Error: {error_msg}
Time: {execution_time:.2f}s
Workspace: {workspace_id or 'N/A'}
"""
                logger.info(f"Marking ticket #{ticket_id} for retry due to retryable error")
            else:
                # Non-retryable or already timed out
                ticket.status = 'failed'
                ticket.notes = f"""
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] FATAL ERROR
Error: {error_msg}
Time: {execution_time:.2f}s
Workspace: {workspace_id or 'N/A'}
Retryable: {is_retryable}
Manual intervention required
"""

            ticket.save(update_fields=['status', 'notes'])

            broadcast_ticket_notification(conversation_id, {
                'is_notification': True,
                'notification_type': 'toolhistory',
                'function_name': 'ticket_execution',
                'status': 'failed' if not is_retryable else 'error',
                'message': f"✗ Ticket #{ticket.id} error: {error_msg[:100]}",
                'ticket_id': ticket.id,
                'ticket_name': ticket.name,
                'refresh_checklist': True
            })

        # Re-raise retryable errors for Django-Q to handle
        if is_retryable and execution_time < max_execution_time:
            raise  # Let Django-Q retry

        return {
            "status": "error",
            "ticket_id": ticket_id,
            "error": error_msg,
            "workspace_id": workspace_id,
            "execution_time": f"{execution_time:.2f}s",
            "retryable": is_retryable
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

    result = None
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            provision_vibe_workspace_tool(
                {
                    'project_name': project.provided_name or project.name,
                    'summary': project.description or ''
                },
                project.project_id,
                conversation_id
            )
        )
    finally:
        asyncio.set_event_loop(None)
        loop.close()

    if isinstance(result, dict) and result.get('status') == 'failed':
        broadcast_ticket_notification(conversation_id, {
            'is_notification': True,
            'notification_type': 'toolhistory',
            'function_name': 'ticket_execution_queue',
            'status': 'failed',
            'message': f"Workspace provisioning failed: {result.get('message_to_agent') or result.get('message')}",
            'refresh_checklist': False
        })
        return {
            "status": "error",
            "message": result.get('message_to_agent') or result.get('message') or 'Workspace provisioning failed'
        }

    if isinstance(result, dict) and not result.get('status'):
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
    from projects.models import ProjectChecklist
    
    try:
        ticket = ProjectChecklist.objects.get(id=ticket_id)
        
        # For now, we'll implement a simple priority-based dependency
        # High priority tickets should be done before medium/low
        if ticket.priority.lower() in ['medium', 'low']:
            # Check if there are any high priority tickets still pending
            high_priority_pending = ProjectChecklist.objects.filter(
                project=ticket.project,
                status='open',
                priority='High',
                role='agent'
            ).exists()
            
            if high_priority_pending:
                return False
        
        return True
        
    except ProjectChecklist.DoesNotExist:
        return False


def monitor_ticket_progress(project_id: int) -> Dict[str, Any]:
    """
    Monitor the progress of all tickets in a project.
    
    Args:
        project_id: The project ID
        
    Returns:
        Dict with project ticket statistics
    """
    from projects.models import ProjectChecklist
    
    tickets = ProjectChecklist.objects.filter(project_id=project_id)
    
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
    from projects.models import ProjectChecklist
    from tasks.task_manager import TaskManager
    
    task_manager = TaskManager()
    
    try:
        # Get all open tickets that can be executed by agents
        open_tickets = ProjectChecklist.objects.filter(
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
