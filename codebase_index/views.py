from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.urls import reverse
import json
import logging

from projects.models import Project
from .models import IndexedRepository, IndexingJob, CodebaseQuery
from .tasks import start_repository_indexing, start_embedding_cleanup
from .github_sync import validate_github_access


logger = logging.getLogger(__name__)


@login_required
def repository_list(request):
    """List all indexed repositories for the user's projects"""
    user_projects = Project.objects.filter(owner=request.user)
    
    indexed_repos = IndexedRepository.objects.filter(
        project__in=user_projects
    ).select_related('project').order_by('-updated_at')
    
    context = {
        'indexed_repositories': indexed_repos,
        'user_projects': user_projects,
    }
    
    return render(request, 'codebase_index/repository_list.html', context)


@login_required
def repository_detail(request, repository_id):
    """Detail view for an indexed repository"""
    indexed_repo = get_object_or_404(
        IndexedRepository, 
        id=repository_id, 
        project__owner=request.user
    )
    
    # Get recent indexing jobs
    recent_jobs = IndexingJob.objects.filter(
        repository=indexed_repo
    ).order_by('-queued_at')[:10]
    
    # Get recent queries
    recent_queries = CodebaseQuery.objects.filter(
        project=indexed_repo.project
    ).order_by('-created_at')[:10]
    
    context = {
        'repository': indexed_repo,
        'recent_jobs': recent_jobs,
        'recent_queries': recent_queries,
    }
    
    return render(request, 'codebase_index/repository_detail.html', context)


@login_required
@require_http_methods(["POST"])
def add_repository(request):
    """Add a new repository for indexing"""
    try:
        data = json.loads(request.body)
        project_id = data.get('project_id')
        github_url = data.get('github_url')
        branch = data.get('branch', 'main')
        
        # Validate inputs
        if not project_id or not github_url:
            return JsonResponse({
                'success': False,
                'error': 'project_id and github_url are required'
            }, status=400)
        
        # Get project and validate ownership
        project = get_object_or_404(Project, project_id=project_id, owner=request.user)
        
        # Validate GitHub access
        valid, message, repo_info = validate_github_access(request.user, github_url)
        if not valid:
            return JsonResponse({
                'success': False,
                'error': f'GitHub access validation failed: {message}'
            }, status=400)
        
        # Create indexed repository
        indexed_repo, created = IndexedRepository.objects.get_or_create(
            project=project,
            defaults={
                'github_url': github_url,
                'github_owner': repo_info['owner'],
                'github_repo_name': repo_info['repo'],
                'github_branch': branch,
                'status': 'pending'
            }
        )
        
        if not created:
            # Update existing repository
            indexed_repo.github_url = github_url
            indexed_repo.github_branch = branch
            indexed_repo.status = 'pending'
            indexed_repo.save()
        
        # Start indexing
        task_id = start_repository_indexing(indexed_repo.id, False, request.user.id)
        
        return JsonResponse({
            'success': True,
            'message': f'Repository {repo_info["owner"]}/{repo_info["repo"]} added and indexing started',
            'repository_id': indexed_repo.id,
            'task_id': task_id
        })
        
    except Exception as e:
        logger.error(f"Error adding repository: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def reindex_repository(request, repository_id):
    """Trigger re-indexing of a repository"""
    try:
        indexed_repo = get_object_or_404(
            IndexedRepository,
            id=repository_id,
            project__owner=request.user
        )
        
        # # Check if already indexing
        # if indexed_repo.status == 'indexing':
        #     return JsonResponse({
        #         'success': False,
        #         'error': 'Repository is already being indexed'
        #     }, status=400)
        
        # Start reindexing
        task_id = start_repository_indexing(indexed_repo.id, True, request.user.id)
        
        return JsonResponse({
            'success': True,
            'message': f'Re-indexing started for {indexed_repo.github_repo_name}',
            'task_id': task_id
        })
        
    except Exception as e:
        logger.error(f"Error starting re-indexing: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def delete_repository(request, repository_id):
    """Delete a repository and its embeddings"""
    try:
        indexed_repo = get_object_or_404(
            IndexedRepository,
            id=repository_id,
            project__owner=request.user
        )
        
        # Start cleanup task to remove embeddings
        cleanup_task_id = start_embedding_cleanup(indexed_repo.id)
        
        # Delete the repository record (this will cascade to files and chunks)
        repo_name = indexed_repo.github_repo_name
        indexed_repo.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Repository {repo_name} deleted and embeddings cleanup started',
            'cleanup_task_id': cleanup_task_id
        })
        
    except Exception as e:
        logger.error(f"Error deleting repository: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def repository_status(request, repository_id):
    """Get current status of repository indexing"""
    try:
        indexed_repo = get_object_or_404(
            IndexedRepository,
            id=repository_id,
            project__owner=request.user
        )
        
        # Get latest job
        latest_job = IndexingJob.objects.filter(
            repository=indexed_repo
        ).order_by('-queued_at').first()
        
        status_data = {
            'status': indexed_repo.status,
            'progress': indexed_repo.indexing_progress,
            'total_files': indexed_repo.total_files,
            'indexed_files': indexed_repo.indexed_files_count,
            'total_chunks': indexed_repo.total_chunks,
            'total_entities': indexed_repo.total_entities,
            'last_indexed_at': indexed_repo.last_indexed_at.isoformat() if indexed_repo.last_indexed_at else None,
            'error_message': indexed_repo.error_message,
        }
        
        if latest_job:
            status_data['latest_job'] = {
                'job_type': latest_job.job_type,
                'status': latest_job.status,
                'progress': latest_job.progress_percentage,
                'queued_at': latest_job.queued_at.isoformat(),
                'started_at': latest_job.started_at.isoformat() if latest_job.started_at else None,
                'completed_at': latest_job.completed_at.isoformat() if latest_job.completed_at else None,
            }
        
        return JsonResponse(status_data)
        
    except Exception as e:
        logger.error(f"Error getting repository status: {e}")
        return JsonResponse({
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def search_codebase(request):
    """Search the codebase for specific functionality"""
    try:
        data = json.loads(request.body)
        project_id = data.get('project_id')
        query = data.get('query')
        n_results = data.get('n_results', 10)
        
        if not project_id or not query:
            return JsonResponse({
                'success': False,
                'error': 'project_id and query are required'
            }, status=400)
        
        # Get project and validate ownership
        project = get_object_or_404(Project, project_id=project_id, owner=request.user)
        
        # Check if repository is indexed
        try:
            indexed_repo = project.indexed_repository
            if indexed_repo.status != 'completed':
                return JsonResponse({
                    'success': False,
                    'error': f'Repository not fully indexed (status: {indexed_repo.status})'
                }, status=400)
        except IndexedRepository.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'No repository indexed for this project'
            }, status=400)
        
        # Perform direct ChromaDB search
        from .chroma_client import get_chroma_client
        
        try:
            chroma_client = get_chroma_client()
            collection_name = indexed_repo.get_chroma_collection_name()
            
            # Query ChromaDB directly for better results format
            results = chroma_client.query_similar_code(
                collection_name=collection_name,
                query_texts=[query],
                n_results=min(n_results, 20)
            )
            
            # Convert ChromaDB results to our expected format
            search_results = []
            if results and results.get('documents') and results['documents'][0]:
                documents = results['documents'][0]
                metadatas = results.get('metadatas', [[]])[0]
                distances = results.get('distances', [[]])[0]
                
                for i, (document, metadata, distance) in enumerate(zip(documents, metadatas, distances)):
                    # Convert cosine distance to similarity percentage
                    # Cosine distance: 0 = identical, 2 = opposite
                    # Good matches are typically 0.8-1.5, poor matches 1.5+
                    if distance is not None:
                        # Use exponential decay for better differentiation
                        import math
                        similarity = max(0, min(100, round(100 * math.exp(-distance/2))))
                    else:
                        similarity = 100
                    
                    search_results.append({
                        'document': document,
                        'content': document,
                        'metadata': metadata,
                        'distance': distance,
                        'similarity': similarity
                    })
            
            # Log the query for analytics
            try:
                CodebaseQuery.objects.create(
                    project=project,
                    user=request.user,
                    query_text=query,
                    retrieved_chunks=[r.get('metadata', {}).get('chunk_id') for r in search_results if r.get('metadata', {}).get('chunk_id')],
                    relevance_scores=[r.get('similarity', 0) for r in search_results],
                    context_used="",  # Not used in direct search
                    retrieval_time_ms=0,  # Could be calculated if needed
                    total_chunks_considered=len(search_results)
                )
            except Exception as e:
                logger.warning(f"Failed to log search query: {e}")  # Better error logging
            
            return JsonResponse({
                'success': True,
                'results': search_results,
                'total_results': len(search_results),
                'query': query
            })
            
        except Exception as e:
            logger.error(f"ChromaDB search error: {e}")
            return JsonResponse({
                'success': False,
                'error': f'Search failed: {str(e)}'
            }, status=500)
        
    except Exception as e:
        logger.error(f"Error searching codebase: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def codebase_analytics(request, project_id):
    """Analytics view for codebase usage"""
    project = get_object_or_404(Project, project_id=project_id, owner=request.user)
    
    try:
        indexed_repo = project.indexed_repository
    except IndexedRepository.DoesNotExist:
        messages.error(request, "No repository indexed for this project")
        return redirect('projects:project_detail', project_id=project_id)
    
    # Get query analytics
    queries = CodebaseQuery.objects.filter(
        project=project
    ).order_by('-created_at')[:50]
    
    # Calculate analytics
    analytics = {
        'total_queries': queries.count(),
        'avg_retrieval_time': sum(q.retrieval_time_ms for q in queries) / len(queries) if queries else 0,
        'queries_with_prd': queries.filter(enhanced_prd_generated=True).count(),
    }
    
    context = {
        'project': project,
        'repository': indexed_repo,
        'recent_queries': queries[:20],
        'analytics': analytics,
    }
    
    return render(request, 'codebase_index/analytics.html', context)


@login_required
@require_http_methods(["POST"])
def update_repository_url(request, repository_id):
    """Update the GitHub URL for an indexed repository"""
    try:
        indexed_repo = get_object_or_404(
            IndexedRepository,
            id=repository_id,
            project__owner=request.user
        )
        
        data = json.loads(request.body)
        new_github_url = data.get('github_url')
        
        if not new_github_url:
            return JsonResponse({
                'success': False,
                'error': 'GitHub URL is required'
            }, status=400)
        
        # Validate the new URL
        from .github_sync import GitHubRepositoryManager
        github_manager = GitHubRepositoryManager(request.user)
        valid, message, repo_info = github_manager.validate_repository_access(new_github_url)
        
        if not valid:
            return JsonResponse({
                'success': False,
                'error': f'Cannot access repository: {message}'
            }, status=400)
        
        # Update repository information
        indexed_repo.github_url = new_github_url
        indexed_repo.github_owner = repo_info['owner']
        indexed_repo.github_repo_name = repo_info['repo']
        indexed_repo.status = 'pending'  # Will need re-indexing
        indexed_repo.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Repository URL updated to {repo_info["owner"]}/{repo_info["repo"]}',
            'repo_info': repo_info
        })
        
    except Exception as e:
        logger.error(f"Error updating repository URL: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def get_code_preview(request, repository_id):
    """Get a preview of code chunks for the sidebar"""
    try:
        indexed_repo = get_object_or_404(
            IndexedRepository,
            id=repository_id,
            project__owner=request.user
        )
        
        from .models import CodeChunk
        
        # Get recent code chunks with different types
        chunks_query = CodeChunk.objects.filter(
            file__repository=indexed_repo
        ).select_related('file').order_by('-created_at')
        
        # Get diverse chunk types
        function_chunks = chunks_query.filter(chunk_type='function')[:2]
        class_chunks = chunks_query.filter(chunk_type='class')[:1]
        other_chunks = chunks_query.exclude(chunk_type__in=['function', 'class'])[:2]
        
        # Combine and limit to 5 total
        code_chunks = list(function_chunks) + list(class_chunks) + list(other_chunks)
        code_chunks = code_chunks[:5]
        
        # Prepare chunk data
        chunks_data = []
        for chunk in code_chunks:
            chunks_data.append({
                'id': str(chunk.chunk_id),
                'chunk_type': chunk.chunk_type,
                'function_name': chunk.function_name,
                'file_path': chunk.file.file_path,
                'start_line': chunk.start_line,
                'end_line': chunk.end_line,
                'complexity': chunk.complexity,
                'content_preview': chunk.content_preview,
                'tags': chunk.tags[:3] if chunk.tags else [],
                'language': chunk.file.language
            })
        
        return JsonResponse({
            'success': True,
            'chunks': chunks_data,
            'total_chunks': chunks_query.count()
        })
        
    except Exception as e:
        logger.error(f"Error getting code preview: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def get_repository_stats(request, repository_id):
    """Get repository stats for dashboard display"""
    try:
        indexed_repo = get_object_or_404(
            IndexedRepository,
            id=repository_id,
            project__owner=request.user
        )

        from .models import CodeChunk

        # Count total chunks
        total_chunks = CodeChunk.objects.filter(
            file__repository=indexed_repo
        ).count()

        # Count functions
        total_functions = CodeChunk.objects.filter(
            file__repository=indexed_repo,
            chunk_type__in=['function', 'method']
        ).count()

        return JsonResponse({
            'success': True,
            'stats': {
                'indexed_files': indexed_repo.indexed_files_count,
                'total_chunks': total_chunks,
                'total_functions': total_functions,
                'total_entities': indexed_repo.total_entities,
            }
        })
    except Exception as e:
        logger.error(f"Error getting repository stats: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
def get_repository_insights(request, repository_id):
    """Get repository insights and statistics"""
    try:
        indexed_repo = get_object_or_404(
            IndexedRepository,
            id=repository_id,
            project__owner=request.user
        )

        from .models import RepositoryMetadata

        try:
            insights = indexed_repo.metadata
            insights_data = {
                'primary_language': insights.primary_language,
                'languages_distribution': insights.languages_distribution,
                'complexity_distribution': insights.complexity_distribution,
                'functions_count': insights.functions_count,
                'classes_count': insights.classes_count,
                'average_complexity': insights.average_complexity,
                'documentation_coverage': insights.documentation_coverage,
                'top_dependencies': insights.top_dependencies[:10] if insights.top_dependencies else []
            }
        except RepositoryMetadata.DoesNotExist:
            insights_data = None

        return JsonResponse({
            'success': True,
            'insights': insights_data
        })

    except Exception as e:
        logger.error(f"Error getting repository insights: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def get_codebase_summary(request, repository_id):
    """Get the stored AI-generated codebase summary"""
    try:
        indexed_repo = get_object_or_404(
            IndexedRepository,
            id=repository_id,
            project__owner=request.user
        )

        if not indexed_repo.codebase_summary:
            return JsonResponse({
                'success': False,
                'error': 'Summary not yet generated. Please wait for indexing to complete.'
            })

        return JsonResponse({
            'success': True,
            'summary': indexed_repo.codebase_summary,
            'generated_at': indexed_repo.summary_generated_at.isoformat() if indexed_repo.summary_generated_at else None,
            'repository_name': indexed_repo.github_repo_name
        })

    except Exception as e:
        logger.error(f"Error getting codebase summary: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
