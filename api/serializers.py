from rest_framework import serializers
from django.contrib.auth.models import User
from accounts.models import Profile, LLMApiKeys
from subscriptions.models import PaymentPlan
from chat.models import Conversation, Message
from projects.models import Project, ProjectFile, ProjectTicket, ProjectTaskList


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = ['id']


class ProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    subscription_plan_name = serializers.SerializerMethodField()
    total_tokens_used = serializers.SerializerMethodField()
    org_mode_enabled = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = [
            'user', 'avatar', 'email_verified',
            'subscription_plan_name', 'total_tokens_used', 'org_mode_enabled'
        ]
        read_only_fields = ['email_verified', 'total_tokens_used', 'subscription_plan_name', 'org_mode_enabled']

    def get_subscription_plan_name(self, obj):
        credit = getattr(obj.user, 'credit', None)
        if credit:
            if credit.subscription_tier == 'pro' and credit.has_active_subscription:
                return 'Pro'
            return credit.subscription_tier.title()
        return 'Free'

    def get_total_tokens_used(self, obj):
        credit = getattr(obj.user, 'credit', None)
        if credit:
            return credit.total_tokens_used
        return 0

    def get_org_mode_enabled(self, obj):
        return False


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
    project = serializers.SerializerMethodField()
    project_id = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Conversation
        fields = [
            'id', 'title', 'created_at', 'updated_at',
            'message_count', 'project', 'project_id'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'message_count', 'project']

    def get_message_count(self, obj):
        annotated = getattr(obj, 'message_count', None)
        if annotated is not None:
            return annotated
        return obj.messages.count()

    def get_project(self, obj):
        if obj.project:
            return {
                'id': obj.project.project_id,
                'name': obj.project.name,
                'icon': obj.project.icon,
            }
        return None


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ['id', 'conversation', 'role', 'content', 'timestamp', 'token_count']
        read_only_fields = ['id', 'timestamp', 'token_count']


class ProjectSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='project_id', read_only=True)
    conversations_count = serializers.SerializerMethodField()
    documents_count = serializers.SerializerMethodField()
    tickets_count = serializers.SerializerMethodField()
    code_chunks = serializers.SerializerMethodField()
    owner = UserSerializer(read_only=True)

    class Meta:
        model = Project
        fields = [
            'id', 'name', 'icon', 'description', 'status',
            'created_at', 'updated_at', 'conversations_count',
            'documents_count', 'tickets_count', 'code_chunks', 'owner'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'conversations_count',
            'documents_count', 'tickets_count', 'code_chunks', 'owner'
        ]
        extra_kwargs = {
            'name': {'required': True},
            'icon': {'required': False, 'allow_blank': True},
            'description': {'required': False, 'allow_blank': True, 'allow_null': True},
        }

    def get_conversations_count(self, obj: Project) -> int:
        annotated = getattr(obj, 'conversations_count', None)
        if annotated is not None:
            return annotated
        return obj.direct_conversations.count()

    def get_documents_count(self, obj: Project) -> int:
        annotated = getattr(obj, 'documents_count', None)
        if annotated is not None:
            return annotated
        return obj.files.filter(is_active=True).count()

    def get_tickets_count(self, obj: Project) -> int:
        annotated = getattr(obj, 'tickets_count', None)
        if annotated is not None:
            return annotated
        return obj.tickets.count()

    def get_code_chunks(self, obj: Project):
        indexed_repo = getattr(obj, 'indexed_repository', None)
        if indexed_repo:
            return indexed_repo.total_chunks
        return None


class ProjectDocumentSerializer(serializers.ModelSerializer):
    project_id = serializers.CharField(source='project.project_id', read_only=True)
    content = serializers.SerializerMethodField()

    class Meta:
        model = ProjectFile
        fields = [
            'id', 'project_id', 'name', 'file_type', 'content',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = fields

    def get_content(self, obj: ProjectFile):
        return obj.file_content


class ProjectTicketSerializer(serializers.ModelSerializer):
    project_id = serializers.CharField(source='project.project_id', read_only=True)
    tasks = serializers.SerializerMethodField()

    class Meta:
        model = ProjectTicket
        fields = [
            'id', 'project_id', 'name', 'status', 'priority', 'role',
            'details', 'ui_requirements', 'component_specs',
            'acceptance_criteria', 'dependencies', 'notes', 'complexity',
            'requires_worktree', 'linear_issue_id', 'linear_issue_url',
            'linear_state', 'linear_priority', 'linear_assignee_id',
            'linear_synced_at', 'linear_sync_enabled', 'created_at', 'updated_at', 'tasks'
        ]
        read_only_fields = fields

    def get_tasks(self, obj):
        from api.serializers import ProjectTaskSerializer
        return ProjectTaskSerializer(obj.tasks.all(), many=True).data


class ProjectTaskSerializer(serializers.ModelSerializer):
    ticket_id = serializers.IntegerField(source='ticket.id', read_only=True)

    class Meta:
        model = ProjectTaskList
        fields = [
            'id', 'ticket_id', 'name', 'description', 'status', 'order',
            'created_at', 'updated_at'
        ]
        read_only_fields = fields
