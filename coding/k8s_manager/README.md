# Kubernetes Pod Management

This module provides functionality to create, manage, and execute commands on Kubernetes pods for LFG projects and conversations.

## Overview

The Kubernetes pod management system allows you to:

1. Create and manage Kubernetes pods associated with projects or conversations
2. Execute commands in these pods
3. Delete pods when they're no longer needed
4. Store pod information in the database for persistence

## Prerequisites

- A running Kubernetes cluster accessible via SSH
- SSH key-based authentication set up for the Kubernetes host
- `kubectl` installed on the Kubernetes host server
- `paramiko` Python package (included in requirements.txt)

## Configuration

The system is configured via environment variables in the `.env` file or Django settings:

```
# Kubernetes SSH Server Configuration in .env
K8S_SSH_HOST=178.156.174.242
K8S_SSH_PORT=22
K8S_SSH_USERNAME=root
K8S_SSH_KEY_FILE=~/.ssh/id_rsa
# K8S_SSH_KEY_STRING="-----BEGIN RSA PRIVATE KEY-----\nYOUR_PRIVATE_KEY_CONTENT_HERE\n-----END RSA PRIVATE KEY-----"
# K8S_SSH_KEY_PASSPHRASE=
```

These settings are loaded into Django's settings.py:

```python
# Kubernetes SSH server settings in settings.py
K8S_SSH_HOST = os.environ.get('K8S_SSH_HOST', '127.0.0.1')
K8S_SSH_PORT = int(os.environ.get('K8S_SSH_PORT', 22))
K8S_SSH_USERNAME = os.environ.get('K8S_SSH_USERNAME', 'root')
K8S_SSH_KEY_FILE = os.environ.get('K8S_SSH_KEY_FILE', os.path.expanduser('~/.ssh/id_rsa'))
K8S_SSH_KEY_STRING = os.environ.get('K8S_SSH_KEY_STRING', None)  # SSH private key as a string
K8S_SSH_KEY_PASSPHRASE = os.environ.get('K8S_SSH_KEY_PASSPHRASE', None)
```

### SSH Key Options

You have two options for providing the SSH private key for connecting to the Kubernetes server:

1. **SSH Key File**: Specify the path to your private key file using `K8S_SSH_KEY_FILE`. This is the traditional approach.
   
2. **SSH Key String**: Provide the private key content directly as a string using `K8S_SSH_KEY_STRING`. This is useful in environments where storing the key in a file is not practical, such as containerized deployments or when using environment variables for secrets.

The system will prioritize using the key string if provided, falling back to the key file if needed.

## Key Components

### Database Model

The `KubernetesPod` model in `coding/models.py` stores information about pods:

- Association with project_id or conversation_id
- Namespace and pod name
- Pod status (created, running, stopped, error)
- Resource limits
- Service details (URLs, ports)
- SSH connection details

### Main Functions

#### 1. Managing Pods

```python
from coding.k8s_manager import manage_kubernetes_pod

# Create or restart a pod for a project
success, pod = manage_kubernetes_pod(
    project_id="my-project-123",
    image="gitpod/workspace-full:latest",
    resource_limits={
        'memory': '200Mi',
        'cpu': '200m',
        'memory_requests': '100Mi',
        'cpu_requests': '100m'
    }
)

# OR create/restart a pod for a conversation
success, pod = manage_kubernetes_pod(
    conversation_id="my-conversation-456",
    image="gitpod/workspace-full:latest"
)

# Access pod details
if success and pod:
    print(f"Pod name: {pod.pod_name}")
    print(f"Namespace: {pod.namespace}")
    print(f"Pod status: {pod.status}")
    if pod.service_details and pod.service_details.get('access_url'):
        print(f"Access URL: {pod.service_details.get('access_url')}")
```

#### 2. Executing Commands

```python
from coding.k8s_manager import execute_command_in_pod

# Execute a command in a pod for a project
success, stdout, stderr = execute_command_in_pod(
    project_id="my-project-123",
    command="ls -la /workspace"
)

# OR execute a command in a pod for a conversation
success, stdout, stderr = execute_command_in_pod(
    conversation_id="my-conversation-456",
    command="python3 -m pip install numpy"
)

# Check command result
if success:
    print(f"Command output: {stdout}")
else:
    print(f"Error: {stderr}")
```

#### 3. Deleting Pods

```python
from coding.k8s_manager import delete_kubernetes_pod

# Delete a pod for a project
success = delete_kubernetes_pod(project_id="my-project-123")

# OR delete a pod for a conversation
success = delete_kubernetes_pod(conversation_id="my-conversation-456")

if success:
    print("Pod deleted successfully!")
else:
    print("Failed to delete pod")
```

## Command Line Usage

The module includes an example script that can be used from the command line:

```bash
# Create/restart a pod
python coding/k8s_manager.py/example_usage.py --project-id=my-project-123 --action=create

# Execute a command
python coding/k8s_manager.py/example_usage.py --project-id=my-project-123 --action=execute --command="ls -la"

# Delete a pod
python coding/k8s_manager.py/example_usage.py --project-id=my-project-123 --action=delete

# Using conversation ID
python coding/k8s_manager.py/example_usage.py --conversation-id=my-conversation-456 --action=create
```

## Pod Creation Details

When creating a pod:

1. The system generates a unique namespace based on the project or conversation ID
2. It creates a Kubernetes deployment with the specified Docker image
3. It creates a service with NodePort for accessing the pod externally
4. It sets up an emptyDir volume mounted at `/workspace`
5. It records all details in the database for future access

## Behavior Logic

- If a pod already exists and is running, the system will return the existing pod details
- If a pod exists but is not running, the system will attempt to restart it
- If a pod doesn't exist, the system will create a new one
- Project ID takes precedence over conversation ID for pod associations
- Each project or conversation can have at most one associated pod

## Error Handling

- All SSH connection and command execution errors are logged
- Functions return success/failure status and appropriate error messages
- Pod status is updated in the database to reflect errors

## Typical Workflow

1. Call `manage_kubernetes_pod()` to create or ensure a pod is running
2. Use `execute_command_in_pod()` to run commands in the pod
3. When finished, use `delete_kubernetes_pod()` to clean up resources

## Security Considerations

- SSH key-based authentication is used for security
- Kubernetes namespaces provide isolation between pods
- Resource limits prevent excessive resource usage
- All pod details are stored securely in the database

## Troubleshooting

If you encounter issues:

1. Check SSH connectivity to the Kubernetes host
2. Verify the Kubernetes host has kubectl configured properly
3. Check if the resource limits are appropriate for your cluster
4. Look at the Django logs for detailed error messages

## Future Improvements

- Persistent volume support
- Multiple pod support for a single project/conversation
- Network policies for additional security
- Health check probes for pods
- Custom pod templates 