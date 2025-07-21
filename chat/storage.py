from django.core.files.storage import Storage
from django.core.files.base import ContentFile
from django.conf import settings
from django.utils.deconstruct import deconstructible
import os
import uuid
from datetime import datetime
import boto3
from botocore.config import Config


def get_s3_client():
    """Get a properly configured S3 client."""
    region = getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1')
    return boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=region,
        config=Config(
            signature_version='s3v4',
            region_name=region,
            s3={'addressing_style': 'virtual'}
        )
    )


@deconstructible
class ChatFileStorage(Storage):
    """
    Custom storage backend for chat files that uses either local or S3 storage
    based on the FILE_STORAGE_TYPE setting.
    """
    
    def __init__(self, location=None, base_url=None):
        self._location = location
        self._base_url = base_url
        self.file_storage_type = getattr(settings, 'FILE_STORAGE_TYPE', 'local').lower()
        
    @property
    def location(self):
        return self._location or settings.MEDIA_ROOT
        
    @property
    def base_url(self):
        return self._base_url or settings.MEDIA_URL
    
    def _open(self, name, mode='rb'):
        """Open a file from storage."""
        # For S3 storage, we need to download the file content
        if self.file_storage_type == 's3':
            # Use boto3 directly
            s3_client = get_s3_client()
            try:
                # Construct the full S3 key
                prefix = getattr(settings, 'AWS_S3_PROJECT_PREFIX', 'projects')
                s3_key = f"{prefix}/{name}"
                response = s3_client.get_object(
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                    Key=s3_key
                )
                content = response['Body'].read()
                return ContentFile(content, name=name)
            except Exception as e:
                raise FileNotFoundError(f"File not found: {name}")
        else:
            # For local storage, use the default file opening
            file_path = os.path.join(self.location, name)
            return open(file_path, mode)
    
    def _save(self, name, content):
        """Save a file to storage."""
        # Read the content as bytes
        content_data = content.read()
        
        if self.file_storage_type == 's3':
            # For S3, upload binary files directly using boto3
            s3_client = get_s3_client()
            try:
                # Construct the full S3 key
                prefix = getattr(settings, 'AWS_S3_PROJECT_PREFIX', 'projects')
                s3_key = f"{prefix}/{name}"
                
                # Determine content type
                import mimetypes
                content_type, _ = mimetypes.guess_type(name)
                if not content_type:
                    content_type = 'application/octet-stream'
                
                # Upload to S3
                s3_client.put_object(
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                    Key=s3_key,
                    Body=content_data,
                    ContentType=content_type
                )
                return name
            except Exception as e:
                raise Exception(f"Failed to save file to S3: {str(e)}")
        else:
            # For local storage, ensure directory exists
            full_path = os.path.join(self.location, name)
            directory = os.path.dirname(full_path)
            os.makedirs(directory, exist_ok=True)
            
            # Write the file
            with open(full_path, 'wb') as f:
                f.write(content_data)
            return name
    
    def delete(self, name):
        """Delete a file from storage."""
        if self.file_storage_type == 's3':
            s3_client = get_s3_client()
            try:
                prefix = getattr(settings, 'AWS_S3_PROJECT_PREFIX', 'projects')
                s3_key = f"{prefix}/{name}"
                s3_client.delete_object(
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                    Key=s3_key
                )
                return True
            except Exception:
                return False
        else:
            file_path = os.path.join(self.location, name)
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
        return False
    
    def exists(self, name):
        """Check if a file exists in storage."""
        if self.file_storage_type == 's3':
            s3_client = get_s3_client()
            try:
                prefix = getattr(settings, 'AWS_S3_PROJECT_PREFIX', 'projects')
                s3_key = f"{prefix}/{name}"
                s3_client.head_object(
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                    Key=s3_key
                )
                return True
            except Exception:
                return False
        else:
            file_path = os.path.join(self.location, name)
            return os.path.exists(file_path)
        return False
    
    def url(self, name):
        """Return URL to access the file."""
        if self.file_storage_type == 's3':
            # For S3, generate a presigned URL for temporary access
            import boto3
            from botocore.exceptions import ClientError
            from botocore.config import Config
            
            region = getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1')
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=region,
                config=Config(signature_version='s3v4', region_name=region, s3={'addressing_style': 'virtual'})
            )
            
            try:
                prefix = getattr(settings, 'AWS_S3_PROJECT_PREFIX', 'projects')
                s3_key = f"{prefix}/{name}"
                
                # Debug logging
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Generating presigned URL for bucket: {settings.AWS_STORAGE_BUCKET_NAME}, key: {s3_key}")
                
                # Generate a presigned URL
                presigned_url = s3_client.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                        'Key': s3_key
                    },
                    ExpiresIn=getattr(settings, 'AWS_S3_PRESIGNED_URL_EXPIRY', 3600)
                )
                return presigned_url
            except ClientError as e:
                # Fallback to direct URL if presigned URL generation fails
                bucket_name = settings.AWS_STORAGE_BUCKET_NAME
                region = getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1')
                prefix = getattr(settings, 'AWS_S3_PROJECT_PREFIX', 'projects')
                return f"https://{bucket_name}.s3.{region}.amazonaws.com/{prefix}/{name}"
        else:
            # For local storage, use media URL
            return f"{self.base_url}{name}"
    
    def size(self, name):
        """Return the file size."""
        if self.file_storage_type == 's3':
            s3_client = get_s3_client()
            try:
                prefix = getattr(settings, 'AWS_S3_PROJECT_PREFIX', 'projects')
                s3_key = f"{prefix}/{name}"
                response = s3_client.head_object(
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                    Key=s3_key
                )
                return response['ContentLength']
            except Exception:
                return 0
        else:
            file_path = os.path.join(self.location, name)
            return os.path.getsize(file_path) if os.path.exists(file_path) else 0