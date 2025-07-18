from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from .models import Project, ProjectFeature, ProjectPersona, ProjectPRD, ProjectImplementation, ProjectDesignSchema, ProjectChecklist, ToolCallHistory
from django.views.decorators.http import require_POST
from django.core.exceptions import PermissionDenied
import asyncio
import subprocess
import time
from pathlib import Path
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import json

# Import ServerConfig from development app
from development.models import ServerConfig
from accounts.models import LLMApiKeys, ExternalServicesAPIKeys
from utils.easylogs import log_info

# Import the functions from ai_functions
from development.utils.ai_functions import execute_local_command, restart_server_from_config

# Create your views here.

@login_required
def project_list(request):
    """View to display all projects for the current user"""
    projects = Project.objects.filter(owner=request.user).order_by('-created_at')
    
    # Annotate each project with counts
    projects_with_stats = []
    for project in projects:
        # Count conversations
        conversations_count = project.direct_conversations.count()
        
        # Count documents (tool call histories that generated content)
        documents_count = project.tool_call_histories.filter(
            tool_name__in=['create_prd', 'create_implementation_plan', 'create_design_schema']
        ).count()
        
        # Count tickets (checklist items)
        tickets_count = project.checklist.count()
        
        projects_with_stats.append({
            'project': project,
            'conversations_count': conversations_count,
            'documents_count': documents_count,
            'tickets_count': tickets_count
        })
    
    return render(request, 'projects/project_list.html', {
        'projects': projects_with_stats
    })

@login_required
def project_detail(request, project_id):
    """View to display a specific project"""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    
    # If it's an API request, return JSON
    if request.headers.get('Accept') == 'application/json' or request.GET.get('format') == 'json':
        return JsonResponse({
            'id': project.id,
            'name': project.name,
            'description': project.description,
            'linear_sync_enabled': project.linear_sync_enabled,
            'linear_team_id': project.linear_team_id,
            'linear_project_id': project.linear_project_id,
        })
    
    log_info(f"Project direct conversations: {project.direct_conversations.all()}", project_id=project.id, project_name=project.name)
    return render(request, 'projects/project_detail.html', {
        'project': project
    })

@login_required
def create_project(request):
    """View to create a new project"""
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        icon = request.POST.get('icon', '📋')
        
        if not name:
            messages.error(request, "Project name is required")
            return redirect('create_project')
        
        project = Project.objects.create(
            name=name,
            description=description,
            icon=icon,
            owner=request.user
        )
        
        # messages.success(request, f"Project '{name}' created successfully!")
        
        # Redirect to create a conversation for this project
        return redirect('create_conversation', project_id=project.project_id)
    
    return render(request, 'projects/create_project.html')

@login_required
@require_POST
def create_project_api(request):
    """API endpoint to create a new project"""
    try:
        data = json.loads(request.body)
        
        # Check if this is just a request to check existing projects
        if data.get('check_existing'):
            projects = Project.objects.filter(owner=request.user)
            project_list = []
            for p in projects[:10]:  # Limit to 10 most recent projects
                project_list.append({
                    'id': str(p.project_id),
                    'name': p.name,
                    'created_at': p.created_at.strftime('%Y-%m-%d')
                })
            return JsonResponse({
                'success': True,
                'has_existing_projects': projects.exists(),
                'project_count': projects.count(),
                'projects': project_list
            })
        
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        requirements = data.get('requirements', '')
        
        if not name:
            return JsonResponse({
                'success': False,
                'error': 'Project name is required'
            }, status=400)
        
        # Create the project
        project = Project.objects.create(
            name=name,
            description=description,
            owner=request.user,
            icon='🚀'  # Default rocket icon for projects from landing
        )
        
        return JsonResponse({
            'success': True,
            'project_id': str(project.project_id),
            'project': {
                'id': project.id,
                'project_id': str(project.project_id),
                'name': project.name,
                'description': project.description,
                'icon': project.icon,
                'created_at': project.created_at.isoformat()
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
def update_project(request, project_id):
    """View to update a project"""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    
    if request.method == 'POST':
        project.name = request.POST.get('name', project.name)
        project.description = request.POST.get('description', project.description)
        project.icon = request.POST.get('icon', project.icon)
        project.status = request.POST.get('status', project.status)
        
        # Handle Linear integration settings
        project.linear_sync_enabled = request.POST.get('linear_sync_enabled') == 'on'
        if project.linear_sync_enabled:
            project.linear_team_id = request.POST.get('linear_team_id', '').strip()
            project.linear_project_id = request.POST.get('linear_project_id', '').strip()
        else:
            # Clear Linear settings if sync is disabled
            project.linear_team_id = ''
            project.linear_project_id = ''
        
        project.save()
        
        messages.success(request, "Project updated successfully!")
        return redirect('projects:project_detail', project_id=project.project_id)
    
    # For GET requests, render the update form
    # Check if user has Linear API key
    try:
        external_keys = ExternalServicesAPIKeys.objects.get(user=request.user)
        has_linear_key = bool(external_keys.linear_api_key)
    except ExternalServicesAPIKeys.DoesNotExist:
        has_linear_key = False
    
    return render(request, 'projects/update_project.html', {
        'project': project,
        'has_linear_key': has_linear_key
    })

@login_required
@require_POST
def delete_project(request, project_id):
    """View to delete a project"""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    project_name = project.name
    project.delete()
    
    messages.success(request, f"Project '{project_name}' deleted successfully")
    return redirect('projects:project_list')

@login_required
def project_features_api(request, project_id):
    """API view to get features for a project"""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    features = ProjectFeature.objects.filter(project=project).order_by('-created_at')
    
    features_list = []
    for feature in features:
        features_list.append({
            'id': feature.id,
            'name': feature.name,
            'description': feature.description,
            'details': feature.details,
            'priority': feature.priority
        })
    
    return JsonResponse({'features': features_list})

@login_required
def project_personas_api(request, project_id):
    """API view to get personas for a project"""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    personas = ProjectPersona.objects.filter(project=project).order_by('-created_at')
    
    personas_list = []
    for persona in personas:
        personas_list.append({
            'id': persona.id,
            'name': persona.name,
            'role': persona.role,
            'description': persona.description
        })
    
    return JsonResponse({'personas': personas_list})

@login_required
def project_prd_api(request, project_id):
    """API view to get or update PRD for a project"""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    
    import json
    
    # Get PRD name from query params or default
    prd_name = request.GET.get('prd_name', 'Main PRD')
    
    if request.method == 'GET' and 'list' in request.GET:
        # List all PRDs for the project
        prds = ProjectPRD.objects.filter(project=project).order_by('-updated_at')
        prds_list = []
        for prd in prds:
            prds_list.append({
                'id': prd.id,
                'name': prd.name,
                'is_active': prd.is_active,
                'created_at': prd.created_at.strftime('%Y-%m-%d %H:%M'),
                'updated_at': prd.updated_at.strftime('%Y-%m-%d %H:%M')
            })
        return JsonResponse({'prds': prds_list})
    
    # Get the PRD by name or create it if it doesn't exist
    prd, created = ProjectPRD.objects.get_or_create(
        project=project,
        name=prd_name,
        defaults={'prd': ''}  # Default empty content if we're creating a new PRD
    )
    
    if request.method == 'POST':
        # Update PRD content
        try:
            data = json.loads(request.body)
            prd.prd = data.get('content', '')
            prd.save()
            
            return JsonResponse({
                'success': True,
                'id': prd.id,
                'name': prd.name,
                'content': prd.prd,
                'title': f'PRD: {prd.name}',
                'updated_at': prd.updated_at.strftime('%Y-%m-%d %H:%M') if prd.updated_at else None
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
    elif request.method == 'DELETE':
        # Delete PRD (but don't allow deleting the Main PRD)
        if prd_name == 'Main PRD':
            return JsonResponse({'success': False, 'error': 'Cannot delete the Main PRD'}, status=400)
        
        try:
            prd.delete()
            return JsonResponse({
                'success': True,
                'message': f'PRD "{prd_name}" deleted successfully'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
    # Convert to JSON-serializable format
    prd_data = {
        'id': prd.id,
        'name': prd.name,
        'content': prd.prd,
        'title': f'PRD: {prd.name}',
        'updated_at': prd.updated_at.strftime('%Y-%m-%d %H:%M') if prd.updated_at else None
    }
    
    return JsonResponse(prd_data)   

@login_required
def project_design_schema_api(request, project_id):
    """API view to get design schema for a project"""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    
    # Get the design schema or create it if it doesn't exist
    design_schema, created = ProjectDesignSchema.objects.get_or_create(
        project=project,
        defaults={'design_schema': ''}  # Default empty content if we're creating a new design schema
    )
    
    # Convert to JSON-serializable format
    design_schema_data = {
        'id': design_schema.id,
        'content': design_schema.design_schema,
        'title': 'Design Schema',
        'updated_at': design_schema.updated_at.strftime('%Y-%m-%d %H:%M') if design_schema.updated_at else None
    }
    
    return JsonResponse(design_schema_data)

# ProjectTickets has been removed - use ProjectChecklist instead

@login_required
def project_checklist_api(request, project_id):
    """API view to get checklist items for a project"""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    
    # Get all checklist items for this project
    checklist_items = ProjectChecklist.objects.filter(project=project)
    
    checklist_list = []
    for item in checklist_items:
        checklist_list.append({
            'id': item.id,
            'name': item.name,
            'description': item.description,
            'status': item.status,
            'priority': item.priority,
            'role': item.role,
            'created_at': item.created_at.isoformat(),
            'updated_at': item.updated_at.isoformat(),
            'details': item.details,
            'ui_requirements': item.ui_requirements,
            'component_specs': item.component_specs,
            'acceptance_criteria': item.acceptance_criteria,
            'dependencies': item.dependencies,
            'complexity': item.complexity,
            'requires_worktree': item.requires_worktree,
            # Linear integration fields
            'linear_issue_id': item.linear_issue_id,
            'linear_issue_url': item.linear_issue_url,
            'linear_state': item.linear_state,
            'linear_priority': item.linear_priority,
            'linear_assignee_id': item.linear_assignee_id,
            'linear_synced_at': item.linear_synced_at.isoformat() if item.linear_synced_at else None,
            'linear_sync_enabled': item.linear_sync_enabled,
        })
    
    return JsonResponse({'checklist': checklist_list})

@login_required
def project_server_configs_api(request, project_id):
    """API view to get server configurations for a project"""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    
    # Get all server configs for this project
    server_configs = ServerConfig.objects.filter(project=project).order_by('port')
    
    configs_list = []
    for config in server_configs:
        configs_list.append({
            'id': config.id,
            'command': config.command,
            'start_server_command': config.start_server_command,
            'port': config.port,
            'type': config.type,
            'created_at': config.created_at.isoformat(),
            'updated_at': config.updated_at.isoformat(),
        })
    
    return JsonResponse({'server_configs': configs_list})

@login_required
def project_terminal(request, project_id):
    """
    View for the terminal page of a project.
    This can either be a local terminal or a connection to a Kubernetes pod.
    """
    project = get_object_or_404(Project, project_id=project_id)
    
    # Check if the user has permission to access this project
    if project.owner != request.user:
        raise PermissionDenied("You don't have permission to access this project.")
    
    # You can add pod information here if you have Kubernetes integration
    pod = None
    
    context = {
        'project': project,
        'pod': pod,
        'active_tab': 'terminal',
    }
    
    return render(request, 'projects/terminal.html', context)

@login_required
def project_implementation_api(request, project_id):
    """API view to get or update implementation for a project"""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    
    # Get the implementation or create it if it doesn't exist
    implementation, created = ProjectImplementation.objects.get_or_create(
        project=project,
        defaults={'implementation': ''}  # Default empty content if we're creating a new implementation
    )
    
    if request.method == 'POST':
        # Update implementation content
        import json
        try:
            data = json.loads(request.body)
            implementation.implementation = data.get('content', '')
            implementation.save()
            
            return JsonResponse({
                'success': True,
                'id': implementation.id,
                'content': implementation.implementation,
                'title': 'Implementation Plan',
                'updated_at': implementation.updated_at.strftime('%Y-%m-%d %H:%M') if implementation.updated_at else None
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
    # Convert to JSON-serializable format
    implementation_data = {
        'id': implementation.id,
        'content': implementation.implementation,
        'title': 'Implementation Plan',
        'updated_at': implementation.updated_at.strftime('%Y-%m-%d %H:%M') if implementation.updated_at else None
    }
    
    return JsonResponse(implementation_data)

@login_required
def check_server_status_api(request, project_id):
    """API view to check server status and restart if needed"""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    
    try:
        # Get server configurations for this project
        server_configs = ServerConfig.objects.filter(project=project)
        
        if not server_configs.exists():
            return JsonResponse({
                'status': 'no_config',
                'message': 'No server configurations found for this project',
                'servers': []
            })
        
        # Create workspace directory if it doesn't exist
        workspace_path = Path.home() / "LFG" / "workspace" / project.provided_name
        workspace_path.mkdir(parents=True, exist_ok=True)
        
        server_status = []
        
        for config in server_configs:
            port = config.port
            server_type = config.type or 'application'
            
            # Always kill any existing process on the port first
            kill_command = f"lsof -ti:{port} | xargs kill -9 2>/dev/null || true"
            execute_local_command(kill_command, str(workspace_path))
            
            # Wait a moment for port to be freed
            time.sleep(1)
            
            # Now attempt to start the server
            server_command = config.start_server_command or config.command
            
            if server_command:
                # Create log file for the server
                log_file = workspace_path / f"server_{project_id}_{port}.log"
                
                # Use nohup to run in background
                background_command = f"nohup {server_command} > {log_file} 2>&1 &"
                restart_success, restart_stdout, restart_stderr = execute_local_command(background_command, str(workspace_path))
                
                if restart_success:
                    # Wait a bit for server to start
                    time.sleep(3)
                    
                    # Check if server is running
                    check_command = f"lsof -i:{port} | grep LISTEN"
                    recheck_success, recheck_stdout, recheck_stderr = execute_local_command(check_command, str(workspace_path))
                    
                    if recheck_success and recheck_stdout.strip():
                        server_status.append({
                            'port': port,
                            'type': server_type,
                            'status': 'restarted',
                            'url': f'http://localhost:{port}',
                            'message': f'{server_type.capitalize()} server started successfully on port {port}'
                        })
                    else:
                        server_status.append({
                            'port': port,
                            'type': server_type,
                            'status': 'failed',
                            'url': f'http://localhost:{port}',
                            'message': f'Failed to start {server_type} server on port {port}. Check logs at {log_file}'
                        })
                else:
                    server_status.append({
                        'port': port,
                        'type': server_type,
                        'status': 'failed',
                        'url': f'http://localhost:{port}',
                        'message': f'Failed to start {server_type} server: {restart_stderr}'
                    })
            else:
                server_status.append({
                    'port': port,
                    'type': server_type,
                    'status': 'no_command',
                    'url': f'http://localhost:{port}',
                    'message': f'No start command configured for {server_type} server on port {port}'
                })
        
        # Determine overall status
        if all(server['status'] in ['running', 'restarted'] for server in server_status):
            overall_status = 'all_running'
            overall_message = 'All servers are running successfully'
        elif any(server['status'] in ['running', 'restarted'] for server in server_status):
            overall_status = 'partial_running'
            overall_message = 'Some servers are running'
        else:
            overall_status = 'none_running'
            overall_message = 'No servers are currently running'
        
        return JsonResponse({
            'status': overall_status,
            'message': overall_message,
            'servers': server_status
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error checking server status: {str(e)}',
            'servers': []
        })

@csrf_exempt
@login_required
@require_POST
def update_checklist_item_api(request, project_id):
    """API endpoint to update status or role of a checklist item"""
    import json
    try:
        data = json.loads(request.body.decode('utf-8'))
        item_id = data.get('item_id')
        new_status = data.get('status')
        new_role = data.get('role')
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'Invalid request data', 'details': str(e)}, status=400)

    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    try:
        item = ProjectChecklist.objects.get(id=item_id, project=project)
    except ProjectChecklist.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Checklist item not found'}, status=404)

    changed = False
    if new_status and new_status != item.status:
        item.status = new_status
        changed = True
    if new_role and new_role != item.role:
        item.role = new_role
        changed = True
    if changed:
        item.updated_at = timezone.now()
        item.save()
        return JsonResponse({'success': True, 'id': item.id, 'status': item.status, 'role': item.role, 'updated_at': item.updated_at})
    else:
        return JsonResponse({'success': False, 'error': 'No changes made'})

@login_required
def project_tool_call_history_api(request, project_id):
    """API view to get tool call history for a project"""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    
    # Get query parameters for filtering
    tool_name = request.GET.get('tool_name')
    limit = int(request.GET.get('limit', 50))
    offset = int(request.GET.get('offset', 0))
    
    # Build query
    query = ToolCallHistory.objects.filter(project=project)
    
    if tool_name:
        query = query.filter(tool_name=tool_name)
    
    # Get total count before pagination
    total_count = query.count()
    
    # Apply pagination
    tool_calls = query[offset:offset+limit]
    
    # Serialize the data
    history_data = []
    for call in tool_calls:
        history_data.append({
            'id': call.id,
            'tool_name': call.tool_name,
            'tool_input': call.tool_input,
            'generated_content': call.generated_content,
            'content_type': call.content_type,
            'metadata': call.metadata,
            'created_at': call.created_at.isoformat(),
            'conversation_id': call.conversation_id if call.conversation else None,
            'message_id': call.message_id if call.message else None
        })
    
    return JsonResponse({
        'tool_call_history': history_data,
        'total_count': total_count,
        'limit': limit,
        'offset': offset,
        'has_more': (offset + limit) < total_count
    })


@login_required
def linear_sync_tickets_api(request, project_id):
    """API view to sync project tickets with Linear"""
    from .linear_sync import LinearSyncService
    
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    # Check if user has Linear API key
    try:
        external_keys = ExternalServicesAPIKeys.objects.get(user=request.user)
        linear_api_key = external_keys.linear_api_key
    except ExternalServicesAPIKeys.DoesNotExist:
        linear_api_key = None
    
    if not linear_api_key:
        return JsonResponse({
            'success': False, 
            'error': 'Linear API key not configured. Please set it up in your integrations.'
        })
    
    # Check if project has Linear team ID set
    if not project.linear_team_id:
        return JsonResponse({
            'success': False,
            'error': 'Linear team ID not set for this project. Please configure it in project settings.'
        })
    
    # Initialize Linear sync service
    linear_service = LinearSyncService(linear_api_key)
    
    # Test connection first
    connected, result = linear_service.test_connection()
    if not connected:
        return JsonResponse({
            'success': False,
            'error': f'Failed to connect to Linear: {result}'
        })
    
    # Perform sync
    success, sync_results = linear_service.sync_all_tickets(project)
    
    if success:
        return JsonResponse({
            'success': True,
            'results': sync_results,
            'message': f"Synced {sync_results['created']} new and {sync_results['updated']} existing tickets"
        })
    else:
        return JsonResponse({
            'success': False,
            'error': sync_results
        })


@login_required
def linear_teams_api(request, project_id):
    """API view to get Linear teams for the current user"""
    from .linear_sync import LinearSyncService
    
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    
    # Check if user has Linear API key
    try:
        external_keys = ExternalServicesAPIKeys.objects.get(user=request.user)
        linear_api_key = external_keys.linear_api_key
    except ExternalServicesAPIKeys.DoesNotExist:
        linear_api_key = None
    
    if not linear_api_key:
        return JsonResponse({
            'success': False,
            'error': 'Linear API key not configured'
        })
    
    # Initialize Linear sync service
    linear_service = LinearSyncService(linear_api_key)
    
    # Get teams
    teams = linear_service.get_teams()
    
    return JsonResponse({
        'success': True,
        'teams': teams
    })


@login_required
def linear_projects_api(request, project_id):
    """API view to get Linear projects for a specific team"""
    from .linear_sync import LinearSyncService
    
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    team_id = request.GET.get('team_id')
    
    if not team_id:
        return JsonResponse({
            'success': False,
            'error': 'Team ID is required'
        })
    
    # Check if user has Linear API key
    try:
        external_keys = ExternalServicesAPIKeys.objects.get(user=request.user)
        linear_api_key = external_keys.linear_api_key
    except ExternalServicesAPIKeys.DoesNotExist:
        linear_api_key = None
    
    if not linear_api_key:
        return JsonResponse({
            'success': False,
            'error': 'Linear API key not configured'
        })
    
    # Initialize Linear sync service
    linear_service = LinearSyncService(linear_api_key)
    
    # Get projects
    projects = linear_service.get_projects(team_id)
    
    return JsonResponse({
        'success': True,
        'projects': projects
    })


@login_required
def delete_checklist_item_api(request, project_id, item_id):
    """API endpoint to delete a checklist item"""
    if request.method != 'DELETE':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    
    try:
        checklist_item = ProjectChecklist.objects.get(id=item_id, project=project)
        checklist_item.delete()
        
        return JsonResponse({
            'success': True,
            'message': 'Checklist item deleted successfully'
        })
    except ProjectChecklist.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Checklist item not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def linear_create_project_api(request, project_id):
    """API view to create a new Linear project"""
    from .linear_sync import LinearSyncService
    import json
    
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        team_id = data.get('team_id')
        project_name = data.get('name')
        project_description = data.get('description', '')
        
        if not team_id or not project_name:
            return JsonResponse({
                'success': False,
                'error': 'Team ID and project name are required'
            })
        
        # Check if user has Linear API key
        try:
            llm_keys = LLMApiKeys.objects.get(user=request.user)
            linear_api_key = llm_keys.linear_api_key
        except LLMApiKeys.DoesNotExist:
            linear_api_key = None
        
        if not linear_api_key:
            return JsonResponse({
                'success': False,
                'error': 'Linear API key not configured'
            })
        
        # Initialize Linear sync service
        linear_service = LinearSyncService(linear_api_key)
        
        # Create the project
        success, result = linear_service.create_project(team_id, project_name, project_description)
        
        if success:
            return JsonResponse({
                'success': True,
                'project': result
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result
            })
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

