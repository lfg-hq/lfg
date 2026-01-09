import json
import os
import re
import asyncio
import subprocess
import logging
import textwrap
import time
from datetime import datetime
from pathlib import Path
from asgiref.sync import sync_to_async
from projects.models import Project, ProjectFeature, ProjectPersona, \
                            ProjectPRD, ProjectDesignSchema, ProjectTicket, \
                            ProjectImplementation, ProjectFile, ProjectTodoList, TicketLog, \
                            ProjectDesignFeature
from projects.websocket_utils import async_send_ticket_log_notification

from development.models import ServerConfig, MagpieWorkspace

from django.conf import settings
from django.core.cache import cache
from development.k8s_manager.manage_pods import execute_command_in_pod

from development.models import KubernetesPod
from accounts.models import GitHubToken, ExternalServicesAPIKeys
from chat.models import Conversation
from factory.notion_connector import NotionConnector
from projects.linear_sync import LinearSyncService
from django.utils import timezone
from tasks.task_manager import TaskManager

try:
    from magpie import Magpie
except ImportError:  # pragma: no cover - Magpie is optional in some environments
    Magpie = None

# Configure logger
logger = logging.getLogger(__name__)

# Import codebase indexing functions
try:
    from codebase_index.ai_integration import (
        get_codebase_context_for_feature,
        search_similar_implementations,
        get_codebase_context_for_prd,
        enhance_ticket_with_codebase_context
    )
    from codebase_index.tasks import start_repository_indexing
    from codebase_index.models import IndexedRepository
    from codebase_index.embeddings import generate_repository_insights
    CODEBASE_INDEX_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Codebase indexing not available: {e}")
    CODEBASE_INDEX_AVAILABLE = False


# ============================================================================
# MAGPIE WORKSPACE CONSTANTS & HELPERS
# ============================================================================

DEFAULT_MAGPIE_API_KEY = "e1e90cc27dfe6a50cc28699cdcb937ef8c443567b62cf064a063f9b34af0b91b"
MAGPIE_API_KEY = getattr(settings, "MAGPIE_API_KEY", os.getenv("MAGPIE_API_KEY", DEFAULT_MAGPIE_API_KEY))

MAGPIE_NODE_VERSION = "20.18.0"
MAGPIE_NODE_DISTRO = "linux-x64"
MAGPIE_WORKSPACE_DIR = "/workspace/nextjs-app"

MAGPIE_NODE_ENV_LINES = [
    "export PATH=/workspace/node/current/bin:$PATH",
    "export npm_config_prefix=/workspace/.npm-global",
    "export npm_config_cache=/workspace/.npm-cache",
    "export NODE_ENV=development",
    "mkdir -p /workspace/.npm-global/lib /workspace/.npm-cache",
]

MAGPIE_BOOTSTRAP_SCRIPT = """#!/bin/sh
set -eux
cd /workspace
echo "VM ready for Next.js provisioning" > /workspace/READY

# keep the job marked running so SSH window stays open for orchestration
while :; do sleep 3600 & wait $!; done
"""


def magpie_available() -> bool:
    """Return True when the Magpie SDK and API key are configured."""
    return Magpie is not None and bool(MAGPIE_API_KEY)


def get_magpie_client():
    """Instantiate a Magpie client or raise a helpful error."""
    if not magpie_available():
        raise RuntimeError("Magpie SDK or MAGPIE_API_KEY is not configured")
    # Create client with extended timeout for long-running commands (npm install, build, etc.)
    client = Magpie(api_key=MAGPIE_API_KEY)
    # Increase HTTP read timeout from default 30s to 5 minutes
    if hasattr(client, 'session'):
        client.session.timeout = 300
    elif hasattr(client, 'timeout'):
        client.timeout = 300
    return client


def _slugify_project_name(name: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower())
    slug = slug.strip('-')
    return slug or "turbo-app"


def _generate_proxy_subdomain(workspace: MagpieWorkspace) -> str:
    """
    Generate a custom subdomain for proxy URL based on project name.
    Format: {project-slug}-preview-{short-id}
    """
    import uuid

    # Get project name
    project_name = "app"
    if workspace.project:
        project_name = workspace.project.provided_name or workspace.project.name or "app"
    elif workspace.metadata and workspace.metadata.get('project_name'):
        project_name = workspace.metadata.get('project_name')

    # Slugify the project name
    slug = _slugify_project_name(project_name)

    # Add a short unique suffix to avoid collisions
    short_id = str(uuid.uuid4())[:6]

    # Create subdomain: max 63 chars for DNS labels
    subdomain = f"{slug}-preview-{short_id}"
    if len(subdomain) > 63:
        subdomain = f"{slug[:50]}-preview-{short_id}"

    return subdomain


def get_or_create_proxy_url(workspace: MagpieWorkspace, port: int = 3000, client=None) -> str | None:
    """
    Get the proxy URL for a workspace from database. If not exists, create a new
    proxy target with a custom subdomain name.

    Args:
        workspace: The MagpieWorkspace instance
        port: The port number for the proxy (default: 3000)
        client: Optional Magpie client. If not provided, one will be created.

    Returns:
        The proxy URL string, or None if unavailable
    """
    # Return existing proxy URL if available in database
    if workspace.proxy_url:
        logger.debug(f"[PROXY] Using existing proxy URL for workspace {workspace.workspace_id}: {workspace.proxy_url}")
        return workspace.proxy_url

    # No proxy URL in DB - create a new one
    try:
        if client is None:
            client = get_magpie_client()

        # Check if workspace has IPv6 address
        if not workspace.ipv6_address:
            logger.warning(f"[PROXY] Cannot create proxy - workspace {workspace.workspace_id} has no IPv6 address")
            return None

        ipv6 = workspace.ipv6_address.strip('[]')
        proxy_url = None

        # Try to create custom proxy target with custom subdomain (newer API)
        if hasattr(client, 'proxy_targets'):
            try:
                subdomain = _generate_proxy_subdomain(workspace)
                logger.info(f"[PROXY] Creating custom proxy target: subdomain={subdomain}, IPv6={ipv6}, port={port}")

                target = client.proxy_targets.create(
                    ipv6_address=ipv6,
                    port=port,
                    name=f"LFG Preview - {subdomain}",
                    subdomain=subdomain
                )

                # Extract proxy URL from response
                if hasattr(target, 'proxy_url'):
                    proxy_url = target.proxy_url
                elif isinstance(target, dict):
                    proxy_url = target.get('proxy_url') or target.get('url')

                # If no url field, construct it from subdomain
                if not proxy_url:
                    proxy_url = f"https://{subdomain}.app.lfg.run"

                logger.info(f"[PROXY] Created custom proxy target: {proxy_url}")

            except Exception as e:
                logger.warning(f"[PROXY] Custom proxy target creation failed, falling back to get_proxy_url: {e}")

        # Fallback: use get_proxy_url for existing jobs
        if not proxy_url:
            job_id = workspace.job_id
            logger.info(f"[PROXY] Fetching proxy URL for job {job_id}")
            proxy_url = client.jobs.get_proxy_url(job_id)

        if proxy_url:
            # Store the proxy URL in the database
            workspace.proxy_url = proxy_url
            workspace.save(update_fields=['proxy_url', 'updated_at'])
            logger.info(f"[PROXY] Stored proxy URL for workspace {workspace.workspace_id}: {proxy_url}")
            return proxy_url
        else:
            logger.warning(f"[PROXY] No proxy URL obtained for workspace {workspace.workspace_id}")
            return None

    except Exception as e:
        logger.error(f"[PROXY] Failed to get/create proxy URL for workspace {workspace.workspace_id}: {e}", exc_info=True)
        return None


# Keep old function name as alias for backward compatibility
def get_or_fetch_proxy_url(workspace: MagpieWorkspace, port: int = 3000, client=None) -> str | None:
    """Alias for get_or_create_proxy_url for backward compatibility."""
    return get_or_create_proxy_url(workspace, port, client)


async def async_get_or_fetch_proxy_url(workspace: MagpieWorkspace, port: int = 3000, client=None) -> str | None:
    """Async version of get_or_create_proxy_url."""
    return await sync_to_async(get_or_fetch_proxy_url, thread_sensitive=True)(workspace, port, client)


def _sanitize_string(value: str) -> str:
    """
    Remove NUL bytes and other problematic characters that PostgreSQL cannot store.
    """
    if not value:
        return ""
    # Remove NUL bytes (0x00) which PostgreSQL text fields cannot store
    sanitized = value.replace('\x00', '')
    # Optionally remove other control characters except newlines, tabs, and carriage returns
    # sanitized = ''.join(char for char in sanitized if char >= ' ' or char in '\n\r\t')
    return sanitized

def _truncate_output(value: str, limit: int = 4000) -> str:
    if not value:
        return ""
    # Sanitize NUL bytes first
    value = _sanitize_string(value)
    if len(value) <= limit:
        return value
    truncated = value[:limit]
    omitted = len(value) - limit
    return f"{truncated}\n... (truncated {omitted} characters)"


def _format_command_output(stdout: str, stderr: str, limit: int = 6000) -> str:
    stdout_trimmed = _truncate_output(stdout, limit // 2)
    stderr_trimmed = _truncate_output(stderr, limit // 2)
    parts = []
    if stdout_trimmed:
        parts.append(f"STDOUT:\n{stdout_trimmed}")
    if stderr_trimmed:
        parts.append(f"STDERR:\n{stderr_trimmed}")
    return "\n\n".join(parts) if parts else "(no output)"


def _run_magpie_ssh(client, job_id: str, command: str, timeout: int = 300, with_node_env: bool = True, project_id = None):
    env_lines = ["set -e", "cd /workspace"]
    if with_node_env:
        env_lines.extend(MAGPIE_NODE_ENV_LINES)

    # Add project-specific environment variables if project_id provided
    if project_id:
        project_env_exports = get_project_env_exports(project_id)
        if project_env_exports:
            env_lines.extend(project_env_exports)
            logger.info(f"[MAGPIE][SSH] Injecting {len(project_env_exports)} project env vars")

    wrapped = "\n".join(env_lines + [command])
    logger.info("[MAGPIE][SSH] job_id=%s timeout=%s command=%s", job_id, timeout, command.split('\n')[0][:120])
    print("[MAGPIE][SSH] Job prints", wrapped)
    result = client.jobs.ssh(job_id, wrapped, timeout=timeout)
    logger.debug(
        "[MAGPIE][SSH RESULT] job_id=%s exit_code=%s stdout_len=%s stderr_len=%s",
        job_id,
        getattr(result, 'exit_code', None),
        len(getattr(result, 'stdout', '') or ''),
        len(getattr(result, 'stderr', '') or ''),
    )
    return {
        "exit_code": getattr(result, 'exit_code', 0),
        "stdout": getattr(result, 'stdout', '') or '',
        "stderr": getattr(result, 'stderr', '') or ''
    }


def _extract_pid_from_output(output: str) -> str:
    if not output:
        return ""
    match = re.search(r"PID:(\d+)", output)
    if match:
        return match.group(1)
    match = re.search(r"\b(\d{3,})\b", output)
    return match.group(1) if match else ""


def _build_log_entries_from_steps(steps):
    log_entries = []
    for description, result in steps:
        if not isinstance(result, dict):
            continue
        log_entries.append({
            "title": description,
            "command": _truncate_output(result.get("command", ""), 600),
            "stdout": _truncate_output(result.get("stdout", ""), 800),
            "stderr": _truncate_output(result.get("stderr", ""), 800),
            "exit_code": result.get("exit_code")
        })
    return log_entries


def _bootstrap_magpie_workspace(client, job_id: str):
    """Install Node, scaffold the Next.js app, add Prisma, and launch the dev server."""
    steps = []

    install_node_cmd = textwrap.dedent(
        f"""
        mkdir -p node
        cd node
        if [ ! -d node-v{MAGPIE_NODE_VERSION}-{MAGPIE_NODE_DISTRO} ]; then
            if ! command -v curl >/dev/null 2>&1 || ! command -v xz >/dev/null 2>&1; then
                apk update
                apk add --no-cache curl xz
            fi
            curl -fsSL https://nodejs.org/dist/v{MAGPIE_NODE_VERSION}/node-v{MAGPIE_NODE_VERSION}-{MAGPIE_NODE_DISTRO}.tar.xz -o node.tar.xz
            tar -xf node.tar.xz
            rm node.tar.xz
            ln -sfn node-v{MAGPIE_NODE_VERSION}-{MAGPIE_NODE_DISTRO} current
        fi
        mkdir -p /workspace/.npm-global /workspace/.npm-cache
        """
    )
    install_result = _run_magpie_ssh(client, job_id, install_node_cmd, timeout=240, with_node_env=False)
    install_result["command"] = install_node_cmd
    steps.append(("Install Node.js", install_result))

    scaffold_cmd = textwrap.dedent(
        """
        rm -rf nextjs-app
        """
    )
    scaffold_result = _run_magpie_ssh(client, job_id, scaffold_cmd, timeout=360)
    scaffold_result["command"] = scaffold_cmd
    steps.append(("Write Next.js project skeleton", scaffold_result))

    install_dependencies_cmd = "cd nextjs-app && npm install"
    deps_result = _run_magpie_ssh(client, job_id, install_dependencies_cmd, timeout=480)
    deps_result["command"] = install_dependencies_cmd
    steps.append(("Install npm dependencies", deps_result))

    start_server_cmd = textwrap.dedent(
        """
        cd nextjs-app
        if [ -f .devserver_pid ]; then
          old_pid=$(cat .devserver_pid)
          if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
            kill "$old_pid" || true
          fi
        fi
        : > /workspace/nextjs-app/dev.log
        nohup npm run dev -- --hostname :: --port 3000 > /workspace/nextjs-app/dev.log 2>&1 &
        pid=$!
        echo "$pid" > .devserver_pid
        echo "PID:$pid"
        """
    )
    start_result = _run_magpie_ssh(client, job_id, start_server_cmd, timeout=120)
    start_result["command"] = start_server_cmd
    steps.append(("Launch dev server", start_result))

    # Allow the dev server a few seconds to boot
    time.sleep(5)

    preview_cmd = "cd nextjs-app && curl -s --max-time 5 http://127.0.0.1:3000 | head -n 20"
    preview_result = _run_magpie_ssh(client, job_id, preview_cmd, timeout=120)
    preview_result["command"] = preview_cmd
    steps.append(("Fetch preview", preview_result))

    return {
        "steps": steps,
        "pid": _extract_pid_from_output(start_result.get("stdout", "")),
        "preview": preview_result.get("stdout", "")
    }


def _update_workspace_metadata(workspace, **metadata):
    current_metadata = workspace.metadata or {}
    if metadata:
        current_metadata.update(metadata)
    workspace.metadata = current_metadata
    workspace.last_seen_at = timezone.now()
    workspace.save(update_fields=['metadata', 'last_seen_at', 'updated_at'])


async def _fetch_workspace(project=None, conversation_id=None, workspace_id=None):
    """Fetch a MagpieWorkspace by workspace_id, project, or conversation."""

    logger.info(f"[FETCH_WORKSPACE] Called with workspace_id={workspace_id}, project={project.id if project else None}, conversation_id={conversation_id}")

    def _query():
        qs = MagpieWorkspace.objects.all()
        if workspace_id:
            logger.info(f"[FETCH_WORKSPACE] Querying by workspace_id: {workspace_id}")
            result = qs.filter(workspace_id=workspace_id).first()
            if result:
                logger.info(f"[FETCH_WORKSPACE] Found workspace by workspace_id: {result.workspace_id}, job_id: {result.job_id}, status: {result.status}")
            else:
                logger.warning(f"[FETCH_WORKSPACE] No workspace found for workspace_id: {workspace_id}")
            return result
        if project:
            logger.info(f"[FETCH_WORKSPACE] Querying by project: {project.id}")
            workspace = qs.filter(project=project).first()
            if workspace:
                logger.info(f"[FETCH_WORKSPACE] Found workspace by project: {workspace.workspace_id}, job_id: {workspace.job_id}, status: {workspace.status}")
                return workspace
            else:
                logger.info(f"[FETCH_WORKSPACE] No workspace found for project: {project.id}")
        if conversation_id:
            logger.info(f"[FETCH_WORKSPACE] Querying by conversation_id: {conversation_id}")
            result = qs.filter(conversation_id=str(conversation_id)).first()
            if result:
                logger.info(f"[FETCH_WORKSPACE] Found workspace by conversation_id: {result.workspace_id}, job_id: {result.job_id}, status: {result.status}")
            else:
                logger.info(f"[FETCH_WORKSPACE] No workspace found for conversation_id: {conversation_id}")
            return result

        logger.warning("[FETCH_WORKSPACE] No query parameters provided (workspace_id, project, or conversation_id)")
        return None

    return await sync_to_async(_query, thread_sensitive=True)()

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def validate_project_id(project_id):
    """Validate project_id and return error response if invalid"""
    if not project_id:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required"
        }
    return None

async def get_project(project_id):
    """Get project by ID with proper error handling"""
    try:
        return await sync_to_async(Project.objects.get)(project_id=project_id)
    except Project.DoesNotExist:
        return None

async def get_project_with_relations(project_id, *relations):
    """Get project with select_related for avoiding additional queries"""
    try:
        return await sync_to_async(
            lambda: Project.objects.select_related(*relations).get(project_id=project_id)
        )()
    except Project.DoesNotExist:
        return None

def validate_function_args(function_args, required_keys=None):
    """Validate function arguments structure"""
    if not isinstance(function_args, dict):
        return {
            "is_notification": False,
            "message_to_agent": "Error: Invalid function arguments format"
        }
    
    if required_keys:
        missing_keys = [key for key in required_keys if key not in function_args]
        if missing_keys:
            return {
                "is_notification": False,
                "message_to_agent": f"Error: Missing required arguments: {', '.join(missing_keys)}"
            }
    return None

def get_project_env_exports(project_id) -> list[str]:
    """
    Get project environment variables formatted as shell export statements.

    Args:
        project_id: The project database ID (int) or project_id string

    Returns:
        List of export statements like ['export KEY=value', ...]
    """
    try:
        from projects.models import ProjectEnvironmentVariable, Project

        project = None

        # Try to convert to int for database id lookup
        try:
            int_id = int(project_id)
            project = Project.objects.filter(id=int_id).first()
        except (ValueError, TypeError):
            pass

        # If not found, try by project_id string
        if not project and project_id:
            project = Project.objects.filter(project_id=str(project_id)).first()

        if not project:
            logger.debug(f"[ENV] No project found for project_id={project_id}")
            return []

        env_vars = ProjectEnvironmentVariable.get_project_env_dict(project)
        if env_vars:
            logger.info(f"[ENV] Found {len(env_vars)} env vars for project {project.project_id}")
        exports = []
        for key, value in env_vars.items():
            # Escape single quotes in value for shell safety
            escaped_value = value.replace("'", "'\\''")
            exports.append(f"export {key}='{escaped_value}'")
        return exports
    except Exception as e:
        logger.warning(f"[ENV] Failed to get project env vars: {e}", exc_info=True)
        return []


def execute_local_command(command: str, workspace_path: str, project_id: int = None) -> tuple[bool, str, str]:
    """
    Execute a command locally using subprocess.

    Args:
        command: The command to execute
        workspace_path: The workspace directory path
        project_id: Optional project ID to inject environment variables

    Returns:
        Tuple of (success, stdout, stderr)
    """
    try:
        # Get project environment variables if project_id provided
        env_exports = []
        if project_id:
            env_exports = get_project_env_exports(project_id)

        # Prepend env exports to command if any
        if env_exports:
            full_command = " && ".join(env_exports + [command])
        else:
            full_command = command

        result = subprocess.run(
            full_command,
            shell=True,
            cwd=workspace_path,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out after 5 minutes"
    except Exception as e:
        return False, "", f"Error executing command: {str(e)}"

def execute_local_server_command(command: str, workspace_path: str) -> tuple[bool, str, str]:
    """
    Execute a server command locally using subprocess in background.
    
    Args:
        command: The command to execute
        workspace_path: The workspace directory path
        
    Returns:
        Tuple of (success, stdout, stderr)
    """
    try:
        # Create tmp directory for logs if it doesn't exist
        tmp_path = Path(workspace_path) / "tmp"
        tmp_path.mkdir(exist_ok=True)
        
        # Run command in background and redirect output to log file
        full_command = f"{command} > {tmp_path}/server_output.log 2>&1 &"
        
        result = subprocess.run(
            full_command,
            shell=True,
            cwd=workspace_path,
            capture_output=True,
            text=True,
            timeout=30  # Shorter timeout since server should start quickly
        )
        
        # For background processes, success is typically when the command starts successfully
        if result.returncode == 0:
            return True, f"Server command started successfully in background", ""
        else:
            return False, result.stdout, result.stderr
            
    except subprocess.TimeoutExpired:
        return False, "", "Server command timed out after 30 seconds"
    except Exception as e:
        return False, "", f"Error executing server command: {str(e)}"

# ============================================================================
# MAIN DISPATCHER
# ============================================================================

async def app_functions(function_name, function_args, project_id, conversation_id, ticket_id=None):
    """
    Return a list of all the functions that can be called by the AI
    """
    logger.info(f"Function name: {function_name}")
    logger.debug(f"Function args: {function_args}")
    if ticket_id:
        logger.info(f"Executing for ticket_id: {ticket_id}")

    # Validate project_id for most functions
    if function_name not in ["get_github_access_token", "web_search"] and project_id:
        error_response = validate_project_id(project_id)
        if error_response:
            return error_response

    match function_name:
        case "extract_features":
            return await extract_features(function_args, project_id, conversation_id)
        case "extract_personas":
            return await extract_personas(function_args, project_id, conversation_id)
        case "get_features":
            return await get_features(project_id)
        case "get_personas":
            return await get_personas(project_id)
        case "create_prd":
            return await create_prd(function_args, project_id)
        case "get_prd":
            return await get_prd(project_id)
        case "stream_prd_content":
            return await stream_prd_content(function_args, project_id)
        case "stream_implementation_content":
            return await stream_implementation_content(function_args, project_id)
        case "stream_document_content":
            return await stream_document_content(function_args, project_id)
        case "create_implementation":
            return await create_implementation(function_args, project_id)
        case "get_implementation":
            return await get_implementation(project_id)
        case "update_implementation":
            return await update_implementation(function_args, project_id)
        case "create_tickets":
            return await create_tickets(function_args, project_id)
        case "update_ticket":
            return await update_individual_checklist_ticket(project_id, function_args.get('ticket_id'), function_args.get('status'))
        case "update_all_tickets":
            return await update_all_checklist_tickets(project_id, function_args.get('ticket_ids'), function_args.get('status'))
        case "get_pending_tickets":
            return await get_pending_tickets(project_id)
        case "get_next_ticket":
            return await get_next_ticket(project_id)

        case "execute_command":
            command = function_args.get('commands', '')
            logger.debug(f"Running command: {command}")
            if settings.ENVIRONMENT == "local":
                result = await run_command_locally(command, project_id=project_id, conversation_id=conversation_id, ticket_id=ticket_id)
            else:
                result = await run_command_in_k8s(command, project_id=project_id, conversation_id=conversation_id, ticket_id=ticket_id)
            return result

        case "ssh_command":
            logger.info(f"[TOOL_HANDLER] ssh_command called with ticket_id={ticket_id}")
            return await ssh_command_tool(function_args, project_id, conversation_id, ticket_id)

        case "new_dev_sandbox":
            return await new_dev_sandbox_tool(function_args, project_id, conversation_id)

        case "queue_ticket_execution":
            return await queue_ticket_execution_tool(function_args, project_id, conversation_id)

        case "open_app_in_artifacts":
            return await open_app_in_artifacts_tool(function_args, project_id, conversation_id)

        case "manage_ticket_tasks":
            return await manage_ticket_tasks_tool(function_args, project_id, conversation_id)

        case "get_ticket_todos":
            return await get_ticket_todos_tool(function_args, project_id, conversation_id)

        case "create_ticket_todos":
            return await create_ticket_todos_tool(function_args, project_id, conversation_id)

        case "update_todo_status":
            return await update_todo_status_tool(function_args, project_id, conversation_id)

        case "record_ticket_summary":
            return await record_ticket_summary_tool(function_args, project_id, conversation_id)

        case "broadcast_to_user":
            return await broadcast_to_user_tool(function_args, project_id, conversation_id)

        case "run_code_server":
            return await run_code_server_tool(function_args, project_id, conversation_id)

        case "register_required_env_vars":
            return await register_required_env_vars_tool(function_args, project_id, conversation_id)

        case "get_project_env_vars":
            return await get_project_env_vars_tool(function_args, project_id, conversation_id)

        case "agent_create_ticket":
            return await agent_create_ticket_tool(function_args, project_id, conversation_id)

        case "start_server":
            command = function_args.get('start_server_command', '')
            application_port = function_args.get('application_port', '')
            type = function_args.get('type', '')
            logger.debug(f"Running server: {command}")
            if settings.ENVIRONMENT == "local":
                result = await run_server_locally(command, project_id=project_id, conversation_id=conversation_id, application_port=application_port, type=type)
            else:
                result = await server_command_in_k8s(command, project_id=project_id, conversation_id=conversation_id, application_port=application_port, type=type)
            return result
        
        case "start_server_local":
            command = function_args.get('start_server_command', '')
            application_port = function_args.get('application_port', '')
            type = function_args.get('type', '')
            logger.debug(f"Running local server: {command}")
            result = await run_server_locally(command, project_id=project_id, conversation_id=conversation_id, application_port=application_port, type=type)
            return result
        
        case "get_github_access_token":
            return await get_github_access_token(project_id=project_id, conversation_id=conversation_id)
        
        case "implement_ticket":
            ticket_id = function_args.get('ticket_id')
            ticket_details = function_args.get('ticket_details')
            logger.debug(f"Ticket details: {ticket_details}")
            implementation_plan = function_args.get('implementation_plan')
            return await implement_ticket(ticket_id, project_id, conversation_id, ticket_details, implementation_plan)
        
        case "copy_boilerplate_code":
            project_name = function_args.get('project_name')
            return await copy_boilerplate_code(project_id, project_name)
        
        case "capture_name":
            action = function_args.get('action')
            project_name = function_args.get('project_name')
            return await capture_name(action, project_name, project_id)
        
        case "web_search":
            queries = function_args.get('queries', [])
            logger.debug(f"Search Queries: {queries}")
            return await web_search(queries, conversation_id)
        
        case "get_file_list":
            file_type = function_args.get('file_type', 'all')
            limit = function_args.get('limit', 10)
            return await get_file_list(project_id, file_type, limit)
        
        case "get_file_content":
            file_ids = function_args.get('file_ids') or function_args.get('file_id')  # Support both for backwards compatibility
            return await get_file_content(project_id, file_ids)

        # Codebase indexing functions
        case "index_repository":
            github_url = function_args.get('github_url')
            branch = function_args.get('branch', 'main')
            force_reindex = function_args.get('force_reindex', False)
            return await index_repository(project_id, github_url, branch, force_reindex, conversation_id)

        case "get_codebase_context":
            feature_description = function_args.get('feature_description')
            search_type = function_args.get('search_type', 'all')
            return await get_codebase_context(project_id, feature_description, search_type)

        case "search_existing_code":
            functionality = function_args.get('functionality')
            chunk_types = function_args.get('chunk_types', [])
            return await search_existing_code(project_id, functionality, chunk_types)

        case "get_repository_insights":
            return await get_repository_insights(project_id)

        case "get_codebase_summary":
            return await get_codebase_summary(project_id)

        case "ask_codebase":
            question = function_args.get('question')
            intent = function_args.get('intent', 'answer_question')
            include_code_snippets = function_args.get('include_code_snippets', True)
            return await ask_codebase(project_id, question, intent, include_code_snippets)

        # Notion integration functions
        case "connect_notion":
            return await connect_notion(project_id, conversation_id)

        case "search_notion":
            query = function_args.get('query', '')  # Default to empty string for listing all pages
            page_size = function_args.get('page_size', 10)
            return await search_notion(project_id, conversation_id, query, page_size)

        case "get_notion_page":
            page_id = function_args.get('page_id')
            return await get_notion_page(project_id, conversation_id, page_id)

        case "list_notion_databases":
            page_size = function_args.get('page_size', 10)
            return await list_notion_databases(project_id, conversation_id, page_size)

        case "query_notion_database":
            database_id = function_args.get('database_id')
            page_size = function_args.get('page_size', 10)
            return await query_notion_database(project_id, conversation_id, database_id, page_size)

        # Linear integration functions
        case "get_linear_issues":
            limit = function_args.get('limit', 50)
            team_id = function_args.get('team_id')
            return await get_linear_issues(project_id, conversation_id, limit, team_id)

        case "get_linear_issue_details":
            issue_id = function_args.get('issue_id')
            return await get_linear_issue_details(project_id, conversation_id, issue_id)

        # Technology lookup function
        case "lookup_technology_specs":
            category = function_args.get('category', 'all')
            return await lookup_technology_specs(category)

        # Design preview generation
        case "generate_design_preview":
            return await generate_design_preview(function_args, project_id, conversation_id)

        # case "implement_ticket_async":
        #     ticket_id = function_args.get('ticket_id')
        #     return await implement_ticket_async(ticket_id, project_id, conversation_id)

        # case "execute_tickets_in_parallel":
        #     max_workers = function_args.get('max_workers', 3)
        #     return await execute_tickets_in_parallel(project_id, conversation_id, max_workers)

        # case "get_ticket_execution_status":
        #     task_id = function_args.get('task_id')
        #     return await get_ticket_execution_status(project_id, task_id)

    return None


async def extract_features(function_args, project_id, conversation_id=None):
    """
    Extract the features from the project into a different list and save them to the database
    """
    logger.info("Feature extraction function called ")
    
    # Import progress utility
    from factory.progress_utils import send_tool_progress
    
    # Step 1: Start
    if conversation_id:
        await send_tool_progress(
            conversation_id, 
            "extract_features", 
            "Starting feature extraction...", 
            10
        )
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    validation_error = validate_function_args(function_args, ['features'])
    if validation_error:
        return validation_error
    
    # Step 2: Validate project
    if conversation_id:
        await send_tool_progress(
            conversation_id, 
            "extract_features", 
            "Validating project information...", 
            30
        )
    
    project = await get_project(project_id)
    if not project:
        if conversation_id:
            await send_tool_progress(
                conversation_id, 
                "extract_features", 
                f"Error: Project with ID {project_id} does not exist", 
                -1  # Error state
            )
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    features = function_args.get('features', [])
    
    if not isinstance(features, list):
        if conversation_id:
            await send_tool_progress(
                conversation_id, 
                "extract_features", 
                "Error: features must be a list", 
                -1  # Error state
            )
        return {
            "is_notification": False,
            "message_to_agent": "Error: features must be a list"
        }
    
    # Step 3: Extract and categorize features
    if conversation_id:
        await send_tool_progress(
            conversation_id, 
            "extract_features", 
            f"Processing {len(features)} features...", 
            60
        )
    
    try:
        # Step 4: Save to database
        if conversation_id:
            await send_tool_progress(
                conversation_id, 
                "extract_features", 
                "Saving features to project database...", 
                90
            )
        
        # Create new features using async database operations
        await sync_to_async(lambda: [
            ProjectFeature.objects.create(
                project=project,
                name=feature.get('name', ''),
                description=feature.get('description', ''),
                details=feature.get('details', ''),
                priority=feature.get('priority', 'medium')
            ) for feature in features if isinstance(feature, dict)
        ])()
        
        # Step 5: Complete
        if conversation_id:
            await send_tool_progress(
                conversation_id, 
                "extract_features", 
                f"Successfully saved {len(features)} features!", 
                100
            )
        
        return {
            "is_notification": False,
            "notification_type": "features",
            "message_to_agent": f"Features have been saved in the database"
        }
    except Exception as e:
        logger.error(f"Error saving features: {str(e)}")
        if conversation_id:
            await send_tool_progress(
                conversation_id, 
                "extract_features", 
                f"Error: {str(e)}", 
                -1  # Error state
            )
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving features: {str(e)}"
        }

async def extract_personas(function_args, project_id, conversation_id=None):
    """
    Extract the personas from the project and save them to the database
    """
    logger.info("Persona extraction function called ")
    
    # Import progress utility
    from factory.progress_utils import send_tool_progress
    
    # Step 1: Start
    if conversation_id:
        await send_tool_progress(
            conversation_id, 
            "extract_personas", 
            "Starting persona extraction...", 
            10
        )
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    validation_error = validate_function_args(function_args, ['personas'])
    if validation_error:
        return validation_error
    
    # Step 2: Validate project
    if conversation_id:
        await send_tool_progress(
            conversation_id, 
            "extract_personas", 
            "Validating project information...", 
            30
        )
    
    project = await get_project(project_id)
    if not project:
        if conversation_id:
            await send_tool_progress(
                conversation_id, 
                "extract_personas", 
                f"Error: Project with ID {project_id} does not exist", 
                -1  # Error state
            )
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    personas = function_args.get('personas', [])
    
    if not isinstance(personas, list):
        if conversation_id:
            await send_tool_progress(
                conversation_id, 
                "extract_personas", 
                "Error: personas must be a list", 
                -1  # Error state
            )
        return {
            "is_notification": False,
            "message_to_agent": "Error: personas must be a list"
        }
    
    # Step 3: Extract and categorize personas
    if conversation_id:
        await send_tool_progress(
            conversation_id, 
            "extract_personas", 
            f"Processing {len(personas)} personas...", 
            60
        )
    
    try:
        # Step 4: Save to database
        if conversation_id:
            await send_tool_progress(
                conversation_id, 
                "extract_personas", 
                "Saving personas to project database...", 
                90
            )
        
        # Create new personas using async database operations
        await sync_to_async(lambda: [
            ProjectPersona.objects.create(
                project=project,
                name=persona.get('name', ''),
                role=persona.get('role', ''),
                description=persona.get('description', '')
            ) for persona in personas if isinstance(persona, dict)
        ])()
        
        # Step 5: Complete
        if conversation_id:
            await send_tool_progress(
                conversation_id, 
                "extract_personas", 
                f"Successfully saved {len(personas)} personas!", 
                100
            )
        
        return {
            "is_notification": False,
            "notification_type": "personas",
            "message_to_agent": f"Personas have been saved in the database"
        }
    except Exception as e:
        logger.error(f"Error saving personas: {str(e)}")
        if conversation_id:
            await send_tool_progress(
                conversation_id, 
                "extract_personas", 
                f"Error: {str(e)}", 
                -1  # Error state
            )
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving personas: {str(e)}"
        }

async def get_features(project_id):
    """
    Retrieve existing features for a project
    """
    logger.info("Get features function called ")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required to retrieve features"
        }
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    features = await sync_to_async(
        lambda: list(ProjectFeature.objects.filter(project=project))
    )()
    
    if not features:
        return {
            "is_notification": False,
            "notification_type": "features",
            "message_to_agent": "No features found for this project"
        }
    
    feature_list = []
    for feature in features:
        feature_list.append({
            "name": feature.name,
            "description": feature.description,
            "details": feature.details,
            "priority": feature.priority
        })

    return {
        "is_notification": False,
        "notification_type": "features",
        "message_to_agent": f"Following features already exists in the database: {feature_list}"
    }

async def get_personas(project_id):
    """
    Retrieve existing personas for a project
    """
    logger.info("Get personas function called ")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required to retrieve personas"
        }
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    personas = await sync_to_async(
        lambda: list(ProjectPersona.objects.filter(project=project))
    )()
    
    if not personas:
        return {
            "is_notification": False,
            "notification_type": "personas",
            "message_to_agent": "No personas found for this project"
        }
    
    persona_list = []
    for persona in personas:
        persona_list.append({
            "name": persona.name,
            "role": persona.role,
            "description": persona.description
        })

    return {
        "is_notification": False,
        "notification_type": "personas",
        "message_to_agent": f"Following personas already exists in the database: {persona_list}"
    }

async def create_prd(function_args, project_id):
    """
    Save the PRD for a project
    """
    logger.info(f"PRD saving function called : {function_args}")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    validation_error = validate_function_args(function_args, ['prd'])
    if validation_error:
        return validation_error
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    prd_content = function_args.get('prd', '')
    prd_name = function_args.get('prd_name', 'Main PRD')

    if not prd_content:
        return {
            "is_notification": False,
            "message_to_agent": "Error: PRD content cannot be empty"
        }

    logger.debug(f"\nPRD Name: {prd_name}")
    logger.debug(f"\nPRD Content: {prd_content}")

    try:
        # Save PRD to database with name
        created = await sync_to_async(lambda: (
            lambda: (
                lambda prd, created: created
            )(*ProjectPRD.objects.get_or_create(
                project=project, 
                name=prd_name,
                defaults={'prd': prd_content}
            ))
        )())()
        
        # Update existing PRD if it wasn't created
        if not created:
            await sync_to_async(lambda: (
                ProjectPRD.objects.filter(project=project, name=prd_name).update(prd=prd_content)
            ))()
        
        action = "created" if created else "updated"

        # Save features and personas
        await save_features(project_id)
        await save_personas(project_id)
        
        return {
            "is_notification": False,
            "notification_type": "prd",
            "message_to_agent": f"PRD '{prd_name}' {action} successfully in the database",
            "prd_name": prd_name
        }
        
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving PRD: {str(e)}"
        }

async def get_prd(project_id, prd_name=None):
    """
    Retrieve a specific PRD or all PRDs for a project
    """
    logger.info(f"Get PRD function called for project {project_id}, PRD name: {prd_name}")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required to retrieve PRD"
        }
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    try:
        if prd_name:
            # Get specific PRD by name
            prd = await sync_to_async(
                lambda: ProjectPRD.objects.get(project=project, name=prd_name)
            )()
            return {
                "is_notification": False,
                "notification_type": "prd",
                "message_to_agent": f"Here is the PRD '{prd_name}': {prd.prd}. Please proceed with users request.",
                "prd_name": prd_name
            }
        else:
            # Get all PRDs for the project
            prds = await sync_to_async(
                lambda: list(ProjectPRD.objects.filter(project=project).values('name', 'created_at', 'updated_at'))
            )()
            
            if not prds:
                return {
                    "is_notification": False,
                    "message_to_agent": "No PRDs found for this project. Please create a PRD first."
                }
            
            # Get the most recent PRD content as well
            latest_prd = await sync_to_async(
                lambda: ProjectPRD.objects.filter(project=project).order_by('-updated_at').first()
            )()
            
            prd_list = "\n".join([f"- {prd['name']} (Created: {prd['created_at']}, Updated: {prd['updated_at']})" for prd in prds])
            
            return {
                "is_notification": False,
                "notification_type": "prd_list",
                "message_to_agent": f"Found {len(prds)} PRD(s) for this project:\n{prd_list}\n\nLatest PRD '{latest_prd.name}' content: {latest_prd.prd}",
                "prds": prds,
                "latest_prd_name": latest_prd.name
            }
    except ProjectPRD.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": f"No PRD with name '{prd_name}' found for this project." if prd_name else "No PRDs found for this project."
        }
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error retrieving PRD: {str(e)}"
        }

async def stream_prd_content(function_args, project_id):
    """
    Stream PRD content chunk by chunk as it's being generated
    This function is called multiple times during PRD generation to provide live updates
    """
    logger.info(f"Stream PRD content function called with args: {function_args}")
    logger.info(f"Project ID: {project_id}")
    
    error_response = validate_project_id(project_id)
    if error_response:
        logger.error(f"Project ID validation failed: {error_response}")
        return error_response
    
    validation_error = validate_function_args(function_args, ['content_chunk', 'is_complete'])
    if validation_error:
        logger.error(f"Function args validation failed: {validation_error}")
        return validation_error
    
    project = await get_project(project_id)
    if not project:
        logger.error(f"Project not found for ID: {project_id}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    content_chunk = function_args.get('content_chunk', '')
    is_complete = function_args.get('is_complete', False)
    prd_name = function_args.get('prd_name', 'Main PRD')
    
    logger.info(f"Streaming PRD chunk - Length: {len(content_chunk)}, Is Complete: {is_complete}")
    logger.info(f"First 100 chars of chunk: {content_chunk[:100]}...")
    
    # CONSOLE OUTPUT FOR DEBUGGING
    logger.info(f"PRD STREAM CHUNK - Project {project_id}", 
             extra={'easylogs_metadata': {
                 'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                 'length': len(content_chunk),
                 'complete': is_complete,
                 'project_id': project_id
             }})
    if content_chunk:
        logger.debug(f"Content Preview: {content_chunk[:200]}..." if len(content_chunk) > 200 else f"Content: {content_chunk}")
    
    # Create cache key for this project and PRD name
    cache_key = f"streaming_prd_content_{project_id}_{prd_name.replace(' ', '_')}"
    
    # Get existing content from cache or initialize
    existing_content = cache.get(cache_key, "")
    if not existing_content:
        logger.info(f"Initialized PRD content storage for project {project_id}")
    
    # Accumulate content
    if content_chunk:
        existing_content += content_chunk
        # Store updated content in cache with 1 hour timeout
        cache.set(cache_key, existing_content, timeout=3600)
        logger.info(f"Accumulated PRD content length: {len(existing_content)}")
    
    # If streaming is complete, save the PRD to database
    if is_complete:
        full_prd_content = cache.get(cache_key, "")
        logger.info(f"Streaming complete. Saving PRD with total length: {len(full_prd_content)}")
        
        # CONSOLE OUTPUT FOR COMPLETION
        logger.info(f"PRD STREAM COMPLETE - Project {project_id}",
                 extra={'easylogs_metadata': {
                     'total_length': len(full_prd_content),
                     'status': "saving_to_database",
                     'project_id': project_id
                 }})
        
        file_id = None
        if full_prd_content:
            try:
                # Save PRD to database with name
                created = await sync_to_async(lambda: (
                    lambda: (
                        lambda prd, created: created
                    )(*ProjectPRD.objects.get_or_create(
                        project=project, 
                        name=prd_name,
                        defaults={'prd': full_prd_content}
                    ))
                )())()
                
                # Update existing PRD if it wasn't created
                if not created:
                    await sync_to_async(lambda: (
                        ProjectPRD.objects.filter(project=project, name=prd_name).update(prd=full_prd_content)
                    ))()
                
                logger.info(f"PRD '{prd_name}' {'created' if created else 'updated'} successfully in database")
                
                # Save to ProjectFile and get the file_id
                try:
                    file_obj, file_created = await sync_to_async(
                        lambda: ProjectFile.objects.update_or_create(
                            project=project,
                            name=prd_name,
                            file_type='prd',
                            defaults={'content': full_prd_content}
                        )
                    )()
                    file_id = file_obj.id
                    logger.info(f"PRD saved to ProjectFile with ID: {file_id}")
                except Exception as e:
                    logger.error(f"Error saving PRD to ProjectFile: {str(e)}")
                
                # Clear the cache
                cache.delete(cache_key)
                
                # Also save features and personas
                # await save_features(project_id)
                # await save_personas(project_id)
                
            except Exception as e:
                logger.error(f"Error saving streamed PRD: {str(e)}")
                return {
                    "is_notification": False,
                    "notification_type": "prd_stream",
                    "content_chunk": "",
                    "is_complete": True,
                    "message_to_agent": f"PRD streaming complete but error saving: {str(e)}"
                }
    
    # Return notification to stream the chunk to frontend
    result = {
        "is_notification": False,
        "notification_type": "prd_stream",
        "content_chunk": content_chunk,
        "is_complete": is_complete,
        "prd_name": prd_name,
        "message_to_agent": f"PRD '{prd_name}' content chunk streamed" if not is_complete else f"PRD '{prd_name}' streaming complete and saved"
    }
    
    # Add file_id to result if streaming is complete and we have a file_id
    if is_complete and file_id:
        result["file_id"] = file_id
        logger.info(f"[PRD_STREAM] Including file_id {file_id} in completion notification")
    elif is_complete:
        logger.warning(f"[PRD_STREAM] Completion notification but no file_id available")
    
    logger.info(f"[PRD_STREAM] Returning stream result: is_complete={is_complete}, has_file_id={'file_id' in result}, keys={list(result.keys())}")
    return result

async def create_implementation(function_args, project_id):
    """
    Save the implementation for a project
    """
    logger.info(f"Implementation saving function called : {function_args}")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    validation_error = validate_function_args(function_args, ['implementation'])
    if validation_error:
        return validation_error
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    implementation_content = function_args.get('implementation', '')

    if not implementation_content:
        return {
            "is_notification": False,
            "message_to_agent": "Error: PRD content cannot be empty"
        }

    logger.debug(f"\nImplementation Content: {implementation_content}")

    try:
        # Save PRD to database
        created = await sync_to_async(lambda: (
            lambda: (
                lambda prd, created: created
            )(*ProjectImplementation.objects.get_or_create(project=project, defaults={'implementation': implementation_content}))
        )())()
        
        # Update existing PRD if it wasn't created
        if not created:
            await sync_to_async(lambda: (
                ProjectImplementation.objects.filter(project=project).update(implementation=implementation_content)
            ))()
        
        action = "created" if created else "updated"
        
        return {
            "is_notification": False,
            "notification_type": "implementation",
            "message_to_agent": f"Implementation {action} successfully in the database"
        }
        
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving Implementation: {str(e)}"
        }

async def get_implementation(project_id):
    """
    Retrieve the Implementation for a project
    """
    logger.info("Get Implementation function called ")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required to retrieve Implementation"
        }
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    try:
        # Check if project has PRD and get content
        implementation_content = await sync_to_async(lambda: project.implementation.implementation)()
        return {
            "is_notification": False,
            "notification_type": "implementation",
            "message_to_agent": f"Here is the existing version of the Implementation: {implementation_content}. Proceed with user's request."
        }
    except ProjectImplementation.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": "No Implementation found for this project. Please create a Implementation first."
        }
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error retrieving Implementation: {str(e)}"
        }

async def update_implementation(function_args, project_id):
    """
    Update the implementation for a project by adding new sections or modifications
    """
    logger.info(f"Update Implementation function called : {function_args}")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    validation_error = validate_function_args(function_args, ['update_type', 'update_content', 'update_summary'])
    if validation_error:
        return validation_error
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    update_type = function_args.get('update_type', '')
    update_content = function_args.get('update_content', '')
    update_summary = function_args.get('update_summary', '')

    if not update_content:
        return {
            "is_notification": False,
            "message_to_agent": "Error: Update content cannot be empty"
        }

    logger.debug(f"\nUpdate Type: {update_type}")
    logger.debug(f"Update Summary: {update_summary}")

    try:
        # Get existing implementation or create new one
        try:
            implementation = await sync_to_async(lambda: project.implementation)()
            existing_content = implementation.implementation
        except ProjectImplementation.DoesNotExist:
            # Create new implementation if it doesn't exist
            implementation = await sync_to_async(ProjectImplementation.objects.create)(
                project=project,
                implementation=""
            )
            existing_content = ""
        
        # Format the update based on type
        from datetime import datetime
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        if update_type == "complete_rewrite":
            # Replace entire document
            new_content = update_content
            action = "completely rewritten"
        else:
            # Add update to the top of the document
            update_header = f"""# Implementation Update - {timestamp}
**Update Type:** {update_type.replace('_', ' ').title()}
**Summary:** {update_summary}

---

{update_content}

---

# Previous Implementation Content
"""
            if existing_content:
                new_content = update_header + "\n" + existing_content
            else:
                new_content = update_header + "\n(No previous implementation content)"
            
            action = "updated with new " + ("additions" if update_type == "addition" else "modifications")
        
        # Save the updated implementation
        await sync_to_async(lambda: (
            setattr(implementation, 'implementation', new_content),
            implementation.save()
        )[1])()
        
        return {
            "is_notification": False,
            "notification_type": "implementation",
            "message_to_agent": f"Implementation {action} successfully. The update has been added to the document with timestamp {timestamp}."
        }
        
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error updating Implementation: {str(e)}"
        }

async def stream_implementation_content(function_args, project_id):
    """
    Stream Implementation content chunk by chunk as it's being generated
    This function is called multiple times during Implementation generation to provide live updates
    """
    logger.info(f"Stream Implementation content function called with args: {function_args}")
    logger.info(f"Project ID: {project_id}")
    
    error_response = validate_project_id(project_id)
    if error_response:
        logger.error(f"Project ID validation failed: {error_response}")
        return error_response
    
    validation_error = validate_function_args(function_args, ['content_chunk', 'is_complete'])
    if validation_error:
        logger.error(f"Function args validation failed: {validation_error}")
        return validation_error
    
    project = await get_project(project_id)
    if not project:
        logger.error(f"Project not found for ID: {project_id}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    content_chunk = function_args.get('content_chunk', '')
    is_complete = function_args.get('is_complete', False)
    
    logger.info(f"Streaming Implementation chunk - Length: {len(content_chunk)}, Is Complete: {is_complete}")
    logger.info(f"First 100 chars of chunk: {content_chunk[:100]}...")
    
    # CONSOLE OUTPUT FOR DEBUGGING
    logger.info(f"IMPLEMENTATION STREAM CHUNK - Project {project_id}",
             extra={'easylogs_metadata': {
                 'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                 'length': len(content_chunk),
                 'complete': is_complete,
                 'project_id': project_id
             }})
    if content_chunk:
        logger.debug(f"Content Preview: {content_chunk[:200]}..." if len(content_chunk) > 200 else f"Content: {content_chunk}")
    
    # Create cache key for this project
    cache_key = f"streaming_implementation_content_{project_id}"
    
    # Get existing content from cache or initialize
    existing_content = cache.get(cache_key, "")
    if not existing_content:
        logger.info(f"Initialized Implementation content storage for project {project_id}")
    
    # Accumulate content
    if content_chunk:
        existing_content += content_chunk
        # Store updated content in cache with 1 hour timeout
        cache.set(cache_key, existing_content, timeout=3600)
        logger.info(f"Accumulated Implementation content length: {len(existing_content)}")
    
    # If streaming is complete, save the Implementation to database
    if is_complete:
        full_implementation_content = cache.get(cache_key, "")
        logger.info(f"Streaming complete. Saving Implementation with total length: {len(full_implementation_content)}")
        
        # CONSOLE OUTPUT FOR COMPLETION
        logger.info(f"IMPLEMENTATION STREAM COMPLETE - Project {project_id}",
                 extra={'easylogs_metadata': {
                     'total_length': len(full_implementation_content),
                     'status': "saving_to_database",
                     'project_id': project_id
                 }})
        
        file_id = None
        if full_implementation_content:
            try:
                # Save Implementation to database
                created = await sync_to_async(lambda: (
                    lambda: (
                        lambda implementation, created: created
                    )(*ProjectImplementation.objects.get_or_create(project=project, defaults={'implementation': full_implementation_content}))
                )())()
                
                # Update existing Implementation if it wasn't created
                if not created:
                    await sync_to_async(lambda: (
                        ProjectImplementation.objects.filter(project=project).update(implementation=full_implementation_content)
                    ))()
                
                logger.info(f"Implementation {'created' if created else 'updated'} successfully in database")
                
                # Save to ProjectFile and get the file_id
                try:
                    file_obj, file_created = await sync_to_async(
                        lambda: ProjectFile.objects.update_or_create(
                            project=project,
                            name='Implementation Plan',
                            file_type='implementation',
                            defaults={'content': full_implementation_content}
                        )
                    )()
                    file_id = file_obj.id
                    logger.info(f"Implementation saved to ProjectFile with ID: {file_id}")
                except Exception as e:
                    logger.error(f"Error saving Implementation to ProjectFile: {str(e)}")
                
                # Clear the cache
                cache.delete(cache_key)
                
            except Exception as e:
                logger.error(f"Error saving streamed Implementation: {str(e)}")
                return {
                    "is_notification": False,
                    "notification_type": "implementation_stream",
                    "content_chunk": "",
                    "is_complete": True,
                    "message_to_agent": f"Implementation streaming complete but error saving: {str(e)}"
                }
    
    # Return notification to stream the chunk to frontend
    result = {
        "is_notification": False,
        "notification_type": "implementation_stream",
        "content_chunk": content_chunk,
        "is_complete": is_complete,
        "message_to_agent": "Implementation content chunk streamed" if not is_complete else "Implementation streaming complete and saved"
    }
    
    # Add file_id to result if streaming is complete and we have a file_id
    if is_complete and file_id:
        result["file_id"] = file_id
        logger.info(f"[IMPLEMENTATION_STREAM] Including file_id {file_id} in completion notification")
    elif is_complete:
        logger.warning(f"[IMPLEMENTATION_STREAM] Completion notification but no file_id available")
    
    logger.info(f"[IMPLEMENTATION_STREAM] Returning stream result: is_complete={is_complete}, has_file_id={'file_id' in result}, keys={list(result.keys())}")
    return result

async def stream_document_content(function_args, project_id):
    """
    Stream generic document content chunk by chunk as it's being generated
    This function is called multiple times during document generation to provide live updates
    Supports any document type including competitor analysis, market research, etc.
    """
    logger.info(f"Stream document content function called with args: {function_args}")
    logger.info(f"Project ID: {project_id}")
    
    error_response = validate_project_id(project_id)
    if error_response:
        logger.error(f"Project ID validation failed: {error_response}")
        return error_response
    
    validation_error = validate_function_args(function_args, ['content_chunk', 'is_complete', 'document_type', 'document_name'])
    if validation_error:
        logger.error(f"Function args validation failed: {validation_error}")
        return validation_error
    
    project = await get_project(project_id)
    if not project:
        logger.error(f"Project not found for ID: {project_id}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    content_chunk = function_args.get('content_chunk', '')
    is_complete = function_args.get('is_complete', False)
    document_type = function_args.get('document_type', 'document')
    document_name = function_args.get('document_name', 'Document')
    
    logger.info(f"Streaming {document_type} chunk - Length: {len(content_chunk)}, Is Complete: {is_complete}, Name: {document_name}")
    logger.info(f"First 100 chars of chunk: {content_chunk[:100]}...")
    
    # CONSOLE OUTPUT FOR DEBUGGING
    logger.info(f"DOCUMENT STREAM CHUNK - Project {project_id} - Type: {document_type}",
             extra={'easylogs_metadata': {
                 'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                 'length': len(content_chunk),
                 'complete': is_complete,
                 'project_id': project_id,
                 'document_type': document_type,
                 'document_name': document_name
             }})
    if content_chunk:
        logger.debug(f"Content Preview: {content_chunk[:200]}..." if len(content_chunk) > 200 else f"Content: {content_chunk}")
    
    # Create cache key for this project and document
    cache_key = f"streaming_document_content_{project_id}_{document_type}_{document_name.replace(' ', '_')}"
    
    # Get existing content from cache or initialize
    existing_content = cache.get(cache_key, "")
    if not existing_content:
        logger.info(f"Initialized document content storage for project {project_id}, type: {document_type}")
    
    # Accumulate content
    if content_chunk:
        existing_content += content_chunk
        # Store updated content in cache with 1 hour timeout
        cache.set(cache_key, existing_content, timeout=3600)
        logger.info(f"Accumulated document content length: {len(existing_content)}")
    
    # If streaming is complete, save the document to database
    file_id = None
    if is_complete:
        full_document_content = cache.get(cache_key, "")
        logger.info(f"Streaming complete. Saving document with total length: {len(full_document_content)}")
        
        # CONSOLE OUTPUT FOR COMPLETION
        logger.info(f"DOCUMENT STREAM COMPLETE - Project {project_id} - Type: {document_type}",
                 extra={'easylogs_metadata': {
                     'total_length': len(full_document_content),
                     'status': "saving_to_database",
                     'project_id': project_id,
                     'document_type': document_type
                 }})
        
        if full_document_content:
            try:
                # Save to ProjectFile
                file_obj, file_created = await sync_to_async(
                    lambda: ProjectFile.objects.update_or_create(
                        project=project,
                        name=document_name,
                        file_type=document_type,
                        defaults={
                            'content': full_document_content,
                            'mime_type': 'text/markdown'
                        }
                    )
                )()
                
                file_id = file_obj.id
                logger.info(f"Document file {'created' if file_created else 'updated'} with ID: {file_id}")
                
                # Clear the cache
                cache.delete(cache_key)
                logger.info(f"Cleared cache for document stream: {cache_key}")
                
            except Exception as e:
                logger.error(f"Error saving document to database: {str(e)}", exc_info=True)
                # Don't fail the stream, just log the error
    
    # Build the result for streaming notification
    result = {
        "is_notification": True,
        "notification_type": "file_stream",
        "content_chunk": content_chunk,
        "is_complete": is_complete,
        "file_type": document_type,
        "file_name": document_name
    }
    
    # Add file_id to result if streaming is complete and we have a file_id
    if is_complete and file_id:
        result["file_id"] = file_id
        logger.info(f"[DOCUMENT_STREAM] Including file_id {file_id} in completion notification")
    elif is_complete:
        logger.warning(f"[DOCUMENT_STREAM] Completion notification but no file_id available")
    
    logger.info(f"[DOCUMENT_STREAM] Returning stream result: is_complete={is_complete}, has_file_id={'file_id' in result}, keys={list(result.keys())}")
    return result

async def create_tickets(function_args, project_id):
    """
    Generate checklist tickets for a project
    """
    logger.info("Checklist tickets function called ")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    # Validate function arguments
    validation_error = validate_function_args(function_args, ['tickets'])
    if validation_error:
        return validation_error
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    checklist_tickets = function_args.get('tickets', [])
    
    if not isinstance(checklist_tickets, list):
        return {
            "is_notification": False,
            "message_to_agent": "Error: tickets must be a list"
        }
    
    try:
        # Create tickets with enhanced details
        created_tickets = []
        for ticket in checklist_tickets:
            if isinstance(ticket, dict):
                # Extract details from the ticket
                details = ticket.get('details', {})
                
                new_ticket = await sync_to_async(ProjectTicket.objects.create)(
                    project=project,
                    name=ticket.get('name', ''),
                    description=ticket.get('description', ''),
                    priority=ticket.get('priority', 'Medium'),
                    status='open',
                    role=ticket.get('role', 'agent'),
                    # Enhanced fields
                    # details=details,
                    ui_requirements=ticket.get('ui_requirements', {}),
                    component_specs=ticket.get('component_specs', {}),
                    acceptance_criteria=ticket.get('acceptance_criteria', []),
                    dependencies=ticket.get('dependencies', []),
                    # complexity=details.get('complexity', 'medium'),
                    # requires_worktree=details.get('requires_worktree', True)
                )
                created_tickets.append(new_ticket.id)
        
        return {
            "is_notification": True,
            "notification_type": "create_tickets",
            "message_to_agent": f"Successfully created {len(created_tickets)} detailed tickets with design specifications"
        }
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error creating checklist tickets: {str(e)}"
        }

async def get_next_ticket(project_id):
    """
    Get the latest ticket for a project
    """
    logger.info("Get pending tickets function called ")

    error_response = validate_project_id(project_id)
    if error_response:
        return error_response

    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    pending_ticket = await sync_to_async(
        lambda: ProjectTicket.objects.filter(project=project, status='open', role='agent').first()
    )()
    
    # Print ticket ID instead of the object to avoid triggering __str__ method
    logger.debug(f"Pending ticket ID: {pending_ticket.id if pending_ticket else None}")

    if pending_ticket:
        # Access the fields directly without triggering related queries
        message_to_agent = f"Pending ticket: \nTicket Id: {pending_ticket.id}, \nTicket Name: {pending_ticket.name},\
              \nTicket Description: {pending_ticket.description}, \nTicket Priority: {pending_ticket.priority}. Build this ticket first."
    else:
        message_to_agent = "No pending tickets found"

    logger.debug(f"Message to agent: {message_to_agent}")

    return {
        "is_notification": False,
        "notification_type": "get_pending_tickets",
        "message_to_agent": message_to_agent
    }

async def update_individual_checklist_ticket(project_id, ticket_id, status):
    """
    Update an individual checklist ticket for a project
    """
    logger.info("Update individual checklist ticket function called ")
    logger.debug(f"Ticket ID: {ticket_id} and status: {status}")
    
    if not ticket_id or not status:
        return {
            "is_notification": False,
            "message_to_agent": "Error: ticket_id and status are required"
        }
    
    try:
        # Get and update ticket in a single async operation
        await sync_to_async(lambda: (
            ProjectTicket.objects.filter(id=ticket_id).update(status=status)
        ))()

        logger.info(f"Checklist ticket {ticket_id} has been successfully updated in the database. Proceed to next checklist item, unless otherwise specified by the user")

        return {
            "is_notification": False,
            "notification_type": "create_tickets",
            "message_to_agent": f"Checklist ticket {ticket_id} has been successfully updated in the database. Proceed to next checklist item, unless otherwise specified by the user"
        }
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error updating ticket: {str(e)}"
        }


async def update_all_checklist_tickets(project_id, ticket_ids, status):
    """
    Update checklist tickets by their ticket IDs
    """
    logger.info(f"Update checklist tickets by IDs function called - ticket_ids: {ticket_ids}, status: {status}")
    
    try:
       # Get and update tickets with the specified IDs
        updated_count = await sync_to_async(lambda: (
                ProjectTicket.objects.filter(
                    id__in=ticket_ids,
                ).update(status=status)
            ))()

        logger.info(f"{updated_count} pending checklist ticket(s) have been successfully updated in the database.")

        return {
            "is_notification": False,
            "notification_type": "create_tickets",
            "message_to_agent": f"{updated_count} pending checklist ticket(s) have been successfully updated to status '{status}' in the database."
        }
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error updating tickets: {str(e)}"
        }


async def get_pending_tickets(project_id):
    """
    Get pending tickets for a project
    """
    logger.info("Get pending tickets function called ")

    error_response = validate_project_id(project_id)
    if error_response:
        return error_response

    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    project_tickets = await sync_to_async(
        lambda: list(
            ProjectTicket.objects.filter(project=project, role='agent')
            .order_by('created_at', 'id')
            .values('id', 'name', 'description', 'status', 'priority')
        )
    )()

    if project_tickets:
        # Format all pending tickets with their details
        ticket_details = []
        for ticket in project_tickets:
            ticket_details.append(
                f"Ticket ID: {ticket['id']}, Name: {ticket['name']}, "
                f"Description: {ticket['description']}, Status: {ticket['status']}, "
                f"Priority: {ticket['priority']}"
            )
        message_content = "\n".join(ticket_details)
    else:
        message_content = "No pending tickets found"

    return {
        "is_notification": False,
        "notification_type": "get_pending_tickets",
        "message_to_agent": f"Pending tickets in open state: {message_content}. Please update the status of the tickets as needed. If not, continue closing them."
    }

async def get_github_access_token(project_id: int | str = None, conversation_id: int | str = None) -> dict:
    """
    Get GitHub access token for a project
    """
    try:
        error_response = validate_project_id(project_id)
        if error_response:
            return {
                "is_notification": False,
                "notification_type": "command_error",
                "message_to_agent": "Error: project_id is required to get GitHub access token"
            }

        # Get project with owner to avoid additional database queries
        project = await get_project_with_relations(project_id, 'owner')
        if not project:
            return {
                "is_notification": False,
                "notification_type": "command_error",
                "message_to_agent": f"Project with ID {project_id} not found"
            }

        user_id = project.owner.id
        project_name = project.name

        github_token = await sync_to_async(GitHubToken.objects.get)(user_id=user_id)
        access_token = github_token.access_token

        if access_token is None or access_token == "":
            return {
                "is_notification": False,
                "notification_type": "command_error",
                "message_to_agent": f"No Github access token found. Inform user to connect their Github account."
            }
        
        return {
            "is_notification": False,
            "notification_type": "command_output", 
            "message_to_agent": f"Github access token {access_token} found and project name {project_name} found. Please use this to commit the code",
            "user_id": user_id
        }

    except Project.DoesNotExist:
        return {
            "is_notification": False,
            "notification_type": "command_error",
            "message_to_agent": f"Project with ID {project_id} not found"
        }
    except GitHubToken.DoesNotExist:
        return {
            "is_notification": False,
            "notification_type": "command_error",
            "message_to_agent": f"No Github access token found for this user. Inform user to connect their Github account."
        }
    except Exception as e:
        return {
            "is_notification": False,
            "notification_type": "command_error", 
            "message_to_agent": f"Error getting user_id: {str(e)}"
        }

async def run_command_in_k8s(command: str, project_id: int | str = None, conversation_id: int | str = None, ticket_id: int = None) -> dict:
    """
    Run a command in the terminal using Kubernetes pod.
    """

    # Try to get ticket_id from context variable if not passed
    if ticket_id is None:
        try:
            from tasks.task_definitions import current_ticket_id
            ticket_id = current_ticket_id.get()
            if ticket_id:
                logger.info(f"[RUN_COMMAND_K8S] Retrieved ticket_id={ticket_id} from context variable")
        except Exception as e:
            logger.debug(f"[RUN_COMMAND_K8S] Could not get ticket_id from context: {e}")

    if project_id:
        pod = await sync_to_async(
            lambda: KubernetesPod.objects.filter(project_id=project_id).first()
        )()

    command_to_run = f"cd /workspace && {command}"
    logger.debug(f"Command: {command_to_run}")

    # Create command record in database (only if ticket_id is provided)
    cmd_record = None
    if ticket_id:
        try:
            ticket = await sync_to_async(ProjectTicket.objects.get)(id=ticket_id)
            cmd_record = await sync_to_async(TicketLog.objects.create)(
                ticket=ticket,
                command=command,
                output=None,  # Will update after execution
                exit_code=None
            )
        except ProjectTicket.DoesNotExist:
            logger.warning(f"Ticket {ticket_id} not found, skipping log creation")
        except Exception as e:
            logger.error(f"Error creating TicketLog: {e}")

    success = False
    stdout = ""
    stderr = ""

    if pod:
        # Execute the command using the Kubernetes API function in thread pool
        success, stdout, stderr = await asyncio.get_event_loop().run_in_executor(
            None, execute_command_in_pod, project_id, conversation_id, command_to_run
        )

        logger.debug(f"Command output: {stdout}")

        # Update command record with output
        if cmd_record:
            await sync_to_async(lambda: (
                setattr(cmd_record, 'output', stdout if success else stderr),
                setattr(cmd_record, 'exit_code', 0 if success else 1),
                cmd_record.save()
            )[2])()

            # Send WebSocket notification for the updated log
            await async_send_ticket_log_notification(
                ticket_id=ticket_id,
                log_data={
                    'id': cmd_record.id,
                    'command': cmd_record.command,
                    'explanation': cmd_record.explanation,
                    'output': cmd_record.output,
                    'exit_code': cmd_record.exit_code,
                    'created_at': cmd_record.created_at.isoformat()
                }
            )

    if not success or not pod:
        # If no pod is found, update the command record
        if not pod and cmd_record:
            await sync_to_async(lambda: (
                setattr(cmd_record, 'output', "No Kubernetes pod found for the project"),
                setattr(cmd_record, 'exit_code', 1),
                cmd_record.save()
            )[2])()

            # Send WebSocket notification for the error log
            await async_send_ticket_log_notification(
                ticket_id=ticket_id,
                log_data={
                    'id': cmd_record.id,
                    'command': cmd_record.command,
                    'explanation': cmd_record.explanation,
                    'output': cmd_record.output,
                    'exit_code': cmd_record.exit_code,
                    'created_at': cmd_record.created_at.isoformat()
                }
            )

        return {
            "is_notification": False,
            "notification_type": "command_error",
            "message_to_agent": f"{stderr}The command execution failed. Stop generating further steps and inform the user that the command could not be executed.",
        }
    
    return {
        "is_notification": False,
        "notification_type": "command_output", 
        "message_to_agent": f"Command output: {stdout}Fix if there is any error, otherwise you can proceed to next step",
    }

async def server_command_in_k8s(command: str, project_id: int | str = None, conversation_id: int | str = None, application_port: int | str = None, type: str = None) -> dict:
    """
    Run a command in the terminal using Kubernetes pod to start an application server.
    
    Args:
        command: The command to run
        project_id: The project ID
        conversation_id: The conversation ID
        application_port: The port the application listens on inside the container
        type: The type of application (frontend, backend, etc.)
        
    Returns:
        Dict containing command output and port mapping information
    """
    from development.k8s_manager.manage_pods import execute_command_in_pod, get_k8s_api_client
    from coding.models import KubernetesPod, KubernetesPortMapping
    from kubernetes import client as k8s_client
    from kubernetes.client.rest import ApiException

    logger.debug(f"Application port: {application_port}")
    logger.debug(f"Type: {type}")

    if project_id:
        pod = await sync_to_async(
            lambda: KubernetesPod.objects.filter(project_id=project_id).first()
        )()
    else:
        return {
            "is_notification": False,
            "notification_type": "command_error",
            "message_to_agent": f"No project ID provided. Cannot execute the command."
        }

    if not pod:
        return {
            "is_notification": False,
            "notification_type": "command_error",
            "message_to_agent": f"No Kubernetes pod found for the project. Cannot execute the command."
        }

    # Handle application port if provided
    if application_port:
        try:
            # Convert application_port to integer if it's a string
            application_port = int(application_port)
            
            # Check if port is in valid range
            if application_port < 1 or application_port > 65535:
                return {
                    "is_notification": False,
                    "notification_type": "command_error",
                    "message_to_agent": f"Invalid application port: {application_port}. Port must be between 1 and 65535."
                }
        except (ValueError, TypeError):
            return {
                "is_notification": False,
                "notification_type": "command_error",
                "message_to_agent": f"Invalid application port: {application_port}. Must be a valid integer."
            }
            
        # Standardize port type
        port_type = type.lower() if type else "application"
        if port_type not in ["frontend", "backend", "application"]:
            port_type = "application"
            
        # Check if we've already set up a port mapping for this container port
        existing_mapping = await sync_to_async(
            lambda: KubernetesPortMapping.objects.filter(
                pod=pod,
                container_port=application_port
            ).first()
        )()
        
        service_name = f"{pod.namespace}-service"
        
        if existing_mapping:
            # Use existing mapping
            logger.debug(f"Using existing port mapping for {port_type} port {application_port}")
            node_port = existing_mapping.node_port
        else:
            # Need to add port to service and create mapping using Kubernetes API
            logger.debug(f"Creating new port mapping for {port_type} port {application_port}")
            
            # Get Kubernetes API client in thread pool
            api_client, core_v1_api, apps_v1_api = await asyncio.get_event_loop().run_in_executor(
                None, get_k8s_api_client
            )
            if not core_v1_api:
                return {
                    "is_notification": False,
                    "notification_type": "command_error",
                    "message_to_agent": f"Failed to connect to Kubernetes API"
                }
            
            try:
                # Get the current service in thread pool
                service = await asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: core_v1_api.read_namespaced_service(
                        name=service_name,
                        namespace=pod.namespace
                    )
                )
                
                # Define a unique port name for this application port
                port_name = f"{port_type}-{application_port}"
                
                # Check if port already exists in service
                existing_port = None
                for port in service.spec.ports:
                    if port.port == application_port or port.name == port_name:
                        existing_port = port
                        break
                
                if existing_port:
                    node_port = existing_port.node_port
                    logger.debug(f"Port {application_port} already exists in service with nodePort {node_port}")
                else:
                    # Add new port to service
                    new_port = k8s_client.V1ServicePort(
                        name=port_name,
                        port=application_port,
                        target_port=application_port,
                        protocol="TCP"
                    )
                    
                    # Add the new port to the existing ports
                    service.spec.ports.append(new_port)
                    
                    # Update the service in thread pool
                    updated_service = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: core_v1_api.patch_namespaced_service(
                            name=service_name,
                            namespace=pod.namespace,
                            body=service
                        )
                    )
                    
                    # Get the assigned nodePort
                    for port in updated_service.spec.ports:
                        if port.name == port_name:
                            node_port = port.node_port
                            break
                    else:
                        return {
                            "is_notification": False,
                            "notification_type": "command_error",
                            "message_to_agent": f"Failed to get nodePort for port {application_port}"
                        }
                    
                    logger.debug(f"Kubernetes assigned nodePort {node_port} for {port_type} port {application_port}")
                
                # Get node IP using Kubernetes API in thread pool
                try:
                    nodes = await asyncio.get_event_loop().run_in_executor(
                        None, core_v1_api.list_node
                    )
                    node_ip = "localhost"
                    if nodes.items:
                        for address in nodes.items[0].status.addresses:
                            if address.type == "InternalIP":
                                node_ip = address.address
                                break
                except Exception as e:
                    logger.warning(f"Could not get node IP: {e}")
                    node_ip = "localhost"
                
                # Create port mapping in database if it doesn't exist
                if not existing_mapping:
                    description = f"{port_type.capitalize()} service"
                    
                    await sync_to_async(lambda: (
                        KubernetesPortMapping.objects.create(
                            pod=pod,
                            container_name="dev-environment",
                            container_port=application_port,
                            service_port=application_port,
                            node_port=node_port,
                            protocol="TCP",
                            service_name=service_name,
                            description=description
                        )
                    ))()
                
                # Update pod's service_details
                await sync_to_async(lambda: (
                    lambda: (
                        setattr(pod, 'service_details', {
                            **(pod.service_details or {}),
                            f"{port_type}Port": node_port,
                            "nodeIP": node_ip,
                            f"{port_type}Url": f"http://{node_ip}:{node_port}"
                        }),
                        pod.save()
                    )[1]
                )())()
                
            except ApiException as e:
                return {
                    "is_notification": False,
                    "notification_type": "command_error",
                    "message_to_agent": f"Failed to update service: {e}"
                }
            except Exception as e:
                return {
                    "is_notification": False,
                    "notification_type": "command_error",
                    "message_to_agent": f"Error setting up port mapping: {str(e)}"
                }
    
    # Prepare and run the command in the pod using Kubernetes API
    full_command = f"mkdir -p /workspace/tmp && cd /workspace && {command} > /workspace/tmp/cmd_output.log 2>&1 &"
    logger.debug(f"Command: {full_command}")

    # Execute the command using the Kubernetes API function in thread pool
    success, stdout, stderr = await asyncio.get_event_loop().run_in_executor(
        None, execute_command_in_pod, project_id, conversation_id, full_command
    )
    
    logger.debug(f"Command output: {stdout}")

    if not success:
        return {
            "is_notification": False,
            "notification_type": "command_error",
            "message_to_agent": f"{stderr}The command execution failed. Stop generating further steps and inform the user that the command could not be executed.",
        }
    
    # Prepare success message with port information if applicable
    message = f"{stdout}Command to run server is successful."
    
    if application_port:
        # Get the pod's service details
        service_details = pod.service_details or {}
        node_ip = service_details.get('nodeIP', 'localhost')
        
        # Add URL information to the message
        message += f"{port_type.capitalize()} is running on port {application_port} inside the container."
        message += f"\nYou can access it at: [http://{node_ip}:{node_port}](http://{node_ip}:{node_port})"
    
    return {
        "is_notification": False,
        "notification_type": "command_output",
        "message_to_agent": message + "Proceed to next step",
    }

async def ssh_command_tool(function_args, project_id, conversation_id, ticket_id=None):
    """Execute a command inside the Magpie workspace via SSH."""

    # Try to get ticket_id from context variable if not passed
    if ticket_id is None:
        try:
            from tasks.task_definitions import current_ticket_id
            ticket_id = current_ticket_id.get()
            if ticket_id:
                logger.info(f"[SSH_COMMAND_TOOL] Retrieved ticket_id={ticket_id} from context variable")
        except Exception as e:
            logger.debug(f"[SSH_COMMAND_TOOL] Could not get ticket_id from context: {e}")

    # Try to get workspace_id from context variable first, then fallback to function_args
    workspace_id = function_args.get('workspace_id')
    if not workspace_id:
        try:
            from tasks.task_definitions import current_workspace_id
            workspace_id = current_workspace_id.get()
            if workspace_id:
                logger.info(f"[SSH_COMMAND_TOOL] Retrieved workspace_id={workspace_id} from context variable")
        except Exception as e:
            logger.debug(f"[SSH_COMMAND_TOOL] Could not get workspace_id from context: {e}")

    if not magpie_available():
        return {
            "is_notification": False,
            "message_to_agent": "Magpie command execution is not available. Configure the Magpie SDK and API key."
        }

    command = function_args.get('command')
    original_command = command  # Save original command for logging
    explanation = function_args.get('explanation')
    timeout = function_args.get('timeout', 300)
    with_node_env = function_args.get('with_node_env', True)

    # Check if user has requested to stop execution
    if ticket_id:
        from django.core.cache import cache
        cache_key = f'ticket_cancel_{ticket_id}'
        if cache.get(cache_key):
            logger.info(f"[SSH_COMMAND_TOOL] Cancellation requested for ticket #{ticket_id}")
            # Clear the flag so subsequent operations can proceed
            cache.delete(cache_key)
            return {
                "is_notification": False,
                "message_to_agent": "STOP REQUESTED: User has interrupted the execution. Please acknowledge the stop request and end your current task gracefully. Respond with: IMPLEMENTATION_STATUS: STOPPED - User requested interruption"
            }

    # Prepend cd /workspace && to ensure all commands run in workspace directory
    if command and not command.strip().startswith('cd /workspace'):
        command = f"cd /workspace && {command}"

    if not command:
        return {
            "is_notification": False,
            "message_to_agent": "command is required to run a Magpie SSH command."
        }

    # Lazy workspace initialization: if no workspace_id but we have ticket_id, create workspace on-demand
    if not workspace_id and ticket_id:
        logger.info(f"[SSH_COMMAND_TOOL] No workspace_id, attempting lazy initialization for ticket #{ticket_id}")
        try:
            from tasks.task_definitions import ensure_workspace_available
            ensure_result = await sync_to_async(ensure_workspace_available, thread_sensitive=True)(ticket_id)

            if ensure_result['status'] == 'success':
                workspace_id = ensure_result['workspace_id']
                logger.info(f"[SSH_COMMAND_TOOL] Workspace {'created' if ensure_result.get('created') else 'found'}: {workspace_id}")
            else:
                error_msg = f"Failed to provision workspace: {ensure_result.get('error', 'Unknown error')}"
                logger.error(f"[SSH_COMMAND_TOOL] {error_msg}")
                return {
                    "is_notification": False,
                    "message_to_agent": error_msg
                }
        except Exception as e:
            logger.error(f"[SSH_COMMAND_TOOL] Error during lazy workspace init: {e}", exc_info=True)
            return {
                "is_notification": False,
                "message_to_agent": f"Failed to initialize workspace: {str(e)}"
            }

    if not workspace_id:
        return {
            "is_notification": False,
            "message_to_agent": "workspace_id is required. Either provide it directly or ensure ticket_id is set for automatic workspace provisioning."
        }

    workspace = await _fetch_workspace(workspace_id=workspace_id)
    if not workspace:
        error_msg = f"No Magpie workspace found for ID {workspace_id}. Provision one first."

        # Log this failure to TicketLog if ticket_id is available
        if ticket_id:
            try:
                ticket = await sync_to_async(ProjectTicket.objects.get, thread_sensitive=True)(id=ticket_id)
                await sync_to_async(TicketLog.objects.create, thread_sensitive=True)(
                    ticket=ticket,
                    command=original_command,
                    explanation=explanation or "No workspace available",
                    output=error_msg,
                    exit_code=-1
                )
                logger.info(f"[SSH_COMMAND_TOOL] TicketLog created for failed workspace lookup")
            except Exception as e:
                logger.error(f"[SSH_COMMAND_TOOL] Error creating TicketLog for failure: {e}")

        return {
            "is_notification": False,
            "message_to_agent": error_msg
        }

    try:
        client = get_magpie_client()
    except RuntimeError as exc:
        logger.error("Magpie client configuration error: %s", exc)
        error_msg = f"Magpie client error: {exc}"

        # Log this failure to TicketLog if ticket_id is available
        if ticket_id:
            try:
                ticket = await sync_to_async(ProjectTicket.objects.get, thread_sensitive=True)(id=ticket_id)
                await sync_to_async(TicketLog.objects.create, thread_sensitive=True)(
                    ticket=ticket,
                    command=original_command,
                    explanation=explanation or "Magpie client error",
                    output=error_msg,
                    exit_code=-1
                )
                logger.info(f"[SSH_COMMAND_TOOL] TicketLog created for Magpie client error")
            except Exception as e:
                logger.error(f"[SSH_COMMAND_TOOL] Error creating TicketLog for failure: {e}")

        return {
            "is_notification": False,
            "message_to_agent": error_msg
        }

    try:
        result = await asyncio.to_thread(
            _run_magpie_ssh,
            client,
            workspace.job_id,
            command,
            timeout,
            with_node_env,
            project_id,
        )
        logger.info(
            "[MAGPIE][SSH COMMAND] workspace=%s exit_code=%s",
            workspace.workspace_id,
            result.get('exit_code')
        )
    except Exception as exc:
        logger.exception("Magpie SSH command failed")
        await sync_to_async(workspace.mark_error, thread_sensitive=True)(metadata={"last_error": str(exc)})

        # Provide specific guidance for different error types
        error_msg = str(exc)
        if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
            agent_message = (
                f"Command execution timed out after {timeout}s. "
                f"For long-running commands (npm install, build), either: "
                f"1) Assume they succeeded if earlier output looked good, or "
                f"2) Run a quick check command (ls, cat package.json) to verify. "
                f"DO NOT retry the same long command."
            )
        elif "500" in error_msg or "failed to execute ssh command" in error_msg:
            agent_message = (
                f"Magpie API error (500): Command was too long or complex. "
                f"You likely tried to create multiple files in one ssh_command. "
                f"Create ONE file per ssh_command instead. "
                f"DO NOT retry the exact same command."
            )
        else:
            agent_message = f"Magpie SSH command failed: {exc}"

        # Log this failure to TicketLog if ticket_id is available
        if ticket_id:
            try:
                ticket = await sync_to_async(ProjectTicket.objects.get, thread_sensitive=True)(id=ticket_id)
                await sync_to_async(TicketLog.objects.create, thread_sensitive=True)(
                    ticket=ticket,
                    command=original_command,
                    explanation=explanation or "SSH command failed",
                    output=agent_message,
                    exit_code=-1
                )
                logger.info(f"[SSH_COMMAND_TOOL] TicketLog created for SSH command failure")
            except Exception as e:
                logger.error(f"[SSH_COMMAND_TOOL] Error creating TicketLog for failure: {e}")

        return {
            "is_notification": False,
            "notification_type": "toolhistory",
            "notification_marker": "__NOTIFICATION__",
            "function_name": "ssh_command",
            "status": "failed",
            "message": "Magpie SSH command could not be executed. The remote workspace is unavailable.",
            "error": error_msg,
            "message_to_agent": agent_message
        }

    meta_updates = {
        "last_command": explanation or command,
        "last_exit_code": result.get('exit_code'),
        "last_command_at": datetime.utcnow().isoformat() + "Z",
    }
    await sync_to_async(_update_workspace_metadata, thread_sensitive=True)(workspace, **meta_updates)

    # Create TicketLog if ticket_id is provided
    logger.info(f"[SSH_COMMAND_TOOL] ticket_id={ticket_id}, command={original_command[:50] if original_command else 'N/A'}")
    if ticket_id:
        logger.info(f"[SSH_COMMAND_TOOL] Creating TicketLog for ticket_id={ticket_id}")
        try:
            ticket = await sync_to_async(ProjectTicket.objects.get, thread_sensitive=True)(id=ticket_id)
            logger.info(f"[SSH_COMMAND_TOOL] Found ticket: {ticket.name} (id={ticket.id})")
            log_entry = await sync_to_async(TicketLog.objects.create, thread_sensitive=True)(
                ticket=ticket,
                command=original_command,  # Use original command without cd /workspace prefix
                explanation=explanation,
                output=_truncate_output(result.get('stdout') or result.get('stderr'), 4000),
                exit_code=result.get('exit_code')
            )
            logger.info(f"[SSH_COMMAND_TOOL] TicketLog created successfully: id={log_entry.id}")

            # Send WebSocket notification for the new log
            await async_send_ticket_log_notification(
                ticket_id=ticket_id,
                log_data={
                    'id': log_entry.id,
                    'command': log_entry.command,
                    'explanation': log_entry.explanation,
                    'output': log_entry.output,
                    'exit_code': log_entry.exit_code,
                    'created_at': log_entry.created_at.isoformat()
                }
            )
        except ProjectTicket.DoesNotExist:
            logger.warning(f"[SSH_COMMAND_TOOL] Ticket {ticket_id} not found, skipping log creation")
        except Exception as e:
            logger.error(f"[SSH_COMMAND_TOOL] Error creating TicketLog: {e}", exc_info=True)
    else:
        logger.warning(f"[SSH_COMMAND_TOOL] No ticket_id provided, skipping log creation")

    status_text = "completed successfully" if result.get('exit_code') == 0 else f"exited with code {result.get('exit_code')}"
    status_value = "completed" if result.get('exit_code') == 0 else "failed"
    output_block = _format_command_output(result.get('stdout', ''), result.get('stderr', ''))
    message = textwrap.dedent(
        f"""
        Command {status_text}: {explanation or command}

        {output_block}
        """
    ).strip()

    log_entries = [{
        "title": "SSH command",
        "command": command,
        "stdout": _truncate_output(result.get('stdout', ''), 800),
        "stderr": _truncate_output(result.get('stderr', ''), 800),
        "exit_code": result.get('exit_code')
    }]

    return {
        "is_notification": False,
        "workspace_id": workspace.workspace_id,
        "exit_code": result.get('exit_code'),
        "stdout": _truncate_output(result.get('stdout', ''), 4000),
        "stderr": _truncate_output(result.get('stderr', ''), 4000),
        "status": status_value,
        "command": command,
        "log_entries": log_entries,
        "message_to_agent": message
    }


async def new_dev_sandbox_tool(function_args, project_id, conversation_id):
    """Clone the Next.js template, install dependencies, and start the dev server on the Magpie workspace."""

    logger.info(f"[DEV_SANDBOX] Setting up dev sandbox for workspace: {function_args.get('workspace_id')}")

    if not magpie_available():
        return {
            "is_notification": False,
            "message_to_agent": "Magpie workspace tools are unavailable. Configure the Magpie SDK and API key."
        }

    workspace_id = function_args.get('workspace_id')
    log_tail_lines = function_args.get('log_tail_lines', 60)
    environment_label = function_args.get('environment')

    if not workspace_id:
        return {
            "is_notification": False,
            "message_to_agent": "workspace_id is required to create a new dev sandbox."
        }

    workspace = await _fetch_workspace(workspace_id=workspace_id)
    if not workspace:
        return {
            "is_notification": False,
            "message_to_agent": f"No Magpie workspace found for ID {workspace_id}. Provision one first."
        }

    try:
        client = get_magpie_client()
    except RuntimeError as exc:
        logger.error("Magpie client configuration error: %s", exc)
        return {
            "is_notification": False,
            "message_to_agent": f"Magpie client error: {exc}"
        }

    restart_cmd = textwrap.dedent(
        f"""
        cd /workspace
        # Kill any existing dev server
        if [ -f nextjs-app/.devserver_pid ]; then
          old_pid=$(cat nextjs-app/.devserver_pid)
          if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
            kill "$old_pid" || true
          fi
        fi
        npm config set cache /workspace/.npm-cache
        # Clone the nextjs-template repo if it doesn't exist
        # if [ ! -d "nextjs-app" ]; then
        #   echo "Cloning nextjs-template repository..."
        #   git clone https://github.com/lfg-hq/nextjs-template nextjs-app
        #   cd nextjs-app
        #   echo "Installing dependencies..."
        #   npm install
        # fi
        """
    )

    try:
        result = await asyncio.to_thread(
            _run_magpie_ssh,
            client,
            workspace.job_id,
            restart_cmd,
            240,
            True,
            project_id,
        )
        logger.info(
            "[MAGPIE][DEV RESTART] workspace=%s exit_code=%s",
            workspace.workspace_id,
            result.get('exit_code')
        )
    except Exception as exc:
        logger.exception("Failed to create new dev sandbox")
        await sync_to_async(workspace.mark_error, thread_sensitive=True)(metadata={"last_error": str(exc)})
        return {
            "is_notification": False,
            "notification_type": "toolhistory",
            "notification_marker": "__NOTIFICATION__",
            "function_name": "new_dev_sandbox",
            "status": "failed",
            "message": "Dev sandbox creation failed because the Magpie workspace is unavailable.",
            "error": str(exc),
            "message_to_agent": f"Dev sandbox creation failed: {exc}"
        }

    stdout = result.get('stdout', '')
    stderr = result.get('stderr', '')
    pid = _extract_pid_from_output(stdout)

    log_section = stdout
    preview_section = ""
    if "---PREVIEW---" in stdout:
        log_section, preview_section = stdout.split("---PREVIEW---", 1)
    if "---LOG---" in log_section:
        _, log_section = log_section.split("---LOG---", 1)

    log_tail = _truncate_output(log_section.strip(), 2000)
    preview_snippet = _truncate_output(preview_section.strip(), 2000)

    metadata_updates = {
        "dev_server_pid": pid,
        "last_restart": datetime.utcnow().isoformat() + "Z",
        "last_preview": preview_snippet,
        "sandbox_initialized": True,  # Mark sandbox as initialized to prevent duplicate setup
    }
    if environment_label:
        metadata_updates['environment_label'] = environment_label

    await sync_to_async(_update_workspace_metadata, thread_sensitive=True)(workspace, **metadata_updates)

    # Use proxy URL if available, otherwise fall back to IPv6
    preview_url = await async_get_or_fetch_proxy_url(workspace, port=3000)
    if not preview_url:
        preview_url = f"http://[{workspace.ipv6_address}]:3000" if workspace.ipv6_address else "(URL pending)"
    status_text = "completed successfully" if result.get('exit_code') == 0 else f"exited with code {result.get('exit_code')}"
    message_lines = [
        f"Dev sandbox setup {status_text} 🚀",
        f"Workspace ID: {workspace.workspace_id}",
        f"PID: {pid or 'unknown'}",
        f"Preview: {preview_url}",
        f"Logs: {MAGPIE_WORKSPACE_DIR}/dev.log"
    ]
    if log_tail:
        message_lines.append("\nLog tail:\n" + log_tail)
    if preview_snippet:
        message_lines.append("\nPreview snippet:\n" + preview_snippet)
    if stderr.strip():
        message_lines.append("\nSTDERR:\n" + _truncate_output(stderr.strip(), 2000))

    log_entries = [
        {
            "title": "Setup new dev sandbox",
            "command": "git clone nextjs-template && npm install && npm run dev",
            "stdout": _truncate_output(stdout, 800),
            "stderr": _truncate_output(stderr, 800),
            "exit_code": result.get('exit_code')
        }
    ]

    return {
        "is_notification": False,
        "workspace_id": workspace.workspace_id,
        "exit_code": result.get('exit_code'),
        "preview_url": preview_url,
        "log_path": f"{MAGPIE_WORKSPACE_DIR}/dev.log",
        "preview_snippet": preview_snippet,
        "log_tail": log_tail,
        "dev_server_pid": pid,
        "stderr": _truncate_output(stderr.strip(), 2000),
        "status": "completed" if result.get('exit_code') == 0 else "failed",
        "log_entries": log_entries,
        "message_to_agent": "\n".join(message_lines)
    }


async def queue_ticket_execution_tool(function_args, project_id, conversation_id):
    logger.info("Queue ticket execution tool called")
    logger.debug(f"Function arguments: {function_args}")

    error_response = validate_project_id(project_id)
    if error_response:
        return error_response

    if not conversation_id:
        return {
            "is_notification": False,
            "message_to_agent": "Cannot queue ticket execution without an active conversation. Start a conversation first."
        }

    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }

    ticket_id_list = function_args.get('ticket_ids') or []

    # def _get_ticket_ids(ids):
    #     queryset = ProjectTicket.objects.filter(project=project, role='agent', status='open')
    #     if ids:
    #         queryset = queryset.filter(id__in=ids)
    #     return list(queryset.order_by('created_at', 'id').values_list('id', flat=True))

    # cleaned_requested_ids = []
    # for raw_id in requested_ids:
    #     try:
    #         cleaned_requested_ids.append(int(raw_id))
    #     except (TypeError, ValueError):
    #         continue

    # ticket_id_list = await sync_to_async(_get_ticket_ids)(cleaned_requested_ids)

    if not ticket_id_list:
        return {
            "is_notification": False,
            "notification_type": "toolhistory",
            "notification_marker": "__NOTIFICATION__",
            "message_to_agent": "No open agent tickets are available to execute.",
            "status": "skipped"
        }

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")


    # Queue each ticket as a separate task for parallel execution
    task_ids = []
    failed_tickets = []

    for ticket_id in ticket_id_list:
        try:
            task_id = await sync_to_async(TaskManager.publish_task)(
                'tasks.task_definitions.execute_ticket_implementation',
                ticket_id,
                project.id,
                conversation_id,
                task_name=f"Ticket #{ticket_id} execution for {project.name}",
                timeout=7200
            )
            task_ids.append(task_id)
            logger.info(f"Queued ticket {ticket_id} with task ID {task_id}")
        except Exception as exc:
            logger.exception(f"Failed to queue ticket {ticket_id}")
            failed_tickets.append({'ticket_id': ticket_id, 'error': str(exc)})

    if failed_tickets and not task_ids:
        # All tickets failed to queue
        return {
            "is_notification": False,
            "notification_type": "toolhistory",
            "notification_marker": "__NOTIFICATION__",
            "status": "failed",
            "message_to_agent": f"Failed to queue all {len(ticket_id_list)} tickets for execution.",
            "failed_tickets": failed_tickets
        }

    if failed_tickets:
        # Some tickets failed
        return {
            "is_notification": False,
            "notification_type": "toolhistory",
            "status": "partial",
            "message_to_agent": f"Queued {len(task_ids)} tickets for background execution. {len(failed_tickets)} tickets failed to queue.",
            "ticket_ids": ticket_id_list,
            "task_ids": task_ids,
            "failed_tickets": failed_tickets,
            "notification_marker": "__NOTIFICATION__"
        }

    return {
        "is_notification": False,
        "notification_type": "toolhistory",
        "status": "queued",
        "message_to_agent": f"Queued {len(task_ids)} tickets for parallel background execution. Each ticket will run independently.",
        "ticket_ids": ticket_id_list,
        "task_ids": task_ids,
        "notification_marker": "__NOTIFICATION__"
    }


async def manage_ticket_tasks_tool(function_args, project_id, conversation_id):
    """
    Manage tasks for a specific ticket. Can add new tasks, update existing tasks, or change task status.
    """
    logger.info("Manage ticket tasks tool called")
    logger.debug(f"Function arguments: {function_args}")

    error_response = validate_project_id(project_id)
    if error_response:
        return error_response

    ticket_id = function_args.get('ticket_id')
    action = function_args.get('action')
    tasks_data = function_args.get('tasks', [])

    if not ticket_id:
        return {
            "is_notification": False,
            "message_to_agent": "Error: ticket_id is required"
        }

    if not action:
        return {
            "is_notification": False,
            "message_to_agent": "Error: action is required (add, update, or update_status)"
        }

    try:
        # Verify ticket exists
        ticket = await sync_to_async(ProjectTicket.objects.get)(id=ticket_id)

        if action == "get":
            # Get all existing tasks for this ticket
            tasks_qs = ProjectTodoList.objects.filter(ticket=ticket).order_by('order')
            tasks = await sync_to_async(list)(tasks_qs)

            tasks_list = []
            for task in tasks:
                tasks_list.append({
                    'task_id': task.id,
                    'description': task.description,
                    'status': task.status,
                    'order': task.order
                })

            if tasks_list:
                logger.debug(f"Task Lists: {tasks_list}")
                return {
                    "is_notification": False,
                    "message_to_agent": f"Retrieved {len(tasks_list)} task(s) for ticket #{ticket_id}. Use these task_id values when updating tasks.",
                    "tasks": tasks_list
                }
            else:
                return {
                    "is_notification": False,
                    "message_to_agent": f"No tasks found for ticket #{ticket_id}. You can add new tasks using action='add'.",
                    "tasks": []
                }

        elif action == "add":
            # Add new tasks
            created_tasks = []
            for task_data in tasks_data:
                task = await sync_to_async(ProjectTodoList.objects.create)(
                    ticket=ticket,
                    description=task_data.get('description', ''),
                    status=task_data.get('status', 'pending'),
                    order=task_data.get('order', 0)
                )
                created_tasks.append({
                    'id': task.id,
                    'description': task.description,
                    'status': task.status
                })

            return {
                "is_notification": False,
                "message_to_agent": f"Successfully created {len(created_tasks)} task(s) for ticket #{ticket_id}",
                "created_tasks": created_tasks
            }

        elif action == "update":
            # Update existing tasks
            updated_tasks = []
            for task_data in tasks_data:
                task_id = task_data.get('task_id')
                if not task_id:
                    continue

                task = await sync_to_async(ProjectTodoList.objects.get)(id=task_id, ticket=ticket)

                if 'description' in task_data:
                    task.description = task_data['description']
                if 'status' in task_data:
                    task.status = task_data['status']
                if 'order' in task_data:
                    task.order = task_data['order']

                await sync_to_async(task.save)()
                updated_tasks.append({
                    'id': task.id,
                    'description': task.description,
                    'status': task.status
                })

            return {
                "is_notification": False,
                "message_to_agent": f"Successfully updated {len(updated_tasks)} task(s) for ticket #{ticket_id}",
                "updated_tasks": updated_tasks
            }

        elif action == "update_status":
            # Update task status only
            updated_tasks = []
            for task_data in tasks_data:
                task_id = task_data.get('task_id')
                new_status = task_data.get('status')

                if not task_id or not new_status:
                    continue

                task = await sync_to_async(ProjectTodoList.objects.get)(id=task_id, ticket=ticket)
                task.status = new_status
                await sync_to_async(task.save)()

                updated_tasks.append({
                    'id': task.id,
                    'description': task.description,
                    'status': task.status
                })

            return {
                "is_notification": False,
                "message_to_agent": f"Successfully updated status for {len(updated_tasks)} task(s) for ticket #{ticket_id}",
                "updated_tasks": updated_tasks
            }

        else:
            return {
                "is_notification": False,
                "message_to_agent": f"Error: Invalid action '{action}'. Use 'get', 'add', 'update', or 'update_status'"
            }

    except ProjectTicket.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Ticket with ID {ticket_id} does not exist"
        }
    except ProjectTodoList.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": "Error: One or more tasks not found"
        }
    except Exception as e:
        logger.error(f"Error managing ticket tasks: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error managing tasks: {str(e)}"
        }


async def get_ticket_todos_tool(function_args, project_id, conversation_id):
    """Get all todos for a ticket with their current status and IDs."""
    logger.info("Get ticket todos tool called")
    logger.debug(f"Function arguments: {function_args}")

    error_response = validate_project_id(project_id)
    if error_response:
        return error_response

    ticket_id = function_args.get('ticket_id')

    if not ticket_id:
        return {
            "is_notification": False,
            "message_to_agent": "Error: ticket_id is required"
        }

    try:
        # Verify ticket exists
        ticket = await sync_to_async(ProjectTicket.objects.get)(id=ticket_id)

        # Get all todos ordered by their order field
        todos_qs = ProjectTodoList.objects.filter(ticket=ticket).order_by('order')
        todos = await sync_to_async(list)(todos_qs)

        todos_list = []
        for todo in todos:
            todos_list.append({
                'todo_id': todo.id,  # Return the actual database ID
                'description': todo.description,
                'status': todo.status,
                'order': todo.order
            })

        if todos_list:
            logger.debug(f"Todo List: {todos_list}")
            return {
                "is_notification": False,
                "message_to_agent": f"Retrieved {len(todos_list)} todo(s) for ticket #{ticket_id}. Todo List: {todos_list} \nUse the todo_id values to update todo status.",
                "todos": todos_list
            }
        else:
            return {
                "is_notification": False,
                "message_to_agent": f"No todos found for ticket #{ticket_id}. Create todos using create_ticket_todos.",
                "todos": []
            }

    except ProjectTicket.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Ticket with ID {ticket_id} does not exist"
        }
    except Exception as e:
        logger.error(f"Error getting ticket todos: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error getting todos: {str(e)}"
        }


async def create_ticket_todos_tool(function_args, project_id, conversation_id):
    """Create todos for a ticket."""
    logger.info("Create ticket todos tool called")
    logger.debug(f"Function arguments: {function_args}")

    error_response = validate_project_id(project_id)
    if error_response:
        return error_response

    ticket_id = function_args.get('ticket_id')
    todos_data = function_args.get('todos', [])

    if not ticket_id:
        return {
            "is_notification": False,
            "message_to_agent": "Error: ticket_id is required"
        }

    if not todos_data:
        return {
            "is_notification": False,
            "message_to_agent": "Error: todos array is required"
        }

    try:
        # Verify ticket exists
        ticket = await sync_to_async(ProjectTicket.objects.get)(id=ticket_id)

        # Delete existing todos for this ticket (if recreating)
        await sync_to_async(ProjectTodoList.objects.filter(ticket=ticket).delete)()

        # Create new todos
        created_todos = []
        for idx, todo_data in enumerate(todos_data):
            todo = await sync_to_async(ProjectTodoList.objects.create)(
                ticket=ticket,
                description=todo_data.get('description', ''),
                status='pending',
                order=idx  # Set order based on array index
            )
            created_todos.append({
                'order': idx,
                'todo_id': todo.id,
                'description': todo.description,
                'status': todo.status
            })

        return {
            "is_notification": False,
            "message_to_agent": f"Successfully created {len(created_todos)} todo(s) for ticket #{ticket_id}. Todos are numbered 0-{len(created_todos)-1}.",
            "todos": created_todos
        }

    except ProjectTicket.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Ticket with ID {ticket_id} does not exist"
        }
    except Exception as e:
        logger.error(f"Error creating ticket todos: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error creating todos: {str(e)}"
        }


async def update_todo_status_tool(function_args, project_id, conversation_id):
    """Update the status of a todo by its database ID."""
    logger.info("Update todo status tool called")
    logger.debug(f"Function arguments: {function_args}")

    error_response = validate_project_id(project_id)
    if error_response:
        return error_response

    ticket_id = function_args.get('ticket_id')
    todo_id = function_args.get('todo_id')
    new_status = function_args.get('status')

    if not ticket_id:
        return {
            "is_notification": False,
            "message_to_agent": "Error: ticket_id is required"
        }

    if not todo_id:
        return {
            "is_notification": False,
            "message_to_agent": "Error: todo_id is required"
        }

    if not new_status:
        return {
            "is_notification": False,
            "message_to_agent": "Error: status is required"
        }

    try:
        # Verify ticket exists
        ticket = await sync_to_async(ProjectTicket.objects.get)(id=ticket_id)

        # Get the specific todo by ID and verify it belongs to this ticket
        todo = await sync_to_async(ProjectTodoList.objects.get)(id=todo_id, ticket=ticket)

        # Update status
        todo.status = new_status
        await sync_to_async(todo.save)()

        return {
            "is_notification": False,
            "message_to_agent": f"Successfully updated todo '{todo.description[:50]}' (ID: {todo_id}) to status '{new_status}' for ticket #{ticket_id}",
            "todo": {
                'todo_id': todo.id,
                'description': todo.description,
                'status': todo.status
            }
        }

    except ProjectTicket.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Ticket with ID {ticket_id} does not exist"
        }
    except ProjectTodoList.DoesNotExist:
        # If todo_id not found, fetch and return all valid todos for this ticket
        try:
            # Get all todos for this ticket
            todos = await sync_to_async(list)(
                ProjectTodoList.objects.filter(ticket=ticket).order_by('order')
            )

            todos_list = []
            for todo in todos:
                todos_list.append({
                    'todo_id': todo.id,
                    'description': todo.description,
                    'status': todo.status,
                    'order': todo.order
                })

            return {
                "is_notification": False,
                "message_to_agent": f"Error: Todo with ID {todo_id} not found for ticket #{ticket_id}. Here are the valid todos for this ticket - use one of these todo_id values:",
                "valid_todos": todos_list
            }
        except Exception as e:
            logger.error(f"Error fetching valid todos: {str(e)}")
            return {
                "is_notification": False,
                "message_to_agent": f"Error: Todo with ID {todo_id} not found for ticket #{ticket_id}. Could not fetch valid todos: {str(e)}"
            }
    except Exception as e:
        logger.error(f"Error updating todo status: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error updating todo status: {str(e)}"
        }


async def record_ticket_summary_tool(function_args, project_id, conversation_id):
    """
    Record a summary of changes made during ticket execution.
    Appends to the ticket's notes field with a timestamp, preserving previous entries.
    """
    logger.info("Record ticket summary tool called")
    logger.debug(f"Function arguments: {function_args}")

    error_response = validate_project_id(project_id)
    if error_response:
        return error_response

    ticket_id = function_args.get('ticket_id')
    summary = function_args.get('summary', '')
    files_modified = function_args.get('files_modified', [])

    if not ticket_id:
        return {
            "is_notification": False,
            "message_to_agent": "Error: ticket_id is required"
        }

    if not summary:
        return {
            "is_notification": False,
            "message_to_agent": "Error: summary is required"
        }

    try:
        # Verify ticket exists and get it
        ticket = await sync_to_async(ProjectTicket.objects.get)(id=ticket_id)

        # Build the new summary entry with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Format the summary entry
        summary_entry = f"\n---\n## Summary - {timestamp}\n\n{summary}\n"

        # Add files modified if provided (structured format with filename, path, action)
        if files_modified:
            summary_entry += "\n**Files Modified:**\n"
            for file_info in files_modified:
                if isinstance(file_info, dict):
                    filename = file_info.get('filename', '')
                    path = file_info.get('path', '')
                    action = file_info.get('action', 'modified')
                    summary_entry += f"- [{action}] `{filename}` - `{path}`\n"
                else:
                    # Fallback for simple string format
                    summary_entry += f"- {file_info}\n"

        # Get existing notes and append (not replace)
        existing_notes = ticket.notes or ""
        new_notes = existing_notes + summary_entry

        # Update the ticket's notes field
        ticket.notes = new_notes
        await sync_to_async(ticket.save)(update_fields=['notes', 'updated_at'])

        logger.info(f"Successfully recorded summary for ticket #{ticket_id}")

        return {
            "is_notification": False,
            "message_to_agent": f"Successfully recorded summary for ticket #{ticket_id}. The summary has been appended to the ticket's notes.",
            "ticket_id": ticket_id,
            "timestamp": timestamp,
            "files_count": len(files_modified)
        }

    except ProjectTicket.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Ticket with ID {ticket_id} does not exist"
        }
    except Exception as e:
        logger.error(f"Error recording ticket summary: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error recording ticket summary: {str(e)}"
        }


async def broadcast_to_user_tool(function_args, project_id, conversation_id):
    """
    Broadcast a message to the user DIRECTLY via WebSocket AND save to database.
    This sends the message immediately, not through the LLM notification harness.
    Returns a simple confirmation to the agent.
    """
    from tasks.task_definitions import current_ticket_id, current_workspace_id
    from channels.layers import get_channel_layer
    from channels.db import database_sync_to_async

    logger.info(f"[BROADCAST] Tool called - project_id={project_id}, conversation_id={conversation_id}")

    # Get ticket_id and workspace_id from context
    ticket_id = current_ticket_id.get()
    workspace_id = current_workspace_id.get()
    logger.info(f"[BROADCAST] Context - ticket_id={ticket_id}, workspace_id={workspace_id}")

    message = function_args.get('message', '')
    status = function_args.get('status', 'progress')
    summary = function_args.get('summary', {})

    if not message:
        return "Error: message is required for broadcast"

    if status not in ['progress', 'complete', 'blocked', 'error']:
        status = 'progress'

    logger.info(f"[BROADCAST] Sending to user: status={status}, message={message[:100]}...")

    log_data = None

    # Save to database for persistence (so message survives tab switch)
    try:
        if ticket_id:
            from projects.models import ProjectTicket, TicketLog
            from django.db import transaction

            def _save_broadcast_log():
                with transaction.atomic():
                    ticket = ProjectTicket.objects.get(id=ticket_id)
                    log = TicketLog.objects.create(
                        ticket=ticket,
                        log_type='ai_response',
                        command=f'[{status.upper()}]',
                        explanation='AI Agent Broadcast',
                        output=message
                    )
                    logger.info(f"[BROADCAST] Created TicketLog {log.id} in DB")
                    return log

            ai_log = await database_sync_to_async(_save_broadcast_log)()
            log_data = {
                'id': ai_log.id,
                'log_type': 'ai_response',
                'command': f'[{status.upper()}]',
                'output': message,
                'exit_code': None,
                'created_at': ai_log.created_at.isoformat()
            }
            logger.info(f"[BROADCAST] ✓ Saved to DB as log {ai_log.id}")
    except Exception as e:
        import traceback
        logger.error(f"[BROADCAST] Error saving to DB: {e}\n{traceback.format_exc()}")
        # Still continue to send WebSocket even if DB save fails
        log_data = {
            'log_type': 'ai_response',
            'command': f'[{status.upper()}]',
            'output': message,
            'exit_code': None,
        }

    # Send WebSocket notification DIRECTLY to the user as an AI response (chat message style)
    try:
        channel_layer = get_channel_layer()
        if channel_layer and ticket_id and log_data:
            group_name = f'ticket_logs_{ticket_id}'
            await channel_layer.group_send(
                group_name,
                {
                    'type': 'ticket_log_created',
                    'log_data': log_data
                }
            )
            logger.info(f"[BROADCAST] ✓ Sent via WebSocket to ticket_logs_{ticket_id}")
        else:
            logger.warning(f"[BROADCAST] Could not send - channel_layer={bool(channel_layer)}, ticket_id={ticket_id}")
    except Exception as e:
        logger.error(f"[BROADCAST] Error sending WebSocket notification: {e}")

    # Return simple confirmation to agent (no notification dict, no message_to_agent)
    # return f"Message broadcast to user successfully (status: {status})"
    return {
        "is_notification": False,
        "message_to_agent": "User notified. Continue with next step"
    }


async def get_project_env_vars_tool(function_args, project_id, conversation_id):
    """
    Get the list of environment variables configured for a project.
    Returns metadata only - not actual secret values.
    """
    from projects.models import Project, ProjectEnvironmentVariable
    from asgiref.sync import sync_to_async

    logger.info(f"[ENV_VARS] Getting env vars for project {project_id}")

    include_values = function_args.get('include_values', False)

    if not project_id:
        return {
            "success": False,
            "error": "Project ID is required",
            "is_notification": False
        }

    try:
        @sync_to_async
        def _get_env_vars():
            project = Project.objects.get(project_id=project_id)
            env_vars = ProjectEnvironmentVariable.objects.filter(project=project).order_by('key')

            result = []
            for env in env_vars:
                var_info = {
                    "key": env.key,
                    "has_value": env.has_value,
                    "is_required": env.is_required,
                    "is_secret": env.is_secret,
                    "description": env.description or ""
                }
                # Only include masked value for non-secrets if requested
                if include_values and env.has_value:
                    if env.is_secret:
                        var_info["value"] = "***SECRET***"
                    else:
                        # Show first/last few chars
                        try:
                            decrypted = env.get_value()
                            if len(decrypted) > 8:
                                var_info["value"] = f"{decrypted[:4]}...{decrypted[-4:]}"
                            else:
                                var_info["value"] = "****"
                        except:
                            var_info["value"] = "****"

                result.append(var_info)

            return result

        env_vars = await _get_env_vars()

        # Build summary
        total = len(env_vars)
        with_values = sum(1 for e in env_vars if e['has_value'])
        missing = total - with_values
        required_missing = sum(1 for e in env_vars if e['is_required'] and not e['has_value'])

        summary = f"Found {total} environment variable(s)"
        if missing > 0:
            summary += f" ({missing} missing value(s)"
            if required_missing > 0:
                summary += f", {required_missing} REQUIRED"
            summary += ")"

        return {
            "success": True,
            "env_vars": env_vars,
            "summary": summary,
            "total": total,
            "with_values": with_values,
            "missing_values": missing,
            "required_missing": required_missing,
            "is_notification": False
        }

    except Project.DoesNotExist:
        return {
            "success": False,
            "error": f"Project {project_id} not found",
            "is_notification": False
        }
    except Exception as e:
        logger.error(f"[ENV_VARS] Error getting env vars: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "is_notification": False
        }


async def agent_create_ticket_tool(function_args, project_id, conversation_id):
    """
    Create a single ticket for the project.
    Used by builder/agent to create follow-up tasks, document issues, or flag items for user attention.
    """
    from projects.models import Project, ProjectTicket
    from asgiref.sync import sync_to_async

    logger.info(f"[CREATE_TICKET] Creating ticket for project {project_id}")

    name = function_args.get('name', '')
    description = function_args.get('description', '')
    priority = function_args.get('priority', 'Medium')
    status = function_args.get('status', 'open')

    if not name:
        return {
            "success": False,
            "error": "Ticket name is required",
            "is_notification": False
        }

    if not project_id:
        return {
            "success": False,
            "error": "Project ID is required",
            "is_notification": False
        }

    try:
        @sync_to_async
        def _create_ticket():
            project = Project.objects.get(project_id=project_id)

            ticket = ProjectTicket.objects.create(
                project=project,
                name=name,
                description=description,
                priority=priority,
                status=status
            )
            return ticket

        ticket = await _create_ticket()

        logger.info(f"[CREATE_TICKET] Created ticket '{name}' with ID {ticket.id}")

        return {
            "success": True,
            "message": f"Created ticket: {name}",
            "ticket": {
                "id": ticket.id,
                "name": ticket.name,
                "description": ticket.description,
                "priority": ticket.priority,
                "status": ticket.status
            },
            "is_notification": True,
            "notification_type": "create_ticket",
            "notification_data": {
                "ticket_id": ticket.id,
                "ticket_name": name,
                "priority": priority,
                "status": status
            }
        }

    except Project.DoesNotExist:
        return {
            "success": False,
            "error": f"Project {project_id} not found",
            "is_notification": False
        }
    except Exception as e:
        logger.error(f"[CREATE_TICKET] Error creating ticket: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "is_notification": False
        }


async def register_required_env_vars_tool(function_args, project_id, conversation_id):
    """
    Register required environment variables for a project.
    Creates empty placeholder entries marked as 'missing' and optionally creates a ticket.
    """
    from projects.models import Project, ProjectEnvironmentVariable, ProjectTicket
    from asgiref.sync import sync_to_async

    logger.info(f"[ENV_VARS] Registering required env vars for project {project_id}")

    env_vars = function_args.get('env_vars', [])
    reason = function_args.get('reason', 'Required by application')
    create_ticket = function_args.get('create_ticket', True)

    if not env_vars:
        return {
            "is_notification": False,
            "message_to_agent": "No environment variables specified to register."
        }

    # Get the project
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Project with ID {project_id} not found."
        }

    created_vars = []
    existing_vars = []

    @sync_to_async
    def _register_env_vars():
        nonlocal created_vars, existing_vars
        from projects.utils.encryption import encrypt_value

        for var in env_vars:
            key = var.get('key', '').upper().strip()
            description = var.get('description', '')
            example = var.get('example', '')
            is_secret = var.get('is_secret', True)

            if not key:
                continue

            # Build description with example if provided
            full_description = description
            if example:
                full_description += f" (Example: {example})"

            # Check if variable already exists
            existing = ProjectEnvironmentVariable.objects.filter(
                project=project,
                key=key
            ).first()

            if existing:
                # If exists and has a value, skip
                if existing.has_value:
                    existing_vars.append(key)
                    continue
                # If exists but no value, update description if provided
                if full_description:
                    existing.description = full_description
                    existing.save()
                existing_vars.append(key)
            else:
                # Create new empty placeholder
                env_var = ProjectEnvironmentVariable(
                    project=project,
                    key=key,
                    encrypted_value=encrypt_value(''),  # Empty value
                    is_secret=is_secret,
                    is_required=True,
                    has_value=False,  # Mark as missing
                    description=full_description
                )
                env_var.save()
                created_vars.append(key)
                logger.info(f"[ENV_VARS] Created required env var: {key}")

    await _register_env_vars()

    # Create a ticket if requested and we created new vars
    ticket_id = None
    if create_ticket and created_vars:
        @sync_to_async
        def _create_ticket():
            # Build ticket description
            var_list = "\n".join([f"- `{key}`" for key in created_vars])
            ticket_description = f"""## Required Environment Variables

The following environment variables are required for the application to run properly:

{var_list}

**Reason:** {reason}

### Action Required
Please go to Project Settings → Environment tab and provide values for the missing environment variables (shown in red).
"""

            # Create the ticket
            ticket = ProjectTicket.objects.create(
                project=project,
                name="⚠️ Configure Required Environment Variables",
                description=ticket_description,
                status='open',
                priority='High'
            )
            logger.info(f"[ENV_VARS] Created ticket #{ticket.id} for missing env vars")
            return ticket.id

        ticket_id = await _create_ticket()

    # Build response message
    message_parts = []
    if created_vars:
        message_parts.append(f"Created {len(created_vars)} required environment variable(s): {', '.join(created_vars)}")
    if existing_vars:
        message_parts.append(f"Skipped {len(existing_vars)} existing variable(s): {', '.join(existing_vars)}")
    if ticket_id:
        message_parts.append(f"Created ticket #{ticket_id} to remind user to provide values.")

    return {
        "is_notification": True,
        "notification_type": "env_vars_registered",
        "notification_marker": "__NOTIFICATION__",
        "created_vars": created_vars,
        "existing_vars": existing_vars,
        "ticket_id": ticket_id,
        "message_to_agent": " ".join(message_parts) if message_parts else "No changes made."
    }


async def run_code_server_tool(function_args, project_id, conversation_id):
    """
    Execute code via SSH on the Magpie server and open the app in the artifacts panel.
    Uses default values if not specified: command='cd /workspace/nextjs-app && npm run dev', port=3000
    """
    logger.info("Run code server tool called")
    logger.debug(f"Function arguments: {function_args}")

    if not magpie_available():
        return {
            "is_notification": False,
            "message_to_agent": "Magpie workspace is not available. Configure the Magpie SDK and API key to run apps."
        }

    # Get parameters with defaults
    command = function_args.get('command', 'cd /workspace/nextjs-app && npm run dev')
    port = function_args.get('port', 3000)
    description = function_args.get('description', 'Starting development server')

    project = await get_project(project_id) if project_id else None

    # Fetch workspace
    workspace = await _fetch_workspace(workspace_id=None, project=project, conversation_id=conversation_id)

    if not workspace:
        return {
            "is_notification": False,
            "message_to_agent": "No Magpie workspace found. Workspaces are automatically created during ticket execution."
        }

    if workspace.status != 'ready':
        return {
            "is_notification": False,
            "message_to_agent": f"Workspace is not ready yet (status: {workspace.status}). Wait for provisioning to complete."
        }

    if not workspace.ipv6_address:
        return {
            "is_notification": False,
            "message_to_agent": "Workspace IPv6 address is not available. Try restarting the workspace."
        }

    # Execute the command via SSH with environment variables
    try:
        client = get_magpie_client()

        # Build command with project environment variables
        env_exports = get_project_env_exports(project_id) if project_id else []
        if env_exports:
            env_prefix = " && ".join(env_exports)
            full_command = f"{env_prefix} && {command}"
            logger.info(f"[RUN_CODE_SERVER] Injecting {len(env_exports)} env vars")
        else:
            full_command = command

        logger.info(f"Executing command on workspace: {command}")

        # Execute the command using _run_magpie_ssh for proper env injection
        result = await asyncio.to_thread(
            _run_magpie_ssh,
            client,
            workspace.job_id,
            full_command,
            30,  # Short timeout as server runs in background
            True,  # with_node_env
            project_id,
        )

        logger.info(f"Command execution result: exit_code={result.get('exit_code')}")

    except Exception as exc:
        logger.error(f"Error executing command: {exc}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error executing command: {str(exc)}"
        }

    # Use proxy URL if available, otherwise fall back to IPv6
    app_url = await async_get_or_fetch_proxy_url(workspace, port=port)
    if not app_url:
        ipv6 = workspace.ipv6_address.strip('[]')
        app_url = f"http://[{ipv6}]:{port}"

    logger.info(f"App should be available at: {app_url}")

    # Send notification to open the app in artifacts panel
    return {
        "is_notification": True,
        "notification_type": "open_app",
        "message_to_agent": f"{description}. The app should be starting at {app_url}",
        "app_url": app_url,
        "port": port,
        "command": command,
        "workspace_id": workspace.workspace_id,
        "notification_marker": "__NOTIFICATION__"
    }


async def open_app_in_artifacts_tool(function_args, project_id, conversation_id):
    """
    Open the app in the artifacts panel.
    Fetches the workspace and constructs the app URL from the IPv6 address.
    Can optionally start the dev server if not already running.
    """
    if not magpie_available():
        return {
            "is_notification": False,
            "message_to_agent": "Magpie workspace is not available. Configure the Magpie SDK and API key to run apps."
        }

    project = await get_project(project_id) if project_id else None
    workspace_id = function_args.get('workspace_id')
    port = function_args.get('port', 3000)
    start_server = function_args.get('start_server', False)
    server_command = function_args.get('server_command', 'npm run dev')

    # Fetch workspace by workspace_id or project
    workspace = await _fetch_workspace(workspace_id=workspace_id, project=project, conversation_id=conversation_id)

    if not workspace:
        return {
            "is_notification": False,
            "message_to_agent": "No Magpie workspace found. Workspaces are automatically created during ticket execution."
        }

    if workspace.status != 'ready':
        return {
            "is_notification": False,
            "message_to_agent": f"Workspace is not ready yet (status: {workspace.status}). Wait for provisioning to complete."
        }

    if not workspace.ipv6_address:
        return {
            "is_notification": False,
            "message_to_agent": "Workspace IPv6 address is not available. Try restarting the workspace."
        }

    # Optionally start the dev server
    if start_server:
        try:
            client = get_magpie_client()
        except RuntimeError as exc:
            logger.error("Magpie client configuration error: %s", exc)
            return {
                "is_notification": False,
                "message_to_agent": f"Magpie client error: {exc}"
            }

        # Start the server in background
        start_cmd = textwrap.dedent(
            f"""
            cd nextjs-app
            if [ -f .devserver_pid ]; then
              old_pid=$(cat .devserver_pid)
              if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
                echo "Server already running with PID $old_pid"
                exit 0
              fi
            fi
            : > /workspace/nextjs-app/dev.log
            nohup {server_command} -- --hostname :: --port {port} > /workspace/nextjs-app/dev.log 2>&1 &
            pid=$!
            echo "$pid" > .devserver_pid
            echo "PID:$pid"
            sleep 2
            """
        )

        try:
            result = await asyncio.to_thread(
                _run_magpie_ssh,
                client,
                workspace.job_id,
                start_cmd,
                120,
                True,
                project_id,
            )
            logger.info(
                "[MAGPIE][START SERVER] workspace=%s exit_code=%s",
                workspace.workspace_id,
                result.get('exit_code')
            )

            # Extract PID
            stdout = result.get('stdout', '')
            pid = _extract_pid_from_output(stdout)

            # Update workspace metadata
            metadata_updates = {
                "dev_server_pid": pid,
                "last_server_start": datetime.utcnow().isoformat() + "Z",
            }
            await sync_to_async(_update_workspace_metadata, thread_sensitive=True)(workspace, **metadata_updates)

        except Exception as exc:
            logger.exception("Failed to start dev server")
            # Continue anyway - maybe server is already running

    # Use proxy URL if available, otherwise fall back to IPv6
    app_url = await async_get_or_fetch_proxy_url(workspace, port=port)
    if not app_url:
        app_url = f"http://[{workspace.ipv6_address}]:{port}"

    logger.info(f"Opening app in artifacts panel: {app_url}")

    return {
        "is_notification": True,
        "notification_type": "app_url",
        "app_url": app_url,
        "workspace_id": workspace.workspace_id,
        "port": port,
        "message_to_agent": f"App is now available at {app_url}. The app will be displayed in the artifacts panel."
    }


async def run_command_locally(command: str, project_id: int | str = None, conversation_id: int | str = None, ticket_id: int = None) -> dict:
    """
    Run a command in the local terminal using subprocess.
    Creates a local workspace directory if it doesn't exist.
    """
    # Try to get ticket_id from context variable if not passed
    if ticket_id is None:
        try:
            from tasks.task_definitions import current_ticket_id
            ticket_id = current_ticket_id.get()
            if ticket_id:
                logger.info(f"[RUN_COMMAND_LOCALLY] Retrieved ticket_id={ticket_id} from context variable")
        except Exception as e:
            logger.debug(f"[RUN_COMMAND_LOCALLY] Could not get ticket_id from context: {e}")

    project = await get_project(project_id)
    # Create workspace directory if it doesn't exist
    workspace_path = Path.home() / "LFG" / "workspace" / project.name
    workspace_path.mkdir(parents=True, exist_ok=True)

    command_to_run = f"cd {workspace_path} && {command}"
    logger.debug(f"Local Command: {command_to_run}")

    # Create command record in database (only if ticket_id is provided)
    cmd_record = None
    if ticket_id:
        try:
            ticket = await sync_to_async(ProjectTicket.objects.get)(id=ticket_id)
            cmd_record = await sync_to_async(TicketLog.objects.create)(
                ticket=ticket,
                command=command,
                output=None,  # Will update after execution
                exit_code=None
            )
        except ProjectTicket.DoesNotExist:
            logger.warning(f"Ticket {ticket_id} not found, skipping log creation")
        except Exception as e:
            logger.error(f"Error creating TicketLog: {e}")

    success = False
    stdout = ""
    stderr = ""

    try:
        # Execute the command locally using subprocess in thread pool
        # Pass project.id to inject project environment variables
        success, stdout, stderr = await asyncio.get_event_loop().run_in_executor(
            None, execute_local_command, command, str(workspace_path), project.id
        )

        logger.debug(f"Local Command output: {stdout}")
        if stderr:
            logger.warning(f"Local Command stderr: {stderr}")

        # Update command record with output
        if cmd_record:
            await sync_to_async(lambda: (
                setattr(cmd_record, 'output', stdout if success else stderr),
                setattr(cmd_record, 'exit_code', 0 if success else 1),
                cmd_record.save()
            )[2])()

    except Exception as e:
        error_msg = f"Failed to execute command locally: {str(e)}"
        stderr = error_msg

        # Update command record with error
        if cmd_record:
            await sync_to_async(lambda: (
                setattr(cmd_record, 'output', error_msg),
                setattr(cmd_record, 'exit_code', 1),
                cmd_record.save()
            )[2])()

    if not success:
        return {
            "is_notification": False,
            "notification_type": "command_error",
            "message_to_agent": f"{stderr}The local command execution failed. Stop generating further steps and inform the user that the command could not be executed.",
        }
    
    return {
        "is_notification": False,
        "notification_type": "command_output", 
        "message_to_agent": f"Local command output: {stdout}Fix if there is any error, otherwise you can proceed to next step",
    }

# Updated run_server_locally function
async def run_server_locally(command: str, project_id: int | str = None,
                           conversation_id: int | str = None,
                           application_port: int | str = None,
                           type: str = None) -> dict:
    """
    Run a server command locally in background.
    """
    logger.debug(f"Local Application port: {application_port}")
    logger.debug(f"Local Type: {type}")

    # Get project for env vars injection
    project = await get_project(project_id) if project_id else None
    db_project_id = project.id if project else None

    # Create workspace directory if it doesn't exist
    workspace_path = Path.home() / "LFG" / "workspace"
    workspace_path.mkdir(parents=True, exist_ok=True)
    
    # Validate port
    if not application_port:
        return {
            "is_notification": False,
            "notification_type": "command_error",
            "message_to_agent": "Port is required to run a server."
        }
    
    try:
        application_port = int(application_port)
        if application_port < 1 or application_port > 65535:
            return {
                "is_notification": False,
                "notification_type": "command_error",
                "message_to_agent": f"Invalid application port: {application_port}. Port must be between 1 and 65535."
            }
    except (ValueError, TypeError):
        return {
            "is_notification": False,
            "notification_type": "command_error",
            "message_to_agent": f"Invalid application port: {application_port}. Must be a valid integer."
        }
    
    # 1. Save server config to database
    await sync_to_async(lambda: ServerConfig.objects.update_or_create(
        project_id=project_id,
        port=application_port,
        defaults={
            'command': command,
            'start_server_command': command,
            'type': type or 'application'
        }
    ))()
    
    # 2. Check if server is running on the port and kill it
    kill_command = f"lsof -ti:{application_port} | xargs kill -9 2>/dev/null || true"
    success, stdout, stderr = execute_local_command(kill_command, str(workspace_path))
    logger.info(f"Killed existing process on port {application_port}")

    # Wait a moment for port to be freed
    await asyncio.sleep(1)

    # 3. Run the server command in background using nohup
    # Create a log file for the server
    log_file = workspace_path / f"server_{project_id}_{application_port}.log"

    # Build command with env vars if project has them
    env_exports = get_project_env_exports(db_project_id) if db_project_id else []
    if env_exports:
        # Prepend env exports to the server command
        env_prefix = " && ".join(env_exports)
        full_server_command = f"{env_prefix} && {command}"
        logger.info(f"[SERVER] Injecting {len(env_exports)} env vars for server start")
    else:
        full_server_command = command

    # Use nohup to run in background and redirect output to log file
    background_command = f"nohup sh -c '{full_server_command}' > {log_file} 2>&1 &"

    success, stdout, stderr = execute_local_command(background_command, str(workspace_path))
    
    if not success:
        return {
            "is_notification": False,
            "notification_type": "command_error",
            "message_to_agent": f"Failed to start server: {stderr}"
        }
    
    # 4. Wait a bit for server to start
    await asyncio.sleep(3)
    
    # 5. Check if server is running by checking if port is listening
    check_command = f"lsof -i:{application_port} | grep LISTEN"
    success, stdout, stderr = execute_local_command(check_command, str(workspace_path))
    
    if success and stdout:
        # Server is running
        return {
            "is_notification": False,
            "notification_type": "server_started",
            "message_to_agent": f"✅ Server started successfully!"
                               f"📍 Running on port {application_port}\n"
                               f"🔗 URL: [http://localhost:{application_port}](http://localhost:{application_port})\n"
                               f"📄 Logs: {log_file}"
                               f"The server is running in the background. Proceed with next steps.\n"
                               f"To view logs: tail -f {log_file}"
        }
    else:
        # Check logs for errors
        try:
            with open(log_file, 'r') as f:
                log_content = f.read()
                last_lines = '\n'.join(log_content.split('\n')[-20:])
        except:
            last_lines = "Could not read log file"
        
        return {
            "is_notification": False,
            "notification_type": "server_error",
            "message_to_agent": f"⚠️ Server may not have started properly."
                               f"Recent logs:\n```\n{last_lines}\n```"
                               f"Please check the logs and fix any issues."
        }


# Simple helper function to stop a server
async def stop_server(project_id: int, port: int) -> dict:
    """Stop a server running on a specific port"""
    workspace_path = Path.home() / "LFG" / "workspace"
    
    kill_command = f"lsof -ti:{port} | xargs kill -9 2>/dev/null || true"
    success, stdout, stderr = execute_local_command(kill_command, str(workspace_path))
    
    return {
        "is_notification": False,
        "notification_type": "server_stopped",
        "message_to_agent": f"Server on port {port} has been stopped."
    }


# Function to restart server (can be called from a button)
async def restart_server_from_config(project_id: int) -> dict:
    """Restart all servers for a project using saved config"""
    
    configs = await sync_to_async(list)(
        ServerConfig.objects.filter(project_id=project_id)
    )
    
    results = []
    for config in configs:
        # Use start_server_command if available, otherwise fall back to command
        server_command = config.start_server_command or config.command
        result = await run_server_locally(
            command=server_command,
            project_id=project_id,
            application_port=config.port,
            type=config.type
        )
        # results.append(f"Port {config.port}: {result['message_to_agent'].split('\\n')[0]}")
        results.append(result['message_to_agent'])
    
    return {
        "is_notification": False,
        "notification_type": "servers_restarted",
        "message_to_agent": "\n".join(results)
    }

async def copy_boilerplate_code(project_id, project_name):
    """Copy the boilerplate code from the project"""
    logger.info("Copy boilerplate code function called ")
    logger.debug(f"Project name: {project_name}")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    try:
        # Use provided_name if available, otherwise use the passed project_name
        folder_name = project.provided_name if project.provided_name else project_name
        
        # Define source and destination paths
        source_path = os.path.join(os.getcwd(), "boilerplate", "lfg-template")
        dest_path = os.path.join(os.path.expanduser("~"), "LFG", "workspace", folder_name)
        logger.debug(f"Source path: {source_path}")
        logger.debug(f"Destination path: {dest_path}")
        
        # Create destination directory if it doesn't exist
        os.makedirs(dest_path, exist_ok=True)
        
        # Copy files using shutil
        import shutil
        shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
        
        # Initialize git repository if not already initialized
        if not os.path.exists(os.path.join(dest_path, ".git")):
            subprocess.run(["git", "init"], cwd=dest_path, check=True)
            
            # Create initial commit
            subprocess.run(["git", "add", "."], cwd=dest_path, check=True)
            subprocess.run(["git", "commit", "-m", "Initial commit: Copy boilerplate code"], cwd=dest_path, check=True)
        
        return {
            "is_notification": False,
            "notification_type": "boilerplate_code_copied",
            "message_to_agent": f"Boilerplate code has been successfully copied to ~/LFG/workspace/{folder_name}. The project has been initialized with git."
        }
    except Exception as e:
        logger.error(f"Error copying boilerplate code: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error copying boilerplate code: {str(e)}"
        }

async def capture_name(action, project_name, project_id):
    """
    Save or retrieve the project name
    """
    logger.info(f"Capture name function called with action: {action}, project_name: {project_name}")
    
    if action == "save":
        return await save_project_name(project_name, project_id)
    elif action == "get":
        return await get_project_name(project_id)
    else:
        return {
            "is_notification": False,
            "message_to_agent": "Error: Invalid action. Must be 'save' or 'get'"
        }

async def save_project_name(project_name, project_id):
    """
    Save the project name to the project model
    """
    logger.info(f"Save project name function called: {project_name}")
    
    if not project_name:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_name is required when action is 'save'"
        }
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    try:
        # Update the provided_name field with user-confirmed name
        await sync_to_async(lambda: (
            setattr(project, 'provided_name', project_name),
            project.save()
        )[1])()
        
        return {
            "is_notification": False,
            "notification_type": "project_name_saved",
            "message_to_agent": f"Project name '{project_name}' has been saved successfully as provided_name"
        }
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving project name: {str(e)}"
        }

async def get_project_name(project_id):
    """
    Retrieve the project name from the project model
    """
    logger.info(f"Get project name function called for project_id: {project_id}")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    try:
        if project.provided_name:
            return {
                "is_notification": False,
                "notification_type": "project_name_retrieved",
                "message_to_agent": f"Project name is: {project.provided_name}"
            }
        else:
            current_project_name = project.name.replace(' ', '-').lower()
            # Remove all special characters except alphanumeric and dashes
            import re
            current_project_name = re.sub(r'[^a-z0-9-]', '', current_project_name)
            return {
                "is_notification": False,
                "notification_type": "project_name_not_confirmed",
                "message_to_agent": f"Ask the user if they wish to use the name. You can ask user if they want to save this name: '{current_project_name}'? Do not proceed until user responds."
            }
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error retrieving project name: {str(e)}"
        }

async def implement_ticket(ticket_id, project_id, conversation_id, ticket_details, implementation_plan):
    """
    Implement a specific ticket with all its requirements
    Returns a special marker that indicates this tool should stream its implementation
    """
    try:
        logger.debug(f"\nTicket details: {ticket_details}")
        
        # Extract key details
        ticket_name = ticket_details.get('name', 'Unknown')
        project_name = ticket_details.get('project_name', 'Unknown')
        requires_worktree = ticket_details.get('details', {}).get('requires_worktree', False)
        
        # Instead of executing here, return a special response that tells the system
        # to create a streaming implementation
        return {
            "is_streaming_tool": True,
            "tool_name": "implement_ticket",
            "streaming_config": {
                "ticket_id": ticket_id,
                "ticket_name": ticket_name,
                "project_name": project_name,
                "requires_worktree": requires_worktree,
                "ticket_details": ticket_details,
                "implementation_plan": implementation_plan
            },
            "message_to_agent": f"I'll now implement ticket #{ticket_id}: {ticket_name}. Let me work through this step by step..."
        }
        
    except Exception as e:
        logger.error(f"Error setting up ticket implementation {ticket_id}: {str(e)}")
        return {
            "is_notification": False,
            "notification_type": "ticket_error",
            "message_to_agent": f"Error setting up ticket implementation {ticket_id}: {str(e)}",
            "error": str(e)
        }

async def save_file_from_stream(file_content, project_id, file_type, file_name):
    """
    Save file content that was captured from the streaming response.
    This function is called from streaming_handlers.py when file generation is complete.
    
    Args:
        file_content: The complete file content captured from streaming
        project_id: The project ID to save the file for
        file_type: Type of file (prd, implementation, design, test, etc.)
        file_name: Name of the file
        
    Returns:
        Dict with notification data
    """
    logger.info(f"[SAVE_FILE_FROM_STREAM] CALLED!")
    logger.info(f"[SAVE_FILE_FROM_STREAM] Saving file from stream for project {project_id}")
    logger.info(f"[SAVE_FILE_FROM_STREAM] File type: {file_type}, Name: {file_name}, Size: {len(file_content)} characters")
    logger.info(f"[SAVE_FILE_FROM_STREAM] First 200 chars: {file_content[:200]}")
    logger.info(f"[SAVE_FILE_FROM_STREAM] Last 200 chars: {file_content[-200:]}")
    
    # Validate project ID
    if not project_id:
        logger.error("[SAVE_FILE_FROM_STREAM] No project_id provided")
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required"
        }
    
    # Get the project
    try:
        project = await get_project(project_id)
        if not project:
            logger.error(f"Project with ID {project_id} not found")
            return {
                "is_notification": False,
                "message_to_agent": f"Error: Project with ID {project_id} does not exist"
            }
    except Exception as e:
        logger.error(f"Error fetching project: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error fetching project: {str(e)}"
        }
    
    # Validate file content
    if not file_content or not file_content.strip():
        logger.error("File content is empty")
        return {
            "is_notification": False,
            "message_to_agent": "Error: File content cannot be empty"
        }
    
    # Clean up any residual artifacts
    file_content = file_content.strip()
    
    # Remove leading '>' if present
    if file_content.startswith('>'):
        file_content = file_content[1:].strip()
    
    # Remove any trailing tag fragments
    if '</lfg-file' in file_content:
        file_content = file_content[:file_content.rfind('</lfg-file')].strip()
    
    # Remove opening tag if it somehow got included
    if '<lfg-file' in file_content:
        import re
        file_content = re.sub(r'<lfg-file[^>]*>', '', file_content, count=1).lstrip()
    
    try:
        # Save file to database
        logger.info(f"[SAVE_FILE_FROM_STREAM] About to save to database")
        file_obj, created = await sync_to_async(
            ProjectFile.objects.get_or_create
        )(
            project=project,
            name=file_name,
            file_type=file_type,
            defaults={}  # Don't set content in defaults
        )
        logger.info(f"[SAVE_FILE_FROM_STREAM] File object {'created' if created else 'updated'}, ID: {file_obj.id if file_obj else 'None'}")
        
        # Save content using the model's save_content method
        logger.info(f"[SAVE_FILE_FROM_STREAM] Saving content to file object")
        await sync_to_async(file_obj.save_content)(file_content)
        await sync_to_async(file_obj.save)()
        logger.info(f"[SAVE_FILE_FROM_STREAM] Content saved successfully")
        
        if not created:
            logger.info(f"[SAVE_FILE_FROM_STREAM] Updated existing {file_type} file '{file_name}' for project {project_id}")
        else:
            logger.info(f"[SAVE_FILE_FROM_STREAM] Created new {file_type} file '{file_name}' for project {project_id}")
        
        action = "created" if created else "updated"
        
        # Get display name for notification
        file_type_display = {
            'prd': 'PRD',
            'implementation': 'Implementation',
            'design': 'Design Document',
            'test': 'Test Plan'
        }.get(file_type, 'File')
        
        logger.info(f"Returning notification with file_id: {file_obj.id}")
        logger.info(f"[SAVE NOTIFICATION] Type: {file_type}, Name: {file_name}, ID: {file_obj.id}")
        
        notification = {
            "is_notification": True,  # Fixed: Must be True for notification to be sent
            "notification_type": "file_saved",  # Use a generic notification type for all saved files
            "message_to_agent": f"{file_type_display} '{file_name}' {action} successfully in the database",
            "file_name": file_name,
            "file_type": file_type,
            "file_id": file_obj.id,
            "project_id": str(project.project_id) if project else None,  # Include project_id
            "notification_marker": "__NOTIFICATION__"  # Add this marker
        }
        
        logger.info(f"[SAVE NOTIFICATION] Full notification data: {notification}")
        logger.info(f"[SAVE_FILE_FROM_STREAM] RETURNING NOTIFICATION - Type: {notification.get('notification_type')}, Has ID: {bool(notification.get('file_id'))}")
        return notification
        
    except Exception as e:
        logger.error(f"Error saving file: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving file: {str(e)}"
        }

async def edit_file_content(file_id, edit_operations, project_id):
    """
    Edit an existing file with specified operations
    
    Args:
        file_id: The ID of the file to edit
        edit_operations: List of edit operations to apply
        project_id: The project ID
    
    Returns:
        Dict with operation result
    """
    logger.info(f"[edit_file_content] Starting edit for file {file_id} with {len(edit_operations)} operations")
    logger.info(f"[edit_file_content] Project ID: {project_id}")
    
    # Validate inputs
    if not file_id:
        return {
            "is_notification": False,
            "message_to_agent": "Error: file_id is required for editing"
        }
    
    if not edit_operations or not isinstance(edit_operations, list):
        return {
            "is_notification": False,
            "message_to_agent": "Error: edit_operations must be a non-empty list"
        }
    
    # Get the file
    try:
        logger.info(f"[edit_file_content] Fetching file with ID {file_id} from project {project_id}")
        file_obj = await sync_to_async(
            ProjectFile.objects.get
        )(id=file_id, project_id=project_id)
        logger.info(f"[edit_file_content] Found file: {file_obj.name} (Type: {file_obj.file_type})")
    except ProjectFile.DoesNotExist:
        logger.error(f"[edit_file_content] File with ID {file_id} not found in project {project_id}")
        return {
            "is_notification": False,
            "message_to_agent": f"File with ID {file_id} not found in project {project_id}"
        }
    
    # Get current content and split into lines
    current_content = file_obj.content
    lines = current_content.split('\n')
    original_line_count = len(lines)
    logger.info(f"[edit_file_content] Current file has {original_line_count} lines")
    
    # Sort operations by type and position to apply them in order
    # Apply replacements first, then insertions
    replace_ops = [op for op in edit_operations if op.get('type') == 'replace_lines']
    insert_ops = [op for op in edit_operations if op.get('type') == 'insert_after']
    pattern_ops = [op for op in edit_operations if op.get('type') == 'pattern_replace']
    
    # Sort replace operations by start line (descending) to avoid index shifting
    replace_ops.sort(key=lambda x: x.get('start', 0), reverse=True)
    # Sort insert operations by line number (descending) to avoid index shifting
    insert_ops.sort(key=lambda x: x.get('line', 0), reverse=True)
    
    # Apply replace operations
    logger.info(f"[edit_file_content] Applying {len(replace_ops)} replace operations")
    for i, operation in enumerate(replace_ops):
        try:
            start = operation['start'] - 1  # Convert to 0-based index
            end = operation['end']  # End is inclusive in 1-based, exclusive in slice
            new_lines = operation['content'].split('\n')
            
            logger.info(f"[edit_file_content] Replace op {i+1}: lines {start+1}-{end} with {len(new_lines)} new lines")
            
            # Validate line numbers
            if start < 0 or end > len(lines):
                logger.warning(f"[edit_file_content] Invalid line range: {start+1}-{end} for file with {len(lines)} lines")
                continue
                
            lines[start:end] = new_lines
            logger.info(f"[edit_file_content] Successfully replaced lines {start+1}-{end} with {len(new_lines)} new lines")
        except Exception as e:
            logger.error(f"[edit_file_content] Error applying replace operation: {str(e)}", exc_info=True)
    
    # Apply insert operations
    logger.info(f"[edit_file_content] Applying {len(insert_ops)} insert operations")
    for i, operation in enumerate(insert_ops):
        try:
            line_num = operation['line']  # Insert after this line
            new_lines = operation['content'].split('\n')
            
            logger.info(f"[edit_file_content] Insert op {i+1}: {len(new_lines)} lines after line {line_num}")
            
            # Validate line number
            if line_num < 0 or line_num > len(lines):
                logger.warning(f"[edit_file_content] Invalid insert position: after line {line_num} for file with {len(lines)} lines")
                continue
            
            # Insert after the specified line (Python slice insert at position inserts BEFORE that position)
            # So to insert after line N, we insert at position N+1
            insert_position = line_num + 1 if line_num < len(lines) else len(lines)
            lines[insert_position:insert_position] = new_lines
            logger.info(f"[edit_file_content] Successfully inserted {len(new_lines)} lines after line {line_num} (at position {insert_position})")
        except Exception as e:
            logger.error(f"[edit_file_content] Error applying insert operation: {str(e)}", exc_info=True)
    
    # Apply pattern replacements
    logger.info(f"[edit_file_content] Applying {len(pattern_ops)} pattern operations")
    for i, operation in enumerate(pattern_ops):
        try:
            pattern = operation['pattern']
            content = operation['content']
            
            logger.info(f"[edit_file_content] Pattern op {i+1}: replacing '{pattern[:30]}...' with '{content[:30]}...'")
            
            # Join lines, replace pattern, split again
            full_content = '\n'.join(lines)
            occurrences = full_content.count(pattern)
            full_content = full_content.replace(pattern, content)
            lines = full_content.split('\n')
            
            logger.info(f"[edit_file_content] Replaced {occurrences} occurrences of pattern '{pattern[:30]}...'")
        except Exception as e:
            logger.error(f"[edit_file_content] Error applying pattern operation: {str(e)}", exc_info=True)
    
    # Save the edited content
    new_content = '\n'.join(lines)
    new_line_count = len(lines)
    
    logger.info(f"[edit_file_content] Saving edited content. New line count: {new_line_count}")
    
    # Update the file
    await sync_to_async(file_obj.save_content)(new_content)
    await sync_to_async(file_obj.save)()
    
    logger.info(f"[edit_file_content] File '{file_obj.name}' edited successfully. Lines changed from {original_line_count} to {new_line_count}")
    
    result = {
        "is_notification": True,  # Fixed: Must be True for notification to be sent
        "notification_type": "file_edited",
        "message_to_agent": f"File '{file_obj.name}' edited successfully. Applied {len(edit_operations)} operations. Lines: {original_line_count} → {new_line_count}",
        "file_id": file_id,
        "file_name": file_obj.name,
        "file_type": file_obj.file_type,
        "operations_applied": len(edit_operations),
        "line_count_before": original_line_count,
        "line_count_after": new_line_count,
        "notification_marker": "__NOTIFICATION__"  # Important for UI processing
    }
    
    logger.info(f"[edit_file_content] Returning result: {result}")
    return result

async def save_implementation_from_stream(implementation_content, project_id):
    """
    Save implementation content that was captured from the streaming response.
    This function is called from ai_providers.py when implementation generation is complete.
    
    Args:
        implementation_content: The complete implementation content captured from streaming
        project_id: The project ID to save the implementation for
        
    Returns:
        Dict with notification data
    """
    logger.info(f"Saving implementation from stream for project {project_id}")
    logger.info(f"Implementation content length: {len(implementation_content)} characters")
    
    # Validate project ID
    if not project_id:
        logger.error("No project_id provided")
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required"
        }
    
    # Get the project
    try:
        project = await get_project(project_id)
        if not project:
            logger.error(f"Project with ID {project_id} not found")
            return {
                "is_notification": False,
                "message_to_agent": f"Error: Project with ID {project_id} does not exist"
            }
    except Exception as e:
        logger.error(f"Error fetching project: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error fetching project: {str(e)}"
        }
    
    # Validate implementation content
    if not implementation_content or not implementation_content.strip():
        logger.error("Implementation content is empty")
        return {
            "is_notification": False,
            "message_to_agent": "Error: Implementation content cannot be empty"
        }
    
    # Clean up any residual artifacts
    implementation_content = implementation_content.strip()
    # Remove leading '>' if present
    if implementation_content.startswith('>'):
        implementation_content = implementation_content[1:].strip()
    # Remove any trailing tag fragments
    if '</lfg-plan' in implementation_content:
        implementation_content = implementation_content[:implementation_content.rfind('</lfg-plan')].strip()
    
    try:
        # Save implementation to database
        impl_obj, created = await sync_to_async(
            ProjectImplementation.objects.get_or_create
        )(
            project=project,
            defaults={'implementation': implementation_content}
        )
        
        # Update if it already existed
        if not created:
            impl_obj.implementation = implementation_content
            await sync_to_async(impl_obj.save)()
            logger.info(f"Updated existing implementation for project {project_id}")
        else:
            logger.info(f"Created new implementation for project {project_id}")
        
        action = "created" if created else "updated"
        
        return {
            "is_notification": False,
            "notification_type": "implementation",
            "message_to_agent": f"Implementation {action} successfully in the database"
        }
        
    except Exception as e:
        logger.error(f"Error saving implementation: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving implementation: {str(e)}"
        }

async def save_prd_from_stream(prd_content, project_id, prd_name=None):
    """
    Save PRD content that was captured from the streaming response.
    This function is called from ai_providers.py when PRD generation is complete.
    
    Args:
        prd_content: The complete PRD content captured from streaming
        project_id: The project ID to save the PRD for
        prd_name: Optional name for the PRD (defaults to "Main PRD")
        
    Returns:
        Dict with notification data
    """
    logger.info(f"Saving PRD from stream for project {project_id}")
    logger.info(f"PRD content length: {len(prd_content)} characters")
    logger.info(f"PRD name: {prd_name}")
    
    # Validate project ID
    if not project_id:
        logger.error("No project_id provided")
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required"
        }
    
    # Get the project
    try:
        project = await get_project(project_id)
        if not project:
            logger.error(f"Project with ID {project_id} not found")
            return {
                "is_notification": False,
                "message_to_agent": f"Error: Project with ID {project_id} does not exist"
            }
    except Exception as e:
        logger.error(f"Error fetching project: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error fetching project: {str(e)}"
        }
    
    # Validate PRD content
    if not prd_content or not prd_content.strip():
        logger.error("PRD content is empty")
        return {
            "is_notification": False,
            "message_to_agent": "Error: PRD content cannot be empty"
        }
    
    # Clean up any residual artifacts
    prd_content = prd_content.strip()
    
    # Remove leading '>' if present (but preserve line breaks)
    if prd_content.startswith('>'):
        prd_content = prd_content[1:].lstrip(' \t')  # Only strip spaces and tabs, not newlines
    
    # Remove any trailing tag fragments more carefully
    if '</lfg-prd' in prd_content:
        # Find the last occurrence and remove everything from there
        last_tag_pos = prd_content.rfind('</lfg-prd')
        prd_content = prd_content[:last_tag_pos].rstrip()
    
    # Remove opening tag if it somehow got included
    if '<lfg-prd' in prd_content:
        # Find the tag and remove it
        import re
        prd_content = re.sub(r'<lfg-prd[^>]*>', '', prd_content, count=1).lstrip()
    
    # Ensure the content is not empty after cleaning
    prd_content = prd_content.strip()
    
    # Set default name if not provided
    if not prd_name:
        prd_name = "Main PRD"
    
    try:
        # Save PRD to database with name
        prd_obj, created = await sync_to_async(
            ProjectPRD.objects.get_or_create
        )(
            project=project, 
            name=prd_name,
            defaults={'prd': prd_content}
        )
        
        # Update existing PRD if it wasn't created
        if not created:
            prd_obj.prd = prd_content
            await sync_to_async(prd_obj.save)()
        
        action = "created" if created else "updated"
        logger.info(f"PRD '{prd_name}' {action} successfully for project {project_id}")
        
        return {
            "is_notification": False,
            "notification_type": "prd",
            "message_to_agent": f"PRD '{prd_name}' {action} successfully in the database",
            "prd_name": prd_name
        }
        
    except Exception as e:
        logger.error(f"Error saving PRD from stream: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving PRD: {str(e)}"
        }

async def save_ticket_from_stream(ticket_data, project_id):
    """
    Save a single ticket that was captured from the streaming response.
    This function is called from ai_providers.py when a complete ticket is parsed.
    
    Args:
        ticket_data: The complete ticket data parsed from <lfg-ticket> tags
        project_id: The project ID to save the ticket for
        
    Returns:
        Dict with notification data
    """
    logger.info(f"Saving ticket from stream for project {project_id}")
    logger.debug(f"Ticket data: {ticket_data}")
    
    # Validate project ID
    if not project_id:
        logger.error("No project_id provided")
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required"
        }
    
    # Get project
    project = await get_project(project_id)
    if not project:
        logger.error(f"Project with ID {project_id} not found")
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    try:
        # Create ticket with enhanced details
        new_ticket = await sync_to_async(ProjectTicket.objects.create)(
            project=project,
            name=ticket_data.get('name', ''),
            description=ticket_data.get('description', ''),
            priority=ticket_data.get('priority', 'Medium'),
            status='open',
            role=ticket_data.get('role', 'agent'),
            ui_requirements=ticket_data.get('ui_requirements', {}),
            component_specs=ticket_data.get('component_specs', {}),
            acceptance_criteria=ticket_data.get('acceptance_criteria', []),
            dependencies=ticket_data.get('dependencies', [])
        )
        
        logger.info(f"Ticket created successfully with ID {new_ticket.id}")
        
        return {
            "is_notification": False,
            "notification_type": "checklist",
            "message_to_agent": f"Ticket '{ticket_data.get('name', 'Unnamed')}' created successfully"
        }
        
    except Exception as e:
        logger.error(f"Error saving ticket from stream: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving ticket: {str(e)}"
        }


# Only to be used with OpenAIProvider
# As OpenAI doesn't support web search tool yet
# Claude does.
async def web_search(queries, conversation_id=None):
    """
    Perform web searches using OpenAI's web search capabilities.
    This function is only available for OpenAI provider.

    Args:
        queries: List of search query strings
        conversation_id: The conversation ID (optional)

    Returns:
        Dict with combined search results or error message
    """
    logger.info(f"Web search function called with {len(queries)} queries: {queries}")

    if not queries or not isinstance(queries, list):
        return {
            "is_notification": False,
            "message_to_agent": "Error: queries must be a non-empty list of search queries"
        }

    try:
        # Get user and conversation details
        model = "gpt-5-nano"  # Default model

        # Get OpenAI API key
        openai_api_key = os.environ.get('OPENAI_API_KEY')

        # Initialize OpenAI client
        import openai
        client = openai.OpenAI(api_key=openai_api_key)

        logger.info(f"Using model {model} for web search")

        # Loop through each query and collect results
        all_results = []
        for idx, query in enumerate(queries, 1):
            if not query or not isinstance(query, str):
                logger.warning(f"Skipping invalid query at index {idx}: {query}")
                continue

            logger.info(f"Searching query {idx}/{len(queries)}: {query}")

            try:
                # Make the search request using OpenAI's responses.create API
                response = client.responses.create(
                    model=model,
                    tools=[{"type": "web_search_preview"}],
                    input=query
                )

                # Extract the search results from the response
                if response:
                    search_results = str(response)
                    all_results.append(f"### Query {idx}: {query}\n\n{search_results}\n")
                    logger.info(f"Web search completed successfully for query {idx}: {query}")
                else:
                    all_results.append(f"### Query {idx}: {query}\n\nNo results found\n")

            except Exception as query_error:
                logger.error(f"Error searching query {idx} '{query}': {str(query_error)}")
                all_results.append(f"### Query {idx}: {query}\n\nError: {str(query_error)}\n")

        # Combine all results
        if all_results:
            combined_results = "\n---\n\n".join(all_results)
            return {
                "is_notification": False,
                "notification_type": "toolhistory",
                "message_to_agent": f"Web search results for {len(queries)} queries:\n\n{combined_results}"
            }
        else:
            return {
                "is_notification": False,
                "message_to_agent": "No valid queries provided or all searches failed"
            }

    except Exception as e:
        logger.error(f"Error performing web searches: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error performing web searches: {str(e)}"
        }

async def get_file_list(project_id, file_type="all", limit=10):
    """
    Get the list of files in the project
    
    Args:
        project_id: The project ID
        file_type: Type of files to retrieve ("prd", "implementation", "design", "all")
        limit: Number of files to return (default: 10)
        
    Returns:
        Dict with list of files or error message
    """
    logger.info(f"Get file list function called for project {project_id}, file_type: {file_type}")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    try:
        # Build query based on file_type
        query_kwargs = {"project": project}
        if file_type != "all":
            query_kwargs["file_type"] = file_type
        
        # Get files from ProjectFile model
        files = await sync_to_async(
            lambda: list(ProjectFile.objects.filter(**query_kwargs).order_by("-updated_at")[:limit])
        )()
        
        if not files:
            return {
                "is_notification": False,
                "notification_type": "file_list",
                "message_to_agent": f"No {file_type} files found for this project"
            }
        
        # Format file list
        file_list = []
        for file in files:
            file_list.append({
                "file_id": file.id,
                "name": file.name,
                "file_type": file.file_type,
                "created_at": file.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": file.updated_at.strftime("%Y-%m-%d %H:%M:%S")
            })
        
        return {
            "is_notification": False,
            "notification_type": "file_list",
            "message_to_agent": f"Found {len(file_list)} {file_type} files. Here are the file details {file_list}",
            "files": file_list
        }
        
    except Exception as e:
        logger.error(f"Error getting file list: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error getting file list: {str(e)}"
        }

async def get_file_content(project_id, file_ids):
    """
    Get the content of multiple files in the project
    
    Args:
        project_id: The project ID
        file_ids: A single file ID or list of file IDs to retrieve (max 5)
        
    Returns:
        Dict with file contents or error message
    """
    print(f"Get file content function called for project {project_id}, file_ids: {file_ids}")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    # Handle both single file_id and list of file_ids
    if isinstance(file_ids, (int, str)):
        file_ids = [file_ids]
    elif not isinstance(file_ids, list):
        return {
            "is_notification": False,
            "message_to_agent": "Error: file_ids must be an integer, string, or list"
        }
    
    if not file_ids:
        return {
            "is_notification": False,
            "message_to_agent": "Error: at least one file_id is required"
        }
    
    # Limit to 5 files
    if len(file_ids) > 5:
        return {
            "is_notification": False,
            "message_to_agent": "Error: Maximum 5 files can be retrieved at once"
        }
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    try:
        # Get multiple files by IDs and ensure they belong to the project
        files = await sync_to_async(
            lambda: list(ProjectFile.objects.filter(id__in=file_ids, project=project))
        )()
        
        if not files:
            return {
                "is_notification": False,
                "message_to_agent": f"Error: No files found with the provided IDs in project {project_id}"
            }
        
        # Check which file IDs were not found
        found_ids = {file.id for file in files}
        missing_ids = set(file_ids) - found_ids
        
        # Format file contents
        file_contents = []
        for file_obj in files:
            file_contents.append({
                "file_id": file_obj.id,
                "name": file_obj.name,
                "file_type": file_obj.file_type,
                "content": file_obj.file_content,
                "created_at": file_obj.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": file_obj.updated_at.strftime("%Y-%m-%d %H:%M:%S")
            })
        
        response = {
            "is_notification": False,
            "notification_type": "file_content",
            "message_to_agent": f"Retrieved {len(files)} file(s). Here are the file contents: {file_contents}. You can proceed to the next step.",
            "files": file_contents
        }
        
        if missing_ids:
            response["missing_file_ids"] = list(missing_ids)
            response["message_to_agent"] += f". Warning: File IDs not found: {missing_ids}"
        
        return response
        
    except Exception as e:
        logger.error(f"Error getting file content: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error getting file content: {str(e)}"
        }
        

# Add this function to ai_functions.py

async def update_file_content(file_id, updated_content, project_id):
    """
    Update an existing file with new content (complete replacement)
    
    Args:
        file_id: The ID of the file to update
        updated_content: The complete new content for the file
        project_id: The project ID
    
    Returns:
        Dict with operation result
    """
    logger.info(f"Updating file {file_id} with new content ({len(updated_content)} characters)")

    logger.info(f"Updated Content: {updated_content}")
    
    # Validate inputs
    if not file_id:
        return {
            "is_notification": False,
            "message_to_agent": "Error: file_id is required for updating"
        }
    
    if not updated_content:
        return {
            "is_notification": False,
            "message_to_agent": "Error: updated_content cannot be empty"
        }
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    # Get the file
    try:
        file_obj = await sync_to_async(
            ProjectFile.objects.get
        )(id=file_id, project=project)
    except ProjectFile.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": f"File with ID {file_id} not found in project {project_id}"
        }
    
    # Store old content length for comparison
    old_content_length = len(file_obj.content) if file_obj.content else 0
    new_content_length = len(updated_content)
    
    # Update the file content
    try:
        # Update content using the model's method
        await sync_to_async(file_obj.save_content)(updated_content)
        await sync_to_async(file_obj.save)()
        
        logger.info(f"File '{file_obj.name}' updated successfully. Content size: {old_content_length} → {new_content_length} characters")
        
        return {
            "is_notification": True,  # Fixed: Must be True for notification to be sent
            "notification_type": "file_edited",
            "message_to_agent": f"File '{file_obj.name}' updated successfully. Content updated from {old_content_length} to {new_content_length} characters.",
            "file_id": file_id,
            "file_name": file_obj.name,
            "file_type": file_obj.file_type,
            "old_size": old_content_length,
            "new_size": new_content_length,
            "notification_marker": "__NOTIFICATION__"  # Add notification marker
        }
        
    except Exception as e:
        logger.error(f"Error updating file content: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error updating file: {str(e)}"
        }


# ============================================================================
# CODEBASE INDEXING FUNCTIONS
# ============================================================================

async def index_repository(project_id, github_url, branch='main', force_reindex=False, conversation_id=None):
    """Index a GitHub repository for context-aware development"""
    if not CODEBASE_INDEX_AVAILABLE:
        return {
            "is_notification": False,
            "message_to_agent": "Codebase indexing is not available. Please install required dependencies."
        }

    logger.info(f"Repository indexing function called for URL: {github_url}")

    error_response = validate_project_id(project_id)
    if error_response:
        return error_response

    if not github_url:
        return {
            "is_notification": False,
            "message_to_agent": "Error: github_url is required"
        }

    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    try:
        from codebase_index.github_sync import validate_github_access
        from codebase_index.models import IndexedRepository
        
        # Validate GitHub access
        valid, message, repo_info = validate_github_access(project.owner, github_url)
        if not valid:
            return {
                "is_notification": False,
                "message_to_agent": f"GitHub access validation failed: {message}"
            }
        
        # Create or get indexed repository
        indexed_repo, created = await sync_to_async(
            IndexedRepository.objects.get_or_create
        )(
            project=project,
            defaults={
                'github_url': github_url,
                'github_owner': repo_info['owner'],
                'github_repo_name': repo_info['repo'],
                'github_branch': branch,
                'status': 'pending'
            }
        )
        
        if not created and not force_reindex:
            # Update repository info if needed
            updated = False
            if indexed_repo.github_url != github_url:
                indexed_repo.github_url = github_url
                updated = True
            if indexed_repo.github_branch != branch:
                indexed_repo.github_branch = branch
                updated = True
            
            if updated:
                await sync_to_async(indexed_repo.save)()
        
        # Start indexing task
        task_id = start_repository_indexing(indexed_repo.id, force_reindex, project.owner.id)
        
        # Update repository with task ID
        indexed_repo.status = 'indexing'
        await sync_to_async(indexed_repo.save)()
        
        return {
            "is_notification": False,
            "notification_type": "repository_indexing",
            "message_to_agent": f"Repository indexing started for {repo_info['owner']}/{repo_info['repo']}. "
                               f"Task ID: {task_id}. This may take a few minutes depending on repository size."
        }
        
    except Exception as e:
        logger.error(f"Error starting repository indexing: {e}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error starting repository indexing: {str(e)}"
        }


async def get_codebase_context(project_id, feature_description, search_type='all'):
    """Get relevant codebase context for a feature or question"""
    if not CODEBASE_INDEX_AVAILABLE:
        return {
            "is_notification": False,
            "message_to_agent": "Codebase indexing is not available."
        }

    logger.info(f"Codebase context function called for: {feature_description}")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response

    if not feature_description:
        return {
            "is_notification": False,
            "message_to_agent": "Error: feature_description is required"
        }

    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    try:
        # Check if repository is indexed
        if not hasattr(project, 'indexed_repository'):
            return {
                "is_notification": False,
                "message_to_agent": "No repository has been indexed for this project yet. Please index a repository first using the index_repository function."
            }

        indexed_repo = project.indexed_repository
        if indexed_repo.status != 'completed':
            return {
                "is_notification": False,
                "message_to_agent": f"Repository indexing is not complete (status: {indexed_repo.status}). Please wait for indexing to finish."
            }

        # Get codebase context
        context_result = await sync_to_async(get_codebase_context_for_feature)(
            str(project_id), feature_description, project.owner
        )
        
        if context_result.get('error'):
            return {
                "is_notification": False,
                "message_to_agent": f"Error getting codebase context: {context_result['error']}"
            }
        
        # Format response based on search type
        if search_type == 'implementation':
            message = f"Found {len(context_result['relevant_files'])} relevant files with similar implementations:\n"
            message += context_result['context']
        elif search_type == 'patterns':
            patterns = [s for s in context_result['suggestions'] if s['type'] == 'patterns']
            message = f"Architectural patterns detected:\n"
            for pattern in patterns:
                message += f"- {pattern['description']}\n"
        elif search_type == 'files':
            message = f"Relevant files to consider:\n"
            for file_info in context_result['relevant_files'][:10]:
                message += f"- {file_info['path']} ({file_info['language']})\n"
        else:
            message = context_result['context']
        
        return {
            "is_notification": False,
            "notification_type": "codebase_context",
            "message_to_agent": f"Codebase context for '{feature_description}':\n\n{message}"
        }
        
    except Exception as e:
        logger.error(f"Error getting codebase context: {e}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error getting codebase context: {str(e)}"
        }


async def search_existing_code(project_id, functionality, chunk_types=[]):
    """Search for existing implementations of similar functionality"""
    if not CODEBASE_INDEX_AVAILABLE:
        return {
            "is_notification": False,
            "message_to_agent": "Codebase indexing is not available."
        }

    logger.info(f"Code search function called for: {functionality}")

    error_response = validate_project_id(project_id)
    if error_response:
        return error_response

    if not functionality:
        return {
            "is_notification": False,
            "message_to_agent": "Error: functionality is required"
        }

    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    try:
        # Check if repository is indexed
        if not hasattr(project, 'indexed_repository'):
            return {
                "is_notification": False,
                "message_to_agent": "No repository has been indexed for this project yet. Please index a repository first."
            }

        indexed_repo = project.indexed_repository
        if indexed_repo.status != 'completed':
            return {
                "is_notification": False,
                "message_to_agent": f"Repository indexing is not complete (status: {indexed_repo.status})."
            }

        # Search for similar implementations
        implementations = await sync_to_async(search_similar_implementations)(
            str(project_id), functionality, project.owner
        )
        
        if not implementations:
            return {
                "is_notification": False,
                "notification_type": "code_search",
                "message_to_agent": f"No existing implementations found for '{functionality}'. "
                                   "This appears to be a new feature that will need to be built from scratch."
            }
        
        # Format implementations for response
        message_parts = [f"Found {len(implementations)} similar implementations for '{functionality}':\n"]
        
        for impl in implementations[:5]:  # Show top 5
            message_parts.append(
                f"- **{impl['function_name']}** in `{impl['file_path']}` "
                f"(relevance: {impl['relevance_score']:.1%})\n"
                f"  Type: {impl['chunk_type']}, Complexity: {impl['complexity']}\n"
            )
        
        return {
            "is_notification": False,
            "notification_type": "code_search",
            "message_to_agent": ''.join(message_parts)
        }
        
    except Exception as e:
        logger.error(f"Error searching existing code: {e}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error searching existing code: {str(e)}"
        }


async def get_repository_insights(project_id):
    """Get high-level insights about the indexed repository"""
    if not CODEBASE_INDEX_AVAILABLE:
        return {
            "is_notification": False,
            "message_to_agent": "Codebase indexing is not available."
        }

    logger.info("Repository insights function called")

    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    try:
        # Check if repository is indexed
        if not hasattr(project, 'indexed_repository'):
            return {
                "is_notification": False,
                "message_to_agent": "No repository has been indexed for this project yet."
            }
        
        indexed_repo = project.indexed_repository
        if indexed_repo.status != 'completed':
            return {
                "is_notification": False,
                "message_to_agent": f"Repository indexing is not complete (status: {indexed_repo.status})"
            }
        
        # Generate insights
        insights = await sync_to_async(generate_repository_insights)(indexed_repo)
        
        if insights.get('error'):
            return {
                "is_notification": False,
                "message_to_agent": f"Error generating insights: {insights['error']}"
            }
        
        # Format insights message
        message_parts = [
            f"## Repository Insights for {indexed_repo.github_repo_name}\n",
            f"**Primary Language**: {insights.get('primary_language', 'Unknown')}\n",
            f"**Total Files Indexed**: {indexed_repo.indexed_files_count}\n",
            f"**Total Code Chunks**: {indexed_repo.total_chunks}\n",
            f"**Functions**: {insights.get('functions_count', 0)}\n",
            f"**Classes**: {insights.get('classes_count', 0)}\n",
        ]
        
        if insights.get('languages_distribution'):
            message_parts.append("**Languages Used**:\n")
            for lang, count in insights['languages_distribution'].items():
                message_parts.append(f"  - {lang}: {count} chunks\n")
        
        if insights.get('top_dependencies'):
            message_parts.append("**Top Dependencies**:\n")
            for dep, count in insights['top_dependencies'][:5]:
                message_parts.append(f"  - {dep} (used {count} times)\n")
        
        if insights.get('documentation_coverage'):
            coverage = insights['documentation_coverage']
            message_parts.append(f"**Documentation Coverage**: {coverage:.1f}%\n")
        
        return {
            "is_notification": False,
            "notification_type": "repository_insights",
            "message_to_agent": ''.join(message_parts)
        }
        
    except Exception as e:
        logger.error(f"Error getting repository insights: {e}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error getting repository insights: {str(e)}"
        }


async def get_codebase_summary(project_id):
    """
    Retrieve the comprehensive AI-generated codebase summary.

    This function retrieves the pre-generated summary that was created during
    repository indexing. The summary includes:
    - Overall purpose and architecture
    - File organization structure
    - All functions/methods mapped by file
    - Data models and structures
    - API endpoints (if detected)
    - Key dependencies and integrations

    Args:
        project_id: Project UUID

    Returns:
        dict with is_notification and message_to_agent
    """
    try:
        if not CODEBASE_INDEX_AVAILABLE:
            return {
                "is_notification": False,
                "message_to_agent": "Codebase indexing is not available in this environment"
            }

        # Get project
        project = await sync_to_async(Project.objects.select_related('indexed_repository').get)(project_id=project_id)

        if not hasattr(project, 'indexed_repository'):
            return {
                "is_notification": False,
                "message_to_agent": "No repository is linked to this project. Please link a repository first using the Codebase tab."
            }

        indexed_repo = project.indexed_repository

        if indexed_repo.status != 'completed':
            return {
                "is_notification": False,
                "message_to_agent": f"Repository indexing is not complete (status: {indexed_repo.status}). Please wait for indexing to finish."
            }

        # Check if summary exists
        if not indexed_repo.codebase_summary:
            return {
                "is_notification": False,
                "message_to_agent": "Codebase summary has not been generated yet. The summary is automatically created during indexing. Please try re-indexing the repository from the Codebase tab."
            }

        # Get summary metadata
        summary_date = indexed_repo.summary_generated_at
        date_str = summary_date.strftime('%Y-%m-%d %H:%M:%S UTC') if summary_date else 'Unknown'

        # Format final response
        final_message = f"""# Codebase Summary for {indexed_repo.github_repo_name}

{indexed_repo.codebase_summary}

---
*Summary generated on {date_str}*

**Next Steps**: Use `search_existing_code` to find specific implementations, patterns, or code details within this codebase.
"""

        return {
            "is_notification": False,
            "notification_type": "codebase_summary",
            "message_to_agent": final_message
        }

    except Exception as e:
        logger.error(f"Error retrieving codebase summary: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error retrieving codebase summary: {str(e)}"
        }


async def ask_codebase(project_id, question, intent='answer_question', include_code_snippets=True):
    """
    Ask questions about the indexed codebase or get detailed context for creating tickets.

    This function provides a Q&A interface to the codebase, allowing the AI to:
    - Answer user questions about how something works in the codebase
    - Find where specific functionality is implemented
    - Get detailed context to create specific and accurate tickets
    - Understand code patterns and architecture

    Args:
        project_id: Project UUID
        question: The question to ask about the codebase
        intent: 'answer_question', 'ticket_context', or 'find_implementation'
        include_code_snippets: Whether to include actual code snippets in the response

    Returns:
        dict with is_notification and message_to_agent containing the answer
    """
    logger.info(f"[ASK_CODEBASE] === FUNCTION CALLED ===")
    logger.info(f"[ASK_CODEBASE] project_id: {project_id}")
    logger.info(f"[ASK_CODEBASE] question: {question}")
    logger.info(f"[ASK_CODEBASE] intent: {intent}")
    logger.info(f"[ASK_CODEBASE] include_code_snippets: {include_code_snippets}")

    if not CODEBASE_INDEX_AVAILABLE:
        logger.warning(f"[ASK_CODEBASE] Codebase indexing not available")
        return {
            "is_notification": False,
            "message_to_agent": "Codebase indexing is not available."
        }

    error_response = validate_project_id(project_id)
    if error_response:
        logger.warning(f"[ASK_CODEBASE] Invalid project_id: {project_id}")
        return error_response

    if not question:
        logger.warning(f"[ASK_CODEBASE] No question provided")
        return {
            "is_notification": False,
            "message_to_agent": "Error: question is required"
        }

    project = await get_project(project_id)
    if not project:
        logger.warning(f"[ASK_CODEBASE] Project not found: {project_id}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }

    logger.info(f"[ASK_CODEBASE] Found project: {project.name}")

    try:
        # Check if repository is indexed (must use sync_to_async for ORM access)
        def get_indexed_repo():
            try:
                return project.indexed_repository
            except IndexedRepository.DoesNotExist:
                return None

        indexed_repo = await sync_to_async(get_indexed_repo)()

        if not indexed_repo:
            logger.warning(f"[ASK_CODEBASE] No indexed repository for project: {project.name}")
            return {
                "is_notification": False,
                "message_to_agent": "No repository has been indexed for this project yet. Please index a repository first using the Codebase tab."
            }

        logger.info(f"[ASK_CODEBASE] Found indexed repo: {indexed_repo.github_repo_name}, status: {indexed_repo.status}")

        if indexed_repo.status != 'completed':
            logger.warning(f"[ASK_CODEBASE] Repo indexing not complete: {indexed_repo.status}")
            return {
                "is_notification": False,
                "message_to_agent": f"Repository indexing is not complete (status: {indexed_repo.status}). Please wait for indexing to finish."
            }

        # Get codebase context for the question
        logger.info(f"[ASK_CODEBASE] Fetching codebase context...")
        context_result = await sync_to_async(get_codebase_context_for_feature)(
            str(project_id), question, project.owner
        )
        logger.info(f"[ASK_CODEBASE] Context result - error: {context_result.get('error')}, files: {len(context_result.get('relevant_files', []))}")

        # Also search for specific implementations
        logger.info(f"[ASK_CODEBASE] Searching similar implementations...")
        implementations = await sync_to_async(search_similar_implementations)(
            str(project_id), question, project.owner
        )
        logger.info(f"[ASK_CODEBASE] Found {len(implementations)} implementations")

        # Build response based on intent
        response_parts = []

        if intent == 'answer_question':
            response_parts.append(f"## Answer to: {question}\n")

            if context_result.get('error'):
                response_parts.append(f"Limited context available: {context_result.get('context', 'No context found')}\n")
            else:
                # Add context overview
                response_parts.append("### Relevant Context from Codebase\n")
                response_parts.append(context_result.get('context', 'No relevant context found.'))
                response_parts.append("\n")

                # Add suggestions if available
                if context_result.get('suggestions'):
                    response_parts.append("\n### Insights\n")
                    for suggestion in context_result['suggestions'][:3]:
                        response_parts.append(f"- **{suggestion['title']}**: {suggestion['description']}\n")

        elif intent == 'ticket_context':
            response_parts.append(f"## Ticket Context for: {question}\n")
            response_parts.append("Use this context to create accurate, specific tickets.\n\n")

            # Add relevant files that should be modified
            if context_result.get('relevant_files'):
                response_parts.append("### Files to Consider Modifying\n")
                for file_info in context_result['relevant_files'][:8]:
                    functions = ', '.join(file_info.get('functions', [])[:4])
                    response_parts.append(f"- `{file_info['path']}` ({file_info['language']})")
                    if functions:
                        response_parts.append(f" - Functions: {functions}")
                    response_parts.append("\n")
                response_parts.append("\n")

            # Add implementation suggestions
            if context_result.get('suggestions'):
                response_parts.append("### Implementation Guidance\n")
                for suggestion in context_result['suggestions']:
                    response_parts.append(f"- {suggestion['description']}\n")
                response_parts.append("\n")

            # Add similar implementations for reference
            if implementations:
                response_parts.append("### Existing Similar Implementations (for reference)\n")
                for impl in implementations[:5]:
                    response_parts.append(
                        f"- **{impl['function_name']}** in `{impl['file_path']}` "
                        f"(relevance: {impl['relevance_score']:.0%})\n"
                    )
                response_parts.append("\n")

        elif intent == 'find_implementation':
            response_parts.append(f"## Implementation Search: {question}\n")

            if implementations:
                response_parts.append(f"Found {len(implementations)} relevant implementations:\n\n")
                for impl in implementations:
                    response_parts.append(
                        f"### {impl['function_name']}\n"
                        f"- **File**: `{impl['file_path']}`\n"
                        f"- **Type**: {impl['chunk_type']}\n"
                        f"- **Complexity**: {impl['complexity']}\n"
                        f"- **Relevance**: {impl['relevance_score']:.0%}\n"
                    )
                    if include_code_snippets and impl.get('content_preview'):
                        response_parts.append(f"\n```\n{impl['content_preview']}\n```\n\n")
            else:
                response_parts.append("No existing implementations found for this functionality.\n")

            # Also add relevant files from context
            if context_result.get('relevant_files'):
                response_parts.append("\n### Other Relevant Files\n")
                for file_info in context_result['relevant_files'][:5]:
                    response_parts.append(f"- `{file_info['path']}` ({file_info['language']})\n")

        # Add code snippets section if requested and available
        if include_code_snippets and intent != 'find_implementation':
            if implementations:
                response_parts.append("\n### Code Examples\n")
                for impl in implementations[:3]:
                    if impl.get('content_preview'):
                        response_parts.append(f"**{impl['function_name']}** (`{impl['file_path']}`):\n")
                        response_parts.append(f"```\n{impl['content_preview']}\n```\n\n")

        final_response = ''.join(response_parts)
        logger.info(f"[ASK_CODEBASE] Response built successfully, length: {len(final_response)} chars")
        logger.info(f"[ASK_CODEBASE] === FUNCTION COMPLETE ===")

        return {
            "is_notification": False,
            "notification_type": "codebase_qa",
            "message_to_agent": final_response
        }

    except Exception as e:
        logger.error(f"[ASK_CODEBASE] ERROR: {e}")
        import traceback
        logger.error(f"[ASK_CODEBASE] Traceback: {traceback.format_exc()}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error querying codebase: {str(e)}"
        }


# ============================================================================
# NOTION INTEGRATION FUNCTIONS
# ============================================================================

async def connect_notion(project_id, conversation_id=None):
    """
    Test connection to Notion workspace using the user's API key

    Returns:
        Dict with connection status and user info
    """
    try:
        # Get conversation to access user
        conversation = await sync_to_async(Conversation.objects.select_related('user').get)(id=conversation_id)
        user = conversation.user

        # Get Notion API key from user's external services
        external_keys = await sync_to_async(
            lambda: ExternalServicesAPIKeys.objects.filter(user=user).first()
        )()

        if not external_keys or not external_keys.notion_api_key:
            return {
                "is_notification": False,
                "message_to_agent": "Notion API key not configured. Please add your Notion integration token in Settings > Integrations."
            }

        # Test the connection
        connector = NotionConnector(external_keys.notion_api_key)
        success, result = await sync_to_async(connector.test_connection)()

        if success:
            user_name = result.get('name', 'Unknown')
            user_type = result.get('type', 'user')

            return {
                "is_notification": False,
                "notification_type": "notion_connection",
                "message_to_agent": f"✅ Successfully connected to Notion!\n\nUser: {user_name}\nType: {user_type}\n\nYou can now search and retrieve Notion pages and databases."
            }
        else:
            return {
                "is_notification": False,
                "message_to_agent": f"Failed to connect to Notion: {result}\n\nPlease check your API key in Settings > Integrations."
            }

    except Conversation.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": "Conversation not found"
        }
    except Exception as e:
        logger.error(f"Error connecting to Notion: {e}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error connecting to Notion: {str(e)}"
        }


async def search_notion(project_id, conversation_id, query="", page_size=10):
    """
    Search for pages and databases in Notion workspace

    Args:
        project_id: Project ID
        conversation_id: Conversation ID to get user
        query: Search query string (empty returns all accessible pages)
        page_size: Number of results to return

    Returns:
        Dict with search results
    """
    try:
        # Get conversation to access user
        conversation = await sync_to_async(Conversation.objects.select_related('user').get)(id=conversation_id)
        user = conversation.user

        # Get Notion API key
        external_keys = await sync_to_async(
            lambda: ExternalServicesAPIKeys.objects.filter(user=user).first()
        )()

        if not external_keys or not external_keys.notion_api_key:
            return {
                "is_notification": False,
                "message_to_agent": "Notion API key not configured. Please add your Notion integration token in Settings > Integrations."
            }

        # Perform search
        connector = NotionConnector(external_keys.notion_api_key)
        success, results = await sync_to_async(connector.search_pages)(query, page_size)

        if success:
            if not results:
                search_desc = f"query: '{query}'" if query else "your workspace"
                return {
                    "is_notification": False,
                    "notification_type": "notion_search",
                    "message_to_agent": f"No results found for {search_desc}. Make sure pages are shared with your integration in Notion."
                }

            # Format results for display
            if query:
                results_text = f"# Notion Search Results for '{query}'\n\nFound {len(results)} page(s):\n\n"
            else:
                results_text = f"# All Accessible Notion Pages\n\nFound {len(results)} page(s):\n\n"

            for i, page in enumerate(results, 1):
                results_text += f"{i}. **{page['title']}**\n"
                results_text += f"   - ID: `{page['id']}`\n"
                results_text += f"   - URL: {page['url']}\n"
                results_text += f"   - Last edited: {page['last_edited_time']}\n\n"

            results_text += "\n**Next Steps**: Use `get_notion_page` with a page ID to retrieve full content."

            return {
                "is_notification": False,
                "notification_type": "notion_search",
                "message_to_agent": results_text
            }
        else:
            return {
                "is_notification": False,
                "message_to_agent": f"Search failed: {results}"
            }

    except Exception as e:
        logger.error(f"Error searching Notion: {e}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error searching Notion: {str(e)}"
        }


async def get_notion_page(project_id, conversation_id, page_id):
    """
    Retrieve full content of a Notion page

    Args:
        project_id: Project ID
        conversation_id: Conversation ID to get user
        page_id: Notion page ID

    Returns:
        Dict with page content
    """
    try:
        # Get conversation to access user
        conversation = await sync_to_async(Conversation.objects.select_related('user').get)(id=conversation_id)
        user = conversation.user

        # Get Notion API key
        external_keys = await sync_to_async(
            lambda: ExternalServicesAPIKeys.objects.filter(user=user).first()
        )()

        if not external_keys or not external_keys.notion_api_key:
            return {
                "is_notification": False,
                "message_to_agent": "Notion API key not configured. Please add your Notion integration token in Settings > Integrations."
            }

        # Get page content
        connector = NotionConnector(external_keys.notion_api_key)
        success, page_data = await sync_to_async(connector.get_page_content)(page_id)

        if success:
            # Format page content for display
            content_text = f"# {page_data['title']}\n\n"
            content_text += f"**URL**: {page_data['url']}\n"
            content_text += f"**Last edited**: {page_data['last_edited_time']}\n\n"

            if page_data.get('properties'):
                content_text += "## Properties\n"
                for key, value in page_data['properties'].items():
                    content_text += f"- **{key}**: {value}\n"
                content_text += "\n"

            if page_data.get('content'):
                content_text += "## Content\n\n"
                content_text += page_data['content']

            return {
                "is_notification": False,
                "notification_type": "notion_page",
                "message_to_agent": content_text
            }
        else:
            return {
                "is_notification": False,
                "message_to_agent": f"Failed to retrieve page: {page_data}"
            }

    except Exception as e:
        logger.error(f"Error retrieving Notion page: {e}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error retrieving Notion page: {str(e)}"
        }


async def list_notion_databases(project_id, conversation_id, page_size=10):
    """
    List all accessible databases in Notion workspace

    Args:
        project_id: Project ID
        conversation_id: Conversation ID to get user
        page_size: Number of results to return

    Returns:
        Dict with database list
    """
    try:
        # Get conversation to access user
        conversation = await sync_to_async(Conversation.objects.select_related('user').get)(id=conversation_id)
        user = conversation.user

        # Get Notion API key
        external_keys = await sync_to_async(
            lambda: ExternalServicesAPIKeys.objects.filter(user=user).first()
        )()

        if not external_keys or not external_keys.notion_api_key:
            return {
                "is_notification": False,
                "message_to_agent": "Notion API key not configured. Please add your Notion integration token in Settings > Integrations."
            }

        # List databases
        connector = NotionConnector(external_keys.notion_api_key)
        success, databases = await sync_to_async(connector.list_databases)(page_size)

        if success:
            if not databases:
                return {
                    "is_notification": False,
                    "notification_type": "notion_databases",
                    "message_to_agent": "No databases found in your Notion workspace."
                }

            # Format database list
            db_text = f"# Notion Databases\n\nFound {len(databases)} database(s):\n\n"
            for i, db in enumerate(databases, 1):
                db_text += f"{i}. **{db['title']}**\n"
                db_text += f"   - ID: `{db['id']}`\n"
                db_text += f"   - URL: {db['url']}\n"
                db_text += f"   - Properties: {', '.join(db['properties'])}\n\n"

            db_text += "\n**Next Steps**: Use `query_notion_database` with a database ID to retrieve entries."

            return {
                "is_notification": False,
                "notification_type": "notion_databases",
                "message_to_agent": db_text
            }
        else:
            return {
                "is_notification": False,
                "message_to_agent": f"Failed to list databases: {databases}"
            }

    except Exception as e:
        logger.error(f"Error listing Notion databases: {e}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error listing Notion databases: {str(e)}"
        }


async def query_notion_database(project_id, conversation_id, database_id, page_size=10):
    """
    Query a specific Notion database and retrieve entries

    Args:
        project_id: Project ID
        conversation_id: Conversation ID to get user
        database_id: Notion database ID
        page_size: Number of entries to return

    Returns:
        Dict with database entries
    """
    try:
        # Get conversation to access user
        conversation = await sync_to_async(Conversation.objects.select_related('user').get)(id=conversation_id)
        user = conversation.user

        # Get Notion API key
        external_keys = await sync_to_async(
            lambda: ExternalServicesAPIKeys.objects.filter(user=user).first()
        )()

        if not external_keys or not external_keys.notion_api_key:
            return {
                "is_notification": False,
                "message_to_agent": "Notion API key not configured. Please add your Notion integration token in Settings > Integrations."
            }

        # Query database
        connector = NotionConnector(external_keys.notion_api_key)
        success, entries = await sync_to_async(connector.query_database)(database_id, page_size)

        if success:
            if not entries:
                return {
                    "is_notification": False,
                    "notification_type": "notion_database_query",
                    "message_to_agent": "No entries found in this database."
                }

            # Format entries
            entries_text = f"# Database Entries\n\nFound {len(entries)} entry/entries:\n\n"
            for i, entry in enumerate(entries, 1):
                entries_text += f"{i}. **{entry['title']}**\n"
                entries_text += f"   - ID: `{entry['id']}`\n"
                entries_text += f"   - URL: {entry['url']}\n"

                if entry.get('properties'):
                    entries_text += "   - Properties:\n"
                    for key, value in entry['properties'].items():
                        entries_text += f"     - {key}: {value}\n"

                entries_text += "\n"

            return {
                "is_notification": False,
                "notification_type": "notion_database_query",
                "message_to_agent": entries_text
            }
        else:
            return {
                "is_notification": False,
                "message_to_agent": f"Failed to query database: {entries}"
            }

    except Exception as e:
        logger.error(f"Error querying Notion database: {e}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error querying Notion database: {str(e)}"
        }


# ============================================================================
# LINEAR INTEGRATION FUNCTIONS
# ============================================================================

async def get_linear_issues(project_id, conversation_id, limit=50, team_id=None):
    """
    Fetch all Linear issues/tickets accessible to the user

    Args:
        project_id: Project ID
        conversation_id: Conversation ID to get user
        limit: Maximum number of issues to return
        team_id: Optional team ID to filter by team

    Returns:
        Dict with Linear issues
    """
    try:
        # Get conversation to access user
        conversation = await sync_to_async(Conversation.objects.select_related('user').get)(id=conversation_id)
        user = conversation.user

        # Get Linear API key
        external_keys = await sync_to_async(
            lambda: ExternalServicesAPIKeys.objects.filter(user=user).first()
        )()

        if not external_keys or not external_keys.linear_api_key:
            return {
                "is_notification": False,
                "message_to_agent": "Linear API key not configured. Please add your Linear API key in Settings > Integrations."
            }

        # Fetch issues from Linear
        linear_service = LinearSyncService(external_keys.linear_api_key)
        success, result = await sync_to_async(linear_service.get_all_issues)(limit, team_id)

        if success:
            issues = result
            if not issues:
                return {
                    "is_notification": False,
                    "notification_type": "linear_issues",
                    "message_to_agent": "No Linear issues found. This could mean you have no issues or the API key doesn't have access to any teams."
                }

            # Format issues for display
            issues_text = f"# Linear Issues\n\nFound {len(issues)} issue(s):\n\n"

            for issue in issues:
                # Format issue details
                identifier = issue.get('identifier', 'N/A')
                title = issue.get('title', 'Untitled')
                state = issue.get('state', {}).get('name', 'Unknown')
                priority = issue.get('priority', 0)
                url = issue.get('url', '')

                # Priority mapping
                priority_labels = {0: "None", 1: "Urgent", 2: "High", 3: "Medium", 4: "Low"}
                priority_label = priority_labels.get(priority, "Unknown")

                # Team and project info
                team = issue.get('team', {})
                team_name = team.get('name', 'No team') if team else 'No team'

                project = issue.get('project', {})
                project_name = project.get('name', 'No project') if project else 'No project'

                # Assignee
                assignee = issue.get('assignee', {})
                assignee_name = assignee.get('name', 'Unassigned') if assignee else 'Unassigned'

                # Full description (not preview)
                description = issue.get('description', '')
                if description:
                    # Limit to 500 chars for list view, can get full details with get_linear_issue_details
                    desc_text = (description[:500] + '...') if len(description) > 500 else description
                else:
                    desc_text = 'No description'

                # Build issue entry
                issues_text += f"### [{identifier}] {title}\n"
                issues_text += f"- **Status:** {state}\n"
                issues_text += f"- **Priority:** {priority_label}\n"
                issues_text += f"- **Team:** {team_name}\n"
                issues_text += f"- **Project:** {project_name}\n"
                issues_text += f"- **Assignee:** {assignee_name}\n"
                issues_text += f"- **Description:** {desc_text}\n"
                issues_text += f"- **URL:** {url}\n\n"

            issues_text += f"\n**Total:** {len(issues)} issue(s)"
            if limit < 250:
                issues_text += f" (limited to {limit}, use higher limit to see more)"

            return {
                "is_notification": False,
                "notification_type": "linear_issues",
                "message_to_agent": issues_text
            }
        else:
            return {
                "is_notification": False,
                "message_to_agent": f"Failed to fetch Linear issues: {result}"
            }

    except Exception as e:
        logger.error(f"Error fetching Linear issues: {e}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error fetching Linear issues: {str(e)}"
        }


async def get_linear_issue_details(project_id, conversation_id, issue_id):
    """
    Get detailed information for a specific Linear issue

    Args:
        project_id: Project ID
        conversation_id: Conversation ID to get user
        issue_id: Linear issue ID or identifier (e.g., 'PED-8')

    Returns:
        Dict with detailed issue information
    """
    try:
        # Get conversation to access user
        conversation = await sync_to_async(Conversation.objects.select_related('user').get)(id=conversation_id)
        user = conversation.user

        # Get Linear API key
        external_keys = await sync_to_async(
            lambda: ExternalServicesAPIKeys.objects.filter(user=user).first()
        )()

        if not external_keys or not external_keys.linear_api_key:
            return {
                "is_notification": False,
                "message_to_agent": "Linear API key not configured. Please add your Linear API key in Settings > Integrations."
            }

        # Fetch issue details from Linear
        linear_service = LinearSyncService(external_keys.linear_api_key)
        success, result = await sync_to_async(linear_service.get_issue_by_identifier)(issue_id)

        if success:
            issue = result

            # Format detailed issue information
            identifier = issue.get('identifier', 'N/A')
            title = issue.get('title', 'Untitled')
            description = issue.get('description', 'No description provided')

            # State and priority
            state = issue.get('state', {}).get('name', 'Unknown')
            state_type = issue.get('state', {}).get('type', 'unknown')
            priority = issue.get('priority', 0)
            priority_label = issue.get('priorityLabel', 'None')
            estimate = issue.get('estimate', 'Not estimated')

            # People
            assignee = issue.get('assignee', {})
            assignee_name = assignee.get('name', 'Unassigned') if assignee else 'Unassigned'
            assignee_email = assignee.get('email', '') if assignee else ''

            creator = issue.get('creator', {})
            creator_name = creator.get('name', 'Unknown') if creator else 'Unknown'

            # Team and project
            team = issue.get('team', {})
            team_name = team.get('name', 'No team') if team else 'No team'

            project = issue.get('project', {})
            project_name = project.get('name', 'No project') if project else 'No project'

            # Labels
            labels = issue.get('labels', {}).get('nodes', [])
            label_names = [label.get('name') for label in labels] if labels else []

            # Comments
            comments = issue.get('comments', {}).get('nodes', [])
            comments_count = len(comments) if comments else 0

            # Relationships
            parent = issue.get('parent')
            children = issue.get('children', {}).get('nodes', [])

            # Dates
            created_at = issue.get('createdAt', '')
            updated_at = issue.get('updatedAt', '')
            completed_at = issue.get('completedAt', '')
            due_date = issue.get('dueDate', '')

            url = issue.get('url', '')

            # Build detailed response
            details_text = f"# Linear Issue: [{identifier}] {title}\n\n"

            details_text += f"## Overview\n"
            details_text += f"- **Status:** {state} ({state_type})\n"
            details_text += f"- **Priority:** {priority_label}\n"
            details_text += f"- **Estimate:** {estimate}\n"
            details_text += f"- **Team:** {team_name}\n"
            details_text += f"- **Project:** {project_name}\n"
            details_text += f"- **URL:** {url}\n\n"

            details_text += f"## People\n"
            details_text += f"- **Assignee:** {assignee_name}"
            if assignee_email:
                details_text += f" ({assignee_email})"
            details_text += f"\n"
            details_text += f"- **Created by:** {creator_name}\n\n"

            if label_names:
                details_text += f"## Labels\n"
                details_text += ", ".join([f"`{label}`" for label in label_names]) + "\n\n"

            details_text += f"## Description\n{description}\n\n"

            if parent:
                details_text += f"## Parent Issue\n"
                details_text += f"[{parent.get('identifier')}] {parent.get('title')}\n\n"

            if children:
                details_text += f"## Sub-issues ({len(children)})\n"
                for child in children:
                    details_text += f"- [{child.get('identifier')}] {child.get('title')}\n"
                details_text += "\n"

            if comments:
                details_text += f"## Comments ({comments_count})\n"
                for i, comment in enumerate(comments[:5], 1):  # Show first 5 comments
                    user_name = comment.get('user', {}).get('name', 'Unknown')
                    comment_body = comment.get('body', '')
                    created = comment.get('createdAt', '')
                    details_text += f"\n**{user_name}** ({created}):\n"
                    # Limit comment length
                    if len(comment_body) > 200:
                        details_text += f"{comment_body[:200]}...\n"
                    else:
                        details_text += f"{comment_body}\n"

                if comments_count > 5:
                    details_text += f"\n_...and {comments_count - 5} more comments_\n"
                details_text += "\n"

            details_text += f"## Timeline\n"
            details_text += f"- **Created:** {created_at}\n"
            details_text += f"- **Last updated:** {updated_at}\n"
            if completed_at:
                details_text += f"- **Completed:** {completed_at}\n"
            if due_date:
                details_text += f"- **Due date:** {due_date}\n"

            return {
                "is_notification": False,
                "notification_type": "linear_issue_details",
                "message_to_agent": details_text
            }
        else:
            return {
                "is_notification": False,
                "message_to_agent": f"Failed to fetch Linear issue details: {result}"
            }

    except Exception as e:
        logger.error(f"Error fetching Linear issue details: {e}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error fetching Linear issue details: {str(e)}"
        }


# ============================================================================
# TECHNOLOGY SPECS LOOKUP
# ============================================================================

async def lookup_technology_specs(category: str = 'all'):
    """
    Look up technology specifications from the JSON configuration file.

    Args:
        category: The technology category to look up (e.g., 'payments', 'file_storage', 'database') or 'all'

    Returns:
        dict: Technology specifications with tech, provider, description, documentation, and why
    """
    logger.info(f"Technology specs lookup called - category: {category}")

    try:
        specs_file_path = Path(__file__).parent / 'technology_specs.json'

        if not specs_file_path.exists():
            return {
                "is_notification": False,
                "message_to_agent": "Error: technology_specs.json not found in factory directory."
            }

        with open(specs_file_path, 'r') as f:
            tech_specs = json.load(f)

        # Return all specs
        if category == 'all':
            return {
                "is_notification": False,
                "message_to_agent": f"Technology specifications: {json.dumps(tech_specs, indent=2)}"
            }

        # Return specific category
        if category in tech_specs:
            return {
                "is_notification": False,
                "message_to_agent": f"Technology spec for '{category}': {json.dumps(tech_specs[category], indent=2)}. \nPlease web search and collect more information"
            }

        # Category not found
        available = list(tech_specs.keys())
        return {
            "is_notification": False,
            "message_to_agent": f"Category '{category}' not found. Available: {', '.join(available)}"
        }

    except Exception as e:
        logger.error(f"Error looking up technology specs: {e}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error: {str(e)}"
        }


async def generate_design_preview(function_args, project_id, conversation_id=None):
    """
    Generate a design preview for a feature with multiple pages/screens.
    Stores data in ProjectDesignFeature model with proper JSONFields.

    Args:
        function_args: Dictionary containing:
            - feature_name: Name of the feature
            - feature_description: Brief description of the feature
            - explainer: Detailed explanation of the feature
            - css_style: Complete CSS stylesheet
            - pages: Array of page objects with connections
            - feature_connections: Array of cross-feature navigation links
            - entry_page_id: The entry point page for this feature
            - canvas_position: Optional position on the design canvas
        project_id: The project ID
        conversation_id: Optional conversation ID

    Returns:
        Dictionary with notification data and message for the agent
    """
    import uuid

    logger.info(f"[generate_design_preview] Called for project: {project_id}, conversation: {conversation_id}")
    logger.info(f"[generate_design_preview] Function args keys: {list(function_args.keys())}")

    # Validate project
    error_response = validate_project_id(project_id)
    if error_response:
        logger.error(f"[generate_design_preview] Project validation failed: {error_response}")
        return error_response

    # Validate required arguments
    required_fields = ['feature_name', 'feature_description', 'explainer', 'css_style', 'pages', 'entry_page_id']
    validation_error = validate_function_args(function_args, required_fields)
    if validation_error:
        logger.error(f"[generate_design_preview] Argument validation failed: {validation_error}")
        return validation_error

    platform = function_args.get('platform', 'web')  # Default to 'web' for backwards compatibility
    feature_name = function_args.get('feature_name')
    feature_description = function_args.get('feature_description')
    explainer = function_args.get('explainer')
    css_style = function_args.get('css_style')
    common_elements = function_args.get('common_elements', [])
    pages = function_args.get('pages', [])
    feature_connections = function_args.get('feature_connections', [])
    entry_page_id = function_args.get('entry_page_id')
    canvas_position = function_args.get('canvas_position', {'x': 0, 'y': 0})

    logger.info(f"[generate_design_preview] feature_name={feature_name}, platform={platform}, pages_count={len(pages)}, common_elements_count={len(common_elements)}")

    # Validate pages structure
    if not isinstance(pages, list) or len(pages) == 0:
        return {
            "is_notification": False,
            "message_to_agent": "Error: pages must be a non-empty array of page objects"
        }

    # Helper to sanitize null characters that PostgreSQL cannot store
    def sanitize_text(text):
        if isinstance(text, str):
            return text.replace('\x00', '').replace('\u0000', '')
        return text

    try:
        project = await sync_to_async(Project.objects.get)(project_id=project_id)

        # Get conversation if provided
        conversation = None
        if conversation_id:
            try:
                conversation = await sync_to_async(Conversation.objects.get)(id=conversation_id)
            except Conversation.DoesNotExist:
                logger.warning(f"Conversation {conversation_id} not found, proceeding without linking")

        # Sanitize text fields
        feature_name = sanitize_text(feature_name)
        feature_description = sanitize_text(feature_description)
        explainer = sanitize_text(explainer)
        css_style = sanitize_text(css_style)

        # Build pages array for JSONField with sanitized content
        pages_data = [
            {
                "page_id": page.get('page_id'),
                "page_name": sanitize_text(page.get('page_name', '')),
                "page_type": page.get('page_type', 'screen'),
                "html_content": sanitize_text(page.get('html_content', '')),
                "include_common_elements": page.get('include_common_elements', True),
                "navigates_to": page.get('navigates_to', [])
            }
            for page in pages
        ]

        # Build common_elements array for JSONField with sanitized content
        common_elements_data = [
            {
                "element_id": elem.get('element_id'),
                "element_type": elem.get('element_type', 'header'),
                "element_name": sanitize_text(elem.get('element_name', '')),
                "html_content": sanitize_text(elem.get('html_content', '')),
                "position": elem.get('position', 'top'),
                "applies_to": elem.get('applies_to', ['all']),
                "exclude_from": elem.get('exclude_from', [])
            }
            for elem in common_elements
        ] if common_elements else []

        # Create or update the design feature (identified by project + feature_name)
        design_feature, created = await sync_to_async(ProjectDesignFeature.objects.update_or_create)(
            project=project,
            feature_name=feature_name,
            defaults={
                'conversation': conversation,
                'platform': platform,
                'feature_description': feature_description,
                'explainer': explainer,
                'css_style': css_style,
                'common_elements': common_elements_data,
                'pages': pages_data,
                'entry_page_id': entry_page_id,
                'feature_connections': feature_connections,
                'canvas_position': canvas_position
            }
        )
        logger.info(f"Saved design feature to database: id={design_feature.id}, feature_name={feature_name}")

        # Auto-add screens to the current/default canvas
        try:
            from projects.models import DesignCanvas
            from factory.tool_execution import get_current_canvas_id

            # Get canvas_id from context (set by consumer from user's selection)
            canvas_id = get_current_canvas_id()
            logger.info(f"[generate_design_preview] Canvas ID from context: {canvas_id}")

            # If no canvas_id from context, try to get from conversation
            if not canvas_id and conversation:
                canvas_id = await sync_to_async(lambda: conversation.design_canvas_id)()
                logger.info(f"[generate_design_preview] Canvas ID from conversation: {canvas_id}")

            if canvas_id:
                # Use the specifically selected canvas
                canvas = await sync_to_async(
                    lambda: DesignCanvas.objects.filter(id=canvas_id, project=project).first()
                )()
                logger.info(f"[generate_design_preview] Using specified canvas: {canvas.id if canvas else 'None'}")
            else:
                # Fallback to most recently updated canvas or default canvas
                canvas = await sync_to_async(
                    lambda: DesignCanvas.objects.filter(project=project).order_by('-is_default', '-updated_at').first()
                )()
                logger.info(f"[generate_design_preview] Using fallback canvas: {canvas.id if canvas else 'None'}")

            if canvas:
                # Add each page to the canvas positions
                positions = canvas.feature_positions or {}
                logger.info(f"[generate_design_preview] Existing positions count: {len(positions)}")
                y_offset = 50
                for idx, page in enumerate(pages_data):
                    page_key = f"{design_feature.id}_{page['page_id']}"
                    if page_key not in positions:
                        # Calculate position - stack new screens vertically
                        col = idx % 4
                        row = idx // 4
                        positions[page_key] = {
                            'x': 50 + col * 320,
                            'y': y_offset + row * 280
                        }
                        logger.info(f"[generate_design_preview] Added position for {page_key}")

                canvas.feature_positions = positions
                await sync_to_async(canvas.save)()
                logger.info(f"[generate_design_preview] Saved canvas with {len(positions)} positions to canvas {canvas.id}")
            else:
                logger.warning(f"[generate_design_preview] No canvas found for project {project_id}")
        except Exception as canvas_error:
            logger.error(f"[generate_design_preview] Could not auto-add screens to canvas: {canvas_error}", exc_info=True)

        # Build success message
        pages_summary = ', '.join([p.get('page_name', p.get('page_id')) for p in pages])
        connections_count = len(feature_connections)
        internal_nav_count = sum(len(p.get('navigates_to', [])) for p in pages)
        common_elements_count = len(common_elements_data)

        success_message = (
            f"Design preview generated successfully for feature '{feature_name}'!\n\n"
            f"**Feature Details:**\n"
            f"- Entry Point: {entry_page_id}\n"
            f"- Pages: {pages_summary}\n"
            f"- Common Elements: {common_elements_count} (header, footer, sidebar, etc.)\n"
            f"- Internal navigations: {internal_nav_count}\n"
            f"- Cross-feature connections: {connections_count}\n\n"
            f"**Saved to Database:**\n"
            f"- Record ID: {design_feature.id}"
        )

        return {
            "is_notification": True,
            "notification_type": "design_preview",
            "message_to_agent": success_message,
            "data": {
                "feature_name": feature_name,
                "record_id": design_feature.id,
                "conversation_id": conversation_id
            }
        }

    except Project.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} not found."
        }
    except Exception as e:
        logger.error(f"Error generating design preview: {e}", exc_info=True)
        return {
            "is_notification": False,
            "message_to_agent": f"Error generating design preview: {str(e)}"
        }
