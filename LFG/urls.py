from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts import views as accounts_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('marketing.urls')),  # Marketing URLs (including landing page)
    path('', include('chat.urls')),
    path('accounts/', include('accounts.urls')),
    path('settings/', accounts_views.integrations, name='settings'),  # Settings page
    path('projects/', include('projects.urls')),  # Projects URLs
    path('subscriptions/', include('subscriptions.urls')),  # Subscription URLs
    path('coding/', include('coding.urls')),  # Coding URLs
    path('api/tasks/', include('tasks.urls')),  # Task management APIs
    path('administrator-rocks/', include('administrator.urls')),  # Administrator URLs
]

# Serve media files in development
# if settings.DEBUG:
#     urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) 