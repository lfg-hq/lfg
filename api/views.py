from rest_framework import status, generics, viewsets
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import ValidationError
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from urllib.parse import urlencode, urlparse
import uuid
import requests
from accounts.models import Profile, LLMApiKeys
from chat.models import Conversation, Message
from projects.models import Project, ProjectFile, ProjectChecklist
from subscriptions.models import UserCredit
from .serializers import (
    UserSerializer, ProfileSerializer, RegisterSerializer,
    LLMApiKeysSerializer, ConversationSerializer, MessageSerializer,
    ProjectSerializer, ProjectDocumentSerializer, ProjectChecklistItemSerializer
)
from django.db.models import Count, Q


GOOGLE_AUTH_BASE_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v2/userinfo'
GOOGLE_STATE_CACHE_PREFIX = 'google_oauth_state:'
GOOGLE_STATE_TTL = 300


def _generate_unique_username(email: str) -> str:
    """Generate a unique username based on email."""
    base_username = email.split('@')[0][:30] if email else 'user'
    if not base_username:
        base_username = 'user'
    username = base_username
    counter = 1
    while User.objects.filter(username=username).exists():
        suffix = f"{counter}"
        max_length = 150 - len(suffix)
        username = f"{base_username[:max_length]}{suffix}"
        counter += 1
    return username


def _is_redirect_allowed(redirect_uri: str) -> bool:
    if not redirect_uri:
        return False
    parsed = urlparse(redirect_uri)
    if not parsed.scheme or not parsed.netloc:
        return False
    origin = f"{parsed.scheme}://{parsed.netloc}"
    allowed_origins = set(getattr(settings, 'GOOGLE_ALLOWED_REDIRECTS', []))
    allowed_origins.update(getattr(settings, 'CORS_ALLOWED_ORIGINS', []))
    allowed_origins.update(getattr(settings, 'CSRF_TRUSTED_ORIGINS', []))
    return origin in allowed_origins


# Authentication Views
@csrf_exempt
@api_view(['POST', 'OPTIONS'])
@permission_classes([AllowAny])
def register(request):
    """Register a new user"""
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        return Response({
            'user': UserSerializer(user).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            },
            'message': 'Registration successful'
        }, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@csrf_exempt
@api_view(['POST', 'OPTIONS'])
@permission_classes([AllowAny])
def login(request):
    """Login with email/username and password"""
    email_or_username = request.data.get('email') or request.data.get('username')
    password = request.data.get('password')

    if not email_or_username or not password:
        return Response({
            'error': 'Please provide both email/username and password'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Try to find user by email or username
    user = None
    if '@' in email_or_username:
        # It's an email
        try:
            user = User.objects.get(email=email_or_username)
            user = authenticate(username=user.username, password=password)
        except User.DoesNotExist:
            pass
    else:
        # It's a username
        user = authenticate(username=email_or_username, password=password)

    if user is not None:
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        profile_obj, _ = Profile.objects.get_or_create(user=user)

        return Response({
            'user': UserSerializer(user).data,
            'profile': ProfileSerializer(profile_obj).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            },
            'message': 'Login successful'
        })

    return Response({
        'error': 'Invalid credentials'
    }, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['GET'])
@permission_classes([AllowAny])
def google_auth_url(request):
    """Return Google OAuth authorization URL for client-side flows."""
    client_id = getattr(settings, 'GOOGLE_CLIENT_ID', None)
    client_secret = getattr(settings, 'GOOGLE_CLIENT_SECRET', None)

    if not client_id or not client_secret:
        return Response(
            {'error': 'Google OAuth is not configured.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    redirect_uri = request.query_params.get('redirect_uri')
    if redirect_uri:
        if not _is_redirect_allowed(redirect_uri):
            return Response(
                {'error': 'redirect_uri is not allowed.'},
                status=status.HTTP_400_BAD_REQUEST
            )
    else:
        redirect_uri = request.build_absolute_uri(reverse('accounts:google_callback'))

    state = uuid.uuid4().hex
    cache.set(f"{GOOGLE_STATE_CACHE_PREFIX}{state}", {'redirect_uri': redirect_uri}, GOOGLE_STATE_TTL)

    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'access_type': 'online',
        'prompt': 'select_account'
    }

    authorization_url = f"{GOOGLE_AUTH_BASE_URL}?{urlencode(params)}"
    return Response({'authorization_url': authorization_url, 'state': state})


@api_view(['POST'])
@permission_classes([AllowAny])
def google_auth_exchange(request):
    """Handle exchanging Google OAuth code for application JWT tokens."""
    client_id = getattr(settings, 'GOOGLE_CLIENT_ID', None)
    client_secret = getattr(settings, 'GOOGLE_CLIENT_SECRET', None)

    if not client_id or not client_secret:
        return Response(
            {'error': 'Google OAuth is not configured.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    code = request.data.get('code')
    state = request.data.get('state')
    redirect_uri = request.data.get('redirect_uri')

    if not code or not state or not redirect_uri:
        return Response(
            {'error': 'code, state, and redirect_uri are required.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not _is_redirect_allowed(redirect_uri):
        return Response(
            {'error': 'redirect_uri is not allowed.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    cache_key = f"{GOOGLE_STATE_CACHE_PREFIX}{state}"
    cached_state = cache.get(cache_key)
    cache.delete(cache_key)

    if not cached_state or cached_state.get('redirect_uri') != redirect_uri:
        return Response({'error': 'Invalid or expired OAuth state.'}, status=status.HTTP_400_BAD_REQUEST)

    token_data = {
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code'
    }

    try:
        token_response = requests.post(GOOGLE_TOKEN_URL, data=token_data, timeout=10)
        token_response.raise_for_status()
        token_payload = token_response.json()
    except requests.RequestException as exc:
        return Response({'error': f'Error exchanging code: {str(exc)}'}, status=status.HTTP_400_BAD_REQUEST)

    if 'error' in token_payload:
        return Response({
            'error': token_payload.get('error_description', token_payload['error'])
        }, status=status.HTTP_400_BAD_REQUEST)

    access_token = token_payload.get('access_token')
    if not access_token:
        return Response({'error': 'No access token returned by Google.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        userinfo_response = requests.get(
            GOOGLE_USERINFO_URL,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()
    except requests.RequestException as exc:
        return Response({'error': f'Error fetching user info: {str(exc)}'}, status=status.HTTP_400_BAD_REQUEST)

    email = userinfo.get('email')
    if not email:
        return Response({'error': 'Unable to retrieve email from Google.'}, status=status.HTTP_400_BAD_REQUEST)

    first_name = userinfo.get('given_name', '')
    last_name = userinfo.get('family_name', '')

    user = User.objects.filter(email__iexact=email).first()
    is_new_user = False

    if user is None:
        username = _generate_unique_username(email)
        user = User.objects.create_user(
            username=username,
            email=email,
            password=None,
            first_name=first_name,
            last_name=last_name
        )
        is_new_user = True
    else:
        updated = False
        if first_name and not user.first_name:
            user.first_name = first_name
            updated = True
        if last_name and not user.last_name:
            user.last_name = last_name
            updated = True
        if updated:
            user.save(update_fields=['first_name', 'last_name'])

    profile, _ = Profile.objects.get_or_create(user=user)
    if not profile.email_verified:
        profile.email_verified = True
        profile.save(update_fields=['email_verified'])

    refresh = RefreshToken.for_user(user)

    return Response({
        'user': UserSerializer(user).data,
        'profile': ProfileSerializer(profile).data,
        'tokens': {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        },
        'is_new_user': is_new_user
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    """Logout by blacklisting the refresh token"""
    try:
        refresh_token = request.data.get('refresh_token')
        token = RefreshToken(refresh_token)
        token.blacklist()
        return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)
    except Exception:
        return Response({'error': 'Invalid token'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user(request):
    """Get current user info"""
    profile, _ = Profile.objects.get_or_create(user=request.user)
    return Response({
        'user': UserSerializer(request.user).data,
        'profile': ProfileSerializer(profile).data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def chat_socket_info(request):
    """Provide WebSocket connection info for chat interface."""
    scheme = 'wss' if request.is_secure() else 'ws'
    socket_url = f"{scheme}://{request.get_host()}/ws/chat/"
    return Response({'url': socket_url})


# Profile Views
class ProfileViewSet(viewsets.ModelViewSet):
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Profile.objects.filter(user=self.request.user)

    def get_object(self):
        return self.request.user.profile

    def list(self, request):
        profile = self.get_object()
        serializer = self.get_serializer(profile)
        return Response(serializer.data)

    def update(self, request):
        profile = self.get_object()
        serializer = self.get_serializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# API Keys Views
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_keys(request):
    """Get or update API keys"""
    llm_keys, created = LLMApiKeys.objects.get_or_create(user=request.user)

    if request.method == 'GET':
        serializer = LLMApiKeysSerializer(llm_keys)
        return Response(serializer.data)

    elif request.method == 'POST':
        serializer = LLMApiKeysSerializer(llm_keys, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'API keys updated successfully',
                'data': LLMApiKeysSerializer(llm_keys).data
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Subscription Views
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def subscription_info(request):
    """Get user's subscription and credit info"""
    credit, created = UserCredit.objects.get_or_create(user=request.user)

    subscription_plan = 'Free'
    if credit.subscription_tier == 'pro' and credit.has_active_subscription:
        subscription_plan = 'Pro'
    elif credit.subscription_tier:
        subscription_plan = credit.subscription_tier.replace('_', ' ').title()

    return Response({
        'subscription_plan': subscription_plan,
        'total_tokens_used': credit.total_tokens_used,
        'credits': {
            'balance': credit.credits,
            'lifetime_tokens': credit.total_tokens_used,
            'monthly_tokens': credit.monthly_tokens_used,
        }
    })


# Conversation Views
class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user).select_related('project').annotate(
            message_count=Count('messages', distinct=True)
        ).order_by('-updated_at')

    def perform_create(self, serializer):
        project_id = serializer.validated_data.pop('project_id', None)
        project_obj = None

        if project_id:
            try:
                project_obj = Project.objects.get(project_id=project_id)
            except Project.DoesNotExist:
                raise ValidationError({'project_id': 'Project not found.'})

            if not project_obj.can_user_access(self.request.user):
                raise ValidationError({'project_id': 'You do not have access to this project.'})

        serializer.save(user=self.request.user, project=project_obj)

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """Get all messages for a conversation"""
        conversation = self.get_object()
        messages = conversation.messages.all().order_by('timestamp')
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)


# Message Views
class MessageViewSet(viewsets.ModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        conversation_id = self.request.query_params.get('conversation')
        if conversation_id:
            return Message.objects.filter(
                conversation_id=conversation_id,
                conversation__user=self.request.user
            ).order_by('timestamp')
        return Message.objects.none()

    def perform_create(self, serializer):
        conversation = serializer.validated_data['conversation']
        # Verify the conversation belongs to the user
        if conversation.user != self.request.user:
            raise PermissionError("You don't have permission to add messages to this conversation")
        serializer.save()


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'project_id'
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        accessible_projects = Project.objects.filter(
            Q(owner=user) | Q(members__user=user, members__status='active')
        ).distinct()

        return accessible_projects.select_related('owner', 'indexed_repository').annotate(
            conversations_count=Count('direct_conversations', distinct=True),
            documents_count=Count('files', filter=Q(files__is_active=True), distinct=True),
            tickets_count=Count('checklist', distinct=True),
        ).order_by('-updated_at')

    def perform_create(self, serializer):
        icon = serializer.validated_data.get('icon') or '🚀'
        serializer.save(owner=self.request.user, icon=icon)

    @action(detail=True, methods=['get'])
    def documents(self, request, project_id=None):
        project = self.get_object()
        files = project.files.filter(is_active=True).order_by('-updated_at')
        serializer = ProjectDocumentSerializer(files, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def checklist(self, request, project_id=None):
        project = self.get_object()
        checklist_items = project.checklist.all().order_by('created_at')
        serializer = ProjectChecklistItemSerializer(checklist_items, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def conversations(self, request, project_id=None):
        project = self.get_object()
        conversations = project.direct_conversations.filter(user=request.user).order_by('-updated_at')
        serializer = ConversationSerializer(conversations, many=True)
        return Response(serializer.data)


class ProjectDocumentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProjectDocumentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        accessible_projects = Project.objects.filter(
            Q(owner=user) | Q(members__user=user, members__status='active')
        ).distinct()
        return ProjectFile.objects.filter(
            project__in=accessible_projects,
            is_active=True
        ).select_related('project').order_by('-updated_at')


class ProjectChecklistViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProjectChecklistItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        accessible_projects = Project.objects.filter(
            Q(owner=user) | Q(members__user=user, members__status='active')
        ).distinct()
        return ProjectChecklist.objects.filter(
            project__in=accessible_projects
        ).select_related('project').order_by('created_at')
