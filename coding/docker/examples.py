#!/usr/bin/env python3
"""
Examples of using the Docker Sandbox utility for various scenarios.

This file contains practical examples for using the docker_utils module
to create and manage sandboxed Docker environments.
"""

import os
import sys
import tempfile
import time
import requests

# Update the import path to use the correct module
try:
    # Try importing from the coding package first (when installed as a package)
    from coding.docker.docker_utils import (
        Sandbox, 
        create_project_sandbox, 
        list_running_sandboxes, 
        kill_all_sandboxes,
        get_sandbox_by_project_id
    )
except ImportError:
    # Fall back to local import if the module is not installed as a package
    from docker_utils import (
        Sandbox, 
        create_project_sandbox, 
        list_running_sandboxes, 
        kill_all_sandboxes,
        get_sandbox_by_project_id
    )

def example_basic_usage():
    """Basic usage of the Sandbox class with context manager."""
    print("\n=== Basic Sandbox Usage ===")
    
    # Create a temporary directory with a test script
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a simple Python script
        with open(os.path.join(temp_dir, "hello.py"), "w") as f:
            f.write('print("Hello from Docker Sandbox!")\n')
            f.write('print("This is running in an isolated container.")\n')
        
        print(f"Created test directory at: {temp_dir}")
        
        # Create and use a sandbox with context manager
        print("Starting sandbox...")
        with Sandbox(code_dir=temp_dir, timeout=60) as sandbox:
            print("Sandbox started successfully.")
            
            # Run the Python script
            print("\nRunning Python script:")
            output = sandbox.exec("python hello.py")
            print(f"Output from container:\n{output}")
            
            # Run some shell commands
            print("\nRunning shell commands:")
            output = sandbox.exec("uname -a")
            print(f"System info: {output.strip()}")
            
            # Check container environment
            print("\nContainer environment:")
            output = sandbox.exec("ls -la /workspace")
            print(output)
        
        print("Sandbox closed automatically via context manager.")

def example_project_sandbox():
    """Create a sandbox for a specific project."""
    print("\n=== Project-Specific Sandbox ===")
    
    project_id = f"example-project-{os.getpid()}"
    print(f"Creating sandbox for project: {project_id}")
    
    # Create a project sandbox
    sandbox = create_project_sandbox(project_id)
    
    try:
        # Run some commands
        print("\nChecking container environment:")
        output = sandbox.exec("echo 'Project directory:' && ls -la /workspace")
        print(output)
        
        print("\nInstalling a Python package:")
        output = sandbox.exec("pip install --no-cache-dir requests")
        print("Package installation completed.")
        
        print("\nVerifying package installation:")
        output = sandbox.exec("python -c 'import requests; print(f\"Requests version: {requests.__version__}\")'")
        print(output)
    finally:
        # Always close the sandbox to clean up resources
        print("\nClosing the sandbox...")
        sandbox.close()
        print("Sandbox closed successfully.")

def example_custom_resources():
    """Create a sandbox with custom resource limits."""
    print("\n=== Custom Resource Limits ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        print("Creating sandbox with custom resource limits...")
        
        # Create a sandbox with custom resource limits
        with Sandbox(
            code_dir=temp_dir,
            timeout=60,
            limits={
                "mem_limit": "512m",        # 512MB RAM
                "nano_cpus": 500_000_000,   # 0.5 CPU
                "pids_limit": 50,           # Max 50 processes
            }
        ) as sandbox:
            print("Sandbox created with custom resource limits.")
            
            print("\nChecking available resources:")
            
            # Check memory limit
            output = sandbox.exec("free -h")
            print(f"Memory information:\n{output}")
            
            # Check CPU info - fix the command for Alpine/BusyBox compatibility
            output = sandbox.exec("cat /proc/cpuinfo")
            print(f"CPU count: {output.strip()}")
            
            # Test resource limits with a simple workload
            print("\nRunning a simple workload:")
            script = """
import multiprocessing
cores = multiprocessing.cpu_count()
print(f"Available CPU cores: {cores}")
"""
            
            # Write the script to a file - fix indentation
            with open(os.path.join(temp_dir, "resources.py"), "w") as f:
                f.write(script.strip())  # Use strip() to remove leading/trailing whitespace
            
            # Execute the script
            output = sandbox.exec("python resources.py")
            print(output)

def example_multiple_commands():
    """Execute multiple commands in the same sandbox."""
    print("\n=== Multiple Commands Execution ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a simple shell script
        with open(os.path.join(temp_dir, "script.sh"), "w") as f:
            f.write("#!/bin/bash\n")
            f.write("echo 'This is a shell script running in the container'\n")
            f.write("echo 'Current directory:' $(pwd)\n")
            f.write("echo 'Environment variables:'\n")
            f.write("env | sort\n")
            f.write("ls -la\n")
            f.write("ls -la ../\n")
            f.write("pwd\n")
        
        print("Created shell script in temporary directory.")
        
        with Sandbox(code_dir=temp_dir, timeout=60) as sandbox:
            print("Sandbox started.")
            
            # Make the script executable
            sandbox.exec("chmod +x /workspace/script.sh")
            
            # Execute multiple commands
            print("\nRunning multiple commands:")
            
            print("\n1. Creating a directory:")
            output = sandbox.exec("mkdir -p /workspace/data")
            
            print("\n2. Creating a file:")
            output = sandbox.exec("echo 'Hello, world!' > /workspace/data/file.txt")
            
            print("\n3. Reading the file:")
            output = sandbox.exec("cat /workspace/data/file.txt")
            print(f"File contents: {output.strip()}")
            
            print("\n4. Running the shell script:")
            output = sandbox.exec("/workspace/script.sh")
            print(f"Script output:\n{output}")

def example_manage_sandboxes():
    """Demonstrate management of multiple sandboxes."""
    print("\n=== Managing Multiple Sandboxes ===")
    
    # First, clean up any existing sandboxes from previous runs
    kill_all_sandboxes()
    print("Cleaned up existing sandboxes.")
    
    # Create multiple sandboxes
    sandboxes = []
    for i in range(3):
        project_id = f"manage-example-{i}-{os.getpid()}"
        print(f"Creating sandbox {i+1}...")
        
        # Create a temporary code directory
        temp_dir = tempfile.mkdtemp()
        
        # Create a sandbox
        sandbox = Sandbox(code_dir=temp_dir, project_id=project_id)
        sandbox.start()
        sandboxes.append((sandbox, temp_dir))
        
        # Run a background process to keep it busy
        sandbox.exec(f"echo 'Sandbox {i+1} is running' > /workspace/status.txt")
    
    try:
        # List all running sandboxes
        print("\nListing all running sandboxes:")
        running_sandboxes = list_running_sandboxes()
        for i, box in enumerate(running_sandboxes):
            print(f"  {i+1}. {box['name']} (Status: {box['status']})")
        
        # Get info about a specific sandbox
        if sandboxes:
            project_id = sandboxes[0][0].project_id
            print(f"\nGetting info for sandbox with project ID: {project_id}")
            info = get_sandbox_by_project_id(project_id)
            if info:
                print(f"  Container ID: {info['id']}")
                print(f"  Name: {info['name']}")
                print(f"  Status: {info['status']}")
                print(f"  Image: {info['image']}")
            else:
                print("Sandbox not found.")
    finally:
        # Clean up all sandboxes
        print("\nCleaning up all sandboxes...")
        for sandbox, temp_dir in sandboxes:
            sandbox.close()
            try:
                os.rmdir(temp_dir)
            except:
                pass
        print("All sandboxes closed.")

def example_custom_image():
    """Using a custom Docker image with specific requirements."""
    print("\n=== Using a Custom Docker Image ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Using an Ubuntu image instead of the default
        print("Creating sandbox with Ubuntu image...")
        
        with Sandbox(
            code_dir=temp_dir,
            image="ubuntu:latest",
            timeout=60
        ) as sandbox:
            print("Sandbox with Ubuntu image started.")
            
            # Update package lists and install Python
            print("\nUpdating package lists and installing Python...")
            sandbox.exec("apt-get update && apt-get install -y python3 python3-pip")
            
            # Create a simple Python script
            with open(os.path.join(temp_dir, "test.py"), "w") as f:
                f.write('print("Hello from Ubuntu container!")\n')
                f.write('import platform\n')
                f.write('print(f"Platform: {platform.platform()}")\n')
            
            # Run the script
            print("\nRunning Python script in Ubuntu container:")
            output = sandbox.exec("python3 /workspace/test.py")
            print(output)

def example_http_server():
    """Start a simple HTTP server in the container on port 22000."""
    print("\n=== HTTP Server Example ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a simple Python HTTP server script
        with open(os.path.join(temp_dir, "server.py"), "w") as f:
            f.write('''
import http.server
import socketserver
import json
import sys
from datetime import datetime

# Print startup messages to help with debugging
print("Server starting up...", file=sys.stderr)
print(f"Current time: {datetime.now().isoformat()}", file=sys.stderr)
print("Python version: " + sys.version, file=sys.stderr)
print("Server will listen on 0.0.0.0:22000", file=sys.stderr)

try:
    class HTMLHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            
            # Create a simple HTML page with dynamic content
            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Docker Sandbox Server</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.6;
            color: #333;
        }}
        header {{
            background-color: #4CAF50;
            color: white;
            padding: 10px 20px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
        .container {{
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 20px;
            background-color: #f9f9f9;
        }}
        .info {{
            display: flex;
            justify-content: space-between;
            margin-top: 20px;
        }}
        .info div {{
            flex: 1;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 3px;
            margin: 0 5px;
            background-color: white;
        }}
        h1 {{
            margin: 0;
        }}
        footer {{
            margin-top: 20px;
            text-align: center;
            font-size: 0.8em;
            color: #777;
        }}
    </style>
</head>
<body>
    <header>
        <h1>Hello World from Docker Sandbox!</h1>
    </header>
    
    <div class="container">
        <h2>Welcome to the Sandboxed Web Server</h2>
        <p>This is a simple web server running inside a Docker container.</p>
        <p>The server is automatically managed and will be terminated when the sandbox closes.</p>
        
        <div class="info">
            <div>
                <h3>Server Info</h3>
                <p><strong>Date/Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p><strong>Port:</strong> 22000</p>
                <p><strong>Path:</strong> {self.path}</p>
            </div>
            <div>
                <h3>Request Info</h3>
                <p><strong>Client:</strong> {self.client_address[0]}</p>
                <p><strong>User Agent:</strong> {self.headers.get('User-Agent', 'Unknown')}</p>
                <p><strong>Host:</strong> {self.headers.get('Host', 'Unknown')}</p>
            </div>
        </div>
    </div>
    
    <footer>
        <p>Remote Polyglot-Sandbox Orchestrator &copy; {datetime.now().year}</p>
    </footer>
</body>
</html>"""

            self.wfile.write(html.encode('utf-8'))
            print(f"GET request handled for path: {self.path}", file=sys.stderr)
        
        def do_POST(self):
            """Handle POST requests to demonstrate API functionality"""
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            print(f"POST request received with {content_length} bytes", file=sys.stderr)
            
            # Try to parse as JSON
            try:
                data = json.loads(post_data.decode('utf-8'))
                response = {
                    "success": True,
                    "message": "Data received successfully",
                    "data": data,
                    "timestamp": datetime.now().isoformat()
                }
                print(f"Request contained valid JSON: {data}", file=sys.stderr)
            except Exception as e:
                response = {
                    "success": False,
                    "message": f"Failed to parse JSON data: {str(e)}",
                    "received": post_data.decode('utf-8'),
                    "timestamp": datetime.now().isoformat()
                }
                print(f"Error parsing JSON: {e}", file=sys.stderr)
            
            # Send response
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response, indent=2).encode('utf-8'))
        
        def log_message(self, format, *args):
            # Log to stderr instead of suppressing
            print(f"Server log: {format % args}", file=sys.stderr)

    print("Starting server at port 22000...")
    httpd = socketserver.TCPServer(("0.0.0.0", 22000), HTMLHandler)
    print("Server started successfully!", file=sys.stderr)
    httpd.serve_forever()
except Exception as e:
    print(f"ERROR STARTING SERVER: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)
''')
        
        # Create a sample JavaScript file to demonstrate static file serving
        with open(os.path.join(temp_dir, "app.js"), "w") as f:
            f.write('''
// Sample JavaScript file
console.log("This is a JavaScript file from the Docker sandbox");

function callSandboxAPI() {
    fetch('/api/data', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            message: "Hello from client",
            timestamp: new Date().toISOString()
        })
    })
    .then(response => response.json())
    .then(data => console.log('API response:', data))
    .catch(error => console.error('Error:', error));
}
''')
        
        print("Created HTTP server script with logging to stderr.")
        
        # Create a sandbox with port mapping for the HTTP server
        with Sandbox(
            code_dir=temp_dir,
            timeout=120,  # 2 minutes
            ports={'8000/tcp': 22000}  # Map container port 22000 to host port 22000
        ) as sandbox:
            print("Sandbox with port mapping started.")
            
            # Start the HTTP server and capture its output
            print("Starting HTTP server in the container...")
            
            # Start the server and redirect output to a file we can read
            sandbox.exec("python server.py > /workspace/server_stdout.log 2> /workspace/server_stderr.log &")
            
            # Wait for the server to start
            print("Waiting for server to start...")
            for i in range(3):
                print(".", end="", flush=True)
                time.sleep(1)
            print(" Done!")
            
            # Check for server errors
            print("\n===== SERVER STARTUP LOG =====")
            stderr = sandbox.exec("cat /workspace/server_stderr.log")
            if stderr.strip():
                print(stderr)
            else:
                print("No server output or errors detected.")
            print("===== END OF SERVER LOG =====")
            
            # Try to connect to the server from the host
            print("\nTesting HTTP server connection from host...")
            try:
                response = requests.get("http://localhost:22000")
                print(f"Server responded with status code: {response.status_code}")
                print(f"Content type: {response.headers.get('Content-Type')}")
                
                # After request, check for any new server logs
                print("\n===== SERVER LOGS AFTER REQUEST =====")
                stderr_after = sandbox.exec("cat /workspace/server_stderr.log")
                if stderr_after != stderr:
                    # Only display the new lines
                    print(stderr_after[len(stderr):])
                else:
                    print("No new server output after request.")
                print("===== END OF SERVER LOGS =====")
                
                # Test the API endpoint
                print("\nTesting POST request to the API...")
                api_response = requests.post(
                    "http://localhost:22000/api/data",
                    json={"test": "data", "from": "host"}
                )
                print(f"API response status: {api_response.status_code}")
                
                # Check for API logs
                print("\n===== SERVER LOGS AFTER API REQUEST =====")
                stderr_after_api = sandbox.exec("cat /workspace/server_stderr.log")
                if stderr_after_api != stderr_after:
                    # Only display the new lines
                    print(stderr_after_api[len(stderr_after):])
                else:
                    print("No new server output after API request.")
                print("===== END OF SERVER LOGS =====")
                
            except Exception as e:
                print(f"Error connecting to server: {e}")
                print("Note: This may fail if port 22000 is already in use or if Docker networking has issues.")
                
                # Show server logs which might contain error information
                print("\n===== FULL SERVER LOGS =====")
                print(sandbox.exec("cat /workspace/server_stderr.log"))
                print("===== END OF SERVER LOGS =====")
            
            print("\nServer process info:")
            output = sandbox.exec("ps aux | grep python")
            print(output)
            
            print("\nServer will be terminated when the sandbox is closed.")
            print("You can manually access the server at http://localhost:22000 while this example is running.")

def main():
    """Run all examples."""
    print("Docker Sandbox Examples")
    print("======================")
    
    # Run all examples
    # example_basic_usage()
    # example_project_sandbox()
    # example_custom_resources()
    # example_multiple_commands()
    # example_manage_sandboxes()
    # example_custom_image()
    example_http_server()
    
    print("\nAll examples completed successfully!")

if __name__ == "__main__":
    main() 