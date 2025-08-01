"""
Custom email backend that uses SendGrid when available,
falls back to SMTP when SendGrid is not configured.
"""
import logging
import json
from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend as SMTPBackend

logger = logging.getLogger(__name__)

try:
    from sendgrid_backend import SendgridBackend
    SENDGRID_AVAILABLE = True
except ImportError:
    SENDGRID_AVAILABLE = False
    logger.warning("SendGrid backend not available. Install django-sendgrid-v5 to use SendGrid.")


class EmailBackend:
    """
    Dynamic email backend that chooses between SendGrid and SMTP
    based on configuration and availability.
    """
    
    def __init__(self, *args, **kwargs):
        if settings.SENDGRID_API_KEY and SENDGRID_AVAILABLE:
            logger.info("Using SendGrid email backend")
            self.backend = SendgridBackend(*args, **kwargs)
        else:
            logger.info("Using SMTP email backend")
            self.backend = SMTPBackend(*args, **kwargs)
    
    def send_messages(self, messages):
        """Send email messages using the configured backend."""
        try:
            # If using SendGrid, disable click tracking for all messages
            if hasattr(self.backend, '__class__') and 'Sendgrid' in self.backend.__class__.__name__:
                for message in messages:
                    # For django-sendgrid-v5, we need to set tracking settings
                    if not hasattr(message, 'track_clicks'):
                        # Disable click tracking for this message
                        message.track_clicks = False
                    if not hasattr(message, 'track_opens'):
                        # Also disable open tracking for privacy
                        message.track_opens = False
            
            return self.backend.send_messages(messages)
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            # Re-raise the exception so Django knows the email failed
            raise
    
    def open(self):
        """Open a network connection."""
        if hasattr(self.backend, 'open'):
            return self.backend.open()
        return True
    
    def close(self):
        """Close the network connection."""
        if hasattr(self.backend, 'close'):
            self.backend.close()