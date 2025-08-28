from django.contrib import admin
from .models import Profile, GitHubToken, TokenUsage, LLMApiKeys, ExternalServicesAPIKeys, Organization, OrganizationMembership, OrganizationInvitation

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


class OrganizationMembershipInline(admin.TabularInline):
    model = OrganizationMembership
    extra = 0
    readonly_fields = ('joined_at', 'updated_at')
    fields = ('user', 'role', 'status', 'joined_at')


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'member_count', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at', 'allow_member_invites')
    search_fields = ('name', 'owner__username', 'owner__email', 'description')
    readonly_fields = ('slug', 'created_at', 'updated_at', 'member_count')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [OrganizationMembershipInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'description', 'avatar', 'owner')
        }),
        ('Settings', {
            'fields': ('allow_member_invites', 'is_active')
        }),
        ('Billing', {
            'fields': ('stripe_customer_id',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'member_count'),
            'classes': ('collapse',)
        })
    )
    
    def member_count(self, obj):
        return obj.member_count
    member_count.short_description = 'Members'


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization', 'role', 'status', 'joined_at')
    list_filter = ('role', 'status', 'joined_at')
    search_fields = ('user__username', 'user__email', 'organization__name')
    readonly_fields = ('joined_at', 'updated_at')
    
    fieldsets = (
        (None, {
            'fields': ('user', 'organization', 'role', 'status')
        }),
        ('Timestamps', {
            'fields': ('joined_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(OrganizationInvitation)
class OrganizationInvitationAdmin(admin.ModelAdmin):
    list_display = ('email', 'organization', 'role', 'status', 'inviter', 'created_at', 'expires_at')
    list_filter = ('role', 'status', 'created_at', 'expires_at')
    search_fields = ('email', 'organization__name', 'inviter__username')
    readonly_fields = ('token', 'created_at', 'expires_at', 'responded_at')
    
    fieldsets = (
        ('Invitation Details', {
            'fields': ('organization', 'inviter', 'email', 'role')
        }),
        ('Status', {
            'fields': ('status', 'responded_at')
        }),
        ('Security & Timestamps', {
            'fields': ('token', 'created_at', 'expires_at'),
            'classes': ('collapse',)
        })
    )
    
    def has_add_permission(self, request):
        # Prevent creating invitations through admin
        return False 