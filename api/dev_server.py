"""
API endpoints for managing development servers for ticket previews using Magpie workspaces.
"""
import logging
import os
import textwrap
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from asgiref.sync import async_to_sync
from projects.models import ProjectTicket
from development.models import MagpieWorkspace
from accounts.models import ExternalServicesAPIKeys, GitHubToken
from projects.websocket_utils import send_workspace_progress

logger = logging.getLogger(__name__)

# Import Magpie utilities from factory/ai_functions.py
try:
    from factory.ai_functions import get_magpie_client, _run_magpie_ssh, magpie_available, _fetch_workspace, get_or_fetch_proxy_url
except ImportError:
    logger.error("Failed to import Magpie utilities from factory.ai_functions")
    get_magpie_client = None
    _run_magpie_ssh = None
    magpie_available = lambda: False
    _fetch_workspace = None
    get_or_fetch_proxy_url = None

# Import git setup function
try:
    from tasks.task_definitions import setup_git_in_workspace
except ImportError:
    logger.error("Failed to import setup_git_in_workspace from tasks.task_definitions")
    setup_git_in_workspace = None


def _ensure_code_in_workspace(client, workspace, project, user, ticket=None, send_progress=True):
    """
    Ensure code exists in the workspace and is on the correct branch.
    - If ticket has github_branch, use that
    - Otherwise default to 'lfg-agent'
    Returns (success, message)
    """
    from factory.stack_configs import get_stack_config

    job_id = workspace.job_id
    stack_config = get_stack_config(project.stack, project)
    project_dir = stack_config['project_dir']
    workspace_path = f"/workspace/{project_dir}"
    project_id = str(project.project_id)

    logger.info(f"[CODE_SETUP] Project stack: {project.stack}, project_dir: {project_dir}")

    # Helper to send progress if enabled
    def progress(step, message=None, extra_data=None):
        if send_progress:
            send_workspace_progress(project_id, step, message, extra_data=extra_data)

    # Determine target branch: ticket branch > lfg-agent (default)
    target_branch = 'lfg-agent'
    if ticket and ticket.github_branch:
        target_branch = ticket.github_branch
        logger.info(f"[CODE_SETUP] Using ticket branch: {target_branch}")

    # Check if code already exists - use stack-specific file patterns
    progress('checking_workspace', 'Checking workspace structure...')
    file_patterns = stack_config.get('file_patterns', ['package.json'])
    # Check for first file pattern (most common indicator file)
    check_file = file_patterns[0] if file_patterns else 'package.json'
    check_cmd = f"test -d {workspace_path} && test -f {workspace_path}/{check_file} && echo 'EXISTS' || echo 'MISSING'"
    check_result = _run_magpie_ssh(client, job_id, check_cmd, timeout=30, with_node_env=False)

    code_exists = 'EXISTS' in check_result.get('stdout', '')

    # Check if project has GitHub repo configured (via IndexedRepository)
    indexed_repo = getattr(project, 'indexed_repository', None)

    if indexed_repo and indexed_repo.github_url:
        # Get GitHub token
        github_token_obj = GitHubToken.objects.filter(user=user).first()
        github_token = github_token_obj.access_token if github_token_obj else None

        if not github_token:
            return False, "GitHub token not configured"

        owner = indexed_repo.github_owner
        repo = indexed_repo.github_repo_name

        # Build authenticated git URL
        auth_remote_url = f"https://x-access-token:{github_token}@github.com/{owner}/{repo}.git"

        if code_exists:
            # Code exists - check if we need to switch branches and pull latest
            logger.info(f"[CODE_SETUP] Code exists, switching to {target_branch} and pulling latest...")
            progress('switching_branch', f'Switching to branch {target_branch}...', extra_data={'branch': target_branch})

            # Get current branch, switch if needed, and always pull latest
            # Note: All commands use || true to prevent set -e from causing early exit
            switch_cmd = f'''
cd {workspace_path}

# Update remote URL with auth token for this operation
git remote set-url origin "{auth_remote_url}" || true

current_branch=$(git branch --show-current 2>/dev/null || echo "unknown")
echo "CURRENT_BRANCH:$current_branch"

# Remove untracked files that block checkout (dev server artifacts)
echo "Cleaning up untracked files..."
rm -f .devserver_pid dev.log 2>/dev/null || true

# Fetch ALL branches from remote
echo "Fetching all branches..."
git fetch origin --prune 2>&1 || true

# List available remote branches for debugging
echo "Available remote branches:"
git branch -r 2>/dev/null | head -20 || true

# Stash any local changes
echo "Stashing local changes..."
git stash 2>/dev/null || true

# Try to checkout the branch
echo "Checking out {target_branch}..."

# Method 1: Try simple checkout (if branch exists locally)
git checkout {target_branch} 2>&1 && echo "METHOD1_SUCCESS" || true

# Check if we're on the right branch now
on_branch=$(git branch --show-current 2>/dev/null || echo "none")
if [ "$on_branch" = "{target_branch}" ]; then
    echo "On correct branch, pulling latest..."
    git pull origin {target_branch} 2>&1 || true
else
    # Method 2: Try to create from remote tracking branch
    echo "Method 1 failed, trying method 2..."
    git checkout -b {target_branch} origin/{target_branch} 2>&1 && echo "METHOD2_SUCCESS" || true

    on_branch=$(git branch --show-current 2>/dev/null || echo "none")
    if [ "$on_branch" != "{target_branch}" ]; then
        # Method 3: Fetch the specific branch and checkout
        echo "Method 2 failed, trying method 3..."
        git fetch origin {target_branch} 2>&1 || true
        git checkout -B {target_branch} FETCH_HEAD 2>&1 && echo "METHOD3_SUCCESS" || true
    fi
fi

# Final verification
final_branch=$(git branch --show-current 2>/dev/null || echo "unknown")
echo "FINAL_BRANCH:$final_branch"

if [ "$final_branch" = "{target_branch}" ]; then
    echo "SUCCESS: Now on branch {target_branch}"
else
    echo "BRANCH_SWITCH_FAILED: wanted {target_branch} but on $final_branch"
fi

# Reset remote URL to non-auth version for safety
git remote set-url origin "https://github.com/{owner}/{repo}.git" || true

echo "SWITCH_COMPLETE"
'''
            switch_result = _run_magpie_ssh(client, job_id, switch_cmd, timeout=120, with_node_env=False)
            stdout = switch_result.get('stdout', '')
            stderr = switch_result.get('stderr', '')
            exit_code = switch_result.get('exit_code', -1)
            logger.info(f"[CODE_SETUP] Branch switch exit_code: {exit_code}")
            logger.info(f"[CODE_SETUP] Branch switch stdout: {stdout}")
            if stderr:
                logger.warning(f"[CODE_SETUP] Branch switch stderr: {stderr}")

            if 'BRANCH_SWITCH_FAILED' in stdout:
                logger.warning(f"[CODE_SETUP] Failed to switch branch, but continuing...")

            # Run npm install after branch switch to ensure dependencies are up to date
            progress('downloading_dependencies', 'Installing dependencies (npm install)...')
            logger.info(f"[CODE_SETUP] Running npm install after branch switch...")
            npm_result = _run_magpie_ssh(
                client, job_id,
                f"cd {workspace_path} && npm config set cache /workspace/.npm-cache && npm install",
                timeout=300, with_node_env=True
            )
            if npm_result.get('exit_code', 0) != 0:
                logger.warning(f"[CODE_SETUP] npm install warning: {npm_result.get('stderr', '')[:200]}")
            else:
                logger.info(f"[CODE_SETUP] npm install completed successfully")

            # Update metadata with current branch
            metadata = workspace.metadata or {}
            metadata['git_branch'] = target_branch
            workspace.metadata = metadata
            workspace.save()

            return True, f"Code ready on branch {target_branch}"
        else:
            # Code doesn't exist - clone the repo
            logger.info(f"[CODE_SETUP] Code missing, cloning {owner}/{repo} branch {target_branch}")

            if setup_git_in_workspace:
                git_result = setup_git_in_workspace(
                    workspace_id=job_id,
                    owner=owner,
                    repo_name=repo,
                    branch_name=target_branch,
                    token=github_token,
                    stack=project.stack  # Use project's actual stack
                )

                if git_result.get('status') == 'success':
                    # Run npm install
                    logger.info(f"[CODE_SETUP] Running npm install...")
                    npm_result = _run_magpie_ssh(
                        client, job_id,
                        f"cd {workspace_path} && npm config set cache /workspace/.npm-cache && npm install",
                        timeout=300, with_node_env=True
                    )
                    if npm_result.get('exit_code', 0) == 0:
                        # Update workspace metadata
                        metadata = workspace.metadata or {}
                        metadata['git_configured'] = True
                        metadata['git_branch'] = target_branch
                        workspace.metadata = metadata
                        workspace.save()
                        return True, f"Cloned {owner}/{repo} on branch {target_branch}"
                    else:
                        return False, f"npm install failed: {npm_result.get('stderr', '')[:200]}"
                else:
                    return False, f"Git clone failed: {git_result.get('message', 'unknown error')}"
            else:
                return False, "setup_git_in_workspace not available"
    else:
        # No GitHub repo - create empty project directory with minimal files
        # AI will generate the codebase based on requirements
        if code_exists:
            return True, "Project code already exists"

        logger.info(f"[CODE_SETUP] No GitHub repo, creating empty project directory")

        from factory.stack_configs import get_gitignore_content
        gitignore_content = get_gitignore_content(project.stack)

        empty_project_cmd = f'''
cd /workspace
if [ ! -d {project_dir} ]; then
    mkdir -p {project_dir}
    cat > {project_dir}/.gitignore << 'GITIGNORE_EOF'
{gitignore_content}
GITIGNORE_EOF
    cat > {project_dir}/README.md << 'README_EOF'
# {project.name}

Project generated by LFG.

This project structure will be generated by AI based on your requirements.
README_EOF
    echo "EMPTY_PROJECT_CREATED"
else
    echo "ALREADY_EXISTS"
fi
'''
        result = _run_magpie_ssh(client, job_id, empty_project_cmd, timeout=60, with_node_env=False)

        if result.get('exit_code', 0) == 0:
            # Update workspace metadata
            metadata = workspace.metadata or {}
            metadata['empty_project_created'] = True
            workspace.metadata = metadata
            workspace.save()
            return True, "Empty project directory created"
        else:
            return False, f"Project setup failed: {result.get('stderr', '')[:200]}"


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def start_dev_server(request, ticket_id):
    """
    Start a development server for the ticket's project using Magpie workspace.
    This will:
    1. Get the MagpieWorkspace for the project
    2. Kill any existing npm/node processes and remove lock files
    3. Start 'npm run dev' via SSH in the Magpie workspace
    """
    try:
        # Get the ticket
        ticket = ProjectTicket.objects.select_related('project').get(id=ticket_id)

        # Check permissions
        if ticket.project.owner != request.user:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

        project = ticket.project

        # Check if Magpie is available
        if not magpie_available():
            return JsonResponse(
                {'error': 'Magpie workspace execution is not available. Configure the Magpie SDK and API key.'},
                status=503
            )

        # Get the MagpieWorkspace for this project using _fetch_workspace
        # This matches the pattern from execute_ticket_implementation
        magpie_workspace = async_to_sync(_fetch_workspace)(project=project)

        if not magpie_workspace:
            return JsonResponse(
                {'error': 'No Magpie workspace found for this project. Please provision a workspace first.'},
                status=400
            )

        # Use workspace regardless of status (matches task_definitions.py behavior)
        # Just log a warning if not ready
        if magpie_workspace.status != 'ready':
            logger.warning(f"Using workspace with status '{magpie_workspace.status}' (not 'ready')")

        # Get stack configuration
        from factory.stack_configs import get_stack_config
        stack_config = get_stack_config(project.stack, project)
        project_dir = stack_config['project_dir']
        workspace_path = f"/workspace/{project_dir}"
        job_id = magpie_workspace.job_id

        logger.info(f"[DEV_SERVER] Starting dev server for ticket {ticket_id}")
        logger.info(f"[DEV_SERVER] Project stack: {project.stack}, project_dir: {project_dir}")
        logger.info(f"[DEV_SERVER] Workspace ID: {magpie_workspace.workspace_id}")
        logger.info(f"[DEV_SERVER] Workspace status: {magpie_workspace.status}")
        logger.info(f"[DEV_SERVER] Job ID: {job_id}")
        logger.info(f"[DEV_SERVER] Workspace path: {workspace_path}")
        logger.info(f"[DEV_SERVER] IPv6: {magpie_workspace.ipv6_address}")

        # Get Magpie client
        client = get_magpie_client()

        # Step 0: Ensure code exists in workspace and is on correct branch
        logger.info(f"[DEV_SERVER] Checking workspace structure...")
        logger.info(f"[DEV_SERVER] Ticket branch: {ticket.github_branch or 'not set (will use lfg-agent)'}")
        code_success, code_message = _ensure_code_in_workspace(client, magpie_workspace, project, request.user, ticket=ticket)
        logger.info(f"[DEV_SERVER] Code setup result: {code_success}, {code_message}")

        if not code_success:
            send_workspace_progress(str(project.project_id), 'error', f'Failed to set up code: {code_message}', error=code_message)
            return JsonResponse(
                {'error': f'Failed to set up code in workspace: {code_message}'},
                status=500
            )
        # verify_command = textwrap.dedent(f"""
        #     echo "=== Workspace verification ==="
        #     echo "Current directory: $(pwd)"
        #     echo "Workspace path exists: $(test -d {workspace_path} && echo 'YES' || echo 'NO')"
        #     echo "Contents of /workspace:"
        #     ls -la /workspace/ || echo "Failed to list /workspace"
        #     echo "Node installed: $(which node || echo 'NOT FOUND')"
        #     echo "NPM installed: $(which npm || echo 'NOT FOUND')"
        #     echo "Package.json exists: $(test -f {workspace_path}/package.json && echo 'YES' || echo 'NO')"
        # """)

        # verify_result = _run_magpie_ssh(client, job_id, verify_command, timeout=30, with_node_env=True)
        # logger.info(f"[VERIFY] Stdout:\n{verify_result.get('stdout', '')}")
        # logger.info(f"[VERIFY] Stderr:\n{verify_result.get('stderr', '')}")

        project_id = str(project.project_id)

        # Step 0.5: Run bootstrap script to ensure stack tools are installed
        bootstrap_script = stack_config.get('bootstrap_script', '')
        if bootstrap_script and project.stack != 'nextjs':  # Node.js is pre-installed
            send_workspace_progress(project_id, 'installing_tools', f'Checking/installing {stack_config["name"]} tools...')
            logger.info(f"[DEV_SERVER] Running bootstrap script for {project.stack}")

            bootstrap_result = _run_magpie_ssh(
                client, job_id, bootstrap_script, timeout=300, with_node_env=False, project_id=project.id
            )
            if bootstrap_result.get('exit_code', 0) != 0:
                logger.warning(f"[DEV_SERVER] Bootstrap warning: {bootstrap_result.get('stderr', '')[:200]}")
            else:
                logger.info(f"[DEV_SERVER] Bootstrap completed successfully")

        # Step 1: Kill existing processes and remove lock files
        send_workspace_progress(project_id, 'clearing_cache', 'Clearing cache and stopping existing processes...')

        # Build stack-specific cleanup command
        # Use custom_default_port if set, otherwise fall back to stack default
        default_port = project.custom_default_port or stack_config.get('default_port', 3000)
        if project.stack == 'nextjs':
            cleanup_extras = """
            npm config set cache /workspace/.npm-cache
            killall -9 node 2>/dev/null || true
            pkill -9 node 2>/dev/null || true
            rm -rf .next || true
            rm -f package-lock.json || true
            """
        elif project.stack in ('python-django', 'python-fastapi'):
            cleanup_extras = """
            pkill -f 'runserver' 2>/dev/null || true
            pkill -f 'uvicorn' 2>/dev/null || true
            rm -rf __pycache__ .pytest_cache || true
            """
        elif project.stack == 'go':
            cleanup_extras = """
            pkill -f 'go run' 2>/dev/null || true
            """
        elif project.stack == 'rust':
            cleanup_extras = """
            pkill -f 'cargo run' 2>/dev/null || true
            """
        elif project.stack == 'ruby-rails':
            cleanup_extras = """
            pkill -f 'rails server' 2>/dev/null || true
            rm -rf tmp/cache || true
            """
        else:
            cleanup_extras = ""

        cleanup_command = textwrap.dedent(f"""
            cd {workspace_path}

            echo "Stopping existing processes..."
            {cleanup_extras}

            # Kill anything on the default port
            fuser -k -9 {default_port}/tcp 2>/dev/null || true

            # Clean up PID file
            rm -f .devserver_pid || true

            # Wait for port to be fully released
            sleep 3

            echo "Cleanup completed"
        """)

        cleanup_result = _run_magpie_ssh(client, job_id, cleanup_command, timeout=60, with_node_env=(project.stack == 'nextjs'), project_id=project.id)
        
        logger.info(f"[CLEANUP] Result: {cleanup_result}")
        logger.info(f"[CLEANUP] Exit code: {cleanup_result.get('exit_code')}")
        logger.info(f"[CLEANUP] Stdout: {cleanup_result.get('stdout', '')[:500]}")
        logger.info(f"[CLEANUP] Stderr: {cleanup_result.get('stderr', '')[:500]}")

        if cleanup_result.get('exit_code') != 0:
            logger.warning(f"Cleanup had non-zero exit code {cleanup_result.get('exit_code')}: {cleanup_result.get('stderr', '')}")

        # Step 2: Start the dev server in background
        send_workspace_progress(project_id, 'starting_server', 'Starting development server...')

        # Get the dev command from stack config
        dev_cmd = stack_config['dev_cmd']
        default_port = stack_config.get('default_port', 3000)
        pre_dev_cmd = stack_config.get('pre_dev_cmd', '')

        # Customize dev command for different stacks
        if project.stack == 'nextjs':
            final_dev_cmd = f"npm run dev -- --hostname :: --port {default_port}"
        elif project.stack in ('python-django', 'python-fastapi'):
            final_dev_cmd = dev_cmd
        else:
            final_dev_cmd = f"PORT={default_port} {dev_cmd}" if dev_cmd else f"echo 'No dev command configured'"

        # Build the full dev command including any pre-setup (e.g., export PATH)
        if pre_dev_cmd:
            full_dev_cmd = f"{pre_dev_cmd} && {final_dev_cmd}"
        else:
            full_dev_cmd = final_dev_cmd

        start_command = textwrap.dedent(f"""
            cd {workspace_path}

            # Start dev server in background
            : > {workspace_path}/dev.log
            nohup sh -c '{full_dev_cmd}' > {workspace_path}/dev.log 2>&1 &
            pid=$!
            echo "$pid" > .devserver_pid
            echo "PID:$pid"

            # Wait for server to start (Go/Rust need time to compile)
            sleep 10

            # Check if process is still running
            if kill -0 "$pid" 2>/dev/null; then
                echo "Dev server started successfully with PID $pid"
            else
                echo "ERROR: Dev server failed to start"
                echo "=== Last 50 lines of dev.log ==="
                tail -50 {workspace_path}/dev.log 2>/dev/null || echo "(no log available)"
                echo "=== End of dev.log ==="
                exit 1
            fi
        """)

        start_result = _run_magpie_ssh(client, job_id, start_command, timeout=120, with_node_env=True, project_id=project.id)

        logger.info(f"[START] Result: {start_result}")
        logger.info(f"[START] Exit code: {start_result.get('exit_code')}")
        logger.info(f"[START] Stdout: {start_result.get('stdout', '')}")
        logger.info(f"[START] Stderr: {start_result.get('stderr', '')}")

        if start_result.get('exit_code') != 0:
            stdout = start_result.get('stdout', '')
            stderr = start_result.get('stderr', '')
            error_msg = stderr or stdout or 'Unknown error - command exited with non-zero status'
            logger.error(f"Failed to start dev server (exit {start_result.get('exit_code')}): stdout={stdout}, stderr={stderr}")
            send_workspace_progress(project_id, 'error', f'Failed to start server: {error_msg[:100]}', error=error_msg)
            return JsonResponse(
                {'error': f'Failed to start dev server: {error_msg}'},
                status=500
            )

        # Extract PID from output
        stdout = start_result.get('stdout', '')
        pid = None
        for line in stdout.split('\n'):
            if 'PID:' in line:
                pid = line.split('PID:')[1].strip()
                break

        logger.info(f"Dev server started successfully with PID: {pid}")

        # Get proxy URL, force refresh to ensure it points to current IPv6/port
        send_workspace_progress(project_id, 'assigning_proxy', 'Getting preview URL...')
        preview_url = None
        if get_or_fetch_proxy_url:
            preview_url = get_or_fetch_proxy_url(magpie_workspace, port=default_port, client=client, force_refresh=True)
        if not preview_url:
            preview_url = f'http://[{magpie_workspace.ipv6_address}]:{default_port}' if magpie_workspace.ipv6_address else f'http://localhost:{default_port}'

        # Send completion notification
        send_workspace_progress(project_id, 'complete', 'Dev server is ready!', extra_data={'url': preview_url})

        return JsonResponse({
            'success': True,
            'message': 'Dev server started successfully',
            'pid': pid,
            'workspace_id': magpie_workspace.workspace_id,
            'url': preview_url
        })

    except ProjectTicket.DoesNotExist:
        return JsonResponse(
            {'error': 'Ticket not found'},
            status=404
        )
    except Exception as e:
        logger.error(f"Error starting dev server: {e}", exc_info=True)
        return JsonResponse(
            {'error': str(e)},
            status=500
        )


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def stop_dev_server(request, ticket_id):
    """
    Stop the development server for the ticket's project.
    """
    try:
        # Get the ticket
        ticket = ProjectTicket.objects.select_related('project').get(id=ticket_id)

        # Check permissions
        if ticket.project.owner != request.user:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

        project = ticket.project

        # Check if Magpie is available
        if not magpie_available():
            return JsonResponse(
                {'error': 'Magpie workspace execution is not available.'},
                status=503
            )

        # Get the MagpieWorkspace for this project using _fetch_workspace
        magpie_workspace = async_to_sync(_fetch_workspace)(project=project)

        if not magpie_workspace:
            return JsonResponse(
                {'error': 'No Magpie workspace found for this project.'},
                status=400
            )

        # Use workspace regardless of status
        if magpie_workspace.status != 'ready':
            logger.warning(f"Stopping dev server on workspace with status '{magpie_workspace.status}'")

        # Get stack configuration
        from factory.stack_configs import get_stack_config
        stack_config = get_stack_config(project.stack, project)
        project_dir = stack_config['project_dir']
        workspace_path = f"/workspace/{project_dir}"
        job_id = magpie_workspace.job_id

        logger.info(f"Stopping dev server for ticket {ticket_id} in Magpie workspace {magpie_workspace.workspace_id}")

        # Get Magpie client
        client = get_magpie_client()

        # Stop dev server
        stop_command = textwrap.dedent(f"""
            cd {workspace_path}

            # Kill processes using PID file
            if [ -f .devserver_pid ]; then
              old_pid=$(cat .devserver_pid)
              if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
                kill "$old_pid" || true
                sleep 2
                # Force kill if still running
                kill -9 "$old_pid" 2>/dev/null || true
              fi
              rm -f .devserver_pid
            fi

            # Kill any remaining npm/node processes
            pkill -f 'npm run dev' || true
            pkill -f 'next dev' || true

            echo "Dev server stopped"
        """)

        stop_result = _run_magpie_ssh(client, job_id, stop_command, timeout=60, with_node_env=True, project_id=project.id)

        if stop_result.get('exit_code') != 0:
            logger.warning(f"Stop command had non-zero exit code: {stop_result.get('stderr')}")

        return JsonResponse({
            'success': True,
            'message': 'Dev server stopped successfully'
        })

    except ProjectTicket.DoesNotExist:
        return JsonResponse(
            {'error': 'Ticket not found'},
            status=404
        )
    except Exception as e:
        logger.error(f"Error stopping dev server: {e}", exc_info=True)
        return JsonResponse(
            {'error': str(e)},
            status=500
        )


@csrf_exempt
@login_required
@require_http_methods(["GET"])
def get_dev_server_logs(request, ticket_id):
    """
    Get the dev server logs from the workspace.
    Query params:
        - lines: Number of lines to tail (default 100, max 500)
    """
    try:
        # Get the ticket
        ticket = ProjectTicket.objects.select_related('project').get(id=ticket_id)

        # Check permissions
        if ticket.project.owner != request.user:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

        project = ticket.project

        # Check if Magpie is available
        if not magpie_available():
            return JsonResponse(
                {'error': 'Magpie workspace execution is not available.'},
                status=503
            )

        # Get the MagpieWorkspace for this project
        magpie_workspace = async_to_sync(_fetch_workspace)(project=project)

        if not magpie_workspace:
            return JsonResponse(
                {'error': 'No Magpie workspace found for this project.'},
                status=400
            )

        # Get stack configuration
        from factory.stack_configs import get_stack_config
        stack_config = get_stack_config(project.stack, project)
        project_dir = stack_config['project_dir']
        workspace_path = f"/workspace/{project_dir}"
        log_file_path = f"{workspace_path}/dev.log"
        job_id = magpie_workspace.job_id

        # Get number of lines from query param (default 100, max 500)
        lines = min(int(request.GET.get('lines', 100)), 500)

        logger.info(f"Fetching {lines} lines of dev server logs for ticket {ticket_id}")

        # Get Magpie client
        client = get_magpie_client()

        # Tail the dev.log file
        log_command = f"tail -n {lines} {log_file_path} 2>/dev/null || echo ''"

        log_result = _run_magpie_ssh(client, job_id, log_command, timeout=30, with_node_env=False, project_id=project.id)

        logs = log_result.get('stdout', '')

        # Also check if the dev server is running
        status_command = f"""
            if [ -f {workspace_path}/.devserver_pid ]; then
                pid=$(cat {workspace_path}/.devserver_pid)
                if kill -0 "$pid" 2>/dev/null; then
                    echo "running:$pid"
                else
                    echo "stopped"
                fi
            else
                echo "stopped"
            fi
        """
        status_result = _run_magpie_ssh(client, job_id, status_command, timeout=10, with_node_env=False, project_id=project.id)
        status_output = status_result.get('stdout', '').strip()

        is_running = status_output.startswith('running')
        pid = status_output.split(':')[1] if is_running else None

        return JsonResponse({
            'success': True,
            'logs': logs,
            'is_running': is_running,
            'pid': pid,
            'lines_requested': lines
        })

    except ProjectTicket.DoesNotExist:
        return JsonResponse(
            {'error': 'Ticket not found'},
            status=404
        )
    except Exception as e:
        logger.error(f"Error fetching dev server logs: {e}", exc_info=True)
        return JsonResponse(
            {'error': str(e)},
            status=500
        )


@login_required
@require_http_methods(["GET"])
def get_workspace_dev_server_logs(request, workspace_id):
    """
    Get the dev server logs from a workspace by workspace_id.
    Query params:
        - lines: Number of lines to tail (default 100, max 500)
    """
    try:
        # Get the workspace
        workspace = MagpieWorkspace.objects.select_related('project').get(workspace_id=workspace_id)

        # Check permissions - user must own the project
        if workspace.project.owner != request.user:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

        # Check if Magpie is available
        if not magpie_available():
            return JsonResponse(
                {'error': 'Magpie workspace execution is not available.'},
                status=503
            )

        # Get stack configuration
        from factory.stack_configs import get_stack_config
        project = workspace.project
        stack_config = get_stack_config(project.stack, project)
        project_dir = stack_config['project_dir']
        workspace_path = f"/workspace/{project_dir}"
        log_file_path = f"{workspace_path}/dev.log"
        job_id = workspace.job_id

        # Get number of lines from query param (default 100, max 500)
        lines = min(int(request.GET.get('lines', 100)), 500)

        logger.info(f"Fetching {lines} lines of dev server logs for workspace {workspace_id}")

        # Get Magpie client
        client = get_magpie_client()

        # Tail the dev.log file
        log_command = f"tail -n {lines} {log_file_path} 2>/dev/null || echo ''"

        log_result = _run_magpie_ssh(client, job_id, log_command, timeout=30, with_node_env=False, project_id=project.id)

        logs = log_result.get('stdout', '')

        # Also check if the dev server is running
        status_command = f"""
            if [ -f {workspace_path}/.devserver_pid ]; then
                pid=$(cat {workspace_path}/.devserver_pid)
                if kill -0 "$pid" 2>/dev/null; then
                    echo "running:$pid"
                else
                    echo "stopped"
                fi
            else
                echo "stopped"
            fi
        """
        status_result = _run_magpie_ssh(client, job_id, status_command, timeout=10, with_node_env=False, project_id=workspace.project.id)
        status_output = status_result.get('stdout', '').strip()

        is_running = status_output.startswith('running')
        pid = status_output.split(':')[1] if is_running else None

        return JsonResponse({
            'success': True,
            'logs': logs,
            'is_running': is_running,
            'pid': pid,
            'lines_requested': lines
        })

    except MagpieWorkspace.DoesNotExist:
        return JsonResponse(
            {'error': 'Workspace not found'},
            status=404
        )
    except Exception as e:
        logger.error(f"Error fetching dev server logs for workspace: {e}", exc_info=True)
        return JsonResponse(
            {'error': str(e)},
            status=500
        )
