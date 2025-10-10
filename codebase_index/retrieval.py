"""
Smart retrieval system for codebase context
"""

import time
import logging
from typing import List, Dict, Any, Optional
from django.contrib.auth.models import User

from .embeddings import CodebaseRetriever
from .models import CodebaseQuery, IndexedRepository


logger = logging.getLogger(__name__)


class ContextualCodeRetriever:
    """Advanced retrieval system that provides context-aware code suggestions"""
    
    def __init__(self, project, user: Optional[User] = None):
        self.project = project
        self.user = user
        self.retriever = CodebaseRetriever()
    
    def get_context_for_feature_request(self, feature_description: str) -> Dict[str, Any]:
        """
        Get relevant codebase context for a new feature request
        
        Args:
            feature_description: Description of the requested feature
            
        Returns:
            Dictionary containing relevant code context, suggestions, and metadata
        """
        start_time = time.time()
        
        try:
            # Check if repository is indexed
            if not hasattr(self.project, 'indexed_repository'):
                return {
                    'context': "No codebase has been indexed for this project yet. Please index a repository first.",
                    'suggestions': [],
                    'relevant_files': [],
                    'error': 'No indexed repository'
                }
            
            indexed_repo = self.project.indexed_repository
            if indexed_repo.status != 'completed':
                return {
                    'context': f"Repository indexing is not complete (status: {indexed_repo.status}). Please wait for indexing to finish.",
                    'suggestions': [],
                    'relevant_files': [],
                    'error': f'Indexing incomplete: {indexed_repo.status}'
                }
            
            # Generate expanded queries for better retrieval
            expanded_queries = self._generate_feature_queries(feature_description)
            
            # Retrieve relevant code chunks
            retrieval_results = self.retriever.retrieve_relevant_code(
                project=self.project,
                query=feature_description,
                max_chunks=25,
                chunk_types=None  # Get all types
            )
            
            if retrieval_results.get('error'):
                return {
                    'context': f"Error retrieving code: {retrieval_results['error']}",
                    'suggestions': [],
                    'relevant_files': [],
                    'error': retrieval_results['error']
                }
            
            # Analyze retrieved chunks for patterns
            analysis = self._analyze_retrieved_chunks(retrieval_results['chunks'])
            
            # Assemble context for PRD generation
            context = self._assemble_feature_context(
                feature_description,
                retrieval_results['chunks'],
                analysis
            )
            
            # Generate implementation suggestions
            suggestions = self._generate_implementation_suggestions(
                feature_description,
                analysis
            )
            
            # Extract relevant file information
            relevant_files = self._extract_file_info(retrieval_results['chunks'])
            
            # Store query for analytics
            if self.user:
                self._store_query_record(
                    feature_description,
                    expanded_queries,
                    retrieval_results,
                    context,
                    suggestions,
                    time.time() - start_time
                )
            
            return {
                'context': context,
                'suggestions': suggestions,
                'relevant_files': relevant_files,
                'retrieval_meta': {
                    'chunks_found': len(retrieval_results['chunks']),
                    'retrieval_time_ms': retrieval_results['retrieval_time_ms'],
                    'query_expansions': expanded_queries[:3],  # Show first few
                },
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Error in contextual retrieval: {e}")
            return {
                'context': f"Error analyzing codebase: {str(e)}",
                'suggestions': [],
                'relevant_files': [],
                'error': str(e)
            }
    
    def get_context_for_prd_generation(self, project_description: str, features: List[str]) -> str:
        """
        Get codebase context specifically for PRD generation
        
        Args:
            project_description: High-level project description
            features: List of feature descriptions
            
        Returns:
            Formatted context string for PRD generation
        """
        
        # Combine project description and features into search query
        combined_query = f"{project_description}. Features: {' '.join(features)}"
        
        # Get contextual information
        context_result = self.get_context_for_feature_request(combined_query)
        
        if context_result.get('error'):
            return f"Codebase Analysis: {context_result['context']}"
        
        # Format context for PRD generation
        formatted_context = self._format_context_for_prd(
            context_result['context'],
            context_result['suggestions'],
            context_result['relevant_files']
        )
        
        return formatted_context
    
    def search_existing_implementations(self, functionality: str) -> List[Dict[str, Any]]:
        """
        Search for existing implementations of similar functionality
        
        Args:
            functionality: Description of functionality to search for
            
        Returns:
            List of existing implementations found
        """
        try:
            # Focus on functions and classes for implementation search
            results = self.retriever.retrieve_relevant_code(
                project=self.project,
                query=functionality,
                max_chunks=15,
                chunk_types=['function', 'class']
            )
            
            if results.get('error'):
                return []
            
            # Process and rank implementations
            implementations = []
            for chunk in results['chunks']:
                if chunk['relevance_score'] > 0.7:  # High relevance threshold
                    implementations.append({
                        'function_name': chunk['metadata'].get('function_name', 'Unknown'),
                        'file_path': chunk['metadata']['file_path'],
                        'chunk_type': chunk['metadata']['chunk_type'],
                        'relevance_score': chunk['relevance_score'],
                        'content_preview': chunk['content'][:300] + '...',
                        'complexity': chunk['metadata']['complexity'],
                        'dependencies': chunk['metadata'].get('dependencies', []),
                    })
            
            return implementations[:10]  # Return top 10
            
        except Exception as e:
            logger.error(f"Error searching existing implementations: {e}")
            return []
    
    def _generate_feature_queries(self, feature_description: str) -> List[str]:
        """Generate multiple query variations for better retrieval"""
        queries = [feature_description]
        
        # Add implementation-focused queries
        queries.append(f"implement {feature_description}")
        queries.append(f"how to {feature_description}")
        
        # Add component-focused queries based on common patterns
        if any(term in feature_description.lower() for term in ['user', 'auth', 'login']):
            queries.extend(['user authentication', 'login system', 'user management'])
        
        if any(term in feature_description.lower() for term in ['payment', 'billing', 'subscription']):
            queries.extend(['payment processing', 'stripe integration', 'subscription management'])
        
        if any(term in feature_description.lower() for term in ['chat', 'message', 'real-time']):
            queries.extend(['websocket implementation', 'real-time messaging', 'chat system'])
        
        if any(term in feature_description.lower() for term in ['file', 'upload', 'document']):
            queries.extend(['file upload', 'file storage', 'document handling'])
        
        if any(term in feature_description.lower() for term in ['api', 'endpoint', 'rest']):
            queries.extend(['api endpoints', 'rest api', 'django views'])
        
        return queries[:5]  # Limit to 5 queries
    
    def _analyze_retrieved_chunks(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze retrieved chunks to understand patterns and architecture"""
        if not chunks:
            return {}
        
        analysis = {
            'file_types': {},
            'chunk_types': {},
            'languages': {},
            'complexity_levels': {},
            'common_patterns': [],
            'suggested_files': [],
            'dependencies': {},
        }
        
        for chunk in chunks:
            metadata = chunk['metadata']
            
            # Count file types
            file_ext = metadata.get('file_extension', 'unknown')
            analysis['file_types'][file_ext] = analysis['file_types'].get(file_ext, 0) + 1
            
            # Count chunk types
            chunk_type = metadata.get('chunk_type', 'unknown')
            analysis['chunk_types'][chunk_type] = analysis['chunk_types'].get(chunk_type, 0) + 1
            
            # Count languages
            language = metadata.get('language', 'unknown')
            analysis['languages'][language] = analysis['languages'].get(language, 0) + 1
            
            # Count complexity levels
            complexity = metadata.get('complexity', 'medium')
            analysis['complexity_levels'][complexity] = analysis['complexity_levels'].get(complexity, 0) + 1
            
            # Collect dependencies
            deps = metadata.get('dependencies', '[]')
            try:
                import json
                deps_list = json.loads(deps) if isinstance(deps, str) else deps
                for dep in deps_list:
                    analysis['dependencies'][dep] = analysis['dependencies'].get(dep, 0) + 1
            except:
                pass
            
            # Collect suggested files for modification
            file_path = metadata.get('file_path')
            if file_path and file_path not in analysis['suggested_files']:
                analysis['suggested_files'].append(file_path)
        
        # Limit suggested files
        analysis['suggested_files'] = analysis['suggested_files'][:10]
        
        # Find most common dependencies
        analysis['top_dependencies'] = sorted(
            analysis['dependencies'].items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:10]
        
        return analysis
    
    def _assemble_feature_context(self, 
                                feature_description: str, 
                                chunks: List[Dict[str, Any]], 
                                analysis: Dict[str, Any]) -> str:
        """Assemble comprehensive context for feature development"""
        
        if not chunks:
            return "No relevant existing code found for this feature."
        
        context_parts = [
            f"# Codebase Context for: {feature_description}\n",
            f"Based on analysis of {len(chunks)} relevant code sections from your existing codebase.\n"
        ]
        
        # Add architecture overview
        if analysis:
            context_parts.extend([
                "## Architecture Overview",
                f"- Primary language: {max(analysis['languages'], key=analysis['languages'].get) if analysis['languages'] else 'Unknown'}",
                f"- File types involved: {', '.join(analysis['file_types'].keys())}",
                f"- Code complexity: {max(analysis['complexity_levels'], key=analysis['complexity_levels'].get) if analysis['complexity_levels'] else 'Unknown'}",
                ""
            ])
            
            if analysis['top_dependencies']:
                deps_list = ', '.join([dep for dep, _ in analysis['top_dependencies'][:5]])
                context_parts.append(f"- Key dependencies: {deps_list}\n")
        
        # Add relevant code sections
        context_parts.append("## Relevant Existing Code\n")
        
        # Group by file for better organization
        chunks_by_file = {}
        for chunk in chunks[:15]:  # Limit to top 15 chunks
            file_path = chunk['metadata']['file_path']
            if file_path not in chunks_by_file:
                chunks_by_file[file_path] = []
            chunks_by_file[file_path].append(chunk)
        
        for file_path, file_chunks in chunks_by_file.items():
            context_parts.append(f"### {file_path}")
            
            for chunk in file_chunks[:3]:  # Max 3 chunks per file
                func_name = chunk['metadata'].get('function_name', 'Anonymous')
                chunk_type = chunk['metadata']['chunk_type']
                relevance = chunk['relevance_score']
                
                context_parts.extend([
                    f"**{chunk_type.title()}: {func_name}** (relevance: {relevance:.2f})",
                    f"```{chunk['metadata']['language']}",
                    chunk['content'][:500] + ('...' if len(chunk['content']) > 500 else ''),
                    "```",
                    ""
                ])
        
        return '\n'.join(context_parts)
    
    def _generate_implementation_suggestions(self, 
                                           feature_description: str, 
                                           analysis: Dict[str, Any]) -> List[Dict[str, str]]:
        """Generate implementation suggestions based on codebase analysis"""
        suggestions = []
        
        if not analysis:
            return suggestions
        
        # Suggest files to modify based on patterns
        if analysis['suggested_files']:
            suggestions.append({
                'type': 'files_to_modify',
                'title': 'Files to Consider Modifying',
                'description': f"Based on similar functionality, consider modifying: {', '.join(analysis['suggested_files'][:5])}"
            })
        
        # Suggest dependencies to use
        if analysis['top_dependencies']:
            top_deps = [dep for dep, _ in analysis['top_dependencies'][:3]]
            suggestions.append({
                'type': 'dependencies',
                'title': 'Recommended Dependencies',
                'description': f"Consider using existing dependencies: {', '.join(top_deps)}"
            })
        
        # Suggest complexity approach
        if 'complexity_levels' in analysis and analysis['complexity_levels']:
            common_complexity = max(analysis['complexity_levels'], key=analysis['complexity_levels'].get)
            suggestions.append({
                'type': 'complexity',
                'title': 'Complexity Guidance',
                'description': f"Most code in this project is {common_complexity} complexity. Aim for similar patterns."
            })
        
        # Language-specific suggestions
        if 'languages' in analysis and analysis['languages']:
            primary_lang = max(analysis['languages'], key=analysis['languages'].get)
            
            if primary_lang == 'python':
                suggestions.append({
                    'type': 'patterns',
                    'title': 'Python Best Practices',
                    'description': "Follow Django patterns: use class-based views, model managers, and proper separation of concerns."
                })
            elif primary_lang in ['javascript', 'typescript']:
                suggestions.append({
                    'type': 'patterns',
                    'title': 'JavaScript/TypeScript Patterns',
                    'description': "Follow existing component patterns and use consistent async/await patterns."
                })
        
        return suggestions
    
    def _extract_file_info(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Extract relevant file information from chunks"""
        files_info = {}
        
        for chunk in chunks:
            file_path = chunk['metadata']['file_path']
            if file_path not in files_info:
                files_info[file_path] = {
                    'path': file_path,
                    'language': chunk['metadata']['language'],
                    'relevance_score': chunk['relevance_score'],
                    'chunk_types': [],
                    'functions': []
                }
            
            # Update file info
            file_info = files_info[file_path]
            chunk_type = chunk['metadata']['chunk_type']
            
            if chunk_type not in file_info['chunk_types']:
                file_info['chunk_types'].append(chunk_type)
            
            function_name = chunk['metadata'].get('function_name')
            if function_name and function_name not in file_info['functions']:
                file_info['functions'].append(function_name)
            
            # Keep highest relevance score
            file_info['relevance_score'] = max(
                file_info['relevance_score'],
                chunk['relevance_score']
            )
        
        # Sort by relevance and return top files
        sorted_files = sorted(
            files_info.values(),
            key=lambda x: x['relevance_score'],
            reverse=True
        )
        
        return sorted_files[:10]
    
    def _format_context_for_prd(self, 
                               context: str, 
                               suggestions: List[Dict[str, str]], 
                               relevant_files: List[Dict[str, str]]) -> str:
        """Format context specifically for PRD generation"""
        
        formatted_parts = [
            "# Existing Codebase Analysis\n",
            "## Current Implementation Patterns",
            context,
            "\n## Implementation Recommendations",
        ]
        
        for suggestion in suggestions:
            formatted_parts.append(f"- **{suggestion['title']}**: {suggestion['description']}")
        
        if relevant_files:
            formatted_parts.extend([
                "\n## Key Files to Reference",
                "The following files contain relevant patterns and implementations:"
            ])
            
            for file_info in relevant_files[:5]:
                functions_str = ', '.join(file_info['functions'][:3])
                formatted_parts.append(
                    f"- `{file_info['path']}` ({file_info['language']}) - "
                    f"Functions: {functions_str if functions_str else 'N/A'}"
                )
        
        return '\n'.join(formatted_parts)
    
    def _store_query_record(self, 
                           query: str, 
                           expanded_queries: List[str],
                           retrieval_results: Dict[str, Any],
                           context: str,
                           suggestions: List[Dict[str, str]],
                           total_time_seconds: float):
        """Store query record for analytics"""
        try:
            chunk_ids = []
            scores = []
            
            for chunk in retrieval_results['chunks']:
                chunk_ids.append(chunk['metadata'].get('chunk_id', ''))
                scores.append(chunk['relevance_score'])
            
            CodebaseQuery.objects.create(
                project=self.project,
                user=self.user,
                query_text=query,
                expanded_queries=expanded_queries,
                retrieved_chunks=chunk_ids,
                relevance_scores=scores,
                context_used=context,
                retrieval_time_ms=int(total_time_seconds * 1000),
                total_chunks_considered=len(retrieval_results['chunks']),
                enhanced_prd_generated=False,  # Will be updated when PRD is generated
                feature_suggestions=[s['description'] for s in suggestions]
            )
            
        except Exception as e:
            logger.warning(f"Failed to store query record: {e}")


class ArchitecturalPatternDetector:
    """Detect and analyze architectural patterns in the codebase"""
    
    def __init__(self, project):
        self.project = project
    
    def detect_patterns(self) -> Dict[str, Any]:
        """Detect common architectural patterns in the codebase"""
        try:
            from .models import CodeChunk
            
            # Get all chunks for analysis
            chunks = CodeChunk.objects.filter(
                file__repository=self.project.indexed_repository
            ).select_related('file')
            
            patterns = {
                'mvc_pattern': self._detect_mvc_pattern(chunks),
                'dependency_injection': self._detect_dependency_injection(chunks),
                'factory_pattern': self._detect_factory_pattern(chunks),
                'observer_pattern': self._detect_observer_pattern(chunks),
                'singleton_pattern': self._detect_singleton_pattern(chunks),
                'api_patterns': self._detect_api_patterns(chunks),
            }
            
            return patterns
            
        except Exception as e:
            logger.error(f"Error detecting patterns: {e}")
            return {}
    
    def _detect_mvc_pattern(self, chunks) -> Dict[str, Any]:
        """Detect MVC/MVT pattern usage"""
        mvc_indicators = {
            'models': chunks.filter(file__file_path__icontains='models.py').count(),
            'views': chunks.filter(file__file_path__icontains='views.py').count(),
            'controllers': chunks.filter(function_name__icontains='controller').count(),
            'templates': chunks.filter(file__file_extension__in=['.html', '.jinja2']).count(),
        }
        
        return {
            'detected': any(mvc_indicators.values()),
            'confidence': sum(mvc_indicators.values()) / len(mvc_indicators),
            'indicators': mvc_indicators
        }
    
    def _detect_dependency_injection(self, chunks) -> Dict[str, Any]:
        """Detect dependency injection patterns"""
        di_keywords = ['inject', 'dependency', 'container', 'provide']
        di_chunks = chunks.filter(
            models.Q(content__icontains='inject') |
            models.Q(function_name__icontains='inject') |
            models.Q(content__icontains='dependency')
        ).count()
        
        return {
            'detected': di_chunks > 0,
            'confidence': min(di_chunks / 10, 1.0),  # Normalize to 0-1
            'instances': di_chunks
        }
    
    def _detect_factory_pattern(self, chunks) -> Dict[str, Any]:
        """Detect factory pattern usage"""
        factory_chunks = chunks.filter(
            models.Q(function_name__icontains='factory') |
            models.Q(function_name__icontains='create') |
            models.Q(content__icontains='factory')
        ).count()
        
        return {
            'detected': factory_chunks > 0,
            'confidence': min(factory_chunks / 5, 1.0),
            'instances': factory_chunks
        }
    
    def _detect_observer_pattern(self, chunks) -> Dict[str, Any]:
        """Detect observer pattern (signals, events, etc.)"""
        observer_chunks = chunks.filter(
            models.Q(content__icontains='signal') |
            models.Q(content__icontains='observer') |
            models.Q(content__icontains='event') |
            models.Q(content__icontains='listener')
        ).count()
        
        return {
            'detected': observer_chunks > 0,
            'confidence': min(observer_chunks / 5, 1.0),
            'instances': observer_chunks
        }
    
    def _detect_singleton_pattern(self, chunks) -> Dict[str, Any]:
        """Detect singleton pattern usage"""
        singleton_chunks = chunks.filter(
            models.Q(content__icontains='singleton') |
            models.Q(content__icontains='__new__') |
            models.Q(function_name__icontains='instance')
        ).count()
        
        return {
            'detected': singleton_chunks > 0,
            'confidence': min(singleton_chunks / 3, 1.0),
            'instances': singleton_chunks
        }
    
    def _detect_api_patterns(self, chunks) -> Dict[str, Any]:
        """Detect API design patterns"""
        api_chunks = chunks.filter(
            models.Q(file__file_path__icontains='api') |
            models.Q(file__file_path__icontains='views') |
            models.Q(content__icontains='@api_view') |
            models.Q(content__icontains='APIView') |
            models.Q(content__icontains='def get') |
            models.Q(content__icontains='def post')
        ).count()
        
        rest_chunks = chunks.filter(
            models.Q(content__icontains='rest') |
            models.Q(content__icontains='serializer') |
            models.Q(content__icontains='viewset')
        ).count()
        
        return {
            'detected': api_chunks > 0,
            'rest_api_usage': rest_chunks > 0,
            'confidence': min(api_chunks / 10, 1.0),
            'api_endpoints': api_chunks,
            'rest_patterns': rest_chunks
        }