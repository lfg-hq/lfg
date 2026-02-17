import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from accounts.models import ApplicationState, TokenUsage
from chat.models import ModelSelection
from development.models import InstantApp
from factory.llm_config import get_llm_model_config, get_model_label
from projects.models import Project
from subscriptions.models import UserCredit
from subscriptions.constants import FREE_TIER_TOKEN_LIMIT, PRO_MONTHLY_TOKEN_LIMIT

logger = logging.getLogger(__name__)


def _build_instant_context(request, project, instant_apps, current_app):
    """Build the shared context dict for instant mode views."""
    # Application state (turbo mode + role)
    app_state, _ = ApplicationState.objects.get_or_create(
        user=request.user,
        defaults={'last_selected_role': 'product_analyst', 'turbo_mode_enabled': False}
    )

    # Model selection
    model_selection, _ = ModelSelection.objects.get_or_create(
        user=request.user,
        defaults={'selected_model': ModelSelection.DEFAULT_MODEL_KEY}
    )

    # Force free-tier users to default model
    if hasattr(request.user, 'credit'):
        user_credit = request.user.credit
        if user_credit.is_free_tier and model_selection.selected_model != 'gpt-5-mini':
            model_selection.selected_model = 'gpt-5-mini'
            model_selection.save()

    # Ensure sidebar defaults are set
    if not app_state.last_selected_model:
        app_state.last_selected_model = model_selection.selected_model
        app_state.save(update_fields=['last_selected_model'])

    # Subscription info
    user_credit, _ = UserCredit.objects.get_or_create(user=request.user)

    return {
        'project': project,
        'current_project': project,
        'instant_apps': instant_apps,
        'current_app': current_app,
        # Sidebar
        'sidebar_minimized': app_state.sidebar_minimized,
        # Model / role
        'model_key': model_selection.selected_model,
        'current_model_label': get_model_label(model_selection.selected_model),
        'role_key': app_state.last_selected_role,
        'turbo_mode': app_state.turbo_mode_enabled,
        # Subscription
        'is_free_tier': user_credit.is_free_tier,
        'remaining_tokens': user_credit.get_remaining_tokens(),
        'total_tokens_limit': (
            FREE_TIER_TOKEN_LIMIT if user_credit.is_free_tier else PRO_MONTHLY_TOKEN_LIMIT
        ),
        'llm_model_config': get_llm_model_config(),
    }


@login_required
def instant_mode(request, project_id):
    """Main instant mode page — new app conversation."""
    project = get_object_or_404(Project, project_id=project_id)
    if not project.can_user_access(request.user):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    instant_apps = InstantApp.objects.filter(project=project, user=request.user)
    context = _build_instant_context(request, project, instant_apps, None)

    return render(request, 'instant/instant_mode.html', context)


@login_required
def instant_app_detail(request, project_id, app_id):
    """View a specific instant app — loads its conversation + preview."""
    project = get_object_or_404(Project, project_id=project_id)
    if not project.can_user_access(request.user):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    app = get_object_or_404(InstantApp, app_id=app_id, project=project, user=request.user)
    instant_apps = InstantApp.objects.filter(project=project, user=request.user)
    context = _build_instant_context(request, project, instant_apps, app)

    return render(request, 'instant/instant_mode.html', context)


@login_required
def instant_apps_list_api(request, project_id):
    """JSON API for listing instant apps (used by project detail tab)."""
    project = get_object_or_404(Project, project_id=project_id)
    if not project.can_user_access(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    apps = InstantApp.objects.filter(project=project, user=request.user).order_by('-created_at')
    data = [
        {
            'app_id': str(a.app_id),
            'name': a.name,
            'description': (a.description or '')[:200],
            'status': a.status,
            'preview_url': a.preview_url or '',
            'created_at': a.created_at.isoformat(),
        }
        for a in apps
    ]
    return JsonResponse({'apps': data})


@login_required
def instant_app_env_vars_api(request, project_id, app_id):
    """CRUD for env vars on an instant app."""
    project = get_object_or_404(Project, project_id=project_id)
    if not project.can_user_access(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    app = get_object_or_404(InstantApp, app_id=app_id, project=project, user=request.user)

    if request.method == 'GET':
        return JsonResponse({'env_vars': app.env_vars})

    if request.method in ('POST', 'PUT'):
        try:
            body = json.loads(request.body)
            app.env_vars = body.get('env_vars', {})
            app.save(update_fields=['env_vars', 'updated_at'])
            return JsonResponse({'env_vars': app.env_vars})
        except (json.JSONDecodeError, Exception) as e:
            return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'error': 'Method not allowed'}, status=405)
