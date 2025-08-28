import json
import os
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.conf import settings
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from chat.models import Conversation, Message, ChatFile
from factory.ai_providers import FileHandler
import asyncio
from asgiref.sync import sync_to_async
import logging

logger = logging.getLogger(__name__)


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
@login_required
def upload_file(request):
    """
    API endpoint to upload a file and attach it to a conversation.
    
    Request should include:
    - file: The file to upload
    - conversation_id: The ID of the conversation
    - message_id: (Optional) The ID of the message to associate with the file
    """
    file_obj = request.FILES.get('file')
    conversation_id = request.data.get('conversation_id')
    message_id = request.data.get('message_id')
    
    if not file_obj:
        return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)
    
    if not conversation_id:
        return Response({'error': 'Conversation ID is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Ensure the conversation belongs to the user
        conversation = get_object_or_404(Conversation, id=conversation_id)
        if conversation.user and conversation.user != request.user:
            return Response({'error': 'You do not have permission to access this conversation'}, 
                            status=status.HTTP_403_FORBIDDEN)
        
        # Get the associated message if provided
        message = None
        if message_id:
            message = get_object_or_404(Message, id=message_id, conversation=conversation)
        
        # Create the chat file
        chat_file = ChatFile.objects.create(
            conversation=conversation,
            message=message,
            file=file_obj,
            original_filename=file_obj.name,
            file_type=file_obj.content_type,
            file_size=file_obj.size
        )
        
        return Response({
            'id': chat_file.id,
            'filename': chat_file.original_filename,
            'file_type': chat_file.file_type,
            'file_size': chat_file.file_size,
            'uploaded_at': chat_file.uploaded_at,
            'url': chat_file.file.url,
            'conversation_id': conversation.id,
            'message_id': message.id if message else None
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@login_required
def conversation_files(request, conversation_id):
    """
    API endpoint to retrieve all files associated with a conversation.
    """
    try:
        # Ensure the conversation belongs to the user
        conversation = get_object_or_404(Conversation, id=conversation_id)
        if conversation.user and conversation.user != request.user:
            return Response({'error': 'You do not have permission to access this conversation'}, 
                            status=status.HTTP_403_FORBIDDEN)
        
        # Get all files for the conversation
        files = ChatFile.objects.filter(conversation=conversation)
        
        # Format the response
        file_data = [{
            'id': f.id,
            'filename': f.original_filename,
            'file_type': f.file_type,
            'file_size': f.file_size,
            'uploaded_at': f.uploaded_at,
            'url': f.file.url,
            'conversation_id': conversation.id,
            'message_id': f.message.id if f.message else None
        } for f in files]
        
        return Response(file_data, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


from rest_framework.decorators import authentication_classes, permission_classes
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.csrf import ensure_csrf_cookie
from asgiref.sync import async_to_sync
import tempfile

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
@ensure_csrf_cookie
def transcribe_file(request, file_id):
    """
    API endpoint to transcribe an audio file using OpenAI Whisper.
    
    URL: GET /api/files/transcribe/<file_id>/
    
    Authentication: Required (login_required)
    
    Parameters:
    - file_id: The ID of the ChatFile object to transcribe
    
    Returns:
    - 200 OK: {
        "transcription": "The transcribed text content",
        "file_id": 123,
        "filename": "audio.mp3"
      }
    - 400 Bad Request: If file is not an audio file
    - 403 Forbidden: If user doesn't have permission
    - 404 Not Found: If file doesn't exist
    - 500 Internal Server Error: If transcription fails
    
    Notes:
    - Uses OpenAI Whisper API for transcription
    - Supports formats: mp3, wav, webm, ogg, flac, m4a, mp4
    - Requires user to have OpenAI API key configured
    """
    try:
        # Get the file object - ensure we're in sync context
        try:
            chat_file = ChatFile.objects.get(id=file_id)
        except ChatFile.DoesNotExist:
            return Response({'error': 'File not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Ensure the conversation belongs to the user
        if chat_file.conversation and chat_file.conversation.user:
            if chat_file.conversation.user != request.user:
                return Response({'error': 'You do not have permission to access this file'}, 
                                status=status.HTTP_403_FORBIDDEN)
        
        # Check if it's an audio file
        audio_types = ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/x-wav', 'audio/webm', 
                       'audio/ogg', 'audio/flac', 'audio/x-flac', 'audio/mp4', 'audio/x-m4a']
        
        if not chat_file.file_type or chat_file.file_type.lower() not in audio_types:
            # Check file extension if content type is not set
            file_ext = chat_file.original_filename.lower().split('.')[-1]
            audio_extensions = ['mp3', 'wav', 'webm', 'ogg', 'flac', 'm4a', 'mp4']
            if file_ext not in audio_extensions:
                return Response({'error': 'File is not an audio file'}, 
                                status=status.HTTP_400_BAD_REQUEST)
        
        # Get file content
        try:
            chat_file.file.open('rb')
            file_content = chat_file.file.read()
            chat_file.file.close()
        except Exception as e:
            return Response({'error': f'Failed to read file: {str(e)}'}, 
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Use OpenAI directly for transcription to avoid async issues
        from openai import OpenAI
        from django.conf import settings
        
        # Get OpenAI API key
        api_key = None
        if request.user.is_authenticated:
            try:
                from accounts.models import Profile, LLMApiKeys
                # Try to get API key from LLMApiKeys first
                try:
                    llm_keys = LLMApiKeys.objects.get(user=request.user)
                    if llm_keys.openai_api_key:
                        api_key = llm_keys.openai_api_key
                except LLMApiKeys.DoesNotExist:
                    pass
                
                # Fallback to Profile if needed
                if not api_key:
                    try:
                        profile = Profile.objects.get(user=request.user)
                        if hasattr(profile, 'openai_api_key') and profile.openai_api_key:
                            api_key = profile.openai_api_key
                    except Profile.DoesNotExist:
                        pass
            except Exception as e:
                logger.error(f"Error getting API key: {e}")
        
        if not api_key:
            api_key = getattr(settings, 'OPENAI_API_KEY', None)
        
        if not api_key:
            return Response({'error': 'OpenAI API key not configured'}, 
                            status=status.HTTP_400_BAD_REQUEST)
        
        # Create OpenAI client
        client = OpenAI(api_key=api_key)
        
        # Create a temporary file for the audio
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{chat_file.original_filename.split(".")[-1]}') as tmp_file:
            tmp_file.write(file_content)
            tmp_file_path = tmp_file.name
        
        try:
            # Transcribe using OpenAI Whisper
            with open(tmp_file_path, 'rb') as audio_file:
                result = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )
            
            transcription = result
            
            # Track usage
            from accounts.models import TokenUsage
            # Audio transcription costs $0.006 per minute
            # Estimate duration based on file size (rough estimate: 1MB = 1 minute)
            estimated_minutes = max(1, chat_file.file_size / (1024 * 1024))
            cost = estimated_minutes * 0.006
            
            TokenUsage.objects.create(
                user=request.user,
                model='whisper-1',
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                cost=cost,
                conversation=chat_file.conversation,
                message=None
            )
        finally:
            # Clean up temp file
            os.unlink(tmp_file_path)
        
        # The transcription is already a string from OpenAI
        
        return Response({
            'transcription': transcription,
            'file_id': file_id,
            'filename': chat_file.original_filename
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR) 
