from django.contrib import admin
from .models import Profile, GitHubToken, TokenUsage, LLMApiKeys, ExternalServicesAPIKeys

admin.site.register(Profile)
admin.site.register(GitHubToken)

@admin.register(LLMApiKeys)
class LLMApiKeysAdmin(admin.ModelAdmin):
    list_display = ('user', 'free_trial', 'has_openai', 'has_anthropic', 'has_xai')
    list_filter = ('free_trial',)
    search_fields = ('user__username', 'user__email')
    
    def has_openai(self, obj):
        return bool(obj.openai_api_key)
    has_openai.boolean = True
    has_openai.short_description = 'OpenAI Key'
    
    def has_anthropic(self, obj):
        return bool(obj.anthropic_api_key)
    has_anthropic.boolean = True
    has_anthropic.short_description = 'Anthropic Key'
    
    def has_xai(self, obj):
        return bool(obj.xai_api_key)
    has_xai.boolean = True
    has_xai.short_description = 'xai Key'

@admin.register(ExternalServicesAPIKeys)
class ExternalServicesAPIKeysAdmin(admin.ModelAdmin):
    list_display = ('user', 'has_linear', 'has_jira', 'has_notion', 'has_google_docs')
    search_fields = ('user__username', 'user__email')
    
    def has_linear(self, obj):
        return bool(obj.linear_api_key)
    has_linear.boolean = True
    has_linear.short_description = 'Linear Key'
    
    def has_jira(self, obj):
        return bool(obj.jira_api_key)
    has_jira.boolean = True
    has_jira.short_description = 'Jira Key'
    
    def has_notion(self, obj):
        return bool(obj.notion_api_key)
    has_notion.boolean = True
    has_notion.short_description = 'Notion Key'
    
    def has_google_docs(self, obj):
        return bool(obj.google_docs_api_key)
    has_google_docs.boolean = True
    has_google_docs.short_description = 'Google Docs Key'

@admin.register(TokenUsage)
class TokenUsageAdmin(admin.ModelAdmin):
    list_display = ('user', 'provider', 'model', 'total_tokens', 'cost', 'timestamp', 'project', 'conversation')
    list_filter = ('provider', 'model', 'timestamp')
    search_fields = ('user__username', 'project__name', 'conversation__title')
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)
    readonly_fields = ('cost',) 