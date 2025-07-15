from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import os
import json
import subprocess
import shutil
from development.models import DockerSandbox, KubernetesPod
from django.db.models import Q
from .docker.docker_utils import get_sandbox_by_project_id
from development.k8s_manager.manage_pods import manage_kubernetes_pod, execute_command_in_pod, delete_kubernetes_pod, get_pod_service_details, get_k8s_api_client
import time
import logging
import requests
from requests.exceptions import RequestException
import base64
import mimetypes
from urllib.parse import quote
from django.core.cache import cache
import hashlib
from pathlib import Path
import platform

logger = logging.getLogger(__name__)

# Token cache for FileBrowser authentication
_token_cache = {}

# Cache for database lookups
_sandbox_cache = {}
_pod_cache = {}

def get_cached_sandbox(project_id=None, conversation_id=None):
    """
    Helper function to get sandbox with caching
    """
    cache_key = f"sandbox_{project_id}_{conversation_id}"
    
    # Check cache first
    cached_sandbox = _sandbox_cache.get(cache_key)
    if cached_sandbox:
        return cached_sandbox
    
    # Build query to find matching sandbox
    query = Q(status='running')
    if project_id:
        query &= Q(project_id=project_id)
    elif conversation_id:
        query &= Q(conversation_id=conversation_id)
    else:
        return None
    
    # Get the sandbox record
    sandbox = DockerSandbox.objects.filter(query).first()
    
    # Cache for 5 minutes
    if sandbox:
        _sandbox_cache[cache_key] = sandbox
        # Simple cache expiry - remove after 300 seconds
        # In production, use a proper cache with TTL
    
    return sandbox

def get_cached_pod(project_id=None, conversation_id=None):
    """
    Helper function to get pod with caching
    """
    cache_key = f"pod_{project_id}_{conversation_id}"
    
    # Check cache first
    cached_pod = _pod_cache.get(cache_key)
    if cached_pod:
        return cached_pod
    
    # Build query to find matching pod
    query = Q()
    if project_id:
        query &= Q(project_id=str(project_id))
    elif conversation_id:
        query &= Q(conversation_id=str(conversation_id))
    else:
        return None
    
    # Get the pod record
    pod = KubernetesPod.objects.filter(query).first()
    
    # Cache for 5 minutes
    if pod:
        _pod_cache[cache_key] = pod
    
    return pod

def editor(request):
    """
    Main view for the Monaco Editor interface
    """
    project_id = request.GET.get('project_id')
    conversation_id = request.GET.get('conversation_id')
    
    # If neither project_id nor conversation_id provided, show a message
    if not project_id and not conversation_id:
        return render(request, 'coding/editor.html', {
            'no_context': True,
            'message': 'Please provide either project_id or conversation_id as a URL parameter.'
        })
    
    # Create context with project or conversation data
    context = {
        # Pass both IDs directly to the template
        'project_id': project_id,
        'conversation_id': conversation_id
    }
    
    return render(request, 'coding/editor.html', context)

def editor_local(request):
    """
    View for opening local code editors
    """
    # Get the workspace path (same as in ai_functions.py)
    workspace_path = Path.home() / "LFG" / "workspace"
    workspace_path.mkdir(parents=True, exist_ok=True)
    
    # Detect installed editors
    detected_editors = []
    system = platform.system().lower()
    
    # VS Code detection
    vscode_detected = False
    vscode_command = None
    if system == "darwin":  # macOS
        vscode_paths = [
            "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code",
            "/usr/local/bin/code"
        ]
        for path in vscode_paths:
            if os.path.exists(path):
                vscode_detected = True
                vscode_command = path
                break
        if not vscode_detected and shutil.which("code"):
            vscode_detected = True
            vscode_command = "code"
    elif system == "windows":
        # Check common Windows paths
        if shutil.which("code"):
            vscode_detected = True
            vscode_command = "code"
    else:  # Linux
        if shutil.which("code"):
            vscode_detected = True
            vscode_command = "code"
    
    if vscode_detected:
        detected_editors.append({
            'name': 'Visual Studio Code',
            'command': vscode_command,
            'icon': 'vscode',
            'description': 'Microsoft Visual Studio Code'
        })
    
    # Cursor detection
    cursor_detected = False
    cursor_command = None
    if system == "darwin":  # macOS
        cursor_paths = [
            "/Applications/Cursor.app/Contents/Resources/app/bin/cursor",
            "/usr/local/bin/cursor"
        ]
        for path in cursor_paths:
            if os.path.exists(path):
                cursor_detected = True
                cursor_command = path
                break
        if not cursor_detected and shutil.which("cursor"):
            cursor_detected = True
            cursor_command = "cursor"
    elif system == "windows":
        if shutil.which("cursor"):
            cursor_detected = True
            cursor_command = "cursor"
    else:  # Linux
        if shutil.which("cursor"):
            cursor_detected = True
            cursor_command = "cursor"
    
    if cursor_detected:
        detected_editors.append({
            'name': 'Cursor',
            'command': cursor_command,
            'icon': 'cursor',
            'description': 'Cursor AI Code Editor'
        })
    
    context = {
        'workspace_path': str(workspace_path),
        'detected_editors': detected_editors,
        'has_editors': len(detected_editors) > 0
    }
    
    return render(request, 'coding/editor_local.html', context)

@csrf_exempt
def open_local_editor(request):
    """
    API endpoint to open local code editor
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        editor_command = data.get('command')
        
        if not editor_command:
            return JsonResponse({'error': 'Editor command is required'}, status=400)
        
        try:
            # Get the workspace path
            workspace_path = Path.home() / "LFG" / "workspace"
            workspace_path.mkdir(parents=True, exist_ok=True)
            
            # Open the editor with the workspace path
            # Use subprocess.Popen to open the editor without blocking
            subprocess.Popen([editor_command, str(workspace_path)], 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
            
            return JsonResponse({
                'status': 'success',
                'message': f'Opening workspace at {workspace_path}'
            })
        except Exception as e:
            return JsonResponse({'error': f'Failed to open editor: {str(e)}'}, status=500)
    
    return JsonResponse({'error': 'POST request expected'}, status=400)

@csrf_exempt
def get_file_tree(request):
    """
    API endpoint to get the file structure with lazy loading
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        project_id = data.get('project_id')
        conversation_id = data.get('conversation_id')
        directory = data.get('directory', '')  # Add support for specific directory
        
        # Build query to find matching sandbox
        query = Q(status='running')
        if project_id:
            query &= Q(project_id=project_id)
        elif conversation_id:
            query &= Q(conversation_id=conversation_id)
        else:
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        # Get the sandbox record
        sandbox = DockerSandbox.objects.filter(query).first()
        if not sandbox or not sandbox.code_dir:
            return JsonResponse({'error': 'No active sandbox found for the given project or conversation'}, status=404)
        
        # Use the code_dir from the sandbox
        base_path = sandbox.code_dir
        target_path = os.path.join(base_path, directory) if directory else base_path
        
        def get_directory_contents_shallow(path):
            """Get only immediate children, no recursion"""
            tree = []
            try:
                entries = sorted(os.listdir(path), key=lambda name: (not os.path.isdir(os.path.join(path, name)), name.lower()))
                for item in entries:
                    if item.startswith('.'):  # Skip hidden files
                        continue
                    item_path = os.path.join(path, item)
                    relative_path = os.path.relpath(item_path, base_path)
                    
                    if os.path.isfile(item_path):
                        tree.append({
                            'name': item,
                            'type': 'file',
                            'path': relative_path
                        })
                    elif os.path.isdir(item_path):
                        tree.append({
                            'name': item,
                            'type': 'directory',
                            'path': relative_path,
                            'children': []  # Empty children - will be loaded on demand
                        })
            except (OSError, PermissionError) as e:
                logger.warning(f"Could not read directory {path}: {e}")
            return tree

        try:
            file_tree = get_directory_contents_shallow(target_path)
            return JsonResponse({
                'files': file_tree,
                'directory': directory
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    else:
        return JsonResponse({'error': 'POST request expected'}, status=400)

@csrf_exempt
def get_file_content(request):
    """
    API endpoint to get file content
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        file_path = data.get('path')
        project_id = data.get('project_id')
        conversation_id = data.get('conversation_id')
        
        # Build query to find matching sandbox
        query = Q(status='running')
        if project_id:
            query &= Q(project_id=project_id)
        elif conversation_id:
            query &= Q(conversation_id=conversation_id)
        else:
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        # Get the sandbox record
        sandbox = DockerSandbox.objects.filter(query).first()
        if not sandbox or not sandbox.code_dir:
            return JsonResponse({'error': 'No active sandbox found for the given project or conversation'}, status=404)
        
        # Use the code_dir from the sandbox
        base_path = sandbox.code_dir
        full_path = os.path.join(base_path, file_path)
        
        try:
            with open(full_path, 'r') as file:
                content = file.read()
            return JsonResponse({'content': content})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'POST request expected'}, status=400)

@csrf_exempt
def save_file(request):
    """
    API endpoint to save file content
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        file_path = data.get('path')
        content = data.get('content')
        project_id = data.get('project_id')
        conversation_id = data.get('conversation_id')
        
        # Build query to find matching sandbox
        query = Q(status='running')
        if project_id:
            query &= Q(project_id=project_id)
        elif conversation_id:
            query &= Q(conversation_id=conversation_id)
        else:
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        # Get the sandbox record
        sandbox = DockerSandbox.objects.filter(query).first()
        if not sandbox or not sandbox.code_dir:
            return JsonResponse({'error': 'No active sandbox found for the given project or conversation'}, status=404)
        
        # Use the code_dir from the sandbox
        base_path = sandbox.code_dir
        full_path = os.path.join(base_path, file_path)
        
        try:
            # Make sure directory exists
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            with open(full_path, 'w') as file:
                file.write(content)
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'POST request expected'}, status=400)

@csrf_exempt
def execute_command(request):
    """
    API endpoint to execute terminal commands
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        command = data.get('command')
        project_id = data.get('project_id')
        conversation_id = data.get('conversation_id')
        
        # Build query to find matching sandbox
        query = Q(status='running')
        if project_id:
            query &= Q(project_id=project_id)
        elif conversation_id:
            query &= Q(conversation_id=conversation_id)
        else:
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        # Get the sandbox record
        sandbox = DockerSandbox.objects.filter(query).first()
        if not sandbox or not sandbox.code_dir:
            return JsonResponse({'error': 'No active sandbox found for the given project or conversation'}, status=404)
        
        # Use the code_dir from the sandbox as the working directory
        working_dir = sandbox.code_dir
        
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=working_dir
            )
            stdout, stderr = process.communicate()
            return JsonResponse({
                'stdout': stdout,
                'stderr': stderr,
                'returncode': process.returncode
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'POST request expected'}, status=400)

@csrf_exempt
def create_folder(request):
    """
    API endpoint to create a new folder
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        folder_path = data.get('path')
        project_id = data.get('project_id')
        conversation_id = data.get('conversation_id')
        
        # Build query to find matching sandbox
        query = Q(status='running')
        if project_id:
            query &= Q(project_id=project_id)
        elif conversation_id:
            query &= Q(conversation_id=conversation_id)
        else:
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        # Get the sandbox record
        sandbox = DockerSandbox.objects.filter(query).first()
        if not sandbox or not sandbox.code_dir:
            return JsonResponse({'error': 'No active sandbox found for the given project or conversation'}, status=404)
        
        # Use the code_dir from the sandbox
        base_path = sandbox.code_dir
        full_path = os.path.join(base_path, folder_path)
        
        try:
            os.makedirs(full_path, exist_ok=True)
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'POST request expected'}, status=400)

@csrf_exempt
def delete_item(request):
    """
    API endpoint to delete a file or folder
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        path = data.get('path')
        is_directory = data.get('is_directory', False)
        project_id = data.get('project_id')
        conversation_id = data.get('conversation_id')
        
        # Build query to find matching sandbox
        query = Q(status='running')
        if project_id:
            query &= Q(project_id=project_id)
        elif conversation_id:
            query &= Q(conversation_id=conversation_id)
        else:
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        # Get the sandbox record
        sandbox = DockerSandbox.objects.filter(query).first()
        if not sandbox or not sandbox.code_dir:
            return JsonResponse({'error': 'No active sandbox found for the given project or conversation'}, status=404)
        
        # Use the code_dir from the sandbox
        base_path = sandbox.code_dir
        full_path = os.path.join(base_path, path)
        
        try:
            if is_directory:
                shutil.rmtree(full_path)
            else:
                os.remove(full_path)
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'POST request expected'}, status=400)

@csrf_exempt
def rename_item(request):
    """
    API endpoint to rename a file or folder
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        old_path = data.get('old_path')
        new_path = data.get('new_path')
        project_id = data.get('project_id')
        conversation_id = data.get('conversation_id')
        
        # Build query to find matching sandbox
        query = Q(status='running')
        if project_id:
            query &= Q(project_id=project_id)
        elif conversation_id:
            query &= Q(conversation_id=conversation_id)
        else:
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        # Get the sandbox record
        sandbox = DockerSandbox.objects.filter(query).first()
        if not sandbox or not sandbox.code_dir:
            return JsonResponse({'error': 'No active sandbox found for the given project or conversation'}, status=404)
        
        # Use the code_dir from the sandbox
        base_path = sandbox.code_dir
        full_old_path = os.path.join(base_path, old_path)
        full_new_path = os.path.join(base_path, new_path)
        
        try:
            # Ensure parent directory of new path exists
            os.makedirs(os.path.dirname(full_new_path), exist_ok=True)
            
            os.rename(full_old_path, full_new_path)
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'POST request expected'}, status=400)

@csrf_exempt
def get_sandbox_info(request):
    """
    API endpoint to get information about a sandbox, including its port
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        project_id = data.get('project_id')
        conversation_id = data.get('conversation_id')
        
        # Build query to find matching sandbox
        query = Q(status='running')
        if project_id:
            query &= Q(project_id=project_id)
        elif conversation_id:
            query &= Q(conversation_id=conversation_id)
        else:
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        # Get the sandbox record
        sandbox = DockerSandbox.objects.filter(query).first()
        if not sandbox:
            return JsonResponse({'error': 'No active sandbox found for the given project or conversation'}, status=404)
        
        # Get port mappings for this sandbox
        port_mappings = []
        
        # Add the main port from the sandbox model if it exists
        if sandbox.port is not None:
            port_mappings.append({
                'container_port': 8000,  # Default web server port
                'host_port': sandbox.port,
                'is_primary': True
            })
            
        # Add all port mappings from the related DockerPortMapping model
        for mapping in sandbox.port_mappings.all():
            # Check if this mapping is already included
            if not any(pm.get('host_port') == mapping.host_port for pm in port_mappings):
                port_mappings.append({
                    'container_port': mapping.container_port,
                    'host_port': mapping.host_port,
                    'is_primary': False
                })
        
        # If we have no port mappings but sandbox is running, add a default one
        # This is a fallback for older sandboxes that might not have explicit mappings
        if not port_mappings and sandbox.status == 'running':
            # Try to get port from Docker directly using the docker_utils module
            try:
                sandbox_info = get_sandbox_by_project_id(project_id or "")
                if sandbox_info and sandbox_info.get('port'):
                    port_mappings.append({
                        'container_port': 8000,
                        'host_port': sandbox_info['port'],
                        'is_primary': True
                    })
            except Exception as e:
                print(f"Error getting sandbox info from Docker: {e}")
        
        # Return sandbox information including port
        return JsonResponse({
            'sandbox_id': sandbox.id,
            'status': sandbox.status,
            'port': sandbox.port,  # Include the main port directly for backward compatibility
            'port_mappings': port_mappings
        })
    
    return JsonResponse({'error': 'POST request expected'}, status=400)

@csrf_exempt
def get_k8s_file_tree(request):
    """
    API endpoint to get the file structure from a Kubernetes pod with lazy loading
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        project_id = data.get('project_id')
        conversation_id = data.get('conversation_id')
        directory = data.get('directory', '')  # Default to root directory (empty string)
        
        # Validate input
        if not (project_id or conversation_id):
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        try:
            # Get the pod from the database
            query = Q()
            if project_id:
                query &= Q(project_id=str(project_id))
            elif conversation_id:
                query &= Q(conversation_id=str(conversation_id))
            
            pod = KubernetesPod.objects.filter(query).first()
            
            if not pod or pod.status != 'running':
                # Try to create/start the pod if it doesn't exist or isn't running
                success, pod, error_message = manage_kubernetes_pod(
                    project_id=project_id,
                    conversation_id=conversation_id
                )
                
                if not success or not pod:
                    return JsonResponse({
                        'error': 'Failed to start Kubernetes pod',
                        'debug_info': {
                            'project_id': project_id,
                            'conversation_id': conversation_id,
                            'pod_exists': pod is not None,
                            'error_message': error_message
                        }
                    }, status=500)
            
            # Get the filebrowser URL
            filebrowser_url = None
            if pod.service_details and 'filebrowserUrl' in pod.service_details:
                filebrowser_url = pod.service_details.get('filebrowserUrl')
            else:
                # If filebrowserUrl is not directly available, try to construct it
                if pod.service_details:
                    filebrowser_port = pod.service_details.get('filebrowserPort')
                    node_ip = pod.service_details.get('nodeIP')
                    
                    if filebrowser_port and node_ip:
                        # Construct filebrowser URL
                        filebrowser_url = f"http://{node_ip}:{filebrowser_port}"
                        
                        # Update the pod record for future requests
                        pod.service_details['filebrowserUrl'] = filebrowser_url
                        pod.save(update_fields=['service_details'])
            
            if not filebrowser_url:
                return JsonResponse({
                    'error': 'FileBrowser URL not available',
                    'debug_info': {
                        'pod_name': pod.pod_name,
                        'namespace': pod.namespace,
                        'service_details': pod.service_details
                    }
                }, status=400)
            
            # Format the directory path for the API request
            api_path = directory
            if api_path.startswith('/'):
                api_path = api_path[1:]  # Remove leading slash
            
            # URL encode the path for the API request
            encoded_path = quote(api_path, safe='')
            api_endpoint = f"/api/resources/{encoded_path}"
            
            # Make API request to get directory contents (only current level)
            success, response_data, error_message = filebrowser_api_request(
                filebrowser_url=filebrowser_url,
                method="GET",
                endpoint=api_endpoint
            )
            
            if not success:
                return JsonResponse({
                    'error': f'Failed to list files: {error_message}',
                    'debug_info': {
                        'api_endpoint': api_endpoint,
                        'filebrowser_url': filebrowser_url
                    }
                }, status=500)
            
            # Process the response to build a simple tree structure (no recursion)
            file_tree = []
            items = response_data.get('items', [])
            
            for item in items:
                name = item.get('name', '')
                is_dir = item.get('isDir', False)
                path = os.path.join(directory, name).replace('\\', '/')
                
                if path.startswith('/'):
                    path = path[1:]  # Remove leading slash
                
                node = {
                    'name': name,
                    'type': 'directory' if is_dir else 'file',
                    'path': path
                }
                
                # For directories, just set empty children - will be loaded on demand
                if is_dir:
                    node['children'] = []
                
                file_tree.append(node)
            
            return JsonResponse({
                'files': file_tree,
                'directory': directory,
                'pod_info': {
                    'namespace': pod.namespace,
                    'pod_name': pod.pod_name,
                    'status': pod.status,
                    'filebrowser_url': filebrowser_url
                }
            })
        except Exception as e:
            logger.exception(f"Error in get_k8s_file_tree: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'POST request expected'}, status=400)

@csrf_exempt
def get_k8s_file_content(request):
    """
    API endpoint to get file content from a Kubernetes pod via the FileBrowser API
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        project_id = data.get('project_id')
        conversation_id = data.get('conversation_id')
        file_path = data.get('path')
        
        # Validate input
        if not (project_id or conversation_id):
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        if not file_path:
            return JsonResponse({'error': 'File path must be provided'}, status=400)
        
        try:
            # Ensure the pod is running
            # success, pod, error_message = manage_kubernetes_pod(
            #     project_id=project_id,
            #     conversation_id=conversation_id
            # )

            pod = None
            if project_id:
                pod = KubernetesPod.objects.filter(project_id=project_id).first()
            elif conversation_id:
                pod = KubernetesPod.objects.filter(conversation_id=conversation_id).first()

            logger.debug(f"Pod: {pod}")
            
            if not pod:
                return JsonResponse({
                    'error': 'Failed to start Kubernetes pod',
                    'debug_info': {
                        'project_id': project_id,
                        'conversation_id': conversation_id,
                        'pod_exists': pod is not None,
                        'error_message': error_message
                    }
                }, status=500)
            
            # Get the filebrowser URL
            filebrowser_url = None
            if pod.service_details and 'filebrowserUrl' in pod.service_details:
                filebrowser_url = pod.service_details.get('filebrowserUrl')
            else:
                # If filebrowserUrl is not directly available, try to construct it
                if pod.service_details:
                    filebrowser_port = pod.service_details.get('filebrowserPort')
                    node_ip = pod.service_details.get('nodeIP')
                    
                    if filebrowser_port and node_ip:
                        # Construct filebrowser URL
                        filebrowser_url = f"http://{node_ip}:{filebrowser_port}"
                        
                        # Update the pod record for future requests
                        pod.service_details['filebrowserUrl'] = filebrowser_url
                        pod.save(update_fields=['service_details'])
                        
                        logger.info(f"Created and saved missing filebrowserUrl: {filebrowser_url}")
            
            if not filebrowser_url:
                return JsonResponse({
                    'error': 'FileBrowser URL not available',
                    'debug_info': {
                        'pod_name': pod.pod_name,
                        'namespace': pod.namespace,
                        'service_details': pod.service_details
                    }
                }, status=400)
                
            # Format file path for the API request
            abs_path = file_path
            if abs_path.startswith('/'):
                abs_path = abs_path[1:]  # Remove leading slash
                
            # URL encode the path for the API request
            encoded_path = quote(abs_path, safe='')
            
            # Use the raw endpoint to get the file content directly
            api_endpoint = f"/api/raw/{encoded_path}"

            logger.debug(f"API Endpoint: {api_endpoint}")
            
            # Make API request to get the file content
            success, response_data, error_message = filebrowser_api_request(
                filebrowser_url=filebrowser_url,
                method="GET",
                endpoint=api_endpoint
            )

            logger.debug(f"Success: {success}")
            logger.debug(f"Response Data type: {type(response_data)}")
            
            if not success:
                return JsonResponse({
                    'error': f'Failed to read file: {error_message}',
                    'debug_info': {
                        'api_endpoint': api_endpoint,
                        'filebrowser_url': filebrowser_url
                    }
                }, status=500)
            
            # Decode the response if it's binary
            if isinstance(response_data, bytes):
                try:
                    content = response_data.decode('utf-8')
                except UnicodeDecodeError:
                    # If it's not UTF-8 decodable, encode in base64
                    content = base64.b64encode(response_data).decode('ascii')
                    return JsonResponse({
                        'content': content,
                        'encoding': 'base64',
                        'filebrowser_url': filebrowser_url
                    })
            else:
                content = response_data
            
            return JsonResponse({
                'content': content,
                'filebrowser_url': filebrowser_url
            })
        except Exception as e:
            logger.exception(f"Error in get_k8s_file_content: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'POST request expected'}, status=400)



@csrf_exempt
def save_k8s_file(request):
    """
    API endpoint to save file content to a Kubernetes pod via the FileBrowser API
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        project_id = data.get('project_id')
        conversation_id = data.get('conversation_id')
        file_path = data.get('path')
        content = data.get('content')
        
        # Validate input
        if not (project_id or conversation_id):
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        if not file_path:
            return JsonResponse({'error': 'File path must be provided'}, status=400)
        
        try:
            # Ensure the pod is running
            pod = None
            if project_id:
                pod = KubernetesPod.objects.filter(project_id=project_id).first()
            elif conversation_id:
                pod = KubernetesPod.objects.filter(conversation_id=conversation_id).first()
            
            if not pod:
                return JsonResponse({
                    'error': 'Failed to start Kubernetes pod',
                    'debug_info': {
                        'project_id': project_id,
                        'conversation_id': conversation_id,
                        'pod_exists': pod is not None,
                        'error_message': error_message
                    }
                }, status=500)
            
            # Get the filebrowser URL
            filebrowser_url = None
            if pod.service_details and 'filebrowserUrl' in pod.service_details:
                filebrowser_url = pod.service_details.get('filebrowserUrl')
            else:
                # If filebrowserUrl is not directly available, try to construct it
                if pod.service_details:
                    filebrowser_port = pod.service_details.get('filebrowserPort')
                    node_ip = pod.service_details.get('nodeIP')
                    
                    if filebrowser_port and node_ip:
                        # Construct filebrowser URL
                        filebrowser_url = f"http://{node_ip}:{filebrowser_port}"
                        
                        # Update the pod record for future requests
                        pod.service_details['filebrowserUrl'] = filebrowser_url
                        pod.save(update_fields=['service_details'])
                        
                        logger.info(f"Created and saved missing filebrowserUrl: {filebrowser_url}")
            
            if not filebrowser_url:
                return JsonResponse({
                    'error': 'FileBrowser URL not available',
                    'debug_info': {
                        'pod_name': pod.pod_name,
                        'namespace': pod.namespace,
                        'service_details': pod.service_details
                    }
                }, status=400)
            
            # Get absolute path
            abs_path = file_path
            if abs_path.startswith('/'):
                abs_path = abs_path[1:]  # Remove leading slash
            
            # First, ensure parent directory exists
            dir_path = os.path.dirname(abs_path)
            if dir_path:  # Skip if it's in the root
                # URL encode the directory path
                encoded_dir_path = quote(dir_path, safe='')
                
                # Check if the directory exists
                dir_endpoint = f"/api/resources/{encoded_dir_path}"
                dir_exists, _, _ = filebrowser_api_request(
                    filebrowser_url=filebrowser_url,
                    method="GET",
                    endpoint=dir_endpoint
                )
                
                # If directory doesn't exist, create it recursively
                if not dir_exists:
                    parent_dirs = dir_path.split('/')
                    current_path = ""
                    
                    for dir_name in parent_dirs:
                        if current_path:
                            current_path = f"{current_path}/{dir_name}"
                        else:
                            current_path = dir_name
                        
                        # Create directory data
                        dir_data = {
                            "item": {
                                "path": current_path,
                                "type": "directory"
                            }
                        }
                        
                        # Try to create the directory
                        create_success, _, create_error = filebrowser_api_request(
                            filebrowser_url=filebrowser_url,
                            method="POST",
                            endpoint="/api/resources",
                            data=dir_data
                        )
                        
                        if not create_success and "already exists" not in str(create_error):
                            logger.warning(f"Failed to create directory {current_path}: {create_error}")
                            # Continue anyway as the directory might already exist
            
            # URL encode the file path
            encoded_file_path = quote(abs_path, safe='')
            
            # Prepare file content
            file_content = content.encode('utf-8')  # Encode the content as bytes

            logger.debug(f"File Content length: {len(file_content)} bytes")
            
            # Create the directory structure if it doesn't exist
            dir_path = os.path.dirname(abs_path)
            if dir_path:
                dir_data = {
                    "item": {
                        "path": dir_path,
                        "type": "directory"
                    }
                }
                dir_endpoint = f"/api/resources/{quote(dir_path, safe='')}"
                dir_exists, _, _ = filebrowser_api_request(
                    filebrowser_url=filebrowser_url,
                    method="GET",
                    endpoint=dir_endpoint
                )
                if not dir_exists:
                    create_success, _, _ = filebrowser_api_request(
                        filebrowser_url=filebrowser_url,
                        method="POST",
                        endpoint="/api/resources",
                        data=dir_data
                    )
            
            # According to FileBrowser API docs, use /api/raw/ endpoint for uploading raw file content
            raw_endpoint = f"/api/raw/{encoded_file_path}"
            
            # Upload the file using the raw endpoint
            success, response_data, error_message = filebrowser_api_request(
                filebrowser_url=filebrowser_url,
                method="POST",
                endpoint=raw_endpoint,
                data=file_content,
                params={"override": "true"}  # Override existing file
            )
            
            if not success:
                logger.warning(f"Raw endpoint upload failed: {error_message}. Trying multipart...")
                
                # Try using a multipart/form-data approach as fallback
                import io
                file_name = os.path.basename(abs_path)
                file_obj = io.BytesIO(file_content)
                
                files = {
                    'file': (file_name, file_obj, 'application/octet-stream')
                }
                
                resources_endpoint = f"/api/resources/{encoded_file_path}"
                fallback_success, fallback_response, fallback_error = filebrowser_api_request(
                    filebrowser_url=filebrowser_url,
                    method="POST",
                    endpoint=resources_endpoint,
                    files=files,
                    params={"override": "true"}
                )
                
                if not fallback_success:
                    return JsonResponse({
                        'error': f'Failed to save file: {error_message}. Fallback also failed: {fallback_error}',
                        'debug_info': {
                            'raw_endpoint': raw_endpoint,
                            'resources_endpoint': resources_endpoint,
                            'filebrowser_url': filebrowser_url
                        }
                    }, status=500)
                else:
                    logger.info("Fallback multipart upload succeeded")
                    success = True
            
            return JsonResponse({
                'status': 'success',
                'filebrowser_url': filebrowser_url
            })
        except Exception as e:
            logger.exception(f"Error in save_k8s_file: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'POST request expected'}, status=400)

@csrf_exempt
def k8s_create_folder(request):
    """
    API endpoint to create a new folder in a Kubernetes pod via the FileBrowser API
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        project_id = data.get('project_id')
        conversation_id = data.get('conversation_id')
        folder_path = data.get('path')
        
        # Validate input
        if not (project_id or conversation_id):
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        if not folder_path:
            return JsonResponse({'error': 'Folder path must be provided'}, status=400)
        
        try:
            # Ensure the pod is running
            success, pod, error_message = manage_kubernetes_pod(
                project_id=project_id,
                conversation_id=conversation_id
            )
            
            if not success or not pod:
                return JsonResponse({
                    'error': 'Failed to start Kubernetes pod',
                    'debug_info': {
                        'project_id': project_id,
                        'conversation_id': conversation_id,
                        'pod_exists': pod is not None,
                        'error_message': error_message
                    }
                }, status=500)
            
            # Get the filebrowser URL
            filebrowser_url = None
            if pod.service_details and 'filebrowserUrl' in pod.service_details:
                filebrowser_url = pod.service_details.get('filebrowserUrl')
            else:
                # If filebrowserUrl is not directly available, try to construct it
                if pod.service_details:
                    filebrowser_port = pod.service_details.get('filebrowserPort')
                    node_ip = pod.service_details.get('nodeIP')
                    
                    if filebrowser_port and node_ip:
                        # Construct filebrowser URL
                        filebrowser_url = f"http://{node_ip}:{filebrowser_port}"
                        
                        # Update the pod record for future requests
                        pod.service_details['filebrowserUrl'] = filebrowser_url
                        pod.save(update_fields=['service_details'])
                        
                        logger.info(f"Created and saved missing filebrowserUrl: {filebrowser_url}")
            
            if not filebrowser_url:
                return JsonResponse({
                    'error': 'FileBrowser URL not available',
                    'debug_info': {
                        'pod_name': pod.pod_name,
                        'namespace': pod.namespace,
                        'service_details': pod.service_details
                    }
                }, status=400)
            
            # Get absolute path
            abs_path = folder_path
            if abs_path.startswith('/'):
                abs_path = abs_path[1:]  # Remove leading slash
            
            # Create folder using FileBrowser API
            # Format the path for API request
            path_for_api = abs_path
            
            # Prepare directory creation data
            dir_data = {
                "item": {
                    "path": path_for_api,
                    "type": "directory"
                }
            }
            
            # Make API request to create the directory
            success, response_data, error_message = filebrowser_api_request(
                filebrowser_url=filebrowser_url,
                method="POST",
                endpoint="/api/resources",
                data=dir_data
            )
            
            # If the API reports the directory already exists, try a direct mkdir command as fallback
            if not success and ("409 Conflict" in error_message or "already exists" in error_message):
                logger.info(f"Directory '{abs_path}' already exists according to API, trying direct command fallback")
                
                # Try a direct command to ensure the directory exists
                try:
                    # Use execute_command_in_pod to run mkdir
                    cmd_success, cmd_stdout, cmd_stderr = execute_command_in_pod(
                        project_id=project_id,
                        conversation_id=conversation_id,
                        command=f"mkdir -p /workspace/{abs_path}"
                    )
                    
                    if cmd_success:
                        # Command succeeded - directory should now exist
                        logger.info(f"Successfully created directory via direct command: {abs_path}")
                        return JsonResponse({
                            'status': 'success',
                            'message': f'Directory created via command: {folder_path}',
                            'filebrowser_url': filebrowser_url,
                            'note': 'Used command fallback since API reported directory already exists'
                        })
                    else:
                        # Command failed
                        logger.warning(f"Command fallback also failed: {cmd_stderr}")
                except Exception as cmd_error:
                    logger.exception(f"Error in command fallback: {str(cmd_error)}")
                
                # Even if command fallback fails, still return success since FileBrowser thinks it exists
                return JsonResponse({
                    'status': 'success',
                    'message': f'Directory already exists: {folder_path}',
                    'filebrowser_url': filebrowser_url
                })
            
            if not success:
                return JsonResponse({
                    'error': f'Failed to create directory: {error_message}',
                    'debug_info': {
                        'api_endpoint': "/api/resources",
                        'filebrowser_url': filebrowser_url,
                        'dir_data': dir_data
                    }
                }, status=500)
            
            return JsonResponse({
                'status': 'success',
                'message': f'Directory created: {folder_path}',
                'filebrowser_url': filebrowser_url
            })
        except Exception as e:
            logger.exception(f"Error in k8s_create_folder: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'POST request expected'}, status=400)

@csrf_exempt
def k8s_delete_item(request):
    """
    API endpoint to delete a file or folder in a Kubernetes pod via the FileBrowser API
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        project_id = data.get('project_id')
        conversation_id = data.get('conversation_id')
        path = data.get('path')
        is_directory = data.get('is_directory', False)  # Not needed for FileBrowser API but kept for compatibility
        
        # Validate input
        if not (project_id or conversation_id):
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        if not path:
            return JsonResponse({'error': 'Path must be provided'}, status=400)
        
        try:
            # Ensure the pod is running
            success, pod, error_message = manage_kubernetes_pod(
                project_id=project_id,
                conversation_id=conversation_id
            )
            
            if not success or not pod:
                return JsonResponse({
                    'error': 'Failed to start Kubernetes pod',
                    'debug_info': {
                        'project_id': project_id,
                        'conversation_id': conversation_id,
                        'pod_exists': pod is not None,
                        'error_message': error_message
                    }
                }, status=500)
            
            # Get the filebrowser URL
            filebrowser_url = None
            if pod.service_details and 'filebrowserUrl' in pod.service_details:
                filebrowser_url = pod.service_details.get('filebrowserUrl')
            else:
                # If filebrowserUrl is not directly available, try to construct it
                if pod.service_details:
                    filebrowser_port = pod.service_details.get('filebrowserPort')
                    node_ip = pod.service_details.get('nodeIP')
                    
                    if filebrowser_port and node_ip:
                        # Construct filebrowser URL
                        filebrowser_url = f"http://{node_ip}:{filebrowser_port}"
                        
                        # Update the pod record for future requests
                        pod.service_details['filebrowserUrl'] = filebrowser_url
                        pod.save(update_fields=['service_details'])
                        
                        logger.info(f"Created and saved missing filebrowserUrl: {filebrowser_url}")
            
            if not filebrowser_url:
                return JsonResponse({
                    'error': 'FileBrowser URL not available',
                    'debug_info': {
                        'pod_name': pod.pod_name,
                        'namespace': pod.namespace,
                        'service_details': pod.service_details
                    }
                }, status=400)
            
            # Get absolute path
            abs_path = path
            if abs_path.startswith('/'):
                abs_path = abs_path[1:]  # Remove leading slash
            
            # Format the path for API request
            path_for_api = abs_path
            
            # URL encode the path
            encoded_path = quote(path_for_api, safe='')
            
            # Make API request to delete the item
            api_endpoint = f"/api/resources/{encoded_path}"
            success, response_data, error_message = filebrowser_api_request(
                filebrowser_url=filebrowser_url,
                method="DELETE",
                endpoint=api_endpoint
            )
            
            if not success:
                return JsonResponse({
                    'error': f'Failed to delete item: {error_message}',
                    'debug_info': {
                        'api_endpoint': api_endpoint,
                        'filebrowser_url': filebrowser_url
                    }
                }, status=500)
            
            return JsonResponse({
                'status': 'success',
                'filebrowser_url': filebrowser_url
            })
        except Exception as e:
            logger.exception(f"Error in k8s_delete_item: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'POST request expected'}, status=400)

@csrf_exempt
def k8s_rename_item(request):
    """
    API endpoint to rename a file or folder in a Kubernetes pod via the FileBrowser API
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        project_id = data.get('project_id')
        conversation_id = data.get('conversation_id')
        old_path = data.get('old_path')
        new_path = data.get('new_path')
        
        # Validate input
        if not (project_id or conversation_id):
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        if not old_path or not new_path:
            return JsonResponse({'error': 'Both old_path and new_path must be provided'}, status=400)
        
        try:
            # Ensure the pod is running
            success, pod, error_message = manage_kubernetes_pod(
                project_id=project_id,
                conversation_id=conversation_id
            )
            
            if not success or not pod:
                return JsonResponse({
                    'error': 'Failed to start Kubernetes pod',
                    'debug_info': {
                        'project_id': project_id,
                        'conversation_id': conversation_id,
                        'pod_exists': pod is not None,
                        'error_message': error_message
                    }
                }, status=500)
            
            # Get the filebrowser URL
            filebrowser_url = None
            if pod.service_details and 'filebrowserUrl' in pod.service_details:
                filebrowser_url = pod.service_details.get('filebrowserUrl')
            else:
                # If filebrowserUrl is not directly available, try to construct it
                if pod.service_details:
                    filebrowser_port = pod.service_details.get('filebrowserPort')
                    node_ip = pod.service_details.get('nodeIP')
                    
                    if filebrowser_port and node_ip:
                        # Construct filebrowser URL
                        filebrowser_url = f"http://{node_ip}:{filebrowser_port}"
                        
                        # Update the pod record for future requests
                        pod.service_details['filebrowserUrl'] = filebrowser_url
                        pod.save(update_fields=['service_details'])
                        
                        logger.info(f"Created and saved missing filebrowserUrl: {filebrowser_url}")
            
            if not filebrowser_url:
                return JsonResponse({
                    'error': 'FileBrowser URL not available',
                    'debug_info': {
                        'pod_name': pod.pod_name,
                        'namespace': pod.namespace,
                        'service_details': pod.service_details
                    }
                }, status=400)
            
            # Get absolute paths
            abs_old_path = old_path
            if abs_old_path.startswith('/'):
                abs_old_path = abs_old_path[1:]  # Remove leading slash
                
            abs_new_path = new_path
            if abs_new_path.startswith('/'):
                abs_new_path = abs_new_path[1:]  # Remove leading slash
            
            # Format paths for API requests
            old_path_for_api = abs_old_path
            new_path_for_api = abs_new_path
            
            # URL encode the source path
            encoded_old_path = quote(old_path_for_api, safe='')
            
            # Ensure parent directory of the destination exists
            new_dir_path = os.path.dirname(abs_new_path)
            if new_dir_path and new_dir_path != '':  # Skip if it's in the root
                # URL encode the directory path
                encoded_dir_path = quote(new_dir_path, safe='')
                
                # Check if the directory exists
                dir_endpoint = f"/api/resources/{encoded_dir_path}"
                dir_exists, _, _ = filebrowser_api_request(
                    filebrowser_url=filebrowser_url,
                    method="GET",
                    endpoint=dir_endpoint
                )
                
                # If directory doesn't exist, create it recursively
                if not dir_exists:
                    parent_dirs = new_dir_path.split('/')
                    current_path = ""
                    
                    for dir_name in parent_dirs:
                        if current_path:
                            current_path = f"{current_path}/{dir_name}"
                        else:
                            current_path = dir_name
                        
                        # Create directory data
                        dir_data = {
                            "item": {
                                "path": current_path,
                                "type": "directory"
                            }
                        }
                        
                        # Try to create the directory
                        create_success, _, create_error = filebrowser_api_request(
                            filebrowser_url=filebrowser_url,
                            method="POST",
                            endpoint="/api/resources",
                            data=dir_data
                        )
                        
                        if not create_success and "already exists" not in str(create_error):
                            logger.warning(f"Failed to create directory {current_path}: {create_error}")
                            # Continue anyway as the directory might already exist
            
            # Prepare the rename data
            rename_data = {
                "dst": new_path_for_api
            }
            
            # Make API request to rename the item
            api_endpoint = f"/api/resources/{encoded_old_path}"
            success, response_data, error_message = filebrowser_api_request(
                filebrowser_url=filebrowser_url,
                method="PUT",
                endpoint=api_endpoint,
                data=rename_data
            )
            
            if not success:
                return JsonResponse({
                    'error': f'Failed to rename item: {error_message}',
                    'debug_info': {
                        'api_endpoint': api_endpoint,
                        'filebrowser_url': filebrowser_url,
                        'rename_data': rename_data
                    }
                }, status=500)
            
            return JsonResponse({
                'status': 'success',
                'filebrowser_url': filebrowser_url
            })
        except Exception as e:
            logger.exception(f"Error in k8s_rename_item: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'POST request expected'}, status=400)

@csrf_exempt
def get_k8s_pod_info(request):
    """
    API endpoint to get information about a Kubernetes pod
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        project_id = data.get('project_id')
        conversation_id = data.get('conversation_id')
        
        # Validate input
        if not (project_id or conversation_id):
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        try:
            # Check DB for pod info first
            query = Q()
            if project_id:
                query &= Q(project_id=str(project_id))
            elif conversation_id:
                query &= Q(conversation_id=str(conversation_id))
            
            pod = KubernetesPod.objects.filter(query).first()
            
            # Define variables to track what's happening
            pod_existed = pod is not None
            pod_was_running = pod and pod.status == 'running'
            
            logger.info(f"Starting get_k8s_pod_info: db_record_exists={pod_existed}, was_running={pod_was_running}")
            
            # IMPORTANT OPTIMIZATION: If pod is in DB and marked as running, and has valid service details,
            # we can skip the expensive K8s checks and management operations
            if pod_existed and pod_was_running and pod.service_details and 'ttydUrl' in pod.service_details:
                logger.info(f"Using existing pod info from database for {pod.pod_name} - skipping K8s operations")
                
                # Return pod info directly from DB
                pod_info = {
                    'pod_id': pod.id,
                    'pod_name': pod.pod_name,
                    'namespace': pod.namespace,
                    'status': pod.status,
                    'image': pod.image,
                    'service_details': pod.service_details,
                    'ttydUrl': pod.service_details.get('ttydUrl'),
                    'from_cache': True
                }
                
                # Add filebrowserUrl to top level if available
                if 'filebrowserUrl' in pod.service_details:
                    pod_info['filebrowserUrl'] = pod.service_details.get('filebrowserUrl')
                
                # Add debug info
                pod_info['debug_info'] = {
                    'has_service_details': bool(pod.service_details),
                    'service_details_keys': list(pod.service_details.keys()) if pod.service_details else [],
                    'pod_existed': pod_existed,
                    'pod_was_running': pod_was_running,
                    'pod_name': pod.pod_name,
                    'pod_namespace': pod.namespace,
                    'skipped_k8s_check': True
                }
                
                return JsonResponse(pod_info)
            
            # Only perform expensive K8s operations if necessary
            # Ensure a pod is available and running - will check for existing resources first
            success, pod, error_message = manage_kubernetes_pod(
                project_id=project_id,
                conversation_id=conversation_id,
                image=pod.image if pod and pod.image else "gitpod/workspace-full:latest",
                resource_limits=pod.resource_limits if pod and pod.resource_limits else None
            )
            
            if not success or not pod:
                return JsonResponse({
                    'error': 'Failed to ensure Kubernetes pod is running',
                    'debug_info': {
                        'project_id': project_id,
                        'conversation_id': conversation_id,
                        'pod_exists': pod is not None,
                        'error_message': error_message
                    }
                }, status=500)
            
            # Verify the pod is now running
            if pod.status != 'running':
                logger.error(f"Pod {pod.pod_name} is still not running after creation/start attempts")
                return JsonResponse({
                    'error': 'Pod is not running after creation/start attempts',
                    'debug_info': {
                        'pod_name': pod.pod_name,
                        'status': pod.status,
                        'existed_before': pod_existed,
                        'was_running_before': pod_was_running
                    }
                }, status=500)
            
            # Extract pod info
            pod_info = {
                'pod_id': pod.id,
                'pod_name': pod.pod_name,
                'namespace': pod.namespace,
                'status': pod.status,
                'image': pod.image,
                'from_cache': False
            }
            
            # Add service details if available
            if pod.service_details:
                # Log details about service_details for debugging
                logger.info(f"Pod service_details: {pod.service_details}")
                
                # Add full service_details to response for debugging
                pod_info['service_details'] = pod.service_details
                
                # Check for ttydUrl and directly expose it at the top level for easy access
                if 'ttydUrl' in pod.service_details and pod.service_details.get('ttydUrl'):
                    # Add ttydUrl directly to the response object for easier access in the frontend
                    pod_info['ttydUrl'] = pod.service_details.get('ttydUrl')
                else:
                    # No ttydUrl found, check if ttydPort exists
                    ttyd_port = pod.service_details.get('ttydPort')
                    node_ip = pod.service_details.get('nodeIP')
                    
                    if ttyd_port and node_ip:
                        # We have the ttyd port and node IP, but no direct URL - create it
                        ttyd_url = f"http://{node_ip}:{ttyd_port}"
                        pod_info['ttydUrl'] = ttyd_url
                        
                        # Also update the database record for next time
                        pod.service_details['ttydUrl'] = ttyd_url
                        pod.save(update_fields=['service_details'])
                        
                        logger.info(f"Created and saved missing ttydUrl: {ttyd_url}")
                    else:
                        # Log the missing information
                        logger.warning(f"Missing ttydPort ({ttyd_port}) or nodeIP ({node_ip}) for pod {pod.pod_name}")
                        pod_info['warning'] = 'Missing ttyd connection information'
                
                # Similarly add filebrowserUrl at the top level
                if 'filebrowserUrl' in pod.service_details and pod.service_details.get('filebrowserUrl'):
                    # Add filebrowserUrl directly to the response object
                    pod_info['filebrowserUrl'] = pod.service_details.get('filebrowserUrl')
                else:
                    # No filebrowserUrl found, check if filebrowserPort exists
                    filebrowser_port = pod.service_details.get('filebrowserPort')
                    node_ip = pod.service_details.get('nodeIP')
                    
                    if filebrowser_port and node_ip:
                        # We have the filebrowser port and node IP, but no direct URL - create it
                        filebrowser_url = f"http://{node_ip}:{filebrowser_port}"
                        pod_info['filebrowserUrl'] = filebrowser_url
                        
                        # Also update the database record for next time
                        pod.service_details['filebrowserUrl'] = filebrowser_url
                        pod.save(update_fields=['service_details'])
                        
                        logger.info(f"Created and saved missing filebrowserUrl: {filebrowser_url}")
            else:
                pod_info['warning'] = 'No service details available'
                
            # Add debug info
            pod_info['debug_info'] = {
                'has_service_details': bool(pod.service_details),
                'service_details_keys': list(pod.service_details.keys()) if pod.service_details else [],
                'pod_existed': pod_existed,
                'pod_was_running': pod_was_running,
                'pod_name': pod.pod_name,
                'pod_namespace': pod.namespace
            }
                
            return JsonResponse(pod_info)
        except Exception as e:
            logger.exception(f"Error in get_k8s_pod_info: {str(e)}")
            return JsonResponse({
                'error': str(e),
                'debug_info': {
                    'project_id': project_id,
                    'conversation_id': conversation_id,
                    'exception_type': type(e).__name__
                }
            }, status=500)
    
    return JsonResponse({'error': 'POST request expected'}, status=400)

@csrf_exempt
def k8s_execute_command(request):
    """
    API endpoint to execute a command in a Kubernetes pod
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        project_id = data.get('project_id')
        conversation_id = data.get('conversation_id')
        command = data.get('command')
        
        # Validate input
        if not (project_id or conversation_id):
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        if not command:
            return JsonResponse({'error': 'Command must be provided'}, status=400)
        
        try:
            # Ensure the pod is running
            success, pod, error_message = manage_kubernetes_pod(
                project_id=project_id,
                conversation_id=conversation_id
            )
            
            if not success or not pod:
                return JsonResponse({
                    'error': 'Failed to start Kubernetes pod',
                    'debug_info': {
                        'project_id': project_id,
                        'conversation_id': conversation_id,
                        'pod_exists': pod is not None,
                        'error_message': error_message
                    }
                }, status=500)
            
            # Execute command
            success, stdout, stderr = execute_command_in_pod(
                project_id=project_id,
                conversation_id=conversation_id,
                command=command
            )
            
            return JsonResponse({
                'success': success,
                'stdout': stdout,
                'stderr': stderr
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'POST request expected'}, status=400)

@csrf_exempt
def get_filebrowser_url(request):
    """
    API endpoint to get the filebrowser URL for a Kubernetes pod
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        project_id = data.get('project_id')
        conversation_id = data.get('conversation_id')
        
        # Validate input
        if not (project_id or conversation_id):
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        try:
            # Check DB for pod info first
            query = Q()
            if project_id:
                query &= Q(project_id=str(project_id))
            elif conversation_id:
                query &= Q(conversation_id=str(conversation_id))
            
            pod = KubernetesPod.objects.filter(query).first()
            
            if not pod:
                return JsonResponse({'error': 'No pod found for the given project or conversation'}, status=404)
            
            # Check if pod is running
            if pod.status != 'running':
                return JsonResponse({'error': f'Pod is not running (status: {pod.status})'}, status=400)
            
            # Extract filebrowser URL from service details
            if pod.service_details and 'filebrowserUrl' in pod.service_details:
                filebrowser_url = pod.service_details.get('filebrowserUrl')
                return JsonResponse({
                    'filebrowserUrl': filebrowser_url,
                    'pod_name': pod.pod_name,
                    'namespace': pod.namespace
                })
            
            # If filebrowserUrl is not directly available, try to construct it
            if pod.service_details:
                filebrowser_port = pod.service_details.get('filebrowserPort')
                node_ip = pod.service_details.get('nodeIP')
                
                if filebrowser_port and node_ip:
                    # Construct filebrowser URL
                    filebrowser_url = f"http://{node_ip}:{filebrowser_port}"
                    
                    # Update the pod record for future requests
                    pod.service_details['filebrowserUrl'] = filebrowser_url
                    pod.save(update_fields=['service_details'])
                    
                    logger.info(f"Created and saved missing filebrowserUrl: {filebrowser_url}")
                    
                    return JsonResponse({
                        'filebrowserUrl': filebrowser_url,
                        'pod_name': pod.pod_name,
                        'namespace': pod.namespace
                    })
                else:
                    # Log the missing information
                    logger.warning(f"Missing filebrowserPort or nodeIP for pod {pod.pod_name}")
                    return JsonResponse({
                        'error': 'Missing filebrowser connection information',
                        'debug_info': {
                            'has_filebrowser_port': bool(filebrowser_port),
                            'has_node_ip': bool(node_ip),
                            'service_details': pod.service_details
                        }
                    }, status=400)
            else:
                return JsonResponse({'error': 'No service details available for this pod'}, status=400)
                
        except Exception as e:
            logger.exception(f"Error in get_filebrowser_url: {str(e)}")
            return JsonResponse({
                'error': str(e),
                'debug_info': {
                    'project_id': project_id,
                    'conversation_id': conversation_id,
                    'exception_type': type(e).__name__
                }
            }, status=500)
    
    return JsonResponse({'error': 'POST request expected'}, status=400)

def get_filebrowser_auth_token(filebrowser_url):
    """
    Helper function to authenticate with the FileBrowser API and get a JWT token with caching
    
    Args:
        filebrowser_url (str): The base URL of the FileBrowser instance
    
    Returns:
        str: The JWT token if successful, None otherwise
    """
    # Create a cache key based on the filebrowser URL
    cache_key = f"filebrowser_token_{hashlib.md5(filebrowser_url.encode()).hexdigest()}"
    
    # Try to get token from cache first
    token = _token_cache.get(cache_key)
    if token:
        # TODO: Add token expiry validation here if needed
        return token
    
    try:
        # Log the authentication attempt
        logger.info(f"Attempting to authenticate with FileBrowser at: {filebrowser_url}")
        
        # FileBrowser uses admin/admin as default credentials
        auth_data = {
            "username": "admin",
            "password": "admin"
        }
        
        # Make API call to login and get token
        response = requests.post(
            f"{filebrowser_url.rstrip('/')}/api/login", 
            json=auth_data, 
            timeout=5
        )
        
        if response.status_code == 200:
            # Check if the response has content
            if not response.content:
                logger.error("FileBrowser authentication returned empty response")
                return None
                
            # The JWT token is returned directly as a string, not JSON
            token = response.content.decode('utf-8')
            
            # Cache the token for 30 minutes
            _token_cache[cache_key] = token
            
            return token
        else:
            logger.error(f"Failed to authenticate with FileBrowser: {response.status_code} - {response.text}")
            return None
            
    except RequestException as e:
        logger.error(f"Error connecting to FileBrowser for authentication: {str(e)}")
        return None


def filebrowser_api_request(filebrowser_url, method, endpoint, data=None, files=None, params=None, timeout=30, max_retries=3):
    """
    Enhanced FileBrowser API request function with retry logic and reduced logging
    """
    import time
    import re
    from urllib.parse import quote
    
    # Normalize method to uppercase
    method = method.upper()
    
    # For file uploads (POST/PUT), always use /api/resources/ directly, not /api/raw/
    if method in ['POST', 'PUT'] and '/api/raw/' in endpoint:
        endpoint = endpoint.replace('/api/raw/', '/api/resources/')
    
    # Don't encode the endpoint for raw file downloads or resources
    if '/api/raw/' not in endpoint and '/api/resources/' not in endpoint:
        endpoint_parts = endpoint.split('/')
        encoded_parts = [quote(part, safe='') for part in endpoint_parts if part]
        endpoint = '/' + '/'.join(encoded_parts)
    
    # Prepare for retry logic
    last_error = None
    attempt = 0
    
    while attempt < max_retries:
        try:
            # Get auth token (cached)
            token = get_filebrowser_auth_token(filebrowser_url)
            if not token:
                return False, None, "Failed to authenticate with FileBrowser"
            
            # Prepare URL and headers
            url = f"{filebrowser_url.rstrip('/')}{endpoint}"
            headers = {"X-Auth": token}
            
            # Determine content type based on data type
            json_data = None
            data_payload = None
            
            if data is not None:
                if isinstance(data, (dict, list)):
                    json_data = data
                    headers["Content-Type"] = "application/json"
                elif isinstance(data, bytes):
                    data_payload = data
                    if '/api/resources/' in endpoint and method in ['POST', 'PUT']:
                        pass  # Don't set Content-Type, let requests handle it
                    else:
                        headers["Content-Type"] = "application/octet-stream"
                elif isinstance(data, str):
                    data_payload = data.encode('utf-8')
                    if '/api/resources/' in endpoint and method in ['POST', 'PUT']:
                        pass  # Don't set Content-Type, let requests handle it
                    else:
                        headers["Content-Type"] = "text/plain; charset=utf-8"
                else:
                    try:
                        import json
                        json_data = json.loads(json.dumps(data, default=str))
                        headers["Content-Type"] = "application/json"
                    except:
                        return False, None, f"Unsupported data type: {type(data)}"
            
            # Make the request
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=json_data,
                data=data_payload,
                files=files,
                params=params,
                timeout=timeout
            )
            
            # Handle 401 Unauthorized - try to refresh token once
            if response.status_code == 401 and attempt == 0:
                logger.warning("Got 401, attempting to refresh token...")
                attempt += 1
                continue
            
            # Check if request was successful
            if 200 <= response.status_code < 300:
                if not response.content:
                    return True, {}, None
                
                # Check if response is JSON
                content_type = response.headers.get('content-type', '')
                if 'application/json' in content_type:
                    try:
                        response_data = response.json()
                        return True, response_data, None
                    except ValueError:
                        return True, response.content, None
                else:
                    return True, response.content, None
            else:
                error_msg = f"FileBrowser API error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return False, None, error_msg
                
        except (requests.Timeout, requests.ConnectionError) as e:
            last_error = e
            attempt += 1
            if attempt < max_retries:
                wait_time = 2 ** (attempt - 1)  # Exponential backoff
                logger.warning(f"Request failed: {str(e)}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                error_msg = f"Error connecting to FileBrowser API after {max_retries} attempts: {str(e)}"
                logger.error(error_msg)
                return False, None, error_msg
                
        except requests.RequestException as e:
            error_msg = f"Error connecting to FileBrowser API: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg
    
    # This should not be reached, but just in case
    return False, None, f"Failed after {max_retries} attempts"


def filebrowser_api_request__(filebrowser_url, method, endpoint, data=None, files=None, params=None):
    """
    Helper function to make requests to the FileBrowser API
    
    Args:
        filebrowser_url (str): The base URL of the FileBrowser instance
        method (str): HTTP method (GET, POST, PUT, DELETE)
        endpoint (str): API endpoint path
        data (dict or bytes, optional): Request data for POST/PUT requests
        files (dict, optional): Files to upload
        params (dict, optional): Query parameters
    
    Returns:
        tuple: (success (bool), response_data (dict), error_message (str))
    """
    try:
        # Log the API request
        logger.info(f"Making FileBrowser API request: {method} {endpoint}")
        
        # Get auth token
        token = get_filebrowser_auth_token(filebrowser_url)
        if not token:
            return False, None, "Failed to authenticate with FileBrowser"
        
        # Prepare URL and headers
        url = f"{filebrowser_url.rstrip('/')}{endpoint}"
        headers = {"X-Auth": token}
        
        # Determine content type based on data type
        json_data = None
        data_payload = None
        
        if data is not None:
            if isinstance(data, dict) or isinstance(data, list):
                # If data is dict/list, send as JSON
                json_data = data
                headers["Content-Type"] = "application/json"
                logger.debug(f"Sending JSON data: {json_data}")
            elif isinstance(data, bytes):
                # If data is bytes, send as raw data
                data_payload = data
                # Add Content-Type header for file uploads
                headers["Content-Type"] = "application/octet-stream"
                logger.debug(f"Sending binary data: {len(data_payload)} bytes")
            elif isinstance(data, str):
                # If data is string, encode and send as raw data
                data_payload = data.encode('utf-8')
                headers["Content-Type"] = "text/plain"
                logger.debug(f"Sending text data: {len(data_payload)} bytes")
            else:
                # For other types, try JSON serialization
                json_data = data
                headers["Content-Type"] = "application/json"
                logger.debug(f"Sending data with type {type(data)} as JSON")
        
        # Log request details for debugging
        logger.info(f"Request URL: {url}")
        logger.info(f"Request headers: {headers}")
        logger.info(f"Request params: {params}")
        logger.info(f"Request data: {data_payload}")
        logger.info(f"Request JSON DATA: {json_data}")
        
        # Make the request
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=json_data,
            data=data_payload,
            files=files,
            params=params,
            timeout=10
        )
        
        # Log response status
        logger.info(f"FileBrowser API response status: {response.status_code} for {method} {endpoint}")
        logger.info(f"FileBrowser API response content: {response.content}")
        logger.info(f"FileBrowser API response: {response}")
        
        # Check if request was successful
        if 200 <= response.status_code < 300:
            if not response.content:
                logger.debug("Empty response content")
                return True, {}, None
            
            # Check if response is JSON
            content_type = response.headers.get('content-type', '')
            if 'application/json' in content_type:
                try:
                    response_data = response.json()
                    logger.debug(f"Received JSON response: {response_data}")
                    return True, response_data, None
                except ValueError:
                    # JSON parsing failed, return raw content
                    logger.debug(f"Failed to parse JSON, returning raw content: {len(response.content)} bytes")
                    return True, response.content, None
            else:
                # For non-JSON responses (like raw file content)
                logger.debug(f"Received non-JSON response ({content_type}): {len(response.content)} bytes")
                return True, response.content, None
        else:
            error_msg = f"FileBrowser API error: {response.status_code} - {response.text}"
            logger.error(error_msg)
            # Include status code in the error message for better error handling
            return False, None, f"{response.status_code} {response.reason}: {response.text}"
            
    except RequestException as e:
        error_msg = f"Error connecting to FileBrowser API: {str(e)}"
        logger.error(error_msg)
        return False, None, error_msg

@csrf_exempt
def k8s_create_item(request):
    """
    API endpoint to create either a file or folder in a Kubernetes pod via the FileBrowser API
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        project_id = data.get('project_id')
        conversation_id = data.get('conversation_id')
        path = data.get('path')
        item_type = data.get('type', 'file')  # 'file' or 'directory'
        content = data.get('content', '')  # Only used for files
        
        # Validate input
        if not (project_id or conversation_id):
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        if not path:
            return JsonResponse({'error': 'Path must be provided'}, status=400)
        
        try:
            # Ensure the pod is running
            query = Q()
            if project_id:
                query &= Q(project_id=str(project_id))
            elif conversation_id:
                query &= Q(conversation_id=str(conversation_id))
            
            pod = KubernetesPod.objects.filter(query).first()
            
            if not pod or pod.status != 'running':
                # Try to create/start the pod if it doesn't exist or isn't running
                success, pod, error_message = manage_kubernetes_pod(
                    project_id=project_id,
                    conversation_id=conversation_id
                )
                
                if not success or not pod:
                    return JsonResponse({
                        'error': 'Failed to start Kubernetes pod',
                        'debug_info': {
                            'project_id': project_id,
                            'conversation_id': conversation_id,
                            'pod_exists': pod is not None,
                            'error_message': error_message
                        }
                    }, status=500)
            
            # Get the filebrowser URL
            filebrowser_url = None
            if pod.service_details and 'filebrowserUrl' in pod.service_details:
                filebrowser_url = pod.service_details.get('filebrowserUrl')
            else:
                # If filebrowserUrl is not directly available, try to construct it
                if pod.service_details:
                    filebrowser_port = pod.service_details.get('filebrowserPort')
                    node_ip = pod.service_details.get('nodeIP')
                    
                    if filebrowser_port and node_ip:
                        # Construct filebrowser URL
                        filebrowser_url = f"http://{node_ip}:{filebrowser_port}"
                        
                        # Update the pod record for future requests
                        pod.service_details['filebrowserUrl'] = filebrowser_url
                        pod.save(update_fields=['service_details'])
                        
                        logger.info(f"Created and saved missing filebrowserUrl: {filebrowser_url}")
            
            if not filebrowser_url:
                return JsonResponse({
                    'error': 'FileBrowser URL not available',
                    'debug_info': {
                        'pod_name': pod.pod_name,
                        'namespace': pod.namespace,
                        'service_details': pod.service_details
                    }
                }, status=400)
            
            # Process the path
            abs_path = path
            if abs_path.startswith('/'):
                abs_path = abs_path[1:]  # Remove leading slash
            
            if item_type == 'directory':
                # Create a directory
                dir_data = {
                    "item": {
                        "path": abs_path,
                        "type": "directory"
                    }
                }
                
                # Make API request to create the directory
                success, response_data, error_message = filebrowser_api_request(
                    filebrowser_url=filebrowser_url,
                    method="POST",
                    endpoint="/api/resources",
                    data=dir_data
                )
                
                # If the API reports the directory already exists, try a direct mkdir command as fallback
                if not success and ("409 Conflict" in error_message or "already exists" in error_message):
                    logger.info(f"Directory '{abs_path}' already exists according to API, trying direct command fallback")
                    
                    # Try a direct command to ensure the directory exists
                    try:
                        # Use execute_command_in_pod to run mkdir
                        cmd_success, cmd_stdout, cmd_stderr = execute_command_in_pod(
                            project_id=project_id,
                            conversation_id=conversation_id,
                            command=f"mkdir -p /workspace/{abs_path}"
                        )
                        
                        if cmd_success:
                            # Command succeeded - directory should now exist
                            logger.info(f"Successfully created directory via direct command: {abs_path}")
                            return JsonResponse({
                                'status': 'success',
                                'message': f'Directory created via command: {path}',
                                'filebrowser_url': filebrowser_url,
                                'note': 'Used command fallback since API reported directory already exists'
                            })
                        else:
                            # Command failed
                            logger.warning(f"Command fallback also failed: {cmd_stderr}")
                    except Exception as cmd_error:
                        logger.exception(f"Error in command fallback: {str(cmd_error)}")
                    
                    # Even if command fallback fails, still return success since FileBrowser thinks it exists
                    logger.info(f"Directory '{abs_path}' already exists, continuing as normal")
                    return JsonResponse({
                        'status': 'success',
                        'message': f'Directory already exists: {path}',
                        'filebrowser_url': filebrowser_url
                    })
                
                if not success:
                    # Check if this is a 409 Conflict error (directory already exists)
                    # This is actually not an error for our purposes
                    if "409 Conflict" in error_message or "already exists" in error_message:
                        logger.info(f"Directory '{abs_path}' already exists, continuing as normal")
                        return JsonResponse({
                            'status': 'success',
                            'message': f'Directory already exists: {path}',
                            'filebrowser_url': filebrowser_url
                        })
                    
                    return JsonResponse({
                        'error': f'Failed to create directory: {error_message}',
                        'debug_info': {
                            'api_endpoint': "/api/resources",
                            'filebrowser_url': filebrowser_url,
                            'dir_data': dir_data
                        }
                    }, status=500)
                
                return JsonResponse({
                    'status': 'success',
                    'message': f'Directory created: {path}',
                    'filebrowser_url': filebrowser_url
                })
            
            else:  # File creation
                # First, ensure parent directory exists
                dir_path = os.path.dirname(abs_path)
                if dir_path:  # Skip if it's in the root
                    parent_dirs = dir_path.split('/')
                    current_path = ""
                    
                    for dir_name in parent_dirs:
                        if current_path:
                            current_path = f"{current_path}/{dir_name}"
                        else:
                            current_path = dir_name
                        
                        # Create directory data
                        dir_data = {
                            "item": {
                                "path": current_path,
                                "type": "directory"
                            }
                        }
                        
                        # Try to create the directory
                        create_success, _, create_error = filebrowser_api_request(
                            filebrowser_url=filebrowser_url,
                            method="POST",
                            endpoint="/api/resources",
                            data=dir_data
                        )
                        
                        # If it failed for a reason other than "already exists", log a warning
                        if not create_success:
                            if "409 Conflict" in create_error or "already exists" in create_error:
                                logger.info(f"Parent directory '{current_path}' already exists, continuing")
                            else:
                                logger.warning(f"Failed to create directory {current_path}: {create_error}")
                            # Continue anyway as the directory might already exist
                
                # URL encode the file path
                encoded_file_path = quote(abs_path, safe='')
                
                # Prepare file content
                file_content = content.encode('utf-8')  # Encode the content as bytes
                
                # Upload the file using the raw endpoint
                raw_endpoint = f"/api/raw/{encoded_file_path}"
                
                success, response_data, error_message = filebrowser_api_request(
                    filebrowser_url=filebrowser_url,
                    method="POST",
                    endpoint=raw_endpoint,
                    data=file_content,
                    params={"override": "true"}  # Override existing file
                )
                
                if not success:
                    logger.warning(f"Raw endpoint upload failed: {error_message}. Trying multipart...")
                    
                    # Try using a multipart/form-data approach as fallback
                    import io
                    file_name = os.path.basename(abs_path)
                    file_obj = io.BytesIO(file_content)
                    
                    files = {
                        'file': (file_name, file_obj, 'application/octet-stream')
                    }
                    
                    resources_endpoint = f"/api/resources/{encoded_file_path}"
                    fallback_success, fallback_response, fallback_error = filebrowser_api_request(
                        filebrowser_url=filebrowser_url,
                        method="POST",
                        endpoint=resources_endpoint,
                        files=files,
                        params={"override": "true"}
                    )
                    
                    if not fallback_success:
                        return JsonResponse({
                            'error': f'Failed to create file: {error_message}. Fallback also failed: {fallback_error}',
                            'debug_info': {
                                'raw_endpoint': raw_endpoint,
                                'resources_endpoint': resources_endpoint,
                                'filebrowser_url': filebrowser_url
                            }
                        }, status=500)
                    else:
                        logger.info("Fallback multipart upload succeeded")
                        success = True
                
                return JsonResponse({
                    'status': 'success',
                    'message': f'File created: {path}',
                    'filebrowser_url': filebrowser_url
                })
        
        except Exception as e:
            logger.exception(f"Error in k8s_create_item: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'POST request expected'}, status=400)

@csrf_exempt
def get_folder_contents(request):
    """
    API endpoint to get the contents of a specific folder (optimized for lazy loading)
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        project_id = data.get('project_id')
        conversation_id = data.get('conversation_id')
        folder_path = data.get('path', '')
        
        # Validate input
        if not (project_id or conversation_id):
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        # Build query to find matching sandbox
        query = Q(status='running')
        if project_id:
            query &= Q(project_id=project_id)
        elif conversation_id:
            query &= Q(conversation_id=conversation_id)
        else:
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        # Get the sandbox record
        sandbox = DockerSandbox.objects.filter(query).first()
        if not sandbox or not sandbox.code_dir:
            return JsonResponse({'error': 'No active sandbox found for the given project or conversation'}, status=404)
        
        # Use the code_dir from the sandbox
        base_path = sandbox.code_dir
        target_path = os.path.join(base_path, folder_path) if folder_path else base_path
        
        try:
            if not os.path.exists(target_path):
                return JsonResponse({'error': 'Folder does not exist'}, status=404)
            
            if not os.path.isdir(target_path):
                return JsonResponse({'error': 'Path is not a directory'}, status=400)
            
            folder_contents = []
            entries = sorted(os.listdir(target_path), key=lambda name: (not os.path.isdir(os.path.join(target_path, name)), name.lower()))
            
            for item in entries:
                if item.startswith('.'):  # Skip hidden files
                    continue
                    
                item_path = os.path.join(target_path, item)
                relative_path = os.path.relpath(item_path, base_path)
                
                if os.path.isfile(item_path):
                    folder_contents.append({
                        'name': item,
                        'type': 'file',
                        'path': relative_path
                    })
                elif os.path.isdir(item_path):
                    folder_contents.append({
                        'name': item,
                        'type': 'directory',
                        'path': relative_path,
                        'children': []  # Empty children - will be loaded on demand
                    })
            
            return JsonResponse({
                'files': folder_contents,
                'folder_path': folder_path
            })
            
        except Exception as e:
            logger.exception(f"Error in get_folder_contents: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'POST request expected'}, status=400)

@csrf_exempt
def get_k8s_folder_contents(request):
    """
    API endpoint to get the contents of a specific folder from a Kubernetes pod (optimized for lazy loading)
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        project_id = data.get('project_id')
        conversation_id = data.get('conversation_id')
        folder_path = data.get('path', '')
        
        # Validate input
        if not (project_id or conversation_id):
            return JsonResponse({'error': 'Either project_id or conversation_id must be provided'}, status=400)
        
        try:
            # Get the pod from the database
            query = Q()
            if project_id:
                query &= Q(project_id=str(project_id))
            elif conversation_id:
                query &= Q(conversation_id=str(conversation_id))
            
            pod = KubernetesPod.objects.filter(query).first()
            
            if not pod or pod.status != 'running':
                return JsonResponse({
                    'error': 'No running Kubernetes pod found',
                    'debug_info': {
                        'project_id': project_id,
                        'conversation_id': conversation_id,
                        'pod_exists': pod is not None,
                        'pod_status': pod.status if pod else None
                    }
                }, status=404)
            
            # Get the filebrowser URL from cached service details
            filebrowser_url = None
            if pod.service_details and 'filebrowserUrl' in pod.service_details:
                filebrowser_url = pod.service_details.get('filebrowserUrl')
            else:
                # If filebrowserUrl is not directly available, try to construct it
                if pod.service_details:
                    filebrowser_port = pod.service_details.get('filebrowserPort')
                    node_ip = pod.service_details.get('nodeIP')
                    
                    if filebrowser_port and node_ip:
                        # Construct filebrowser URL
                        filebrowser_url = f"http://{node_ip}:{filebrowser_port}"
                        
                        # Update the pod record for future requests
                        pod.service_details['filebrowserUrl'] = filebrowser_url
                        pod.save(update_fields=['service_details'])
            
            if not filebrowser_url:
                return JsonResponse({
                    'error': 'FileBrowser URL not available',
                    'debug_info': {
                        'pod_name': pod.pod_name,
                        'namespace': pod.namespace,
                        'service_details': pod.service_details
                    }
                }, status=400)
            
            # Format the folder path for the API request
            abs_path = folder_path
            if abs_path.startswith('/'):
                abs_path = abs_path[1:]  # Remove leading slash
            
            # URL encode the path for the API request
            encoded_path = quote(abs_path, safe='')
            
            # Construct the API endpoint
            api_endpoint = f"/api/resources/{encoded_path}"
            
            # Make single API request to get directory contents (no recursion)
            success, response_data, error_message = filebrowser_api_request(
                filebrowser_url=filebrowser_url,
                method="GET",
                endpoint=api_endpoint
            )
            
            if not success:
                return JsonResponse({
                    'error': f'Failed to list folder contents: {error_message}',
                    'debug_info': {
                        'api_endpoint': api_endpoint,
                        'filebrowser_url': filebrowser_url
                    }
                }, status=500)
            
            # Process the response to build a simple folder structure
            folder_contents = []
            items = response_data.get('items', [])
            
            for item in items:
                name = item.get('name', '')
                is_dir = item.get('isDir', False)
                
                path = os.path.join(folder_path, name).replace('\\', '/')
                if path.startswith('/'):
                    path = path[1:]  # Remove leading slash
                
                node = {
                    'name': name,
                    'type': 'directory' if is_dir else 'file',
                    'path': path
                }
                
                # For directories, just set empty children - will be loaded on demand
                if is_dir:
                    node['children'] = []
                
                folder_contents.append(node)
            
            return JsonResponse({
                'files': folder_contents,
                'folder_path': folder_path,
                'pod_info': {
                    'namespace': pod.namespace,
                    'pod_name': pod.pod_name,
                    'status': pod.status
                }
            })
        except Exception as e:
            logger.exception(f"Error in get_k8s_folder_contents: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'POST request expected'}, status=400)
