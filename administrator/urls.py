from django.urls import path
from . import views

app_name = 'administrator'

urlpatterns = [
    path('', views.admin_dashboard, name='dashboard'),
    path('user/<int:user_id>/', views.user_detail, name='user_detail'),
    path('api/user/<int:user_id>/stats/', views.api_user_stats, name='api_user_stats'),
    path('api/project/<int:project_id>/', views.api_project_details, name='api_project_details'),
    path('api/user/<int:user_id>/delete/', views.delete_user, name='delete_user'),
]