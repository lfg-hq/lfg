"""
Encryption utilities for secure storage of sensitive data.

Uses Fernet symmetric encryption from the cryptography library.
Encryption key is stored in Django settings as ENV_ENCRYPTION_KEY.
"""
import base64
import logging
import os
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# Lazy-loaded Fernet instance
_fernet = None


def get_encryption_key() -> bytes:
    """
    Get the encryption key from settings or environment.

    The key should be a URL-safe base64-encoded 32-byte key.
    Generate one with: from cryptography.fernet import Fernet; Fernet.generate_key()

    Returns:
        bytes: The encryption key

    Raises:
        ValueError: If no encryption key is configured
    """
    key = getattr(settings, 'ENV_ENCRYPTION_KEY', None)
    if not key:
        key = os.environ.get('ENV_ENCRYPTION_KEY')

    if not key:
        # Generate a default key for development (not recommended for production)
        logger.warning(
            "[ENCRYPTION] No ENV_ENCRYPTION_KEY configured. "
            "Using a default key. SET THIS IN PRODUCTION!"
        )
        # This is a fallback - in production, always set ENV_ENCRYPTION_KEY
        key = b'development-key-do-not-use-in-production!!'
        # Pad or truncate to 32 bytes and base64 encode
        key = base64.urlsafe_b64encode(key[:32].ljust(32, b'='))

    if isinstance(key, str):
        key = key.encode('utf-8')

    return key


def get_fernet():
    """
    Get a Fernet instance for encryption/decryption.

    Returns:
        Fernet: Configured Fernet instance
    """
    global _fernet

    if _fernet is None:
        from cryptography.fernet import Fernet
        key = get_encryption_key()
        _fernet = Fernet(key)

    return _fernet


def encrypt_value(plaintext: str) -> str:
    """
    Encrypt a string value.

    Args:
        plaintext: The value to encrypt

    Returns:
        str: Base64-encoded encrypted value
    """
    if not plaintext:
        return ''

    try:
        fernet = get_fernet()
        encrypted = fernet.encrypt(plaintext.encode('utf-8'))
        return encrypted.decode('utf-8')
    except Exception as e:
        logger.error(f"[ENCRYPTION] Failed to encrypt value: {e}")
        raise


def decrypt_value(encrypted: str) -> str:
    """
    Decrypt an encrypted string value.

    Args:
        encrypted: Base64-encoded encrypted value

    Returns:
        str: Decrypted plaintext value
    """
    if not encrypted:
        return ''

    try:
        fernet = get_fernet()
        decrypted = fernet.decrypt(encrypted.encode('utf-8'))
        return decrypted.decode('utf-8')
    except Exception as e:
        logger.error(f"[ENCRYPTION] Failed to decrypt value: {e}")
        raise


def mask_value(value: str, show_chars: int = 4) -> str:
    """
    Mask a sensitive value for display.

    Args:
        value: The value to mask
        show_chars: Number of characters to show at start and end

    Returns:
        str: Masked value like "abc...xyz"
    """
    if not value:
        return ''

    if len(value) <= show_chars * 2:
        return '*' * len(value)

    return f"{value[:show_chars]}...{value[-show_chars:]}"


def parse_env_file(content: str) -> dict:
    """
    Parse .env file content into a dictionary.

    Handles:
    - KEY=value format
    - Quoted values (single and double quotes)
    - Comments (lines starting with #)
    - Empty lines
    - Export statements (export KEY=value)

    Args:
        content: The .env file content

    Returns:
        dict: Dictionary of key-value pairs
    """
    env_vars = {}

    for line in content.splitlines():
        line = line.strip()

        # Skip empty lines and comments
        if not line or line.startswith('#'):
            continue

        # Handle export statements
        if line.startswith('export '):
            line = line[7:].strip()

        # Find the first = sign
        if '=' not in line:
            continue

        key, _, value = line.partition('=')
        key = key.strip()
        value = value.strip()

        # Skip invalid keys
        if not key or not key.replace('_', '').replace('-', '').isalnum():
            continue

        # Remove surrounding quotes
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]

        env_vars[key] = value

    return env_vars


def format_env_file(env_vars: dict) -> str:
    """
    Format environment variables as .env file content.

    Args:
        env_vars: Dictionary of key-value pairs

    Returns:
        str: Formatted .env file content
    """
    lines = []
    for key, value in sorted(env_vars.items()):
        # Quote values that contain spaces or special characters
        if ' ' in value or '"' in value or "'" in value or '\n' in value:
            # Escape double quotes and use double quotes
            value = value.replace('"', '\\"')
            value = f'"{value}"'
        lines.append(f"{key}={value}")

    return '\n'.join(lines)
