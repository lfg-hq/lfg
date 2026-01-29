from rest_framework import status, generics, viewsets
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authentication import SessionAuthentication
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
from projects.models import Project, ProjectFile, ProjectTicket, ProjectTodoList
from subscriptions.models import UserCredit
from .serializers import (
    UserSerializer, ProfileSerializer, RegisterSerializer,
    LLMApiKeysSerializer, ConversationSerializer, MessageSerializer,
    ProjectSerializer, ProjectDocumentSerializer, ProjectTicketSerializer, ProjectTaskSerializer
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
    def tickets(self, request, project_id=None):
        project = self.get_object()
        tickets = project.tickets.all().order_by('created_at')
        serializer = ProjectTicketSerializer(tickets, many=True)
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


class ProjectTicketViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProjectTicketSerializer
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        accessible_projects = Project.objects.filter(
            Q(owner=user) | Q(members__user=user, members__status='active')
        ).distinct()
        return ProjectTicket.objects.filter(
            project__in=accessible_projects
        ).select_related('project').order_by('created_at')

    @action(detail=True, methods=['post'], url_path='queue-execution')
    def queue_execution(self, request, pk=None):
        """Queue a ticket for execution in the background task queue"""
        ticket = self.get_object()
        project = ticket.project

        # Get conversation_id from request (optional, could be None)
        conversation_id = request.data.get('conversation_id')

        try:
            from tasks.task_manager import TaskManager
            from django.core.cache import cache

            # Check if ticket is already queued (prevent duplicates)
            ai_processing_key = f'ticket_ai_processing_{ticket.id}'
            if cache.get(ai_processing_key):
                return Response({
                    'status': 'already_queued',
                    'message': f'Ticket #{ticket.id} is already queued or in progress',
                    'ticket_id': ticket.id
                }, status=status.HTTP_200_OK)

            # Set AI processing flag BEFORE queueing to prevent race conditions
            cache.set(ai_processing_key, True, timeout=7200)

            # Queue the ticket execution with project-based group
            # Tasks in the same group execute sequentially, different groups execute in parallel
            task_id = TaskManager.publish_task(
                'tasks.task_definitions.execute_ticket_implementation',
                ticket.id,
                project.id,
                conversation_id,
                task_name=f"Ticket #{ticket.id} execution for {project.name}",
                group=f'project_{project.id}',  # ← Key: Group by project ID
                timeout=7200  # 2 hour timeout
            )

            return Response({
                'status': 'queued',
                'message': f'Ticket #{ticket.id} queued for execution',
                'ticket_id': ticket.id,
                'task_id': task_id
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Failed to queue ticket: {str(e)}',
                'ticket_id': ticket.id
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'], url_path='logs')
    def logs(self, request, pk=None):
        """Get execution logs for a specific ticket"""
        from projects.models import TicketLog
        import logging
        logger = logging.getLogger(__name__)

        ticket = self.get_object()

        logger.info(f"[LOGS API] Fetching logs for ticket {ticket.id}")

        # Get logs for this specific ticket
        logs = TicketLog.objects.filter(ticket=ticket).order_by('created_at')

        logger.info(f"[LOGS API] Found {logs.count()} logs for ticket {ticket.id}")

        # Log type breakdown for debugging
        log_types = {}
        for log in logs:
            lt = log.log_type or 'command'
            log_types[lt] = log_types.get(lt, 0) + 1
        logger.info(f"[LOGS API] Log type breakdown: {log_types}")

        # Format logs for response
        commands_data = [{
            'id': log.id,
            'log_type': log.log_type or 'command',  # Ensure log_type is always set
            'command': log.command,
            'explanation': log.explanation or '',
            'output': log.output or '',
            'exit_code': log.exit_code,
            'created_at': log.created_at.isoformat()
        } for log in logs]

        # Check if there's an active AI task for this ticket
        from django.core.cache import cache
        ai_processing_key = f'ticket_ai_processing_{ticket.id}'
        is_ai_processing = cache.get(ai_processing_key, False)

        return Response({
            'ticket_id': ticket.id,
            'ticket_name': ticket.name,
            'ticket_status': ticket.status,
            'ticket_notes': ticket.notes or '',
            'commands': commands_data,
            'is_ai_processing': is_ai_processing
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='tasks')
    def tasks(self, request, pk=None):
        """Get tasks for a specific ticket"""
        from projects.models import ProjectTodoList
        import logging
        logger = logging.getLogger(__name__)

        ticket = self.get_object()
        logger.info(f"[TASKS API] Fetching tasks for ticket {ticket.id}")

        # Get all tasks for this ticket
        tasks = ProjectTodoList.objects.filter(ticket=ticket).order_by('order', 'created_at')

        logger.info(f"[TASKS API] Found {tasks.count()} tasks for ticket {ticket.id}")

        # Format tasks for response
        tasks_data = [{
            'id': task.id,
            'description': task.description,
            'status': task.status,
            'order': task.order,
            'created_at': task.created_at.isoformat(),
            'updated_at': task.updated_at.isoformat()
        } for task in tasks]

        return Response({
            'ticket_id': ticket.id,
            'ticket_name': ticket.name,
            'tasks': tasks_data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='chat')
    def chat(self, request, pk=None):
        """
        Send a chat message to continue ticket execution with additional instructions.
        This allows users to ask questions or request changes during ticket implementation.
        Supports file attachments via multipart form data.
        """
        import logging
        from projects.models import TicketLog, ProjectTicketAttachment
        from projects.websocket_utils import send_ticket_log_notification

        logger = logging.getLogger(__name__)

        ticket = self.get_object()
        project = ticket.project

        # Handle both JSON and FormData
        if hasattr(request.data, 'get'):
            message = request.data.get('message', '').strip()
        else:
            message = request.POST.get('message', '').strip()

        # Get uploaded files
        attachments = request.FILES.getlist('attachments')

        # Require either message or attachments
        if not message and not attachments:
            return Response({
                'status': 'error',
                'error': 'Message or attachments required'
            }, status=status.HTTP_400_BAD_REQUEST)

        logger.info(f"[TICKET CHAT] Received chat message for ticket {ticket.id}: {message[:100] if message else '(attachments only)'}...")

        # Check if already processing to prevent duplicate task submissions
        from django.core.cache import cache
        ai_processing_key = f'ticket_ai_processing_{ticket.id}'
        if cache.get(ai_processing_key):
            logger.warning(f"[TICKET CHAT] Duplicate request blocked - ticket {ticket.id} already processing")
            return Response({
                'status': 'already_processing',
                'message': 'Your previous message is still being processed. Please wait.',
                'ticket_id': ticket.id
            }, status=status.HTTP_200_OK)

        try:
            # Save attachments first
            attachment_ids = []
            attachment_names = []
            for file in attachments:
                attachment = ProjectTicketAttachment.objects.create(
                    ticket=ticket,
                    uploaded_by=request.user,
                    file=file,
                    original_filename=file.name,
                    file_type=file.content_type or '',
                    file_size=file.size
                )
                attachment_ids.append(attachment.id)
                attachment_names.append(file.name)
                logger.info(f"[TICKET CHAT] Saved attachment: {file.name} ({file.size} bytes)")

            # Build display message including attachment info
            display_message = message
            if attachment_names:
                attachment_text = ', '.join(attachment_names)
                if message:
                    display_message = f"{message}\n\n📎 Attachments: {attachment_text}"
                else:
                    display_message = f"📎 Attachments: {attachment_text}"

            # Save user message to TicketLog
            user_log = TicketLog.objects.create(
                ticket=ticket,
                log_type='user_message',
                command=display_message,  # Store the message in 'command' field
                explanation=f"Message from {request.user.email or request.user.username}"
            )

            # Send WebSocket notification for the new log
            send_ticket_log_notification(ticket.id, {
                'id': user_log.id,
                'log_type': 'user_message',
                'command': display_message,
                'explanation': user_log.explanation,
                'output': '',
                'exit_code': None,
                'created_at': user_log.created_at.isoformat()
            })

            logger.info(f"[TICKET CHAT] Saved user message as log {user_log.id}")

            # Set AI processing flag BEFORE queuing to prevent race conditions
            cache.set(ai_processing_key, True, timeout=1800)  # 30 minutes

            # Check if user has CLI mode enabled
            from accounts.models import ApplicationState, Profile as AccountProfile
            app_state = ApplicationState.objects.filter(user=request.user).first()
            profile = AccountProfile.objects.filter(user=request.user).first()

            cli_mode_enabled = (
                app_state and app_state.claude_code_enabled and
                profile and profile.claude_code_authenticated
            )

            logger.info(f"[TICKET CHAT] CLI mode check: enabled={cli_mode_enabled}, "
                       f"app_state.claude_code_enabled={getattr(app_state, 'claude_code_enabled', None)}, "
                       f"profile.claude_code_authenticated={getattr(profile, 'claude_code_authenticated', None)}")

            # Check if user has CLI mode enabled but not authenticated - block with error
            if app_state and app_state.claude_code_enabled and profile and not profile.claude_code_authenticated:
                logger.warning(f"[TICKET CHAT] CLI mode enabled but not authenticated - blocking request")
                # Clear the processing flag since we're not actually processing
                cache.delete(ai_processing_key)
                return Response({
                    'status': 'error',
                    'error': 'Claude Code session expired. Please go to Settings > Claude Code and reconnect.',
                    'auth_expired': True
                }, status=status.HTTP_401_UNAUTHORIZED)

            if cli_mode_enabled:
                # Use Claude CLI for chat
                import threading
                from tasks.task_definitions import execute_ticket_chat_cli

                session_id = ticket.cli_session_id  # May be None for new conversation

                def run_cli_chat():
                    try:
                        execute_ticket_chat_cli(
                            ticket_id=ticket.id,
                            project_id=project.id,
                            conversation_id=ticket.id,  # Use ticket_id as conversation_id
                            message=message or f"User attached files: {', '.join(attachment_names)}",
                            session_id=session_id
                        )
                    except Exception as e:
                        logger.error(f"[TICKET CHAT] CLI chat error: {e}", exc_info=True)
                    finally:
                        # Clear processing flag when done
                        cache.delete(ai_processing_key)

                thread = threading.Thread(target=run_cli_chat, daemon=True)
                thread.start()

                logger.info(f"[TICKET CHAT] Started CLI chat thread for ticket {ticket.id}, session={session_id}")

                return Response({
                    'status': 'queued',
                    'message': 'Your message has been sent to Claude CLI.',
                    'ticket_id': ticket.id,
                    'mode': 'cli_resume' if session_id else 'cli_new',
                    'log_id': user_log.id,
                    'attachments': attachment_ids
                }, status=status.HTTP_200_OK)
            else:
                # Use standard API method (qcluster task queue)
                from tasks.task_manager import TaskManager

                # Queue the ticket continuation with the user's message and attachment IDs
                task_id = TaskManager.publish_task(
                    'tasks.task_definitions.continue_ticket_with_message',
                    ticket.id,
                    project.id,
                    message or f"User attached files: {', '.join(attachment_names)}",
                    request.user.id,
                    attachment_ids=attachment_ids,  # Pass attachment IDs as keyword arg
                    task_name=f"Ticket #{ticket.id} chat continuation",
                    group=f'project_{project.id}',
                    timeout=3600  # 1 hour timeout
                )

                logger.info(f"[TICKET CHAT] Queued continuation task {task_id} for ticket {ticket.id}")

                return Response({
                    'status': 'queued',
                    'message': 'Your message has been sent. The agent will process it shortly.',
                    'ticket_id': ticket.id,
                    'task_id': task_id,
                    'log_id': user_log.id,
                    'attachments': attachment_ids
                }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"[TICKET CHAT] Error queuing chat message: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'error': f'Failed to send message: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path='stop')
    def stop_execution(self, request, pk=None):
        """
        Stop/interrupt the current AI execution for this ticket.
        This logs a stop request that the AI will see and respond to.
        """
        import logging
        from projects.models import TicketLog
        from projects.websocket_utils import send_ticket_log_notification
        from django.core.cache import cache

        logger = logging.getLogger(__name__)

        ticket = self.get_object()

        logger.info(f"[TICKET STOP] Stop requested for ticket {ticket.id}")

        try:
            # Set a cancellation flag in cache that AI tools can check
            cache_key = f'ticket_cancel_{ticket.id}'
            cache.set(cache_key, True, timeout=300)  # 5 minute timeout

            # Log the stop request
            stop_log = TicketLog.objects.create(
                ticket=ticket,
                log_type='user_message',
                command='🛑 STOP REQUESTED - User interrupted the execution',
                explanation=f"Stop requested by {request.user.email or request.user.username}"
            )

            # Send WebSocket notification
            send_ticket_log_notification(ticket.id, {
                'id': stop_log.id,
                'log_type': 'user_message',
                'command': stop_log.command,
                'explanation': stop_log.explanation,
                'output': '',
                'exit_code': None,
                'created_at': stop_log.created_at.isoformat()
            })

            logger.info(f"[TICKET STOP] Stop flag set for ticket {ticket.id}")

            # Clear the AI processing flag
            ai_processing_key = f'ticket_ai_processing_{ticket.id}'
            cache.delete(ai_processing_key)

            return Response({
                'status': 'stopped',
                'message': 'Stop request sent. The AI will stop at the next checkpoint.',
                'ticket_id': ticket.id
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"[TICKET STOP] Error stopping ticket: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'error': f'Failed to stop: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
