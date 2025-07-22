from django.urls import path
from . import views


app_name = 'projects'


urlpatterns = [
    path('', views.project_list, name='project_list'),
    path('create/', views.create_project, name='create_project'),
    path('api/create/', views.create_project_api, name='create_project_api'),
    path('<str:project_id>/', views.project_detail, name='project_detail'),
    # path('<str:project_id>/update/', views.update_project, name='update_project'),
    path('<str:project_id>/delete/', views.delete_project, name='delete_project'),
    path('<str:project_id>/terminal/', views.project_terminal, name='project_terminal'),
    # path('<str:project_id>/api/features/', views.project_features_api, name='project_features_api'),
    # path('<str:project_id>/api/personas/', views.project_personas_api, name='project_personas_api'),
    # Unified file API
    path('<str:project_id>/api/files/', views.project_files_api, name='project_files_api'),
    
    # Legacy APIs - kept for backward compatibility
    path('<str:project_id>/api/prd/', views.project_prd_api, name='project_prd_api'),
    path('<str:project_id>/api/implementation/', views.project_implementation_api, name='project_implementation_api'),
    path('<str:project_id>/api/design-schema/', views.project_design_schema_api, name='project_design_schema_api'),
    # Removed - use project_checklist_api instead
    path('<str:project_id>/api/checklist/', views.project_checklist_api, name='project_checklist_api'),
    path('<str:project_id>/api/checklist/update/', views.update_checklist_item_api, name='update_checklist_item_api'),
    path('<str:project_id>/api/checklist/<int:item_id>/delete/', views.delete_checklist_item_api, name='delete_checklist_item_api'),
    path('<str:project_id>/api/server-configs/', views.project_server_configs_api, name='project_server_configs_api'),
    path('<str:project_id>/api/check-servers/', views.check_server_status_api, name='check_server_status_api'),
    path('<str:project_id>/api/tool-call-history/', views.project_tool_call_history_api, name='project_tool_call_history_api'),
    path('<str:project_id>/api/linear/sync/', views.linear_sync_tickets_api, name='linear_sync_tickets_api'),
    path('<str:project_id>/api/linear/teams/', views.linear_teams_api, name='linear_teams_api'),
    path('<str:project_id>/api/linear/projects/', views.linear_projects_api, name='linear_projects_api'),
    path('<str:project_id>/api/linear/create-project/', views.linear_create_project_api, name='linear_create_project_api'),
    
    # Enhanced file browser APIs
    path('<str:project_id>/api/files/browser/', views.file_browser_api, name='file_browser_api'),
    path('<str:project_id>/api/files/<int:file_id>/content/', views.file_content_api, name='file_content_api'),
]