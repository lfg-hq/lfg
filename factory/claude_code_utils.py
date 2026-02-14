"""
Claude Code CLI Utilities

Provides functions for:
- Claude Code CLI authentication in Mags workspaces
- Running Claude CLI commands with streaming output via paramiko
- Parsing Claude CLI JSON stream output

Note: S3 backup/restore is no longer needed — Mags workspace overlays
auto-persist .claude/ credentials across sessions.
"""

import json
import logging
import re
import time
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime

from factory.mags import (
    run_command,
    MAGS_WORKING_DIR,
    MAGS_PROJECT_DIR,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Claude Code CLI Authentication
# ============================================================================

def start_claude_auth(workspace_id: str) -> Dict[str, Any]:
    """
    Start Claude Code authentication process on a Mags workspace.

    This runs `claude` in a background expect process and captures the OAuth URL.
    The expect process waits for a code file to be written, then submits the code.

    Args:
        workspace_id: Mags workspace overlay name

    Returns:
        Dict with status and oauth_url (if authentication needed)
    """
    logger.info(f"[CLAUDE_AUTH] Starting auth on workspace {workspace_id}")

    try:
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

        # Create the expect script
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

        result = run_command(
            workspace_id, setup_script,
            timeout=60, with_node_env=False,
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

        bg_result = run_command(
            workspace_id, bg_script,
            timeout=30, with_node_env=False,
        )

        logger.info(f"[CLAUDE_AUTH] Background process started: {bg_result.get('stdout', '')[:100]}")

        # Track retry count for expect process restarts
        expect_restart_count = 0
        max_expect_restarts = 3

        # Wait for URL file to appear (poll for up to 60 seconds)
        for i in range(60):
            time.sleep(1)
            check_script = r"""
            # First check if URL file exists AND has full URL (>100 chars)
            if [ -f /tmp/claude_url.txt ]; then
                FILE_URL=$(cat /tmp/claude_url.txt)
                if [ ${#FILE_URL} -gt 100 ]; then
                    echo "URL_FOUND"
                    echo "$FILE_URL"
                    exit 0
                else
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
                URL=$(grep -v -E 'WAITING|LOG_|CAPTURED|Paste|code here|prompted|spawn|expect' /tmp/claude_auth.log | tr -d '\n\r' | grep -oE 'https://claude\.ai/oauth[A-Za-z0-9_.~:/?#@!$&()*+,;=%=-]+' | head -1)
                URL=$(echo "$URL" | sed 's/Paste.*//; s/code.*here.*//; s/prompted.*//')
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
            check_result = run_command(
                workspace_id, check_script,
                timeout=10, with_node_env=False,
            )
            check_stdout = check_result.get('stdout', '').strip()

            if 'URL_FOUND' in check_stdout:
                lines = check_stdout.split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith('https://claude.ai/oauth'):
                        clean_url = re.sub(r'\x1b\[[0-9;]*m', '', line)
                        clean_url = re.sub(r'[\x00-\x1f\x7f]', '', clean_url)
                        logger.info(f"[CLAUDE_AUTH] Got OAuth URL (full, {len(clean_url)} chars): {clean_url}")
                        return {
                            'status': 'pending',
                            'oauth_url': clean_url,
                            'message': 'Open the URL and authenticate, then paste the code'
                        }

            if i < 3 and 'WAITING' in check_stdout:
                logger.info(f"[CLAUDE_AUTH] Full debug output ({i}s, {len(check_stdout)} chars):\n{check_stdout}")
            elif 'WAITING' in check_stdout:
                if 'NO_EXPECT_RUNNING' in check_stdout:
                    if expect_restart_count < max_expect_restarts:
                        expect_restart_count += 1
                        logger.warning(f"[CLAUDE_AUTH] Expect process died, restarting (attempt {expect_restart_count}/{max_expect_restarts})")

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
                        restart_result = run_command(
                            workspace_id, restart_script,
                            timeout=30, with_node_env=False,
                        )
                        logger.info(f"[CLAUDE_AUTH] Restart result: {restart_result.get('stdout', '')[:100]}")
                        time.sleep(3)
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

    Args:
        workspace_id: Mags workspace overlay name
        auth_code: OAuth code from user

    Returns:
        Dict with status
    """
    logger.info(f"[CLAUDE_AUTH] Submitting auth code to workspace {workspace_id}")

    try:
        auth_code = auth_code.strip()

        write_script = f"""
        echo '{auth_code}' > /tmp/claude_code.txt
        echo "CODE_WRITTEN"
        """

        result = run_command(
            workspace_id, write_script,
            timeout=30, with_node_env=False,
        )

        if 'CODE_WRITTEN' not in result.get('stdout', ''):
            return {
                'status': 'error',
                'error': 'Failed to write auth code to file'
            }

        logger.info(f"[CLAUDE_AUTH] Code written, waiting for auth to complete...")

        for i in range(120):
            time.sleep(1)
            check_script = """
            if [ -f /tmp/claude_status.txt ]; then
                echo "STATUS_FOUND"
                cat /tmp/claude_status.txt
            else
                echo "WAITING"
                if pgrep -x expect > /dev/null; then
                    echo "EXPECT_RUNNING"
                else
                    echo "EXPECT_DEAD"
                fi
            fi
            """
            check_result = run_command(
                workspace_id, check_script,
                timeout=10, with_node_env=False,
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

            if 'EXPECT_DEAD' in check_stdout:
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
        workspace_id: Mags workspace overlay name

    Returns:
        Dict with authenticated status
    """
    logger.info(f"[CLAUDE_AUTH] Checking auth status on {workspace_id}")

    def _exec(cmd, timeout=15):
        return run_command(workspace_id=workspace_id, command=cmd, timeout=timeout, with_node_env=False)

    try:
        quick_check_cmd = """
        if [ -f ~/.claude/.credentials.json ] && [ -s ~/.claude/.credentials.json ]; then
            echo "CREDS_EXIST"
            if grep -q "accessToken" ~/.claude/.credentials.json 2>/dev/null; then
                echo "HAS_TOKEN"
            fi
        else
            echo "NO_CREDS"
        fi
        """
        quick_result = _exec(quick_check_cmd, timeout=15)
        quick_stdout = quick_result.get('stdout', '').strip()
        logger.info(f"[CLAUDE_AUTH] Quick check result: {quick_stdout}")

        if 'NO_CREDS' in quick_stdout:
            return {
                'status': 'success',
                'authenticated': False,
                'message': 'Claude Code is not authenticated (no credentials)',
            }

        if 'HAS_TOKEN' in quick_stdout:
            check_cmd = """
            [ -f /etc/profile ] && . /etc/profile
            [ -f ~/.profile ] && . ~/.profile
            [ -f ~/.bashrc ] && . ~/.bashrc
            cd ~
            timeout 12 claude -p "reply just the word Hello" 2>&1 | head -20
            """
            result = _exec(check_cmd, timeout=20)

            stdout = result.get('stdout', '').strip()
            exit_code = result.get('exit_code', 1)

            logger.info(f"[CLAUDE_AUTH] Check result: exit_code={exit_code}, stdout={stdout[:200]}")

            stdout_lower = stdout.lower()

            if exit_code == 0 and 'hello' in stdout_lower:
                logger.info(f"[CLAUDE_AUTH] Authentication confirmed")
                return {
                    'status': 'success',
                    'authenticated': True,
                    'message': 'Claude Code is authenticated',
                }

            if 'killed' in stdout_lower or exit_code == 137 or exit_code == 124:
                logger.warning(f"[CLAUDE_AUTH] Claude process was killed, but credentials exist - assuming authenticated")
                return {
                    'status': 'success',
                    'authenticated': True,
                    'message': 'Claude Code credentials found (verification skipped due to resource limits)',
                }

            if ('not logged in' in stdout_lower or
                'authenticate' in stdout_lower or
                'oauth' in stdout_lower or
                'expired' in stdout_lower or
                'authentication_error' in stdout_lower or
                'please run /login' in stdout_lower):
                logger.warning(f"[CLAUDE_AUTH] Auth error detected in output: {stdout[:300]}")
                return {
                    'status': 'success',
                    'authenticated': False,
                    'message': 'Claude Code token expired or invalid. Please reconnect.',
                    'token_expired': True,
                }

            logger.warning(f"[CLAUDE_AUTH] Couldn't verify but credentials exist - assuming authenticated")
            return {
                'status': 'success',
                'authenticated': True,
                'message': 'Claude Code credentials found',
            }

        return {
            'status': 'success',
            'authenticated': False,
            'message': 'Claude Code credentials incomplete',
        }

    except Exception as e:
        logger.error(f"[CLAUDE_AUTH] Check status failed: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'authenticated': False,
            'error': str(e),
        }


# ============================================================================
# Claude Code CLI Execution
# ============================================================================

def run_claude_cli(
    workspace_id: str,
    prompt: str,
    session_id: str = None,
    timeout: int = 1200,
    working_dir: str = None,
    project_id: str = None,
    poll_callback: Callable = None,
    lfg_env: Dict[str, str] = None,
) -> Dict[str, Any]:
    """
    Run Claude Code CLI with a prompt using Mags SDK native execution.

    Claude CLI runs in the background with output redirected to a JSONL file.
    A shell polling loop reads new content every ~5 seconds and echoes it to
    stdout, which is captured by the Mags SDK log polling.

    Args:
        workspace_id: Mags workspace overlay name (e.g. "ticket-147-p13")
        prompt: The prompt to send to Claude
        session_id: Optional session ID to resume
        timeout: Command timeout in seconds
        working_dir: Working directory for Claude (defaults to MAGS_WORKING_DIR)
        project_id: Optional project ID for environment variables
        poll_callback: Optional callback for progress updates (receives output lines)
        lfg_env: Dict of LFG environment variables

    Returns:
        Dict with status, output, session_id, and parsed messages
    """
    import base64

    if working_dir is None:
        working_dir = MAGS_WORKING_DIR

    logger.info(f"[CLAUDE_CLI] Running on workspace {workspace_id}, session={session_id}, timeout={timeout}")

    try:
        timestamp = int(time.time())
        prompt_file = f"/tmp/claude_prompt_{timestamp}.txt"

        # Build Claude command arguments
        claude_args = [
            "--model claude-opus-4-5-20251101",
            "--output-format stream-json",
            "--verbose",
            "--dangerously-skip-permissions"
        ]

        if session_id:
            claude_args.insert(0, f"--resume {session_id}")

        claude_args_str = ' '.join(claude_args)

        # Build LFG environment variable exports
        lfg_env_exports = ""
        if lfg_env:
            for key, value in lfg_env.items():
                lfg_env_exports += f"export {key}='{value}'\n"

        env_file = f"/tmp/claude_env_{timestamp}.sh"
        runner_script = f"/tmp/claude_runner_{timestamp}.sh"
        output_file = f"/tmp/claude_output_{timestamp}.jsonl"

        # Known claude binary location (installed in base workspace)
        claude_bin_path = "/usr/local/bin/claude"

        # Step 3: Start Claude CLI in background via exec()
        # Claude CLI refuses --dangerously-skip-permissions as root, so we run
        # as a non-root user (claudeuser) created in CLAUDE_AUTH_SETUP_SCRIPT.
        #
        # Strategy: write a small runner script, start it via nohup/su in
        # background, then poll the output file via exec() for streaming.
        # This avoids relying on Mags logs() API (which only returns platform
        # logs, not script stdout).
        runner_content = f"""#!/bin/bash
export HOME=/home/claudeuser
export PATH=/root/node/current/bin:/root/.npm-global/bin:$PATH
export NPM_CONFIG_CACHE=/home/claudeuser/.npm
export npm_config_cache=/home/claudeuser/.npm
umask 000
source {env_file}
cd {working_dir}
{claude_bin_path} -p "$(cat {prompt_file})" {claude_args_str} > {output_file} 2>&1
CLAUDE_EXIT=$?
echo "" >> {output_file}
echo "___CLAUDE_EXIT_CODE=$CLAUDE_EXIT" >> {output_file}
"""
        runner_b64 = base64.b64encode(runner_content.encode('utf-8')).decode('ascii')
        prompt_b64 = base64.b64encode(prompt.encode('utf-8')).decode('ascii')
        env_b64 = base64.b64encode(lfg_env_exports.encode('utf-8')).decode('ascii') if lfg_env_exports else ""

        # Single combined command: write all files + setup user + launch Claude
        # This replaces 3 separate exec() calls with 1.
        start_cmd = f"""export HOME=/root

# Write prompt and env files via base64 (avoids shell escaping issues)
echo '{prompt_b64}' | base64 -d > {prompt_file}
echo '{env_b64}' | base64 -d > {env_file}

# Verify credentials exist
if [ ! -f /root/.claude/.credentials.json ]; then
    echo "ERROR: No credentials found at /root/.claude"
    exit 1
fi

# Verify claude binary exists
if [ ! -x {claude_bin_path} ]; then
    echo "ERROR: Claude binary not found at {claude_bin_path}"
    exit 1
fi

# Setup non-root user for Claude CLI
CLAUDE_USER=claudeuser
CLAUDE_HOME=/home/$CLAUDE_USER
id $CLAUDE_USER >/dev/null 2>&1 || adduser -D -h $CLAUDE_HOME -s /bin/bash $CLAUDE_USER

# Copy credential files
mkdir -p $CLAUDE_HOME/.claude
for f in .credentials.json settings.json statsig.json; do
    [ -f /root/.claude/$f ] && cp /root/.claude/$f $CLAUDE_HOME/.claude/$f
done
chown -R $CLAUDE_USER:$CLAUDE_USER $CLAUDE_HOME/.claude

# Set permissions — MUST NOT add group/other write to /root (breaks SSH StrictModes)
chmod o+rx /root 2>/dev/null || true
if [ -d {working_dir}/project ]; then
    chown -R $CLAUDE_USER:$CLAUDE_USER {working_dir}/project 2>/dev/null || chmod -R o+rwx {working_dir}/project 2>/dev/null || true
fi
mkdir -p $CLAUDE_HOME/.npm
chown -R $CLAUDE_USER:$CLAUDE_USER $CLAUDE_HOME/.npm
chmod 666 {prompt_file} 2>/dev/null || true
chmod 644 {env_file} 2>/dev/null || true
chmod o+rx /root/node /root/node/current /root/node/current/bin /root/node/current/lib 2>/dev/null || true
chmod o+rx /root/node/current/bin/* 2>/dev/null || true
chmod o+rx $(dirname {claude_bin_path}) {claude_bin_path} 2>/dev/null || true
chmod o+rx /root/.npm-global /root/.npm-global/bin /root/.npm-global/lib 2>/dev/null || true
chmod o+rx /root/.npm-global/bin/* 2>/dev/null || true

# Create output file + write runner script
touch {output_file}
chmod 666 {output_file}
echo '{runner_b64}' | base64 -d > {runner_script}
chmod 755 {runner_script}

# Start Claude CLI in background
nohup su -s /bin/bash $CLAUDE_USER -c "bash {runner_script}" > /dev/null 2>&1 &
echo "___CLAUDE_BG_PID=$!"
echo "CLAUDE_STARTED"
"""

        start_result = run_command(
            workspace_id, start_cmd,
            timeout=180, with_node_env=True,
            project_id=project_id,
        )
        start_stdout = start_result.get('stdout', '')

        # Check for specific errors
        if 'ERROR: No credentials found' in start_stdout:
            return {'status': 'error', 'error': 'No Claude credentials found. Please connect Claude Code in Settings first.'}
        if 'ERROR: Claude binary not found' in start_stdout:
            return {'status': 'error', 'error': 'Claude CLI not installed in workspace.'}
        if 'CLAUDE_STARTED' not in start_stdout:
            return {
                'status': 'error',
                'error': f"Failed to start Claude CLI: {start_stdout[:300]}"
            }

        # Extract background PID for process checking
        bg_pid = None
        for line in start_stdout.split('\n'):
            if line.strip().startswith('___CLAUDE_BG_PID='):
                try:
                    bg_pid = int(line.strip().split('=', 1)[1])
                except (ValueError, IndexError):
                    pass
                break

        logger.info(f"[CLAUDE_CLI] Claude started in background, PID={bg_pid}")

        # Verify workspace is still accessible with a quick probe before polling
        try:
            probe_result = run_command(
                workspace_id, f"ls -la {output_file} 2>&1 && echo PROBE_OK",
                timeout=30, with_node_env=False
            )
            probe_out = probe_result.get('stdout', '')
            probe_exit = probe_result.get('exit_code', -1)
            probe_stderr = probe_result.get('stderr', '')
            logger.info(
                f"[CLAUDE_CLI] Probe: exit={probe_exit} stdout={probe_out[:200]} stderr={probe_stderr[:200]}"
            )
            if probe_exit == 255:
                logger.error(f"[CLAUDE_CLI] SSH probe failed — workspace may be unreachable: {probe_stderr[:200]}")
        except Exception as probe_err:
            logger.warning(f"[CLAUDE_CLI] Probe error: {probe_err}")

        # Step 4: Poll output file via exec() — real-time streaming to callback
        # The runner writes Claude's stream-json output to output_file.
        # We periodically exec() into the VM to read new bytes and feed them
        # to the callback, which creates TicketLog entries + WebSocket broadcasts.
        offset = 0
        all_output = ""
        poll_start = time.time()
        consecutive_ssh_failures = 0
        MAX_SSH_FAILURES = 5

        while time.time() - poll_start < timeout:
            time.sleep(5)

            # Read new bytes from output file + check process status
            pid_check = f'kill -0 {bg_pid} 2>/dev/null && echo "yes" || echo "no"' if bg_pid else 'echo "unknown"'
            poll_cmd = f"""CURSIZE=$(wc -c < {output_file} 2>/dev/null || echo 0)
NEWBYTES=$((CURSIZE - {offset}))
if [ "$NEWBYTES" -gt 0 ]; then
    tail -c +{offset + 1} {output_file} | head -c $NEWBYTES
fi
ALIVE=$({pid_check})
printf '\\n__MAGS_POLL_BOUNDARY__\\nSIZE=%s ALIVE=%s\\n' "$CURSIZE" "$ALIVE"
"""

            try:
                poll_result = run_command(workspace_id, poll_cmd, timeout=30, with_node_env=False)
                poll_exit = poll_result.get('exit_code', -1)
                poll_stdout = poll_result.get('stdout', '')
                poll_stderr = poll_result.get('stderr', '')

                # Detect SSH-level failures (exit_code=255 or -1 with empty stdout)
                if poll_exit in (255, -1) and not poll_stdout:
                    consecutive_ssh_failures += 1
                    logger.warning(
                        f"[CLAUDE_CLI] Poll SSH failure #{consecutive_ssh_failures}/{MAX_SSH_FAILURES}: "
                        f"exit={poll_exit} stderr={poll_stderr[:200]}"
                    )
                    if consecutive_ssh_failures >= MAX_SSH_FAILURES:
                        logger.error("[CLAUDE_CLI] Too many consecutive SSH failures, aborting poll loop")
                        break
                    continue  # Skip parsing, retry on next iteration
                consecutive_ssh_failures = 0  # Reset on any successful exec

                POLL_BOUNDARY = '__MAGS_POLL_BOUNDARY__'
                new_content = ""
                poll_size = offset
                process_alive = True

                if POLL_BOUNDARY in poll_stdout:
                    boundary_idx = poll_stdout.rfind(POLL_BOUNDARY)
                    new_content = poll_stdout[:boundary_idx].rstrip('\n')
                    meta_str = poll_stdout[boundary_idx + len(POLL_BOUNDARY):]

                    size_match = re.search(r'SIZE=(\d+)', meta_str)
                    alive_match = re.search(r'ALIVE=(\w+)', meta_str)
                    if size_match:
                        poll_size = int(size_match.group(1))
                    if alive_match:
                        process_alive = alive_match.group(1) == 'yes'

                if new_content:
                    offset = poll_size
                    all_output += new_content + '\n'
                    if poll_callback:
                        try:
                            poll_callback(new_content + '\n')
                        except Exception as cb_err:
                            logger.warning(f"[CLAUDE_CLI] Callback error: {cb_err}")
                else:
                    offset = poll_size

                logger.debug(
                    f"[CLAUDE_CLI] Poll: offset={offset}, new={len(new_content)}, "
                    f"total={len(all_output)}, alive={process_alive}"
                )

                # Check completion
                if '___CLAUDE_EXIT_CODE=' in all_output:
                    break

                if not process_alive:
                    # Process finished — wait for final writes then exit
                    time.sleep(2)
                    break

            except Exception as poll_err:
                logger.debug(f"[CLAUDE_CLI] Poll error: {poll_err}")

        # Final read to catch any remaining output after loop exit
        try:
            final_cmd = f"""CURSIZE=$(wc -c < {output_file} 2>/dev/null || echo 0)
if [ "$CURSIZE" -gt {offset} ]; then
    tail -c +{offset + 1} {output_file}
fi
"""
            fr = run_command(workspace_id, final_cmd, timeout=30, with_node_env=False)
            fc = fr.get('stdout', '').rstrip('\n')
            if fc:
                all_output += fc + '\n'
                if poll_callback:
                    try:
                        poll_callback(fc + '\n')
                    except Exception:
                        pass
        except Exception:
            pass

        # Extract exit code from output marker
        exit_code = -1
        for line in reversed(all_output.split('\n')):
            line_s = line.strip()
            if line_s.startswith('___CLAUDE_EXIT_CODE='):
                try:
                    exit_code = int(line_s.split('=', 1)[1])
                except (ValueError, IndexError):
                    pass
                break

        # If we never got the exit code marker (SSH died mid-execution) but
        # collected substantial output, check if Claude produced a final result.
        # A {"type":"result"} JSON line indicates Claude completed normally.
        if exit_code == -1 and len(all_output) > 1000:
            import json as _json
            for line in reversed(all_output.split('\n')):
                line_s = line.strip()
                if not line_s:
                    continue
                try:
                    obj = _json.loads(line_s)
                    if obj.get('type') == 'result':
                        logger.info("[CLAUDE_CLI] Found result object in output — treating as success despite missing exit code")
                        exit_code = 0
                        break
                except (ValueError, _json.JSONDecodeError):
                    continue

        logger.info(f"[CLAUDE_CLI] Completed: exit_code={exit_code}, output_len={len(all_output)}")

        # Cleanup temp files (including the output JSONL file)
        cleanup_cmd = f"rm -f {prompt_file} {env_file} {runner_script} {output_file}"
        try:
            run_command(workspace_id, cleanup_cmd, timeout=30, with_node_env=False)
        except Exception:
            pass  # Cleanup failure is non-fatal

        # Filter wrapper control markers before parsing JSON stream
        filtered_lines = []
        for line in all_output.split('\n'):
            if line.strip().startswith('___CLAUDE_'):
                continue
            filtered_lines.append(line)
        filtered_output = '\n'.join(filtered_lines)

        # Parse the JSON stream output
        parsed = parse_claude_json_stream(filtered_output)

        return {
            'status': 'success' if exit_code == 0 else 'error',
            'exit_code': exit_code,
            'stdout': all_output,
            'stderr': '',
            'session_id': parsed.get('session_id'),
            'messages': parsed.get('messages', []),
            'final_result': parsed.get('final_result'),
            'error': None if exit_code == 0 else f"Claude exited with code {exit_code}"
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
                content_blocks = msg.get('message', {}).get('content', [])
                if not isinstance(content_blocks, list):
                    content_blocks = [content_blocks] if content_blocks else []

                text_parts = []
                for block in content_blocks:
                    if isinstance(block, dict):
                        block_type = block.get('type')

                        if block_type == 'text':
                            text = block.get('text', '')
                            if text:
                                text_parts.append(text)

                        elif block_type == 'tool_use':
                            tool_name = block.get('name', 'unknown')
                            tool_input = block.get('input', {})
                            result['messages'].append({
                                'type': 'tool_use',
                                'name': tool_name,
                                'input': tool_input,
                                'timestamp': datetime.now().isoformat()
                            })

                    elif isinstance(block, str):
                        text_parts.append(block)

                if text_parts:
                    content = '\n'.join(text_parts)
                    result['messages'].append({
                        'type': 'assistant',
                        'content': content,
                        'timestamp': datetime.now().isoformat()
                    })

            elif msg_type == 'user':
                content_blocks = msg.get('message', {}).get('content', [])
                if not isinstance(content_blocks, list):
                    content_blocks = [content_blocks] if content_blocks else []

                for block in content_blocks:
                    if isinstance(block, dict):
                        block_type = block.get('type')

                        if block_type == 'tool_result':
                            tool_content = block.get('content', '')
                            if isinstance(tool_content, (list, dict)):
                                tool_content = json.dumps(tool_content, indent=2)
                            result['messages'].append({
                                'type': 'tool_result',
                                'content': str(tool_content)[:5000],
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
                    command='Claude Code',
                    output=content[:10000]
                )

        elif msg_type == 'tool_use':
            tool_name = msg.get('name', 'unknown')
            tool_input = msg.get('input', {})

            if tool_name == 'Bash':
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

            if broadcast_func:
                try:
                    broadcast_func(ticket_id, {
                        'id': log_entry.id,
                        'log_type': log_entry.log_type,
                        'command': log_entry.command,
                        'explanation': getattr(log_entry, 'explanation', ''),
                        'output': log_entry.output[:2000],
                        'created_at': log_entry.created_at.isoformat()
                    })
                except Exception as e:
                    logger.warning(f"[CLAUDE_CLI] Failed to broadcast log: {e}")

    return logs_created
