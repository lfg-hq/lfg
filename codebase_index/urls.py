from django.urls import path
from . import views

app_name = 'codebase_index'

urlpatterns = [
    # Repository management views
    path('repositories/', views.repository_list, name='repository_list'),
    path('repositories/<int:repository_id>/', views.repository_detail, name='repository_detail'),
    
    # API endpoints
    path('api/detect-stack/', views.detect_stack, name='detect_stack'),
    path('api/repositories/add/', views.add_repository, name='add_repository'),
    path('api/repositories/<int:repository_id>/reindex/', views.reindex_repository, name='reindex_repository'),
    path('api/repositories/<int:repository_id>/delete/', views.delete_repository, name='delete_repository'),
    path('api/repositories/<int:repository_id>/status/', views.repository_status, name='repository_status'),
    path('api/repositories/<int:repository_id>/stats/', views.get_repository_stats, name='get_repository_stats'),
    path('api/repositories/<int:repository_id>/summary/', views.get_codebase_summary, name='get_codebase_summary'),
    path('api/repositories/<int:repository_id>/update-url/', views.update_repository_url, name='update_repository_url'),
    path('api/repositories/<int:repository_id>/preview/', views.get_code_preview, name='get_code_preview'),
    path('api/repositories/<int:repository_id>/insights/', views.get_repository_insights, name='get_repository_insights'),
    path('api/search/', views.search_codebase, name='search_codebase'),
    
    # Analytics
    path('analytics/<uuid:project_id>/', views.codebase_analytics, name='codebase_analytics'),
]