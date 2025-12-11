from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
import uuid
import os

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
    
    def has_member(self, user):
        """Check if user is a member of this project"""
        return self.members.filter(user=user, status='active').exists() or self.owner == user
    
    def get_member(self, user):
        """Get project member instance for user"""
        if self.owner == user:
            # Return a virtual owner membership
            return type('ProjectMember', (), {
                'user': user,
                'project': self,
                'role': 'owner',
                'status': 'active',
                'can_edit_files': True,
                'can_manage_tickets': True,
                'can_chat': True,
                'can_invite_members': True,
                'can_manage_project': True,
                'can_delete_project': True,
                'get_permissions': lambda self: {
                    'can_edit_files': True,
                    'can_manage_tickets': True,
                    'can_chat': True,
                    'can_invite_members': True,
                    'can_manage_project': True,
                    'can_delete_project': True,
                }
            })()
        try:
            return self.members.get(user=user, status='active')
        except ProjectMember.DoesNotExist:
            return None
    
    def get_user_role(self, user):
        """Get user's role in this project"""
        if self.owner == user:
            return 'owner'
        member = self.get_member(user)
        return member.role if member else None
    
    def can_user_access(self, user):
        """Check if user can access this project"""
        return self.has_member(user)
    
    def can_user_edit_files(self, user):
        """Check if user can edit files in this project"""
        member = self.get_member(user)
        return member and member.get_permissions().get('can_edit_files', False)
    
    def can_user_manage_tickets(self, user):
        """Check if user can manage tickets in this project"""
        member = self.get_member(user)
        return member and member.get_permissions().get('can_manage_tickets', False)
    
    def can_user_chat(self, user):
        """Check if user can chat in this project"""
        member = self.get_member(user)
        return member and member.get_permissions().get('can_chat', False)
    
    def can_user_invite_members(self, user):
        """Check if user can invite members to this project"""
        member = self.get_member(user)
        return member and member.get_permissions().get('can_invite_members', False)

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


class ProjectDesignFeature(models.Model):
    """Model to store design features with pages, navigation, and styling as JSON"""
    PLATFORM_CHOICES = [
        ('web', 'Web (Responsive)'),
        ('mobile', 'Mobile (iOS)'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='design_features')
    conversation = models.ForeignKey('chat.Conversation', on_delete=models.SET_NULL, null=True, blank=True, related_name='design_features')
    feature_name = models.CharField(max_length=255)
    feature_description = models.TextField(blank=True, default='')
    explainer = models.TextField(blank=True, default='')
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES, default='web')

    # All design data stored as JSON
    css_style = models.TextField(blank=True, default='')
    common_elements = models.JSONField(default=list)  # Array of common elements (header, footer, sidebar)
    pages = models.JSONField(default=list)  # Array of page objects with html_content, navigates_to, etc.
    entry_page_id = models.CharField(max_length=100, blank=True, default='')
    feature_connections = models.JSONField(default=list)  # Cross-feature navigation links
    canvas_position = models.JSONField(default=dict)  # {x: 0, y: 0}

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        unique_together = ['project', 'feature_name']
        indexes = [
            models.Index(fields=['project', '-updated_at']),
            models.Index(fields=['project', 'feature_name']),
        ]

    def __str__(self):
        return f"{self.project.name} - {self.feature_name}"


class DesignCanvas(models.Model):
    """Model to store named design canvases with feature positions"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='design_canvases')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    is_default = models.BooleanField(default=False)

    # Store positions for each feature on this canvas: {feature_id: {x: 0, y: 0}}
    feature_positions = models.JSONField(default=dict)

    # Store which features are visible on this canvas (empty = all features)
    visible_features = models.JSONField(default=list)  # List of feature IDs to show

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        unique_together = ['project', 'name']
        indexes = [
            models.Index(fields=['project', '-updated_at']),
            models.Index(fields=['project', 'is_default']),
        ]

    def __str__(self):
        return f"{self.project.name} - {self.name}"

    def save(self, *args, **kwargs):
        # Ensure only one default canvas per project
        if self.is_default:
            DesignCanvas.objects.filter(project=self.project, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class ProjectTicket(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tickets")
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

    notes = models.TextField(blank=True, default='',
        help_text='Execution notes, issues, and progress updates for this ticket')
    
    # Execution metadata
    complexity = models.CharField(max_length=20, choices=(
        ('simple', 'Simple'),
        ('medium', 'Medium'),
        ('complex', 'Complex'),
    ), default='medium', help_text='Estimated complexity of the ticket')
    requires_worktree = models.BooleanField(default=True,
        help_text='Whether this ticket requires a git worktree for code changes')

    # Git/GitHub metadata
    github_branch = models.CharField(max_length=255, blank=True, null=True,
        help_text='Feature branch name for this ticket (e.g., feature/ticket-name)')
    github_commit_sha = models.CharField(max_length=40, blank=True, null=True,
        help_text='Git commit SHA for the ticket implementation')
    github_merge_status = models.CharField(max_length=20, blank=True, null=True,
        choices=(
            ('merged', 'Merged'),
            ('conflict', 'Conflict'),
            ('failed', 'Failed'),
            ('pending', 'Pending'),
        ), help_text='Merge status of feature branch into lfg-agent')

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

    # Queue status tracking (for parallel executor)
    QUEUE_STATUS_CHOICES = [
        ('none', 'Not Queued'),
        ('queued', 'Queued'),
        ('executing', 'Executing'),
    ]
    queue_status = models.CharField(
        max_length=20,
        choices=QUEUE_STATUS_CHOICES,
        default='none',
        help_text='Current queue status for execution'
    )
    queued_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the ticket was added to the execution queue'
    )
    queue_task_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text='Task ID for tracking in the execution queue'
    )

    def __str__(self):
        return f"{self.project.name} - {self.name}"

    class Meta:
        ordering = ['created_at', 'id']


class ProjectTodoList(models.Model):
    """Model to store tasks associated with each project ticket"""
    ticket = models.ForeignKey(ProjectTicket, on_delete=models.CASCADE, related_name="tasks")
    description = models.TextField(help_text="Task description")
    status = models.CharField(max_length=20, choices=(
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('success', 'Success'),
        ('fail', 'Fail'),
    ), default='pending')
    order = models.IntegerField(default=0, help_text='Order of task execution')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.ticket.name} - {self.description[:50]}"

    class Meta:
        ordering = ['order', 'created_at', 'id']


class TicketLog(models.Model):
    """Model to store execution logs for tickets - includes commands, user messages, and AI responses"""

    LOG_TYPE_CHOICES = [
        ('command', 'Command'),
        ('user_message', 'User Message'),
        ('ai_response', 'AI Response'),
    ]

    ticket = models.ForeignKey(ProjectTicket, on_delete=models.CASCADE, related_name="logs")
    task = models.ForeignKey(ProjectTodoList, on_delete=models.SET_NULL, null=True, blank=True, related_name="logs", help_text="Associated task if any")
    log_type = models.CharField(max_length=20, choices=LOG_TYPE_CHOICES, default='command', help_text="Type of log entry")
    command = models.TextField(help_text="The command that was executed (or message content for user/ai messages)")
    explanation = models.TextField(blank=True, null=True, help_text="Explanation of what this command does")
    output = models.TextField(blank=True, null=True, help_text="Output from the command (or AI response content)")
    exit_code = models.IntegerField(null=True, blank=True, help_text="Command exit code")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Log for {self.ticket.name} - {self.log_type}: {self.command[:50]}"

    class Meta:
        ordering = ['created_at', 'id']
        indexes = [
            models.Index(fields=['ticket']),
            models.Index(fields=['task']),
            models.Index(fields=['log_type']),
        ]


def get_ticket_attachment_upload_path(instance, filename):
    """Generate path for ticket attachments grouped by ticket ID"""
    base, ext = os.path.splitext(filename)
    unique_name = f"{uuid.uuid4().hex}{ext}"
    return os.path.join('ticket_attachments', str(instance.ticket.id), unique_name)


class ProjectTicketAttachment(models.Model):
    """Files/screenshots associated with a ticket"""
    ticket = models.ForeignKey(ProjectTicket, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='ticket_attachments')
    file = models.FileField(upload_to=get_ticket_attachment_upload_path)
    original_filename = models.CharField(max_length=255, blank=True)
    file_type = models.CharField(max_length=100, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at', '-id']

    def __str__(self):
        return self.original_filename or os.path.basename(self.file.name)

class ProjectCodeGeneration(models.Model):
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="code_generation")
    folder_name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.project.name} - Code Generation Folder: {self.folder_name}"

class ProjectFile(models.Model):
    """Model to store different types of project files (PRD, implementation, etc.)"""
    FILE_TYPES = [
        ('prd', 'prd'),
        ('implementation', 'technical plan'),
        ('design', 'design'),
        ('test', 'test plan'),
        ('other', 'other'),
    ]
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='files')
    name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=50, choices=FILE_TYPES)
    content = models.TextField(blank=True, null=True)  # Now optional, as content may be in S3
    s3_key = models.CharField(max_length=500, blank=True, null=True)  # S3 object key
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('project', 'name', 'file_type')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'file_type', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.project.name} - {self.name} ({self.get_file_type_display()})"
    
    @property
    def file_content(self):
        """Get file content from database or S3"""
        # If content is stored in database, return it
        if self.content:
            return self.content
        
        # If content is in S3, fetch it
        if self.s3_key:
            from factory.file_storage import get_file_storage
            storage = get_file_storage()
            
            # For S3 storage, we need to extract project_name and file_path from s3_key
            # S3 key format: prefix/project_name/file_path
            if hasattr(storage, 's3_client'):  # Check if it's S3 storage
                try:
                    response = storage.s3_client.get_object(
                        Bucket=storage.bucket_name,
                        Key=self.s3_key
                    )
                    return response['Body'].read().decode('utf-8')
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error fetching content from S3: {e}")
                    return None
        
        return None
    
    def save_content(self, content_text, user=None, change_description=None):
        """Save content to S3 or database based on settings and create a version"""
        from factory.file_storage import get_file_storage
        from django.conf import settings
        
        # Create a version before saving new content
        if self.pk:  # Only create version if this is an existing file
            self.create_version(user=user, change_description=change_description)
        
        storage = get_file_storage()
        
        # Check if we should use S3
        if getattr(settings, 'FILE_STORAGE_TYPE', 'local').lower() == 's3':
            # Generate S3 key
            s3_key = f"project_files/{self.project.project_id}/{self.file_type}/{self.name}"
            
            # Save to S3
            try:
                storage.s3_client.put_object(
                    Bucket=storage.bucket_name,
                    Key=s3_key,
                    Body=content_text.encode('utf-8'),
                    ContentType='text/plain',
                    ContentEncoding='utf-8'
                )
                
                # Store S3 key and clear content field
                self.s3_key = s3_key
                self.content = None
                
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Saved ProjectFile content to S3: {s3_key}")
                
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error saving to S3, falling back to database: {e}")
                # Fall back to database storage
                self.content = content_text
                self.s3_key = None
        else:
            # Use database storage
            self.content = content_text
            self.s3_key = None
    
    def create_version(self, user=None, change_description=None):
        """Create a new version of the file with current content"""
        # Get the current content
        current_content = self.file_content
        if current_content is None:
            return None
            
        # Get the next version number
        last_version = self.versions.first()
        next_version_number = (last_version.version_number + 1) if last_version else 1
        
        # Create the version
        version = ProjectFileVersion.objects.create(
            file=self,
            version_number=next_version_number,
            content=current_content,
            created_by=user,
            change_description=change_description
        )
        
        return version
    
    def get_version(self, version_number):
        """Get a specific version of the file"""
        try:
            return self.versions.get(version_number=version_number)
        except ProjectFileVersion.DoesNotExist:
            return None
    
    def restore_version(self, version_number, user=None):
        """Restore the file to a specific version"""
        version = self.get_version(version_number)
        if version:
            # Save current as a new version first
            self.save_content(version.content, user=user, 
                            change_description=f"Restored to version {version_number}")
            self.save()
            return True
        return False


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


class ProjectFileVersion(models.Model):
    """Model to store versions of project files"""
    file = models.ForeignKey(ProjectFile, on_delete=models.CASCADE, related_name='versions')
    version_number = models.IntegerField()
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='file_versions')
    change_description = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-version_number']
        unique_together = [('file', 'version_number')]
        indexes = [
            models.Index(fields=['file', '-version_number']),
            models.Index(fields=['file', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.file.name} - v{self.version_number}"


class ProjectMember(models.Model):
    """Model to represent project membership and access control"""
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('member', 'Member'),
        ('viewer', 'Viewer'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('pending', 'Pending'),
        ('inactive', 'Inactive'),
    ]
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='project_memberships')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='member')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    
    # Permissions
    can_edit_files = models.BooleanField(default=True)
    can_manage_tickets = models.BooleanField(default=True)
    can_chat = models.BooleanField(default=True)
    can_invite_members = models.BooleanField(default=False)
    
    # Timestamps
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    invited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='project_members_invited')
    
    class Meta:
        unique_together = ['project', 'user']
        verbose_name = "Project Member"
        verbose_name_plural = "Project Members"
    
    def __str__(self):
        return f"{self.user.username} - {self.project.name} ({self.role})"
    
    @property
    def can_manage_project(self):
        """Check if user can manage project settings"""
        return self.role in ['owner', 'admin']
    
    @property
    def can_delete_project(self):
        """Check if user can delete the project"""
        return self.role == 'owner'
    
    def get_permissions(self):
        """Get all permissions for this member"""
        base_permissions = {
            'can_edit_files': self.can_edit_files,
            'can_manage_tickets': self.can_manage_tickets,
            'can_chat': self.can_chat,
            'can_invite_members': self.can_invite_members,
            'can_manage_project': self.can_manage_project,
            'can_delete_project': self.can_delete_project,
        }
        
        # Override permissions based on role
        if self.role == 'viewer':
            base_permissions.update({
                'can_edit_files': False,
                'can_manage_tickets': False,
                'can_invite_members': False,
            })
        elif self.role == 'admin':
            base_permissions.update({
                'can_invite_members': True,
            })
        elif self.role == 'owner':
            base_permissions.update({
                'can_edit_files': True,
                'can_manage_tickets': True,
                'can_chat': True,
                'can_invite_members': True,
            })
        
        return base_permissions


class ProjectInvitation(models.Model):
    """Model to handle project invitations"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='invitations')
    inviter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='project_invitations_sent')
    email = models.EmailField()
    role = models.CharField(max_length=10, choices=ProjectMember.ROLE_CHOICES, default='member')
    
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
        verbose_name = "Project Invitation"
        verbose_name_plural = "Project Invitations"
        unique_together = ['project', 'email']
    
    def __str__(self):
        return f"Invitation to {self.email} for {self.project.name}"
    
    @classmethod
    def create_invitation(cls, project, inviter, email, role='member'):
        """Create a new invitation with a secure token"""
        import secrets
        from datetime import timedelta
        from django.utils import timezone
        
        # Cancel any existing pending invitations for this email/project
        cls.objects.filter(
            project=project,
            email=email,
            status='pending'
        ).update(status='expired')
        
        # Create new invitation
        token = secrets.token_urlsafe(48)
        expires_at = timezone.now() + timedelta(days=7)  # 7 days to accept
        
        return cls.objects.create(
            project=project,
            inviter=inviter,
            email=email,
            role=role,
            token=token,
            expires_at=expires_at
        )
    
    def is_valid(self):
        """Check if invitation is still valid"""
        from django.utils import timezone
        return (
            self.status == 'pending' and 
            timezone.now() < self.expires_at
        )
    
    def accept(self, user):
        """Accept the invitation and create project membership"""
        from django.utils import timezone
        from accounts.models import Organization, OrganizationMembership
        
        if not self.is_valid():
            raise ValueError("Invitation is not valid")
        
        if user.email.lower() != self.email.lower():
            raise ValueError("User email doesn't match invitation email")
        
        # Create project membership
        membership, created = ProjectMember.objects.get_or_create(
            user=user,
            project=self.project,
            defaults={
                'role': self.role,
                'invited_by': self.inviter,
                'status': 'active'
            }
        )
        
        # Add user to project owner's organization if they're not already a member
        if self.project.owner.profile.current_organization:
            org = self.project.owner.profile.current_organization
            if not org.is_member(user):
                OrganizationMembership.objects.get_or_create(
                    user=user,
                    organization=org,
                    defaults={'role': 'member', 'status': 'active'}
                )
                
                # Set as current organization if user doesn't have one
                if not user.profile.current_organization:
                    user.profile.current_organization = org
                    user.profile.save()
        
        # Mark invitation as accepted
        self.status = 'accepted'
        self.responded_at = timezone.now()
        self.save()
        
        return membership
    
