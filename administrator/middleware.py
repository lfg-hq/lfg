from django.shortcuts import redirect
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import user_passes_test
from functools import wraps

def superadmin_required(view_func):
    """
    Decorator to ensure only superadmins can access a view.
    Redirects to login if not authenticated, returns 403 if not superadmin.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if not request.user.is_superuser:
            return HttpResponseForbidden("Access denied. You must be a superadmin to access this page.")
        
        return view_func(request, *args, **kwargs)
    
    return wrapper

class SuperAdminMiddleware:
    """
    Middleware to protect all administrator routes.
    Only allows superusers to access /administrator-rocks/* paths.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/administrator-rocks/'):
            if not request.user.is_authenticated:
                return redirect('login')
            
            if not request.user.is_superuser:
                return HttpResponseForbidden("Access denied. You must be a superadmin to access this page.")
        
        response = self.get_response(request)
        return response