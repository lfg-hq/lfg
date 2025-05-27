from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from django.urls import reverse_lazy

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.auth, name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page=reverse_lazy('login')), name='logout'),
    path('profile/', views.profile, name='profile'),
    path('auth/', views.auth, name='auth'),
    path('integrations/', views.integrations, name='integrations'),
    path('github-callback/', views.github_callback, name='github_callback'),
    path('save-api-key/<str:provider>/', views.save_api_key, name='save_api_key'),
    path('disconnect-api-key/<str:provider>/', views.disconnect_api_key, name='disconnect_api_key'),
] 