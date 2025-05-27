# Django imports
import django
from django.conf import settings
from django.db.models import Q

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

from coding.models import DockerSandbox, DockerPortMapping
from projects.models import Project, ProjectCodeGeneration
from chat.models import Conversation

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
    DEFAULT_TIMEOUT = 6000  # 5 minutes
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
        
        # Create or get existing database record
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
        """Create a database record for this sandbox or update an existing one."""
        try:
            # Convert resource limits to JSON-serializable format
            resource_limits = {}
            for key, value in self.limits.items():
                if isinstance(value, dict):
                    resource_limits[key] = value
                else:
                    resource_limits[key] = str(value)
            
            # Use the utility function to ensure we don't create duplicates
            self.db_record = find_or_create_sandbox_record(
                project_id=self.project_id,
                conversation_id=self.conversation_id,
                container_name=self.container_name,
                image=self.image,
                code_dir=self.code_dir,
                resource_limits=resource_limits,
                status='created'
            )
            
            identifier = self.project_id if self.project_id else f"conversation {self.conversation_id}"
            logger.info(f"Using sandbox record for {identifier}")
            
        except Exception as e:
            logger.error(f"Failed to create/update database record for sandbox: {e}")
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
    
    def add_port_mapping(self, container_port: int, host_port: Optional[int] = None, command: Optional[str] = None) -> Optional[int]:
        """
        Add a new port mapping to the running container.
        
        Args:
            container_port: Port number inside the container to expose
            host_port: Port number on the host machine (if None, will assign randomly)
            command: Optional description of what this port is used for
            
        Returns:
            int: The host port number that was mapped, or None if mapping failed
            
        Raises:
            RuntimeError: If container is not running or port mapping fails
        """
        logger.info(f"[PORT_MAPPING] Starting port mapping process for container {self.container_name}, container_port={container_port}, requested_host_port={host_port}")
        
        if self.container is None:
            logger.error(f"[PORT_MAPPING] Container is not running for {self.container_name}")
            raise RuntimeError("Container is not running. Start the container first.")
        
        if self.closed:
            logger.error(f"[PORT_MAPPING] Cannot add port mapping to closed sandbox {self.container_name}")
            raise RuntimeError("Cannot add port mapping to a closed sandbox")
        
        # First, check if the container is actually running
        logger.info(f"[PORT_MAPPING] Checking if container {self.container.id} is running")
        container_info = self.docker_client.api.inspect_container(self.container.id)
        container_state = container_info.get('State', {})
        container_running = container_state.get('Running', False)
        
        logger.info(f"[PORT_MAPPING] Container {self.container.id} running status: {container_running}")
        
        if not container_running:
            try:
                logger.info(f"[PORT_MAPPING] Container {self.container.id} exists but is not running. Attempting to start it.")
                self.container.start()
                # Update container info after starting
                container_info = self.docker_client.api.inspect_container(self.container.id)
                logger.info(f"[PORT_MAPPING] Successfully started container {self.container.id}")
            except Exception as e:
                logger.error(f"[PORT_MAPPING] Failed to start container {self.container.id}: {e}")
                raise RuntimeError(f"Container exists but is not running and cannot be started: {e}")
        
        # If host_port is not provided, find an available one
        if host_port is None:
            logger.info(f"[PORT_MAPPING] No host port specified, finding an available port")
            host_port = self._find_available_port()
            logger.info(f"[PORT_MAPPING] Found available port: {host_port}")
            if not host_port:
                logger.error(f"[PORT_MAPPING] Could not find an available port")
                raise RuntimeError("Could not find an available port")
        
        try:
            # Check if the port is already mapped in Docker
            logger.info(f"[PORT_MAPPING] Checking existing port mappings for container {self.container.id}")
            existing_port_mappings = container_info.get('HostConfig', {}).get('PortBindings', {})
            container_port_key = f"{container_port}/tcp"
            port_already_mapped = container_port_key in existing_port_mappings
            existing_host_port = None
            
            if port_already_mapped:
                # Get the current host port from the Docker container
                existing_mappings = existing_port_mappings.get(container_port_key, [])
                if existing_mappings:
                    existing_host_port = existing_mappings[0].get('HostPort')
                    existing_host_port = int(existing_host_port) if existing_host_port else None
                    logger.info(f"[PORT_MAPPING] Container port {container_port} is already mapped to host port {existing_host_port}")
            else:
                logger.info(f"[PORT_MAPPING] Container port {container_port} is not currently mapped in Docker")
            
            # Similarly, check database for existing mapping
            db_mapping = None
            if self.db_record:
                try:
                    logger.info(f"[PORT_MAPPING] Checking for existing port mapping in database for sandbox {self.db_record.id}")
                    db_mapping = DockerPortMapping.objects.filter(
                        sandbox=self.db_record,
                        container_port=container_port
                    ).first()
                    
                    if db_mapping:
                        logger.info(f"[PORT_MAPPING] Found existing database mapping: container_port={container_port}, host_port={db_mapping.host_port}")
                    else:
                        logger.info(f"[PORT_MAPPING] No existing database mapping found for container_port={container_port}")
                except Exception as e:
                    logger.error(f"[PORT_MAPPING] Error checking for existing port mapping in database: {e}")
            else:
                logger.info(f"[PORT_MAPPING] No database record available for this sandbox")
            
            # Determine if we need to create/update the mapping in Docker
            update_docker_mapping = True
            
            # If Docker already has this port mapped but to a different host port than requested
            if port_already_mapped and existing_host_port is not None:
                if host_port != existing_host_port:
                    # If a specific host port was requested but it differs from existing, we update
                    if host_port is not None:
                        logger.info(f"[PORT_MAPPING] Updating existing Docker port mapping from {container_port}:{existing_host_port} to {container_port}:{host_port}")
                    else:
                        # If no specific host port was requested, use the existing one
                        host_port = existing_host_port
                        update_docker_mapping = False
                        logger.info(f"[PORT_MAPPING] Using existing Docker port mapping {container_port}:{host_port}")
                else:
                    logger.info(f"[PORT_MAPPING] Requested host port {host_port} matches existing mapping, no Docker update needed")
                    update_docker_mapping = False
            
            # If we need to update the Docker mapping
            if update_docker_mapping:
                # Get current port bindings
                port_bindings = existing_port_mappings.copy() if existing_port_mappings else {}
                
                # Update port binding for the specified container port
                port_bindings[container_port_key] = [{"HostPort": str(host_port)}]
                
                # Keep track of commands that need to be re-run in the container
                saved_commands = []
                if self.db_record:
                    # Save the commands that are currently running in the container
                    try:
                        logger.info(f"[PORT_MAPPING] Checking for commands to preserve during container restart")
                        # Try to find any command that might be running in the container
                        exec_result = self.docker_client.api.exec_create(
                            self.container.id,
                            "ps -ef | grep -v grep | grep -v 'tail -f /dev/null'",
                            stdout=True,
                            stderr=True
                        )
                        output = self.docker_client.api.exec_start(exec_result["Id"]).decode('utf-8', errors='replace')
                        if output.strip():
                            logger.info(f"[PORT_MAPPING] Found running processes in container: {output}")
                            saved_commands.append(output)
                    except Exception as e:
                        logger.warning(f"[PORT_MAPPING] Error checking running processes: {e}")
                
                # Update container with the new port binding
                logger.info(f"[PORT_MAPPING] Adding/updating port mapping in Docker: {container_port} -> {host_port}")
                container_restarted = False
                
                try:
                    # Most direct method - try to simply restart the container
                    try:
                        # For Docker API compatibility, we need to use a simpler, direct approach
                        logger.info(f"[PORT_MAPPING] Using direct method: stop and recreate container")
                        
                        # Stop the container if it's running
                        if container_running:
                            logger.info(f"[PORT_MAPPING] Stopping container to update port mappings")
                            self.container.stop(timeout=10)
                        
                        # Remove the container
                        logger.info(f"[PORT_MAPPING] Removing container to recreate with updated port mappings")
                        self.container.remove(force=True)
                        
                        # Create a new container with the same name and configuration but with updated port bindings
                        container_ports = {}
                        for port_key, bindings in port_bindings.items():
                            # Extract the container port (e.g., '8000/tcp' -> 8000)
                            container_port_num = int(port_key.split('/')[0])
                            host_port_num = int(bindings[0]["HostPort"])
                            container_ports[container_port_num] = host_port_num
                        
                        # Create a new container
                        logger.info(f"[PORT_MAPPING] Creating new container with updated port mappings: {container_ports}")
                        new_container = self.docker_client.containers.run(
                            self.image,
                            name=self.container_name,
                            command="tail -f /dev/null",  # Keep container running
                            detach=True,
                            ports=container_ports,  # Use the collected port mappings
                            volumes={os.path.abspath(self.code_dir): {'bind': '/workspace', 'mode': 'rw'}},
                            working_dir="/workspace",
                            **self.limits
                        )
                        
                        # Update container reference
                        self.container = new_container
                        
                        # Update DB record with new container ID and port
                        if self.db_record:
                            logger.info(f"[PORT_MAPPING] Updating database record with new container ID and port")
                            self.db_record.container_id = new_container.id
                            self.db_record.port = host_port
                            self.db_record.mark_as_running()
                        
                        container_restarted = True
                        logger.info(f"[PORT_MAPPING] Successfully created new container with port mapping")
                    except Exception as e:
                        logger.error(f"[PORT_MAPPING] Direct method failed: {e}")
                        raise
                        
                except Exception as e:
                    logger.error(f"[PORT_MAPPING] Error updating container port bindings: {e}")
                    
                    # If direct update failed, try another method as last resort
                    try:
                        logger.info(f"[PORT_MAPPING] Attempting alternative approach for port mapping")
                        
                        # Commit the container to a temporary image
                        temp_image_name = f"temp_sandbox_{self.container_name}_{int(time.time())}"
                        logger.info(f"[PORT_MAPPING] Committing container to temporary image: {temp_image_name}")
                        self.container.commit(repository=temp_image_name)
                        
                        # Stop and remove the container
                        logger.info(f"[PORT_MAPPING] Stopping and removing container")
                        try:
                            self.container.stop(timeout=10)
                            self.container.remove(force=True)
                        except Exception as stop_e:
                            logger.warning(f"[PORT_MAPPING] Error stopping container: {stop_e}")
                        
                        # Create new container with the port mapping
                        logger.info(f"[PORT_MAPPING] Creating new container from temporary image with port mapping")
                        new_container = self.docker_client.containers.run(
                            temp_image_name,
                            name=self.container_name,
                            command="tail -f /dev/null",  # Keep container running
                            detach=True,
                            ports={container_port: host_port},
                            volumes={os.path.abspath(self.code_dir): {'bind': '/workspace', 'mode': 'rw'}},
                            working_dir="/workspace"
                        )
                        
                        # Update container reference
                        self.container = new_container
                        
                        # Update DB record
                        if self.db_record:
                            logger.info(f"[PORT_MAPPING] Updating database record with new container ID and port")
                            self.db_record.container_id = new_container.id
                            self.db_record.port = host_port
                            self.db_record.mark_as_running()
                        
                        # Clean up temporary image
                        try:
                            logger.info(f"[PORT_MAPPING] Cleaning up temporary image")
                            self.docker_client.images.remove(temp_image_name)
                        except Exception as img_e:
                            logger.warning(f"[PORT_MAPPING] Error removing temporary image: {img_e}")
                        
                        container_restarted = True
                        logger.info(f"[PORT_MAPPING] Successfully created new container with port mapping")
                    except Exception as alt_e:
                        logger.error(f"[PORT_MAPPING] Alternative port mapping method also failed: {alt_e}")
                        raise RuntimeError(f"Failed to update port mapping: {alt_e}")
                
                # Re-run saved commands in the new container
                if container_restarted and saved_commands:
                    try:
                        logger.info(f"[PORT_MAPPING] Re-running previous commands in the new container")
                        for cmd_info in saved_commands:
                            # Extract command from ps output
                            for line in cmd_info.strip().split('\n'):
                                parts = line.strip().split()
                                if len(parts) > 7:  # ps -ef outputs: UID PID PPID C STIME TTY TIME CMD
                                    cmd = ' '.join(parts[7:])
                                    # Skip some common background processes
                                    if 'tail -f' in cmd or 'ps -ef' in cmd:
                                        continue
                                    logger.info(f"[PORT_MAPPING] Re-running command: {cmd}")
                                    try:
                                        exec_id = self.docker_client.api.exec_create(
                                            self.container.id,
                                            cmd,
                                            workdir="/workspace",
                                            detach=True
                                        )
                                        self.docker_client.api.exec_start(exec_id["Id"])
                                        logger.info(f"[PORT_MAPPING] Successfully re-ran command")
                                    except Exception as exec_e:
                                        logger.warning(f"[PORT_MAPPING] Error re-running command: {exec_e}")
                    except Exception as cmd_e:
                        logger.warning(f"[PORT_MAPPING] Error re-running commands in new container: {cmd_e}")
                
                # If a command was provided for the port mapping, run it in the new container
                if command and container_restarted and command.startswith("cmd:"):
                    cmd = command[4:].strip()
                    try:
                        logger.info(f"[PORT_MAPPING] Running command associated with port mapping: {cmd}")
                        self.exec(cmd)
                        logger.info(f"[PORT_MAPPING] Successfully ran port mapping command")
                    except Exception as cmd_e:
                        logger.warning(f"[PORT_MAPPING] Error running port mapping command: {cmd_e}")
            
            # Now handle the database record
            if self.db_record:
                try:
                    if db_mapping:
                        # Update existing mapping
                        if db_mapping.host_port != host_port:
                            logger.info(f"[PORT_MAPPING] Updating existing database mapping from {container_port}:{db_mapping.host_port} to {container_port}:{host_port}")
                            db_mapping.host_port = host_port
                            if command:
                                db_mapping.command = command
                            db_mapping.save()
                            logger.info(f"[PORT_MAPPING] Successfully updated existing port mapping record: {container_port} -> {host_port}")
                        else:
                            logger.info(f"[PORT_MAPPING] Database mapping already has the correct host port {host_port}, no update needed")
                    else:
                        # Create new mapping
                        logger.info(f"[PORT_MAPPING] Creating new database mapping: {container_port} -> {host_port}")
                        db_mapping = DockerPortMapping.objects.create(
                            sandbox=self.db_record,
                            container_port=container_port,
                            host_port=host_port,
                            command=command or f"Port added at {time.strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                        logger.info(f"[PORT_MAPPING] Successfully created new port mapping record: {container_port} -> {host_port}")
                        
                    # Ensure the main sandbox record has the updated port for the default web port
                    if container_port == 8000 and self.db_record.port != host_port:
                        self.db_record.port = host_port
                        self.db_record.save()
                        logger.info(f"[PORT_MAPPING] Updated main sandbox record with new port: {host_port}")
                        
                except Exception as e:
                    logger.error(f"[PORT_MAPPING] Failed to create/update port mapping record: {e}")
            
            # Verify the mapping was actually applied in Docker
            try:
                logger.info(f"[PORT_MAPPING] Verifying port mapping in Docker container")
                updated_container_info = self.docker_client.api.inspect_container(self.container.id)
                updated_port_mappings = updated_container_info.get('HostConfig', {}).get('PortBindings', {})
                
                if container_port_key in updated_port_mappings:
                    updated_mappings = updated_port_mappings.get(container_port_key, [])
                    if updated_mappings:
                        verified_host_port = updated_mappings[0].get('HostPort')
                        if verified_host_port == str(host_port):
                            logger.info(f"[PORT_MAPPING] Successfully verified port mapping in Docker: {container_port} -> {host_port}")
                        else:
                            logger.warning(f"[PORT_MAPPING] Port mapping verification mismatch: expected {host_port}, got {verified_host_port}")
                else:
                    logger.warning(f"[PORT_MAPPING] Could not verify port mapping in Docker container")
            except Exception as e:
                logger.error(f"[PORT_MAPPING] Error verifying port mapping: {e}")
            
            logger.info(f"[PORT_MAPPING] Port mapping process completed successfully: {container_port} -> {host_port}")
            return host_port
        except docker.errors.APIError as e:
            logger.error(f"[PORT_MAPPING] Docker API error adding port mapping: {e}")
            if "port is already allocated" in str(e).lower():
                # Try with a different port
                if host_port != self._find_available_port():
                    logger.info(f"[PORT_MAPPING] Port conflict detected on host port {host_port}, trying with a different port")
                    return self.add_port_mapping(container_port, None, command)
            raise RuntimeError(f"Failed to add port mapping: {e}")

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

def get_client_project_folder_path(project_id=None, conversation_id=None):
    """
    Generate the client project folder path based on project_id or conversation_id.
    If the folder already exists in the database, use that path instead.
    
    Args:
        project_id: The project ID
        conversation_id: The conversation ID
        
    Returns:
        tuple: (code_dir, folder_name, client_id) - The folder path, folder name, and client ID
    """
    # If both project_id and conversation_id are None, raise an error
    if project_id is None and conversation_id is None:
        logger.error("Either project_id or conversation_id must be provided")
        raise ValueError("Either project_id or conversation_id must be provided")
    
    code_dir = None
    folder_name = None
    client_id = None
    
    # Get the root directory (two levels up from this file)
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    try:
        if project_id:
            try:
                # Try to get the project and determine the client id
                project = Project.objects.get(id=project_id)
                client_id = f"client_{project.owner.id:08d}"
                
                # Check if a code generation record exists for this project
                code_gen = ProjectCodeGeneration.objects.filter(project=project).first()
                
                if code_gen:
                    # Use the existing folder name from the database
                    folder_name = code_gen.folder_name
                else:
                    # Create a new folder name
                    folder_name = f"{project_id}_{project.name.replace(' ', '_').lower()}"
                    
                    # Save the folder name in the database
                    code_gen = ProjectCodeGeneration(
                        project=project,
                        folder_name=folder_name
                    )
                    code_gen.save()
                    logger.info(f"Created new folder entry in database: {folder_name}")
                
                # Create path at the root level
                client_projects_dir = os.path.join(root_dir, "client_projects", client_id)
                code_dir = os.path.join(client_projects_dir, folder_name)
                
                # Create the directory if it doesn't exist
                os.makedirs(client_projects_dir, exist_ok=True)
                os.makedirs(code_dir, exist_ok=True)
                
                logger.info(f"Using project directory: {code_dir}")
            except Project.DoesNotExist:
                # Fallback if project doesn't exist
                client_id = "unknown"
                folder_name = f"project_{project_id}"
                code_dir = os.path.join(root_dir, "client_projects", client_id, folder_name)
                os.makedirs(code_dir, exist_ok=True)
                logger.info(f"Using fallback project directory: {code_dir}")
        elif conversation_id:
            try:
                conversation = Conversation.objects.get(id=conversation_id)
                client_id = f"client_{conversation.user.id:08d}"
                folder_name = f"conversation_{conversation_id}"
                
                # Check if this conversation is associated with a project
                if hasattr(conversation, 'project') and conversation.project:
                    # Look for existing code generation record for the project
                    code_gen = ProjectCodeGeneration.objects.filter(project=conversation.project).first()
                    
                    if code_gen:
                        # Use the project's folder if it exists
                        folder_name = code_gen.folder_name
                        client_projects_dir = os.path.join(root_dir, "client_projects", client_id)
                        code_dir = os.path.join(client_projects_dir, folder_name)
                    else:
                        # Create a conversation folder under the client's directory
                        client_convs_dir = os.path.join(root_dir, "client_projects", client_id, "conversations")
                        code_dir = os.path.join(client_convs_dir, folder_name)
                        os.makedirs(client_convs_dir, exist_ok=True)
                else:
                    # Create a conversation folder under the client's directory
                    client_convs_dir = os.path.join(root_dir, "client_projects", client_id, "conversations")
                    code_dir = os.path.join(client_convs_dir, folder_name)
                    os.makedirs(client_convs_dir, exist_ok=True)
                
                os.makedirs(code_dir, exist_ok=True)
                logger.info(f"Using conversation directory: {code_dir}")
            except Conversation.DoesNotExist:
                # Fallback if conversation doesn't exist
                client_id = "unknown"
                folder_name = f"conversation_{conversation_id}"
                code_dir = os.path.join(root_dir, "client_projects", client_id, "conversations", folder_name)
                os.makedirs(code_dir, exist_ok=True)
                logger.info(f"Using fallback conversation directory: {code_dir}")
    except Exception as e:
        logger.error(f"Error determining client project folder path: {str(e)}")
        # Fallback to a safe location
        client_id = "unknown"
        folder_name = f"project_{project_id or conversation_id}"
        code_dir = os.path.join(root_dir, "client_projects", client_id, folder_name)
        os.makedirs(code_dir, exist_ok=True)
        logger.info(f"Using emergency fallback directory due to error: {code_dir}")
    
    return code_dir, folder_name, client_id

def create_sandbox(project_id: str = None, code_dir: str = None, conversation_id: str = None, port: int = None) -> Sandbox:
    """
    Create a new sandbox for a project or conversation.
    If a sandbox already exists with this project_id or conversation_id, it will be reused.
    
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
    
    # Check if a sandbox already exists with these IDs
    try:
        # Use our utility function to find or create a record
        existing_record = find_or_create_sandbox_record(
            project_id=project_id,
            conversation_id=conversation_id,
            port=port,
            code_dir=code_dir
        )
        
        # If the sandbox exists and is already running, use get_or_create_sandbox
        # to handle the existing record properly
        if existing_record.status == 'running':
            logger.info(f"Sandbox already exists for project_id={project_id}, conversation_id={conversation_id}, reusing it")
            return get_or_create_sandbox(project_id, code_dir, conversation_id, port)
    except Exception as e:
        logger.error(f"Error checking for existing sandbox: {e}")
    
    # Determine directory path
    if code_dir is None:
        # Get folder path from database or create new one
        code_dir, _, _ = get_client_project_folder_path(project_id, conversation_id)
    
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
    
    logger.info(f"[SANDBOX] Getting or creating sandbox for project_id={project_id}, conversation_id={conversation_id}")
    
    # If code_dir is not provided, get it from the database or create a new one
    if code_dir is None:
        code_dir, _, _ = get_client_project_folder_path(project_id, conversation_id)
    
    # Check if we can find an existing sandbox for this project_id or conversation_id
    try:
        # Use project_id as the primary identifier if available
        if project_id:
            # First, try to find any sandbox with this project_id that's running
            existing_sandbox = DockerSandbox.objects.filter(
                project_id=project_id,
                status='running'
            ).first()
            
            # If no running sandbox, check for any sandbox with this project_id
            if not existing_sandbox:
                existing_sandbox = DockerSandbox.objects.filter(
                    project_id=project_id
                ).order_by('-created_at').first()
                
            if existing_sandbox:
                logger.info(f"[SANDBOX] Found existing sandbox record for project_id={project_id}")
        # If no project_id, use conversation_id
        elif conversation_id:
            # Look for a sandbox with this conversation_id
            existing_sandbox = DockerSandbox.objects.filter(
                conversation_id=conversation_id
            ).order_by('-created_at').first()
            
            if existing_sandbox:
                logger.info(f"[SANDBOX] Found existing sandbox record for conversation_id={conversation_id}")
        else:
            existing_sandbox = None
        
        # If we found an existing sandbox, check if the container is running
        if existing_sandbox:
            # Update code_dir if needed
            if not existing_sandbox.code_dir or not os.path.exists(existing_sandbox.code_dir):
                existing_sandbox.code_dir = code_dir
                existing_sandbox.save()
                
            # Get Docker client to check container state
            client = docker.from_env()
            container_running = False
            container = None
            
            try:
                if existing_sandbox.container_id:
                    container = client.containers.get(existing_sandbox.container_id)
                    container_running = container.status == 'running'
                    logger.info(f"[SANDBOX] Container exists with ID {container.short_id}, status={container.status}")
            except (docker.errors.NotFound, docker.errors.APIError) as e:
                logger.warning(f"[SANDBOX] Container not found or Docker API error: {e}")
                container_running = False
            
            # Create a sandbox instance with the existing record
            sandbox = Sandbox(
                code_dir=existing_sandbox.code_dir or code_dir,
                project_id=existing_sandbox.project_id,
                conversation_id=existing_sandbox.conversation_id,
                port=port if port is not None else existing_sandbox.port
            )
            
            # Set the database record
            sandbox.db_record = existing_sandbox
            
            # If container is running, just attach to it
            if container_running:
                sandbox.container = container
                sandbox.started_at = time.time()
                logger.info(f"[SANDBOX] Using existing running sandbox container {container.short_id}")
                return sandbox
            else:
                # Container exists but not running, start it
                logger.info(f"[SANDBOX] Found existing sandbox record but container not running, starting new container")
                return sandbox.start()
    except Exception as e:
        logger.error(f"[SANDBOX] Error checking for existing sandbox: {e}")
    
    # If we get here, we need to create a new sandbox
    logger.info(f"[SANDBOX] Creating new sandbox for project_id={project_id}, conversation_id={conversation_id}")
    
    try:
        # Create a database record first
        db_sandbox = find_or_create_sandbox_record(
            project_id=project_id,
            conversation_id=conversation_id,
            code_dir=code_dir,
            port=port,
            status='created'
        )
        
        # Create and start a new sandbox
        sandbox = Sandbox(
            code_dir=code_dir,
            project_id=project_id,
            conversation_id=conversation_id,
            port=port
        )
        
        # Set the database record and start
        sandbox.db_record = db_sandbox
        return sandbox.start()
        
    except Exception as e:
        logger.error(f"[SANDBOX] Error creating new sandbox: {e}")
        # Fall back to the old way as a last resort
        logger.info(f"[SANDBOX] Falling back to creating sandbox the old way")
        return create_sandbox(project_id=project_id, code_dir=code_dir, conversation_id=conversation_id, port=port)


def add_port_to_sandbox(
    project_id: str = None,
    conversation_id: str = None,
    container_port: int = None,
    host_port: Optional[int] = None,
    command: Optional[str] = None
) -> Optional[int]:
    """
    Add a port mapping to an existing or running sandbox.
    If the container is not running, it will attempt to start it first.
    
    Args:
        project_id: Project ID to identify the sandbox
        conversation_id: Conversation ID to identify the sandbox (if project_id not provided)
        container_port: Port number inside the container to expose (required)
        host_port: Port number on the host to map to (if None, will assign randomly)
        command: Optional description of what this port is used for
    
    Returns:
        int: The host port number that was mapped, or None if mapping failed
    
    Raises:
        ValueError: If container_port is not provided or if sandbox cannot be identified
    """
    if container_port is None:
        logger.error("[PORT_TO_SANDBOX] container_port must be provided")
        raise ValueError("container_port must be provided")
    
    logger.info(f"[PORT_TO_SANDBOX] Adding port {container_port} to sandbox for project_id={project_id}, conversation_id={conversation_id}")
    
    # Find the sandbox record - prioritize project_id if available
    sandbox_record = None
    
    try:
        if project_id:
            # First try to find a running sandbox for this project
            sandbox_record = DockerSandbox.objects.filter(
                project_id=project_id,
                status='running'
            ).first()
            
            # If no running sandbox, get the most recent one for this project
            if not sandbox_record:
                sandbox_record = DockerSandbox.objects.filter(
                    project_id=project_id
                ).order_by('-created_at').first()
                
            if sandbox_record:
                logger.info(f"[PORT_TO_SANDBOX] Found sandbox record for project_id={project_id}")
        elif conversation_id:
            # If no project_id, use conversation_id
            sandbox_record = DockerSandbox.objects.filter(
                conversation_id=conversation_id
            ).order_by('-created_at').first()
            
            if sandbox_record:
                logger.info(f"[PORT_TO_SANDBOX] Found sandbox record for conversation_id={conversation_id}")
        else:
            logger.error("[PORT_TO_SANDBOX] No project_id or conversation_id provided")
            raise ValueError("At least one of project_id or conversation_id must be provided")
    except Exception as e:
        logger.error(f"[PORT_TO_SANDBOX] Error finding sandbox record: {e}")
        raise ValueError(f"Could not find sandbox record: {e}")
    
    # If no sandbox found, create a new one
    if not sandbox_record:
        logger.info(f"[PORT_TO_SANDBOX] No existing sandbox found, creating new one for project_id={project_id}, conversation_id={conversation_id}")
        sandbox = get_or_create_sandbox(
            project_id=project_id,
            conversation_id=conversation_id
        )
        return sandbox.add_port_mapping(container_port, host_port, command)
    
    # Get the Docker client to check container status
    client = docker.from_env()
    
    try:
        # Check if the container exists and is running
        container_exists = True
        container_running = False
        
        try:
            if sandbox_record.container_id:
                container = client.containers.get(sandbox_record.container_id)
                container_running = container.status == 'running'
                logger.info(f"[PORT_TO_SANDBOX] Container exists with ID {container.short_id}, status={container.status}")
            else:
                container_exists = False
                logger.warning(f"[PORT_TO_SANDBOX] Sandbox record exists but has no container_id")
        except (docker.errors.NotFound, docker.errors.APIError) as e:
            logger.warning(f"[PORT_TO_SANDBOX] Container not found or Docker API error: {e}")
            container_exists = False
        
        # If container doesn't exist or is not running, we need to restart or create it
        if not container_exists or not container_running:
            logger.info(f"[PORT_TO_SANDBOX] Container is not running (exists={container_exists}, running={container_running}). Getting or creating sandbox.")
            
            # Get or create the sandbox using the existing record
            code_dir = sandbox_record.code_dir
            if not code_dir or not os.path.exists(code_dir):
                # Get a valid code directory if the existing one is invalid
                code_dir, _, _ = get_client_project_folder_path(
                    project_id=sandbox_record.project_id,
                    conversation_id=sandbox_record.conversation_id
                )
                # Update the record
                sandbox_record.code_dir = code_dir
                sandbox_record.save()
                logger.info(f"[PORT_TO_SANDBOX] Updated sandbox record with new code_dir: {code_dir}")
            
            # Create a sandbox instance with the existing database record
            sandbox = Sandbox(
                code_dir=code_dir,
                project_id=sandbox_record.project_id,
                conversation_id=sandbox_record.conversation_id,
                port=sandbox_record.port
            )
            sandbox.db_record = sandbox_record
            
            # Start the sandbox
            logger.info(f"[PORT_TO_SANDBOX] Starting or restarting sandbox")
            sandbox.start()
            
            # Now add the port mapping
            logger.info(f"[PORT_TO_SANDBOX] Adding port mapping to newly started sandbox")
            return sandbox.add_port_mapping(container_port, host_port, command)
        
        # Container is running, create a Sandbox instance to work with it
        logger.info(f"[PORT_TO_SANDBOX] Using existing running container")
        sandbox = Sandbox(
            code_dir=sandbox_record.code_dir,
            project_id=sandbox_record.project_id,
            conversation_id=sandbox_record.conversation_id,
            port=sandbox_record.port
        )
        sandbox.container = container
        sandbox.db_record = sandbox_record
        
        # Add the port mapping
        logger.info(f"[PORT_TO_SANDBOX] Adding port mapping to existing container")
        return sandbox.add_port_mapping(container_port, host_port, command)
    
    except Exception as e:
        logger.error(f"[PORT_TO_SANDBOX] Error adding port mapping: {e}")
        raise RuntimeError(f"Failed to add port mapping: {e}")

def find_or_create_sandbox_record(project_id=None, conversation_id=None, container_name=None, 
                              image=None, port=None, code_dir=None, resource_limits=None, status='created'):
    """
    Find an existing sandbox record with the given project_id or conversation_id, or create a new one.
    This helps prevent duplicate records from being created.
    
    Args:
        project_id: ID of the project
        conversation_id: ID of the conversation  
        container_name: Name of the Docker container
        image: Docker image used
        port: Port mapping
        code_dir: Directory containing code
        resource_limits: Resource limits for the container
        status: Initial status of the sandbox
        
    Returns:
        DockerSandbox instance
    """
    if project_id is None and conversation_id is None:
        raise ValueError("Either project_id or conversation_id must be provided")
        
    # Build query to find existing sandbox
    query = Q()
    if project_id:
        query &= Q(project_id=project_id)
    if conversation_id:
        query &= Q(conversation_id=conversation_id)
    
    # Try to find an existing sandbox
    existing_sandbox = DockerSandbox.objects.filter(query).first()
    
    if existing_sandbox:
        logger.info(f"Found existing sandbox for project_id={project_id}, conversation_id={conversation_id}")
        
        # Update fields if provided
        if container_name:
            existing_sandbox.container_name = container_name
        if image:
            existing_sandbox.image = image
        if port is not None:
            existing_sandbox.port = port
        if code_dir:
            existing_sandbox.code_dir = code_dir
        if resource_limits:
            existing_sandbox.resource_limits = resource_limits
            
        # Update status if not already running
        if existing_sandbox.status != 'running':
            existing_sandbox.status = status
            
        existing_sandbox.save()
        return existing_sandbox
    
    # Create new sandbox if one doesn't exist
    logger.info(f"Creating new sandbox record for project_id={project_id}, conversation_id={conversation_id}")
    return DockerSandbox.objects.create(
        project_id=project_id,
        conversation_id=conversation_id,
        container_name=container_name or f"lfg-{'project-' + project_id if project_id else 'conversation-' + conversation_id}",
        image=image,
        port=port,
        code_dir=code_dir,
        resource_limits=resource_limits,
        status=status
    )

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
