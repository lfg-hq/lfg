"""
Transcription view separated to handle async context issues
"""
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from chat.models import ChatFile
from accounts.models import LLMApiKeys, TokenUsage
import tempfile
import os
import logging

logger = logging.getLogger(__name__)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def transcribe_file(request, file_id):
    """
    API endpoint to transcribe an audio file using OpenAI Whisper.
    
    URL: GET /api/files/transcribe/<file_id>/
    
    Authentication: Required (IsAuthenticated)
    
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
        # Get the file object
        try:
            chat_file = ChatFile.objects.select_related('conversation', 'conversation__user').get(id=file_id)
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
        
        # Get OpenAI API key
        api_key = None
        if request.user.is_authenticated:
            try:
                # Get API key from LLMApiKeys
                llm_keys = LLMApiKeys.objects.filter(user=request.user).first()
                if llm_keys and llm_keys.openai_api_key:
                    api_key = llm_keys.openai_api_key
            except Exception as e:
                logger.error(f"Error getting API key from LLMApiKeys: {e}")
        
        if not api_key:
            api_key = getattr(settings, 'OPENAI_API_KEY', None)
        
        if not api_key:
            return Response({'error': 'OpenAI API key not configured'}, 
                            status=status.HTTP_400_BAD_REQUEST)
        
        # Use OpenAI directly for transcription
        from openai import OpenAI
        
        # Create OpenAI client
        client = OpenAI(api_key=api_key)
        
        # Create a temporary file for the audio
        file_extension = chat_file.original_filename.split(".")[-1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_extension}') as tmp_file:
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
        
        return Response({
            'transcription': transcription,
            'file_id': file_id,
            'filename': chat_file.original_filename
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        import traceback
        logger.error(f"Transcription error: {str(e)}")
        logger.error(traceback.format_exc())
        return Response({'error': f'Transcription failed: {str(e)}'}, 
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)