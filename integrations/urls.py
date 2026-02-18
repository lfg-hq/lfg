from django.urls import path
from . import views

app_name = 'integrations'

urlpatterns = [
    # Slack
    path('slack/connect/', views.slack_connect, name='slack_connect'),
    path('slack/oauth/callback/', views.slack_oauth_callback, name='slack_oauth_callback'),
    path('slack/disconnect/', views.slack_disconnect, name='slack_disconnect'),
    path('slack/channels/', views.slack_channels_list, name='slack_channels_list'),
    path('slack/webhook/', views.slack_webhook, name='slack_webhook'),

    # Telegram
    path('telegram/connect/', views.telegram_connect, name='telegram_connect'),
    path('telegram/disconnect/', views.telegram_disconnect, name='telegram_disconnect'),
    path('telegram/generate-link/', views.telegram_generate_link, name='telegram_generate_link'),
    path('telegram/webhook/', views.telegram_webhook, name='telegram_webhook'),

    # Channel ↔ Project linking
    path('channels/link/', views.channel_link, name='channel_link'),
    path('channels/unlink/<int:link_id>/', views.channel_unlink, name='channel_unlink'),
]
