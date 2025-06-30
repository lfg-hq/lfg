from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.contrib.auth import authenticate, login
from django.conf import settings
from .forms import UserRegisterForm, UserUpdateForm, ProfileUpdateForm, EmailAuthenticationForm
from django.contrib.auth.models import User
from .models import GitHubToken
import requests
import uuid
import json
from urllib.parse import urlencode
from django.http import JsonResponse

# Define GitHub OAuth constants
GITHUB_CLIENT_ID = settings.GITHUB_CLIENT_ID if hasattr(settings, 'GITHUB_CLIENT_ID') else None
GITHUB_CLIENT_SECRET = settings.GITHUB_CLIENT_SECRET if hasattr(settings, 'GITHUB_CLIENT_SECRET') else None
GITHUB_REDIRECT_URI = None  # Will be set dynamically

def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            email = form.cleaned_data.get('email')
            messages.success(request, f'Account created for {email}! You can now log in.')
            return redirect('login')
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
                
                # Check if email is verified
                profile = user.profile
                if not profile.email_verified:
                    messages.error(request, 'Please verify your email address before logging in. Check your inbox for the verification email.')
                    return render(request, 'accounts/auth.html', {
                        'login_form': login_form,
                        'register_form': register_form,
                        'active_tab': 'login'
                    })
                
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
                register_form.save()
                email = register_form.cleaned_data.get('email')
                messages.success(request, f'Account created for {email}! You can now log in.')
                return redirect('login')
    
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
    else:
        messages.error(request, 'Invalid provider')
        return redirect('integrations')
    
    # Save the profile
    profile.save()
    
    messages.success(request, f'{provider.capitalize()} connection removed successfully.')
    return redirect('integrations')

@login_required
def settings(request):
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
    
    context = {
        'github_connected': github_connected,
        'github_username': github_username,
        'github_avatar': github_avatar,
        'github_auth_url': github_auth_url,
        'github_missing_config': github_missing_config,
        'openai_connected': openai_connected,
        'anthropic_connected': anthropic_connected,
        'groq_connected': groq_connected,
    }
    
    return render(request, 'accounts/integrations.html', context) 