import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from development.models import InstantApp
from projects.models import Project

logger = logging.getLogger(__name__)


@login_required
def instant_mode(request, project_id):
    """Main instant mode page — new app conversation."""
    project = get_object_or_404(Project, project_id=project_id)
    if not project.can_user_access(request.user):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    instant_apps = InstantApp.objects.filter(project=project, user=request.user)

    return render(request, 'instant/instant_mode.html', {
        'project': project,
        'current_project': project,
        'instant_apps': instant_apps,
        'current_app': None,
    })


@login_required
def instant_app_detail(request, project_id, app_id):
    """View a specific instant app — loads its conversation + preview."""
    project = get_object_or_404(Project, project_id=project_id)
    if not project.can_user_access(request.user):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    app = get_object_or_404(InstantApp, app_id=app_id, project=project, user=request.user)
    instant_apps = InstantApp.objects.filter(project=project, user=request.user)

    return render(request, 'instant/instant_mode.html', {
        'project': project,
        'current_project': project,
        'instant_apps': instant_apps,
        'current_app': app,
    })


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
