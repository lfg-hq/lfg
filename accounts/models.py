from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import slugify
import secrets
from datetime import timedelta

class LLMApiKeys(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='llm_api_keys')
    openai_api_key = models.CharField(max_length=255, blank=True, null=True)
    anthropic_api_key = models.CharField(max_length=255, blank=True, null=True)
    xai_api_key = models.CharField(max_length=255, blank=True, null=True)
    google_api_key = models.CharField(max_length=255, blank=True, null=True)

    free_trial = models.BooleanField(default=True)
    use_personal_llm_keys = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.user.username}'s API keys"
    
    def save(self, *args, **kwargs):
        # If any LLM key is provided, set free_trial to False
        if any([self.openai_api_key, self.anthropic_api_key, self.xai_api_key, self.google_api_key]):
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


class Organization(models.Model):
    """Model to represent an organization/team"""
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_organizations')
    description = models.TextField(max_length=500, blank=True)
    avatar = models.ImageField(upload_to='organization_avatars/', null=True, blank=True)
    
    # Billing information
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Settings
    allow_member_invites = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
            # Ensure uniqueness
            counter = 1
            original_slug = self.slug
            while Organization.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)
    
    @property
    def member_count(self):
        return self.memberships.filter(status='active').count()
    
    def get_members(self):
        return User.objects.filter(
            organization_memberships__organization=self,
            organization_memberships__status='active'
        )
    
    def is_member(self, user):
        return self.memberships.filter(user=user, status='active').exists()
    
    def get_user_role(self, user):
        try:
            membership = self.memberships.get(user=user, status='active')
            return membership.role
        except OrganizationMembership.DoesNotExist:
            return None


class OrganizationMembership(models.Model):
    """Model to represent membership in an organization"""
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('member', 'Member'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='organization_memberships')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='member')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    
    # Timestamps
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'organization']
        verbose_name = "Organization Membership"
        verbose_name_plural = "Organization Memberships"
    
    def __str__(self):
        return f"{self.user.username} - {self.organization.name} ({self.role})"
    
    @property
    def can_invite_members(self):
        return self.role in ['owner', 'admin'] or (
            self.role == 'member' and self.organization.allow_member_invites
        )
    
    @property
    def can_manage_members(self):
        return self.role in ['owner', 'admin']
    
    @property
    def can_manage_billing(self):
        return self.role == 'owner'


class OrganizationInvitation(models.Model):
    """Model to handle organization invitations"""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='invitations')
    inviter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invitations')
    email = models.EmailField()
    role = models.CharField(max_length=10, choices=OrganizationMembership.ROLE_CHOICES, default='member')
    
    # Token for secure invitation
    token = models.CharField(max_length=128, unique=True, db_index=True)
    
    # Status tracking
    status = models.CharField(max_length=10, choices=[
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
    ], default='pending')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    responded_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Organization Invitation"
        verbose_name_plural = "Organization Invitations"
        unique_together = ['organization', 'email']
    
    def __str__(self):
        return f"Invitation to {self.email} for {self.organization.name}"
    
    @classmethod
    def create_invitation(cls, organization, inviter, email, role='member'):
        """Create a new invitation with a secure token"""
        # Cancel any existing pending invitations for this email/organization
        cls.objects.filter(
            organization=organization,
            email=email,
            status='pending'
        ).update(status='expired')
        
        # Create new invitation
        token = secrets.token_urlsafe(48)
        expires_at = timezone.now() + timedelta(days=7)  # 7 days to accept
        
        return cls.objects.create(
            organization=organization,
            inviter=inviter,
            email=email,
            role=role,
            token=token,
            expires_at=expires_at
        )
    
    def is_valid(self):
        """Check if invitation is still valid"""
        return (
            self.status == 'pending' and 
            timezone.now() < self.expires_at
        )
    
    def accept(self, user):
        """Accept the invitation and create membership"""
        if not self.is_valid():
            raise ValueError("Invitation is not valid")
        
        if user.email.lower() != self.email.lower():
            raise ValueError("User email doesn't match invitation email")
        
        # Create membership
        membership, created = OrganizationMembership.objects.get_or_create(
            user=user,
            organization=self.organization,
            defaults={'role': self.role}
        )
        
        # Mark invitation as accepted
        self.status = 'accepted'
        self.responded_at = timezone.now()
        self.save()
        
        return membership


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    bio = models.TextField(max_length=500, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    sidebar_collapsed = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    
    # Organization context
    current_organization = models.ForeignKey(
        Organization, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='current_users',
        help_text="The currently selected organization for this user"
    )
    
    # Project collaboration settings
    allow_project_invitations = models.BooleanField(
        default=True,
        help_text="Allow inviting external users to collaborate on projects"
    )
    
    def __str__(self):
        return f"{self.user.username}'s profile"
    
    def get_organizations(self):
        """Get all organizations this user is a member of"""
        return Organization.objects.filter(
            memberships__user=self.user,
            memberships__status='active'
        )
    
    def switch_organization(self, organization):
        """Switch to a specific organization context"""
        if organization and not organization.is_member(self.user):
            raise ValueError("User is not a member of this organization")
        
        self.current_organization = organization
        self.save(update_fields=['current_organization'])


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
        ('google', 'Google'),
    ]
    
    MODEL_CHOICES = [
        # OpenAI models
        ('gpt-4o', 'GPT-4o'),
        ('gpt-4.1', 'GPT-4.1'),
        ('o3', 'o3'),
        ('o4-mini', 'o4 mini'),
        ('whisper-1', 'Whisper (Audio Transcription)'),
        # Anthropic models
        ('claude-sonnet-4-20250514', 'Claude Sonnet 4'),
        ('claude-opus-4-20250514', 'Claude Opus 4'),
        ('claude-3-5-sonnet-20241022', 'Claude 3.5 Sonnet'),
        # XAI models
        ('grok-4', 'Grok 4'),
        # Google models
        ('models/gemini-2.5-pro', 'Gemini 2.5 Pro'),
        ('models/gemini-2.5-flash', 'Gemini 2.5 Flash'),
        ('models/gemini-2.5-flash-lite', 'Gemini 2.5 Flash Lite'),
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
                'o3': {'input': 0.015, 'output': 0.06},
                'o4-mini': {'input': 0.00015, 'output': 0.0006},
            },
            'anthropic': {
                'claude-sonnet-4-20250514': {'input': 0.003, 'output': 0.015},
                'claude-opus-4-20250514': {'input': 0.015, 'output': 0.075},
                'claude-3-5-sonnet-20241022': {'input': 0.003, 'output': 0.015},
            },
            'xai': {
                # XAI pricing (estimated based on typical AI model pricing)
                'grok-4': {'input': 0.003, 'output': 0.008},
            },
            'google': {
                # Google Gemini pricing (as of 2025)
                'models/gemini-2.5-pro': {'input': 0.002, 'output': 0.006},
                'models/gemini-2.5-flash': {'input': 0.00025, 'output': 0.00075},
                'models/gemini-2.5-flash-lite': {'input': 0.0001, 'output': 0.0003},
            }
        }
        
        if self.provider in pricing and self.model in pricing[self.provider]:
            rates = pricing[self.provider][self.model]
            input_cost = (self.input_tokens / 1000) * rates['input']
            output_cost = (self.output_tokens / 1000) * rates['output']
            self.cost = input_cost + output_cost
            return self.cost
        return None


@receiver(post_save, sender=Organization)
def create_owner_membership(sender, instance, created, **kwargs):
    """Create owner membership when organization is created"""
    if created:
        OrganizationMembership.objects.get_or_create(
            user=instance.owner,
            organization=instance,
            defaults={'role': 'owner', 'status': 'active'}
        )

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
