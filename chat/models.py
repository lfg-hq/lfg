from django.db import models
from django.contrib.auth.models import User
import os
import uuid
from .storage import ChatFileStorage
from factory.llm_config import (
    get_model_choices,
    get_default_model_key,
    get_model_label,
)


class AgentRole(models.Model):
    """Model to define different agent roles in the system"""
    ROLE_CHOICES = [
        ('developer', 'Developer'),
        ('designer', 'Designer'),
        ('product_analyst', 'Analyst'),
        ('default', 'Default'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='agent_role')
    name = models.CharField(max_length=50, choices=ROLE_CHOICES, default='product_analyst')
    turbo_mode = models.BooleanField(default=False, help_text='Enable turbo mode for quick MVP generation')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def get_display_name(self):
        return dict(self.ROLE_CHOICES).get(self.name, self.name)
    
    def __str__(self):
        return f"{self.user.username} - {self.get_display_name()}"

class Conversation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations', null=True, blank=True)
    title = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    project = models.ForeignKey('projects.Project', on_delete=models.SET_NULL, related_name='direct_conversations', null=True, blank=True)
    design_canvas = models.ForeignKey('projects.DesignCanvas', on_delete=models.SET_NULL, related_name='conversations', null=True, blank=True)

    def __str__(self):
        return self.title or f"Conversation {self.id}"

class Message(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]
    
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    content_if_file = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    user_role = models.CharField(max_length=50, blank=True, null=True, default='default')
    is_partial = models.BooleanField(default=False, help_text="Whether this is a partially saved message")
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', '-created_at']),
            models.Index(fields=['conversation', 'is_partial']),
        ]
    
    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."

def get_file_upload_path(instance, filename):
    """Generate a unique file path for uploaded files"""
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join('file_storage', str(instance.conversation.id), filename)

class ChatFile(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='files')
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='files', null=True, blank=True)
    file = models.FileField(upload_to=get_file_upload_path, storage=ChatFileStorage())
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=100, blank=True)
    file_size = models.IntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"File: {self.original_filename} ({self.conversation})"

def _get_model_choices():
    choices = get_model_choices()
    if choices:
        return choices
    # Fallback options if config missing
    return [
        ('claude_4_sonnet', 'Claude 4 Sonnet'),
        ('gpt-5', 'GPT-5'),
        ('gpt-5-mini', 'GPT-5-mini'),
        ('grok_4', 'Grok 4'),
        ('gemini_2.5_pro', 'Google Gemini 2.5 Pro'),
        ('gemini_2.5_flash', 'Google Gemini 2.5 Flash'),
        ('gemini_2.5_flash_lite', 'Google Gemini 2.5 Flash Lite'),
    ]


class ModelSelection(models.Model):
    """Model to track which AI model is selected by users"""
    MODEL_CHOICES = _get_model_choices()
    DEFAULT_MODEL_KEY = get_default_model_key() or (MODEL_CHOICES[0][0] if MODEL_CHOICES else 'gpt-5-mini')
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='model_selection')
    selected_model = models.CharField(max_length=50, choices=MODEL_CHOICES, default=DEFAULT_MODEL_KEY)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def get_display_name(self):
        return get_model_label(self.selected_model)
    
    def __str__(self):
        return f"{self.user.username} - {self.get_display_name()}" 
