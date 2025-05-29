#!/usr/bin/env python3

import os
import re
import time
import uuid
import json
import logging
import base64
import tempfile
import threading
from datetime import datetime, timezone
from django.conf import settings
from django.db import transaction
from ..models import KubernetesPod, KubernetesPortMapping
from kubernetes import client as k8s_client, config
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream
import paramiko
import io

# Global lock for namespace operations to prevent race conditions
namespace_locks = {}
namespace_locks_lock = threading.Lock()

# Global lock for pod creation operations to prevent race conditions
pod_creation_locks = {}
pod_creation_locks_lock = threading.Lock()

def get_namespace_lock(namespace):
    """Get or create a lock for a specific namespace"""
    with namespace_locks_lock:
        if namespace not in namespace_locks:
            namespace_locks[namespace] = threading.Lock()
        return namespace_locks[namespace]

def get_pod_creation_lock(project_id=None, conversation_id=None):
    """Get or create a lock for pod creation for a specific project/conversation"""
    lock_key = f"project_{project_id}" if project_id else f"conversation_{conversation_id}"
    
    with pod_creation_locks_lock:
        if lock_key not in pod_creation_locks:
            pod_creation_locks[lock_key] = threading.Lock()
        return pod_creation_locks[lock_key]

# Configure logging
logger = logging.getLogger(__name__)

# K8s server SSH connection settings (kept for backward compatibility)
def get_k8s_server_settings():
    """
    Get Kubernetes server settings from Django settings.
    
    Returns:
        dict: Dictionary with host, port, username, key_file, key_string, and key_passphrase.
    """
    try:
        # Attempt to get settings from Django settings
        k8s_settings = {
            'host': getattr(settings, 'K8S_SSH_HOST', '127.0.0.1'),
            'node_host': getattr(settings, 'K8S_NODE_SSH_HOST', '127.0.0.1'),
            'port': int(getattr(settings, 'K8S_SSH_PORT', 22)),
            'username': getattr(settings, 'K8S_SSH_USERNAME', 'root'),
            'key_file': getattr(settings, 'K8S_SSH_KEY_FILE', os.path.expanduser('~/.ssh/id_rsa')),
            'key_string': getattr(settings, 'K8S_SSH_KEY_STRING', None),
            'key_passphrase': getattr(settings, 'K8S_SSH_KEY_PASSPHRASE', None),
        }
        return k8s_settings
    except Exception as e:
        logger.error(f"Error getting K8s server settings: {str(e)}")
        # Fallback to defaults
        return {
            'host': '127.0.0.1',
            'port': 22,
            'username': 'root',
            'key_file': os.path.expanduser('~/.ssh/id_rsa'),
            'key_string': None,
            'key_passphrase': None,
        }


def get_k8s_api_client():
    """
    Get a configured Kubernetes API client using credentials from settings.
    
    Returns:
        tuple: (api_client, core_v1_api, apps_v1_api) or (None, None, None) if failed
    """
    
    try:
        # Create configuration
        configuration = k8s_client.Configuration()
        
        # Get settings from Django settings
        api_host = getattr(settings, 'K8S_API_HOST', None)
        api_token = getattr(settings, 'K8S_API_TOKEN', None)
        ca_cert = getattr(settings, 'K8S_CA_CERT', None)
        verify_ssl = getattr(settings, 'K8S_VERIFY_SSL', False)
        
        if not api_host:
            logger.error("K8S_API_HOST not configured in settings")
            return None, None, None
            
        if not api_token:
            logger.error("K8S_API_TOKEN not configured in settings")
            return None, None, None
        
        # Set host
        configuration.host = api_host
        
        # Set bearer token authentication
        configuration.api_key = {"authorization": f"Bearer {api_token}"}
        logger.info("Using bearer token authentication")
        
        # Handle CA certificate for SSL verification
        if verify_ssl and ca_cert:
            try:
                # Decode the base64 CA certificate
                decoded_ca_cert = base64.b64decode(ca_cert).decode('utf-8')
                
                # Write CA certificate to temporary file
                with tempfile.NamedTemporaryFile(mode='w', suffix='.crt', delete=False) as ca_file:
                    ca_file.write(decoded_ca_cert)
                    ca_file_path = ca_file.name
                
                configuration.ssl_ca_cert = ca_file_path
                configuration.verify_ssl = True
                logger.info(f"Using CA certificate for SSL verification: {ca_file_path}")
                
            except Exception as e:
                logger.warning(f"Failed to process CA certificate: {str(e)}")
                logger.warning("Falling back to SSL verification disabled")
                configuration.verify_ssl = False
        else:
            configuration.verify_ssl = verify_ssl
        
        # Disable SSL warnings if not verifying
        if not configuration.verify_ssl:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            logger.info("SSL verification disabled")
        
        # Create API client
        api_client = k8s_client.ApiClient(configuration)
        core_v1_api = k8s_client.CoreV1Api(api_client)
        apps_v1_api = k8s_client.AppsV1Api(api_client)
        
        # Test the connection
        try:
            namespaces = core_v1_api.list_namespace(limit=1)
            logger.info("Successfully connected to Kubernetes API")
            logger.info(f"Found {len(namespaces.items)} namespace(s)")
            return api_client, core_v1_api, apps_v1_api
        except ApiException as e:
            logger.error(f"Failed to connect to Kubernetes API: {e}")
            logger.error(f"Status: {e.status}, Reason: {e.reason}")
            
            # Clean up any temporary files on failure
            if hasattr(configuration, 'ssl_ca_cert') and configuration.ssl_ca_cert and os.path.exists(configuration.ssl_ca_cert):
                try:
                    os.unlink(configuration.ssl_ca_cert)
                except:
                    pass
                    
            return None, None, None
            
    except Exception as e:
        logger.error(f"Error creating Kubernetes API client: {str(e)}")
        return None, None, None


def ensure_namespace_exists(core_v1_api, namespace):
    """
    Ensure a namespace exists, create it if it doesn't.
    
    Args:
        core_v1_api: Kubernetes CoreV1Api client
        namespace (str): Namespace name
        
    Returns:
        bool: True if namespace exists or was created successfully
    """
    try:
        # Try to get the namespace
        core_v1_api.read_namespace(name=namespace)
        logger.info(f"Namespace {namespace} already exists")
        return True
    except ApiException as e:
        if e.status == 404:
            # Namespace doesn't exist, create it
            try:
                namespace_body = k8s_client.V1Namespace(
                    metadata=k8s_client.V1ObjectMeta(name=namespace)
                )
                core_v1_api.create_namespace(body=namespace_body)
                logger.info(f"Created namespace {namespace}")
                return True
            except ApiException as create_e:
                logger.error(f"Failed to create namespace {namespace}: {create_e}")
                return False
        else:
            logger.error(f"Error checking namespace {namespace}: {e}")
            return False


def create_ssh_client(host=None, port=None, username=None, key_file=None, key_string=None, key_passphrase=None):
    """
    Create an SSH client connection to the Kubernetes server.
    NOTE: This function is primarily used for host directory setup.
    Most other operations now use Kubernetes API directly.
    
    Returns:
        paramiko.SSHClient: Connected SSH client or None if connection fails
    """
    try:
        
        # Get default settings if not provided
        if not host:
            settings = get_k8s_server_settings()
            host = settings.get('host')
            port = settings.get('port', 22)
            username = settings.get('username')
            key_file = settings.get('key_file')
            key_string = settings.get('key_string')
            key_passphrase = settings.get('key_passphrase')
        
        logger.info(f"Creating SSH connection to {host}:{port} as {username}")
        
        # Create SSH client
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Prepare authentication
        connect_kwargs = {
            'hostname': host,
            'port': port,
            'username': username,
            'timeout': 30
        }
        
        # Use key string if provided
        if key_string:
            try:
                key_file_obj = io.StringIO(key_string)
                private_key = paramiko.RSAKey.from_private_key(key_file_obj, password=key_passphrase)
                connect_kwargs['pkey'] = private_key
                logger.info("Using provided key string for authentication")
            except Exception as e:
                logger.error(f"Failed to load private key from string: {str(e)}")
                return None
        # Use key file if provided and key string is not available
        elif key_file and os.path.exists(key_file):
            try:
                private_key = paramiko.RSAKey.from_private_key_file(key_file, password=key_passphrase)
                connect_kwargs['pkey'] = private_key
                logger.info(f"Using key file {key_file} for authentication")
            except Exception as e:
                logger.error(f"Failed to load private key from file {key_file}: {str(e)}")
                return None
        else:
            logger.warning("No valid SSH key provided, connection may fail")
        
        # Connect
        client.connect(**connect_kwargs)
        logger.info(f"Successfully connected to {host}:{port}")
        return client
        
    except Exception as e:
        logger.error(f"Failed to create SSH connection: {str(e)}")
        return None


def execute_remote_command(client, command):
    """
    Execute a command on the remote server and return the output.
    NOTE: This function is primarily used for host directory setup.
    Most other operations now use Kubernetes API directly.
    
    Returns:
        tuple: (success, stdout, stderr)
    """
    if not client:
        logger.error("No SSH client provided")
        return False, "", "No SSH client provided"
    
    try:
        logger.info(f"Executing SSH command: {command}")
        stdin, stdout, stderr = client.exec_command(command, timeout=30)
        
        # Read output
        stdout_data = stdout.read().decode('utf-8').strip()
        stderr_data = stderr.read().decode('utf-8').strip()
        exit_status = stdout.channel.recv_exit_status()
        
        success = exit_status == 0
        
        if success:
            logger.info(f"Command executed successfully")
            if stdout_data:
                logger.debug(f"STDOUT: {stdout_data}")
        else:
            logger.error(f"Command failed with exit status {exit_status}")
            if stderr_data:
                logger.error(f"STDERR: {stderr_data}")
        
        return success, stdout_data, stderr_data
        
    except Exception as e:
        logger.error(f"Error executing remote command: {str(e)}")
        return False, "", f"Error: {str(e)}"


def generate_namespace(project_id=None, conversation_id=None):
    """
    Generate a unique namespace based on project_id or conversation_id.
    
    Args:
        project_id (str): Project ID
        conversation_id (str): Conversation ID
        
    Returns:
        str: Unique namespace name
    """
    if project_id:
        # Use project ID as base for namespace
        namespace_base = f"proj-{project_id}"
    elif conversation_id:
        # Use conversation ID as base for namespace
        namespace_base = f"conv-{conversation_id}"
    else:
        # Generate a random namespace if neither is provided
        namespace_base = f"lfg-{uuid.uuid4().hex[:8]}"
    
    # Clean namespace: lowercase, replace special chars with dashes
    namespace = re.sub(r'[^a-z0-9-]', '-', namespace_base.lower())
    
    # Ensure it's valid (starts with letter, only contains letters, numbers, and dashes)
    if not re.match(r'^[a-z]', namespace):
        namespace = f"ns-{namespace}"
    
    # Truncate if too long (Kubernetes has a 63 character limit)
    if len(namespace) > 60:
        namespace = namespace[:60]
    
    return namespace


def check_pod_status(client, namespace, pod_name=None):
    """
    Check the status of a pod in the given namespace.
    
    Args:
        client: Kubernetes API client (or None for backward compatibility)
        namespace (str): Kubernetes namespace
        pod_name (str, optional): Specific pod name to check
        
    Returns:
        tuple: (exists, running, pod_details)
    """
    try:
        # Get Kubernetes API client
        api_client, core_v1_api, apps_v1_api = get_k8s_api_client()
        if not core_v1_api:
            logger.error("Failed to get Kubernetes API client")
            return False, False, {}
        
        # Ensure namespace exists
        try:
            core_v1_api.read_namespace(name=namespace)
            logger.info(f"Namespace {namespace} exists")
        except ApiException as e:
            if e.status == 404:
                logger.info(f"Namespace {namespace} does not exist, creating it")
                try:
                    namespace_body = k8s_client.V1Namespace(
                        metadata=k8s_client.V1ObjectMeta(name=namespace)
                    )
                    core_v1_api.create_namespace(body=namespace_body)
                    logger.info(f"Created namespace {namespace}")
                except ApiException as create_e:
                    logger.warning(f"Failed to create namespace {namespace}: {create_e}")
            else:
                logger.warning(f"Error checking namespace {namespace}: {e}")
        
        # List pods in the namespace
        if pod_name:
            # Check specific pod
            try:
                pod = core_v1_api.read_namespaced_pod(name=pod_name, namespace=namespace)
                pods = [pod]
            except ApiException as e:
                if e.status == 404:
                    logger.info(f"Pod {pod_name} not found in namespace {namespace}")
                    return False, False, {}
                else:
                    logger.error(f"Error reading pod {pod_name}: {e}")
                    return False, False, {}
        else:
            # List all pods in namespace
            try:
                pod_list = core_v1_api.list_namespaced_pod(namespace=namespace)
                pods = pod_list.items
            except ApiException as e:
                logger.error(f"Error listing pods in namespace {namespace}: {e}")
                return False, False, {}
        
        if not pods:
            logger.info(f"No pods found in namespace {namespace}")
            return False, False, {}
        
        # First try to find pods with the app label
        labeled_pods = [p for p in pods if p.metadata.labels and p.metadata.labels.get('app') == namespace]
        
        # Then try to find the specific pod if requested
        specific_pod = None
        if pod_name:
            specific_pod = next((p for p in pods if p.metadata.name == pod_name), None)
        
        # Decide which pod to use based on priorities:
        # 1. Specifically requested pod by name
        # 2. Pod with matching app label
        # 3. Any pod in the namespace
        pod = None
        if specific_pod:
            pod = specific_pod
            actual_pod_name = pod_name
            logger.info(f"Using specifically requested pod: {pod_name}")
        elif labeled_pods:
            pod = labeled_pods[0]
            actual_pod_name = pod.metadata.name
            logger.info(f"Found pod with app={namespace} label: {actual_pod_name}")
        else:
            pod = pods[0]
            actual_pod_name = pod.metadata.name
            logger.info(f"Using first available pod in namespace: {actual_pod_name}")
        
        # Check pod phase
        phase = pod.status.phase
        if phase.lower() != 'running':
            logger.info(f"Pod {actual_pod_name} phase is {phase}, not Running")
            return True, False, pod
        
        # Check if all containers are ready
        container_statuses = pod.status.container_statuses or []
        all_containers_ready = True
        
        for container in container_statuses:
            if not container.ready:
                container_name = container.name
                state = container.state
                reason = "unknown"
                
                # Check for container state reasons
                if state.waiting:
                    reason = state.waiting.reason or 'waiting'
                elif state.terminated:
                    reason = state.terminated.reason or 'terminated'
                
                logger.warning(f"Container {container_name} in pod {actual_pod_name} is not ready. State: {reason}")
                all_containers_ready = False
        
        # Only consider pod running if phase is Running AND all containers are ready
        return True, phase.lower() == 'running' and all_containers_ready, pod
        
    except Exception as e:
        logger.error(f"Error checking pod status: {str(e)}")
        return False, False, {}


def create_kubernetes_pod(client, namespace, image="gitpod/workspace-full:latest", resource_limits=None, force_recreate=False):
    """
    Create a Kubernetes pod in the given namespace.
    
    Args:
        client: Kubernetes API client (or None for backward compatibility)
        namespace (str): Kubernetes namespace
        image (str): Docker image to use
        resource_limits (dict): Resource limits for the pod
        force_recreate (bool): Whether to force recreation of all resources
        
    Returns:
        tuple: (success, pod_name, service_details)
    """
    
    image = "jitin2pillai/lfg-base:v1"
    
    # Get Kubernetes API client
    api_client, core_v1_api, apps_v1_api = get_k8s_api_client()
    if not core_v1_api or not apps_v1_api:
        logger.error("Failed to get Kubernetes API client")
        return False, None, {}
    
    # Generate names
    pod_name = f"{namespace}-pod"
    service_name = f"{namespace}-service"
    pv_name = f"{namespace}-pv"
    pvc_name = f"{namespace}-pvc"
    deployment_name = f"{namespace}-dep"
    
    # Log what we're creating
    logger.info(f"Creating pod with the following specifications:")
    logger.info(f"  Namespace: {namespace}")
    logger.info(f"  Pod name: {pod_name}")
    logger.info(f"  Image: {image}")
    logger.info(f"  Resource limits: {resource_limits}")
    logger.info(f"  Force recreate: {force_recreate}")
    
    # Default resource limits if not provided
    if not resource_limits:
        resource_limits = {
            'memory': '800Mi',
            'cpu': '500m',
            'memory_requests': '500Mi',
            'cpu_requests': '250m'
        }
    
    # Use namespace lock to prevent race conditions
    with get_namespace_lock(namespace):
        try:
            # Ensure namespace exists
            try:
                core_v1_api.read_namespace(name=namespace)
                logger.info(f"Namespace {namespace} exists")
            except ApiException as e:
                if e.status == 404:
                    logger.info(f"Namespace {namespace} does not exist, creating it")
                    try:
                        namespace_body = k8s_client.V1Namespace(
                            metadata=k8s_client.V1ObjectMeta(name=namespace)
                        )
                        core_v1_api.create_namespace(body=namespace_body)
                        logger.info(f"Created namespace {namespace}")
                    except ApiException as create_e:
                        logger.warning(f"Failed to create namespace {namespace}: {create_e}")
                else:
                    logger.warning(f"Error checking namespace {namespace}: {e}")
            
            # Only do cleanup if force_recreate is True or if we detect problematic resources
            cleanup_needed = force_recreate
            
            if not cleanup_needed:
                # Check if deployment exists and is healthy
                try:
                    deployment = apps_v1_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
                    # Check if deployment is ready
                    if deployment.status.ready_replicas != deployment.spec.replicas:
                        logger.info(f"Deployment {deployment_name} is not ready, cleanup needed")
                        cleanup_needed = True
                except ApiException as e:
                    if e.status == 404:
                        logger.info(f"Deployment {deployment_name} does not exist, will create new one")
                        # No cleanup needed if deployment doesn't exist
                    else:
                        logger.warning(f"Error checking deployment: {e}")
                        cleanup_needed = True
            
            if cleanup_needed:
                logger.info(f"Performing cleanup for namespace {namespace}...")
                
                # Delete existing deployment
                try:
                    apps_v1_api.delete_namespaced_deployment(
                        name=deployment_name,
                        namespace=namespace,
                        body=k8s_client.V1DeleteOptions()
                    )
                    logger.info(f"Deleted existing deployment {deployment_name}")
                    time.sleep(2)  # Wait for deletion
                except ApiException as e:
                    if e.status != 404:
                        logger.warning(f"Error deleting deployment: {e}")
                
                # Delete existing service
                try:
                    core_v1_api.delete_namespaced_service(
                        name=service_name,
                        namespace=namespace,
                        body=k8s_client.V1DeleteOptions()
                    )
                    logger.info(f"Deleted existing service {service_name}")
                except ApiException as e:
                    if e.status != 404:
                        logger.warning(f"Error deleting service: {e}")
                
                # Only delete PVC if force_recreate is True (preserve data by default)
                if force_recreate:
                    try:
                        core_v1_api.delete_namespaced_persistent_volume_claim(
                            name=pvc_name,
                            namespace=namespace,
                            body=k8s_client.V1DeleteOptions()
                        )
                        logger.info(f"Deleted existing PVC {pvc_name}")
                        time.sleep(3)  # Wait for PVC deletion
                    except ApiException as e:
                        if e.status != 404:
                            logger.warning(f"Error deleting PVC: {e}")
                    
                    # Check and delete existing PV if needed
                    try:
                        pv = core_v1_api.read_persistent_volume(name=pv_name)
                        pv_status = pv.status.phase
                        logger.info(f"PV {pv_name} status: {pv_status}")
                        
                        if pv_status != "Available":
                            logger.info(f"PV {pv_name} is in {pv_status} state. Deleting it...")
                            try:
                                core_v1_api.delete_persistent_volume(
                                    name=pv_name,
                                    body=k8s_client.V1DeleteOptions()
                                )
                                time.sleep(3)  # Wait for deletion
                            except ApiException as delete_e:
                                logger.warning(f"Error deleting PV: {delete_e}")
                    except ApiException as e:
                        if e.status == 404:
                            logger.info(f"PV {pv_name} does not exist")
                        else:
                            logger.warning(f"Error checking PV: {e}")
            else:
                logger.info(f"No cleanup needed for namespace {namespace}")
            
            # Check if PV and PVC already exist and are ready
            pv_exists = False
            pvc_exists = False
            pvc_bound = False
            
            try:
                pv = core_v1_api.read_persistent_volume(name=pv_name)
                pv_exists = True
                logger.info(f"PV {pv_name} already exists with status: {pv.status.phase}")
            except ApiException as e:
                if e.status == 404:
                    logger.info(f"PV {pv_name} does not exist, will create it")
                else:
                    logger.warning(f"Error checking PV: {e}")
            
            try:
                pvc = core_v1_api.read_namespaced_persistent_volume_claim(name=pvc_name, namespace=namespace)
                pvc_exists = True
                pvc_bound = pvc.status.phase == "Bound"
                logger.info(f"PVC {pvc_name} already exists with status: {pvc.status.phase}")
            except ApiException as e:
                if e.status == 404:
                    logger.info(f"PVC {pvc_name} does not exist, will create it")
                else:
                    logger.warning(f"Error checking PVC: {e}")
            
            # Create PersistentVolume if it doesn't exist
            if not pv_exists:
                logger.info(f"Creating PersistentVolume {pv_name}...")
                
                # Check if we should use dynamic storage or manual hostPath
                storage_class = os.getenv("STORAGE_CLASS_NAME", "manual")
                create_pv = storage_class == "manual"
                
                if create_pv:
                    # First, we need to ensure the host directory exists using SSH
                    # This is the one case where we still use SSH for host directory setup
                    logger.info(f"Creating host directory for persistent volume at /mnt/data/user-volumes/{namespace}...")
                    
                    # Get SSH connection details
                    ssh_settings = get_k8s_server_settings()
                    ssh_client = create_ssh_client(
                        host=ssh_settings.get('node_host'),
                        port=ssh_settings.get('port'),
                        username=ssh_settings.get('username'),
                        key_file=ssh_settings.get('key_file'),
                        key_string=ssh_settings.get('key_string'),
                        key_passphrase=ssh_settings.get('key_passphrase')
                    )
                    
                    if not ssh_client:
                        logger.error("Failed to create SSH connection for directory setup - this is required for hostPath volumes")
                        return False, None, {}
                    
                    # Get the node name where we're creating the directory
                    # Use node_host (worker node) instead of host (control plane) for node affinity
                    node_host_ip = ssh_settings.get('node_host', ssh_settings.get('host', 'localhost'))
                    
                    # We need to find the actual node name that corresponds to this IP
                    actual_node_name = None
                    try:
                        nodes = core_v1_api.list_node()
                        for node in nodes.items:
                            for address in node.status.addresses or []:
                                if address.address == node_host_ip:
                                    actual_node_name = node.metadata.name
                                    logger.info(f"Found node {actual_node_name} for IP {node_host_ip}")
                                    break
                            if actual_node_name:
                                break
                        
                        if not actual_node_name:
                            logger.warning(f"Could not find node for IP {node_host_ip}, using IP as node name")
                            actual_node_name = node_host_ip
                            
                    except Exception as e:
                        logger.warning(f"Error finding node name for IP {node_host_ip}: {e}")
                        actual_node_name = node_host_ip
                    
                    node_name = actual_node_name
                    logger.info(f"Will create directory on {node_host_ip} and pin PV to node {node_name}")
                    
                    # Debug: Show the mapping
                    logger.info(f"SSH Configuration:")
                    logger.info(f"  Control Plane (K8S API): {ssh_settings.get('host')}")
                    logger.info(f"  Worker Node (Directory): {node_host_ip}")
                    logger.info(f"  Target Node Name: {node_name}")
                    
                    # Create directory
                    success, stdout, stderr = execute_remote_command(
                        ssh_client, f"mkdir -p /mnt/data/user-volumes/{namespace}"
                    )
                    
                    if not success:
                        logger.error(f"Failed to create directory for volume: {stderr}")
                        ssh_client.close()
                        return False, None, {}
                    else:
                        logger.info(f"Successfully created directory /mnt/data/user-volumes/{namespace}")
                    
                    # Set proper permissions on directory
                    success, stdout, stderr = execute_remote_command(
                        ssh_client, f"chmod 777 /mnt/data/user-volumes/{namespace}"
                    )
                    
                    if not success:
                        logger.error(f"Failed to set permissions on volume directory: {stderr}")
                        ssh_client.close()
                        return False, None, {}
                    else:
                        logger.info(f"Set permissions 777 on /mnt/data/user-volumes/{namespace}")
                    
                    # # Create a test file to verify write access
                    # success, stdout, stderr = execute_remote_command(
                    #     ssh_client, f"echo 'This is a test file to verify write access.' > /mnt/data/user-volumes/{namespace}/test_access.txt"
                    # )
                    
                    # if not success:
                    #     logger.error(f"Failed to create test file: {stderr}")
                    #     ssh_client.close()
                    #     return False, None, {}
                    # else:
                    #     logger.info(f"Created test file in /mnt/data/user-volumes/{namespace}")
                    
                    # Set up the workspace structure that containers expect
                    # logger.info("Setting up workspace directory structure...")
                    
                    # # Create projects directory and other common workspace directories
                    # success, stdout, stderr = execute_remote_command(
                    #     ssh_client, f"mkdir -p /mnt/data/user-volumes/{namespace}/projects"
                    # )
                    # if not success:
                    #     logger.error(f"Failed to create projects directory: {stderr}")
                    #     ssh_client.close()
                    #     return False, None, {}
                    # else:
                    #     logger.info("Created projects directory")
                    
                    # Create additional common directories
                    # directories = [
                    #     f"/mnt/data/user-volumes/{namespace}/tmp",
                    #     f"/mnt/data/user-volumes/{namespace}/.vscode",
                    #     f"/mnt/data/user-volumes/{namespace}/.config",
                    #     f"/mnt/data/user-volumes/{namespace}/.local",
                    #     f"/mnt/data/user-volumes/{namespace}/.cache"
                    # ]
                    
                    # for directory in directories:
                    #     success, stdout, stderr = execute_remote_command(ssh_client, f"mkdir -p {directory}")
                    #     if not success:
                    #         logger.error(f"Failed to create directory {directory}: {stderr}")
                    #         ssh_client.close()
                    #         return False, None, {}
                    
                    # Set up a welcome file
                    success, stdout, stderr = execute_remote_command(
                        ssh_client, f"echo 'Welcome to your workspace! This directory is persistent and will retain your files.' > /mnt/data/user-volumes/{namespace}/README.txt"
                    )
                    if not success:
                        logger.error(f"Failed to create welcome file: {stderr}")
                        ssh_client.close()
                        return False, None, {}
                    else:
                        logger.info("Created welcome README.txt file")
                    
                    # Create a sample project structure
                    # success, stdout, stderr = execute_remote_command(
                    #     ssh_client, f"mkdir -p /mnt/data/user-volumes/{namespace}/projects/sample-project"
                    # )
                    # if success:
                    #     execute_remote_command(
                    #         ssh_client, f"echo '# Sample Project\n\nThis is a sample project directory.' > /mnt/data/user-volumes/{namespace}/projects/sample-project/README.md"
                    #     )
                    
                    # Set proper ownership for the user that will be running in the container
                    # Most development containers run as user ID 1000
                    success, stdout, stderr = execute_remote_command(
                        ssh_client, f"chown -R 1000:1000 /mnt/data/user-volumes/{namespace}"
                    )
                    if not success:
                        logger.warning(f"Failed to set ownership: {stderr}")
                        # This is not critical, continue
                    
                    logger.info("Completed workspace directory structure setup")
                    
                    # Close SSH connection
                    ssh_client.close()
                    
                    # Create PersistentVolume with node affinity
                    pv_body = k8s_client.V1PersistentVolume(
                        metadata=k8s_client.V1ObjectMeta(
                            name=pv_name,
                            labels={"type": "local", "pvname": pv_name}
                        ),
                        spec=k8s_client.V1PersistentVolumeSpec(
                            storage_class_name="manual",
                            capacity={"storage": "1Gi"},
                            access_modes=["ReadWriteOnce"],
                            host_path=k8s_client.V1HostPathVolumeSource(
                                path=f"/mnt/data/user-volumes/{namespace}",
                                type="DirectoryOrCreate"
                            ),
                            persistent_volume_reclaim_policy="Retain",
                            # Pin the PV to the specific node where we created the directory
                            node_affinity=k8s_client.V1VolumeNodeAffinity(
                                required=k8s_client.V1NodeSelector(
                                    node_selector_terms=[
                                        k8s_client.V1NodeSelectorTerm(
                                            match_expressions=[
                                                k8s_client.V1NodeSelectorRequirement(
                                                    key="kubernetes.io/hostname",
                                                    operator="In",
                                                    values=[node_name]
                                                )
                                            ]
                                        )
                                    ]
                                )
                            )
                        )
                    )
                    
                    try:
                        core_v1_api.create_persistent_volume(body=pv_body)
                        logger.info(f"Created PersistentVolume {pv_name} with node affinity to {node_name}")
                    except ApiException as e:
                        logger.error(f"Failed to create PV: {e}")
                        return False, None, {}
                    
                    # Wait for PV to be available
                    logger.info("Waiting for PersistentVolume to be available...")
                    for i in range(5):
                        try:
                            pv = core_v1_api.read_persistent_volume(name=pv_name)
                            if pv.status.phase == "Available":
                                logger.info("PersistentVolume is now Available")
                                break
                            logger.info(f"PV status: {pv.status.phase}, waiting...")
                            time.sleep(3)
                        except ApiException as e:
                            logger.error(f"Error checking PV status: {e}")
                            return False, None, {}
                    else:
                        logger.error("PersistentVolume failed to become Available")
                        return False, None, {}
                else:
                    logger.info(f"Using dynamic storage class: {storage_class}")
                
                # Create PersistentVolumeClaim
                logger.info(f"Creating PersistentVolumeClaim {pvc_name}...")
                
                if create_pv:
                    # Static PVC for hostPath
                    pvc_body = k8s_client.V1PersistentVolumeClaim(
                        metadata=k8s_client.V1ObjectMeta(name=pvc_name, namespace=namespace),
                        spec=k8s_client.V1PersistentVolumeClaimSpec(
                            storage_class_name="manual",
                            access_modes=["ReadWriteOnce"],
                            resources=k8s_client.V1ResourceRequirements(
                                requests={"storage": "1Gi"}
                            ),
                            volume_name=pv_name
                        )
                    )
                else:
                    # Dynamic PVC for real storage class
                    pvc_body = k8s_client.V1PersistentVolumeClaim(
                        metadata=k8s_client.V1ObjectMeta(name=pvc_name, namespace=namespace),
                        spec=k8s_client.V1PersistentVolumeClaimSpec(
                            storage_class_name=storage_class,
                            access_modes=["ReadWriteOnce"],
                            resources=k8s_client.V1ResourceRequirements(
                                requests={"storage": "1Gi"}
                            )
                        )
                    )
                
                try:
                    core_v1_api.create_namespaced_persistent_volume_claim(
                        namespace=namespace,
                        body=pvc_body
                    )
                    logger.info(f"Created PersistentVolumeClaim {pvc_name}")
                except ApiException as e:
                    logger.error(f"Failed to create PVC: {e}")
                    return False, None, {}
                
                # ENFORCE: Wait up to 120s for the claim to bind, else abort
                logger.info("Waiting for PersistentVolumeClaim to bind (up to 120 seconds)...")
                for attempt in range(40):  # 40 * 3 = 120 seconds
                    try:
                        pvc = core_v1_api.read_namespaced_persistent_volume_claim(
                            name=pvc_name,
                            namespace=namespace
                        )
                        phase = pvc.status.phase
                        
                        if phase == "Bound":
                            logger.info(f"{pvc_name} is Bound")
                            break
                        elif phase == "Pending":
                            logger.info(f"PVC status: {phase}, waiting... (attempt {attempt+1}/40)")
                            time.sleep(3)
                        else:
                            logger.error(f"PVC in unexpected phase: {phase}")
                            return False, None, {}
                        
                    except ApiException as e:
                        logger.error(f"Error checking PVC status: {e}")
                        return False, None, {}
                else:
                    # Fell out of loop → never bound
                    logger.error(f"PVC {pvc_name} never bound – aborting")
                    
                    # Get detailed information for debugging
                    try:
                        pvc = core_v1_api.read_namespaced_persistent_volume_claim(
                            name=pvc_name,
                            namespace=namespace
                        )
                        logger.error(f"Final PVC status: {pvc.status}")
                        
                        # Also check events
                        events = core_v1_api.list_namespaced_event(namespace=namespace)
                        for event in events.items[-5:]:
                            if pvc_name in event.message:
                                logger.error(f"PVC Event: {event.reason} - {event.message}")
                                
                    except Exception as debug_e:
                        logger.error(f"Error getting debug info: {debug_e}")
                    
                    return False, None, {}
                
                # Create Deployment
                logger.info(f"Creating Deployment {deployment_name}...")
                
                # Define containers
                containers = [
                    k8s_client.V1Container(
                        name="dev-environment",
                        image=image,
                        ports=[k8s_client.V1ContainerPort(container_port=7681, name="ttyd", protocol="TCP")],
                        env=[
                            k8s_client.V1EnvVar(name="TTYD_USER", value="user"),
                            k8s_client.V1EnvVar(name="TTYD_PASS", value="password")
                        ],
                        volume_mounts=[
                            k8s_client.V1VolumeMount(name="user-data", mount_path="/workspace")
                        ],
                        resources=k8s_client.V1ResourceRequirements(
                            limits={
                                "memory": resource_limits.get('memory', '200Mi'),
                                "cpu": resource_limits.get('cpu', '250m')
                            },
                            requests={
                                "memory": resource_limits.get('memory_requests', '100Mi'),
                                "cpu": resource_limits.get('cpu_requests', '100m')
                            }
                        )
                    ),
                    k8s_client.V1Container(
                        name="filebrowser",
                        image="filebrowser/filebrowser:latest",
                        command=["/filebrowser"],
                        args=["--noauth", "--address", "0.0.0.0", "--port", "8080", "--root", "/workspace"],
                        ports=[k8s_client.V1ContainerPort(container_port=8080, name="filebrowser", protocol="TCP")],
                        volume_mounts=[
                            k8s_client.V1VolumeMount(name="user-data", mount_path="/workspace")
                        ]
                    )
                ]
                
                # Define volumes
                volumes = [
                    k8s_client.V1Volume(
                        name="user-data",
                        persistent_volume_claim=k8s_client.V1PersistentVolumeClaimVolumeSource(
                            claim_name=pvc_name
                        )
                    )
                ]
                
                # Create deployment body
                deployment_body = k8s_client.V1Deployment(
                    metadata=k8s_client.V1ObjectMeta(
                        name=deployment_name,
                        namespace=namespace,
                        labels={"app": namespace, "component": "workspace"}
                    ),
                    spec=k8s_client.V1DeploymentSpec(
                        replicas=1,
                        selector=k8s_client.V1LabelSelector(
                            match_labels={"app": namespace}
                        ),
                        template=k8s_client.V1PodTemplateSpec(
                            metadata=k8s_client.V1ObjectMeta(
                                labels={"app": namespace, "component": "workspace"}
                            ),
                            spec=k8s_client.V1PodSpec(
                                containers=containers,
                                volumes=volumes
                            )
                        )
                    )
                )
                
                try:
                    apps_v1_api.create_namespaced_deployment(
                        namespace=namespace,
                        body=deployment_body
                    )
                    logger.info(f"Created Deployment {deployment_name}")
                except ApiException as e:
                    logger.error(f"Failed to create deployment: {e}")
                    return False, None, {}
                
                # Create Service
                logger.info(f"Creating Service {service_name}...")
                service_body = k8s_client.V1Service(
                    metadata=k8s_client.V1ObjectMeta(
                        name=service_name,
                        namespace=namespace,
                        labels={"app": namespace, "component": "ttyd-service"}
                    ),
                    spec=k8s_client.V1ServiceSpec(
                        type="NodePort",
                        ports=[
                            k8s_client.V1ServicePort(port=8080, target_port=8080, name="http"),
                            k8s_client.V1ServicePort(port=7681, target_port=7681, name="ttyd", protocol="TCP"),
                            k8s_client.V1ServicePort(port=8090, target_port=8080, name="filebrowser", protocol="TCP")
                        ],
                        selector={"app": namespace}
                    )
                )
                
                try:
                    core_v1_api.create_namespaced_service(
                        namespace=namespace,
                        body=service_body
                    )
                    logger.info(f"Created Service {service_name}")
                except ApiException as e:
                    logger.error(f"Failed to create service: {e}")
                    return False, None, {}
                
                # Wait for pod to be running
                actual_pod_name = None
                service_details = {}
                
                for attempt in range(12):  # Try for up to 2 minutes
                    logger.info(f"Checking pod status (attempt {attempt+1}/12)...")
                    
                    try:
                        pod_list = core_v1_api.list_namespaced_pod(
                            namespace=namespace,
                            label_selector=f"app={namespace}"
                        )
                        
                        if pod_list.items:
                            pod = pod_list.items[0]
                            actual_pod_name = pod.metadata.name
                            logger.info(f"Found pod: {actual_pod_name}")
                            
                            # Check if pod phase is Running
                            if pod.status.phase == "Running":
                                logger.info("Pod phase is Running, checking container readiness...")
                                
                                # Check if all containers are ready
                                container_statuses = pod.status.container_statuses or []
                                all_ready = all(status.ready for status in container_statuses)
                                
                                if not all_ready:
                                    logger.warning(f"Not all containers in pod {actual_pod_name} are ready - waiting...")
                                    time.sleep(10)
                                    continue
                                
                                logger.info(f"Pod {actual_pod_name} is now running with all containers ready")
                                
                                # EXTRA SANITY: Verify the workspace mount is working
                                logger.info("Verifying workspace mount...")
                                try:
                                    # Check if /workspace is mounted and accessible
                                    resp = stream(
                                        core_v1_api.connect_get_namespaced_pod_exec,
                                        actual_pod_name,
                                        namespace,
                                        command=['/bin/sh', '-c', 'df -h | grep /workspace && ls -la /workspace'],
                                        container='dev-environment',
                                        stderr=True,
                                        stdin=False,
                                        stdout=True,
                                        tty=False,
                                        _preload_content=False
                                    )
                                    
                                    # Read the output
                                    mount_output = ""
                                    mount_error = ""
                                    
                                    while resp.is_open():
                                        resp.update(timeout=1)
                                        if resp.peek_stdout():
                                            mount_output += resp.read_stdout()
                                        if resp.peek_stderr():
                                            mount_error += resp.read_stderr()
                                    
                                    resp.close()
                                    
                                    if mount_output and "/workspace" in mount_output:
                                        logger.info(f"Workspace mount verified successfully: {mount_output.strip()}")
                                    else:
                                        logger.error(f"Workspace mount verification failed. Output: {mount_output}, Error: {mount_error}")
                                        return False, None, {}
                                        
                                except Exception as mount_e:
                                    logger.error(f"Failed to verify workspace mount: {mount_e}")
                                    return False, None, {}
                                
                                # Get service details
                                try:
                                    service = core_v1_api.read_namespaced_service(
                                        name=service_name,
                                        namespace=namespace
                                    )
                                    
                                    # Get node IP
                                    nodes = core_v1_api.list_node()
                                    node_ip = "localhost"
                                    if nodes.items:
                                        for address in nodes.items[0].status.addresses:
                                            if address.type == "InternalIP":
                                                node_ip = address.address
                                                break
                                    
                                    # Extract port information
                                    http_port = None
                                    ttyd_port = None
                                    filebrowser_port = None
                                    
                                    for port in service.spec.ports:
                                        if port.name == "http":
                                            http_port = port.node_port
                                        elif port.name == "ttyd":
                                            ttyd_port = port.node_port
                                        elif port.name == "filebrowser":
                                            filebrowser_port = port.node_port
                                    
                                    service_details = {
                                        "nodePort": http_port,
                                        "ttydPort": ttyd_port,
                                        "nodeIP": node_ip,
                                        "url": f"http://{node_ip}:{http_port}" if http_port else None,
                                        "ttydUrl": f"http://{node_ip}:{ttyd_port}" if ttyd_port else None
                                    }
                                    
                                    if filebrowser_port:
                                        service_details["filebrowserPort"] = filebrowser_port
                                        service_details["filebrowserUrl"] = f"http://{node_ip}:{filebrowser_port}"
                                    
                                    logger.info(f"Service details: {service_details}")
                                    
                                except ApiException as e:
                                    logger.warning(f"Error getting service details: {e}")
                                
                                return True, actual_pod_name, service_details
                            
                            logger.info(f"Pod status: {pod.status.phase}, waiting...")
                        else:
                            logger.info("No pod found yet, waiting for deployment to create one...")
                        
                    except ApiException as e:
                        logger.warning(f"Error checking pods: {e}")
                    
                    # Wait before checking again
                    time.sleep(10)
                
                # If we get here, the pod didn't reach Running state
                logger.error("Pod didn't reach Running state after multiple attempts")
                return False, None, {}
                
        except Exception as e:
            logger.error(f"Error creating Kubernetes pod: {str(e)}")
            return False, None, {}


def get_kubernetes_access_config():
    """
    Get Kubernetes API access configuration from the environment.
    
    Returns:
        dict: Dictionary with cluster_host, kubeconfig, and token information
    """
    access_config = {
        'cluster_host': None,
        'kubeconfig': None,
        'token': None
    }
    
    try:
        # Get from Django settings
        access_config['cluster_host'] = getattr(settings, 'K8S_API_HOST', None)
        access_config['token'] = getattr(settings, 'K8S_API_TOKEN', None)
        
        # Try to load kubeconfig
        kube_config_path = os.environ.get('KUBECONFIG') or os.path.expanduser('~/.kube/config')
        if os.path.exists(kube_config_path):
            logger.info(f"Loading kubeconfig from {kube_config_path}")
            try:
                import yaml
                with open(kube_config_path, 'r') as f:
                    kubeconfig = yaml.safe_load(f)
                    access_config['kubeconfig'] = kubeconfig
                    
                    # Extract current context info if not already set
                    if not access_config['cluster_host']:
                        current_context = kubeconfig.get('current-context')
                        if current_context:
                            for context in kubeconfig.get('contexts', []):
                                if context.get('name') == current_context:
                                    cluster_name = context.get('context', {}).get('cluster')
                                    if cluster_name:
                                        for cluster in kubeconfig.get('clusters', []):
                                            if cluster.get('name') == cluster_name:
                                                access_config['cluster_host'] = cluster.get('cluster', {}).get('server')
                                                break
                                    break
                    
                    # Try to extract a token if not already set
                    if not access_config['token']:
                        for user in kubeconfig.get('users', []):
                            user_data = user.get('user', {})
                            if user_data.get('token'):
                                access_config['token'] = user_data.get('token')
                                break
                
                logger.info(f"Extracted Kubernetes cluster_host: {access_config['cluster_host']}")
                return access_config
            except Exception as e:
                logger.error(f"Error loading kubeconfig: {str(e)}")
        
        # Try to load from environment variables as fallback
        if os.environ.get('KUBERNETES_SERVICE_HOST'):
            access_config['cluster_host'] = f"https://{os.environ.get('KUBERNETES_SERVICE_HOST')}:{os.environ.get('KUBERNETES_SERVICE_PORT')}"
            
            # Try to load token from service account
            token_path = '/var/run/secrets/kubernetes.io/serviceaccount/token'
            if os.path.exists(token_path):
                with open(token_path, 'r') as f:
                    access_config['token'] = f.read().strip()
                
            logger.info(f"Using in-cluster Kubernetes config: {access_config['cluster_host']}")
            return access_config
        
        logger.info(f"Using configured Kubernetes access: {access_config['cluster_host']}")
        return access_config
        
    except Exception as e:
        logger.exception(f"Error getting Kubernetes access config: {str(e)}")
        return access_config


def manage_kubernetes_pod(project_id=None, conversation_id=None, image="gitpod/workspace-full:latest", resource_limits=None):
    """
    Create or manage a Kubernetes pod for a project or conversation.
    
    Args:
        project_id (str): Project ID (optional)
        conversation_id (str): Conversation ID (optional)
        image (str): Docker image to use (default is gitpod/workspace-full:latest which includes many development tools)
        resource_limits (dict): Resource limits to apply to the pod (default: 200Mi memory limit, 250m CPU limit, 
                              100Mi memory request, 100m CPU request)
        
    Returns:
        tuple: (success, pod, error_message)
    """
    if not (project_id or conversation_id):
        logger.error("Either project_id or conversation_id must be provided")
        return False, None, "Either project_id or conversation_id must be provided"
    
    # Use a lock to prevent concurrent pod creation for the same project/conversation
    with get_pod_creation_lock(project_id, conversation_id):
        try:
            # Get Kubernetes API access configuration
            k8s_access_config = get_kubernetes_access_config()
            logger.info(f"Got Kubernetes access config with cluster_host: {k8s_access_config.get('cluster_host')}")
            
            # Get Kubernetes API client
            api_client, core_v1_api, apps_v1_api = get_k8s_api_client()
            if not core_v1_api or not apps_v1_api:
                logger.error("Failed to get Kubernetes API client")
                return False, None, "Failed to connect to Kubernetes API"
            
            try:
                # Use database transaction to prevent race conditions
                with transaction.atomic():
                    # Check if pod already exists in database (with SELECT FOR UPDATE to prevent race conditions)
                    pod = None
                    if project_id:
                        pod = KubernetesPod.objects.select_for_update().filter(project_id=project_id).first()
                    elif conversation_id:
                        pod = KubernetesPod.objects.select_for_update().filter(conversation_id=conversation_id).first()
                    
                    # Generate a unique namespace for this project/conversation
                    namespace = generate_namespace(project_id, conversation_id)
                    expected_pod_name = f"{namespace}-pod"
                    deployment_name = f"{namespace}-dep"
                    
                    # Check Kubernetes state outside the transaction (since K8s calls can be slow)
                    # First check if there's a deployment in the namespace
                    deployment_exists = check_deployment_exists(api_client, namespace, deployment_name)
                    logger.info(f"Deployment check: exists={deployment_exists}")
                    
                    # If a deployment exists, check if pods are running
                    # Don't specify pod_name here - we want to find any pod in the namespace
                    exists_in_k8s, running_in_k8s, pod_details = check_pod_status(api_client, namespace)
                    
                    # If we found pod details, get the actual pod name
                    actual_pod_name = None
                    if pod_details:
                        actual_pod_name = pod_details.metadata.name
                        logger.info(f"Found pod in K8s: {actual_pod_name}, running={running_in_k8s}")
                    else:
                        logger.info(f"No pod found in K8s for namespace {namespace}")
                    
                    # We have four cases to handle:
                    # 1. Pod exists in DB and is running in K8s -> Just update DB record with actual pod name
                    # 2. Pod exists in DB but not running in K8s -> Start or recreate pod
                    # 3. Pod doesn't exist in DB but exists in K8s -> Create DB record for existing pod
                    # 4. Pod doesn't exist anywhere -> Create new pod and DB record
                    
                    # Case 3: Pod exists in K8s but not in DB - create DB record
                    if (exists_in_k8s or deployment_exists) and not pod:
                        logger.info(f"Resources exist in Kubernetes but not in database. Creating database record.")
                        
                        # If we found pod details, use them
                        if pod_details:
                            containers = pod_details.spec.containers or [{}]
                            actual_image = containers[0].image if containers else image
                        else:
                            # Otherwise use default values
                            actual_image = image
                        
                        # Ensure actual_image is never None or empty, use default if needed
                        if not actual_image:
                            logger.warning(f"No image found for existing pod, using default image: {image}")
                            actual_image = image
                        
                        logger.info(f"Creating pod record with image: {actual_image}")
                        
                        try:
                            pod = KubernetesPod(
                                project_id=project_id,
                                conversation_id=conversation_id,
                                namespace=namespace,
                                pod_name=actual_pod_name or expected_pod_name,
                                image=actual_image,
                                status='running' if running_in_k8s else 'created',
                                resource_limits=resource_limits,
                                ssh_connection_details=get_k8s_server_settings(),
                                # Add Kubernetes API access details
                                cluster_host=k8s_access_config.get('cluster_host'),
                                kubeconfig=k8s_access_config.get('kubeconfig'),
                                token=k8s_access_config.get('token')
                            )
                            
                            # If the pod is running, get service details
                            if running_in_k8s:
                                success, _, service_details = get_pod_service_details(api_client, namespace, actual_pod_name)
                                if success and service_details:
                                    pod.service_details = service_details
                            
                            pod.save()
                            
                            # Create port mapping records for the pod
                            service_name = f"{namespace}-service"
                            create_port_mappings(pod, service_details if 'service_details' in locals() else {}, service_name)
                            
                            logger.info(f"Created database record for existing Kubernetes pod {pod.pod_name}")
                            
                            if running_in_k8s:
                                return True, pod, None
                                
                        except Exception as e:
                            if "UNIQUE constraint failed" in str(e):
                                logger.warning(f"Pod record already exists (race condition), fetching existing record")
                                # Another thread created the record, fetch it
                                if project_id:
                                    pod = KubernetesPod.objects.filter(project_id=project_id).first()
                                elif conversation_id:
                                    pod = KubernetesPod.objects.filter(conversation_id=conversation_id).first()
                                
                                if pod:
                                    # Update the existing record with current K8s state
                                    if actual_pod_name and pod.pod_name != actual_pod_name:
                                        logger.info(f"Updating existing pod name from {pod.pod_name} to {actual_pod_name}")
                                        pod.pod_name = actual_pod_name
                                        pod.save(update_fields=['pod_name'])
                                    return True, pod, None
                            else:
                                raise e
                    
                    # Case 1: Pod exists in both DB and K8s and is running
                    if pod and exists_in_k8s and running_in_k8s:
                        logger.info(f"Pod {pod.pod_name} is already running in namespace {pod.namespace}")
                        
                        # Update pod name in database if it doesn't match actual pod name in K8s
                        # This is important if the pod was created by a deployment with a different name format
                        pod_updated = False
                        if actual_pod_name and pod.pod_name != actual_pod_name:
                            logger.info(f"Updating pod name in database from {pod.pod_name} to {actual_pod_name}")
                            pod.pod_name = actual_pod_name
                            pod_updated = True
                        
                        # Update status if needed
                        if pod.status != 'running':
                            pod.mark_as_running()
                            pod_updated = True
                        
                        # Update Kubernetes API access details
                        if k8s_access_config.get('cluster_host') and pod.cluster_host != k8s_access_config.get('cluster_host'):
                            pod.cluster_host = k8s_access_config.get('cluster_host')
                            pod_updated = True
                        if k8s_access_config.get('kubeconfig'):
                            pod.kubeconfig = k8s_access_config.get('kubeconfig')
                            pod_updated = True
                        if k8s_access_config.get('token') and pod.token != k8s_access_config.get('token'):
                            pod.token = k8s_access_config.get('token')
                            pod_updated = True
                        
                        # Update SSH connection details
                        current_ssh_details = get_k8s_server_settings()
                        if pod.ssh_connection_details != current_ssh_details:
                            pod.ssh_connection_details = current_ssh_details
                            pod_updated = True
                        
                        # Only refresh service details if pod name changed or service details are missing
                        if pod_updated or not pod.service_details or 'ttydUrl' not in pod.service_details:
                            logger.info(f"Refreshing service details for pod {pod.pod_name}")
                            success, _, service_details = get_pod_service_details(api_client, namespace, actual_pod_name or pod.pod_name)
                            if success and service_details:
                                pod.service_details = service_details
                                pod_updated = True
                        
                        if pod_updated:
                            pod.save()
                            logger.info(f"Updated pod {pod.pod_name} with latest details")
                        
                        # Create port mapping records for the pod if they don't exist
                        service_name = f"{namespace}-service"
                        create_port_mappings(pod, pod.service_details or {}, service_name)
                        
                        return True, pod, None
                
                # Cases 2 and 4 need to be handled outside the transaction since they involve K8s operations
                
                # Case 2: Pod exists in DB but not running in K8s - try to start existing pod
                if pod and exists_in_k8s and not running_in_k8s:
                    logger.info(f"Pod {pod.pod_name} exists but is not running. Attempting to start it.")
                    
                    # Try to start the existing pod
                    pod_started = start_kubernetes_pod(api_client, namespace, pod.pod_name)
                    
                    if pod_started:
                        logger.info(f"Successfully started pod {pod.pod_name}")
                        
                        # Check for actual pod name after restart
                        exists_in_k8s, running_in_k8s, pod_details = check_pod_status(api_client, namespace)
                        if pod_details:
                            actual_pod_name = pod_details.metadata.name
                            # Update pod name in database if it has changed
                            if actual_pod_name and pod.pod_name != actual_pod_name:
                                logger.info(f"Updating pod name after restart from {pod.pod_name} to {actual_pod_name}")
                                pod.pod_name = actual_pod_name
                        
                        # Update pod status
                        pod.mark_as_running()
                        
                        # Update service details
                        success, _, service_details = get_pod_service_details(api_client, namespace, pod.pod_name)
                        
                        if success and service_details:
                            pod.service_details = service_details
                        
                        pod.save()
                        return True, pod, None
                
                # Case 4 or fallback from Case 2: Need to create or recreate pod
                logger.info(f"Creating or recreating pod in namespace {namespace}")
                
                # Preserve the pod's original image and resource limits if they exist
                if pod and pod.image:
                    image = pod.image
                    logger.info(f"Using existing pod image for creation/recreation: {image}")
                
                if pod and pod.resource_limits:
                    resource_limits = pod.resource_limits
                    logger.info(f"Using existing pod resource limits for creation/recreation")
                
                # Create the pod in Kubernetes
                success, actual_pod_name, service_details = create_kubernetes_pod(api_client, namespace, image, resource_limits, force_recreate=False)
                
                if not success:
                    logger.error(f"Failed to create pod: {actual_pod_name}")
                    if pod:
                        pod.mark_as_error()
                    return False, pod, f"Failed to create pod: {actual_pod_name}"
                
                # Update or create pod record in database
                with transaction.atomic():
                    if not pod:
                        logger.info(f"Creating new pod record in database for {actual_pod_name}")
                        try:
                            pod = KubernetesPod(
                                project_id=project_id,
                                conversation_id=conversation_id,
                                namespace=namespace,
                                pod_name=actual_pod_name or expected_pod_name,
                                image=image,
                                status='created',
                                resource_limits=resource_limits,
                                ssh_connection_details=get_k8s_server_settings(),
                                # Add Kubernetes API access details
                                cluster_host=k8s_access_config.get('cluster_host'),
                                kubeconfig=k8s_access_config.get('kubeconfig'),
                                token=k8s_access_config.get('token')
                            )
                            pod.save()
                        except Exception as e:
                            if "UNIQUE constraint failed" in str(e):
                                logger.warning(f"Pod record already exists (race condition), fetching existing record")
                                # Another thread created the record, fetch it
                                if project_id:
                                    pod = KubernetesPod.objects.filter(project_id=project_id).first()
                                elif conversation_id:
                                    pod = KubernetesPod.objects.filter(conversation_id=conversation_id).first()
                            else:
                                raise e
                    
                    # Update pod record with actual pod name from K8s
                    pod.pod_name = actual_pod_name or pod.pod_name
                    pod.namespace = namespace
                    pod.service_details = service_details or {}
                    pod.mark_as_running()
                    
                    # Get token for the default service account in the pod's namespace if not already set
                    if not pod.token:
                        try:
                            logger.info("Attempting to get token for service account")
                            secret_list = core_v1_api.list_namespaced_secret(namespace=pod.namespace)
                            for secret in secret_list.items:
                                if secret.type == "kubernetes.io/service-account-token":
                                    token_data = secret.data.get('token')
                                    if token_data:
                                        import base64
                                        token = base64.b64decode(token_data).decode('utf-8')
                                        pod.token = token
                                        logger.info("Successfully retrieved token")
                                        break
                        except Exception as e:
                            logger.warning(f"Failed to get token for service account: {str(e)}")
                    
                    # If we don't have a cluster_host yet, get it from access config
                    if not pod.cluster_host:
                        pod.cluster_host = k8s_access_config.get('cluster_host')
                        logger.info(f"Set cluster host: {pod.cluster_host}")
                    
                    # Ensure SSH connection details are set for fallback
                    if not pod.ssh_connection_details:
                        pod.ssh_connection_details = get_k8s_server_settings()
                    
                    # Save the pod record
                    pod.save()
                
                # Create port mapping records for the pod
                service_name = f"{namespace}-service"
                create_port_mappings(pod, service_details, service_name)
                
                logger.info(f"Pod {pod.pod_name} created successfully in namespace {namespace}")
                logger.info(f"Pod has cluster_host: {pod.cluster_host or 'Not set'}, token: {'Set' if pod.token else 'Not set'}")
                return True, pod, None
                
            except Exception as e:
                logger.error(f"Error in pod management: {str(e)}")
                return False, None, f"Error: {str(e)}"
                
        except Exception as e:
            logger.exception(f"Error creating or managing Kubernetes pod: {str(e)}")
            
            # Check specifically for integrity errors related to image field
            if 'IntegrityError' in str(e) and 'coding_kubernetespod.image' in str(e):
                logger.error("The error is due to missing image field. This happens when creating a pod record for an existing K8s pod.")
                logger.error(f"Debug info - image: {image}, project_id: {project_id}, conversation_id: {conversation_id}")
            
            # Update pod status if we have a pod
            if 'pod' in locals() and pod:
                pod.mark_as_error()
            
            return False, None, f"Error: {str(e)}"


def execute_command_in_pod(project_id=None, conversation_id=None, command=None):
    """
    Execute a command in a Kubernetes pod.
    
    Args:
        project_id (str): Project ID (optional)
        conversation_id (str): Conversation ID (optional)
        command (str): Command to execute
        
    Returns:
        tuple: (success, stdout, stderr)
    """
    if not (project_id or conversation_id):
        logger.error("Either project_id or conversation_id must be provided")
        return False, "", "Either project_id or conversation_id must be provided"
    
    if not command:
        logger.error("Command must be provided")
        return False, "", "Command must be provided"
    
    try:
        # Get pod details from database
        pod = None
        if project_id:
            pod = KubernetesPod.objects.filter(project_id=project_id).first()
        elif conversation_id:
            pod = KubernetesPod.objects.filter(conversation_id=conversation_id).first()
        
        if not pod:
            logger.error(f"No pod found for project_id={project_id} or conversation_id={conversation_id}")
            return False, "", "No pod found. You need to create a pod first."
        
        # Get Kubernetes API client
        api_client, core_v1_api, apps_v1_api = get_k8s_api_client()
        if not core_v1_api:
            logger.error("Failed to get Kubernetes API client")
            return False, "", "Failed to connect to Kubernetes API"
        
        try:
            # Check if pod is running - but don't specify pod name to get any pod with app label
            exists, running, pod_details = check_pod_status(api_client, pod.namespace)
            
            # If we found a pod but it's not the one in our database, update our record
            actual_pod_name = pod.pod_name
            if exists and pod_details:
                found_pod_name = pod_details.metadata.name
                if found_pod_name and found_pod_name != pod.pod_name:
                    logger.info(f"Found different pod name in K8s ({found_pod_name}) than in database ({pod.pod_name})")
                    actual_pod_name = found_pod_name
                    
                    # Update database record with actual pod name
                    pod.pod_name = actual_pod_name
                    pod.save(update_fields=['pod_name'])
                    logger.info(f"Updated pod name in database to {actual_pod_name}")
            
            if not exists:
                logger.error(f"No pod found in namespace {pod.namespace}")
                return False, "", f"No pod found in namespace {pod.namespace}"
            
            if not running:
                logger.error(f"Pod exists in namespace {pod.namespace} but is not running")
                return False, "", f"Pod exists in namespace {pod.namespace} but is not running"
            
            # Execute command in pod using the actual pod name (from K8s)
            logger.info(f"Executing command in pod {actual_pod_name}: {command}")
            
            try:
                # Use the Kubernetes stream API to execute the command
                resp = stream(
                    core_v1_api.connect_get_namespaced_pod_exec,
                    actual_pod_name,
                    pod.namespace,
                    command=['/bin/sh', '-c', command],
                    container='dev-environment',  # Default to dev-environment container
                    stderr=True,
                    stdin=False,
                    stdout=True,
                    tty=False,
                    _preload_content=False
                )
                
                # Read the output
                stdout_data = ""
                stderr_data = ""
                
                while resp.is_open():
                    resp.update(timeout=1)
                    if resp.peek_stdout():
                        stdout_data += resp.read_stdout()
                    if resp.peek_stderr():
                        stderr_data += resp.read_stderr()
                
                resp.close()
                
                # Check if command was successful (no way to get exit code with current approach)
                # We'll consider it successful if we got output and no stderr indicating failure
                success = True
                if stderr_data and any(error_word in stderr_data.lower() for error_word in ['error', 'failed', 'not found', 'permission denied']):
                    success = False
                
                logger.info(f"Command execution completed. Success: {success}")
                if stdout_data:
                    logger.debug(f"STDOUT: {stdout_data[:500]}...")  # Log first 500 chars
                if stderr_data:
                    logger.debug(f"STDERR: {stderr_data[:500]}...")  # Log first 500 chars
                
                return success, stdout_data, stderr_data
                
            except ApiException as e:
                logger.error(f"Kubernetes API error executing command: {e}")
                return False, "", f"Kubernetes API error: {str(e)}"
            except Exception as e:
                logger.error(f"Error executing command in pod: {e}")
                return False, "", f"Error executing command: {str(e)}"
            
        except Exception as e:
            logger.error(f"Error in command execution setup: {str(e)}")
            return False, "", f"Error: {str(e)}"
            
    except Exception as e:
        logger.error(f"Error executing command in pod: {str(e)}")
        return False, "", f"Error: {str(e)}"


def get_ssh_client_for_project(project_id):
    """
    Get an SSH client for a specific project.
    
    Args:
        project_id (str): Project ID
        
    Returns:
        paramiko.SSHClient: Connected SSH client or None if connection fails
    """
    if not project_id:
        logger.error("Project ID must be provided")
        return None
    
    try:
        # Get pod details from database
        pod = KubernetesPod.objects.filter(project_id=project_id).first()
        
        if not pod:
            logger.error(f"No pod found for project_id={project_id}")
            return None
        
        # Get SSH connection details from the pod
        ssh_connection_details = pod.ssh_connection_details
        
        # Create SSH client
        client = None
        if ssh_connection_details:
            client = create_ssh_client(
                host=ssh_connection_details.get('host'),
                port=ssh_connection_details.get('port'),
                username=ssh_connection_details.get('username'),
                key_file=ssh_connection_details.get('key_file'),
                key_string=ssh_connection_details.get('key_string'),
                key_passphrase=ssh_connection_details.get('key_passphrase')
            )
        else:
            client = create_ssh_client()
        
        if not client:
            logger.error("Failed to create SSH client")
            return None
        
        return client
    except Exception as e:
        logger.error(f"Error creating SSH client for project {project_id}: {str(e)}")
        return None


def delete_kubernetes_pod(project_id=None, conversation_id=None, preserve_data=True):
    """
    Delete a Kubernetes pod.
    
    Args:
        project_id (str): Project ID (optional)
        conversation_id (str): Conversation ID (optional)
        preserve_data (bool): Whether to preserve the PersistentVolume for user data (default: True)
        
    Returns:
        bool: Success or failure
    """
    if not (project_id or conversation_id):
        logger.error("Either project_id or conversation_id must be provided")
        return False
    
    try:
        # Get pod details from database
        pod = None
        if project_id:
            pod = KubernetesPod.objects.filter(project_id=project_id).first()
        elif conversation_id:
            pod = KubernetesPod.objects.filter(conversation_id=conversation_id).first()
        
        if not pod:
            logger.error(f"No pod found for project_id={project_id} or conversation_id={conversation_id}")
            return True  # No pod to delete, so technically success
        
        # Get Kubernetes API client
        api_client, core_v1_api, apps_v1_api = get_k8s_api_client()
        if not core_v1_api or not apps_v1_api:
            logger.error("Failed to get Kubernetes API client")
            return False
        
        try:
            namespace = pod.namespace
            pv_name = f"{namespace}-pv"
            pvc_name = f"{namespace}-pvc"
            deployment_name = f"{namespace}-dep"
            service_name = f"{namespace}-service"
            
            # Delete deployments
            logger.info(f"Deleting deployment {deployment_name} in namespace {namespace}...")
            try:
                apps_v1_api.delete_namespaced_deployment(
                    name=deployment_name,
                    namespace=namespace,
                    body=k8s_client.V1DeleteOptions()
                )
                logger.info(f"Deleted deployment {deployment_name}")
            except ApiException as e:
                if e.status != 404:
                    logger.warning(f"Error deleting deployment: {e}")
                else:
                    logger.info(f"Deployment {deployment_name} not found")
            
            # Delete services
            logger.info(f"Deleting service {service_name} in namespace {namespace}...")
            try:
                core_v1_api.delete_namespaced_service(
                    name=service_name,
                    namespace=namespace,
                    body=k8s_client.V1DeleteOptions()
                )
                logger.info(f"Deleted service {service_name}")
            except ApiException as e:
                if e.status != 404:
                    logger.warning(f"Error deleting service: {e}")
                else:
                    logger.info(f"Service {service_name} not found")
            
            # Delete all pods in namespace
            logger.info(f"Deleting all pods in namespace {namespace}...")
            try:
                core_v1_api.delete_collection_namespaced_pod(
                    namespace=namespace,
                    body=k8s_client.V1DeleteOptions()
                )
                logger.info(f"Deleted all pods in namespace {namespace}")
            except ApiException as e:
                if e.status != 404:
                    logger.warning(f"Error deleting pods: {e}")
                else:
                    logger.info(f"No pods found in namespace {namespace}")
            
            if not preserve_data:
                # If we're not preserving data, delete PVCs and PVs as well
                logger.info(f"Removing all user data for {namespace}...")
                
                # First check if the PVC exists and delete it
                logger.info(f"Checking if PVC {pvc_name} exists...")
                try:
                    core_v1_api.read_namespaced_persistent_volume_claim(
                        name=pvc_name,
                        namespace=namespace
                    )
                    logger.info(f"Deleting PVC {pvc_name}...")
                    core_v1_api.delete_namespaced_persistent_volume_claim(
                        name=pvc_name,
                        namespace=namespace,
                        body=k8s_client.V1DeleteOptions()
                    )
                    logger.info(f"Deleted PVC {pvc_name}")
                except ApiException as e:
                    if e.status == 404:
                        logger.info(f"PVC {pvc_name} not found")
                    else:
                        logger.warning(f"Error deleting PVC {pvc_name}: {e}")
                
                # Wait for PVC to be deleted before deleting PV
                logger.info(f"Waiting for PVC to be fully deleted...")
                import time
                time.sleep(5)
                
                # Check if the PV exists and delete it
                logger.info(f"Checking if PV {pv_name} exists...")
                try:
                    pv = core_v1_api.read_persistent_volume(name=pv_name)
                    logger.info(f"Deleting PV {pv_name}...")
                    core_v1_api.delete_persistent_volume(
                        name=pv_name,
                        body=k8s_client.V1DeleteOptions()
                    )
                    logger.info(f"Deleted PV {pv_name}")
                except ApiException as e:
                    if e.status == 404:
                        logger.info(f"PV {pv_name} not found")
                    else:
                        logger.warning(f"Error deleting PV {pv_name}: {e}")
                        
                        # Try to patch the PV to force deletion if it's stuck
                        logger.info("Attempting to patch PV finalizers to force deletion...")
                        try:
                            patch_body = {"metadata": {"finalizers": None}}
                            core_v1_api.patch_persistent_volume(
                                name=pv_name,
                                body=patch_body
                            )
                            
                            # Try to delete again
                            core_v1_api.delete_persistent_volume(
                                name=pv_name,
                                body=k8s_client.V1DeleteOptions(grace_period_seconds=0)
                            )
                            logger.info(f"Force deleted PV {pv_name}")
                        except ApiException as patch_e:
                            logger.warning(f"Failed to force delete PV: {patch_e}")
                
                # Delete the namespace itself
                logger.info(f"Deleting namespace {namespace}...")
                try:
                    core_v1_api.delete_namespace(
                        name=namespace,
                        body=k8s_client.V1DeleteOptions()
                    )
                    logger.info(f"Deleted namespace {namespace}")
                except ApiException as e:
                    if e.status != 404:
                        logger.warning(f"Error deleting namespace: {e}")
                    else:
                        logger.info(f"Namespace {namespace} not found")
                
                success = True
            else:
                # If preserving data, just stop the pod but keep the namespace, PVC, and PV
                logger.info(f"Preserving PV and PVC for namespace {namespace} to retain user data")
                success = True
            
            # Mark pod as stopped in database
            pod.mark_as_stopped()
            
            return success
            
        except Exception as e:
            logger.error(f"Error in pod deletion: {str(e)}")
            return False
            
    except Exception as e:
        logger.error(f"Error deleting Kubernetes pod: {str(e)}")
        return False


def start_kubernetes_pod(client, namespace, pod_name):
    """
    Start a Kubernetes pod that exists but is not running.
    
    Args:
        client: Kubernetes API client (or None for backward compatibility)
        namespace (str): Kubernetes namespace
        pod_name (str): The name of the pod to start
        
    Returns:
        bool: True if the pod was started successfully, False otherwise
    """
    logger.info(f"Attempting to start pod {pod_name} in namespace {namespace}")
    
    # Get Kubernetes API client
    api_client, core_v1_api, apps_v1_api = get_k8s_api_client()
    if not core_v1_api or not apps_v1_api:
        logger.error("Failed to get Kubernetes API client")
        return False
    
    try:
        # First check if any pod with the app label exists and is running
        try:
            pod_list = core_v1_api.list_namespaced_pod(
                namespace=namespace,
                label_selector=f"app={namespace}"
            )
            
            if pod_list.items:
                logger.info(f"Found {len(pod_list.items)} pods with app={namespace} label")
                
                # Check if any of these pods are running
                for found_pod in pod_list.items:
                    if found_pod.status.phase == 'Running':
                        logger.info(f"Pod {found_pod.metadata.name} is already running")
                        return True
        except ApiException as e:
            logger.warning(f"Error listing pods: {e}")
        
        # Check if the specific pod exists
        try:
            pod = core_v1_api.read_namespaced_pod(name=pod_name, namespace=namespace)
            pod_status = pod.status.phase
            logger.info(f"Pod {pod_name} current status: {pod_status}")
            
            if pod_status == 'Running':
                logger.info(f"Pod {pod_name} is already running")
                return True
            else:
                # If pod exists but is not running, try to restart it
                logger.info(f"Deleting non-running pod {pod_name} so it can be recreated by deployment")
                try:
                    core_v1_api.delete_namespaced_pod(
                        name=pod_name,
                        namespace=namespace,
                        body=k8s_client.V1DeleteOptions(grace_period_seconds=0)
                    )
                    logger.info(f"Deleted pod {pod_name}")
                except ApiException as e:
                    logger.warning(f"Error deleting pod: {e}")
                
                # Wait for the pod to be deleted
                logger.info("Waiting for pod deletion to complete...")
                import time
                for i in range(5):  # Wait up to 15 seconds
                    try:
                        core_v1_api.read_namespaced_pod(name=pod_name, namespace=namespace)
                        logger.info("Pod still exists, waiting...")
                        time.sleep(3)
                    except ApiException as e:
                        if e.status == 404:
                            logger.info(f"Pod {pod_name} has been deleted")
                            break
                        else:
                            logger.warning(f"Error checking pod status: {e}")
                            time.sleep(3)
                            
        except ApiException as e:
            if e.status == 404:
                logger.info(f"Pod {pod_name} not found in namespace {namespace}, will check if deployment exists")
                
                # Check if a deployment exists that should create this pod
                deployment_name = f"{namespace}-dep"
                try:
                    deployment = apps_v1_api.read_namespaced_deployment(
                        name=deployment_name,
                        namespace=namespace
                    )
                    logger.info(f"Deployment exists, will scale it to force pod recreation")
                    
                    # Scale down and up to force pod recreation
                    deployment.spec.replicas = 0
                    apps_v1_api.patch_namespaced_deployment(
                        name=deployment_name,
                        namespace=namespace,
                        body=deployment
                    )
                    
                    # Wait for pods to be terminated
                    logger.info("Waiting for pods to be terminated...")
                    import time
                    time.sleep(3)
                    
                    # Scale back up
                    deployment.spec.replicas = 1
                    apps_v1_api.patch_namespaced_deployment(
                        name=deployment_name,
                        namespace=namespace,
                        body=deployment
                    )
                    
                except ApiException as deploy_e:
                    if deploy_e.status == 404:
                        logger.error(f"No deployment found in namespace {namespace} to create pods")
                        return False
                    else:
                        logger.error(f"Error managing deployment: {deploy_e}")
                        return False
            else:
                logger.error(f"Error reading pod {pod_name}: {e}")
                return False
        
        # Wait for a new pod to be created and become ready
        logger.info("Waiting for pod to be created and started...")
        new_pod_running = False
        
        import time
        for i in range(10):  # Wait up to 60 seconds for the pod to start
            try:
                # Find any pod in the namespace with the app label
                pod_list = core_v1_api.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=f"app={namespace}"
                )
                
                if pod_list.items:
                    new_pod = pod_list.items[0]
                    new_pod_name = new_pod.metadata.name
                    logger.info(f"Found pod: {new_pod_name}")
                    
                    # Check if the pod is running
                    if new_pod.status.phase == 'Running':
                        logger.info(f"Pod {new_pod_name} phase is Running, checking container readiness...")
                        
                        # Check if all containers are ready
                        container_statuses = new_pod.status.container_statuses or []
                        all_ready = all(status.ready for status in container_statuses)
                        
                        if not all_ready:
                            logger.warning(f"Not all containers in pod {new_pod_name} are ready")
                            # Continue to the next attempt
                            time.sleep(6)
                            continue
                    
                        logger.info(f"Pod {new_pod_name} is now running with all containers ready")
                        new_pod_running = True
                        break
                else:
                    logger.info("No pod found yet, waiting for deployment to create one...")
                
            except ApiException as e:
                logger.warning(f"Error checking pods: {e}")
            
            time.sleep(6)
        
        if not new_pod_running:
            logger.error(f"Failed to start pod in namespace {namespace} after multiple attempts")
            
            # Let's check the deployment events for debugging
            deployment_name = f"{namespace}-dep"
            try:
                deployment = apps_v1_api.read_namespaced_deployment(
                    name=deployment_name,
                    namespace=namespace
                )
                logger.info(f"Deployment status: {deployment.status}")
            except ApiException as e:
                logger.warning(f"Error checking deployment status: {e}")
            
            # Check events in the namespace
            try:
                events = core_v1_api.list_namespaced_event(namespace=namespace)
                for event in events.items[-5:]:  # Show last 5 events
                    logger.info(f"Event: {event.reason} - {event.message}")
            except ApiException as e:
                logger.warning(f"Error checking events: {e}")
        
        return new_pod_running
        
    except Exception as e:
        logger.error(f"Error starting pod: {str(e)}")
        return False


def get_pod_service_details(client, namespace, pod_name=None):
    """
    Get service details for a running pod.
    
    Args:
        client: Kubernetes API client (or None for backward compatibility)
        namespace (str): Kubernetes namespace
        pod_name (str, optional): Name of the pod
        
    Returns:
        tuple: (success, pod_name, service_details)
    """
    logger.info(f"Getting service details for namespace {namespace}" + (f", pod {pod_name}" if pod_name else ""))
    
    # Get Kubernetes API client
    api_client, core_v1_api, apps_v1_api = get_k8s_api_client()
    if not core_v1_api:
        logger.error("Failed to get Kubernetes API client")
        return False, None, {}
    
    service_name = f"{namespace}-service"
    
    try:
        # If no pod name specified, try to find any pod in the namespace
        if not pod_name:
            try:
                pod_list = core_v1_api.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=f"app={namespace}"
                )
                
                if pod_list.items:
                    pod_name = pod_list.items[0].metadata.name
                    logger.info(f"Found pod: {pod_name}")
                else:
                    # Try to find any pod in the namespace as fallback
                    pod_list = core_v1_api.list_namespaced_pod(namespace=namespace)
                    
                    if pod_list.items:
                        pod_name = pod_list.items[0].metadata.name
                        logger.info(f"Found pod using fallback: {pod_name}")
                    else:
                        logger.error(f"No pods found in namespace {namespace}")
                        return False, None, {}
            except ApiException as e:
                logger.error(f"Error listing pods: {e}")
                return False, None, {}
        
        # Check if pod exists
        try:
            pod = core_v1_api.read_namespaced_pod(name=pod_name, namespace=namespace)
        except ApiException as e:
            if e.status == 404:
                logger.warning(f"Pod {pod_name} not found in namespace {namespace}, trying to find any pod")
                
                # Try to find any pod in the namespace
                try:
                    pod_list = core_v1_api.list_namespaced_pod(
                        namespace=namespace,
                        label_selector=f"app={namespace}"
                    )
                    
                    if pod_list.items:
                        pod_name = pod_list.items[0].metadata.name
                        pod = pod_list.items[0]
                        logger.info(f"Found alternative pod: {pod_name}")
                    else:
                        logger.error(f"No pods found with app={namespace} label")
                        return False, None, {}
                except ApiException as list_e:
                    logger.error(f"Error listing pods: {list_e}")
                    return False, None, {}
            else:
                logger.error(f"Error reading pod {pod_name}: {e}")
                return False, None, {}
        
        # Check if pod is running
        if pod.status.phase != 'Running':
            logger.error(f"Pod {pod_name} is not running (status: {pod.status.phase}), cannot get service details")
            return False, pod_name, {}
        
        # Get service details
        try:
            service = core_v1_api.read_namespaced_service(
                name=service_name,
                namespace=namespace
            )
        except ApiException as e:
            if e.status == 404:
                logger.error(f"Service {service_name} not found in namespace {namespace}")
                return False, pod_name, {}
            else:
                logger.error(f"Error reading service {service_name}: {e}")
                return False, pod_name, {}
        
        # Extract port information
        http_port = None
        ttyd_port = None
        filebrowser_port = None
        
        for port in service.spec.ports:
            if port.name == "http":
                http_port = port.node_port
            elif port.name == "ttyd":
                ttyd_port = port.node_port
            elif port.name == "filebrowser":
                filebrowser_port = port.node_port
        
        logger.info(f"Retrieved ports - http: {http_port}, ttyd: {ttyd_port}, filebrowser: {filebrowser_port}")
        
        # Get node IP
        try:
            nodes = core_v1_api.list_node()
            node_ip = "localhost"
            if nodes.items:
                for address in nodes.items[0].status.addresses:
                    if address.type == "InternalIP":
                        node_ip = address.address
                        break
        except ApiException as e:
            logger.warning(f"Error getting node IP: {e}")
            node_ip = "localhost"
        
        # Create service details with ttyd and filebrowser info
        service_details = {
            "nodePort": http_port,
            "ttydPort": ttyd_port,
            "nodeIP": node_ip,
            "url": f"http://{node_ip}:{http_port}" if http_port else None,
            "ttydUrl": f"http://{node_ip}:{ttyd_port}" if ttyd_port else None
        }
        
        # Add filebrowser details if available
        if filebrowser_port:
            service_details["filebrowserPort"] = filebrowser_port
            service_details["filebrowserUrl"] = f"http://{node_ip}:{filebrowser_port}"
        
        logger.info(f"Service details for namespace {namespace}: {service_details}")
        
        # Verify the ttydUrl is set
        if not service_details.get("ttydUrl"):
            logger.warning(f"ttydUrl is not set in service_details for namespace {namespace}")
            return False, pod_name, service_details
        
        return True, pod_name, service_details
        
    except Exception as e:
        logger.error(f"Error getting service details: {str(e)}")
        return False, pod_name, {}


def check_deployment_exists(client, namespace, deployment_name=None):
    """
    Check if a deployment exists in the namespace.
    
    Args:
        client: Kubernetes API client (or None for backward compatibility)
        namespace (str): Kubernetes namespace
        deployment_name (str, optional): Specific deployment name to check
        
    Returns:
        bool: True if deployment exists, False otherwise
    """
    try:
        # Get Kubernetes API client
        api_client, core_v1_api, apps_v1_api = get_k8s_api_client()
        if not core_v1_api or not apps_v1_api:
            logger.error("Failed to get Kubernetes API client")
            return False
        
        # Ensure namespace exists
        try:
            core_v1_api.read_namespace(name=namespace)
            logger.info(f"Namespace {namespace} exists")
        except ApiException as e:
            if e.status == 404:
                logger.info(f"Namespace {namespace} does not exist, creating it")
                try:
                    namespace_body = k8s_client.V1Namespace(
                        metadata=k8s_client.V1ObjectMeta(name=namespace)
                    )
                    core_v1_api.create_namespace(body=namespace_body)
                    logger.info(f"Created namespace {namespace}")
                except ApiException as create_e:
                    logger.warning(f"Failed to create namespace {namespace}: {create_e}")
            else:
                logger.warning(f"Error checking namespace {namespace}: {e}")
        
        # Get deployment info
        if deployment_name:
            # Check specific deployment
            logger.info(f"Checking if deployment {deployment_name} exists in namespace {namespace}")
            try:
                deployment = apps_v1_api.read_namespaced_deployment(
                    name=deployment_name,
                    namespace=namespace
                )
                logger.info(f"Deployment {deployment_name} exists in namespace {namespace}")
                return True
            except ApiException as e:
                if e.status == 404:
                    logger.info(f"Deployment {deployment_name} does not exist in namespace {namespace}")
                    return False
                else:
                    logger.warning(f"Error checking deployment {deployment_name}: {e}")
                    return False
        else:
            # Get any deployment in namespace
            logger.info(f"Checking for any deployments in namespace {namespace}")
            try:
                deployment_list = apps_v1_api.list_namespaced_deployment(namespace=namespace)
                exists = len(deployment_list.items) > 0
                logger.info(f"Found {len(deployment_list.items)} deployment(s) in namespace {namespace}")
                return exists
            except ApiException as e:
                logger.warning(f"Error listing deployments in namespace {namespace}: {e}")
                return False
        
    except Exception as e:
        logger.error(f"Error checking deployment status: {str(e)}")
        return False


def test_workspace_mount(project_id=None, conversation_id=None):
    """
    Test the workspace volume mount to ensure it's working correctly.
    
    Args:
        project_id (str): Project ID (optional)
        conversation_id (str): Conversation ID (optional)
        
    Returns:
        tuple: (success, test_results, error_message)
    """
    if not (project_id or conversation_id):
        logger.error("Either project_id or conversation_id must be provided")
        return False, {}, "Either project_id or conversation_id must be provided"
    
    try:
        # Get pod details from database
        pod = None
        if project_id:
            pod = KubernetesPod.objects.filter(project_id=project_id).first()
        elif conversation_id:
            pod = KubernetesPod.objects.filter(conversation_id=conversation_id).first()
        
        if not pod:
            logger.error(f"No pod found for project_id={project_id} or conversation_id={conversation_id}")
            return False, {}, "No pod found. You need to create a pod first."
        
        # Get Kubernetes API client
        api_client, core_v1_api, apps_v1_api = get_k8s_api_client()
        if not core_v1_api:
            logger.error("Failed to get Kubernetes API client")
            return False, {}, "Failed to connect to Kubernetes API"
        
        try:
            # Check if pod is running
            exists, running, pod_details = check_pod_status(api_client, pod.namespace)
            
            if not exists:
                return False, {}, f"No pod found in namespace {pod.namespace}"
            
            if not running:
                return False, {}, f"Pod exists in namespace {pod.namespace} but is not running"
            
            # Get actual pod name
            actual_pod_name = pod_details.metadata.name if pod_details else pod.pod_name
            
            # Test workspace mount
            logger.info(f"Testing workspace mount in pod {actual_pod_name}")
            
            test_results = {}
            
            # Test 1: Check if /workspace is mounted
            try:
                resp = stream(
                    core_v1_api.connect_get_namespaced_pod_exec,
                    actual_pod_name,
                    pod.namespace,
                    command=['/bin/sh', '-c', 'df -h | grep /workspace'],
                    container='dev-environment',
                    stderr=True,
                    stdin=False,
                    stdout=True,
                    tty=False,
                    _preload_content=False
                )
                
                mount_output = ""
                mount_error = ""
                
                while resp.is_open():
                    resp.update(timeout=1)
                    if resp.peek_stdout():
                        mount_output += resp.read_stdout()
                    if resp.peek_stderr():
                        mount_error += resp.read_stderr()
                
                resp.close()
                
                test_results['mount_check'] = {
                    'success': "/workspace" in mount_output,
                    'output': mount_output.strip(),
                    'error': mount_error.strip()
                }
                
            except Exception as e:
                test_results['mount_check'] = {
                    'success': False,
                    'output': '',
                    'error': f"Exception: {str(e)}"
                }
            
            # Test 2: Check workspace contents
            try:
                resp = stream(
                    core_v1_api.connect_get_namespaced_pod_exec,
                    actual_pod_name,
                    pod.namespace,
                    command=['/bin/sh', '-c', 'ls -la /workspace'],
                    container='dev-environment',
                    stderr=True,
                    stdin=False,
                    stdout=True,
                    tty=False,
                    _preload_content=False
                )
                
                ls_output = ""
                ls_error = ""
                
                while resp.is_open():
                    resp.update(timeout=1)
                    if resp.peek_stdout():
                        ls_output += resp.read_stdout()
                    if resp.peek_stderr():
                        ls_error += resp.read_stderr()
                
                resp.close()
                
                test_results['content_check'] = {
                    'success': len(ls_output.strip()) > 0,
                    'output': ls_output.strip(),
                    'error': ls_error.strip()
                }
                
            except Exception as e:
                test_results['content_check'] = {
                    'success': False,
                    'output': '',
                    'error': f"Exception: {str(e)}"
                }
            
            # Test 3: Test write access
            try:
                test_file = f"/workspace/test_write_{int(time.time())}.txt"
                resp = stream(
                    core_v1_api.connect_get_namespaced_pod_exec,
                    actual_pod_name,
                    pod.namespace,
                    command=['/bin/sh', '-c', f'echo "Write test successful" > {test_file} && cat {test_file} && rm {test_file}'],
                    container='dev-environment',
                    stderr=True,
                    stdin=False,
                    stdout=True,
                    tty=False,
                    _preload_content=False
                )
                
                write_output = ""
                write_error = ""
                
                while resp.is_open():
                    resp.update(timeout=1)
                    if resp.peek_stdout():
                        write_output += resp.read_stdout()
                    if resp.peek_stderr():
                        write_error += resp.read_stderr()
                
                resp.close()
                
                test_results['write_check'] = {
                    'success': "Write test successful" in write_output,
                    'output': write_output.strip(),
                    'error': write_error.strip()
                }
                
            except Exception as e:
                test_results['write_check'] = {
                    'success': False,
                    'output': '',
                    'error': f"Exception: {str(e)}"
                }
            
            # Overall success
            overall_success = all(test['success'] for test in test_results.values())
            
            logger.info(f"Workspace mount test results: {test_results}")
            
            return overall_success, test_results, None if overall_success else "Some workspace tests failed"
            
        except Exception as e:
            logger.error(f"Error in workspace mount test: {str(e)}")
            return False, {}, f"Error: {str(e)}"
            
    except Exception as e:
        logger.error(f"Error testing workspace mount: {str(e)}")
        return False, {}, f"Error: {str(e)}"


def create_port_mappings(pod, service_details, service_name=None):
    """
    Create port mapping records for a pod.
    
    Args:
        pod (KubernetesPod): The pod object
        service_details (dict): Service details including port information
        service_name (str, optional): Name of the service, defaults to "{namespace}-service" if not provided
    """
    # If service_name is not provided, generate a default one
    if service_name is None and pod and pod.namespace:
        service_name = f"{pod.namespace}-service"
    
    # Create port mapping for ttyd
    if service_details.get('ttydPort'):
        KubernetesPortMapping.objects.update_or_create(
            pod=pod,
            container_name='ttyd',
            container_port=7681,
            defaults={
                'service_port': 7681,
                'node_port': service_details.get('ttydPort'),
                'protocol': 'TCP',
                'service_name': service_name,
                'description': 'Terminal access via ttyd'
            }
        )
    
    # Create port mapping for filebrowser
    if service_details.get('filebrowserPort'):
        KubernetesPortMapping.objects.update_or_create(
            pod=pod,
            container_name='filebrowser',
            container_port=8080,
            defaults={
                'service_port': 8090,
                'node_port': service_details.get('filebrowserPort'),
                'protocol': 'TCP',
                'service_name': service_name,
                'description': 'File browser for workspace'
            }
        )