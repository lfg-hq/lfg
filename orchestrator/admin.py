from django.contrib import admin
from .models import AgentRun, TicketExecution, AgentEvent


@admin.register(AgentRun)
class AgentRunAdmin(admin.ModelAdmin):
    list_display = ['id', 'status', 'run_type', 'user', 'project', 'created_at']
    list_filter = ['status', 'run_type']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(TicketExecution)
class TicketExecutionAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'status', 'execution_type', 'sequence_number', 'created_at']
    list_filter = ['status', 'execution_type']
    readonly_fields = ['id', 'created_at']


@admin.register(AgentEvent)
class AgentEventAdmin(admin.ModelAdmin):
    list_display = ['id', 'event_type', 'agent_run', 'requires_user_action', 'created_at']
    list_filter = ['event_type', 'requires_user_action']
    readonly_fields = ['id', 'created_at']
