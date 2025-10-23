from django.db import models
from django.db.models import Sum
from django.contrib.auth.models import User
from projects.models import Project
import uuid
import json


class IndexedRepository(models.Model):
    """Model to track GitHub repositories and their indexing status"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('indexing', 'Indexing'),
        ('completed', 'Completed'),
        ('error', 'Error'),
        ('paused', 'Paused'),
    ]
    
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="indexed_repository")
    
    # GitHub repository information
    github_url = models.URLField(help_text="GitHub repository URL")
    github_owner = models.CharField(max_length=255, help_text="Repository owner/organization")
    github_repo_name = models.CharField(max_length=255, help_text="Repository name")
    github_branch = models.CharField(max_length=255, default='main', help_text="Branch to index")
    
    # Indexing status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    last_indexed_at = models.DateTimeField(null=True, blank=True)
    last_commit_hash = models.CharField(max_length=40, blank=True, null=True, help_text="Last indexed commit hash")
    
    # Statistics
    total_files = models.IntegerField(default=0, help_text="Total number of files in repository")
    indexed_files_count = models.IntegerField(default=0, help_text="Number of files successfully indexed")
    total_chunks = models.IntegerField(default=0, help_text="Total number of code chunks created")

    # AI-generated summary
    codebase_summary = models.TextField(blank=True, null=True, help_text="AI-generated comprehensive summary of the codebase")
    summary_generated_at = models.DateTimeField(null=True, blank=True, help_text="When the summary was generated")

    # Configuration
    file_extensions = models.JSONField(
        default=list,
        help_text="File extensions to index"
    )
    max_file_size_kb = models.IntegerField(default=500, help_text="Maximum file size to index (KB)")
    exclude_patterns = models.JSONField(
        default=list,
        help_text="Patterns to exclude from indexing"
    )
    
    # Error tracking
    error_message = models.TextField(blank=True, null=True)
    error_count = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Indexed Repository"
        verbose_name_plural = "Indexed Repositories"
        indexes = [
            models.Index(fields=['status', '-updated_at']),
            models.Index(fields=['project', 'status']),
        ]
    
    def __str__(self):
        return f"{self.github_owner}/{self.github_repo_name} ({self.status})"
    
    @property
    def indexing_progress(self):
        """Calculate indexing progress as percentage"""
        if self.total_files == 0:
            return 0
        return (self.indexed_files_count / self.total_files) * 100

    @property
    def total_entities(self):
        total = self.files.aggregate(total=Sum('code_chunks_count'))['total']
        if total is None:
            total = self.total_chunks
        return total or 0
    
    def get_chroma_collection_name(self):
        """Generate ChromaDB collection name for this repository"""
        return f"project_{self.project.project_id}_code"
    
    def save(self, *args, **kwargs):
        """Override save to set default values for JSONFields"""
        if not self.file_extensions:
            self.file_extensions = ['.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h', '.go', '.rs', '.php']
        
        if not self.exclude_patterns:
            self.exclude_patterns = ['node_modules/', '.git/', '__pycache__/', 'venv/', '.env', '*.min.js', '*.bundle.js']
        
        super().save(*args, **kwargs)


class IndexedFile(models.Model):
    """Model to track individual files and their indexing status"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('indexed', 'Indexed'),
        ('error', 'Error'),
        ('skipped', 'Skipped'),
    ]
    
    repository = models.ForeignKey(IndexedRepository, on_delete=models.CASCADE, related_name='files')
    
    # File information
    file_path = models.CharField(max_length=1000, help_text="Relative path from repository root")
    file_name = models.CharField(max_length=255, help_text="File name with extension")
    file_extension = models.CharField(max_length=10, help_text="File extension")
    file_size_bytes = models.IntegerField(help_text="File size in bytes")
    
    # Git information
    last_commit_hash = models.CharField(max_length=40, help_text="Last commit that modified this file")
    last_modified_at = models.DateTimeField(help_text="Last modification timestamp from git")
    
    # Indexing status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    content_hash = models.CharField(max_length=64, help_text="SHA256 hash of file content for change detection")
    
    # Parsing results
    language = models.CharField(max_length=50, blank=True, null=True, help_text="Detected programming language")
    total_lines = models.IntegerField(default=0)
    code_chunks_count = models.IntegerField(default=0, help_text="Number of code chunks created from this file")
    
    # Error tracking
    error_message = models.TextField(blank=True, null=True)
    
    # Timestamps
    indexed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['repository', 'file_path']
        verbose_name = "Indexed File"
        verbose_name_plural = "Indexed Files"
        indexes = [
            models.Index(fields=['repository', 'status']),
            models.Index(fields=['repository', 'file_extension']),
            models.Index(fields=['content_hash']),
        ]
    
    def __str__(self):
        return f"{self.repository.github_repo_name}/{self.file_path}"
    
    @property
    def relative_path(self):
        """Get the relative path for display"""
        return self.file_path


class CodeChunk(models.Model):
    """Model to store parsed code chunks with their metadata"""
    
    CHUNK_TYPES = [
        ('file', 'Full File'),
        ('function', 'Function'),
        ('class', 'Class'),
        ('method', 'Method'),
        ('import', 'Import Block'),
        ('docstring', 'Docstring'),
        ('comment', 'Comment Block'),
    ]
    
    COMPLEXITY_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]
    
    file = models.ForeignKey(IndexedFile, on_delete=models.CASCADE, related_name='chunks')
    
    # Chunk identification
    chunk_id = models.UUIDField(default=uuid.uuid4, unique=True, help_text="Unique identifier for ChromaDB")
    chunk_type = models.CharField(max_length=20, choices=CHUNK_TYPES)
    
    # Content information
    content = models.TextField(help_text="The actual code content")
    content_preview = models.CharField(max_length=200, help_text="Preview of content for display")
    start_line = models.IntegerField(help_text="Starting line number in file")
    end_line = models.IntegerField(help_text="Ending line number in file")
    
    # Code analysis
    function_name = models.CharField(max_length=255, blank=True, null=True, help_text="Function/class/method name")
    complexity = models.CharField(max_length=10, choices=COMPLEXITY_LEVELS, default='medium')
    dependencies = models.JSONField(default=list, help_text="List of dependencies/imports referenced")
    parameters = models.JSONField(default=list, help_text="Function parameters or class attributes")
    
    # Vector embedding information
    embedding_id = models.CharField(max_length=100, help_text="ChromaDB document ID")
    embedding_stored = models.BooleanField(default=False, help_text="Whether embedding is stored in ChromaDB")
    
    # Metadata for retrieval
    tags = models.JSONField(default=list, help_text="Tags for categorization and search")
    description = models.TextField(blank=True, null=True, help_text="Generated description of code functionality")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Code Chunk"
        verbose_name_plural = "Code Chunks"
        indexes = [
            models.Index(fields=['file', 'chunk_type']),
            models.Index(fields=['chunk_type', 'complexity']),
            models.Index(fields=['function_name']),
            models.Index(fields=['embedding_stored']),
        ]
    
    def __str__(self):
        if self.function_name:
            return f"{self.function_name} ({self.chunk_type}) - {self.file.file_path}"
        return f"{self.chunk_type} chunk - {self.file.file_path}:{self.start_line}-{self.end_line}"
    
    def get_metadata_dict(self):
        """Get metadata dictionary for ChromaDB storage"""
        return {
            'file_path': self.file.file_path,
            'file_name': self.file.file_name,
            'file_extension': self.file.file_extension,
            'language': self.file.language or '',
            'chunk_type': self.chunk_type,
            'function_name': self.function_name or '',
            'complexity': self.complexity,
            'start_line': self.start_line,
            'end_line': self.end_line,
            'dependencies': json.dumps(self.dependencies),
            'parameters': json.dumps(self.parameters),
            'tags': json.dumps(self.tags),
            'repository_name': f"{self.file.repository.github_owner}/{self.file.repository.github_repo_name}",
            'project_id': str(self.file.repository.project.project_id),
        }


class IndexingJob(models.Model):
    """Model to track background indexing jobs"""
    
    JOB_TYPES = [
        ('full_index', 'Full Repository Index'),
        ('incremental_update', 'Incremental Update'),
        ('file_reindex', 'Single File Reindex'),
        ('cleanup', 'Cleanup Job'),
    ]
    
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    repository = models.ForeignKey(IndexedRepository, on_delete=models.CASCADE, related_name='indexing_jobs')
    
    # Job information
    job_type = models.CharField(max_length=20, choices=JOB_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    
    # Progress tracking
    total_files = models.IntegerField(default=0)
    processed_files = models.IntegerField(default=0)
    successful_files = models.IntegerField(default=0)
    failed_files = models.IntegerField(default=0)
    
    # Job execution details
    started_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    django_q_task_id = models.CharField(max_length=100, blank=True, null=True, help_text="Django-Q task ID")
    
    # Results
    result_summary = models.JSONField(default=dict, help_text="Summary of job results")
    error_logs = models.TextField(blank=True, null=True)
    
    # Timestamps
    queued_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Indexing Job"
        verbose_name_plural = "Indexing Jobs"
        ordering = ['-queued_at']
        indexes = [
            models.Index(fields=['repository', 'status']),
            models.Index(fields=['status', '-queued_at']),
            models.Index(fields=['django_q_task_id']),
        ]
    
    def __str__(self):
        return f"{self.get_job_type_display()} - {self.repository.github_repo_name} ({self.status})"
    
    @property
    def progress_percentage(self):
        """Calculate job progress as percentage"""
        if self.total_files == 0:
            return 0
        return (self.processed_files / self.total_files) * 100
    
    def update_progress(self, processed=None, successful=None, failed=None):
        """Update job progress counters"""
        if processed is not None:
            self.processed_files = processed
        if successful is not None:
            self.successful_files = successful
        if failed is not None:
            self.failed_files = failed
        self.save(update_fields=['processed_files', 'successful_files', 'failed_files', 'updated_at'])


class CodebaseQuery(models.Model):
    """Model to store and cache codebase queries for analytics"""
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='codebase_queries')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='codebase_queries')
    
    # Query information
    query_text = models.TextField(help_text="Original user query")
    expanded_queries = models.JSONField(default=list, help_text="Expanded queries for better retrieval")
    
    # Results
    retrieved_chunks = models.JSONField(default=list, help_text="List of chunk IDs retrieved")
    relevance_scores = models.JSONField(default=list, help_text="Relevance scores for retrieved chunks")
    context_used = models.TextField(help_text="Final context assembled from chunks")
    
    # Performance metrics
    retrieval_time_ms = models.IntegerField(help_text="Time taken for retrieval in milliseconds")
    total_chunks_considered = models.IntegerField(default=0)
    
    # Generated output context
    enhanced_prd_generated = models.BooleanField(default=False)
    feature_suggestions = models.JSONField(default=list, help_text="AI-suggested features based on codebase")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Codebase Query"
        verbose_name_plural = "Codebase Queries"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', '-created_at']),
            models.Index(fields=['user', '-created_at']),
        ]
    
    def __str__(self):
        return f"Query: {self.query_text[:50]}... - {self.project.name}"


class CodebaseIndexMap(models.Model):
    """Fast lookup index map for files and functions - avoids expensive vector searches"""

    repository = models.ForeignKey(IndexedRepository, on_delete=models.CASCADE, related_name='index_maps')

    # File/Function identification
    file_path = models.CharField(max_length=1000, db_index=True, help_text="Relative file path")
    entity_type = models.CharField(max_length=20, db_index=True, help_text="Type: file, function, class, method")
    entity_name = models.CharField(max_length=500, db_index=True, help_text="Name of function/class/method or file name")
    fully_qualified_name = models.CharField(max_length=1000, db_index=True, help_text="Full path like 'module.Class.method'")

    # Location information
    language = models.CharField(max_length=50, db_index=True, help_text="Programming language")
    start_line = models.IntegerField(help_text="Start line in file")
    end_line = models.IntegerField(help_text="End line in file")

    # Metadata for quick filtering
    parameters = models.JSONField(default=list, help_text="Function parameters")
    return_type = models.CharField(max_length=200, blank=True, null=True, help_text="Return type if available")
    dependencies = models.JSONField(default=list, help_text="Imports and dependencies")
    decorators = models.JSONField(default=list, help_text="Decorators or annotations")

    # Search optimization
    description = models.TextField(blank=True, help_text="Brief description or docstring")
    keywords = models.JSONField(default=list, help_text="Extracted keywords for search")
    complexity = models.CharField(max_length=20, default='medium', help_text="Complexity level")

    # Reference to actual chunk
    code_chunk = models.ForeignKey('CodeChunk', on_delete=models.CASCADE, null=True, blank=True, related_name='index_entries')

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Codebase Index Map"
        verbose_name_plural = "Codebase Index Maps"
        indexes = [
            models.Index(fields=['repository', 'entity_type']),
            models.Index(fields=['repository', 'entity_name']),
            models.Index(fields=['repository', 'language']),
            models.Index(fields=['fully_qualified_name']),
            models.Index(fields=['file_path', 'entity_type']),
        ]
        unique_together = ['repository', 'file_path', 'entity_name', 'start_line']

    def __str__(self):
        return f"{self.entity_type}: {self.fully_qualified_name}"

    @staticmethod
    def search_index(repository, query, entity_types=None, languages=None, limit=20):
        """
        Fast text search on index map before doing vector search

        Args:
            repository: IndexedRepository instance
            query: Search query string
            entity_types: Optional list of entity types to filter (function, class, etc.)
            languages: Optional list of languages to filter
            limit: Maximum results to return

        Returns:
            QuerySet of matching CodebaseIndexMap entries
        """
        from django.db.models import Q

        # Build search query
        search_terms = query.lower().split()
        q_objects = Q()

        for term in search_terms:
            q_objects |= (
                Q(entity_name__icontains=term) |
                Q(description__icontains=term) |
                Q(keywords__contains=[term]) |
                Q(file_path__icontains=term)
            )

        # Base queryset
        results = CodebaseIndexMap.objects.filter(repository=repository).filter(q_objects)

        # Apply filters
        if entity_types:
            results = results.filter(entity_type__in=entity_types)
        if languages:
            results = results.filter(language__in=languages)

        # Order by relevance (prioritize exact matches)
        return results[:limit]


class RepositoryMetadata(models.Model):
    """Model to store repository-level metadata and insights"""

    repository = models.OneToOneField(IndexedRepository, on_delete=models.CASCADE, related_name='metadata')
    
    # Architecture insights
    primary_language = models.CharField(max_length=50, blank=True, null=True)
    languages_detected = models.JSONField(default=list, help_text="List of programming languages found")
    framework_patterns = models.JSONField(default=list, help_text="Detected frameworks and patterns")
    
    # Code statistics
    total_lines_of_code = models.IntegerField(default=0)
    functions_count = models.IntegerField(default=0)
    classes_count = models.IntegerField(default=0)
    
    # Dependency analysis
    external_dependencies = models.JSONField(default=list, help_text="External packages/libraries used")
    internal_dependencies = models.JSONField(default=dict, help_text="Internal module dependency graph")
    
    # Quality metrics
    documentation_coverage = models.FloatField(default=0.0, help_text="Percentage of functions/classes with docstrings")
    average_function_complexity = models.FloatField(default=0.0, help_text="Average cyclomatic complexity")
    
    # Common patterns
    design_patterns = models.JSONField(default=list, help_text="Detected design patterns")
    coding_conventions = models.JSONField(default=dict, help_text="Detected coding conventions and style")
    
    # Timestamps
    analyzed_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Repository Metadata"
        verbose_name_plural = "Repository Metadata"
    
    def __str__(self):
        return f"Metadata for {self.repository.github_repo_name}"
