import os
import json
import uuid
from typing import Optional, Dict, Tuple
from django.conf import settings
from django.core.files.base import ContentFile
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
import logging

logger = logging.getLogger(__name__)


class ProjectS3Storage:
    """
    S3 storage handler for project-related files (PRDs, Implementations, etc.)
    """
    
    def __init__(self):
        self.storage_type = getattr(settings, 'FILE_STORAGE_TYPE', 'local').lower()
        if self.storage_type == 's3':
            self.s3_client = self._get_s3_client()
            self.bucket_name = settings.AWS_STORAGE_BUCKET_NAME
            self.prefix = getattr(settings, 'AWS_S3_PROJECT_PREFIX', 'projects')
        else:
            # For local storage, use media root
            self.local_base_path = os.path.join(settings.MEDIA_ROOT, 'projects')
            os.makedirs(self.local_base_path, exist_ok=True)
    
    def _get_s3_client(self):
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
    
    def _generate_file_key(self, project_id: str, file_type: str, file_name: str = None) -> str:
        """
        Generate a unique file key for S3/local storage
        
        Args:
            project_id: The project ID
            file_type: Type of file (e.g., 'prd', 'implementation')
            file_name: Optional specific filename
        
        Returns:
            The file key/path
        """
        if not file_name:
            # Generate unique filename with timestamp
            timestamp = uuid.uuid4().hex[:8]
            file_name = f"{file_type}_{timestamp}.json"
        
        # Ensure file_name has .json extension if not present
        if not file_name.endswith('.json'):
            file_name = f"{file_name}.json"
        
        return f"{project_id}/{file_type}/{file_name}"
    
    def save_file(self, project_id: str, file_type: str, content: str, 
                  file_name: str = None, metadata: Dict = None) -> Tuple[bool, str, Optional[str]]:
        """
        Save a file to S3 or local storage
        
        Args:
            project_id: The project ID
            file_type: Type of file (e.g., 'prd', 'implementation')
            content: The content to save
            file_name: Optional specific filename
            metadata: Optional metadata dict
        
        Returns:
            Tuple of (success, file_key, error_message)
        """
        try:
            file_key = self._generate_file_key(project_id, file_type, file_name)
            
            # Prepare content as JSON
            content_data = {
                'content': content,
                'metadata': metadata or {},
                'type': file_type
            }
            json_content = json.dumps(content_data, indent=2)
            
            if self.storage_type == 's3':
                # Save to S3
                s3_key = f"{self.prefix}/{file_key}"
                
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=json_content.encode('utf-8'),
                    ContentType='application/json',
                    Metadata={
                        'project_id': project_id,
                        'file_type': file_type
                    }
                )
                
                logger.info(f"Saved {file_type} to S3: {s3_key}")
                return True, file_key, None
                
            else:
                # Save to local filesystem
                full_path = os.path.join(self.local_base_path, file_key)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(json_content)
                
                logger.info(f"Saved {file_type} to local storage: {full_path}")
                return True, file_key, None
                
        except Exception as e:
            error_msg = f"Failed to save {file_type}: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg
    
    def load_file(self, file_key: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Load a file from S3 or local storage
        
        Args:
            file_key: The file key/path
        
        Returns:
            Tuple of (success, content, error_message)
        """
        try:
            if self.storage_type == 's3':
                # Load from S3
                s3_key = f"{self.prefix}/{file_key}"
                
                response = self.s3_client.get_object(
                    Bucket=self.bucket_name,
                    Key=s3_key
                )
                
                json_content = response['Body'].read().decode('utf-8')
                data = json.loads(json_content)
                
                logger.info(f"Loaded file from S3: {s3_key}")
                return True, data.get('content', ''), None
                
            else:
                # Load from local filesystem
                full_path = os.path.join(self.local_base_path, file_key)
                
                if not os.path.exists(full_path):
                    return False, None, f"File not found: {file_key}"
                
                with open(full_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                logger.info(f"Loaded file from local storage: {full_path}")
                return True, data.get('content', ''), None
                
        except Exception as e:
            error_msg = f"Failed to load file: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg
    
    def delete_file(self, file_key: str) -> Tuple[bool, Optional[str]]:
        """
        Delete a file from S3 or local storage
        
        Args:
            file_key: The file key/path
        
        Returns:
            Tuple of (success, error_message)
        """
        try:
            if self.storage_type == 's3':
                # Delete from S3
                s3_key = f"{self.prefix}/{file_key}"
                
                self.s3_client.delete_object(
                    Bucket=self.bucket_name,
                    Key=s3_key
                )
                
                logger.info(f"Deleted file from S3: {s3_key}")
                return True, None
                
            else:
                # Delete from local filesystem
                full_path = os.path.join(self.local_base_path, file_key)
                
                if os.path.exists(full_path):
                    os.remove(full_path)
                    logger.info(f"Deleted file from local storage: {full_path}")
                
                return True, None
                
        except Exception as e:
            error_msg = f"Failed to delete file: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def get_file_url(self, file_key: str, expiry_seconds: int = 3600) -> Optional[str]:
        """
        Get a URL to access the file
        
        Args:
            file_key: The file key/path
            expiry_seconds: URL expiry time for S3 presigned URLs
        
        Returns:
            The file URL or None if error
        """
        try:
            if self.storage_type == 's3':
                # Generate presigned URL
                s3_key = f"{self.prefix}/{file_key}"
                
                url = self.s3_client.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': self.bucket_name,
                        'Key': s3_key
                    },
                    ExpiresIn=expiry_seconds
                )
                
                return url
                
            else:
                # Return local media URL
                return f"{settings.MEDIA_URL}projects/{file_key}"
                
        except Exception as e:
            logger.error(f"Failed to get file URL: {str(e)}")
            return None
    
    def list_project_files(self, project_id: str, file_type: str = None) -> list:
        """
        List all files for a project
        
        Args:
            project_id: The project ID
            file_type: Optional filter by file type
        
        Returns:
            List of file keys
        """
        try:
            prefix = project_id
            if file_type:
                prefix = f"{project_id}/{file_type}/"
            
            files = []
            
            if self.storage_type == 's3':
                # List from S3
                full_prefix = f"{self.prefix}/{prefix}"
                
                paginator = self.s3_client.get_paginator('list_objects_v2')
                for page in paginator.paginate(Bucket=self.bucket_name, Prefix=full_prefix):
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            # Remove the base prefix to get relative key
                            relative_key = obj['Key'].replace(f"{self.prefix}/", '')
                            files.append(relative_key)
                            
            else:
                # List from local filesystem
                base_path = os.path.join(self.local_base_path, prefix)
                
                if os.path.exists(base_path):
                    for root, dirs, filenames in os.walk(base_path):
                        for filename in filenames:
                            if filename.endswith('.json'):
                                full_path = os.path.join(root, filename)
                                relative_key = os.path.relpath(full_path, self.local_base_path)
                                files.append(relative_key.replace('\\', '/'))  # Normalize path separators
            
            return sorted(files)
            
        except Exception as e:
            logger.error(f"Failed to list project files: {str(e)}")
            return []


# Singleton instance
project_s3_storage = ProjectS3Storage()