import os
import re
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
import logging
from datetime import datetime

import git
import requests
from django.utils import timezone
from accounts.models import GitHubToken


logger = logging.getLogger(__name__)


class GitHubRepositoryManager:
    """Manager for GitHub repository operations"""
    
    def __init__(self, user):
        self.user = user
        self.github_token = self._get_github_token()
    
    def _get_github_token(self) -> Optional[GitHubToken]:
        """Get GitHub token for the user"""
        try:
            return GitHubToken.objects.get(user=self.user)
        except GitHubToken.DoesNotExist:
            logger.warning(f"No GitHub token found for user {self.user.username}")
            return None
    
    def validate_repository_access(self, github_url: str) -> Tuple[bool, str, Dict[str, str]]:
        """Validate user access to GitHub repository"""
        if not self.github_token:
            return False, "No GitHub token configured", {}
        
        try:
            # Parse GitHub URL to extract owner and repo
            repo_info = self._parse_github_url(github_url)
            if not repo_info:
                return False, "Invalid GitHub URL format", {}
            
            # Check repository access via GitHub API
            api_url = f"https://api.github.com/repos/{repo_info['owner']}/{repo_info['repo']}"
            headers = {
                'Authorization': f'token {self.github_token.access_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            response = requests.get(api_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                repo_data = response.json()
                return True, "Repository access validated", {
                    'owner': repo_info['owner'],
                    'repo': repo_info['repo'],
                    'default_branch': repo_data.get('default_branch', 'main'),
                    'is_private': repo_data.get('private', False),
                    'language': repo_data.get('language'),
                    'size': repo_data.get('size', 0),
                }
            elif response.status_code == 404:
                return False, "Repository not found or no access", {}
            elif response.status_code == 403:
                # Check if it's a rate limit or permission issue
                rate_limit_remaining = response.headers.get('X-RateLimit-Remaining', 'unknown')
                if rate_limit_remaining == '0':
                    return False, "GitHub API rate limit exceeded. Please try again later.", {}
                else:
                    # Check token scopes
                    token_scopes = response.headers.get('X-OAuth-Scopes', '')
                    return False, f"Access forbidden. Repository may be private or token missing 'repo' scope. Current scopes: {token_scopes}", {}
            else:
                return False, f"GitHub API error: {response.status_code}", {}
                
        except Exception as e:
            logger.error(f"Error validating repository access: {e}")
            return False, f"Error validating repository: {str(e)}", {}
    
    def clone_repository(self, github_url: str, branch: str = None) -> Tuple[bool, str, Optional[str]]:
        """Clone repository to temporary directory"""
        if not self.github_token:
            return False, "No GitHub token configured", None
        
        try:
            # Create temporary directory
            temp_dir = tempfile.mkdtemp(prefix='lfg_repo_')
            
            # Construct authenticated clone URL
            repo_info = self._parse_github_url(github_url)
            if not repo_info:
                return False, "Invalid GitHub URL", None
            
            auth_url = f"https://{self.github_token.access_token}@github.com/{repo_info['owner']}/{repo_info['repo']}.git"
            
            # Clone repository
            logger.info(f"Cloning repository {github_url} to {temp_dir}")
            repo = git.Repo.clone_from(auth_url, temp_dir, branch=branch)
            
            return True, f"Repository cloned successfully to {temp_dir}", temp_dir
            
        except git.exc.GitCommandError as e:
            logger.error(f"Git clone failed: {e}")
            return False, f"Git clone failed: {str(e)}", None
        except Exception as e:
            logger.error(f"Error cloning repository: {e}")
            return False, f"Error cloning repository: {str(e)}", None
    
    def get_repository_files(self, repo_path: str, file_extensions: List[str], 
                           exclude_patterns: List[str]) -> List[Dict[str, Any]]:
        """Get list of files in repository with metadata"""
        files = []
        
        try:
            repo = git.Repo(repo_path)
            repo_root = Path(repo_path)
            
            # Walk through all files in repository
            for file_path in repo_root.rglob('*'):
                if file_path.is_file():
                    relative_path = file_path.relative_to(repo_root)
                    
                    # Check if file should be indexed
                    from .parsers import should_index_file
                    should_index, reason = should_index_file(
                        str(relative_path), exclude_patterns, 500, file_extensions
                    )
                    
                    if should_index:
                        try:
                            # Get file statistics
                            stat = file_path.stat()
                            
                            # Get last commit that modified this file
                            last_commit = self._get_last_commit_for_file(repo, str(relative_path))
                            
                            files.append({
                                'relative_path': str(relative_path),
                                'absolute_path': str(file_path),
                                'file_name': file_path.name,
                                'file_extension': file_path.suffix.lower(),
                                'size_bytes': stat.st_size,
                                'last_commit_hash': last_commit['hash'] if last_commit else None,
                                'last_modified_at': last_commit['date'] if last_commit else timezone.now(),
                            })
                        except Exception as e:
                            logger.warning(f"Error processing file {relative_path}: {e}")
                            continue
            
            logger.info(f"Found {len(files)} files to index in repository")
            return files
            
        except Exception as e:
            logger.error(f"Error scanning repository files: {e}")
            return []
    
    def get_latest_commit_hash(self, repo_path: str, branch: str = None) -> Optional[str]:
        """Get the latest commit hash from repository"""
        try:
            repo = git.Repo(repo_path)
            if branch:
                commit = repo.commit(branch)
            else:
                commit = repo.head.commit
            return commit.hexsha
        except Exception as e:
            logger.error(f"Error getting latest commit hash: {e}")
            return None
    
    def cleanup_temp_directory(self, temp_dir: str):
        """Clean up temporary directory"""
        try:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                logger.debug(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            logger.warning(f"Error cleaning up temporary directory {temp_dir}: {e}")
    
    def _parse_github_url(self, github_url: str) -> Optional[Dict[str, str]]:
        """Parse GitHub URL to extract owner and repository name"""
        # Support various GitHub URL formats
        patterns = [
            r'github\.com[:/]([^/]+)/([^/\.]+)(?:\.git)?',
            r'github\.com/([^/]+)/([^/]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, github_url)
            if match:
                return {
                    'owner': match.group(1),
                    'repo': match.group(2)
                }
        
        return None
    
    def _get_last_commit_for_file(self, repo: git.Repo, file_path: str) -> Optional[Dict[str, Any]]:
        """Get the last commit that modified a specific file"""
        try:
            commits = list(repo.iter_commits(paths=file_path, max_count=1))
            if commits:
                commit = commits[0]
                return {
                    'hash': commit.hexsha,
                    'date': datetime.fromtimestamp(commit.committed_date, tz=timezone.get_current_timezone()),
                    'message': commit.message.strip(),
                    'author': str(commit.author)
                }
            return None
        except Exception as e:
            logger.warning(f"Error getting commit history for {file_path}: {e}")
            return None
    
    def check_for_updates(self, indexed_repo, local_repo_path: str) -> Tuple[bool, List[str]]:
        """Check if repository has updates since last indexing"""
        try:
            latest_hash = self.get_latest_commit_hash(local_repo_path, indexed_repo.github_branch)
            
            if not latest_hash:
                return False, ["Could not get latest commit hash"]
            
            if indexed_repo.last_commit_hash == latest_hash:
                return False, ["Repository is up to date"]
            
            # Get list of changed files
            repo = git.Repo(local_repo_path)
            if indexed_repo.last_commit_hash:
                try:
                    # Get diff between last indexed commit and latest
                    diff = repo.git.diff('--name-only', indexed_repo.last_commit_hash, latest_hash)
                    changed_files = diff.split('\n') if diff.strip() else []
                    return True, changed_files
                except git.exc.GitCommandError:
                    # If diff fails, assume all files need reindexing
                    logger.warning("Could not get diff, assuming full reindex needed")
                    return True, []
            else:
                # First time indexing
                return True, []
                
        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            return False, [f"Error checking updates: {str(e)}"]


class RepositoryIndexer:
    """Main class for indexing GitHub repositories"""
    
    def __init__(self, indexed_repository):
        self.indexed_repository = indexed_repository
        self.github_manager = GitHubRepositoryManager(indexed_repository.project.owner)
        self.temp_dir = None
    
    def index_repository(self, force_full_reindex: bool = False) -> Tuple[bool, str]:
        """Index or update repository"""
        try:
            # Validate repository access
            valid, message, repo_info = self.github_manager.validate_repository_access(
                self.indexed_repository.github_url
            )
            
            if not valid:
                return False, f"Repository validation failed: {message}"
            
            # Clone repository
            success, clone_message, temp_dir = self.github_manager.clone_repository(
                self.indexed_repository.github_url,
                self.indexed_repository.github_branch
            )
            
            if not success:
                return False, f"Clone failed: {clone_message}"
            
            self.temp_dir = temp_dir
            
            # Check for updates if not forcing full reindex
            if not force_full_reindex:
                has_updates, changed_files = self.github_manager.check_for_updates(
                    self.indexed_repository, temp_dir
                )
                if not has_updates:
                    self.github_manager.cleanup_temp_directory(temp_dir)
                    return True, "Repository is already up to date"
            
            # Get files to index
            files_to_index = self.github_manager.get_repository_files(
                temp_dir,
                self.indexed_repository.file_extensions,
                self.indexed_repository.exclude_patterns
            )

            if not files_to_index:
                self.github_manager.cleanup_temp_directory(temp_dir)
                return False, "No files found to index"

            # Auto-detect stack from repository files
            # NOTE: Use ALL files for detection, not just filtered files (go.mod, package.json etc. may be filtered out)
            try:
                from factory.stack_configs import detect_stack_from_files
                from pathlib import Path

                # Get ALL file names in repo for stack detection (ignore extension filter)
                repo_root = Path(temp_dir)
                all_files = []
                for file_path in repo_root.rglob('*'):
                    if file_path.is_file() and not any(excl in str(file_path) for excl in ['.git/', 'node_modules/', '__pycache__/']):
                        all_files.append(str(file_path.relative_to(repo_root)))

                logger.info(f"[STACK] Starting stack detection for {len(all_files)} total files (indexed: {len(files_to_index)}), force_full_reindex={force_full_reindex}")
                logger.info(f"[STACK] Sample file paths: {all_files[:30]}")

                detected_stack = detect_stack_from_files(all_files)
                logger.info(f"[STACK] Detection result: {detected_stack}")

                if detected_stack and self.indexed_repository.project:
                    project = self.indexed_repository.project
                    logger.info(f"[STACK] Current project stack: {project.stack}, force_reindex: {force_full_reindex}")

                    # Update stack if: re-indexing OR stack is still default/custom
                    if force_full_reindex or project.stack in ('nextjs', 'custom'):
                        old_stack = project.stack
                        project.stack = detected_stack
                        project.save(update_fields=['stack'])
                        logger.info(f"[STACK] Updated stack from '{old_stack}' to '{detected_stack}' for project {project.name}")
                    else:
                        logger.info(f"[STACK] Skipping update - stack already set to '{project.stack}' and not re-indexing")
                else:
                    logger.warning(f"[STACK] No stack detected or no project linked")
            except Exception as e:
                logger.error(f"[STACK] Failed to auto-detect stack: {e}", exc_info=True)

            # Update repository status and statistics
            self.indexed_repository.status = 'indexing'
            self.indexed_repository.total_files = len(files_to_index)
            self.indexed_repository.save()
            
            # Index files
            success_count = 0
            error_count = 0
            
            for file_info in files_to_index:
                try:
                    success = self._index_single_file(file_info)
                    if success:
                        success_count += 1
                    else:
                        error_count += 1
                except Exception as e:
                    logger.error(f"Error indexing file {file_info['relative_path']}: {e}")
                    error_count += 1
            
            # Update repository status
            latest_hash = self.github_manager.get_latest_commit_hash(temp_dir)
            
            # Determine status based on success ratio
            total_files = success_count + error_count
            success_ratio = success_count / total_files if total_files > 0 else 0
            
            if error_count == 0:
                # Perfect success
                status = 'completed'
                error_message = None
            elif success_ratio >= 0.75:  # 75% or more success
                # Acceptable partial success
                status = 'completed'
                error_message = f"Successfully indexed {success_count}/{total_files} files ({error_count} files skipped)"
            elif success_ratio >= 0.25:  # 25-74% success  
                # Partial success with warnings
                status = 'completed'  
                error_message = f"Partial indexing: {success_count}/{total_files} files indexed ({error_count} files failed)"
            else:
                # Too many failures
                status = 'error'
                error_message = f"Indexing failed: only {success_count}/{total_files} files indexed ({error_count} failures)"
            
            self.indexed_repository.status = status
            self.indexed_repository.last_indexed_at = timezone.now()
            self.indexed_repository.last_commit_hash = latest_hash
            self.indexed_repository.indexed_files_count = success_count
            self.indexed_repository.error_count = error_count
            self.indexed_repository.error_message = error_message
            
            self.indexed_repository.save()
            
            # Clean up
            self.github_manager.cleanup_temp_directory(temp_dir)
            
            return True, f"Indexing completed. {success_count} files indexed, {error_count} errors"
            
        except Exception as e:
            logger.error(f"Repository indexing failed: {e}")
            if self.temp_dir:
                self.github_manager.cleanup_temp_directory(self.temp_dir)
            return False, f"Indexing failed: {str(e)}"
    
    def _index_single_file(self, file_info: Dict[str, Any]) -> bool:
        """Index a single file"""
        from .models import IndexedFile, CodeChunk
        from .parsers import CodeParser, calculate_content_hash
        
        try:
            # Read file content
            with open(file_info['absolute_path'], 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Calculate content hash for change detection
            content_hash = calculate_content_hash(content)
            
            # Check if file already exists and is unchanged
            existing_file = IndexedFile.objects.filter(
                repository=self.indexed_repository,
                file_path=file_info['relative_path']
            ).first()

            # DISABLED: Always re-index files to ensure CodebaseIndexMap is populated
            # if existing_file and existing_file.content_hash == content_hash:
            #     # File unchanged, skip
            #     existing_file.status = 'indexed'
            #     existing_file.save()
            #     return True
            
            # Parse file content
            parser = CodeParser()
            parse_result = parser.parse_file(file_info['relative_path'], content)
            
            # Create or update IndexedFile record
            indexed_file, created = IndexedFile.objects.update_or_create(
                repository=self.indexed_repository,
                file_path=file_info['relative_path'],
                defaults={
                    'file_name': file_info['file_name'],
                    'file_extension': file_info['file_extension'],
                    'file_size_bytes': file_info['size_bytes'],
                    'last_commit_hash': file_info['last_commit_hash'],
                    'last_modified_at': file_info['last_modified_at'],
                    'status': 'processing',
                    'content_hash': content_hash,
                    'language': parse_result['language'],
                    'total_lines': parse_result['total_lines'],
                    'code_chunks_count': len(parse_result['chunks']),
                }
            )
            
            # Delete existing chunks if updating
            if not created:
                indexed_file.chunks.all().delete()
            
            # Create new code chunks
            for chunk_data in parse_result['chunks']:
                # Truncate fields to fit database constraints
                content_preview = chunk_data['content_preview'][:200] if chunk_data['content_preview'] else ''
                function_name = chunk_data['function_name'][:255] if chunk_data['function_name'] else None

                code_chunk = CodeChunk.objects.create(
                    file=indexed_file,
                    chunk_type=chunk_data['chunk_type'],
                    content=chunk_data['content'],
                    content_preview=content_preview,
                    start_line=chunk_data['start_line'],
                    end_line=chunk_data['end_line'],
                    function_name=function_name,
                    complexity=chunk_data['complexity'],
                    dependencies=chunk_data['dependencies'],
                    parameters=chunk_data['parameters'],
                    tags=chunk_data['tags'],
                    description=chunk_data['description'],
                    embedding_stored=False
                )
                
                # Set embedding_id after object creation
                code_chunk.embedding_id = str(code_chunk.chunk_id)
                code_chunk.save()

            # Build index map entries BEFORE storing embeddings (for fast lookup)
            try:
                self._build_index_map(indexed_file, parse_result)
                logger.info(f"Successfully built index map for {indexed_file.file_path}")
            except Exception as e:
                logger.error(f"Failed to build index map for {indexed_file.file_path}: {e}")
                import traceback
                logger.error(f"Index map traceback: {traceback.format_exc()}")

            indexed_file.status = 'indexed'
            indexed_file.indexed_at = timezone.now()
            indexed_file.error_message = ''
            indexed_file.save()

            return True
            
        except Exception as e:
            logger.error(f"Error indexing file {file_info['relative_path']}: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            
            # Update file status to error
            if 'indexed_file' in locals():
                indexed_file.status = 'error'
                indexed_file.error_message = str(e)
                indexed_file.save()
            
            return False

    def _build_index_map(self, indexed_file, parse_result: Dict[str, Any]) -> None:
        """
        Build searchable index map for fast lookups without vector search

        Creates CodebaseIndexMap entries for all functions, classes, and methods
        to enable quick text-based searches before expensive vector operations.
        """
        from .models import CodebaseIndexMap
        import re

        logger.info(f"Building index map for {indexed_file.file_path}")

        # Clear existing index entries for this file
        CodebaseIndexMap.objects.filter(
            repository=self.indexed_repository,
            file_path=indexed_file.file_path
        ).delete()

        # Build fully qualified names based on language
        language = parse_result.get('language', 'unknown')
        file_module = indexed_file.file_path.replace('/', '.').rsplit('.', 1)[0]  # Remove extension

        # Extract keywords from content
        def extract_keywords(content, description=None):
            """Extract searchable keywords from code"""
            keywords = set()

            # Add words from description/docstring
            if description:
                words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b', description.lower())
                keywords.update(words[:10])  # Limit to top 10

            # Add camelCase/snake_case word splits
            words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]+\b', content)
            for word in words[:20]:  # Limit processing
                # Split camelCase
                split_words = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)', word)
                keywords.update([w.lower() for w in split_words if len(w) > 2])

            return list(keywords)[:15]  # Limit to 15 keywords

        # Create index entries for each chunk
        for chunk_data in parse_result.get('chunks', []):
            chunk_type = chunk_data.get('chunk_type')
            entity_name = chunk_data.get('function_name') or indexed_file.file_name

            # Skip full-file chunks unless it's the only chunk
            if chunk_type == 'file' and len(parse_result['chunks']) > 1:
                continue

            # Build fully qualified name
            if language == 'python':
                # For Python: module.Class.method or module.function
                fqn = f"{file_module}.{entity_name}" if entity_name else file_module
            elif language in ['javascript', 'typescript']:
                # For JS/TS: use file path as namespace
                fqn = f"{file_module}.{entity_name}" if entity_name else file_module
            else:
                fqn = entity_name or file_module

            # Extract decorators/annotations
            decorators = []
            content = chunk_data.get('content', '')
            if language == 'python':
                decorators = re.findall(r'@(\w+)', content)
            elif language in ['javascript', 'typescript']:
                decorators = re.findall(r'@(\w+)\(', content)

            # Find matching code chunk object
            # Truncate function_name to match what was saved in CodeChunk
            truncated_function_name = chunk_data.get('function_name')[:255] if chunk_data.get('function_name') else None

            code_chunk = indexed_file.chunks.filter(
                chunk_type=chunk_type,
                function_name=truncated_function_name,
                start_line=chunk_data.get('start_line')
            ).first()

            # Truncate fields to fit database constraints
            entity_name_truncated = entity_name[:500] if entity_name else ''
            fqn_truncated = fqn[:1000] if fqn else ''

            # Create index map entry
            CodebaseIndexMap.objects.create(
                repository=self.indexed_repository,
                file_path=indexed_file.file_path,
                entity_type=chunk_type,
                entity_name=entity_name_truncated,
                fully_qualified_name=fqn_truncated,
                language=language,
                start_line=chunk_data.get('start_line', 0),
                end_line=chunk_data.get('end_line', 0),
                parameters=chunk_data.get('parameters', []),
                dependencies=chunk_data.get('dependencies', []),
                decorators=decorators,
                description=chunk_data.get('description', '')[:500] if chunk_data.get('description') else '',
                keywords=extract_keywords(content, chunk_data.get('description')),
                complexity=chunk_data.get('complexity', 'medium'),
                code_chunk=code_chunk
            )

        logger.info(f"Created {CodebaseIndexMap.objects.filter(repository=self.indexed_repository, file_path=indexed_file.file_path).count()} index map entries for {indexed_file.file_path}")

    def _parse_github_url(self, github_url: str) -> Optional[Dict[str, str]]:
        """Parse GitHub URL to extract owner and repo"""
        patterns = [
            r'github\.com[:/]([^/]+)/([^/\.]+)(?:\.git)?',
            r'github\.com/([^/]+)/([^/]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, github_url)
            if match:
                return {
                    'owner': match.group(1),
                    'repo': match.group(2)
                }
        
        return None


def sync_repository(indexed_repository, force_full_reindex: bool = False) -> Tuple[bool, str]:
    """Sync a repository (convenience function for background tasks)"""
    indexer = RepositoryIndexer(indexed_repository)
    return indexer.index_repository(force_full_reindex)


def validate_github_access(user, github_url: str) -> Tuple[bool, str, Dict[str, str]]:
    """Validate GitHub access (convenience function)"""
    manager = GitHubRepositoryManager(user)
    return manager.validate_repository_access(github_url)


def get_repo_file_list_via_api(user, github_url: str, branch: str = 'main') -> List[str]:
    """
    Get file list from a GitHub repository using the API (no clone needed).

    Uses the Git Trees API to fetch the file list, which is much faster than cloning.

    Args:
        user: Django user with GitHub token
        github_url: GitHub repository URL
        branch: Branch to get files from (default: 'main')

    Returns:
        List of file paths in the repository
    """
    try:
        # Get GitHub token
        github_token = GitHubToken.objects.get(user=user)
    except GitHubToken.DoesNotExist:
        logger.warning(f"No GitHub token found for user {user.username}")
        return []

    # Parse GitHub URL
    patterns = [
        r'github\.com[:/]([^/]+)/([^/\.]+)(?:\.git)?',
        r'github\.com/([^/]+)/([^/]+)',
    ]

    owner = None
    repo = None
    for pattern in patterns:
        match = re.search(pattern, github_url)
        if match:
            owner = match.group(1)
            repo = match.group(2)
            break

    if not owner or not repo:
        logger.error(f"Could not parse GitHub URL: {github_url}")
        return []

    # Fetch file tree via GitHub API
    api_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    headers = {
        'Authorization': f'token {github_token.access_token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    try:
        response = requests.get(api_url, headers=headers, timeout=30)

        if response.status_code == 200:
            data = response.json()
            # Filter for files only (not directories)
            files = [
                item['path'] for item in data.get('tree', [])
                if item['type'] == 'blob'
            ]
            logger.info(f"Found {len(files)} files in {owner}/{repo} via API")
            return files
        elif response.status_code == 404:
            logger.error(f"Repository or branch not found: {owner}/{repo}:{branch}")
            return []
        else:
            logger.error(f"GitHub API error: {response.status_code} - {response.text}")
            return []

    except requests.RequestException as e:
        logger.error(f"Error fetching file list from GitHub API: {e}")
        return []
