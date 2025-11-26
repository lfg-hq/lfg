from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_page, name='landing_page'),
    path('services/', views.services_page, name='services_page'),
    path('docs/', views.docs_page, name='docs_page'),
    path('services/inquiry/', views.submit_service_inquiry, name='submit_service_inquiry'),
    path('health/', views.health_check, name='health_check'),
]
