"""
Synchronous URL patterns for chat app to avoid async context issues
"""
from django.urls import path
from .views.transcribe_sync import TranscribeFileView

urlpatterns = [
    path('api/files/transcribe/<int:file_id>/', TranscribeFileView.as_view(), name='transcribe_file_sync'),
]