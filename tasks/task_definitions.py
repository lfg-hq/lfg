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
from factory.stack_configs import get_stack_config, get_bootstrap_script
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


def push_template_and_create_branch(workspace_id: str, owner: str, repo_name: str, branch_name: str, token: str, stack: str = 'nextjs') -> Dict[str, Any]:
    """
    Push the template to the empty GitHub repo and create the feature branch.

    Workflow:
    1. Clone template if directory doesn't exist
    2. Remove .git from template
    3. Initialize new git repo
    4. Push to GitHub main branch
    5. Create and push feature branch

    Args:
        workspace_id: Magpie workspace ID
        owner: GitHub repo owner
        repo_name: GitHub repo name
        branch_name: Feature branch name to create
        token: GitHub token
        stack: Technology stack (determines template and project directory)

    Returns:
        Dict with status and any error messages
    """
    from factory.ai_functions import get_magpie_client, _run_magpie_ssh
    import shlex

    # Get stack configuration
    stack_config = get_stack_config(stack)
    project_dir = stack_config['project_dir']
    template_repo = stack_config['template_repo']
    stack_name = stack_config['name']

    client = get_magpie_client()
    escaped_branch = shlex.quote(branch_name)

    # Get GitHub user info for proper commit attribution
    user_info = get_github_user_info(token)
    git_name = user_info['name']
    git_email = user_info['email']

    # Build clone command based on whether template exists
    if template_repo:
        clone_cmd = f"if [ ! -d /workspace/{project_dir} ]; then cd /workspace && git clone https://github.com/{template_repo} {project_dir}; fi"
    else:
        clone_cmd = f"mkdir -p /workspace/{project_dir}"

    commands = [
        # Clone the template if directory doesn't exist
        clone_cmd,
        # Remove the template's .git directory
        f"cd /workspace/{project_dir} && rm -rf .git",
        # Initialize new git repo
        f"cd /workspace/{project_dir} && git init -b main",
        # Configure git user with actual GitHub account info
        f'cd /workspace/{project_dir} && git config user.email "{git_email}"',
        f'cd /workspace/{project_dir} && git config user.name "{git_name}"',
        # Add all template files
        f"cd /workspace/{project_dir} && git add -A",
        # Create initial commit
        f'cd /workspace/{project_dir} && git commit -m "Initial commit: {stack_name} template from LFG" --allow-empty',
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
            logger.info(f"[Template Push {i+1}/{len(commands)}] {cmd}")

            stdout = result.get('stdout', '').strip()
            stderr = result.get('stderr', '').strip()
            exit_code = result.get('exit_code', 0)

            if stdout:
                logger.info(f"  stdout: {stdout}")
            if stderr and exit_code != 0:
                logger.warning(f"  stderr: {stderr}")

            # Capture the current branch from the last line of stdout
            # (The script outputs echo messages, so we need only the last line)
            if 'git branch --show-current' in cmd and stdout:
                current_branch = stdout.strip().split('\n')[-1]
                logger.info(f"  ✓ Current branch: {current_branch}")

            # Allow rm -rf and conditional clone to not fail the operation
            # The conditional clone returns exit 0 even if directory exists (due to if statement)
            is_allowed_failure = ('rm -rf' in cmd)

            if exit_code != 0 and not is_allowed_failure:
                error_msg = stderr or stdout or f"Command failed with exit code {exit_code}"
                logger.error(f"  ✗ Git command failed: {error_msg}")
                return {'status': 'error', 'message': f'Template push failed: {error_msg}'}

        if current_branch != branch_name:
            logger.warning(f"Branch mismatch: expected {branch_name}, got {current_branch}")
            return {'status': 'error', 'message': f'Failed to checkout branch {branch_name}, currently on {current_branch}'}

        logger.info(f"✓ Template pushed and branch '{current_branch}' created successfully")
        return {
            'status': 'success',
            'message': f'Template pushed to GitHub and branch {branch_name} created',
            'current_branch': current_branch
        }
    except Exception as e:
        logger.error(f"Failed to push template: {str(e)}", exc_info=True)
        return {'status': 'error', 'message': str(e)}


def setup_git_in_workspace(workspace_id: str, owner: str, repo_name: str, branch_name: str, token: str, stack: str = 'nextjs') -> Dict[str, Any]:
    """
    Setup git repository in workspace and checkout the feature branch.

    Smart workflow:
    - If repo exists: fetch latest changes and switch to branch
    - If repo doesn't exist: clone the repo and checkout branch

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

    # Single command that handles all cases
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
    git clone https://{token}@github.com/{owner}/{repo_name}.git {project_dir}
    cd {project_dir}
    git checkout {escaped_branch}
else
    echo "Directory doesn't exist, cloning..."
    git clone https://{token}@github.com/{owner}/{repo_name}.git {project_dir}
    cd {project_dir}
    git checkout {escaped_branch}
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

        if response.status_code in [201, 204]:
            logger.info(f"Successfully merged {feature_branch} into lfg-agent")
            return {
                'status': 'success',
                'message': f'Successfully merged {feature_branch} into lfg-agent'
            }
        elif response.status_code == 409:
            logger.warning(f"Merge conflict detected for {feature_branch} → lfg-agent")
            return {
                'status': 'conflict',
                'message': 'Merge conflict detected. Manual resolution required.'
            }
        elif response.status_code == 204:
            # 204 means branches are already merged/identical
            logger.info(f"Branch {feature_branch} already merged into lfg-agent (no changes)")
            return {
                'status': 'success',
                'message': 'Already up to date - no merge needed'
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


def commit_and_push_changes(workspace_id: str, branch_name: str, commit_message: str, ticket_id: int, stack: str = 'nextjs') -> Dict[str, Any]:
    """
    Commit all changes in workspace and push to GitHub.

    Args:
        workspace_id: Magpie workspace ID
        branch_name: Branch to commit to
        commit_message: Commit message
        ticket_id: Ticket ID for reference
        stack: Technology stack (determines project directory)

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

    commands = [
        # Check current branch
        f"cd /workspace/{project_dir} && git branch --show-current",
        # Check git status
        f"cd /workspace/{project_dir} && git status --short",
        # Add all changes
        f"cd /workspace/{project_dir} && git add -A",
        # Commit changes
        f'cd /workspace/{project_dir} && git commit -m "{escaped_message}" || echo "No changes to commit"',
        # Push to remote
        f"cd /workspace/{project_dir} && git push -u origin {escaped_branch}"
    ]

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

            # Capture current branch
            if 'git branch --show-current' in cmd and stdout:
                current_branch = stdout
                logger.info(f"  Current branch: {current_branch}")

            # Check if there are changes
            if 'git status --short' in cmd and stdout:
                changes_detected = bool(stdout)
                logger.info(f"  Changes detected: {changes_detected}")
                if changes_detected:
                    logger.info(f"  Modified files:\n{stdout}")

            # Extract commit SHA
            if 'git commit' in cmd and exit_code == 0:
                # Try to extract commit SHA from output
                if '[' in stdout and ']' in stdout:
                    try:
                        commit_sha = stdout.split('[')[1].split(']')[0].split()[0]
                        logger.info(f"  Commit SHA: {commit_sha}")
                    except:
                        pass

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
            logger.info(f"[WORKSPACE SETUP] Pushing template and creating branch...")
            git_setup_result = push_template_and_create_branch(
                result['workspace_id'],
                result['github_owner'],
                result['github_repo'],
                result['feature_branch'],
                github_token,
                stack=stack
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
            ticket.notes = (ticket.notes or "") + f"""
            ---
            [{datetime.now().strftime('%Y-%m-%d %H:%M')}] EXECUTION FAILED
            Error: {error_msg}
            """
            ticket.save(update_fields=['status', 'notes'])

            broadcast_ticket_notification(conversation_id, {
                'is_notification': True,
                'notification_type': 'toolhistory',
                'function_name': 'ticket_execution',
                'status': 'failed',
                'message': f"✗ Ticket #{ticket.id} failed: {error_msg}",
                'ticket_id': ticket.id,
                'ticket_name': ticket.name,
                'refresh_checklist': True
            })

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
        stack = setup_result.get('stack', 'nextjs')
        project_dir = setup_result.get('project_dir', 'nextjs-app')
        stack_config = get_stack_config(stack)

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
            2. Check if todos exist - if no, create them. If yes, continue from pending ones.
            3. Check agent.md for project state. Update it with important changes.
            4. Execute todos one by one SILENTLY (batch shell commands: ls -la && cat ... && grep ...)
            5. Mark each todo as `Success` when complete
            6. Install libraries as needed
            7. Broadcast final summary

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
                attachments=attachments if attachments else None
            )
            ai_call_duration = time.time() - ai_call_start
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

        if completed and not failed and github_owner and github_repo and github_token and feature_branch_name:
            logger.info(f"\n[COMMIT] Committing and pushing changes to GitHub...")

            # Commit and push changes
            commit_message = f"feat: {ticket.name}\n\nImplemented ticket #{ticket_id}\n\n{ticket.description[:200]}"
            commit_result = commit_and_push_changes(workspace_id, feature_branch_name, commit_message, ticket_id, stack=stack)

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
            ticket.save(update_fields=['status', 'notes'])
            
            broadcast_ticket_notification(conversation_id, {
                'is_notification': True,
                'notification_type': 'toolhistory',
                'function_name': 'ticket_execution',
                'status': 'completed',
                'message': f"✓ Completed ticket #{ticket.id}: {ticket.name}",
                'ticket_id': ticket.id,
                'ticket_name': ticket.name,
                'refresh_checklist': True
            })

            logger.info(f"[FINALIZE] ✓ Task completed successfully in {execution_time:.1f}s")
            logger.info(f"{'='*80}\n[TASK END] SUCCESS - Ticket #{ticket_id}\n{'='*80}\n")

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
            if error_match:
                error_reason = error_match.group(1)
            elif not content or len(content) < 100:
                error_reason = "AI response was empty or incomplete. Possible API timeout or error."
            else:
                error_reason = "No explicit completion status provided. AI may have exceeded tool limit or stopped unexpectedly."

            ticket.status = 'blocked'
            ticket.notes = (ticket.notes or "") + f"""
                ---
                [{datetime.now().strftime('%Y-%m-%d %H:%M')}] IMPLEMENTATION FAILED
                Time: {execution_time:.2f} seconds
                Tool calls: ~{tool_calls_count}
                Files attempted: {len(files_created)}
                Error: {error_reason}
                Workspace: {workspace_id}
                Manual intervention required
                """
            ticket.save(update_fields=['status', 'notes'])

            broadcast_ticket_notification(conversation_id, {
                'is_notification': True,
                'notification_type': 'toolhistory',
                'function_name': 'ticket_execution',
                'status': 'failed',
                'message': f"✗ Failed ticket #{ticket.id}: {error_reason}",
                'ticket_id': ticket.id,
                'ticket_name': ticket.name,
                'refresh_checklist': True
            })

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
            ticket.notes = (ticket.notes or "") + f"""
            ---
            [{datetime.now().strftime('%Y-%m-%d %H:%M')}] EXECUTION FAILED
            Error: {error_msg}
            Time: {execution_time:.2f}s
            Workspace: {workspace_id or 'N/A'}
            Manual intervention required
            """
            ticket.save(update_fields=['status', 'notes'])

            broadcast_ticket_notification(conversation_id, {
                'is_notification': True,
                'notification_type': 'toolhistory',
                'function_name': 'ticket_execution',
                'status': 'failed',
                'message': f"✗ Ticket #{ticket.id} error: {error_msg[:100]}",
                'ticket_id': ticket.id,
                'ticket_name': ticket.name,
                'refresh_checklist': True
            })

        # Return error without re-raising (prevents Django-Q retry loops)
        logger.error(f"{'='*80}\n[TASK END] ERROR - Ticket #{ticket_id}\n{'='*80}\n")

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

    try:
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

        # 5. BUILD THE CONTINUATION PROMPT
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

            PROJECT PATH: nextjs-app
            {workspace_info}

            After completing the user's request:
            - If changes were made: "IMPLEMENTATION_STATUS: COMPLETE - [brief summary]"
            - If answering a question: "IMPLEMENTATION_STATUS: COMPLETE - Answered user's question"
            - If unable to complete: "IMPLEMENTATION_STATUS: FAILED - [reason]"
        """

        system_prompt = """
            You are an expert developer continuing work on a ticket based on user feedback.

            COMMUNICATION PROTOCOL - VERY IMPORTANT:
            1. IMMEDIATELY call broadcast_to_user(status="progress", message="I'll help you with [brief description]...") to acknowledge the request
            2. Work SILENTLY - do NOT output explanatory text like "Let me check...", "Perfect!", "Now I'll..."
            3. Just execute tools directly without narration
            4. At the END, call broadcast_to_user(status="complete", message="[summary of what was done]") with your final summary
            5. If blocked or need help, call broadcast_to_user(status="blocked", message="[what's wrong]")

            WORKFLOW:
            1. Broadcast acknowledgment FIRST
            2. If new task: create Todos, execute them silently one by one
            3. If question: look into codebase if needed
            4. Mark todos as done when complete
            5. Broadcast final summary

            IMPORTANT:
            - DO NOT RE-CREATE the project. Modify existing files.
            - DO NOT verify extensively or test in loops.
            - DO NOT create documentation files (*.md) except agent.md
            - CREATE new TODO list if there are new changes to be made. This will allow user to track the progress being made
            - When done, update todos and broadcast completion

            MANDATORY: You MUST end your response with one of these exact status lines (required for tracking):
            - "IMPLEMENTATION_STATUS: COMPLETE - [changes]"
            - "IMPLEMENTATION_STATUS: FAILED - [reason]"
            """

        # 6. CALL AI
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

        # 7. CLEAR AI PROCESSING FLAG
        # Note: AI response is NOT saved to TicketLog - AI communicates via broadcast_to_user tool only
        from django.core.cache import cache
        ai_processing_key = f'ticket_ai_processing_{ticket_id}'
        cache.delete(ai_processing_key)
        logger.info(f"[TICKET CHAT] Cleared AI processing flag for ticket #{ticket_id}")

        # 8. CHECK COMPLETION STATUS
        completed = 'IMPLEMENTATION_STATUS: COMPLETE' in content
        failed = 'IMPLEMENTATION_STATUS: FAILED' in content

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

        # 9. COMMIT CHANGES AND UPDATE STATUS IF COMPLETE
        commit_sha = None
        merge_status = None
        github_owner = None
        github_repo = None

        logger.info(f"[TICKET CHAT] Commit check: workspace_id={workspace_id}, completed={completed}, failed={failed}")

        if workspace_id and completed:
            from codebase_index.models import IndexedRepository

            try:
                indexed_repo = IndexedRepository.objects.get(project=project)
                github_token = get_github_token(project.owner)
                feature_branch = ticket.github_branch
                github_owner = indexed_repo.github_owner
                github_repo = indexed_repo.github_repo_name

                if github_token and feature_branch:
                    commit_message = f"chore: User requested changes for ticket #{ticket_id}\n\n{user_message[:200]}"
                    commit_result = commit_and_push_changes(workspace_id, feature_branch, commit_message, ticket_id)

                    if commit_result['status'] == 'success':
                        commit_sha = commit_result.get('commit_sha')
                        logger.info(f"[TICKET CHAT] Changes committed: {commit_sha}")

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
                            resolution_result = resolve_merge_conflict(workspace_id, feature_branch, ticket_id, project.project_id, None)

                            if resolution_result['status'] == 'success':
                                logger.info(f"[TICKET CHAT] ✓ Conflicts resolved and merged locally")
                                merge_status = 'merged'
                            else:
                                logger.error(f"[TICKET CHAT] ✗ Could not resolve conflicts: {resolution_result.get('message')}")
                                merge_status = 'conflict'
                        else:
                            logger.error(f"[TICKET CHAT] ✗ Merge failed: {merge_result.get('message')}")
                            merge_status = 'failed'

                        # Save merge status to ticket
                        ticket.github_merge_status = merge_status
                        ticket.save(update_fields=['github_merge_status'])
            except IndexedRepository.DoesNotExist:
                logger.info(f"[TICKET CHAT] No GitHub repo linked, skipping commit")

        # 9. UPDATE TICKET STATUS TO DONE IF ALL TASKS COMPLETE
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
