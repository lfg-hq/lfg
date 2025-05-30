from django.db import models
from django.contrib.auth.models import User
import os
import uuid


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
    
    class Meta:
        ordering = ['created_at']
    
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
    file = models.FileField(upload_to=get_file_upload_path)
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=100, blank=True)
    file_size = models.IntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"File: {self.original_filename} ({self.conversation})"

class ModelSelection(models.Model):
    """Model to track which AI model is selected by users"""
    MODEL_CHOICES = [
        ('claude_4_sonnet', 'Claude 4 Sonnet'),
        ('gpt_4_1', 'OpenAI GPT-4.1'),
        ('gpt_4o', 'OpenAI GPT-4o'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='model_selection')
    selected_model = models.CharField(max_length=50, choices=MODEL_CHOICES, default='claude_4_sonnet')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def get_display_name(self):
        return dict(self.MODEL_CHOICES).get(self.selected_model, self.selected_model)
    
    def __str__(self):
        return f"{self.user.username} - {self.get_display_name()}" 