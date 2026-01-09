from django.urls import path
from . import views


app_name = 'projects'


urlpatterns = [
    path('', views.project_list, name='project_list'),
    path('tickets/', views.tickets_list, name='tickets_list'),
    path('<str:project_id>/tickets/', views.project_tickets_list, name='project_tickets_list'),
    path('create/', views.create_project, name='create_project'),
    path('api/create/', views.create_project_api, name='create_project_api'),
    path('<str:project_id>/', views.project_detail, name='project_detail'),
    path('<str:project_id>/update/', views.update_project, name='update_project'),
    path('<str:project_id>/update-description/', views.update_project_description, name='update_project_description'),
    path('<str:project_id>/update-description/', views.update_project_description, name='update_project_description'),
    path('api/update-name/', views.update_project_name, name='update_project_name'),
    path('<str:project_id>/delete/', views.delete_project, name='delete_project'),
    path('<str:project_id>/terminal/', views.project_terminal, name='project_terminal'),
    path('<str:project_id>/preview/', views.app_preview, name='app_preview'),
    # path('<str:project_id>/api/features/', views.project_features_api, name='project_features_api'),
    # path('<str:project_id>/api/personas/', views.project_personas_api, name='project_personas_api'),
    # Unified file API
    path('<str:project_id>/api/files/', views.project_files_api, name='project_files_api'),
    
    # Legacy APIs - kept for backward compatibility
    path('<str:project_id>/api/prd/', views.project_prd_api, name='project_prd_api'),
    path('<str:project_id>/api/implementation/', views.project_implementation_api, name='project_implementation_api'),
    path('<str:project_id>/api/design-schema/', views.project_design_schema_api, name='project_design_schema_api'),

    # Design Canvas APIs
    path('<str:project_id>/api/design-features/', views.design_features_api, name='design_features_api'),
    path('<str:project_id>/api/design-positions/', views.design_positions_api, name='design_positions_api'),
    path('<str:project_id>/api/design-chat/', views.design_chat_api, name='design_chat_api'),

    # Design Canvas Management APIs
    path('<str:project_id>/api/canvases/', views.design_canvases_api, name='design_canvases_api'),
    path('<str:project_id>/api/canvases/<int:canvas_id>/', views.design_canvas_detail_api, name='design_canvas_detail_api'),
    path('<str:project_id>/api/canvases/<int:canvas_id>/positions/', views.design_canvas_save_positions_api, name='design_canvas_save_positions_api'),
    path('<str:project_id>/api/canvases/<int:canvas_id>/set-default/', views.design_canvas_set_default_api, name='design_canvas_set_default_api'),

    # Generate single screen API
    path('<str:project_id>/api/generate-screen/', views.generate_single_screen_api, name='generate_single_screen_api'),
    # Delete screens API
    path('<str:project_id>/api/delete-screens/', views.delete_screens_api, name='delete_screens_api'),
    # Load external URL API
    path('<str:project_id>/api/load-external-url/', views.load_external_url_api, name='load_external_url_api'),
    # Removed - use project_checklist_api instead
    path('<str:project_id>/api/checklist/', views.project_checklist_api, name='project_checklist_api'),
    path('<str:project_id>/api/checklist/create/', views.create_checklist_item_api, name='create_checklist_item_api'),
    path('<str:project_id>/api/checklist/update/', views.update_checklist_item_api, name='update_checklist_item_api'),
    path('<str:project_id>/api/checklist/<int:item_id>/delete/', views.delete_checklist_item_api, name='delete_checklist_item_api'),
    path('<str:project_id>/api/server-configs/', views.project_server_configs_api, name='project_server_configs_api'),
    path('<str:project_id>/api/check-servers/', views.check_server_status_api, name='check_server_status_api'),
    path('<str:project_id>/api/start-dev-server/', views.start_dev_server_api, name='start_dev_server_api'),
    path('<str:project_id>/api/stop-dev-server/', views.stop_dev_server_api, name='stop_dev_server_api'),
    path('<str:project_id>/api/provision-workspace/', views.provision_workspace_api, name='provision_workspace_api'),

    # Environment variables API
    path('<str:project_id>/api/env-vars/', views.project_env_vars_api, name='project_env_vars_api'),
    path('<str:project_id>/api/env-vars/download/', views.project_env_vars_download_api, name='project_env_vars_download_api'),
    path('<str:project_id>/api/env-vars/bulk-delete/', views.project_env_vars_bulk_delete_api, name='project_env_vars_bulk_delete_api'),
    path('<str:project_id>/api/tool-call-history/', views.project_tool_call_history_api, name='project_tool_call_history_api'),
    path('<str:project_id>/api/linear/sync/', views.linear_sync_tickets_api, name='linear_sync_tickets_api'),
    path('<str:project_id>/api/linear/teams/', views.linear_teams_api, name='linear_teams_api'),
    path('<str:project_id>/api/linear/projects/', views.linear_projects_api, name='linear_projects_api'),
    path('<str:project_id>/api/linear/create-project/', views.linear_create_project_api, name='linear_create_project_api'),
    
    # Enhanced file browser APIs
    path('<str:project_id>/api/files/browser/', views.file_browser_api, name='file_browser_api'),
    path('<str:project_id>/api/files/<int:file_id>/content/', views.file_content_api, name='file_content_api'),
    
    # File versioning APIs
    path('<str:project_id>/api/files/<int:file_id>/versions/', views.file_versions_api, name='file_versions_api'),
    path('<str:project_id>/api/files/<int:file_id>/versions/<int:version_number>/', views.file_version_content_api, name='file_version_content_api'),
    
    # File rename API
    path('<str:project_id>/api/files/<int:file_id>/rename/', views.file_rename_api, name='file_rename_api'),
    
    # File mentions API for chat
    path('<str:project_id>/api/files/mentions/', views.file_mentions_api, name='file_mentions_api'),
    
    # Project member management APIs
    path('<str:project_id>/api/members/', views.project_members_api, name='project_members_api'),
    path('<str:project_id>/api/members/invite/', views.invite_project_member_api, name='invite_project_member_api'),
    path('<str:project_id>/api/members/<int:member_id>/update/', views.update_project_member_api, name='update_project_member_api'),
    path('<str:project_id>/api/members/<int:member_id>/remove/', views.remove_project_member_api, name='remove_project_member_api'),
    path('<str:project_id>/api/invitations/', views.project_invitations_api, name='project_invitations_api'),
    
    # Project invitation acceptance (public URL with token)
    path('invitation/<str:token>/accept/', views.accept_project_invitation, name='accept_project_invitation'),

    # Ticket chat API
    path('<str:project_id>/api/tickets/<int:ticket_id>/chat/', views.ticket_chat_api, name='ticket_chat_api'),
    path('<str:project_id>/api/tickets/<int:ticket_id>/attachments/', views.ticket_attachments_api, name='ticket_attachments_api'),

    # Ticket execution API
    path('<str:project_id>/api/tickets/<int:ticket_id>/execute/', views.execute_ticket_api, name='execute_ticket_api'),

    # Ticket queue cancel API
    path('<str:project_id>/api/tickets/<int:ticket_id>/cancel-queue/', views.cancel_ticket_queue_api, name='cancel_ticket_queue_api'),

    # Ticket queue force reset API (for stuck tickets)
    path('<str:project_id>/api/tickets/<int:ticket_id>/force-reset-queue/', views.force_reset_ticket_queue_api, name='force_reset_ticket_queue_api'),

    # Ticket restart API (force reset + re-queue)
    path('<str:project_id>/api/tickets/<int:ticket_id>/restart-queue/', views.restart_ticket_queue_api, name='restart_ticket_queue_api'),

    # Project queue status API
    path('<str:project_id>/api/queue-status/', views.project_queue_status_api, name='project_queue_status_api'),

    # Ticket logs API
    path('<str:project_id>/api/tickets/<int:ticket_id>/logs/', views.ticket_logs_api, name='ticket_logs_api'),

    # Ticket tasks API
    path('<str:project_id>/api/tickets/<int:ticket_id>/tasks/', views.ticket_tasks_api, name='ticket_tasks_api'),

    # Ticket stages API
    path('<str:project_id>/api/stages/', views.ticket_stages_api, name='ticket_stages_api'),
    path('<str:project_id>/api/stages/<int:stage_id>/', views.ticket_stage_detail_api, name='ticket_stage_detail_api'),
    path('<str:project_id>/api/stages/reorder/', views.ticket_stages_reorder_api, name='ticket_stages_reorder_api'),

    # Git status and push API
    path('<str:project_id>/api/tickets/<int:ticket_id>/git-status/', views.ticket_git_status_api, name='ticket_git_status_api'),
    path('<str:project_id>/api/tickets/<int:ticket_id>/push-to-lfg-agent/', views.push_to_lfg_agent_api, name='push_to_lfg_agent_api'),
]
