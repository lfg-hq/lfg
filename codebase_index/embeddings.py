import time
import logging
from typing import List, Dict, Any, Optional
import openai
from django.conf import settings
import os


logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Generate embeddings for code chunks using OpenAI"""
    
    def __init__(self):
        self.client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.model = "text-embedding-3-small"
        self.max_tokens = 8191  # Token limit for text-embedding-3-small
        self.batch_size = 100   # Number of texts to embed in one request
    
    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts"""
        try:
            # Filter out empty texts
            non_empty_texts = [text for text in texts if text.strip()]
            if not non_empty_texts:
                return []
            
            # Truncate texts that are too long
            truncated_texts = [self._truncate_text(text) for text in non_empty_texts]
            
            # Generate embeddings
            response = self.client.embeddings.create(
                model=self.model,
                input=truncated_texts
            )
            
            # Extract embeddings
            embeddings = [item.embedding for item in response.data]
            
            logger.debug(f"Generated {len(embeddings)} embeddings")
            return embeddings
            
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            return []
    
    def generate_single_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for a single text"""
        embeddings = self.generate_embeddings_batch([text])
        return embeddings[0] if embeddings else None
    
    def _truncate_text(self, text: str) -> str:
        """Truncate text to fit within token limits"""
        # Simple approximation: 1 token ≈ 4 characters for code
        max_chars = self.max_tokens * 3  # Conservative estimate
        
        if len(text) <= max_chars:
            return text
        
        # Truncate and add notice
        truncated = text[:max_chars-50]
        return truncated + "\n\n# [Content truncated due to length]"
    
    def prepare_code_for_embedding(self, chunk: Dict[str, Any]) -> str:
        """Prepare code chunk for embedding generation"""
        content = chunk['content']
        chunk_type = chunk.get('chunk_type', 'unknown')
        function_name = chunk.get('function_name')
        file_path = chunk.get('file_path', '')
        
        # Create enhanced content with context
        context_parts = [
            f"File: {file_path}",
            f"Type: {chunk_type}",
        ]
        
        if function_name:
            context_parts.append(f"Name: {function_name}")
        
        if chunk.get('dependencies'):
            deps = ', '.join(chunk['dependencies'][:5])  # Limit dependencies
            context_parts.append(f"Dependencies: {deps}")
        
        # Combine context with content
        context_header = '\n'.join(context_parts)
        enhanced_content = f"{context_header}\n\n{content}"
        
        return enhanced_content


class CodebaseRetriever:
    """Retrieve relevant code chunks for queries"""
    
    def __init__(self):
        self.embedding_generator = EmbeddingGenerator()
    
    def retrieve_relevant_code(self, 
                             project, 
                             query: str, 
                             max_chunks: int = 20,
                             chunk_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """Retrieve relevant code chunks for a given query"""
        
        start_time = time.time()
        
        try:
            # Get indexed repository for project
            from .models import IndexedRepository
            
            try:
                indexed_repo = project.indexed_repository
            except IndexedRepository.DoesNotExist:
                return {
                    'chunks': [],
                    'metadata': [],
                    'retrieval_time_ms': 0,
                    'error': 'No indexed repository found for project'
                }
            
            if indexed_repo.status != 'completed':
                return {
                    'chunks': [],
                    'metadata': [],
                    'retrieval_time_ms': 0,
                    'error': f'Repository indexing not completed (status: {indexed_repo.status})'
                }
            
            # STEP 1: Try fast index map search first
            from .models import CodebaseIndexMap

            index_results = CodebaseIndexMap.search_index(
                repository=indexed_repo,
                query=query,
                entity_types=chunk_types,
                limit=max_chunks
            )

            retrieved_chunks = []
            chunk_metadatas = []

            # If we found good matches in index map, use those
            if index_results.exists():
                logger.info(f"Found {index_results.count()} matches in index map for query: {query}")

                for i, index_entry in enumerate(index_results):
                    # Get the actual code chunk if available
                    chunk_content = index_entry.code_chunk.content if index_entry.code_chunk else ""

                    retrieved_chunks.append({
                        'content': chunk_content or f"# {index_entry.entity_name} not available",
                        'relevance_score': 0.9 - (i * 0.02),  # Decreasing relevance score
                        'metadata': {
                            'file_path': index_entry.file_path,
                            'file_name': index_entry.file_path.split('/')[-1],
                            'language': index_entry.language,
                            'chunk_type': index_entry.entity_type,
                            'function_name': index_entry.entity_name,
                            'fully_qualified_name': index_entry.fully_qualified_name,
                            'start_line': index_entry.start_line,
                            'end_line': index_entry.end_line,
                            'complexity': index_entry.complexity,
                            'source': 'index_map'  # Mark as from index
                        },
                        'rank': i + 1
                    })
                    chunk_metadatas.append(retrieved_chunks[-1]['metadata'])

            # STEP 2: If index map didn't find enough, use vector search
            if len(retrieved_chunks) < max_chunks:
                logger.info(f"Index map found {len(retrieved_chunks)} results, using vector search for more")

                # Expand query for better retrieval
                expanded_queries = self._expand_query(query)

                # Perform semantic search
                from .chroma_client import get_chroma_client
                chroma_client = get_chroma_client()

                # Build where clause for filtering
                where_clause = {}
                if chunk_types:
                    where_clause['chunk_type'] = {'$in': chunk_types}

                # Query ChromaDB for remaining chunks
                remaining_needed = max_chunks - len(retrieved_chunks)
                results = chroma_client.query_similar_code(
                    collection_name=indexed_repo.get_chroma_collection_name(),
                    query_texts=expanded_queries,
                    n_results=remaining_needed,
                    where=where_clause if where_clause else None
                )

                # Process vector search results and append to existing results
                if results['documents'] and results['documents'][0]:
                    for i, (doc, metadata, distance) in enumerate(zip(
                        results['documents'][0],
                        results['metadatas'][0],
                        results['distances'][0]
                    )):
                        # Mark vector search results
                        metadata['source'] = 'vector_search'
                        retrieved_chunks.append({
                            'content': doc,
                            'relevance_score': 1 - distance,  # Convert distance to similarity
                            'metadata': metadata,
                            'rank': len(retrieved_chunks) + 1
                        })
                        chunk_metadatas.append(metadata)
            
            retrieval_time_ms = int((time.time() - start_time) * 1000)
            
            return {
                'chunks': retrieved_chunks,
                'metadata': chunk_metadatas,
                'retrieval_time_ms': retrieval_time_ms,
                'total_considered': len(retrieved_chunks),
                'query_expansion': expanded_queries,
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Error retrieving code chunks: {e}")
            retrieval_time_ms = int((time.time() - start_time) * 1000)
            
            return {
                'chunks': [],
                'metadata': [],
                'retrieval_time_ms': retrieval_time_ms,
                'error': str(e)
            }
    
    def _expand_query(self, query: str) -> List[str]:
        """Expand query with synonyms and variations for better retrieval"""
        queries = [query]
        
        # Add technical variations
        technical_expansions = {
            'authentication': ['auth', 'login', 'user management', 'session'],
            'database': ['db', 'model', 'orm', 'data storage'],
            'api': ['endpoint', 'route', 'rest', 'http'],
            'frontend': ['ui', 'interface', 'component', 'view'],
            'backend': ['server', 'service', 'logic', 'controller'],
            'payment': ['billing', 'stripe', 'transaction', 'subscription'],
            'file': ['upload', 'storage', 'document', 'attachment'],
            'chat': ['message', 'conversation', 'websocket', 'real-time'],
        }
        
        query_lower = query.lower()
        for key, expansions in technical_expansions.items():
            if key in query_lower:
                queries.extend([exp for exp in expansions if exp not in query_lower])
        
        # Add code-specific variations
        if any(term in query_lower for term in ['create', 'add', 'implement']):
            queries.append(f"how to {query}")
            queries.append(f"implementation of {query}")
        
        # Limit to avoid too many queries
        return queries[:5]
    
    def assemble_context(self, 
                        retrieved_chunks: List[Dict[str, Any]], 
                        max_context_length: int = 8000) -> str:
        """Assemble retrieved chunks into coherent context"""
        
        if not retrieved_chunks:
            return "No relevant code found in the codebase."
        
        # Sort chunks by relevance score
        sorted_chunks = sorted(retrieved_chunks, key=lambda x: x['relevance_score'], reverse=True)
        
        context_parts = []
        current_length = 0
        
        # Group chunks by file for better organization
        chunks_by_file = {}
        for chunk in sorted_chunks:
            file_path = chunk['metadata']['file_path']
            if file_path not in chunks_by_file:
                chunks_by_file[file_path] = []
            chunks_by_file[file_path].append(chunk)
        
        # Add chunks to context, organized by file
        for file_path, file_chunks in chunks_by_file.items():
            file_section = f"\n## File: {file_path}\n"
            
            for chunk in file_chunks:
                chunk_info = (
                    f"\n### {chunk['metadata']['chunk_type'].title()}: "
                    f"{chunk['metadata'].get('function_name', 'Anonymous')}\n"
                    f"Lines {chunk['metadata']['start_line']}-{chunk['metadata']['end_line']}\n"
                    f"Relevance: {chunk['relevance_score']:.2f}\n\n"
                    f"```{chunk['metadata']['language']}\n{chunk['content']}\n```\n"
                )
                
                if current_length + len(chunk_info) > max_context_length:
                    context_parts.append("\n... [Additional code truncated due to length limits]")
                    break
                
                if not context_parts or context_parts[-1] != file_section:
                    context_parts.append(file_section)
                    current_length += len(file_section)
                
                context_parts.append(chunk_info)
                current_length += len(chunk_info)
        
        return ''.join(context_parts)


def generate_repository_insights(indexed_repository) -> Dict[str, Any]:
    """Generate high-level insights about a repository"""
    from .models import RepositoryMetadata, CodeChunk
    
    try:
        # Get all chunks for analysis
        all_chunks = CodeChunk.objects.filter(
            file__repository=indexed_repository
        ).select_related('file')
        
        if not all_chunks.exists():
            return {'error': 'No indexed code chunks found'}
        
        # Analyze languages
        languages = {}
        for chunk in all_chunks:
            lang = chunk.file.language or 'unknown'
            languages[lang] = languages.get(lang, 0) + 1
        
        primary_language = max(languages.keys(), key=lambda k: languages[k])
        
        # Analyze functions and classes
        functions = all_chunks.filter(chunk_type='function')
        classes = all_chunks.filter(chunk_type='class')
        
        # Calculate complexity distribution
        complexity_dist = {}
        for chunk in all_chunks:
            comp = chunk.complexity
            complexity_dist[comp] = complexity_dist.get(comp, 0) + 1
        
        # Analyze dependencies
        all_dependencies = []
        for chunk in all_chunks:
            all_dependencies.extend(chunk.dependencies)
        
        dependency_counts = {}
        for dep in all_dependencies:
            dependency_counts[dep] = dependency_counts.get(dep, 0) + 1
        
        top_dependencies = sorted(dependency_counts.items(), key=lambda x: x[1], reverse=True)[:20]
        
        # Store or update metadata
        metadata, created = RepositoryMetadata.objects.update_or_create(
            repository=indexed_repository,
            defaults={
                'primary_language': primary_language,
                'languages_detected': list(languages.keys()),
                'total_lines_of_code': sum(chunk.file.total_lines for chunk in all_chunks.distinct('file')),
                'functions_count': functions.count(),
                'classes_count': classes.count(),
                'external_dependencies': [dep for dep, count in top_dependencies],
                'documentation_coverage': _calculate_documentation_coverage(all_chunks),
                'average_function_complexity': _calculate_average_complexity(functions),
            }
        )
        
        insights = {
            'primary_language': primary_language,
            'languages_distribution': languages,
            'complexity_distribution': complexity_dist,
            'functions_count': functions.count(),
            'classes_count': classes.count(),
            'top_dependencies': top_dependencies[:10],
            'documentation_coverage': metadata.documentation_coverage,
            'average_complexity': metadata.average_function_complexity,
        }
        
        return insights
        
    except Exception as e:
        logger.error(f"Error generating repository insights: {e}")
        return {'error': str(e)}


def _calculate_documentation_coverage(chunks) -> float:
    """Calculate percentage of functions/classes with documentation"""
    documented_chunks = chunks.filter(
        chunk_type__in=['function', 'class'],
        description__isnull=False
    ).exclude(description='')
    
    total_chunks = chunks.filter(chunk_type__in=['function', 'class']).count()
    
    if total_chunks == 0:
        return 0.0
    
    return (documented_chunks.count() / total_chunks) * 100


def _calculate_average_complexity(chunks) -> float:
    """Calculate average complexity score"""
    if not chunks.exists():
        return 0.0

    complexity_scores = {'low': 1, 'medium': 2, 'high': 3}
    total_score = sum(complexity_scores.get(chunk.complexity, 2) for chunk in chunks)

    return total_score / chunks.count()


def generate_and_store_codebase_summary(indexed_repository) -> Dict[str, Any]:
    """
    Generate a comprehensive AI-powered summary of the codebase and store it in the database.

    This function is called automatically after indexing completes.
    It analyzes the entire AST structure and generates a detailed summary including:
    - Overall purpose and architecture
    - File organization
    - All functions/methods by file
    - Data models
    - API endpoints
    - Dependencies and code flow

    Args:
        indexed_repository: IndexedRepository instance

    Returns:
        dict with success status and summary or error
    """
    try:
        from .models import CodebaseIndexMap, RepositoryMetadata
        from collections import defaultdict
        import anthropic
        from django.utils import timezone
        import json

        logger.info(f"Generating codebase summary for {indexed_repository.github_repo_name}")

        # Fetch all codebase index entries
        index_entries = list(
            CodebaseIndexMap.objects.filter(
                repository=indexed_repository
            ).select_related('code_chunk__file').order_by('file_path', 'start_line')
        )

        if not index_entries:
            logger.warning("No codebase index entries found")
            return {'success': False, 'error': 'No codebase entries to analyze'}

        # Organize data by file and type
        files_structure = defaultdict(lambda: {
            'functions': [],
            'methods': [],
            'classes': [],
            'interfaces': [],
            'language': None
        })

        api_endpoints = []
        models = []

        for entry in index_entries:
            file_path = entry.file_path
            files_structure[file_path]['language'] = entry.language

            entity_data = {
                'name': entry.entity_name,
                'type': entry.entity_type,
                'lines': f"L{entry.start_line}-{entry.end_line}",
                'complexity': entry.complexity,
                'description': entry.description
            }

            # Categorize by entity type
            if entry.entity_type == 'function':
                files_structure[file_path]['functions'].append(entity_data)
            elif entry.entity_type == 'method':
                files_structure[file_path]['methods'].append(entity_data)
            elif entry.entity_type == 'class':
                files_structure[file_path]['classes'].append(entity_data)
                # Check if it's a model
                if any(keyword in entry.entity_name.lower() for keyword in ['model', 'schema', 'entity']):
                    models.append({
                        'file': file_path,
                        'name': entry.entity_name,
                        'description': entry.description
                    })
            elif entry.entity_type == 'interface':
                files_structure[file_path]['interfaces'].append(entity_data)

            # Detect API endpoints
            if entry.entity_name and any(keyword in entry.entity_name.lower() for keyword in
                ['handler', 'endpoint', 'route', 'controller', 'api']):
                api_endpoints.append({
                    'file': file_path,
                    'name': entry.entity_name,
                    'type': entry.entity_type,
                    'description': entry.description
                })

        # Get repository metadata
        try:
            metadata = indexed_repository.metadata
            language_dist = metadata.languages_distribution
            primary_language = metadata.primary_language
            total_functions = metadata.functions_count
            total_classes = metadata.classes_count
            dependencies = metadata.top_dependencies[:10] if metadata.top_dependencies else []
        except:
            language_dist = {}
            primary_language = 'Unknown'
            total_functions = sum(len(f['functions']) + len(f['methods']) for f in files_structure.values())
            total_classes = sum(len(f['classes']) for f in files_structure.values())
            dependencies = []

        # Build analysis data
        analysis_data = {
            'repository_name': indexed_repository.github_repo_name,
            'primary_language': primary_language,
            'total_files': len(files_structure),
            'total_functions': total_functions,
            'total_classes': total_classes,
            'language_distribution': language_dist,
            'dependencies': dependencies,
            'files': {}
        }

        # Add file-level details (limit to prevent token overflow)
        for file_path, data in sorted(files_structure.items())[:50]:
            analysis_data['files'][file_path] = {
                'language': data['language'],
                'functions': [{'name': f['name'], 'complexity': f['complexity'], 'description': f.get('description')}
                             for f in data['functions'][:10]],
                'classes': [{'name': c['name'], 'description': c.get('description')}
                           for c in data['classes']],
                'methods': [{'name': m['name'], 'complexity': m['complexity']}
                           for m in data['methods'][:10]],
            }

        analysis_data['detected_models'] = models[:20]
        analysis_data['detected_api_endpoints'] = api_endpoints[:30]

        # Prepare prompt for AI
        prompt = f"""You are analyzing a codebase to generate a comprehensive summary. Here is the structured data from AST parsing:

Repository: {analysis_data['repository_name']}
Primary Language: {analysis_data['primary_language']}
Total Files Indexed: {analysis_data['total_files']}
Total Functions/Methods: {analysis_data['total_functions']}
Total Classes/Structs: {analysis_data['total_classes']}

Language Distribution:
{json.dumps(analysis_data['language_distribution'], indent=2)}

Top Dependencies:
{json.dumps(analysis_data['dependencies'], indent=2)}

File Structure (top files):
{json.dumps(analysis_data['files'], indent=2, default=str)}

Detected Models/Entities:
{json.dumps(analysis_data['detected_models'], indent=2, default=str)}

Detected API Endpoints/Handlers:
{json.dumps(analysis_data['detected_api_endpoints'], indent=2, default=str)}

Generate a comprehensive codebase summary in markdown format that includes:

1. **Overview**: What is the overall purpose of this codebase? What type of application is it?
2. **Architecture**: Describe the high-level architecture and design patterns used
3. **File Organization**: How are files organized? What are the main directories/modules?
4. **Key Components**:
   - Main functions and their purposes
   - Important classes/models and what they represent
   - API endpoints and their functions (if applicable)
5. **Technology Stack**: Languages, frameworks, and key dependencies
6. **Code Characteristics**: Complexity distribution, code quality observations
7. **Entry Points**: Main entry points and how the code flows

Be specific and use actual file names, function names, and class names from the data provided."""

        # Use Anthropic client to generate summary
        client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        response = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=4000,
            messages=[{'role': 'user', 'content': prompt}]
        )

        # Extract text content from response
        summary = response.content[0].text if response.content else 'Unable to generate summary'

        # Store summary in database
        indexed_repository.codebase_summary = summary
        indexed_repository.summary_generated_at = timezone.now()
        indexed_repository.save()

        logger.info(f"Successfully generated and stored codebase summary for {indexed_repository.github_repo_name}")

        return {
            'success': True,
            'summary': summary
        }

    except Exception as e:
        logger.error(f"Error generating codebase summary: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            'success': False,
            'error': str(e)
        }