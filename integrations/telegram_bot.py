"""Thin wrapper around the Telegram Bot API."""
import logging

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = 'https://api.telegram.org'


def _url(token: str, method: str) -> str:
    return f'{TELEGRAM_API_BASE}/bot{token}/{method}'


def get_me(token: str) -> dict | None:
    """Verify the bot token and return bot info."""
    try:
        resp = requests.get(_url(token, 'getMe'), timeout=10)
        data = resp.json()
        if data.get('ok'):
            return data['result']
        logger.error(f"Telegram getMe error: {data}")
    except Exception as e:
        logger.error(f"Telegram getMe exception: {e}")
    return None


def set_webhook(token: str, webhook_url: str) -> bool:
    """Register a webhook URL with Telegram."""
    try:
        resp = requests.post(
            _url(token, 'setWebhook'),
            json={'url': webhook_url},
            timeout=10,
        )
        data = resp.json()
        if data.get('ok'):
            logger.info(f"Telegram webhook set to {webhook_url}")
            return True
        logger.error(f"Telegram setWebhook error: {data}")
    except Exception as e:
        logger.error(f"Telegram setWebhook exception: {e}")
    return False


def delete_webhook(token: str) -> bool:
    """Remove the current webhook."""
    try:
        resp = requests.post(_url(token, 'deleteWebhook'), timeout=10)
        return resp.json().get('ok', False)
    except Exception as e:
        logger.error(f"Telegram deleteWebhook exception: {e}")
    return False


def send_message(token: str, chat_id: str, text: str) -> dict | None:
    """Send a text message to a Telegram chat."""
    try:
        resp = requests.post(
            _url(token, 'sendMessage'),
            json={'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'},
            timeout=15,
        )
        data = resp.json()
        if not data.get('ok'):
            logger.error(f"Telegram sendMessage error: {data}")
        return data
    except Exception as e:
        logger.error(f"Telegram sendMessage exception: {e}")
    return None
