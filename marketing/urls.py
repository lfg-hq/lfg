from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_page, name='landing_page'),
    path('blog/', views.blog_index_page, name='blog_index_page'),
    path('blog/<slug:slug>/', views.blog_detail_page, name='blog_detail_page'),
    path('ai/', views.ai_first_page, name='ai_first_page'),
    path('services/', views.services_page, name='services_page'),
    path('venture-studio/', views.venture_studio_page, name='venture_studio_page'),
    path('docs/', views.docs_page, name='docs_page'),
    path('services/inquiry/', views.submit_service_inquiry, name='submit_service_inquiry'),
    path('health/', views.health_check, name='health_check'),
]
