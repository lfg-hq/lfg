# Django Q Task Queue System

This project implements a comprehensive Django Q based task queue system that supports both Redis and SQLite brokers based on the `ENVIRONMENT` variable.

## Features

- **Environment-based configuration**: Automatically uses Redis for production/staging and SQLite for local development
- **Task management utilities**: Core TaskManager class for publishing and monitoring tasks
- **REST API endpoints**: HTTP APIs for task monitoring
- **Monitoring and statistics**: Built-in task monitoring and queue statistics
- **Scheduled tasks**: Support for recurring tasks

## Installation and Setup

### 1. Dependencies

The following packages are added to `requirements.txt`:
- `django-q2==1.4.5` - The Django Q task queue
- `redis>=4.0.0` - Redis client (used in production/staging)

### 2. Configuration

The system is configured in `settings.py` based on the `ENVIRONMENT` variable:

**Local Development (SQLite broker):**
```python
ENVIRONMENT = 'local'  # or any value not in ['production', 'staging']
```

**Production/Staging (Redis broker):**
```python
ENVIRONMENT = 'production'  # or 'staging'
```

Environment variables for Redis configuration:
- `REDIS_HOST` (default: 'localhost')
- `REDIS_PORT` (default: 6379)
- `REDIS_DB` (default: 0)
- `REDIS_PASSWORD` (optional)

### 3. Database Migration

Run migrations to create Django Q tables:
```bash
python manage.py migrate
```

### 4. Start the Task Worker

To process tasks, you need to start the Django Q cluster:
```bash
python manage.py qcluster
```

For production, use a process manager like supervisord or systemd.

## Usage

### 1. Creating Task Functions

Add your task functions to `tasks/task_definitions.py`:

```python
def your_task_function(param1: str, param2: int) -> dict:
    """
    Your task description.
    
    Args:
        param1: Description of parameter 1
        param2: Description of parameter 2
        
    Returns:
        Dict with task result
    """
    import logging
    import time
    
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Starting task with {param1} and {param2}")
        
        # Your task logic here
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
```

### 2. Publishing Tasks

#### Using TaskManager Directly
```python
from tasks.task_manager import TaskManager

# Publish a task
task_id = TaskManager.publish_task(
    'tasks.task_definitions.your_task_function',
    'arg1',      # First argument
    123,         # Second argument
    task_name="My task"
)
```

#### Creating Convenience Functions
```python
# In tasks/task_manager.py or your own module
def your_task_async(param1: str, param2: int, task_name: str = None) -> str:
    """Convenience function to publish your task."""
    return TaskManager.publish_task(
        'tasks.task_definitions.your_task_function',
        param1,
        param2,
        task_name=task_name or f"Your task: {param1}"
    )
```

### 3. Task Monitoring

#### Check Task Status
```python
from tasks.task_manager import TaskManager

status = TaskManager.get_task_status(task_id)
```

#### Get Task Result
```python
result = TaskManager.get_task_result(task_id)
```

#### Get Queue Statistics
```python
stats = TaskManager.get_task_statistics()
```

### 4. Scheduled Tasks

#### Schedule a Recurring Task
```python
schedule_id = TaskManager.schedule_task(
    'tasks.task_definitions.your_task_function',
    'D',         # Daily schedule ('H' for hourly, 'I' for minutes)
    'param1',    # Task arguments
    123,
    name="Daily task"
)
```

#### Cancel a Scheduled Task
```python
success = TaskManager.cancel_scheduled_task(schedule_id)
```

### 5. REST API Endpoints

Base URL: `/api/tasks/`

#### Monitor Tasks
- `GET /api/tasks/status/{task_id}/` - Get task status
- `GET /api/tasks/result/{task_id}/` - Get task result
- `GET /api/tasks/queue/status/` - Get queue statistics

#### Schedule Management
- `POST /api/tasks/schedule/cancel/{schedule_id}/` - Cancel scheduled task

### 6. Creating Custom API Endpoints

Add your own task publishing endpoints in `tasks/views.py`:

```python
@csrf_exempt
@require_POST
@login_required
def publish_your_task(request):
    """API endpoint to publish your custom task."""
    try:
        data = json.loads(request.body)
        param1 = data.get('param1')
        param2 = data.get('param2')
        
        task_id = TaskManager.publish_task(
            'tasks.task_definitions.your_task_function',
            param1,
            param2,
            task_name="Your custom task"
        )
        
        return JsonResponse({
            'success': True,
            'task_id': task_id
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
```

Then add the URL pattern in `tasks/urls.py`:
```python
path('publish/your-task/', views.publish_your_task, name='publish_your_task'),
```

## TaskManager Methods

### Publishing
- `publish_task(task_function, *args, **kwargs)` - Publish a task for immediate execution
- `schedule_task(task_function, schedule_type, *args, **kwargs)` - Schedule a recurring task

### Monitoring
- `get_task_status(task_id)` - Get detailed task status
- `get_task_result(task_id)` - Get task result
- `get_running_tasks()` - List currently running tasks
- `get_failed_tasks(hours=24)` - List failed tasks
- `get_queue_size()` - Get pending task count
- `get_task_statistics()` - Get comprehensive queue statistics

### Scheduling
- `get_scheduled_tasks()` - List all scheduled tasks
- `cancel_scheduled_task(schedule_id)` - Cancel a scheduled task

## Schedule Types

- `'I'` - Minutes interval
- `'H'` - Hourly
- `'D'` - Daily
- `'W'` - Weekly
- `'M'` - Monthly

## Monitoring

### Django Admin
Access Django Q monitoring at: `http://localhost:8000/admin/django_q/`

- View task history
- Monitor running tasks
- Check failed tasks
- Manage scheduled tasks

### Programmatic Monitoring
```python
from tasks.task_manager import TaskManager

# Get comprehensive statistics
stats = TaskManager.get_task_statistics()

# Get running tasks
running = TaskManager.get_running_tasks()

# Get failed tasks
failed = TaskManager.get_failed_tasks(hours=24)

# Get scheduled tasks
scheduled = TaskManager.get_scheduled_tasks()
```

## Production Deployment

### 1. Environment Variables
```bash
export environment=production
export REDIS_HOST=your-redis-host
export REDIS_PORT=6379
export REDIS_DB=0
export REDIS_PASSWORD=your-redis-password
```

### 2. Worker Process
Set up a service to run the Django Q worker:
```bash
python manage.py qcluster
```

### 3. Process Management
Consider using:
- Supervisord
- systemd
- Docker containers
- Kubernetes deployments

## Troubleshooting

### Common Issues

1. **Tasks not processing**: Make sure `python manage.py qcluster` is running
2. **Redis connection errors**: Check Redis configuration and connectivity
3. **Import errors**: Ensure all task functions are properly imported
4. **Permission errors**: Ensure API requests include proper authentication

### Logging
Django Q logs are available in your Django logs. Check for:
- Task execution logs
- Error messages
- Queue status information

## File Structure

```
tasks/
├── __init__.py
├── apps.py
├── task_definitions.py    # Your task functions
├── task_manager.py        # Core TaskManager class
├── views.py              # API endpoints
└── urls.py               # URL patterns
```

This implementation provides a robust, scalable task queue system that automatically adapts to your deployment environment while providing comprehensive monitoring and management capabilities. 