from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from .models import Project, ProjectFeature, ProjectPersona, ProjectPRD, ProjectImplementation, ProjectDesignSchema, ProjectTickets, ProjectChecklist
from django.views.decorators.http import require_POST
from django.core.exceptions import PermissionDenied
import asyncio
import subprocess
import time
from pathlib import Path

# Import ServerConfig from coding app
from coding.models import ServerConfig

# Import the functions from ai_functions
from coding.utils.ai_functions import execute_local_command, restart_server_from_config

# Create your views here.

@login_required
def project_list(request):
    """View to display all projects for the current user"""
    projects = Project.objects.filter(owner=request.user).order_by('-created_at')
    return render(request, 'projects/project_list.html', {
        'projects': projects
    })

@login_required
def project_detail(request, project_id):
    """View to display a specific project"""
    project = get_object_or_404(Project, id=project_id, owner=request.user)
    print(project.direct_conversations.all())
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
        return redirect('create_conversation', project_id=project.id)
    
    return render(request, 'projects/create_project.html')

@login_required
def update_project(request, project_id):
    """View to update a project"""
    project = get_object_or_404(Project, id=project_id, owner=request.user)
    
    if request.method == 'POST':
        project.name = request.POST.get('name', project.name)
        project.description = request.POST.get('description', project.description)
        project.icon = request.POST.get('icon', project.icon)
        project.status = request.POST.get('status', project.status)
        project.save()
        
        messages.success(request, "Project updated successfully!")
        return redirect('project_detail', project_id=project.id)
    
    # For GET requests, render the update form
    return render(request, 'projects/update_project.html', {
        'project': project
    })

@login_required
@require_POST
def delete_project(request, project_id):
    """View to delete a project"""
    project = get_object_or_404(Project, id=project_id, owner=request.user)
    project_name = project.name
    project.delete()
    
    messages.success(request, f"Project '{project_name}' deleted successfully")
    return redirect('project_list')

@login_required
def project_features_api(request, project_id):
    """API view to get features for a project"""
    project = get_object_or_404(Project, id=project_id, owner=request.user)
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
    project = get_object_or_404(Project, id=project_id, owner=request.user)
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
    """API view to get PRD for a project"""
    project = get_object_or_404(Project, id=project_id, owner=request.user)
    
    # Get the PRD or create it if it doesn't exist
    prd, created = ProjectPRD.objects.get_or_create(
        project=project,
        defaults={'prd': ''}  # Default empty content if we're creating a new PRD
    )
    
    # Convert to JSON-serializable format
    prd_data = {
        'id': prd.id,
        'content': prd.prd,
        'title': 'Product Requirement Document',
        'updated_at': prd.updated_at.strftime('%Y-%m-%d %H:%M') if prd.updated_at else None
    }
    
    return JsonResponse(prd_data)   

@login_required
def project_design_schema_api(request, project_id):
    """API view to get design schema for a project"""
    project = get_object_or_404(Project, id=project_id, owner=request.user)
    
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

@login_required
def project_tickets_api(request, project_id):
    """API view to get tickets for a project, including feature information"""
    project = get_object_or_404(Project, id=project_id, owner=request.user)
    
    # Get all tickets for this project
    tickets = ProjectTickets.objects.filter(project=project).select_related('feature')
    
    tickets_list = []
    for ticket in tickets:
        tickets_list.append({
            'id': ticket.id,
            'ticket_id': ticket.ticket_id,
            'title': ticket.title,
            'description': ticket.description,
            'status': ticket.status,
            'feature': {
                'id': ticket.feature.id,
                'name': ticket.feature.name,
                'priority': ticket.feature.priority
            },
            'backend_tasks': ticket.backend_tasks,
            'frontend_tasks': ticket.frontend_tasks,
            'implementation_steps': ticket.implementation_steps,
            'created_at': ticket.created_at.isoformat(),
            'updated_at': ticket.updated_at.isoformat(),
        })
    
    return JsonResponse({'tickets': tickets_list})

@login_required
def project_checklist_api(request, project_id):
    """API view to get checklist items for a project"""
    project = get_object_or_404(Project, id=project_id, owner=request.user)
    
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
        })
    
    return JsonResponse({'checklist': checklist_list})

@login_required
def project_server_configs_api(request, project_id):
    """API view to get server configurations for a project"""
    project = get_object_or_404(Project, id=project_id, owner=request.user)
    
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
    project = get_object_or_404(Project, id=project_id)
    
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
    """API view to get implementation for a project"""
    project = get_object_or_404(Project, id=project_id, owner=request.user)
    
    # Get the implementation or create it if it doesn't exist
    implementation, created = ProjectImplementation.objects.get_or_create(
        project=project,
        defaults={'implementation': ''}  # Default empty content if we're creating a new implementation
    )
    
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
    project = get_object_or_404(Project, id=project_id, owner=request.user)
    
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
        workspace_path = Path.home() / "LFG" / "workspace"
        workspace_path.mkdir(parents=True, exist_ok=True)
        
        server_status = []
        
        for config in server_configs:
            port = config.port
            server_type = config.type or 'application'
            
            # Check if server is running on this port
            check_command = f"lsof -i:{port} | grep LISTEN"
            success, stdout, stderr = execute_local_command(check_command, str(workspace_path))
            
            is_running = success and stdout.strip()
            
            if is_running:
                server_status.append({
                    'port': port,
                    'type': server_type,
                    'status': 'running',
                    'url': f'http://localhost:{port}',
                    'message': f'{server_type.capitalize()} server is running on port {port}'
                })
            else:
                # Server is not running, attempt to restart
                server_command = config.start_server_command or config.command
                
                if server_command:
                    # Kill any existing process on the port first
                    kill_command = f"lsof -ti:{port} | xargs kill -9 2>/dev/null || true"
                    execute_local_command(kill_command, str(workspace_path))
                    
                    # Wait a moment for port to be freed
                    time.sleep(1)
                    
                    # Create log file for the server
                    log_file = workspace_path / f"server_{project_id}_{port}.log"
                    
                    # Use nohup to run in background
                    background_command = f"nohup {server_command} > {log_file} 2>&1 &"
                    restart_success, restart_stdout, restart_stderr = execute_local_command(background_command, str(workspace_path))
                    
                    if restart_success:
                        # Wait a bit for server to start
                        time.sleep(3)
                        
                        # Check again if server is running
                        recheck_success, recheck_stdout, recheck_stderr = execute_local_command(check_command, str(workspace_path))
                        
                        if recheck_success and recheck_stdout.strip():
                            server_status.append({
                                'port': port,
                                'type': server_type,
                                'status': 'restarted',
                                'url': f'http://localhost:{port}',
                                'message': f'{server_type.capitalize()} server restarted successfully on port {port}'
                            })
                        else:
                            server_status.append({
                                'port': port,
                                'type': server_type,
                                'status': 'failed',
                                'url': f'http://localhost:{port}',
                                'message': f'Failed to restart {server_type} server on port {port}. Check logs at {log_file}'
                            })
                    else:
                        server_status.append({
                            'port': port,
                            'type': server_type,
                            'status': 'failed',
                            'url': f'http://localhost:{port}',
                            'message': f'Failed to restart {server_type} server: {restart_stderr}'
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

