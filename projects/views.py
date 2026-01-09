from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages
from .models import (
    Project,
    ProjectFeature,
    ProjectPersona,
    ProjectFile,
    ProjectDesignSchema,
    ProjectDesignFeature,
    DesignCanvas,
    ProjectTicket,
    ProjectTicketAttachment,
    ToolCallHistory,
    ProjectMember,
    ProjectInvitation,
    TicketStage
)
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
import mimetypes
import os

# Import ServerConfig and MagpieWorkspace from development app
from development.models import ServerConfig, MagpieWorkspace
from accounts.models import LLMApiKeys, ExternalServicesAPIKeys, GitHubToken
from rest_framework_simplejwt.tokens import RefreshToken
import logging

logger = logging.getLogger(__name__)

# Import the functions from ai_functions
from factory.ai_functions import execute_local_command, restart_server_from_config, get_magpie_client, _run_magpie_ssh, get_or_fetch_proxy_url
from factory.llm_config import get_llm_model_config
from chat.models import ModelSelection
from accounts.models import ApplicationState
from projects.websocket_utils import send_workspace_progress


def serialize_ticket_attachment(attachment, request=None):
    """Return a JSON-friendly representation of an attachment."""
    file_url = attachment.file.url if attachment.file else ''
    if request and file_url:
        file_url = request.build_absolute_uri(file_url)

    uploaded_by = None
    if attachment.uploaded_by:
        uploaded_by = (
            attachment.uploaded_by.get_full_name()
            or attachment.uploaded_by.username
        )

    return {
        'id': attachment.id,
        'original_filename': attachment.original_filename or os.path.basename(attachment.file.name),
        'file_type': attachment.file_type,
        'file_size': attachment.file_size,
        'file_url': file_url,
        'uploaded_at': attachment.uploaded_at.isoformat(),
        'uploaded_by': uploaded_by,
    }
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
        
        # Count tickets
        tickets_count = project.tickets.count()
        
        # Get codebase information if available
        codebase_info = None
        try:
            from codebase_index.models import IndexedRepository
            indexed_repo = project.indexed_repository
            codebase_info = {
                'status': indexed_repo.status,
                'total_files': indexed_repo.total_files,
                'indexed_files': indexed_repo.indexed_files_count,
                'total_chunks': indexed_repo.total_chunks,
                'github_url': indexed_repo.github_url,
                'github_repo_name': indexed_repo.github_repo_name
            }
        except Exception:
            # No codebase indexed
            codebase_info = None
        
        projects_with_stats.append({
            'project': project,
            'conversations_count': conversations_count,
            'documents_count': documents_count,
            'tickets_count': tickets_count,
            'codebase_info': codebase_info
        })
    
    return render(request, 'projects/project_list.html', {
        'projects': projects_with_stats
    })

@login_required
def tickets_list(request):
    """View to display all tickets for the current user across all projects"""
    # Get all projects where user has access
    owned_projects = Project.objects.filter(owner=request.user)

    try:
        member_projects = Project.objects.filter(
            members__user=request.user,
            members__status='active'
        ).exclude(owner=request.user)
    except Exception:
        member_projects = Project.objects.none()

    # Combine projects
    all_projects = list(owned_projects) + list(member_projects)
    project_ids = [p.id for p in all_projects]

    # Get all tickets from these projects (oldest first)
    tickets = ProjectTicket.objects.filter(
        project_id__in=project_ids
    ).select_related('project').order_by('created_at')

    # Fixed status and priority options for filters
    statuses = ['open', 'in_progress', 'done', 'blocked']
    priorities = ['High', 'Medium', 'Low']

    # Determine user's current model selection for pre-selecting option
    model_selection = ModelSelection.objects.filter(user=request.user).first()
    current_model_key = model_selection.selected_model if model_selection else ModelSelection.DEFAULT_MODEL_KEY

    # Get sidebar state
    app_state = ApplicationState.objects.filter(user=request.user).first()
    sidebar_minimized = app_state.sidebar_minimized if app_state else False

    # No stages for global view (stages are project-specific)
    # Kanban will use status field instead
    stages = []

    return render(request, 'projects/tickets_list.html', {
        'tickets': tickets,
        'statuses': statuses,
        'priorities': priorities,
        'projects': all_projects,
        'llm_model_config': get_llm_model_config(),
        'current_model_key': current_model_key,
        'sidebar_minimized': sidebar_minimized,
        'stages': stages,
    })

@login_required
def project_tickets_list(request, project_id):
    """View to display tickets for a specific project"""
    project = get_object_or_404(Project, project_id=project_id)

    # Check if user has access to this project
    if not project.can_user_access(request.user):
        raise PermissionDenied("You don't have permission to access this project.")

    # Get all projects where user has access (for the project dropdown)
    owned_projects = Project.objects.filter(owner=request.user)
    try:
        member_projects = Project.objects.filter(
            members__user=request.user,
            members__status='active'
        ).exclude(owner=request.user)
    except Exception:
        member_projects = Project.objects.none()

    all_projects = list(owned_projects) + list(member_projects)

    # Get tickets for this specific project (oldest first)
    tickets = ProjectTicket.objects.filter(
        project=project
    ).select_related('project').order_by('created_at')

    # Fixed status and priority options for filters
    statuses = ['open', 'in_progress', 'done', 'blocked']
    priorities = ['High', 'Medium', 'Low']

    # Determine user's current model selection
    model_selection = ModelSelection.objects.filter(user=request.user).first()
    current_model_key = model_selection.selected_model if model_selection else ModelSelection.DEFAULT_MODEL_KEY

    # Get sidebar state
    app_state = ApplicationState.objects.filter(user=request.user).first()
    sidebar_minimized = app_state.sidebar_minimized if app_state else False

    # Get stages for this project (create defaults if none exist)
    stages = TicketStage.objects.filter(project=project).order_by('order')
    if not stages.exists():
        TicketStage.get_or_create_defaults(project)
        stages = TicketStage.objects.filter(project=project).order_by('order')

    return render(request, 'projects/tickets_list.html', {
        'tickets': tickets,
        'statuses': statuses,
        'priorities': priorities,
        'projects': all_projects,
        'current_project': project,
        'llm_model_config': get_llm_model_config(),
        'current_model_key': current_model_key,
        'sidebar_minimized': sidebar_minimized,
        'stages': stages,
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
    
    # Get codebase information if available
    indexed_repository = None
    repository_insights = None
    code_chunks = []
    codebase_map = {}

    try:
        from codebase_index.models import IndexedRepository, CodeChunk, RepositoryMetadata, CodebaseIndexMap
        from collections import defaultdict
        indexed_repository = project.indexed_repository

        # Get repository insights
        try:
            repository_insights = indexed_repository.metadata
        except RepositoryMetadata.DoesNotExist:
            repository_insights = None

        # Get sample code chunks for preview
        if indexed_repository:
            chunks_query = CodeChunk.objects.filter(
                file__repository=indexed_repository
            ).select_related('file').order_by('-created_at')

            # Get diverse chunk types for preview
            function_chunks = list(chunks_query.filter(chunk_type='function')[:2])
            class_chunks = list(chunks_query.filter(chunk_type='class')[:1])
            other_chunks = list(chunks_query.exclude(chunk_type__in=['function', 'class'])[:2])

            code_chunks = (function_chunks + class_chunks + other_chunks)[:5]

            # Build codebase map from CodebaseIndexMap
            index_entries = CodebaseIndexMap.objects.filter(
                repository=indexed_repository
            ).select_related('code_chunk__file').order_by('file_path', 'start_line')

            logger.info(f"Found {index_entries.count()} CodebaseIndexMap entries for repository {indexed_repository.id}")

            # Group by file path
            files_map = defaultdict(list)
            for entry in index_entries:
                files_map[entry.file_path].append({
                    'entity_type': entry.entity_type,
                    'entity_name': entry.entity_name,
                    'fully_qualified_name': entry.fully_qualified_name,
                    'start_line': entry.start_line,
                    'end_line': entry.end_line,
                    'language': entry.language,
                    'complexity': entry.complexity,
                    'parameters': entry.parameters,
                    'description': entry.description[:100] if entry.description else None,
                })

            codebase_map = dict(files_map)
            logger.info(f"Built codebase_map with {len(codebase_map)} files")

    except Exception as e:
        logger.debug(f"No codebase index found for project {project.id}: {e}")
    
    logger.info(f"Project direct conversations: {project.direct_conversations.all()}", extra={'easylogs_metadata': {'project_id': project.id, 'project_name': project.name}})
    return render(request, 'projects/project_detail.html', {
        'project': project,
        'indexed_repository': indexed_repository,
        'repository_insights': repository_insights,
        'code_chunks': code_chunks,
        'total_chunks': code_chunks.__len__() if code_chunks else 0,
        'codebase_map': codebase_map
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
@require_POST
def update_project_name(request):
    """API endpoint to update a project's name"""
    try:
        data = json.loads(request.body)
        project_id = data.get('project_id')
        new_name = data.get('name', '').strip()
        
        if not project_id:
            return JsonResponse({
                'success': False,
                'error': 'Project ID is required'
            }, status=400)
            
        if not new_name:
            return JsonResponse({
                'success': False,
                'error': 'Project name is required'
            }, status=400)
        
        # Get the project and ensure user owns it or has permission
        project = get_object_or_404(Project, id=project_id)
        if not project.can_user_access(request.user):
            return JsonResponse({
                'success': False,
                'error': 'You do not have permission to update this project'
            }, status=403)
        
        # Update the project name
        project.name = new_name
        project.save()
        
        return JsonResponse({
            'success': True,
            'name': project.name
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
def update_project_description(request, project_id):
    project = get_object_or_404(Project, project_id=project_id)

    if not project.can_user_access(request.user):
        return HttpResponseForbidden('You do not have permission to update this project')

    description = request.POST.get('description', '').strip()
    project.description = description
    project.save()

    messages.success(request, 'Project description updated successfully.')
    return redirect('projects:project_detail', project_id=project.project_id)

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

# ProjectTickets has been removed - use ProjectTicket instead

@login_required
def project_checklist_api(request, project_id):
    """API view to get checklist items for a project"""
    project = get_object_or_404(Project, project_id=project_id)
    
    # Check if user has access to this project
    if not project.can_user_access(request.user):
        raise PermissionDenied("You don't have permission to access this project.")
    
    # Get all tickets for this project
    tickets = ProjectTicket.objects.filter(project=project).select_related('project', 'stage').prefetch_related('attachments').order_by('created_at', 'id')

    tickets_list = []
    for item in tickets:
        attachments = [
            serialize_ticket_attachment(attachment, request)
            for attachment in item.attachments.all()
        ]
        tickets_list.append({
            'id': item.id,
            'project_id': str(item.project.project_id),
            'project_name': item.project.name,
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
            'notes': item.notes,
            # Stage info
            'stage_id': item.stage.id if item.stage else None,
            'stage_name': item.stage.name if item.stage else None,
            'stage_color': item.stage.color if item.stage else None,
            # Linear integration fields
            'linear_issue_id': item.linear_issue_id,
            'linear_issue_url': item.linear_issue_url,
            'linear_state': item.linear_state,
            'linear_priority': item.linear_priority,
            'linear_assignee_id': item.linear_assignee_id,
            'linear_synced_at': item.linear_synced_at.isoformat() if item.linear_synced_at else None,
            'linear_sync_enabled': item.linear_sync_enabled,
            'attachments': attachments,
            # Queue status for build tracking
            'queue_status': item.queue_status,
        })

    return JsonResponse({'tickets': tickets_list})

@login_required
@require_POST
def create_checklist_item_api(request, project_id):
    """API endpoint to create a new checklist/ticket item"""
    project = get_object_or_404(Project, project_id=project_id)

    if not project.can_user_manage_tickets(request.user):
        return JsonResponse({
            'success': False,
            'error': 'You do not have permission to create tickets in this project'
        }, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)

    name = (data.get('name') or '').strip()
    description = (data.get('description') or '').strip()

    if not name:
        return JsonResponse({
            'success': False,
            'error': 'Ticket name is required'
        }, status=400)

    if not description:
        return JsonResponse({
            'success': False,
            'error': 'Ticket description is required'
        }, status=400)

    def validate_choice(value, choices, default_value):
        return value if value in choices else default_value

    status_choices = [choice[0] for choice in ProjectTicket._meta.get_field('status').choices]
    priority_choices = [choice[0] for choice in ProjectTicket._meta.get_field('priority').choices]
    role_choices = [choice[0] for choice in ProjectTicket._meta.get_field('role').choices]
    complexity_choices = [choice[0] for choice in ProjectTicket._meta.get_field('complexity').choices]

    status = validate_choice(data.get('status', 'open'), status_choices, 'open')
    priority = validate_choice(data.get('priority', 'Medium'), priority_choices, 'Medium')
    role = validate_choice(data.get('role', 'user'), role_choices, 'user')
    complexity = validate_choice(data.get('complexity', 'medium'), complexity_choices, 'medium')

    requires_worktree_value = data.get('requires_worktree', True)
    if isinstance(requires_worktree_value, str):
        requires_worktree = requires_worktree_value.lower() in ['true', '1', 'yes', 'on']
    else:
        requires_worktree = bool(requires_worktree_value)

    ticket = ProjectTicket.objects.create(
        project=project,
        name=name,
        description=description,
        status=status,
        priority=priority,
        role=role,
        complexity=complexity,
        requires_worktree=requires_worktree,
    )

    ticket_data = {
        'id': ticket.id,
        'project_id': str(project.project_id),
        'project_name': project.name,
        'name': ticket.name,
        'description': ticket.description,
        'status': ticket.status,
        'priority': ticket.priority,
        'role': ticket.role,
        'complexity': ticket.complexity,
        'requires_worktree': ticket.requires_worktree,
        'created_at': ticket.created_at.isoformat(),
        'updated_at': ticket.updated_at.isoformat(),
        'attachments': [],
        'queue_status': ticket.queue_status,
    }

    return JsonResponse({
        'success': True,
        'message': 'Ticket created successfully',
        'ticket': ticket_data
    }, status=201)


@login_required
@require_http_methods(["GET", "POST"])
def ticket_attachments_api(request, project_id, ticket_id):
    """Upload or list attachments for a ticket."""
    project = get_object_or_404(Project, project_id=project_id)

    if not project.can_user_access(request.user):
        raise PermissionDenied("You don't have permission to access this project.")

    ticket = get_object_or_404(ProjectTicket, id=ticket_id, project=project)

    if request.method == "GET":
        attachments = [
            serialize_ticket_attachment(attachment, request)
            for attachment in ticket.attachments.all()
        ]
        return JsonResponse({
            'success': True,
            'attachments': attachments
        })

    if not project.can_user_manage_tickets(request.user):
        return JsonResponse({
            'success': False,
            'error': 'You do not have permission to upload attachments for this project'
        }, status=403)

    files = request.FILES.getlist('files')
    if not files:
        return JsonResponse({
            'success': False,
            'error': 'No files provided'
        }, status=400)

    saved = []
    for file_obj in files:
        file_type = file_obj.content_type or (mimetypes.guess_type(file_obj.name)[0] if file_obj.name else '') or ''
        attachment = ProjectTicketAttachment.objects.create(
            ticket=ticket,
            uploaded_by=request.user,
            file=file_obj,
            original_filename=file_obj.name[:255] if file_obj.name else '',
            file_type=file_type,
            file_size=file_obj.size or 0,
        )
        saved.append(serialize_ticket_attachment(attachment, request))

    return JsonResponse({
        'success': True,
        'attachments': saved
    }, status=201)

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
@require_http_methods(["GET", "POST", "DELETE"])
def project_env_vars_api(request, project_id):
    """
    API endpoint for managing project environment variables.

    GET: List all env vars (values masked)
    POST: Create/update env vars (supports bulk import from .env content)
    DELETE: Delete specific env var by key
    """
    from projects.models import ProjectEnvironmentVariable

    project = get_object_or_404(Project, project_id=project_id)

    # Check permissions - must be owner or admin
    if project.owner != request.user:
        member = project.members.filter(user=request.user, status='active').first()
        if not member or member.role not in ['owner', 'admin']:
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    if request.method == 'GET':
        # List all env vars with masked values
        env_vars = []
        for env_var in ProjectEnvironmentVariable.objects.filter(project=project):
            env_vars.append({
                'id': env_var.id,
                'key': env_var.key,
                'masked_value': env_var.get_masked_value(),
                'is_secret': env_var.is_secret,
                'is_required': env_var.is_required,
                'has_value': env_var.has_value,
                'description': env_var.description,
                'created_at': env_var.created_at.isoformat(),
                'updated_at': env_var.updated_at.isoformat(),
            })
        return JsonResponse({'success': True, 'env_vars': env_vars})

    elif request.method == 'POST':
        import json
        try:
            data = json.loads(request.body.decode('utf-8'))
        except:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        # Check if this is a bulk import (.env content)
        if 'env_content' in data:
            content = data['env_content']
            created, updated = ProjectEnvironmentVariable.bulk_set_from_env_content(
                project, content, request.user
            )
            return JsonResponse({
                'success': True,
                'message': f'Created {created} and updated {updated} environment variables',
                'created': created,
                'updated': updated
            })

        # Single variable create/update
        key = data.get('key', '').strip().upper()
        value = data.get('value', '')
        is_secret = data.get('is_secret', True)
        description = data.get('description', '')

        if not key:
            return JsonResponse({'success': False, 'error': 'Key is required'}, status=400)

        # Validate key format
        if not key.replace('_', '').isalnum():
            return JsonResponse({
                'success': False,
                'error': 'Key must contain only letters, numbers, and underscores'
            }, status=400)

        env_var, created = ProjectEnvironmentVariable.objects.get_or_create(
            project=project,
            key=key,
            defaults={'created_by': request.user}
        )
        env_var.set_value(value)
        env_var.is_secret = is_secret
        env_var.description = description
        # Mark as having a value if value is non-empty
        if value:
            env_var.has_value = True
        env_var.save()

        return JsonResponse({
            'success': True,
            'message': 'Created' if created else 'Updated',
            'env_var': {
                'id': env_var.id,
                'key': env_var.key,
                'masked_value': env_var.get_masked_value(),
                'is_secret': env_var.is_secret,
                'description': env_var.description,
            }
        })

    elif request.method == 'DELETE':
        import json
        try:
            data = json.loads(request.body.decode('utf-8'))
        except:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        key = data.get('key', '').strip().upper()
        if not key:
            return JsonResponse({'success': False, 'error': 'Key is required'}, status=400)

        deleted, _ = ProjectEnvironmentVariable.objects.filter(
            project=project, key=key
        ).delete()

        if deleted:
            return JsonResponse({'success': True, 'message': f'Deleted {key}'})
        else:
            return JsonResponse({'success': False, 'error': 'Variable not found'}, status=404)


@login_required
@require_http_methods(["GET"])
def project_env_vars_download_api(request, project_id):
    """
    API endpoint for downloading environment variables with full (unmasked) values.
    Returns env vars in a format suitable for creating a .env file.
    """
    from projects.models import ProjectEnvironmentVariable

    project = get_object_or_404(Project, project_id=project_id)

    # Check permissions - must be owner or admin
    if project.owner != request.user:
        member = project.members.filter(user=request.user, status='active').first()
        if not member or member.role not in ['owner', 'admin']:
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # Get all env vars with full values
    env_vars = []
    for env_var in ProjectEnvironmentVariable.objects.filter(project=project).order_by('key'):
        if env_var.has_value:
            env_vars.append({
                'key': env_var.key,
                'value': env_var.get_value(),  # Full unmasked value
                'is_secret': env_var.is_secret,
            })

    if not env_vars:
        return JsonResponse({'success': False, 'error': 'No environment variables to download'})

    return JsonResponse({'success': True, 'env_vars': env_vars})


@login_required
@require_http_methods(["POST"])
def project_env_vars_bulk_delete_api(request, project_id):
    """Delete all environment variables for a project."""
    from projects.models import ProjectEnvironmentVariable

    project = get_object_or_404(Project, project_id=project_id)

    # Check permissions - must be owner or admin
    if project.owner != request.user:
        member = project.members.filter(user=request.user, status='active').first()
        if not member or member.role not in ['owner', 'admin']:
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    deleted, _ = ProjectEnvironmentVariable.objects.filter(project=project).delete()
    return JsonResponse({
        'success': True,
        'message': f'Deleted {deleted} environment variables',
        'deleted': deleted
    })


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
def app_preview(request, project_id):
    """
    View for the app preview page - allows users to preview their running application
    with viewport toggle, console capture, and server controls.
    """
    project = get_object_or_404(Project, project_id=project_id)

    # Check if user has access to this project
    if not project.can_user_access(request.user):
        raise PermissionDenied("You don't have permission to access this project.")

    # Get all projects where user has access (for the project dropdown)
    owned_projects = Project.objects.filter(owner=request.user)
    try:
        member_projects = Project.objects.filter(
            members__user=request.user,
            members__status='active'
        ).exclude(owner=request.user)
    except Exception:
        member_projects = Project.objects.none()

    all_projects = list(owned_projects) + list(member_projects)

    # Get server configurations for this project
    server_configs = ServerConfig.objects.filter(project=project).order_by('port')

    # Convert server configs to list of dicts for JSON serialization
    server_configs_data = [
        {
            'id': config.id,
            'port': config.port,
            'type': config.type,
            'command': config.start_server_command or config.command,
        }
        for config in server_configs
    ]

    # Get Magpie workspace for this project (any workspace with an IPv6 address)
    workspace = MagpieWorkspace.objects.filter(
        project=project,
        ipv6_address__isnull=False
    ).exclude(ipv6_address='').order_by('-updated_at').first()

    workspace_data = None
    if workspace:
        ipv6 = workspace.ipv6_address.strip('[]') if workspace.ipv6_address else None
        # Use proxy URL if available, otherwise fall back to IPv6
        preview_url = get_or_fetch_proxy_url(workspace, port=3000)
        if not preview_url:
            preview_url = f"http://[{ipv6}]:3000" if ipv6 else None
        workspace_data = {
            'id': workspace.id,
            'workspace_id': workspace.workspace_id,
            'status': workspace.status,
            'ipv6_address': ipv6,
            'preview_url': preview_url,
        }

    # Get sidebar state
    app_state = ApplicationState.objects.filter(user=request.user).first()
    sidebar_minimized = app_state.sidebar_minimized if app_state else False

    # Generate JWT access token for WebSocket authentication
    refresh = RefreshToken.for_user(request.user)
    access_token = str(refresh.access_token)

    context = {
        'project': project,
        'current_project': project,
        'projects': all_projects,
        'server_configs': json.dumps(server_configs_data),
        'workspace': workspace_data,
        'workspace_json': json.dumps(workspace_data) if workspace_data else 'null',
        'sidebar_minimized': sidebar_minimized,
        'access_token': access_token,
    }

    return render(request, 'projects/app_preview.html', context)


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
@require_http_methods(["POST"])
def start_dev_server_api(request, project_id):
    """Start a dev server on the Magpie workspace for the project.
    Always uses lfg-agent branch and pulls latest changes."""
    project = get_object_or_404(Project, project_id=project_id)

    # Check access
    if not project.can_user_access(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        data = {}

    port = data.get('port', 3000)
    target_branch = 'lfg-agent'  # Always use lfg-agent for preview

    try:
        # Send initial progress
        send_workspace_progress(project_id, 'checking_workspace', 'Looking for existing workspace...')

        # Find the Magpie workspace for this project (any workspace with IPv6)
        workspace = MagpieWorkspace.objects.filter(
            project=project,
            ipv6_address__isnull=False
        ).exclude(ipv6_address='').order_by('-updated_at').first()

        if not workspace:
            send_workspace_progress(project_id, 'error', error='No workspace found. Please run a ticket build first.')
            return JsonResponse({
                'success': False,
                'error': 'No workspace found. Please run a ticket build first to set up the project environment.'
            })

        if not workspace.ipv6_address:
            send_workspace_progress(project_id, 'error', error='Workspace still provisioning. Please wait.')
            return JsonResponse({
                'success': False,
                'error': 'Workspace IPv6 address not available. The workspace may still be provisioning.'
            })

        send_workspace_progress(project_id, 'checking_workspace', 'Workspace found, connecting...')

        # Get Magpie client
        client = get_magpie_client()
        if not client:
            send_workspace_progress(project_id, 'error', error='Magpie client not configured.')
            return JsonResponse({
                'success': False,
                'error': 'Magpie client not configured. Check server settings.'
            })

        workspace_path = "/workspace/nextjs-app"

        # Step 1: Ensure code exists and switch to lfg-agent branch with latest changes
        indexed_repo = getattr(project, 'indexed_repository', None)
        if indexed_repo and indexed_repo.github_url:
            send_workspace_progress(project_id, 'switching_branch', f'Switching to branch: {target_branch}...', extra_data={'branch': target_branch})
            logger.info(f"[PREVIEW] Ensuring code is on {target_branch} branch with latest changes")

            # Get GitHub token for authenticated git operations
            github_token_obj = GitHubToken.objects.filter(user=request.user).first()
            github_token = github_token_obj.access_token if github_token_obj else None

            if not github_token:
                logger.warning("[PREVIEW] No GitHub token found, git operations may fail for private repos")
                auth_remote_url = f"https://github.com/{indexed_repo.github_owner}/{indexed_repo.github_repo_name}.git"
            else:
                auth_remote_url = f"https://x-access-token:{github_token}@github.com/{indexed_repo.github_owner}/{indexed_repo.github_repo_name}.git"

            owner = indexed_repo.github_owner
            repo_name = indexed_repo.github_repo_name

            # Check if code exists, switch to lfg-agent, and pull latest
            git_sync_command = f'''
cd /workspace

# Check if code exists
if [ ! -d nextjs-app ] || [ ! -f nextjs-app/package.json ]; then
    echo "CODE_MISSING"
    exit 1
fi

cd nextjs-app

# Update remote URL with auth token for this operation
git remote set-url origin "{auth_remote_url}"

# Get current branch
current_branch=$(git branch --show-current 2>/dev/null || echo "unknown")
echo "CURRENT_BRANCH:$current_branch"

# Remove untracked files that block checkout (dev server artifacts)
echo "Cleaning up untracked files..."
rm -f .devserver_pid dev.log 2>/dev/null || true

# Fetch ALL branches from remote
echo "Fetching all branches..."
git fetch origin --prune 2>&1 || true

# List available remote branches for debugging
echo "Available remote branches:"
git branch -r 2>/dev/null | head -20 || true

# Stash any local changes
echo "Stashing local changes..."
git stash 2>/dev/null || true

# Try to checkout the branch
echo "Checking out {target_branch}..."

# Method 1: Try simple checkout (if branch exists locally)
git checkout {target_branch} 2>&1 && echo "METHOD1_SUCCESS" || true

# Check if we're on the right branch now
on_branch=$(git branch --show-current 2>/dev/null || echo "none")
if [ "$on_branch" = "{target_branch}" ]; then
    echo "On correct branch, pulling latest..."
    git pull origin {target_branch} 2>&1 || true
else
    # Method 2: Try to create from remote tracking branch
    echo "Method 1 failed, trying method 2..."
    git checkout -b {target_branch} origin/{target_branch} 2>&1 && echo "METHOD2_SUCCESS" || true

    on_branch=$(git branch --show-current 2>/dev/null || echo "none")
    if [ "$on_branch" != "{target_branch}" ]; then
        # Method 3: Fetch the specific branch and checkout
        echo "Method 2 failed, trying method 3..."
        git fetch origin {target_branch} 2>&1 || true
        git checkout -B {target_branch} FETCH_HEAD 2>&1 && echo "METHOD3_SUCCESS" || true
    fi
fi

# Final verification
final_branch=$(git branch --show-current 2>/dev/null || echo "unknown")
echo "FINAL_BRANCH:$final_branch"

if [ "$final_branch" = "{target_branch}" ]; then
    echo "SUCCESS: Now on branch {target_branch}"
else
    echo "BRANCH_SWITCH_FAILED: wanted {target_branch} but on $final_branch"
fi

# Reset remote URL to non-auth version for safety
git remote set-url origin "https://github.com/{owner}/{repo_name}.git" || true

echo "SWITCH_COMPLETE"
'''
            git_result = _run_magpie_ssh(client, workspace.job_id, git_sync_command, timeout=120)
            stdout = git_result.get('stdout', '')
            stderr = git_result.get('stderr', '')
            logger.info(f"[PREVIEW] Git sync result: {stdout[:500]}")
            if stderr:
                logger.warning(f"[PREVIEW] Git sync stderr: {stderr[:500]}")

            if 'CODE_MISSING' in stdout:
                send_workspace_progress(project_id, 'error', error='No code found in workspace. Please run a ticket build first.')
                return JsonResponse({
                    'success': False,
                    'error': 'No code found in workspace. Please run a ticket build first.'
                })

            # Run npm install after branch switch to ensure dependencies are up to date
            send_workspace_progress(project_id, 'downloading_dependencies', 'Installing dependencies (npm install)...')
            logger.info(f"[PREVIEW] Running npm install after branch switch...")
            npm_result = _run_magpie_ssh(
                client, workspace.job_id,
                f"cd {workspace_path} && npm config set cache /workspace/.npm-cache && npm install",
                timeout=300, with_node_env=True
            )
            if npm_result.get('exit_code', 0) != 0:
                logger.warning(f"[PREVIEW] npm install warning: {npm_result.get('stderr', '')[:200]}")
            else:
                logger.info(f"[PREVIEW] npm install completed successfully")

        # Step 2: Kill any existing process, clear cache, and start dev server
        send_workspace_progress(project_id, 'clearing_cache', 'Clearing cache and preparing to start server...')

        start_command = f"""
cd {workspace_path}

# Set npm cache to /workspace to avoid disk space issues
npm config set cache /workspace/.npm-cache

# Kill existing process
if [ -f .devserver_pid ]; then
  old_pid=$(cat .devserver_pid)
  if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
    kill "$old_pid" || true
    sleep 2
  fi
fi

# Kill any remaining node processes
pkill -f "npm run dev" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true

# Clear Next.js cache to ensure fresh build from new branch
rm -rf .next 2>/dev/null || true

# Start dev server
: > {workspace_path}/dev.log
nohup npm run dev -- --hostname :: --port {port} > {workspace_path}/dev.log 2>&1 &
pid=$!
echo "$pid" > .devserver_pid
echo "PID:$pid"
sleep 5
echo "Dev server started"
"""

        send_workspace_progress(project_id, 'starting_server', 'Starting development server...')
        result = _run_magpie_ssh(client, workspace.job_id, start_command, timeout=30, project_id=project.id)

        # Use proxy URL if available, otherwise fall back to IPv6
        send_workspace_progress(project_id, 'assigning_proxy', 'Assigning proxy URL...')
        preview_url = get_or_fetch_proxy_url(workspace, port=port, client=client)
        if not preview_url:
            ipv6 = workspace.ipv6_address.strip('[]')
            preview_url = f"http://[{ipv6}]:{port}"

        send_workspace_progress(project_id, 'complete', f'Server started on {target_branch}', extra_data={'url': preview_url, 'branch': target_branch})

        return JsonResponse({
            'success': True,
            'status': 'running',
            'url': preview_url,
            'port': port,
            'workspace_id': workspace.workspace_id,
            'branch': target_branch,
            'message': f'Server started on {preview_url} (branch: {target_branch})',
            'log': result.get('stdout', '')[:500]
        })

    except Exception as e:
        logger.exception("Error starting dev server")
        send_workspace_progress(project_id, 'error', error=str(e))
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def stop_dev_server_api(request, project_id):
    """Stop the dev server on the Magpie workspace"""
    project = get_object_or_404(Project, project_id=project_id)

    if not project.can_user_access(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    try:
        # Find the Magpie workspace for this project (any workspace with IPv6)
        workspace = MagpieWorkspace.objects.filter(
            project=project,
            ipv6_address__isnull=False
        ).exclude(ipv6_address='').order_by('-updated_at').first()

        if not workspace:
            return JsonResponse({
                'success': False,
                'error': 'No workspace found.'
            })

        # Get Magpie client
        client = get_magpie_client()
        if not client:
            return JsonResponse({
                'success': False,
                'error': 'Magpie client not configured.'
            })

        # Kill the dev server process using PID file
        stop_command = """
cd /workspace/nextjs-app
if [ -f .devserver_pid ]; then
  pid=$(cat .devserver_pid)
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" || true
    echo "Killed server PID: $pid"
  fi
  rm -f .devserver_pid
fi
pkill -f "next dev" 2>/dev/null || true
echo "Server stopped"
"""

        result = _run_magpie_ssh(client, workspace.job_id, stop_command, timeout=10, project_id=project.id)

        return JsonResponse({
            'success': True,
            'message': 'Server stopped',
            'output': result.get('stdout', '')
        })
    except Exception as e:
        logger.exception("Error stopping dev server")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


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
    """API endpoint to update a checklist item (supports all fields)"""
    import json
    try:
        data = json.loads(request.body.decode('utf-8'))
        item_id = data.get('item_id')
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'Invalid request data', 'details': str(e)}, status=400)

    if not item_id:
        return JsonResponse({'success': False, 'error': 'item_id is required'}, status=400)

    project = get_object_or_404(Project, project_id=project_id)

    # Check if user can manage tickets
    if not project.can_user_manage_tickets(request.user):
        return JsonResponse({
            'success': False,
            'error': 'You do not have permission to manage tickets in this project'
        }, status=403)
    try:
        item = ProjectTicket.objects.get(id=item_id, project=project)
    except ProjectTicket.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Checklist item not found'}, status=404)

    changed = False

    # Update simple fields
    simple_fields = ['status', 'role', 'name', 'description', 'priority', 'complexity']
    for field in simple_fields:
        if field in data and data[field] != getattr(item, field):
            setattr(item, field, data[field])
            changed = True

    # Update boolean fields
    if 'requires_worktree' in data and data['requires_worktree'] != item.requires_worktree:
        item.requires_worktree = data['requires_worktree']
        changed = True

    # Update JSON fields
    json_fields = ['details', 'ui_requirements', 'component_specs', 'acceptance_criteria', 'dependencies']
    for field in json_fields:
        if field in data and data[field] != getattr(item, field):
            setattr(item, field, data[field])
            changed = True

    # Update stage field
    if 'stage_id' in data:
        new_stage_id = data['stage_id']
        current_stage_id = item.stage.id if item.stage else None
        if new_stage_id != current_stage_id:
            if new_stage_id is None:
                item.stage = None
            else:
                try:
                    new_stage = TicketStage.objects.get(id=new_stage_id, project=project)
                    item.stage = new_stage
                except TicketStage.DoesNotExist:
                    return JsonResponse({'success': False, 'error': 'Invalid stage_id'}, status=400)
            changed = True

    if changed:
        item.updated_at = timezone.now()
        item.save()
        return JsonResponse({
            'success': True,
            'id': item.id,
            'name': item.name,
            'status': item.status,
            'description': item.description,
            'priority': item.priority,
            'role': item.role,
            'complexity': item.complexity,
            'requires_worktree': item.requires_worktree,
            'stage_id': item.stage.id if item.stage else None,
            'stage_name': item.stage.name if item.stage else None,
            'stage_color': item.stage.color if item.stage else None,
            'updated_at': item.updated_at.isoformat(),
            'queue_status': item.queue_status,
        })
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
        checklist_item = ProjectTicket.objects.get(id=item_id, project=project)
        checklist_item.delete()
        
        return JsonResponse({
            'success': True,
            'message': 'Checklist item deleted successfully'
        })
    except ProjectTicket.DoesNotExist:
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


@login_required
@require_http_methods(["POST"])
def ticket_chat_api(request, project_id, ticket_id):
    """API endpoint to handle chat messages for ticket execution"""
    import json
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync

    try:
        data = json.loads(request.body.decode('utf-8'))
        message = data.get('message', '').strip()
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'Invalid request data'}, status=400)

    if not message:
        return JsonResponse({'success': False, 'error': 'Message is required'}, status=400)

    # Get project and ticket
    project = get_object_or_404(Project, project_id=project_id)
    ticket = get_object_or_404(ProjectTicket, id=ticket_id, project=project)

    # Check if user has access
    if not project.can_user_access(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # For now, we'll store the message and send it via WebSocket
    # The actual AI integration will be handled in the backend executor

    try:
        # Get the conversation_id from the request (if available)
        conversation_id = data.get('conversation_id')

        # Store user message (you may want to create a TicketChatMessage model in the future)
        # For now, we'll broadcast it via WebSocket

        channel_layer = get_channel_layer()
        if channel_layer and conversation_id:
            async_to_sync(channel_layer.group_send)(
                f"conversation_{conversation_id}",
                {
                    'type': 'ticket_chat_message',
                    'ticket_id': ticket_id,
                    'role': 'user',
                    'message': message,
                }
            )

        return JsonResponse({
            'success': True,
            'message': 'Message sent successfully',
            'ticket_id': ticket_id
        })

    except Exception as e:
        logger.error(f"Error handling ticket chat message: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Failed to process message: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def execute_ticket_api(request, project_id, ticket_id):
    """API endpoint to execute a ticket using the parallel executor system"""
    import json
    from tasks.dispatch import dispatch_tickets

    try:
        data = json.loads(request.body.decode('utf-8'))
        conversation_id = data.get('conversation_id')
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'Invalid request data'}, status=400)

    # Get project and ticket
    project = get_object_or_404(Project, project_id=project_id)
    ticket = get_object_or_404(ProjectTicket, id=ticket_id, project=project)

    # Check if user has permission to manage tickets
    if not project.can_user_manage_tickets(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # Check if ticket is already done
    if ticket.status == 'done':
        return JsonResponse({
            'success': False,
            'error': 'Ticket is already completed'
        }, status=400)

    # Check if ticket is already queued or executing
    if ticket.queue_status in ['queued', 'executing']:
        return JsonResponse({
            'success': False,
            'error': f'Ticket is already {ticket.queue_status}'
        }, status=400)

    try:
        # Dispatch ticket to the parallel executor queue
        success = dispatch_tickets(
            project_id=project.id,
            ticket_ids=[ticket.id],
            conversation_id=conversation_id or 0
        )

        if success:
            logger.info(f"Queued ticket execution: ticket_id={ticket_id}")
            return JsonResponse({
                'success': True,
                'message': 'Ticket queued for execution',
                'ticket_id': ticket_id,
                'queue_status': 'queued'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Failed to queue ticket'
            }, status=500)

    except Exception as e:
        logger.error(f"Error starting ticket execution: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def cancel_ticket_queue_api(request, project_id, ticket_id):
    """API endpoint to remove a ticket from the execution queue or stop execution"""
    from tasks.dispatch import remove_from_queue, force_reset_ticket_queue_status

    # Get project and ticket
    project = get_object_or_404(Project, project_id=project_id)
    ticket = get_object_or_404(ProjectTicket, id=ticket_id, project=project)

    # Check if user has permission to manage tickets
    if not project.can_user_manage_tickets(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # Check if ticket is in queue
    if ticket.queue_status == 'none':
        return JsonResponse({
            'success': False,
            'error': 'Ticket is not in queue'
        }, status=400)

    # If ticket is executing, use force reset to stop it
    if ticket.queue_status == 'executing':
        try:
            result = force_reset_ticket_queue_status(project.id, ticket.id)
            if result.get('error'):
                return JsonResponse({
                    'success': False,
                    'error': result['error']
                }, status=500)
            return JsonResponse({
                'success': True,
                'message': 'Ticket execution stopped',
                'ticket_id': ticket_id
            })
        except Exception as e:
            logger.error(f"Error stopping ticket execution: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

    try:
        # Remove from queue
        removed = remove_from_queue(project.id, ticket.id)

        if removed:
            return JsonResponse({
                'success': True,
                'message': 'Ticket removed from queue',
                'ticket_id': ticket_id
            })
        else:
            # Ticket not found in queue, update status anyway
            ticket.queue_status = 'none'
            ticket.queued_at = None
            ticket.queue_task_id = None
            ticket.save(update_fields=['queue_status', 'queued_at', 'queue_task_id'])

            return JsonResponse({
                'success': True,
                'message': 'Ticket queue status cleared',
                'ticket_id': ticket_id
            })

    except Exception as e:
        logger.error(f"Error canceling ticket from queue: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def force_reset_ticket_queue_api(request, project_id, ticket_id):
    """
    API endpoint to force reset a ticket's queue status.

    Use when a ticket is stuck in 'queued' or 'executing' state
    due to executor crash or other issues.
    """
    from tasks.dispatch import force_reset_ticket_queue_status

    # Get project and ticket
    project = get_object_or_404(Project, project_id=project_id)
    ticket = get_object_or_404(ProjectTicket, id=ticket_id, project=project)

    # Check if user has permission to manage tickets
    if not project.can_user_manage_tickets(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # Only allow force reset for queued or executing tickets
    if ticket.queue_status == 'none':
        return JsonResponse({
            'success': False,
            'error': 'Ticket is not in queue'
        }, status=400)

    try:
        # Force reset the ticket
        result = force_reset_ticket_queue_status(project.id, ticket.id)

        if result.get('error'):
            return JsonResponse({
                'success': False,
                'error': result['error']
            }, status=500)

        logger.info(f"Force reset ticket queue status: ticket_id={ticket_id}, result={result}")
        return JsonResponse({
            'success': True,
            'message': 'Ticket queue status reset',
            'ticket_id': ticket_id,
            'details': result
        })

    except Exception as e:
        logger.error(f"Error force resetting ticket queue: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def restart_ticket_queue_api(request, project_id, ticket_id):
    """
    API endpoint to restart a stuck ticket.

    This will force reset the ticket and re-queue it for execution.
    Use when a ticket is stuck in 'queued' or 'executing' state.
    """
    import json
    from tasks.dispatch import force_reset_ticket_queue_status, dispatch_tickets

    # Get project and ticket
    project = get_object_or_404(Project, project_id=project_id)
    ticket = get_object_or_404(ProjectTicket, id=ticket_id, project=project)

    # Check if user has permission to manage tickets
    if not project.can_user_manage_tickets(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # Get conversation_id from request body if provided
    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
        conversation_id = data.get('conversation_id', 0)
    except:
        conversation_id = 0

    # Check if ticket is already done
    if ticket.status == 'done':
        return JsonResponse({
            'success': False,
            'error': 'Ticket is already completed'
        }, status=400)

    try:
        # Step 1: Force reset if currently queued or executing
        if ticket.queue_status in ['queued', 'executing']:
            reset_result = force_reset_ticket_queue_status(project.id, ticket.id)
            if reset_result.get('error'):
                return JsonResponse({
                    'success': False,
                    'error': f"Reset failed: {reset_result['error']}"
                }, status=500)
            logger.info(f"Reset ticket before restart: ticket_id={ticket_id}")

        # Step 2: Re-queue the ticket
        success = dispatch_tickets(
            project_id=project.id,
            ticket_ids=[ticket.id],
            conversation_id=conversation_id
        )

        if success:
            logger.info(f"Restarted ticket execution: ticket_id={ticket_id}")
            return JsonResponse({
                'success': True,
                'message': 'Ticket restarted and queued for execution',
                'ticket_id': ticket_id,
                'queue_status': 'queued'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Failed to queue ticket after reset'
            }, status=500)

    except Exception as e:
        logger.error(f"Error restarting ticket: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def project_queue_status_api(request, project_id):
    """API endpoint to get queue status for a project"""
    from tasks.dispatch import get_project_queue_info

    # Get project
    project = get_object_or_404(Project, project_id=project_id)

    # Check if user has permission to view this project
    if not (project.owner == request.user or project.members.filter(user=request.user, status='active').exists()):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    try:
        # Get queue info from Redis
        queue_info = get_project_queue_info(project.id)

        # Get ticket statuses from database
        queued_tickets = ProjectTicket.objects.filter(
            project=project,
            queue_status__in=['queued', 'executing']
        ).values('id', 'title', 'queue_status', 'queued_at')

        return JsonResponse({
            'success': True,
            'project_id': project_id,
            'is_executing': queue_info.get('is_executing', False),
            'queue_position': queue_info.get('queue_position'),
            'total_queued': queue_info.get('total_queued', 0),
            'queued_ticket_ids': queue_info.get('queued_ticket_ids', []),
            'tickets': list(queued_tickets)
        })

    except Exception as e:
        logger.error(f"Error getting project queue status: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def ticket_logs_api(request, project_id, ticket_id):
    """API endpoint to get execution logs for a ticket"""
    project = get_object_or_404(Project, project_id=project_id)
    ticket = get_object_or_404(ProjectTicket, id=ticket_id, project=project)

    # Check if user has permission to view this project
    if not (project.owner == request.user or project.members.filter(user=request.user, status='active').exists()):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    logs = []

    # Parse the ticket notes field to extract execution logs
    if ticket.notes:
        # The notes contain execution information with timestamps and status
        # Parse them into structured log entries
        import re
        from datetime import datetime

        # Split by timestamp pattern to get individual log entries
        log_entries = re.split(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]', ticket.notes)

        # Process log entries (pattern: timestamp, content, timestamp, content, ...)
        for i in range(1, len(log_entries), 2):
            if i + 1 < len(log_entries):
                timestamp_str = log_entries[i]
                content = log_entries[i + 1].strip()

                # Determine status from content
                if 'IMPLEMENTATION COMPLETED' in content or 'Complete' in content:
                    status = 'completed'
                elif 'IMPLEMENTATION FAILED' in content or 'FATAL ERROR' in content:
                    status = 'failed'
                elif 'RETRYABLE ERROR' in content:
                    status = 'retrying'
                else:
                    status = 'in_progress'

                # Extract key information
                time_match = re.search(r'Time: ([\d.]+)', content)
                execution_time = time_match.group(1) if time_match else None

                error_match = re.search(r'Error: (.+?)(?:\n|$)', content)
                error = error_match.group(1) if error_match else None

                logs.append({
                    'timestamp': timestamp_str,
                    'status': status,
                    'notes': content,
                    'execution_time': execution_time,
                    'error': error,
                    'summary': f"{ticket.status.replace('_', ' ').title()} - {execution_time}s" if execution_time else ticket.status.replace('_', ' ').title()
                })

    return JsonResponse({
        'success': True,
        'logs': logs,
        'ticket_id': ticket_id,
        'ticket_status': ticket.status
    })


@login_required
def ticket_tasks_api(request, project_id, ticket_id):
    """API endpoint to get tasks for a ticket"""
    from projects.models import ProjectTodoList

    project = get_object_or_404(Project, project_id=project_id)
    ticket = get_object_or_404(ProjectTicket, id=ticket_id, project=project)

    # Check if user has permission to view this project
    if not (project.owner == request.user or project.members.filter(user=request.user, status='active').exists()):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # Get tasks from ProjectTodoList model
    task_objects = ProjectTodoList.objects.filter(ticket=ticket).order_by('order')

    tasks = []
    for task in task_objects:
        tasks.append({
            'id': task.id,
            'description': task.description,
            'status': task.status,
            'order': task.order,
            'created_at': task.created_at.isoformat() if task.created_at else None,
            'updated_at': task.updated_at.isoformat() if task.updated_at else None
        })

    return JsonResponse({
        'success': True,
        'tasks': tasks,
        'ticket_id': ticket_id,
        'total_tasks': len(tasks)
    })


@login_required
@require_http_methods(["GET", "POST"])
def ticket_stages_api(request, project_id):
    """API endpoint to list all stages or create a new stage"""
    project = get_object_or_404(Project, project_id=project_id)

    # Check permissions
    if not (project.owner == request.user or project.members.filter(user=request.user, status='active').exists()):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    if request.method == 'GET':
        # Get all stages for this project, create defaults if none exist
        stages = TicketStage.objects.filter(project=project).order_by('order')
        if not stages.exists():
            TicketStage.get_or_create_defaults(project)
            stages = TicketStage.objects.filter(project=project).order_by('order')

        stages_data = []
        for stage in stages:
            stages_data.append({
                'id': stage.id,
                'name': stage.name,
                'color': stage.color,
                'order': stage.order,
                'is_default': stage.is_default,
                'is_completed': stage.is_completed,
                'ticket_count': stage.tickets.count()
            })

        return JsonResponse({
            'success': True,
            'stages': stages_data
        })

    elif request.method == 'POST':
        # Create a new stage
        if not project.can_user_manage_tickets(request.user):
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        name = data.get('name', '').strip()
        if not name:
            return JsonResponse({'success': False, 'error': 'Stage name is required'}, status=400)

        # Check for duplicate name
        if TicketStage.objects.filter(project=project, name=name).exists():
            return JsonResponse({'success': False, 'error': 'A stage with this name already exists'}, status=400)

        # Get the highest order and add 1
        max_order = TicketStage.objects.filter(project=project).order_by('-order').values_list('order', flat=True).first()
        new_order = (max_order or 0) + 1

        stage = TicketStage.objects.create(
            project=project,
            name=name,
            color=data.get('color', '#6366f1'),
            order=new_order,
            is_default=data.get('is_default', False),
            is_completed=data.get('is_completed', False)
        )

        return JsonResponse({
            'success': True,
            'stage': {
                'id': stage.id,
                'name': stage.name,
                'color': stage.color,
                'order': stage.order,
                'is_default': stage.is_default,
                'is_completed': stage.is_completed,
                'ticket_count': 0
            }
        })


@login_required
@require_http_methods(["PUT", "DELETE"])
def ticket_stage_detail_api(request, project_id, stage_id):
    """API endpoint to update or delete a stage"""
    project = get_object_or_404(Project, project_id=project_id)
    stage = get_object_or_404(TicketStage, id=stage_id, project=project)

    # Check permissions
    if not project.can_user_manage_tickets(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if 'name' in data:
            name = data['name'].strip()
            if name and name != stage.name:
                # Check for duplicate name
                if TicketStage.objects.filter(project=project, name=name).exclude(id=stage_id).exists():
                    return JsonResponse({'success': False, 'error': 'A stage with this name already exists'}, status=400)
                stage.name = name

        if 'color' in data:
            stage.color = data['color']
        if 'is_default' in data:
            if data['is_default']:
                # Unset default from other stages
                TicketStage.objects.filter(project=project, is_default=True).update(is_default=False)
            stage.is_default = data['is_default']
        if 'is_completed' in data:
            stage.is_completed = data['is_completed']

        stage.save()

        return JsonResponse({
            'success': True,
            'stage': {
                'id': stage.id,
                'name': stage.name,
                'color': stage.color,
                'order': stage.order,
                'is_default': stage.is_default,
                'is_completed': stage.is_completed,
                'ticket_count': stage.tickets.count()
            }
        })

    elif request.method == 'DELETE':
        # Check if there are tickets in this stage
        ticket_count = stage.tickets.count()
        if ticket_count > 0:
            # Move tickets to the default stage or first stage
            default_stage = TicketStage.objects.filter(project=project, is_default=True).exclude(id=stage_id).first()
            if not default_stage:
                default_stage = TicketStage.objects.filter(project=project).exclude(id=stage_id).order_by('order').first()
            if default_stage:
                stage.tickets.update(stage=default_stage)
            else:
                stage.tickets.update(stage=None)

        stage.delete()
        return JsonResponse({'success': True})


@login_required
@require_http_methods(["POST"])
def ticket_stages_reorder_api(request, project_id):
    """API endpoint to reorder stages"""
    project = get_object_or_404(Project, project_id=project_id)

    if not project.can_user_manage_tickets(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    stage_ids = data.get('stage_ids', [])
    if not stage_ids:
        return JsonResponse({'success': False, 'error': 'stage_ids is required'}, status=400)

    # Update order for each stage
    for order, stage_id in enumerate(stage_ids):
        TicketStage.objects.filter(id=stage_id, project=project).update(order=order)

    return JsonResponse({'success': True})


@login_required
@require_http_methods(["GET"])
def ticket_git_status_api(request, project_id, ticket_id):
    """
    API endpoint to get git status information for a ticket.

    Returns:
        - branch: Feature branch name
        - commit_sha: Latest commit SHA (if any)
        - merge_status: Status of merge to lfg-agent
        - repo_url: GitHub repository URL
        - has_uncommitted_changes: Whether there are uncommitted changes in workspace
    """
    from accounts.models import GitHubToken
    from development.models import MagpieWorkspace
    from codebase_index.models import IndexedRepository
    from factory.ai_functions import get_magpie_client, _run_magpie_ssh

    project = get_object_or_404(Project, project_id=project_id)
    ticket = get_object_or_404(ProjectTicket, id=ticket_id, project=project)

    # Check permissions
    if not (project.owner == request.user or project.members.filter(user=request.user, status='active').exists()):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # Get GitHub info from IndexedRepository (linked to project)
    github_owner = None
    github_repo = None
    repo_url = None

    try:
        indexed_repo = IndexedRepository.objects.get(project=project)
        github_owner = indexed_repo.github_owner
        github_repo = indexed_repo.github_repo_name
        repo_url = indexed_repo.github_url
    except IndexedRepository.DoesNotExist:
        pass

    # Build response data
    response_data = {
        'success': True,
        'branch': ticket.github_branch,
        'commit_sha': ticket.github_commit_sha,
        'merge_status': ticket.github_merge_status,
        'github_owner': github_owner,
        'github_repo': github_repo,
        'repo_url': repo_url,
    }

    # Add URLs if we have repo info
    if github_owner and github_repo:
        if not repo_url:
            response_data['repo_url'] = f"https://github.com/{github_owner}/{github_repo}"
        if ticket.github_branch:
            response_data['branch_url'] = f"https://github.com/{github_owner}/{github_repo}/tree/{ticket.github_branch}"
        if ticket.github_commit_sha:
            response_data['commit_url'] = f"https://github.com/{github_owner}/{github_repo}/commit/{ticket.github_commit_sha}"
        # Add lfg-agent branch URL
        response_data['lfg_agent_url'] = f"https://github.com/{github_owner}/{github_repo}/tree/lfg-agent"

    # Get workspace info for live git status
    workspace = MagpieWorkspace.objects.filter(
        project=project,
        status='ready'
    ).order_by('-updated_at').first()

    # Try to get live git status from workspace if available
    if workspace:
        try:
            client = get_magpie_client()

            # Get current branch in workspace
            branch_result = _run_magpie_ssh(
                client,
                workspace.workspace_id,
                "cd /workspace/nextjs-app && git branch --show-current 2>/dev/null || echo ''",
                timeout=30,
                with_node_env=False
            )
            response_data['current_branch'] = branch_result.get('stdout', '').strip()

            # Get git status (check for uncommitted changes)
            status_result = _run_magpie_ssh(
                client,
                workspace.workspace_id,
                "cd /workspace/nextjs-app && git status --porcelain 2>/dev/null | head -20",
                timeout=30,
                with_node_env=False
            )
            status_output = status_result.get('stdout', '').strip()
            response_data['has_uncommitted_changes'] = len(status_output) > 0
            if status_output:
                response_data['uncommitted_files'] = [f for f in status_output.split('\n') if f.strip()]

            # Get recent commits on this branch (last 5)
            log_result = _run_magpie_ssh(
                client,
                workspace.workspace_id,
                "cd /workspace/nextjs-app && git log --oneline -5 2>/dev/null || echo ''",
                timeout=30,
                with_node_env=False
            )
            log_output = log_result.get('stdout', '').strip()
            if log_output:
                response_data['recent_commits'] = [c for c in log_output.split('\n') if c.strip()]

        except Exception as e:
            logger.warning(f"Could not get git status from workspace: {e}")
            # Don't fail the request, just note we couldn't get live status

    return JsonResponse(response_data)


@login_required
@require_http_methods(["POST"])
def push_to_lfg_agent_api(request, project_id, ticket_id):
    """
    API endpoint to commit, push, and merge changes to lfg-agent branch.

    This performs:
    1. git add -A
    2. git commit with ticket info
    3. git push to feature branch
    4. Merge feature branch into lfg-agent
    """
    from accounts.models import GitHubToken
    from development.models import MagpieWorkspace
    from codebase_index.models import IndexedRepository
    from tasks.task_definitions import commit_and_push_changes, merge_feature_to_lfg_agent

    project = get_object_or_404(Project, project_id=project_id)
    ticket = get_object_or_404(ProjectTicket, id=ticket_id, project=project)

    # Check permissions
    if not project.can_user_manage_tickets(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # Validate ticket has a branch
    if not ticket.github_branch:
        return JsonResponse({
            'success': False,
            'error': 'Ticket does not have a feature branch assigned'
        }, status=400)

    # Get GitHub token
    try:
        github_token_obj = GitHubToken.objects.get(user=request.user)
        github_token = github_token_obj.access_token
    except GitHubToken.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'GitHub not connected. Please connect GitHub in settings.',
            'requires_github_setup': True
        }, status=400)

    # Get GitHub repo info from IndexedRepository
    try:
        indexed_repo = IndexedRepository.objects.get(project=project)
        github_owner = indexed_repo.github_owner
        github_repo = indexed_repo.github_repo_name
    except IndexedRepository.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'GitHub repository not configured for this project'
        }, status=400)

    # Get workspace
    workspace = MagpieWorkspace.objects.filter(
        project=project,
        status='ready'
    ).order_by('-updated_at').first()

    if not workspace:
        return JsonResponse({
            'success': False,
            'error': 'No active workspace found. Please ensure the workspace is running.'
        }, status=400)

    try:
        # Parse request body for optional commit message
        try:
            data = json.loads(request.body.decode('utf-8')) if request.body else {}
        except:
            data = {}

        custom_message = data.get('commit_message')
        commit_message = custom_message or f"feat: {ticket.name}\n\nImplemented ticket #{ticket.id}\n\n{ticket.description[:200] if ticket.description else ''}"

        # Step 1: Commit and push changes
        logger.info(f"[GIT API] Committing and pushing changes for ticket #{ticket_id}")
        commit_result = commit_and_push_changes(
            workspace.workspace_id,
            ticket.github_branch,
            commit_message,
            ticket.id
        )

        if commit_result['status'] != 'success':
            return JsonResponse({
                'success': False,
                'error': f"Failed to commit/push: {commit_result.get('message', 'Unknown error')}",
                'details': commit_result
            }, status=500)

        commit_sha = commit_result.get('commit_sha')

        # Save commit SHA to ticket
        if commit_sha:
            ticket.github_commit_sha = commit_sha
            ticket.save(update_fields=['github_commit_sha'])

        # Step 2: Merge into lfg-agent
        logger.info(f"[GIT API] Merging {ticket.github_branch} into lfg-agent")
        merge_result = merge_feature_to_lfg_agent(
            github_token,
            github_owner,
            github_repo,
            ticket.github_branch
        )

        merge_status = merge_result.get('status', 'error')

        # Map status to model choices
        if merge_status == 'success':
            ticket.github_merge_status = 'merged'
        elif merge_status == 'conflict':
            ticket.github_merge_status = 'conflict'
        else:
            ticket.github_merge_status = 'failed'

        ticket.save(update_fields=['github_merge_status'])

        # Build response
        response_data = {
            'success': merge_status in ['success'],
            'commit_sha': commit_sha,
            'merge_status': ticket.github_merge_status,
            'merge_message': merge_result.get('message', ''),
        }

        if commit_sha:
            response_data['commit_url'] = f"https://github.com/{github_owner}/{github_repo}/commit/{commit_sha}"

        if ticket.github_merge_status == 'merged':
            response_data['lfg_agent_url'] = f"https://github.com/{github_owner}/{github_repo}/tree/lfg-agent"

        if merge_status == 'conflict':
            response_data['error'] = 'Merge conflict detected. Manual resolution may be required.'
            return JsonResponse(response_data, status=409)
        elif merge_status not in ['success']:
            response_data['error'] = merge_result.get('message', 'Merge failed')
            return JsonResponse(response_data, status=500)

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error in push_to_lfg_agent: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def design_features_api(request, project_id):
    """API endpoint to get design features for the canvas."""
    import logging
    logger = logging.getLogger(__name__)

    project = get_object_or_404(Project, project_id=project_id)
    logger.info(f"[design_features_api] Fetching design features for project: {project_id}")

    # Check if user has permission to view this project
    if not (project.owner == request.user or project.members.filter(user=request.user, status='active').exists()):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # Get all design features from the dedicated model
    design_features = ProjectDesignFeature.objects.filter(project=project).order_by('-updated_at')
    logger.info(f"[design_features_api] Found {design_features.count()} design features")

    features = []
    for df in design_features:
        logger.info(f"[design_features_api] Processing feature: id={df.id}, name={df.feature_name}, pages_count={len(df.pages or [])}")

        # Mark entry pages
        pages = df.pages or []
        for page in pages:
            page['is_entry'] = page.get('page_id') == df.entry_page_id

        # Safely get platform field (might not exist if migration hasn't run)
        try:
            platform = df.platform
        except AttributeError:
            platform = 'web'  # Default fallback

        features.append({
            'feature_id': df.id,  # Use db id as feature_id for JS compatibility
            'feature_name': df.feature_name,
            'feature_description': df.feature_description,
            'explainer': df.explainer,
            'platform': platform,
            'css_style': df.css_style,
            'common_elements': df.common_elements or [],
            'pages': pages,
            'entry_page_id': df.entry_page_id,
            'feature_connections': df.feature_connections or [],
            'canvas_position': df.canvas_position or {'x': 100, 'y': 100},
            'created_at': df.created_at.isoformat(),
            'updated_at': df.updated_at.isoformat()
        })

    logger.info(f"[design_features_api] Returning {len(features)} features")
    return JsonResponse({
        'success': True,
        'features': features
    })


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def design_positions_api(request, project_id):
    """API endpoint to save feature positions on the canvas"""
    project = get_object_or_404(Project, project_id=project_id)

    # Check if user has permission to edit this project
    if not (project.owner == request.user or project.members.filter(user=request.user, status='active').exists()):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    try:
        data = json.loads(request.body)
        positions = data.get('positions', {})

        updated_count = 0
        for feature_id, position in positions.items():
            # Update the design feature's canvas position using db id
            updated = ProjectDesignFeature.objects.filter(
                project=project,
                id=feature_id
            ).update(canvas_position=position)

            if updated:
                updated_count += 1

        return JsonResponse({
            'success': True,
            'updated_count': updated_count
        })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error saving design positions: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def design_chat_api(request, project_id):
    """API endpoint for AI-powered design editing chat"""
    import anthropic
    from factory.ai_tools import tools_design_chat

    project = get_object_or_404(Project, project_id=project_id)

    # Check permission
    if not (project.owner == request.user or project.members.filter(user=request.user, status='active').exists()):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    try:
        data = json.loads(request.body)
        feature_id = data.get('feature_id')  # This is the db id
        page_id = data.get('page_id')
        user_message = data.get('message', '')

        if not feature_id or not page_id or not user_message:
            return JsonResponse({'success': False, 'error': 'Missing required fields'}, status=400)

        # Get the design feature
        design_feature = ProjectDesignFeature.objects.filter(project=project, id=feature_id).first()
        if not design_feature:
            return JsonResponse({'success': False, 'error': 'Design feature not found'}, status=404)

        # Find the specific page
        pages = design_feature.pages or []
        page_index = None
        current_page = None
        for i, page in enumerate(pages):
            if page.get('page_id') == page_id:
                page_index = i
                current_page = page
                break

        if current_page is None:
            return JsonResponse({'success': False, 'error': 'Page not found'}, status=404)

        # Get common elements
        common_elements = design_feature.common_elements or []

        # Build common elements context for the AI
        common_elements_text = ""
        if common_elements:
            common_elements_text = "\n\nCommon Elements (header, footer, sidebar, etc.):\n"
            for elem in common_elements:
                common_elements_text += f"""
--- {elem.get('element_name', 'Unknown')} ({elem.get('element_type', 'unknown')}) ---
Element ID: {elem.get('element_id')}
Position: {elem.get('position', 'unknown')}
HTML:
```html
{elem.get('html_content', '')}
```
"""

        # Build the prompt for the AI
        system_prompt = """You are a UI/UX design assistant that helps modify HTML designs based on user requests.
You will be given the current screen design which consists of:
1. Page Content Partial - the main content area (does NOT include header/footer/sidebar)
2. Common Elements - shared components like header, footer, sidebar that are rendered separately

IMPORTANT ARCHITECTURE:
- Pages contain ONLY the main content partial (wrapped in <main> or content container)
- Common elements (header, footer, sidebar) are SEPARATE and composed during rendering
- When editing, you MUST specify edit_target:
  - Use "page_content" to edit the main content partial
  - Use "common_element" to edit a shared element (must also provide element_id)

RULES:
- Keep the same design language and style as the original
- Only modify what's necessary to fulfill the request
- Ensure the HTML remains valid and well-structured
- If user asks to change header/footer/sidebar, use edit_target="common_element" with the correct element_id
- If user asks to change main content, use edit_target="page_content"
- Preserve all existing functionality unless explicitly asked to change it"""

        user_prompt = f"""Current Screen: {current_page.get('page_name', 'Unknown')}
Feature: {design_feature.feature_name}

Current CSS (shared across all elements):
```css
{design_feature.css_style or 'No CSS defined'}
```

Page Content Partial (main content only, no header/footer):
```html
{current_page.get('html_content', '')}
```
{common_elements_text}

User Request: {user_message}

Please use the edit_design_screen tool to provide the updated HTML with the requested changes.
Remember to set edit_target correctly:
- "page_content" for main content changes
- "common_element" (with element_id) for header/footer/sidebar changes"""

        # Call Anthropic API
        client = anthropic.Anthropic()

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            system=system_prompt,
            tools=tools_design_chat,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )

        # Process the response
        updated_html = None
        updated_css = None
        change_summary = None
        edit_target = None
        element_id = None
        assistant_message = ""

        for block in response.content:
            if block.type == "text":
                assistant_message = block.text
            elif block.type == "tool_use" and block.name == "edit_design_screen":
                tool_input = block.input
                updated_html = tool_input.get('updated_html')
                updated_css = tool_input.get('updated_css')
                change_summary = tool_input.get('change_summary', 'Design updated')
                edit_target = tool_input.get('edit_target', 'page_content')
                element_id = tool_input.get('element_id')

        if updated_html:
            # Determine what to update based on edit_target
            if edit_target == 'common_element' and element_id:
                # Update a common element
                element_updated = False
                for i, elem in enumerate(common_elements):
                    if elem.get('element_id') == element_id:
                        common_elements[i]['html_content'] = updated_html
                        element_updated = True
                        break

                if not element_updated:
                    return JsonResponse({
                        'success': False,
                        'error': f'Common element with id "{element_id}" not found'
                    }, status=404)

                design_feature.common_elements = common_elements
            else:
                # Update the page's HTML content (default behavior)
                pages[page_index]['html_content'] = updated_html
                design_feature.pages = pages

            # Update CSS if provided
            if updated_css:
                design_feature.css_style = updated_css

            # Save to database
            design_feature.save()

            # Build the composed HTML for preview (page content + common elements)
            composed_html = _compose_page_html(current_page, common_elements, page_id)
            if edit_target == 'common_element':
                # Re-compose with updated common elements
                composed_html = _compose_page_html(current_page, common_elements, page_id)

            return JsonResponse({
                'success': True,
                'updated_html': updated_html,
                'updated_css': updated_css or design_feature.css_style,
                'composed_html': composed_html,
                'edit_target': edit_target,
                'element_id': element_id,
                'change_summary': change_summary,
                'assistant_message': assistant_message or change_summary
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'AI did not return updated HTML',
                'assistant_message': assistant_message
            }, status=400)

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error in design chat: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def _compose_page_html(page, common_elements, page_id):
    """Compose a full page HTML by combining page content with applicable common elements."""
    if not common_elements:
        return page.get('html_content', '')

    # Filter common elements that apply to this page
    applicable_elements = []
    for elem in common_elements:
        applies_to = elem.get('applies_to', [])
        exclude_from = elem.get('exclude_from', [])

        # Check if element applies to this page
        if 'all' in applies_to or page_id in applies_to:
            if page_id not in exclude_from:
                applicable_elements.append(elem)

    # Sort by position for proper ordering
    position_order = {'fixed-top': 0, 'top': 1, 'left': 2, 'right': 3, 'bottom': 4, 'fixed-bottom': 5}
    applicable_elements.sort(key=lambda x: position_order.get(x.get('position', 'top'), 1))

    # Build composed HTML
    top_elements = []
    left_elements = []
    right_elements = []
    bottom_elements = []

    for elem in applicable_elements:
        pos = elem.get('position', 'top')
        html = elem.get('html_content', '')
        if pos in ['top', 'fixed-top']:
            top_elements.append(html)
        elif pos == 'left':
            left_elements.append(html)
        elif pos == 'right':
            right_elements.append(html)
        elif pos in ['bottom', 'fixed-bottom']:
            bottom_elements.append(html)

    # Compose the full page
    composed = ""
    composed += "\n".join(top_elements)

    if left_elements or right_elements:
        composed += '<div class="layout-wrapper">'
        composed += "\n".join(left_elements)
        composed += f'<div class="main-content">{page.get("html_content", "")}</div>'
        composed += "\n".join(right_elements)
        composed += '</div>'
    else:
        composed += page.get('html_content', '')

    composed += "\n".join(bottom_elements)

    return composed


# ============== Design Canvas API Endpoints ==============

@login_required
@require_http_methods(["GET", "POST"])
def design_canvases_api(request, project_id):
    """API endpoint to list and create design canvases."""
    project = get_object_or_404(Project, project_id=project_id)

    # Check permission
    if not (project.owner == request.user or project.members.filter(user=request.user, status='active').exists()):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    if request.method == 'GET':
        # List all canvases for this project
        canvases = DesignCanvas.objects.filter(project=project).order_by('-is_default', '-updated_at')

        canvas_list = []
        for canvas in canvases:
            canvas_list.append({
                'id': canvas.id,
                'name': canvas.name,
                'description': canvas.description,
                'is_default': canvas.is_default,
                'feature_positions': canvas.feature_positions,
                'visible_features': canvas.visible_features,
                'created_at': canvas.created_at.isoformat(),
                'updated_at': canvas.updated_at.isoformat()
            })

        return JsonResponse({
            'success': True,
            'canvases': canvas_list
        })

    elif request.method == 'POST':
        # Create a new canvas
        try:
            data = json.loads(request.body)
            name = data.get('name', '').strip()
            description = data.get('description', '')
            is_default = data.get('is_default', False)
            feature_positions = data.get('feature_positions', {})
            visible_features = data.get('visible_features', [])

            if not name:
                return JsonResponse({'success': False, 'error': 'Canvas name is required'}, status=400)

            # Check if canvas with same name exists
            if DesignCanvas.objects.filter(project=project, name=name).exists():
                return JsonResponse({'success': False, 'error': 'A canvas with this name already exists'}, status=400)

            canvas = DesignCanvas.objects.create(
                project=project,
                name=name,
                description=description,
                is_default=is_default,
                feature_positions=feature_positions,
                visible_features=visible_features
            )

            return JsonResponse({
                'success': True,
                'canvas': {
                    'id': canvas.id,
                    'name': canvas.name,
                    'description': canvas.description,
                    'is_default': canvas.is_default,
                    'feature_positions': canvas.feature_positions,
                    'visible_features': canvas.visible_features,
                    'created_at': canvas.created_at.isoformat(),
                    'updated_at': canvas.updated_at.isoformat()
                }
            })

        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Error creating canvas: {e}", exc_info=True)
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def design_canvas_detail_api(request, project_id, canvas_id):
    """API endpoint to get, update, or delete a specific canvas."""
    project = get_object_or_404(Project, project_id=project_id)

    # Check permission
    if not (project.owner == request.user or project.members.filter(user=request.user, status='active').exists()):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    canvas = get_object_or_404(DesignCanvas, id=canvas_id, project=project)

    if request.method == 'GET':
        return JsonResponse({
            'success': True,
            'canvas': {
                'id': canvas.id,
                'name': canvas.name,
                'description': canvas.description,
                'is_default': canvas.is_default,
                'feature_positions': canvas.feature_positions,
                'visible_features': canvas.visible_features,
                'created_at': canvas.created_at.isoformat(),
                'updated_at': canvas.updated_at.isoformat()
            }
        })

    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)

            if 'name' in data:
                name = data['name'].strip()
                if not name:
                    return JsonResponse({'success': False, 'error': 'Canvas name cannot be empty'}, status=400)
                # Check if another canvas has this name
                if DesignCanvas.objects.filter(project=project, name=name).exclude(id=canvas_id).exists():
                    return JsonResponse({'success': False, 'error': 'A canvas with this name already exists'}, status=400)
                canvas.name = name

            if 'description' in data:
                canvas.description = data['description']

            if 'is_default' in data:
                canvas.is_default = data['is_default']

            if 'feature_positions' in data:
                canvas.feature_positions = data['feature_positions']

            if 'visible_features' in data:
                canvas.visible_features = data['visible_features']

            canvas.save()

            return JsonResponse({
                'success': True,
                'canvas': {
                    'id': canvas.id,
                    'name': canvas.name,
                    'description': canvas.description,
                    'is_default': canvas.is_default,
                    'feature_positions': canvas.feature_positions,
                    'visible_features': canvas.visible_features,
                    'created_at': canvas.created_at.isoformat(),
                    'updated_at': canvas.updated_at.isoformat()
                }
            })

        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Error updating canvas: {e}", exc_info=True)
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    elif request.method == 'DELETE':
        canvas_name = canvas.name
        canvas.delete()
        return JsonResponse({
            'success': True,
            'message': f'Canvas "{canvas_name}" deleted successfully'
        })


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def design_canvas_save_positions_api(request, project_id, canvas_id):
    """API endpoint to save feature positions for a canvas."""
    project = get_object_or_404(Project, project_id=project_id)

    # Check permission
    if not (project.owner == request.user or project.members.filter(user=request.user, status='active').exists()):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    canvas = get_object_or_404(DesignCanvas, id=canvas_id, project=project)

    try:
        data = json.loads(request.body)
        positions = data.get('positions', {})

        # Merge with existing positions
        canvas.feature_positions.update(positions)
        canvas.save()

        return JsonResponse({
            'success': True,
            'feature_positions': canvas.feature_positions
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error saving canvas positions: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def design_canvas_set_default_api(request, project_id, canvas_id):
    """API endpoint to set a canvas as the default."""
    project = get_object_or_404(Project, project_id=project_id)

    # Check permission
    if not (project.owner == request.user or project.members.filter(user=request.user, status='active').exists()):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    canvas = get_object_or_404(DesignCanvas, id=canvas_id, project=project)
    canvas.is_default = True
    canvas.save()  # The model's save() method will unset other defaults

    return JsonResponse({
        'success': True,
        'message': f'Canvas "{canvas.name}" is now the default'
    })


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def generate_single_screen_api(request, project_id):
    """API endpoint for generating a single screen from a description using AI."""
    import anthropic
    from factory.ai_tools import tools_generate_single_screen

    project = get_object_or_404(Project, project_id=project_id)

    # Check permission
    if not (project.owner == request.user or project.members.filter(user=request.user, status='active').exists()):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    try:
        data = json.loads(request.body)
        feature_id = data.get('feature_id')  # The design feature to add the screen to
        description = data.get('description', '')  # User's description of the screen

        if not feature_id or not description:
            return JsonResponse({'success': False, 'error': 'Missing required fields (feature_id, description)'}, status=400)

        # Get the design feature
        design_feature = ProjectDesignFeature.objects.filter(project=project, id=feature_id).first()
        if not design_feature:
            return JsonResponse({'success': False, 'error': 'Design feature not found'}, status=404)

        # Get existing pages to avoid duplicate IDs
        existing_pages = design_feature.pages or []
        existing_page_ids = [p.get('page_id') for p in existing_pages]
        existing_page_names = [p.get('page_name') for p in existing_pages]

        # Get common elements for context
        common_elements = design_feature.common_elements or []
        common_elements_text = ""
        if common_elements:
            common_elements_text = "\n\nExisting Common Elements (already applied to pages):\n"
            for elem in common_elements:
                common_elements_text += f"- {elem.get('element_name', 'Unknown')} ({elem.get('element_type', 'unknown')}) - Position: {elem.get('position', 'unknown')}\n"

        # Build the prompt for AI
        system_prompt = """You are a UI/UX design assistant that creates HTML designs based on user descriptions.
You will be given context about an existing feature and asked to create a new screen for it.

IMPORTANT ARCHITECTURE:
- Pages contain ONLY the main content partial (wrapped in <main> or content container)
- Common elements (header, footer, sidebar) are SEPARATE and will be composed automatically
- DO NOT include header, footer, or sidebar in your HTML - only the main content area

DESIGN GUIDELINES:
- Match the existing design language and style from the CSS provided
- Create semantic, accessible HTML
- Use the existing CSS classes where appropriate
- Keep the design clean and professional
- The content should be wrapped in a semantic container like <main> or a div with appropriate class"""

        user_prompt = f"""Feature: {design_feature.feature_name}
Feature Description: {design_feature.feature_description}

Current CSS (you can add to this if needed):
```css
{design_feature.css_style or 'No CSS defined yet'}
```
{common_elements_text}

Existing pages in this feature (avoid duplicate IDs):
{', '.join(existing_page_ids) if existing_page_ids else 'No existing pages'}

User's description for the new screen:
{description}

Please use the generate_single_screen tool to create this screen. Make sure to:
1. Use a unique page_id that doesn't conflict with existing pages
2. Create appropriate HTML content matching the user's description
3. Add any necessary CSS additions for this specific page"""

        # Call Anthropic API
        client = anthropic.Anthropic()

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            system=system_prompt,
            tools=tools_generate_single_screen,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )

        # Process the response
        page_id = None
        page_name = None
        html_content = None
        page_type = None
        css_additions = None
        assistant_message = ""

        for block in response.content:
            if block.type == "text":
                assistant_message = block.text
            elif block.type == "tool_use" and block.name == "generate_single_screen":
                tool_input = block.input
                page_id = tool_input.get('page_id')
                page_name = tool_input.get('page_name')
                html_content = tool_input.get('html_content')
                page_type = tool_input.get('page_type', 'screen')
                css_additions = tool_input.get('css_additions')

        if not page_id or not html_content:
            return JsonResponse({
                'success': False,
                'error': 'AI did not return valid screen data',
                'assistant_message': assistant_message
            }, status=400)

        # Ensure unique page_id
        original_page_id = page_id
        counter = 1
        while page_id in existing_page_ids:
            page_id = f"{original_page_id}-{counter}"
            counter += 1

        # Create the new page object
        new_page = {
            'page_id': page_id,
            'page_name': page_name,
            'html_content': html_content,
            'page_type': page_type,
            'navigates_to': []
        }

        # Add to the feature's pages
        pages = design_feature.pages or []
        pages.append(new_page)
        design_feature.pages = pages

        # Add CSS additions if provided
        if css_additions:
            current_css = design_feature.css_style or ''
            design_feature.css_style = current_css + '\n\n/* Styles for ' + page_name + ' */\n' + css_additions

        design_feature.save()

        return JsonResponse({
            'success': True,
            'page': new_page,
            'feature_id': feature_id,
            'css_style': design_feature.css_style,
            'assistant_message': assistant_message or f'Created new screen: {page_name}'
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error generating single screen: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def delete_screens_api(request, project_id):
    """API endpoint for deleting screens from a design feature."""
    project = get_object_or_404(Project, project_id=project_id)

    # Check permission
    if not (project.owner == request.user or project.members.filter(user=request.user, status='active').exists()):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    try:
        data = json.loads(request.body)
        feature_id = data.get('feature_id')
        page_ids = data.get('page_ids', [])

        if not feature_id or not page_ids:
            return JsonResponse({'success': False, 'error': 'Missing required fields (feature_id, page_ids)'}, status=400)

        # Get the design feature
        design_feature = ProjectDesignFeature.objects.filter(project=project, id=feature_id).first()
        if not design_feature:
            return JsonResponse({'success': False, 'error': 'Design feature not found'}, status=404)

        # Remove pages from the feature
        pages = design_feature.pages or []
        original_count = len(pages)

        # Filter out the pages to delete
        pages = [p for p in pages if p.get('page_id') not in page_ids]

        deleted_count = original_count - len(pages)

        if deleted_count == 0:
            return JsonResponse({'success': False, 'error': 'No matching pages found to delete'}, status=404)

        # Update the feature
        design_feature.pages = pages
        design_feature.save()

        return JsonResponse({
            'success': True,
            'deleted_count': deleted_count,
            'remaining_pages': len(pages)
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error deleting screens: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def load_external_url_api(request, project_id):
    """API endpoint for loading an external URL as a design feature."""
    project = get_object_or_404(Project, project_id=project_id)

    # Check permission
    if not (project.owner == request.user or project.members.filter(user=request.user, status='active').exists()):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    try:
        data = json.loads(request.body)
        url = data.get('url', '').strip()

        if not url:
            return JsonResponse({'success': False, 'error': 'URL is required'}, status=400)

        # Parse the URL to get domain name for feature name
        from urllib.parse import urlparse
        parsed_url = urlparse(url)
        domain = parsed_url.netloc or parsed_url.path.split('/')[0]
        feature_name = f"Live: {domain}"

        # Create a new design feature with an iframe pointing to the URL
        # The iframe will be rendered in the canvas
        html_content = f'''<div class="external-app-container" style="width: 100%; height: 100vh; display: flex; flex-direction: column;">
    <div class="external-app-header" style="padding: 8px 16px; background: #1a1a1a; border-bottom: 1px solid #2a2a2a; display: flex; align-items: center; gap: 8px;">
        <i class="fas fa-external-link-alt" style="color: #8b5cf6;"></i>
        <span style="color: #e2e8f0; font-size: 12px;">{url}</span>
    </div>
    <iframe src="{url}" style="flex: 1; width: 100%; border: none;" sandbox="allow-scripts allow-same-origin allow-forms allow-popups"></iframe>
</div>'''

        # Create or get the design feature
        design_feature, created = ProjectDesignFeature.objects.get_or_create(
            project=project,
            feature_name=feature_name,
            defaults={
                'feature_description': f'External app loaded from {url}',
                'pages': [{
                    'page_id': 'home',
                    'page_name': domain,
                    'page_type': 'screen',
                    'html_content': html_content,
                    'is_entry': True,
                    'navigates_to': []
                }],
                'entry_page_id': 'home',
                'css_style': '',
                'common_elements': [],
                'canvas_position': {'x': 50, 'y': 50}
            }
        )

        if not created:
            # Update existing feature
            design_feature.pages = [{
                'page_id': 'home',
                'page_name': domain,
                'page_type': 'screen',
                'html_content': html_content,
                'is_entry': True,
                'navigates_to': []
            }]
            design_feature.save()

        # Add the screen to the specified canvas (or default/first canvas)
        from projects.models import DesignCanvas
        canvas_id = data.get('canvas_id')
        canvas = None
        if canvas_id:
            canvas = DesignCanvas.objects.filter(project=project, id=canvas_id).first()
        if not canvas:
            canvas = DesignCanvas.objects.filter(project=project, is_default=True).first()
        if not canvas:
            canvas = DesignCanvas.objects.filter(project=project).first()

        if canvas:
            # Add position for this screen on the canvas
            screen_key = f"{design_feature.id}_home"
            positions = canvas.feature_positions or {}
            if screen_key not in positions:
                # Find a good position (offset from existing screens)
                max_x = 50
                for key, pos in positions.items():
                    if pos.get('x', 0) + 320 > max_x:
                        max_x = pos.get('x', 0) + 320
                positions[screen_key] = {'x': max_x, 'y': 50}
                canvas.feature_positions = positions
                canvas.save()

        return JsonResponse({
            'success': True,
            'feature_id': design_feature.id,
            'feature_name': feature_name,
            'created': created
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error loading external URL: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
@csrf_exempt
def provision_workspace_api(request, project_id):
    """
    Provision a new Magpie workspace for preview when one doesn't exist.
    This creates a workspace on-the-fly so users don't have to run a ticket build first.
    """
    from factory.ai_functions import MAGPIE_BOOTSTRAP_SCRIPT, _slugify_project_name, magpie_available
    from tasks.task_definitions import setup_git_in_workspace, push_template_and_create_branch

    project = get_object_or_404(Project, project_id=project_id)

    # Check access
    if not project.can_user_access(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # Check if Magpie is available
    if not magpie_available():
        return JsonResponse({
            'success': False,
            'error': 'Magpie workspace service is not configured. Please contact support.'
        }, status=503)

    # Check if workspace already exists
    existing_workspace = MagpieWorkspace.objects.filter(
        project=project,
        ipv6_address__isnull=False
    ).exclude(ipv6_address='').order_by('-updated_at').first()

    if existing_workspace:
        ipv6 = existing_workspace.ipv6_address.strip('[]') if existing_workspace.ipv6_address else None
        preview_url = get_or_fetch_proxy_url(existing_workspace, port=3000)
        if not preview_url:
            preview_url = f"http://[{ipv6}]:3000" if ipv6 else None

        # Check if workspace needs code setup (no git_configured and no template_installed)
        metadata = existing_workspace.metadata or {}
        needs_code_setup = not metadata.get('git_configured') and not metadata.get('template_installed')

        git_setup_message = None
        if needs_code_setup:
            try:
                client = get_magpie_client()
                indexed_repo = getattr(project, 'indexed_repository', None)

                if indexed_repo and indexed_repo.github_url:
                    # Has GitHub - clone the repo
                    github_token_obj = GitHubToken.objects.filter(user=request.user).first()
                    github_token = github_token_obj.access_token if github_token_obj else None

                    if github_token:
                        owner = indexed_repo.github_owner
                        repo = indexed_repo.github_repo_name
                        branch_name = indexed_repo.github_branch or 'lfg-agent'
                        logger.info(f"[PROVISION] Setting up git for existing workspace {owner}/{repo}")

                        git_result = setup_git_in_workspace(
                            workspace_id=existing_workspace.job_id,
                            owner=owner,
                            repo_name=repo,
                            branch_name=branch_name,
                            token=github_token
                        )
                        if git_result.get('status') == 'success':
                            git_setup_message = f"Git configured on branch {branch_name}"
                            metadata['git_configured'] = True
                            metadata['git_branch'] = branch_name
                            existing_workspace.metadata = metadata
                            existing_workspace.save()
                else:
                    # No GitHub - clone template
                    logger.info(f"[PROVISION] Cloning template for existing workspace")
                    template_setup_cmd = '''
cd /workspace
npm config set cache /workspace/.npm-cache
if [ ! -d nextjs-app ]; then
    git clone https://github.com/lfg-hq/nextjs-template nextjs-app
    cd nextjs-app
    npm install
    echo "Template cloned and dependencies installed"
else
    echo "Directory already exists"
fi
'''
                    result = _run_magpie_ssh(client, existing_workspace.job_id, template_setup_cmd, timeout=300)
                    if result.get('exit_code', 0) == 0:
                        git_setup_message = "Default Next.js template installed"
                        metadata['template_installed'] = True
                        existing_workspace.metadata = metadata
                        existing_workspace.save()
                    else:
                        git_setup_message = f"Template setup warning: {result.get('stderr', '')}"

            except Exception as setup_err:
                logger.warning(f"[PROVISION] Code setup error for existing workspace: {setup_err}")
                git_setup_message = f"Code setup skipped: {str(setup_err)}"

        return JsonResponse({
            'success': True,
            'message': 'Workspace already exists' + (' - code setup completed' if git_setup_message else ''),
            'git_message': git_setup_message,
            'workspace': {
                'id': existing_workspace.id,
                'workspace_id': existing_workspace.workspace_id,
                'status': existing_workspace.status,
                'ipv6_address': ipv6,
                'preview_url': preview_url,
            }
        })

    try:
        # Get Magpie client
        client = get_magpie_client()
        if not client:
            return JsonResponse({
                'success': False,
                'error': 'Failed to initialize Magpie client'
            }, status=500)

        # Create workspace name
        project_name = project.provided_name or project.name
        slug = _slugify_project_name(project_name)
        workspace_name = f"{slug}-{project.id}"

        logger.info(f"[PROVISION] Creating workspace for project {project_id}: {workspace_name}")

        # Create the Magpie persistent VM (polls internally until ready)
        vm_handle = client.jobs.create_persistent_vm(
            name=workspace_name,
            script=MAGPIE_BOOTSTRAP_SCRIPT,
            stateful=True,
            workspace_size_gb=10,
            vcpus=2,
            memory_mb=2048,
            register_proxy=True,
            proxy_port=3000,
            poll_timeout=180,
            poll_interval=5,
        )

        run_id = vm_handle.request_id
        if not run_id:
            return JsonResponse({
                'success': False,
                'error': 'Failed to create workspace - no job ID returned'
            }, status=500)

        logger.info(f"[PROVISION] Job created: {run_id}")

        # Get IP and proxy URL from the handle (already populated after polling)
        ipv6 = vm_handle.ip_address
        proxy_url = vm_handle.proxy_url

        if not ipv6:
            return JsonResponse({
                'success': False,
                'error': 'Workspace provisioning timed out - no IP address received'
            }, status=500)

        logger.info(f"[PROVISION] VM ready with IP: {ipv6}, Proxy: {proxy_url}")

        # Create DB record and mark as ready
        workspace = MagpieWorkspace.objects.create(
            project=project,
            job_id=run_id,
            workspace_id=run_id,
            status='ready',
            ipv6_address=ipv6,
            project_path='/workspace',
            proxy_url=proxy_url,
            metadata={'project_name': project_name, 'created_for_preview': True}
        )

        # Setup code in workspace
        git_setup_message = None
        try:
            indexed_repo = getattr(project, 'indexed_repository', None)
            if indexed_repo and indexed_repo.github_url:
                # Project has GitHub configured - clone the repo
                github_token_obj = GitHubToken.objects.filter(user=request.user).first()
                github_token = github_token_obj.access_token if github_token_obj else None

                if github_token:
                    owner = indexed_repo.github_owner
                    repo = indexed_repo.github_repo_name
                    branch_name = indexed_repo.github_branch or 'lfg-agent'

                    logger.info(f"[PROVISION] Setting up git for {owner}/{repo} on branch {branch_name}")

                    git_result = setup_git_in_workspace(
                        workspace_id=run_id,
                        owner=owner,
                        repo_name=repo,
                        branch_name=branch_name,
                        token=github_token
                    )

                    if git_result.get('status') == 'success':
                        git_setup_message = f"Git configured on branch {branch_name}"
                        workspace.metadata = workspace.metadata or {}
                        workspace.metadata['git_configured'] = True
                        workspace.metadata['git_branch'] = branch_name
                        workspace.save()
                    else:
                        git_setup_message = f"Git setup warning: {git_result.get('message', 'unknown error')}"
            else:
                # No GitHub repo - clone the default template so there's something to preview
                logger.info(f"[PROVISION] No GitHub repo configured, cloning default template")

                template_setup_cmd = '''
cd /workspace
npm config set cache /workspace/.npm-cache
if [ ! -d nextjs-app ]; then
    git clone https://github.com/lfg-hq/nextjs-template nextjs-app
    cd nextjs-app
    npm install
    echo "Template cloned and dependencies installed"
else
    echo "Directory already exists"
fi
'''
                result = _run_magpie_ssh(client, run_id, template_setup_cmd, timeout=300)

                if result.get('exit_code', 0) == 0:
                    git_setup_message = "Default Next.js template installed"
                    workspace.metadata = workspace.metadata or {}
                    workspace.metadata['template_installed'] = True
                    workspace.save()
                else:
                    git_setup_message = f"Template setup warning: {result.get('stderr', 'unknown error')}"
                    logger.warning(f"[PROVISION] Template setup warning: {result}")

        except Exception as git_err:
            logger.warning(f"[PROVISION] Code setup error (non-fatal): {git_err}")
            git_setup_message = f"Code setup skipped: {str(git_err)}"

        # Get preview URL
        preview_url = get_or_fetch_proxy_url(workspace, port=3000)
        if not preview_url:
            preview_url = f"http://[{ipv6}]:3000" if ipv6 else None

        return JsonResponse({
            'success': True,
            'message': 'Workspace provisioned successfully',
            'git_message': git_setup_message,
            'workspace': {
                'id': workspace.id,
                'workspace_id': workspace.workspace_id,
                'status': workspace.status,
                'ipv6_address': ipv6.strip('[]') if ipv6 else None,
                'preview_url': preview_url,
            }
        })

    except Exception as e:
        logger.exception(f"[PROVISION] Error provisioning workspace: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Failed to provision workspace: {str(e)}'
        }, status=500)
