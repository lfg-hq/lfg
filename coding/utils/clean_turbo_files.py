#!/usr/bin/env python
"""
Utility script to clean turbo mode generated files that may contain XML artifacts.
Usage: python clean_turbo_files.py <project_name>
"""

import sys
import os
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import Django settings
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LFG.settings')
django.setup()

from coding.utils.file_storage import get_file_storage, clean_turbo_file_content


def clean_project_files(project_name: str):
    """Clean all files in a project to remove XML artifacts."""
    storage = get_file_storage()
    
    # Get all files in the project
    files = storage.list_files(project_name)
    
    if not files:
        print(f"No files found for project: {project_name}")
        return
    
    print(f"Found {len(files)} files in project: {project_name}")
    
    cleaned_count = 0
    for file_path in files:
        try:
            # Read the file
            content = storage.get_file(project_name, file_path)
            if not content:
                continue
            
            # Clean the content
            cleaned_content = clean_turbo_file_content(content)
            
            # Only save if content changed
            if cleaned_content != content:
                success = storage.save_file(project_name, file_path, cleaned_content, create_new=False)
                if success:
                    print(f"✓ Cleaned: {file_path}")
                    cleaned_count += 1
                else:
                    print(f"✗ Failed to save: {file_path}")
            
        except Exception as e:
            print(f"✗ Error processing {file_path}: {e}")
    
    print(f"\nCleaned {cleaned_count} files")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python clean_turbo_files.py <project_name>")
        sys.exit(1)
    
    project_name = sys.argv[1]
    clean_project_files(project_name)