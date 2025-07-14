import os
import boto3
from django.conf import settings
from pathlib import Path
from typing import Optional, Union
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger(__name__)


class FileStorage:
    """
    Abstract file storage interface that can switch between local and S3 storage.
    """
    
    def save_file(self, project_name: str, file_path: str, content: str, create_new: bool = True) -> bool:
        """
        Save file content to storage.
        
        Args:
            project_name: Name of the project (root folder)
            file_path: Path relative to project root
            content: File content to save
            create_new: If True, creates new file; if False, overwrites existing
            
        Returns:
            bool: True if successful, False otherwise
        """
        raise NotImplementedError
    
    def get_file(self, project_name: str, file_path: str) -> Optional[str]:
        """
        Retrieve file content from storage.
        
        Args:
            project_name: Name of the project (root folder)
            file_path: Path relative to project root
            
        Returns:
            File content if found, None otherwise
        """
        raise NotImplementedError
    
    def file_exists(self, project_name: str, file_path: str) -> bool:
        """
        Check if file exists in storage.
        
        Args:
            project_name: Name of the project (root folder)
            file_path: Path relative to project root
            
        Returns:
            bool: True if file exists, False otherwise
        """
        raise NotImplementedError
    
    def delete_file(self, project_name: str, file_path: str) -> bool:
        """
        Delete file from storage.
        
        Args:
            project_name: Name of the project (root folder)
            file_path: Path relative to project root
            
        Returns:
            bool: True if successful, False otherwise
        """
        raise NotImplementedError
    
    def list_files(self, project_name: str, directory: str = "") -> list:
        """
        List all files in a directory.
        
        Args:
            project_name: Name of the project (root folder)
            directory: Directory path relative to project root (empty for root)
            
        Returns:
            List of file paths
        """
        raise NotImplementedError
    
    def get_project_structure(self, project_name: str) -> dict:
        """
        Get the complete project structure as a nested dictionary.
        
        Args:
            project_name: Name of the project (root folder)
            
        Returns:
            Dict representing the file structure
        """
        raise NotImplementedError
    
    def save_multiple_files(self, project_name: str, files: dict) -> dict:
        """
        Save multiple files at once (for turbo mode efficiency).
        
        Args:
            project_name: Name of the project (root folder)
            files: Dict of {file_path: content} to save
            
        Returns:
            Dict of {file_path: success_bool} indicating which files were saved
        """
        results = {}
        for file_path, content in files.items():
            results[file_path] = self.save_file(project_name, file_path, content, create_new=False)
        return results


class LocalFileStorage(FileStorage):
    """
    Local filesystem storage implementation.
    """
    
    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path) if base_path else Path(settings.MEDIA_ROOT) / "projects"
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def _get_full_path(self, project_name: str, file_path: str) -> Path:
        """Get full filesystem path."""
        return self.base_path / project_name / file_path
    
    def save_file(self, project_name: str, file_path: str, content: str, create_new: bool = True) -> bool:
        try:
            full_path = self._get_full_path(project_name, file_path)
            
            if create_new and full_path.exists():
                logger.warning(f"File already exists: {full_path}")
                return False
            
            # Create parent directories
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file
            full_path.write_text(content, encoding='utf-8')
            logger.info(f"Saved file: {full_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving file: {e}")
            return False
    
    def get_file(self, project_name: str, file_path: str) -> Optional[str]:
        try:
            full_path = self._get_full_path(project_name, file_path)
            
            if not full_path.exists():
                return None
            
            return full_path.read_text(encoding='utf-8')
            
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return None
    
    def file_exists(self, project_name: str, file_path: str) -> bool:
        full_path = self._get_full_path(project_name, file_path)
        return full_path.exists() and full_path.is_file()
    
    def delete_file(self, project_name: str, file_path: str) -> bool:
        try:
            full_path = self._get_full_path(project_name, file_path)
            
            if full_path.exists() and full_path.is_file():
                full_path.unlink()
                logger.info(f"Deleted file: {full_path}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            return False
    
    def list_files(self, project_name: str, directory: str = "") -> list:
        try:
            base_dir = self._get_full_path(project_name, directory)
            
            if not base_dir.exists():
                return []
            
            files = []
            for item in base_dir.rglob("*"):
                if item.is_file():
                    relative_path = item.relative_to(self.base_path / project_name)
                    files.append(str(relative_path))
            
            return sorted(files)
            
        except Exception as e:
            logger.error(f"Error listing files: {e}")
            return []
    
    def get_project_structure(self, project_name: str) -> dict:
        try:
            base_dir = self._get_full_path(project_name, "")
            
            if not base_dir.exists():
                return {}
            
            def build_tree(path: Path) -> dict:
                tree = {}
                for item in sorted(path.iterdir()):
                    if item.is_file():
                        tree[item.name] = "file"
                    elif item.is_dir():
                        tree[item.name] = build_tree(item)
                return tree
            
            return build_tree(base_dir)
            
        except Exception as e:
            logger.error(f"Error getting project structure: {e}")
            return {}


class S3FileStorage(FileStorage):
    """
    AWS S3 storage implementation.
    """
    
    def __init__(self, bucket_name: Optional[str] = None):
        self.bucket_name = bucket_name or settings.AWS_STORAGE_BUCKET_NAME
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1')
        )
        self.prefix = getattr(settings, 'AWS_S3_PROJECT_PREFIX', 'projects')
    
    def _get_s3_key(self, project_name: str, file_path: str) -> str:
        """Get S3 object key."""
        return f"{self.prefix}/{project_name}/{file_path}"
    
    def save_file(self, project_name: str, file_path: str, content: str, create_new: bool = True) -> bool:
        try:
            s3_key = self._get_s3_key(project_name, file_path)
            
            if create_new and self.file_exists(project_name, file_path):
                logger.warning(f"File already exists: {s3_key}")
                return False
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=content.encode('utf-8'),
                ContentType='text/plain',
                ContentEncoding='utf-8'
            )
            
            logger.info(f"Saved file to S3: {s3_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Error saving to S3: {e}")
            return False
    
    def get_file(self, project_name: str, file_path: str) -> Optional[str]:
        try:
            s3_key = self._get_s3_key(project_name, file_path)
            
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            return response['Body'].read().decode('utf-8')
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return None
            logger.error(f"Error reading from S3: {e}")
            return None
    
    def file_exists(self, project_name: str, file_path: str) -> bool:
        try:
            s3_key = self._get_s3_key(project_name, file_path)
            
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            return True
            
        except ClientError:
            return False
    
    def delete_file(self, project_name: str, file_path: str) -> bool:
        try:
            s3_key = self._get_s3_key(project_name, file_path)
            
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            logger.info(f"Deleted file from S3: {s3_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Error deleting from S3: {e}")
            return False
    
    def list_files(self, project_name: str, directory: str = "") -> list:
        try:
            prefix = self._get_s3_key(project_name, directory)
            if not prefix.endswith('/') and directory:
                prefix += '/'
            
            files = []
            paginator = self.s3_client.get_paginator('list_objects_v2')
            
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        # Skip directories
                        if not obj['Key'].endswith('/'):
                            # Remove prefix to get relative path
                            relative_key = obj['Key'].replace(f"{self.prefix}/{project_name}/", '')
                            files.append(relative_key)
            
            return sorted(files)
            
        except ClientError as e:
            logger.error(f"Error listing S3 files: {e}")
            return []
    
    def get_project_structure(self, project_name: str) -> dict:
        try:
            prefix = self._get_s3_key(project_name, "")
            
            # Get all files
            files = self.list_files(project_name)
            
            # Build tree structure
            tree = {}
            for file_path in files:
                parts = file_path.split('/')
                current = tree
                
                for i, part in enumerate(parts):
                    if i == len(parts) - 1:
                        # It's a file
                        current[part] = "file"
                    else:
                        # It's a directory
                        if part not in current:
                            current[part] = {}
                        current = current[part]
            
            return tree
            
        except Exception as e:
            logger.error(f"Error getting S3 project structure: {e}")
            return {}


def get_file_storage() -> FileStorage:
    """
    Factory function to get the appropriate file storage instance based on settings.
    
    Returns:
        FileStorage instance (LocalFileStorage or S3FileStorage)
    """
    storage_type = getattr(settings, 'FILE_STORAGE_TYPE', 'local').lower()
    
    if storage_type == 's3':
        return S3FileStorage()
    else:
        return LocalFileStorage()


def clean_turbo_file_content(content: str) -> str:
    """
    Clean file content generated by turbo mode to remove any XML tag artifacts.
    
    Args:
        content: Raw file content that may contain XML artifacts
        
    Returns:
        Cleaned file content
    """
    import re
    
    # Remove any lfg tags
    content = re.sub(r'</?lfg-[^>]*>', '', content)
    
    # Remove file path patterns like: package.json">
    content = re.sub(r'^[^"\n]+">[\n\r]*', '', content, flags=re.MULTILINE)
    
    # Remove any remaining tag fragments at the start of lines
    content = re.sub(r'^[^>]*>[\n\r]*', '', content, flags=re.MULTILINE)
    
    # Remove closing tag fragments like: </lfg-
    content = re.sub(r'</lfg-[^>]*$', '', content, flags=re.MULTILINE)
    
    # Remove any lines that are just tag remnants
    lines = content.split('\n')
    cleaned_lines = []
    for line in lines:
        # Skip lines that look like broken tags
        if line.strip() and not (line.strip().endswith('">') and '"' not in line[:-2]):
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)