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

from django.conf import settings
from django.db import transaction
from asgiref.sync import sync_to_async, async_to_sync

from projects.models import ProjectChecklist, Project
from factory.ai_providers import get_ai_response
from development.utils.task_prompt import get_task_implementaion_developer
from factory.ai_tools import tools_code
import time

logger = logging.getLogger(__name__)


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
        ticket.status = 'done'  # Mark as done for testing
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


def execute_ticket_implementation(ticket_id: int, project_id: int, conversation_id: int) -> Dict[str, Any]:
    """
    Execute a single ticket implementation asynchronously with continuous AI interaction.
    
    This task runs in a loop, continuously calling the AI and processing tool calls
    until the ticket is marked as complete. It provides full access to execute_command
    and other tools for comprehensive ticket implementation.
    
    Args:
        ticket_id: The ID of the ProjectChecklist ticket
        project_id: The ID of the project
        conversation_id: The ID of the conversation
        
    Returns:
        Dict with execution results and status
    """
    # Configuration
    MAX_ITERATIONS = 10  # Prevent infinite loops
    ITERATION_DELAY = 2  # Seconds between iterations
    
    try:
        # Get ticket and project
        ticket = ProjectChecklist.objects.get(id=ticket_id)
        project = Project.objects.get(id=project_id)
        
        # Update ticket status to in_progress
        ticket.status = 'in_progress'
        ticket.save()
        
        logger.info(f"Starting implementation of ticket {ticket_id}: {ticket.name}")
        
        # Get implementation prompt
        system_prompt = async_to_sync(get_task_implementaion_developer)()
        
        # Prepare initial ticket context
        initial_message = f"""
        You have been assigned the following ticket to implement:
        
        **Ticket Details:**
        - Ticket ID: {ticket.id}
        - Ticket Name: {ticket.name}
        - Description: {ticket.description}
        - Priority: {ticket.priority}
        - Project: {project.name}
        - Complexity: {ticket.complexity}
        - Requires Worktree: {ticket.requires_worktree}
        
        **Technical Details:**
        ```json
        {json.dumps(ticket.details, indent=2)}
        ```
        
        **UI/UX Requirements:**
        ```json
        {json.dumps(ticket.ui_requirements, indent=2)}
        ```
        
        **Component Specifications:**
        ```json
        {json.dumps(ticket.component_specs, indent=2)}
        ```
        
        **Acceptance Criteria:**
        ```json
        {json.dumps(ticket.acceptance_criteria, indent=2)}
        ```
        
        **Dependencies:**
        ```json
        {json.dumps(ticket.dependencies, indent=2)}
        ```
        
        Please implement this ticket following the workflow outlined in your system prompt.
        Use the execute_command tool to run any necessary commands for setup, implementation, and testing.
        
        Start by setting up the ticket context and environment as described in your prompt.
        Continue working until the ticket is fully implemented and all acceptance criteria are met.
        """
        
        iteration = 0
        ticket_completed = False
        last_ai_response = None
        
        # Main implementation loop
        while not ticket_completed and iteration < MAX_ITERATIONS:
            iteration += 1
            logger.info(f"Ticket {ticket_id} - Iteration {iteration}/{MAX_ITERATIONS}")
            
            try:
                # Call AI with current message
                if iteration == 1:
                    current_message = initial_message
                else:
                    # For subsequent iterations, ask the AI to continue
                    current_message = """
                    Please continue with the ticket implementation. 
                    
                    If you have completed all the requirements:
                    - Ensure all acceptance criteria are met
                    - Run any final tests
                    - State clearly "TICKET IMPLEMENTATION COMPLETED" 
                    
                    If you need to continue working:
                    - Use the execute_command tool for any necessary operations
                    - Follow the implementation workflow from your system prompt
                    - Focus on the remaining tasks for this ticket
                    """
                
                ai_response = async_to_sync(get_ai_response)(
                    user_message=current_message,
                    system_prompt=system_prompt,
                    project_id=project_id,
                    conversation_id=conversation_id,
                    stream=False,
                    tools=tools_code  # Use the full tools_code list which includes execute_command
                )
                
                last_ai_response = ai_response
                
                # Check if ticket implementation is complete
                response_content = ai_response.get('content', '').lower()
                completion_indicators = [
                    'ticket implementation completed',
                    'implementation completed',
                    'ticket completed successfully',
                    'all acceptance criteria met',
                    'implementation finished',
                    'ticket is now complete',
                    'implementation is complete'
                ]
                
                if any(indicator in response_content for indicator in completion_indicators):
                    logger.info(f"Ticket {ticket_id} appears to be completed based on AI response")
                    ticket_completed = True
                    break
                
                # Check for explicit completion signals
                if 'completed' in response_content and iteration > 3:
                    # If we've done several iterations and AI mentions completion
                    logger.info(f"Ticket {ticket_id} likely completed after {iteration} iterations")
                    ticket_completed = True
                    break
                
                # Add delay between iterations to prevent overwhelming
                time.sleep(ITERATION_DELAY)
                
            except Exception as iteration_error:
                logger.error(f"Error in iteration {iteration}: {str(iteration_error)}")
                
                # Don't break on individual iteration errors, but limit retries
                if iteration >= MAX_ITERATIONS - 5:  # Last 5 iterations, be more strict
                    break
        
        # Determine final status
        if ticket_completed:
            ticket.status = 'done'
            ticket.save()
            
            logger.info(f"Successfully completed ticket {ticket_id} after {iteration} iterations")
            
            return {
                "status": "success",
                "ticket_id": ticket_id,
                "message": f"Ticket {ticket.name} implemented successfully",
                "iterations_used": iteration,
                "completion_time": datetime.now().isoformat(),
                "final_response": last_ai_response.get('content', '') if last_ai_response else None
            }
        else:
            # Max iterations reached without completion
            ticket.status = 'failed'
            ticket.save()
            
            logger.warning(f"Ticket {ticket_id} reached max iterations ({MAX_ITERATIONS}) without completion")
            
            return {
                "status": "timeout",
                "ticket_id": ticket_id,
                "message": f"Ticket {ticket.name} reached maximum iterations without completion",
                "iterations_used": iteration,
                "completion_time": datetime.now().isoformat(),
                "final_response": last_ai_response.get('content', '') if last_ai_response else None
            }
        
    except Exception as e:
        logger.error(f"Critical error implementing ticket {ticket_id}: {str(e)}")
        
        # Update ticket status to failed
        if 'ticket' in locals():
            ticket.status = 'failed'
            ticket.save()
        
        return {
            "status": "error",
            "ticket_id": ticket_id,
            "error": str(e),
            "completion_time": datetime.now().isoformat(),
            "iterations_used": iteration if 'iteration' in locals() else 0
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
    
    for ticket_id in ticket_ids:
        result = execute_ticket_implementation(ticket_id, project_id, conversation_id)
        results.append(result)
        
        # Stop on error
        if result.get("status") == "error":
            break
    
    return {
        "batch_status": "completed",
        "total_tickets": len(ticket_ids),
        "completed_tickets": len([r for r in results if r.get("status") == "success"]),
        "failed_tickets": len([r for r in results if r.get("status") == "error"]),
        "results": results
    }


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