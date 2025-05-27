# Django imports
import django
from django.conf import settings

import docker
import os
import time
import logging
import tempfile
import shutil
import threading
import tarfile
import io
import json
import random
from typing import Dict, Optional, Union, Callable, List, Tuple
from contextlib import contextmanager
from django.db.models import Q

from coding.models import DockerSandbox

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("docker_sandbox")

# Port range for container mapping
PORT_RANGE_START = 10000
PORT_RANGE_END = 64000

class Sandbox:
    """
    A sandboxed Docker container environment that allows for remote code execution.
    
    This class provides a secure, ephemeral Docker container that can:
    - Connect to a remote Docker host via SSH or TLS
    - Mount or inject code into the container
    - Execute commands within the container
    - Automatically terminate after a specified timeout
    """
    
    DEFAULT_IMAGE = "gitpod/workspace-full:latest"
    DEFAULT_TIMEOUT = 600  # 5 minutes
    DEFAULT_LIMITS = {
        "mem_limit": "1g",
        "nano_cpus": 1_000_000_000,  # 1 CPU
        "pids_limit": 100
    }
    
    def __init__(
        self,
        code_dir: str,
        timeout: int = DEFAULT_TIMEOUT,
        image: Optional[str] = None,
        buildpacks: bool = False,
        limits: Optional[Dict] = None,
        network_mode: str = "bridge", 
        project_id: str = None,
        conversation_id: str = None,
        port: Optional[int] = None,
        on_start: Optional[Callable] = None,
        on_kill: Optional[Callable] = None,
    ):
        """
        Initialize a new sandbox container.
        
        Args:
            code_dir: Path to the directory containing code to run in the sandbox
            timeout: Number of seconds before the container is automatically killed
            image: Docker image to use (defaults to gitpod/workspace-full:latest)
            buildpacks: Whether to build a custom image with Buildpacks
            limits: Resource limits for the container
            network_mode: Docker network mode ("bridge", "none", "host")
            project_id: Unique identifier for the project (used in container name)
            conversation_id: Unique identifier for the conversation
            port: Port to expose from the container (if None, will assign randomly)
            on_start: Callback function to execute when container starts
            on_kill: Callback function to execute when container is killed
        """
        # Initialize docker client (could be local or remote based on env vars)
        self.docker_client = self._create_docker_client()
        
        # Initialize properties
        self.code_dir = os.path.expanduser(code_dir)
        self.timeout = timeout
        self.image = image or self.DEFAULT_IMAGE
        self.buildpacks = buildpacks
        self.limits = limits or self.DEFAULT_LIMITS
        self.network_mode = network_mode
        
        # At least one of project_id or conversation_id must be provided
        if project_id is None and conversation_id is None:
            raise ValueError("Either project_id or conversation_id must be provided")
            
        # Container identifier - we'll use this for naming
        self.project_id = project_id
        self.conversation_id = conversation_id
        
        # Generate a container name based on available IDs
        if self.project_id:
            self.container_name = f"lfg-project-{self.project_id}"
        else:
            self.container_name = f"lfg-conversation-{self.conversation_id}"
        
        self.port = port
        self.on_start = on_start
        self.on_kill = on_kill
        
        # Container state
        self.container = None
        self.timer = None
        self.closed = False
        self.started_at = None
        self.db_record = None
        
        # Validate code directory exists
        if not os.path.exists(self.code_dir):
            raise ValueError(f"Code directory does not exist: {self.code_dir}")
        
        logger.info(f"Initialized sandbox with container name {self.container_name}")
        
        # Create database record if Django is available
        self._create_db_record()
    
    def _create_docker_client(self):
        """Create a Docker client using environment variables for configuration."""
        try:
            client = docker.from_env()
            # Test connectivity
            client.ping()
            return client
        except Exception as e:
            logger.error(f"Failed to connect to Docker: {e}")
            raise RuntimeError(f"Could not connect to Docker daemon: {e}")
    
    def _start_timeout_timer(self):
        """Start the timeout timer that will kill the container after the specified timeout."""
        if self.timeout <= 0:
            return
        
        def _kill_on_timeout():
            logger.info(f"Timeout reached for container {self.project_id}, killing...")
            try:
                self.close()
            except Exception as e:
                logger.error(f"Error during timeout-triggered close: {e}")
        
        self.timer = threading.Timer(self.timeout, _kill_on_timeout)
        self.timer.daemon = True
        self.timer.start()
        logger.info(f"Started timeout timer for {self.timeout}s")
    
    def _build_with_buildpacks(self) -> str:
        """
        Build a container image using Cloud Native Buildpacks.
        
        Returns:
            str: Name of the built image
        """
        # This is a placeholder for buildpacks integration
        # In a real implementation, you would use pack CLI or buildpacks Python library
        if self.buildpacks:
            # TODO: Implement buildpacks image building
            image_name = f"sandbox-{self.project_id}:latest"
            logger.warning("Buildpacks support not yet implemented, using default image")
            return self.image
        
        return self.image
    
    def _prepare_container_config(self) -> Dict:
        """Prepare configuration for container creation."""
        # Prepare the configuration for creating a container
        config = {
            "image": self.image,
            "detach": True,
            "tty": True,
            "network_mode": self.network_mode,
            "name": self.container_name,
            "working_dir": "/workspace",
            "command": "tail -f /dev/null",  # Keep container running
            **self.limits
        }
        
        # Add code mounting configuration (bind mount for simplicity in initial version)
        config["volumes"] = {
            os.path.abspath(self.code_dir): {
                "bind": "/workspace",
                "mode": "rw"
            }
        }
        
        # Add port mapping if needed
        if not self.port:  # Only find available port if not explicitly provided
            self.port = self._find_available_port()
            
        if self.port:
            # Create port bindings for port 8000 only
            port_bindings = {
                '8000/tcp': self.port
            }
            
            # Create proper host config with binds and port mappings
            host_config = self.docker_client.api.create_host_config(
                port_bindings=port_bindings,
                binds={
                    os.path.abspath(self.code_dir): {
                        "bind": "/workspace",
                        "mode": "rw"
                    }
                }
            )
            
            # Add host config to the configuration
            config["host_config"] = host_config
            
            # Expose port 8000
            config["ports"] = {'8000/tcp': {}}
            
            logger.info(f"Mapping container port 8000 to host port {self.port}")
        
        return config
    
    def start(self):
        """
        Start the sandbox container.
        
        Returns:
            self: For method chaining
        """
        if self.container is not None:
            logger.info(f"Container {self.container_name} already exists")
            return self
        
        try:
            # Pull the image if needed
            try:
                logger.info(f"Pulling image: {self.image}")
                self.docker_client.images.pull(self.image)
            except docker.errors.ImageNotFound:
                logger.error(f"Image not found: {self.image}")
                raise ValueError(f"Docker image not found: {self.image}")
            except Exception as e:
                logger.warning(f"Error pulling image {self.image}: {e}")
                # Continue anyway - image might be available locally
            
            # If buildpacks enabled, build custom image
            if self.buildpacks:
                self.image = self._build_with_buildpacks()
            
            # Create container configuration
            config = self._prepare_container_config()
            logger.info(f"Creating container {self.container_name}")

            print("\n\n\n\n\nconfig\n\n\n\n\n", config)
            
            # Extract host_config from the config if present
            host_config = None
            if "host_config" in config:
                host_config = config.pop("host_config")
            
            # For debugging, log the config
            logger.debug(f"Container config: {config}")
            
            # Clean up any conflicting containers with the same name
            try:
                old_container = self.docker_client.containers.get(self.container_name)
                logger.warning(f"Found existing container with name {self.container_name}, removing it")
                old_container.remove(force=True)
            except docker.errors.NotFound:
                # No existing container with this name
                pass
            
            # Create the container
            try:
                self.container = self.docker_client.containers.create(**config)
            except docker.errors.APIError as e:
                logger.error(f"Docker API error creating container: {e}")
                if "port is already allocated" in str(e).lower():
                    # Try with a different port
                    logger.info("Port conflict detected, trying with a different port")
                    self.port = self._find_available_port()
                    config = self._prepare_container_config()
                    if "host_config" in config:
                        config.pop("host_config")
                    self.container = self.docker_client.containers.create(**config)
                else:
                    raise
            
            # Start the container
            try:
                self.container.start()
                self.started_at = time.time()
            except docker.errors.APIError as e:
                logger.error(f"Docker API error starting container: {e}")
                # If it's a port binding issue, retry with a different port
                if "port is already allocated" in str(e).lower():
                    logger.info("Port conflict detected on start, trying with a different port")
                    self.container.remove(force=True)
                    self.port = self._find_available_port()
                    # Create a new container with the new port
                    config = self._prepare_container_config()
                    if "host_config" in config:
                        config.pop("host_config")
                    self.container = self.docker_client.containers.create(**config)
                    self.container.start()
                    self.started_at = time.time()
                else:
                    raise
            
            # Start timeout timer
            self._start_timeout_timer()
            
            logger.info(f"Container {self.container.short_id} started as {self.container_name}")
            
            # Update database record if available
            if self.db_record:
                try:
                    self.db_record.mark_as_running(
                        container_id=self.container.id,
                        port=self.port,
                        code_dir=self.code_dir
                    )
                except Exception as e:
                    logger.error(f"Failed to update database record: {e}")
                
            # Execute on_start callback if provided
            if self.on_start:
                try:
                    self.on_start(self)
                except Exception as e:
                    logger.error(f"Error in on_start callback: {e}")
            
            return self
        
        except Exception as e:
            logger.error(f"Failed to start container {self.container_name}: {str(e)}")
            
            # Update database record on error if available
            if self.db_record:
                try:
                    self.db_record.mark_as_error()
                except Exception as db_e:
                    logger.error(f"Failed to update database record on error: {db_e}")
                
            # Cleanup any half-started resources
            self.close()
            
            # Re-raise with more detailed message
            raise RuntimeError(f"Failed to start sandbox: {str(e)}")
    
    def exec(self, cmd: str, workdir: str = "/workspace", stream: bool = True) -> str:
        """
        Execute a command inside the container.
        
        Args:
            cmd: Command to execute
            workdir: Working directory inside the container
            stream: Whether to stream output (if False, just wait for completion)
            
        Returns:
            str: Command output (stdout + stderr)
        """
        if self.container is None:
            # Start container if not already started
            self.start()
        
        if self.closed:
            raise RuntimeError("Cannot exec in a closed sandbox")
        
        try:
            logger.info(f"Executing in container {self.container_name}: {cmd}")
            
            # Execute command
            exec_id = self.docker_client.api.exec_create(
                self.container.id,
                cmd,
                workdir=workdir,
                stderr=True
            )
            
            # Stream output for interactive feedback
            if stream:
                output = []
                for line in self.docker_client.api.exec_start(exec_id["Id"], stream=True):
                    line_str = line.decode('utf-8', errors='replace')
                    output.append(line_str)
                    logger.debug(f"Container output: {line_str.strip()}")
                result = ''.join(output)
            else:
                # Wait for completion and get output at once
                result = self.docker_client.api.exec_start(exec_id["Id"], stream=False)
                result = result.decode('utf-8', errors='replace')
            
            # Get exit code
            exec_info = self.docker_client.api.exec_inspect(exec_id["Id"])
            exit_code = exec_info.get("ExitCode", None)
            
            if exit_code != 0:
                logger.warning(f"Command exited with code {exit_code}: {cmd}")
            
            return result
        
        except Exception as e:
            logger.error(f"Error executing command in container {self.container_name}: {e}")
            raise RuntimeError(f"Command execution failed: {e}")
    
    def copy_to_container(self, src: str, dest: str):
        """
        Copy a file or directory from local machine to the container.
        
        Args:
            src: Source path on local machine
            dest: Destination path in container
        """
        if self.container is None:
            self.start()
        
        if self.closed:
            raise RuntimeError("Cannot copy to a closed sandbox")
        
        try:
            # Create a tarfile in memory
            tar_stream = io.BytesIO()
            
            with tarfile.open(fileobj=tar_stream, mode='w') as tar:
                if os.path.isdir(src):
                    # Add directory contents to tar
                    for root, dirs, files in os.walk(src):
                        for file in files:
                            full_path = os.path.join(root, file)
                            arcname = os.path.relpath(full_path, os.path.dirname(src))
                            tar.add(full_path, arcname=arcname)
                else:
                    # Add single file to tar
                    arcname = os.path.basename(src)
                    tar.add(src, arcname=arcname)
            
            # Reset stream position
            tar_stream.seek(0)
            
            # Copy the tarfile to the container
            self.container.put_archive(dest, tar_stream.read())
            logger.info(f"Copied {src} to container at {dest}")
        
        except Exception as e:
            logger.error(f"Error copying files to container: {e}")
            raise RuntimeError(f"Failed to copy files to container: {e}")
    
    def close(self):
        """Stop and remove the container."""
        if self.closed:
            logger.debug(f"Container {self.container_name} already closed")
            return
        
        # Cancel the timeout timer if it's running
        if self.timer and self.timer.is_alive():
            self.timer.cancel()
        
        try:
            # Call on_kill callback if provided
            if self.on_kill and self.container:
                try:
                    self.on_kill(self)
                except Exception as e:
                    logger.error(f"Error in on_kill callback: {e}")
            
            # Kill and remove the container if it exists
            if self.container:
                container_id = self.container.id
                
                try:
                    logger.info(f"Killing container {container_id}")
                    self.container.kill()
                except docker.errors.APIError as e:
                    logger.warning(f"Error killing container {container_id}: {e}")
                
                try:
                    logger.info(f"Removing container {container_id}")
                    self.container.remove(force=True)
                except docker.errors.APIError as e:
                    logger.error(f"Error removing container {container_id}: {e}")
                
                # Update database record
                if self.db_record:
                    self.db_record.mark_as_stopped()
            
            # Mark sandbox as closed
            self.closed = True
            self.container = None
            
            logger.info(f"Sandbox for container {self.container_name} closed")
        
        except Exception as e:
            logger.error(f"Error closing sandbox for container {self.container_name}: {e}")
            raise RuntimeError(f"Failed to close sandbox: {e}")
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
    
    def _create_db_record(self):
        """Create a database record for this sandbox."""
        try:
            # Convert resource limits to JSON-serializable format
            resource_limits = {}
            for key, value in self.limits.items():
                if isinstance(value, dict):
                    resource_limits[key] = value
                else:
                    resource_limits[key] = str(value)
                    
            self.db_record = DockerSandbox.objects.create(
                project_id=self.project_id,
                conversation_id=self.conversation_id,
                container_name=self.container_name,
                image=self.image,
                port=self.port,
                code_dir=self.code_dir,
                resource_limits=resource_limits,
                status='created'
            )
            
            identifier = self.project_id if self.project_id else f"conversation {self.conversation_id}"
            logger.info(f"Created database record for sandbox with {identifier}")
        except Exception as e:
            logger.error(f"Failed to create database record for sandbox: {e}")
            # Continue without database record
            self.db_record = None
    
    def _update_db_record(self, **kwargs):
        """Update the database record with the provided values."""

            
        try:
            for key, value in kwargs.items():
                setattr(self.db_record, key, value)
            self.db_record.save()
            logger.info(f"Updated database record for sandbox {self.project_id}")
        except Exception as e:
            logger.error(f"Failed to update database record for sandbox: {e}")
            
    def _find_available_port(self):
        """Find an available port in the configured range."""
        if self.port:
            return self.port
            
        # Try to find an unused port
        used_ports = set()

        try:
            # Get ports used by other sandboxes from the database
            for sandbox in DockerSandbox.objects.filter(status='running').exclude(port__isnull=True):
                used_ports.add(sandbox.port)
        except Exception as e:
            logger.error(f"Failed to get used ports from database: {e}")
                
        # Also check container port mappings directly from Docker
        try:
            containers = self.docker_client.containers.list()
            for container in containers:
                ports = container.attrs.get('NetworkSettings', {}).get('Ports', {})
                for port_config in ports.values():
                    if port_config:
                        for mapping in port_config:
                            host_port = mapping.get('HostPort')
                            if host_port:
                                used_ports.add(int(host_port))
        except Exception as e:
            logger.error(f"Failed to check container port mappings: {e}")
            
        # Find an available port
        available_ports = set(range(PORT_RANGE_START, PORT_RANGE_END)) - used_ports
        if not available_ports:
            logger.warning("No available ports found in range")
            return None
            
        return random.choice(list(available_ports))

def list_running_sandboxes() -> List[Dict]:
    """
    List all running sandbox containers.
    
    Returns:
        List of dictionaries with container information
    """
    try:
        # Get sandboxes from database
        db_sandboxes = DockerSandbox.objects.filter(status='running')
        
        # Get Docker client to verify containers are actually running
        client = docker.from_env()
        
        sandboxes = []
        for db_sandbox in db_sandboxes:
            try:
                # Check if container exists
                container = client.containers.get(db_sandbox.container_id)
                if container.status != 'running':
                    # Container not running, update database
                    db_sandbox.mark_as_stopped()
                    continue
                    
                # Container is running, add to list
                sandboxes.append({
                    "id": container.id,
                    "name": container.name,
                    "image": container.image.tags[0] if container.image.tags else container.image.id,
                    "status": container.status,
                    "created": container.attrs.get("Created"),
                    "project_id": db_sandbox.project_id,
                    "conversation_id": db_sandbox.conversation_id,
                    "port": db_sandbox.port
                })
            except (docker.errors.NotFound, docker.errors.APIError):
                # Container not found, update database
                db_sandbox.mark_as_stopped()
        
        return sandboxes
    except Exception as e:
        logger.error(f"Error getting sandboxes from database: {e}")
        # Fall back to Docker API if database query fails
    
    # If database query failed, use Docker API directly
    client = docker.from_env()
    
    # Find all containers with the "lfg-" prefix
    containers = client.containers.list(filters={"name": "lfg-"})
    
    return [
        {
            "id": container.id,
            "name": container.name,
            "image": container.image.tags[0] if container.image.tags else container.image.id,
            "status": container.status,
            "created": container.attrs.get("Created"),
            "project_id": container.name.replace("lfg-project-", "") if container.name.startswith("lfg-project-") else None,
            "conversation_id": container.name.replace("lfg-conversation-", "") if container.name.startswith("lfg-conversation-") else None,
            "port": _get_container_port(container)
        }
        for container in containers
    ]

def _get_container_port(container) -> Optional[int]:
    """Extract the mapped port from a container."""
    try:
        ports = container.attrs.get('NetworkSettings', {}).get('Ports', {})
        # Check for exposed port 8000
        port_mappings = ports.get('8000/tcp', [])
        if port_mappings:
            for mapping in port_mappings:
                host_port = mapping.get('HostPort')
                if host_port:
                    return int(host_port)
    except Exception as e:
        logger.error(f"Error getting container port: {e}")
    return None

def kill_all_sandboxes():
    """Kill and remove all sandbox containers."""
    client = docker.from_env()
    
    # Find all containers with the "lfg-" prefix
    containers = client.containers.list(filters={"name": "lfg-"})
    
    for container in containers:
        try:
            logger.info(f"Killing container {container.name}")
            container.kill()
            container.remove(force=True)
        except Exception as e:
            logger.error(f"Error killing container {container.name}: {e}")

def get_sandbox_by_project_id(project_id: str) -> Optional[Dict]:
    """
    Get information about a sandbox by project ID.
    
    Args:
        project_id: Project ID used when creating the sandbox
        
    Returns:
        Dictionary with container information or None if not found
    """
    try:
        # Get sandbox from database
        db_sandbox = DockerSandbox.objects.filter(
            project_id=project_id,
            status='running'
        ).first()
        
        if db_sandbox:
            # Get Docker client to verify container is running
            client = docker.from_env()
            
            try:
                # Check if container exists
                container = client.containers.get(db_sandbox.container_id)
                if container.status != 'running':
                    # Container not running, update database
                    db_sandbox.mark_as_stopped()
                    return None
                    
                # Container is running, return info
                return {
                    "id": container.id,
                    "name": container.name,
                    "image": container.image.tags[0] if container.image.tags else container.image.id,
                    "status": container.status,
                    "created": container.attrs.get("Created"),
                    "project_id": db_sandbox.project_id,
                    "conversation_id": db_sandbox.conversation_id,
                    "port": db_sandbox.port
                }
            except (docker.errors.NotFound, docker.errors.APIError):
                # Container not found, update database
                db_sandbox.mark_as_stopped()
                # Fall through to Docker API check
    except Exception as e:
        logger.error(f"Error getting sandbox from database: {e}")
        # Fall back to Docker API
    
    # If database lookup failed or container not found, use Docker API directly
    client = docker.from_env()
    
    # Find container with the project ID
    containers = client.containers.list(filters={"name": f"lfg-project-{project_id}"})
    
    if not containers:
        return None
    
    container = containers[0]
    
    return {
        "id": container.id,
        "name": container.name,
        "image": container.image.tags[0] if container.image.tags else container.image.id,
        "status": container.status,
        "created": container.attrs.get("Created"),
        "project_id": project_id,
        "conversation_id": None,  # No conversation ID available from Docker API
        "port": _get_container_port(container)
    }

def create_sandbox(project_id: str = None, code_dir: str = None, conversation_id: str = None, port: int = None) -> Sandbox:
    """
    Create a new sandbox for a project or conversation.
    
    Args:
        project_id: Unique identifier for the project (optional if conversation_id is provided)
        code_dir: Directory containing project code (optional, will create if None)
        conversation_id: Unique identifier for the conversation (optional if project_id is provided)
        port: Port to expose from the container (optional, will be assigned randomly if None)
        
    Returns:
        Sandbox instance
        
    Raises:
        ValueError: If neither project_id nor conversation_id is provided
    """
    # Require either project_id or conversation_id
    if project_id is None and conversation_id is None:
        raise ValueError("Either project_id or conversation_id must be provided")
    
    # Determine directory path
    if code_dir is None:
        if project_id:
            # For project-based sandboxes, use projects directory
            code_dir = os.path.join(os.getcwd(), "projects", project_id)
        else:
            # For conversation-based sandboxes, use conversations directory
            code_dir = os.path.join(os.getcwd(), "conversations", conversation_id)
        
        # Create directory if it doesn't exist
        os.makedirs(code_dir, exist_ok=True)
    
    # Create and start sandbox
    sandbox = Sandbox(
        code_dir=code_dir,
        project_id=project_id,
        conversation_id=conversation_id,
        port=port
    )
    
    return sandbox.start()

def get_or_create_sandbox(project_id: str = None, code_dir: str = None, conversation_id: str = None, port: int = None) -> Sandbox:
    """
    Get an existing sandbox for a project or conversation, or create a new one.
    
    Args:
        project_id: Unique identifier for the project (optional if conversation_id is provided)
        code_dir: Directory containing project code (optional, will create if None)
        conversation_id: Unique identifier for the conversation (optional if project_id is provided)
        port: Port to expose from the container (optional, will be assigned randomly if None)
        
    Returns:
        Sandbox instance
        
    Raises:
        ValueError: If neither project_id nor conversation_id is provided
    """
    # Require either project_id or conversation_id
    if project_id is None and conversation_id is None:
        raise ValueError("Either project_id or conversation_id must be provided")
    
    # Try to find an existing sandbox in the database
    try:
        # Build the query based on provided identifiers
        query = Q(status='running')
        
        if project_id is not None:
            query &= Q(project_id=project_id)
        if conversation_id is not None:
            query &= Q(conversation_id=conversation_id)
            
        existing_sandbox = DockerSandbox.objects.filter(query).first()
        
        if existing_sandbox:
            # Check if the container is actually running
            client = docker.from_env()
            try:
                container = client.containers.get(existing_sandbox.container_id)
                if container.status == 'running':
                    # Use the code_dir from the database if it exists, otherwise use provided or determine default
                    if existing_sandbox.code_dir and os.path.exists(existing_sandbox.code_dir):
                        sandbox_code_dir = existing_sandbox.code_dir
                    elif code_dir is not None:
                        sandbox_code_dir = code_dir
                    else:
                        if existing_sandbox.project_id:
                            sandbox_code_dir = os.path.join(os.getcwd(), "projects", existing_sandbox.project_id)
                        else:
                            sandbox_code_dir = os.path.join(os.getcwd(), "conversations", existing_sandbox.conversation_id)
                    
                    # Create a sandbox instance from the existing container
                    sandbox = Sandbox(
                        code_dir=sandbox_code_dir,
                        project_id=existing_sandbox.project_id,
                        conversation_id=existing_sandbox.conversation_id,
                        port=port if port is not None else existing_sandbox.port
                    )
                    sandbox.container = container
                    sandbox.started_at = time.time()
                    sandbox.db_record = existing_sandbox
                    
                    # Update conversation_id or code_dir if provided and different from existing
                    update_fields = {}
                    if conversation_id and conversation_id != existing_sandbox.conversation_id:
                        update_fields['conversation_id'] = conversation_id
                    if code_dir and code_dir != existing_sandbox.code_dir:
                        update_fields['code_dir'] = code_dir
                        
                    if update_fields:
                        sandbox._update_db_record(**update_fields)
                    
                    logger.info(f"Using existing sandbox container {container.short_id}")
                    return sandbox
                else:
                    # Container exists but not running, mark as stopped and create new
                    logger.info(f"Found existing container {existing_sandbox.container_id} but it's not running")
                    existing_sandbox.mark_as_stopped()
            except (docker.errors.NotFound, docker.errors.APIError) as e:
                # Container not found or other Docker error
                logger.warning(f"Container lookup error for {existing_sandbox.container_id}: {e}")
                existing_sandbox.mark_as_stopped()
    except Exception as e:
        logger.error(f"Error finding existing sandbox: {e}")
    
    # If we get here, we need to create a new sandbox
    logger.info(f"Creating new sandbox for project_id={project_id}, conversation_id={conversation_id}")
    return create_sandbox(project_id=project_id, code_dir=code_dir, conversation_id=conversation_id, port=port)

# Example usage
if __name__ == "__main__":
    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        # Write a simple Python script to the temp directory
        with open(os.path.join(temp_dir, "hello.py"), "w") as f:
            f.write('print("Hello from sandboxed container!")')
        
        # Create a sandbox
        with Sandbox(code_dir=temp_dir, timeout=60) as sandbox:
            # Execute the Python script
            output = sandbox.exec("python hello.py")
            print(f"Script output: {output}")
            
            # Install and test a package
            sandbox.exec("pip install requests")
            output = sandbox.exec('python -c "import requests; print(requests.get(\'https://httpbin.org/ip\').json())"')
            print(f"Network test output: {output}")
