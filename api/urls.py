from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

# Create router for ViewSets
router = DefaultRouter()
router.register(r'profile', views.ProfileViewSet, basename='profile')
router.register(r'conversations', views.ConversationViewSet, basename='conversation')
router.register(r'messages', views.MessageViewSet, basename='message')
router.register(r'projects', views.ProjectViewSet, basename='project')
router.register(r'project-documents', views.ProjectDocumentViewSet, basename='project-document')
router.register(r'project-tickets', views.ProjectTicketViewSet, basename='project-ticket')

urlpatterns = [
    # Authentication endpoints
    path('auth/register/', views.register, name='api_register'),
    path('auth/login/', views.login, name='api_login'),
    path('auth/logout/', views.logout, name='api_logout'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/user/', views.current_user, name='current_user'),
    path('auth/google/url/', views.google_auth_url, name='google_auth_url'),
    path('auth/google/exchange/', views.google_auth_exchange, name='google_auth_exchange'),

    # API Keys
    path('api-keys/', views.api_keys, name='api_keys'),

    # Subscription
    path('subscription/', views.subscription_info, name='subscription_info'),

    # Chat helpers
    path('chat/socket/', views.chat_socket_info, name='chat_socket_info'),

    # Include router URLs
    path('', include(router.urls)),
]
