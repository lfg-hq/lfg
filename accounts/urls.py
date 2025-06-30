from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .forms import PasswordResetForm
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
    
    # Email verification URLs
    path('email-verification-required/', views.email_verification_required, name='email_verification_required'),
    path('resend-verification-email/', views.resend_verification_email, name='resend_verification_email'),
    path('verify-email/<str:token>/', views.verify_email, name='verify_email'),
    
    # Password reset URLs
    path('password-reset/', views.password_reset, name='password_reset'),
    
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(
             template_name='accounts/password_reset_done.html'
         ), 
         name='password_reset_done'),
    
    path('password-reset-confirm/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(
             template_name='accounts/password_reset_confirm.html',
             success_url=reverse_lazy('password_reset_complete')
         ), 
         name='password_reset_confirm'),
    
    path('password-reset-complete/', 
         auth_views.PasswordResetCompleteView.as_view(
             template_name='accounts/password_reset_complete.html'
         ), 
         name='password_reset_complete'),
] 