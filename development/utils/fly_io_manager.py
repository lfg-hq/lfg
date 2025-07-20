"""
Fly.io Micro-VM Manager

This module provides functionality to launch and manage Fly.io micro-VMs using their Machines API.
Fly Machines are fast-launching VMs that can boot in ~300ms.

API Documentation: https://fly.io/docs/machines/api/
Authentication: All requests require a Fly.io API token in the Authorization header

Key Features:
- Create and launch micro-VMs with custom configurations
- Start, stop, and restart machines
- Monitor machine status and logs
- Manage machine lifecycle
- Deploy containerized applications
"""

import os
import json
import time
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


class MachineState(Enum):
    """Possible states for a Fly Machine"""
    CREATED = "created"
    STARTING = "starting"
    STARTED = "started"
    STOPPING = "stopping"
    STOPPED = "stopped"
    DESTROYING = "destroying"
    DESTROYED = "destroyed"
    ERROR = "error"


@dataclass
class MachineConfig:
    """Configuration for creating a Fly Machine"""
    image: str  # Required: Docker image (e.g., "registry-1.docker.io/library/ubuntu:latest")
    name: Optional[str] = None
    region: Optional[str] = None  # e.g., "iad", "lax", "ams"
    cpus: int = 1  # Number of CPUs (shared: 1, 2, 4, 6, 8)
    memory_mb: int = 256  # Memory in MB (256, 512, 1024, 2048, 4096, 8192)
    env: Optional[Dict[str, str]] = None  # Environment variables
    cmd: Optional[List[str]] = None  # Override container CMD
    entrypoint: Optional[List[str]] = None  # Override container ENTRYPOINT
    services: Optional[List[Dict]] = None  # HTTP/TCP services configuration
    mounts: Optional[List[Dict]] = None  # Volume mounts
    restart_policy: str = "no"  # "no", "on-failure", "always"
    auto_destroy: bool = False  # Auto-destroy on exit
    skip_launch: bool = False  # Create without starting


class FlyIOManager:
    """
    Manager class for interacting with Fly.io Machines API
    
    Example usage:
        manager = FlyIOManager(api_token="your-fly-api-token")
        
        # Create an app
        app = manager.create_app("my-app-name", "iad")
        
        # Launch a machine
        config = MachineConfig(
            image="nginx:latest",
            name="web-server",
            cpus=1,
            memory_mb=512,
            services=[{
                "ports": [{"port": 80, "handlers": ["http"]}],
                "protocol": "tcp",
                "internal_port": 80
            }]
        )
        machine = manager.create_machine("my-app-name", config)
    """
    
    BASE_URL = "https://api.machines.dev/v1"
    
    def __init__(self, api_token: str):
        """
        Initialize the Fly.io Manager
        
        Args:
            api_token: Fly.io API token (get from: fly auth token)
        """
        self.api_token = api_token
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make HTTP request to Fly.io API"""
        url = f"{self.BASE_URL}{endpoint}"
        
        response = requests.request(
            method=method,
            url=url,
            headers=self.headers,
            json=data
        )
        
        if response.status_code >= 400:
            error_msg = f"API Error: {response.status_code} - {response.text}"
            raise Exception(error_msg)
        
        return response.json() if response.text else {}
    
    # ============== APP MANAGEMENT ==============
    
    def create_app(self, app_name: str, org_slug: Optional[str] = None) -> Dict:
        """
        Create a new Fly app
        
        Args:
            app_name: Name for the app (must be unique)
            org_slug: Organization slug (optional)
        
        Returns:
            App details
            
        API Endpoint: POST /v1/apps
        """
        data = {"app_name": app_name}
        if org_slug:
            data["org_slug"] = org_slug
        
        return self._make_request("POST", "/apps", data)
    
    def get_app(self, app_name: str) -> Dict:
        """
        Get app details
        
        API Endpoint: GET /v1/apps/{app_name}
        """
        return self._make_request("GET", f"/apps/{app_name}")
    
    def delete_app(self, app_name: str) -> None:
        """
        Delete an app and all its resources
        
        API Endpoint: DELETE /v1/apps/{app_name}
        """
        self._make_request("DELETE", f"/apps/{app_name}")
    
    # ============== MACHINE MANAGEMENT ==============
    
    def create_machine(self, app_name: str, config: MachineConfig, region: Optional[str] = None) -> Dict:
        """
        Create and optionally launch a new machine
        
        Args:
            app_name: Name of the app to create machine in
            config: Machine configuration
            region: Region to launch in (optional)
        
        Returns:
            Machine details including ID
            
        API Endpoint: POST /v1/apps/{app_name}/machines
        """
        machine_config = {
            "image": config.image,
            "guest": {
                "cpus": config.cpus,
                "memory_mb": config.memory_mb
            }
        }
        
        if config.env:
            machine_config["env"] = config.env
        
        if config.cmd:
            machine_config["init"] = {"cmd": config.cmd}
        
        if config.entrypoint:
            if "init" not in machine_config:
                machine_config["init"] = {}
            machine_config["init"]["entrypoint"] = config.entrypoint
        
        if config.services:
            machine_config["services"] = config.services
        
        if config.mounts:
            machine_config["mounts"] = config.mounts
        
        machine_config["restart"] = {"policy": config.restart_policy}
        machine_config["auto_destroy"] = config.auto_destroy
        
        data = {
            "config": machine_config,
            "skip_launch": config.skip_launch
        }
        
        if config.name:
            data["name"] = config.name
        
        if region or config.region:
            data["region"] = region or config.region
        
        return self._make_request("POST", f"/apps/{app_name}/machines", data)
    
    def get_machine(self, app_name: str, machine_id: str) -> Dict:
        """
        Get machine details
        
        API Endpoint: GET /v1/apps/{app_name}/machines/{machine_id}
        """
        return self._make_request("GET", f"/apps/{app_name}/machines/{machine_id}")
    
    def list_machines(self, app_name: str) -> List[Dict]:
        """
        List all machines for an app
        
        API Endpoint: GET /v1/apps/{app_name}/machines
        """
        return self._make_request("GET", f"/apps/{app_name}/machines")
    
    def start_machine(self, app_name: str, machine_id: str) -> None:
        """
        Start a stopped machine
        
        API Endpoint: POST /v1/apps/{app_name}/machines/{machine_id}/start
        """
        self._make_request("POST", f"/apps/{app_name}/machines/{machine_id}/start")
    
    def stop_machine(self, app_name: str, machine_id: str, timeout: int = 30) -> None:
        """
        Stop a running machine
        
        Args:
            app_name: App name
            machine_id: Machine ID
            timeout: Timeout in seconds (default: 30)
            
        API Endpoint: POST /v1/apps/{app_name}/machines/{machine_id}/stop
        """
        data = {"timeout": timeout}
        self._make_request("POST", f"/apps/{app_name}/machines/{machine_id}/stop", data)
    
    def restart_machine(self, app_name: str, machine_id: str, timeout: int = 30) -> None:
        """
        Restart a machine
        
        API Endpoint: POST /v1/apps/{app_name}/machines/{machine_id}/restart
        """
        data = {"timeout": timeout}
        self._make_request("POST", f"/apps/{app_name}/machines/{machine_id}/restart", data)
    
    def update_machine(self, app_name: str, machine_id: str, config: Dict) -> Dict:
        """
        Update machine configuration
        
        API Endpoint: POST /v1/apps/{app_name}/machines/{machine_id}
        """
        return self._make_request("POST", f"/apps/{app_name}/machines/{machine_id}", {"config": config})
    
    def delete_machine(self, app_name: str, machine_id: str, force: bool = False) -> None:
        """
        Delete a machine
        
        Args:
            app_name: App name
            machine_id: Machine ID
            force: Force delete even if running
            
        API Endpoint: DELETE /v1/apps/{app_name}/machines/{machine_id}
        """
        endpoint = f"/apps/{app_name}/machines/{machine_id}"
        if force:
            endpoint += "?force=true"
        self._make_request("DELETE", endpoint)
    
    def wait_for_state(self, app_name: str, machine_id: str, 
                      target_state: MachineState, timeout: int = 60) -> bool:
        """
        Wait for machine to reach a specific state
        
        Args:
            app_name: App name
            machine_id: Machine ID
            target_state: Desired state
            timeout: Timeout in seconds
            
        Returns:
            True if state reached, False if timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            machine = self.get_machine(app_name, machine_id)
            if machine.get("state") == target_state.value:
                return True
            time.sleep(1)
        
        return False
    
    def get_machine_logs(self, app_name: str, machine_id: str, lines: int = 50) -> List[str]:
        """
        Get machine logs
        
        Note: This is a simplified version. Full log streaming requires WebSocket connection.
        """
        # This would typically use the logs endpoint or WebSocket streaming
        # For now, returning placeholder
        return [f"Logs for machine {machine_id} would be retrieved here"]
    
    # ============== VOLUME MANAGEMENT ==============
    
    def create_volume(self, app_name: str, volume_name: str, size_gb: int, region: str) -> Dict:
        """
        Create a persistent volume
        
        Args:
            app_name: App name
            volume_name: Volume name
            size_gb: Size in gigabytes
            region: Region to create volume in
            
        API Endpoint: POST /v1/apps/{app_name}/volumes
        """
        data = {
            "name": volume_name,
            "size_gb": size_gb,
            "region": region
        }
        return self._make_request("POST", f"/apps/{app_name}/volumes", data)
    
    def list_volumes(self, app_name: str) -> List[Dict]:
        """
        List all volumes for an app
        
        API Endpoint: GET /v1/apps/{app_name}/volumes
        """
        return self._make_request("GET", f"/apps/{app_name}/volumes")
    
    def delete_volume(self, app_name: str, volume_id: str) -> None:
        """
        Delete a volume
        
        API Endpoint: DELETE /v1/apps/{app_name}/volumes/{volume_id}
        """
        self._make_request("DELETE", f"/apps/{app_name}/volumes/{volume_id}")
    
    # ============== HELPER METHODS ==============
    
    def launch_web_app(self, app_name: str, image: str, port: int = 8080, 
                      region: str = "iad", cpus: int = 1, memory_mb: int = 512) -> Dict:
        """
        Helper method to quickly launch a web application
        
        Args:
            app_name: App name
            image: Docker image
            port: Internal port the app listens on
            region: Region to deploy to
            cpus: Number of CPUs
            memory_mb: Memory in MB
            
        Returns:
            Machine details
        """
        config = MachineConfig(
            image=image,
            name=f"{app_name}-web",
            region=region,
            cpus=cpus,
            memory_mb=memory_mb,
            services=[{
                "ports": [{
                    "port": 443,
                    "handlers": ["http", "tls"]
                }, {
                    "port": 80,
                    "handlers": ["http"]
                }],
                "protocol": "tcp",
                "internal_port": port
            }]
        )
        
        return self.create_machine(app_name, config)
    
    def launch_worker(self, app_name: str, image: str, cmd: List[str], 
                     region: str = "iad", cpus: int = 1, memory_mb: int = 512) -> Dict:
        """
        Helper method to launch a background worker
        
        Args:
            app_name: App name
            image: Docker image
            cmd: Command to run
            region: Region to deploy to
            cpus: Number of CPUs
            memory_mb: Memory in MB
            
        Returns:
            Machine details
        """
        config = MachineConfig(
            image=image,
            name=f"{app_name}-worker",
            region=region,
            cpus=cpus,
            memory_mb=memory_mb,
            cmd=cmd,
            restart_policy="on-failure"
        )
        
        return self.create_machine(app_name, config)


# ============== USAGE EXAMPLES ==============

if __name__ == "__main__":
    # Example usage
    print("""
    Fly.io Micro-VM Manager - Usage Examples
    
    # Initialize manager
    manager = FlyIOManager(api_token="your-fly-api-token")
    
    # Create an app
    app = manager.create_app("my-awesome-app")
    
    # Launch a web server
    web_machine = manager.launch_web_app(
        app_name="my-awesome-app",
        image="nginx:latest",
        port=80,
        region="iad"
    )
    
    # Launch a custom machine
    config = MachineConfig(
        image="python:3.11-slim",
        name="data-processor",
        cpus=2,
        memory_mb=1024,
        env={"API_KEY": "secret"},
        cmd=["python", "process.py"]
    )
    machine = manager.create_machine("my-awesome-app", config)
    
    # Manage machines
    manager.stop_machine("my-awesome-app", machine["id"])
    manager.start_machine("my-awesome-app", machine["id"])
    manager.delete_machine("my-awesome-app", machine["id"])
    """)