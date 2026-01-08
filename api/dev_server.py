"""
API endpoints for managing development servers for ticket previews using Magpie workspaces.
"""
import logging
import textwrap
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from asgiref.sync import async_to_sync
from projects.models import ProjectTicket
from development.models import MagpieWorkspace
from accounts.models import ExternalServicesAPIKeys, GitHubToken

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


def _ensure_code_in_workspace(client, workspace, project, user):
    """
    Ensure code exists in the workspace. If not, clone from GitHub or use template.
    Returns (success, message)
    """
    job_id = workspace.job_id
    workspace_path = "/workspace/nextjs-app"

    # First, check if code already exists
    check_cmd = f"test -d {workspace_path} && test -f {workspace_path}/package.json && echo 'EXISTS' || echo 'MISSING'"
    check_result = _run_magpie_ssh(client, job_id, check_cmd, timeout=30, with_node_env=False)

    if 'EXISTS' in check_result.get('stdout', ''):
        logger.info(f"[CODE_SETUP] Code already exists in workspace")
        return True, "Code already exists"

    logger.info(f"[CODE_SETUP] Code missing, setting up...")

    # Check if project has GitHub repo configured (via IndexedRepository)
    indexed_repo = getattr(project, 'indexed_repository', None)

    if indexed_repo and indexed_repo.github_url:
        # Clone from GitHub
        github_token_obj = GitHubToken.objects.filter(user=user).first()
        github_token = github_token_obj.access_token if github_token_obj else None

        if github_token and setup_git_in_workspace:
            owner = indexed_repo.github_owner
            repo = indexed_repo.github_repo_name
            branch_name = indexed_repo.github_branch or 'main'

            logger.info(f"[CODE_SETUP] Cloning {owner}/{repo} branch {branch_name}")

            git_result = setup_git_in_workspace(
                workspace_id=job_id,
                owner=owner,
                repo_name=repo,
                branch_name=branch_name,
                token=github_token
            )

            if git_result.get('status') == 'success':
                # Run npm install
                logger.info(f"[CODE_SETUP] Running npm install...")
                npm_result = _run_magpie_ssh(
                    client, job_id,
                    f"cd {workspace_path} && npm install",
                    timeout=300, with_node_env=True
                )
                if npm_result.get('exit_code', 0) == 0:
                    # Update workspace metadata
                    metadata = workspace.metadata or {}
                    metadata['git_configured'] = True
                    metadata['git_branch'] = branch_name
                    workspace.metadata = metadata
                    workspace.save()
                    return True, f"Cloned {owner}/{repo} and installed dependencies"
                else:
                    return False, f"npm install failed: {npm_result.get('stderr', '')[:200]}"
            else:
                return False, f"Git clone failed: {git_result.get('message', 'unknown error')}"
        else:
            return False, "GitHub token not configured"
    else:
        # No GitHub repo - clone the default template
        logger.info(f"[CODE_SETUP] No GitHub repo, cloning default template")

        template_cmd = '''
cd /workspace
if [ ! -d nextjs-app ]; then
    git clone https://github.com/lfg-hq/nextjs-template nextjs-app
    cd nextjs-app
    npm install
    echo "TEMPLATE_INSTALLED"
else
    echo "ALREADY_EXISTS"
fi
'''
        result = _run_magpie_ssh(client, job_id, template_cmd, timeout=300, with_node_env=True)

        if result.get('exit_code', 0) == 0:
            # Update workspace metadata
            metadata = workspace.metadata or {}
            metadata['template_installed'] = True
            workspace.metadata = metadata
            workspace.save()
            return True, "Default Next.js template installed"
        else:
            return False, f"Template setup failed: {result.get('stderr', '')[:200]}"


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

        workspace_path = "/workspace/nextjs-app"
        job_id = magpie_workspace.job_id

        logger.info(f"[DEV_SERVER] Starting dev server for ticket {ticket_id}")
        logger.info(f"[DEV_SERVER] Workspace ID: {magpie_workspace.workspace_id}")
        logger.info(f"[DEV_SERVER] Workspace status: {magpie_workspace.status}")
        logger.info(f"[DEV_SERVER] Job ID: {job_id}")
        logger.info(f"[DEV_SERVER] Workspace path: {workspace_path}")
        logger.info(f"[DEV_SERVER] IPv6: {magpie_workspace.ipv6_address}")

        # Get Magpie client
        client = get_magpie_client()

        # Step 0: Ensure code exists in workspace
        logger.info(f"[DEV_SERVER] Checking workspace structure...")
        code_success, code_message = _ensure_code_in_workspace(client, magpie_workspace, project, request.user)
        logger.info(f"[DEV_SERVER] Code setup result: {code_success}, {code_message}")

        if not code_success:
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

        # Step 1: Kill existing processes and remove lock files
        cleanup_command = textwrap.dedent(f"""
            cd {workspace_path}

            echo "Stopping all Node processes..."
            
            # Nuclear option - kill all node processes
            killall -9 node 2>/dev/null || true
            pkill -9 node 2>/dev/null || true
            
            # Kill anything on port 3000
            fuser -k -9 3000/tcp 2>/dev/null || true
            
            # Clean up files
            rm -rf .next || true
            rm -f .devserver_pid || true
            rm -f package-lock.json || true
            
            # Wait for port to be fully released
            sleep 3
            
            echo "Cleanup completed"
        """)

        cleanup_result = _run_magpie_ssh(client, job_id, cleanup_command, timeout=60, with_node_env=True, project_id=project.id)
        
        logger.info(f"[CLEANUP] Result: {cleanup_result}")
        logger.info(f"[CLEANUP] Exit code: {cleanup_result.get('exit_code')}")
        logger.info(f"[CLEANUP] Stdout: {cleanup_result.get('stdout', '')[:500]}")
        logger.info(f"[CLEANUP] Stderr: {cleanup_result.get('stderr', '')[:500]}")

        if cleanup_result.get('exit_code') != 0:
            logger.warning(f"Cleanup had non-zero exit code {cleanup_result.get('exit_code')}: {cleanup_result.get('stderr', '')}")

        # Step 2: Start the dev server in background
        start_command = textwrap.dedent(f"""
            cd {workspace_path}

            # Clear old logs
            : > /workspace/nextjs-app/dev.log

            # Start npm run dev in background
            nohup npm run dev -- --hostname :: --port 3000 >/workspace/nextjs-app/dev.log 2>&1 &
            pid=$!
            echo "$pid" > .devserver_pid
            echo "PID:$pid"

            # Wait a moment to ensure process started
            sleep 3

            # Check if process is still running
            if kill -0 "$pid" 2>/dev/null; then
                echo "Dev server started successfully with PID $pid"
            else
                echo "ERROR: Dev server failed to start"
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

        # Get proxy URL, fetch if not available
        preview_url = None
        if get_or_fetch_proxy_url:
            preview_url = get_or_fetch_proxy_url(magpie_workspace, port=3000, client=client)
        if not preview_url:
            preview_url = f'http://[{magpie_workspace.ipv6_address}]:3000' if magpie_workspace.ipv6_address else 'http://localhost:3000'

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

        workspace_path = magpie_workspace.project_path or "/workspace/nextjs-app"
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
