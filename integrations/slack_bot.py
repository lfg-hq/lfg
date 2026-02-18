"""Thin wrapper around the Slack Web API."""
import hashlib
import hmac
import json
import logging
import time

import requests

logger = logging.getLogger(__name__)

SLACK_API_BASE = 'https://slack.com/api'


def verify_slack_signature(signing_secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    """Verify that a request actually came from Slack."""
    if abs(time.time() - int(timestamp)) > 60 * 5:
        return False
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    computed = 'v0=' + hmac.new(
        signing_secret.encode(), sig_basestring.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, signature)


def send_message(token: str, channel: str, text: str) -> dict:
    """Post a message to a Slack channel."""
    resp = requests.post(
        f'{SLACK_API_BASE}/chat.postMessage',
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        json={'channel': channel, 'text': text},
        timeout=15,
    )
    data = resp.json()
    if not data.get('ok'):
        logger.error(f"Slack chat.postMessage error: {data.get('error')}")
    return data


def get_channels(token: str) -> list:
    """List public channels the bot has been added to."""
    resp = requests.get(
        f'{SLACK_API_BASE}/conversations.list',
        headers={'Authorization': f'Bearer {token}'},
        params={'types': 'public_channel,private_channel', 'limit': 200},
        timeout=15,
    )
    data = resp.json()
    if not data.get('ok'):
        logger.error(f"Slack conversations.list error: {data.get('error')}")
        return []
    return data.get('channels', [])


def exchange_code_for_token(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    """Exchange an OAuth code for a bot token."""
    resp = requests.post(
        f'{SLACK_API_BASE}/oauth.v2.access',
        data={
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'redirect_uri': redirect_uri,
        },
        timeout=15,
    )
    return resp.json()
