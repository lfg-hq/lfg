from django.contrib import admin
from .models import Profile, GitHubToken, TokenUsage

admin.site.register(Profile)
admin.site.register(GitHubToken)

@admin.register(TokenUsage)
class TokenUsageAdmin(admin.ModelAdmin):
    list_display = ('user', 'provider', 'model', 'total_tokens', 'cost', 'timestamp', 'project', 'conversation')
    list_filter = ('provider', 'model', 'timestamp')
    search_fields = ('user__username', 'project__name', 'conversation__title')
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)
    readonly_fields = ('cost',) 