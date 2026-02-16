from projects.models import Project


def sidebar_projects(request):
    """
    Context processor to provide projects list for the sidebar dropdown.
    """
    if request.user.is_authenticated:
        projects = Project.objects.filter(
            owner=request.user,
            status='active'
        ).order_by('-updated_at')[:10]
        return {'projects': projects}
    return {'projects': []}
