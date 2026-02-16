from django.urls import re_path

# Direct import with as_asgi() - this works because our asgi.py calls django.setup() before imports
from chat.consumers import ChatConsumer

websocket_urlpatterns = [
    re_path(r'ws/chat/', ChatConsumer.as_asgi()),
] 