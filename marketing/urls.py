from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_page, name='landing_page'),
    path('for-agencies/', views.agencies_landing, name='agencies_landing'),
    path('for-agencies', views.agencies_landing, name='agencies_landing_no_slash'),
    path('for-startups/', views.startups_landing, name='startups_landing'),
    path('for-startups', views.startups_landing, name='startups_landing_no_slash'),
    path('for-product-managers/', views.product_managers_landing, name='product_managers_landing'),
    path('for-product-managers', views.product_managers_landing, name='product_managers_landing_no_slash'),
    path('for-technical-analysis/', views.technical_analysis_landing, name='technical_analysis_landing'),
    path('for-technical-analysis', views.technical_analysis_landing, name='technical_analysis_landing_no_slash'),
    path('for-project-planning/', views.project_planning_landing, name='project_planning_landing'),
    path('for-project-planning', views.project_planning_landing, name='project_planning_landing_no_slash'),
    path('health/', views.health_check, name='health_check'),
] 