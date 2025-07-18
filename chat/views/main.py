import json
import openai
import os
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from chat.models import Conversation, Message, AgentRole, ModelSelection
import markdown
from django.conf import settings
from django.contrib.auth.decorators import login_required
from projects.models import Project
from django.utils.decorators import method_decorator
from django.views import View
from django.utils import timezone
from datetime import datetime, time
from django.db.models import Sum
from accounts.models import TokenUsage
from accounts.utils import get_daily_token_usage


@login_required
def index(request):
    """Render the main chat interface."""
    context = {}
    
    # Ensure user has a default project
    if not request.user.projects.exists():
        default_project = Project.get_or_create_default_project(request.user)
        context['project'] = default_project
        context['project_id'] = str(default_project.project_id)  # Use project_id instead of id
    else:
        # Get the most recent project or the default one
        default_project = request.user.projects.filter(name="Untitled Project").first()
        if not default_project:
            default_project = request.user.projects.order_by('-updated_at').first()
        context['project'] = default_project
        context['project_id'] = str(default_project.project_id)  # Use project_id instead of id
    
    if hasattr(request.user, 'profile'):
        context['sidebar_collapsed'] = request.user.profile.sidebar_collapsed
    return render(request, 'chat/main.html', context)

@login_required
def project_chat(request, project_id):
    """Create a new conversation linked to a project and redirect to the chat interface."""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    
    # Redirect to the chat interface with this conversation open
    context = {
        'project': project,
        'project_id': project.project_id
    }
    
    if hasattr(request.user, 'profile'):
        context['sidebar_collapsed'] = request.user.profile.sidebar_collapsed
        
    return render(request, 'chat/main.html', context)

@login_required
def show_conversation(request, conversation_id):
    """Show a specific conversation."""
    conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
    
    # Check if this conversation is linked to any project
    project = None
    if hasattr(conversation, 'projects'):
        projects = conversation.projects.all()
        if projects.exists():
            project = projects.first()
    
    context = {
        'conversation_id': conversation.id
    }
    
    if project:
        context['project'] = project
        context['project_id'] = str(project.project_id)
    
    if hasattr(request.user, 'profile'):
        context['sidebar_collapsed'] = request.user.profile.sidebar_collapsed
        
    return render(request, 'chat/main.html', context)


@require_http_methods(["GET"])
@login_required
def conversation_list(request, project_id):
    """Return a list of all conversations for the current user."""
    # Get base queryset for user's conversations
    conversations = Conversation.objects.filter(user=request.user)
    
    # Filter by project using the correct field name
    if project_id:
        conversations = conversations.filter(project__project_id=project_id)
    
    # Order by most recent first
    conversations = conversations.order_by('-updated_at')
    
    data = []
    for conv in conversations:
        # Check if this conversation has a project
        project_info = None
        if conv.project:
            project_info = {
                'id': str(conv.project.project_id),
                'name': conv.project.name,
                'icon': conv.project.icon
            }
        
        data.append({
            'id': conv.id,
            'title': conv.title or f"Conversation {conv.id}",
            'created_at': conv.created_at.isoformat(),
            'updated_at': conv.updated_at.isoformat(),
            'project': project_info
        })
    
    return JsonResponse(data, safe=False)

@require_http_methods(["GET", "DELETE"])
@login_required
def conversation_detail(request, conversation_id):
    """Return messages for a specific conversation or delete the conversation."""
    conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
    
    # Handle DELETE request
    if request.method == "DELETE":
        conversation.delete()
        return JsonResponse({"status": "success", "message": "Conversation deleted successfully"})
    
    # Handle GET request
    messages = conversation.messages.all()
    
    # Check if this conversation is linked to any project
    project_info = None
    if hasattr(conversation, 'projects'):
        projects = conversation.projects.all()
        if projects.exists():
            project = projects.first()
            project_info = {
                'id': str(project.project_id),
                'name': project.name,
                'icon': project.icon
            }
    
    data = {
        'id': conversation.id,
        'title': conversation.title,
        'created_at': conversation.created_at.isoformat(),
        'project': project_info,
        'messages': [
            {
                'id': msg.id,
                'role': msg.role,
                'content': msg.content if msg.content is not None and msg.content != "" else \
                                            f"{msg.content_if_file[0].get('text')} (file upload)",
                'created_at': msg.created_at.isoformat(),
            }
            for msg in messages
        ]
    }
    
    return JsonResponse(data)

# @csrf_exempt
# @require_http_methods(["GET", "POST"])
# def ai_provider(request):
#     """Get or set the AI provider."""
#     if request.method == "GET":
#         return JsonResponse({"provider": settings.AI_PROVIDER_DEFAULT})
#     else:
#         data = json.loads(request.body)
#         provider = data.get('provider')
#         # In a real app, you might store this in the user's session or profile
#         # For now, we'll just return the provided value
#         return JsonResponse({"provider": provider})

@csrf_exempt
@require_http_methods(["POST"])
@login_required
def toggle_sidebar(request):
    """Toggle sidebar collapsed state and save to user profile."""
    data = json.loads(request.body)
    collapsed = data.get('collapsed', False)
    
    # Update user profile
    if hasattr(request.user, 'profile'):
        request.user.profile.sidebar_collapsed = collapsed
        request.user.profile.save()
    
    return JsonResponse({"success": True, "collapsed": collapsed})

@login_required
@require_http_methods(["GET", "PUT"])
@csrf_exempt
def user_agent_role(request):
    """Get or update the current user's agent role"""
    
    if request.method == "GET":
        # Get user's agent role or create default one
        agent_role, created = AgentRole.objects.get_or_create(
            user=request.user,
            defaults={'name': 'product_analyst'}
        )
        
        return JsonResponse({
            'success': True,
            'agent_role': {
                'name': agent_role.name,
                'display_name': agent_role.get_display_name(),
                'created_at': agent_role.created_at.isoformat(),
                'updated_at': agent_role.updated_at.isoformat()
            }
        })
    
    elif request.method == "PUT":
        try:
            data = json.loads(request.body)
            role_name = data.get('name')
            
            if not role_name:
                return JsonResponse({
                    'success': False,
                    'error': 'Role name is required'
                }, status=400)
            
            # Map frontend values to backend values
            role_mapping = {
                'developer': 'developer',
                'designer': 'designer',
                'product_analyst': 'product_analyst',
                'default': 'product_analyst'
            }
            
            # Convert frontend role name to backend role name
            backend_role_name = role_mapping.get(role_name, role_name)
            
            # Validate role name
            valid_roles = [choice[0] for choice in AgentRole.ROLE_CHOICES]
            if backend_role_name not in valid_roles:
                return JsonResponse({
                    'success': False,
                    'error': f'Invalid role. Must be one of: {", ".join(valid_roles)}'
                }, status=400)
            
            # Get or create user's agent role and update it
            agent_role, created = AgentRole.objects.get_or_create(
                user=request.user,
                defaults={'name': backend_role_name}
            )
            
            if not created:
                agent_role.name = backend_role_name
                agent_role.save()
            
            return JsonResponse({
                'success': True,
                'message': f'Agent role updated to {agent_role.get_display_name()}',
                'agent_role': {
                    'name': agent_role.name,
                    'display_name': agent_role.get_display_name(),
                    'created_at': agent_role.created_at.isoformat(),
                    'updated_at': agent_role.updated_at.isoformat()
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
@require_http_methods(["GET", "PUT"])
@csrf_exempt
def user_model_selection(request):
    """Get or update the current user's selected AI model"""
    
    if request.method == "GET":
        # Get user's model selection or create default one
        model_selection, created = ModelSelection.objects.get_or_create(
            user=request.user,
            defaults={'selected_model': 'o4-mini'}
        )
        
        return JsonResponse({
            'success': True,
            'model_selection': {
                'selected_model': model_selection.selected_model,
                'display_name': model_selection.get_display_name(),
                'created_at': model_selection.created_at.isoformat(),
                'updated_at': model_selection.updated_at.isoformat()
            }
        })
    
    elif request.method == "PUT":
        try:
            data = json.loads(request.body)
            selected_model = data.get('selected_model')
            
            if not selected_model:
                return JsonResponse({
                    'success': False,
                    'error': 'Selected model is required'
                }, status=400)
            
            # Validate model choice
            valid_models = [choice[0] for choice in ModelSelection.MODEL_CHOICES]
            if selected_model not in valid_models:
                return JsonResponse({
                    'success': False,
                    'error': f'Invalid model. Must be one of: {", ".join(valid_models)}'
                }, status=400)
            
            # Get or create user's model selection and update it
            model_selection, created = ModelSelection.objects.get_or_create(
                user=request.user,
                defaults={'selected_model': selected_model}
            )
            
            if not created:
                model_selection.selected_model = selected_model
                model_selection.save()
            
            return JsonResponse({
                'success': True,
                'message': f'Model selection updated to {model_selection.get_display_name()}',
                'model_selection': {
                    'selected_model': model_selection.selected_model,
                    'display_name': model_selection.get_display_name(),
                    'created_at': model_selection.created_at.isoformat(),
                    'updated_at': model_selection.updated_at.isoformat()
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
@require_http_methods(["GET"])
def available_models(request):
    """Get list of available AI models"""
    
    models = [
        {
            'value': choice[0],
            'display_name': choice[1]
        }
        for choice in ModelSelection.MODEL_CHOICES
    ]
    
    return JsonResponse({
        'success': True,
        'models': models
    })


@login_required
def latest_conversation(request):
    """Get the latest conversation info as JSON."""
    # Get the user's latest conversation
    latest_conv = Conversation.objects.filter(
        user=request.user
    ).order_by('-updated_at').first()
    
    if latest_conv and latest_conv.project:
        return JsonResponse({
            'success': True,
            'project_id': str(latest_conv.project.project_id),
            'conversation_id': latest_conv.id
        })
    else:
        # No conversations exist, return info to create one
        # Get the user's latest project or default
        project = request.user.projects.order_by('-updated_at').first()
        if not project:
            project = Project.get_or_create_default_project(request.user)
        
        return JsonResponse({
            'success': True,
            'project_id': str(project.project_id),
            'conversation_id': None
        })


@login_required
def daily_token_usage(request):
    """Get daily token usage for the current user."""
    # Get today's date
    today = timezone.now().date()
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timezone.timedelta(days=1)
    
    # Get today's token usage directly
    daily_tokens = TokenUsage.objects.filter(
        user=request.user,
        timestamp__gte=today_start,
        timestamp__lt=today_end
    ).aggregate(total=Sum('total_tokens'))['total'] or 0
    
    return JsonResponse({
        'success': True,
        'tokens': daily_tokens,
        'date': today.isoformat()
    }) 