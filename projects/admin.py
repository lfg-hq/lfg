from django.contrib import admin
from .models import Project

# Register your models here.
@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('name', 'description', 'owner__username')
    date_hierarchy = 'created_at'
