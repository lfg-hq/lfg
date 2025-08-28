#!/usr/bin/env python
"""
One-time script to migrate existing ProjectPRD and ProjectImplementation data to ProjectFile model
"""
import os
import sys
import django
import logging

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LFG.settings')
django.setup()

from projects.models import Project, ProjectPRD, ProjectImplementation, ProjectFile

logger = logging.getLogger(__name__)

def migrate_prds_to_files():
    """Migrate ProjectPRD entries to ProjectFile"""
    logger.info("Migrating PRDs to ProjectFile...")
    
    prds = ProjectPRD.objects.all()
    migrated = 0
    skipped = 0
    
    for prd in prds:
        # Check if already exists
        existing = ProjectFile.objects.filter(
            project=prd.project,
            file_type='prd',
            name=prd.name
        ).first()
        
        if existing:
            logger.info(f"  Skipping {prd.project.name} - {prd.name} (already exists)")
            skipped += 1
            continue
        
        # Create new ProjectFile
        file_obj = ProjectFile.objects.create(
            project=prd.project,
            name=prd.name,
            file_type='prd',
            content=prd.prd,
            is_active=prd.is_active,
            created_at=prd.created_at,
            updated_at=prd.updated_at
        )
        
        # Manually set timestamps to preserve original
        ProjectFile.objects.filter(id=file_obj.id).update(
            created_at=prd.created_at,
            updated_at=prd.updated_at
        )
        
        logger.info(f"  Migrated {prd.project.name} - {prd.name}")
        migrated += 1
    
    logger.info(f"PRDs: Migrated {migrated}, Skipped {skipped}")
    return migrated, skipped

def migrate_implementations_to_files():
    """Migrate ProjectImplementation entries to ProjectFile"""
    logger.info("\nMigrating Implementations to ProjectFile...")
    
    implementations = ProjectImplementation.objects.all()
    migrated = 0
    skipped = 0
    
    for impl in implementations:
        # Check if already exists
        existing = ProjectFile.objects.filter(
            project=impl.project,
            file_type='implementation',
            name='Technical Implementation Plan'
        ).first()
        
        if existing:
            logger.info(f"  Skipping {impl.project.name} implementation (already exists)")
            skipped += 1
            continue
        
        # Create new ProjectFile
        file_obj = ProjectFile.objects.create(
            project=impl.project,
            name='Technical Implementation Plan',
            file_type='implementation',
            content=impl.implementation,
            is_active=True,
            created_at=impl.created_at,
            updated_at=impl.updated_at
        )
        
        # Manually set timestamps to preserve original
        ProjectFile.objects.filter(id=file_obj.id).update(
            created_at=impl.created_at,
            updated_at=impl.updated_at
        )
        
        logger.info(f"  Migrated {impl.project.name} implementation")
        migrated += 1
    
    logger.info(f"Implementations: Migrated {migrated}, Skipped {skipped}")
    return migrated, skipped

if __name__ == '__main__':
    logger.info("Starting migration of PRDs and Implementations to ProjectFile model...")
    
    prd_migrated, prd_skipped = migrate_prds_to_files()
    impl_migrated, impl_skipped = migrate_implementations_to_files()
    
    logger.info(f"\nMigration complete!")
    logger.info(f"Total migrated: {prd_migrated + impl_migrated}")
    logger.info(f"Total skipped: {prd_skipped + impl_skipped}")