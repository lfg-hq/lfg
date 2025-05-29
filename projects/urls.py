from django.urls import path
from . import views


app_name = 'projects'


urlpatterns = [
    path('', views.project_list, name='project_list'),
    path('create/', views.create_project, name='create_project'),
    path('<int:project_id>/', views.project_detail, name='project_detail'),
    path('<int:project_id>/update/', views.update_project, name='update_project'),
    path('<int:project_id>/delete/', views.delete_project, name='delete_project'),
    path('<int:project_id>/terminal/', views.project_terminal, name='project_terminal'),
    path('<int:project_id>/api/features/', views.project_features_api, name='project_features_api'),
    path('<int:project_id>/api/personas/', views.project_personas_api, name='project_personas_api'),
    path('<int:project_id>/api/prd/', views.project_prd_api, name='project_prd_api'),
    path('<int:project_id>/api/design-schema/', views.project_design_schema_api, name='project_design_schema_api'),
    path('<int:project_id>/api/tickets/', views.project_tickets_api, name='project_tickets_api'),
    path('<int:project_id>/api/checklist/', views.project_checklist_api, name='project_checklist_api'),
]