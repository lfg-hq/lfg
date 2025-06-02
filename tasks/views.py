import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required

from .task_manager import TaskManager

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET"])
@login_required
def get_task_status(request, task_id):
    """
    API endpoint to get the status of a specific task.
    """
    try:
        task_status = TaskManager.get_task_status(task_id)
        
        if task_status is None:
            return JsonResponse({
                'success': False,
                'error': 'Task not found'
            }, status=404)
        
        return JsonResponse({
            'success': True,
            'task_status': task_status
        })
        
    except Exception as e:
        logger.error(f"Error getting task status: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@login_required
def get_task_result(request, task_id):
    """
    API endpoint to get the result of a completed task.
    """
    try:
        task_result = TaskManager.get_task_result(task_id)
        
        if task_result is None:
            return JsonResponse({
                'success': False,
                'error': 'Task not found or not completed'
            }, status=404)
        
        return JsonResponse({
            'success': True,
            'task_result': task_result
        })
        
    except Exception as e:
        logger.error(f"Error getting task result: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@login_required
def get_queue_status(request):
    """
    API endpoint to get the current queue status and statistics.
    """
    try:
        statistics = TaskManager.get_task_statistics()
        running_tasks = TaskManager.get_running_tasks()
        failed_tasks = TaskManager.get_failed_tasks(hours=24)
        scheduled_tasks = TaskManager.get_scheduled_tasks()
        
        return JsonResponse({
            'success': True,
            'statistics': statistics,
            'running_tasks': running_tasks,
            'failed_tasks_24h': failed_tasks,
            'scheduled_tasks': scheduled_tasks
        })
        
    except Exception as e:
        logger.error(f"Error getting queue status: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def cancel_scheduled_task(request, schedule_id):
    """
    API endpoint to cancel a scheduled task.
    """
    try:
        success = TaskManager.cancel_scheduled_task(schedule_id)
        
        if success:
            return JsonResponse({
                'success': True,
                'message': 'Scheduled task cancelled successfully'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Scheduled task not found'
            }, status=404)
        
    except Exception as e:
        logger.error(f"Error cancelling scheduled task: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500) 