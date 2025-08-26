from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from .models import Project, ProjectFeature, ProjectPersona, ProjectFile, ProjectDesignSchema, ProjectChecklist, ToolCallHistory, ProjectMember, ProjectInvitation
from django.views.decorators.http import require_POST, require_http_methods
from django.core.exceptions import PermissionDenied
from django.db.models import Q
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
import logging

logger = logging.getLogger(__name__)

# Import the functions from ai_functions
from factory.ai_functions import execute_local_command, restart_server_from_config

# Create your views here.

@login_required
def project_list(request):
    """View to display all projects for the current user"""
    # Get projects where user is owner
    owned_projects = Project.objects.filter(owner=request.user)
    
    # Get projects where user is a member (with fallback for migration issues)
    try:
        member_projects = Project.objects.filter(
            members__user=request.user,
            members__status='active'
        ).exclude(owner=request.user)
    except Exception:
        # Fallback if ProjectMember table doesn't exist yet
        member_projects = Project.objects.none()
    
    # Combine and order projects
    projects = list(owned_projects) + list(member_projects)
    projects.sort(key=lambda p: p.updated_at, reverse=True)
    
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
    project = get_object_or_404(Project, project_id=project_id)
    
    # Check if user has access to this project
    if not project.can_user_access(request.user):
        raise PermissionDenied("You don't have permission to access this project.")
    
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
    
    logger.info(f"Project direct conversations: {project.direct_conversations.all()}", extra={'easylogs_metadata': {'project_id': project.id, 'project_name': project.name}})
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
    project = get_object_or_404(Project, project_id=project_id)
    
    # Check if user has access to this project
    if not project.can_user_access(request.user):
        raise PermissionDenied("You don't have permission to access this project.")
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
    project = get_object_or_404(Project, project_id=project_id)
    
    # Check if user has access to this project
    if not project.can_user_access(request.user):
        raise PermissionDenied("You don't have permission to access this project.")
    
    # For POST requests (updates), check file editing permission
    if request.method == 'POST' and not project.can_user_edit_files(request.user):
        return JsonResponse({
            'success': False,
            'error': 'You do not have permission to edit files in this project'
        }, status=403)
    
    import json
    
    # Get PRD name from query params or default
    prd_name = request.GET.get('prd_name', 'Main PRD')
    
    if request.method == 'GET' and 'list' in request.GET:
        # List all PRDs for the project
        prds = ProjectFile.objects.filter(project=project, file_type='prd').order_by('-updated_at')
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
    prd, created = ProjectFile.objects.get_or_create(
        project=project,
        name=prd_name,
        file_type='prd',
        defaults={'content': ''}  # Default empty content if we're creating a new PRD
    )
    
    if request.method == 'POST':
        # Update PRD content
        try:
            data = json.loads(request.body)
            prd.save_content(data.get('content', ''))
            prd.save()
            
            return JsonResponse({
                'success': True,
                'id': prd.id,
                'name': prd.name,
                'content': prd.file_content,
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
        'content': prd.file_content,
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
    project = get_object_or_404(Project, project_id=project_id)
    
    # Check if user has access to this project
    if not project.can_user_access(request.user):
        raise PermissionDenied("You don't have permission to access this project.")
    
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
    implementation, created = ProjectFile.objects.get_or_create(
        project=project,
        name='Technical Implementation Plan',
        file_type='implementation',
        defaults={'content': ''}  # Default empty content if we're creating a new implementation
    )
    
    if request.method == 'POST':
        # Update implementation content
        import json
        try:
            data = json.loads(request.body)
            implementation.save_content(data.get('content', ''))
            implementation.save()
            
            return JsonResponse({
                'success': True,
                'id': implementation.id,
                'content': implementation.file_content,
                'title': 'Implementation Plan',
                'updated_at': implementation.updated_at.strftime('%Y-%m-%d %H:%M') if implementation.updated_at else None
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
    elif request.method == 'DELETE':
        # Delete the implementation
        try:
            implementation.delete()
            return JsonResponse({'success': True, 'message': 'Implementation deleted successfully'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
    # Convert to JSON-serializable format
    implementation_data = {
        'id': implementation.id,
        'content': implementation.file_content,
        'title': 'Implementation Plan',
        'updated_at': implementation.updated_at.strftime('%Y-%m-%d %H:%M') if implementation.updated_at else None
    }
    
    return JsonResponse(implementation_data)

@login_required
def project_files_api(request, project_id):
    """Unified API to get, create, update, or delete project files by type"""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    
    import json
    
    # Get file type and name from query params
    file_type = request.GET.get('type')  # prd, implementation, design, test, etc.
    file_name = request.GET.get('name')
    
    if request.method == 'GET' and 'list' in request.GET:
        # List all files of a specific type or all files
        if file_type:
            files = ProjectFile.objects.filter(project=project, file_type=file_type).order_by('-updated_at')
        else:
            files = ProjectFile.objects.filter(project=project).order_by('-updated_at')
        
        files_list = []
        for file_obj in files:
            files_list.append({
                'id': file_obj.id,
                'name': file_obj.name,
                'type': file_obj.file_type,
                'is_active': file_obj.is_active,
                'created_at': file_obj.created_at.strftime('%Y-%m-%d %H:%M'),
                'updated_at': file_obj.updated_at.strftime('%Y-%m-%d %H:%M')
            })
        return JsonResponse({'files': files_list})
    
    # For specific file operations, both type and name are required
    if not file_type or not file_name:
        return JsonResponse({'error': 'Both type and name parameters are required'}, status=400)
    
    if request.method == 'GET':
        # Get a specific file
        try:
            file_obj = ProjectFile.objects.get(project=project, file_type=file_type, name=file_name)
            return JsonResponse({
                'id': file_obj.id,
                'name': file_obj.name,
                'type': file_obj.file_type,
                'content': file_obj.file_content,
                'title': file_obj.name,
                'created_at': file_obj.created_at.strftime('%Y-%m-%d %H:%M'),
                'updated_at': file_obj.updated_at.strftime('%Y-%m-%d %H:%M')
            })
        except ProjectFile.DoesNotExist:
            return JsonResponse({'error': 'File not found'}, status=404)
    
    elif request.method == 'POST':
        # Create or update a file
        try:
            data = json.loads(request.body)
            file_obj, created = ProjectFile.objects.get_or_create(
                project=project,
                file_type=file_type,
                name=file_name,
                defaults={}
            )
            
            file_obj.save_content(data.get('content', ''))
            file_obj.save()
            
            return JsonResponse({
                'success': True,
                'id': file_obj.id,
                'name': file_obj.name,
                'type': file_obj.file_type,
                'content': file_obj.file_content,
                'created': created,
                'updated_at': file_obj.updated_at.strftime('%Y-%m-%d %H:%M')
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
    elif request.method == 'DELETE':
        # Delete a file
        try:
            file_obj = ProjectFile.objects.get(project=project, file_type=file_type, name=file_name)
            file_obj.delete()
            return JsonResponse({
                'success': True,
                'message': f'{file_obj.get_file_type_display()} "{file_name}" deleted successfully'
            })
        except ProjectFile.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'File not found'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)

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

    project = get_object_or_404(Project, project_id=project_id)
    
    # Check if user can manage tickets
    if not project.can_user_manage_tickets(request.user):
        return JsonResponse({
            'success': False,
            'error': 'You do not have permission to manage tickets in this project'
        }, status=403)
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


@login_required
def file_browser_api(request, project_id):
    """Enhanced API for file browser with search, filtering, and sorting"""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    
    from django.db.models import Q
    from django.core.paginator import Paginator
    
    # Get query parameters
    search_query = request.GET.get('search', '')
    file_type_filter = request.GET.get('type', '')
    sort_by = request.GET.get('sort', 'updated_at')  # updated_at, created_at, name, type
    sort_order = request.GET.get('order', 'desc')  # asc, desc
    page = request.GET.get('page', 1)
    per_page = request.GET.get('per_page', 20)
    
    # Start with base queryset
    files = ProjectFile.objects.filter(project=project)
    
    # Apply search filter
    if search_query:
        # Search in name and content
        files = files.filter(
            Q(name__icontains=search_query) |
            Q(content__icontains=search_query)
        )
    
    # Apply type filter
    if file_type_filter:
        files = files.filter(file_type=file_type_filter)
    
    # Apply sorting
    order_prefix = '-' if sort_order == 'desc' else ''
    if sort_by in ['updated_at', 'created_at', 'name', 'file_type']:
        files = files.order_by(f'{order_prefix}{sort_by}')
    else:
        files = files.order_by(f'{order_prefix}updated_at')
    
    # Get file type statistics for filters
    type_stats = {}
    all_files = ProjectFile.objects.filter(project=project)
    for file_type, display_name in ProjectFile.FILE_TYPES:
        count = all_files.filter(file_type=file_type).count()
        if count > 0:
            type_stats[file_type] = {
                'name': display_name,
                'count': count
            }
    
    # Paginate results
    paginator = Paginator(files, per_page)
    try:
        page_obj = paginator.page(page)
    except:
        page_obj = paginator.page(1)
    
    # Build response
    files_list = []
    for file_obj in page_obj:
        # Get file size (approximate based on content length)
        # content = file_obj.file_content or ''
        # file_size = len(content.encode('utf-8'))
        
        files_list.append({
            'id': file_obj.id,
            'name': file_obj.name,
            'type': file_obj.file_type,
            'type_display': file_obj.get_file_type_display(),
            'is_active': file_obj.is_active,
            # 'size': file_size,
            # 'size_display': _format_file_size(file_size),
            'created_at': file_obj.created_at.isoformat(),
            'updated_at': file_obj.updated_at.isoformat(),
            'created_at_display': file_obj.created_at.strftime('%Y-%m-%d %H:%M'),
            'updated_at_display': file_obj.updated_at.strftime('%Y-%m-%d %H:%M'),
            'has_content': bool(file_obj.content or file_obj.s3_key),
            # 'preview': content[:200] + '...' if len(content) > 200 else content,
            'owner': file_obj.project.owner.username if file_obj.project.owner else 'System'
        })
    
    return JsonResponse({
        'files': files_list,
        'pagination': {
            'page': page_obj.number,
            'pages': paginator.num_pages,
            'per_page': per_page,
            'total': paginator.count,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous()
        },
        'filters': {
            'types': type_stats,
            'current_type': file_type_filter,
            'search': search_query,
            'sort_by': sort_by,
            'sort_order': sort_order
        }
    })


@login_required
def file_content_api(request, project_id, file_id):
    """API to get full content of a specific file"""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    file_obj = get_object_or_404(ProjectFile, id=file_id, project=project)
    
    return JsonResponse({
        'id': file_obj.id,
        'name': file_obj.name,
        'type': file_obj.file_type,
        'type_display': file_obj.get_file_type_display(),
        'content': file_obj.file_content,
        'created_at': file_obj.created_at.isoformat(),
        'updated_at': file_obj.updated_at.isoformat()
    })


@require_http_methods(["GET", "POST"])
@login_required
def file_versions_api(request, project_id, file_id):
    """API to manage file versions"""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    file_obj = get_object_or_404(ProjectFile, id=file_id, project=project)
    
    if request.method == 'GET':
        # Get all versions
        versions = file_obj.versions.all()
        version_data = []
        
        for version in versions:
            version_data.append({
                'version_number': version.version_number,
                'created_at': version.created_at.isoformat(),
                'created_by': version.created_by.username if version.created_by else 'System',
                'change_description': version.change_description or 'No description'
            })
        
        # Get current version info
        current_version = file_obj.versions.first()
        current_version_number = current_version.version_number if current_version else 0
        
        return JsonResponse({
            'current_version': current_version_number + 1,  # Next version will be current + 1
            'versions': version_data,
            'total_versions': len(version_data)
        })
    
    elif request.method == 'POST':
        # Create a new version (manual save)
        data = json.loads(request.body)
        change_description = data.get('change_description', 'Manual save')
        
        version = file_obj.create_version(
            user=request.user,
            change_description=change_description
        )
        
        if version:
            return JsonResponse({
                'success': True,
                'version_number': version.version_number,
                'message': f'Version {version.version_number} created successfully'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Failed to create version'
            }, status=400)


@require_http_methods(["GET", "POST"])
@login_required
def file_version_content_api(request, project_id, file_id, version_number):
    """API to get content of a specific version or restore to that version"""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    file_obj = get_object_or_404(ProjectFile, id=file_id, project=project)
    
    if request.method == 'GET':
        # Get specific version content
        version = file_obj.get_version(int(version_number))
        if version:
            return JsonResponse({
                'success': True,
                'version_number': version.version_number,
                'content': version.content,
                'created_at': version.created_at.isoformat(),
                'created_by': version.created_by.username if version.created_by else 'System',
                'change_description': version.change_description or 'No description'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Version not found'
            }, status=404)
    
    elif request.method == 'POST':
        # Restore to this version
        if file_obj.restore_version(int(version_number), user=request.user):
            return JsonResponse({
                'success': True,
                'message': f'Successfully restored to version {version_number}'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Failed to restore version'
            }, status=400)


def _format_file_size(size_in_bytes):
    """Format file size in human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.1f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.1f} TB"


@require_POST
@login_required
def file_rename_api(request, project_id, file_id):
    """API to rename a file"""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    file_obj = get_object_or_404(ProjectFile, id=file_id, project=project)
    
    try:
        data = json.loads(request.body)
        new_name = data.get('name', '').strip()
        
        if not new_name:
            return JsonResponse({
                'success': False,
                'error': 'File name cannot be empty'
            }, status=400)
        
        # Check if another file with the same name and type already exists
        existing_file = ProjectFile.objects.filter(
            project=project,
            file_type=file_obj.file_type,
            name=new_name
        ).exclude(id=file_obj.id).first()
        
        if existing_file:
            return JsonResponse({
                'success': False,
                'error': f'A {file_obj.get_file_type_display()} with name "{new_name}" already exists'
            }, status=400)
        
        # Update the file name
        old_name = file_obj.name
        file_obj.name = new_name
        file_obj.save()
        
        return JsonResponse({
            'success': True,
            'message': f'File renamed from "{old_name}" to "{new_name}"',
            'new_name': new_name
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
def file_mentions_api(request, project_id):
    """API to get files for @ mentions in chat"""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    
    # Get search query if provided
    search_query = request.GET.get('q', '').strip()
    
    # Start with all project files
    files = ProjectFile.objects.filter(project=project)
    
    # Apply search filter if provided
    if search_query:
        files = files.filter(
            Q(name__icontains=search_query) |
            Q(file_type__icontains=search_query)
        )
    
    # Order by most recently updated first
    files = files.order_by('-updated_at')[:20]  # Limit to 20 most recent files
    
    # Build response
    files_list = []
    for file_obj in files:
        # Create a display label for the file
        display_label = f"{file_obj.name} ({file_obj.get_file_type_display()})"
        
        files_list.append({
            'id': file_obj.id,
            'name': file_obj.name,
            'type': file_obj.file_type,
            'label': display_label,
            'updated_at': file_obj.updated_at.strftime('%Y-%m-%d %H:%M')
        })
    
    return JsonResponse({
        'files': files_list,
        'count': len(files_list)
    })


@login_required
def project_members_api(request, project_id):
    """API view to get project members"""
    project = get_object_or_404(Project, project_id=project_id)
    
    # Check if user has access to this project
    if not project.can_user_access(request.user):
        raise PermissionDenied("You don't have permission to access this project.")
    
    # Get all active members
    members = ProjectMember.objects.filter(project=project, status='active').select_related('user', 'invited_by')
    
    members_list = []
    
    # Add owner as first member
    members_list.append({
        'id': None,
        'user_id': project.owner.id,
        'username': project.owner.username,
        'email': project.owner.email,
        'first_name': project.owner.first_name,
        'last_name': project.owner.last_name,
        'role': 'owner',
        'status': 'active',
        'joined_at': project.created_at.isoformat(),
        'invited_by': None,
        'is_owner': True,
        'permissions': {
            'can_edit_files': True,
            'can_manage_tickets': True,
            'can_chat': True,
            'can_invite_members': True,
            'can_manage_project': True,
            'can_delete_project': True,
        }
    })
    
    # Add other members
    for member in members:
        members_list.append({
            'id': member.id,
            'user_id': member.user.id,
            'username': member.user.username,
            'email': member.user.email,
            'first_name': member.user.first_name,
            'last_name': member.user.last_name,
            'role': member.role,
            'status': member.status,
            'joined_at': member.joined_at.isoformat(),
            'invited_by': member.invited_by.username if member.invited_by else None,
            'is_owner': False,
            'permissions': member.get_permissions()
        })
    
    return JsonResponse({
        'members': members_list,
        'total_members': len(members_list),
        'user_can_invite': project.can_user_invite_members(request.user)
    })


@login_required
@require_POST
def invite_project_member_api(request, project_id):
    """API view to invite a user to a project"""
    project = get_object_or_404(Project, project_id=project_id)
    
    # Check if user can invite members
    if not project.can_user_invite_members(request.user):
        return JsonResponse({
            'success': False,
            'error': 'You do not have permission to invite members to this project'
        }, status=403)
    
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip().lower()
        role = data.get('role', 'member')
        
        if not email:
            return JsonResponse({
                'success': False,
                'error': 'Email address is required'
            }, status=400)
        
        # Validate role
        valid_roles = [choice[0] for choice in ProjectMember.ROLE_CHOICES if choice[0] != 'owner']
        if role not in valid_roles:
            return JsonResponse({
                'success': False,
                'error': f'Invalid role. Must be one of: {", ".join(valid_roles)}'
            }, status=400)
        
        # Check if user is already a member
        from django.contrib.auth.models import User
        try:
            user = User.objects.get(email=email)
            if project.has_member(user):
                return JsonResponse({
                    'success': False,
                    'error': 'User is already a member of this project'
                }, status=400)
        except User.DoesNotExist:
            pass  # User doesn't exist yet, invitation will be sent
        
        # Create invitation
        invitation = ProjectInvitation.create_invitation(
            project=project,
            inviter=request.user,
            email=email,
            role=role
        )
        
        # Send invitation email (you can implement this separately)
        # send_project_invitation_email(invitation)
        
        return JsonResponse({
            'success': True,
            'message': f'Invitation sent to {email}',
            'invitation_id': invitation.id
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
@require_POST
def update_project_member_api(request, project_id, member_id):
    """API view to update a project member's role or permissions"""
    project = get_object_or_404(Project, project_id=project_id)
    member = get_object_or_404(ProjectMember, id=member_id, project=project)
    
    # Check if user can manage project
    if not project.get_member(request.user) or not project.get_member(request.user).can_manage_project:
        return JsonResponse({
            'success': False,
            'error': 'You do not have permission to manage project members'
        }, status=403)
    
    try:
        data = json.loads(request.body)
        
        # Update role if provided
        new_role = data.get('role')
        if new_role and new_role != member.role:
            valid_roles = [choice[0] for choice in ProjectMember.ROLE_CHOICES if choice[0] != 'owner']
            if new_role not in valid_roles:
                return JsonResponse({
                    'success': False,
                    'error': f'Invalid role. Must be one of: {", ".join(valid_roles)}'
                }, status=400)
            member.role = new_role
        
        # Update individual permissions if provided
        if 'can_edit_files' in data:
            member.can_edit_files = data['can_edit_files']
        if 'can_manage_tickets' in data:
            member.can_manage_tickets = data['can_manage_tickets']
        if 'can_chat' in data:
            member.can_chat = data['can_chat']
        if 'can_invite_members' in data:
            member.can_invite_members = data['can_invite_members']
        
        member.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Member updated successfully',
            'member': {
                'id': member.id,
                'role': member.role,
                'permissions': member.get_permissions()
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
@require_POST
def remove_project_member_api(request, project_id, member_id):
    """API view to remove a member from a project"""
    project = get_object_or_404(Project, project_id=project_id)
    member = get_object_or_404(ProjectMember, id=member_id, project=project)
    
    # Check if user can manage project
    if not project.get_member(request.user) or not project.get_member(request.user).can_manage_project:
        return JsonResponse({
            'success': False,
            'error': 'You do not have permission to manage project members'
        }, status=403)
    
    # Don't allow removing the project owner
    if member.user == project.owner:
        return JsonResponse({
            'success': False,
            'error': 'Cannot remove the project owner'
        }, status=400)
    
    try:
        member_username = member.user.username
        member.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Member {member_username} removed from project'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def project_invitations_api(request, project_id):
    """API view to get pending project invitations"""
    project = get_object_or_404(Project, project_id=project_id)
    
    # Check if user can invite members (to view invitations)
    if not project.can_user_invite_members(request.user):
        return JsonResponse({
            'success': False,
            'error': 'You do not have permission to view project invitations'
        }, status=403)
    
    # Get pending invitations
    invitations = ProjectInvitation.objects.filter(
        project=project,
        status='pending'
    ).select_related('inviter').order_by('-created_at')
    
    invitations_list = []
    for invitation in invitations:
        invitations_list.append({
            'id': invitation.id,
            'email': invitation.email,
            'role': invitation.role,
            'status': invitation.status,
            'created_at': invitation.created_at.isoformat(),
            'expires_at': invitation.expires_at.isoformat(),
            'invited_by': invitation.inviter.username,
            'is_valid': invitation.is_valid()
        })
    
    return JsonResponse({
        'invitations': invitations_list,
        'total_invitations': len(invitations_list)
    })


@login_required
def accept_project_invitation(request, token):
    """View to accept a project invitation"""
    invitation = get_object_or_404(ProjectInvitation, token=token)
    
    if not invitation.is_valid():
        messages.error(request, "This invitation has expired or is no longer valid.")
        return redirect('project_list')
    
    if request.user.email.lower() != invitation.email.lower():
        messages.error(request, "This invitation is for a different email address.")
        return redirect('project_list')
    
    try:
        membership = invitation.accept(request.user)
        messages.success(request, f"You have successfully joined the project '{invitation.project.name}'!")
        return redirect('projects:project_detail', project_id=invitation.project.project_id)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('project_list')
    except Exception as e:
        messages.error(request, "An error occurred while accepting the invitation. Please try again.")
        return redirect('project_list')


