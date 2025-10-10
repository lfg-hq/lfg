from rest_framework import serializers
from django.contrib.auth.models import User
from accounts.models import Profile, LLMApiKeys
from subscriptions.models import PaymentPlan
from chat.models import Conversation, Message


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = ['id']


class ProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    subscription_plan_name = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = [
            'user', 'avatar', 'email_verified', 'github_username',
            'subscription_plan', 'subscription_plan_name', 'total_tokens_used',
            'org_mode_enabled'
        ]
        read_only_fields = ['email_verified', 'total_tokens_used']

    def get_subscription_plan_name(self, obj):
        if obj.subscription_plan:
            return obj.subscription_plan.name
        return "Free"


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password2']

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Passwords don't match"})

        # Check if email already exists
        if User.objects.filter(email=attrs['email']).exists():
            raise serializers.ValidationError({"email": "Email already exists"})

        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password']
        )
        return user


class LLMApiKeysSerializer(serializers.ModelSerializer):
    # Mask the API keys for security
    openai_api_key_masked = serializers.SerializerMethodField()
    anthropic_api_key_masked = serializers.SerializerMethodField()
    xai_api_key_masked = serializers.SerializerMethodField()
    google_api_key_masked = serializers.SerializerMethodField()

    class Meta:
        model = LLMApiKeys
        fields = [
            'openai_api_key', 'anthropic_api_key', 'xai_api_key', 'google_api_key',
            'openai_api_key_masked', 'anthropic_api_key_masked',
            'xai_api_key_masked', 'google_api_key_masked'
        ]
        extra_kwargs = {
            'openai_api_key': {'write_only': True},
            'anthropic_api_key': {'write_only': True},
            'xai_api_key': {'write_only': True},
            'google_api_key': {'write_only': True},
        }

    def get_openai_api_key_masked(self, obj):
        return self._mask_key(obj.openai_api_key)

    def get_anthropic_api_key_masked(self, obj):
        return self._mask_key(obj.anthropic_api_key)

    def get_xai_api_key_masked(self, obj):
        return self._mask_key(obj.xai_api_key)

    def get_google_api_key_masked(self, obj):
        return self._mask_key(obj.google_api_key)

    def _mask_key(self, key):
        if not key:
            return None
        if len(key) > 8:
            return f"{key[:4]}...{key[-4:]}"
        return "***"


class ConversationSerializer(serializers.ModelSerializer):
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ['id', 'title', 'created_at', 'updated_at', 'message_count']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_message_count(self, obj):
        return obj.messages.count()


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ['id', 'conversation', 'role', 'content', 'timestamp', 'token_count']
        read_only_fields = ['id', 'timestamp', 'token_count']
