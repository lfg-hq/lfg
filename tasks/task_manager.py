import logging
from typing import Any, Dict, List, Optional, Union
from django_q.tasks import async_task, schedule, result
from django_q.models import Task, Schedule
from django.utils import timezone
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class TaskManager:
    """
    A utility class for managing Django Q tasks.
    Provides convenient methods to publish, monitor, and manage background tasks.
    """
    
    @staticmethod
    def publish_task(
        task_function: str,
        *args,
        task_name: Optional[str] = None,
        hook: Optional[str] = None,
        timeout: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        Publish a task to the queue for immediate execution.
        
        Args:
            task_function: Function path (e.g., 'tasks.task_definitions.your_task')
            *args: Positional arguments for the task function
            task_name: Optional name for the task
            hook: Optional hook function to call when task completes
            timeout: Optional timeout in seconds
            **kwargs: Keyword arguments for the task function
            
        Returns:
            Task ID string
        """
        try:
            task_id = async_task(
                task_function,
                *args,
                task_name=task_name,
                hook=hook,
                timeout=timeout,
                **kwargs
            )
            
            logger.info(f"Published task '{task_name or task_function}' with ID: {task_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to publish task '{task_function}': {str(e)}")
            raise
    
    @staticmethod
    def schedule_task(
        task_function: str,
        schedule_type: str,
        *args,
        name: Optional[str] = None,
        hook: Optional[str] = None,
        timeout: Optional[int] = None,
        repeats: int = -1,
        next_run: Optional[datetime] = None,
        **kwargs
    ) -> int:
        """
        Schedule a task for recurring execution.
        
        Args:
            task_function: Function path (e.g., 'tasks.task_definitions.your_task')
            schedule_type: Type of schedule ('I' for minutes, 'H' for hourly, 'D' for daily, etc.)
            *args: Positional arguments for the task function
            name: Optional name for the scheduled task
            hook: Optional hook function to call when task completes
            timeout: Optional timeout in seconds
            repeats: Number of times to repeat (-1 for infinite)
            next_run: When to run the task next (defaults to now)
            **kwargs: Keyword arguments for the task function
            
        Returns:
            Schedule ID
        """
        try:
            schedule_id = schedule(
                task_function,
                *args,
                name=name,
                hook=hook,
                timeout=timeout,
                schedule_type=schedule_type,
                repeats=repeats,
                next_run=next_run or timezone.now(),
                **kwargs
            )
            
            logger.info(f"Scheduled task '{name or task_function}' with ID: {schedule_id}")
            return schedule_id
            
        except Exception as e:
            logger.error(f"Failed to schedule task '{task_function}': {str(e)}")
            raise
    
    @staticmethod
    def get_task_result(task_id: str) -> Optional[Any]:
        """
        Get the result of a completed task.
        
        Args:
            task_id: ID of the task
            
        Returns:
            Task result or None if task not found/not completed
        """
        try:
            return result(task_id)
        except Exception as e:
            logger.error(f"Failed to get result for task {task_id}: {str(e)}")
            return None
    
    @staticmethod
    def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status and details of a task.
        
        Args:
            task_id: ID of the task
            
        Returns:
            Dict with task details or None if not found
        """
        try:
            task = Task.objects.filter(id=task_id).first()
            if not task:
                return None
            
            return {
                'id': task.id,
                'name': task.name,
                'func': task.func,
                'started': task.started,
                'stopped': task.stopped,
                'success': task.success,
                'result': task.result,
                'group': task.group,
                'attempt_count': task.attempt_count,
            }
            
        except Exception as e:
            logger.error(f"Failed to get status for task {task_id}: {str(e)}")
            return None
    
    @staticmethod
    def get_running_tasks() -> List[Dict[str, Any]]:
        """
        Get a list of currently running tasks.
        
        Returns:
            List of task details dictionaries
        """
        try:
            running_tasks = Task.objects.filter(
                started__isnull=False,
                stopped__isnull=True
            )
            
            return [
                {
                    'id': task.id,
                    'name': task.name,
                    'func': task.func,
                    'started': task.started,
                    'group': task.group,
                    'attempt_count': task.attempt_count,
                }
                for task in running_tasks
            ]
            
        except Exception as e:
            logger.error(f"Failed to get running tasks: {str(e)}")
            return []
    
    @staticmethod
    def get_failed_tasks(hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get a list of failed tasks within the specified time period.
        
        Args:
            hours: Number of hours to look back for failed tasks
            
        Returns:
            List of failed task details
        """
        try:
            since = timezone.now() - timedelta(hours=hours)
            failed_tasks = Task.objects.filter(
                success=False,
                stopped__gte=since
            )
            
            return [
                {
                    'id': task.id,
                    'name': task.name,
                    'func': task.func,
                    'started': task.started,
                    'stopped': task.stopped,
                    'result': task.result,
                    'group': task.group,
                    'attempt_count': task.attempt_count,
                }
                for task in failed_tasks
            ]
            
        except Exception as e:
            logger.error(f"Failed to get failed tasks: {str(e)}")
            return []
    
    @staticmethod
    def get_queue_size() -> int:
        """
        Get the current size of the task queue (pending tasks).
        
        Returns:
            Number of pending tasks
        """
        try:
            return Task.objects.filter(
                started__isnull=True,
                stopped__isnull=True
            ).count()
            
        except Exception as e:
            logger.error(f"Failed to get queue size: {str(e)}")
            return 0
    
    @staticmethod
    def get_scheduled_tasks() -> List[Dict[str, Any]]:
        """
        Get a list of all scheduled tasks.
        
        Returns:
            List of scheduled task details
        """
        try:
            scheduled_tasks = Schedule.objects.all()
            
            return [
                {
                    'id': schedule.id,
                    'name': schedule.name,
                    'func': schedule.func,
                    'schedule_type': schedule.schedule_type,
                    'next_run': schedule.next_run,
                    'repeats': schedule.repeats,
                    'task_count': schedule.task_count(),
                }
                for schedule in scheduled_tasks
            ]
            
        except Exception as e:
            logger.error(f"Failed to get scheduled tasks: {str(e)}")
            return []
    
    @staticmethod
    def cancel_scheduled_task(schedule_id: int) -> bool:
        """
        Cancel a scheduled task.
        
        Args:
            schedule_id: ID of the scheduled task to cancel
            
        Returns:
            True if cancelled successfully, False otherwise
        """
        try:
            schedule = Schedule.objects.filter(id=schedule_id).first()
            if schedule:
                schedule.delete()
                logger.info(f"Cancelled scheduled task with ID: {schedule_id}")
                return True
            else:
                logger.warning(f"Scheduled task with ID {schedule_id} not found")
                return False
                
        except Exception as e:
            logger.error(f"Failed to cancel scheduled task {schedule_id}: {str(e)}")
            return False
    
    @staticmethod
    def get_task_statistics() -> Dict[str, Any]:
        """
        Get overall task queue statistics.
        
        Returns:
            Dict with various statistics
        """
        try:
            now = timezone.now()
            last_24h = now - timedelta(hours=24)
            last_7d = now - timedelta(days=7)
            
            stats = {
                'queue_size': Task.objects.filter(
                    started__isnull=True,
                    stopped__isnull=True
                ).count(),
                'running_tasks': Task.objects.filter(
                    started__isnull=False,
                    stopped__isnull=True
                ).count(),
                'completed_24h': Task.objects.filter(
                    success=True,
                    stopped__gte=last_24h
                ).count(),
                'failed_24h': Task.objects.filter(
                    success=False,
                    stopped__gte=last_24h
                ).count(),
                'completed_7d': Task.objects.filter(
                    success=True,
                    stopped__gte=last_7d
                ).count(),
                'failed_7d': Task.objects.filter(
                    success=False,
                    stopped__gte=last_7d
                ).count(),
                'scheduled_tasks': Schedule.objects.count(),
                'total_tasks': Task.objects.count(),
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get task statistics: {str(e)}")
            return {} 