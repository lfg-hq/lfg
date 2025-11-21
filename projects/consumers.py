import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.db import close_old_connections
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed

logger = logging.getLogger(__name__)


class TicketLogsConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time ticket log updates.
    Clients connect to ws://host/ws/tickets/<ticket_id>/logs/
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ticket_id = None
        self.ticket_group_name = None
        self.user = None

    async def connect(self):
        """Handle WebSocket connection"""
        connection_accepted = False

        try:
            # Clean up any stale database connections
            await database_sync_to_async(close_old_connections)()

            # Get ticket_id from URL route
            self.ticket_id = self.scope['url_route']['kwargs']['ticket_id']
            self.ticket_group_name = f'ticket_logs_{self.ticket_id}'

            # Get user from scope
            lazy_user = self.scope["user"]

            # Convert LazyUser to actual User instance
            if hasattr(lazy_user, '_wrapped') and hasattr(lazy_user, '_setup'):
                if lazy_user.is_authenticated:
                    User_model = User
                    self.user = await database_sync_to_async(User_model.objects.get)(pk=lazy_user.pk)
                else:
                    self.user = lazy_user
            else:
                self.user = lazy_user

            # Try JWT authentication from query string if user not authenticated
            query_string = self.scope.get('query_string', b'').decode()
            query_params = dict(param.split('=') for param in query_string.split('&') if '=' in param)
            token = query_params.get('token')

            if (not getattr(self.user, 'is_authenticated', False) or not self.user) and token:
                jwt_auth = JWTAuthentication()
                try:
                    validated_token = jwt_auth.get_validated_token(token)
                    self.user = await database_sync_to_async(jwt_auth.get_user)(validated_token)
                except (InvalidToken, AuthenticationFailed) as e:
                    logger.warning(f"Invalid JWT token for ticket logs WebSocket: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error validating JWT token: {e}")

            # Verify user is authenticated
            if not self.user or not getattr(self.user, 'is_authenticated', False):
                logger.warning(f"Unauthenticated user tried to connect to ticket logs WebSocket")
                await self.close()
                return

            # Verify user has access to this ticket
            has_access = await self.verify_ticket_access()
            if not has_access:
                logger.warning(f"User {self.user.email} denied access to ticket {self.ticket_id}")
                await self.close()
                return

            # Accept the connection
            await self.accept()
            connection_accepted = True
            logger.info(f"WebSocket connection accepted for user {self.user.email} on ticket {self.ticket_id}")

            # Join the ticket group
            await self.channel_layer.group_add(
                self.ticket_group_name,
                self.channel_name
            )
            logger.info(f"User {self.user.email} joined group {self.ticket_group_name}")

        except Exception as e:
            logger.error(f"Error in TicketLogsConsumer connect: {str(e)}")
            if not connection_accepted:
                try:
                    await self.accept()
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': f"Connection error: {str(e)}"
                    }))
                except Exception as inner_e:
                    logger.error(f"Could not accept WebSocket connection: {str(inner_e)}")

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        try:
            if self.ticket_group_name:
                await self.channel_layer.group_discard(
                    self.ticket_group_name,
                    self.channel_name
                )
                logger.info(f"User {self.user.email if self.user else 'Unknown'} left group {self.ticket_group_name}")
        except Exception as e:
            logger.error(f"Error during TicketLogsConsumer disconnect: {str(e)}")
        finally:
            # Close database connections
            await database_sync_to_async(close_old_connections)()

    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type', 'ping')

            # Handle ping/pong for keepalive
            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong'
                }))

        except Exception as e:
            logger.error(f"Error processing message in TicketLogsConsumer: {str(e)}")

    async def ticket_log_created(self, event):
        """
        Handler for ticket_log_created events sent to the group.
        Receives log data and sends it to the WebSocket client.
        """
        logger.info(f"ticket_log_created event received for ticket {self.ticket_id}")

        # Extract log data from event
        log_data = event.get('log_data', {})

        # Send to WebSocket client
        await self.send(text_data=json.dumps({
            'type': 'log_created',
            'log': log_data
        }))

        logger.info(f"Sent new log to client for ticket {self.ticket_id}: {log_data.get('id')}")

    @database_sync_to_async
    def verify_ticket_access(self):
        """Verify that the user has access to this ticket"""
        try:
            from projects.models import ProjectTicket

            ticket = ProjectTicket.objects.select_related('project').get(id=self.ticket_id)

            # Check if user is project owner or has access
            if ticket.project.owner == self.user:
                return True

            # Check if user is a project member
            if ticket.project.has_member(self.user):
                return True

            return False

        except Exception as e:
            logger.error(f"Error verifying ticket access: {e}")
            return False
