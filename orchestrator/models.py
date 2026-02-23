import uuid
from django.db import models
from django.contrib.auth.models import User


class AgentRun(models.Model):
    """A single orchestrator run triggered by a user request."""

    RUN_TYPE_CHOICES = [
        ('direct_response', 'Direct Response'),
        ('research', 'Research Task'),
        ('single_ticket', 'Single Ticket Execution'),
        ('pipeline', 'Ticket Pipeline'),
    ]

    STATUS_CHOICES = [
        ('planning', 'Planning'),
        ('executing', 'Executing'),
        ('waiting_on_user', 'Waiting on User'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        'chat.Conversation', on_delete=models.CASCADE, related_name='agent_runs'
    )
    project = models.ForeignKey(
        'projects.Project', on_delete=models.CASCADE, related_name='agent_runs'
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='agent_runs')

    trigger_message = models.TextField()

    run_type = models.CharField(
        max_length=50, choices=RUN_TYPE_CHOICES, default='direct_response'
    )

    # Orchestrator's plan — ordered list of work items
    plan = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planning')

    # Orchestrator's conversation history with the LLM (multi-turn reasoning)
    orchestrator_messages = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['conversation', 'status']),
            models.Index(fields=['project', 'status']),
        ]

    def __str__(self):
        return f"AgentRun {self.id} [{self.status}] - {self.run_type}"


class TicketExecution(models.Model):
    """A single unit of work dispatched to a worker agent."""

    EXECUTION_TYPE_CHOICES = [
        ('research', 'Research'),
        ('create_document', 'Create Document'),
        ('create_prd', 'Create PRD'),
        ('code_implementation', 'Code Implementation'),
        ('code_review', 'Code Review'),
        ('test_writing', 'Test Writing'),
        ('bug_fix', 'Bug Fix'),
        ('knowledge_lookup', 'Knowledge Lookup'),
        ('user_task', 'User Task'),
    ]

    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('ready', 'Ready'),
        ('running', 'Running'),
        ('blocked', 'Blocked'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('skipped', 'Skipped'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent_run = models.ForeignKey(
        AgentRun, on_delete=models.CASCADE, related_name='ticket_executions'
    )

    # Link to actual ProjectTicket if one was created
    ticket = models.ForeignKey(
        'projects.ProjectTicket', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='executions'
    )

    title = models.CharField(max_length=500)
    description = models.TextField()
    execution_type = models.CharField(max_length=50, choices=EXECUTION_TYPE_CHOICES)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')

    # Ordering within the pipeline
    sequence_number = models.IntegerField(default=0)

    # Dependencies (other TicketExecutions that must complete first)
    depends_on = models.ManyToManyField(
        'self', symmetrical=False, blank=True, related_name='blocks'
    )

    # Context passed to the worker
    worker_context = models.JSONField(default=dict, blank=True)

    # Results from the worker
    result = models.JSONField(null=True, blank=True)

    # Blocking info
    blocked_reason = models.TextField(null=True, blank=True)
    blocked_question = models.TextField(null=True, blank=True)
    user_response = models.TextField(null=True, blank=True)

    # Worker assignment (Django-Q task ID)
    task_id = models.CharField(max_length=255, null=True, blank=True)
    worker_type = models.CharField(max_length=50, null=True, blank=True)

    # Timing
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['sequence_number', 'created_at']
        indexes = [
            models.Index(fields=['agent_run', 'status']),
            models.Index(fields=['status', 'sequence_number']),
        ]

    def __str__(self):
        return f"TicketExecution {self.id} [{self.status}] - {self.title[:60]}"


class AgentEvent(models.Model):
    """Immutable event log for all agent activity."""

    EVENT_TYPE_CHOICES = [
        # Orchestrator events
        ('run_started', 'Run Started'),
        ('plan_created', 'Plan Created'),
        ('ticket_dispatched', 'Ticket Dispatched'),
        ('run_completed', 'Run Completed'),
        ('run_failed', 'Run Failed'),
        # Worker events
        ('ticket_started', 'Ticket Started'),
        ('ticket_progress', 'Ticket Progress'),
        ('ticket_completed', 'Ticket Completed'),
        ('ticket_failed', 'Ticket Failed'),
        ('ticket_blocked', 'Ticket Blocked'),
        # Interaction events
        ('user_question', 'Question for User'),
        ('user_response', 'User Response'),
        ('env_var_needed', 'Environment Variable Needed'),
        ('env_var_created', 'Environment Variable Created'),
        ('bug_reported', 'Bug Reported'),
        ('bug_routed', 'Bug Routed'),
        # Knowledge events
        ('knowledge_lookup', 'Knowledge Lookup'),
        ('document_created', 'Document Created'),
        # Bridge events (from existing pipeline → orchestrator)
        ('project_ticket_completed', 'Project Ticket Completed'),
        ('project_ticket_failed', 'Project Ticket Failed'),
        ('project_ticket_blocked', 'Project Ticket Blocked'),
        # Automated checks
        ('preview_check_completed', 'Preview Check Completed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent_run = models.ForeignKey(
        AgentRun, on_delete=models.CASCADE, related_name='events'
    )
    ticket_execution = models.ForeignKey(
        TicketExecution, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='events'
    )

    event_type = models.CharField(max_length=50, choices=EVENT_TYPE_CHOICES)
    payload = models.JSONField(default=dict)
    requires_user_action = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['agent_run', 'event_type']),
            models.Index(fields=['requires_user_action', 'created_at']),
        ]

    def __str__(self):
        return f"AgentEvent {self.event_type} @ {self.created_at}"
