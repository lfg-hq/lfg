from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from accounts import views as accounts_views

def health_check(request):
    """Simple health check endpoint for container health monitoring"""
    return JsonResponse({'status': 'healthy'}, status=200)

urlpatterns = [
    path('health/', health_check, name='health_check'),
    path('admin/', admin.site.urls),
    path('api/v1/', include('api.urls')),  # REST API endpoints
    path('', include('marketing.urls')),  # Marketing URLs (including landing page)
    path('', include('chat.urls')),
    path('accounts/', include('accounts.urls')),
    path('settings/', accounts_views.integrations, name='settings'),  # Settings page
    path('projects/', include('projects.urls')),  # Projects URLs
    path('subscriptions/', include('subscriptions.urls')),  # Subscription URLs
    path('development/', include('development.urls')),  # Development URLs
    path('api/tasks/', include('tasks.urls')),  # Task management APIs
    path('codebase/', include('codebase_index.urls')),  # Codebase indexing URLs
    path('administrator-rocks/', include('administrator.urls')),  # Administrator URLs
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) 