from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
from . import dev_server
from . import cli_endpoints

# Create router for ViewSets
router = DefaultRouter()
router.register(r'profile', views.ProfileViewSet, basename='profile')
router.register(r'conversations', views.ConversationViewSet, basename='conversation')
router.register(r'messages', views.MessageViewSet, basename='message')
router.register(r'projects', views.ProjectViewSet, basename='project')
router.register(r'project-documents', views.ProjectDocumentViewSet, basename='project-document')
router.register(r'project-tickets', views.ProjectTicketViewSet, basename='project-ticket')

urlpatterns = [
    # Authentication endpoints
    path('auth/register/', views.register, name='api_register'),
    path('auth/login/', views.login, name='api_login'),
    path('auth/logout/', views.logout, name='api_logout'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/user/', views.current_user, name='current_user'),
    path('auth/google/url/', views.google_auth_url, name='google_auth_url'),
    path('auth/google/exchange/', views.google_auth_exchange, name='google_auth_exchange'),

    # API Keys
    path('api-keys/', views.api_keys, name='api_keys'),

    # Subscription
    path('subscription/', views.subscription_info, name='subscription_info'),

    # Chat helpers
    path('chat/socket/', views.chat_socket_info, name='chat_socket_info'),

    # Dev Server management
    path('project-tickets/<int:ticket_id>/start-dev-server/', dev_server.start_dev_server, name='start_dev_server'),
    path('project-tickets/<int:ticket_id>/stop-dev-server/', dev_server.stop_dev_server, name='stop_dev_server'),
    path('project-tickets/<int:ticket_id>/dev-server-logs/', dev_server.get_dev_server_logs, name='get_dev_server_logs'),
    path('workspace/<str:workspace_id>/dev-server-logs/', dev_server.get_workspace_dev_server_logs, name='get_workspace_dev_server_logs'),

    # CLI API endpoints (for Claude Code CLI running on VM)
    path('cli/stream/', cli_endpoints.cli_stream_log, name='cli_stream_log'),
    path('cli/task/', cli_endpoints.cli_update_task, name='cli_update_task'),
    path('cli/tasks/bulk/', cli_endpoints.cli_bulk_tasks, name='cli_bulk_tasks'),
    path('cli/status/', cli_endpoints.cli_update_status, name='cli_update_status'),
    path('cli/user-action/', cli_endpoints.cli_create_user_action_ticket, name='cli_create_user_action'),
    path('cli/request-input/', cli_endpoints.cli_request_user_input, name='cli_request_user_input'),

    # Include router URLs
    path('', include(router.urls)),
]
