from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from chat.models import ChatFile


@api_view(['GET'])
@login_required
def get_file_url(request, file_id):
    """
    Get a presigned URL for a specific file.
    
    Usage:
        GET /api/files/{file_id}/url/
    
    Returns:
        {
            "id": 123,
            "filename": "document.pdf",
            "file_type": "application/pdf",
            "file_size": 1024000,
            "uploaded_at": "2025-07-18T18:30:00Z",
            "presigned_url": "https://...",
            "expires_in_seconds": 600
        }
    """
    try:
        # Get the file and ensure user has access
        chat_file = get_object_or_404(ChatFile, id=file_id)
        
        # Check if user has access to this file's conversation
        if chat_file.conversation.user and chat_file.conversation.user != request.user:
            return Response({'error': 'You do not have permission to access this file'}, 
                            status=status.HTTP_403_FORBIDDEN)
        
        return Response({
            'id': chat_file.id,
            'filename': chat_file.original_filename,
            'file_type': chat_file.file_type,
            'file_size': chat_file.file_size,
            'uploaded_at': chat_file.uploaded_at,
            'presigned_url': chat_file.file.url,
            'expires_in_seconds': getattr(settings, 'AWS_S3_PRESIGNED_URL_EXPIRY', 600)
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)