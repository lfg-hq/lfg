"""
ASGI config for LFG project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os
import django

# Set Django settings module before anything else
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LFG.settings')

# Initialize Django ASGI application first to avoid AppRegistryNotReady errors
django.setup()

# Import dependencies after Django is set up
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

# Import websocket URL patterns (safe now that Django is initialized)
import chat.routing
import development.routing  # Import the development WebSocket routes
import projects.routing  # Import the projects WebSocket routes

# Create ASGI application
application = ProtocolTypeRouter({
    # HTTP requests are handled by Django's ASGI application
    "http": get_asgi_application(),

    # WebSocket requests are handled with the chat routing configuration and coding terminal routes
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                chat.routing.websocket_urlpatterns +  # Chat WebSockets
                development.routing.websocket_urlpatterns +  # Terminal WebSockets
                projects.routing.websocket_urlpatterns  # Ticket Logs WebSockets
            )
        )
    ),
})

# Wrap the entire application with ASGIStaticFilesHandler for static file serving in development
application = ASGIStaticFilesHandler(application) 