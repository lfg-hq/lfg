from django.urls import path
from . import views

app_name = 'tasks'

urlpatterns = [
    # Task monitoring endpoints
    path('status/<str:task_id>/', views.get_task_status, name='get_task_status'),
    path('result/<str:task_id>/', views.get_task_result, name='get_task_result'),
    path('queue/status/', views.get_queue_status, name='get_queue_status'),
    
    # Scheduling endpoints
    path('schedule/cancel/<int:schedule_id>/', views.cancel_scheduled_task, name='cancel_scheduled_task'),
] 