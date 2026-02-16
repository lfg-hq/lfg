import uuid

from django.db import models
from django.utils import timezone

from projects.models import Project

# Create your models here.

class DockerSandbox(models.Model):
    """
    Model to store information about Docker sandboxes for projects and conversations.
    """
    STATUS_CHOICES = (
        ('created', 'Created'),
        ('running', 'Running'),
        ('stopped', 'Stopped'),
        ('error', 'Error'),
    )
    
    project_id = models.CharField(max_length=255, blank=True, null=True, 
                                 help_text="Project identifier associated with this sandbox")
    conversation_id = models.CharField(max_length=255, blank=True, null=True,
                                      help_text="Conversation identifier associated with this sandbox")
    container_id = models.CharField(max_length=255, help_text="Docker container ID")
    container_name = models.CharField(max_length=255, help_text="Docker container name")
    image = models.CharField(max_length=255, help_text="Docker image used")
    code_dir = models.CharField(max_length=512, blank=True, null=True, 
                               help_text="Directory containing the code for this sandbox")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='created', 
                             help_text="Current status of the sandbox")
    resource_limits = models.JSONField(blank=True, null=True, 
                                      help_text="Resource limits applied to the container")
    created_at = models.DateTimeField(auto_now_add=True, help_text="When the sandbox was created")
    updated_at = models.DateTimeField(auto_now=True, help_text="When the sandbox was last updated")
    started_at = models.DateTimeField(blank=True, null=True, help_text="When the sandbox was started")
    stopped_at = models.DateTimeField(blank=True, null=True, help_text="When the sandbox was stopped")
    
    class Meta:
        indexes = [
            models.Index(fields=['project_id']),
            models.Index(fields=['conversation_id']),
            models.Index(fields=['container_id']),
            models.Index(fields=['status']),
        ]
        # Add uniqueness constraints
        constraints = [
            models.UniqueConstraint(
                fields=['project_id'], 
                condition=models.Q(conversation_id__isnull=True),
                name='unique_project_sandbox'
            ),
            models.UniqueConstraint(
                fields=['conversation_id'], 
                condition=models.Q(project_id__isnull=True),
                name='unique_conversation_sandbox'
            ),
            models.UniqueConstraint(
                fields=['project_id', 'conversation_id'],
                condition=models.Q(project_id__isnull=False, conversation_id__isnull=False),
                name='unique_project_conversation_sandbox'
            ),
        ]
        verbose_name = "Docker Sandbox"
        verbose_name_plural = "Docker Sandboxes"
    
    def __str__(self):
        return f"Sandbox {self.container_name} ({self.status})"
    
    def mark_as_running(self, container_id=None, port=None, code_dir=None):
        """Mark the sandbox as running with the given container ID and port."""
        self.status = 'running'
        self.started_at = timezone.now()
        
        if container_id:
            self.container_id = container_id
        
        if port is not None:
            self.port = port
            
        if code_dir is not None:
            self.code_dir = code_dir
            
        self.save()
    
    def mark_as_stopped(self):
        """Mark the sandbox as stopped."""
        self.status = 'stopped'
        self.stopped_at = timezone.now()
        self.save()
    
    def mark_as_error(self):
        """Mark the sandbox as having an error."""
        self.status = 'error'
        self.save()


class DockerPortMapping(models.Model):
    """
    Model to store port mappings for Docker sandboxes.
    Each Docker sandbox can have multiple port mappings.
    """
    sandbox = models.ForeignKey(
        DockerSandbox,
        on_delete=models.CASCADE,
        related_name='port_mappings',
        help_text="Docker sandbox this port mapping belongs to"
    )
    container_port = models.IntegerField(
        help_text="Port number inside the container"
    )
    host_port = models.IntegerField(
        help_text="Port number on the host machine mapped to the container port"
    )
    command = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="Command associated with this port (e.g., service running on this port)"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the port mapping was created"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When the port mapping was last updated"
    )
    
    class Meta:
        indexes = [
            models.Index(fields=['sandbox']),
            models.Index(fields=['container_port']),
            models.Index(fields=['host_port']),
        ]
        verbose_name = "Docker Port Mapping"
        verbose_name_plural = "Docker Port Mappings"
        unique_together = [
            ('sandbox', 'container_port'),
            ('sandbox', 'host_port'),
        ]
    
    def __str__(self):
        return f"{self.host_port}:{self.container_port} for {self.sandbox.container_name}"


class Sandbox(models.Model):
    """Persistent Mags VM used for Turbo mode remote environments."""

    STATUS_CHOICES = (
        ('provisioning', 'Provisioning'),
        ('ready', 'Ready'),
        ('sleeping', 'Sleeping'),
        ('stopped', 'Stopped'),
        ('error', 'Error'),
    )

    WORKSPACE_TYPE_CHOICES = (
        ('execute', 'Ticket Execution'),
        ('claude_auth', 'Claude Code Auth'),
        ('preview', 'Preview'),
    )

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="sandboxes",
        blank=True,
        null=True,
        help_text="Project associated with this sandbox"
    )
    user = models.ForeignKey(
        'auth.User',
        on_delete=models.CASCADE,
        related_name="sandboxes",
        blank=True,
        null=True,
        help_text="User associated with this sandbox (for user-level workspaces like Claude auth)"
    )
    workspace_type = models.CharField(
        max_length=20,
        choices=WORKSPACE_TYPE_CHOICES,
        default='execute',
        help_text="Purpose of this workspace"
    )
    conversation_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Conversation identifier associated with this workspace"
    )
    job_id = models.CharField(
        max_length=255,
        unique=True,
        help_text="Magpie job identifier"
    )
    workspace_id = models.CharField(
        max_length=255,
        unique=True,
        help_text="Workspace identifier used by the AI agent"
    )
    # Mags API fields
    mags_job_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Mags job request_id"
    )
    mags_workspace_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text="Mags workspace overlay name"
    )
    mags_base_workspace_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Mags base workspace (for forked workspaces)"
    )
    ssh_host = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="SSH host for Mags workspace"
    )
    ssh_port = models.IntegerField(
        blank=True,
        null=True,
        help_text="SSH port for Mags workspace"
    )
    ssh_private_key = models.TextField(
        blank=True,
        null=True,
        help_text="SSH private key for Mags workspace"
    )
    ipv6_address = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="IPv6 (or IPv4) address assigned to the VM"
    )
    proxy_url = models.URLField(
        max_length=512,
        blank=True,
        null=True,
        help_text="Public HTTPS proxy URL for accessing the workspace"
    )
    project_path = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="Primary project directory inside the VM"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='provisioning',
        help_text="Current lifecycle status of the workspace"
    )
    metadata = models.JSONField(
        blank=True,
        null=True,
        help_text="Arbitrary metadata including project summary, last restart, etc."
    )
    cli_session_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Claude Code CLI session ID for resuming conversations"
    )
    last_seen_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Timestamp when the workspace was last verified"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "development_sandbox"
        indexes = [
            models.Index(fields=['project']),
            models.Index(fields=['conversation_id']),
            models.Index(fields=['workspace_id']),
            models.Index(fields=['status']),
            models.Index(fields=['user', 'workspace_type']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['conversation_id'],
                condition=models.Q(conversation_id__isnull=False),
                name='unique_sandbox_conversation'
            ),
            models.UniqueConstraint(
                fields=['user', 'workspace_type'],
                condition=models.Q(user__isnull=False, workspace_type='claude_auth'),
                name='unique_user_workspace_type'
            ),
            models.UniqueConstraint(
                fields=['mags_workspace_id'],
                condition=models.Q(mags_workspace_id__isnull=False),
                name='unique_mags_workspace_id'
            ),
        ]
        verbose_name = "Sandbox"
        verbose_name_plural = "Sandboxes"

    def __str__(self):
        identifier = self.project.provided_name if self.project and self.project.provided_name else self.workspace_id
        return f"Sandbox {identifier} ({self.status})"

    def get_ssh_credentials(self) -> dict | None:
        """Return SSH credentials dict if all fields are set, else None."""
        if self.ssh_host and self.ssh_port and self.ssh_private_key:
            return {
                "ssh_host": self.ssh_host,
                "ssh_port": self.ssh_port,
                "ssh_private_key": self.ssh_private_key,
            }
        return None

    def save_ssh_credentials(self, credentials: dict):
        """Save SSH credentials from Mags enable_ssh_access response."""
        self.ssh_host = credentials.get("ssh_host")
        self.ssh_port = credentials.get("ssh_port")
        self.ssh_private_key = credentials.get("ssh_private_key")
        self.save(update_fields=["ssh_host", "ssh_port", "ssh_private_key", "updated_at"])

    def mark_ready(self, ipv6=None, project_path=None, metadata=None, proxy_url=None):
        """Mark the workspace as ready and update connection details."""
        self.status = 'ready'
        self.last_seen_at = timezone.now()
        if ipv6:
            self.ipv6_address = ipv6
        if project_path:
            self.project_path = project_path
        if proxy_url:
            self.proxy_url = proxy_url
        if metadata:
            current_metadata = self.metadata or {}
            current_metadata.update(metadata)
            self.metadata = current_metadata
        self.save()

    def mark_error(self, metadata=None):
        """Mark the workspace as errored."""
        self.status = 'error'
        self.last_seen_at = timezone.now()
        if metadata:
            current_metadata = self.metadata or {}
            current_metadata.update(metadata)
            self.metadata = current_metadata
        self.save()



class KubernetesPod(models.Model):
    """
    Model to store information about Kubernetes pods for projects and conversations.
    """
    STATUS_CHOICES = (
        ('created', 'Created'),
        ('running', 'Running'),
        ('stopped', 'Stopped'),
        ('error', 'Error'),
    )
    
    project_id = models.CharField(max_length=255, blank=True, null=True, 
                                 help_text="Project identifier associated with this pod")
    conversation_id = models.CharField(max_length=255, blank=True, null=True,
                                      help_text="Conversation identifier associated with this pod")
    pod_name = models.CharField(max_length=255, help_text="Kubernetes pod name")
    namespace = models.CharField(max_length=255, help_text="Kubernetes namespace")
    image = models.CharField(max_length=255, help_text="Container image used")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='created', 
                             help_text="Current status of the pod")
    resource_limits = models.JSONField(blank=True, null=True, 
                                      help_text="Resource limits applied to the pod")
    service_details = models.JSONField(blank=True, null=True,
                                      help_text="Details of the associated services (ports, node ports, etc.)")
    ssh_connection_details = models.JSONField(blank=True, null=True,
                                            help_text="SSH connection details for the k8s host server")
    # New fields for direct Kubernetes API access
    cluster_host = models.CharField(max_length=255, blank=True, null=True,
                                  help_text="Kubernetes cluster API server host")
    kubeconfig = models.JSONField(blank=True, null=True,
                                help_text="Kubernetes config as JSON for direct API access")
    token = models.TextField(blank=True, null=True,
                           help_text="Kubernetes API token for authentication")
    created_at = models.DateTimeField(auto_now_add=True, help_text="When the pod was created")
    updated_at = models.DateTimeField(auto_now=True, help_text="When the pod was last updated")
    started_at = models.DateTimeField(blank=True, null=True, help_text="When the pod was started")
    stopped_at = models.DateTimeField(blank=True, null=True, help_text="When the pod was stopped")
    
    class Meta:
        indexes = [
            models.Index(fields=['project_id']),
            models.Index(fields=['conversation_id']),
            models.Index(fields=['pod_name']),
            models.Index(fields=['namespace']),
            models.Index(fields=['status']),
        ]
        # Add uniqueness constraints
        constraints = [
            models.UniqueConstraint(
                fields=['project_id'], 
                condition=models.Q(conversation_id__isnull=True),
                name='unique_project_pod'
            ),
            models.UniqueConstraint(
                fields=['conversation_id'], 
                condition=models.Q(project_id__isnull=True),
                name='unique_conversation_pod'
            ),
            models.UniqueConstraint(
                fields=['project_id', 'conversation_id'],
                condition=models.Q(project_id__isnull=False, conversation_id__isnull=False),
                name='unique_project_conversation_pod'
            ),
        ]
        verbose_name = "Kubernetes Pod"
        verbose_name_plural = "Kubernetes Pods"
    
    def __str__(self):
        return f"Pod {self.pod_name} in {self.namespace} ({self.status})"
    
    def mark_as_running(self, pod_name=None, service_details=None):
        """Mark the pod as running with the given details."""
        self.status = 'running'
        self.started_at = timezone.now()
        
        if pod_name:
            self.pod_name = pod_name
            
        if service_details is not None:
            self.service_details = service_details
            
        self.save()
    
    def mark_as_stopped(self):
        """Mark the pod as stopped."""
        self.status = 'stopped'
        self.stopped_at = timezone.now()
        self.save()
    
    def mark_as_error(self):
        """Mark the pod as having an error."""
        self.status = 'error'
        self.save()


class KubernetesPortMapping(models.Model):
    """
    Model to store port mappings for Kubernetes pods.
    Each Kubernetes pod can have multiple port mappings for different services.
    """
    pod = models.ForeignKey(
        KubernetesPod,
        on_delete=models.CASCADE,
        related_name='port_mappings',
        help_text="Kubernetes pod this port mapping belongs to"
    )
    container_name = models.CharField(
        max_length=255,
        help_text="Name of the container within the pod"
    )
    container_port = models.IntegerField(
        help_text="Port number inside the container"
    )
    service_port = models.IntegerField(
        help_text="Port number on the Kubernetes service"
    )
    node_port = models.IntegerField(
        blank=True,
        null=True,
        help_text="NodePort value if exposed via NodePort service type"
    )
    protocol = models.CharField(
        max_length=10,
        default="TCP",
        help_text="Protocol for this port (TCP, UDP)"
    )
    service_name = models.CharField(
        max_length=255,
        help_text="Name of the service exposing this port"
    )
    description = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="Description of the service running on this port"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the port mapping was created"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When the port mapping was last updated"
    )
    
    class Meta:
        indexes = [
            models.Index(fields=['pod']),
            models.Index(fields=['container_name']),
            models.Index(fields=['service_name']),
            models.Index(fields=['container_port']),
        ]
        verbose_name = "Kubernetes Port Mapping"
        verbose_name_plural = "Kubernetes Port Mappings"
        unique_together = [
            ('pod', 'container_name', 'container_port'),
        ]
    
    def __str__(self):
        return f"{self.service_name}: {self.container_port} ({self.container_name}) for pod {self.pod.pod_name}"


class CommandExecutionOld(models.Model):
    """
    Model to store history of commands executed in the system.
    """
    project_id = models.CharField(max_length=255, blank=True, null=True)
    ticket_id = models.IntegerField(blank=True, null=True, help_text="Ticket ID that initiated this command")
    command = models.TextField(help_text="The command that was executed")
    explanation = models.TextField(blank=True, null=True, help_text="Explanation of what this command does")
    output = models.TextField(blank=True, null=True, help_text="Output from the command")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['project_id']),
            models.Index(fields=['ticket_id']),
        ]

    def __str__(self):
        return f"Command: {self.command[:50]}{'...' if len(self.command) > 50 else ''}"


class InstantApp(models.Model):
    """Instant Mode app — a lightweight, self-contained app with its own sandbox."""

    STATUS_CHOICES = (
        ('gathering', 'Gathering Requirements'),
        ('building', 'Building'),
        ('running', 'Running'),
        ('stopped', 'Stopped'),
        ('error', 'Error'),
    )

    app_id = models.CharField(max_length=36, unique=True, default=uuid.uuid4, db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="instant_apps",
    )
    user = models.ForeignKey(
        'auth.User',
        on_delete=models.CASCADE,
        related_name="instant_apps",
    )
    sandbox = models.OneToOneField(
        Sandbox,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="instant_app",
    )
    conversation = models.OneToOneField(
        'chat.Conversation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='gathering')
    requirements = models.TextField(blank=True, null=True)
    env_vars = models.JSONField(default=dict, blank=True)
    preview_url = models.URLField(max_length=512, blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['project']),
            models.Index(fields=['user']),
            models.Index(fields=['status']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"InstantApp {self.name} ({self.status})"


class ServerConfig(models.Model):
    project = models.ForeignKey(Project, 
                               on_delete=models.CASCADE, 
                               related_name="server_configs"
                              )
    command = models.TextField()
    start_server_command = models.TextField(blank=True, null=True, help_text="Command to start the server")
    port = models.IntegerField()
    type = models.CharField(max_length=50, default='application')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'server_configs'
        unique_together = ['project', 'port']
