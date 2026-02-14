"""
Mags SDK Client

Compatibility layer around the official `magpie-mags` Python package.
This module keeps the existing function-level API used across the codebase.
"""

import base64
import io
import json
import logging
import os
import time
import re
import uuid
from typing import Any, Callable, Optional

import paramiko

try:
    from mags import Mags  # type: ignore
except Exception:  # pragma: no cover - validated at runtime
    Mags = None

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

MAGS_BASE_URL = os.getenv("MAGS_API_URL", "https://api.magpiecloud.com")
# Legacy alias retained for backward compatibility with existing deployments.
MAGS_API_KEY = os.getenv("MAGS_API_KEY", "")

MAGS_WORKING_DIR = "/root"
MAGS_PROJECT_DIR = "/root/project"

MAGS_NODE_VERSION = "20.18.0"
MAGS_NODE_DISTRO = "linux-x64"

MAGS_NODE_ENV_LINES = [
    "export PATH=/root/node/current/bin:$PATH",
    "export npm_config_prefix=/root/.npm-global",
    "export npm_config_cache=/root/.npm-cache",
    "export NODE_ENV=development",
    "mkdir -p /root/.npm-global/lib /root/.npm-cache",
]

# Fat base script for claude-auth workspaces.
# Installs system packages, Node.js, Claude CLI, and creates non-root user.
CLAUDE_AUTH_SETUP_SCRIPT = f"""#!/bin/sh
set -eux

# Install system packages
apk update && apk add --no-cache curl xz git expect bash openssh-client

# Install Node.js
cd /root && mkdir -p node && cd node
if [ ! -d node-v{MAGS_NODE_VERSION}-{MAGS_NODE_DISTRO} ]; then
    curl -fsSL https://nodejs.org/dist/v{MAGS_NODE_VERSION}/node-v{MAGS_NODE_VERSION}-{MAGS_NODE_DISTRO}.tar.xz -o node.tar.xz
    tar -xf node.tar.xz && rm node.tar.xz
    ln -sfn node-v{MAGS_NODE_VERSION}-{MAGS_NODE_DISTRO} current
fi
export PATH=/root/node/current/bin:$PATH
mkdir -p /root/.npm-global /root/.npm-cache
npm config set prefix /root/.npm-global
npm config set cache /root/.npm-cache

# Install Claude CLI
npm install -g @anthropic-ai/claude-code

# Create non-root user for Claude --dangerously-skip-permissions
adduser -D -h /home/claudeuser -s /bin/bash claudeuser 2>/dev/null || true

echo "CLAUDE_AUTH_SETUP_COMPLETE"

# Keep the job running so SSH stays open
while :; do sleep 3600 & wait $!; done
"""

# Lightweight script for workspaces that inherit from claude-auth
MAGS_KEEPALIVE_SCRIPT = """#!/bin/sh
echo "WORKSPACE_READY"
while :; do sleep 3600 & wait $!; done
"""

# Preview workspace bootstrap (standalone, not forked from claude-auth)
PREVIEW_SETUP_SCRIPT = f"""#!/bin/sh
set -eux

# Install system packages
apk update && apk add --no-cache curl xz git bash

# Install Node.js
cd /root && mkdir -p node && cd node
if [ ! -d node-v{MAGS_NODE_VERSION}-{MAGS_NODE_DISTRO} ]; then
    curl -fsSL https://nodejs.org/dist/v{MAGS_NODE_VERSION}/node-v{MAGS_NODE_VERSION}-{MAGS_NODE_DISTRO}.tar.xz -o node.tar.xz
    tar -xf node.tar.xz && rm node.tar.xz
    ln -sfn node-v{MAGS_NODE_VERSION}-{MAGS_NODE_DISTRO} current
fi
export PATH=/root/node/current/bin:$PATH
mkdir -p /root/.npm-global /root/.npm-cache
npm config set prefix /root/.npm-global
npm config set cache /root/.npm-cache

echo "PREVIEW_SETUP_COMPLETE"

while :; do sleep 3600 & wait $!; done
"""


# ============================================================================
# Exceptions
# ============================================================================

class MagsAPIError(Exception):
    """Exception raised for Mags API errors."""

    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(message)


# ============================================================================
# SDK Helpers
# ============================================================================

_mags_client = None
_mags_client_config = None


def _get_api_token() -> str:
    """Resolve token from modern and legacy environment variable names."""
    token = (
        os.getenv("MAGS_TOKEN")
    )
    if not token:
        raise MagsAPIError("MAGS_TOKEN is not configured")
    return token


def _get_mags_client(timeout: int = 60):
    """Return a cached Mags SDK client instance."""
    global _mags_client, _mags_client_config

    if Mags is None:
        raise MagsAPIError(
            "magpie-mags is not installed. Install with: pip install magpie-mags"
        )

    token = _get_api_token()
    api_url = os.getenv("MAGS_API_URL", MAGS_BASE_URL)
    cfg = (token, api_url)

    if _mags_client is not None and _mags_client_config == cfg:
        return _mags_client

    try:
        _mags_client = Mags(api_token=token, api_url=api_url, timeout=timeout)
        _mags_client_config = cfg
        return _mags_client
    except TypeError:
        _mags_client = Mags(api_token=token, api_url=api_url)
        _mags_client_config = cfg
        return _mags_client
    except Exception as e:
        status_code = getattr(e, "status_code", None)
        raise MagsAPIError(f"Failed to initialize Mags SDK client: {e}", status_code=status_code)


def _normalize_job_response(resp: Any) -> dict:
    """Normalize SDK responses to include both request_id and id when possible."""
    if resp is None:
        return {}
    if isinstance(resp, dict):
        out = dict(resp)
    else:
        out = {"data": resp}

    req_id = out.get("request_id") or out.get("id")
    if req_id:
        out.setdefault("request_id", req_id)
        out.setdefault("id", req_id)
    return out


def _raise_mags_error(action: str, error: Exception) -> None:
    """Convert SDK exceptions into MagsAPIError with optional status code/body."""
    status_code = getattr(error, "status_code", None)
    response_body = getattr(error, "response_body", None) or getattr(error, "response_text", None)
    raise MagsAPIError(f"Mags SDK failed to {action}: {error}", status_code=status_code, response_body=response_body)


# ============================================================================
# Job Lifecycle
# ============================================================================

def submit_job(
    script: str,
    workspace_id: str = None,
    base_workspace_id: str = None,
    persistent: bool = True,
    startup_command: str = None,
    environment: dict = None,
) -> dict:
    """
    Submit a new Mags job.

    Args:
        script: Shell script to run in the VM
        workspace_id: Workspace overlay name (for persistence)
        base_workspace_id: Base workspace to fork from
        persistent: Whether workspace state persists
        startup_command: Optional startup command override
        environment: Optional environment variables dict

    Returns:
        Job response dict with request_id, status, etc.
    """
    client = _get_mags_client()
    kwargs = {}
    if workspace_id:
        kwargs["workspace_id"] = workspace_id
    if base_workspace_id:
        kwargs["base_workspace_id"] = base_workspace_id
    if persistent is not None:
        kwargs["persistent"] = persistent
    if startup_command:
        kwargs["startup_command"] = startup_command
    if environment:
        kwargs["environment"] = environment

    logger.info("[MAGS] Submitting job via SDK: workspace_id=%s, base=%s, persistent=%s", workspace_id, base_workspace_id, persistent)
    try:
        resp = client.run(script, **kwargs)
        return _normalize_job_response(resp)
    except Exception as e:
        _raise_mags_error("submit job", e)


def get_job_status(job_id: str) -> dict:
    """Get the current status of a Mags job."""
    client = _get_mags_client()
    try:
        resp = client.status(job_id)
        return _normalize_job_response(resp)
    except Exception as e:
        _raise_mags_error(f"get status for job {job_id}", e)


def get_job_logs(job_id: str) -> dict:
    """Get logs for a Mags job."""
    client = _get_mags_client()
    try:
        resp = client.logs(job_id)
        return _normalize_job_response(resp)
    except Exception as e:
        _raise_mags_error(f"get logs for job {job_id}", e)


def list_jobs() -> dict:
    """
    List Mags jobs if exposed by installed SDK version.

    Returns:
        Dict with jobs list under "jobs" key when available.
    """
    client = _get_mags_client()
    for method_name in ("list_jobs", "jobs", "job_list", "list"):
        method = getattr(client, method_name, None)
        if callable(method):
            try:
                resp = method()
                if isinstance(resp, list):
                    return {"jobs": [_normalize_job_response(job) for job in resp]}
                if isinstance(resp, dict):
                    jobs = resp.get("jobs") or resp.get("data")
                    if isinstance(jobs, list):
                        resp = dict(resp)
                        resp["jobs"] = [_normalize_job_response(job) for job in jobs]
                    return resp
                return {"jobs": []}
            except TypeError:
                continue
            except Exception as e:
                _raise_mags_error("list jobs", e)
    raise MagsAPIError("Installed magpie-mags SDK does not expose a job listing method")


def update_job(job_id: str, data: dict) -> dict:
    """Update a Mags job if exposed by installed SDK version."""
    client = _get_mags_client()
    for method_name in ("update_job", "update", "job_update"):
        method = getattr(client, method_name, None)
        if callable(method):
            try:
                resp = method(job_id, data)
                return _normalize_job_response(resp)
            except TypeError:
                try:
                    resp = method(job_id=job_id, data=data)
                    return _normalize_job_response(resp)
                except TypeError:
                    continue
            except Exception as e:
                _raise_mags_error(f"update job {job_id}", e)
    raise MagsAPIError("Installed magpie-mags SDK does not expose a job update method")


def force_sync_workspace(workspace_ref: str) -> dict:
    """
    Force an immediate workspace sync to persistent storage (S3).

    This is useful after Claude authentication so credentials are flushed
    immediately instead of waiting for background sync.

    Args:
        workspace_ref: Workspace overlay ID (preferred) or job/request ID.
    """
    client = _get_mags_client()

    # Try common SDK method names to stay compatible across versions.
    for method_name in ("sync", "sync_job", "workspace_sync"):
        method = getattr(client, method_name, None)
        if callable(method):
            try:
                resp = method(workspace_ref)
                logger.info("[MAGS] Force sync requested for ref %s via %s", workspace_ref, method_name)
                return _normalize_job_response(resp)
            except TypeError:
                try:
                    resp = method(workspace_id=workspace_ref)
                    logger.info("[MAGS] Force sync requested for workspace %s via %s", workspace_ref, method_name)
                    return _normalize_job_response(resp)
                except TypeError:
                    try:
                        resp = method(request_id=workspace_ref)
                        logger.info("[MAGS] Force sync requested for request %s via %s", workspace_ref, method_name)
                        return _normalize_job_response(resp)
                    except TypeError:
                        try:
                            resp = method(job_id=workspace_ref)
                            logger.info("[MAGS] Force sync requested for job %s via %s", workspace_ref, method_name)
                            return _normalize_job_response(resp)
                        except TypeError:
                            continue
            except Exception as e:
                _raise_mags_error(f"force sync workspace {workspace_ref}", e)

    logger.info(
        "[MAGS] Force sync skipped for ref %s: installed magpie-mags SDK has no sync method",
        workspace_ref,
    )
    return {"status": "skipped", "reason": "sync_not_supported", "workspace_ref": workspace_ref}


def poll_until_running(job_id: str, timeout: int = 60, poll_interval: float = 0.5) -> dict:
    """
    Poll a Mags job until its status is 'running'.

    Args:
        job_id: The job request_id
        timeout: Maximum seconds to wait
        poll_interval: Seconds between polls

    Returns:
        Final job status dict

    Raises:
        MagsAPIError: If timeout exceeded or job enters error state
    """
    start = time.time()
    last_status = None

    while time.time() - start < timeout:
        status_resp = get_job_status(job_id)
        status = status_resp.get("status", "unknown")
        last_status = status

        if status == "running":
            logger.info("[MAGS] Job %s is running (%.1fs)", job_id, time.time() - start)
            return status_resp

        if status in ("failed", "error", "terminated"):
            raise MagsAPIError(
                f"Job {job_id} entered terminal state: {status}",
                response_body=str(status_resp),
            )

        time.sleep(poll_interval)

    raise MagsAPIError(
        f"Timeout waiting for job {job_id} to be running (last status: {last_status}, waited {timeout}s)"
    )


def enable_ssh_access(
    job_id: str,
    wait_timeout: int = 5,
    poll_interval: int = 5,
    keep_polling: bool = True,
) -> dict:
    """
    Enable SSH access for a Mags job.

    Returns:
        Dict with ssh_host, ssh_port, ssh_private_key
    """
    client = _get_mags_client()
    start_time = time.time()
    attempt = 0
    last_error = None

    while True:
        attempt += 1
        try:
            resp = client.enable_access(job_id, port=22)
            resp = _normalize_job_response(resp)
            creds = {
                "ssh_host": resp.get("ssh_host") or resp.get("host"),
                "ssh_port": resp.get("ssh_port") or resp.get("port"),
                "ssh_private_key": resp.get("ssh_private_key") or resp.get("private_key"),
            }
            if creds["ssh_host"] and creds["ssh_port"] and creds["ssh_private_key"]:
                logger.info(
                    "[MAGS] SSH access enabled for job %s: host=%s port=%s (attempt=%s)",
                    job_id, creds["ssh_host"], creds["ssh_port"], attempt
                )
                return creds
            last_error = MagsAPIError(f"Incomplete SSH credentials returned for job {job_id}: {resp}")
        except Exception as e:
            last_error = e

        elapsed = time.time() - start_time
        if elapsed < max(wait_timeout, 0):
            logger.info(
                "[MAGS] SSH access not ready for job %s (attempt=%s, elapsed=%.1fs). Retrying in %ss...",
                job_id, attempt, elapsed, poll_interval
            )
            time.sleep(poll_interval)
            continue

        if not keep_polling:
            break

        job_status = "unknown"
        try:
            status_resp = get_job_status(job_id)
            job_status = status_resp.get("status", "unknown")
        except Exception:
            pass

        if job_status in ("failed", "error", "terminated", "completed", "cancelled"):
            raise MagsAPIError(
                f"Failed to enable SSH access for job {job_id}: job status is {job_status}"
            )

        logger.info(
            "[MAGS] SSH access still pending for job %s (attempt=%s, elapsed=%.1fs, status=%s). Polling again in %ss...",
            job_id, attempt, elapsed, job_status, poll_interval
        )
        time.sleep(poll_interval)

    if isinstance(last_error, MagsAPIError):
        raise last_error
    if last_error is not None:
        _raise_mags_error(f"enable SSH access for job {job_id}", last_error)
    raise MagsAPIError(f"Failed to enable SSH access for job {job_id}: timed out after {wait_timeout}s")


def enable_http_access(job_id: str, port: int) -> dict:
    """
    Enable HTTP access for a Mags job on a given port.

    Returns:
        Dict with subdomain and url
    """
    client = _get_mags_client()
    try:
        resp = client.enable_access(job_id, port=port)
    except Exception as e:
        _raise_mags_error(f"enable HTTP access for job {job_id} on port {port}", e)

    resp = _normalize_job_response(resp)
    subdomain = resp.get("subdomain", "")
    url = resp.get("url") or (f"https://{subdomain}.apps.magpiecloud.com" if subdomain else "")
    logger.info("[MAGS] HTTP access enabled for job %s port %d: %s", job_id, port, url)
    return {
        "subdomain": subdomain,
        "url": url,
    }


# ============================================================================
# SSH via paramiko
# ============================================================================

def _get_ssh_client(host: str, port: int, private_key: str, connect_timeout: int = 30) -> paramiko.SSHClient:
    """Create a paramiko SSHClient connected to the given host."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Load private key from string
    key_file = io.StringIO(private_key)
    try:
        pkey = paramiko.RSAKey.from_private_key(key_file)
    except paramiko.ssh_exception.SSHException:
        key_file.seek(0)
        try:
            pkey = paramiko.Ed25519Key.from_private_key(key_file)
        except Exception:
            key_file.seek(0)
            pkey = paramiko.ECDSAKey.from_private_key(key_file)

    client.connect(
        hostname=host,
        port=port,
        username="root",
        pkey=pkey,
        timeout=connect_timeout,
        allow_agent=False,
        look_for_keys=False,
    )
    return client


def run_ssh(
    job_id: str,
    command: str,
    timeout: int = 300,
    ssh_credentials: dict = None,
    with_node_env: bool = True,
    project_id=None,
) -> dict:
    """
    Execute a command via SSH on a Mags job.

    Args:
        job_id: The Mags job request_id
        command: Shell command to execute
        timeout: Command timeout in seconds
        ssh_credentials: Dict with ssh_host, ssh_port, ssh_private_key.
                        If None, will call enable_ssh_access() to get them.
        with_node_env: Whether to prepend Node.js environment setup
        project_id: Optional project ID for environment variables

    Returns:
        Dict with exit_code, stdout, stderr, ssh_credentials
    """
    # Get or reuse SSH credentials
    if not ssh_credentials:
        try:
            ssh_credentials = enable_ssh_access(job_id)
        except Exception as ssh_err:
            # SSH credentials unavailable — fall back to SDK native execution.
            # This handles the case where job_id is a workspace overlay name
            # (SDK-native path) rather than a job UUID.
            logger.info(
                "[MAGS][SSH] SSH access unavailable for %s (%s), falling back to SDK run_command",
                job_id, ssh_err,
            )
            result = run_command(
                workspace_id=job_id,
                command=command,
                timeout=timeout,
                with_node_env=with_node_env,
                project_id=project_id,
            )
            # Add empty ssh_credentials to match expected return shape
            result["ssh_credentials"] = None
            return result

    host = ssh_credentials["ssh_host"]
    port = int(ssh_credentials["ssh_port"])
    private_key = ssh_credentials["ssh_private_key"]

    # Build command with environment
    env_lines = ["set -e", f"cd {MAGS_WORKING_DIR}"]
    if with_node_env:
        env_lines.extend(MAGS_NODE_ENV_LINES)

    # Add project-specific environment variables
    if project_id:
        try:
            from factory.ai_functions import get_project_env_exports
            project_env_exports = get_project_env_exports(project_id)
            if project_env_exports:
                env_lines.extend(project_env_exports)
        except Exception:
            pass

    wrapped_command = "\n".join(env_lines + [command])

    # Use command timeout for connection too (but cap at 30s for normal ops)
    connect_timeout = min(timeout, 30)

    logger.info(
        "[MAGS][SSH] job_id=%s connect_timeout=%s cmd_timeout=%s command=%s",
        job_id, connect_timeout, timeout, command.split('\n')[0][:120]
    )

    ssh_client = None
    try:
        ssh_client = _get_ssh_client(host, port, private_key, connect_timeout=connect_timeout)
        stdin, stdout_ch, stderr_ch = ssh_client.exec_command(
            wrapped_command,
            timeout=timeout,
        )

        # Read output
        stdout_str = stdout_ch.read().decode("utf-8", errors="replace")
        stderr_str = stderr_ch.read().decode("utf-8", errors="replace")
        exit_code = stdout_ch.channel.recv_exit_status()

        logger.debug(
            "[MAGS][SSH RESULT] job_id=%s exit_code=%s stdout_len=%s stderr_len=%s",
            job_id, exit_code, len(stdout_str), len(stderr_str),
        )

        return {
            "exit_code": exit_code,
            "stdout": stdout_str,
            "stderr": stderr_str,
            "ssh_credentials": ssh_credentials,
        }

    except paramiko.ssh_exception.SSHException as e:
        logger.error("[MAGS][SSH] SSH error for job %s: %s", job_id, e)
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"SSH error: {e}",
            "ssh_credentials": ssh_credentials,
        }
    except Exception as e:
        logger.error("[MAGS][SSH] Error for job %s: %s", job_id, e, exc_info=True)
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Error: {e}",
            "ssh_credentials": ssh_credentials,
        }
    finally:
        if ssh_client:
            try:
                ssh_client.close()
            except Exception:
                pass


def run_ssh_streaming(
    job_id: str,
    command: str,
    timeout: int = 1200,
    output_callback: Callable[[str], None] = None,
    ssh_credentials: dict = None,
    with_node_env: bool = True,
    project_id=None,
    poll_interval: float = 2.0,
) -> dict:
    """
    Execute a long-running command via SSH with streaming output.
    Used for Claude CLI execution where we need real-time output.

    Args:
        job_id: The Mags job request_id
        command: Shell command to execute
        timeout: Command timeout in seconds
        output_callback: Callback function receiving new output chunks
        ssh_credentials: SSH credentials dict (or None to auto-fetch)
        with_node_env: Whether to set up Node.js environment
        project_id: Optional project ID for env vars
        poll_interval: Seconds between output polls

    Returns:
        Dict with exit_code, stdout, stderr, ssh_credentials
    """
    if not ssh_credentials:
        ssh_credentials = enable_ssh_access(job_id)

    host = ssh_credentials["ssh_host"]
    port = int(ssh_credentials["ssh_port"])
    private_key = ssh_credentials["ssh_private_key"]

    # Build command with environment
    env_lines = ["set -e", f"cd {MAGS_WORKING_DIR}"]
    if with_node_env:
        env_lines.extend(MAGS_NODE_ENV_LINES)

    if project_id:
        try:
            from factory.ai_functions import get_project_env_exports
            project_env_exports = get_project_env_exports(project_id)
            if project_env_exports:
                env_lines.extend(project_env_exports)
        except Exception:
            pass

    wrapped_command = "\n".join(env_lines + [command])

    # Cap connection timeout at 30s even for long-running streaming commands
    connect_timeout = min(timeout, 30)

    logger.info(
        "[MAGS][SSH_STREAM] job_id=%s timeout=%s command=%s",
        job_id, timeout, command.split('\n')[0][:120]
    )

    ssh_client = None
    all_output = ""
    all_stderr = ""

    try:
        ssh_client = _get_ssh_client(host, port, private_key, connect_timeout=connect_timeout)
        transport = ssh_client.get_transport()
        channel = transport.open_session()
        channel.settimeout(timeout)
        channel.exec_command(wrapped_command)

        start_time = time.time()
        buffer = b""

        while True:
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed > timeout:
                logger.warning("[MAGS][SSH_STREAM] Timeout after %.1fs", elapsed)
                channel.close()
                break

            # Read available data
            if channel.recv_ready():
                chunk = channel.recv(65536)
                if chunk:
                    buffer += chunk
                    decoded = buffer.decode("utf-8", errors="replace")
                    buffer = b""  # Reset buffer after successful decode
                    all_output += decoded

                    if output_callback:
                        try:
                            output_callback(decoded)
                        except Exception as e:
                            logger.warning("[MAGS][SSH_STREAM] Callback error: %s", e)

            # Read stderr
            if channel.recv_stderr_ready():
                stderr_chunk = channel.recv_stderr(65536)
                if stderr_chunk:
                    decoded_err = stderr_chunk.decode("utf-8", errors="replace")
                    all_stderr += decoded_err
                    all_output += decoded_err
                    logger.debug("[MAGS][SSH_STREAM] stderr: %s", decoded_err[:200])
                    if output_callback:
                        try:
                            output_callback(decoded_err)
                        except Exception as e:
                            logger.warning("[MAGS][SSH_STREAM] Callback error (stderr): %s", e)

            # Check if channel is closed
            if channel.exit_status_ready():
                # Read any remaining data
                while channel.recv_ready():
                    chunk = channel.recv(65536)
                    if chunk:
                        decoded = chunk.decode("utf-8", errors="replace")
                        all_output += decoded
                        if output_callback:
                            try:
                                output_callback(decoded)
                            except Exception:
                                pass
                break

            time.sleep(poll_interval)

        exit_code = channel.recv_exit_status()
        logger.info(
            "[MAGS][SSH_STREAM] Completed: exit_code=%s, output_len=%d, elapsed=%.1fs",
            exit_code, len(all_output), time.time() - start_time,
        )

        return {
            "exit_code": exit_code,
            "stdout": all_output,
            "stderr": all_stderr,
            "ssh_credentials": ssh_credentials,
        }

    except Exception as e:
        logger.error("[MAGS][SSH_STREAM] Error: %s", e, exc_info=True)
        return {
            "exit_code": -1,
            "stdout": all_output,
            "stderr": f"{all_stderr}\nError: {e}" if all_stderr else f"Error: {e}",
            "ssh_credentials": ssh_credentials,
        }
    finally:
        if ssh_client:
            try:
                ssh_client.close()
            except Exception:
                pass


# ============================================================================
# Workspace Helpers
# ============================================================================

def workspace_name_for_claude_auth(user_id: int, unique_suffix: str = None) -> str:
    """
    Get the workspace name for a user's Claude auth workspace.

    If `unique_suffix` is provided, returns `claude-auth-{suffix}`.
    Otherwise keeps the legacy deterministic format for backwards compatibility.
    """
    if unique_suffix:
        clean = re.sub(r"[^a-zA-Z0-9-]", "", str(unique_suffix)).lower()
        return f"claude-auth-{clean}"
    return f"claude-auth-{user_id}"


def generate_unique_claude_auth_workspace_name() -> str:
    """Generate a unique Claude auth workspace ID."""
    return workspace_name_for_claude_auth(user_id=0, unique_suffix=uuid.uuid4().hex[:8])


def get_latest_claude_auth_workspace_id(user_id: int) -> Optional[str]:
    """
    Resolve the latest Claude auth workspace overlay ID for a user from DB.

    Returns None when no valid workspace record exists.
    """
    try:
        from development.models import MagpieWorkspace

        workspace = (
            MagpieWorkspace.objects.filter(
                user_id=user_id,
                workspace_type='claude_auth',
            )
            .exclude(mags_workspace_id__isnull=True)
            .exclude(mags_workspace_id__exact="")
            .order_by('-updated_at')
            .first()
        )
        return workspace.mags_workspace_id if workspace else None
    except Exception as e:
        logger.warning("[MAGS] Failed to resolve latest claude auth workspace for user %s: %s", user_id, e)
        return None


def workspace_name_for_ticket(ticket_id: int, unique_suffix: str = None) -> str:
    """
    Get the workspace name for a ticket execution workspace.

    Format: ``{ticket_id}-{unique_suffix}``
    Each execution run should pass a unique suffix (e.g. a short UUID) so that
    a fresh workspace is created every time, avoiding "already in use" conflicts.
    """
    if not unique_suffix:
        unique_suffix = uuid.uuid4().hex[:8]
    clean = re.sub(r"[^a-zA-Z0-9-]", "", str(unique_suffix)).lower()
    return f"{ticket_id}-{clean}"


def workspace_name_for_preview(project_id) -> str:
    """Get the workspace name for a project preview workspace."""
    return f"preview-{project_id}"


def get_or_create_workspace_job(
    workspace_id: str,
    base_workspace_id: str = None,
    script: str = None,
    persistent: bool = True,
    environment: dict = None,
) -> dict:
    """
    Get an existing running job for a workspace, or create a new one.

    Handles the case where a workspace already exists (500 conflict)
    by finding the existing job.

    Args:
        workspace_id: Workspace overlay name
        base_workspace_id: Optional base workspace to fork from
        script: Script to run (defaults to keepalive)
        persistent: Whether workspace persists
        environment: Optional environment variables

    Returns:
        Job dict with request_id, status, etc.
    """
    if not script:
        script = MAGS_KEEPALIVE_SCRIPT

    try:
        # Try to submit a new job
        job = submit_job(
            script=script,
            workspace_id=workspace_id,
            base_workspace_id=base_workspace_id,
            persistent=persistent,
            environment=environment,
        )
        job_id = job.get("request_id") or job.get("id")

        if not job_id:
            raise MagsAPIError(f"No job ID returned for workspace {workspace_id}: {job}")

        logger.info("[MAGS] Created job %s for workspace %s", job_id, workspace_id)

        # Poll until running
        status = poll_until_running(job_id, timeout=60)
        job["status"] = status.get("status", "running")
        return job

    except MagsAPIError as e:
        # If we get a 500/409, the workspace may already have a running job
        # Check for various conflict indicators in the error message
        error_str = str(e).lower()
        is_conflict = (
            e.status_code in (500, 409) or
            "conflict" in error_str or
            "already" in error_str or
            "in use" in error_str or
            "exists" in error_str or
            "workspace" in error_str  # Broad catch for workspace-related errors
        )
        if is_conflict:
            logger.info("[MAGS] Workspace %s may already exist (error: %s), looking for running job...", workspace_id, str(e)[:200])
            return _find_existing_workspace_job(workspace_id)
        logger.error("[MAGS] Non-conflict error creating workspace %s: %s", workspace_id, e)
        raise


def _find_existing_workspace_job(workspace_id: str) -> dict:
    """
    Find an existing running job for a workspace.

    Args:
        workspace_id: The workspace name to search for

    Returns:
        Job dict for the running job

    Raises:
        MagsAPIError: If no running job found
    """
    try:
        jobs_resp = list_jobs()
        jobs = jobs_resp.get("jobs", jobs_resp.get("data", []))

        logger.info("[MAGS] Searching for workspace %s among %d jobs", workspace_id, len(jobs))

        for job in jobs:
            job_ws = job.get("workspace_id", "")
            job_status = job.get("status", "")
            job_id = job.get("request_id") or job.get("id")

            # Log each job for debugging
            logger.debug("[MAGS] Job %s: workspace=%s, status=%s", job_id, job_ws, job_status)

            if job_ws == workspace_id and job_status in ("running", "sleeping"):
                logger.info("[MAGS] Found existing job %s for workspace %s (status: %s)",
                            job_id, workspace_id, job_status)
                # If sleeping, it will wake up on SSH access
                return job

        # Log all workspaces for debugging when not found
        all_workspaces = [j.get("workspace_id", "?") for j in jobs]
        logger.warning("[MAGS] No running/sleeping job found for workspace %s. Active workspaces: %s",
                       workspace_id, all_workspaces[:10])
        raise MagsAPIError(f"No running job found for workspace {workspace_id}")

    except MagsAPIError:
        raise
    except Exception as e:
        raise MagsAPIError(f"Failed to find existing job for workspace {workspace_id}: {e}")


def _stop_workspace_job(client, workspace_id: str, max_wait: int = 15) -> bool:
    """Stop any running job on a workspace and wait until it's actually stopped.

    Returns True if the job was stopped (or no job found), False on timeout.
    """
    try:
        job = client.find_job(workspace_id)
        if not job:
            logger.debug("[MAGS][STOP] No job found for workspace %s", workspace_id)
            return True

        request_id = job.get("request_id") or job.get("id")
        job_status = job.get("status", "unknown")
        logger.info("[MAGS][STOP] Found job %s on %s (status=%s), stopping...", request_id, workspace_id, job_status)

        if job_status in ("completed", "error", "failed", "terminated"):
            return True

        client.stop(request_id)
        logger.info("[MAGS][STOP] Stop requested for job %s", request_id)

        # Poll until the job is no longer running
        for _ in range(max_wait):
            time.sleep(1)
            try:
                st = client.status(request_id)
                status = st.get("status", "unknown")
                if status not in ("running", "sleeping"):
                    logger.info("[MAGS][STOP] Job %s now %s", request_id, status)
                    return True
            except Exception:
                return True  # Job gone — that's fine
        logger.warning("[MAGS][STOP] Job %s still running after %ds", request_id, max_wait)
        return False
    except Exception as e:
        logger.warning("[MAGS][STOP] Failed to stop workspace %s: %s", workspace_id, e)
        return False


def run_command(
    workspace_id: str,
    command: str,
    timeout: int = 300,
    with_node_env: bool = True,
    project_id=None,
    base_workspace_id: str = None,
) -> dict:
    """
    Execute a command on a Mags workspace using the SDK.

    Strategy:
    1. If base_workspace_id is set → create workspace with new(), then exec()
    2. Otherwise → exec() on existing running/sleeping workspace

    Mirrors the CLI flow: ``mags new <name> --base <base>`` then ``mags exec <name> <cmd>``

    Args:
        workspace_id: Workspace overlay name (e.g. "147-a3f2b1c8")
        command: Shell command to execute
        timeout: Command timeout in seconds
        with_node_env: Whether to prepend Node.js environment setup
        project_id: Optional project ID for environment variables
        base_workspace_id: Base workspace to fork from (triggers workspace creation)

    Returns:
        Dict with exit_code, stdout, stderr
    """
    # Build command with environment
    env_lines = [f"cd {MAGS_WORKING_DIR}"]
    if with_node_env:
        env_lines.extend(MAGS_NODE_ENV_LINES)

    if project_id:
        try:
            from factory.ai_functions import get_project_env_exports
            project_env_exports = get_project_env_exports(project_id)
            if project_env_exports:
                env_lines.extend(project_env_exports)
        except Exception:
            pass

    full_command = "\n".join(env_lines) + "\n" + command

    # The SDK's exec() wraps commands with chroot/overlay shell escaping that
    # breaks multi-line scripts.  Encode as base64 and pipe to sh so exec()
    # only sees a simple single-line command.
    cmd_b64 = base64.b64encode(full_command.encode("utf-8")).decode("ascii")
    exec_command = f"echo {cmd_b64} | base64 -d | sh"

    logger.info(
        "[MAGS][CMD] workspace=%s timeout=%s base=%s command=%s",
        workspace_id, timeout, base_workspace_id, command.split('\n')[0][:120],
    )

    client = _get_mags_client(timeout=timeout + 60)

    # If base_workspace_id is set, create the workspace first with new().
    # new() runs "sleep infinity" with persistent=True and waits until the VM
    # is running — this is the equivalent of ``mags new <name> --base <base>``.
    new_request_id = None
    if base_workspace_id:
        # Validate base workspace exists before forking
        try:
            workspaces_resp = client.list_workspaces()
            ws_list = workspaces_resp.get("workspaces", [])
            base_exists = any(
                w.get("workspace_id") == base_workspace_id or w.get("id") == base_workspace_id
                for w in ws_list
            )
            logger.info(
                "[MAGS][CMD] Base workspace '%s' exists=%s (checked %d workspaces)",
                base_workspace_id, base_exists, len(ws_list),
            )
            if not base_exists:
                logger.error(
                    "[MAGS][CMD] Base workspace '%s' NOT FOUND on Mags platform. "
                    "Available workspaces: %s",
                    base_workspace_id,
                    [w.get("workspace_id") or w.get("id") for w in ws_list[:20]],
                )
                return {
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"Base workspace '{base_workspace_id}' does not exist on Mags platform",
                }
        except Exception as ws_err:
            logger.warning("[MAGS][CMD] Could not validate base workspace: %s", ws_err)

        try:
            new_resp = client.new(
                workspace_id,
                base_workspace_id=base_workspace_id,
                timeout=min(timeout, 120),
            )
            new_request_id = new_resp.get("request_id")
            logger.info(
                "[MAGS][CMD] new() created workspace %s (request_id=%s)",
                workspace_id, new_request_id,
            )
            # Verify job status after new() returns
            try:
                job_status = client.status(new_request_id)
                logger.info(
                    "[MAGS][CMD] Post-new() job status: %s",
                    {k: v for k, v in job_status.items() if k in ('status', 'workspace_id', 'subdomain')},
                )
            except Exception:
                pass
        except Exception as new_err:
            error_str = str(new_err).lower()
            # If workspace already exists / in use, that's fine — we'll exec on it
            if "already" in error_str or "in use" in error_str or "conflict" in error_str:
                logger.info("[MAGS][CMD] Workspace %s already exists, proceeding to exec()", workspace_id)
            else:
                logger.error("[MAGS][CMD] new() failed for %s: %s", workspace_id, new_err, exc_info=True)
                return {"exit_code": -1, "stdout": "", "stderr": str(new_err)}

    # exec() runs the command on the running/sleeping VM via SSH (handled internally by SDK).
    # After new(), the VM may need a few seconds to fully boot — retry on transient errors.
    # Use more retries with longer delay for "no VM" since provisioning can be slow.
    max_exec_attempts = 10
    for attempt in range(1, max_exec_attempts + 1):
        try:
            resp = client.exec(workspace_id, exec_command, timeout=timeout)
            stdout = resp.get("output", "")
            stderr = resp.get("stderr", "")
            exit_code = resp.get("exit_code", -1)
            logger.info(
                "[MAGS][CMD] exec() completed: workspace=%s exit_code=%s stdout_len=%d stderr_len=%d",
                workspace_id, exit_code, len(stdout), len(stderr),
            )
            # exit_code 255 = SSH connection failure (not the remote command).
            # Treat as transient and retry — the VM's SSH may need a moment.
            # Limit to 2 retries (not all 6) to avoid long delays in polling loops.
            if exit_code == 255 and attempt <= 2:
                logger.warning(
                    "[MAGS][CMD] SSH failure (exit_code=255) for %s attempt %d/%d: %s — retrying in 5s",
                    workspace_id, attempt, max_exec_attempts, stderr[:200],
                )
                time.sleep(5)
                continue
            return {"exit_code": exit_code, "stdout": stdout, "stderr": stderr}
        except Exception as exec_err:
            err_str = str(exec_err).lower()
            # "no vm associated" / "not found" are transient — VM still booting
            is_transient = "no vm" in err_str or "not found" in err_str or "not running" in err_str
            if is_transient and attempt < max_exec_attempts:
                # Check job status to detect dead jobs early
                if new_request_id and attempt % 3 == 0:
                    try:
                        st = client.status(new_request_id)
                        job_st = st.get("status", "unknown")
                        logger.info(
                            "[MAGS][CMD] Job status check for %s: %s",
                            workspace_id, job_st,
                        )
                        if job_st in ("completed", "error", "stopped"):
                            logger.error(
                                "[MAGS][CMD] Job %s has died (status=%s), aborting retries",
                                workspace_id, job_st,
                            )
                            return {"exit_code": -1, "stdout": "", "stderr": f"Job died: {job_st}. {exec_err}"}
                    except Exception:
                        pass
                retry_delay = 5
                logger.info(
                    "[MAGS][CMD] exec() attempt %d/%d for %s: %s — retrying in %ds",
                    attempt, max_exec_attempts, workspace_id, exec_err, retry_delay,
                )
                time.sleep(retry_delay)
                continue
            logger.error("[MAGS][CMD] exec() failed for %s after %d attempts: %s", workspace_id, attempt, exec_err)
            return {"exit_code": -1, "stdout": "", "stderr": str(exec_err)}


def run_command_streaming(
    workspace_id: str,
    command: str,
    timeout: int = 1200,
    output_callback: Optional[Callable[[str], None]] = None,
    with_node_env: bool = True,
    project_id=None,
    base_workspace_id: str = None,
    poll_interval: float = 5.0,
) -> dict:
    """
    Execute a long-running command with streaming output via SDK log polling.

    Stops any existing job on the workspace, submits the command as a new
    persistent job via run(), then polls logs() and status() to stream output
    through output_callback.  Used for Claude CLI execution.

    Args:
        workspace_id: Workspace overlay name
        command: Shell command to execute
        timeout: Command timeout in seconds
        output_callback: Callback receiving new output chunks
        with_node_env: Whether to prepend Node.js environment setup
        project_id: Optional project ID for environment variables
        base_workspace_id: Base workspace to fork from (only needed for first run)
        poll_interval: Seconds between log polls

    Returns:
        Dict with exit_code, stdout, stderr
    """
    # Build command with environment
    env_lines = [f"cd {MAGS_WORKING_DIR}"]
    if with_node_env:
        env_lines.extend(MAGS_NODE_ENV_LINES)

    if project_id:
        try:
            from factory.ai_functions import get_project_env_exports
            project_env_exports = get_project_env_exports(project_id)
            if project_env_exports:
                env_lines.extend(project_env_exports)
        except Exception:
            pass

    full_script = "#!/bin/bash\n" + "\n".join(env_lines) + "\n" + command

    logger.info(
        "[MAGS][STREAM] workspace=%s timeout=%s command=%s",
        workspace_id, timeout, command.split('\n')[0][:120],
    )

    client = _get_mags_client(timeout=timeout + 60)
    all_output = ""
    last_log_len = 0

    try:
        # Stop any existing job on this workspace so we can submit a new one
        _stop_workspace_job(client, workspace_id)

        # Submit new job.  persistent=True keeps the workspace overlay.
        run_kwargs = {"workspace_id": workspace_id, "persistent": True}
        if base_workspace_id:
            run_kwargs["base_workspace_id"] = base_workspace_id

        resp = client.run(full_script, **run_kwargs)
        request_id = resp.get("request_id") or resp.get("id")

        if not request_id:
            return {"exit_code": -1, "stdout": "", "stderr": "No request_id returned from run()"}

        logger.info("[MAGS][STREAM] Job submitted: request_id=%s", request_id)

        start_time = time.time()

        while time.time() - start_time < timeout:
            time.sleep(poll_interval)

            # Poll logs for new output
            try:
                log_resp = client.logs(request_id)
                logs = log_resp.get("logs", []) if isinstance(log_resp, dict) else []

                if isinstance(logs, list) and len(logs) > last_log_len:
                    new_entries = logs[last_log_len:]
                    last_log_len = len(logs)

                    # Convert log entries to text, filtering infrastructure logs.
                    # Mags logs() returns a mix of:
                    #  - dicts with timestamp/level/message (platform infra logs)
                    #  - strings (script stdout lines)
                    lines = []
                    for entry in new_entries:
                        if isinstance(entry, dict):
                            # Skip Mags infrastructure logs (job provisioning, VM, etc.)
                            if "timestamp" in entry and "level" in entry:
                                continue
                            lines.append(json.dumps(entry))
                        else:
                            lines.append(str(entry))
                    new_text = "\n".join(lines)
                    if new_text:
                        all_output += new_text + "\n"
                        if output_callback:
                            try:
                                output_callback(new_text + "\n")
                            except Exception as cb_err:
                                logger.warning("[MAGS][STREAM] Callback error: %s", cb_err)
            except Exception as log_err:
                logger.debug("[MAGS][STREAM] Log poll error: %s", log_err)

            # Check job status.  With persistent=True the job goes to
            # "sleeping" (not "completed") when the script exits.
            try:
                status_resp = client.status(request_id)
                status = status_resp.get("status", "unknown") if isinstance(status_resp, dict) else "unknown"

                if status in ("completed", "sleeping", "error", "failed", "terminated"):
                    # Final log fetch
                    try:
                        final_logs = client.logs(request_id).get("logs", [])
                        if isinstance(final_logs, list) and len(final_logs) > last_log_len:
                            remaining = final_logs[last_log_len:]
                            rem_lines = []
                            for entry in remaining:
                                if isinstance(entry, dict):
                                    if "timestamp" in entry and "level" in entry:
                                        continue
                                    rem_lines.append(json.dumps(entry))
                                else:
                                    rem_lines.append(str(entry))
                            remaining_text = "\n".join(rem_lines)
                            if remaining_text:
                                all_output += remaining_text + "\n"
                                if output_callback:
                                    try:
                                        output_callback(remaining_text + "\n")
                                    except Exception:
                                        pass
                    except Exception:
                        pass

                    exit_code = status_resp.get("exit_code") if isinstance(status_resp, dict) else -1
                    if exit_code is None:
                        exit_code = 0 if status in ("completed", "sleeping") else -1

                    elapsed = time.time() - start_time
                    logger.info(
                        "[MAGS][STREAM] Completed: status=%s exit_code=%s output_len=%d elapsed=%.1fs",
                        status, exit_code, len(all_output), elapsed,
                    )
                    return {"exit_code": exit_code, "stdout": all_output, "stderr": ""}
            except Exception as status_err:
                logger.debug("[MAGS][STREAM] Status poll error: %s", status_err)

        # Timeout
        logger.warning("[MAGS][STREAM] Timeout after %ds", timeout)
        return {"exit_code": -1, "stdout": all_output, "stderr": f"Timeout after {timeout}s"}

    except Exception as e:
        logger.error("[MAGS][STREAM] Error: %s", e, exc_info=True)
        return {"exit_code": -1, "stdout": all_output, "stderr": str(e)}


def get_http_proxy_url(job_id: str, port: int) -> str:
    """
    Enable HTTP access and return the proxy URL.

    Args:
        job_id: The Mags job request_id
        port: The port to expose

    Returns:
        The proxy URL string
    """
    access = enable_http_access(job_id, port)
    return access.get("url", "")
