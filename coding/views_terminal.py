import asyncio
import json
import logging
import threading
import websockets
from urllib.parse import parse_qs, parse_qsl, urlparse
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from coding.models import KubernetesPod
from kubernetes import client, config
from kubernetes.stream import ws_client
import base64
import os
from django.conf import settings
import tempfile
import urllib.parse
import re

logger = logging.getLogger(__name__)

class TerminalConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for handling terminal connections to Kubernetes pods."""
    
    async def connect(self):
        """Handle WebSocket connection."""
        logger.info("WebSocket connection attempt")
        
        # Accept the WebSocket connection
        await self.accept()
        
        try:
            # Get query parameters
            query_string = self.scope.get('query_string', b'').decode()
            query_params = dict(parse_qsl(query_string))
            
            # Extract required parameters
            project_id = query_params.get('project_id')
            conversation_id = query_params.get('conversation_id')
            
            if not project_id and not conversation_id:
                await self.send(text_data="Error: Missing project_id or conversation_id parameter\n")
                await self.close(code=4000)
                return
                
            # Get pod details
            pod = await self.get_pod_details(project_id, conversation_id)
            if not pod:
                await self.send(text_data="Error: Could not find or create pod\n")
                await self.close(code=4001)
                return
                
            # Set up Kubernetes client
            k8s_success = await self.setup_k8s_client(pod)
            
            if not k8s_success:
                # Could not establish a connection
                await self.send(text_data="Error: Failed to connect to the terminal\n")
                await self.close(code=4002)
                
        except Exception as e:
            logger.exception("Error in WebSocket connection")
            await self.send(text_data=f"Error connecting to terminal: {str(e)}\n")
            await self.close(code=4003)
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnect."""
        logger.info(f"WebSocket disconnected with code {close_code}")
        
        # Cancel the WebSocket read task if it exists
        if hasattr(self, 'ws_read_task') and self.ws_read_task:
            self.ws_read_task.cancel()
            
        # Close Kubernetes WebSocket connection
        if hasattr(self, 'k8s_ws') and self.k8s_ws:
            try:
                await self.k8s_ws.close()
            except Exception as e:
                logger.error(f"Error closing K8s WebSocket: {str(e)}")
                
        # Close SSH connections if in SSH mode
        if hasattr(self, 'ssh_mode') and self.ssh_mode:
            if hasattr(self, 'shell_channel') and self.shell_channel:
                try:
                    self.shell_channel.close()
                except Exception:
                    pass
                    
            if hasattr(self, 'ssh_client') and self.ssh_client:
                try:
                    self.ssh_client.close()
                except Exception:
                    pass
    
    async def receive(self, text_data=None, bytes_data=None):
        """Handle data received from WebSocket client."""
        if not text_data:
            return
            
        try:
            # Check if we're in SSH mode (fallback)
            if hasattr(self, 'ssh_mode') and self.ssh_mode and hasattr(self, 'shell_channel') and self.shell_channel:
                # Log what we're trying to send
                logger.info(f"Sending command to SSH shell: {text_data[:20]}...")
                try:
                    # Send directly to SSH shell
                    self.shell_channel.send(text_data + "\n")  # Make sure we append a newline
                except Exception as ssh_err:
                    logger.error(f"Error sending to SSH shell: {str(ssh_err)}")
                    await self.send(text_data=f"\x1b[1;31mError sending command to SSH shell: {str(ssh_err)}\x1b[0m\n")
                    # Try to reconnect the SSH shell if it closed
                    if self.shell_channel.closed:
                        await self.send(text_data="\x1b[1;33mSSH connection closed, attempting to reconnect...\x1b[0m\n")
                        # We can't directly reconnect here, so we'll close the WebSocket
                        await self.close(code=4004)
            # Otherwise use K8s WebSocket
            elif hasattr(self, 'k8s_ws') and self.k8s_ws:
                # Send the data to K8s WebSocket
                # Convert to channel 0 (stdin)
                stdin_data = chr(0) + text_data
                await self.k8s_ws.send(stdin_data)
            else:
                logger.error("No terminal connection established (neither SSH nor K8s WebSocket)")
                await self.send(text_data="\x1b[1;31mError: Terminal connection not established.\x1b[0m\n")
                await self.send(text_data="\x1b[1;33mTry disconnecting and reconnecting the terminal.\x1b[0m\n")
        except Exception as e:
            logger.exception("Error sending data to terminal")
            await self.send(text_data=f"\x1b[1;31mError sending command: {str(e)}\x1b[0m\n")
    
    async def read_from_k8s_ws(self):
        """Background task to read data from K8s WebSocket and send to WebSocket client."""
        try:
            # Regular expressions to match unwanted terminal control sequences and prompts
            control_code_regex = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\[[\?0-9]*[a-zA-Z]')
            prompt_regex = re.compile(r'\[[\?0-9]*[a-zA-Z]|gitpod\s+/workspace\s+\$\s*')
            
            last_sent = ""
            buffer = ""
            
            while True:
                if hasattr(self, 'k8s_ws') and self.k8s_ws and not self.k8s_ws.closed:
                    message = await self.k8s_ws.recv()
                    if message:
                        # K8s WebSocket protocol: first byte is channel (0: stdin, 1: stdout, 2: stderr, 3: error)
                        channel = ord(message[0])
                        data = message[1:]
                        
                        if channel == 1 or channel == 2:  # stdout or stderr
                            # Clean up control sequences
                            cleaned_data = control_code_regex.sub('', data)
                            # Remove prompt lines
                            cleaned_data = prompt_regex.sub('', cleaned_data)
                            # Remove empty lines
                            cleaned_data = re.sub(r'^\s*\n', '', cleaned_data)
                            
                            # If we have actual content, send it
                            if cleaned_data.strip():
                                # Don't send duplicate lines (e.g., echo of commands)
                                if cleaned_data.strip() != last_sent.strip():
                                    await self.send(text_data=cleaned_data)
                                    last_sent = cleaned_data
                        elif channel == 3:  # error
                            error_data = f"Error from pod: {data}\n"
                            await self.send(text_data=error_data)
                else:
                    # Connection closed, exit loop
                    break
                
                # Small sleep to prevent CPU hogging
                await asyncio.sleep(0.01)
        
        except asyncio.CancelledError:
            # Task was cancelled, exit gracefully
            logger.info("K8s WebSocket read task cancelled")
            return
        
        except Exception as e:
            logger.exception("Error in K8s WebSocket read task")
            await self.send(text_data=f"Error reading from terminal: {str(e)}\n")
            await self.close(code=1011)
    
    @database_sync_to_async
    def get_pod_details(self, project_id, conversation_id):
        """Get pod details from database based on project_id or conversation_id."""
        try:
            # Query based on available parameters
            if project_id:
                pod = KubernetesPod.objects.filter(project_id=project_id, status='running').first()
            elif conversation_id:
                pod = KubernetesPod.objects.filter(conversation_id=conversation_id, status='running').first()
            else:
                return None
            
            if not pod:
                return None
            
            # Return pod details as dictionary
            return {
                'pod_name': pod.pod_name,
                'namespace': pod.namespace,
                'cluster_host': pod.cluster_host if hasattr(pod, 'cluster_host') else None,
                'kubeconfig': pod.kubeconfig if hasattr(pod, 'kubeconfig') else None,
                'token': pod.token if hasattr(pod, 'token') else None,
                # Keep SSH details for fallback if needed
                'ssh_connection_details': pod.ssh_connection_details if hasattr(pod, 'ssh_connection_details') else {}
            }
        
        except Exception as e:
            logger.exception("Error getting pod details")
            return None
    
    async def setup_k8s_client(self, pod_details):
        """
        Set up a Kubernetes client and establish a WebSocket connection to the pod.
        Will fall back to SSH if Kubernetes API connection fails.
        """
        namespace = pod_details.get('namespace')
        pod_name = pod_details.get('pod_name')
        container = pod_details.get('container', 'app')
        
        logger.info(f"Setting up Kubernetes client for pod {pod_name} in namespace {namespace}")
        
        # First, try direct Kubernetes API WebSocket connection
        try:
            # Variables to track auth method used
            auth_method_used = "unknown"
            k8s_config_loaded = False
            
            # Try to load from kubeconfig provided in pod_details
            if pod_details.get('kubeconfig'):
                try:
                    # Load from the provided kubeconfig
                    logger.info("Using kubeconfig from database")
                    config_file = tempfile.NamedTemporaryFile(delete=False)
                    config_file.write(pod_details['kubeconfig'].encode())
                    config_file.close()
                    
                    # Load the temporary kubeconfig file
                    client.Configuration.set_default(
                        config.load_kube_config(config_file=config_file.name)
                    )
                    os.unlink(config_file.name)  # Clean up the temp file
                    k8s_config_loaded = True
                    auth_method_used = "kubeconfig from database"
                except Exception as e:
                    logger.warning(f"Failed to load kubeconfig from database: {str(e)}")
            
            # If that fails, try direct config with token
            if not k8s_config_loaded and pod_details.get('cluster_host') and pod_details.get('token'):
                try:
                    logger.info("Using direct cluster_host and token from database")
                    # Configure API client with token auth
                    configuration = client.Configuration()
                    configuration.host = pod_details['cluster_host']
                    configuration.verify_ssl = False  # Often needed for self-signed certs
                    configuration.api_key = {"authorization": f"Bearer {pod_details['token']}"}
                    client.Configuration.set_default(configuration)
                    k8s_config_loaded = True
                    auth_method_used = "direct token from database"
                except Exception as e:
                    logger.warning(f"Failed to setup direct k8s config: {str(e)}")
            
            # Try default kubeconfig as a fallback
            if not k8s_config_loaded:
                try:
                    # Try loading from default location
                    logger.info("Attempting to load kubeconfig from default location")
                    client.Configuration.set_default(config.load_kube_config())
                    k8s_config_loaded = True
                    auth_method_used = "default kubeconfig file"
                except Exception as e:
                    logger.warning(f"Failed to load default kubeconfig: {str(e)}")
            
            # If all that fails, try in-cluster config
            if not k8s_config_loaded:
                try:
                    logger.info("Attempting to use in-cluster config")
                    client.Configuration.set_default(config.load_incluster_config())
                    k8s_config_loaded = True
                    auth_method_used = "in-cluster config"
                except Exception as e:
                    logger.warning(f"Failed to load in-cluster config: {str(e)}")
            
            # If we've loaded a K8s config successfully, try the WebSocket connection
            if k8s_config_loaded:
                logger.info(f"Kubernetes config loaded successfully using {auth_method_used}")
                
                # Create the API instance
                api_instance = client.CoreV1Api()
                
                # Prepare the WebSocket URL
                command = [
                    '/bin/sh',
                    '-c',
                    'exec /bin/bash -i || exec /bin/sh -i'
                ]
                
                # Initialize the WebSocket connection
                ws = await websockets.connect(
                    f"ws://localhost:8001/api/v1/namespaces/{namespace}/pods/{pod_name}/exec?container={container}" +
                    "&stdout=1&stdin=1&stderr=1&tty=1&command=/bin/sh&command=-c&command=" +
                    urllib.parse.quote("exec /bin/bash -i || exec /bin/sh -i"),
                    ping_interval=None,
                    ping_timeout=None
                )
                
                # Store the WebSocket for later use
                self.k8s_ws = ws
                self.k8s_ws_connected = True
                
                # Log success
                logger.info(f"Successfully connected to pod {pod_name} via Kubernetes WebSocket")
                
                # Start the background task to read from the WebSocket
                self.ws_read_task = asyncio.create_task(self.read_from_k8s_ws())
                
                return True
            else:
                logger.error("All Kubernetes API connection methods failed")
                error_msg = "Could not load any Kubernetes configuration method"
                await self.send(text_data=f"Error: {error_msg}\n")
                raise Exception(error_msg)
                
        except Exception as e:
            # Log the WebSocket connection failure
            logger.warning(f"Failed to connect to pod {pod_name} via Kubernetes WebSocket: {str(e)}")
            await self.send(text_data=f"Kubernetes WebSocket connection failed: {str(e)}\n")
            await self.send(text_data="Attempting fallback to SSH connection...\n")
            
            # Try SSH as fallback
            try:
                ssh_success = await self.fallback_to_ssh(pod_details)
                if ssh_success:
                    # Start the read task for SSH
                    self.ws_read_task = asyncio.create_task(self.read_from_ssh())
                    return True
                else:
                    # Neither method worked
                    await self.send(text_data="All connection methods failed.\n")
                    return False
            except Exception as ssh_error:
                logger.exception(f"SSH fallback also failed: {str(ssh_error)}")
                await self.send(text_data=f"SSH fallback also failed: {str(ssh_error)}\n")
                return False
    
    @sync_to_async
    def fallback_to_ssh(self, pod):
        """Fallback to SSH connection method when direct Kubernetes API access fails."""
        try:
            import paramiko
            import io
            import time
            
            # Debug all settings to help diagnose the issue
            logger.info("=== SSH FALLBACK DEBUG INFO ===")
            logger.info(f"Pod: {pod.get('pod_name')} in {pod.get('namespace')}")
            
            # Get SSH connection details from pod or settings
            ssh_details = pod.get('ssh_connection_details', {})
            if not ssh_details:
                logger.warning("No SSH connection details in pod record, trying to use settings directly")
                ssh_details = {
                    'host': getattr(settings, 'K8S_SSH_HOST', None),
                    'port': getattr(settings, 'K8S_SSH_PORT', 22),
                    'username': getattr(settings, 'K8S_SSH_USERNAME', 'root'),
                    'key_file': getattr(settings, 'K8S_SSH_KEY_FILE', None),
                    'key_string': getattr(settings, 'K8S_SSH_KEY_STRING', None),
                    'key_passphrase': getattr(settings, 'K8S_SSH_KEY_PASSPHRASE', None)
                }
                
                logger.info(f"SSH host from settings: {ssh_details['host']}")
                logger.info(f"SSH port from settings: {ssh_details['port']}")
                logger.info(f"SSH username from settings: {ssh_details['username']}")
                logger.info(f"SSH key_file from settings: {ssh_details['key_file'] or 'None'}")
                logger.info(f"SSH key_string present: {'Yes' if ssh_details['key_string'] else 'No'}")
                
                if not ssh_details['host'] or (not ssh_details['key_file'] and not ssh_details['key_string']):
                    logger.error("Missing essential SSH connection details in settings")
                    return False
            else:
                logger.info(f"Using SSH connection details from pod record")
                logger.info(f"SSH host: {ssh_details.get('host')}")
                logger.info(f"SSH port: {ssh_details.get('port', 22)}")
                logger.info(f"SSH username: {ssh_details.get('username')}")
                logger.info(f"SSH key_file: {ssh_details.get('key_file') or 'None'}")
                logger.info(f"SSH key_string present: {'Yes' if ssh_details.get('key_string') else 'No'}")
            
            host = ssh_details.get('host')
            port = ssh_details.get('port', 22)
            username = ssh_details.get('username', 'root')
            
            logger.info(f"Setting up SSH connection to {host}:{port} as {username}")
            
            # Create SSH client
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect using either key file or key string
            connected = False
            error_messages = []
            
            # Try key string first if provided (from settings)
            key_string = ssh_details.get('key_string')
            if key_string:
                try:
                    logger.info("Using SSH key string for authentication")
                    key_file = io.StringIO(key_string)
                    private_key = paramiko.RSAKey.from_private_key(
                        key_file,
                        password=ssh_details.get('key_passphrase')
                    )
                    
                    # Enable more verbose logging for connection attempt
                    paramiko.common.logging.basicConfig(level=paramiko.common.DEBUG)
                    
                    ssh_client.connect(
                        hostname=host, 
                        port=port, 
                        username=username, 
                        pkey=private_key,
                        timeout=15,
                        look_for_keys=False,
                        allow_agent=False
                    )
                    connected = True
                    logger.info("Successfully connected using key string")
                except Exception as e:
                    error_message = f"Failed to connect using key string: {str(e)}"
                    logger.warning(error_message)
                    error_messages.append(error_message)
            
            # Try key file if key string failed or wasn't provided
            if not connected and ssh_details.get('key_file'):
                try:
                    key_file = ssh_details.get('key_file')
                    logger.info(f"Using SSH key file: {key_file}")
                    
                    # Check if key file exists
                    if not os.path.exists(key_file):
                        logger.error(f"SSH key file does not exist: {key_file}")
                        error_messages.append(f"SSH key file not found: {key_file}")
                    else:
                        ssh_client.connect(
                            hostname=host, 
                            port=port, 
                            username=username, 
                            key_filename=key_file,
                            passphrase=ssh_details.get('key_passphrase'),
                            timeout=15,
                            look_for_keys=False,
                            allow_agent=False
                        )
                        connected = True
                        logger.info("Successfully connected using key file")
                except Exception as e:
                    error_message = f"Failed to connect using key file: {str(e)}"
                    logger.warning(error_message)
                    error_messages.append(error_message)
            
            # Last resort - try password authentication if provided
            if not connected and ssh_details.get('password'):
                try:
                    logger.info("Trying password authentication as last resort")
                    ssh_client.connect(
                        hostname=host,
                        port=port,
                        username=username,
                        password=ssh_details.get('password'),
                        timeout=15,
                        look_for_keys=False,
                        allow_agent=False
                    )
                    connected = True
                    logger.info("Successfully connected using password")
                except Exception as e:
                    error_message = f"Failed to connect using password: {str(e)}"
                    logger.warning(error_message)
                    error_messages.append(error_message)
            
            if not connected:
                logger.error("All SSH connection methods failed")
                for i, error in enumerate(error_messages):
                    logger.error(f"Error {i+1}: {error}")
                return False
            
            logger.info("SSH connection established successfully")
            
            # Create kubectl exec command to access the pod
            # Using the exact format that works for the user
            namespace = pod.get('namespace')
            pod_name = pod.get('pod_name')
            
            logger.info(f"Working with pod {pod_name} in namespace {namespace}")
            
            # Try to get the deployment pod if pod_name isn't a direct pod name
            if not pod_name or pod_name.endswith('-pod'):
                try:
                    # First, check if we can get the actual pod name from the deployment
                    check_cmd = f"kubectl get pods -n {namespace} -l app={namespace} -o jsonpath='{{.items[0].metadata.name}}'"
                    logger.info(f"Executing command to find pod: {check_cmd}")
                    stdin, stdout, stderr = ssh_client.exec_command(check_cmd)
                    exit_status = stdout.channel.recv_exit_status()
                    actual_pod = stdout.read().decode('utf-8').strip()
                    stderr_output = stderr.read().decode('utf-8').strip()
                    
                    if stderr_output:
                        logger.warning(f"Error output from kubectl get pods: {stderr_output}")
                    
                    if actual_pod:
                        logger.info(f"Found actual pod: {actual_pod}")
                        pod_name = actual_pod
                    else:
                        # If can't find pod by label, try to list all pods in namespace
                        logger.warning(f"Could not find pod by label, listing all pods in namespace {namespace}")
                        list_cmd = f"kubectl get pods -n {namespace}"
                        logger.info(f"Executing command: {list_cmd}")
                        stdin, stdout, stderr = ssh_client.exec_command(list_cmd)
                        exit_status = stdout.channel.recv_exit_status()
                        pods_list = stdout.read().decode('utf-8').strip()
                        stderr_output = stderr.read().decode('utf-8').strip()
                        
                        if stderr_output:
                            logger.warning(f"Error output from kubectl get pods: {stderr_output}")
                            
                        logger.info(f"Pods in namespace {namespace}:\n{pods_list}")
                        
                        # Try to parse the output to find a pod
                        if pods_list and "No resources found" not in pods_list:
                            lines = pods_list.split('\n')
                            if len(lines) > 1:  # Header + at least one pod
                                # Get the first pod name (after header line)
                                parts = lines[1].split()
                                if parts:
                                    pod_name = parts[0]
                                    logger.info(f"Using pod {pod_name} from namespace {namespace}")
                except Exception as e:
                    logger.warning(f"Error trying to find actual pod name: {str(e)}")
            
            # Construct the kubectl exec command with the exact format that works
            kubectl_cmd = f"kubectl exec -it {pod_name} -n {namespace} -- /bin/bash\n"
            logger.info(f"Using kubectl command: {kubectl_cmd}")
            
            # Create a shell channel
            try:
                logger.info("Creating SSH shell channel")
                self.ssh_client = ssh_client
                self.shell_channel = ssh_client.invoke_shell(width=120, height=40)
                self.shell_channel.settimeout(10)
                
                # Send the kubectl command
                logger.info("Sending kubectl command")
                self.shell_channel.send(kubectl_cmd)
                
                # Wait a bit longer for the command to take effect
                logger.info("Waiting for kubectl exec to establish session...")
                time.sleep(3)
                
                # Check if there's any error output
                if self.shell_channel.recv_ready():
                    initial_output = self.shell_channel.recv(4096).decode('utf-8', errors='replace')
                    logger.info(f"Initial shell output: {initial_output[:200]}")
                    
                    # Check for common error messages
                    if "error" in initial_output.lower() or "not found" in initial_output.lower():
                        # Try again with a different kubectl format
                        if "error: unable to upgrade connection" in initial_output.lower():
                            logger.warning("TTY error detected, trying without -it flags")
                            kubectl_cmd_alt = f"kubectl exec {pod_name} -n {namespace} -- /bin/bash\n"
                            logger.info(f"Trying alternative kubectl command: {kubectl_cmd_alt}")
                            self.shell_channel.send(kubectl_cmd_alt)
                            time.sleep(2)
                            
                            # Check output from alternative command
                            if self.shell_channel.recv_ready():
                                alt_output = self.shell_channel.recv(4096).decode('utf-8', errors='replace')
                                logger.info(f"Alternative command output: {alt_output[:200]}")
                                
                                if "error" in alt_output.lower():
                                    logger.error(f"Alternative kubectl command also failed: {alt_output[:200]}")
                                    raise Exception(f"kubectl command failed: {alt_output[:200]}")
                        elif "not found" in initial_output.lower():
                            logger.error(f"Pod {pod_name} not found in namespace {namespace}")
                            
                            # Try listing pods in the namespace again for debugging
                            list_cmd = f"kubectl get pods -n {namespace}\n"
                            self.shell_channel.send(list_cmd)
                            time.sleep(2)
                            
                            raise Exception(f"kubectl command failed: Pod not found")
                        else:
                            logger.error(f"kubectl command failed: {initial_output[:200]}")
                            raise Exception(f"kubectl command failed: {initial_output[:200]}")
                else:
                    logger.warning("No initial output received from shell channel")
                
                # Try a basic command to see if the shell is responsive
                self.shell_channel.send("echo $SHELL\n")
                time.sleep(1)
                if self.shell_channel.recv_ready():
                    shell_output = self.shell_channel.recv(4096).decode('utf-8', errors='replace')
                    logger.info(f"Shell detection output: {shell_output[:200]}")
                
                # Setup for SSH mode
                self.ssh_mode = True
                
                # Signal client that connection is ready
                logger.info("SSH fallback connection ready for terminal access")
                return True
            except Exception as e:
                logger.error(f"Error creating shell channel: {str(e)}")
                ssh_client.close()
                raise
        
        except Exception as e:
            logger.exception(f"Error in SSH fallback method: {str(e)}")
            return False
    
    async def read_from_ssh(self):
        """Background task to read data from SSH shell and send to WebSocket."""
        try:
            # Regular expressions to match unwanted terminal control sequences and prompts
            control_code_regex = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\[[\?0-9]*[a-zA-Z]')
            prompt_regex = re.compile(r'\[[\?0-9]*[a-zA-Z]|gitpod\s+/workspace\s+\$\s*')
            
            # Send a simplified feedback message
            await self.send(text_data="Using SSH fallback mode for terminal connection.\n")
            
            # Give the connection a moment to stabilize
            await asyncio.sleep(0.5)
            
            # Send an initial command to wake up the shell
            if hasattr(self, 'shell_channel') and self.shell_channel:
                logger.info("Sending initial command to wake up shell")
                self.shell_channel.send("echo 'Terminal Ready'\n")
            
            # Flag to detect if we've received any data at all
            received_data = False
            connection_timeout = 20  # seconds
            start_time = asyncio.get_event_loop().time()
            last_activity_time = start_time
            keep_alive_interval = 30  # seconds
            
            last_sent = ""
            buffer = ""
            
            while True:
                current_time = asyncio.get_event_loop().time()
                
                if hasattr(self, 'shell_channel') and self.shell_channel:
                    is_ready = False
                    try:
                        is_ready = self.shell_channel.recv_ready()
                    except Exception as e:
                        logger.warning(f"Error checking recv_ready: {str(e)}")
                    
                    if is_ready:
                        try:
                            data = self.shell_channel.recv(4096).decode('utf-8', errors='replace')
                            if data:
                                received_data = True
                                last_activity_time = current_time
                                
                                # Clean up control sequences
                                cleaned_data = control_code_regex.sub('', data)
                                # Remove prompt lines
                                cleaned_data = prompt_regex.sub('', cleaned_data)
                                # Remove empty lines and Terminal Ready message
                                cleaned_data = re.sub(r'^\s*\n|Terminal Ready', '', cleaned_data)
                                
                                # If we have actual content, send it
                                if cleaned_data.strip():
                                    # Don't send duplicate lines (e.g., echo of commands)
                                    if cleaned_data.strip() != last_sent.strip():
                                        await self.send(text_data=cleaned_data)
                                        last_sent = cleaned_data
                                
                                logger.debug(f"Received {len(data)} bytes from SSH shell")
                        except Exception as recv_error:
                            logger.error(f"Error receiving data from shell: {str(recv_error)}")
                            await self.send(text_data=f"Error reading from terminal: {str(recv_error)}\n")
                    
                    # Check for initial timeout
                    if not received_data and current_time - start_time > connection_timeout:
                        logger.warning("SSH connection timeout - no data received")
                        await self.send(text_data="Warning: No response from terminal. The connection might be working but not showing output.\n")
                        await self.send(text_data="Try typing some commands to see if the terminal responds.\n")
                        received_data = True  # Prevent further timeout messages
                    
                    # Send keep-alive if needed
                    if received_data and current_time - last_activity_time > keep_alive_interval:
                        try:
                            logger.info("Sending keep-alive command")
                            self.shell_channel.send("\n")  # Send just a newline as a gentle keep-alive
                            last_activity_time = current_time
                        except Exception as ka_error:
                            logger.warning(f"Error sending keep-alive: {str(ka_error)}")
                
                    # Check if the connection is still active
                    if self.shell_channel.closed:
                        logger.warning("SSH channel was closed")
                        await self.send(text_data="SSH connection was closed by the server.\n")
                        break
                        
                    # Sometimes the channel can appear open but actually be disconnected
                    if received_data and (current_time - last_activity_time > 60):  # 1 minute of no activity is suspicious
                        try:
                            logger.warning("Long period of inactivity detected, sending test command")
                            self.shell_channel.send("echo ${RANDOM}\n")  # Send a test command that should produce output
                            last_activity_time = current_time
                            # We'll check for a response in the next loop iteration
                        except Exception as test_error:
                            logger.error(f"Error sending test command: {str(test_error)}")
                            await self.send(text_data="Connection appears to be unresponsive.\n")
                            break
                else:
                    logger.warning("Shell channel no longer exists")
                    await self.send(text_data="Terminal connection lost.\n")
                    break
                
                # Small sleep to prevent CPU hogging
                await asyncio.sleep(0.01)
        
        except asyncio.CancelledError:
            # Task was cancelled, exit gracefully
            logger.info("SSH read task cancelled")
            return
        
        except Exception as e:
            logger.exception("Error in SSH read task")
            await self.send(text_data=f"Error reading from terminal: {str(e)}\n")
            try:
                await self.close(code=1011)
            except:
                pass