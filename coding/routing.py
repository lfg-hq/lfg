from django.urls import re_path

# We're now using ttyd directly for terminal access, so no WebSocket route is needed
websocket_urlpatterns = [
    # Empty as we're using ttyd sidecar now
]