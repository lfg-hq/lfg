"""Bridge between external messaging channels and the LFG AI chat pipeline.

This module extracts the core AI-call logic used by the WebSocket consumer
into a reusable function that can be invoked synchronously from webhook views.
"""
import logging

from django.contrib.auth.models import User

from chat.models import Conversation, Message, ModelSelection, AgentRole
from projects.models import Project
from factory.ai_providers import AIProvider
from factory.ai_tools import tools_product
from factory.prompts import get_system_prompt_product
from factory.llm_config import get_model_provider_map

from .models import ChannelProjectLink, ChannelMessage

logger = logging.getLogger(__name__)

MODEL_TO_PROVIDER = get_model_provider_map()


def process_external_message(
    user: User,
    project: Project,
    message_text: str,
    channel_link: ChannelProjectLink,
    sender_name: str = '',
    sender_id: str = '',
    platform_message_id: str = '',
) -> str:
    """Process an inbound message from Slack/Telegram through the AI pipeline.

    1. Get or create a Conversation linked to the channel/project.
    2. Save the inbound user Message.
    3. Call the AI provider (non-streaming, synchronous).
    4. Save the assistant response Message.
    5. Record ChannelMessage entries for both directions.
    6. Return the response text for the bot to relay back.
    """
    # 1. Get or create conversation
    conversation = _get_or_create_conversation(user, project, channel_link)

    # 2. Save inbound message
    user_msg = Message.objects.create(
        conversation=conversation,
        role='user',
        content=message_text,
    )

    # Record inbound ChannelMessage
    ChannelMessage.objects.create(
        channel_link=channel_link,
        platform_message_id=platform_message_id,
        direction='inbound',
        content=message_text,
        sender_name=sender_name,
        sender_id=sender_id,
        message=user_msg,
    )

    # 3. Build message history and call AI
    response_text = _generate_ai_response(user, project, conversation)

    # 4. Save assistant message
    assistant_msg = Message.objects.create(
        conversation=conversation,
        role='assistant',
        content=response_text,
    )

    # 5. Record outbound ChannelMessage
    ChannelMessage.objects.create(
        channel_link=channel_link,
        direction='outbound',
        content=response_text,
        sender_name='LFG AI',
        message=assistant_msg,
    )

    return response_text


def _get_or_create_conversation(
    user: User, project: Project, channel_link: ChannelProjectLink
) -> Conversation:
    """Return the conversation linked to this channel, creating one if needed."""
    if channel_link.conversation:
        return channel_link.conversation

    conversation = Conversation.objects.create(
        user=user,
        project=project,
        title=f"{channel_link.get_platform_display()} - {channel_link.channel_name}",
    )
    channel_link.conversation = conversation
    channel_link.save(update_fields=['conversation'])
    return conversation


def _generate_ai_response(user: User, project: Project, conversation: Conversation) -> str:
    """Run the AI provider synchronously and return the full response text."""
    import asyncio
    from asgiref.sync import sync_to_async

    async def _run():
        # Build message history — wrap ORM in sync_to_async
        def _get_history():
            history = []
            for msg in conversation.messages.order_by('created_at'):
                history.append({'role': msg.role, 'content': msg.content})
            return history

        history = await sync_to_async(_get_history, thread_sensitive=True)()

        # System prompt
        system_prompt = await get_system_prompt_product()
        if not any(m['role'] == 'system' for m in history):
            history.insert(0, {'role': 'system', 'content': system_prompt})

        # Determine model/provider — wrap ORM
        def _get_model():
            try:
                ms = ModelSelection.objects.get(user=user)
                return ms.selected_model
            except ModelSelection.DoesNotExist:
                ms = ModelSelection.objects.create(
                    user=user, selected_model=ModelSelection.DEFAULT_MODEL_KEY
                )
                return ms.selected_model

        selected_model = await sync_to_async(_get_model, thread_sensitive=True)()

        provider_name = MODEL_TO_PROVIDER.get(selected_model, 'openai')
        provider = AIProvider.get_provider(
            provider_name, selected_model,
            user=user, conversation=conversation, project=project,
        )

        conversation_id = conversation.id if conversation else None
        project_id = project.id if project else None

        # Collect all chunks from the async generator
        full_response = ''
        async for chunk in provider.generate_stream(history, project_id, conversation_id, tools_product):
            if isinstance(chunk, str) and not chunk.startswith('__NOTIFICATION__'):
                full_response += chunk

        return full_response or "I'm sorry, I couldn't generate a response. Please try again."

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.error(f"AI generation error for channel message: {e}", exc_info=True)
        return "Sorry, an error occurred while processing your message."
