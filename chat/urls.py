from django.urls import path
from . import views
from .views.main import user_agent_role, user_model_selection, available_models, latest_conversation, daily_token_usage, user_turbo_mode, complete_onboarding
from .views.files_extra import get_file_url
from .views.transcribe_fixed import transcribe_file


urlpatterns = [
    path('chat/', views.index, name='index'),
    path('chat/project/<str:project_id>/', views.project_chat, name='create_conversation'),
    path('chat/conversation/<int:conversation_id>/', views.show_conversation, name='conversation_detail'),
    path('api/projects/<str:project_id>/conversations/', views.conversation_list, name='conversation_list'),
    path('api/conversations/', views.create_conversation, name='create_conversation_api'),
    path('api/conversations/<int:conversation_id>/', views.conversation_detail, name='conversation_detail_api'),
    # path('api/provider/', views.ai_provider, name='ai_provider'),
    path('api/toggle-sidebar/', views.toggle_sidebar, name='toggle_sidebar'),
    # File upload API endpoints
    path('api/files/upload/', views.upload_file, name='upload_file'),
    path('api/conversations/<int:conversation_id>/files/', views.conversation_files, name='conversation_files'),
    path('api/files/<int:file_id>/url/', get_file_url, name='get_file_url'),
    path('api/files/transcribe/<int:file_id>/', transcribe_file, name='transcribe_file'),

    # Single Agent Role API
    path('api/user/agent-role/', user_agent_role, name='user_agent_role'),
    
    # Model Selection APIs
    path('api/user/model-selection/', user_model_selection, name='user_model_selection'),
    path('api/models/available/', available_models, name='available_models'),
    
    # Turbo Mode API
    path('api/user/turbo-mode/', user_turbo_mode, name='user_turbo_mode'),
    
    # Latest conversation API
    path('api/latest-conversation/', latest_conversation, name='latest_conversation'),
    
    # Daily token usage API
    path('api/daily-token-usage/', daily_token_usage, name='daily_token_usage'),

    # Onboarding API
    path('api/complete-onboarding/', complete_onboarding, name='complete_onboarding'),
] 