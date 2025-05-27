# Remote Polyglot-Sandbox Orchestrator

A Python utility for creating sandboxed Docker environments to run code safely on remote servers with automatic timeout and cleanup.

## Features

- 🚀 **Remote Execution**: Run containers on remote Docker hosts via SSH or TLS
- 📦 **Code Injection**: Mount or copy your code into the container
- 🔄 **Interactive Commands**: Execute commands and capture output 
- ⏱️ **Auto-Termination**: Containers automatically terminate after a specified timeout
- 🛡️ **Resource Limits**: Set CPU, memory, and other resource constraints
- 🧩 **Extensible**: Hooks for custom start/kill behavior
- 🌐 **Port Forwarding**: Expose container ports to the host for accessing web apps and services

## Requirements

- Python 3.6+
- Docker (local or remote)
- Docker SDK for Python (`docker` package)

```bash
pip install docker
```

## Quick Start

```python
from coding.docker.docker_utils import Sandbox

# Using context manager (recommended)
with Sandbox(code_dir="~/my_project", timeout=300) as sandbox:
    # Install dependencies
    sandbox.exec("pip install -r requirements.txt")
    
    # Run your code
    output = sandbox.exec("python main.py")
    print(output)
```

## Usage Examples

### Basic Usage

```python
from coding.docker.docker_utils import Sandbox, create_project_sandbox

# Create a sandbox for a specific project
sandbox = create_project_sandbox(project_id="my-awesome-project")

# Run commands
sandbox.exec("ls -la")
sandbox.exec("python -m pip install numpy pandas")
result = sandbox.exec("python -c 'import numpy as np; print(np.random.rand(5))'")
print(result)

# Don't forget to close the sandbox when done
sandbox.close()
```

### Custom Resource Limits

```python
from coding.docker.docker_utils import Sandbox

# Create a sandbox with custom resource limits
sandbox = Sandbox(
    code_dir="~/my_project",
    timeout=600,  # 10 minutes
    limits={
        "mem_limit": "2g",        # 2GB RAM
        "nano_cpus": 2_000_000_000,  # 2 CPUs
        "pids_limit": 200,        # Max 200 processes
    }
)

# Start the sandbox
sandbox.start()

# Run commands...

# Close when done
sandbox.close()
```

### Using a Custom Docker Image

```python
from coding.docker.docker_utils import Sandbox

# Create a sandbox with a custom Docker image
with Sandbox(
    code_dir="~/java_project",
    image="openjdk:11",
    timeout=300
) as sandbox:
    # Compile and run Java code
    sandbox.exec("javac Main.java")
    output = sandbox.exec("java Main")
    print(output)
```

### Exposing a Container Port

```python
from coding.docker.docker_utils import Sandbox
import time
import requests

# Create a sandbox with port forwarding
with Sandbox(
    code_dir="~/server_project",
    timeout=300,
    ports={'8080/tcp': 22000}  # Map container port 8080 to host port 22000
) as sandbox:
    # Start a server in the container
    sandbox.exec("python -m http.server 8080 &")
    
    # Wait for the server to start
    time.sleep(1)
    
    # Access the server from the host
    response = requests.get("http://localhost:22000")
    print(response.text)
```

### Running a Web Application

You can run complete web applications in the sandbox and access them from the host:

```python
from coding.docker.docker_utils import Sandbox
import time

# Create web server file
with open("server.py", "w") as f:
    f.write('''
import http.server
import socketserver

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Sandbox Web App</title>
            <style>
                body { font-family: Arial; max-width: 800px; margin: 0 auto; padding: 20px; }
                .container { border: 1px solid #ddd; padding: 20px; border-radius: 5px; }
            </style>
        </head>
        <body>
            <h1>Hello from Sandbox!</h1>
            <div class="container">
                <p>This web app is running inside a Docker container</p>
            </div>
        </body>
        </html>
        """
        self.wfile.write(html.encode())

httpd = socketserver.TCPServer(("0.0.0.0", 3000), Handler)
httpd.serve_forever()
''')

# Create and run the sandbox with port mapping
with Sandbox(
    code_dir="./",
    timeout=300,
    ports={'3000/tcp': 3000}  # Map container port 3000 to host port 3000
) as sandbox:
    # Start the web server
    print("Starting web server...")
    sandbox.exec("python server.py &")
    
    print("Web application is running at http://localhost:3000")
    
    # Keep the sandbox running until user presses Enter
    input("Press Enter to stop the server and close the sandbox...")

### Copying Files to the Container

```python
from coding.docker.docker_utils import Sandbox

with Sandbox(code_dir="/tmp/empty_dir") as sandbox:
    # Copy a file to the container
    sandbox.copy_to_container(
        src="/path/to/local/file.txt", 
        dest="/workspace/"
    )
    
    # Verify the file exists
    output = sandbox.exec("cat /workspace/file.txt")
    print(output)
```

### Listing and Managing Sandboxes

```python
from coding.docker.docker_utils import list_running_sandboxes, kill_all_sandboxes, get_sandbox_by_project_id

# List all running sandboxes
sandboxes = list_running_sandboxes()
for box in sandboxes:
    print(f"Sandbox: {box['project_id']} - Status: {box['status']}")

# Get a specific sandbox
sandbox_info = get_sandbox_by_project_id("my-project-id")
if sandbox_info:
    print(f"Found sandbox: {sandbox_info['name']}")

# Kill all running sandboxes
kill_all_sandboxes()
```

## API Reference

### Sandbox Class

```python
class Sandbox:
    def __init__(
        self,
        code_dir: str,                        # Directory containing code to run
        timeout: int = 300,                   # Auto-terminate after N seconds (default: 5 minutes)
        image: Optional[str] = None,          # Docker image to use (default: gitpod/workspace-full:latest)
        buildpacks: bool = False,             # Whether to build a custom image with Buildpacks
        limits: Optional[Dict] = None,        # Resource limits for the container
        network_mode: str = "bridge",         # Docker network mode ("bridge", "none", "host")
        project_id: str = None,               # Unique identifier for the project
        on_start: Optional[Callable] = None,  # Callback function on container start
        on_kill: Optional[Callable] = None,   # Callback function on container kill
        ports: Optional[Dict[str, int]] = None, # Port mappings from container to host
    )
    
    def start(self)                           # Start the container
    def exec(self, cmd, workdir="/workspace", stream=True) -> str  # Execute a command in the container
    def copy_to_container(self, src, dest)    # Copy files from host to container
    def close()                               # Stop and remove the container
```

### Utility Functions

```python
def list_running_sandboxes() -> List[Dict]    # List all running sandbox containers
def kill_all_sandboxes()                      # Kill and remove all sandbox containers
def get_sandbox_by_project_id(project_id) -> Optional[Dict]  # Get sandbox by project ID
def create_project_sandbox(project_id, code_dir=None) -> Sandbox  # Create a sandbox for a project
```

## Environment Variables

The Docker client uses the following environment variables:

- `DOCKER_HOST`: Set to `ssh://user@hostname` for SSH connection or `tcp://hostname:port` for TCP/TLS
- `DOCKER_TLS_VERIFY`: Set to `1` to verify TLS certificates
- `DOCKER_CERT_PATH`: Path to TLS certificates
- `DOCKER_API_VERSION`: Docker API version to use

Example for SSH connection:

```bash
export DOCKER_HOST=ssh://username@remote-server
```

## Security Considerations

- Containers run as non-root by default when using the GitPod image
- Use `network_mode="none"` for complete network isolation
- Resource limits prevent container DoS attacks
- Auto-termination ensures containers don't run indefinitely
- Always validate and sanitize command inputs before execution

## Troubleshooting

- **Permission denied**: Make sure the Docker daemon is running and the user has permission to access it
- **Connection refused**: Check that the Docker host is correct and reachable
- **Image not found**: Verify the image name and make sure it's available in the registry
- **Storage options error**: If you encounter an error about storage options (`--storage-opt is supported only for overlay over xfs with 'pquota' mount option`), you may need to customize the container limits to remove storage options. This is common on macOS and Windows Docker Desktop setups:

```python
# Create a sandbox without storage options
sandbox = Sandbox(
    code_dir="~/my_project",
    limits={
        "mem_limit": "1g",
        "nano_cpus": 1_000_000_000,  # 1 CPU
        "pids_limit": 100
        # No storage_opt here
    }
)
```

## License

[MIT License](LICENSE)

## Running the Examples

The package includes several example scripts that demonstrate how to use the Docker sandbox. 

To run the examples:

```bash
# Navigate to the docker directory
cd coding/docker

# Run a specific example
python run_example.py basic  # Runs the basic usage example
python run_example.py server # Runs the HTTP server example

# List all available examples
python run_example.py
```

Available examples:
- `basic`: Basic sandbox usage with context manager
- `project`: Project-specific sandbox creation
- `resources`: Custom resource limits configuration
- `commands`: Multiple command execution
- `manage`: Managing multiple sandboxes
- `image`: Using custom Docker images
- `server`: Running an HTTP server with port forwarding
- `all`: Run all examples (this may take some time)

### Common Issues

When running the examples, you might encounter the following issues:

1. **Import errors**: Make sure you're running the examples from the correct directory.

2. **Docker not running**: Ensure Docker Desktop or Docker daemon is running on your system.

3. **Storage options error**: On macOS or Windows, you might see an error about storage options not being supported. This is expected and has been addressed in the latest version of the code.

4. **Port already in use**: If you see an error about a port being already in use, you may have another service using that port. You can modify the port mapping in the examples. 