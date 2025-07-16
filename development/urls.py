from django.urls import path
from . import views
from django.conf import settings

if settings.ENVIRONMENT == 'local':
    editor_view = views.editor_local
elif settings.ENVIRONMENT == 'prod':
    editor_view = views.editor
else:
    editor_view = views.editor

urlpatterns = [
    path('editor/', editor_view, name='editor'),
    # path('editor-local/', views.editor_local, name='editor_local'),
    path('open-local-editor/', views.open_local_editor, name='open_local_editor'),
    path('get_file_tree/', views.get_file_tree, name='get_file_tree'),
    path('get_file_content/', views.get_file_content, name='get_file_content'),
    path('save_file/', views.save_file, name='save_file'),
    path('execute_command/', views.execute_command, name='execute_command'),
    path('create_folder/', views.create_folder, name='create_folder'),
    path('delete_item/', views.delete_item, name='delete_item'),
    path('rename_item/', views.rename_item, name='rename_item'),
    # path('get_sandbox_info/', views.get_sandbox_info, name='get_sandbox_info'),
    path('get_folder_contents/', views.get_folder_contents, name='get_folder_contents'),
    
    # Kubernetes API endpoints
    path('k8s/get_file_tree/', views.get_k8s_file_tree, name='get_k8s_file_tree'),
    path('k8s/get_file_content/', views.get_k8s_file_content, name='get_k8s_file_content'),
    path('k8s/save_file/', views.save_k8s_file, name='save_k8s_file'),
    path('k8s/create_folder/', views.k8s_create_folder, name='k8s_create_folder'),
    path('k8s/delete_item/', views.k8s_delete_item, name='k8s_delete_item'),
    path('k8s/rename_item/', views.k8s_rename_item, name='k8s_rename_item'),
    path('k8s/create_item/', views.k8s_create_item, name='k8s_create_item'),
    path('k8s/get_folder_contents/', views.get_k8s_folder_contents, name='get_k8s_folder_contents'),
    
    path('k8s/get_pod_info/', views.get_k8s_pod_info, name='get_k8s_pod_info'),
    path('k8s/execute_command/', views.k8s_execute_command, name='k8s_execute_command'),
    path('k8s/get_filebrowser_url/', views.get_filebrowser_url, name='get_filebrowser_url'),
] 