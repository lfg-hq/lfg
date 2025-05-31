from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse

# Create your models here.
class Project(models.Model):
    name = models.CharField(max_length=255)
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
    
    def __str__(self):
        return self.name
    
    def get_absolute_url(self):
        return reverse('project_detail', kwargs={'project_id': self.id})
        
    def get_chat_url(self):
        """Get URL for the latest conversation or create a new one"""
        latest_conversation = self.direct_conversations.order_by('-updated_at').first()
        if latest_conversation:
            return reverse('conversation_detail', kwargs={'conversation_id': latest_conversation.id})
        return reverse('create_conversation', kwargs={'project_id': self.id})

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
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="prd")
    prd = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.project.name} - PRD"

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
    
    
class ProjectTickets(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tickets")
    feature = models.ForeignKey(ProjectFeature, on_delete=models.CASCADE, related_name="tickets")
    ticket_id = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=(
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('agent', 'Agent'),
        ('closed', 'Closed'),
    ), default='open')
    backend_tasks = models.TextField(default='')
    frontend_tasks = models.TextField(default='')
    implementation_steps = models.TextField(default='')
    test_case = models.TextField(default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
class ProjectChecklist(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="checklist")
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=(
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('agent', 'Agent'),
        ('closed', 'Closed'),
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.project.name} - Checklist"
    
class ProjectCodeGeneration(models.Model):
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="code_generation")
    folder_name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.project.name} - Code Generation Folder: {self.folder_name}"
    
    