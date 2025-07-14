from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
import uuid

# Create your models here.
class Project(models.Model):
    # Keep default integer ID for foreign key compatibility
    # Use project_id for URLs and external references
    project_id = models.CharField(max_length=36, unique=True, default=uuid.uuid4, db_index=True)
    name = models.CharField(max_length=255)
    provided_name = models.CharField(max_length=255, blank=True, null=True)  # User-provided name for project references
    description = models.TextField(blank=True, null=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="projects")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=20, choices=(
        ('active', 'Active'),
        ('archived', 'Archived'),
        ('completed', 'Completed')
    ), default='active')
    icon = models.CharField(max_length=50, default='📋')  # Default icon is a clipboard
    
    # Linear integration fields
    linear_team_id = models.CharField(max_length=255, blank=True, null=True, help_text="Linear team ID for syncing")
    linear_project_id = models.CharField(max_length=255, blank=True, null=True, help_text="Linear project ID for syncing")
    linear_sync_enabled = models.BooleanField(default=False, help_text="Enable automatic ticket syncing with Linear")
    
    def __str__(self):
        return self.name
    
    def get_absolute_url(self):
        return reverse('project_detail', kwargs={'project_id': str(self.project_id)})
        
    def get_chat_url(self):
        """Get URL for the latest conversation or create a new one"""
        latest_conversation = self.direct_conversations.order_by('-updated_at').first()
        if latest_conversation:
            return reverse('conversation_detail', kwargs={'conversation_id': latest_conversation.id})
        return reverse('create_conversation', kwargs={'project_id': str(self.project_id)})
    
    @classmethod
    def get_or_create_default_project(cls, user):
        """Get or create a default project for the user"""
        # Check if user has any projects
        existing_project = user.projects.filter(name="Untitled Project").first()
        if existing_project:
            return existing_project
        
        # Create a default project
        project = cls.objects.create(
            name="Untitled Project",
            description="Default project for quick start",
            owner=user,
            icon="🚀"
        )
        return project

class ProjectFeature(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="features")
    name = models.CharField(max_length=255)
    description = models.TextField(help_text="A short description of this feature")
    details = models.TextField(help_text="Detailed description with at least 3-4 lines")
    PRIORITY_CHOICES = [
        ('High Priority', 'High Priority'),
        ('Medium Priority', 'Medium Priority'),
        ('Low Priority', 'Low Priority'),
    ]
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.project.name})"
    
class ProjectPersona(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="personas")
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=255)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} - {self.role} ({self.project.name})"


class ProjectPRD(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="prds")
    name = models.CharField(max_length=255, default="Main PRD")
    prd = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('project', 'name')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.project.name} - {self.name}"

    def get_prd(self):
        return self.prd


class ProjectImplementation(models.Model):
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="implementation")
    implementation = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.project.name} - Implementation"

    def get_implementation(self):
        return self.implementation


class ProjectDesignSchema(models.Model):
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="design_schema")
    design_schema = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_design_schema(self):
        return self.design_schema
    
    
class ProjectChecklist(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="checklist")
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=(
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('failed', 'Failed'),
        ('blocked', 'Blocked'),
    ), default='open')
    description = models.TextField()
    priority = models.CharField(max_length=20, choices=(
        ('High', 'High'),
        ('Medium', 'Medium'),
        ('Low', 'Low'),
    ), default='Medium')
    role = models.CharField(max_length=20, choices=(
        ('agent', 'Agent'),
        ('user', 'User'),
    ), default='user')
    
    # Enhanced fields for detailed specifications
    details = models.JSONField(default=dict, blank=True, 
        help_text='Detailed specifications including files, technical requirements')
    
    # UI/UX specific fields
    ui_requirements = models.JSONField(default=dict, blank=True,
        help_text='UI/UX design specifications (layout, colors, typography, spacing, animations)')
    component_specs = models.JSONField(default=dict, blank=True,
        help_text='Component-level specifications (buttons, forms, modals, etc.)')
    
    # Implementation details
    acceptance_criteria = models.JSONField(default=list, blank=True,
        help_text='List of acceptance criteria for ticket completion')
    dependencies = models.JSONField(default=list, blank=True,
        help_text='List of ticket IDs or names this ticket depends on')
    
    # Execution metadata
    complexity = models.CharField(max_length=20, choices=(
        ('simple', 'Simple'),
        ('medium', 'Medium'), 
        ('complex', 'Complex'),
    ), default='medium', help_text='Estimated complexity of the ticket')
    requires_worktree = models.BooleanField(default=True,
        help_text='Whether this ticket requires a git worktree for code changes')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Linear integration fields
    linear_issue_id = models.CharField(max_length=255, blank=True, null=True, help_text="Linear issue ID for this ticket")
    linear_issue_url = models.URLField(blank=True, null=True, help_text="Direct URL to the Linear issue")
    linear_state = models.CharField(max_length=50, blank=True, null=True, help_text="Current state in Linear (e.g., Todo, In Progress, Done)")
    linear_priority = models.IntegerField(blank=True, null=True, help_text="Priority level from Linear (0-4)")
    linear_assignee_id = models.CharField(max_length=255, blank=True, null=True, help_text="Linear user ID of assignee")
    linear_synced_at = models.DateTimeField(blank=True, null=True, help_text="Last time this ticket was synced with Linear")
    linear_sync_enabled = models.BooleanField(default=True, help_text="Whether to sync this specific ticket with Linear")
    
    def __str__(self):
        return f"{self.project.name} - {self.name}"
    
class ProjectCodeGeneration(models.Model):
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="code_generation")
    folder_name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.project.name} - Code Generation Folder: {self.folder_name}"

class ToolCallHistory(models.Model):
    """Model to store content generated during tool calls"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tool_call_histories')
    conversation = models.ForeignKey('chat.Conversation', on_delete=models.CASCADE, related_name='tool_call_histories', null=True, blank=True)
    message = models.ForeignKey('chat.Message', on_delete=models.CASCADE, related_name='tool_call_histories', null=True, blank=True)
    tool_name = models.CharField(max_length=100)
    tool_input = models.JSONField(default=dict, blank=True)
    generated_content = models.TextField()
    content_type = models.CharField(max_length=50, default='text')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', '-created_at']),
            models.Index(fields=['project', 'tool_name']),
            models.Index(fields=['conversation', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.tool_name} - {self.project.name} - {self.created_at}"
    
    