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
