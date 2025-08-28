"""
Fixed transcription view that properly handles async context
"""
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from chat.models import ChatFile
from accounts.models import LLMApiKeys, TokenUsage
from asgiref.sync import sync_to_async
import tempfile
import os
import logging

logger = logging.getLogger(__name__)


@require_GET
@login_required
@csrf_exempt
def transcribe_file(request, file_id):
    """
    Synchronous endpoint for file transcription.
    This avoids the "You cannot call this from an async context" error.
    """
    try:
        # Get the file object - all DB operations are synchronous
        try:
            chat_file = ChatFile.objects.select_related('conversation__user').get(id=file_id)
        except ChatFile.DoesNotExist:
            return JsonResponse({'error': 'File not found'}, status=404)
        
        # Check permissions
        if chat_file.conversation and chat_file.conversation.user:
            if chat_file.conversation.user != request.user:
                return JsonResponse(
                    {'error': 'You do not have permission to access this file'}, 
                    status=403
                )
        
        # Validate audio file type
        audio_types = ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/x-wav', 
                       'audio/webm', 'audio/ogg', 'audio/flac', 'audio/x-flac', 
                       'audio/mp4', 'audio/x-m4a']
        
        is_audio = False
        if chat_file.file_type and chat_file.file_type.lower() in audio_types:
            is_audio = True
        else:
            # Check file extension
            file_ext = chat_file.original_filename.lower().split('.')[-1]
            audio_extensions = ['mp3', 'wav', 'webm', 'ogg', 'flac', 'm4a', 'mp4']
            if file_ext in audio_extensions:
                is_audio = True
        
        if not is_audio:
            return JsonResponse({'error': 'File is not an audio file'}, status=400)
        
        # Read file content
        try:
            chat_file.file.open('rb')
            file_content = chat_file.file.read()
            chat_file.file.close()
        except Exception as e:
            return JsonResponse(
                {'error': f'Failed to read file: {str(e)}'}, 
                status=500
            )
        
        # Get OpenAI API key
        api_key = None
        
        # Try user's API keys first
        try:
            llm_keys = LLMApiKeys.objects.filter(user=request.user).first()
            if llm_keys and llm_keys.openai_api_key:
                api_key = llm_keys.openai_api_key
        except Exception:
            pass
        
        # Fallback to settings
        if not api_key:
            api_key = getattr(settings, 'OPENAI_API_KEY', None)
        
        if not api_key:
            return JsonResponse(
                {'error': 'OpenAI API key not configured'}, 
                status=400
            )
        
        # Import OpenAI
        try:
            from openai import OpenAI
        except ImportError:
            return JsonResponse(
                {'error': 'OpenAI library not installed'}, 
                status=500
            )
        
        # Create OpenAI client
        client = OpenAI(api_key=api_key)
        
        # Create temporary file
        file_extension = chat_file.original_filename.split(".")[-1]
        tmp_file_path = None
        
        try:
            with tempfile.NamedTemporaryFile(
                delete=False, 
                suffix=f'.{file_extension}'
            ) as tmp_file:
                tmp_file.write(file_content)
                tmp_file_path = tmp_file.name
            
            # Transcribe using OpenAI Whisper
            with open(tmp_file_path, 'rb') as audio_file:
                result = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )
            
            transcription = result
            
            # Track usage
            estimated_minutes = max(1, chat_file.file_size / (1024 * 1024))
            cost = estimated_minutes * 0.006
            
            TokenUsage.objects.create(
                user=request.user,
                project=chat_file.conversation.project if chat_file.conversation else None,
                conversation=chat_file.conversation,
                provider='openai',
                model='whisper-1',
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                cost=cost
            )
            
            return JsonResponse({
                'transcription': transcription,
                'file_id': file_id,
                'filename': chat_file.original_filename
            })
            
        finally:
            # Clean up temp file
            if tmp_file_path and os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
    
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Transcription error: {str(e)}")
        logger.error(error_details)
        
        # Return a more detailed error in development
        if settings.DEBUG:
            return JsonResponse(
                {'error': f'Transcription failed: {str(e)}', 'details': error_details}, 
                status=500
            )
        else:
            return JsonResponse(
                {'error': 'Transcription failed'}, 
                status=500
            )