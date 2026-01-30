"""
Task Definitions

Add your custom task functions here. Each task function should:
1. Accept the necessary parameters
2. Return a dictionary with the result
3. Handle exceptions appropriately
4. Use logging for debugging

Example structure:

def your_task_function(param1: str, param2: int) -> dict:
    '''
    Your task description.
    
    Args:
        param1: Description of parameter 1
        param2: Description of parameter 2
        
    Returns:
        Dict with task result
    '''
    import logging
    import time
    
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Starting task with {param1} and {param2}")
        
        # Your task logic here
        time.sleep(1)  # Simulate work
        
        result = {
            'status': 'success',
            'param1': param1,
            'param2': param2,
            'completed_at': time.time()
        }
        
        logger.info(f"Task completed: {result}")
        return result
        
    except Exception as e:
        error_msg = f"Task failed: {str(e)}"
        logger.error(error_msg)
        return {'status': 'error', 'error': error_msg}
"""

# Add your task functions below this line

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
import os
from contextvars import ContextVar

from channels.layers import get_channel_layer
from django.conf import settings
from django.db import transaction
from asgiref.sync import sync_to_async, async_to_sync

from projects.models import ProjectTicket, Project
from factory.ai_providers import get_ai_response
from factory.ai_functions import new_dev_sandbox_tool, _fetch_workspace, get_magpie_client, _slugify_project_name, MAGPIE_BOOTSTRAP_SCRIPT
from factory.prompts.builder_prompt import get_system_builder_mode
from factory.ai_tools import tools_builder
from factory.stack_configs import get_stack_config, get_bootstrap_script, get_gitignore_content
from development.models import MagpieWorkspace
import time

# Context variables to store execution context
current_ticket_id: ContextVar[Optional[int]] = ContextVar('current_ticket_id', default=None)
current_workspace_id: ContextVar[Optional[str]] = ContextVar('current_workspace_id', default=None)

logger = logging.getLogger(__name__)


def broadcast_ticket_notification(conversation_id: Optional[int], payload: Dict[str, Any]) -> None:
    if not conversation_id:
        return
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    event = {
        'type': 'ai_response_chunk',
        'chunk': '',
        'is_final': False,
        'conversation_id': conversation_id,
    }
    event.update(payload)
    event.setdefault('is_notification', True)
    event.setdefault('notification_marker', "__NOTIFICATION__")
    try:
        async_to_sync(channel_layer.group_send)(f"conversation_{conversation_id}", event)
    except Exception as exc:
        logger.error(f"Failed to broadcast ticket notification: {exc}")


def broadcast_ticket_status_change(ticket_id: int, status: str, queue_status: str = 'none', error_reason: str = None) -> None:
    """
    Broadcast a status change to the ticket logs WebSocket group.
    This updates the UI to reflect the new ticket status and queue status.
    """
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    try:
        message = {
            'type': 'ticket_status_changed',
            'status': status,
            'ticket_id': ticket_id,
            'queue_status': queue_status
        }
        if error_reason:
            message['error_reason'] = error_reason
        async_to_sync(channel_layer.group_send)(
            f"ticket_logs_{ticket_id}",
            message
        )
        logger.info(f"Broadcast status change for ticket #{ticket_id}: status={status}, queue_status={queue_status}, error={error_reason[:50] if error_reason else None}")
    except Exception as exc:
        logger.error(f"Failed to broadcast ticket status change: {exc}")


def simple_test_task_for_debugging(message: str, delay: int = 1) -> dict:
    """
    A simple test task to verify Django-Q functionality without complex operations.
    This helps isolate the timer issue from the complex ticket implementation logic.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Simple test task started: {message}")
    
    try:
        # Simulate some work without complex Django operations
        time.sleep(delay)
        
        result = {
            'status': 'success',
            'message': message,
            'timestamp': time.time(),
            'delay': delay,
            'worker_info': {
                'process_id': os.getpid(),
                'working_directory': os.getcwd()
            }
        }
        
        logger.info(f"Simple test task completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error in simple test task: {str(e)}")
        return {
            'status': 'error',
            'message': str(e),
            'timestamp': time.time()
        }


def safe_execute_ticket_implementation(ticket_id: int, project_id: int, conversation_id: int) -> Dict[str, Any]:
    """
    A safer version of execute_ticket_implementation that reduces complexity to prevent timer issues.
    This version does minimal operations and delegates complex work to synchronous mode.
    """
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Starting SAFE implementation of ticket {ticket_id}")
        
        # Simple task simulation for now
        time.sleep(2)  # Simulate work
        
        # Update ticket status with minimal Django operations
        from projects.models import ProjectTicket
        
        ticket = ProjectTicket.objects.get(id=ticket_id)
        ticket.status = 'review'  # Mark as review when execution completes
        ticket.save()
        
        logger.info(f"Successfully completed SAFE implementation of ticket {ticket_id}")
        
        return {
            "status": "success",
            "ticket_id": ticket_id,
            "message": f"SAFE implementation completed for ticket {ticket_id}",
            "completion_time": datetime.now().isoformat(),
            "worker_info": {
                "process_id": os.getpid(),
                "working_directory": os.getcwd()
            }
        }
        
    except Exception as e:
        logger.error(f"Error in SAFE ticket implementation {ticket_id}: {str(e)}")
        
        return {
            "status": "error",
            "ticket_id": ticket_id,
            "error": str(e),
            "completion_time": datetime.now().isoformat()
        }

import json
import time
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from django.db import models
from asgiref.sync import async_to_sync
import requests

logger = logging.getLogger(__name__)


# ============================================================================
# GitHub Integration Helper Functions
# ============================================================================

def get_github_token(user) -> Optional[str]:
    """Get user's GitHub access token"""
    from accounts.models import GitHubToken
    try:
        github_token = GitHubToken.objects.get(user=user)
        return github_token.access_token
    except GitHubToken.DoesNotExist:
        return None


def get_or_create_github_repo(project, user, stack: str = None) -> Dict[str, Any]:
    """
    Get existing GitHub repo or create a new one for the project.
    If creating new, initialize it with the appropriate template for the stack.

    Args:
        project: The Project instance
        user: The User instance
        stack: Technology stack (e.g., 'nextjs', 'python-django', 'go'). Uses project.stack if not provided.

    Returns:
        Dict with 'owner', 'repo_name', 'url', 'created' keys

    Raises:
        Exception with detailed error message if repo cannot be created or accessed
    """
    from codebase_index.models import IndexedRepository

    # Get stack config
    stack = stack or getattr(project, 'stack', 'nextjs')
    stack_config = get_stack_config(stack)
    template_repo = stack_config['template_repo']

    # Check if project already has a GitHub repo linked
    try:
        indexed_repo = IndexedRepository.objects.get(project=project)
        logger.info(f"Found existing GitHub repo: {indexed_repo.github_owner}/{indexed_repo.github_repo_name}")

        # Check if the repo actually has content (main branch exists)
        token = get_github_token(user)
        if not token:
            raise Exception("GitHub not connected. Please connect GitHub in settings.")

        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }

        # Try to get the main branch to see if repo has content
        try:
            main_response = requests.get(
                f'https://api.github.com/repos/{indexed_repo.github_owner}/{indexed_repo.github_repo_name}/git/refs/heads/main',
                headers=headers,
                timeout=10
            )
            repo_has_content = (main_response.status_code == 200)
        except:
            repo_has_content = False

        logger.info(f"Existing repo has content: {repo_has_content}")

        return {
            'owner': indexed_repo.github_owner,
            'repo_name': indexed_repo.github_repo_name,
            'url': indexed_repo.github_url,
            'created': False,
            'needs_template': not repo_has_content  # If no content, needs template
        }
    except IndexedRepository.DoesNotExist:
        logger.info(f"No existing GitHub repo found for project {project.name}, will create new one")

    # Get GitHub token
    token = get_github_token(user)
    if not token:
        raise Exception("GitHub not connected. Please connect GitHub in settings.")

    # Create new repo name
    repo_name = project.provided_name or project.name
    repo_name = repo_name.lower().replace(' ', '-').replace('_', '-')
    logger.info(f"Creating GitHub repository: {repo_name}")

    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    # Step 1: Create empty repo on GitHub
    data = {
        'name': repo_name,
        'description': f'LFG Project: {project.name}',
        'private': True,
        'auto_init': False
    }

    try:
        response = requests.post(
            'https://api.github.com/user/repos',
            headers=headers,
            json=data,
            timeout=10
        )
    except requests.exceptions.Timeout:
        raise Exception("GitHub API timeout while creating repository")
    except requests.exceptions.RequestException as e:
        raise Exception(f"GitHub API request failed: {str(e)}")

    if response.status_code == 201:
        repo_data = response.json()
        owner = repo_data['owner']['login']
        repo_url = repo_data['html_url']

        logger.info(f"Created empty GitHub repo: {owner}/{repo_name}")

        # Step 2: Initialize repo with template using GitHub API
        # This is a template repository, so we use the GitHub template API
        repo_needs_template = True

        # Only use template if one is configured for this stack
        if template_repo:
            try:
                # First, delete the empty repo we just created
                delete_response = requests.delete(
                    f'https://api.github.com/repos/{owner}/{repo_name}',
                    headers=headers,
                    timeout=10
                )

                if delete_response.status_code not in [204, 404]:
                    logger.warning(f"Failed to delete empty repo (will continue): {delete_response.status_code}")

                # Now create from template
                logger.info(f"Creating repo from template: {template_repo}")
                template_response = requests.post(
                    f'https://api.github.com/repos/{template_repo}/generate',
                    headers=headers,
                    json={
                        'owner': owner,
                        'name': repo_name,
                        'description': f'LFG Project: {project.name}',
                        'private': True
                    },
                    timeout=30
                )

                if template_response.status_code == 201:
                    repo_data = template_response.json()
                    repo_url = repo_data['html_url']
                    logger.info(f"Successfully created repo from template: {owner}/{repo_name}")
                    repo_needs_template = False  # Template was successfully applied
                else:
                    # If template creation fails, fall back to the empty repo
                    error_detail = template_response.json().get('message', '') if template_response.text else ''
                    logger.warning(f"Template creation failed ({template_response.status_code}): {error_detail}. Will push template from workspace.")
                    # Recreate the empty repo
                    response = requests.post(
                        'https://api.github.com/user/repos',
                        headers=headers,
                        json=data,
                        timeout=10
                    )
                    if response.status_code == 201:
                        repo_data = response.json()
                        repo_url = repo_data['html_url']

            except Exception as e:
                logger.warning(f"Failed to use template repository: {str(e)}. Will push template from workspace.")
        else:
            # No template configured for this stack (e.g., 'custom')
            logger.info(f"No template configured for stack '{stack}', using empty repo")

        # Create IndexedRepository record
        IndexedRepository.objects.create(
            project=project,
            github_url=repo_url,
            github_owner=owner,
            github_repo_name=repo_name,
            github_branch='main'
        )

        logger.info(f"Successfully created GitHub repo: {owner}/{repo_name}")
        return {
            'owner': owner,
            'repo_name': repo_name,
            'url': repo_url,
            'created': True,
            'needs_template': repo_needs_template
        }
    elif response.status_code == 422:
        # Repo already exists, get user info first to determine owner
        logger.info(f"Repository {repo_name} already exists, fetching existing repo...")
        try:
            user_response = requests.get('https://api.github.com/user', headers=headers, timeout=10)
            if user_response.status_code != 200:
                error_detail = user_response.json().get('message', user_response.text) if user_response.text else 'Unknown error'
                raise Exception(f"Failed to get GitHub user info: {error_detail}")

            username = user_response.json()['login']
            logger.info(f"GitHub username: {username}")

            # Now get the existing repo
            repo_response = requests.get(
                f'https://api.github.com/repos/{username}/{repo_name}',
                headers=headers,
                timeout=10
            )

            if repo_response.status_code == 200:
                repo_data = repo_response.json()
                owner = repo_data['owner']['login']

                # Create IndexedRepository record
                IndexedRepository.objects.create(
                    project=project,
                    github_url=repo_data['html_url'],
                    github_owner=owner,
                    github_repo_name=repo_name,
                    github_branch='main'
                )

                logger.info(f"Using existing GitHub repo: {owner}/{repo_name}")
                return {
                    'owner': owner,
                    'repo_name': repo_name,
                    'url': repo_data['html_url'],
                    'created': False,
                    'needs_template': False  # Existing repo already has content
                }
            else:
                error_detail = repo_response.json().get('message', repo_response.text) if repo_response.text else 'Unknown error'
                raise Exception(f"Repository exists but cannot be accessed: {error_detail}")
        except requests.exceptions.Timeout:
            raise Exception("GitHub API timeout while fetching existing repository")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to fetch existing repository: {str(e)}")
    elif response.status_code == 401:
        raise Exception("GitHub authentication failed. Please reconnect GitHub in settings.")
    elif response.status_code == 403:
        error_detail = response.json().get('message', 'Permission denied') if response.text else 'Permission denied'
        raise Exception(f"GitHub permission denied: {error_detail}. Check your GitHub token scopes.")
    else:
        error_detail = response.json().get('message', response.text) if response.text else 'Unknown error'
        logger.error(f"GitHub API error: HTTP {response.status_code} - {error_detail}")
        raise Exception(f"Failed to create GitHub repository: {error_detail}")


def ensure_branch_exists(token: str, owner: str, repo_name: str, branch_name: str, base_branch: str = 'main') -> bool:
    """
    Ensure a branch exists in the GitHub repo. Create if it doesn't exist.

    If creating a feature branch, ensures lfg-agent branch exists first and uses it as base.

    Returns:
        True if branch exists or was created, False otherwise

    Raises:
        Exception with detailed error message if branch cannot be verified or created
    """
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    # Check if branch exists
    try:
        response = requests.get(
            f'https://api.github.com/repos/{owner}/{repo_name}/branches/{branch_name}',
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            logger.info(f"Branch {branch_name} already exists in {owner}/{repo_name}")
            return True

        # If this is a feature branch, ensure lfg-agent exists first
        if branch_name.startswith('feature/'):
            logger.info(f"Feature branch detected, ensuring lfg-agent branch exists...")
            # Recursively ensure lfg-agent exists (from main)
            ensure_branch_exists(token, owner, repo_name, 'lfg-agent', 'main')
            # Now create feature branch from lfg-agent
            base_branch = 'lfg-agent'

        # Get base branch SHA
        logger.info(f"Branch {branch_name} doesn't exist, creating from {base_branch}...")
        base_response = requests.get(
            f'https://api.github.com/repos/{owner}/{repo_name}/git/refs/heads/{base_branch}',
            headers=headers,
            timeout=10
        )

        if base_response.status_code != 200:
            error_detail = base_response.json().get('message', base_response.text) if base_response.text else 'Unknown error'
            logger.error(f"Failed to get base branch {base_branch}: HTTP {base_response.status_code} - {error_detail}")
            raise Exception(f"Base branch '{base_branch}' not found in {owner}/{repo_name}. Error: {error_detail}")

        base_sha = base_response.json()['object']['sha']
        logger.info(f"Base branch SHA: {base_sha[:8]}...")

        # Create new branch
        data = {
            'ref': f'refs/heads/{branch_name}',
            'sha': base_sha
        }

        create_response = requests.post(
            f'https://api.github.com/repos/{owner}/{repo_name}/git/refs',
            headers=headers,
            json=data,
            timeout=10
        )

        if create_response.status_code == 201:
            logger.info(f"Successfully created branch {branch_name} from {base_branch}")
            return True
        else:
            error_detail = create_response.json().get('message', create_response.text) if create_response.text else 'Unknown error'
            logger.error(f"Failed to create branch {branch_name}: HTTP {create_response.status_code} - {error_detail}")
            raise Exception(f"Failed to create branch '{branch_name}': {error_detail}")

    except requests.exceptions.Timeout:
        error_msg = f"GitHub API timeout while creating branch {branch_name}"
        logger.error(error_msg)
        raise Exception(error_msg)
    except requests.exceptions.RequestException as e:
        error_msg = f"GitHub API request failed for branch {branch_name}: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)


def get_github_user_info(token: str) -> Dict[str, str]:
    """Get GitHub user's name and email from their profile."""
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    try:
        response = requests.get('https://api.github.com/user', headers=headers, timeout=10)
        if response.status_code == 200:
            user_data = response.json()
            name = user_data.get('name') or user_data.get('login', 'LFG Agent')
            email = user_data.get('email') or f"{user_data.get('login')}@users.noreply.github.com"
            return {'name': name, 'email': email}
    except:
        pass

    # Fallback to default
    return {'name': 'LFG Agent', 'email': 'agent@lfg.ai'}


def push_template_and_create_branch(workspace_id: str, owner: str, repo_name: str, branch_name: str, token: str, stack: str = 'nextjs', project=None) -> Dict[str, Any]:
    """
    Initialize an empty repository and create the feature branch.

    The AI will generate the full project structure based on requirements.
    This function only creates minimal files (.gitignore + README.md).

    Workflow:
    1. Create empty project directory
    2. Create stack-specific .gitignore and README.md
    3. Initialize git repo
    4. Push to GitHub main branch
    5. Create and push feature branch

    Args:
        workspace_id: Magpie workspace ID
        owner: GitHub repo owner
        repo_name: GitHub repo name
        branch_name: Feature branch name to create
        token: GitHub token
        stack: Technology stack (determines project directory and .gitignore content)
        project: Optional Project instance for triggering codebase indexing

    Returns:
        Dict with status and any error messages
    """
    from factory.ai_functions import get_magpie_client, _run_magpie_ssh
    import shlex

    # Get stack configuration
    stack_config = get_stack_config(stack)
    project_dir = stack_config['project_dir']
    stack_name = stack_config['name']

    client = get_magpie_client()
    escaped_branch = shlex.quote(branch_name)

    # Get GitHub user info for proper commit attribution
    user_info = get_github_user_info(token)
    git_name = user_info['name']
    git_email = user_info['email']

    # Generate stack-specific .gitignore content
    gitignore_content = get_gitignore_content(stack)

    # Create README content
    readme_content = f"""# {repo_name}

Project generated by LFG.

## Stack: {stack_name}

This project structure will be generated by AI based on your requirements.
"""

    commands = [
        # Create empty project directory
        f"mkdir -p /workspace/{project_dir}",
        # Create .gitignore file with stack-specific content
        f"cat > /workspace/{project_dir}/.gitignore << 'GITIGNORE_EOF'\n{gitignore_content}\nGITIGNORE_EOF",
        # Create README.md
        f"cat > /workspace/{project_dir}/README.md << 'README_EOF'\n{readme_content}\nREADME_EOF",
        # Initialize new git repo
        f"cd /workspace/{project_dir} && git init -b main",
        # Configure git user with actual GitHub account info
        f'cd /workspace/{project_dir} && git config user.email "{git_email}"',
        f'cd /workspace/{project_dir} && git config user.name "{git_name}"',
        # Add all files
        f"cd /workspace/{project_dir} && git add -A",
        # Create initial commit
        f'cd /workspace/{project_dir} && git commit -m "Initial commit: {stack_name} project initialized by LFG"',
        # Add remote origin (allow to fail if remote already exists)
        f"cd /workspace/{project_dir} && (git remote add origin https://{token}@github.com/{owner}/{repo_name}.git || git remote set-url origin https://{token}@github.com/{owner}/{repo_name}.git)",
        # Push main branch to GitHub
        f"cd /workspace/{project_dir} && git push -u origin main",
        # Create lfg-agent branch from main
        f"cd /workspace/{project_dir} && git checkout -b lfg-agent",
        # Push lfg-agent branch to GitHub
        f"cd /workspace/{project_dir} && git push -u origin lfg-agent",
        # Create and checkout feature branch from lfg-agent
        f"cd /workspace/{project_dir} && git checkout -b {escaped_branch}",
        # Push feature branch to GitHub
        f"cd /workspace/{project_dir} && git push -u origin {escaped_branch}",
        # Verify current branch
        f"cd /workspace/{project_dir} && git branch --show-current"
    ]

    try:
        current_branch = None
        for i, cmd in enumerate(commands):
            result = _run_magpie_ssh(client, workspace_id, cmd, timeout=120, with_node_env=False)
            logger.info(f"[Repo Init {i+1}/{len(commands)}] {cmd[:100]}...")

            stdout = result.get('stdout', '').strip()
            stderr = result.get('stderr', '').strip()
            exit_code = result.get('exit_code', 0)

            if stdout:
                logger.info(f"  stdout: {stdout}")
            if stderr and exit_code != 0:
                logger.warning(f"  stderr: {stderr}")

            # Capture the current branch from the last line of stdout
            if 'git branch --show-current' in cmd and stdout:
                current_branch = stdout.strip().split('\n')[-1]
                logger.info(f"  ✓ Current branch: {current_branch}")

            if exit_code != 0:
                error_msg = stderr or stdout or f"Command failed with exit code {exit_code}"
                logger.error(f"  ✗ Git command failed: {error_msg}")
                return {'status': 'error', 'message': f'Repository initialization failed: {error_msg}'}

        if current_branch != branch_name:
            logger.warning(f"Branch mismatch: expected {branch_name}, got {current_branch}")
            return {'status': 'error', 'message': f'Failed to checkout branch {branch_name}, currently on {current_branch}'}

        logger.info(f"✓ Repository initialized and branch '{current_branch}' created successfully")

        # Trigger codebase indexing if project is provided
        if project:
            try:
                from codebase_index.models import IndexedRepository
                from codebase_index.tasks import start_repository_indexing

                indexed_repo = IndexedRepository.objects.filter(
                    project=project,
                    github_owner=owner,
                    github_repo_name=repo_name
                ).first()

                if indexed_repo:
                    logger.info(f"Triggering codebase indexing for repository {owner}/{repo_name}")
                    start_repository_indexing(indexed_repo.id, force_full_reindex=True)
            except Exception as idx_err:
                # Don't fail the whole operation if indexing fails
                logger.warning(f"Failed to trigger codebase indexing: {idx_err}")

        return {
            'status': 'success',
            'message': f'Repository initialized and branch {branch_name} created',
            'current_branch': current_branch
        }
    except Exception as e:
        logger.error(f"Failed to initialize repository: {str(e)}", exc_info=True)
        return {'status': 'error', 'message': str(e)}


def setup_git_in_workspace(workspace_id: str, owner: str, repo_name: str, branch_name: str, token: str, stack: str = 'nextjs') -> Dict[str, Any]:
    """
    Setup git repository in workspace and checkout the feature branch.

    Smart workflow:
    - If repo exists locally: fetch latest changes and switch to branch
    - If repo doesn't exist locally: clone the repo and checkout branch
    - If remote repo is empty: initialize local repo with minimal files

    This avoids unnecessary deletions and re-cloning.

    Args:
        workspace_id: Magpie workspace ID
        owner: GitHub repo owner
        repo_name: GitHub repo name
        branch_name: Branch to checkout
        token: GitHub token
        stack: Technology stack (determines project directory)

    Returns:
        Dict with status and any error messages
    """
    from factory.ai_functions import get_magpie_client, _run_magpie_ssh
    import shlex

    # Get stack configuration
    stack_config = get_stack_config(stack)
    project_dir = stack_config['project_dir']

    client = get_magpie_client()

    # Properly escape branch name for shell (handles special characters like &, spaces, etc.)
    escaped_branch = shlex.quote(branch_name)

    # Get GitHub user info for proper commit attribution
    user_info = get_github_user_info(token)
    git_name = user_info['name']
    git_email = user_info['email']

    # Generate gitignore content for empty repo initialization
    gitignore_content = get_gitignore_content(stack)

    # Single command that handles all cases including empty repos
    setup_command = f'''
cd /workspace
if [ -d {project_dir}/.git ]; then
    echo "Git repo exists, updating..."
    cd {project_dir}
    git remote set-url origin https://{token}@github.com/{owner}/{repo_name}.git
    git fetch origin
    git checkout {escaped_branch} || git checkout -b {escaped_branch} origin/{escaped_branch} || (git fetch origin {escaped_branch} && git checkout {escaped_branch})
elif [ -d {project_dir} ]; then
    echo "Directory exists but not a git repo, removing and cloning..."
    rm -rf {project_dir}
    # Try to clone, handle empty repo case
    if git clone https://{token}@github.com/{owner}/{repo_name}.git {project_dir} 2>/dev/null; then
        cd {project_dir}
        # Check if the repo has any commits
        if git rev-parse HEAD >/dev/null 2>&1; then
            git checkout {escaped_branch} || git checkout -b {escaped_branch}
        else
            echo "Empty repo, initializing with minimal files..."
            git checkout -b main
        fi
    else
        echo "Clone failed (possibly empty repo), initializing fresh..."
        mkdir -p {project_dir}
        cd {project_dir}
        git init -b main
        git remote add origin https://{token}@github.com/{owner}/{repo_name}.git
    fi
else
    echo "Directory doesn't exist, cloning..."
    # Try to clone, handle empty repo case
    if git clone https://{token}@github.com/{owner}/{repo_name}.git {project_dir} 2>/dev/null; then
        cd {project_dir}
        # Check if the repo has any commits
        if git rev-parse HEAD >/dev/null 2>&1; then
            git checkout {escaped_branch} || git checkout -b {escaped_branch}
        else
            echo "Empty repo, initializing with minimal files..."
            git checkout -b main
        fi
    else
        echo "Clone failed (possibly empty repo), initializing fresh..."
        mkdir -p {project_dir}
        cd {project_dir}
        git init -b main
        git remote add origin https://{token}@github.com/{owner}/{repo_name}.git
    fi
fi
git config user.email "{git_email}"
git config user.name "{git_name}"
git branch --show-current
'''

    commands = [setup_command]

    try:
        current_branch = None
        for i, cmd in enumerate(commands):
            result = _run_magpie_ssh(client, workspace_id, cmd, timeout=120, with_node_env=False)
            logger.info(f"[Git Setup {i+1}/{len(commands)}] {cmd}")

            stdout = result.get('stdout', '').strip()
            stderr = result.get('stderr', '').strip()
            exit_code = result.get('exit_code', 0)

            # Log output for debugging
            if stdout:
                logger.info(f"  stdout: {stdout}")
            if stderr and exit_code != 0:
                logger.warning(f"  stderr: {stderr}")

            # Capture the current branch from the last line of stdout
            # (The script outputs echo messages, so we need only the last line)
            if 'git branch --show-current' in cmd and stdout:
                current_branch = stdout.strip().split('\n')[-1]
                logger.info(f"  ✓ Current branch: {current_branch}")

            # Check for errors (but allow some commands to fail gracefully)
            is_allowed_failure = ('rm -rf' in cmd)

            if exit_code != 0 and not is_allowed_failure:
                error_msg = stderr or stdout or f"Command failed with exit code {exit_code}"
                logger.error(f"  ✗ Git command failed: {error_msg}")
                return {'status': 'error', 'message': f'Git setup failed: {error_msg}'}

        if current_branch != branch_name:
            logger.warning(f"Branch mismatch: expected {branch_name}, got {current_branch}")
            return {'status': 'error', 'message': f'Failed to checkout branch {branch_name}, currently on {current_branch}'}

        logger.info(f"✓ Git setup complete: workspace is on branch '{current_branch}'")
        return {'status': 'success', 'message': f'Git setup complete on branch {branch_name}', 'current_branch': current_branch}
    except Exception as e:
        logger.error(f"Failed to setup git in workspace: {str(e)}", exc_info=True)
        return {'status': 'error', 'message': str(e)}


def resolve_merge_conflict(workspace_id: str, feature_branch: str, ticket_id: int, project_id: str, conversation_id: int, stack: str = 'nextjs') -> Dict[str, Any]:
    """
    Resolve merge conflicts by having AI fix them in the workspace.

    Args:
        workspace_id: The Magpie workspace ID
        feature_branch: The feature branch name (e.g., feature/xxx)
        ticket_id: The ticket ID
        project_id: The project UUID
        conversation_id: The conversation ID
        stack: Technology stack (determines project directory)

    Returns:
        Dict with resolution status
    """
    from factory.ai_functions import get_magpie_client, _run_magpie_ssh
    from factory.ai_providers import get_ai_response
    from factory.ai_tools import tools_builder

    # Get stack configuration
    stack_config = get_stack_config(stack)
    project_dir = stack_config['project_dir']

    client = get_magpie_client()

    logger.info(f"[CONFLICT RESOLUTION] Starting automatic conflict resolution for {feature_branch}")

    # Step 1: Checkout lfg-agent and try to merge locally
    merge_command = f'''
cd /workspace/{project_dir}
git fetch origin
git checkout lfg-agent
git pull origin lfg-agent
git merge {feature_branch} || echo "CONFLICT_DETECTED"
'''

    result = _run_magpie_ssh(client, workspace_id, merge_command, timeout=60, with_node_env=False)
    stdout = result.get('stdout', '')

    if 'CONFLICT' in stdout or 'conflict' in stdout.lower():
        logger.info(f"[CONFLICT RESOLUTION] Conflicts detected, getting conflict details...")

        # Get list of conflicted files
        status_cmd = f"cd /workspace/{project_dir} && git status --short | grep '^UU\\|^AA\\|^DD'"
        status_result = _run_magpie_ssh(client, workspace_id, status_cmd, timeout=30, with_node_env=False)
        conflicted_files_raw = status_result.get('stdout', '').strip()
        conflicted_files = [f.strip() for f in conflicted_files_raw.split('\n') if f.strip()]

        logger.info(f"[CONFLICT RESOLUTION] Conflicted files: {conflicted_files}")

        # if not conflicted_files:
        #     logger.warning(f"[CONFLICT RESOLUTION] No conflicted files found, aborting merge")
        #     abort_cmd = f"cd /workspace/{project_dir} && git merge --abort"
        #     _run_magpie_ssh(client, workspace_id, abort_cmd, timeout=30, with_node_env=False)
        #     return {
        #         'status': 'conflict',
        #         'message': 'Merge conflict detected but no conflicted files found',
        #         'conflicted_files': []
        #     }

        # Get conflict diff details
        diff_cmd = f"cd /workspace/{project_dir} && git diff --name-status"
        diff_result = _run_magpie_ssh(client, workspace_id, diff_cmd, timeout=30, with_node_env=False)
        conflict_diff = diff_result.get('stdout', '').strip()

        logger.info(f"[CONFLICT RESOLUTION] Calling AI to resolve conflicts...")

        # Build AI prompt for conflict resolution
        implementation_prompt = f"""
            You are resolving merge conflicts between two branches:
            - Base branch: lfg-agent
            - Feature branch: {feature_branch}


            CONFLICT DETAILS:
            {conflict_diff}

            PROJECT PATH: {project_dir}

            Your task: Fix all merge conflicts using SSH commands.

            Steps:
            1. Check the conflicted files to understand the conflicts
            2. Resolve conflicts by editing files (choose appropriate resolution strategy)
            3. After resolving, stage the resolved files: git add <files>
            4. Complete the merge: git commit -m "Merge {feature_branch} into lfg-agent"
            5. Verify no conflicts remain: git status

            ✅ Success case: "IMPLEMENTATION_STATUS: COMPLETE - Resolved all conflicts"
            ❌ Failure case: "IMPLEMENTATION_STATUS: FAILED - [reason]"
            """

        system_prompt = """
            You are an expert developer resolving merge conflicts.

            IMPORTANT:
            1. Use ssh_command tool to inspect and edit conflicted files
            2. Understand BOTH sides of the conflict before resolving
            3. Choose the correct resolution strategy (accept theirs, ours, or manual merge)
            4. After resolving, stage files with: git add <file>
            5. Complete merge with: git commit -m "Merge conflicts resolved"
            6. DO NOT create new features - only resolve conflicts
            7. Keep all valid changes from both branches when possible

            🎯 COMPLETION CRITERIA:
            - All conflicted files are resolved
            - Changes are staged and committed
            - git status shows no conflicts

            End with: "IMPLEMENTATION_STATUS: COMPLETE - [summary]" or "IMPLEMENTATION_STATUS: FAILED - [reason]"
            """

        # Set context for workspace
        current_workspace_id.set(workspace_id)

        # Call AI to resolve conflicts
        ai_start = time.time()
        try:
            ai_response = async_to_sync(get_ai_response)(
                user_message=implementation_prompt,
                system_prompt=system_prompt,
                project_id=project_id,
                conversation_id=conversation_id,
                stream=False,
                tools=tools_builder
            )
            ai_duration = time.time() - ai_start
            logger.info(f"[CONFLICT RESOLUTION] AI call completed in {ai_duration:.1f}s")

            content = ai_response.get('content', '') if ai_response else ''

            # Check if AI successfully resolved conflicts
            if 'IMPLEMENTATION_STATUS: COMPLETE' in content:
                logger.info(f"[CONFLICT RESOLUTION] ✓ AI reported successful resolution")

                # Verify conflicts are actually resolved
                verify_cmd = f"cd /workspace/{project_dir} && git status --short | grep '^UU\\|^AA\\|^DD'"
                verify_result = _run_magpie_ssh(client, workspace_id, verify_cmd, timeout=30, with_node_env=False)
                remaining_conflicts = verify_result.get('stdout', '').strip()

                if remaining_conflicts:
                    logger.error(f"[CONFLICT RESOLUTION] ✗ Conflicts still remain: {remaining_conflicts}")
                    # Abort the merge
                    abort_cmd = f"cd /workspace/{project_dir} && git merge --abort"
                    _run_magpie_ssh(client, workspace_id, abort_cmd, timeout=30, with_node_env=False)
                    return {
                        'status': 'conflict',
                        'message': f'AI attempted resolution but conflicts remain in: {remaining_conflicts}',
                        'conflicted_files': [f.strip() for f in remaining_conflicts.split('\n') if f.strip()]
                    }

                # Push the merge to GitHub
                push_cmd = f"cd /workspace/{project_dir} && git push origin lfg-agent"
                push_result = _run_magpie_ssh(client, workspace_id, push_cmd, timeout=60, with_node_env=False)

                if push_result.get('exit_code') == 0:
                    logger.info(f"[CONFLICT RESOLUTION] ✓ Successfully resolved and pushed merge")
                    return {'status': 'success', 'message': 'Conflicts resolved by AI and merged'}
                else:
                    push_error = push_result.get('stderr', push_result.get('stdout', 'Unknown error'))
                    logger.error(f"[CONFLICT RESOLUTION] ✗ Failed to push: {push_error}")
                    return {'status': 'error', 'message': f'Conflicts resolved but push failed: {push_error}'}
            else:
                # AI failed to resolve conflicts
                logger.error(f"[CONFLICT RESOLUTION] ✗ AI failed to resolve conflicts")
                abort_cmd = f"cd /workspace/{project_dir} && git merge --abort"
                _run_magpie_ssh(client, workspace_id, abort_cmd, timeout=30, with_node_env=False)
                return {
                    'status': 'conflict',
                    'message': 'AI could not resolve conflicts automatically',
                    'conflicted_files': conflicted_files
                }

        except Exception as ai_error:
            logger.error(f"[CONFLICT RESOLUTION] ✗ AI error: {str(ai_error)}", exc_info=True)
            # Abort the merge on error
            abort_cmd = f"cd /workspace/{project_dir} && git merge --abort"
            _run_magpie_ssh(client, workspace_id, abort_cmd, timeout=30, with_node_env=False)
            return {
                'status': 'error',
                'message': f'AI error during conflict resolution: {str(ai_error)}',
                'conflicted_files': conflicted_files
            }

    # No conflicts - push the merge
    push_cmd = f"cd /workspace/{project_dir} && git push origin lfg-agent"
    push_result = _run_magpie_ssh(client, workspace_id, push_cmd, timeout=60, with_node_env=False)

    if push_result.get('exit_code') == 0:
        logger.info(f"[CONFLICT RESOLUTION] ✓ Successfully merged {feature_branch} into lfg-agent (no conflicts)")
        return {'status': 'success', 'message': 'No conflicts - merged successfully'}
    else:
        return {'status': 'error', 'message': 'Failed to push merge'}


def merge_feature_to_lfg_agent(token: str, owner: str, repo_name: str, feature_branch: str) -> Dict[str, Any]:
    """
    Merge the feature branch into lfg-agent branch using GitHub API.

    Returns:
        Dict with merge status and details
    """
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    # Merge feature branch into lfg-agent
    data = {
        'base': 'lfg-agent',
        'head': feature_branch,
        'commit_message': f'Merge {feature_branch} into lfg-agent'
    }

    try:
        response = requests.post(
            f'https://api.github.com/repos/{owner}/{repo_name}/merges',
            headers=headers,
            json=data,
            timeout=10
        )

        if response.status_code == 201:
            response_data = response.json()
            merge_sha = response_data.get('sha')
            logger.info(f"Successfully merged {feature_branch} into lfg-agent (merge SHA: {merge_sha})")
            return {
                'status': 'success',
                'message': f'Successfully merged {feature_branch} into lfg-agent',
                'merge_commit_sha': merge_sha,
                'html_url': response_data.get('html_url'),
            }
        elif response.status_code == 204:
            # 204 means branches are already merged/identical
            logger.info(f"Branch {feature_branch} already merged into lfg-agent (no changes)")
            return {
                'status': 'success',
                'message': 'Already up to date - no merge needed',
                'merge_commit_sha': None,
            }
        elif response.status_code == 409:
            logger.warning(f"Merge conflict detected for {feature_branch} → lfg-agent")
            return {
                'status': 'conflict',
                'message': 'Merge conflict detected. Manual resolution required.'
            }
        else:
            error_detail = response.json().get('message', response.text) if response.text else 'Unknown error'
            logger.error(f"Merge failed: {response.status_code} - {error_detail}")
            return {
                'status': 'error',
                'message': f'Merge failed: {error_detail}'
            }
    except requests.exceptions.Timeout:
        return {'status': 'error', 'message': 'GitHub API timeout during merge'}
    except Exception as e:
        logger.error(f"Exception during merge: {str(e)}", exc_info=True)
        return {'status': 'error', 'message': str(e)}


def get_commit_details(token: str, owner: str, repo_name: str, commit_sha: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific commit using GitHub API.

    Args:
        token: GitHub access token
        owner: Repository owner
        repo_name: Repository name
        commit_sha: The commit SHA to get details for

    Returns:
        Dict with commit details including files changed and stats
    """
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    try:
        # Get commit details
        response = requests.get(
            f'https://api.github.com/repos/{owner}/{repo_name}/commits/{commit_sha}',
            headers=headers,
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()

            # Extract file changes with stats
            files = []
            for file in data.get('files', []):
                files.append({
                    'filename': file.get('filename'),
                    'status': file.get('status'),  # added, removed, modified, renamed
                    'additions': file.get('additions', 0),
                    'deletions': file.get('deletions', 0),
                    'changes': file.get('changes', 0),
                })

            commit_info = data.get('commit', {})
            author_info = commit_info.get('author', {})

            return {
                'success': True,
                'sha': data.get('sha'),
                'message': commit_info.get('message', ''),
                'author': {
                    'name': author_info.get('name'),
                    'email': author_info.get('email'),
                    'date': author_info.get('date'),
                },
                'stats': {
                    'additions': data.get('stats', {}).get('additions', 0),
                    'deletions': data.get('stats', {}).get('deletions', 0),
                    'total': data.get('stats', {}).get('total', 0),
                },
                'files': files,
                'html_url': data.get('html_url'),
                'parents': [p.get('sha') for p in data.get('parents', [])],
            }
        elif response.status_code == 404:
            return {
                'success': False,
                'error': 'Commit not found'
            }
        else:
            error_detail = response.json().get('message', response.text) if response.text else 'Unknown error'
            return {
                'success': False,
                'error': f'GitHub API error: {error_detail}'
            }

    except requests.exceptions.Timeout:
        return {'success': False, 'error': 'GitHub API timeout'}
    except Exception as e:
        logger.error(f"Error getting commit details: {str(e)}", exc_info=True)
        return {'success': False, 'error': str(e)}


def revert_merge_on_branch(token: str, owner: str, repo_name: str, branch: str,
                           merge_commit_sha: str, revert_message: str) -> Dict[str, Any]:
    """
    Revert a merge commit on a branch using GitHub API.

    This uses the GitHub API to create a revert commit. The process:
    1. Get the merge commit to find its parent (the state before merge)
    2. Create a new commit that reverses all changes from the merge
    3. Update the branch ref to point to the new revert commit

    Args:
        token: GitHub access token
        owner: Repository owner
        repo_name: Repository name
        branch: Branch to revert on (e.g., 'lfg-agent')
        merge_commit_sha: SHA of the merge commit to revert
        revert_message: Commit message for the revert

    Returns:
        Dict with revert result and new commit SHA
    """
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    try:
        # Step 1: Get the merge commit details
        commit_response = requests.get(
            f'https://api.github.com/repos/{owner}/{repo_name}/commits/{merge_commit_sha}',
            headers=headers,
            timeout=15
        )

        if commit_response.status_code != 200:
            return {
                'status': 'error',
                'message': f'Failed to get merge commit: {commit_response.status_code}'
            }

        commit_data = commit_response.json()
        parents = commit_data.get('parents', [])

        # For a merge commit, we need the first parent (the branch we merged into)
        if len(parents) < 1:
            return {
                'status': 'error',
                'message': 'Commit has no parents - cannot revert'
            }

        # Step 2: Get current branch ref
        ref_response = requests.get(
            f'https://api.github.com/repos/{owner}/{repo_name}/git/refs/heads/{branch}',
            headers=headers,
            timeout=10
        )

        if ref_response.status_code != 200:
            return {
                'status': 'error',
                'message': f'Failed to get branch ref: {ref_response.status_code}'
            }

        current_sha = ref_response.json().get('object', {}).get('sha')

        # Step 3: Get the tree of the first parent (state before merge)
        parent_sha = parents[0].get('sha')
        parent_response = requests.get(
            f'https://api.github.com/repos/{owner}/{repo_name}/commits/{parent_sha}',
            headers=headers,
            timeout=10
        )

        if parent_response.status_code != 200:
            return {
                'status': 'error',
                'message': f'Failed to get parent commit: {parent_response.status_code}'
            }

        parent_tree_sha = parent_response.json().get('commit', {}).get('tree', {}).get('sha')

        # Step 4: Create a new commit using the parent's tree but pointing to current HEAD
        new_commit_data = {
            'message': revert_message,
            'tree': parent_tree_sha,
            'parents': [current_sha]
        }

        create_commit_response = requests.post(
            f'https://api.github.com/repos/{owner}/{repo_name}/git/commits',
            headers=headers,
            json=new_commit_data,
            timeout=15
        )

        if create_commit_response.status_code not in [200, 201]:
            error_detail = create_commit_response.json().get('message', create_commit_response.text)
            return {
                'status': 'error',
                'message': f'Failed to create revert commit: {error_detail}'
            }

        new_commit_sha = create_commit_response.json().get('sha')

        # Step 5: Update branch ref to point to new commit
        update_ref_response = requests.patch(
            f'https://api.github.com/repos/{owner}/{repo_name}/git/refs/heads/{branch}',
            headers=headers,
            json={'sha': new_commit_sha, 'force': False},
            timeout=10
        )

        if update_ref_response.status_code != 200:
            error_detail = update_ref_response.json().get('message', update_ref_response.text)
            return {
                'status': 'error',
                'message': f'Failed to update branch ref: {error_detail}'
            }

        logger.info(f"Successfully reverted merge {merge_commit_sha} on {branch} with commit {new_commit_sha}")

        return {
            'status': 'success',
            'message': 'Successfully reverted merge commit',
            'revert_commit_sha': new_commit_sha,
            'reverted_merge_sha': merge_commit_sha,
        }

    except requests.exceptions.Timeout:
        return {'status': 'error', 'message': 'GitHub API timeout during revert'}
    except Exception as e:
        logger.error(f"Exception during revert: {str(e)}", exc_info=True)
        return {'status': 'error', 'message': str(e)}


def commit_and_push_changes(workspace_id: str, branch_name: str, commit_message: str, ticket_id: int, stack: str = 'nextjs', github_token: str = None, github_owner: str = None, github_repo: str = None) -> Dict[str, Any]:
    """
    Commit all changes in workspace and push to GitHub.

    Args:
        workspace_id: Magpie workspace ID
        branch_name: Branch to commit to
        commit_message: Commit message
        ticket_id: Ticket ID for reference
        stack: Technology stack (determines project directory)
        github_token: GitHub token for authentication (optional but recommended)
        github_owner: GitHub repo owner (required if github_token provided)
        github_repo: GitHub repo name (required if github_token provided)

    Returns:
        Dict with status and commit details
    """
    from factory.ai_functions import get_magpie_client, _run_magpie_ssh
    import shlex

    # Get stack configuration
    stack_config = get_stack_config(stack)
    project_dir = stack_config['project_dir']

    client = get_magpie_client()

    # Escape commit message for shell
    escaped_message = commit_message.replace('"', '\\"').replace('$', '\\$').replace('`', '\\`').replace('\n', ' ')

    # Properly escape branch name for shell (handles special characters like &, spaces, etc.)
    escaped_branch = shlex.quote(branch_name)

    # Build commands list
    # IMPORTANT: Order matters! We must commit local changes BEFORE pulling,
    # because git pull fails when there are uncommitted changes.
    commands = [
        # Fix git "dubious ownership" error (happens when directory ownership changed for claudeuser)
        f"git config --global --add safe.directory /workspace/{project_dir}",
        # Fetch latest from remote to ensure we have remote branch refs
        f"cd /workspace/{project_dir} && git fetch origin 2>/dev/null || true",
        # Checkout feature branch with proper fallback order:
        # 1. Try existing local branch
        # 2. Try creating from remote tracking branch (origin/feature-branch)
        # 3. Create new branch from current position (only if remote doesn't exist)
        f"cd /workspace/{project_dir} && (git checkout {escaped_branch} 2>/dev/null || git checkout -b {escaped_branch} origin/{escaped_branch} 2>/dev/null || git checkout -b {escaped_branch}) && echo 'On branch:' && git branch --show-current",
        # Check git status
        f"cd /workspace/{project_dir} && git status --short",
        # Add all changes
        f"cd /workspace/{project_dir} && git add -A",
        # Commit local changes FIRST (before pulling - git pull fails with uncommitted changes)
        f'cd /workspace/{project_dir} && git commit -m "{escaped_message}" || echo "No changes to commit"',
    ]

    # If we have GitHub token, update remote URL to include auth before pulling/pushing
    if github_token and github_owner and github_repo:
        commands.append(
            f"cd /workspace/{project_dir} && git remote set-url origin https://{github_token}@github.com/{github_owner}/{github_repo}.git"
        )

    # Pull with rebase to integrate remote changes (now safe since local changes are committed)
    # This rebases our commit on top of any remote commits
    commands.append(f"cd /workspace/{project_dir} && git pull --rebase origin {escaped_branch} 2>/dev/null || true")

    # Push feature branch to remote
    commands.append(f"cd /workspace/{project_dir} && git push -u origin {escaped_branch}")

    try:
        commit_sha = None
        current_branch = None
        changes_detected = False

        for i, cmd in enumerate(commands):
            result = _run_magpie_ssh(client, workspace_id, cmd, timeout=120, with_node_env=False)
            logger.info(f"[Git Commit {i+1}/{len(commands)}] {cmd}")

            stdout = result.get('stdout', '').strip()
            stderr = result.get('stderr', '').strip()
            exit_code = result.get('exit_code', 0)

            # Log output
            if stdout:
                logger.info(f"  stdout: {stdout}")
            if stderr and exit_code != 0:
                logger.warning(f"  stderr: {stderr}")

            # Capture current branch (from checkout command output)
            if 'git branch --show-current' in cmd and stdout:
                # Output format: "On branch:\n<branch-name>" or just "<branch-name>"
                lines = stdout.strip().split('\n')
                current_branch = lines[-1].strip()  # Last line is the branch name
                logger.info(f"  Current branch: {current_branch}")

            # Check if there are changes
            if 'git status --short' in cmd and stdout:
                changes_detected = bool(stdout)
                logger.info(f"  Changes detected: {changes_detected}")
                if changes_detected:
                    logger.info(f"  Modified files:\n{stdout}")

            # Extract commit SHA
            # Git commit output format: "[branch_name SHA] message"
            # Example: "[feature/google-login b6bd18a] chore: User requested changes"
            if 'git commit' in cmd and exit_code == 0:
                # Try to extract commit SHA from output
                if '[' in stdout and ']' in stdout:
                    try:
                        # Extract content between [ and ]
                        bracket_content = stdout.split('[')[1].split(']')[0]
                        parts = bracket_content.split()
                        # SHA is the LAST part (after branch name which may contain slashes)
                        # Format is: "branch/name SHA" so SHA is always last
                        if len(parts) >= 2:
                            commit_sha = parts[-1]  # Last element is the SHA
                        else:
                            commit_sha = parts[0] if parts else None
                        logger.info(f"  Commit SHA: {commit_sha}")
                    except Exception as e:
                        logger.warning(f"  Could not parse commit SHA: {e}")

            # Check for errors
            if exit_code != 0:
                # Allow "nothing to commit" and git pull failures
                if 'nothing to commit' in stderr or 'nothing to commit' in stdout:
                    logger.info(f"  No changes to commit")
                    continue
                elif 'No changes to commit' in stdout:
                    logger.info(f"  No changes to commit")
                    continue
                else:
                    logger.error(f"  ✗ Git command failed: {stderr or stdout}")
                    return {'status': 'error', 'message': stderr or stdout or 'Git command failed'}

        if current_branch != branch_name:
            logger.warning(f"Branch mismatch during commit: expected {branch_name}, on {current_branch}")

        return {
            'status': 'success',
            'message': f'Changes committed and pushed to {branch_name}',
            'commit_sha': commit_sha,
            'changes_detected': changes_detected
        }
    except Exception as e:
        logger.error(f"Failed to commit and push changes: {str(e)}", exc_info=True)
        return {'status': 'error', 'message': str(e)}


def ensure_workspace_available(ticket_id: int) -> Dict[str, Any]:
    """
    Ensure a workspace is available for the given ticket. Creates one if needed.

    This is used for lazy initialization - called by tools when they need workspace
    but one doesn't exist yet.

    Args:
        ticket_id: The ID of the ProjectTicket

    Returns:
        Dict with:
            - status: 'success' or 'error'
            - workspace_id: The workspace identifier (if success)
            - error: Error message (if error)
    """
    from development.models import MagpieWorkspace

    logger.info(f"[ENSURE_WORKSPACE] Checking workspace for ticket #{ticket_id}")

    try:
        ticket = ProjectTicket.objects.get(id=ticket_id)
        project = ticket.project

        # Check if workspace already exists
        workspace = MagpieWorkspace.objects.filter(
            project=project,
            status='ready'
        ).order_by('-updated_at').first()

        if workspace:
            workspace_id = workspace.workspace_id
            current_workspace_id.set(workspace_id)
            logger.info(f"[ENSURE_WORKSPACE] Found existing workspace: {workspace_id}")
            return {
                'status': 'success',
                'workspace_id': workspace_id,
                'workspace': workspace,
                'created': False
            }

        # No workspace - create one
        logger.info(f"[ENSURE_WORKSPACE] No workspace found, creating one...")
        setup_result = setup_ticket_workspace(
            ticket=ticket,
            project=project,
            conversation_id=None,
            create_branch=False  # Use existing branch from ticket
        )

        if setup_result['status'] == 'success':
            logger.info(f"[ENSURE_WORKSPACE] Workspace created: {setup_result['workspace_id']}")
            return {
                'status': 'success',
                'workspace_id': setup_result['workspace_id'],
                'workspace': setup_result['workspace'],
                'created': True
            }
        else:
            logger.error(f"[ENSURE_WORKSPACE] Failed to create workspace: {setup_result.get('error')}")
            return {
                'status': 'error',
                'error': setup_result.get('error', 'Failed to create workspace')
            }

    except ProjectTicket.DoesNotExist:
        return {
            'status': 'error',
            'error': f'Ticket #{ticket_id} not found'
        }
    except Exception as e:
        logger.error(f"[ENSURE_WORKSPACE] Error: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'error': str(e)
        }


def setup_ticket_workspace(
    ticket: 'ProjectTicket',
    project: 'Project',
    conversation_id: int = None,
    create_branch: bool = True
) -> Dict[str, Any]:
    """
    Setup workspace, GitHub repo, and Git configuration for a ticket.

    This function handles:
    1. GitHub repository setup (get or create)
    2. Feature branch creation
    3. Magpie workspace provisioning
    4. Dev sandbox initialization
    5. Git configuration in workspace

    Args:
        ticket: The ProjectTicket instance
        project: The Project instance
        conversation_id: Optional conversation ID for notifications
        create_branch: Whether to create a new feature branch (default: True)

    Returns:
        Dict with:
            - status: 'success' or 'error'
            - workspace_id: The workspace identifier
            - workspace: The MagpieWorkspace instance
            - github_owner: GitHub repository owner
            - github_repo: GitHub repository name
            - feature_branch: Feature branch name
            - stack: Technology stack
            - project_dir: Project directory name
            - git_setup_error: Any git setup errors (for AI to fix)
            - error: Error message if status is 'error'
    """
    from development.models import MagpieWorkspace

    # Get stack configuration
    stack = getattr(project, 'stack', 'nextjs')
    stack_config = get_stack_config(stack)

    logger.info(f"\n{'='*60}\n[WORKSPACE SETUP] Starting for ticket #{ticket.id} (stack: {stack})\n{'='*60}")

    result = {
        'status': 'success',
        'workspace_id': None,
        'workspace': None,
        'github_owner': None,
        'github_repo': None,
        'feature_branch': None,
        'git_setup_error': None,
        'repo_needs_template': False,
        'stack': stack,
        'project_dir': stack_config['project_dir'],
    }

    # 1. GITHUB REPOSITORY SETUP
    logger.info(f"[WORKSPACE SETUP] Step 1: Setting up GitHub repository...")

    github_token = get_github_token(project.owner)
    if not github_token:
        error_msg = "GitHub not connected. Please connect GitHub in settings."
        logger.error(f"[WORKSPACE SETUP] ✗ {error_msg}")
        return {
            **result,
            'status': 'error',
            'error': error_msg,
            'requires_github_setup': True
        }

    try:
        # Get or create GitHub repo
        repo_info = get_or_create_github_repo(project, project.owner, stack=stack)
        result['github_owner'] = repo_info['owner']
        result['github_repo'] = repo_info['repo_name']
        result['repo_needs_template'] = repo_info.get('needs_template', False)

        if repo_info['created']:
            logger.info(f"[WORKSPACE SETUP] ✓ Created GitHub repo: {result['github_owner']}/{result['github_repo']}")
        else:
            logger.info(f"[WORKSPACE SETUP] ✓ Using existing repo: {result['github_owner']}/{result['github_repo']}")

        # Create feature branch name from ticket
        if create_branch:
            sanitized_name = ticket.name.lower().replace(' ', '-').replace('_', '-')[:30]
            result['feature_branch'] = f"feature/{sanitized_name}"

            # Save branch name to ticket
            ticket.github_branch = result['feature_branch']
            ticket.github_merge_status = 'pending'
            ticket.save(update_fields=['github_branch', 'github_merge_status'])

            logger.info(f"[WORKSPACE SETUP] ✓ Feature branch: {result['feature_branch']}")

            # Create branch on GitHub if repo already has content
            if not result['repo_needs_template']:
                branch_created = ensure_branch_exists(
                    token=github_token,
                    owner=result['github_owner'],
                    repo_name=result['github_repo'],
                    branch_name=result['feature_branch'],
                    base_branch='main'
                )
                if branch_created:
                    logger.info(f"[WORKSPACE SETUP] ✓ Branch ready on GitHub")
        else:
            # Use existing branch from ticket
            result['feature_branch'] = ticket.github_branch
            logger.info(f"[WORKSPACE SETUP] ✓ Using existing branch: {result['feature_branch']}")

    except Exception as e:
        error_msg = f"GitHub setup failed: {str(e)}"
        logger.error(f"[WORKSPACE SETUP] ✗ {error_msg}", exc_info=True)
        return {
            **result,
            'status': 'error',
            'error': error_msg,
            'github_error': str(e)
        }

    # 2. WORKSPACE PROVISIONING
    logger.info(f"[WORKSPACE SETUP] Step 2: Fetching or creating workspace...")

    workspace = async_to_sync(_fetch_workspace)(project=project, conversation_id=conversation_id)

    if not workspace:
        logger.info(f"[WORKSPACE SETUP] No existing workspace, creating new one...")
        try:
            client = get_magpie_client()
            project_name = project.provided_name or project.name
            slug = _slugify_project_name(project_name)
            workspace_name = f"{slug}-{project.id}"

            vm_handle = client.jobs.create_persistent_vm(
                name=workspace_name,
                script=MAGPIE_BOOTSTRAP_SCRIPT,
                stateful=True,
                workspace_size_gb=10,
                vcpus=2,
                memory_mb=2048,
                poll_timeout=180,
                poll_interval=5,
            )
            logger.info(f"[MAGPIE][CREATE] vm_handle: {vm_handle}")

            run_id = vm_handle.request_id
            workspace_identifier = run_id
            ipv6 = vm_handle.ip_address

            if not ipv6:
                raise Exception(f"VM provisioning timed out - no IP address received")

            workspace = MagpieWorkspace.objects.create(
                project=project,
                conversation_id=str(conversation_id) if conversation_id else None,
                job_id=run_id,
                workspace_id=workspace_identifier,
                status='ready',
                ipv6_address=ipv6,
                project_path='/workspace',
                metadata={'project_name': project_name}
            )
            logger.info(f"[MAGPIE][READY] Workspace ready: {workspace.workspace_id}, IP: {ipv6}")

        except Exception as e:
            error_msg = f"Workspace provisioning failed: {str(e)}"
            logger.error(f"[WORKSPACE SETUP] ✗ {error_msg}", exc_info=True)
            return {
                **result,
                'status': 'error',
                'error': error_msg
            }

    result['workspace'] = workspace
    result['workspace_id'] = workspace.workspace_id
    logger.info(f"[WORKSPACE SETUP] ✓ Workspace ready: {result['workspace_id']}")

    # Set workspace_id in context
    current_workspace_id.set(result['workspace_id'])

    # 3. DEV SANDBOX SETUP
    logger.info(f"[WORKSPACE SETUP] Step 3: Setting up dev sandbox...")

    workspace_metadata = workspace.metadata or {}
    if not workspace_metadata.get('sandbox_initialized'):
        try:
            sandbox_result = async_to_sync(new_dev_sandbox_tool)(
                {'workspace_id': result['workspace_id']},
                project.project_id,
                conversation_id
            )

            if sandbox_result.get('status') == 'failed':
                raise Exception(f"Dev sandbox setup failed: {sandbox_result.get('message_to_agent')}")
            logger.info(f"[WORKSPACE SETUP] ✓ Dev sandbox initialized")
        except Exception as e:
            logger.warning(f"[WORKSPACE SETUP] ⚠ Dev sandbox setup error: {str(e)}")
            # Don't fail - sandbox might already be set up
    else:
        logger.info(f"[WORKSPACE SETUP] ⊘ Dev sandbox already initialized")

    # 4. GIT CONFIGURATION IN WORKSPACE
    logger.info(f"[WORKSPACE SETUP] Step 4: Setting up Git in workspace...")

    if result['github_owner'] and result['github_repo'] and result['feature_branch']:
        if result['repo_needs_template']:
            logger.info(f"[WORKSPACE SETUP] Initializing repo and creating branch...")
            git_setup_result = push_template_and_create_branch(
                result['workspace_id'],
                result['github_owner'],
                result['github_repo'],
                result['feature_branch'],
                github_token,
                stack=stack,
                project=project
            )
        else:
            logger.info(f"[WORKSPACE SETUP] Cloning repo and checking out branch...")
            git_setup_result = setup_git_in_workspace(
                result['workspace_id'],
                result['github_owner'],
                result['github_repo'],
                result['feature_branch'],
                github_token,
                stack=stack
            )

        if git_setup_result['status'] == 'success':
            logger.info(f"[WORKSPACE SETUP] ✓ Git configured on branch {result['feature_branch']}")
            workspace.metadata = workspace.metadata or {}
            workspace.metadata['git_configured'] = True
            workspace.metadata['git_branch'] = result['feature_branch']
            # Reset workspace status to 'ready' after successful operations
            if workspace.status != 'ready':
                logger.info(f"[WORKSPACE SETUP] Resetting workspace status from '{workspace.status}' to 'ready'")
                workspace.status = 'ready'
            workspace.save(update_fields=['metadata', 'status'])
        else:
            # Git setup failed - capture error for AI to fix
            error_msg = git_setup_result.get('message', 'Unknown git setup error')
            logger.warning(f"[WORKSPACE SETUP] ⚠ Git setup issue: {error_msg}")
            result['git_setup_error'] = {
                'message': error_msg,
                'details': git_setup_result.get('details', ''),
                'branch': result['feature_branch'],
                'repo': f"{result['github_owner']}/{result['github_repo']}"
            }
    else:
        logger.info(f"[WORKSPACE SETUP] ⊘ Skipping Git setup - missing configuration")

    logger.info(f"[WORKSPACE SETUP] ✓ Setup complete for ticket #{ticket.id}")
    return result


def execute_ticket_implementation(ticket_id: int, project_id: int, conversation_id: int, max_execution_time: int = 1200) -> Dict[str, Any]:
    """
    Execute a single ticket implementation - streamlined version with timeout protection.
    Works like Claude Code CLI - fast, efficient, limited tool rounds.

    Args:
        ticket_id: The ID of the ProjectTicket ticket
        project_id: The ID of the project
        conversation_id: The ID of the conversation
        max_execution_time: Maximum execution time in seconds (default: 300s/5min)

    Returns:
        Dict with execution results and status
    """
    # Set the current ticket_id in context for tool functions to access
    current_ticket_id.set(ticket_id)
    logger.info(f"\n{'='*80}\n[TASK START] Ticket #{ticket_id} | Project #{project_id} | Conv #{conversation_id}\n{'='*80}")

    start_time = time.time()
    workspace_id = None

    try:
        logger.info(f"\n[STEP 1/6] Fetching ticket and project data...")
        # 1. GET TICKET AND PROJECT
        ticket = ProjectTicket.objects.get(id=ticket_id)
        project = Project.objects.get(id=project_id)
        logger.info(f"[STEP 1/6] ✓ Ticket: '{ticket.name}' | Project: '{project.name}'")

        logger.info(f"\n[STEP 2/6] Checking if ticket already completed...")
        # 2. CHECK IF ALREADY COMPLETED (prevent duplicate execution on retry)
        if ticket.status == 'done':
            logger.info(f"[STEP 2/6] ⊘ Ticket already completed, skipping")
            return {
                "status": "success",
                "ticket_id": ticket_id,
                "message": "Already completed",
                "skipped": True
            }

        # Check if this is a retry (ticket was previously blocked, failed, or in_progress)
        is_retry = ticket.status in ['blocked', 'failed', 'in_progress']
        previous_status = ticket.status
        if is_retry:
            logger.info(f"[STEP 2/6] ⟳ RETRY detected - previous status was '{previous_status}'")
            # Add retry note to ticket
            ticket.notes = (ticket.notes or "") + f"""
---
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] ⟳ EXECUTION RETRY
Previous status: {previous_status}
Retrying execution...
"""
            ticket.save(update_fields=['notes'])

        logger.info(f"[STEP 2/6] ✓ Ticket status: {ticket.status}, proceeding...")

        attachments = list(ticket.attachments.all())

        def _format_file_size(num_bytes: int) -> str:
            try:
                size = float(num_bytes or 0)
            except (TypeError, ValueError):
                size = 0
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if size < 1024 or unit == 'TB':
                    return f"{size:.1f} {unit}" if size >= 1024 and unit != 'B' else f"{int(size)} {unit}"
                size /= 1024
            return f"{size:.1f} TB"

        if attachments:
            attachment_lines = []
            for attachment in attachments:
                display_name = attachment.original_filename or os.path.basename(attachment.file.name)
                size_label = _format_file_size(attachment.file_size)
                uploaded_label = attachment.uploaded_at.strftime('%Y-%m-%d %H:%M')
                attachment_lines.append(f"- {display_name} ({size_label}, uploaded {uploaded_label})")
            attachments_summary = "\n".join(attachment_lines)
        else:
            attachments_summary = "No attachments were provided for this ticket."

        logger.info(f"\n[STEP 3/6] Setting up workspace, GitHub, and Git...")
        # 3. SETUP WORKSPACE (GitHub repo, branch, Magpie workspace, dev sandbox, Git)
        setup_result = setup_ticket_workspace(
            ticket=ticket,
            project=project,
            conversation_id=conversation_id,
            create_branch=True
        )

        if setup_result['status'] == 'error':
            error_msg = setup_result.get('error', 'Workspace setup failed')
            logger.error(f"[STEP 3/6] ✗ {error_msg}")

            ticket.status = 'blocked'
            ticket.queue_status = 'none'  # Clear queue status
            ticket.notes = (ticket.notes or "") + f"""
---
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] ❌ BLOCKED - Workspace Setup Failed
Reason: {error_msg}
Stage: Workspace/GitHub setup
Action required: Check workspace configuration and GitHub access
"""
            ticket.save(update_fields=['status', 'queue_status', 'notes'])

            broadcast_ticket_notification(conversation_id, {
                'is_notification': True,
                'notification_type': 'toolhistory',
                'function_name': 'ticket_execution',
                'status': 'failed',
                'message': f"✗ Ticket #{ticket.id} failed: {error_msg}",
                'ticket_id': ticket.id,
                'ticket_name': ticket.name,
                'queue_status': 'none',  # Tell frontend to clear queue indicator
                'refresh_checklist': True
            })

            # Broadcast status change to ticket logs WebSocket (clears queue indicator)
            broadcast_ticket_status_change(ticket_id, 'blocked', 'none')

            return {
                "status": "error",
                "ticket_id": ticket_id,
                "error": error_msg,
                "execution_time": f"{time.time() - start_time:.2f}s"
            }

        # Extract setup results
        workspace = setup_result['workspace']
        workspace_id = setup_result['workspace_id']
        feature_branch_name = setup_result['feature_branch']
        git_setup_error = setup_result.get('git_setup_error')
        github_owner = setup_result.get('github_owner')
        github_repo = setup_result.get('github_repo')
        github_token = get_github_token(project.owner)
        # Use project's actual stack, not hardcoded fallback
        stack = setup_result.get('stack') or project.stack or 'nextjs'
        stack_config = get_stack_config(stack, project)
        # Get project_dir from stack_config, not hardcoded fallback
        project_dir = setup_result.get('project_dir') or stack_config.get('project_dir', 'nextjs-app')

        logger.info(f"[STEP 3/6] ✓ Workspace setup complete: {workspace_id}")

        # Check for cancellation before proceeding
        from tasks.dispatch import is_ticket_cancelled, clear_ticket_cancellation_flag
        if is_ticket_cancelled(ticket_id):
            logger.info(f"[STEP 3/6] ⊘ Ticket #{ticket_id} was cancelled, stopping execution")
            return {
                "status": "cancelled",
                "ticket_id": ticket_id,
                "message": "Ticket execution was cancelled by user",
                "execution_time": f"{time.time() - start_time:.2f}s"
            }

        # 4. UPDATE STATUS TO IN-PROGRESS
        logger.info(f"\n[STEP 4/6] Updating ticket status to in_progress...")
        ticket.status = 'in_progress'
        ticket.save(update_fields=['status'])
        logger.info(f"[STEP 4/6] ✓ Ticket #{ticket_id} marked as in_progress")

        # Broadcast start notification
        broadcast_ticket_notification(conversation_id, {
            'is_notification': True,
            'notification_type': 'toolhistory',
            'function_name': 'ticket_execution',
            'status': 'in_progress',
            'message': f"Working on ticket #{ticket.id}: {ticket.name}",
            'ticket_id': ticket.id,
            'ticket_name': ticket.name,
            'refresh_checklist': True
        })

        logger.info(f"\n[STEP 5/6] Fetching project documentation...")
        # 5. FETCH PROJECT DOCUMENTATION (PRD & Implementation)
        project_context = ""
        try:
            from projects.models import ProjectFile

            # Fetch PRD files
            prd_files = ProjectFile.objects.filter(
                project=project,
                file_type='prd',
                is_active=True
            ).order_by('-updated_at')[:2]  # Get up to 2 most recent PRDs

            # Fetch implementation files
            impl_files = ProjectFile.objects.filter(
                project=project,
                file_type='implementation',
                is_active=True
            ).order_by('-updated_at')[:2]  # Get up to 2 most recent implementation docs

            if prd_files or impl_files:
                project_context = "\n\n📋 PROJECT DOCUMENTATION:\n"

                for prd in prd_files:
                    project_context += f"\n--- PRD: {prd.name} ---\n"
                    project_context += prd.file_content[:5000]  # Limit to 5000 chars per file
                    if len(prd.file_content) > 5000:
                        project_context += "\n...(truncated for brevity)\n"
                    project_context += "\n"

                for impl in impl_files:
                    project_context += f"\n--- Technical Implementation: {impl.name} ---\n"
                    project_context += impl.file_content[:5000]  # Limit to 5000 chars per file
                    if len(impl.file_content) > 5000:
                        project_context += "\n...(truncated for brevity)\n"
                    project_context += "\n"

                logger.info(f"[STEP 5/6] ✓ Added {len(prd_files)} PRDs, {len(impl_files)} implementation docs to context")
            else:
                logger.info(f"[STEP 5/6] ⊘ No project documentation found")
        except Exception as e:
            logger.warning(f"[STEP 5/6] ⚠ Could not fetch project documentation: {str(e)}")

        # Build git error context if present
        git_error_context = ""
        if git_setup_error:
            git_error_context = f"""
                ⚠️ GIT SETUP ISSUE DETECTED:
                Repository: {git_setup_error['repo']}
                Target Branch: {git_setup_error['branch']}
                Error: {git_setup_error['message']}

                🔧 BEFORE implementing the ticket, you MUST fix this git issue:
                1. Check the current git status: cd /workspace/{project_dir} && git status
                2. If there are merge conflicts, resolve them:
                - Check conflicted files
                - Resolve conflicts by editing files
                - Stage resolved files: git add <files>
                - Complete merge: git commit -m "Resolve merge conflicts"
                3. If there are uncommitted changes, either commit or stash them
                4. Checkout the correct branch: git checkout {git_setup_error['branch']}
                5. Verify you're on the right branch: git branch --show-current

                Only AFTER fixing the git issue should you proceed with ticket implementation.
                """

        implementation_prompt = f"""
            You are implementing ticket #{ticket.id}: {ticket.name}

            TICKET DESCRIPTION:
            {ticket.description}

            PROJECT STACK: {stack_config['name']}
            PROJECT PATH: {project_dir}
            {project_context}
            {git_error_context}

            ATTACHMENTS:
            {attachments_summary}

            ✅ Success case: "IMPLEMENTATION_STATUS: COMPLETE - [brief summary of what you did]"
            ❌ Failure case: "IMPLEMENTATION_STATUS: FAILED - [reason]"
            """

        # Build stack-specific completion criteria
        dev_cmd = stack_config.get('dev_cmd', 'npm run dev')

        system_prompt = f"""
            You are expert developer assigned to work on a {stack_config['name']} development ticket.

            COMMUNICATION PROTOCOL - VERY IMPORTANT:
            1. IMMEDIATELY call broadcast_to_user(status="progress", message="Starting work on: [ticket name]...")
            2. Work SILENTLY - do NOT output explanatory text like "Let me check...", "Perfect!", "Now I'll..."
            3. Just execute tools directly without narration
            4. At the END, call broadcast_to_user(status="complete", message="[summary of what was done]")
            5. If blocked or need help, call broadcast_to_user(status="blocked", message="[what's wrong]")

            The user only sees broadcast_to_user messages clearly. All other text output clutters the logs.

            WORKFLOW:
            1. Broadcast that you're starting
            2. Check existing todos: get_ticket_todos(ticket_id={ticket_id}). If none exist, create them with create_ticket_todos(ticket_id={ticket_id}, todos=[...])
            3. Check agent.md for project state. Update it with important changes.
            4. Execute todos one by one SILENTLY (batch shell commands: ls -la && cat ... && grep ...)
            5. Mark each todo as done: update_todo_status(ticket_id={ticket_id}, todo_index=X, status="Success")
            6. Install libraries as needed
            7. Broadcast final summary

            TODO MANAGEMENT (IMPORTANT):
            - ALWAYS use ticket_id={ticket_id} when calling todo functions
            - Check existing todos: get_ticket_todos(ticket_id={ticket_id})
            - Create todos: create_ticket_todos(ticket_id={ticket_id}, todos=[{{"description": "Task 1"}}, {{"description": "Task 2"}}])
            - Update status: update_todo_status(ticket_id={ticket_id}, todo_index=0, status="Success")

            🎯 COMPLETION CRITERIA:
            - Project runs with `{dev_cmd}` (DO NOT BUILD)
            - All todos marked `Success`

            IMPORTANT:
            - DO NOT RE-CREATE the project. Modify existing files.
            - DO NOT verify extensively or test in loops.
            - DO NOT create documentation files (*.md) except agent.md
            - When done, update todos and broadcast completion

            MANDATORY: You MUST end your response with one of these exact status lines (required for tracking):
            - "IMPLEMENTATION_STATUS: COMPLETE - [changes]"
            - "IMPLEMENTATION_STATUS: FAILED - [reason]"
                    """

        logger.info(f"\n[STEP 6/6] Calling AI for ticket implementation...")
        logger.info(f"[STEP 6/6] Max execution time: {max_execution_time}s | Elapsed: {time.time() - start_time:.1f}s")

        # Check for cancellation before expensive AI call
        if is_ticket_cancelled(ticket_id):
            logger.info(f"[STEP 6/6] ⊘ Ticket #{ticket_id} was cancelled before AI call, stopping execution")
            ticket.status = 'open'  # Reset to open so it can be re-queued
            ticket.save(update_fields=['status'])
            return {
                "status": "cancelled",
                "ticket_id": ticket_id,
                "message": "Ticket execution was cancelled by user before AI processing",
                "execution_time": f"{time.time() - start_time:.2f}s"
            }

        # 10. CALL AI WITH TIMEOUT PROTECTION

        # Wrap AI call with timeout check
        ai_call_start = time.time()
        try:
            ai_response = async_to_sync(get_ai_response)(
                user_message=implementation_prompt,
                system_prompt=system_prompt,
                project_id=project.project_id,  # Use UUID, not database ID
                conversation_id=conversation_id,
                stream=False,
                tools=tools_builder,
                attachments=attachments if attachments else None,
                ticket_id=ticket_id  # Pass ticket_id for cancellation checking during AI execution
            )
            ai_call_duration = time.time() - ai_call_start

            # Check if AI execution was cancelled during tool execution
            if ai_response and ai_response.get('cancelled'):
                logger.info(f"[STEP 6/6] ⊘ Ticket #{ticket_id} was cancelled during AI tool execution")
                clear_ticket_cancellation_flag(ticket_id)
                ticket.status = 'open'
                ticket.save(update_fields=['status'])
                return {
                    "status": "cancelled",
                    "ticket_id": ticket_id,
                    "message": "Ticket execution was cancelled during AI tool execution",
                    "execution_time": f"{time.time() - start_time:.2f}s"
                }

            logger.info(f"[STEP 6/6] ✓ AI call completed in {ai_call_duration:.1f}s")
        except Exception as ai_error:
            # Handle API errors (500s, timeouts, etc.) - no retry, just fail
            logger.error(f"[STEP 6/6] ✗ AI call failed: {str(ai_error)}")
            raise Exception(f"AI API error: {str(ai_error)}")

        content = ai_response.get('content', '') if ai_response else ''
        execution_time = time.time() - start_time

        # Log the AI response for debugging
        logger.info(f"[STEP 6/6] AI response length: {len(content)} chars")
        logger.info(f"[STEP 6/6] Total elapsed time: {execution_time:.1f}s")

        # Check for cancellation after AI call (user may have cancelled during execution)
        if is_ticket_cancelled(ticket_id):
            logger.info(f"[POST-AI] ⊘ Ticket #{ticket_id} was cancelled during AI execution, stopping")
            clear_ticket_cancellation_flag(ticket_id)
            ticket.status = 'open'  # Reset to open so it can be re-queued
            ticket.save(update_fields=['status'])
            return {
                "status": "cancelled",
                "ticket_id": ticket_id,
                "message": "Ticket execution was cancelled by user during AI processing",
                "execution_time": f"{execution_time:.2f}s"
            }

        # Check if AI response indicates an error (500, overloaded, etc.)
        has_api_error = ai_response.get('error') if ai_response else False
        error_message = ai_response.get('error_message', '') if ai_response else ''

        # Check for timeout
        if execution_time > max_execution_time:
            raise Exception(f"Execution timeout after {execution_time:.2f}s (max: {max_execution_time}s)")

        # If there was an API error, treat as failed
        if has_api_error:
            raise Exception(f"AI API error during execution: {error_message}")

        logger.info(f"\n[POST-AI] Checking AI completion status and committing changes...")
        # 11. CHECK COMPLETION STATUS (with fallback detection)
        completed = 'IMPLEMENTATION_STATUS: COMPLETE' in content
        failed = 'IMPLEMENTATION_STATUS: FAILED' in content

        # Fallback: If no explicit status, ticket is NOT complete
        # Only mark as complete if there's an explicit success status
        if not completed and not failed:
            logger.warning(f"[POST-AI] ⚠ No explicit completion status found in AI response")
            logger.warning(f"[POST-AI] Content length: {len(content)} chars")
            # ALWAYS mark as failed if no explicit completion status
            # The AI MUST provide explicit status - anything else is incomplete
            failed = True
            logger.error("[POST-AI] ✗ Marking as FAILED - AI must end with IMPLEMENTATION_STATUS")

        logger.info(f"[POST-AI] Status check - Completed: {completed} | Failed: {failed} | Time: {execution_time:.1f}s")
        
        # 9. EXTRACT WHAT WAS DONE (for logging)
        import re
        files_created = re.findall(r'cat > (nextjs-app/[\w\-\./]+)', content)
        deps_installed = re.findall(r'npm install ([\w\-\s@/]+)', content)
        dependencies = []
        for dep_string in deps_installed:
            dependencies.extend(dep_string.split())

        # Count tool executions from content
        tool_calls_count = content.count('ssh_command') + content.count('Tool call')
        logger.info(f"Estimated tool calls: {tool_calls_count}, Files created: {len(files_created)}, Dependencies: {len(dependencies)}")

        # 12. COMMIT AND PUSH TO GITHUB (if configured and ticket completed)
        commit_sha = None
        merge_status = None

        # Check for cancellation one more time before committing
        if is_ticket_cancelled(ticket_id):
            logger.info(f"[PRE-COMMIT] ⊘ Ticket #{ticket_id} was cancelled before commit, skipping push")
            clear_ticket_cancellation_flag(ticket_id)
            ticket.status = 'open'
            ticket.save(update_fields=['status'])
            return {
                "status": "cancelled",
                "ticket_id": ticket_id,
                "message": "Ticket was cancelled before commit - changes NOT pushed to GitHub",
                "execution_time": f"{time.time() - start_time:.2f}s"
            }

        if completed and not failed and github_owner and github_repo and github_token and feature_branch_name:
            logger.info(f"\n[COMMIT] Committing and pushing changes to GitHub...")

            # Commit and push changes
            commit_message = f"feat: {ticket.name}\n\nImplemented ticket #{ticket_id}\n\n{ticket.description[:200]}"
            commit_result = commit_and_push_changes(workspace_id, feature_branch_name, commit_message, ticket_id, stack=stack, github_token=github_token, github_owner=github_owner, github_repo=github_repo)

            if commit_result['status'] == 'success':
                commit_sha = commit_result.get('commit_sha')
                logger.info(f"[COMMIT] ✓ Changes committed and pushed: {commit_sha}")

                # Save commit SHA to ticket
                ticket.github_commit_sha = commit_sha
                ticket.save(update_fields=['github_commit_sha'])

                # Merge feature branch into lfg-agent
                logger.info(f"[COMMIT] Merging {feature_branch_name} into lfg-agent...")
                merge_result = merge_feature_to_lfg_agent(github_token, github_owner, github_repo, feature_branch_name)

                if merge_result['status'] == 'success':
                    logger.info(f"[COMMIT] ✓ Merged {feature_branch_name} into lfg-agent")
                    merge_status = 'merged'
                elif merge_result['status'] == 'conflict':
                    # Try to resolve conflict locally in workspace
                    logger.warning(f"[COMMIT] ⚠ Merge conflict detected via API, attempting AI-based resolution...")
                    resolution_result = resolve_merge_conflict(workspace_id, feature_branch_name, ticket_id, project.project_id, conversation_id, stack=stack)

                    if resolution_result['status'] == 'success':
                        logger.info(f"[COMMIT] ✓ Conflicts resolved and merged locally")
                        merge_status = 'merged'
                    else:
                        logger.error(f"[COMMIT] ✗ Could not resolve conflicts: {resolution_result.get('message')}")
                        merge_status = 'conflict'
                        # Add conflict details to ticket notes
                        if 'conflicted_files' in resolution_result:
                            ticket.notes += f"\n\n⚠ MERGE CONFLICTS:\nFiles: {', '.join(resolution_result['conflicted_files'])}"
                            ticket.save(update_fields=['notes'])
                else:
                    logger.error(f"[COMMIT] ✗ Merge failed: {merge_result.get('message')}")
                    merge_status = 'failed'

                # Save merge status to ticket
                ticket.github_merge_status = merge_status
                ticket.save(update_fields=['github_merge_status'])
            else:
                logger.error(f"[COMMIT] ✗ Failed to commit changes: {commit_result.get('message')}")

        logger.info(f"\n[FINALIZE] Updating ticket status and saving results...")
        # 13. UPDATE TICKET BASED ON RESULT
        if completed and not failed:
            # SUCCESS!
            logger.info(f"[FINALIZE] ✓ SUCCESS - Marking ticket as review")
            ticket.status = 'review'

            # Build notes with Git information if available
            git_info = ""
            if github_owner and github_repo:
                repo_url = f"https://github.com/{github_owner}/{github_repo}"
                git_info = f"\nGitHub Repository: {repo_url}"
                if feature_branch_name:
                    git_info += f"\nFeature Branch: {feature_branch_name}"
                    branch_url = f"{repo_url}/tree/{feature_branch_name}"
                    git_info += f"\nFeature Branch URL: {branch_url}"
                if commit_sha:
                    git_info += f"\nCommit: {commit_sha}"
                    commit_url = f"{repo_url}/commit/{commit_sha}"
                    git_info += f"\nCommit URL: {commit_url}"
                if merge_status:
                    merge_emoji = '✓' if merge_status == 'merged' else ('⚠' if merge_status == 'conflict' else '✗')
                    git_info += f"\nMerge to lfg-agent: {merge_emoji} {merge_status}"
                    if merge_status == 'merged':
                        lfg_agent_url = f"{repo_url}/tree/lfg-agent"
                        git_info += f"\nlfg-agent Branch: {lfg_agent_url}"

            ticket.notes = (ticket.notes or "") + f"""
                ---
                [{datetime.now().strftime('%Y-%m-%d %H:%M')}] IMPLEMENTATION COMPLETED
                Time: {execution_time:.2f} seconds
                Files created: {len(files_created)}
                Dependencies: {', '.join(set(dependencies))}{git_info}
                Status: ✓ Complete
                """
            # Update execution time tracking
            ticket.execution_time_seconds = (ticket.execution_time_seconds or 0) + execution_time
            ticket.last_execution_at = datetime.now()
            ticket.save(update_fields=['status', 'notes', 'execution_time_seconds', 'last_execution_at'])
            
            broadcast_ticket_notification(conversation_id, {
                'is_notification': True,
                'notification_type': 'toolhistory',
                'function_name': 'ticket_execution',
                'status': 'completed',
                'message': f"✓ Completed ticket #{ticket.id}: {ticket.name}",
                'ticket_id': ticket.id,
                'ticket_name': ticket.name,
                'queue_status': 'none',  # Tell frontend to clear queue indicator
                'refresh_checklist': True
            })

            logger.info(f"[FINALIZE] ✓ Task completed successfully in {execution_time:.1f}s")
            logger.info(f"{'='*80}\n[TASK END] SUCCESS - Ticket #{ticket_id}\n{'='*80}\n")

            # Broadcast status change to ticket logs WebSocket (clears queue indicator)
            broadcast_ticket_status_change(ticket_id, 'review', 'none')

            # Clear any cancellation flag (may have been set but we finished anyway)
            clear_ticket_cancellation_flag(ticket_id)

            result = {
                "status": "success",
                "ticket_id": ticket_id,
                "ticket_name": ticket.name,
                "message": f"Ticket completed in {execution_time:.2f}s",
                "execution_time": f"{execution_time:.2f}s",
                "files_created": files_created,
                "dependencies": list(set(dependencies)),
                "workspace_id": workspace_id,
                "completion_time": datetime.now().isoformat()
            }

            # Add Git information to result if available
            if github_owner and github_repo:
                result["git"] = {
                    "repository": f"{github_owner}/{github_repo}",
                    "branch": feature_branch_name,
                    "commit_sha": commit_sha,
                    "merge_status": merge_status
                }

            return result
        else:
            # FAILED OR INCOMPLETE
            logger.warning(f"[FINALIZE] ✗ FAILED - Marking ticket as blocked")
            error_match = re.search(r'IMPLEMENTATION_STATUS: FAILED - (.+)', content)

            # Detect specific failure reasons
            hit_tool_limit = 'Maximum tool execution limit reached' in content or 'exceeded tool limit' in content.lower()
            hit_timeout = execution_time >= max_execution_time
            failure_type = 'tool_limit' if hit_tool_limit else ('timeout' if hit_timeout else 'incomplete')

            if error_match:
                error_reason = error_match.group(1)
            elif hit_tool_limit:
                error_reason = f"Maximum tool execution limit reached (80 rounds). Implementation may be incomplete."
            elif hit_timeout:
                error_reason = f"Execution timed out after {execution_time:.0f}s (limit: {max_execution_time}s)."
            elif not content or len(content) < 100:
                error_reason = "AI response was empty or incomplete. Possible API timeout or error."
            else:
                error_reason = "No explicit completion status provided. AI may have exceeded tool limit or stopped unexpectedly."

            ticket.status = 'blocked'
            ticket.queue_status = 'none'  # Clear queue status

            # Build failure indicator for notes
            failure_indicator = "⏱️ TIMEOUT" if hit_timeout else ("🔧 TOOL LIMIT" if hit_tool_limit else "❌ BLOCKED")
            ticket.notes = (ticket.notes or "") + f"""
---
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {failure_indicator} - Implementation Failed
Reason: {error_reason}
Stage: AI Implementation
Execution time: {execution_time:.2f}s
Tool calls: ~{tool_calls_count}
Files attempted: {len(files_created)}
Workspace: {workspace_id}
Action required: Review error and retry or manually fix
"""
            # Update execution time tracking even on failure
            ticket.execution_time_seconds = (ticket.execution_time_seconds or 0) + execution_time
            ticket.last_execution_at = datetime.now()
            ticket.save(update_fields=['status', 'queue_status', 'notes', 'execution_time_seconds', 'last_execution_at'])

            broadcast_ticket_notification(conversation_id, {
                'is_notification': True,
                'notification_type': 'toolhistory',
                'function_name': 'ticket_execution',
                'status': 'failed',
                'failure_type': failure_type,  # 'tool_limit', 'timeout', or 'incomplete'
                'message': f"✗ Failed ticket #{ticket.id}: {error_reason}",
                'ticket_id': ticket.id,
                'ticket_name': ticket.name,
                'queue_status': 'none',  # Tell frontend to clear queue indicator
                'execution_time': execution_time,
                'tool_calls_count': tool_calls_count,
                'refresh_checklist': True
            })

            # Broadcast status change to ticket logs WebSocket (clears queue indicator)
            broadcast_ticket_status_change(ticket_id, 'blocked', 'none')

            logger.info(f"{'='*80}\n[TASK END] FAILED - Ticket #{ticket_id}\n{'='*80}\n")

            # Clear any cancellation flag
            clear_ticket_cancellation_flag(ticket_id)

            return {
                "status": "failed",
                "ticket_id": ticket_id,
                "ticket_name": ticket.name,
                "error": error_reason,
                "execution_time": f"{execution_time:.2f}s",
                "workspace_id": workspace_id,
                "requires_manual_intervention": True
            }

    except Exception as e:
        # EXCEPTION HANDLING - NO RETRIES
        execution_time = time.time() - start_time
        error_msg = str(e)
        logger.error(f"\n{'='*80}\n[EXCEPTION] Critical error in ticket {ticket_id}\n{'='*80}")
        logger.error(f"Error: {error_msg}", exc_info=True)
        logger.error(f"Elapsed time: {execution_time:.1f}s")

        if 'ticket' in locals():
            # Mark ticket as blocked - no retry logic
            ticket.status = 'blocked'
            ticket.queue_status = 'none'  # Clear queue status
            ticket.notes = (ticket.notes or "") + f"""
---
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] ❌ BLOCKED - Exception Error
Reason: {error_msg}
Stage: Execution crashed
Execution time: {execution_time:.2f}s
Workspace: {workspace_id or 'N/A'}
Action required: Check logs for detailed error trace and retry
"""
            # Update execution time tracking even on exception
            ticket.execution_time_seconds = (ticket.execution_time_seconds or 0) + execution_time
            ticket.last_execution_at = datetime.now()
            ticket.save(update_fields=['status', 'queue_status', 'notes', 'execution_time_seconds', 'last_execution_at'])

            broadcast_ticket_notification(conversation_id, {
                'is_notification': True,
                'notification_type': 'toolhistory',
                'function_name': 'ticket_execution',
                'status': 'failed',
                'message': f"✗ Ticket #{ticket.id} error: {error_msg[:100]}",
                'ticket_id': ticket.id,
                'ticket_name': ticket.name,
                'queue_status': 'none',  # Tell frontend to clear queue indicator
                'refresh_checklist': True
            })

        # Return error without re-raising (prevents Django-Q retry loops)
        logger.error(f"{'='*80}\n[TASK END] ERROR - Ticket #{ticket_id}\n{'='*80}\n")

        # Broadcast status change to ticket logs WebSocket (clears queue indicator)
        try:
            broadcast_ticket_status_change(ticket_id, 'blocked', 'none')
        except Exception:
            pass  # Don't fail on cleanup

        # Clear any cancellation flag
        try:
            from tasks.dispatch import clear_ticket_cancellation_flag
            clear_ticket_cancellation_flag(ticket_id)
        except Exception:
            pass  # Don't fail on cleanup

        return {
            "status": "error",
            "ticket_id": ticket_id,
            "error": error_msg,
            "workspace_id": workspace_id,
            "execution_time": f"{execution_time:.2f}s"
        }


def execute_ticket_with_claude_cli(ticket_id: int, project_id: int, conversation_id: int, max_execution_time: int = 1200) -> Dict[str, Any]:
    """
    Execute a ticket using Claude Code CLI instead of direct API calls.

    This function delegates AI work to Claude Code CLI installed in the Magpie workspace,
    providing better context handling and leveraging Claude Code's built-in tools.

    Args:
        ticket_id: The ID of the ProjectTicket ticket
        project_id: The ID of the project
        conversation_id: The ID of the conversation
        max_execution_time: Maximum execution time in seconds (default: 1200s/20min)

    Returns:
        Dict with execution results and status
    """
    from factory.claude_code_utils import (
        restore_claude_auth_from_s3,
        backup_claude_auth_to_s3,
        run_claude_cli,
        parse_claude_json_stream,
        create_ticket_logs_from_claude_output
    )
    from accounts.models import Profile
    from projects.websocket_utils import async_send_ticket_log_notification

    # Set the current ticket_id in context
    current_ticket_id.set(ticket_id)
    logger.info(f"\n{'='*80}\n[CLI TASK START] Ticket #{ticket_id} | Project #{project_id} | Conv #{conversation_id}\n{'='*80}")

    start_time = time.time()
    workspace_id = None

    try:
        logger.info(f"\n[CLI STEP 1/7] Fetching ticket and project data...")
        # 1. GET TICKET AND PROJECT
        ticket = ProjectTicket.objects.get(id=ticket_id)
        project = Project.objects.get(id=project_id)
        user = project.owner
        profile = Profile.objects.get(user=user)

        # Ensure user has a CLI API key
        if not profile.cli_api_key:
            profile.generate_cli_api_key()
            logger.info(f"[CLI STEP 1/7] Generated new CLI API key for user")

        logger.info(f"[CLI STEP 1/7] ✓ Ticket: '{ticket.name}' | Project: '{project.name}'")

        logger.info(f"\n[CLI STEP 2/7] Checking ticket status...")
        # 2. CHECK IF ALREADY COMPLETED
        if ticket.status == 'done':
            logger.info(f"[CLI STEP 2/7] ⊘ Ticket already completed, skipping")
            return {
                "status": "success",
                "ticket_id": ticket_id,
                "message": "Already completed",
                "skipped": True
            }

        # Check if retry
        is_retry = ticket.status in ['blocked', 'failed', 'in_progress']
        if is_retry:
            logger.info(f"[CLI STEP 2/7] ⟳ RETRY detected - previous status: {ticket.status}")
            ticket.notes = (ticket.notes or "") + f"""
---
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] ⟳ CLI EXECUTION RETRY
Previous status: {ticket.status}
Using Claude Code CLI mode
"""
            ticket.save(update_fields=['notes'])

        # Get attachments
        attachments = list(ticket.attachments.all())

        def _format_file_size(num_bytes: int) -> str:
            try:
                size = float(num_bytes or 0)
            except (TypeError, ValueError):
                size = 0
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if size < 1024 or unit == 'TB':
                    return f"{size:.1f} {unit}" if size >= 1024 and unit != 'B' else f"{int(size)} {unit}"
                size /= 1024
            return f"{size:.1f} TB"

        if attachments:
            attachment_lines = []
            for attachment in attachments:
                display_name = attachment.original_filename or os.path.basename(attachment.file.name)
                size_label = _format_file_size(attachment.file_size)
                uploaded_label = attachment.uploaded_at.strftime('%Y-%m-%d %H:%M')
                attachment_lines.append(f"- {display_name} ({size_label}, uploaded {uploaded_label})")
            attachments_summary = "\n".join(attachment_lines)
        else:
            attachments_summary = "No attachments were provided for this ticket."

        logger.info(f"\n[CLI STEP 3/7] Getting Claude auth workspace...")
        # 3. USE CLAUDE AUTH WORKSPACE (instead of creating new one)
        from development.models import MagpieWorkspace
        from factory.ai_functions import _run_magpie_ssh, get_magpie_client

        # Get the user's Claude auth workspace
        claude_workspace = MagpieWorkspace.objects.filter(
            user=user,
            workspace_type='claude_auth',
            status='ready'
        ).first()

        client = get_magpie_client()
        workspace_id = None
        need_new_workspace = False

        if not claude_workspace:
            logger.info(f"[CLI STEP 3/7] No Claude auth workspace found, will create one...")
            need_new_workspace = True
        else:
            workspace_id = claude_workspace.workspace_id
            logger.info(f"[CLI STEP 3/7] Found Claude auth workspace: {workspace_id}")

            # Verify workspace is accessible
            workspace_accessible = False
            try:
                check_result = _run_magpie_ssh(client, workspace_id, "echo 'OK'", timeout=15)
                if check_result.get('exit_code') == 0 and 'OK' in check_result.get('stdout', ''):
                    workspace_accessible = True
                    logger.info(f"[CLI STEP 3/7] ✓ Workspace is accessible")
            except Exception as e:
                logger.warning(f"[CLI STEP 3/7] Workspace {workspace_id} not accessible: {e}")

            if not workspace_accessible:
                # Mark old workspace as error
                claude_workspace.status = 'error'
                claude_workspace.save(update_fields=['status'])
                need_new_workspace = True

        # Create new workspace if needed
        if need_new_workspace:
            logger.info(f"[CLI STEP 3/7] Creating new Claude workspace...")

            # Create new workspace (MAGPIE_BOOTSTRAP_SCRIPT imported at top of file)
            workspace_name = f"claude-auth-{user.id}"

            try:
                vm_handle = client.jobs.create_persistent_vm(
                    name=workspace_name,
                    script=MAGPIE_BOOTSTRAP_SCRIPT,
                    stateful=True,
                    workspace_size_gb=5,
                    vcpus=1,
                    memory_mb=1024,
                    poll_timeout=120,
                    poll_interval=5,
                )

                new_workspace_id = vm_handle.request_id
                ipv6 = vm_handle.ip_address

                if not new_workspace_id:
                    raise Exception("Failed to create new workspace - no ID returned")

                # Delete old workspace record and create new one
                MagpieWorkspace.objects.filter(user=user, workspace_type='claude_auth').delete()
                claude_workspace = MagpieWorkspace.objects.create(
                    user=user,
                    workspace_type='claude_auth',
                    job_id=new_workspace_id,
                    workspace_id=new_workspace_id,
                    ipv6_address=ipv6,
                    status='ready'
                )
                workspace_id = new_workspace_id
                logger.info(f"[CLI STEP 3/7] ✓ Created new workspace: {workspace_id}")

                # Wait for workspace to be ready
                time.sleep(3)

                # Restore Claude auth from S3
                s3_key = profile.claude_code_s3_key or f"claude-auth/{user.id}/claude-config.tar.gz"
                logger.info(f"[CLI STEP 3/7] Restoring Claude auth from S3: {s3_key}")
                restore_result = restore_claude_auth_from_s3(workspace_id, user.id, s3_key)
                if restore_result.get('status') == 'success':
                    logger.info(f"[CLI STEP 3/7] ✓ Restored auth from S3")
                else:
                    logger.warning(f"[CLI STEP 3/7] ⚠ S3 restore failed: {restore_result.get('error')}")

            except Exception as create_error:
                error_msg = f"Failed to create new workspace: {str(create_error)}"
                logger.error(f"[CLI STEP 3/7] ✗ {error_msg}")

                ticket.status = 'blocked'
                ticket.queue_status = 'none'
                ticket.notes = (ticket.notes or "") + f"""
---
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] ❌ BLOCKED - Could Not Create Workspace
Reason: {error_msg}
Mode: Claude Code CLI
"""
                ticket.save(update_fields=['status', 'queue_status', 'notes'])
                broadcast_ticket_status_change(ticket_id, 'blocked', 'none')

                return {
                    "status": "error",
                    "ticket_id": ticket_id,
                    "error": error_msg,
                    "cli_error": True,
                    "execution_time": f"{time.time() - start_time:.2f}s"
                }

        # Setup git in the Claude workspace
        from codebase_index.models import IndexedRepository

        github_token = get_github_token(project.owner)
        github_owner = None
        github_repo = None
        git_setup_error = None
        stack = project.stack or 'nextjs'
        stack_config = get_stack_config(stack, project)
        project_dir = stack_config.get('project_dir', 'nextjs-app')
        feature_branch_name = f"feature/ticket-{ticket.id}"

        # Get GitHub info from IndexedRepository
        try:
            indexed_repo = IndexedRepository.objects.get(project=project)
            github_owner = indexed_repo.github_owner
            github_repo = indexed_repo.github_repo_name
            logger.info(f"[CLI STEP 3/7] Found repo: {github_owner}/{github_repo}")
        except IndexedRepository.DoesNotExist:
            logger.warning(f"[CLI STEP 3/7] No IndexedRepository found for project")

        if github_owner and github_repo and github_token:
            # Setup git in workspace
            logger.info(f"[CLI STEP 3/7] Setting up git repo in Claude workspace...")

            git_setup_script = f"""
            cd /workspace

            # Check if repo already cloned
            if [ -d "{project_dir}/.git" ]; then
                echo "REPO_EXISTS"
                cd {project_dir}
                git fetch origin
            else
                echo "CLONING_REPO"
                rm -rf {project_dir}
                git clone https://{github_token}@github.com/{github_owner}/{github_repo}.git {project_dir}
                cd {project_dir}
            fi

            # Ensure lfg-agent branch exists and is up to date
            # lfg-agent is the base branch for all feature branches
            git checkout lfg-agent 2>/dev/null || git checkout -b lfg-agent origin/lfg-agent 2>/dev/null || (git checkout main && git checkout -b lfg-agent)
            git pull origin lfg-agent 2>/dev/null || echo "PULL_SKIPPED"

            # Create or checkout feature branch from lfg-agent
            git checkout -b {feature_branch_name} 2>/dev/null || git checkout {feature_branch_name} 2>/dev/null || echo "BRANCH_ERROR"

            # Configure git
            git config user.email "ai@lfg.dev"
            git config user.name "LFG AI"

            echo "GIT_SETUP_COMPLETE"
            pwd
            git branch --show-current
            """

            git_result = _run_magpie_ssh(client, workspace_id, git_setup_script, timeout=120)
            git_stdout = git_result.get('stdout', '')

            if 'GIT_SETUP_COMPLETE' in git_stdout:
                logger.info(f"[CLI STEP 3/7] ✓ Git setup complete, branch: {feature_branch_name}")
                # Save branch name to ticket so it can be used for commits later
                if not ticket.github_branch:
                    ticket.github_branch = feature_branch_name
                    ticket.github_merge_status = 'pending'
                    ticket.save(update_fields=['github_branch', 'github_merge_status'])
                    logger.info(f"[CLI STEP 3/7] ✓ Saved github_branch to ticket: {feature_branch_name}")
            else:
                git_setup_error = f"Git setup issue: {git_stdout[:200]}"
                logger.warning(f"[CLI STEP 3/7] ⚠ {git_setup_error}")
        else:
            git_setup_error = "No GitHub repo configured or missing token"

        logger.info(f"[CLI STEP 3/7] ✓ Workspace ready: {workspace_id}")

        # Check for cancellation
        from tasks.dispatch import is_ticket_cancelled, clear_ticket_cancellation_flag
        if is_ticket_cancelled(ticket_id):
            logger.info(f"[CLI STEP 3/7] ⊘ Ticket cancelled")
            return {
                "status": "cancelled",
                "ticket_id": ticket_id,
                "message": "Cancelled by user",
                "execution_time": f"{time.time() - start_time:.2f}s"
            }

        logger.info(f"\n[CLI STEP 4/7] Verifying Claude auth...")
        # 4. VERIFY CLAUDE AUTH - run test command to ensure Claude is working
        from factory.claude_code_utils import check_claude_auth_status

        auth_check = check_claude_auth_status(workspace_id)

        if not auth_check.get('authenticated'):
            logger.warning(f"[CLI STEP 4/7] ⚠ Claude not authenticated, attempting to restore from S3...")

            # Try to restore from S3
            if profile.claude_code_s3_key:
                restore_result = restore_claude_auth_from_s3(workspace_id, user.id, profile.claude_code_s3_key)

                if restore_result.get('status') == 'success':
                    # Verify again after restore
                    auth_check = check_claude_auth_status(workspace_id)

            if not auth_check.get('authenticated'):
                error_msg = "Claude Code is not authenticated. Please reconnect in Settings."
                logger.error(f"[CLI STEP 4/7] ✗ {error_msg}")

                # Mark the user as not authenticated so Settings page shows correct status
                profile.claude_code_authenticated = False
                profile.save(update_fields=['claude_code_authenticated'])
                logger.info(f"[CLI STEP 4/7] Marked user as not authenticated")

                ticket.status = 'blocked'
                ticket.queue_status = 'none'
                ticket.notes = (ticket.notes or "") + f"""
---
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] ❌ BLOCKED - Claude Auth Failed
Reason: {error_msg}
Mode: Claude Code CLI
Action: Please go to Settings > Claude Code and reconnect
"""
                ticket.save(update_fields=['status', 'queue_status', 'notes'])

                broadcast_ticket_notification(conversation_id, {
                    'is_notification': True,
                    'notification_type': 'claude_auth_required',
                    'function_name': 'ticket_execution',
                    'status': 'failed',
                    'message': f"⚠️ Claude Code authentication required. Please reconnect in Settings.",
                    'ticket_id': ticket.id,
                    'ticket_name': ticket.name,
                    'queue_status': 'none',
                    'settings_url': '/settings/#claude-code',
                    'refresh_checklist': True
                })

                broadcast_ticket_status_change(ticket_id, 'blocked', 'none', error_reason=error_msg)

                return {
                    "status": "error",
                    "ticket_id": ticket_id,
                    "error": error_msg,
                    "cli_error": True,
                    "auth_required": True,
                    "settings_url": "/settings/#claude-code",
                    "execution_time": f"{time.time() - start_time:.2f}s"
                }

        logger.info(f"[CLI STEP 4/7] ✓ Claude auth verified")

        # 5. UPDATE STATUS TO IN-PROGRESS
        logger.info(f"\n[CLI STEP 5/7] Updating status to in_progress...")
        ticket.status = 'in_progress'
        ticket.save(update_fields=['status'])

        broadcast_ticket_notification(conversation_id, {
            'is_notification': True,
            'notification_type': 'toolhistory',
            'function_name': 'ticket_execution',
            'status': 'in_progress',
            'message': f"🤖 Working on ticket #{ticket.id} with Claude Code CLI",
            'ticket_id': ticket.id,
            'ticket_name': ticket.name,
            'refresh_checklist': True
        })

        logger.info(f"\n[CLI STEP 6/7] Fetching project documentation...")
        # 6. FETCH PROJECT DOCUMENTATION
        project_context = ""
        try:
            from projects.models import ProjectFile

            prd_files = ProjectFile.objects.filter(
                project=project,
                file_type='prd',
                is_active=True
            ).order_by('-updated_at')[:2]

            impl_files = ProjectFile.objects.filter(
                project=project,
                file_type='implementation',
                is_active=True
            ).order_by('-updated_at')[:2]

            if prd_files or impl_files:
                project_context = "\n\n📋 PROJECT DOCUMENTATION:\n"

                for prd in prd_files:
                    project_context += f"\n--- PRD: {prd.name} ---\n"
                    project_context += prd.file_content[:5000]
                    if len(prd.file_content) > 5000:
                        project_context += "\n...(truncated)\n"

                for impl in impl_files:
                    project_context += f"\n--- Technical Implementation: {impl.name} ---\n"
                    project_context += impl.file_content[:5000]
                    if len(impl.file_content) > 5000:
                        project_context += "\n...(truncated)\n"

                logger.info(f"[CLI STEP 6/7] ✓ Added {len(prd_files)} PRDs, {len(impl_files)} impl docs")
        except Exception as e:
            logger.warning(f"[CLI STEP 6/7] ⚠ Could not fetch docs: {str(e)}")

        # Build git error context if present
        git_error_context = ""
        if git_setup_error:
            git_error_context = f"""
⚠️ GIT SETUP ISSUE DETECTED:
{git_setup_error}

Before implementing, fix the git issue:
1. Check: cd /workspace/{project_dir} && git status
2. Resolve any conflicts or uncommitted changes
3. Checkout the correct branch: git checkout {feature_branch_name}
"""

        # Build the API URL for CLI callbacks
        from django.conf import settings
        api_base_url = getattr(settings, 'LFG_API_BASE_URL', 'https://www.turboship.ai')
        cli_api_key = profile.cli_api_key

        # Build the prompt for Claude Code CLI
        implementation_prompt = f"""You are implementing ticket #{ticket.id}: {ticket.name}

TICKET DESCRIPTION:
{ticket.description}

PROJECT STACK: {stack_config['name']}
PROJECT PATH: /workspace/{project_dir}
{project_context}
{git_error_context}

ATTACHMENTS:
{attachments_summary}

## LFG PLATFORM INTEGRATION

You can update the LFG platform in real-time using these environment variables and commands:

**Environment Variables (already set):**
- LFG_API_URL={api_base_url}
- LFG_API_KEY={cli_api_key}
- LFG_TICKET_ID={ticket.id}
- LFG_PROJECT_ID={project.project_id}

**Update Tasks/Progress:**
Use the TodoWrite tool to track your progress. Your tasks will be synced to LFG automatically via the API.

Alternatively, you can directly call the API to create/update tasks:
```bash
curl -X POST "$LFG_API_URL/api/v1/cli/tasks/bulk/" \\
  -H "X-CLI-API-Key: $LFG_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{{"ticket_id": {ticket.id}, "tasks": [{{"content": "Task 1", "status": "completed"}}, {{"content": "Task 2", "status": "in_progress"}}]}}'
```

**Mark Ticket Complete:**
When you finish implementing, call this to mark the ticket as complete:
```bash
curl -X POST "$LFG_API_URL/api/v1/cli/status/" \\
  -H "X-CLI-API-Key: $LFG_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{{"ticket_id": {ticket.id}, "status": "completed", "summary": "Brief summary of what was implemented"}}'
```

**Report Failure:**
If you encounter blockers or cannot complete the ticket:
```bash
curl -X POST "$LFG_API_URL/api/v1/cli/status/" \\
  -H "X-CLI-API-Key: $LFG_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{{"ticket_id": {ticket.id}, "status": "failed", "summary": "Reason for failure"}}'
```

**Create User Action Ticket:**
If you need the user to do something (add API keys, configure settings, etc.):
```bash
curl -X POST "$LFG_API_URL/api/v1/cli/user-action/" \\
  -H "X-CLI-API-Key: $LFG_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{{"project_id": "'$LFG_PROJECT_ID'", "parent_ticket_id": '$LFG_TICKET_ID', "title": "Add API Key", "description": "Description of what the user needs to do", "action_type": "add_api_key", "priority": "high"}}'
```
Action types: add_api_key, configure_setting, review_code, manual_fix, other

**Request User Input:**
If you need clarification or a decision from the user:
```bash
curl -X POST "$LFG_API_URL/api/v1/cli/request-input/" \\
  -H "X-CLI-API-Key: $LFG_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{{"ticket_id": {ticket.id}, "question": "Which approach should I use?", "options": ["Option A", "Option B"], "context": "Additional context..."}}'
```
This will block the ticket until the user responds.

## INSTRUCTIONS

1. Navigate to the project directory: cd /workspace/{project_dir}
2. Understand the existing codebase structure
3. Create tasks to track your implementation progress (using TodoWrite or the API)
4. Implement the required changes for this ticket
5. DO NOT commit changes - that will be handled automatically
6. When done, call the status API to mark complete (or failed)

## COMPLETION

IMPORTANT: After implementing, you MUST call the status API to mark the ticket as complete or failed.
This is how the LFG platform knows you are done.

You can also output (for logging purposes):
✅ IMPLEMENTATION_STATUS: COMPLETE - [brief summary of changes]
❌ IMPLEMENTATION_STATUS: FAILED - [reason]"""

        logger.info(f"\n[CLI STEP 7/7] Running Claude Code CLI...")
        # 7. RUN CLAUDE CODE CLI
        cli_start = time.time()

        # Real-time streaming callback to create logs and broadcast to UI
        streamed_log_count = [0]  # Use list to allow mutation in closure
        line_buffer = ['']  # Buffer for partial lines (byte-based tail may split lines)

        def stream_output_callback(new_output: str):
            """Parse streaming output and create TicketLogs in real-time."""
            import json
            from projects.models import TicketLog

            logger.info(f"[CLI CALLBACK] Received {len(new_output)} bytes")

            # Prepend any leftover from previous call (partial line)
            if line_buffer[0]:
                logger.info(f"[CLI CALLBACK] Prepending {len(line_buffer[0])} bytes from buffer")
                new_output = line_buffer[0] + new_output
                line_buffer[0] = ''

            lines = new_output.split('\n')

            # If last line doesn't end with newline, it might be partial - save for next call
            if new_output and not new_output.endswith('\n'):
                line_buffer[0] = lines[-1]
                lines = lines[:-1]
                logger.info(f"[CLI CALLBACK] Buffered {len(line_buffer[0])} bytes for next call")

            logger.info(f"[CLI CALLBACK] Processing {len(lines)} lines")
            json_objects_found = 0
            logs_created = 0

            def parse_json_objects(text):
                """Parse multiple JSON objects from a string (handles concatenated JSON)."""
                decoder = json.JSONDecoder()
                idx = 0
                objects = []
                text = text.strip()
                while idx < len(text):
                    # Skip whitespace
                    while idx < len(text) and text[idx] in ' \t\r\n':
                        idx += 1
                    if idx >= len(text):
                        break
                    try:
                        obj, end_idx = decoder.raw_decode(text, idx)
                        objects.append(obj)
                        idx += end_idx
                    except json.JSONDecodeError:
                        # Can't parse more, return what we have
                        break
                return objects

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # Skip status/metadata lines from the poll output
                if line.startswith('STATUS=') or line.startswith('OUTPUT_SIZE=') or line.startswith('EXIT_CODE='):
                    continue

                # Parse potentially multiple JSON objects from the line
                json_objects = parse_json_objects(line)
                if not json_objects and line.startswith('{'):
                    logger.warning(f"[CLI CALLBACK] Could not parse JSON from line: {line[:100]}...")
                    continue

                for msg in json_objects:
                    json_objects_found += 1
                    msg_type = msg.get('type', '')

                    # Handle assistant messages (which may contain text AND tool_use blocks)
                    if msg_type == 'assistant':
                        content_blocks = msg.get('message', {}).get('content', [])
                        if not isinstance(content_blocks, list):
                            content_blocks = [content_blocks] if content_blocks else []

                        for block in content_blocks:
                            if not isinstance(block, dict):
                                continue

                            block_type = block.get('type')
                            log_entry = None

                            # Handle text content
                            if block_type == 'text':
                                text = block.get('text', '')
                                if text and len(text) > 10:  # Skip tiny messages
                                    log_entry = TicketLog.objects.create(
                                        ticket_id=ticket.id,
                                        log_type='ai_response',
                                        command="Claude CLI Response",
                                        output=text[:4000]
                                    )
                                    logs_created += 1
                                    logger.info(f"[CLI CALLBACK] Created ai_response log: {text[:50]}...")

                            # Handle tool_use blocks (nested inside assistant message)
                            elif block_type == 'tool_use':
                                tool_name = block.get('name', 'unknown')
                                tool_input = block.get('input', {})
                                # Format tool input and explanation based on tool type
                                if tool_name == 'Bash':
                                    cmd = tool_input.get('command', '')
                                    desc = tool_input.get('description', '')
                                    output_str = f"{desc}\n{cmd}" if desc else cmd
                                    explanation = desc if desc else f"Running command: {cmd[:80]}"
                                elif tool_name == 'Read':
                                    file_path = tool_input.get('file_path', '')
                                    output_str = f"File: {file_path}"
                                    explanation = f"Reading file: {file_path.split('/')[-1] if file_path else 'unknown'}"
                                elif tool_name == 'Write':
                                    file_path = tool_input.get('file_path', '')
                                    output_str = f"File: {file_path}"
                                    explanation = f"Writing file: {file_path.split('/')[-1] if file_path else 'unknown'}"
                                elif tool_name == 'Edit':
                                    file_path = tool_input.get('file_path', '')
                                    output_str = f"File: {file_path}"
                                    explanation = f"Editing file: {file_path.split('/')[-1] if file_path else 'unknown'}"
                                elif tool_name == 'Glob':
                                    pattern = tool_input.get('pattern', '')
                                    output_str = f"Pattern: {pattern}"
                                    explanation = f"Searching for files: {pattern}"
                                elif tool_name == 'Grep':
                                    pattern = tool_input.get('pattern', '')
                                    path = tool_input.get('path', 'codebase')
                                    output_str = f"Search: {pattern} in {path}"
                                    explanation = f"Searching for: {pattern}"
                                elif tool_name == 'TodoWrite':
                                    output_str = str(tool_input)[:1000]
                                    explanation = "Updating task list"

                                    # Sync todos to ProjectTodoList
                                    try:
                                        from projects.models import ProjectTodoList
                                        todos = tool_input.get('todos', [])
                                        if todos and isinstance(todos, list):
                                            # Status mapping: Claude CLI -> ProjectTodoList
                                            status_map = {
                                                'completed': 'success',
                                                'in_progress': 'in_progress',
                                                'pending': 'pending'
                                            }

                                            # Get existing tasks for this ticket (keyed by cli_task_id)
                                            existing_tasks = {
                                                t.cli_task_id: t for t in
                                                ProjectTodoList.objects.filter(ticket_id=ticket.id)
                                                if t.cli_task_id
                                            }

                                            synced_task_ids = set()
                                            for idx, todo in enumerate(todos):
                                                cli_id = todo.get('id', str(idx))
                                                content = todo.get('content', '')
                                                status = status_map.get(todo.get('status', 'pending'), 'pending')

                                                if cli_id in existing_tasks:
                                                    # Update existing task
                                                    task = existing_tasks[cli_id]
                                                    task.description = content
                                                    task.status = status
                                                    task.order = idx
                                                    task.save(update_fields=['description', 'status', 'order', 'updated_at'])
                                                else:
                                                    # Create new task
                                                    task = ProjectTodoList.objects.create(
                                                        ticket_id=ticket.id,
                                                        description=content,
                                                        status=status,
                                                        order=idx,
                                                        cli_task_id=cli_id
                                                    )

                                                synced_task_ids.add(cli_id)

                                                # Broadcast task update
                                                try:
                                                    async_to_sync(async_send_ticket_log_notification)(ticket.id, {
                                                        'is_notification': True,
                                                        'notification_type': 'task_update',
                                                        'ticket_id': ticket.id,
                                                        'task': {
                                                            'id': task.id,
                                                            'content': task.description,
                                                            'status': task.status,
                                                            'order': task.order
                                                        }
                                                    })
                                                except Exception:
                                                    pass

                                            logger.info(f"[CLI CALLBACK] Synced {len(todos)} tasks to ProjectTodoList")
                                    except Exception as e:
                                        logger.warning(f"[CLI CALLBACK] Failed to sync todos: {e}")
                                elif tool_name == 'Task':
                                    output_str = str(tool_input)[:1000]
                                    explanation = tool_input.get('description', 'Running subtask')
                                else:
                                    output_str = str(tool_input)[:1000]
                                    explanation = f"Using tool: {tool_name}"

                                log_entry = TicketLog.objects.create(
                                    ticket_id=ticket.id,
                                    log_type='command',
                                    command=tool_name,
                                    explanation=explanation,
                                    output=output_str[:4000]
                                )
                                logs_created += 1
                                logger.info(f"[CLI CALLBACK] Created tool_use log: {tool_name}")

                            # Broadcast if log was created
                            if log_entry:
                                streamed_log_count[0] += 1
                                try:
                                    async_to_sync(async_send_ticket_log_notification)(ticket.id, {
                                        'id': log_entry.id,
                                        'log_type': log_entry.log_type,
                                        'command': log_entry.command,
                                        'explanation': log_entry.explanation or '',
                                        'output': log_entry.output,
                                        'created_at': log_entry.created_at.isoformat()
                                    })
                                except Exception as e:
                                    logger.warning(f"[CLI CALLBACK] Broadcast error: {e}")

                    # Handle user messages (which contain tool_result blocks)
                    elif msg_type == 'user':
                        content_blocks = msg.get('message', {}).get('content', [])
                        if not isinstance(content_blocks, list):
                            content_blocks = [content_blocks] if content_blocks else []

                        for block in content_blocks:
                            if not isinstance(block, dict):
                                continue

                            block_type = block.get('type')
                            log_entry = None

                            # Handle tool_result blocks (nested inside user message)
                            if block_type == 'tool_result':
                                result_content = str(block.get('content', ''))[:4000]
                                is_error = block.get('is_error', False)

                                # Only log significant results
                                if result_content and len(result_content) > 50:
                                    log_entry = TicketLog.objects.create(
                                        ticket_id=ticket.id,
                                        log_type='command',
                                        command='Result' + (' (Error)' if is_error else ''),
                                        explanation='Tool execution result',
                                        output=result_content
                                    )
                                    logs_created += 1
                                    logger.info(f"[CLI CALLBACK] Created tool_result log: {result_content[:50]}...")

                            # Broadcast if log was created
                            if log_entry:
                                streamed_log_count[0] += 1
                                try:
                                    async_to_sync(async_send_ticket_log_notification)(ticket.id, {
                                        'id': log_entry.id,
                                        'log_type': log_entry.log_type,
                                        'command': log_entry.command,
                                        'explanation': log_entry.explanation or '',
                                        'output': log_entry.output,
                                        'created_at': log_entry.created_at.isoformat()
                                    })
                                except Exception as e:
                                    logger.warning(f"[CLI CALLBACK] Broadcast error: {e}")

            logger.info(f"[CLI CALLBACK] Summary: {json_objects_found} JSON objects parsed, {logs_created} logs created")

        cli_result = run_claude_cli(
            workspace_id=workspace_id,
            prompt=implementation_prompt,
            timeout=max_execution_time,
            working_dir=f"/workspace/{project_dir}",
            project_id=str(project.project_id),
            poll_callback=stream_output_callback,
            lfg_env={
                'LFG_API_URL': api_base_url,
                'LFG_API_KEY': cli_api_key,
                'LFG_TICKET_ID': str(ticket.id),
                'LFG_PROJECT_ID': str(project.project_id)
            }
        )

        cli_duration = time.time() - cli_start
        logger.info(f"[CLI STEP 7/7] CLI completed in {cli_duration:.1f}s, streamed {streamed_log_count[0]} logs")

        # Check for auth errors and update profile if token expired
        # Be specific to avoid false positives (e.g., Claude mentioning "401" in conversation)
        cli_error = cli_result.get('error') or ''
        cli_stdout = cli_result.get('stdout') or ''

        is_auth_error = False
        if cli_error:
            error_lower = cli_error.lower()
            if any(ind in error_lower for ind in ['oauth token has expired', 'authentication_error', 'please run /login']):
                is_auth_error = True
        if not is_auth_error and cli_stdout:
            stdout_start = cli_stdout[:500].lower()
            if 'api error: 401' in stdout_start and ('authentication_error' in stdout_start or 'oauth token has expired' in stdout_start):
                is_auth_error = True

        if is_auth_error:
            logger.warning(f"[CLI] Auth error detected, marking profile as not authenticated")
            profile.claude_code_authenticated = False
            profile.save(update_fields=['claude_code_authenticated'])

            # Update ticket status
            ticket.status = 'failed'
            ticket.queue_status = 'none'
            ticket.save(update_fields=['status', 'queue_status'])

            return {
                "status": "auth_error",
                "ticket_id": ticket_id,
                "error": "Claude Code token expired. Please reconnect in Settings > Claude Code.",
                "auth_expired": True
            }

        # Save session_id and workspace_id for potential resume (allows chat replies to continue conversation)
        session_id = cli_result.get('session_id')
        if session_id:
            ticket.cli_session_id = session_id
            ticket.cli_workspace_id = workspace_id  # Track which workspace this session belongs to
            ticket.save(update_fields=['cli_session_id', 'cli_workspace_id'])
            logger.info(f"[CLI] Saved session_id: {session_id} for workspace {workspace_id}")

        # Only create logs from full output if streaming didn't capture any
        # (fallback for cases where streaming callback didn't work)
        if cli_result.get('messages') and streamed_log_count[0] == 0:
            logger.info(f"[CLI] No logs streamed, creating from full output as fallback")
            def broadcast_log(ticket_id, log_data):
                try:
                    async_to_sync(async_send_ticket_log_notification)(ticket_id, log_data)
                except Exception as e:
                    logger.warning(f"Broadcast failed: {e}")

            logs = create_ticket_logs_from_claude_output(
                ticket_id=ticket_id,
                parsed_output=cli_result,
                broadcast_func=broadcast_log
            )
            logger.info(f"[CLI STEP 7/7] Created {len(logs)} ticket logs from fallback")
        else:
            logger.info(f"[CLI STEP 7/7] Streamed {streamed_log_count[0]} logs during execution, skipping post-processing")

        # Check CLI result
        execution_time = time.time() - start_time
        stdout = cli_result.get('stdout', '')

        # Determine completion status
        completed = 'IMPLEMENTATION_STATUS: COMPLETE' in stdout
        failed = 'IMPLEMENTATION_STATUS: FAILED' in stdout or cli_result.get('status') == 'error'

        if not completed and not failed:
            # Check final_result from parsed output
            final_result = cli_result.get('final_result', '')
            if final_result:
                if 'COMPLETE' in str(final_result).upper():
                    completed = True
                elif 'FAILED' in str(final_result).upper():
                    failed = True

        # If still no status, mark as failed
        if not completed and not failed:
            logger.warning(f"[CLI] No explicit status found, marking as failed")
            failed = True

        logger.info(f"[CLI] Status - Completed: {completed} | Failed: {failed} | Time: {execution_time:.1f}s")

        # COMMIT AND PUSH
        commit_sha = None
        merge_status = None

        if is_ticket_cancelled(ticket_id):
            logger.info(f"[CLI] Ticket cancelled before commit")
            clear_ticket_cancellation_flag(ticket_id)
            ticket.status = 'open'
            ticket.save(update_fields=['status'])
            return {
                "status": "cancelled",
                "ticket_id": ticket_id,
                "message": "Cancelled before commit",
                "execution_time": f"{execution_time:.2f}s"
            }

        if completed and not failed and github_owner and github_repo and github_token and feature_branch_name:
            logger.info(f"\n[CLI COMMIT] Committing and pushing changes...")

            commit_message = f"feat: {ticket.name}\n\nImplemented ticket #{ticket_id} (via Claude Code CLI)\n\n{ticket.description[:200]}"
            commit_result = commit_and_push_changes(
                workspace_id, feature_branch_name, commit_message, ticket_id,
                stack=stack, github_token=github_token,
                github_owner=github_owner, github_repo=github_repo
            )

            if commit_result['status'] == 'success':
                commit_sha = commit_result.get('commit_sha')
                logger.info(f"[CLI COMMIT] ✓ Committed: {commit_sha}")

                ticket.github_commit_sha = commit_sha
                ticket.save(update_fields=['github_commit_sha'])

                # Merge to lfg-agent
                merge_result = merge_feature_to_lfg_agent(github_token, github_owner, github_repo, feature_branch_name)

                if merge_result['status'] == 'success':
                    logger.info(f"[CLI COMMIT] ✓ Merged to lfg-agent")
                    merge_status = 'merged'
                elif merge_result['status'] == 'conflict':
                    logger.warning(f"[CLI COMMIT] ⚠ Merge conflict, attempting resolution...")
                    resolution_result = resolve_merge_conflict(
                        workspace_id, feature_branch_name, ticket_id,
                        project.project_id, conversation_id, stack=stack
                    )
                    merge_status = 'merged' if resolution_result['status'] == 'success' else 'conflict'
                else:
                    merge_status = 'failed'

                ticket.github_merge_status = merge_status
                ticket.save(update_fields=['github_merge_status'])
            else:
                logger.error(f"[CLI COMMIT] ✗ Commit failed: {commit_result.get('message')}")

        # NOTE: Backup is NOT done after each ticket execution
        # Auth backup only happens during initial authentication in Settings
        # The Claude workspace persists between executions, so no backup needed

        # UPDATE TICKET STATUS
        if completed and not failed:
            logger.info(f"\n[CLI FINALIZE] ✓ SUCCESS - Marking as review")
            ticket.status = 'review'

            git_info = ""
            if github_owner and github_repo:
                repo_url = f"https://github.com/{github_owner}/{github_repo}"
                git_info = f"\nGitHub: {repo_url}"
                if feature_branch_name:
                    git_info += f"\nBranch: {feature_branch_name}"
                if commit_sha:
                    git_info += f"\nCommit: {commit_sha}"
                if merge_status:
                    merge_emoji = '✓' if merge_status == 'merged' else ('⚠' if merge_status == 'conflict' else '✗')
                    git_info += f"\nMerge: {merge_emoji} {merge_status}"

            ticket.notes = (ticket.notes or "") + f"""
---
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] ✅ IMPLEMENTATION COMPLETED (Claude Code CLI)
Execution time: {execution_time:.2f}s
CLI duration: {cli_duration:.2f}s{git_info}
"""
            ticket.execution_time_seconds = (ticket.execution_time_seconds or 0) + execution_time
            ticket.last_execution_at = datetime.now()
            ticket.save(update_fields=['status', 'notes', 'execution_time_seconds', 'last_execution_at'])

            broadcast_ticket_notification(conversation_id, {
                'is_notification': True,
                'notification_type': 'toolhistory',
                'function_name': 'ticket_execution',
                'status': 'completed',
                'message': f"✓ Completed ticket #{ticket.id} with Claude Code CLI",
                'ticket_id': ticket.id,
                'ticket_name': ticket.name,
                'queue_status': 'none',
                'refresh_checklist': True
            })

            broadcast_ticket_status_change(ticket_id, 'review', 'none')
            clear_ticket_cancellation_flag(ticket_id)

            return {
                "status": "success",
                "ticket_id": ticket_id,
                "ticket_name": ticket.name,
                "message": f"Completed with Claude Code CLI in {execution_time:.2f}s",
                "execution_time": f"{execution_time:.2f}s",
                "cli_duration": f"{cli_duration:.2f}s",
                "session_id": cli_result.get('session_id'),
                "workspace_id": workspace_id,
                "git": {
                    "repository": f"{github_owner}/{github_repo}" if github_owner else None,
                    "branch": feature_branch_name,
                    "commit_sha": commit_sha,
                    "merge_status": merge_status
                } if github_owner else None
            }
        else:
            # FAILED
            logger.warning(f"\n[CLI FINALIZE] ✗ FAILED - Marking as blocked")

            error_reason = cli_result.get('error') or 'No explicit completion status'
            if 'IMPLEMENTATION_STATUS: FAILED' in stdout:
                import re
                error_match = re.search(r'IMPLEMENTATION_STATUS: FAILED - (.+)', stdout)
                if error_match:
                    error_reason = error_match.group(1)

            # If stdout is small, it's likely the actual error message from CLI
            if stdout and len(stdout) < 500 and not stdout.startswith('{'):
                error_reason = f"CLI Error: {stdout.strip()}"

            # Log the raw output for debugging
            logger.warning(f"[CLI FINALIZE] Error reason: {error_reason}")
            logger.warning(f"[CLI FINALIZE] Raw stdout ({len(stdout)} bytes): {stdout[:500] if stdout else '(empty)'}")

            # Check if this is an auth-related error - if so, mark user as disconnected
            auth_error_keywords = ['not logged in', 'authentication', 'credential', 'login required', 'auth failed', 'unauthorized']
            is_auth_error = any(keyword in error_reason.lower() for keyword in auth_error_keywords)
            if is_auth_error:
                logger.warning(f"[CLI FINALIZE] Detected auth error - marking user as disconnected")
                profile = ticket.project.owner.profile
                profile.claude_code_authenticated = False
                profile.save(update_fields=['claude_code_authenticated'])

            ticket.status = 'blocked'
            ticket.queue_status = 'none'
            ticket.notes = (ticket.notes or "") + f"""
---
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] ❌ BLOCKED - Claude Code CLI Failed
Reason: {error_reason}
Execution time: {execution_time:.2f}s
Workspace: {workspace_id}
"""
            ticket.execution_time_seconds = (ticket.execution_time_seconds or 0) + execution_time
            ticket.last_execution_at = datetime.now()
            ticket.save(update_fields=['status', 'queue_status', 'notes', 'execution_time_seconds', 'last_execution_at'])

            # Create a TicketLog entry so the error shows in the Actions tab
            from projects.models import TicketLog
            error_log = TicketLog.objects.create(
                ticket=ticket,
                log_type='ai_response',
                command=f"Claude Code CLI Execution Failed",
                output=f"❌ **Execution Failed**\n\n**Reason:** {error_reason}\n\nCheck the Notes tab for more details."
            )
            logger.info(f"[CLI FINALIZE] Created error TicketLog {error_log.id}")

            # Broadcast the error log
            async_send_ticket_log_notification(ticket.id, error_log)

            broadcast_ticket_notification(conversation_id, {
                'is_notification': True,
                'notification_type': 'toolhistory',
                'function_name': 'ticket_execution',
                'status': 'failed',
                'message': f"✗ Claude Code CLI failed: {error_reason[:100]}",
                'ticket_id': ticket.id,
                'ticket_name': ticket.name,
                'queue_status': 'none',
                'refresh_checklist': True
            })

            broadcast_ticket_status_change(ticket_id, 'blocked', 'none', error_reason=error_reason)
            clear_ticket_cancellation_flag(ticket_id)

            return {
                "status": "failed",
                "ticket_id": ticket_id,
                "ticket_name": ticket.name,
                "error": error_reason,
                "cli_error": True,
                "execution_time": f"{execution_time:.2f}s",
                "workspace_id": workspace_id
            }

    except Exception as e:
        execution_time = time.time() - start_time
        error_msg = str(e)
        logger.error(f"\n{'='*80}\n[CLI EXCEPTION] Error in ticket {ticket_id}\n{'='*80}")
        logger.error(f"Error: {error_msg}", exc_info=True)

        if 'ticket' in locals():
            ticket.status = 'blocked'
            ticket.queue_status = 'none'
            ticket.notes = (ticket.notes or "") + f"""
---
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] ❌ BLOCKED - CLI Exception
Reason: {error_msg}
Execution time: {execution_time:.2f}s
Workspace: {workspace_id or 'N/A'}
"""
            ticket.execution_time_seconds = (ticket.execution_time_seconds or 0) + execution_time
            ticket.last_execution_at = datetime.now()
            ticket.save(update_fields=['status', 'queue_status', 'notes', 'execution_time_seconds', 'last_execution_at'])

            broadcast_ticket_notification(conversation_id, {
                'is_notification': True,
                'notification_type': 'toolhistory',
                'function_name': 'ticket_execution',
                'status': 'failed',
                'message': f"✗ CLI error: {error_msg[:100]}",
                'ticket_id': ticket.id,
                'ticket_name': ticket.name,
                'queue_status': 'none',
                'refresh_checklist': True
            })

        try:
            broadcast_ticket_status_change(ticket_id, 'blocked', 'none')
        except Exception:
            pass

        try:
            from tasks.dispatch import clear_ticket_cancellation_flag
            clear_ticket_cancellation_flag(ticket_id)
        except Exception:
            pass

        return {
            "status": "error",
            "ticket_id": ticket_id,
            "error": error_msg,
            "cli_error": True,
            "workspace_id": workspace_id,
            "execution_time": f"{execution_time:.2f}s"
        }


def execute_ticket_chat_cli(
    ticket_id: int,
    project_id: int,
    conversation_id: int,
    message: str,
    session_id: str = None
) -> Dict[str, Any]:
    """
    Run Claude CLI for ticket chat - either resume existing session or start new one.

    Args:
        ticket_id: The ticket ID
        project_id: The project ID
        conversation_id: The conversation ID for WebSocket notifications
        message: The user's chat message
        session_id: Optional session ID to resume (None = start new session)

    Returns:
        Dict with execution result
    """
    import time
    from projects.models import ProjectTicket, Project, TicketLog
    from accounts.models import Profile
    from development.models import MagpieWorkspace
    from factory.ai_functions import get_magpie_client
    from factory.claude_code_utils import run_claude_cli
    from projects.websocket_utils import async_send_ticket_log_notification
    from asgiref.sync import async_to_sync

    start_time = time.time()

    try:
        ticket = ProjectTicket.objects.select_related('project').get(id=ticket_id)
        project = ticket.project
        user = project.owner
        profile = Profile.objects.get(user=user)

        # Get Claude workspace
        claude_workspace = MagpieWorkspace.objects.filter(
            user=user,
            workspace_type='claude_auth',
            status='ready'
        ).first()

        # Check if we have S3 backup for auto-recovery
        from factory.ai_functions import get_magpie_client, MAGPIE_BOOTSTRAP_SCRIPT, _run_magpie_ssh
        from projects.websocket_utils import async_send_ticket_log_notification
        from asgiref.sync import async_to_sync

        client = get_magpie_client()
        workspace_id = None
        workspace_accessible = False

        # Test existing workspace if available
        if claude_workspace:
            workspace_id = claude_workspace.workspace_id
            try:
                test_result = _run_magpie_ssh(client, workspace_id, "echo 'WORKSPACE_OK'", timeout=15, with_node_env=False)
                if test_result.get('exit_code') == 0 and 'WORKSPACE_OK' in test_result.get('stdout', ''):
                    workspace_accessible = True
                    logger.info(f"[CLI_CHAT] Workspace {workspace_id} is accessible")

                    # Check if workspace matches the ticket's stored workspace
                    # If workspace_id not stored (old session) or doesn't match, clear session_id
                    if session_id:
                        if not ticket.cli_workspace_id:
                            # Old session without workspace tracking - can't verify, clear it
                            logger.info(f"[CLI_CHAT] Session has no workspace_id stored, clearing to start fresh")
                            session_id = None
                            ticket.cli_session_id = None
                            ticket.save(update_fields=['cli_session_id'])
                        elif ticket.cli_workspace_id != workspace_id:
                            # Workspace changed - session won't work
                            logger.info(f"[CLI_CHAT] Workspace changed: {ticket.cli_workspace_id} -> {workspace_id}, clearing old session")
                            session_id = None
                            ticket.cli_session_id = None
                            ticket.cli_workspace_id = None
                            ticket.save(update_fields=['cli_session_id', 'cli_workspace_id'])
            except Exception as e:
                logger.warning(f"[CLI_CHAT] Workspace {workspace_id} not accessible: {e}")
        else:
            logger.info(f"[CLI_CHAT] No workspace record found for user {user.id}")

        # If no workspace or not accessible, try to create new one and restore from S3
        if not workspace_accessible:
            # Check if we can recover from S3 backup
            if not profile.claude_code_s3_key:
                logger.error(f"[CLI_CHAT] No workspace and no S3 backup for ticket #{ticket_id}")
                error_log = TicketLog.objects.create(
                    ticket_id=ticket_id,
                    log_type='error',
                    command='Workspace Error',
                    explanation='No Claude Code credentials found',
                    output='Please go to Settings > Claude Code and click "Connect Claude Code" to set up your workspace.'
                )
                async_to_sync(async_send_ticket_log_notification)(ticket_id, {
                    'id': error_log.id,
                    'log_type': error_log.log_type,
                    'command': error_log.command,
                    'explanation': error_log.explanation,
                    'output': error_log.output,
                    'created_at': error_log.created_at.isoformat()
                })
                return {"status": "error", "error": "No Claude workspace. Please connect Claude Code in Settings."}

            logger.info(f"[CLI_CHAT] Creating new workspace and restoring from S3...")

            # Send notification to user
            setup_log = TicketLog.objects.create(
                ticket_id=ticket_id,
                log_type='system',
                command='Setting up environment',
                explanation='Creating new sandbox, restoring Claude Code credentials...',
                output='Please wait while we set up the environment.'
            )
            async_to_sync(async_send_ticket_log_notification)(ticket_id, {
                'id': setup_log.id,
                'log_type': setup_log.log_type,
                'command': setup_log.command,
                'explanation': setup_log.explanation,
                'output': setup_log.output,
                'created_at': setup_log.created_at.isoformat()
            })

            # Mark old workspace as error if it exists
            if claude_workspace:
                claude_workspace.status = 'error'
                claude_workspace.save(update_fields=['status'])

            # Create new workspace
            workspace_name = f"claude-auth-{user.id}"

            try:
                vm_handle = client.jobs.create_persistent_vm(
                    name=workspace_name,
                    script=MAGPIE_BOOTSTRAP_SCRIPT,
                    stateful=True,
                    workspace_size_gb=5,
                    vcpus=1,
                    memory_mb=1024,
                    poll_timeout=120,
                    poll_interval=5,
                )
                new_workspace_id = vm_handle.request_id
                ipv6 = vm_handle.ip_address

                if not new_workspace_id:
                    return {"status": "error", "error": "Failed to create new workspace"}

                # Delete old workspace records and create new one
                MagpieWorkspace.objects.filter(user=user, workspace_type='claude_auth').delete()
                claude_workspace = MagpieWorkspace.objects.create(
                    user=user,
                    workspace_type='claude_auth',
                    job_id=new_workspace_id,
                    workspace_id=new_workspace_id,
                    ipv6_address=ipv6,
                    status='ready'
                )
                workspace_id = new_workspace_id
                logger.info(f"[CLI_CHAT] Created new workspace: {workspace_id}")

                # Restore Claude credentials from S3 (we already verified S3 backup exists above)
                from factory.claude_code_utils import restore_claude_auth_from_s3
                restore_result = restore_claude_auth_from_s3(workspace_id, user.id, profile.claude_code_s3_key)
                if restore_result.get('status') == 'success':
                    logger.info(f"[CLI_CHAT] Restored Claude credentials from S3")
                else:
                    logger.warning(f"[CLI_CHAT] Failed to restore credentials: {restore_result.get('error')}")
                    return {"status": "error", "error": "Failed to restore Claude Code credentials. Please reconnect in Settings."}

                # Set up git repo in new workspace
                stack = project.stack or 'nextjs'
                stack_config = get_stack_config(stack, project)
                project_dir = stack_config.get('project_dir', 'nextjs-app')

                try:
                    from codebase_index.models import IndexedRepository
                    from accounts.models import GitHubToken
                    indexed_repo = IndexedRepository.objects.get(project=project)
                    github_token_obj = GitHubToken.objects.filter(user=user).first()

                    if indexed_repo and github_token_obj:
                        github_owner = indexed_repo.github_owner
                        github_repo = indexed_repo.github_repo_name
                        github_token = github_token_obj.access_token

                        git_setup_script = f"""
                        cd /workspace
                        rm -rf {project_dir}
                        git clone https://{github_token}@github.com/{github_owner}/{github_repo}.git {project_dir}
                        cd {project_dir}
                        git config --global --add safe.directory /workspace/{project_dir}
                        git checkout lfg-agent 2>/dev/null || git checkout -b lfg-agent origin/lfg-agent 2>/dev/null || git checkout main
                        git config user.email "ai@lfg.dev"
                        git config user.name "LFG AI"
                        echo "GIT_SETUP_COMPLETE"
                        """
                        git_result = _run_magpie_ssh(client, workspace_id, git_setup_script, timeout=120, with_node_env=False)
                        if 'GIT_SETUP_COMPLETE' in git_result.get('stdout', ''):
                            logger.info(f"[CLI_CHAT] Git repo cloned in new workspace")
                        else:
                            logger.warning(f"[CLI_CHAT] Git setup issue: {git_result.get('stdout', '')[:200]}")
                except Exception as e:
                    logger.warning(f"[CLI_CHAT] Git setup failed: {e}")

                # Clear the session_id since old session won't be valid in new workspace
                session_id = None
                ticket.cli_session_id = None
                ticket.cli_workspace_id = None  # Will be set when new session is created
                ticket.save(update_fields=['cli_session_id', 'cli_workspace_id'])
                logger.info(f"[CLI_CHAT] Cleared old session_id (new workspace {workspace_id})")

                # Update notification
                setup_log.output = 'Environment ready. Continuing with your request...'
                setup_log.save(update_fields=['output'])
                async_to_sync(async_send_ticket_log_notification)(ticket_id, {
                    'id': setup_log.id,
                    'log_type': setup_log.log_type,
                    'command': setup_log.command,
                    'explanation': setup_log.explanation,
                    'output': setup_log.output,
                    'created_at': setup_log.created_at.isoformat()
                })

            except Exception as e:
                logger.error(f"[CLI_CHAT] Failed to create new workspace: {e}")
                return {"status": "error", "error": f"Failed to create sandbox: {str(e)}"}

        # Note: User message log is created by the caller (api/views.py) before calling this function
        # This prevents duplicate messages from appearing in the UI

        # Get stack config for working directory
        stack = project.stack or 'nextjs'
        stack_config = get_stack_config(stack, project)
        project_dir = stack_config.get('project_dir', 'nextjs-app')

        # Ensure project directory exists in workspace (handles VM re-provisioning, workspace resets)
        try:
            dir_check = _run_magpie_ssh(client, workspace_id, f"ls -d /workspace/{project_dir}/.git 2>/dev/null && echo DIR_EXISTS || echo DIR_MISSING", timeout=10, with_node_env=False)
            dir_stdout = dir_check.get('stdout', '')

            if 'DIR_MISSING' in dir_stdout or 'DIR_EXISTS' not in dir_stdout:
                logger.info(f"[CLI_CHAT] Project directory /workspace/{project_dir} missing, setting up git repo...")

                # Send notification to user
                setup_code_log = TicketLog.objects.create(
                    ticket_id=ticket_id,
                    log_type='system',
                    command='Project Setup',
                    explanation='Setting up project code in workspace...',
                    output='Cloning repository and checking out branch...'
                )
                async_to_sync(async_send_ticket_log_notification)(ticket_id, {
                    'id': setup_code_log.id,
                    'log_type': setup_code_log.log_type,
                    'command': setup_code_log.command,
                    'explanation': setup_code_log.explanation,
                    'output': setup_code_log.output,
                    'created_at': setup_code_log.created_at.isoformat()
                })

                # Get GitHub repo info and token
                from codebase_index.models import IndexedRepository
                from accounts.models import GitHubToken
                indexed_repo = IndexedRepository.objects.filter(project=project).first()
                github_token_obj = GitHubToken.objects.filter(user=user).first()

                if indexed_repo and github_token_obj:
                    branch_name = ticket.github_branch or 'main'
                    git_result = setup_git_in_workspace(
                        workspace_id=workspace_id,
                        owner=indexed_repo.github_owner,
                        repo_name=indexed_repo.github_repo_name,
                        branch_name=branch_name,
                        token=github_token_obj.access_token,
                        stack=stack
                    )
                    if git_result.get('status') == 'success':
                        logger.info(f"[CLI_CHAT] Project code restored successfully on branch {branch_name}")
                    else:
                        logger.warning(f"[CLI_CHAT] Git setup returned: {git_result.get('message', 'unknown error')}")
                else:
                    logger.warning(f"[CLI_CHAT] Cannot restore project code: missing IndexedRepository or GitHubToken")

                # Project dir was missing → VM was likely reset, old CLI session is gone too
                if session_id:
                    logger.info(f"[CLI_CHAT] Clearing stale session_id (project dir was missing, VM likely reset)")
                    session_id = None
                    ticket.cli_session_id = None
                    ticket.save(update_fields=['cli_session_id'])
            else:
                # Directory exists - ensure correct branch is checked out
                branch_name = ticket.github_branch
                if branch_name:
                    import shlex
                    escaped_branch = shlex.quote(branch_name)
                    branch_check = _run_magpie_ssh(
                        client, workspace_id,
                        f"cd /workspace/{project_dir} && git rev-parse --abbrev-ref HEAD",
                        timeout=10, with_node_env=False
                    )
                    current_branch = branch_check.get('stdout', '').strip()
                    if current_branch and current_branch != branch_name:
                        logger.info(f"[CLI_CHAT] Switching branch from {current_branch} to {branch_name}")
                        _run_magpie_ssh(
                            client, workspace_id,
                            f"cd /workspace/{project_dir} && git fetch origin && git checkout {escaped_branch} 2>/dev/null || git checkout -b {escaped_branch} origin/{escaped_branch}",
                            timeout=30, with_node_env=False
                        )
        except Exception as e:
            logger.warning(f"[CLI_CHAT] Project directory check failed: {e}")

        # Streaming callback for real-time logs
        def stream_callback(new_output: str):
            import json
            for line in new_output.strip().split('\n'):
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                    msg_type = msg.get('type', '')

                    if msg_type == 'assistant':
                        content_blocks = msg.get('message', {}).get('content', [])
                        if not isinstance(content_blocks, list):
                            content_blocks = [content_blocks] if content_blocks else []

                        for block in content_blocks:
                            if not isinstance(block, dict):
                                continue
                            block_type = block.get('type')
                            log_entry = None

                            if block_type == 'text':
                                text = block.get('text', '')
                                if text and len(text) > 10:
                                    log_entry = TicketLog.objects.create(
                                        ticket_id=ticket_id,
                                        log_type='ai_response',
                                        command='Claude CLI Response',
                                        output=text[:4000]
                                    )

                            elif block_type == 'tool_use':
                                tool_name = block.get('name', 'unknown')
                                tool_input = block.get('input', {})
                                explanation = f"Using tool: {tool_name}"

                                if tool_name == 'Bash':
                                    output_str = tool_input.get('command', '')
                                elif tool_name in ['Read', 'Write', 'Edit']:
                                    output_str = f"File: {tool_input.get('file_path', '')}"
                                elif tool_name == 'TodoWrite':
                                    output_str = str(tool_input)[:1000]
                                    explanation = "Updating task list"

                                    # Sync todos to ProjectTodoList
                                    try:
                                        from projects.models import ProjectTodoList
                                        todos = tool_input.get('todos', [])
                                        if todos and isinstance(todos, list):
                                            status_map = {
                                                'completed': 'success',
                                                'in_progress': 'in_progress',
                                                'pending': 'pending'
                                            }
                                            existing_tasks = {
                                                t.cli_task_id: t for t in
                                                ProjectTodoList.objects.filter(ticket_id=ticket_id)
                                                if t.cli_task_id
                                            }
                                            for idx, todo in enumerate(todos):
                                                cli_id = todo.get('id', str(idx))
                                                content = todo.get('content', '')
                                                status = status_map.get(todo.get('status', 'pending'), 'pending')

                                                if cli_id in existing_tasks:
                                                    task = existing_tasks[cli_id]
                                                    task.description = content
                                                    task.status = status
                                                    task.order = idx
                                                    task.save(update_fields=['description', 'status', 'order', 'updated_at'])
                                                else:
                                                    task = ProjectTodoList.objects.create(
                                                        ticket_id=ticket_id,
                                                        description=content,
                                                        status=status,
                                                        order=idx,
                                                        cli_task_id=cli_id
                                                    )

                                                # Broadcast task update
                                                try:
                                                    async_to_sync(async_send_ticket_log_notification)(ticket_id, {
                                                        'is_notification': True,
                                                        'notification_type': 'task_update',
                                                        'ticket_id': ticket_id,
                                                        'task': {
                                                            'id': task.id,
                                                            'content': task.description,
                                                            'status': task.status,
                                                            'order': task.order
                                                        }
                                                    })
                                                except Exception:
                                                    pass
                                            logger.info(f"[CLI_CHAT] Synced {len(todos)} tasks to ProjectTodoList")
                                    except Exception as e:
                                        logger.warning(f"[CLI_CHAT] Failed to sync todos: {e}")
                                else:
                                    output_str = str(tool_input)[:1000]

                                log_entry = TicketLog.objects.create(
                                    ticket_id=ticket_id,
                                    log_type='command',
                                    command=tool_name,
                                    explanation=explanation,
                                    output=output_str[:4000]
                                )

                            if log_entry:
                                try:
                                    async_to_sync(async_send_ticket_log_notification)(ticket_id, {
                                        'id': log_entry.id,
                                        'log_type': log_entry.log_type,
                                        'command': log_entry.command,
                                        'explanation': log_entry.explanation or '',
                                        'output': log_entry.output or '',
                                        'created_at': log_entry.created_at.isoformat()
                                    })
                                except Exception:
                                    pass

                    elif msg_type == 'user':
                        # Handle tool_result blocks inside user messages
                        content_blocks = msg.get('message', {}).get('content', [])
                        if not isinstance(content_blocks, list):
                            content_blocks = [content_blocks] if content_blocks else []

                        for block in content_blocks:
                            if isinstance(block, dict) and block.get('type') == 'tool_result':
                                result_content = str(block.get('content', ''))[:4000]
                                if result_content and len(result_content) > 50:
                                    log_entry = TicketLog.objects.create(
                                        ticket_id=ticket_id,
                                        log_type='command',
                                        command='Result',
                                        explanation='Tool execution result',
                                        output=result_content
                                    )
                                    try:
                                        async_to_sync(async_send_ticket_log_notification)(ticket_id, {
                                            'id': log_entry.id,
                                            'log_type': log_entry.log_type,
                                            'command': log_entry.command,
                                            'explanation': log_entry.explanation or '',
                                            'output': log_entry.output,
                                            'created_at': log_entry.created_at.isoformat()
                                        })
                                    except Exception:
                                        pass

                except json.JSONDecodeError:
                    pass
                except Exception:
                    pass

        if session_id:
            logger.info(f"[CLI_CHAT] Running CLI with --resume {session_id[:20]}...")
        else:
            logger.info(f"[CLI_CHAT] Running CLI with new session for ticket #{ticket_id}")

        # Build prompt with ticket context for new sessions
        if not session_id:
            # For new sessions, include ticket context
            prompt_with_context = f"""You are helping with ticket #{ticket.id}: {ticket.name}

TICKET DESCRIPTION:
{ticket.description}

PROJECT: {project.name}
WORKING DIRECTORY: /workspace/{project_dir}

USER MESSAGE:
{message}

Please respond to the user's message in the context of this ticket."""
        else:
            # For resume sessions, just send the user message
            prompt_with_context = message

        # Run Claude CLI (session_id=None starts new session, otherwise resumes)
        cli_result = run_claude_cli(
            workspace_id=workspace_id,
            prompt=prompt_with_context,
            session_id=session_id,  # None = new session, otherwise --resume
            timeout=600,  # 10 minute timeout for chat
            working_dir=f"/workspace/{project_dir}",
            poll_callback=stream_callback
        )

        # Check for auth errors and update profile if token expired
        # Be specific to avoid false positives (e.g., Claude mentioning "401" in conversation)
        cli_error = cli_result.get('error') or ''
        cli_stdout = cli_result.get('stdout') or ''

        is_auth_error = False
        if cli_error:
            error_lower = cli_error.lower()
            if any(ind in error_lower for ind in ['oauth token has expired', 'authentication_error', 'please run /login']):
                is_auth_error = True
        if not is_auth_error and cli_stdout:
            stdout_start = cli_stdout[:500].lower()
            if 'api error: 401' in stdout_start and ('authentication_error' in stdout_start or 'oauth token has expired' in stdout_start):
                is_auth_error = True

        if is_auth_error:
            logger.warning(f"[CLI_CHAT] Auth error detected, marking profile as not authenticated")
            profile.claude_code_authenticated = False
            profile.save(update_fields=['claude_code_authenticated'])

            # Send notification to user
            auth_error_log = TicketLog.objects.create(
                ticket_id=ticket_id,
                log_type='error',
                command='Authentication Error',
                explanation='Claude Code token has expired',
                output='Your Claude Code session has expired. Please go to Settings > Claude Code and click "Disconnect" then reconnect.'
            )
            async_to_sync(async_send_ticket_log_notification)(ticket_id, {
                'id': auth_error_log.id,
                'log_type': auth_error_log.log_type,
                'command': auth_error_log.command,
                'explanation': auth_error_log.explanation,
                'output': auth_error_log.output,
                'created_at': auth_error_log.created_at.isoformat()
            })

            return {
                "status": "auth_error",
                "ticket_id": ticket_id,
                "error": "Claude Code token expired. Please reconnect in Settings.",
                "auth_expired": True
            }

        # Check for "No conversation found" error - this means session_id was invalid
        # Don't save the new session from the error response
        cli_stdout = cli_result.get('stdout') or ''
        session_not_found = 'No conversation found with session ID' in cli_stdout

        if session_not_found:
            logger.warning(f"[CLI_CHAT] Session not found error - clearing session_id")
            ticket.cli_session_id = None
            ticket.cli_workspace_id = None
            ticket.save(update_fields=['cli_session_id', 'cli_workspace_id'])

            # Notify user to retry - use 'error' log type to hide typing indicator
            retry_log = TicketLog.objects.create(
                ticket_id=ticket_id,
                log_type='error',
                command='Session Reset',
                explanation='Previous conversation session was not found (workspace may have been recreated)',
                output='Please send your message again to start a new conversation.'
            )
            async_to_sync(async_send_ticket_log_notification)(ticket_id, {
                'id': retry_log.id,
                'log_type': retry_log.log_type,
                'command': retry_log.command,
                'explanation': retry_log.explanation,
                'output': retry_log.output,
                'created_at': retry_log.created_at.isoformat()
            })
        else:
            # Save session_id and workspace_id for future resume
            new_session_id = cli_result.get('session_id')
            if new_session_id:
                ticket.cli_session_id = new_session_id
                ticket.cli_workspace_id = workspace_id  # Track which workspace this session belongs to
                ticket.save(update_fields=['cli_session_id', 'cli_workspace_id'])
                logger.info(f"[CLI_CHAT] Saved session_id: {new_session_id[:20]}... for workspace {workspace_id}")

        # Check for uncommitted changes and auto-commit if there are any
        commit_sha = None
        try:
            from accounts.models import GitHubToken
            from codebase_index.models import IndexedRepository
            from factory.ai_functions import _run_magpie_ssh

            client = get_magpie_client()

            # Add safe.directory to prevent "dubious ownership" errors
            # This happens because repo may be owned by root but we run git as different user
            _run_magpie_ssh(
                client,
                workspace_id,
                f"git config --global --add safe.directory /workspace/{project_dir} 2>/dev/null || true",
                timeout=10,
                with_node_env=False
            )

            # Check if there are uncommitted changes
            git_status_result = _run_magpie_ssh(
                client,
                workspace_id,
                f"cd /workspace/{project_dir} && git status --porcelain",
                timeout=30,
                with_node_env=False
            )

            # Only check for changes if git command succeeded
            git_exit_code = git_status_result.get('exit_code', 1)
            git_failed = False
            has_uncommitted_changes = False
            has_unpushed_commits = False

            if git_exit_code != 0:
                git_stderr = git_status_result.get('stderr', '')
                logger.warning(f"[CLI_CHAT] Git status failed (exit_code={git_exit_code}): {git_stderr[:200]}")
                git_failed = True
            else:
                has_uncommitted_changes = bool(git_status_result.get('stdout', '').strip())

            # Also check for unpushed commits (Claude CLI may have committed but not pushed)
            # Compare local HEAD with remote branch - if different (or remote doesn't exist), need to push
            if not git_failed and ticket.github_branch:
                unpushed_result = _run_magpie_ssh(
                    client,
                    workspace_id,
                    f"""cd /workspace/{project_dir} && git fetch origin 2>/dev/null
LOCAL_HEAD=$(git rev-parse HEAD 2>/dev/null)
REMOTE_HEAD=$(git rev-parse origin/{ticket.github_branch} 2>/dev/null || echo "REMOTE_NOT_FOUND")
if [ "$LOCAL_HEAD" != "$REMOTE_HEAD" ]; then
    echo "NEEDS_PUSH: local=$LOCAL_HEAD remote=$REMOTE_HEAD"
    git log origin/{ticket.github_branch}..HEAD --oneline 2>/dev/null || echo "New branch - all commits unpushed"
fi""",
                    timeout=30,
                    with_node_env=False
                )
                unpushed_stdout = unpushed_result.get('stdout', '').strip()
                has_unpushed_commits = 'NEEDS_PUSH' in unpushed_stdout
                if has_unpushed_commits:
                    logger.info(f"[CLI_CHAT] Found unpushed commits: {unpushed_stdout[:300]}")

            # Need to push if there are uncommitted changes OR unpushed commits
            has_changes = has_uncommitted_changes or has_unpushed_commits

            if has_uncommitted_changes:
                logger.info(f"[CLI_CHAT] Uncommitted changes detected, will commit and push...")
            elif has_unpushed_commits:
                logger.info(f"[CLI_CHAT] Unpushed commits detected, will push...")

            if has_changes:
                logger.info(f"[CLI_CHAT] Changes detected, auto-committing...")

                # Get GitHub credentials
                indexed_repo = getattr(project, 'indexed_repository', None)
                github_token_obj = GitHubToken.objects.filter(user=user).first()
                github_token = github_token_obj.access_token if github_token_obj else None

                # If ticket has no branch but we have GitHub configured, set up the branch now
                if not ticket.github_branch and indexed_repo and github_token:
                    logger.info(f"[CLI_CHAT] No branch set, creating feature branch...")
                    feature_branch_name = f"feature/ticket-{ticket.id}"
                    github_owner = indexed_repo.github_owner
                    github_repo = indexed_repo.github_repo_name

                    # Set up git branch in workspace
                    branch_setup_script = f"""
                    cd /workspace/{project_dir}
                    git fetch origin 2>/dev/null || true
                    # Try to checkout existing branch, or create from lfg-agent
                    git checkout {feature_branch_name} 2>/dev/null || git checkout -b {feature_branch_name} 2>/dev/null || echo "BRANCH_SETUP_FAILED"
                    git branch --show-current
                    """
                    branch_result = _run_magpie_ssh(client, workspace_id, branch_setup_script, timeout=60, with_node_env=False)
                    branch_stdout = branch_result.get('stdout', '').strip()

                    if feature_branch_name in branch_stdout or 'BRANCH_SETUP_FAILED' not in branch_stdout:
                        ticket.github_branch = feature_branch_name
                        ticket.github_merge_status = 'pending'
                        ticket.save(update_fields=['github_branch', 'github_merge_status'])
                        logger.info(f"[CLI_CHAT] Created and saved branch: {feature_branch_name}")
                    else:
                        logger.warning(f"[CLI_CHAT] Failed to set up branch: {branch_stdout[:200]}")

                # Debug log to show what's missing
                logger.info(f"[CLI_CHAT] Commit check: indexed_repo={indexed_repo is not None}, "
                           f"github_token={github_token is not None}, "
                           f"github_branch={ticket.github_branch}")

                if indexed_repo and github_token and ticket.github_branch:
                    github_owner = indexed_repo.github_owner
                    github_repo = indexed_repo.github_repo_name

                    # Build commit message
                    short_message = message[:100] + ('...' if len(message) > 100 else '')
                    commit_message = f"chore(chat): Changes from chat session - TKT-{ticket.id}\n\nUser request: {short_message}"

                    # Call commit_and_push_changes
                    commit_result = commit_and_push_changes(
                        workspace_id,
                        ticket.github_branch,
                        commit_message,
                        ticket.id,
                        stack=stack,
                        github_token=github_token,
                        github_owner=github_owner,
                        github_repo=github_repo
                    )

                    # Log the commit
                    if commit_result.get('status') == 'success':
                        commit_sha = commit_result.get('commit_sha', 'unknown')
                        commit_log = TicketLog.objects.create(
                            ticket_id=ticket_id,
                            log_type='git',
                            command='git commit & push',
                            explanation='Auto-committed changes from chat',
                            output=f"Committed: {commit_sha} on branch {ticket.github_branch}"
                        )
                        async_to_sync(async_send_ticket_log_notification)(ticket_id, {
                            'id': commit_log.id,
                            'log_type': commit_log.log_type,
                            'command': commit_log.command,
                            'explanation': commit_log.explanation,
                            'output': commit_log.output,
                            'created_at': commit_log.created_at.isoformat()
                        })
                        logger.info(f"[CLI_CHAT] Auto-committed changes: {commit_sha}")

                        # Merge feature branch to lfg-agent
                        logger.info(f"[CLI_CHAT] Merging {ticket.github_branch} to lfg-agent...")
                        merge_result = merge_feature_to_lfg_agent(github_token, github_owner, github_repo, ticket.github_branch)
                        merge_status = merge_result.get('status')

                        if merge_status == 'success':
                            merge_log = TicketLog.objects.create(
                                ticket_id=ticket_id,
                                log_type='git',
                                command='git merge to lfg-agent',
                                explanation='Merged feature branch to lfg-agent',
                                output=f"Merged {ticket.github_branch} → lfg-agent"
                            )
                            async_to_sync(async_send_ticket_log_notification)(ticket_id, {
                                'id': merge_log.id,
                                'log_type': merge_log.log_type,
                                'command': merge_log.command,
                                'explanation': merge_log.explanation,
                                'output': merge_log.output,
                                'created_at': merge_log.created_at.isoformat()
                            })
                            logger.info(f"[CLI_CHAT] Merged to lfg-agent: {merge_result.get('merge_commit_sha', 'success')}")
                            ticket.github_merge_status = 'merged'
                        elif merge_status == 'conflict':
                            logger.warning(f"[CLI_CHAT] Merge conflict detected")
                            ticket.github_merge_status = 'conflict'
                            # Try to resolve conflicts
                            try:
                                resolution_result = resolve_merge_conflict(
                                    workspace_id, ticket.github_branch, ticket_id,
                                    project.project_id, None, stack=stack
                                )
                                if resolution_result.get('status') == 'success':
                                    logger.info(f"[CLI_CHAT] Conflicts resolved automatically")
                                    ticket.github_merge_status = 'merged'
                            except Exception as e:
                                logger.warning(f"[CLI_CHAT] Could not resolve conflicts: {e}")
                        else:
                            logger.warning(f"[CLI_CHAT] Merge failed: {merge_result.get('message')}")
                            ticket.github_merge_status = 'failed'

                        ticket.save(update_fields=['github_merge_status'])
                    else:
                        logger.warning(f"[CLI_CHAT] Auto-commit failed: {commit_result.get('message')}")
                else:
                    # Log exactly what's missing
                    missing = []
                    if not indexed_repo:
                        missing.append("indexed_repo (project not linked to GitHub)")
                    if not github_token:
                        missing.append("github_token (no GitHub token found)")
                    if not ticket.github_branch:
                        missing.append("github_branch (ticket has no branch)")
                    logger.warning(f"[CLI_CHAT] Cannot commit - missing: {', '.join(missing)}")
            elif not git_failed:
                logger.info(f"[CLI_CHAT] No changes to commit")
        except Exception as e:
            logger.warning(f"[CLI_CHAT] Auto-commit check failed: {e}")

        execution_time = time.time() - start_time
        logger.info(f"[CLI_CHAT] Completed in {execution_time:.1f}s")

        # Check if CLI returned an error that we haven't already handled
        # This ensures the UI always gets notified to hide the typing indicator
        if cli_result.get('status') == 'error' and not session_not_found and not is_auth_error:
            error_msg = cli_result.get('error') or 'Unknown error occurred'
            general_error_log = TicketLog.objects.create(
                ticket_id=ticket_id,
                log_type='error',
                command='CLI Error',
                explanation='Claude CLI encountered an error',
                output=error_msg[:1000]
            )
            async_to_sync(async_send_ticket_log_notification)(ticket_id, {
                'id': general_error_log.id,
                'log_type': general_error_log.log_type,
                'command': general_error_log.command,
                'explanation': general_error_log.explanation,
                'output': general_error_log.output,
                'created_at': general_error_log.created_at.isoformat()
            })

        return {
            "status": "success" if cli_result.get('status') == 'success' else "error",
            "ticket_id": ticket_id,
            "session_id": cli_result.get('session_id') if not session_not_found else None,
            "execution_time": f"{execution_time:.2f}s",
            "commit_sha": commit_sha
        }

    except Exception as e:
        logger.error(f"[CLI_CHAT] Error: {e}", exc_info=True)
        return {
            "status": "error",
            "ticket_id": ticket_id,
            "error": str(e)
        }


def batch_execute_tickets(ticket_ids: List[int], project_id: int, conversation_id: int) -> Dict[str, Any]:
    """
    Execute multiple tickets in sequence for a single project.

    NOTE: This function executes tickets SYNCHRONOUSLY (one after another).
    For the same project, tickets always execute sequentially.
    Different projects can execute in parallel if workers > 1.

    Args:
        ticket_ids: List of ticket IDs to execute
        project_id: The project ID (database ID, not UUID)
        conversation_id: The conversation ID

    Returns:
        Dict with batch execution results
    """
    results = []

    broadcast_ticket_notification(conversation_id, {
        'is_notification': True,
        'notification_type': 'toolhistory',
        'function_name': 'ticket_execution_queue',
        'status': 'queued',
        'message': f"Starting background execution for {len(ticket_ids)} tickets.",
        'refresh_checklist': bool(ticket_ids)
    })

    for index, ticket_id in enumerate(ticket_ids, start=1):
        broadcast_ticket_notification(conversation_id, {
            'is_notification': True,
            'notification_type': 'toolhistory',
            'function_name': 'ticket_execution_queue',
            'status': 'in_progress',
            'message': f"Executing ticket {index}/{len(ticket_ids)} (#{ticket_id}).",
            'ticket_id': ticket_id,
            'refresh_checklist': True
        })

        result = execute_ticket_implementation(ticket_id, project_id, conversation_id)
        results.append(result)

        broadcast_ticket_notification(conversation_id, {
            'is_notification': True,
            'notification_type': 'toolhistory',
            'function_name': 'ticket_execution_queue',
            'status': result.get('status'),
            'message': f"Ticket #{ticket_id} finished with status: {result.get('status')}",
            'ticket_id': ticket_id,
            'refresh_checklist': True
        })
        
        if result.get("status") == "error":
            break
    
    failed_tickets = len([r for r in results if r.get("status") in {"error", "failed", "timeout"}])
    broadcast_ticket_notification(conversation_id, {
        'is_notification': True,
        'notification_type': 'toolhistory',
        'function_name': 'ticket_execution_queue',
        'status': 'completed' if failed_tickets == 0 else 'partial',
        'message': f"Ticket execution batch finished. Success: {len([r for r in results if r.get('status') == 'success'])}, Issues: {failed_tickets}.",
        'refresh_checklist': True
    })

    return {
        "batch_status": "completed" if failed_tickets == 0 else "partial",
        "total_tickets": len(ticket_ids),
        "completed_tickets": len([r for r in results if r.get("status") == "success"]),
        "failed_tickets": failed_tickets,
        "results": results
    }


def ensure_workspace_and_execute(ticket_ids: List[int], project_db_id: int, conversation_id: Optional[int]) -> Dict[str, Any]:
    try:
        project = Project.objects.get(id=project_db_id)
    except Project.DoesNotExist:
        return {
            "status": "error",
            "message": f"Project with id {project_db_id} does not exist"
        }

    broadcast_ticket_notification(conversation_id, {
        'is_notification': True,
        'notification_type': 'toolhistory',
        'function_name': 'ticket_execution_queue',
        'status': 'queued',
        'message': "Ensuring Magpie workspace is available...",
        'refresh_checklist': bool(ticket_ids)
    })

    # Get or create workspace
    workspace = None
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        workspace = loop.run_until_complete(_fetch_workspace(project=project, conversation_id=conversation_id))

        if not workspace:
            # Create new Magpie workspace
            try:
                client = get_magpie_client()
                project_name = project.provided_name or project.name
                slug = _slugify_project_name(project_name)
                workspace_name = f"{slug}-{project.id}"

                vm_handle = client.jobs.create_persistent_vm(
                    name=workspace_name,
                    script=MAGPIE_BOOTSTRAP_SCRIPT,
                    stateful=True,
                    workspace_size_gb=10,
                    vcpus=2,
                    memory_mb=2048,
                    poll_timeout=180,
                    poll_interval=5,
                )
                logger.info(f"[MAGPIE][CREATE] vm_handle: {vm_handle}")

                run_id = vm_handle.request_id
                workspace_identifier = run_id
                ipv6 = vm_handle.ip_address

                if not ipv6:
                    raise Exception(f"VM provisioning timed out - no IP address received")

                workspace = MagpieWorkspace.objects.create(
                    project=project,
                    conversation_id=str(conversation_id) if conversation_id else None,
                    job_id=run_id,
                    workspace_id=workspace_identifier,
                    status='ready',
                    ipv6_address=ipv6,
                    project_path='/workspace',
                    metadata={'project_name': project_name}
                )
                logger.info(f"[MAGPIE][READY] Workspace ready: {workspace.workspace_id}, IP: {ipv6}")
            except Exception as e:
                broadcast_ticket_notification(conversation_id, {
                    'is_notification': True,
                    'notification_type': 'toolhistory',
                    'function_name': 'ticket_execution_queue',
                    'status': 'failed',
                    'message': f"Workspace provisioning failed: {str(e)}",
                    'refresh_checklist': False
                })
                return {
                    "status": "error",
                    "message": f"Workspace provisioning failed: {str(e)}"
                }

        # Setup dev sandbox
        sandbox_result = loop.run_until_complete(
            new_dev_sandbox_tool(
                {'workspace_id': workspace.workspace_id},
                project.project_id,
                conversation_id
            )
        )
    finally:
        asyncio.set_event_loop(None)
        loop.close()

    if isinstance(sandbox_result, dict) and sandbox_result.get('status') == 'failed':
        broadcast_ticket_notification(conversation_id, {
            'is_notification': True,
            'notification_type': 'toolhistory',
            'function_name': 'ticket_execution_queue',
            'status': 'failed',
            'message': f"Dev sandbox setup failed: {sandbox_result.get('message_to_agent') or sandbox_result.get('message')}",
            'refresh_checklist': False
        })
        return {
            "status": "error",
            "message": sandbox_result.get('message_to_agent') or sandbox_result.get('message') or 'Dev sandbox setup failed'
        }

    broadcast_ticket_notification(conversation_id, {
        'is_notification': True,
        'notification_type': 'toolhistory',
        'function_name': 'ticket_execution_queue',
        'status': 'completed',
        'message': "Workspace ready. Beginning ticket execution...",
        'refresh_checklist': False
    })

    return batch_execute_tickets(ticket_ids, project_db_id, conversation_id)


def check_ticket_dependencies(ticket_id: int) -> bool:
    """
    Check if all dependencies for a ticket are completed.
    
    Args:
        ticket_id: The ticket ID to check
        
    Returns:
        bool: True if all dependencies are met, False otherwise
    """
    from projects.models import ProjectTicket
    
    try:
        ticket = ProjectTicket.objects.get(id=ticket_id)
        
        # For now, we'll implement a simple priority-based dependency
        # High priority tickets should be done before medium/low
        if ticket.priority.lower() in ['medium', 'low']:
            # Check if there are any high priority tickets still pending
            high_priority_pending = ProjectTicket.objects.filter(
                project=ticket.project,
                status='open',
                priority='High',
                role='agent'
            ).exists()
            
            if high_priority_pending:
                return False
        
        return True
        
    except ProjectTicket.DoesNotExist:
        return False


def monitor_ticket_progress(project_id: int) -> Dict[str, Any]:
    """
    Monitor the progress of all tickets in a project.
    
    Args:
        project_id: The project ID
        
    Returns:
        Dict with project ticket statistics
    """
    from projects.models import ProjectTicket
    
    tickets = ProjectTicket.objects.filter(project_id=project_id)
    
    stats = {
        "total_tickets": tickets.count(),
        "open_tickets": tickets.filter(status='open').count(),
        "in_progress_tickets": tickets.filter(status='in_progress').count(),
        "done_tickets": tickets.filter(status='done').count(),
        "failed_tickets": tickets.filter(status='failed').count(),
        "agent_tickets": tickets.filter(role='agent').count(),
        "user_tickets": tickets.filter(role='user').count(),
        "by_priority": {
            "high": tickets.filter(priority='High').count(),
            "medium": tickets.filter(priority='Medium').count(),
            "low": tickets.filter(priority='Low').count()
        }
    }
    
    return stats


def parallel_ticket_executor(project_id: int, conversation_id: int, max_workers: int = 3) -> Dict[str, Any]:
    """
    Execute multiple independent tickets in parallel using Django-Q.
    
    This function identifies tickets that can be run in parallel (no dependencies)
    and queues them for concurrent execution.
    
    Args:
        project_id: The project ID
        conversation_id: The conversation ID
        max_workers: Maximum number of parallel workers
        
    Returns:
        Dict with parallel execution status
    """
    from projects.models import ProjectTicket
    from tasks.task_manager import TaskManager
    
    task_manager = TaskManager()
    
    try:
        # Get all open tickets that can be executed by agents
        open_tickets = ProjectTicket.objects.filter(
            project_id=project_id,
            status='open',
            role='agent'
        ).order_by('priority', 'id')
        
        # Group tickets by priority for parallel execution
        high_priority = []
        medium_priority = []
        low_priority = []
        
        for ticket in open_tickets:
            if ticket.priority == 'High':
                high_priority.append(ticket.id)
            elif ticket.priority == 'Medium':
                medium_priority.append(ticket.id)
            else:
                low_priority.append(ticket.id)
        
        queued_tasks = []
        
        # Queue high priority tickets first (in parallel)
        for ticket_id in high_priority[:max_workers]:
            task_id = task_manager.publish_task(
                'tasks.task_definitions.execute_ticket_implementation',
                ticket_id, project_id, conversation_id,  # Pass args directly
                task_name=f'Ticket_{ticket_id}_High_Priority',
                group=f'project_{project_id}_high'
            )
            queued_tasks.append({
                'ticket_id': ticket_id,
                'task_id': task_id,
                'priority': 'High'
            })
        
        # Queue medium priority tickets (after high priority completes)
        for ticket_id in medium_priority[:max_workers]:
            if check_ticket_dependencies(ticket_id):
                task_id = task_manager.publish_task(
                    'tasks.task_definitions.execute_ticket_implementation',
                    ticket_id, project_id, conversation_id,  # Pass args directly
                    task_name=f'Ticket_{ticket_id}_Medium_Priority',
                    group=f'project_{project_id}_medium'
                )
                queued_tasks.append({
                    'ticket_id': ticket_id,
                    'task_id': task_id,
                    'priority': 'Medium'
                })
        
        return {
            "status": "success",
            "queued_tasks": queued_tasks,
            "total_queued": len(queued_tasks),
            "message": f"Queued {len(queued_tasks)} tickets for parallel execution"
        }
        
    except Exception as e:
        logger.error(f"Error in parallel ticket executor: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "queued_tasks": []
        }


def continue_ticket_with_message(ticket_id: int, project_id: int, user_message: str, user_id: int, attachment_ids: list = None) -> Dict[str, Any]:
    """
    Continue a ticket implementation with a user's chat message.

    This allows users to ask questions, request changes, or provide additional
    instructions to the AI agent working on the ticket.

    Args:
        ticket_id: The ID of the ProjectTicket
        project_id: The ID of the project
        user_message: The message from the user
        user_id: The ID of the user sending the message
        attachment_ids: Optional list of ProjectTicketAttachment IDs

    Returns:
        Dict with execution results and status
    """
    logger.info(f"\n{'='*80}\n[TICKET CHAT] Processing message for ticket #{ticket_id}\n{'='*80}")
    logger.info(f"[TICKET CHAT] Input params: ticket_id={ticket_id}, project_id={project_id}, user_id={user_id}")

    start_time = time.time()
    workspace_id = None

    # Import cancellation utilities at the top of the function
    from tasks.dispatch import is_ticket_cancelled, clear_ticket_cancellation_flag

    try:
        # 0. CHECK FOR CANCELLATION BEFORE STARTING
        if is_ticket_cancelled(ticket_id):
            logger.info(f"[TICKET CHAT] ⊘ Ticket #{ticket_id} was cancelled before processing, stopping")
            return {
                "status": "cancelled",
                "ticket_id": ticket_id,
                "message": "Ticket chat was cancelled by user",
                "execution_time": f"{time.time() - start_time:.2f}s"
            }

        # 1. GET TICKET AND PROJECT
        ticket = ProjectTicket.objects.get(id=ticket_id)
        project = Project.objects.get(id=project_id)

        # Set the ticket ID context for lazy workspace initialization
        current_ticket_id.set(ticket_id)
        logger.info(f"[TICKET CHAT] Context set: ticket_id={ticket_id}, project.project_id={project.project_id}")

        logger.info(f"[TICKET CHAT] Ticket: '{ticket.name}' | Project: '{project.name}'")
        logger.info(f"[TICKET CHAT] User message: {user_message[:200]}...")

        # 2. CHECK FOR EXISTING WORKSPACE (don't create yet - lazy initialization)
        from development.models import MagpieWorkspace

        workspace = MagpieWorkspace.objects.filter(
            project=project,
            status='ready'
        ).order_by('-updated_at').first()

        if workspace:
            workspace_id = workspace.workspace_id
            current_workspace_id.set(workspace_id)
            logger.info(f"[TICKET CHAT] Using existing workspace: {workspace_id}")
        else:
            # No workspace yet - will be created on-demand if AI calls tools that need it
            logger.info(f"[TICKET CHAT] No active workspace - will be created on-demand if needed")
            workspace_id = None

        # 3. GET RECENT CONVERSATION HISTORY (last 5 chat exchanges)
        from projects.models import TicketLog

        # Get chat messages (user messages and AI responses)
        chat_logs = TicketLog.objects.filter(
            ticket=ticket,
            log_type__in=['user_message', 'ai_response']
        ).order_by('-created_at')[:10]  # Last 10 entries = ~5 exchanges

        conversation_history = ""
        if chat_logs:
            conversation_history = "\n\nCONVERSATION HISTORY:\n"
            for log in reversed(list(chat_logs)):
                if log.log_type == 'user_message':
                    conversation_history += f"\n[USER]: {log.command}\n"
                elif log.log_type == 'ai_response':
                    # Use output field for full AI response, truncate if too long
                    ai_content = log.output or log.command
                    if len(ai_content) > 1000:
                        ai_content = ai_content[:1000] + "... [truncated]"
                    conversation_history += f"\n[ASSISTANT]: {ai_content}\n"

        # Get recent command executions (separate from chat)
        recent_commands = TicketLog.objects.filter(
            ticket=ticket,
            log_type='command'
        ).order_by('-created_at')[:5]

        logs_context = ""
        if recent_commands:
            logs_context = "\n\nRECENT COMMAND EXECUTIONS:\n"
            for log in reversed(list(recent_commands)):
                explanation = log.explanation or "Command executed"
                logs_context += f"- {explanation}\n"
                if log.output:
                    logs_context += f"  Output: {log.output[:200]}...\n" if len(log.output) > 200 else f"  Output: {log.output}\n"

        # 4. GET TODO LIST STATUS
        from projects.models import ProjectTodoList

        todos = ProjectTodoList.objects.filter(ticket=ticket).order_by('order')
        todos_context = ""
        if todos:
            todos_context = "\n\nCURRENT TASK LIST:\n"
            for todo in todos:
                status_icon = "✓" if todo.status == "Success" else ("⏳" if todo.status == "in_progress" else "○")
                todos_context += f"{status_icon} {todo.description} [{todo.status}]\n"

        # 4.5 GET ATTACHMENTS
        from projects.models import ProjectTicketAttachment

        attachments_context = ""
        attachment_files = []
        if attachment_ids:
            attachments = ProjectTicketAttachment.objects.filter(id__in=attachment_ids)
            if attachments:
                attachments_context = "\n\nATTACHED FILES:\n"
                for att in attachments:
                    attachments_context += f"- {att.original_filename} ({att.file_type}, {att.file_size} bytes)\n"
                    # Store file paths for potential use with multimodal AI
                    if att.file.path:
                        attachment_files.append({
                            'path': att.file.path,
                            'name': att.original_filename,
                            'type': att.file_type
                        })
                logger.info(f"[TICKET CHAT] Including {len(attachment_files)} attachments in context")

        # 5. GET STACK CONFIGURATION FOR CORRECT PROJECT DIRECTORY
        stack = getattr(project, 'stack', 'nextjs')
        stack_config = get_stack_config(stack)
        project_dir = stack_config['project_dir']
        logger.info(f"[TICKET CHAT] Using stack: {stack}, project_dir: {project_dir}")

        # 5.5 BUILD THE CONTINUATION PROMPT
        workspace_info = ""
        if workspace_id:
            workspace_info = """
                You have full access to the workspace and can:
                1. Execute commands to inspect or modify code
                2. Make changes requested by the user
                3. Answer questions about the current state
                4. Continue implementation if needed"""
        else:
            workspace_info = """
                NOTE: No active workspace is currently running, but one will be created automatically when you use the ssh_command tool.
                You can:
                1. Execute commands using ssh_command - workspace will be provisioned on-demand
                2. Answer questions about the ticket based on the description and logs
                3. Make code changes as requested by the user

                When you call ssh_command for the first time, the workspace will be automatically initialized."""

        continuation_prompt = f"""
            USER REQUEST:
            {user_message}

            TICKET CONTEXT:
            Ticket #{ticket.id}: {ticket.name}
            Description: {ticket.description}
            Status: {ticket.status}
            {todos_context}
            {conversation_history}
            {logs_context}
            {attachments_context}

            PROJECT STACK: {stack_config['name']}
            PROJECT PATH: {project_dir}
            {workspace_info}

            After completing the user's request:
            - If changes were made: "IMPLEMENTATION_STATUS: COMPLETE - [brief summary]"
            - If answering a question: "IMPLEMENTATION_STATUS: COMPLETE - Answered user's question"
            - If unable to complete: "IMPLEMENTATION_STATUS: FAILED - [reason]"
        """

        system_prompt = """
            You are an expert developer continuing work on a ticket based on user feedback.

            COMMUNICATION PROTOCOL - CRITICAL (The user ONLY sees broadcast_to_user messages!):
            ALL your responses MUST go through broadcast_to_user. Never just return text - it won't be shown to the user!

            1. IMMEDIATELY call broadcast_to_user(status="progress", message="I'll help you with [brief description]...") to acknowledge
            2. For questions: call broadcast_to_user(status="complete", message="[your answer here]") with your full answer
            3. For tasks: work SILENTLY (no explanatory text), then call broadcast_to_user(status="complete", message="[summary]")
            4. If blocked: call broadcast_to_user(status="blocked", message="[what's wrong]")

            WORKFLOW:
            For QUESTIONS:
            - Call broadcast_to_user with your complete answer as the message

            For TASKS:
            1. Broadcast acknowledgment FIRST
            2. If new task: First check existing todos with get_ticket_todos(ticket_id={ticket.id}), then create new todos with create_ticket_todos(ticket_id={ticket.id}, todos=[...])
            3. Execute todos one by one SILENTLY
            4. Mark each todo as done with update_todo_status(ticket_id={ticket.id}, todo_index=X, status="Success")
            5. Broadcast final summary

            TODO MANAGEMENT (IMPORTANT):
            - ALWAYS use ticket_id={ticket.id} when calling todo functions
            - Check existing todos first: get_ticket_todos(ticket_id={ticket.id})
            - Create new todos: create_ticket_todos(ticket_id={ticket.id}, todos=[{{"description": "Task 1"}}, {{"description": "Task 2"}}])
            - Update todo status: update_todo_status(ticket_id={ticket.id}, todo_index=0, status="Success")

            IMPORTANT:
            - DO NOT RE-CREATE the project. Modify existing files.
            - DO NOT verify extensively or test in loops.
            - DO NOT create documentation files (*.md) except agent.md
            - When done, update todos and broadcast completion

            MANDATORY: You MUST end your response with one of these exact status lines (required for tracking):
            - "IMPLEMENTATION_STATUS: COMPLETE - [changes]"
            - "IMPLEMENTATION_STATUS: FAILED - [reason]"
            """

        # 6. CHECK FOR CANCELLATION BEFORE AI CALL
        if is_ticket_cancelled(ticket_id):
            logger.info(f"[TICKET CHAT] ⊘ Ticket #{ticket_id} was cancelled before AI call, stopping")
            # Clear AI processing flag
            from django.core.cache import cache
            cache.delete(f'ticket_ai_processing_{ticket_id}')
            return {
                "status": "cancelled",
                "ticket_id": ticket_id,
                "message": "Ticket chat was cancelled by user before AI processing",
                "execution_time": f"{time.time() - start_time:.2f}s"
            }

        # 7. CALL AI
        logger.info(f"[TICKET CHAT] Calling AI to process user message...")

        ai_start = time.time()
        ai_response = async_to_sync(get_ai_response)(
            user_message=continuation_prompt,
            system_prompt=system_prompt,
            project_id=project.project_id,
            conversation_id=None,  # No specific conversation
            stream=False,
            tools=tools_builder
        )
        ai_duration = time.time() - ai_start
        logger.info(f"[TICKET CHAT] AI call completed in {ai_duration:.1f}s")

        content = ai_response.get('content', '') if ai_response else ''
        execution_time = time.time() - start_time

        # 8. CLEAR AI PROCESSING FLAG
        from django.core.cache import cache
        ai_processing_key = f'ticket_ai_processing_{ticket_id}'
        cache.delete(ai_processing_key)
        logger.info(f"[TICKET CHAT] Cleared AI processing flag for ticket #{ticket_id}")

        # 8.5 FALLBACK: If AI didn't call broadcast_to_user, we need to send the response manually
        # Check if there was a recent ai_response log for this ticket (created during AI execution)
        try:
            from django.utils import timezone
            from datetime import timedelta

            # Check for ai_response logs created in the last 60 seconds (during this execution)
            recent_cutoff = timezone.now() - timedelta(seconds=60)
            recent_ai_logs = TicketLog.objects.filter(
                ticket_id=ticket_id,
                log_type='ai_response',
                created_at__gte=recent_cutoff
            ).exists()

            if not recent_ai_logs and content:
                # AI didn't broadcast any response, we need to send a fallback
                # Extract meaningful content - strip implementation status markers
                fallback_content = content
                for marker in ['IMPLEMENTATION_STATUS: COMPLETE', 'IMPLEMENTATION_STATUS: FAILED', 'IMPLEMENTATION_STATUS: BLOCKED']:
                    fallback_content = fallback_content.replace(marker, '').strip()

                if fallback_content:
                    logger.info(f"[TICKET CHAT] No broadcast_to_user call detected, sending fallback response")

                    # Save to TicketLog
                    fallback_log = TicketLog.objects.create(
                        ticket=ticket,
                        log_type='ai_response',
                        command='[RESPONSE]',
                        explanation='AI Agent Response',
                        output=fallback_content[:5000]  # Limit to 5000 chars
                    )

                    # Send via WebSocket
                    try:
                        from channels.layers import get_channel_layer
                        # Note: async_to_sync is already imported globally at top of file

                        channel_layer = get_channel_layer()
                        if channel_layer:
                            log_data = {
                                'id': fallback_log.id,
                                'log_type': 'ai_response',
                                'command': '[RESPONSE]',
                                'output': fallback_content[:5000],
                                'exit_code': None,
                                'created_at': fallback_log.created_at.isoformat()
                            }
                            async_to_sync(channel_layer.group_send)(
                                f'ticket_logs_{ticket_id}',
                                {
                                    'type': 'ticket_log_created',
                                    'log_data': log_data
                                }
                            )
                            logger.info(f"[TICKET CHAT] ✓ Fallback response sent via WebSocket (log #{fallback_log.id})")
                    except Exception as ws_error:
                        logger.warning(f"[TICKET CHAT] Failed to send fallback via WebSocket: {ws_error}")
                else:
                    logger.info(f"[TICKET CHAT] No meaningful content to send as fallback")
            elif recent_ai_logs:
                logger.info(f"[TICKET CHAT] AI already broadcast response, no fallback needed")
            else:
                logger.warning(f"[TICKET CHAT] No content from AI response")
        except Exception as fallback_error:
            logger.warning(f"[TICKET CHAT] Error checking/sending fallback response: {fallback_error}")

        # 9. CHECK FOR CANCELLATION AFTER AI CALL
        if is_ticket_cancelled(ticket_id):
            logger.info(f"[TICKET CHAT] ⊘ Ticket #{ticket_id} was cancelled during AI execution, stopping")
            clear_ticket_cancellation_flag(ticket_id)
            return {
                "status": "cancelled",
                "ticket_id": ticket_id,
                "message": "Ticket chat was cancelled by user during AI processing",
                "execution_time": f"{execution_time:.2f}s",
                "workspace_id": workspace_id
            }

        # 10. CHECK COMPLETION STATUS
        completed = 'IMPLEMENTATION_STATUS: COMPLETE' in content
        failed = 'IMPLEMENTATION_STATUS: FAILED' in content

        # Debug logging for completion status
        logger.info(f"[TICKET CHAT] AI response length: {len(content)} chars")
        logger.info(f"[TICKET CHAT] Completion status: completed={completed}, failed={failed}")
        if not completed and not failed:
            # Log last 500 chars to see if status was almost there
            logger.warning(f"[TICKET CHAT] ⚠ No completion status found! Last 500 chars of response: {content[-500:] if content else '(empty)'}")

        # Re-fetch workspace in case it was created during AI execution (lazy initialization)
        if not workspace_id:
            # First check context variable (set by tools during AI execution)
            context_workspace_id = current_workspace_id.get()
            if context_workspace_id:
                workspace_id = context_workspace_id
                logger.info(f"[TICKET CHAT] Got workspace from context variable: {workspace_id}")
            else:
                # Fall back to database query - check 'ready' first, then any usable workspace
                workspace = MagpieWorkspace.objects.filter(
                    project=project,
                    status='ready'
                ).order_by('-updated_at').first()

                if not workspace:
                    # Also check for workspaces in 'error' or 'provisioning' state - they might still be usable
                    workspace = MagpieWorkspace.objects.filter(
                        project=project,
                        status__in=['error', 'provisioning']
                    ).order_by('-updated_at').first()
                    if workspace:
                        logger.warning(f"[TICKET CHAT] Using workspace in '{workspace.status}' state: {workspace.workspace_id}")

                if workspace:
                    workspace_id = workspace.workspace_id
                    logger.info(f"[TICKET CHAT] Workspace found in DB: {workspace_id}")
                else:
                    logger.warning(f"[TICKET CHAT] No workspace found for project")

        # 11. COMMIT CHANGES AND UPDATE STATUS IF COMPLETE
        commit_sha = None
        merge_status = None
        github_owner = None
        github_repo = None

        logger.info(f"[TICKET CHAT] Commit check: workspace_id={workspace_id}, completed={completed}, failed={failed}, stack={stack}, github_branch={ticket.github_branch}")

        if workspace_id and completed and not failed:
            from codebase_index.models import IndexedRepository

            try:
                indexed_repo = IndexedRepository.objects.get(project=project)
                github_token = get_github_token(project.owner)
                feature_branch = ticket.github_branch
                github_owner = indexed_repo.github_owner
                github_repo = indexed_repo.github_repo_name

                if github_token and feature_branch:
                    commit_message = f"chore: User requested changes for ticket #{ticket_id}\n\n{user_message[:200]}"
                    commit_result = commit_and_push_changes(workspace_id, feature_branch, commit_message, ticket_id, stack=stack, github_token=github_token, github_owner=github_owner, github_repo=github_repo)

                    if commit_result['status'] == 'success':
                        commit_sha = commit_result.get('commit_sha')
                        logger.info(f"[TICKET CHAT] ✓ Changes committed and pushed: {commit_sha}")

                        # Save commit SHA to ticket
                        ticket.github_commit_sha = commit_sha
                        ticket.save(update_fields=['github_commit_sha'])

                        # Merge feature branch into lfg-agent (like execute_ticket_implementation does)
                        logger.info(f"[TICKET CHAT] Merging {feature_branch} into lfg-agent...")
                        merge_result = merge_feature_to_lfg_agent(github_token, github_owner, github_repo, feature_branch)

                        if merge_result['status'] == 'success':
                            logger.info(f"[TICKET CHAT] ✓ Merged {feature_branch} into lfg-agent")
                            merge_status = 'merged'
                        elif merge_result['status'] == 'conflict':
                            # Try to resolve conflict locally in workspace
                            logger.warning(f"[TICKET CHAT] ⚠ Merge conflict detected, attempting AI-based resolution...")
                            resolution_result = resolve_merge_conflict(workspace_id, feature_branch, ticket_id, project.project_id, None, stack=stack)

                            if resolution_result['status'] == 'success':
                                logger.info(f"[TICKET CHAT] ✓ Conflicts resolved and merged locally")
                                merge_status = 'merged'
                            else:
                                logger.error(f"[TICKET CHAT] ✗ Could not resolve conflicts: {resolution_result.get('message')}")
                                merge_status = 'conflict'
                                # Add conflict details to ticket notes
                                if 'conflicted_files' in resolution_result:
                                    ticket.notes = (ticket.notes or "") + f"\n\n⚠ MERGE CONFLICTS:\nFiles: {', '.join(resolution_result['conflicted_files'])}"
                                    ticket.save(update_fields=['notes'])
                        else:
                            logger.error(f"[TICKET CHAT] ✗ Merge failed: {merge_result.get('message')}")
                            merge_status = 'failed'

                        # Save merge status to ticket
                        ticket.github_merge_status = merge_status
                        ticket.save(update_fields=['github_merge_status'])
                    else:
                        logger.error(f"[TICKET CHAT] ✗ Failed to commit changes: {commit_result.get('message')}")
                else:
                    if not github_token:
                        logger.warning(f"[TICKET CHAT] No GitHub token available, skipping commit")
                    if not feature_branch:
                        logger.warning(f"[TICKET CHAT] No feature branch set on ticket, skipping commit")
            except IndexedRepository.DoesNotExist:
                logger.info(f"[TICKET CHAT] No GitHub repo linked, skipping commit")
            except Exception as git_error:
                logger.error(f"[TICKET CHAT] ✗ Git operation failed: {str(git_error)}", exc_info=True)

        # 12. UPDATE TICKET STATUS TO DONE IF ALL TASKS COMPLETE
        if completed and not failed:
            # Check if all todos are done
            from projects.models import ProjectTodoList
            pending_todos = ProjectTodoList.objects.filter(
                ticket=ticket
            ).exclude(status='Success').count()

            if pending_todos == 0:
                logger.info(f"[TICKET CHAT] ✓ All tasks complete - marking ticket as done")
                ticket.status = 'done'

                # Build notes with Git information if available
                git_info = ""
                if github_owner and github_repo:
                    repo_url = f"https://github.com/{github_owner}/{github_repo}"
                    git_info = f"\nGitHub Repository: {repo_url}"
                    if ticket.github_branch:
                        git_info += f"\nFeature Branch: {ticket.github_branch}"
                    if commit_sha:
                        git_info += f"\nCommit: {commit_sha}"
                    if merge_status:
                        merge_emoji = '✓' if merge_status == 'merged' else ('⚠' if merge_status == 'conflict' else '✗')
                        git_info += f"\nMerge to lfg-agent: {merge_emoji} {merge_status}"

                ticket.notes = (ticket.notes or "") + f"""
---
[{datetime.now().strftime('%Y-%m-%d %H:%M')}] IMPLEMENTATION COMPLETED (via chat)
Time: {execution_time:.2f} seconds{git_info}
Status: ✓ Complete
"""
                ticket.save(update_fields=['status', 'notes'])

                # Send completion notification
                broadcast_ticket_notification(None, {
                    'is_notification': True,
                    'notification_type': 'toolhistory',
                    'function_name': 'ticket_execution',
                    'status': 'completed',
                    'message': f"✓ Completed ticket #{ticket.id}: {ticket.name}",
                    'ticket_id': ticket.id,
                    'ticket_name': ticket.name,
                    'refresh_checklist': True
                })
            else:
                logger.info(f"[TICKET CHAT] {pending_todos} todos still pending - ticket remains in progress")

        logger.info(f"[TICKET CHAT] Completed in {execution_time:.1f}s")

        return {
            "status": "success" if completed else ("failed" if failed else "completed"),
            "ticket_id": ticket_id,
            "message": f"Processed user message in {execution_time:.2f}s",
            "execution_time": f"{execution_time:.2f}s",
            "workspace_id": workspace_id,
            "ai_response_length": len(content),
            "commit_sha": commit_sha,
            "merge_status": merge_status
        }

    except Exception as e:
        execution_time = time.time() - start_time
        error_msg = str(e)
        logger.error(f"[TICKET CHAT] Error: {error_msg}", exc_info=True)

        return {
            "status": "error",
            "ticket_id": ticket_id,
            "error": error_msg,
            "workspace_id": workspace_id,
            "execution_time": f"{execution_time:.2f}s"
        }
