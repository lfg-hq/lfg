from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.contrib.auth import authenticate, login
from django.conf import settings
from .forms import UserRegisterForm, UserUpdateForm, ProfileUpdateForm, EmailAuthenticationForm, PasswordResetForm
from django.contrib.auth.models import User
from .models import GitHubToken, EmailVerificationToken
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
            return redirect('email_verification_required')
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
                    return redirect('email_verification_required')
                
                login(request, user)
                
                # Check if user has required API keys set up
                openai_key_missing = not bool(profile.openai_api_key)
                anthropic_key_missing = not bool(profile.anthropic_api_key)
                
                # If both OpenAI and Anthropic keys are missing, redirect to integrations
                if openai_key_missing and anthropic_key_missing:
                    messages.success(request, 'Please set up OpenAI or Anthropic API keys to get started.')
                    return redirect('integrations')
                
                # Redirect to the chat page or next parameter if provided
                next_url = request.GET.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('projects:project_list')  # Changed from projects:project_list to project_list
        
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
                return redirect('email_verification_required')
    
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
def settings_page(request, show_github=False):
    # Get GitHub connection status
    github_connected = False
    github_username = None
    github_avatar = None
    github_missing_config = not hasattr(settings, 'GITHUB_CLIENT_ID') or not settings.GITHUB_CLIENT_ID
    
    try:
        github_social = request.user.social_auth.get(provider='github')
        github_connected = True
        extra_data = github_social.extra_data
        github_username = extra_data.get('login')
        github_avatar = extra_data.get('avatar_url')
    except:
        pass
    
    # Create GitHub redirect URI if not connected
    github_auth_url = None
    if (not github_connected and not github_missing_config) or show_github:
        GITHUB_CLIENT_ID = settings.GITHUB_CLIENT_ID
        GITHUB_REDIRECT_URI = request.build_absolute_uri(reverse('github_callback'))
        state = str(uuid.uuid4())
        request.session['github_oauth_state'] = state
        params = {
            'client_id': GITHUB_CLIENT_ID,
            'redirect_uri': GITHUB_REDIRECT_URI,
            'scope': 'repo user',
            'state': state,
        }
        github_auth_url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"
        
        # If show_github is True, redirect directly to GitHub OAuth
        if show_github:
            return redirect(github_auth_url)
    
    # Handle GitHub disconnect
    if request.method == 'POST' and request.POST.get('action') == 'github_disconnect':
        if github_connected:
            try:
                github_social.delete()
                messages.success(request, 'GitHub connection removed successfully.')
                return redirect('settings_page')
            except Exception as e:
                messages.error(request, f'Error disconnecting GitHub: {str(e)}')
    
    # Get API keys status
    openai_connected = bool(request.user.profile.openai_api_key)
    anthropic_connected = bool(request.user.profile.anthropic_api_key)
    groq_connected = bool(request.user.profile.groq_api_key)
    
    # Check for URL parameters that might indicate which form to show
    openai_api_form_visible = request.GET.get('show') == 'openai'
    anthropic_api_form_visible = request.GET.get('show') == 'anthropic'
    groq_api_form_visible = request.GET.get('show') == 'groq'
    
    context = {
        'github_connected': github_connected,
        'github_username': github_username,
        'github_avatar': github_avatar,
        'github_auth_url': github_auth_url,
        'github_missing_config': github_missing_config,
        'openai_connected': openai_connected,
        'anthropic_connected': anthropic_connected,
        'groq_connected': groq_connected,
        'openai_api_form_visible': openai_api_form_visible,
        'anthropic_api_form_visible': anthropic_api_form_visible,
        'groq_api_form_visible': groq_api_form_visible,
    }
    
    return render(request, 'accounts/settings.html', context)

@login_required
def save_api_key(request, provider):
    """Handle saving API keys for various providers"""
    if request.method != 'POST':
        messages.error(request, 'Invalid request')
        return redirect('integrations')
    
    api_key = request.POST.get('api_key', '').strip()
    if not api_key:
        messages.error(request, 'API key cannot be empty')
        return redirect('integrations')
    
    # Get user profile
    profile = request.user.profile
    
    # Update the appropriate API key based on provider
    if provider == 'openai':
        profile.openai_api_key = api_key
    elif provider == 'anthropic':
        profile.anthropic_api_key = api_key
    elif provider == 'groq':
        profile.groq_api_key = api_key
    elif provider == 'linear':
        profile.linear_api_key = api_key
    else:
        messages.error(request, 'Invalid provider')
        return redirect('integrations')
    
    # Save the profile
    profile.save()
    
    messages.success(request, f'{provider.capitalize()} API key saved successfully.')
    return redirect('integrations')

@login_required
def disconnect_api_key(request, provider):
    """Handle disconnecting API keys for various providers"""
    if request.method != 'POST':
        messages.error(request, 'Invalid request')
        return redirect('integrations')
    
    # Get user profile
    profile = request.user.profile
    
    # Update the appropriate API key based on provider
    if provider == 'openai':
        profile.openai_api_key = ''
    elif provider == 'anthropic':
        profile.anthropic_api_key = ''
    elif provider == 'groq':
        profile.groq_api_key = ''
    elif provider == 'linear':
        profile.linear_api_key = ''
    else:
        messages.error(request, 'Invalid provider')
        return redirect('integrations')
    
    # Save the profile
    profile.save()
    
    messages.success(request, f'{provider.capitalize()} connection removed successfully.')
    return redirect('integrations')

@login_required
def user_settings(request):
    """
    User settings page with integrations like GitHub
    """
    # Check if the user already has a GitHub token
    try:
        github_token = GitHubToken.objects.get(user=request.user)
        has_github_token = True
        github_user = github_token.github_username if github_token.github_username else "GitHub User"
        github_avatar = github_token.github_avatar_url
    except GitHubToken.DoesNotExist:
        github_token = None
        has_github_token = False
        github_user = None
        github_avatar = None
    
    # Create GitHub redirect URI
    global GITHUB_REDIRECT_URI
    GITHUB_REDIRECT_URI = request.build_absolute_uri(reverse('github_callback'))
    
    # GitHub OAuth setup
    github_auth_url = None
    if GITHUB_CLIENT_ID:
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
        if has_github_token:
            github_token.delete()
            messages.success(request, 'GitHub connection removed successfully.')
            return redirect('settings')
    
    context = {
        'has_github_token': has_github_token,
        'github_auth_url': github_auth_url,
        'github_user': github_user,
        'github_avatar': github_avatar,
        'github_missing_config': not GITHUB_CLIENT_ID,
    }
    
    return render(request, 'accounts/settings.html', context)

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
        return redirect('integrations')
    
    if not code:
        messages.error(request, 'No authorization code received from GitHub.')
        return redirect('integrations')
    
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
        return redirect('integrations')
    
    # Parse token response
    token_data = response.json()
    if 'error' in token_data:
        messages.error(request, f"GitHub authentication error: {token_data.get('error_description', 'Unknown error')}")
        return redirect('integrations')
    
    access_token = token_data.get('access_token')
    scope = token_data.get('scope', '')
    
    if not access_token:
        messages.error(request, 'Failed to get access token from GitHub.')
        return redirect('integrations')
    
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
        return redirect('integrations')
    
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
    return redirect('integrations')

@login_required
def integrations(request):
    """
    Integrations page for connecting GitHub, OpenAI, Anthropic, and Groq
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
        GITHUB_REDIRECT_URI = request.build_absolute_uri(reverse('github_callback'))
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
                return redirect('integrations')
            except Exception as e:
                messages.error(request, f'Error disconnecting GitHub: {str(e)}')
    
    # Get API keys status
    openai_connected = bool(request.user.profile.openai_api_key)
    anthropic_connected = bool(request.user.profile.anthropic_api_key)
    groq_connected = bool(request.user.profile.groq_api_key)
    linear_connected = bool(request.user.profile.linear_api_key)
    
    context = {
        'github_connected': github_connected,
        'github_username': github_username,
        'github_avatar': github_avatar,
        'github_auth_url': github_auth_url,
        'github_missing_config': github_missing_config,
        'openai_connected': openai_connected,
        'anthropic_connected': anthropic_connected,
        'groq_connected': groq_connected,
        'linear_connected': linear_connected,
    }
    
    return render(request, 'accounts/integrations.html', context)


def send_verification_email(request, user):
    """Send email verification link to user"""
    try:
        # Create verification token
        token = EmailVerificationToken.create_token(user)
        
        # Build verification URL
        verification_url = request.build_absolute_uri(
            reverse('verify_email', kwargs={'token': token.token})
        )
        
        # Email content
        subject = 'Verify your email for LFG'
        html_message = render_to_string('accounts/email_verification.html', {
            'user': user,
            'verification_url': verification_url,
            'expiration_hours': 24,
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
        print(f"Error sending verification email: {e}")
        return False


@login_required
def email_verification_required(request):
    """Show email verification required page"""
    user = request.user
    profile = user.profile
    
    # Check if already verified
    if profile.email_verified:
        # Check if user has required API keys set up
        openai_key_missing = not bool(profile.openai_api_key)
        anthropic_key_missing = not bool(profile.anthropic_api_key)
        
        # If both OpenAI and Anthropic keys are missing, redirect to integrations
        if openai_key_missing and anthropic_key_missing:
            messages.success(request, 'Please set up OpenAI or Anthropic API keys to get started.')
            return redirect('integrations')
        
        return redirect('projects:project_list')
    
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
        
        return redirect('email_verification_required')
    
    return redirect('email_verification_required')


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
        
        # If user is logged in, redirect to appropriate page
        if request.user.is_authenticated:
            # Check if user has required API keys set up
            openai_key_missing = not bool(profile.openai_api_key)
            anthropic_key_missing = not bool(profile.anthropic_api_key)
            
            # If both keys are missing, redirect to integrations
            if openai_key_missing and anthropic_key_missing:
                messages.success(request, 'Please set up OpenAI or Anthropic API keys to get started.')
                return redirect('integrations')
            
            return redirect('projects:project_list')
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
        print(f"Error sending password reset email: {e}")
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
            return redirect('password_reset_done')
    else:
        form = PasswordResetForm()
    
    return render(request, 'accounts/password_reset.html', {'form': form})


def google_login(request):
    """Initiate Google OAuth flow"""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        messages.error(request, 'Google OAuth is not configured. Please contact the administrator.')
        return redirect('auth')
    
    # Build redirect URI
    global GOOGLE_REDIRECT_URI
    GOOGLE_REDIRECT_URI = request.build_absolute_uri(reverse('google_callback'))
    
    # Generate state for CSRF protection
    state = str(uuid.uuid4())
    request.session['google_oauth_state'] = state
    
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
        return redirect('auth')
    
    if not code:
        messages.error(request, 'No authorization code received from Google.')
        return redirect('auth')
    
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
            return redirect('auth')
        
        access_token = token_response.get('access_token')
        
        if not access_token:
            messages.error(request, 'Failed to get access token from Google.')
            return redirect('auth')
        
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
            return redirect('auth')
        
        # Check if user exists
        try:
            user = User.objects.get(email=email)
            # If user exists, log them in
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, 'Successfully logged in with Google!')
        except User.DoesNotExist:
            # Create new user
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
        
        # Check if user has required API keys set up
        openai_key_missing = not bool(user.profile.openai_api_key)
        anthropic_key_missing = not bool(user.profile.anthropic_api_key)
        
        # If both keys are missing, redirect to integrations
        if openai_key_missing and anthropic_key_missing:
            messages.info(request, 'Please set up OpenAI or Anthropic API keys to get started.')
            return redirect('integrations')
        
        # Redirect to projects list
        return redirect('projects:project_list')
        
    except requests.exceptions.RequestException as e:
        messages.error(request, f'Error communicating with Google: {str(e)}')
        return redirect('auth')
    except Exception as e:
        messages.error(request, f'An unexpected error occurred: {str(e)}')
        return redirect('auth') 