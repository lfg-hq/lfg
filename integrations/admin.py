from django.contrib import admin
from .models import SlackIntegration, TelegramIntegration, ChannelProjectLink, ChannelMessage


@admin.register(SlackIntegration)
class SlackIntegrationAdmin(admin.ModelAdmin):
    list_display = ('user', 'team_name', 'is_active', 'connected_at')
    list_filter = ('is_active',)
    search_fields = ('user__username', 'team_name')


@admin.register(TelegramIntegration)
class TelegramIntegrationAdmin(admin.ModelAdmin):
    list_display = ('user', 'bot_username', 'is_active', 'connected_at')
    list_filter = ('is_active',)
    search_fields = ('user__username', 'bot_username')


@admin.register(ChannelProjectLink)
class ChannelProjectLinkAdmin(admin.ModelAdmin):
    list_display = ('user', 'platform', 'channel_name', 'project', 'is_active', 'created_at')
    list_filter = ('platform', 'is_active')
    search_fields = ('user__username', 'channel_name')


@admin.register(ChannelMessage)
class ChannelMessageAdmin(admin.ModelAdmin):
    list_display = ('channel_link', 'direction', 'sender_name', 'created_at')
    list_filter = ('direction',)
    search_fields = ('content', 'sender_name')
    readonly_fields = ('created_at',)
