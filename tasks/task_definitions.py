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

from django.conf import settings
from django.db import transaction
from asgiref.sync import sync_to_async, async_to_sync

logger = logging.getLogger(__name__)


def execute_ticket_implementation(ticket_id: int, project_id: int, conversation_id: int) -> Dict[str, Any]:
    """
    Execute a single ticket implementation asynchronously.
    
    This task is called by Django-Q to implement a ticket in the background.
    It updates ticket status, calls the AI implementation, and handles results.
    
    Args:
        ticket_id: The ID of the ProjectChecklist ticket
        project_id: The ID of the project
        conversation_id: The ID of the conversation
        
    Returns:
        Dict with execution results and status
    """
    from projects.models import ProjectChecklist, Project
    from coding.utils.ai_providers import get_ai_response
    from coding.utils.task_prompt import get_task_implementaion_developer
    from coding.utils.ai_functions import execute_function
    
    try:
        # Get ticket and project
        ticket = ProjectChecklist.objects.get(id=ticket_id)
        project = Project.objects.get(id=project_id)
        
        # Update ticket status to in_progress
        ticket.status = 'in_progress'
        ticket.save()
        
        logger.info(f"Starting implementation of ticket {ticket_id}: {ticket.name}")
        
        # Prepare ticket context for AI
        ticket_context = {
            "ticket_id": ticket.id,
            "ticket_name": ticket.name,
            "ticket_description": ticket.description,
            "ticket_priority": ticket.priority,
            "project_name": project.name,
            "project_id": project.id,
            "requires_worktree": True  # Default to true for code changes
        }
        
        # Get implementation prompt
        system_prompt = async_to_sync(get_task_implementaion_developer)()
        
        # Prepare user message with detailed ticket information
        user_message = f"""
        You have been assigned the following ticket to implement:
        
        Ticket ID: {ticket.id}
        Ticket Name: {ticket.name}
        Description: {ticket.description}
        Priority: {ticket.priority}
        Project: {project.name}
        Complexity: {ticket.complexity}
        Requires Worktree: {ticket.requires_worktree}
        
        Technical Details:
        {json.dumps(ticket.details, indent=2)}
        
        UI/UX Requirements:
        {json.dumps(ticket.ui_requirements, indent=2)}
        
        Component Specifications:
        {json.dumps(ticket.component_specs, indent=2)}
        
        Acceptance Criteria:
        {json.dumps(ticket.acceptance_criteria, indent=2)}
        
        Dependencies:
        {json.dumps(ticket.dependencies, indent=2)}
        
        Please implement this ticket with exceptional attention to visual design and user experience.
        Follow the design system specifications exactly.
        Ensure all acceptance criteria are met, including UI/UX requirements.
        """
        
        # Call AI to implement the ticket
        ai_response = async_to_sync(get_ai_response)(
            user_message=user_message,
            system_prompt=system_prompt,
            project_id=project_id,
            conversation_id=conversation_id,
            stream=False
        )
        
        # Process AI response and execute any tool calls
        if ai_response.get('tool_calls'):
            for tool_call in ai_response['tool_calls']:
                function_name = tool_call.get('function', {}).get('name')
                function_args = json.loads(tool_call.get('function', {}).get('arguments', '{}'))
                
                result = async_to_sync(execute_function)(
                    function_name=function_name,
                    function_args=function_args,
                    project_id=project_id,
                    conversation_id=conversation_id
                )
                
                logger.info(f"Executed function {function_name} with result: {result}")
        
        # Update ticket status to done
        ticket.status = 'done'
        ticket.save()
        
        logger.info(f"Successfully completed ticket {ticket_id}")
        
        return {
            "status": "success",
            "ticket_id": ticket_id,
            "message": f"Ticket {ticket.name} implemented successfully",
            "completion_time": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error implementing ticket {ticket_id}: {str(e)}")
        
        # Update ticket status to failed
        if 'ticket' in locals():
            ticket.status = 'failed'
            ticket.save()
        
        return {
            "status": "error",
            "ticket_id": ticket_id,
            "error": str(e),
            "completion_time": datetime.now().isoformat()
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
                args=(ticket_id, project_id, conversation_id),
                group=f'project_{project_id}_high',
                sync=False
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
                    args=(ticket_id, project_id, conversation_id),
                    group=f'project_{project_id}_medium',
                    sync=False
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