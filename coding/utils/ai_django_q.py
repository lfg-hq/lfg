# ============================================================================
# DJANGO-Q TICKET IMPLEMENTATION FUNCTIONS
# ============================================================================

from asgiref.sync import sync_to_async


async def implement_ticket_async(ticket_id: int, project_id: int, conversation_id: int) -> dict:
    """
    Queue a ticket for asynchronous implementation using Django-Q.
    
    Args:
        ticket_id: The ID of the ticket to implement
        project_id: The project ID
        conversation_id: The conversation ID
        
    Returns:
        Dict with task queuing status
    """
    from tasks.task_manager import TaskManager
    from projects.models import ProjectChecklist
    
    if not ticket_id:
        return {
            "is_notification": False,
            "message_to_agent": "Error: ticket_id is required"
        }
    
    try:
        # Verify ticket exists
        ticket = await sync_to_async(
            lambda: ProjectChecklist.objects.get(id=ticket_id)
        )()
        
        # Initialize task manager
        task_manager = TaskManager()
        
        # Queue the ticket for implementation
        task_id = task_manager.publish_task(
            'tasks.task_definitions.execute_ticket_implementation',
            args=(ticket_id, project_id, conversation_id),
            group=f'project_{project_id}',
            sync=False  # Async execution
        )
        
        return {
            "is_notification": True,
            "notification_type": "ticket_queued",
            "message_to_agent": f"Ticket {ticket_id} ({ticket.name}) has been queued for implementation. Django-Q task ID: {task_id}"
        }
        
    except ProjectChecklist.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Ticket with ID {ticket_id} does not exist"
        }
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error queuing ticket: {str(e)}"
        }


async def execute_tickets_in_parallel(project_id: int, conversation_id: int, max_workers: int = 3) -> dict:
    """
    Execute multiple tickets in parallel using Django-Q.
    
    Args:
        project_id: The project ID
        conversation_id: The conversation ID
        max_workers: Maximum number of parallel workers
        
    Returns:
        Dict with parallel execution status
    """
    from tasks.task_definitions import parallel_ticket_executor
    
    try:
        # Call the parallel executor
        result = await sync_to_async(parallel_ticket_executor)(
            project_id, conversation_id, max_workers
        )
        
        if result['status'] == 'success':
            message = f"Successfully queued {result['total_queued']} tickets for parallel execution:\n"
            for task in result['queued_tasks']:
                message += f"- Ticket {task['ticket_id']} (Priority: {task['priority']}) - Task ID: {task['task_id']}\n"
            
            return {
                "is_notification": True,
                "notification_type": "parallel_execution_started",
                "message_to_agent": message
            }
        else:
            return {
                "is_notification": False,
                "message_to_agent": f"Error in parallel execution: {result.get('error', 'Unknown error')}"
            }
            
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error starting parallel execution: {str(e)}"
        }


async def get_ticket_execution_status(project_id: int, task_id: str = None) -> dict:
    """
    Get the execution status of tickets being processed by Django-Q.
    
    Args:
        project_id: The project ID
        task_id: Optional specific task ID to check
        
    Returns:
        Dict with ticket execution status
    """
    from tasks.task_manager import TaskManager
    from tasks.task_definitions import monitor_ticket_progress
    
    task_manager = TaskManager()
    
    try:
        if task_id:
            # Get status of specific task
            status = task_manager.get_task_status(task_id)
            
            if status:
                message = f"Task {task_id} status:\n"
                message += f"- Function: {status.get('func', 'N/A')}\n"
                message += f"- Status: {status.get('status', 'Unknown')}\n"
                message += f"- Started: {status.get('started', 'N/A')}\n"
                message += f"- Result: {status.get('result', 'Pending')}\n"
            else:
                message = f"Task {task_id} not found or no longer in queue"
        else:
            # Get overall project ticket progress
            progress = await sync_to_async(monitor_ticket_progress)(project_id)
            
            message = f"Project ticket execution status:\n"
            message += f"- Total tickets: {progress['total_tickets']}\n"
            message += f"- Open: {progress['open_tickets']}\n"
            message += f"- In Progress: {progress['in_progress_tickets']}\n"
            message += f"- Completed: {progress['done_tickets']}\n"
            message += f"- Failed: {progress['failed_tickets']}\n\n"
            
            # Get queue statistics
            stats = task_manager.get_task_statistics()
            message += f"Django-Q queue status:\n"
            message += f"- Pending tasks: {stats['queue_size']}\n"
            message += f"- Running tasks: {len(stats['running_tasks'])}\n"
            
        return {
            "is_notification": True,
            "notification_type": "execution_status",
            "message_to_agent": message
        }
        
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error getting execution status: {str(e)}"
        }