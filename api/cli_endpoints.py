"""
CLI API Endpoints

These endpoints allow Claude Code CLI running on a VM to communicate
with the LFG platform in real-time:
- Stream logs as they happen
- Create/update tasks
- Update ticket status

Authentication is via a per-user CLI API key passed in the X-CLI-API-Key header.
"""

import json
import logging
from functools import wraps

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from accounts.models import Profile
from projects.models import ProjectTicket, TicketLog, ProjectTodoList
from projects.websocket_utils import async_send_ticket_log_notification
from tasks.task_definitions import broadcast_ticket_notification, broadcast_ticket_status_change

logger = logging.getLogger(__name__)


def cli_api_key_required(view_func):
    """
    Decorator to validate CLI API key from X-CLI-API-Key header.
    Sets request.cli_user to the authenticated user.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        api_key = request.headers.get('X-CLI-API-Key')

        if not api_key:
            return JsonResponse({
                'error': 'Missing X-CLI-API-Key header'
            }, status=401)

        try:
            profile = Profile.objects.select_related('user').get(cli_api_key=api_key)
            request.cli_user = profile.user
            request.cli_profile = profile
        except Profile.DoesNotExist:
            return JsonResponse({
                'error': 'Invalid API key'
            }, status=401)

        return view_func(request, *args, **kwargs)

    return wrapper


def validate_ticket_access(request, ticket_id):
    """
    Validate that the CLI user has access to the ticket.
    Returns (ticket, error_response) tuple.
    """
    try:
        ticket = ProjectTicket.objects.select_related('project').get(id=ticket_id)
    except ProjectTicket.DoesNotExist:
        return None, JsonResponse({'error': 'Ticket not found'}, status=404)

    # Check user has access to the project
    if ticket.project.owner != request.cli_user:
        # Could also check for project membership here
        return None, JsonResponse({'error': 'Access denied'}, status=403)

    return ticket, None


@csrf_exempt
@require_http_methods(["POST"])
@cli_api_key_required
def cli_stream_log(request):
    """
    Stream a log entry from Claude CLI to the LFG platform.

    POST /api/v1/cli/stream/
    Header: X-CLI-API-Key: <key>
    Body: {
        "ticket_id": 123,
        "type": "assistant" | "tool_use" | "tool_result" | "raw",
        "data": {
            // For assistant: {"content": "..."}
            // For tool_use: {"name": "Bash", "input": {...}}
            // For tool_result: {"content": "...", "is_error": false}
            // For raw: {"content": "..."}
        }
    }
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    ticket_id = body.get('ticket_id')
    log_type = body.get('type')
    data = body.get('data', {})

    if not ticket_id:
        return JsonResponse({'error': 'ticket_id required'}, status=400)

    ticket, error = validate_ticket_access(request, ticket_id)
    if error:
        return error

    # Create log entry based on type
    log_entry = None

    if log_type == 'assistant':
        content = data.get('content', '')
        if content:
            log_entry = TicketLog.objects.create(
                ticket_id=ticket_id,
                log_type='ai_response',
                command='Claude Code',
                output=content[:10000]
            )

    elif log_type == 'tool_use':
        tool_name = data.get('name', 'unknown')
        tool_input = data.get('input', {})

        # Format based on tool type
        if tool_name == 'Bash':
            command_text = tool_input.get('command', '')
            description = tool_input.get('description', '')
            explanation = description if description else f"Running: {command_text[:100]}"
            output_text = command_text
        elif tool_name == 'Read':
            file_path = tool_input.get('file_path', '')
            explanation = f"Reading file: {file_path}"
            output_text = f"File: {file_path}"
        elif tool_name == 'Write':
            file_path = tool_input.get('file_path', '')
            content = tool_input.get('content', '')
            explanation = f"Writing file: {file_path}"
            output_text = f"File: {file_path}\n\n{content[:3000]}"
        elif tool_name == 'Edit':
            file_path = tool_input.get('file_path', '')
            old_string = tool_input.get('old_string', '')[:200]
            new_string = tool_input.get('new_string', '')[:500]
            explanation = f"Editing file: {file_path}"
            output_text = f"File: {file_path}\n\nOld:\n{old_string}\n\nNew:\n{new_string}"
        elif tool_name == 'Glob':
            pattern = tool_input.get('pattern', '')
            explanation = f"Searching for: {pattern}"
            output_text = f"Pattern: {pattern}"
        elif tool_name == 'Grep':
            pattern = tool_input.get('pattern', '')
            path = tool_input.get('path', '')
            explanation = f"Searching for '{pattern}' in {path or 'codebase'}"
            output_text = json.dumps(tool_input, indent=2)
        else:
            explanation = f"Using tool: {tool_name}"
            output_text = json.dumps(tool_input, indent=2)

        log_entry = TicketLog.objects.create(
            ticket_id=ticket_id,
            log_type='command',
            command=tool_name,
            explanation=explanation[:500],
            output=output_text[:5000]
        )

    elif log_type == 'tool_result':
        content = data.get('content', '')
        is_error = data.get('is_error', False)

        # Only log significant results or errors
        if is_error or len(str(content)) > 100:
            log_entry = TicketLog.objects.create(
                ticket_id=ticket_id,
                log_type='command',
                command='Result' + (' (Error)' if is_error else ''),
                explanation='Tool execution result',
                output=str(content)[:10000]
            )

    elif log_type == 'raw':
        content = data.get('content', '')
        if content:
            log_entry = TicketLog.objects.create(
                ticket_id=ticket_id,
                log_type='command',
                command='Output',
                output=content[:10000]
            )

    # Broadcast via WebSocket
    if log_entry:
        try:
            from asgiref.sync import async_to_sync
            async_to_sync(async_send_ticket_log_notification)(ticket_id, {
                'id': log_entry.id,
                'log_type': log_entry.log_type,
                'command': log_entry.command,
                'explanation': getattr(log_entry, 'explanation', ''),
                'output': log_entry.output[:2000],
                'created_at': log_entry.created_at.isoformat()
            })
        except Exception as e:
            logger.warning(f"[CLI API] Failed to broadcast log: {e}")

    return JsonResponse({
        'status': 'ok',
        'log_id': log_entry.id if log_entry else None
    })


@csrf_exempt
@require_http_methods(["POST"])
@cli_api_key_required
def cli_update_task(request):
    """
    Create or update a task for a ticket.

    POST /api/v1/cli/task/
    Header: X-CLI-API-Key: <key>
    Body: {
        "ticket_id": 123,
        "task": "Implement feature X",
        "status": "pending" | "in_progress" | "completed",
        "task_id": null  // Optional - if provided, updates existing task
    }
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    ticket_id = body.get('ticket_id')
    task_content = body.get('task')
    status = body.get('status', 'pending')
    task_id = body.get('task_id')

    if not ticket_id:
        return JsonResponse({'error': 'ticket_id required'}, status=400)
    if not task_content:
        return JsonResponse({'error': 'task required'}, status=400)
    if status not in ['pending', 'in_progress', 'completed']:
        return JsonResponse({'error': 'Invalid status'}, status=400)

    # Map API status to model status
    status_map = {'pending': 'pending', 'in_progress': 'in_progress', 'completed': 'success'}
    db_status = status_map.get(status, 'pending')

    ticket, error = validate_ticket_access(request, ticket_id)
    if error:
        return error

    if task_id:
        # Update existing task
        try:
            task = ProjectTodoList.objects.get(id=task_id, ticket_id=ticket_id)
            task.description = task_content
            task.status = db_status
            task.save(update_fields=['description', 'status', 'updated_at'])
        except ProjectTodoList.DoesNotExist:
            return JsonResponse({'error': 'Task not found'}, status=404)
    else:
        # Create new task
        # Get max order for existing tasks
        max_order = ProjectTodoList.objects.filter(ticket_id=ticket_id).count()
        task = ProjectTodoList.objects.create(
            ticket_id=ticket_id,
            description=task_content,
            status=db_status,
            order=max_order
        )

    # Broadcast task update via WebSocket
    try:
        broadcast_ticket_notification(ticket.conversation_id or 0, {
            'is_notification': True,
            'notification_type': 'task_update',
            'ticket_id': ticket_id,
            'task': {
                'id': task.id,
                'content': task.description,
                'status': task.status,
                'order': task.order
            }
        })
    except Exception as e:
        logger.warning(f"[CLI API] Failed to broadcast task update: {e}")

    return JsonResponse({
        'status': 'ok',
        'task_id': task.id,
        'task_status': task.status
    })


@csrf_exempt
@require_http_methods(["POST"])
@cli_api_key_required
def cli_update_status(request):
    """
    Update ticket status (complete, failed, blocked).

    POST /api/v1/cli/status/
    Header: X-CLI-API-Key: <key>
    Body: {
        "ticket_id": 123,
        "status": "completed" | "failed" | "blocked",
        "summary": "Optional completion summary"
    }
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    ticket_id = body.get('ticket_id')
    status = body.get('status')
    summary = body.get('summary', '')

    if not ticket_id:
        return JsonResponse({'error': 'ticket_id required'}, status=400)
    if status not in ['completed', 'failed', 'blocked']:
        return JsonResponse({'error': 'Invalid status. Must be: completed, failed, or blocked'}, status=400)

    ticket, error = validate_ticket_access(request, ticket_id)
    if error:
        return error

    # Map to internal status values
    status_map = {
        'completed': 'completed',
        'failed': 'blocked',  # failed maps to blocked status
        'blocked': 'blocked'
    }

    old_status = ticket.status
    ticket.status = status_map[status]
    ticket.queue_status = 'none'

    # Append summary to notes if provided
    if summary:
        ticket.notes = (ticket.notes or '') + f"\n\n[CLI] {status.upper()}: {summary}"

    ticket.save(update_fields=['status', 'queue_status', 'notes'])

    # Broadcast status change
    try:
        broadcast_ticket_status_change(ticket_id, ticket.status, 'none')

        # Also send a notification
        broadcast_ticket_notification(ticket.conversation_id or 0, {
            'is_notification': True,
            'notification_type': 'toolhistory',
            'function_name': 'ticket_execution',
            'status': 'completed' if status == 'completed' else 'failed',
            'message': f"{'✓' if status == 'completed' else '✗'} {summary or f'Ticket {status}'}",
            'ticket_id': ticket_id,
            'ticket_name': ticket.name,
            'queue_status': 'none',
            'refresh_checklist': True
        })
    except Exception as e:
        logger.warning(f"[CLI API] Failed to broadcast status change: {e}")

    logger.info(f"[CLI API] Ticket {ticket_id} status changed: {old_status} -> {ticket.status}")

    return JsonResponse({
        'status': 'ok',
        'ticket_status': ticket.status,
        'message': f'Ticket marked as {status}'
    })


@csrf_exempt
@require_http_methods(["POST"])
@cli_api_key_required
def cli_bulk_tasks(request):
    """
    Set all tasks for a ticket at once (replaces existing tasks).

    POST /api/v1/cli/tasks/bulk/
    Header: X-CLI-API-Key: <key>
    Body: {
        "ticket_id": 123,
        "tasks": [
            {"content": "Task 1", "status": "completed"},
            {"content": "Task 2", "status": "in_progress"},
            {"content": "Task 3", "status": "pending"}
        ]
    }
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    ticket_id = body.get('ticket_id')
    tasks = body.get('tasks', [])

    if not ticket_id:
        return JsonResponse({'error': 'ticket_id required'}, status=400)
    if not isinstance(tasks, list):
        return JsonResponse({'error': 'tasks must be a list'}, status=400)

    ticket, error = validate_ticket_access(request, ticket_id)
    if error:
        return error

    # Map API status to model status
    status_map = {'pending': 'pending', 'in_progress': 'in_progress', 'completed': 'success'}

    # Delete existing tasks and create new ones
    ProjectTodoList.objects.filter(ticket_id=ticket_id).delete()

    created_tasks = []
    for i, task_data in enumerate(tasks):
        content = task_data.get('content', '')
        status = task_data.get('status', 'pending')

        if not content:
            continue
        if status not in ['pending', 'in_progress', 'completed']:
            status = 'pending'

        # Map to database status
        db_status = status_map.get(status, 'pending')

        task = ProjectTodoList.objects.create(
            ticket_id=ticket_id,
            description=content,
            status=db_status,
            order=i
        )
        created_tasks.append({
            'id': task.id,
            'content': task.description,
            'status': task.status,
            'order': task.order
        })

    # Broadcast tasks update
    try:
        broadcast_ticket_notification(ticket.conversation_id or 0, {
            'is_notification': True,
            'notification_type': 'tasks_refresh',
            'ticket_id': ticket_id,
            'tasks': created_tasks
        })
    except Exception as e:
        logger.warning(f"[CLI API] Failed to broadcast tasks: {e}")

    return JsonResponse({
        'status': 'ok',
        'tasks_created': len(created_tasks),
        'tasks': created_tasks
    })


@csrf_exempt
@require_http_methods(["POST"])
@cli_api_key_required
def cli_create_user_action_ticket(request):
    """
    Create a new ticket for user action (e.g., add API keys, configure settings).

    This allows Claude to create tickets when it encounters issues that require
    user intervention, such as missing API keys, configuration issues, etc.

    POST /api/v1/cli/user-action/
    Header: X-CLI-API-Key: <key>
    Body: {
        "project_id": "uuid-string",  // Project to create ticket in
        "parent_ticket_id": 123,      // Optional - the ticket that triggered this
        "title": "Add OpenAI API Key",
        "description": "The OpenAI API key is required for...",
        "action_type": "add_api_key" | "configure_setting" | "review_code" | "manual_fix" | "other",
        "priority": "high" | "medium" | "low",  // Optional, defaults to "high"
        "metadata": {}  // Optional - additional context
    }
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    project_id = body.get('project_id')
    parent_ticket_id = body.get('parent_ticket_id')
    title = body.get('title')
    description = body.get('description', '')
    action_type = body.get('action_type', 'other')
    priority = body.get('priority', 'high')
    metadata = body.get('metadata', {})

    if not project_id:
        return JsonResponse({'error': 'project_id required'}, status=400)
    if not title:
        return JsonResponse({'error': 'title required'}, status=400)

    # Validate action_type
    valid_action_types = ['add_api_key', 'configure_setting', 'review_code', 'manual_fix', 'other']
    if action_type not in valid_action_types:
        action_type = 'other'

    # Validate priority
    valid_priorities = ['high', 'medium', 'low']
    if priority not in valid_priorities:
        priority = 'high'

    # Get the project
    from projects.models import Project
    try:
        project = Project.objects.get(project_id=project_id)
    except Project.DoesNotExist:
        return JsonResponse({'error': 'Project not found'}, status=404)

    # Verify user has access to the project
    if project.owner != request.cli_user:
        return JsonResponse({'error': 'Access denied'}, status=403)

    # Get parent ticket if provided (for linking)
    parent_ticket = None
    if parent_ticket_id:
        try:
            parent_ticket = ProjectTicket.objects.get(id=parent_ticket_id, project=project)
        except ProjectTicket.DoesNotExist:
            pass  # Parent ticket not found, that's ok

    # Build description with context
    full_description = description
    if parent_ticket:
        full_description = f"""**User Action Required**

{description}

---
*This ticket was automatically created while working on: #{parent_ticket.id} - {parent_ticket.name}*
"""
    else:
        full_description = f"""**User Action Required**

{description}
"""

    # Add action type badge to title
    action_badges = {
        'add_api_key': '🔑',
        'configure_setting': '⚙️',
        'review_code': '👀',
        'manual_fix': '🔧',
        'other': '📋'
    }
    badge = action_badges.get(action_type, '📋')
    full_title = f"{badge} {title}"

    # Create the ticket
    # Get the max order for existing tickets in the project
    from django.db.models import Max
    max_order = ProjectTicket.objects.filter(project=project).aggregate(Max('order'))['order__max']
    new_order = (max_order or 0) + 1

    new_ticket = ProjectTicket.objects.create(
        project=project,
        name=full_title[:255],
        description=full_description,
        status='open',
        priority=priority,
        order=new_order,
        notes=f"[Auto-created] Action type: {action_type}\nMetadata: {json.dumps(metadata)}"
    )

    # If there's a parent ticket, add a note to it
    if parent_ticket:
        parent_ticket.notes = (parent_ticket.notes or '') + f"\n\n[CLI] Created user action ticket #{new_ticket.id}: {title}"
        parent_ticket.save(update_fields=['notes'])

    # Broadcast notification about new ticket
    try:
        broadcast_ticket_notification(0, {
            'is_notification': True,
            'notification_type': 'new_ticket',
            'ticket_id': new_ticket.id,
            'ticket_name': new_ticket.name,
            'project_id': str(project.project_id),
            'action_type': action_type,
            'priority': priority,
            'message': f"Action required: {title}"
        })
    except Exception as e:
        logger.warning(f"[CLI API] Failed to broadcast new ticket: {e}")

    logger.info(f"[CLI API] Created user action ticket #{new_ticket.id}: {title}")

    return JsonResponse({
        'status': 'ok',
        'ticket_id': new_ticket.id,
        'ticket_name': new_ticket.name,
        'message': f'User action ticket created: {title}'
    })


@csrf_exempt
@require_http_methods(["POST"])
@cli_api_key_required
def cli_request_user_input(request):
    """
    Request input from the user (blocks current ticket until user responds).

    This allows Claude to ask the user a question and wait for a response
    before continuing with the implementation.

    POST /api/v1/cli/request-input/
    Header: X-CLI-API-Key: <key>
    Body: {
        "ticket_id": 123,
        "question": "Which authentication method should I use?",
        "options": ["OAuth", "JWT", "Session-based"],  // Optional - if not provided, free-form input
        "context": "I need to implement authentication but there are multiple approaches..."
    }
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    ticket_id = body.get('ticket_id')
    question = body.get('question')
    options = body.get('options', [])
    context = body.get('context', '')

    if not ticket_id:
        return JsonResponse({'error': 'ticket_id required'}, status=400)
    if not question:
        return JsonResponse({'error': 'question required'}, status=400)

    ticket, error = validate_ticket_access(request, ticket_id)
    if error:
        return error

    # Mark ticket as blocked waiting for user input
    ticket.status = 'blocked'
    ticket.queue_status = 'waiting_for_input'
    ticket.notes = (ticket.notes or '') + f"\n\n[CLI] Waiting for user input:\nQuestion: {question}"
    if options:
        ticket.notes += f"\nOptions: {', '.join(options)}"
    ticket.save(update_fields=['status', 'queue_status', 'notes'])

    # Create a log entry for the question
    log_entry = TicketLog.objects.create(
        ticket_id=ticket_id,
        log_type='ai_response',
        command='Question for User',
        output=f"**{question}**\n\n{context}" + (f"\n\nOptions:\n" + "\n".join(f"- {opt}" for opt in options) if options else "")
    )

    # Broadcast the question via WebSocket
    try:
        from asgiref.sync import async_to_sync
        async_to_sync(async_send_ticket_log_notification)(ticket_id, {
            'id': log_entry.id,
            'log_type': log_entry.log_type,
            'command': log_entry.command,
            'output': log_entry.output,
            'created_at': log_entry.created_at.isoformat()
        })

        # Also broadcast a special notification for user input request
        broadcast_ticket_notification(ticket.conversation_id or 0, {
            'is_notification': True,
            'notification_type': 'user_input_required',
            'ticket_id': ticket_id,
            'ticket_name': ticket.name,
            'question': question,
            'options': options,
            'context': context,
            'message': f"Input needed: {question}"
        })

        broadcast_ticket_status_change(ticket_id, 'blocked', 'waiting_for_input')
    except Exception as e:
        logger.warning(f"[CLI API] Failed to broadcast input request: {e}")

    logger.info(f"[CLI API] Ticket {ticket_id} waiting for user input: {question}")

    return JsonResponse({
        'status': 'ok',
        'ticket_status': 'blocked',
        'queue_status': 'waiting_for_input',
        'message': 'Waiting for user input'
    })
