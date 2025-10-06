from rest_framework import status, generics, viewsets
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.views.decorators.csrf import csrf_exempt
from accounts.models import Profile, LLMApiKeys
from chat.models import Conversation, Message
from subscriptions.models import UserCredit
from .serializers import (
    UserSerializer, ProfileSerializer, RegisterSerializer,
    LLMApiKeysSerializer, ConversationSerializer, MessageSerializer
)


# Authentication Views
@csrf_exempt
@api_view(['POST'])
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
@api_view(['POST'])
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

        return Response({
            'user': UserSerializer(user).data,
            'profile': ProfileSerializer(user.profile).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            },
            'message': 'Login successful'
        })

    return Response({
        'error': 'Invalid credentials'
    }, status=status.HTTP_401_UNAUTHORIZED)


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
    return Response({
        'user': UserSerializer(request.user).data,
        'profile': ProfileSerializer(request.user.profile).data
    })


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
    profile = request.user.profile

    # Get or create user credit
    credit, created = UserCredit.objects.get_or_create(user=request.user)

    return Response({
        'subscription_plan': profile.subscription_plan.name if profile.subscription_plan else 'Free',
        'total_tokens_used': profile.total_tokens_used,
        'credits': {
            'balance': credit.balance,
            'lifetime_tokens': credit.lifetime_tokens,
            'monthly_tokens': credit.monthly_tokens,
        }
    })


# Conversation Views
class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user).order_by('-updated_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

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
