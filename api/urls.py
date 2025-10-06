from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

# Create router for ViewSets
router = DefaultRouter()
router.register(r'profile', views.ProfileViewSet, basename='profile')
router.register(r'conversations', views.ConversationViewSet, basename='conversation')
router.register(r'messages', views.MessageViewSet, basename='message')

urlpatterns = [
    # Authentication endpoints
    path('auth/register/', views.register, name='api_register'),
    path('auth/login/', views.login, name='api_login'),
    path('auth/logout/', views.logout, name='api_logout'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/user/', views.current_user, name='current_user'),

    # API Keys
    path('api-keys/', views.api_keys, name='api_keys'),

    # Subscription
    path('subscription/', views.subscription_info, name='subscription_info'),

    # Include router URLs
    path('', include(router.urls)),
]
