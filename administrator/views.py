from django.shortcuts import render, get_object_or_404
from django.contrib.auth.models import User
from django.db.models import Count, Q, Prefetch
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import timedelta

from .middleware import superadmin_required
from projects.models import Project, ProjectPRD, ProjectImplementation, ProjectChecklist
from chat.models import Conversation, Message
from accounts.models import Profile, TokenUsage

@superadmin_required
def admin_dashboard(request):
    """Main admin dashboard showing user list with statistics"""
    users = User.objects.select_related('profile').annotate(
        project_count=Count('projects'),
        conversation_count=Count('conversations')
    ).order_by('-date_joined')
    
    # Get overall statistics
    total_users = users.count()
    active_users_24h = User.objects.filter(last_login__gte=timezone.now() - timedelta(days=1)).count()
    total_projects = Project.objects.count()
    total_conversations = Conversation.objects.count()
    
    context = {
        'users': users,
        'total_users': total_users,
        'active_users_24h': active_users_24h,
        'total_projects': total_projects,
        'total_conversations': total_conversations,
    }
    
    return render(request, 'administrator/dashboard.html', context)

@superadmin_required
def user_detail(request, user_id):
    """Detailed view of a specific user and their resources"""
    user = get_object_or_404(User.objects.select_related('profile'), pk=user_id)
    
    # Get user's projects with related data
    projects = Project.objects.filter(owner=user).prefetch_related(
        'prd',
        'implementation',
        'checklist',
        'features',
        'personas'
    ).order_by('-created_at')
    
    # Get user's conversations with message count
    conversations = Conversation.objects.filter(user=user).annotate(
        message_count=Count('messages')
    ).order_by('-updated_at')[:10]  # Show last 10 conversations
    
    # Get token usage statistics
    from django.db.models import Sum
    token_usage = TokenUsage.objects.filter(user=user).values('provider', 'model').annotate(
        total_tokens=Sum('total_tokens'),
        total_cost=Sum('cost')
    )
    
    # Calculate total token usage and cost
    total_tokens = TokenUsage.objects.filter(user=user).aggregate(Sum('total_tokens'))['total_tokens__sum'] or 0
    total_cost = TokenUsage.objects.filter(user=user).aggregate(Sum('cost'))['cost__sum'] or 0
    
    context = {
        'user': user,
        'projects': projects,
        'conversations': conversations,
        'token_usage': token_usage,
        'total_tokens': total_tokens,
        'total_cost': total_cost,
    }
    
    return render(request, 'administrator/user_detail.html', context)

@superadmin_required
@require_http_methods(["GET"])
def api_user_stats(request, user_id):
    """API endpoint to get detailed user statistics"""
    user = get_object_or_404(User, pk=user_id)
    
    # Get counts for different resources
    stats = {
        'projects': {
            'total': Project.objects.filter(owner=user).count(),
            'active': Project.objects.filter(owner=user, status='active').count(),
            'with_prd': Project.objects.filter(owner=user, prd__isnull=False).count(),
            'with_implementation': Project.objects.filter(owner=user, implementation__isnull=False).count(),
        },
        'conversations': {
            'total': Conversation.objects.filter(user=user).count(),
            'last_24h': Conversation.objects.filter(
                user=user, 
                updated_at__gte=timezone.now() - timedelta(days=1)
            ).count(),
        },
        'tickets': {
            'total': ProjectChecklist.objects.filter(project__owner=user).count(),
            'open': ProjectChecklist.objects.filter(project__owner=user, status='open').count(),
            'in_progress': ProjectChecklist.objects.filter(project__owner=user, status='in_progress').count(),
            'done': ProjectChecklist.objects.filter(project__owner=user, status='done').count(),
        },
        'messages': {
            'total': Message.objects.filter(conversation__user=user).count(),
            'user_messages': Message.objects.filter(conversation__user=user, role='user').count(),
            'assistant_messages': Message.objects.filter(conversation__user=user, role='assistant').count(),
        }
    }
    
    return JsonResponse(stats)

@superadmin_required
@require_http_methods(["GET"])
def api_project_details(request, project_id):
    """API endpoint to get detailed project information"""
    project = get_object_or_404(Project, pk=project_id)
    
    # Check if requesting user is superadmin
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    # Gather project details
    data = {
        'id': project.id,
        'project_id': str(project.project_id),
        'name': project.name,
        'description': project.description,
        'icon': project.icon,
        'owner': {
            'id': project.owner.id,
            'username': project.owner.username,
            'email': project.owner.email,
        },
        'created_at': project.created_at.isoformat(),
        'updated_at': project.updated_at.isoformat(),
        'status': project.status,
        'has_prd': hasattr(project, 'prd'),
        'has_implementation': hasattr(project, 'implementation'),
        'has_design_schema': hasattr(project, 'design_schema'),
        'features_count': project.features.count(),
        'personas_count': project.personas.count(),
        'checklist_items': {
            'total': project.checklist.count(),
            'by_status': dict(project.checklist.values('status').annotate(count=Count('id')).values_list('status', 'count'))
        },
        'conversations_count': project.direct_conversations.count(),
    }
    
    # Include PRD content if exists
    if hasattr(project, 'prd') and project.prd:
        data['prd_content'] = project.prd.prd
    
    # Include implementation content if exists
    if hasattr(project, 'implementation') and project.implementation:
        data['implementation_content'] = project.implementation.implementation
    
    # Include tickets details
    tickets = project.checklist.all().values('id', 'name', 'status', 'priority', 'description')[:20]  # Limit to 20 tickets
    data['tickets'] = list(tickets)
    
    return JsonResponse(data)

@superadmin_required
@require_http_methods(["POST"])
def delete_user(request, user_id):
    """Delete a user and all their associated data"""
    import json
    
    user = get_object_or_404(User, pk=user_id)
    
    # Prevent deleting superusers
    if user.is_superuser:
        return JsonResponse({'error': 'Cannot delete superuser accounts'}, status=403)
    
    # Prevent self-deletion
    if user.id == request.user.id:
        return JsonResponse({'error': 'Cannot delete your own account'}, status=403)
    
    # Parse request body
    try:
        body = json.loads(request.body)
        confirm_email = body.get('confirm_email', '').strip()
    except:
        return JsonResponse({'error': 'Invalid request data'}, status=400)
    
    # Verify email confirmation
    if confirm_email != user.email:
        return JsonResponse({'error': 'Email confirmation does not match user email'}, status=400)
    
    # Store username and email for response
    username = user.username
    email = user.email
    
    # Log the deletion action
    import logging
    logger = logging.getLogger('administrator')
    logger.warning(f'Admin {request.user.username} (ID: {request.user.id}) is deleting user {username} (ID: {user_id}, Email: {email})')
    
    try:
        # Delete the user (this will cascade delete all related objects)
        user.delete()
        
        logger.info(f'Successfully deleted user {username} (ID: {user_id}, Email: {email})')
        
        return JsonResponse({
            'success': True,
            'message': f'User {username} ({email}) and all associated data have been deleted successfully'
        })
    except Exception as e:
        logger.error(f'Failed to delete user {username} (ID: {user_id}): {str(e)}')
        return JsonResponse({
            'error': f'Failed to delete user: {str(e)}'
        }, status=500)
