from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
import secrets
from datetime import timedelta

class LLMApiKeys(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='llm_api_keys')
    openai_api_key = models.CharField(max_length=255, blank=True, null=True)
    anthropic_api_key = models.CharField(max_length=255, blank=True, null=True)
    xai_api_key = models.CharField(max_length=255, blank=True, null=True)

    free_trial = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.user.username}'s API keys"
    
    def save(self, *args, **kwargs):
        # If any LLM key is provided, set free_trial to False
        if any([self.openai_api_key, self.anthropic_api_key, self.xai_api_key]):
            self.free_trial = False
        super().save(*args, **kwargs)


class ExternalServicesAPIKeys(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='external_api_keys')
    linear_api_key = models.CharField(max_length=255, blank=True, null=True)
    jira_api_key = models.CharField(max_length=255, blank=True, null=True)
    notion_api_key = models.CharField(max_length=255, blank=True, null=True)
    google_docs_api_key = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.user.username}'s External Services"


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    bio = models.TextField(max_length=500, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    sidebar_collapsed = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.user.username}'s profile"


class EmailVerificationToken(models.Model):
    """Model to store email verification tokens"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_verification_tokens')
    token = models.CharField(max_length=128, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Token for {self.user.email}"
    
    @classmethod
    def create_token(cls, user):
        """Create a new verification token for the user"""
        # Invalidate any existing unused tokens
        cls.objects.filter(user=user, used=False).update(used=True)
        
        # Create new token
        token = secrets.token_urlsafe(48)
        expires_at = timezone.now() + timedelta(hours=24)
        
        return cls.objects.create(
            user=user,
            token=token,
            expires_at=expires_at
        )
    
    def is_valid(self):
        """Check if token is still valid"""
        return not self.used and timezone.now() < self.expires_at


class EmailVerificationCode(models.Model):
    """Model to store 6-digit email verification codes"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_verification_codes')
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Code for {self.user.email}"
    
    @classmethod
    def create_code(cls, user):
        """Create a new 6-digit verification code for the user"""
        import random
        
        # Invalidate any existing unused codes
        cls.objects.filter(user=user, used=False).update(used=True)
        
        # Create new 6-digit code
        code = str(random.randint(100000, 999999))
        expires_at = timezone.now() + timedelta(minutes=30)  # 30 minutes expiry
        
        return cls.objects.create(
            user=user,
            code=code,
            expires_at=expires_at
        )
    
    def is_valid(self):
        """Check if code is still valid"""
        return not self.used and timezone.now() < self.expires_at


class ApplicationState(models.Model):
    """Model to store user-specific application UI state"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='app_state')
    sidebar_minimized = models.BooleanField(default=False)
    last_selected_model = models.CharField(max_length=50, default='o4-mini')
    last_selected_role = models.CharField(max_length=50, default='product_analyst')
    turbo_mode_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username}'s app state"


class GitHubToken(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    access_token = models.CharField(max_length=255)
    github_user_id = models.CharField(max_length=100, blank=True, null=True)
    github_username = models.CharField(max_length=100, blank=True, null=True)
    github_avatar_url = models.URLField(max_length=500, blank=True, null=True)
    scope = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username}'s GitHub token"


class TokenUsage(models.Model):
    """Model to track AI token usage across different providers"""
    PROVIDER_CHOICES = [
        ('openai', 'OpenAI'),
        ('anthropic', 'Anthropic'),
        ('xai', 'XAI'),
    ]
    
    MODEL_CHOICES = [
        # OpenAI models
        ('gpt-4o', 'GPT-4o'),
        ('gpt-4.1', 'GPT-4.1'),
        ('whisper-1', 'Whisper (Audio Transcription)'),
        # Anthropic models
        ('claude-sonnet-4-20250514', 'Claude Sonnet 4'),
        ('claude-opus-4-20250514', 'Claude Opus 4'),
        ('claude-3-5-sonnet-20241022', 'Claude 3.5 Sonnet'),
        # XAI models
        ('grok-4', 'Grok 4'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='token_usage')
    project = models.ForeignKey('projects.Project', on_delete=models.CASCADE, related_name='token_usage', null=True, blank=True)
    conversation = models.ForeignKey('chat.Conversation', on_delete=models.CASCADE, related_name='token_usage', null=True, blank=True)
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    model = models.CharField(max_length=50, choices=MODEL_CHOICES)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    timestamp = models.DateTimeField(default=timezone.now)
    
    # Optional metadata
    request_id = models.CharField(max_length=255, blank=True, null=True, help_text="Provider request ID for tracking")
    cost = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True, help_text="Estimated cost in USD")
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['project', 'timestamp']),
            models.Index(fields=['conversation', 'timestamp']),
            models.Index(fields=['provider', 'model']),
        ]
        verbose_name = "Token Usage"
        verbose_name_plural = "Token Usage Records"
    
    def __str__(self):
        return f"{self.user.username} - {self.provider}/{self.model} - {self.total_tokens} tokens"
    
    def calculate_cost(self):
        """Calculate estimated cost based on provider and model pricing"""
        # Pricing as of 2025 (in USD per 1K tokens)
        pricing = {
            'openai': {
                'gpt-4o': {'input': 0.005, 'output': 0.015},
                'gpt-4.1': {'input': 0.01, 'output': 0.03},
            },
            'anthropic': {
                'claude-sonnet-4-20250514': {'input': 0.003, 'output': 0.015},
                'claude-opus-4-20250514': {'input': 0.015, 'output': 0.075},
                'claude-3-5-sonnet-20241022': {'input': 0.003, 'output': 0.015},
            },
            'xai': {
                # XAI pricing (estimated based on typical AI model pricing)
                'xai-4': {'input': 0.003, 'output': 0.008},
            }
        }
        
        if self.provider in pricing and self.model in pricing[self.provider]:
            rates = pricing[self.provider][self.model]
            input_cost = (self.input_tokens / 1000) * rates['input']
            output_cost = (self.output_tokens / 1000) * rates['output']
            self.cost = input_cost + output_cost
            return self.cost
        return None


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    try:
        if created:
            Profile.objects.create(user=instance)
            # Also create LLMApiKeys for the new user
            LLMApiKeys.objects.create(user=instance)
            # Create ApplicationState for the new user
            ApplicationState.objects.create(user=instance)
    except:
        # Handle the case when the table doesn't exist yet
        pass

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    try:
        instance.profile.save()
    except:
        # Handle the case when the profile doesn't exist
        pass 