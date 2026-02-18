import uuid

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from projects.models import Project
from chat.models import Conversation, Message


class SlackIntegration(models.Model):
    """Stores Slack bot OAuth credentials per user."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='slack_integration')
    bot_token = models.CharField(max_length=512, help_text='Encrypted Slack Bot OAuth token')
    team_id = models.CharField(max_length=64, blank=True, default='')
    team_name = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    connected_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Slack: {self.user.username} ({self.team_name})"


class TelegramIntegration(models.Model):
    """Stores Telegram bot credentials per user."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='telegram_integration')
    bot_token = models.CharField(max_length=512, help_text='Telegram Bot API token')
    bot_username = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    connected_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Telegram: {self.user.username} (@{self.bot_username})"


class ChannelProjectLink(models.Model):
    """Links an external messaging channel to an LFG project."""
    PLATFORM_CHOICES = [
        ('slack', 'Slack'),
        ('telegram', 'Telegram'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='channel_links')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='channel_links')
    platform = models.CharField(max_length=16, choices=PLATFORM_CHOICES)
    channel_id = models.CharField(max_length=128, help_text='Slack channel ID or Telegram chat ID')
    channel_name = models.CharField(max_length=255, blank=True, default='')
    conversation = models.ForeignKey(
        Conversation, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='channel_link',
        help_text='Reusable conversation for this channel link'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'platform', 'channel_id')
        indexes = [
            models.Index(fields=['platform', 'channel_id']),
        ]

    def __str__(self):
        return f"{self.platform}:{self.channel_name} -> {self.project.name}"


class TelegramLinkToken(models.Model):
    """One-time token for Telegram deep-link auto-linking."""
    token = models.CharField(max_length=32, unique=True, default='')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='telegram_link_tokens')
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = uuid.uuid4().hex[:16]
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return (timezone.now() - self.created_at).total_seconds() > 600  # 10 min

    def __str__(self):
        return f"Link token for {self.user.username} -> {self.project.name}"


class ChannelMessage(models.Model):
    """Tracks messages sent/received through external channels."""
    DIRECTION_CHOICES = [
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ]

    channel_link = models.ForeignKey(ChannelProjectLink, on_delete=models.CASCADE, related_name='channel_messages')
    platform_message_id = models.CharField(max_length=128, blank=True, default='')
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    content = models.TextField()
    sender_name = models.CharField(max_length=255, blank=True, default='')
    sender_id = models.CharField(max_length=128, blank=True, default='')
    message = models.ForeignKey(
        Message, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='channel_messages',
        help_text='Linked LFG chat message'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['channel_link', '-created_at']),
        ]

    def __str__(self):
        return f"{self.direction}: {self.content[:50]}"
