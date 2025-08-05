import os
import logging
import base64
import tempfile
from typing import Optional, Dict, Any, Tuple
from asgiref.sync import sync_to_async
from django.conf import settings

logger = logging.getLogger(__name__)


class FileHandler:
    """Factory class for handling file uploads and parsing across different AI providers"""
    
    def __init__(self, provider_name: str, user: Optional[Any] = None):
        self.provider_name = provider_name.lower()
        self.user = user
        self.supported_formats = self._get_supported_formats()
    
    def _get_supported_formats(self) -> Dict[str, Any]:
        """Get supported file formats for each provider"""
        formats = {
            'anthropic': {
                'images': ['.jpg', '.jpeg', '.png', '.gif', '.webp'],
                'documents': ['.pdf', '.csv', '.txt', '.md', '.docx', '.xlsx'],
                'audio': ['.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm'],  # Supported by transcription
                'max_size_mb': 100,  # Reasonable limit
                'methods': ['base64', 'file_id']
            },
            'openai': {
                'images': ['.jpg', '.jpeg', '.png', '.gif', '.webp'],
                'documents': ['.pdf'],  # PDFs supported by GPT-4o models
                'audio': ['.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm'],  # Whisper supported formats
                'max_size_mb': 32,  # PDF limit
                'max_audio_mb': 25,  # Whisper API limit
                'max_images': 10,
                'methods': ['base64', 'url']
            },
            'xai': {
                'images': ['.jpg', '.jpeg', '.png', '.gif', '.webp'],
                'documents': [],  # Limited document support currently
                'audio': ['.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm'],  # Can use OpenAI Whisper
                'max_size_mb': 20,  # Conservative estimate
                'methods': ['base64', 'url']
            },
            'google': {
                'images': ['.jpg', '.jpeg', '.png', '.gif', '.webp'],
                'documents': ['.pdf', '.txt', '.md'],  # Google Gemini document support
                'audio': ['.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm'],  # Via transcription
                'max_size_mb': 20,
                'methods': ['base64']
            }
        }
        return formats.get(self.provider_name, formats['openai'])
    
    def is_supported_file(self, filename: str) -> bool:
        """Check if a file type is supported by the provider"""
        ext = os.path.splitext(filename)[1].lower()
        supported = self.supported_formats
        return ext in supported['images'] + supported['documents'] + supported.get('audio', [])
    
    def get_file_category(self, filename: str) -> Optional[str]:
        """Determine if file is an image, document, or audio"""
        ext = os.path.splitext(filename)[1].lower()
        if ext in self.supported_formats['images']:
            return 'image'
        elif ext in self.supported_formats['documents']:
            return 'document'
        elif ext in self.supported_formats.get('audio', []):
            return 'audio'
        return None
    
    async def prepare_file_for_provider(self, chat_file: Any, storage: Any) -> Dict[str, Any]:
        """Prepare a file for sending to the AI provider"""
        try:
            filename = chat_file.original_filename
            file_category = self.get_file_category(filename)
            
            if not file_category:
                raise ValueError(f"Unsupported file type for {self.provider_name}: {filename}")
            
            # Get file content
            file_content = await self._get_file_content(chat_file, storage)
            
            # Handle audio files specially - they need transcription
            if file_category == 'audio':
                return await self._prepare_audio_file(chat_file, file_content)
            
            # Prepare based on provider for non-audio files
            if self.provider_name == 'anthropic':
                return await self._prepare_anthropic_file(chat_file, file_content, file_category)
            elif self.provider_name == 'openai':
                return await self._prepare_openai_file(chat_file, file_content, file_category)
            elif self.provider_name == 'xai':
                return await self._prepare_xai_file(chat_file, file_content, file_category)
            elif self.provider_name == 'google':
                return await self._prepare_google_file(chat_file, file_content, file_category)
            else:
                raise ValueError(f"Unknown provider: {self.provider_name}")
                
        except Exception as e:
            logger.error(f"Error preparing file for {self.provider_name}: {str(e)}")
            raise
    
    async def _get_file_content(self, chat_file: Any, storage: Any) -> bytes:
        """Get file content from storage"""
        try:
            @sync_to_async
            def read_file():
                file_obj = storage._open(chat_file.file.name, 'rb')
                content = file_obj.read()
                if hasattr(file_obj, 'close'):
                    file_obj.close()
                return content
            
            return await read_file()
        except Exception as e:
            logger.error(f"Error reading file content: {str(e)}")
            raise
    
    async def _prepare_anthropic_file(self, chat_file: Any, content: bytes, category: str) -> Dict[str, Any]:
        """Prepare file for Anthropic Claude API"""
        if category == 'image':
            # Use base64 for images
            base64_content = base64.b64encode(content).decode('utf-8')
            media_type = chat_file.file_type or 'image/jpeg'
            
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64_content
                }
            }
        else:
            # For documents (PDF), use base64 encoding
            base64_content = base64.b64encode(content).decode('utf-8')
            
            return {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": chat_file.file_type or "application/pdf",
                    "data": base64_content
                },
                "title": chat_file.original_filename
            }
    
    async def _prepare_openai_file(self, chat_file: Any, content: bytes, category: str) -> Dict[str, Any]:
        """Prepare file for OpenAI API"""
        if category in ['image', 'document']:
            # Use base64 for both images and PDFs
            base64_content = base64.b64encode(content).decode('utf-8')
            media_type = chat_file.file_type or ('image/jpeg' if category == 'image' else 'application/pdf')
            
            return {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{media_type};base64,{base64_content}"
                }
            }
        
        raise ValueError(f"Unsupported file category for OpenAI: {category}")
    
    async def _prepare_xai_file(self, chat_file: Any, content: bytes, category: str) -> Dict[str, Any]:
        """Prepare file for XAI Grok API (OpenAI-compatible)"""
        # XAI uses the same format as OpenAI
        return await self._prepare_openai_file(chat_file, content, category)
    
    async def _prepare_google_file(self, chat_file: Any, content: bytes, category: str) -> Dict[str, Any]:
        """Prepare file for Google Gemini API"""
        if category in ['image', 'document']:
            # Use base64 for Google Gemini
            base64_content = base64.b64encode(content).decode('utf-8')
            media_type = chat_file.file_type or ('image/jpeg' if category == 'image' else 'application/pdf')
            
            return {
                "inline_data": {
                    "mime_type": media_type,
                    "data": base64_content
                }
            }
        
        raise ValueError(f"Unsupported file category for Google: {category}")
    
    async def _prepare_audio_file(self, chat_file: Any, content: bytes) -> Dict[str, Any]:
        """Prepare audio file by transcribing it using OpenAI Whisper"""
        try:
            from openai import OpenAI
            
            # Get OpenAI API key from user profile or settings
            @sync_to_async
            def get_openai_api_key():
                # Try to get from user profile first
                if hasattr(self, 'user') and self.user:
                    try:
                        from accounts.models import LLMApiKeys
                        llm_keys = LLMApiKeys.objects.get(user=self.user)
                        if llm_keys.openai_api_key:
                            return llm_keys.openai_api_key
                    except:
                        pass
                
                # Fallback to settings
                return getattr(settings, 'OPENAI_API_KEY', None)
            
            api_key = await get_openai_api_key()
            if not api_key:
                raise ValueError("OpenAI API key not found for audio transcription")
            
            # Create OpenAI client
            client = OpenAI(api_key=api_key)
            
            # Get file extension
            ext = os.path.splitext(chat_file.original_filename)[1].lower()
            
            # Create temporary file with proper extension
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
                tmp_file.write(content)
                tmp_file_path = tmp_file.name
            
            try:
                # Transcribe using Whisper API
                @sync_to_async
                def transcribe_audio():
                    with open(tmp_file_path, 'rb') as audio_file:
                        transcript = client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            response_format="text"
                        )
                    return transcript
                
                transcription = await transcribe_audio()
                
                # Track audio transcription usage
                await self._track_audio_transcription_usage(chat_file, content)
                
                # Format the transcription as a text message
                return {
                    "type": "text",
                    "text": f"[Audio Transcription of {chat_file.original_filename}]:\n\n{transcription}"
                }
                
            finally:
                # Clean up temporary file
                try:
                    os.unlink(tmp_file_path)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Error transcribing audio file: {str(e)}")
            # Return error message instead of raising
            return {
                "type": "text",
                "text": f"[Error transcribing audio file {chat_file.original_filename}: {str(e)}]"
            }
    
    async def _track_audio_transcription_usage(self, chat_file: Any, content: bytes) -> None:
        """Track audio transcription usage for billing"""
        try:
            from accounts.models import TokenUsage
            
            # Calculate audio duration in seconds (approximate based on file size)
            # Average audio bitrate: 128 kbps = 16 KB/s
            file_size_kb = len(content) / 1024
            duration_seconds = file_size_kb / 16  # Rough estimate
            duration_minutes = max(1, int(duration_seconds / 60))  # Minimum 1 minute
            
            # OpenAI Whisper costs $0.006 per minute
            cost = duration_minutes * 0.006
            
            @sync_to_async
            def save_usage():
                if self.user:
                    # Create a token usage record for transcription
                    usage = TokenUsage(
                        user=self.user,
                        provider='openai',
                        model='whisper-1',
                        input_tokens=0,  # Whisper doesn't use tokens
                        output_tokens=0,
                        total_tokens=0,
                        cost=cost,
                        conversation=getattr(chat_file, 'conversation', None),
                        project=getattr(chat_file.conversation, 'project', None) if hasattr(chat_file, 'conversation') else None
                    )
                    usage.save()
                    
                    logger.info(f"Tracked audio transcription: {duration_minutes} minutes, cost: ${cost:.4f}")
            
            await save_usage()
            
        except Exception as e:
            logger.error(f"Error tracking audio transcription usage: {e}")
    
    def format_file_message(self, file_data: Dict[str, Any], text_content: Optional[str] = None) -> list:
        """Format file data into a message structure for the provider"""
        if self.provider_name == 'anthropic':
            # Anthropic supports mixing text and files in content array
            content = []
            if text_content:
                content.append({"type": "text", "text": text_content})
            content.append(file_data)
            return content
        
        elif self.provider_name in ['openai', 'xai']:
            # OpenAI/XAI require separate content entries
            content = []
            if text_content:
                content.append({"type": "text", "text": text_content})
            content.append(file_data)
            return content
        
        elif self.provider_name == 'google':
            # Google Gemini format
            content = []
            if text_content:
                content.append({"text": text_content})
            content.append(file_data)
            return content
        
        else:
            raise ValueError(f"Unknown provider: {self.provider_name}")
    
    @staticmethod
    def get_handler(provider_name: str, user: Optional[Any] = None) -> 'FileHandler':
        """Factory method to get a FileHandler instance"""
        return FileHandler(provider_name, user)