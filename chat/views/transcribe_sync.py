"""
Synchronous transcription endpoint to avoid async context issues
"""
from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from chat.models import ChatFile
from accounts.models import LLMApiKeys, TokenUsage
import json
import tempfile
import os
import logging

logger = logging.getLogger(__name__)


@method_decorator(login_required, name='dispatch')
@method_decorator(csrf_exempt, name='dispatch')
class TranscribeFileView(View):
    """
    Synchronous view for file transcription to avoid async context issues.
    """
    
    def get(self, request, file_id):
        """Handle GET request for transcription"""
        try:
            # Get the file object with related objects to minimize queries
            try:
                chat_file = ChatFile.objects.select_related(
                    'conversation', 
                    'conversation__user'
                ).get(id=file_id)
            except ChatFile.DoesNotExist:
                return JsonResponse({'error': 'File not found'}, status=404)
            
            # Check permissions
            if chat_file.conversation and chat_file.conversation.user:
                if chat_file.conversation.user != request.user:
                    return JsonResponse({'error': 'You do not have permission to access this file'}, 
                                      status=403)
            
            # Validate audio file
            audio_types = ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/x-wav', 'audio/webm', 
                           'audio/ogg', 'audio/flac', 'audio/x-flac', 'audio/mp4', 'audio/x-m4a']
            
            if not chat_file.file_type or chat_file.file_type.lower() not in audio_types:
                file_ext = chat_file.original_filename.lower().split('.')[-1]
                audio_extensions = ['mp3', 'wav', 'webm', 'ogg', 'flac', 'm4a', 'mp4']
                if file_ext not in audio_extensions:
                    return JsonResponse({'error': 'File is not an audio file'}, status=400)
            
            # Read file content
            try:
                chat_file.file.open('rb')
                file_content = chat_file.file.read()
                chat_file.file.close()
            except Exception as e:
                return JsonResponse({'error': f'Failed to read file: {str(e)}'}, status=500)
            
            # Get API key
            api_key = self._get_openai_api_key(request.user)
            if not api_key:
                return JsonResponse({'error': 'OpenAI API key not configured'}, status=400)
            
            # Perform transcription
            transcription = self._transcribe_audio(
                file_content, 
                chat_file.original_filename, 
                api_key
            )
            
            # Track usage
            self._track_usage(request.user, chat_file)
            
            return JsonResponse({
                'transcription': transcription,
                'file_id': file_id,
                'filename': chat_file.original_filename
            })
            
        except Exception as e:
            import traceback
            logger.error(f"Transcription error: {str(e)}")
            logger.error(traceback.format_exc())
            return JsonResponse({'error': f'Transcription failed: {str(e)}'}, status=500)
    
    def _get_openai_api_key(self, user):
        """Get OpenAI API key for the user"""
        api_key = None
        
        # Try to get from user's LLM API keys
        try:
            llm_keys = LLMApiKeys.objects.filter(user=user).first()
            if llm_keys and llm_keys.openai_api_key:
                api_key = llm_keys.openai_api_key
        except Exception as e:
            logger.error(f"Error getting API key from LLMApiKeys: {e}")
        
        # Fallback to settings
        if not api_key:
            api_key = getattr(settings, 'OPENAI_API_KEY', None)
        
        return api_key
    
    def _transcribe_audio(self, file_content, filename, api_key):
        """Transcribe audio using OpenAI Whisper"""
        from openai import OpenAI
        
        client = OpenAI(api_key=api_key)
        
        # Create temporary file
        file_extension = filename.split(".")[-1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_extension}') as tmp_file:
            tmp_file.write(file_content)
            tmp_file_path = tmp_file.name
        
        try:
            # Transcribe
            with open(tmp_file_path, 'rb') as audio_file:
                result = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )
            return result
        finally:
            # Clean up
            os.unlink(tmp_file_path)
    
    def _track_usage(self, user, chat_file):
        """Track token usage for transcription"""
        # Estimate cost: $0.006 per minute, 1MB ≈ 1 minute
        estimated_minutes = max(1, chat_file.file_size / (1024 * 1024))
        cost = estimated_minutes * 0.006
        
        TokenUsage.objects.create(
            user=user,
            model='whisper-1',
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost=cost,
            conversation=chat_file.conversation,
            message=None
        )