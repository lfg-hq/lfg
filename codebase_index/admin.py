from django.contrib import admin
from .models import IndexedRepository, IndexedFile, CodeChunk, IndexingJob, CodebaseQuery, RepositoryMetadata


@admin.register(IndexedRepository)
class IndexedRepositoryAdmin(admin.ModelAdmin):
    list_display = ['github_repo_name', 'github_owner', 'project', 'status', 'indexing_progress', 'last_indexed_at']
    list_filter = ['status', 'created_at', 'last_indexed_at']
    search_fields = ['github_repo_name', 'github_owner', 'project__name']
    readonly_fields = ['indexing_progress', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Repository Information', {
            'fields': ('project', 'github_url', 'github_owner', 'github_repo_name', 'github_branch')
        }),
        ('Indexing Status', {
            'fields': ('status', 'last_indexed_at', 'last_commit_hash', 'indexing_progress')
        }),
        ('Statistics', {
            'fields': ('total_files', 'indexed_files_count', 'total_chunks')
        }),
        ('Configuration', {
            'fields': ('file_extensions', 'max_file_size_kb', 'exclude_patterns')
        }),
        ('Error Information', {
            'fields': ('error_message', 'error_count')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        })
    )


@admin.register(IndexedFile)
class IndexedFileAdmin(admin.ModelAdmin):
    list_display = ['file_name', 'file_path', 'repository', 'status', 'language', 'code_chunks_count', 'indexed_at']
    list_filter = ['status', 'language', 'file_extension', 'indexed_at']
    search_fields = ['file_name', 'file_path', 'repository__github_repo_name']
    readonly_fields = ['content_hash', 'indexed_at', 'created_at', 'updated_at']


@admin.register(CodeChunk)
class CodeChunkAdmin(admin.ModelAdmin):
    list_display = ['function_name', 'chunk_type', 'file', 'complexity', 'embedding_stored', 'start_line', 'end_line']
    list_filter = ['chunk_type', 'complexity', 'embedding_stored', 'file__language']
    search_fields = ['function_name', 'content_preview', 'file__file_path']
    readonly_fields = ['chunk_id', 'embedding_id', 'created_at', 'updated_at']


@admin.register(IndexingJob)
class IndexingJobAdmin(admin.ModelAdmin):
    list_display = ['repository', 'job_type', 'status', 'progress_percentage', 'queued_at', 'started_at', 'completed_at']
    list_filter = ['job_type', 'status', 'queued_at']
    search_fields = ['repository__github_repo_name', 'django_q_task_id']
    readonly_fields = ['progress_percentage', 'queued_at', 'started_at', 'completed_at']


@admin.register(CodebaseQuery)
class CodebaseQueryAdmin(admin.ModelAdmin):
    list_display = ['project', 'user', 'query_text_preview', 'enhanced_prd_generated', 'retrieval_time_ms', 'created_at']
    list_filter = ['enhanced_prd_generated', 'created_at', 'project']
    search_fields = ['query_text', 'project__name', 'user__username']
    readonly_fields = ['created_at']
    
    def query_text_preview(self, obj):
        return obj.query_text[:100] + '...' if len(obj.query_text) > 100 else obj.query_text
    query_text_preview.short_description = 'Query Preview'


@admin.register(RepositoryMetadata)
class RepositoryMetadataAdmin(admin.ModelAdmin):
    list_display = ['repository', 'primary_language', 'total_lines_of_code', 'functions_count', 'classes_count', 'analyzed_at']
    list_filter = ['primary_language', 'analyzed_at']
    search_fields = ['repository__github_repo_name']
    readonly_fields = ['analyzed_at', 'created_at']
