from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .forms import PasswordResetForm
from django.urls import reverse_lazy

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.auth, name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page=reverse_lazy('accounts:login')), name='logout'),
    path('profile/', views.profile, name='profile'),
    path('auth/', views.auth, name='auth'),
    path('integrations/', views.integrations, name='integrations'),
    path('github-callback/', views.github_callback, name='github_callback'),
    path('google-login/', views.google_login, name='google_login'),
    path('google-callback/', views.google_callback, name='google_callback'),
    path('save-api-key/<str:provider>/', views.save_api_key, name='save_api_key'),
    path('disconnect-api-key/<str:provider>/', views.disconnect_api_key, name='disconnect_api_key'),
    path('toggle-llm-keys/', views.toggle_llm_byok, name='toggle_llm_byok'),
    path('agent-settings/', views.get_agent_settings, name='get_agent_settings'),
    
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
    
    # API endpoints
    path('api/auth/status/', views.auth_status, name='api_auth_status'),
    path('api/github-status/', views.github_status, name='api_github_status'),
    path('api/github-oauth-url/', views.github_oauth_url, name='api_github_oauth_url'),
    path('api/user/api-keys/', views.api_keys_status, name='api_keys_status'),
    path('profile/api-keys/', views.save_api_keys, name='api_save_keys'),
    path('verify-email-code/', views.verify_email_code, name='verify_email_code'),
    path('resend-verification-code/', views.resend_verification_code, name='resend_verification_code'),
    
    # Organization URLs
    path('organizations/', views.organization_list, name='organization_list'),
    path('organizations/create/', views.create_organization, name='create_organization'),
    path('organizations/switch/', views.switch_organization, name='switch_organization'),
    path('organization/<slug:slug>/', views.organization_dashboard, name='organization_dashboard'),
    path('organization/<slug:slug>/settings/', views.organization_settings, name='organization_settings'),
    path('organization/<slug:slug>/invite/', views.invite_member, name='invite_member'),
    path('organization/<slug:slug>/remove-member/<int:user_id>/', views.remove_member, name='remove_member'),
    path('organization/<slug:slug>/update-role/<int:user_id>/', views.update_member_role, name='update_member_role'),
    path('invitation/<str:token>/', views.accept_invitation, name='accept_invitation'),
    
    # Settings endpoints
    path('settings/project-collaboration/', views.update_project_collaboration_setting, name='update_project_collaboration_setting'),

    # Claude Code CLI Integration
    path('claude-code/start-auth/', views.claude_code_start_auth, name='claude_code_start_auth'),
    path('claude-code/submit-code/', views.claude_code_submit_code, name='claude_code_submit_code'),
    path('claude-code/status/', views.claude_code_check_status, name='claude_code_status'),
    path('claude-code/toggle/', views.claude_code_toggle, name='claude_code_toggle'),
    path('claude-code/disconnect/', views.claude_code_disconnect, name='claude_code_disconnect'),
    path('claude-code/verify/', views.claude_code_verify, name='claude_code_verify'),
] 
