from django.contrib import admin
from .models import Project, ProjectMember, ProjectInvitation

# Register your models here.
@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('name', 'description', 'owner__username')
    date_hierarchy = 'created_at'


@admin.register(ProjectMember)
class ProjectMemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'project', 'role', 'status', 'joined_at')
    list_filter = ('role', 'status', 'joined_at')
    search_fields = ('user__username', 'user__email', 'project__name')
    date_hierarchy = 'joined_at'
    raw_id_fields = ('user', 'project', 'invited_by')


@admin.register(ProjectInvitation)
class ProjectInvitationAdmin(admin.ModelAdmin):
    list_display = ('email', 'project', 'role', 'status', 'created_at', 'expires_at')
    list_filter = ('role', 'status', 'created_at')
    search_fields = ('email', 'project__name', 'inviter__username')
    date_hierarchy = 'created_at'
    raw_id_fields = ('project', 'inviter')
    readonly_fields = ('token',)
