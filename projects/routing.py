from django.urls import re_path
from projects.consumers import TicketLogsConsumer, WorkspaceProgressConsumer

websocket_urlpatterns = [
    re_path(r'ws/tickets/(?P<ticket_id>\d+)/logs/$', TicketLogsConsumer.as_asgi()),
    re_path(r'ws/projects/(?P<project_id>[0-9a-f-]+)/workspace-progress/$', WorkspaceProgressConsumer.as_asgi()),
]
