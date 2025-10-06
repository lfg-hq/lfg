"""
Management command to fix missing embeddings in ChromaDB
"""

import logging
import time
from django.core.management.base import BaseCommand, CommandError
from codebase_index.models import CodeChunk, IndexedRepository
from codebase_index.chroma_client import get_chroma_client

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fix missing embeddings by processing chunks that failed to store in ChromaDB'

    def add_arguments(self, parser):
        parser.add_argument(
            '--repository-id',
            type=int,
            help='Process only specific repository ID'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=20,
            help='Number of chunks to process per batch (default: 20)'
        )
        parser.add_argument(
            '--max-batches',
            type=int,
            help='Maximum number of batches to process (for testing)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without making changes'
        )

    def handle(self, *args, **options):
        repository_id = options.get('repository_id')
        batch_size = options['batch_size']
        max_batches = options.get('max_batches')
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        # Get repositories to process
        if repository_id:
            try:
                repositories = [IndexedRepository.objects.get(id=repository_id)]
            except IndexedRepository.DoesNotExist:
                raise CommandError(f'Repository with ID {repository_id} not found')
        else:
            repositories = IndexedRepository.objects.filter(status='completed')

        # Initialize ChromaDB client
        if not dry_run:
            try:
                chroma_client = get_chroma_client()
            except Exception as e:
                raise CommandError(f'Failed to initialize ChromaDB client: {e}')

        total_processed = 0
        total_failed = 0

        for repo in repositories:
            self.stdout.write(f'\nProcessing repository: {repo.github_repo_name}')
            
            # Get chunks that need embeddings
            chunks_to_process = CodeChunk.objects.filter(
                file__repository=repo, 
                embedding_stored=False
            )
            
            total_chunks = chunks_to_process.count()
            self.stdout.write(f'Found {total_chunks} chunks missing embeddings')
            
            if total_chunks == 0:
                self.stdout.write(self.style.SUCCESS('✓ All chunks already have embeddings'))
                continue
                
            if dry_run:
                self.stdout.write(f'Would process {total_chunks} chunks in {(total_chunks + batch_size - 1) // batch_size} batches')
                continue

            collection_name = repo.get_chroma_collection_name()
            batch_count = 0
            
            for i in range(0, total_chunks, batch_size):
                if max_batches and batch_count >= max_batches:
                    self.stdout.write(f'Reached max batches limit ({max_batches})')
                    break
                    
                batch = chunks_to_process[i:i+batch_size]
                batch_list = list(batch)
                batch_count += 1
                
                self.stdout.write(f'Processing batch {batch_count}/{(total_chunks + batch_size - 1)//batch_size} ({len(batch_list)} chunks)...')
                
                # Prepare chunks for ChromaDB
                chroma_chunks = []
                chunk_ids = []
                
                for chunk in batch_list:
                    chroma_chunks.append({
                        'id': str(chunk.chunk_id),
                        'content': chunk.content,
                        'metadata': chunk.get_metadata_dict()
                    })
                    chunk_ids.append(chunk.id)
                
                try:
                    # Add to ChromaDB
                    success = chroma_client.add_code_chunks(collection_name, chroma_chunks)
                    
                    if success:
                        # Mark as stored
                        updated_count = CodeChunk.objects.filter(id__in=chunk_ids).update(embedding_stored=True)
                        total_processed += updated_count
                        self.stdout.write(self.style.SUCCESS(f'✓ Batch successful - {updated_count} chunks processed'))
                    else:
                        total_failed += len(batch_list)
                        self.stdout.write(self.style.ERROR(f'✗ Batch failed - check logs for details'))
                        
                    # Small delay to avoid rate limits
                    time.sleep(1)
                    
                except Exception as e:
                    total_failed += len(batch_list)
                    self.stdout.write(self.style.ERROR(f'✗ Batch error: {e}'))
                    logger.error(f'Batch processing error: {e}')

            # Final stats for this repository
            if not dry_run:
                stats = chroma_client.get_collection_stats(collection_name)
                remaining_chunks = CodeChunk.objects.filter(
                    file__repository=repo,
                    embedding_stored=False
                ).count()
                
                self.stdout.write(f'Repository {repo.github_repo_name} results:')
                self.stdout.write(f'  ChromaDB documents: {stats["total_documents"]}')
                self.stdout.write(f'  Remaining chunks: {remaining_chunks}')

        # Overall summary
        if not dry_run:
            self.stdout.write(f'\n=== Overall Results ===')
            self.stdout.write(f'Total processed: {total_processed}')
            self.stdout.write(f'Total failed: {total_failed}')
            
            if total_processed > 0:
                self.stdout.write(self.style.SUCCESS(f'✓ Successfully processed {total_processed} chunks'))
            if total_failed > 0:
                self.stdout.write(self.style.ERROR(f'✗ Failed to process {total_failed} chunks'))