"""
Claude Code CLI Utilities

Provides functions for:
- Claude Code CLI authentication in Magpie workspaces
- S3 backup/restore of Claude auth folder (/root/.claude)
- Running Claude CLI commands with streaming output
- Parsing Claude CLI JSON stream output
"""

import base64
import json
import logging
import re
import time
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime

import boto3
from botocore.exceptions import ClientError
from django.conf import settings

from factory.ai_functions import get_magpie_client, _run_magpie_ssh

logger = logging.getLogger(__name__)

# S3 configuration
S3_CLAUDE_AUTH_PREFIX = "claude-auth"


def get_s3_client():
    """Get configured S3 client."""
    return boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1'),
    )


def get_s3_bucket_name():
    """Get S3 bucket name from settings."""
    return getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)


# ============================================================================
# S3 Backup/Restore Functions
# ============================================================================

def backup_claude_auth_to_s3(workspace_id: str, user_id: int) -> Dict[str, Any]:
    """
    Backup /root/.claude folder from workspace to S3.

    This preserves Claude Code authentication across workspace recreations.

    Args:
        workspace_id: Magpie workspace ID
        user_id: User ID for S3 key namespace

    Returns:
        Dict with status, s3_key, and any error message
    """
    logger.info(f"[CLAUDE_AUTH] Backing up Claude auth for user {user_id} from workspace {workspace_id}")

    try:
        client = get_magpie_client()

        # Check if .claude folder exists
        check_result = _run_magpie_ssh(
            client, workspace_id,
            "[ -d /root/.claude ] && echo 'EXISTS' || echo 'NOT_FOUND'",
            timeout=30, with_node_env=False
        )

        if 'NOT_FOUND' in check_result.get('stdout', ''):
            return {
                'status': 'error',
                'error': 'Claude auth folder not found. User may not be authenticated.'
            }

        # Create tar archive of .claude folder
        tar_result = _run_magpie_ssh(
            client, workspace_id,
            "cd /root && tar -czf /tmp/claude-auth.tar.gz .claude && echo 'TAR_SUCCESS'",
            timeout=60, with_node_env=False
        )

        if tar_result.get('exit_code') != 0 or 'TAR_SUCCESS' not in tar_result.get('stdout', ''):
            return {
                'status': 'error',
                'error': f"Failed to create tar archive: {tar_result.get('stderr', tar_result.get('stdout', 'Unknown error'))}"
            }

        # Read tar file as base64
        base64_result = _run_magpie_ssh(
            client, workspace_id,
            "base64 /tmp/claude-auth.tar.gz",
            timeout=120, with_node_env=False
        )

        if base64_result.get('exit_code') != 0:
            return {
                'status': 'error',
                'error': f"Failed to encode tar archive: {base64_result.get('stderr', 'Unknown error')}"
            }

        base64_content = base64_result.get('stdout', '').strip()
        if not base64_content:
            return {
                'status': 'error',
                'error': 'Empty base64 content received'
            }

        # Decode base64 to bytes
        try:
            tar_bytes = base64.b64decode(base64_content)
        except Exception as e:
            return {
                'status': 'error',
                'error': f"Failed to decode base64: {str(e)}"
            }

        # Upload to S3
        bucket_name = get_s3_bucket_name()
        if not bucket_name:
            return {
                'status': 'error',
                'error': 'S3 bucket not configured'
            }

        s3_key = f"{S3_CLAUDE_AUTH_PREFIX}/{user_id}/claude-config.tar.gz"

        try:
            s3_client = get_s3_client()
            s3_client.put_object(
                Bucket=bucket_name,
                Key=s3_key,
                Body=tar_bytes,
                ContentType='application/gzip',
                Metadata={
                    'user_id': str(user_id),
                    'workspace_id': workspace_id,
                    'backup_time': datetime.now().isoformat()
                }
            )
            logger.info(f"[CLAUDE_AUTH] Successfully backed up to S3: {s3_key}")
        except ClientError as e:
            return {
                'status': 'error',
                'error': f"S3 upload failed: {str(e)}"
            }

        # Cleanup temp file
        _run_magpie_ssh(
            client, workspace_id,
            "rm -f /tmp/claude-auth.tar.gz",
            timeout=30, with_node_env=False
        )

        return {
            'status': 'success',
            's3_key': s3_key,
            'message': 'Claude auth backed up successfully'
        }

    except Exception as e:
        logger.error(f"[CLAUDE_AUTH] Backup failed: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'error': str(e)
        }


def restore_claude_auth_from_s3(workspace_id: str, user_id: int, s3_key: str = None) -> Dict[str, Any]:
    """
    Restore /root/.claude folder from S3 to workspace.

    Uses a pre-signed URL so the VM can download directly from S3 (much faster).

    Args:
        workspace_id: Magpie workspace ID
        user_id: User ID for S3 key namespace
        s3_key: Optional specific S3 key (defaults to user's backup)

    Returns:
        Dict with status and any error message
    """
    logger.info(f"[CLAUDE_AUTH] Restoring Claude auth for user {user_id} to workspace {workspace_id}")

    try:
        bucket_name = get_s3_bucket_name()
        if not bucket_name:
            return {
                'status': 'error',
                'error': 'S3 bucket not configured'
            }

        if not s3_key:
            s3_key = f"{S3_CLAUDE_AUTH_PREFIX}/{user_id}/claude-config.tar.gz"

        # Generate a pre-signed URL (5 minutes expiry)
        try:
            s3_client = get_s3_client()

            # First check if the object exists
            try:
                s3_client.head_object(Bucket=bucket_name, Key=s3_key)
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    return {
                        'status': 'not_found',
                        'error': 'No Claude auth backup found for this user'
                    }
                raise

            # Generate pre-signed URL (5 minutes = 300 seconds)
            presigned_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': s3_key},
                ExpiresIn=300
            )
            logger.info(f"[CLAUDE_AUTH] Generated pre-signed URL for {s3_key}")

        except ClientError as e:
            return {
                'status': 'error',
                'error': f"S3 error: {str(e)}"
            }

        client = get_magpie_client()

        # Have the VM download directly using wget/curl and extract
        # Using curl with the pre-signed URL
        restore_script = f"""
        set -e
        echo "Downloading from S3..."
        curl -sS -o /tmp/claude-auth.tar.gz '{presigned_url}'

        if [ ! -f /tmp/claude-auth.tar.gz ]; then
            echo "DOWNLOAD_FAILED"
            exit 1
        fi

        FILE_SIZE=$(stat -c%s /tmp/claude-auth.tar.gz 2>/dev/null || stat -f%z /tmp/claude-auth.tar.gz 2>/dev/null || echo "0")
        echo "Downloaded file size: $FILE_SIZE bytes"

        if [ "$FILE_SIZE" -lt 1000 ]; then
            echo "DOWNLOAD_TOO_SMALL"
            cat /tmp/claude-auth.tar.gz
            exit 1
        fi

        echo "Extracting to /root/.claude..."
        rm -rf /root/.claude
        tar -xzf /tmp/claude-auth.tar.gz -C /root

        if [ -d /root/.claude ]; then
            echo "RESTORE_SUCCESS"
            ls -la /root/.claude/ | head -5
        else
            echo "EXTRACT_FAILED"
            exit 1
        fi

        rm -f /tmp/claude-auth.tar.gz
        """

        extract_result = _run_magpie_ssh(
            client, workspace_id,
            restore_script,
            timeout=120, with_node_env=False
        )

        stdout = extract_result.get('stdout', '')
        logger.info(f"[CLAUDE_AUTH] Restore output: {stdout[:500]}")

        if extract_result.get('exit_code') != 0 or 'RESTORE_SUCCESS' not in stdout:
            return {
                'status': 'error',
                'error': f"Failed to restore: {stdout[:200]}"
            }

        logger.info(f"[CLAUDE_AUTH] Successfully restored Claude auth from S3")
        return {
            'status': 'success',
            'message': 'Claude auth restored successfully'
        }

    except Exception as e:
        logger.error(f"[CLAUDE_AUTH] Restore failed: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'error': str(e)
        }


# ============================================================================
# Claude Code CLI Authentication
# ============================================================================

def start_claude_auth(workspace_id: str) -> Dict[str, Any]:
    """
    Start Claude Code authentication process on workspace.

    This runs `claude` in a background expect process and captures the OAuth URL.
    The expect process waits for a code file to be written, then submits the code.

    Args:
        workspace_id: Magpie workspace ID

    Returns:
        Dict with status and oauth_url (if authentication needed)
    """
    logger.info(f"[CLAUDE_AUTH] Starting auth on workspace {workspace_id}")

    try:
        client = get_magpie_client()

        # First check if already authenticated
        check_result = check_claude_auth_status(workspace_id)
        if check_result.get('authenticated'):
            return {
                'status': 'already_authenticated',
                'message': 'Claude Code is already authenticated'
            }

        # Setup script: install expect, create the expect script, run in background
        setup_script = """
        # Source shell profiles to get PATH
        [ -f /etc/profile ] && . /etc/profile
        [ -f ~/.profile ] && . ~/.profile
        [ -f ~/.bashrc ] && . ~/.bashrc

        # Clean up any previous auth attempt
        rm -f /tmp/claude_url.txt /tmp/claude_code.txt /tmp/claude_status.txt /tmp/claude_auth.exp

        # Check if expect is available, install if not
        if ! command -v expect >/dev/null 2>&1; then
            apk add --no-cache expect >/dev/null 2>&1 || echo "EXPECT_INSTALL_FAILED"
        fi

        # Find the full path to claude
        CLAUDE_PATH=$(which claude 2>/dev/null || echo "/root/.claude/local/claude")
        echo "CLAUDE_PATH=$CLAUDE_PATH"

        # Create a wrapper script that sets up the environment
        cat > /tmp/claude_wrapper.sh << 'WRAPPEREOF'
#!/bin/sh
[ -f /etc/profile ] && . /etc/profile
[ -f ~/.profile ] && . ~/.profile
[ -f ~/.bashrc ] && . ~/.bashrc
# Set wide terminal to prevent URL wrapping
export COLUMNS=2000
export TERM=dumb
exec claude "$@"
WRAPPEREOF
        chmod +x /tmp/claude_wrapper.sh

        # Create the expect script - use a different approach to avoid escaping issues
        # Write expect script using echo commands
        cat > /tmp/claude_auth.exp << 'EXPECTSCRIPT'
log_user 1
set timeout 300
set CR [format %c 13]

spawn /tmp/claude_wrapper.sh

expect {
    -re {\.\.\.} {
        exp_continue
    }
    -re {trust the files|Yes, proceed|trust.*folder} {
        puts "TRUST_PROMPT_DETECTED"
        after 500
        send $CR
        exp_continue
    }
    -re {looks best|text style|style preference|output format|terminal} {
        after 500
        send $CR
        exp_continue
    }
    -re {Select an account|authenticate|login method|choose.*account|sign in} {
        after 500
        send $CR
        exp_continue
    }
    -re {(https://claude\.ai/oauth[!-~]+)} {
        set url $expect_out(1,string)
        set f [open "/tmp/claude_url.txt" w]
        puts $f $url
        close $f
        exp_continue
    }
    -re {[Pp]aste.*code|[Ee]nter.*code|authorization code|[Cc]ode:} {
        puts "WAITING_FOR_CODE"
        for {set i 0} {$i < 300} {incr i} {
            if {[file exists "/tmp/claude_code.txt"]} {
                set f [open "/tmp/claude_code.txt" r]
                set code [string trim [read $f]]
                close $f
                file delete "/tmp/claude_code.txt"
                puts "SENDING_CODE: $code"
                send -- "$code"
                after 500
                send $CR
                break
            }
            after 1000
        }
        exp_continue
    }
    -re {Login successful|Logged in as|successfully authenticated} {
        set f [open "/tmp/claude_status.txt" w]
        puts $f "SUCCESS"
        close $f
        puts "LOGIN_SUCCESS"
        after 1000
        send $CR
        exp_continue
    }
    -re {What can I help|help you with|How can I|Tips:} {
        if {![file exists "/tmp/claude_status.txt"]} {
            set f [open "/tmp/claude_status.txt" w]
            puts $f "ALREADY_AUTH"
            close $f
            puts "ALREADY_AUTHENTICATED"
        }
        after 500
        send "/exit"
        send $CR
    }
    -re {[Ee]rror|[Ii]nvalid|expired|failed} {
        set f [open "/tmp/claude_status.txt" w]
        puts $f "ERROR"
        close $f
        puts "AUTH_ERROR"
    }
    timeout {
        if {[file exists "/tmp/claude_status.txt"]} {
            puts "TIMEOUT_WITH_STATUS"
        } else {
            set f [open "/tmp/claude_status.txt" w]
            puts $f "TIMEOUT"
            close $f
            puts "TIMEOUT_NO_STATUS"
        }
    }
}
expect eof
EXPECTSCRIPT

        echo "SETUP_COMPLETE"
        """

        result = _run_magpie_ssh(
            client, workspace_id,
            setup_script,
            timeout=60, with_node_env=False
        )

        stdout = result.get('stdout', '').strip()
        if 'EXPECT_INSTALL_FAILED' in stdout:
            return {
                'status': 'error',
                'error': 'Failed to install expect. Cannot proceed with authentication.'
            }

        if 'SETUP_COMPLETE' not in stdout:
            return {
                'status': 'error',
                'error': f'Setup failed: {stdout[:200]}'
            }

        # Now run the expect script in background
        bg_script = """
        [ -f /etc/profile ] && . /etc/profile
        [ -f ~/.profile ] && . ~/.profile
        [ -f ~/.bashrc ] && . ~/.bashrc

        # Run expect in background
        nohup expect /tmp/claude_auth.exp > /tmp/claude_auth.log 2>&1 &
        echo "BG_PID=$!"
        """

        bg_result = _run_magpie_ssh(
            client, workspace_id,
            bg_script,
            timeout=30, with_node_env=False
        )

        logger.info(f"[CLAUDE_AUTH] Background process started: {bg_result.get('stdout', '')[:100]}")

        # Track retry count for expect process restarts
        expect_restart_count = 0
        max_expect_restarts = 3

        # Wait for URL file to appear (poll for up to 60 seconds)
        for i in range(60):
            time.sleep(1)
            # Check files and also try to extract URL from log if not found
            check_script = r"""
            # First check if URL file exists AND has full URL (>100 chars)
            if [ -f /tmp/claude_url.txt ]; then
                FILE_URL=$(cat /tmp/claude_url.txt)
                if [ ${#FILE_URL} -gt 100 ]; then
                    echo "URL_FOUND"
                    echo "$FILE_URL"
                    exit 0
                else
                    # URL in file is truncated, delete and re-extract from log
                    rm -f /tmp/claude_url.txt
                fi
            fi

            # Check status file
            if [ -f /tmp/claude_status.txt ]; then
                echo "STATUS_FOUND"
                cat /tmp/claude_status.txt
                exit 0
            fi

            # Try to extract URL from log file
            if [ -f /tmp/claude_auth.log ]; then
                # Remove lines with known non-URL text, join remaining, extract URL
                URL=$(grep -v -E 'WAITING|LOG_|CAPTURED|Paste|code here|prompted|spawn|expect' /tmp/claude_auth.log | tr -d '\n\r' | grep -oE 'https://claude\.ai/oauth[A-Za-z0-9_.~:/?#@!$&()*+,;=%=-]+' | head -1)
                # Truncate at any obvious garbage (lowercase words that aren't URL params)
                URL=$(echo "$URL" | sed 's/Paste.*//; s/code.*here.*//; s/prompted.*//')
                # Verify it looks like a complete URL (should end with state= parameter)
                if ! echo "$URL" | grep -q 'state='; then
                    URL=""
                fi
                if [ -n "$URL" ] && [ ${#URL} -gt 100 ]; then
                    echo "$URL" > /tmp/claude_url.txt
                    echo "URL_FOUND"
                    echo "$URL"
                else
                    echo "WAITING"
                    echo "URL_LEN=${#URL}"
                    echo "LOG_START"
                    tail -20 /tmp/claude_auth.log | cat -v
                    echo "LOG_END"
                    pgrep -a expect || echo "NO_EXPECT_RUNNING"
                fi
            else
                echo "WAITING"
                echo "NO_LOG_FILE"
                pgrep -a expect || echo "NO_EXPECT_RUNNING"
            fi
            """
            check_result = _run_magpie_ssh(
                client, workspace_id,
                check_script,
                timeout=10, with_node_env=False
            )
            check_stdout = check_result.get('stdout', '').strip()

            if 'URL_FOUND' in check_stdout:
                # Extract URL from output
                lines = check_stdout.split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith('https://claude.ai/oauth'):
                        # Clean any stray ANSI codes or control characters
                        import re as regex
                        clean_url = regex.sub(r'\x1b\[[0-9;]*m', '', line)
                        clean_url = regex.sub(r'[\x00-\x1f\x7f]', '', clean_url)
                        # Log the FULL URL for debugging
                        logger.info(f"[CLAUDE_AUTH] Got OAuth URL (full, {len(clean_url)} chars): {clean_url}")
                        return {
                            'status': 'pending',
                            'oauth_url': clean_url,
                            'message': 'Open the URL and authenticate, then paste the code'
                        }

            # Log debug info on first few iterations
            if i < 3 and 'WAITING' in check_stdout:
                # Print full stdout for debugging (first 3 iterations only)
                logger.info(f"[CLAUDE_AUTH] Full debug output ({i}s, {len(check_stdout)} chars):\n{check_stdout}")
            elif 'WAITING' in check_stdout:
                # Check if expect process died and needs restart
                if 'NO_EXPECT_RUNNING' in check_stdout:
                    if expect_restart_count < max_expect_restarts:
                        expect_restart_count += 1
                        logger.warning(f"[CLAUDE_AUTH] Expect process died, restarting (attempt {expect_restart_count}/{max_expect_restarts})")

                        # Clean up and restart expect
                        restart_script = """
                        pkill -9 claude 2>/dev/null || true
                        pkill -9 expect 2>/dev/null || true
                        rm -f /tmp/claude_auth.log
                        sleep 2

                        [ -f /etc/profile ] && . /etc/profile
                        [ -f ~/.profile ] && . ~/.profile
                        [ -f ~/.bashrc ] && . ~/.bashrc

                        nohup expect /tmp/claude_auth.exp > /tmp/claude_auth.log 2>&1 &
                        echo "RESTARTED_PID=$!"
                        """
                        restart_result = _run_magpie_ssh(
                            client, workspace_id,
                            restart_script,
                            timeout=30, with_node_env=False
                        )
                        logger.info(f"[CLAUDE_AUTH] Restart result: {restart_result.get('stdout', '')[:100]}")
                        time.sleep(3)  # Give it time to start
                    else:
                        logger.error(f"[CLAUDE_AUTH] Max restarts ({max_expect_restarts}) exceeded, giving up")
                        return {
                            'status': 'error',
                            'error': 'Authentication process keeps failing. Please try again later.'
                        }
                elif i % 10 == 0 and 'LOG_START' in check_stdout:
                    logger.info(f"[CLAUDE_AUTH] Still waiting at {i}s...")

            if 'STATUS_FOUND' in check_stdout:
                if 'ALREADY_AUTH' in check_stdout or 'SUCCESS' in check_stdout:
                    return {
                        'status': 'already_authenticated',
                        'message': 'Claude Code is already authenticated'
                    }
                if 'ERROR' in check_stdout:
                    return {
                        'status': 'error',
                        'error': 'Authentication error occurred'
                    }

            if i % 10 == 0:
                logger.info(f"[CLAUDE_AUTH] Waiting for URL... ({i}s)")

        return {
            'status': 'error',
            'error': 'Timeout waiting for OAuth URL'
        }

    except Exception as e:
        logger.error(f"[CLAUDE_AUTH] Start auth failed: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'error': str(e)
        }


def submit_claude_auth_code(workspace_id: str, auth_code: str) -> Dict[str, Any]:
    """
    Submit the OAuth code to complete Claude authentication.

    This writes the code to a file that the background expect process is watching.
    The expect process will read the code and submit it to Claude.

    Args:
        workspace_id: Magpie workspace ID
        auth_code: OAuth code from user

    Returns:
        Dict with status
    """
    logger.info(f"[CLAUDE_AUTH] Submitting auth code to workspace {workspace_id}")

    try:
        client = get_magpie_client()

        # Clean the auth code
        auth_code = auth_code.strip()

        # Write the code to the file that expect is watching
        write_script = f"""
        echo '{auth_code}' > /tmp/claude_code.txt
        echo "CODE_WRITTEN"
        """

        result = _run_magpie_ssh(
            client, workspace_id,
            write_script,
            timeout=30, with_node_env=False
        )

        if 'CODE_WRITTEN' not in result.get('stdout', ''):
            return {
                'status': 'error',
                'error': 'Failed to write auth code to file'
            }

        logger.info(f"[CLAUDE_AUTH] Code written, waiting for auth to complete...")

        # Wait for status file to appear (poll for up to 120 seconds)
        expect_restart_attempted = False
        for i in range(120):
            time.sleep(1)
            check_script = """
            if [ -f /tmp/claude_status.txt ]; then
                echo "STATUS_FOUND"
                cat /tmp/claude_status.txt
            else
                echo "WAITING"
                # Check if expect is still running
                if pgrep -x expect > /dev/null; then
                    echo "EXPECT_RUNNING"
                else
                    echo "EXPECT_DEAD"
                fi
            fi
            """
            check_result = _run_magpie_ssh(
                client, workspace_id,
                check_script,
                timeout=10, with_node_env=False
            )
            check_stdout = check_result.get('stdout', '').strip()

            if 'STATUS_FOUND' in check_stdout:
                if 'SUCCESS' in check_stdout or 'ALREADY_AUTH' in check_stdout:
                    logger.info(f"[CLAUDE_AUTH] Authentication successful")
                    return {
                        'status': 'success',
                        'message': 'Claude Code authenticated successfully'
                    }
                if 'ERROR' in check_stdout:
                    return {
                        'status': 'error',
                        'error': 'Authentication failed - code may be invalid or expired'
                    }
                if 'TIMEOUT' in check_stdout:
                    return {
                        'status': 'error',
                        'error': 'Authentication timed out'
                    }

            # Check if expect process died
            if 'EXPECT_DEAD' in check_stdout and not expect_restart_attempted:
                logger.warning(f"[CLAUDE_AUTH] Expect process died, cannot complete auth")
                return {
                    'status': 'error',
                    'error': 'Authentication process died. Please restart the authentication flow.'
                }

            if i % 10 == 0:
                logger.info(f"[CLAUDE_AUTH] Waiting for auth result... ({i}s)")

        return {
            'status': 'error',
            'error': 'Timeout waiting for authentication result'
        }

    except Exception as e:
        logger.error(f"[CLAUDE_AUTH] Submit code failed: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'error': str(e)
        }


def check_claude_auth_status(workspace_id: str) -> Dict[str, Any]:
    """
    Check if Claude Code is authenticated on the workspace.

    Args:
        workspace_id: Magpie workspace ID

    Returns:
        Dict with authenticated status
    """
    logger.info(f"[CLAUDE_AUTH] Checking auth status on workspace {workspace_id}")

    try:
        client = get_magpie_client()

        # First, quick check - see if credentials file exists (doesn't run Claude)
        quick_check_cmd = """
        if [ -f ~/.claude/.credentials.json ] && [ -s ~/.claude/.credentials.json ]; then
            echo "CREDS_EXIST"
            # Check if the file has valid JSON with accessToken
            if grep -q "accessToken" ~/.claude/.credentials.json 2>/dev/null; then
                echo "HAS_TOKEN"
            fi
        else
            echo "NO_CREDS"
        fi
        """
        quick_result = _run_magpie_ssh(
            client, workspace_id,
            quick_check_cmd,
            timeout=15, with_node_env=False
        )
        quick_stdout = quick_result.get('stdout', '').strip()
        logger.info(f"[CLAUDE_AUTH] Quick check result: {quick_stdout}")

        # If no credentials file, definitely not authenticated
        if 'NO_CREDS' in quick_stdout:
            return {
                'status': 'success',
                'authenticated': False,
                'message': 'Claude Code is not authenticated (no credentials)'
            }

        # If credentials exist with token, try to verify by running Claude
        if 'HAS_TOKEN' in quick_stdout:
            # Run a simple test command - source profiles and run from home directory
            check_cmd = """
            [ -f /etc/profile ] && . /etc/profile
            [ -f ~/.profile ] && . ~/.profile
            [ -f ~/.bashrc ] && . ~/.bashrc
            cd ~
            timeout 30 claude -p "reply just the word Hello" 2>&1 | head -20
            """
            result = _run_magpie_ssh(
                client, workspace_id,
                check_cmd,
                timeout=60, with_node_env=False
            )

            stdout = result.get('stdout', '').strip()
            exit_code = result.get('exit_code', 1)

            logger.info(f"[CLAUDE_AUTH] Check result: exit_code={exit_code}, stdout={stdout[:200]}")

            stdout_lower = stdout.lower()

            # Check if response contains "hello"
            if exit_code == 0 and 'hello' in stdout_lower:
                logger.info(f"[CLAUDE_AUTH] Authentication confirmed")
                return {
                    'status': 'success',
                    'authenticated': True,
                    'message': 'Claude Code is authenticated'
                }

            # If Claude was killed or timed out but credentials exist, assume authenticated
            if 'killed' in stdout_lower or exit_code == 137 or exit_code == 124:
                logger.warning(f"[CLAUDE_AUTH] Claude process was killed, but credentials exist - assuming authenticated")
                return {
                    'status': 'success',
                    'authenticated': True,
                    'message': 'Claude Code credentials found (verification skipped due to resource limits)'
                }

            # Check for common error messages
            if 'not logged in' in stdout_lower or 'authenticate' in stdout_lower or 'oauth' in stdout_lower:
                return {
                    'status': 'success',
                    'authenticated': False,
                    'message': 'Claude Code is not authenticated'
                }

            # If we have credentials but couldn't verify, assume authenticated
            logger.warning(f"[CLAUDE_AUTH] Couldn't verify but credentials exist - assuming authenticated")
            return {
                'status': 'success',
                'authenticated': True,
                'message': 'Claude Code credentials found'
            }

        # Credentials file exists but no token - not authenticated
        return {
            'status': 'success',
            'authenticated': False,
            'message': 'Claude Code credentials incomplete'
        }

    except Exception as e:
        logger.error(f"[CLAUDE_AUTH] Check status failed: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'authenticated': False,
            'error': str(e)
        }


# ============================================================================
# Claude Code CLI Execution
# ============================================================================

def run_claude_cli(
    workspace_id: str,
    prompt: str,
    session_id: str = None,
    timeout: int = 1200,
    working_dir: str = "/workspace/nextjs-app",
    project_id: str = None,
    poll_callback: Callable = None,
    lfg_env: Dict[str, str] = None
) -> Dict[str, Any]:
    """
    Run Claude Code CLI with a prompt.

    This runs Claude in background and polls for output to avoid
    the 300-second Magpie API timeout on long-running commands.

    Args:
        workspace_id: Magpie workspace ID
        prompt: The prompt to send to Claude
        session_id: Optional session ID to resume
        timeout: Command timeout in seconds
        working_dir: Working directory for Claude
        project_id: Optional project ID for environment variables
        poll_callback: Optional callback for progress updates (receives output lines)
        lfg_env: Dict of LFG environment variables (LFG_API_URL, LFG_API_KEY, LFG_TICKET_ID)

    Returns:
        Dict with status, output, session_id, and parsed messages
    """
    logger.info(f"[CLAUDE_CLI] Running on workspace {workspace_id}, session={session_id}, timeout={timeout}")

    try:
        client = get_magpie_client()

        # Create a unique timestamp for all temp files
        timestamp = int(time.time())

        # Create a unique output file for this run
        output_file = f"/tmp/claude_output_{timestamp}.jsonl"
        pid_file = f"/tmp/claude_pid_{timestamp}.txt"
        exit_code_file = f"/tmp/claude_exit_{timestamp}.txt"

        # Escape the prompt for shell - write to file to avoid escaping issues
        prompt_file = f"/tmp/claude_prompt_{timestamp}.txt"

        # Write prompt to file first
        write_prompt_cmd = f"""
cat > {prompt_file} << 'PROMPT_EOF'
{prompt}
PROMPT_EOF
echo "PROMPT_WRITTEN"
"""
        write_result = _run_magpie_ssh(
            client, workspace_id,
            write_prompt_cmd,
            timeout=30, with_node_env=False
        )

        if 'PROMPT_WRITTEN' not in write_result.get('stdout', ''):
            return {
                'status': 'error',
                'error': f"Failed to write prompt file: {write_result.get('stderr', '')}"
            }

        # Build the Claude command
        # NOTE: --dangerously-skip-permissions cannot be used when running as root
        # We'll create a non-root user and run Claude as that user
        claude_args = [
            "--model claude-opus-4-5-20251101",
            "--output-format stream-json",
            "--verbose",
            "--dangerously-skip-permissions"
        ]

        if session_id:
            claude_args.insert(0, f"--resume {session_id}")

        # Build LFG environment variable exports
        lfg_env_exports = ""
        if lfg_env:
            for key, value in lfg_env.items():
                lfg_env_exports += f"export {key}='{value}'\n"

        # Start Claude in background with output to file
        # Use a wrapper script that captures exit code
        # NOTE: Claude CLI requires -p flag with prompt, not stdin redirection
        # NOTE: --dangerously-skip-permissions requires non-root user, so we create one
        env_file = f"/tmp/claude_env_{timestamp}.sh"
        wrapper_script = f"/tmp/claude_wrapper_{timestamp}.sh"

        start_cmd = f"""
        [ -f /etc/profile ] && . /etc/profile
        [ -f ~/.profile ] && . ~/.profile
        [ -f ~/.bashrc ] && . ~/.bashrc

        # Create non-root user for Claude (--dangerously-skip-permissions requires non-root)
        if ! id -u claudeuser > /dev/null 2>&1; then
            # Try useradd (Debian/Ubuntu) first, then adduser (Alpine)
            useradd -m -s /bin/bash claudeuser 2>/dev/null || \
            adduser -D -s /bin/bash claudeuser 2>/dev/null || \
            echo "Warning: Could not create claudeuser"
        fi

        # Verify user was created
        if ! id -u claudeuser > /dev/null 2>&1; then
            echo "ERROR: Failed to create claudeuser"
            exit 1
        fi

        # Copy Claude credentials to claudeuser's home
        if [ -d /root/.claude ]; then
            cp -r /root/.claude /home/claudeuser/.claude 2>/dev/null || true
            chown -R claudeuser:claudeuser /home/claudeuser/.claude 2>/dev/null || true
            # Also make the binary executable if it exists
            chmod +x /home/claudeuser/.claude/local/claude 2>/dev/null || true
        fi

        # Give claudeuser access to workspace
        chown -R claudeuser:claudeuser {working_dir} 2>/dev/null || true
        chmod -R 755 {working_dir} 2>/dev/null || true

        # Make temp files accessible to all
        chmod 666 {prompt_file} 2>/dev/null || true
        touch {output_file} && chmod 666 {output_file}
        touch {exit_code_file} && chmod 666 {exit_code_file}

        # Write env vars to a file that claudeuser can source
        cat > {env_file} << 'ENVEOF'
{lfg_env_exports}
ENVEOF
        chmod 644 {env_file}

        # Find the actual path to claude binary
        # Check claudeuser's home first (copied), then root locations
        CLAUDE_BIN=""
        for path in /home/claudeuser/.claude/local/claude /root/.claude/local/claude /root/.local/bin/claude /usr/local/bin/claude $(which claude 2>/dev/null); do
            if [ -x "$path" ]; then
                CLAUDE_BIN="$path"
                break
            fi
        done

        if [ -z "$CLAUDE_BIN" ]; then
            echo "ERROR: Could not find claude binary"
            echo "Checked paths: /home/claudeuser/.claude/local/claude, /root/.claude/local/claude, /root/.local/bin/claude, /usr/local/bin/claude"
            exit 1
        fi
        echo "FOUND_CLAUDE=$CLAUDE_BIN"

        # If using root's claude binary, ensure it's accessible
        if [[ "$CLAUDE_BIN" == /root/* ]]; then
            chmod 755 /root 2>/dev/null || true
            chmod -R 755 $(dirname "$CLAUDE_BIN") 2>/dev/null || true
        fi

        # Create wrapper script that claudeuser will run
        # Use the absolute path to claude to avoid PATH issues
        cat > {wrapper_script} << WRAPPEREOF
#!/bin/bash
# Ensure HOME is set correctly for claudeuser (claude looks for config in HOME/.claude)
export HOME=/home/claudeuser
source {env_file}
cd {working_dir}
$CLAUDE_BIN -p "\\$(cat {prompt_file})" {' '.join(claude_args)}
WRAPPEREOF
        chmod 755 {wrapper_script}

        # Run Claude as non-root user in background
        (
            su - claudeuser -c "{wrapper_script}" > {output_file} 2>&1
            echo $? > {exit_code_file}
        ) &

        CLAUDE_PID=$!
        echo $CLAUDE_PID > {pid_file}
        echo "STARTED_PID=$CLAUDE_PID"
        """

        start_result = _run_magpie_ssh(
            client, workspace_id,
            start_cmd,
            timeout=60, with_node_env=True, project_id=project_id
        )

        start_stdout = start_result.get('stdout', '')
        start_stderr = start_result.get('stderr', '')
        logger.info(f"[CLAUDE_CLI] Start result: {start_stdout[:500]}")
        if start_stderr:
            logger.info(f"[CLAUDE_CLI] Start stderr: {start_stderr[:200]}")

        # Check for specific errors
        if 'ERROR: Could not find claude binary' in start_stdout:
            return {
                'status': 'error',
                'error': 'Claude CLI not installed. Please ensure Claude Code is installed in the workspace.'
            }

        if 'ERROR: Failed to create claudeuser' in start_stdout:
            return {
                'status': 'error',
                'error': 'Could not create non-root user for Claude CLI execution.'
            }

        if 'STARTED_PID=' not in start_stdout:
            return {
                'status': 'error',
                'error': f"Failed to start Claude: {start_stderr if start_stderr else start_stdout[:300]}"
            }

        # Poll for completion
        poll_interval = 5  # seconds
        max_polls = timeout // poll_interval
        last_output_size = 0
        all_output = ""

        for poll_num in range(max_polls):
            time.sleep(poll_interval)

            # Check if process is still running and get new output
            poll_cmd = f"""
            # Check if process is running
            if [ -f {pid_file} ]; then
                PID=$(cat {pid_file})
                if kill -0 $PID 2>/dev/null; then
                    echo "STATUS=RUNNING"
                else
                    echo "STATUS=DONE"
                fi
            else
                echo "STATUS=NO_PID"
            fi

            # Check for exit code
            if [ -f {exit_code_file} ]; then
                echo "EXIT_CODE=$(cat {exit_code_file})"
            fi

            # Get output file size
            if [ -f {output_file} ]; then
                echo "OUTPUT_SIZE=$(wc -c < {output_file})"
                # Read new output (from last position)
                tail -c +{last_output_size + 1} {output_file} 2>/dev/null || cat {output_file}
            else
                echo "OUTPUT_SIZE=0"
            fi
            """

            poll_result = _run_magpie_ssh(
                client, workspace_id,
                poll_cmd,
                timeout=60, with_node_env=False
            )

            poll_stdout = poll_result.get('stdout', '')

            # Parse status
            status_match = re.search(r'STATUS=(\w+)', poll_stdout)
            status = status_match.group(1) if status_match else 'UNKNOWN'

            # Parse output size
            size_match = re.search(r'OUTPUT_SIZE=(\d+)', poll_stdout)
            current_size = int(size_match.group(1)) if size_match else 0

            # Parse exit code if available
            exit_match = re.search(r'EXIT_CODE=(\d+)', poll_stdout)
            exit_code = int(exit_match.group(1)) if exit_match else None

            # Extract new output (everything after the STATUS and OUTPUT_SIZE lines)
            new_output_lines = []
            capture_output = False
            for line in poll_stdout.split('\n'):
                if capture_output:
                    new_output_lines.append(line)
                elif line.startswith('OUTPUT_SIZE='):
                    capture_output = True

            new_output = '\n'.join(new_output_lines)

            # Log extraction details for debugging
            if current_size > last_output_size:
                logger.info(f"[CLAUDE_CLI] Poll {poll_num}: output grew {last_output_size} -> {current_size} (+{current_size - last_output_size} bytes)")
                logger.info(f"[CLAUDE_CLI] Extracted {len(new_output)} chars, lines captured: {len(new_output_lines)}")
                if new_output_lines:
                    first_line = new_output_lines[0][:100] if new_output_lines[0] else "(empty)"
                    logger.info(f"[CLAUDE_CLI] First extracted line: {first_line}")

            if new_output.strip():
                all_output += new_output
                if poll_callback:
                    try:
                        # Log what we're sending to callback for debugging
                        json_line_count = sum(1 for line in new_output.split('\n') if line.strip().startswith('{'))
                        logger.info(f"[CLAUDE_CLI] Sending {len(new_output)} bytes ({json_line_count} JSON lines) to callback")
                        poll_callback(new_output)
                    except Exception as e:
                        logger.warning(f"[CLAUDE_CLI] Poll callback error: {e}")

            last_output_size = current_size

            # Log progress
            if poll_num % 6 == 0:  # Log every 30 seconds
                logger.info(f"[CLAUDE_CLI] Poll {poll_num}: status={status}, output_size={current_size}, exit_code={exit_code}")

            # Check if done
            if status == 'DONE' or exit_code is not None:
                logger.info(f"[CLAUDE_CLI] Completed with exit_code={exit_code}")

                # Always get full output when done for accuracy
                final_cmd = f"cat {output_file} 2>/dev/null || echo ''"
                final_result = _run_magpie_ssh(
                    client, workspace_id,
                    final_cmd,
                    timeout=60, with_node_env=False
                )
                all_output = final_result.get('stdout', '')

                # Log the actual output for debugging (especially important for errors)
                output_preview = all_output[:1000] if all_output else "(empty)"
                logger.info(f"[CLAUDE_CLI] Output ({len(all_output)} bytes): {output_preview}")

                # Clean up temp files (including wrapper script and env file)
                cleanup_cmd = f"rm -f {prompt_file} {output_file} {pid_file} {exit_code_file} {env_file} {wrapper_script}"
                _run_magpie_ssh(client, workspace_id, cleanup_cmd, timeout=30, with_node_env=False)

                # Parse the JSON stream output
                parsed = parse_claude_json_stream(all_output)

                return {
                    'status': 'success' if exit_code == 0 else 'error',
                    'exit_code': exit_code or 0,
                    'stdout': all_output,
                    'stderr': '',
                    'session_id': parsed.get('session_id'),
                    'messages': parsed.get('messages', []),
                    'final_result': parsed.get('final_result'),
                    'error': None if exit_code == 0 else f"Claude exited with code {exit_code}"
                }

        # Timeout - kill the process
        logger.warning(f"[CLAUDE_CLI] Timeout after {timeout}s, killing process")

        kill_cmd = f"""
        if [ -f {pid_file} ]; then
            PID=$(cat {pid_file})
            kill -9 $PID 2>/dev/null || true
        fi
        # Get whatever output we have
        cat {output_file} 2>/dev/null || echo ''
        # Cleanup
        rm -f {prompt_file} {output_file} {pid_file} {exit_code_file} {env_file} {wrapper_script}
        """

        kill_result = _run_magpie_ssh(
            client, workspace_id,
            kill_cmd,
            timeout=60, with_node_env=False
        )

        all_output = kill_result.get('stdout', '')
        parsed = parse_claude_json_stream(all_output)

        return {
            'status': 'error',
            'exit_code': -1,
            'stdout': all_output,
            'stderr': '',
            'session_id': parsed.get('session_id'),
            'messages': parsed.get('messages', []),
            'final_result': parsed.get('final_result'),
            'error': f'Timeout after {timeout} seconds'
        }

    except Exception as e:
        logger.error(f"[CLAUDE_CLI] Execution failed: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'error': str(e)
        }


def parse_claude_json_stream(output: str) -> Dict[str, Any]:
    """
    Parse Claude CLI JSON stream output.

    JSON message structure (Claude Code CLI):
    - {"type":"system","subtype":"init","session_id":"..."} - Session init
    - {"type":"assistant","message":{"content":[{"type":"text","text":"..."}]}} - AI text response
    - {"type":"assistant","message":{"content":[{"type":"tool_use","name":"...","input":{}}]}} - Tool use
    - {"type":"user","message":{"content":[{"type":"tool_result","content":"..."}]}} - Tool result
    - {"type":"result","result":"..."} - Final result

    Args:
        output: Raw stdout from Claude CLI

    Returns:
        Dict with session_id, messages list, and final_result
    """
    result = {
        'session_id': None,
        'messages': [],
        'final_result': None
    }

    for line in output.split('\n'):
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
            msg_type = msg.get('type')

            if msg_type == 'system' and msg.get('subtype') == 'init':
                result['session_id'] = msg.get('session_id')
                result['messages'].append({
                    'type': 'system_init',
                    'session_id': msg.get('session_id'),
                    'timestamp': datetime.now().isoformat()
                })

            elif msg_type == 'assistant':
                # Parse content blocks from assistant message
                content_blocks = msg.get('message', {}).get('content', [])
                if not isinstance(content_blocks, list):
                    content_blocks = [content_blocks] if content_blocks else []

                text_parts = []
                for block in content_blocks:
                    if isinstance(block, dict):
                        block_type = block.get('type')

                        if block_type == 'text':
                            # Text content
                            text = block.get('text', '')
                            if text:
                                text_parts.append(text)

                        elif block_type == 'tool_use':
                            # Tool use is inside assistant message content
                            tool_name = block.get('name', 'unknown')
                            tool_input = block.get('input', {})

                            # Add as separate tool_use message
                            result['messages'].append({
                                'type': 'tool_use',
                                'name': tool_name,
                                'input': tool_input,
                                'timestamp': datetime.now().isoformat()
                            })

                    elif isinstance(block, str):
                        text_parts.append(block)

                # If there was text content, add as assistant message
                if text_parts:
                    content = '\n'.join(text_parts)
                    result['messages'].append({
                        'type': 'assistant',
                        'content': content,
                        'timestamp': datetime.now().isoformat()
                    })

            elif msg_type == 'user':
                # Parse content blocks from user message (usually tool results)
                content_blocks = msg.get('message', {}).get('content', [])
                if not isinstance(content_blocks, list):
                    content_blocks = [content_blocks] if content_blocks else []

                for block in content_blocks:
                    if isinstance(block, dict):
                        block_type = block.get('type')

                        if block_type == 'tool_result':
                            tool_content = block.get('content', '')
                            # Handle content that might be a list or dict
                            if isinstance(tool_content, (list, dict)):
                                tool_content = json.dumps(tool_content, indent=2)
                            result['messages'].append({
                                'type': 'tool_result',
                                'content': str(tool_content)[:5000],  # Truncate long results
                                'is_error': block.get('is_error', False),
                                'timestamp': datetime.now().isoformat()
                            })

            elif msg_type == 'result':
                result['final_result'] = msg.get('result')
                result['messages'].append({
                    'type': 'result',
                    'result': msg.get('result'),
                    'timestamp': datetime.now().isoformat()
                })

        except json.JSONDecodeError:
            # Non-JSON line, might be raw output
            if line and not line.startswith('{'):
                result['messages'].append({
                    'type': 'raw_output',
                    'content': line,
                    'timestamp': datetime.now().isoformat()
                })

    return result


def create_ticket_logs_from_claude_output(
    ticket_id: int,
    parsed_output: Dict[str, Any],
    broadcast_func: Callable = None
) -> List[Dict[str, Any]]:
    """
    Create TicketLog entries from parsed Claude CLI output.

    Args:
        ticket_id: The ticket ID
        parsed_output: Output from parse_claude_json_stream()
        broadcast_func: Optional function to broadcast logs via WebSocket

    Returns:
        List of created log entries
    """
    from projects.models import TicketLog
    from projects.websocket_utils import async_send_ticket_log_notification
    from asgiref.sync import async_to_sync

    logs_created = []

    for msg in parsed_output.get('messages', []):
        msg_type = msg.get('type')
        log_entry = None

        if msg_type == 'assistant':
            content = msg.get('content', '')
            if content:
                log_entry = TicketLog.objects.create(
                    ticket_id=ticket_id,
                    log_type='ai_response',
                    command='Claude Code',  # Short command name
                    output=content[:10000]  # Full content in output
                )

        elif msg_type == 'tool_use':
            tool_name = msg.get('name', 'unknown')
            tool_input = msg.get('input', {})

            # Format tool input nicely
            if tool_name == 'Bash':
                # For bash commands, show the command itself
                command_text = tool_input.get('command', '')
                description = tool_input.get('description', '')
                explanation = description if description else f"Running: {command_text[:100]}"
                output_text = command_text
            elif tool_name == 'Read':
                file_path = tool_input.get('file_path', '')
                explanation = f"Reading file: {file_path}"
                output_text = f"File: {file_path}"
            elif tool_name == 'Write':
                file_path = tool_input.get('file_path', '')
                content = tool_input.get('content', '')
                explanation = f"Writing file: {file_path}"
                output_text = f"File: {file_path}\n\n{content[:3000]}"
            elif tool_name == 'Edit':
                file_path = tool_input.get('file_path', '')
                old_string = tool_input.get('old_string', '')[:200]
                new_string = tool_input.get('new_string', '')[:500]
                explanation = f"Editing file: {file_path}"
                output_text = f"File: {file_path}\n\nOld:\n{old_string}\n\nNew:\n{new_string}"
            elif tool_name == 'Glob':
                pattern = tool_input.get('pattern', '')
                explanation = f"Searching for: {pattern}"
                output_text = f"Pattern: {pattern}"
            elif tool_name == 'Grep':
                pattern = tool_input.get('pattern', '')
                path = tool_input.get('path', '')
                explanation = f"Searching for '{pattern}' in {path or 'codebase'}"
                output_text = json.dumps(tool_input, indent=2)
            else:
                explanation = f"Using tool: {tool_name}"
                output_text = json.dumps(tool_input, indent=2)

            log_entry = TicketLog.objects.create(
                ticket_id=ticket_id,
                log_type='command',
                command=tool_name,
                explanation=explanation[:500],
                output=output_text[:5000]
            )

        elif msg_type == 'tool_result':
            content = msg.get('content', '')
            is_error = msg.get('is_error', False)

            # Only log tool results if they're errors or significant
            if is_error or len(str(content)) > 100:
                log_entry = TicketLog.objects.create(
                    ticket_id=ticket_id,
                    log_type='command',
                    command='Result' + (' (Error)' if is_error else ''),
                    explanation='Tool execution result',
                    output=str(content)[:10000]
                )

        if log_entry:
            logs_created.append({
                'id': log_entry.id,
                'type': msg_type,
                'created_at': log_entry.created_at.isoformat()
            })

            # Broadcast via WebSocket
            if broadcast_func:
                try:
                    broadcast_func(ticket_id, {
                        'id': log_entry.id,
                        'log_type': log_entry.log_type,
                        'command': log_entry.command,
                        'explanation': getattr(log_entry, 'explanation', ''),
                        'output': log_entry.output[:2000],  # Truncate for WebSocket
                        'created_at': log_entry.created_at.isoformat()
                    })
                except Exception as e:
                    logger.warning(f"[CLAUDE_CLI] Failed to broadcast log: {e}")

    return logs_created
