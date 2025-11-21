from django.urls import re_path
from projects.consumers import TicketLogsConsumer

websocket_urlpatterns = [
    re_path(r'ws/tickets/(?P<ticket_id>\d+)/logs/$', TicketLogsConsumer.as_asgi()),
]
