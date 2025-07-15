from django.urls import path
from . import views
from .views.main import user_agent_role, user_model_selection, available_models, latest_conversation


urlpatterns = [
    path('chat/', views.index, name='index'),
    path('chat/project/<str:project_id>/', views.project_chat, name='create_conversation'),
    path('chat/conversation/<int:conversation_id>/', views.show_conversation, name='conversation_detail'),
    path('api/projects/<str:project_id>/conversations/', views.conversation_list, name='conversation_list'),
    path('api/conversations/<int:conversation_id>/', views.conversation_detail, name='conversation_detail_api'),
    # path('api/provider/', views.ai_provider, name='ai_provider'),
    path('api/toggle-sidebar/', views.toggle_sidebar, name='toggle_sidebar'),
    # File upload API endpoints
    path('api/files/upload/', views.upload_file, name='upload_file'),
    path('api/conversations/<int:conversation_id>/files/', views.conversation_files, name='conversation_files'),

    # Single Agent Role API
    path('api/user/agent-role/', user_agent_role, name='user_agent_role'),
    
    # Model Selection APIs
    path('api/user/model-selection/', user_model_selection, name='user_model_selection'),
    path('api/models/available/', available_models, name='available_models'),
    
    # Latest conversation API
    path('api/latest-conversation/', latest_conversation, name='latest_conversation'),
] 