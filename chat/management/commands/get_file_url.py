from django.core.management.base import BaseCommand
from chat.models import ChatFile


class Command(BaseCommand):
    help = 'Get presigned URL for a file'

    def add_arguments(self, parser):
        parser.add_argument('file_id', type=int, help='ID of the ChatFile')

    def handle(self, *args, **options):
        file_id = options['file_id']
        
        try:
            chat_file = ChatFile.objects.get(id=file_id)
            
            self.stdout.write(f"File: {chat_file.original_filename}")
            self.stdout.write(f"Uploaded: {chat_file.uploaded_at}")
            self.stdout.write(f"Size: {chat_file.file_size} bytes")
            self.stdout.write(f"Type: {chat_file.file_type}")
            self.stdout.write(f"\nPresigned URL (valid for 10 minutes):")
            self.stdout.write(self.style.SUCCESS(chat_file.file.url))
            
        except ChatFile.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"File with ID {file_id} not found"))