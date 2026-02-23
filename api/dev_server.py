"""
API endpoints for managing development servers for ticket previews using Mags workspaces.
"""
import logging
import os
import textwrap
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from projects.models import ProjectTicket, TicketLog
from development.models import Sandbox
from accounts.models import ExternalServicesAPIKeys, GitHubToken
from projects.websocket_utils import send_workspace_progress, send_ticket_log_notification

logger = logging.getLogger(__name__)

# Import Mags utilities
try:
    from factory.mags import (
        run_command, get_or_create_workspace_job,
        workspace_name_for_preview, get_http_proxy_url,
        create_preview_url_alias,
        MAGS_WORKING_DIR, PREVIEW_SETUP_SCRIPT, MagsAPIError,
    )
    mags_available = True
except ImportError:
    logger.error("Failed to import Mags utilities from factory.mags")
    run_command = None
    mags_available = False

# Import git setup function
try:
    from tasks.task_definitions import setup_git_in_workspace
except ImportError:
    logger.error("Failed to import setup_git_in_workspace from tasks.task_definitions")
    setup_git_in_workspace = None


def _get_ticket_workspace(ticket):
    """
    Get the Sandbox for a ticket's CLI workspace.
    If the ticket's sandbox is broken (error/stopped), delete it and provision a fresh one.
    Returns (workspace, error_response) — error_response is None on success.
    """
    from factory.mags import (
        get_latest_claude_auth_workspace_id,
        workspace_name_for_ticket,
        workspace_name_for_claude_auth,
    )

    # 1. Try ticket's own healthy sandbox
    ws = Sandbox.objects.filter(
        mags_workspace_id__startswith=f'{ticket.id}-',
        workspace_type='ticket',
    ).exclude(status__in=['stopped', 'error']).order_by('-updated_at').first()
    if ws:
        return ws, None

    # 2. Ticket has no healthy sandbox — delete any broken ones and provision fresh
    broken = Sandbox.objects.filter(
        mags_workspace_id__startswith=f'{ticket.id}-',
        workspace_type='ticket',
        status__in=['stopped', 'error'],
    )
    if broken.exists():
        logger.info(f"[DEV_SERVER] Deleting {broken.count()} broken sandbox(es) for ticket {ticket.id}")
        broken.delete()

    # Provision a new workspace
    user = ticket.project.owner
    base_ws = get_latest_claude_auth_workspace_id(user.id) or workspace_name_for_claude_auth(user.id)
    ticket_ws = workspace_name_for_ticket(ticket.id)
    logger.info(f"[DEV_SERVER] Provisioning new workspace {ticket_ws} from base {base_ws}")

    try:
        probe_result = run_command(
            workspace_id=ticket_ws,
            command='echo "WORKSPACE_READY"',
            timeout=180,
            with_node_env=False,
            base_workspace_id=base_ws,
        )
        if 'WORKSPACE_READY' not in probe_result.get('stdout', ''):
            logger.error(f"[DEV_SERVER] New workspace probe failed: {probe_result}")
            return None, JsonResponse(
                {'error': 'Failed to provision a new workspace. Please try again.'},
                status=500
            )
    except Exception as e:
        logger.error(f"[DEV_SERVER] Workspace provisioning error: {e}", exc_info=True)
        return None, JsonResponse(
            {'error': f'Failed to provision workspace: {str(e)}'},
            status=500
        )

    # Create sandbox record
    ws = Sandbox.objects.create(
        project=ticket.project,
        user=user,
        job_id=ticket_ws,
        workspace_id=ticket_ws,
        mags_workspace_id=ticket_ws,
        mags_base_workspace_id=base_ws,
        workspace_type='ticket',
        status='ready',
    )
    logger.info(f"[DEV_SERVER] New workspace ready: {ticket_ws}")
    return ws, None


def _get_job_request_id(workspace_id):
    """Get the Mags job request_id for a workspace overlay name.

    Uses client.find_job() for a direct lookup by workspace name,
    falling back to listing all jobs if that fails.
    """
    from factory.mags import _get_mags_client, _find_existing_workspace_job
    # 1. Direct lookup via find_job (fast, reliable)
    try:
        client = _get_mags_client()
        job = client.find_job(workspace_id)
        if job:
            req_id = job.get('request_id') or job.get('id')
            if req_id:
                logger.info(f"[DEV_SERVER] find_job resolved {workspace_id} -> {req_id}")
                return req_id
    except Exception as e:
        logger.debug(f"[DEV_SERVER] find_job failed for {workspace_id}: {e}")

    # 2. Fallback: scan all running jobs
    try:
        job = _find_existing_workspace_job(workspace_id)
        return job.get('request_id') or job.get('id')
    except Exception as e:
        logger.warning(f"[DEV_SERVER] Could not find job for workspace {workspace_id}: {e}")
        return None


def _ensure_code_in_workspace(workspace, project, user, ticket=None, send_progress=True):
    """
    Ensure code exists in the workspace and is on the correct branch.
    - If ticket has github_branch, use that
    - Otherwise default to 'lfg-agent'
    Returns (success, message)
    """
    from factory.stack_configs import get_stack_config

    workspace_id = workspace.mags_workspace_id or workspace.workspace_id
    stack_config = get_stack_config(project.stack, project)
    project_dir = stack_config['project_dir']
    workspace_path = f"{MAGS_WORKING_DIR}/{project_dir}"
    project_id = str(project.project_id)

    logger.info(f"[CODE_SETUP] Project stack: {project.stack}, project_dir: {project_dir}")

    # Helper to send progress if enabled
    def progress(step, message=None, extra_data=None):
        if send_progress:
            send_workspace_progress(project_id, step, message, extra_data=extra_data)

    # Determine target branch: saved ticket branch > derived ticket branch > lfg-agent
    if ticket and ticket.github_branch:
        target_branch = ticket.github_branch
        logger.info(f"[CODE_SETUP] Using ticket branch: {target_branch}")
    elif ticket:
        target_branch = f'feature/ticket-{ticket.id}'
        logger.info(f"[CODE_SETUP] No saved branch, using derived: {target_branch}")
    else:
        target_branch = 'lfg-agent'
        logger.info(f"[CODE_SETUP] No ticket context, defaulting to lfg-agent")

    # Check if code already exists - use stack-specific file patterns
    progress('checking_workspace', 'Checking workspace structure...')
    file_patterns = stack_config.get('file_patterns', ['package.json'])
    # Check for first file pattern (most common indicator file)
    check_file = file_patterns[0] if file_patterns else 'package.json'
    check_cmd = f"test -d {workspace_path} && test -f {workspace_path}/{check_file} && echo 'EXISTS' || echo 'MISSING'"
    check_result = run_command(workspace_id, check_cmd, timeout=30)

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
            switch_result = run_command(workspace_id, switch_cmd, timeout=120)
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
            npm_result = run_command(
                workspace_id,
                f"cd {workspace_path} && npm config set cache {MAGS_WORKING_DIR}/.npm-cache && npm install",
                timeout=300,
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
                    job_id=workspace_id,
                    owner=owner,
                    repo_name=repo,
                    branch_name=target_branch,
                    token=github_token,
                    stack=project.stack,
                )

                if git_result.get('status') == 'success':
                    # Run npm install
                    logger.info(f"[CODE_SETUP] Running npm install...")
                    npm_result = run_command(
                        workspace_id,
                        f"cd {workspace_path} && npm config set cache {MAGS_WORKING_DIR}/.npm-cache && npm install",
                        timeout=300,
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
cd {MAGS_WORKING_DIR}
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
        result = run_command(workspace_id, empty_project_cmd, timeout=60)

        if result.get('exit_code', 0) == 0:
            # Update workspace metadata
            metadata = workspace.metadata or {}
            metadata['empty_project_created'] = True
            workspace.metadata = metadata
            workspace.save()
            return True, "Empty project directory created"
        else:
            return False, f"Project setup failed: {result.get('stderr', '')[:200]}"


def _log_dev_server_error(ticket_id, error_msg):
    """Log a dev server error to the ticket's action stream so the agent can see it."""
    try:
        log_entry = TicketLog.objects.create(
            ticket_id=ticket_id,
            log_type='error',
            command='Dev Server',
            explanation='Dev server preview failed',
            output=error_msg[:2000],
        )
        send_ticket_log_notification(ticket_id, {
            'id': log_entry.id,
            'log_type': log_entry.log_type,
            'command': log_entry.command,
            'explanation': log_entry.explanation,
            'output': log_entry.output,
            'created_at': log_entry.created_at.isoformat(),
        })
    except Exception as e:
        logger.warning(f"[DEV_SERVER] Failed to log error to ticket {ticket_id}: {e}")


def start_dev_server_core(ticket, user):
    """
    Start dev server for a ticket. No HTTP request dependency.

    Args:
        ticket: ProjectTicket instance (with project already selected)
        user: User instance (project owner)

    Returns:
        dict with keys: success, url, pid, workspace_id, error, message, auto_fix, status_code
    """
    project = ticket.project
    ticket_id = ticket.id

    # Check if Mags is available
    if not mags_available:
        return {
            'success': False,
            'error': 'Workspace service is not available. Please check configuration.',
            'status_code': 503,
        }

    # Get the Sandbox for this ticket
    sandbox, err_resp = _get_ticket_workspace(ticket)
    if err_resp:
        # err_resp is a JsonResponse — extract content for the dict return
        import json as _json
        err_body = _json.loads(err_resp.content)
        return {
            'success': False,
            'error': err_body.get('error', 'Workspace provisioning failed'),
            'status_code': err_resp.status_code,
        }

    # Ensure workspace job is running
    workspace_id = sandbox.mags_workspace_id or sandbox.workspace_id
    job_id = sandbox.mags_job_id or sandbox.job_id

    # Get stack configuration
    from factory.stack_configs import get_stack_config
    stack_config = get_stack_config(project.stack, project)
    project_dir = stack_config['project_dir']
    workspace_path = f"{MAGS_WORKING_DIR}/{project_dir}"

    logger.info(f"[DEV_SERVER] Starting dev server for ticket {ticket_id}")
    logger.info(f"[DEV_SERVER] Project stack: {project.stack}, project_dir: {project_dir}")
    logger.info(f"[DEV_SERVER] Job ID: {job_id}")
    logger.info(f"[DEV_SERVER] Workspace path: {workspace_path}")

    project_id = str(project.project_id)

    # If this is the ticket's own workspace (code already built by Claude),
    # skip the heavy code setup. Only run it for non-ticket workspaces.
    sandbox_ws_id = sandbox.mags_workspace_id or sandbox.workspace_id
    is_ticket_workspace = (
        sandbox.workspace_type == 'ticket' and
        sandbox_ws_id and str(sandbox_ws_id).startswith(f'{ticket.id}-')
    )

    if not is_ticket_workspace:
        # Step 0: Ensure code exists in workspace and is on correct branch
        logger.info(f"[DEV_SERVER] Non-ticket workspace, running code setup...")
        code_success, code_message = _ensure_code_in_workspace(sandbox, project, user, ticket=ticket)
        logger.info(f"[DEV_SERVER] Code setup result: {code_success}, {code_message}")

        if not code_success:
            send_workspace_progress(project_id, 'error', f'Failed to set up code: {code_message}', error=code_message)
            _log_dev_server_error(ticket_id, f'Code setup failed: {code_message}')
            return {
                'success': False,
                'error': f'Failed to set up code in workspace: {code_message}',
                'status_code': 500,
            }

        # Step 0.5: Run bootstrap script to ensure stack tools are installed
        bootstrap_script = stack_config.get('bootstrap_script', '')
        if bootstrap_script and project.stack != 'nextjs':
            send_workspace_progress(project_id, 'installing_tools', f'Checking/installing {stack_config["name"]} tools...')
            bootstrap_result = run_command(workspace_id, bootstrap_script, timeout=300)
            if bootstrap_result.get('exit_code', 0) != 0:
                logger.warning(f"[DEV_SERVER] Bootstrap warning: {bootstrap_result.get('stderr', '')[:200]}")
    else:
        logger.info(f"[DEV_SERVER] Using ticket's own workspace — skipping code setup")

    # Pre-check: verify project directory exists in workspace
    dir_verify = run_command(workspace_id, f"test -d {workspace_path} && echo DIR_OK || echo DIR_MISSING", timeout=15)
    if 'DIR_MISSING' in dir_verify.get('stdout', '') or 'DIR_OK' not in dir_verify.get('stdout', ''):
        logger.warning(f"[DEV_SERVER] Project directory {workspace_path} missing in workspace {workspace_id}, running code setup...")
        # Code is missing — set it up regardless of workspace type
        code_success, code_message = _ensure_code_in_workspace(sandbox, project, user, ticket=ticket)
        logger.info(f"[DEV_SERVER] Code setup result: {code_success}, {code_message}")

        if not code_success:
            error_msg = f"Failed to set up code in workspace: {code_message}"
            send_workspace_progress(project_id, 'error', error_msg, error=error_msg)
            _log_dev_server_error(ticket_id, f'Code setup failed: {code_message}')
            return {'success': False, 'error': error_msg, 'status_code': 500}

        # Re-check after setup
        dir_verify2 = run_command(workspace_id, f"test -d {workspace_path} && echo DIR_OK || echo DIR_MISSING", timeout=15)
        if 'DIR_MISSING' in dir_verify2.get('stdout', '') or 'DIR_OK' not in dir_verify2.get('stdout', ''):
            logger.error(f"[DEV_SERVER] Project directory still missing after code setup — workspace is broken")
            sandbox.status = 'error'
            sandbox.save(update_fields=['status'])
            error_msg = f"Workspace filesystem is broken — code setup succeeded but files didn't persist."
            send_workspace_progress(project_id, 'error', error_msg, error=error_msg)
            _log_dev_server_error(ticket_id, error_msg)
            return {'success': False, 'error': error_msg, 'status_code': 500}

    # Step 1: Kill existing processes and remove lock files
    send_workspace_progress(project_id, 'clearing_cache', 'Clearing cache and stopping existing processes...')

    # Build stack-specific cleanup command
    # Use port 8080 — this is the Mags default proxy port. The URL alias
    # (*.app.lfg.run) routes to 8080 automatically, so running the dev
    # server on 8080 means the preview works without custom port mapping.
    MAGS_PROXY_PORT = 8080
    default_port = project.custom_default_port or MAGS_PROXY_PORT
    if project.stack == 'nextjs':
        cleanup_extras = """
        npm config set cache {MAGS_WORKING_DIR}/.npm-cache
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

    cleanup_result = run_command(workspace_id, cleanup_command, timeout=60)

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
    # default_port is already set to MAGS_PROXY_PORT (8080) above
    pre_dev_cmd = stack_config.get('pre_dev_cmd', '')

    # Customize dev command for different stacks
    if project.stack == 'nextjs':
        final_dev_cmd = f"npm run dev -- --hostname :: --port {default_port}"
    elif project.stack == 'astro':
        final_dev_cmd = f"npx astro dev --host 0.0.0.0 --port {default_port}"
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

    start_result = run_command(workspace_id, start_command, timeout=120)

    logger.info(f"[START] Result: {start_result}")
    logger.info(f"[START] Exit code: {start_result.get('exit_code')}")
    logger.info(f"[START] Stdout: {start_result.get('stdout', '')}")
    logger.info(f"[START] Stderr: {start_result.get('stderr', '')}")

    if start_result.get('exit_code') != 0:
        stdout = start_result.get('stdout', '')
        stderr = start_result.get('stderr', '')
        error_msg = stderr or stdout or 'Unknown error - command exited with non-zero status'
        logger.error(f"Failed to start dev server (exit {start_result.get('exit_code')}): stdout={stdout}, stderr={stderr}")

        # Extract just the error from dev.log output (between the === markers)
        dev_log_error = ''
        if '=== Last' in stdout and '=== End' in stdout:
            dev_log_error = stdout.split('=== Last')[1].split('===')[1].strip('= \n')
            if dev_log_error.startswith('of dev.log'):
                dev_log_error = dev_log_error[len('of dev.log'):].strip('= \n')

        # Pipe the error to the ticket's chat agent so Claude can fix it
        fix_message = (
            f"The dev server failed to start with the following error:\n\n"
            f"```\n{dev_log_error or error_msg[:500]}\n```\n\n"
            f"Please fix this error so the dev server can run successfully. "
            f"The dev command is: `{full_dev_cmd}`"
        )
        logger.info(f"[DEV_SERVER] Piping server error to ticket chat agent for auto-fix")
        send_workspace_progress(project_id, 'fixing_error', 'Dev server failed — asking Claude to fix it...')

        try:
            # Create a system message log entry
            fix_log = TicketLog.objects.create(
                ticket=ticket,
                log_type='user_message',
                command=fix_message,
                explanation='Auto-fix request from Preview (dev server failed to start)',
            )
            send_ticket_log_notification(ticket.id, {
                'id': fix_log.id,
                'log_type': 'user_message',
                'command': fix_message,
                'explanation': fix_log.explanation,
                'output': '',
                'exit_code': None,
                'created_at': fix_log.created_at.isoformat()
            })

            # Trigger Claude CLI chat in background thread
            import threading
            from tasks.task_definitions import execute_ticket_chat_cli

            session_id = sandbox.cli_session_id

            def run_auto_fix():
                try:
                    execute_ticket_chat_cli(
                        ticket_id=ticket.id,
                        project_id=project.id,
                        conversation_id=ticket.id,
                        message=fix_message,
                        session_id=session_id,
                    )
                except Exception as e:
                    logger.error(f"[DEV_SERVER] Auto-fix chat error: {e}", exc_info=True)

            thread = threading.Thread(target=run_auto_fix, daemon=True)
            thread.start()

        except Exception as e:
            logger.error(f"[DEV_SERVER] Failed to trigger auto-fix: {e}", exc_info=True)

        return {
            'success': False,
            'auto_fix': True,
            'message': 'Dev server failed to start. Claude is working on a fix...',
            'error': error_msg[:200],
            'status_code': 200,
        }

    # Extract PID from output
    stdout = start_result.get('stdout', '')
    pid = None
    for line in stdout.split('\n'):
        if 'PID:' in line:
            pid = line.split('PID:')[1].strip()
            break

    logger.info(f"Dev server started successfully with PID: {pid}")

    # Get preview URL via Mags HTTP access + stable alias
    send_workspace_progress(project_id, 'assigning_proxy', 'Getting preview URL...')
    preview_url = None

    # Step A: Enable HTTP access on the port. Since we run the dev server
    # on 8080 (the Mags default), the URL alias routes there automatically.
    # enable_access is still called to ensure the port is open and to
    # capture the raw proxy URL as a fallback.
    mags_job_id = sandbox.mags_job_id or sandbox.job_id

    # Attempt 1: use stored mags_job_id (the original request_id)
    if mags_job_id:
        try:
            logger.info(f"[DEV_SERVER] Enabling HTTP access: mags_job_id={mags_job_id}, port={default_port}")
            raw_url = get_http_proxy_url(mags_job_id, default_port)
            if raw_url and not raw_url.startswith('http://localhost'):
                preview_url = raw_url
                logger.info(f"[DEV_SERVER] enable_access returned URL: {raw_url}")
        except Exception as e:
            logger.warning(f"[DEV_SERVER] enable_access failed for job {mags_job_id}: {e}")

    # Attempt 2: resolve a fresh request_id via find_job (handles stale mags_job_id)
    if not preview_url:
        try:
            from factory.mags import _get_mags_client
            client = _get_mags_client()
            job = client.find_job(workspace_id)
            if job:
                fresh_id = job.get('request_id') or job.get('id')
                if fresh_id and fresh_id != mags_job_id:
                    logger.info(f"[DEV_SERVER] Retrying enable_access with fresh request_id={fresh_id}, port={default_port}")
                    raw_url = get_http_proxy_url(fresh_id, default_port)
                    if raw_url and not raw_url.startswith('http://localhost'):
                        preview_url = raw_url
                    # Save the fresh request_id regardless of URL response
                    sandbox.mags_job_id = fresh_id
                    sandbox.save(update_fields=['mags_job_id', 'updated_at'])
                    logger.info(f"[DEV_SERVER] Updated mags_job_id to {fresh_id}")
        except Exception as e:
            logger.warning(f"[DEV_SERVER] Fallback enable_access also failed: {e}")

    # Step B: Create a stable URL alias (uses workspace_id, not request_id).
    # This maps <subdomain>.app.lfg.run to the workspace's active job.
    # Always attempt this — it's the primary way to get a working preview URL.
    alias_url = create_preview_url_alias(workspace_id, project_id)
    if alias_url:
        logger.info(f"[DEV_SERVER] Using stable alias URL: {alias_url}")
        preview_url = alias_url

    if not preview_url:
        logger.warning(f"[DEV_SERVER] Could not obtain proxy URL, falling back to localhost:{default_port}")
        preview_url = f'http://localhost:{default_port}'

    # Save proxy_url on the sandbox for future use
    if preview_url and not preview_url.startswith('http://localhost'):
        sandbox.proxy_url = preview_url
        sandbox.save(update_fields=['proxy_url', 'updated_at'])

    # Step C: Ask Claude to whitelist the proxy URL in the project config
    # (e.g. Vite allowedHosts, Django ALLOWED_HOSTS, etc.)
    # Run in background so we don't block the response.
    if preview_url and not preview_url.startswith('http://localhost'):
        try:
            from urllib.parse import urlparse
            proxy_host = urlparse(preview_url).hostname
            if proxy_host:
                import threading
                from tasks.task_definitions import execute_ticket_chat_cli

                whitelist_message = (
                    f"The dev server preview is being served through a proxy at {preview_url} "
                    f"(hostname: {proxy_host}). "
                    f"Please ensure this hostname is whitelisted/allowed in the project configuration "
                    f"so the server accepts requests from it. For example:\n"
                    f"- Vite/Astro: add `server.allowedHosts` or `vite.server.allowedHosts` in the config\n"
                    f"- Django: add to ALLOWED_HOSTS\n"
                    f"- Next.js: usually no change needed\n\n"
                    f"Check the project config at {workspace_path} and make the necessary change. "
                    f"Do NOT restart the server — just update the config file."
                )
                whitelist_session_id = sandbox.cli_session_id

                def run_whitelist_fix():
                    try:
                        execute_ticket_chat_cli(
                            ticket_id=ticket.id,
                            project_id=project.id,
                            conversation_id=ticket.id,
                            message=whitelist_message,
                            session_id=whitelist_session_id,
                        )
                    except Exception as e:
                        logger.warning(f"[DEV_SERVER] Whitelist fix error: {e}")

                thread = threading.Thread(target=run_whitelist_fix, daemon=True)
                thread.start()
                logger.info(f"[DEV_SERVER] Started whitelist fix thread for host {proxy_host}")
        except Exception as e:
            logger.warning(f"[DEV_SERVER] Could not start whitelist fix: {e}")

    # Send completion notification
    send_workspace_progress(project_id, 'complete', 'Dev server is ready!', extra_data={'url': preview_url})

    return {
        'success': True,
        'message': 'Dev server started successfully',
        'pid': pid,
        'workspace_id': sandbox.workspace_id,
        'url': preview_url,
    }


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def start_dev_server(request, ticket_id):
    """
    Start a development server for the ticket's project using sandbox workspace.
    Thin HTTP wrapper around start_dev_server_core().
    """
    try:
        ticket = ProjectTicket.objects.select_related('project').get(id=ticket_id)

        if ticket.project.owner != request.user:
            return JsonResponse({'error': 'Permission denied'}, status=403)

        result = start_dev_server_core(ticket, request.user)
        status_code = 200 if result.get('success') else result.get('status_code', 500)
        return JsonResponse(result, status=status_code)

    except ProjectTicket.DoesNotExist:
        return JsonResponse(
            {'error': 'Ticket not found'},
            status=404
        )
    except Exception as e:
        logger.error(f"Error starting dev server: {e}", exc_info=True)
        _log_dev_server_error(ticket_id, f'Dev server failed: {str(e)}')
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

        # Check if Mags is available
        if not mags_available:
            return JsonResponse(
                {'error': 'Workspace service is not available. Please check configuration.'},
                status=503
            )

        # Get the Sandbox for this ticket
        sandbox, err_resp = _get_ticket_workspace(ticket)
        if err_resp:
            return err_resp

        # Use workspace regardless of status
        if sandbox.status != 'ready':
            logger.warning(f"Stopping dev server on workspace with status '{sandbox.status}'")

        # Get stack configuration
        from factory.stack_configs import get_stack_config
        stack_config = get_stack_config(project.stack, project)
        project_dir = stack_config['project_dir']
        workspace_path = f"{MAGS_WORKING_DIR}/{project_dir}"
        workspace_id = sandbox.mags_workspace_id or sandbox.workspace_id

        logger.info(f"Stopping dev server for ticket {ticket_id} in workspace {workspace_id}")

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

        stop_result = run_command(workspace_id, stop_command, timeout=60)

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

        # Check if Mags is available
        if not mags_available:
            return JsonResponse(
                {'error': 'Workspace service is not available. Please check configuration.'},
                status=503
            )

        # Get the Sandbox for this ticket
        sandbox, err_resp = _get_ticket_workspace(ticket)
        if err_resp:
            return err_resp

        # Get stack configuration
        from factory.stack_configs import get_stack_config
        stack_config = get_stack_config(project.stack, project)
        project_dir = stack_config['project_dir']
        workspace_path = f"{MAGS_WORKING_DIR}/{project_dir}"
        log_file_path = f"{workspace_path}/dev.log"
        workspace_id = sandbox.mags_workspace_id or sandbox.workspace_id

        # Get number of lines from query param (default 100, max 500)
        lines = min(int(request.GET.get('lines', 100)), 500)

        logger.info(f"Fetching {lines} lines of dev server logs for ticket {ticket_id}")

        # Tail the dev.log file
        log_command = f"tail -n {lines} {log_file_path} 2>/dev/null || echo ''"

        log_result = run_command(workspace_id, log_command, timeout=30)

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
        status_result = run_command(workspace_id, status_command, timeout=10)
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
        workspace = Sandbox.objects.select_related('project').get(workspace_id=workspace_id)

        # Check permissions - user must own the project
        if workspace.project.owner != request.user:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

        # Check if Mags is available
        if not mags_available:
            return JsonResponse(
                {'error': 'Workspace service is not available. Please check configuration.'},
                status=503
            )

        # Get stack configuration
        from factory.stack_configs import get_stack_config
        project = workspace.project
        stack_config = get_stack_config(project.stack, project)
        project_dir = stack_config['project_dir']
        workspace_path = f"{MAGS_WORKING_DIR}/{project_dir}"
        log_file_path = f"{workspace_path}/dev.log"
        ws_id = workspace.mags_workspace_id or workspace.workspace_id

        # Get number of lines from query param (default 100, max 500)
        lines = min(int(request.GET.get('lines', 100)), 500)

        logger.info(f"Fetching {lines} lines of dev server logs for workspace {workspace_id}")

        # Tail the dev.log file
        log_command = f"tail -n {lines} {log_file_path} 2>/dev/null || echo ''"

        log_result = run_command(ws_id, log_command, timeout=30)

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
        status_result = run_command(ws_id, status_command, timeout=10)
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

    except Sandbox.DoesNotExist:
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
