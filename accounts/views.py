from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.contrib.auth import authenticate, login
from django.conf import settings
from .forms import UserRegisterForm, UserUpdateForm, ProfileUpdateForm, EmailAuthenticationForm, PasswordResetForm, OrganizationCreationForm, OrganizationUpdateForm, OrganizationInvitationForm, MembershipUpdateForm, OrganizationSwitchForm
from django.contrib.auth.models import User
from .models import GitHubToken, EmailVerificationToken, LLMApiKeys, ExternalServicesAPIKeys, Organization, OrganizationMembership, OrganizationInvitation
from subscriptions.models import UserCredit, OrganizationCredit
from subscriptions.constants import FREE_TIER_TOKEN_LIMIT, PRO_MONTHLY_TOKEN_LIMIT
from chat.models import AgentRole
import requests
import uuid
import json
from urllib.parse import urlencode
from django.http import JsonResponse
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.core.exceptions import PermissionDenied
from django.db import transaction
import logging

logger = logging.getLogger(__name__)

def build_secure_absolute_uri(request, path):
    """Build absolute URI with HTTPS in production"""
    url = request.build_absolute_uri(path)
    # Force HTTPS in production environments
    if ENVIRONMENT != 'local' and url.startswith('http://'):
        url = url.replace('http://', 'https://', 1)
    return url

# Define GitHub OAuth constants
GITHUB_CLIENT_ID = settings.GITHUB_CLIENT_ID if hasattr(settings, 'GITHUB_CLIENT_ID') else None
GITHUB_CLIENT_SECRET = settings.GITHUB_CLIENT_SECRET if hasattr(settings, 'GITHUB_CLIENT_SECRET') else None
GITHUB_REDIRECT_URI = None  # Will be set dynamically
ENVIRONMENT = settings.ENVIRONMENT if hasattr(settings, 'ENVIRONMENT') else 'local'

# Define Google OAuth constants
GOOGLE_CLIENT_ID = settings.GOOGLE_CLIENT_ID if hasattr(settings, 'GOOGLE_CLIENT_ID') else None
GOOGLE_CLIENT_SECRET = settings.GOOGLE_CLIENT_SECRET if hasattr(settings, 'GOOGLE_CLIENT_SECRET') else None
GOOGLE_REDIRECT_URI = None  # Will be set dynamically

def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            email = form.cleaned_data.get('email')
            
            # Send verification email
            send_verification_email(request, user)
            
            # Auto-login the user
            login(request, user)
            
            # Redirect to email verification page
            return redirect('accounts:email_verification_required')
    else:
        form = UserRegisterForm()
    return render(request, 'accounts/auth.html', {'form': form, 'active_tab': 'register'})

def auth(request):
    """
    Combined login and registration view that renders the tabbed auth page.
    This view handles both GET requests (displaying the form) and POST requests
    (processing form submissions) for both login and registration.
    """
    # Initialize both forms
    login_form = EmailAuthenticationForm()
    register_form = UserRegisterForm()
    
    # Determine which form was submitted based on a hidden input field
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        
        if form_type == 'login':
            login_form = EmailAuthenticationForm(request, data=request.POST)
            if login_form.is_valid():
                user = login_form.get_user()
                
                # Check if email is verified (skip for local environment)
                profile = user.profile
                if not profile.email_verified and ENVIRONMENT != 'local':
                    # Login the user but redirect to verification page
                    login(request, user)
                    return redirect('accounts:email_verification_required')
                
                login(request, user)

                # Redirect to the chat page or next parameter if provided
                next_url = request.GET.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('index')  # Redirect to chat page
        
        elif form_type == 'register':
            register_form = UserRegisterForm(request.POST)
            if register_form.is_valid():
                user = register_form.save()
                email = register_form.cleaned_data.get('email')
                
                # Send verification email
                send_verification_email(request, user)
                
                # Auto-login the user
                login(request, user)
                
                # Redirect to email verification page
                return redirect('accounts:email_verification_required')
    
    # Render the template with both forms
    context = {
        'login_form': login_form,
        'register_form': register_form,
        'active_tab': 'login' if request.method == 'GET' or (request.method == 'POST' and request.POST.get('form_type') == 'login') else 'register'
    }
    return render(request, 'accounts/auth.html', context)

@login_required
def profile(request):
    if request.method == 'POST':
        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user.profile)
        
        if u_form.is_valid() and p_form.is_valid():
            u_form.save()
            p_form.save()
            messages.success(request, f'Your account has been updated!')
            return redirect('profile')
    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=request.user.profile)
        
    context = {
        'u_form': u_form,
        'p_form': p_form
    }
    return render(request, 'accounts/profile.html', context)

@login_required
def save_api_key(request, provider):
    """Handle saving API keys for various providers"""
    if request.method != 'POST':
        messages.error(request, 'Invalid request')
        return redirect('accounts:integrations')
    
    api_key = request.POST.get('api_key', '').strip()
    if not api_key:
        messages.error(request, 'API key cannot be empty')
        return redirect('accounts:integrations')

    if provider == 'openai':
        user_credit, _ = UserCredit.objects.get_or_create(user=request.user)
        has_paid_subscription = (
            user_credit.subscription_tier == 'pro'
            and (user_credit.is_subscribed or user_credit.has_active_subscription)
        )
        if not has_paid_subscription:
            messages.error(request, 'Upgrade to Pro to use your own OpenAI API key.')
            return redirect('accounts:integrations')
    
    # Enforce subscription requirements for OpenAI self-hosted keys
    if provider == 'openai':
        user_credit, _ = UserCredit.objects.get_or_create(user=request.user)
        has_paid_subscription = (
            user_credit.subscription_tier == 'pro'
            and (user_credit.is_subscribed or user_credit.has_active_subscription)
        )
        if not has_paid_subscription:
            messages.error(request, 'Upgrade to Pro to use your own OpenAI API key.')
            return redirect('accounts:integrations')
    
    # Handle external services (Linear, Notion, etc.) separately as they're in ExternalServicesAPIKeys
    if provider in ['linear', 'notion', 'jira']:
        external_keys, created = ExternalServicesAPIKeys.objects.get_or_create(user=request.user)
        if provider == 'linear':
            external_keys.linear_api_key = api_key
        elif provider == 'notion':
            external_keys.notion_api_key = api_key
        elif provider == 'jira':
            external_keys.jira_api_key = api_key
        external_keys.save()
    else:
        # Get or create LLMApiKeys for user
        llm_keys, created = LLMApiKeys.objects.get_or_create(user=request.user)
        
        # Update the appropriate API key based on provider
        if provider == 'openai':
            llm_keys.openai_api_key = api_key
        elif provider == 'anthropic':
            llm_keys.anthropic_api_key = api_key
        elif provider == 'xai':
            llm_keys.xai_api_key = api_key
        elif provider == 'google':
            llm_keys.google_api_key = api_key
        else:
            messages.error(request, 'Invalid provider')
            return redirect('accounts:integrations')
        
        # Save the LLM keys
        llm_keys.save()
    
    messages.success(request, f'{provider.capitalize()} API key saved successfully.')
    return redirect('accounts:integrations')

@login_required
def disconnect_api_key(request, provider):
    """Handle disconnecting API keys for various providers"""
    if request.method != 'POST':
        messages.error(request, 'Invalid request')
        return redirect('accounts:integrations')
    
    # Handle external services (Linear, Notion, etc.) separately as they're in ExternalServicesAPIKeys
    if provider in ['linear', 'notion', 'jira']:
        try:
            external_keys = ExternalServicesAPIKeys.objects.get(user=request.user)
            if provider == 'linear':
                external_keys.linear_api_key = ''
            elif provider == 'notion':
                external_keys.notion_api_key = ''
            elif provider == 'jira':
                external_keys.jira_api_key = ''
            external_keys.save()
        except ExternalServicesAPIKeys.DoesNotExist:
            messages.error(request, f'No {provider.capitalize()} API key found')
            return redirect('accounts:integrations')
    else:
        # Get LLMApiKeys for user
        try:
            llm_keys = LLMApiKeys.objects.get(user=request.user)
        except LLMApiKeys.DoesNotExist:
            messages.error(request, 'No API keys found')
            return redirect('accounts:integrations')
        
        # Update the appropriate API key based on provider
        if provider == 'openai':
            llm_keys.openai_api_key = ''
        elif provider == 'anthropic':
            llm_keys.anthropic_api_key = ''
        elif provider == 'xai':
            llm_keys.xai_api_key = ''
        elif provider == 'google':
            llm_keys.google_api_key = ''
        else:
            messages.error(request, 'Invalid provider')
            return redirect('accounts:integrations')
        
        # Save the LLM keys
        llm_keys.save()
    
    messages.success(request, f'{provider.capitalize()} connection removed successfully.')
    return redirect('accounts:integrations')


@login_required
def toggle_llm_byok(request):
    """Enable or disable BYOK usage by keeping or clearing saved keys."""
    if request.method != 'POST':
        messages.error(request, 'Invalid request')
        return redirect('accounts:integrations')

    enable = request.POST.get('enable', '1') == '1'

    user_credit, _ = UserCredit.objects.get_or_create(user=request.user)
    has_paid_subscription = (
        user_credit.subscription_tier == 'pro'
        and (user_credit.is_subscribed or user_credit.has_active_subscription)
    )

    if not has_paid_subscription:
        messages.error(request, 'Bring-your-own keys are available on the Pro plan. Please upgrade to enable this feature.')
        return redirect('accounts:integrations')

    llm_keys, _ = LLMApiKeys.objects.get_or_create(user=request.user)

    if enable:
        llm_keys.use_personal_llm_keys = True
        llm_keys.save(update_fields=['use_personal_llm_keys'])
        messages.success(request, 'Bring-your-own-keys enabled. Add your provider keys below.')
    else:
        llm_keys.openai_api_key = ''
        llm_keys.anthropic_api_key = ''
        llm_keys.google_api_key = ''
        llm_keys.xai_api_key = ''
        llm_keys.use_personal_llm_keys = False
        llm_keys.save()
        messages.success(request, 'Your provider keys were removed. LFG platform credits will be used instead.')

    return redirect('accounts:integrations')


@login_required
def github_callback(request):
    """
    Callback endpoint for GitHub OAuth flow
    """
    code = request.GET.get('code')
    state = request.GET.get('state')
    stored_state = request.session.get('github_oauth_state')
    
    # Validate state to prevent CSRF
    if not state or state != stored_state:
        messages.error(request, 'Invalid OAuth state. Please try connecting to GitHub again.')
        return redirect('accounts:integrations')
    
    if not code:
        messages.error(request, 'No authorization code received from GitHub.')
        return redirect('accounts:integrations')
    
    # Exchange code for access token
    response = requests.post(
        'https://github.com/login/oauth/access_token',
        headers={'Accept': 'application/json'},
        data={
            'client_id': GITHUB_CLIENT_ID,
            'client_secret': GITHUB_CLIENT_SECRET,
            'code': code,
            'redirect_uri': GITHUB_REDIRECT_URI,
        }
    )
    
    # Check if token exchange was successful
    if response.status_code != 200:
        messages.error(request, 'Failed to authenticate with GitHub. Please try again.')
        return redirect('accounts:integrations')
    
    # Parse token response
    token_data = response.json()
    if 'error' in token_data:
        messages.error(request, f"GitHub authentication error: {token_data.get('error_description', 'Unknown error')}")
        return redirect('accounts:integrations')
    
    access_token = token_data.get('access_token')
    scope = token_data.get('scope', '')
    
    if not access_token:
        messages.error(request, 'Failed to get access token from GitHub.')
        return redirect('accounts:integrations')
    
    # Get GitHub user info
    user_response = requests.get(
        'https://api.github.com/user',
        headers={
            'Authorization': f'token {access_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
    )
    
    if user_response.status_code != 200:
        messages.error(request, 'Failed to get user info from GitHub.')
        return redirect('accounts:integrations')
    
    github_user_data = user_response.json()
    
    # Save or update token
    try:
        github_token = GitHubToken.objects.get(user=request.user)
        github_token.access_token = access_token
        github_token.github_user_id = str(github_user_data.get('id', ''))
        github_token.github_username = github_user_data.get('login', '')
        github_token.github_avatar_url = github_user_data.get('avatar_url', '')
        github_token.scope = scope
        github_token.save()
    except GitHubToken.DoesNotExist:
        GitHubToken.objects.create(
            user=request.user,
            access_token=access_token,
            github_user_id=str(github_user_data.get('id', '')),
            github_username=github_user_data.get('login', ''),
            github_avatar_url=github_user_data.get('avatar_url', ''),
            scope=scope
        )
    
    messages.success(request, 'Successfully connected to GitHub!')
    return redirect('accounts:integrations')

@login_required
def integrations(request):
    """
    Integrations page for connecting GitHub, OpenAI, Anthropic, and XAI
    """
    # Get GitHub connection status
    github_connected = False
    github_username = None
    github_avatar = None
    github_missing_config = not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET
    
    try:
        # Try to get GitHub token first
        github_token = GitHubToken.objects.get(user=request.user)
        github_connected = True
        github_username = github_token.github_username
        github_avatar = github_token.github_avatar_url
    except GitHubToken.DoesNotExist:
        try:
            # Try social_auth as fallback (if using django-social-auth)
            github_social = request.user.social_auth.get(provider='github')
            github_connected = True
            extra_data = github_social.extra_data
            github_username = extra_data.get('login')
            github_avatar = extra_data.get('avatar_url')
        except:
            pass
    
    # Create GitHub redirect URI if not connected
    github_auth_url = None
    if not github_connected and not github_missing_config:
        global GITHUB_REDIRECT_URI
        GITHUB_REDIRECT_URI = build_secure_absolute_uri(request, reverse('accounts:github_callback'))
        state = str(uuid.uuid4())
        request.session['github_oauth_state'] = state
        params = {
            'client_id': GITHUB_CLIENT_ID,
            'redirect_uri': GITHUB_REDIRECT_URI,
            'scope': 'repo user',
            'state': state,
        }
        github_auth_url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"
    
    # Handle GitHub disconnect
    if request.method == 'POST' and request.POST.get('action') == 'github_disconnect':
        if github_connected:
            try:
                GitHubToken.objects.filter(user=request.user).delete()
                messages.success(request, 'GitHub connection removed successfully.')
                return redirect('accounts:integrations')
            except Exception as e:
                messages.error(request, f'Error disconnecting GitHub: {str(e)}')
    
    # Get or create API keys record for LLM providers
    llm_keys, _ = LLMApiKeys.objects.get_or_create(user=request.user)
    openai_connected = bool(llm_keys.openai_api_key)
    anthropic_connected = bool(llm_keys.anthropic_api_key)
    xai_connected = bool(llm_keys.xai_api_key)
    google_connected = bool(llm_keys.google_api_key)
    personal_llm_keys_enabled = llm_keys.use_personal_llm_keys
    
    # Check external service API keys (Linear, Notion, etc.)
    try:
        external_keys = ExternalServicesAPIKeys.objects.get(user=request.user)
        linear_connected = bool(external_keys.linear_api_key)
        notion_connected = bool(external_keys.notion_api_key)
    except ExternalServicesAPIKeys.DoesNotExist:
        linear_connected = False
        notion_connected = False
    
    # Get user's organization role if in an organization
    current_org_role = None
    if request.user.profile.current_organization:
        current_org_role = request.user.profile.current_organization.get_user_role(request.user)

    # Get user's credit and token usage information
    user_credit, created = UserCredit.objects.get_or_create(user=request.user)
    
    # Determine subscription access flags
    has_paid_subscription = (
        user_credit.subscription_tier == 'pro'
        and (user_credit.is_subscribed or user_credit.has_active_subscription)
    )

    # Calculate usage percentages and display tokens
    if user_credit.is_free_tier:
        total_limit = FREE_TIER_TOKEN_LIMIT
        tokens_used = user_credit.total_tokens_used
        usage_percentage = min((tokens_used / total_limit * 100), 100) if total_limit > 0 else 0
        monthly_usage_percentage = 0
        additional_credits_usage_percentage = 0
        total_additional_credits_purchased = 0
        additional_credits_consumed = 0
    else:
        # Pro tier calculations
        monthly_limit = PRO_MONTHLY_TOKEN_LIMIT
        additional_credits_remaining = max(0, user_credit.credits)
        total_limit = monthly_limit + additional_credits_remaining

        # For "Used" display: Show actual tokens consumed (from paid_tokens_used)
        tokens_used = user_credit.paid_tokens_used

        # Calculate monthly usage based on paid tokens (fallback when monthly_tokens_used isn't tracked)
        monthly_tokens_consumed = min(tokens_used, monthly_limit)
        monthly_usage_percentage = min((monthly_tokens_consumed / monthly_limit * 100), 100) if monthly_limit > 0 else 0

        usage_percentage = monthly_usage_percentage

        # Calculate additional credits usage percentage
        # Additional credits start being consumed after the monthly limit is reached
        additional_credits_consumed = max(0, tokens_used - monthly_limit)
        total_additional_credits_purchased = additional_credits_consumed + additional_credits_remaining
        if total_additional_credits_purchased > 0:
            additional_credits_usage_percentage = (additional_credits_consumed / total_additional_credits_purchased * 100)
        else:
            additional_credits_usage_percentage = 0

    # Calculate free tokens remaining for Pro tier display
    free_tokens_remaining = 0
    if not user_credit.is_free_tier:
        free_tokens_remaining = max(0, FREE_TIER_TOKEN_LIMIT - user_credit.free_tokens_used)
    
    # Get subscription data for subscriptions section
    from subscriptions.models import PaymentPlan, Transaction
    import os
    payment_plans = PaymentPlan.objects.filter(is_active=True)
    additional_credits_plan = PaymentPlan.objects.filter(name='Additional Credits', is_active=True).first()
    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')[:5]
    stripe_public_key = os.environ.get('STRIPE_PUBLIC_KEY', '')
    
    context = {
        'github_connected': github_connected,
        'github_username': github_username,
        'github_avatar': github_avatar,
        'github_auth_url': github_auth_url,
        'github_missing_config': github_missing_config,
        'openai_connected': openai_connected,
        'anthropic_connected': anthropic_connected,
        'xai_connected': xai_connected,
        'google_connected': google_connected,
        'byok_enabled': personal_llm_keys_enabled,
        'linear_connected': linear_connected,
        'notion_connected': notion_connected,
        'current_org_role': current_org_role,
        # Project collaboration setting
        'allow_project_invitations': request.user.profile.allow_project_invitations,
        # Token usage data
        'user_credit': user_credit,
        'tokens_used': tokens_used,
        'tokens_remaining': user_credit.get_remaining_tokens(),
        'total_limit': total_limit,
        'usage_percentage': round(usage_percentage, 1),
        'is_free_tier': user_credit.is_free_tier,
        'subscription_tier': user_credit.subscription_tier,
        'has_paid_subscription': has_paid_subscription,
        'free_tokens_used': user_credit.free_tokens_used,
        'paid_tokens_used': user_credit.paid_tokens_used,
        'free_tokens_remaining': free_tokens_remaining,
        # Subscription data
        'payment_plans': payment_plans,
        'additional_credits_plan': additional_credits_plan,
        'transactions': transactions,
        'STRIPE_PUBLIC_KEY': stripe_public_key,
        'monthly_usage_percentage': round(monthly_usage_percentage, 1),
        'additional_credits_usage_percentage': round(additional_credits_usage_percentage, 1) if not user_credit.is_free_tier else 0,
        'total_additional_credits_purchased': total_additional_credits_purchased if not user_credit.is_free_tier else 0,
        'additional_credits_consumed': additional_credits_consumed,
        'free_tier_token_limit': FREE_TIER_TOKEN_LIMIT,
        'pro_monthly_token_limit': PRO_MONTHLY_TOKEN_LIMIT,
    }
    
    return render(request, 'accounts/settings_new.html', context)


def send_verification_email(request, user):
    """Send email verification code to user"""
    try:
        from .models import EmailVerificationCode
        
        # Create verification code
        verification = EmailVerificationCode.create_code(user)
        
        # Email content
        subject = 'Your LFG Verification Code'
        
        # Check if template exists, if not use plain text
        try:
            html_message = render_to_string('accounts/email_verification_code.html', {
                'user': user,
                'code': verification.code,
                'expiration_minutes': 30,
            })
        except:
            html_message = None
            
        plain_message = f"""
Hi {user.username},

Your verification code is: {verification.code}

This code will expire in 30 minutes.

Best regards,
The LFG Team
"""
        
        # Send email
        result = send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        return result > 0
        
    except Exception as e:
        logger.error(f"Error sending verification email: {e}", extra={'easylogs_metadata': {'user_email': user.email, 'error_type': type(e).__name__}})
        return False


@login_required
def email_verification_required(request):
    """Show email verification required page"""
    user = request.user
    profile = user.profile

    # Check if already verified - redirect to chat page
    if profile.email_verified:
        return redirect('index')

    context = {
        'email': user.email,
    }
    return render(request, 'accounts/email_verification_required.html', context)


@login_required
def resend_verification_email(request):
    """Resend verification email"""
    if request.method == 'POST':
        user = request.user
        
        # Check if already verified
        if user.profile.email_verified:
            messages.info(request, 'Your email is already verified.')
            return redirect('projects:project_list')
        
        # Send new verification email
        if send_verification_email(request, user):
            messages.success(request, 'Verification email sent! Please check your inbox.')
        else:
            messages.error(request, 'Failed to send verification email. Please try again later.')
        
        return redirect('accounts:email_verification_required')
    
    return redirect('accounts:email_verification_required')


def verify_email(request, token):
    """Verify email with token"""
    try:
        # Find the token
        verification_token = EmailVerificationToken.objects.get(token=token)

        # Check if token is valid
        if not verification_token.is_valid():
            messages.error(request, 'This verification link has expired or been used already.')
            return redirect('login')

        # Mark email as verified
        user = verification_token.user
        profile = user.profile
        profile.email_verified = True
        profile.save()

        # Mark token as used
        verification_token.used = True
        verification_token.save()

        messages.success(request, 'Your email has been verified successfully!')

        # If user is logged in, redirect to chat page
        if request.user.is_authenticated:
            return redirect('index')
        else:
            return redirect('login')

    except EmailVerificationToken.DoesNotExist:
        messages.error(request, 'Invalid verification link.')
        return redirect('login')


def send_password_reset_email(request, user):
    """Send password reset email - similar to send_verification_email"""
    try:
        # Generate token and uid for password reset
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
        # Build password reset URL
        reset_url = request.build_absolute_uri(
            reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
        )
        
        # Email content
        subject = 'Reset your password for LFG'
        html_message = render_to_string('accounts/password_reset_email.html', {
            'user': user,
            'reset_url': reset_url,
            'protocol': 'https' if request.is_secure() else 'http',
            'domain': request.get_host(),
            'uid': uid,
            'token': token,
        })
        plain_message = strip_tags(html_message)
        
        # Send email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        logger.error(f"Error sending password reset email: {e}", extra={'easylogs_metadata': {'user_email': user.email, 'error_type': type(e).__name__}})
        return False


def password_reset(request):
    """Custom password reset view"""
    if request.method == 'POST':
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            # Find users with this email
            users = User.objects.filter(email__iexact=email, is_active=True)
            
            # Send reset email to each user
            email_sent = False
            for user in users:
                if user.has_usable_password():
                    if send_password_reset_email(request, user):
                        email_sent = True
            
            # Always redirect to done page (don't reveal if email exists)
            return redirect('accounts:password_reset_done')
    else:
        form = PasswordResetForm()
    
    return render(request, 'accounts/password_reset.html', {'form': form})


def google_login(request):
    """Initiate Google OAuth flow"""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        messages.error(request, 'Google OAuth is not configured. Please contact the administrator.')
        return redirect('accounts:auth')
    
    # Build redirect URI
    global GOOGLE_REDIRECT_URI
    GOOGLE_REDIRECT_URI = build_secure_absolute_uri(request, reverse('accounts:google_callback'))
    
    # Generate state for CSRF protection
    state = str(uuid.uuid4())
    request.session['google_oauth_state'] = state
    
    # Check if this is from the landing page onboarding flow
    from_landing = request.GET.get('from_landing', False)
    if from_landing:
        request.session['from_landing_onboarding'] = True
    
    # Build Google OAuth URL
    params = {
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'access_type': 'online',
        'prompt': 'select_account'
    }
    
    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    
    return redirect(google_auth_url)


def google_callback(request):
    """Handle Google OAuth callback"""
    code = request.GET.get('code')
    state = request.GET.get('state')
    stored_state = request.session.get('google_oauth_state')
    
    # Validate state to prevent CSRF
    if not state or state != stored_state:
        messages.error(request, 'Invalid OAuth state. Please try connecting to Google again.')
        return redirect('accounts:auth')
    
    if not code:
        messages.error(request, 'No authorization code received from Google.')
        return redirect('accounts:auth')
    
    # Exchange code for access token
    token_url = 'https://oauth2.googleapis.com/token'
    token_data = {
        'code': code,
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'redirect_uri': GOOGLE_REDIRECT_URI,
        'grant_type': 'authorization_code'
    }
    
    try:
        response = requests.post(token_url, data=token_data)
        response.raise_for_status()
        token_response = response.json()
        
        if 'error' in token_response:
            messages.error(request, f"Google authentication error: {token_response.get('error_description', 'Unknown error')}")
            return redirect('accounts:auth')
        
        access_token = token_response.get('access_token')
        
        if not access_token:
            messages.error(request, 'Failed to get access token from Google.')
            return redirect('accounts:auth')
        
        # Get user info from Google
        userinfo_url = 'https://www.googleapis.com/oauth2/v2/userinfo'
        headers = {'Authorization': f'Bearer {access_token}'}
        
        userinfo_response = requests.get(userinfo_url, headers=headers)
        userinfo_response.raise_for_status()
        user_data = userinfo_response.json()
        
        # Get or create user
        email = user_data.get('email')
        if not email:
            messages.error(request, 'Could not retrieve email from Google.')
            return redirect('accounts:auth')
        
        # Check if user exists
        is_new_user = False
        try:
            user = User.objects.get(email=email)
            # If user exists, log them in
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        except User.DoesNotExist:
            # Create new user
            is_new_user = True
            username = email.split('@')[0]
            # Ensure unique username
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1
            
            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=user_data.get('given_name', ''),
                last_name=user_data.get('family_name', '')
            )
            
            # Mark email as verified since it comes from Google
            profile = user.profile
            profile.email_verified = True
            profile.save()
            
            # Log the user in
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, 'Successfully registered and logged in with Google!')
        
        # Check if this was from the landing page onboarding flow
        from_landing_onboarding = request.session.pop('from_landing_onboarding', False)

        if from_landing_onboarding:
            # Redirect back to landing page with a flag to continue onboarding at step 3
            return redirect('/?onboarding=true&step=3')

        # Redirect to chat page
        return redirect('index')
        
    except requests.exceptions.RequestException as e:
        messages.error(request, f'Error communicating with Google: {str(e)}')
        return redirect('accounts:auth')
    except Exception as e:
        messages.error(request, f'An unexpected error occurred: {str(e)}')
        return redirect('accounts:auth')


# API Endpoints
def auth_status(request):
    """Check if user is authenticated"""
    return JsonResponse({
        'authenticated': request.user.is_authenticated,
        'username': request.user.username if request.user.is_authenticated else None,
        'email_verified': request.user.profile.email_verified if request.user.is_authenticated else False
    })


def api_keys_status(request):
    """Check if user has API keys configured"""
    if not request.user.is_authenticated:
        return JsonResponse({
            'error': 'Not authenticated',
            'has_openai_key': False,
            'has_anthropic_key': False,
            'has_xai_key': False,
            'has_google_key': False
        }, status=401)
    
    try:
        llm_keys = LLMApiKeys.objects.get(user=request.user)
        return JsonResponse({
            'has_openai_key': bool(llm_keys.openai_api_key),
            'has_anthropic_key': bool(llm_keys.anthropic_api_key),
            'has_xai_key': bool(llm_keys.xai_api_key),
            'has_google_key': bool(llm_keys.google_api_key)
        })
    except LLMApiKeys.DoesNotExist:
        return JsonResponse({
            'has_openai_key': False,
            'has_anthropic_key': False,
            'has_xai_key': False,
            'has_google_key': False
        })


@login_required
def save_api_keys(request):
    """Save API keys via AJAX"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        import json
        data = json.loads(request.body)
        
        # Get or create LLMApiKeys for user
        llm_keys, created = LLMApiKeys.objects.get_or_create(user=request.user)
        
        # Update API keys if provided
        if 'openai_api_key' in data and data['openai_api_key']:
            llm_keys.openai_api_key = data['openai_api_key']
        
        if 'anthropic_api_key' in data and data['anthropic_api_key']:
            llm_keys.anthropic_api_key = data['anthropic_api_key']
        
        if 'xai_api_key' in data and data['xai_api_key']:
            llm_keys.xai_api_key = data['xai_api_key']
        
        if 'google_api_key' in data and data['google_api_key']:
            llm_keys.google_api_key = data['google_api_key']
        
        llm_keys.save()
        
        return JsonResponse({
            'success': True,
            'has_openai_key': bool(llm_keys.openai_api_key),
            'has_anthropic_key': bool(llm_keys.anthropic_api_key),
            'has_xai_key': bool(llm_keys.xai_api_key),
            'has_google_key': bool(llm_keys.google_api_key)
        })
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def verify_email_code(request):
    """Verify email using 6-digit code"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        import json
        from .models import EmailVerificationCode
        
        data = json.loads(request.body)
        code = data.get('code', '').strip()
        
        if not code or len(code) != 6:
            return JsonResponse({'error': 'Invalid code format'}, status=400)
        
        # Find valid code for the user
        verification = EmailVerificationCode.objects.filter(
            user=request.user,
            code=code,
            used=False
        ).first()
        
        if not verification:
            return JsonResponse({'error': 'Invalid code'}, status=400)
        
        if not verification.is_valid():
            return JsonResponse({'error': 'Code has expired'}, status=400)
        
        # Mark code as used and verify email
        verification.used = True
        verification.save()
        
        profile = request.user.profile
        profile.email_verified = True
        profile.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Email verified successfully'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def resend_verification_code(request):
    """Resend email verification code"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        from .models import EmailVerificationCode
        from django.core.mail import send_mail
        from django.conf import settings
        
        # Create new code
        verification = EmailVerificationCode.create_code(request.user)
        
        # Send email with code
        subject = 'Your LFG Verification Code'
        message = f"""
Hi {request.user.username},

Your verification code is: {verification.code}

This code will expire in 30 minutes.

Best regards,
The LFG Team
"""
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [request.user.email],
            fail_silently=False,
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Verification code sent'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def get_agent_settings(request):
    """Get the user's agent role settings including turbo mode state"""
    try:
        agent_role, created = AgentRole.objects.get_or_create(
            user=request.user,
            defaults={'name': 'product_analyst', 'turbo_mode': False}
        )

        return JsonResponse({
            'agent_role': agent_role.name,
            'turbo_mode': agent_role.turbo_mode
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# Organization Views

@login_required
def create_organization(request):
    """Create a new organization"""
    if request.method == 'POST':
        form = OrganizationCreationForm(request.POST, request.FILES)
        if form.is_valid():
            organization = form.save(commit=False)
            organization.owner = request.user
            organization.save()
            
            # Create organization credit instance
            OrganizationCredit.objects.get_or_create(organization=organization)
            
            messages.success(request, f'Organization "{organization.name}" created successfully!')
            return redirect('accounts:organization_dashboard', slug=organization.slug)
    else:
        form = OrganizationCreationForm()
    
    context = {
        'form': form,
        'page_title': 'Create Organization',
        'form_action': 'Create Organization'
    }
    return render(request, 'accounts/organization_form.html', context)


@login_required
def organization_dashboard(request, slug):
    """Organization dashboard showing members, billing, and settings"""
    organization = get_object_or_404(Organization, slug=slug)
    
    # Check if user is a member
    if not organization.is_member(request.user):
        raise PermissionDenied("You are not a member of this organization.")
    
    # Get user's role in the organization
    user_role = organization.get_user_role(request.user)
    
    # Get organization credit info
    org_credit, created = OrganizationCredit.objects.get_or_create(organization=organization)
    if created:
        # Update seat count on first access
        org_credit.update_seat_count()
    
    # Get members and invitations
    memberships = organization.memberships.filter(status='active').select_related('user')
    pending_invitations = organization.invitations.filter(status='pending').order_by('-created_at')
    recent_transactions = organization.transactions.all()[:5]
    
    # Calculate usage statistics
    if org_credit.is_free_tier:
        total_limit = FREE_TIER_TOKEN_LIMIT
        tokens_used = org_credit.total_tokens_used
        usage_percentage = min((tokens_used / total_limit * 100), 100) if total_limit > 0 else 0
    else:
        total_limit = PRO_MONTHLY_TOKEN_LIMIT * org_credit.seat_count
        tokens_used = org_credit.monthly_tokens_used
        usage_percentage = min((tokens_used / total_limit * 100), 100) if total_limit > 0 else 0
    
    context = {
        'organization': organization,
        'user_role': user_role,
        'org_credit': org_credit,
        'memberships': memberships,
        'pending_invitations': pending_invitations,
        'recent_transactions': recent_transactions,
        'can_manage_members': user_role in ['owner', 'admin'],
        'can_manage_billing': user_role == 'owner',
        'can_invite_members': (
            user_role in ['owner', 'admin'] or 
            (user_role == 'member' and organization.allow_member_invites)
        ),
        'tokens_used': tokens_used,
        'tokens_remaining': org_credit.get_remaining_tokens(),
        'total_limit': total_limit,
        'usage_percentage': round(usage_percentage, 1),
        'is_free_tier': org_credit.is_free_tier,
        'monthly_cost': org_credit.monthly_seat_cost,
    }
    
    return render(request, 'accounts/organization_dashboard.html', context)


@login_required
def organization_settings(request, slug):
    """Organization settings page"""
    organization = get_object_or_404(Organization, slug=slug)
    
    # Check if user can manage organization settings
    user_role = organization.get_user_role(request.user)
    if user_role not in ['owner', 'admin']:
        raise PermissionDenied("You don't have permission to manage organization settings.")
    
    if request.method == 'POST':
        form = OrganizationUpdateForm(request.POST, request.FILES, instance=organization)
        if form.is_valid():
            form.save()
            messages.success(request, 'Organization settings updated successfully!')
            return redirect('accounts:organization_dashboard', slug=organization.slug)
    else:
        form = OrganizationUpdateForm(instance=organization)
    
    context = {
        'form': form,
        'organization': organization,
        'user_role': user_role,
        'page_title': 'Organization Settings',
        'form_action': 'Update Settings'
    }
    
    return render(request, 'accounts/organization_form.html', context)


@login_required
def invite_member(request, slug):
    """Invite new member to organization"""
    organization = get_object_or_404(Organization, slug=slug)
    
    # Check if user can invite members
    user_role = organization.get_user_role(request.user)
    can_invite = (
        user_role in ['owner', 'admin'] or 
        (user_role == 'member' and organization.allow_member_invites)
    )
    
    if not can_invite:
        raise PermissionDenied("You don't have permission to invite members.")
    
    if request.method == 'POST':
        form = OrganizationInvitationForm(
            request.POST, 
            organization=organization, 
            inviter=request.user
        )
        if form.is_valid():
            email = form.cleaned_data['email']
            role = form.cleaned_data['role']
            message = form.cleaned_data['message']
            
            # Create invitation
            invitation = OrganizationInvitation.create_invitation(
                organization=organization,
                inviter=request.user,
                email=email,
                role=role
            )
            
            # Send invitation email
            send_invitation_email(request, invitation, message)
            
            messages.success(request, f'Invitation sent to {email}!')
            return redirect('accounts:organization_dashboard', slug=organization.slug)
    else:
        form = OrganizationInvitationForm(
            organization=organization, 
            inviter=request.user
        )
    
    context = {
        'form': form,
        'organization': organization,
        'user_role': user_role,
        'page_title': 'Invite Member',
        'form_action': 'Send Invitation'
    }
    
    return render(request, 'accounts/invite_member.html', context)


def accept_invitation(request, token):
    """Accept organization invitation"""
    try:
        invitation = OrganizationInvitation.objects.get(token=token)
        
        if not invitation.is_valid():
            messages.error(request, 'This invitation has expired or is no longer valid.')
            return redirect('accounts:auth')
        
        # If user is not logged in, redirect to login with invitation token
        if not request.user.is_authenticated:
            return redirect(f'/auth/?invitation_token={token}')
        
        # Check if user's email matches invitation
        if request.user.email.lower() != invitation.email.lower():
            messages.error(request, 'Your email does not match the invitation email.')
            return redirect('accounts:auth')
        
        # Accept the invitation
        try:
            membership = invitation.accept(request.user)
            
            # Update organization seat count and credits
            org_credit, created = OrganizationCredit.objects.get_or_create(
                organization=invitation.organization
            )
            org_credit.update_seat_count()
            
            messages.success(request, f'Successfully joined {invitation.organization.name}!')
            return redirect('accounts:organization_dashboard', slug=invitation.organization.slug)
            
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('accounts:auth')
        
    except OrganizationInvitation.DoesNotExist:
        messages.error(request, 'Invalid invitation link.')
        return redirect('accounts:auth')


@login_required
def remove_member(request, slug, user_id):
    """Remove member from organization"""
    organization = get_object_or_404(Organization, slug=slug)
    member_user = get_object_or_404(User, id=user_id)
    
    # Check permissions
    user_role = organization.get_user_role(request.user)
    if user_role not in ['owner', 'admin']:
        raise PermissionDenied("You don't have permission to remove members.")
    
    # Get the membership
    try:
        membership = OrganizationMembership.objects.get(
            organization=organization, 
            user=member_user, 
            status='active'
        )
    except OrganizationMembership.DoesNotExist:
        messages.error(request, 'User is not a member of this organization.')
        return redirect('accounts:organization_dashboard', slug=slug)
    
    # Prevent removing the owner
    if membership.role == 'owner':
        messages.error(request, 'Cannot remove the organization owner.')
        return redirect('accounts:organization_dashboard', slug=slug)
    
    # Prevent non-owners from removing admins
    if user_role == 'admin' and membership.role == 'admin':
        messages.error(request, 'Admins cannot remove other admins.')
        return redirect('accounts:organization_dashboard', slug=slug)
    
    if request.method == 'POST':
        # Remove the member
        membership.status = 'inactive'
        membership.save()
        
        # Update seat count
        org_credit, created = OrganizationCredit.objects.get_or_create(organization=organization)
        org_credit.update_seat_count()
        
        # Clear current organization if user was using it
        if member_user.profile.current_organization == organization:
            member_user.profile.current_organization = None
            member_user.profile.save()
        
        messages.success(request, f'{member_user.email} has been removed from the organization.')
    
    return redirect('accounts:organization_dashboard', slug=slug)


@login_required
def update_member_role(request, slug, user_id):
    """Update member role in organization"""
    organization = get_object_or_404(Organization, slug=slug)
    member_user = get_object_or_404(User, id=user_id)
    
    # Check permissions - only owners can change roles
    user_role = organization.get_user_role(request.user)
    if user_role != 'owner':
        raise PermissionDenied("Only organization owners can change member roles.")
    
    try:
        membership = OrganizationMembership.objects.get(
            organization=organization,
            user=member_user,
            status='active'
        )
    except OrganizationMembership.DoesNotExist:
        messages.error(request, 'User is not a member of this organization.')
        return redirect('accounts:organization_dashboard', slug=slug)
    
    if request.method == 'POST':
        form = MembershipUpdateForm(request.POST, instance=membership, current_user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f'Role updated for {member_user.email}.')
            return redirect('accounts:organization_dashboard', slug=slug)
    
    return redirect('accounts:organization_dashboard', slug=slug)


@login_required
def switch_organization(request):
    """Switch organization context"""
    if request.method == 'POST':
        form = OrganizationSwitchForm(request.POST, user=request.user)
        if form.is_valid():
            organization = form.cleaned_data['organization']
            current_org = request.user.profile.current_organization
            
            # Only show message if actually switching
            if organization != current_org:
                # Switch to the selected organization
                request.user.profile.switch_organization(organization)
                
                if organization:
                    messages.success(request, f'Switched to {organization.name}.')
                else:
                    messages.success(request, 'Switched to personal space.')
            
            # Redirect to the page they came from or dashboard
            next_url = request.POST.get('next') or request.META.get('HTTP_REFERER')
            if next_url:
                return redirect(next_url)
            return redirect('projects:project_list')
    
    return redirect('projects:project_list')


@login_required
def organization_list(request):
    """List user's organizations"""
    # Get organizations where user is a member
    organizations = Organization.objects.filter(
        memberships__user=request.user,
        memberships__status='active',
        is_active=True
    ).select_related().order_by('name')
    
    # Add role and member count to each organization
    org_data = []
    for org in organizations:
        org_data.append({
            'organization': org,
            'role': org.get_user_role(request.user),
            'member_count': org.member_count,
            'is_current': request.user.profile.current_organization == org
        })
    
    context = {
        'organizations': org_data,
        'current_organization': request.user.profile.current_organization,
    }
    
    return render(request, 'accounts/organization_list.html', context)


def send_invitation_email(request, invitation, custom_message=""):
    """Send invitation email to new member"""
    try:
        # Build invitation URL
        invitation_url = request.build_absolute_uri(
            reverse('accounts:accept_invitation', kwargs={'token': invitation.token})
        )
        
        # Email content
        subject = f'You\'re invited to join {invitation.organization.name} on LFG'
        
        context = {
            'invitation': invitation,
            'invitation_url': invitation_url,
            'custom_message': custom_message,
            'inviter_name': invitation.inviter.get_full_name() or invitation.inviter.username,
        }
        
        try:
            html_message = render_to_string('accounts/invitation_email.html', context)
        except:
            html_message = None
        
        plain_message = f"""
Hi!

{invitation.inviter.get_full_name() or invitation.inviter.username} has invited you to join {invitation.organization.name} on LFG as a {invitation.get_role_display()}.

{custom_message if custom_message else ''}

Click here to accept the invitation:
{invitation_url}

This invitation will expire in 7 days.

Best regards,
The LFG Team
"""
        
        # Send email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invitation.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Error sending invitation email: {e}", extra={
            'easylogs_metadata': {
                'invitation_id': invitation.id,
                'email': invitation.email,
                'error_type': type(e).__name__
            }
        })
        return False


@login_required
def github_status(request):
    """Check if user has GitHub connected"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        github_token = GitHubToken.objects.get(user=request.user)
        
        # Test token by making a simple API call
        test_response = requests.get(
            'https://api.github.com/user',
            headers={
                'Authorization': f'token {github_token.access_token}',
                'Accept': 'application/vnd.github.v3+json'
            },
            timeout=5
        )
        
        token_valid = test_response.status_code == 200
        token_scopes = test_response.headers.get('X-OAuth-Scopes', '') if token_valid else ''
        
        return JsonResponse({
            'connected': True,
            'username': github_token.github_username,
            'avatar': github_token.github_avatar_url,
            'token_valid': token_valid,
            'scopes': token_scopes,
            'scope_list': token_scopes.split(', ') if token_scopes else []
        })
    except GitHubToken.DoesNotExist:
        return JsonResponse({
            'connected': False
        })
    except Exception as e:
        return JsonResponse({
            'connected': True,
            'error': f'Error checking token: {str(e)}'
        })


@login_required
def github_oauth_url(request):
    """Get GitHub OAuth URL for linking projects"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    # Check if already connected
    try:
        github_token = GitHubToken.objects.get(user=request.user)
        return JsonResponse({
            'connected': True,
            'username': github_token.github_username
        })
    except GitHubToken.DoesNotExist:
        pass
    
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        return JsonResponse({
            'error': 'GitHub OAuth is not configured'
        }, status=500)
    
    # Build redirect URI
    global GITHUB_REDIRECT_URI
    GITHUB_REDIRECT_URI = build_secure_absolute_uri(request, reverse('accounts:github_callback'))
    
    # Generate state for CSRF protection
    state = str(uuid.uuid4())
    request.session['github_oauth_state'] = state
    
    # Build GitHub OAuth URL
    params = {
        'client_id': GITHUB_CLIENT_ID,
        'redirect_uri': GITHUB_REDIRECT_URI,
        'scope': 'repo user',
        'state': state,
    }
    
    github_auth_url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"
    
    return JsonResponse({
        'connected': False,
        'auth_url': github_auth_url
    })


@login_required
def update_project_collaboration_setting(request):
    """Update user's project collaboration setting"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        import json
        data = json.loads(request.body)
        allow_project_invitations = data.get('allow_project_invitations', True)
        
        # Update the user's profile setting
        profile = request.user.profile
        profile.allow_project_invitations = bool(allow_project_invitations)
        profile.save(update_fields=['allow_project_invitations'])
        
        logger.info(f"Updated project collaboration setting for user {request.user.username}: {allow_project_invitations}")
        
        return JsonResponse({
            'success': True,
            'allow_project_invitations': profile.allow_project_invitations,
            'message': 'Project collaboration setting updated successfully'
        })
        
    except Exception as e:
        logger.error(f"Error updating project collaboration setting: {e}", extra={
            'easylogs_metadata': {
                'user_id': request.user.id,
                'error_type': type(e).__name__
            }
        })
        return JsonResponse({'error': 'Failed to update setting'}, status=500)
