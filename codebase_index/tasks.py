"""
Background tasks for codebase indexing using Django-Q2
"""

import logging
from typing import Optional, Dict, Any
from django.utils import timezone
from django_q.tasks import async_task, result
from django_q.models import Task

logger = logging.getLogger(__name__)


def index_repository_task(repository_id: int, force_full_reindex: bool = False, user_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Background task to index a repository
    
    Args:
        repository_id: ID of the IndexedRepository to index
        force_full_reindex: Whether to force a complete reindex
        user_id: ID of user who initiated the task
    
    Returns:
        Dictionary with task results
    """
    from .models import IndexedRepository, IndexingJob
    from .github_sync import RepositoryIndexer
    from .embeddings import generate_repository_insights
    from django.contrib.auth.models import User
    
    # Get repository
    try:
        repository = IndexedRepository.objects.get(id=repository_id)
    except IndexedRepository.DoesNotExist:
        error_msg = f"IndexedRepository with id {repository_id} not found"
        logger.error(error_msg)
        return {'success': False, 'error': error_msg}
    
    # Get user if provided
    user = None
    if user_id:
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.warning(f"User with id {user_id} not found")
    
    # Create indexing job record
    job = IndexingJob.objects.create(
        repository=repository,
        job_type='full_index' if force_full_reindex else 'incremental_update',
        status='running',
        started_by=user,
        started_at=timezone.now()
    )
    
    try:
        logger.info(f"Starting indexing task for repository {repository.github_repo_name}")
        
        # Update repository status
        repository.status = 'indexing'
        repository.save()
        
        # Perform indexing
        indexer = RepositoryIndexer(repository)
        success, message = indexer.index_repository(force_full_reindex)
        
        # Update job status
        if success:
            job.status = 'completed'
            job.result_summary = {
                'message': message,
                'indexed_files': repository.indexed_files_count,
                'total_chunks': repository.total_chunks,
            }
            
            # Generate repository insights
            try:
                insights = generate_repository_insights(repository)
                job.result_summary['insights'] = insights
            except Exception as e:
                logger.warning(f"Failed to generate insights: {e}")
                job.result_summary['insights_error'] = str(e)

            # Generate AI-powered codebase summary
            try:
                from .embeddings import generate_and_store_codebase_summary
                logger.info("Generating AI-powered codebase summary...")
                summary_result = generate_and_store_codebase_summary(repository)
                if summary_result.get('success'):
                    logger.info("Codebase summary generated successfully")
                    job.result_summary['summary_generated'] = True
                else:
                    logger.warning(f"Failed to generate codebase summary: {summary_result.get('error')}")
                    job.result_summary['summary_error'] = summary_result.get('error')
            except Exception as e:
                logger.warning(f"Failed to generate codebase summary: {e}")
                job.result_summary['summary_error'] = str(e)

            logger.info(f"Repository indexing completed successfully: {message}")
            
        else:
            job.status = 'failed'
            job.error_logs = message
            repository.status = 'error'
            repository.error_message = message
            repository.save()
            
            logger.error(f"Repository indexing failed: {message}")
        
        job.completed_at = timezone.now()
        job.save()
        
        # Send WebSocket notification if needed
        _send_indexing_notification(repository, job, success, message)
        
        return {
            'success': success,
            'message': message,
            'job_id': job.id,
            'repository_id': repository.id,
            'insights': job.result_summary.get('insights') if success else None
        }
        
    except Exception as e:
        error_msg = f"Unexpected error during indexing: {str(e)}"
        logger.exception(error_msg)
        
        # Update job with error
        job.status = 'failed'
        job.error_logs = error_msg
        job.completed_at = timezone.now()
        job.save()
        
        # Update repository status
        repository.status = 'error'
        repository.error_message = error_msg
        repository.save()
        
        return {
            'success': False,
            'error': error_msg,
            'job_id': job.id,
            'repository_id': repository.id
        }


def cleanup_old_embeddings_task(repository_id: int) -> Dict[str, Any]:
    """
    Background task to clean up old embeddings from ChromaDB
    
    Args:
        repository_id: ID of the IndexedRepository to clean
    
    Returns:
        Dictionary with cleanup results
    """
    from .models import IndexedRepository, IndexingJob
    from .chroma_client import get_chroma_client
    
    try:
        repository = IndexedRepository.objects.get(id=repository_id)
    except IndexedRepository.DoesNotExist:
        return {'success': False, 'error': f'Repository {repository_id} not found'}
    
    # Create cleanup job
    job = IndexingJob.objects.create(
        repository=repository,
        job_type='cleanup',
        status='running',
        started_at=timezone.now()
    )
    
    try:
        chroma_client = get_chroma_client()
        collection_name = repository.get_chroma_collection_name()
        
        # Delete the entire collection
        success = chroma_client.delete_collection(collection_name)
        
        if success:
            # Reset embedding status for all chunks
            repository.files.all().update(embedding_stored=False)
            
            job.status = 'completed'
            job.result_summary = {'message': 'Successfully cleaned up embeddings'}
            logger.info(f"Cleaned up embeddings for repository {repository.github_repo_name}")
            
        else:
            job.status = 'failed'
            job.error_logs = 'Failed to delete ChromaDB collection'
            logger.error(f"Failed to clean up embeddings for repository {repository.github_repo_name}")
        
        job.completed_at = timezone.now()
        job.save()
        
        return {
            'success': success,
            'message': job.result_summary.get('message') if success else job.error_logs,
            'job_id': job.id
        }
        
    except Exception as e:
        error_msg = f"Error during cleanup: {str(e)}"
        logger.exception(error_msg)
        
        job.status = 'failed'
        job.error_logs = error_msg
        job.completed_at = timezone.now()
        job.save()
        
        return {'success': False, 'error': error_msg, 'job_id': job.id}


def _send_indexing_notification(repository, job, success: bool, message: str):
    """Send WebSocket notification about indexing completion"""
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        channel_layer = get_channel_layer()
        if not channel_layer:
            return
        
        notification = {
            'type': 'indexing_update',
            'repository_id': repository.id,
            'job_id': job.id,
            'status': 'completed' if success else 'failed',
            'message': message,
            'progress': repository.indexing_progress,
            'timestamp': timezone.now().isoformat()
        }
        
        # Send to project-specific group
        group_name = f"project_{repository.project.project_id}"
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'send_notification',
                'notification': notification
            }
        )
        
    except Exception as e:
        logger.warning(f"Failed to send indexing notification: {e}")


# Convenience functions for starting tasks

def start_repository_indexing(repository_id: int, force_full_reindex: bool = False, user_id: Optional[int] = None) -> str:
    """
    Start repository indexing task
    
    Returns:
        Task ID for tracking
    """
    task_id = async_task(
        'codebase_index.tasks.index_repository_task',
        repository_id,
        force_full_reindex,
        user_id,
        task_name=f'index_repo_{repository_id}',
        timeout=3600,  # 1 hour timeout
    )
    
    logger.info(f"Started repository indexing task {task_id} for repository {repository_id}")
    return task_id


def start_embedding_cleanup(repository_id: int) -> str:
    """
    Start embedding cleanup task
    
    Returns:
        Task ID for tracking
    """
    task_id = async_task(
        'codebase_index.tasks.cleanup_old_embeddings_task',
        repository_id,
        task_name=f'cleanup_embeddings_{repository_id}',
        timeout=300,  # 5 minutes timeout
    )
    
    logger.info(f"Started embedding cleanup task {task_id} for repository {repository_id}")
    return task_id


def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    Get status of a background task
    
    Args:
        task_id: Django-Q task ID
    
    Returns:
        Dictionary with task status information
    """
    try:
        task = Task.objects.get(id=task_id)
        
        status_info = {
            'id': task.id,
            'name': task.name,
            'func': task.func,
            'started': task.started,
            'stopped': task.stopped,
            'success': task.success,
            'result': task.result,
            'group': task.group,
        }
        
        return status_info
        
    except Task.DoesNotExist:
        return {'error': f'Task {task_id} not found'}
    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        return {'error': str(e)}