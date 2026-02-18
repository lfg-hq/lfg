import hashlib
import hmac
import json
import logging
import os
import threading

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import (
    SlackIntegration,
    TelegramIntegration,
    ChannelProjectLink,
    TelegramLinkToken,
)
from . import slack_bot, telegram_bot
from .chat_bridge import process_external_message

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Slack OAuth
# ---------------------------------------------------------------------------

@login_required
@require_POST
def slack_connect(request):
    """Start Slack OAuth flow — redirect user to Slack's authorize URL."""
    client_id = os.environ.get('SLACK_CLIENT_ID', '')
    if not client_id:
        messages.error(request, 'Slack integration is not configured.')
        return redirect('settings')

    base_url = settings.LFG_API_BASE_URL
    redirect_uri = f"{base_url.rstrip('/')}/integrations/slack/oauth/callback/"
    scopes = 'channels:read,chat:write,channels:history'
    state = request.session.session_key or 'no-session'
    request.session['slack_oauth_state'] = state

    url = (
        f"https://slack.com/oauth/v2/authorize"
        f"?client_id={client_id}&scope={scopes}"
        f"&redirect_uri={redirect_uri}&state={state}"
    )
    return redirect(url)


@login_required
def slack_oauth_callback(request):
    """Handle Slack OAuth callback — exchange code for token."""
    code = request.GET.get('code')
    error = request.GET.get('error')
    if error or not code:
        messages.error(request, f'Slack authorization failed: {error or "no code"}')
        return redirect('settings')

    client_id = os.environ.get('SLACK_CLIENT_ID', '')
    client_secret = os.environ.get('SLACK_CLIENT_SECRET', '')
    base_url = settings.LFG_API_BASE_URL
    redirect_uri = f"{base_url.rstrip('/')}/integrations/slack/oauth/callback/"

    data = slack_bot.exchange_code_for_token(client_id, client_secret, code, redirect_uri)
    if not data.get('ok'):
        messages.error(request, f"Slack OAuth error: {data.get('error', 'unknown')}")
        return redirect('settings')

    bot_token = data.get('access_token', '')
    team = data.get('team', {})

    SlackIntegration.objects.update_or_create(
        user=request.user,
        defaults={
            'bot_token': bot_token,
            'team_id': team.get('id', ''),
            'team_name': team.get('name', ''),
            'is_active': True,
        },
    )
    messages.success(request, f"Slack connected to workspace: {team.get('name', '')}")
    return redirect('settings')


@login_required
@require_POST
def slack_disconnect(request):
    """Remove Slack integration."""
    SlackIntegration.objects.filter(user=request.user).delete()
    # Deactivate related channel links
    ChannelProjectLink.objects.filter(user=request.user, platform='slack').update(is_active=False)
    messages.success(request, 'Slack disconnected.')
    return redirect('settings')


@login_required
def slack_channels_list(request):
    """AJAX: list Slack channels for linking UI."""
    try:
        integration = SlackIntegration.objects.get(user=request.user, is_active=True)
    except SlackIntegration.DoesNotExist:
        return JsonResponse({'channels': []})

    channels = slack_bot.get_channels(integration.bot_token)
    return JsonResponse({
        'channels': [{'id': c['id'], 'name': c['name']} for c in channels]
    })


# ---------------------------------------------------------------------------
# Telegram connect / disconnect
# ---------------------------------------------------------------------------

@login_required
@require_POST
def telegram_connect(request):
    """Save Telegram bot token, verify it, and set webhook."""
    bot_token = request.POST.get('bot_token', '').strip()
    if not bot_token:
        messages.error(request, 'Please provide a Telegram bot token.')
        return redirect('settings')

    bot_info = telegram_bot.get_me(bot_token)
    if not bot_info:
        messages.error(request, 'Invalid Telegram bot token.')
        return redirect('settings')

    base_url = settings.LFG_API_BASE_URL
    webhook_url = f"{base_url.rstrip('/')}/integrations/telegram/webhook/"
    telegram_bot.set_webhook(bot_token, webhook_url)

    TelegramIntegration.objects.update_or_create(
        user=request.user,
        defaults={
            'bot_token': bot_token,
            'bot_username': bot_info.get('username', ''),
            'is_active': True,
        },
    )
    messages.success(request, f"Telegram bot connected: @{bot_info.get('username', '')}")
    return redirect('settings')


@login_required
@require_POST
def telegram_disconnect(request):
    """Remove Telegram integration and delete webhook."""
    try:
        integration = TelegramIntegration.objects.get(user=request.user)
        telegram_bot.delete_webhook(integration.bot_token)
        integration.delete()
    except TelegramIntegration.DoesNotExist:
        pass
    ChannelProjectLink.objects.filter(user=request.user, platform='telegram').update(is_active=False)
    messages.success(request, 'Telegram disconnected.')
    return redirect('settings')


@login_required
@require_POST
def telegram_generate_link(request):
    """Generate a Telegram deep-link URL that auto-links a chat to a project."""
    project_id = request.POST.get('project_id', '')
    if not project_id:
        return JsonResponse({'error': 'Missing project_id'}, status=400)

    from projects.models import Project
    try:
        project = Project.objects.get(project_id=project_id, owner=request.user)
    except Project.DoesNotExist:
        return JsonResponse({'error': 'Project not found'}, status=404)

    try:
        integration = TelegramIntegration.objects.get(user=request.user, is_active=True)
    except TelegramIntegration.DoesNotExist:
        return JsonResponse({'error': 'Telegram not connected'}, status=400)

    # Clean up old tokens for this user/project and create a fresh one
    TelegramLinkToken.objects.filter(user=request.user, project=project).delete()
    link_token = TelegramLinkToken.objects.create(user=request.user, project=project)

    deep_link = f"https://t.me/{integration.bot_username}?start={link_token.token}"
    return JsonResponse({
        'deep_link': deep_link,
        'project_name': project.name,
        'bot_username': integration.bot_username,
    })


# ---------------------------------------------------------------------------
# Channel ↔ Project linking
# ---------------------------------------------------------------------------

@login_required
@require_POST
def channel_link(request):
    """Create a ChannelProjectLink."""
    platform = request.POST.get('platform', '')
    project_id = request.POST.get('project_id', '')
    channel_id = request.POST.get('channel_id', '').strip()
    channel_name = request.POST.get('channel_name', '').strip()

    if not all([platform, project_id, channel_id]):
        messages.error(request, 'Missing required fields.')
        return redirect('settings')

    from projects.models import Project
    try:
        project = Project.objects.get(project_id=project_id, owner=request.user)
    except Project.DoesNotExist:
        messages.error(request, 'Project not found.')
        return redirect('settings')

    ChannelProjectLink.objects.update_or_create(
        user=request.user,
        platform=platform,
        channel_id=channel_id,
        defaults={
            'project': project,
            'channel_name': channel_name or channel_id,
            'is_active': True,
        },
    )
    messages.success(request, f'Channel linked to {project.name}.')
    return redirect('settings')


@login_required
@require_POST
def channel_unlink(request, link_id):
    """Deactivate a ChannelProjectLink."""
    link = get_object_or_404(ChannelProjectLink, id=link_id, user=request.user)
    link.is_active = False
    link.save(update_fields=['is_active'])
    messages.success(request, 'Channel unlinked.')
    return redirect('settings')


# ---------------------------------------------------------------------------
# Slack webhook (event subscription)
# ---------------------------------------------------------------------------

@csrf_exempt
def slack_webhook(request):
    """Receive Slack events (url_verification + event_callback)."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    # Verify Slack signature
    signing_secret = os.environ.get('SLACK_SIGNING_SECRET', '')
    if signing_secret:
        timestamp = request.headers.get('X-Slack-Request-Timestamp', '')
        signature = request.headers.get('X-Slack-Signature', '')
        if not slack_bot.verify_slack_signature(signing_secret, timestamp, request.body, signature):
            return HttpResponse('Invalid signature', status=403)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse('Bad request', status=400)

    # Handle URL verification challenge
    if payload.get('type') == 'url_verification':
        return JsonResponse({'challenge': payload.get('challenge', '')})

    # Handle event callbacks
    if payload.get('type') == 'event_callback':
        event = payload.get('event', {})
        if event.get('type') == 'message' and not event.get('bot_id'):
            # Process in a background thread so Slack gets a quick 200
            threading.Thread(
                target=_handle_slack_message, args=(event,), daemon=True
            ).start()

    return HttpResponse(status=200)


def _handle_slack_message(event: dict):
    """Process a single Slack message event (runs in background thread)."""
    channel_id = event.get('channel', '')
    text = event.get('text', '')
    user_id = event.get('user', '')
    ts = event.get('ts', '')

    if not text or not channel_id:
        return

    links = ChannelProjectLink.objects.filter(
        platform='slack', channel_id=channel_id, is_active=True
    ).select_related('user', 'project')

    for link in links:
        try:
            integration = SlackIntegration.objects.get(user=link.user, is_active=True)
        except SlackIntegration.DoesNotExist:
            continue

        try:
            response = process_external_message(
                user=link.user,
                project=link.project,
                message_text=text,
                channel_link=link,
                sender_name=user_id,
                sender_id=user_id,
                platform_message_id=ts,
            )
            slack_bot.send_message(integration.bot_token, channel_id, response)
        except Exception:
            logger.exception(f"Error processing Slack message in channel {channel_id}")


# ---------------------------------------------------------------------------
# Telegram webhook
# ---------------------------------------------------------------------------

@csrf_exempt
def telegram_webhook(request):
    """Receive Telegram updates."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        update = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse('Bad request', status=400)

    message = update.get('message')
    if not message:
        return HttpResponse(status=200)

    chat_id = str(message.get('chat', {}).get('id', ''))
    text = message.get('text', '')
    from_user = message.get('from', {})
    message_id = str(message.get('message_id', ''))

    logger.info(f"[Telegram webhook] chat_id={chat_id}, from={from_user.get('username', '?')}, text={text[:80]}")

    if not text or not chat_id:
        return HttpResponse(status=200)

    # Handle bot commands
    if text.startswith('/start'):
        parts = text.split(maxsplit=1)
        token_str = parts[1].strip() if len(parts) > 1 else ''
        if token_str:
            threading.Thread(
                target=_handle_telegram_deep_link,
                args=(chat_id, token_str, from_user),
                daemon=True,
            ).start()
        else:
            _telegram_reply_to_chat(chat_id, "Welcome to LFG! Link this chat to a project in your LFG settings page.")
        return HttpResponse(status=200)

    if text.startswith('/project'):
        threading.Thread(
            target=_handle_telegram_project_command,
            args=(chat_id, text, from_user),
            daemon=True,
        ).start()
        return HttpResponse(status=200)

    if text.startswith('/help'):
        threading.Thread(
            target=_handle_telegram_help,
            args=(chat_id,),
            daemon=True,
        ).start()
        return HttpResponse(status=200)

    # Route through AI pipeline
    threading.Thread(
        target=_handle_telegram_message,
        args=(chat_id, text, from_user, message_id),
        daemon=True,
    ).start()

    return HttpResponse(status=200)


def _telegram_reply_to_chat(chat_id: str, text: str):
    """Find the Telegram integration for this chat and send a reply."""
    links = ChannelProjectLink.objects.filter(
        platform='telegram', channel_id=chat_id, is_active=True
    ).select_related('user')
    for link in links:
        try:
            integration = TelegramIntegration.objects.get(user=link.user, is_active=True)
            telegram_bot.send_message(integration.bot_token, chat_id, text)
            return
        except TelegramIntegration.DoesNotExist:
            continue


def _handle_telegram_message(chat_id: str, text: str, from_user: dict, message_id: str):
    """Process a single Telegram message (runs in background thread)."""
    links = ChannelProjectLink.objects.filter(
        platform='telegram', channel_id=chat_id, is_active=True
    ).select_related('user', 'project')

    if not links.exists():
        logger.warning(f"[Telegram] No channel link found for chat_id={chat_id}. Link this chat to a project in Settings > Channels.")
        return

    for link in links:
        try:
            integration = TelegramIntegration.objects.get(user=link.user, is_active=True)
        except TelegramIntegration.DoesNotExist:
            continue

        sender_name = from_user.get('first_name', '') + ' ' + from_user.get('last_name', '')
        sender_id = str(from_user.get('id', ''))

        try:
            response = process_external_message(
                user=link.user,
                project=link.project,
                message_text=text,
                channel_link=link,
                sender_name=sender_name.strip(),
                sender_id=sender_id,
                platform_message_id=message_id,
            )
            telegram_bot.send_message(integration.bot_token, chat_id, response)
        except Exception:
            logger.exception(f"Error processing Telegram message in chat {chat_id}")


def _handle_telegram_deep_link(chat_id: str, token_str: str, from_user: dict):
    """Auto-link a Telegram chat to a project using a deep-link token."""
    try:
        link_token = TelegramLinkToken.objects.select_related('user', 'project').get(token=token_str)
    except TelegramLinkToken.DoesNotExist:
        logger.warning(f"[Telegram] Invalid deep-link token: {token_str}")
        return

    if link_token.is_expired:
        link_token.delete()
        logger.warning(f"[Telegram] Expired deep-link token: {token_str}")
        # Try to notify
        try:
            integration = TelegramIntegration.objects.get(user=link_token.user, is_active=True)
            telegram_bot.send_message(integration.bot_token, chat_id, "This link has expired. Please generate a new one from your LFG settings.")
        except TelegramIntegration.DoesNotExist:
            pass
        return

    user = link_token.user
    project = link_token.project
    sender_name = (from_user.get('first_name', '') + ' ' + from_user.get('last_name', '')).strip()

    # Create or reactivate the channel link
    link, created = ChannelProjectLink.objects.update_or_create(
        user=user,
        platform='telegram',
        channel_id=chat_id,
        defaults={
            'project': project,
            'channel_name': sender_name or f"Telegram {chat_id}",
            'is_active': True,
        },
    )

    # Consume the token
    link_token.delete()

    # Send confirmation
    try:
        integration = TelegramIntegration.objects.get(user=user, is_active=True)
        telegram_bot.send_message(
            integration.bot_token, chat_id,
            f"Connected! This chat is now linked to *{project.name}*.\n\nSend any message here and the LFG AI will respond in the context of your project."
        )
    except TelegramIntegration.DoesNotExist:
        logger.error(f"[Telegram] No active integration for user {user.username} after deep-link")


def _handle_telegram_project_command(chat_id: str, text: str, from_user: dict):
    """Handle /project command — list projects or switch active project."""
    from projects.models import Project

    # Find the channel link for this chat
    link = ChannelProjectLink.objects.filter(
        platform='telegram', channel_id=chat_id, is_active=True
    ).select_related('user', 'project').first()

    if not link:
        logger.warning(f"[Telegram] /project command but no link for chat_id={chat_id}")
        return

    user = link.user

    try:
        integration = TelegramIntegration.objects.get(user=user, is_active=True)
    except TelegramIntegration.DoesNotExist:
        return

    projects = list(Project.objects.filter(owner=user).order_by('-created_at'))
    if not projects:
        telegram_bot.send_message(integration.bot_token, chat_id, "You don't have any projects yet.")
        return

    # Parse argument: /project or /project <number or name>
    parts = text.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ''

    if not arg:
        # List projects with numbers
        lines = [f"*Active project:* {link.project.name}\n"]
        lines.append("Switch project with `/project <number>`:\n")
        for i, proj in enumerate(projects, 1):
            marker = " (current)" if proj.id == link.project.id else ""
            lines.append(f"`{i}.` {proj.name}{marker}")
        telegram_bot.send_message(integration.bot_token, chat_id, '\n'.join(lines))
        return

    # Try to match by number
    target_project = None
    if arg.isdigit():
        idx = int(arg) - 1
        if 0 <= idx < len(projects):
            target_project = projects[idx]

    # Try to match by name (case-insensitive partial match)
    if not target_project:
        arg_lower = arg.lower()
        for proj in projects:
            if arg_lower in proj.name.lower():
                target_project = proj
                break

    if not target_project:
        telegram_bot.send_message(
            integration.bot_token, chat_id,
            f"Project not found. Use `/project` to see the list."
        )
        return

    if target_project.id == link.project.id:
        telegram_bot.send_message(
            integration.bot_token, chat_id,
            f"Already on *{target_project.name}*."
        )
        return

    # Switch project — also clear conversation so a new one starts fresh
    link.project = target_project
    link.conversation = None
    link.save(update_fields=['project', 'conversation'])

    telegram_bot.send_message(
        integration.bot_token, chat_id,
        f"Switched to *{target_project.name}*. New messages will use this project's context."
    )


def _handle_telegram_help(chat_id: str):
    """Send help text."""
    link = ChannelProjectLink.objects.filter(
        platform='telegram', channel_id=chat_id, is_active=True
    ).select_related('user').first()

    if not link:
        return

    try:
        integration = TelegramIntegration.objects.get(user=link.user, is_active=True)
    except TelegramIntegration.DoesNotExist:
        return

    help_text = (
        "*LFG Bot Commands*\n\n"
        "`/project` — List your projects\n"
        "`/project <number>` — Switch active project\n"
        "`/project <name>` — Switch by project name\n"
        "`/help` — Show this message\n\n"
        "Any other message is sent to the AI in the context of your active project."
    )
    telegram_bot.send_message(integration.bot_token, chat_id, help_text)
