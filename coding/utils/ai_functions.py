import json
import os
import string
import random
import shlex
import asyncio
import subprocess
from pathlib import Path
from asgiref.sync import sync_to_async
from django.db import transaction
from projects.models import Project, ProjectFeature, ProjectPersona, \
                            ProjectPRD, ProjectDesignSchema, ProjectTickets, \
                            ProjectCodeGeneration, ProjectChecklist
from coding.utils.prd_functions import analyze_features, analyze_personas, \
                    design_schema, generate_tickets_per_feature 

from coding.docker.docker_utils import (
    Sandbox, 
    get_or_create_sandbox,
    get_sandbox_by_project_id, 
    list_running_sandboxes,
    get_client_project_folder_path,
    add_port_to_sandbox
)
from django.conf import settings
from coding.k8s_manager.manage_pods import execute_command_in_pod, manage_kubernetes_pod

from coding.models import KubernetesPod, KubernetesPortMapping
from coding.models import CommandExecution
from accounts.models import GitHubToken


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def validate_project_id(project_id):
    """Validate project_id and return error response if invalid"""
    if not project_id:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required"
        }
    return None

async def get_project(project_id):
    """Get project by ID with proper error handling"""
    try:
        return await sync_to_async(Project.objects.get)(id=project_id)
    except Project.DoesNotExist:
        return None

async def get_project_with_relations(project_id, *relations):
    """Get project with select_related for avoiding additional queries"""
    try:
        return await sync_to_async(
            lambda: Project.objects.select_related(*relations).get(id=project_id)
        )()
    except Project.DoesNotExist:
        return None

def validate_function_args(function_args, required_keys=None):
    """Validate function arguments structure"""
    if not isinstance(function_args, dict):
        return {
            "is_notification": False,
            "message_to_agent": "Error: Invalid function arguments format"
        }
    
    if required_keys:
        missing_keys = [key for key in required_keys if key not in function_args]
        if missing_keys:
            return {
                "is_notification": False,
                "message_to_agent": f"Error: Missing required arguments: {', '.join(missing_keys)}"
            }
    return None

def execute_local_command(command: str, workspace_path: str) -> tuple[bool, str, str]:
    """
    Execute a command locally using subprocess.
    
    Args:
        command: The command to execute
        workspace_path: The workspace directory path
        
    Returns:
        Tuple of (success, stdout, stderr)
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=workspace_path,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out after 5 minutes"
    except Exception as e:
        return False, "", f"Error executing command: {str(e)}"

def execute_local_server_command(command: str, workspace_path: str) -> tuple[bool, str, str]:
    """
    Execute a server command locally using subprocess in background.
    
    Args:
        command: The command to execute
        workspace_path: The workspace directory path
        
    Returns:
        Tuple of (success, stdout, stderr)
    """
    try:
        # Create tmp directory for logs if it doesn't exist
        tmp_path = Path(workspace_path) / "tmp"
        tmp_path.mkdir(exist_ok=True)
        
        # Run command in background and redirect output to log file
        full_command = f"{command} > {tmp_path}/server_output.log 2>&1 &"
        
        result = subprocess.run(
            full_command,
            shell=True,
            cwd=workspace_path,
            capture_output=True,
            text=True,
            timeout=30  # Shorter timeout since server should start quickly
        )
        
        # For background processes, success is typically when the command starts successfully
        if result.returncode == 0:
            return True, f"Server command started successfully in background", ""
        else:
            return False, result.stdout, result.stderr
            
    except subprocess.TimeoutExpired:
        return False, "", "Server command timed out after 30 seconds"
    except Exception as e:
        return False, "", f"Error executing server command: {str(e)}"

# ============================================================================
# MAIN DISPATCHER
# ============================================================================

async def app_functions(function_name, function_args, project_id, conversation_id):
    """
    Return a list of all the functions that can be called by the AI
    """
    print(f"Function name: {function_name}")
    print(f"Function args: {function_args}")

    # Validate project_id for most functions
    if function_name not in ["get_github_access_token"] and project_id:
        error_response = validate_project_id(project_id)
        if error_response:
            return error_response

    match function_name:
        case "extract_features":
            return await extract_features(function_args, project_id)
        case "extract_personas":
            return await extract_personas(function_args, project_id)
        case "get_features":
            return await get_features(project_id)
        case "get_personas":
            return await get_personas(project_id)
        case "save_prd":
            return await save_prd(function_args, project_id)
        case "get_prd":
            return await get_prd(project_id)
        case "save_features":
            return await save_features(project_id)
        case "save_personas":
            return await save_personas(project_id)
        case "design_schema":
            return await save_design_schema(function_args, project_id)
        case "checklist_tickets":
            return await checklist_tickets(function_args, project_id)
        case "update_checklist_ticket":
            return await update_individual_checklist_ticket(project_id, function_args.get('ticket_id'), function_args.get('status'))
        case "get_pending_tickets":
            return await get_pending_tickets(project_id)
        case "get_latest_ticket":
            return await get_latest_ticket(project_id)
        
        case "execute_command":
            command = function_args.get('commands', '')
            print(f"Running command: {command}")
            if settings.ENVIRONMENT == "local":
                result = await run_command_locally(command, project_id=project_id, conversation_id=conversation_id)
            else:
                result = await run_command_in_k8s(command, project_id=project_id, conversation_id=conversation_id)
            return result
        
        case "start_server":
            command = function_args.get('start_server_command', '')
            application_port = function_args.get('application_port', '')
            type = function_args.get('type', '')
            print(f"Running server: {command}")
            if settings.ENVIRONMENT == "local":
                result = await run_server_locally(command, project_id=project_id, conversation_id=conversation_id, application_port=application_port, type=type)
            else:
                result = await server_command_in_k8s(command, project_id=project_id, conversation_id=conversation_id, application_port=application_port, type=type)
            return result
        
        case "start_server_local":
            command = function_args.get('start_server_command', '')
            application_port = function_args.get('application_port', '')
            type = function_args.get('type', '')
            print(f"Running local server: {command}")
            result = await run_server_locally(command, project_id=project_id, conversation_id=conversation_id, application_port=application_port, type=type)
            return result
        
        case "get_github_access_token":
            return await get_github_access_token(project_id=project_id, conversation_id=conversation_id)

    return None

# ============================================================================
# FEATURE FUNCTIONS
# ============================================================================

async def save_features(project_id):
    """
    Save the features from the PRD into a different list
    """
    print("Save features function called \n\n")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }

    try:
        # Check if project has PRD
        try:
            prd_content = await sync_to_async(lambda: project.prd.prd)()
        except ProjectPRD.DoesNotExist:
            return {
                "is_notification": False,
                "message_to_agent": "Error: Project does not have a PRD. Please create a PRD first."
            }

        # Get all features for this project
        features = await sync_to_async(
            lambda: list(ProjectFeature.objects.filter(project=project))
        )()
        
        # Convert features to list of dicts
        feature_list = []
        for feature in features:
            feature_list.append({
                "name": feature.name,
                "description": feature.description,
                "details": feature.details,
                "priority": feature.priority
            })
        
        # Run AI analysis in thread pool to avoid blocking
        new_features_data = await asyncio.get_event_loop().run_in_executor(
            None, analyze_features, feature_list, prd_content
        )

        # Parse the JSON response
        new_features_dict = json.loads(new_features_data)
        
        # Extract the list of features from the dictionary
        if 'features' in new_features_dict:
            new_features = new_features_dict['features']
        else:
            new_features = new_features_dict

        print(f"\n\n New features: {new_features}")
    
        # Create new features using async database operations
        await sync_to_async(lambda: [
            ProjectFeature.objects.create(
                project=project,
                name=feature['name'],
                description=feature['description'],
                details=feature['details'],
                priority=feature['priority']
            ) for feature in new_features
        ])()
        
        return {
            "is_notification": False,
            "notification_type": "features",
            "message_to_agent": f"Features have been saved in the database"
        }
    except Exception as e:
        print(f"Error saving features: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving features: {str(e)}"
        }

async def save_personas(project_id):
    """
    Save the personas from the PRD into a different list
    """
    print("Save personas function called \n\n")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }

    try:
        # Check if project has PRD
        try:
            prd_content = await sync_to_async(lambda: project.prd.prd)()
        except ProjectPRD.DoesNotExist:
            return {
                "is_notification": False,
                "message_to_agent": "Error: Project does not have a PRD. Please create a PRD first."
            }

        # Get all personas for this project
        personas = await sync_to_async(
            lambda: list(ProjectPersona.objects.filter(project=project))
        )()
        
        # Convert personas to list of dicts
        persona_list = []
        for persona in personas:
            persona_list.append({
                "name": persona.name,
                "role": persona.role,
                "description": persona.description
            })
        
        # Run AI analysis in thread pool to avoid blocking
        new_personas_data = await asyncio.get_event_loop().run_in_executor(
            None, analyze_personas, persona_list, prd_content
        )

        # Parse the JSON response
        new_personas_dict = json.loads(new_personas_data)
        
        # Extract the list of personas from the dictionary
        if 'personas' in new_personas_dict:
            new_personas = new_personas_dict['personas']
        else:
            new_personas = new_personas_dict

        print(f"\n\n New personas: {new_personas}")
    
        # Create new personas using async database operations
        await sync_to_async(lambda: [
            ProjectPersona.objects.create(
                project=project,
                name=persona['name'],
                role=persona['role'],
                description=persona['description']
            ) for persona in new_personas
        ])()
        
        return {
            "is_notification": True,
            "notification_type": "personas",
            "message_to_agent": f"Personas have been successfully saved in the database"
        }
    except Exception as e:
        print(f"Error saving personas: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving personas: {str(e)}"
        }

async def extract_features(function_args, project_id):
    """
    Extract the features from the project into a different list and save them to the database
    """
    print("Feature extraction function called \n\n")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    validation_error = validate_function_args(function_args, ['features'])
    if validation_error:
        return validation_error
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    features = function_args.get('features', [])
    
    if not isinstance(features, list):
        return {
            "is_notification": False,
            "message_to_agent": "Error: features must be a list"
        }
    
    try:
        # Create new features using async database operations
        await sync_to_async(lambda: [
            ProjectFeature.objects.create(
                project=project,
                name=feature.get('name', ''),
                description=feature.get('description', ''),
                details=feature.get('details', ''),
                priority=feature.get('priority', 'medium')
            ) for feature in features if isinstance(feature, dict)
        ])()
        
        return {
            "is_notification": True,
            "notification_type": "features",
            "message_to_agent": f"Features have been saved in the database"
        }
    except Exception as e:
        print(f"Error saving features: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving features: {str(e)}"
        }

async def extract_personas(function_args, project_id):
    """
    Extract the personas from the project and save them to the database
    """
    print("Persona extraction function called \n\n")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    validation_error = validate_function_args(function_args, ['personas'])
    if validation_error:
        return validation_error
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    personas = function_args.get('personas', [])
    
    if not isinstance(personas, list):
        return {
            "is_notification": False,
            "message_to_agent": "Error: personas must be a list"
        }
    
    try:
        # Create new personas using async database operations
        await sync_to_async(lambda: [
            ProjectPersona.objects.create(
                project=project,
                name=persona.get('name', ''),
                role=persona.get('role', ''),
                description=persona.get('description', '')
            ) for persona in personas if isinstance(persona, dict)
        ])()
        
        return {
            "is_notification": True,
            "notification_type": "personas",
            "message_to_agent": f"Personas have been saved in the database"
        }
    except Exception as e:
        print(f"Error saving personas: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving personas: {str(e)}"
        }

async def get_features(project_id):
    """
    Retrieve existing features for a project
    """
    print("Get features function called \n\n")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required to retrieve features"
        }
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    features = await sync_to_async(
        lambda: list(ProjectFeature.objects.filter(project=project))
    )()
    
    if not features:
        return {
            "is_notification": True,
            "notification_type": "features",
            "message_to_agent": "No features found for this project"
        }
    
    feature_list = []
    for feature in features:
        feature_list.append({
            "name": feature.name,
            "description": feature.description,
            "details": feature.details,
            "priority": feature.priority
        })

    return {
        "is_notification": True,
        "notification_type": "features",
        "message_to_agent": f"Following features already exists in the database: {feature_list}"
    }

async def get_personas(project_id):
    """
    Retrieve existing personas for a project
    """
    print("Get personas function called \n\n")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required to retrieve personas"
        }
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    personas = await sync_to_async(
        lambda: list(ProjectPersona.objects.filter(project=project))
    )()
    
    if not personas:
        return {
            "is_notification": True,
            "notification_type": "personas",
            "message_to_agent": "No personas found for this project"
        }
    
    persona_list = []
    for persona in personas:
        persona_list.append({
            "name": persona.name,
            "role": persona.role,
            "description": persona.description
        })

    return {
        "is_notification": True,
        "notification_type": "personas",
        "message_to_agent": f"Following personas already exists in the database: {persona_list}"
    }

async def save_prd(function_args, project_id):
    """
    Save the PRD for a project
    """
    print(f"PRD saving function called \n\n: {function_args}")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    validation_error = validate_function_args(function_args, ['prd'])
    if validation_error:
        return validation_error
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    prd_content = function_args.get('prd', '')

    if not prd_content:
        return {
            "is_notification": False,
            "message_to_agent": "Error: PRD content cannot be empty"
        }

    print(f"\n\n\nPRD Content: {prd_content}")

    try:
        # Save PRD to database
        created = await sync_to_async(lambda: (
            lambda: (
                lambda prd, created: created
            )(*ProjectPRD.objects.get_or_create(project=project, defaults={'prd': prd_content}))
        )())()
        
        # Update existing PRD if it wasn't created
        if not created:
            await sync_to_async(lambda: (
                ProjectPRD.objects.filter(project=project).update(prd=prd_content)
            ))()
        
        action = "created" if created else "updated"

        # Save features and personas
        await save_features(project_id)
        await save_personas(project_id)
        
        return {
            "is_notification": True,
            "notification_type": "prd",
            "message_to_agent": f"PRD {action} successfully in the database"
        }
        
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving PRD: {str(e)}"
        }

async def get_prd(project_id):
    """
    Retrieve the PRD for a project
    """
    print("Get PRD function called \n\n")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required to retrieve PRD"
        }
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    try:
        # Check if project has PRD and get content
        prd_content = await sync_to_async(lambda: project.prd.prd)()
        return {
            "is_notification": True,
            "notification_type": "prd",
            "message_to_agent": f"Here is the existing version of the PRD: {prd_content} \n\n Please update this as needed."
        }
    except ProjectPRD.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": "No PRD found for this project. Please create a PRD first."
        }
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error retrieving PRD: {str(e)}"
        }

async def save_design_schema(function_args, project_id):
    """
    Save the design schema for a project
    """
    print("Save design schema function called \n\n")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    validation_error = validate_function_args(function_args, ['user_input'])
    if validation_error:
        return validation_error
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    user_input = function_args.get('user_input', '')

    try:
        # Check if project has PRD
        try:
            prd_content = await sync_to_async(lambda: project.prd.prd)()
        except ProjectPRD.DoesNotExist:
            return {
                "is_notification": False,
                "message_to_agent": "Error: Project does not have a PRD. Please create a PRD first."
            }

        # Get existing design schema if any
        try:
            existing_schema = await sync_to_async(lambda: project.design_schema.design_schema)()
        except ProjectDesignSchema.DoesNotExist:
            existing_schema = ""
        
        # Run design schema generation in thread pool
        design_schema_content = await asyncio.get_event_loop().run_in_executor(
            None, design_schema, prd_content, existing_schema, user_input
        )
        design_schema_content = json.loads(design_schema_content)

        if 'design_schema' in design_schema_content:
            design_schema_content = design_schema_content['design_schema']
        else:
            return {
                "is_notification": False,
                "message_to_agent": "Error: design_schema is required to save design schema"
            }
        
        # Save design schema using async database operations
        await sync_to_async(lambda: (
            lambda schema, created: None
        )(*ProjectDesignSchema.objects.get_or_create(
            project=project, 
            defaults={'design_schema': design_schema_content}
        )))()
        
        # Update if it already existed
        await sync_to_async(lambda: (
            ProjectDesignSchema.objects.filter(project=project).update(design_schema=design_schema_content)
        ))()
        
        return {
            "is_notification": True,
            "notification_type": "design_schema",
            "message_to_agent": f"Design schema successfully updated in the database"
        }
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving design schema: {str(e)}"
        }

async def checklist_tickets(function_args, project_id):
    """
    Generate checklist tickets for a project
    """
    print("Checklist tickets function called \n\n")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    # Validate function arguments
    validation_error = validate_function_args(function_args, ['tickets'])
    if validation_error:
        return validation_error
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    checklist_tickets = function_args.get('tickets', [])
    
    if not isinstance(checklist_tickets, list):
        return {
            "is_notification": False,
            "message_to_agent": "Error: tickets must be a list"
        }
    
    try:
        # Create tickets in bulk
        await sync_to_async(lambda: [
            ProjectChecklist.objects.create(
                project=project,
                name=ticket.get('name', ''),
                description=ticket.get('description', ''),
                priority=ticket.get('priority', 'medium'),
                status='open',
                role=ticket.get('role', 'agent')
            ) for ticket in checklist_tickets if isinstance(ticket, dict)
        ])()
        
        return {
            "is_notification": True,
            "notification_type": "checklist_tickets",
            "message_to_agent": f"Checklist tickets have been successfully generated and saved in the database"
        }
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error creating checklist tickets: {str(e)}"
        }

async def get_latest_ticket(project_id):
    """
    Get the latest ticket for a project
    """
    print("Get pending tickets function called \n\n")

    error_response = validate_project_id(project_id)
    if error_response:
        return error_response

    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    pending_ticket = await sync_to_async(
        lambda: ProjectChecklist.objects.filter(project=project, status='open', role='agent').first()
    )()
    
    # Print ticket ID instead of the object to avoid triggering __str__ method
    print(f"\n\nPending ticket ID: {pending_ticket.id if pending_ticket else None}")

    if pending_ticket:
        # Access the fields directly without triggering related queries
        message_to_agent = f"Pending ticket: \nTicket Id: {pending_ticket.id}, \nTicket Name: {pending_ticket.name},\
              \nTicket Description: {pending_ticket.description}, \nTicket Priority: {pending_ticket.priority}. \n\nBuild this ticket first."
    else:
        message_to_agent = "No pending tickets found"

    print(f"\n\nMessage to agent: {message_to_agent}")

    return {
        "is_notification": True,
        "notification_type": "get_pending_tickets",
        "message_to_agent": message_to_agent
    }

async def update_individual_checklist_ticket(project_id, ticket_id, status):
    """
    Update an individual checklist ticket for a project
    """
    print("Update individual checklist ticket function called \n\n")
    print(f"\n\nTicket ID: {ticket_id} and status: {status}")
    
    if not ticket_id or not status:
        return {
            "is_notification": False,
            "message_to_agent": "Error: ticket_id and status are required"
        }
    
    try:
        # Get and update ticket in a single async operation
        await sync_to_async(lambda: (
            ProjectChecklist.objects.filter(id=ticket_id).update(status=status)
        ))()

        print(f"\n\nChecklist ticket {ticket_id} has been successfully updated in the database. Proceed to next checklist item, unless otherwise specified by the user")

        return {
            "is_notification": True,
            "notification_type": "checklist_tickets",
            "message_to_agent": f"Checklist ticket {ticket_id} has been successfully updated in the database. Proceed to next checklist item, unless otherwise specified by the user"
        }
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error updating ticket: {str(e)}"
        }

async def get_pending_tickets(project_id):
    """
    Get pending tickets for a project
    """
    print("Get pending tickets function called \n\n")

    error_response = validate_project_id(project_id)
    if error_response:
        return error_response

    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    project_list = await sync_to_async(
        lambda: ProjectChecklist.objects.filter(project=project, status='open', role='agent').first()
    )()

    if project_list:
        # Access the fields directly without triggering related queries
        message_content = f"Ticket ID: {project_list.id}, Name: {project_list.name}, Description: {project_list.description}, Status: {project_list.status}"
    else:
        message_content = "No pending tickets found"

    return {
        "is_notification": True,
        "notification_type": "get_pending_tickets",
        "message_to_agent": f"Pending tickets in open state: {message_content}. Please update the status of the tickets as needed. If not, continue closing them."
    }

async def get_github_access_token(project_id: int | str = None, conversation_id: int | str = None) -> dict:
    """
    Get GitHub access token for a project
    """
    try:
        error_response = validate_project_id(project_id)
        if error_response:
            return {
                "is_notification": True,
                "notification_type": "command_error",
                "message_to_agent": "Error: project_id is required to get GitHub access token"
            }

        # Get project with owner to avoid additional database queries
        project = await get_project_with_relations(project_id, 'owner')
        if not project:
            return {
                "is_notification": True,
                "notification_type": "command_error",
                "message_to_agent": f"Project with ID {project_id} not found"
            }

        user_id = project.owner.id
        project_name = project.name

        github_token = await sync_to_async(GitHubToken.objects.get)(user_id=user_id)
        access_token = github_token.access_token

        if access_token is None or access_token == "":
            return {
                "is_notification": True,
                "notification_type": "command_error",
                "message_to_agent": f"No Github access token found. Inform user to connect their Github account."
            }
        
        return {
            "is_notification": True,
            "notification_type": "command_output", 
            "message_to_agent": f"Github access token {access_token} found and project name {project_name} found. Please use this to commit the code",
            "user_id": user_id
        }

    except Project.DoesNotExist:
        return {
            "is_notification": True,
            "notification_type": "command_error",
            "message_to_agent": f"Project with ID {project_id} not found"
        }
    except GitHubToken.DoesNotExist:
        return {
            "is_notification": True,
            "notification_type": "command_error",
            "message_to_agent": f"No Github access token found for this user. Inform user to connect their Github account."
        }
    except Exception as e:
        return {
            "is_notification": True,
            "notification_type": "command_error", 
            "message_to_agent": f"Error getting user_id: {str(e)}"
        }

async def run_command_in_k8s(command: str, project_id: int | str = None, conversation_id: int | str = None) -> dict:
    """
    Run a command in the terminal using Kubernetes pod.
    """

    if project_id:
        pod = await sync_to_async(
            lambda: KubernetesPod.objects.filter(project_id=project_id).first()
        )()

    command_to_run = f"cd /workspace && {command}"
    print(f"\n\nCommand: {command_to_run}")

    # Create command record in database
    cmd_record = await sync_to_async(lambda: (
        CommandExecution.objects.create(
            project_id=project_id,
            command=command,
            output=None  # Will update after execution
        )
    ))()

    success = False
    stdout = ""
    stderr = ""

    if pod:
        # Execute the command using the Kubernetes API function in thread pool
        success, stdout, stderr = await asyncio.get_event_loop().run_in_executor(
            None, execute_command_in_pod, project_id, conversation_id, command_to_run
        )

        print(f"\n\nCommand output: {stdout}")

        # Update command record with output
        await sync_to_async(lambda: (
            setattr(cmd_record, 'output', stdout if success else stderr),
            cmd_record.save()
        )[1])()

    if not success or not pod:
        # If no pod is found, update the command record
        if not pod:
            await sync_to_async(lambda: (
                setattr(cmd_record, 'output', "No Kubernetes pod found for the project"),
                cmd_record.save()
            )[1])()
            
        return {
            "is_notification": True,
            "notification_type": "command_error",
            "message_to_agent": f"{stderr}\n\nThe command execution failed. Stop generating further steps and inform the user that the command could not be executed.",
        }
    
    return {
        "is_notification": True,
        "notification_type": "command_output", 
        "message_to_agent": f"Command output: {stdout}\n\nFix if there is any error, otherwise you can proceed to next step",
    }

async def server_command_in_k8s(command: str, project_id: int | str = None, conversation_id: int | str = None, application_port: int | str = None, type: str = None) -> dict:
    """
    Run a command in the terminal using Kubernetes pod to start an application server.
    
    Args:
        command: The command to run
        project_id: The project ID
        conversation_id: The conversation ID
        application_port: The port the application listens on inside the container
        type: The type of application (frontend, backend, etc.)
        
    Returns:
        Dict containing command output and port mapping information
    """
    from coding.k8s_manager.manage_pods import execute_command_in_pod, get_k8s_api_client
    from coding.models import KubernetesPod, KubernetesPortMapping
    from kubernetes import client as k8s_client
    from kubernetes.client.rest import ApiException

    print(f"\n\nApplication port: {application_port}")
    print(f"\n\nType: {type}")

    if project_id:
        pod = await sync_to_async(
            lambda: KubernetesPod.objects.filter(project_id=project_id).first()
        )()
    else:
        return {
            "is_notification": True,
            "notification_type": "command_error",
            "message_to_agent": f"No project ID provided. Cannot execute the command."
        }

    if not pod:
        return {
            "is_notification": True,
            "notification_type": "command_error",
            "message_to_agent": f"No Kubernetes pod found for the project. Cannot execute the command."
        }

    # Handle application port if provided
    if application_port:
        try:
            # Convert application_port to integer if it's a string
            application_port = int(application_port)
            
            # Check if port is in valid range
            if application_port < 1 or application_port > 65535:
                return {
                    "is_notification": True,
                    "notification_type": "command_error",
                    "message_to_agent": f"Invalid application port: {application_port}. Port must be between 1 and 65535."
                }
        except (ValueError, TypeError):
            return {
                "is_notification": True,
                "notification_type": "command_error",
                "message_to_agent": f"Invalid application port: {application_port}. Must be a valid integer."
            }
            
        # Standardize port type
        port_type = type.lower() if type else "application"
        if port_type not in ["frontend", "backend", "application"]:
            port_type = "application"
            
        # Check if we've already set up a port mapping for this container port
        existing_mapping = await sync_to_async(
            lambda: KubernetesPortMapping.objects.filter(
                pod=pod,
                container_port=application_port
            ).first()
        )()
        
        service_name = f"{pod.namespace}-service"
        
        if existing_mapping:
            # Use existing mapping
            print(f"Using existing port mapping for {port_type} port {application_port}")
            node_port = existing_mapping.node_port
        else:
            # Need to add port to service and create mapping using Kubernetes API
            print(f"Creating new port mapping for {port_type} port {application_port}")
            
            # Get Kubernetes API client in thread pool
            api_client, core_v1_api, apps_v1_api = await asyncio.get_event_loop().run_in_executor(
                None, get_k8s_api_client
            )
            if not core_v1_api:
                return {
                    "is_notification": True,
                    "notification_type": "command_error",
                    "message_to_agent": f"Failed to connect to Kubernetes API"
                }
            
            try:
                # Get the current service in thread pool
                service = await asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: core_v1_api.read_namespaced_service(
                        name=service_name,
                        namespace=pod.namespace
                    )
                )
                
                # Define a unique port name for this application port
                port_name = f"{port_type}-{application_port}"
                
                # Check if port already exists in service
                existing_port = None
                for port in service.spec.ports:
                    if port.port == application_port or port.name == port_name:
                        existing_port = port
                        break
                
                if existing_port:
                    node_port = existing_port.node_port
                    print(f"Port {application_port} already exists in service with nodePort {node_port}")
                else:
                    # Add new port to service
                    new_port = k8s_client.V1ServicePort(
                        name=port_name,
                        port=application_port,
                        target_port=application_port,
                        protocol="TCP"
                    )
                    
                    # Add the new port to the existing ports
                    service.spec.ports.append(new_port)
                    
                    # Update the service in thread pool
                    updated_service = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: core_v1_api.patch_namespaced_service(
                            name=service_name,
                            namespace=pod.namespace,
                            body=service
                        )
                    )
                    
                    # Get the assigned nodePort
                    for port in updated_service.spec.ports:
                        if port.name == port_name:
                            node_port = port.node_port
                            break
                    else:
                        return {
                            "is_notification": True,
                            "notification_type": "command_error",
                            "message_to_agent": f"Failed to get nodePort for port {application_port}"
                        }
                    
                    print(f"Kubernetes assigned nodePort {node_port} for {port_type} port {application_port}")
                
                # Get node IP using Kubernetes API in thread pool
                try:
                    nodes = await asyncio.get_event_loop().run_in_executor(
                        None, core_v1_api.list_node
                    )
                    node_ip = "localhost"
                    if nodes.items:
                        for address in nodes.items[0].status.addresses:
                            if address.type == "InternalIP":
                                node_ip = address.address
                                break
                except Exception as e:
                    print(f"Warning: Could not get node IP: {e}")
                    node_ip = "localhost"
                
                # Create port mapping in database if it doesn't exist
                if not existing_mapping:
                    description = f"{port_type.capitalize()} service"
                    
                    await sync_to_async(lambda: (
                        KubernetesPortMapping.objects.create(
                            pod=pod,
                            container_name="dev-environment",
                            container_port=application_port,
                            service_port=application_port,
                            node_port=node_port,
                            protocol="TCP",
                            service_name=service_name,
                            description=description
                        )
                    ))()
                
                # Update pod's service_details
                await sync_to_async(lambda: (
                    lambda: (
                        setattr(pod, 'service_details', {
                            **(pod.service_details or {}),
                            f"{port_type}Port": node_port,
                            "nodeIP": node_ip,
                            f"{port_type}Url": f"http://{node_ip}:{node_port}"
                        }),
                        pod.save()
                    )[1]
                )())()
                
            except ApiException as e:
                return {
                    "is_notification": True,
                    "notification_type": "command_error",
                    "message_to_agent": f"Failed to update service: {e}"
                }
            except Exception as e:
                return {
                    "is_notification": True,
                    "notification_type": "command_error",
                    "message_to_agent": f"Error setting up port mapping: {str(e)}"
                }
    
    # Prepare and run the command in the pod using Kubernetes API
    full_command = f"mkdir -p /workspace/tmp && cd /workspace && {command} > /workspace/tmp/cmd_output.log 2>&1 &"
    print(f"\n\nCommand: {full_command}")

    # Execute the command using the Kubernetes API function in thread pool
    success, stdout, stderr = await asyncio.get_event_loop().run_in_executor(
        None, execute_command_in_pod, project_id, conversation_id, full_command
    )
    
    print(f"\n\nCommand output: {stdout}")

    if not success:
        return {
            "is_notification": True,
            "notification_type": "command_error",
            "message_to_agent": f"{stderr}\n\nThe command execution failed. Stop generating further steps and inform the user that the command could not be executed.",
        }
    
    # Prepare success message with port information if applicable
    message = f"{stdout}\n\nCommand to run server is successful."
    
    if application_port:
        # Get the pod's service details
        service_details = pod.service_details or {}
        node_ip = service_details.get('nodeIP', 'localhost')
        
        # Add URL information to the message
        message += f"\n\n{port_type.capitalize()} is running on port {application_port} inside the container."
        message += f"\nYou can access it at: http://{node_ip}:{node_port}"
    
    return {
        "is_notification": True,
        "notification_type": "command_output",
        "message_to_agent": message + "\n\nProceed to next step",
    }

async def run_command_locally(command: str, project_id: int | str = None, conversation_id: int | str = None) -> dict:
    """
    Run a command in the local terminal using subprocess.
    Creates a local workspace directory if it doesn't exist.
    """
    # Create workspace directory if it doesn't exist
    workspace_path = Path.home() / "LFG" / "workspace"
    workspace_path.mkdir(parents=True, exist_ok=True)
    
    command_to_run = f"cd {workspace_path} && {command}"
    print(f"\n\nLocal Command: {command_to_run}")

    # Create command record in database
    cmd_record = await sync_to_async(lambda: (
        CommandExecution.objects.create(
            project_id=project_id,
            command=command,
            output=None  # Will update after execution
        )
    ))()

    success = False
    stdout = ""
    stderr = ""

    try:
        # Execute the command locally using subprocess in thread pool
        success, stdout, stderr = await asyncio.get_event_loop().run_in_executor(
            None, execute_local_command, command, str(workspace_path)
        )

        print(f"\n\nLocal Command output: {stdout}")
        if stderr:
            print(f"\n\nLocal Command stderr: {stderr}")

        # Update command record with output
        await sync_to_async(lambda: (
            setattr(cmd_record, 'output', stdout if success else stderr),
            cmd_record.save()
        )[1])()

    except Exception as e:
        error_msg = f"Failed to execute command locally: {str(e)}"
        stderr = error_msg
        
        # Update command record with error
        await sync_to_async(lambda: (
            setattr(cmd_record, 'output', error_msg),
            cmd_record.save()
        )[1])()

    if not success:
        return {
            "is_notification": True,
            "notification_type": "command_error",
            "message_to_agent": f"{stderr}\n\nThe local command execution failed. Stop generating further steps and inform the user that the command could not be executed.",
        }
    
    return {
        "is_notification": True,
        "notification_type": "command_output", 
        "message_to_agent": f"Local command output: {stdout}\n\nFix if there is any error, otherwise you can proceed to next step",
    }

async def run_server_locally(command: str, project_id: int | str = None, conversation_id: int | str = None, application_port: int | str = None, type: str = None) -> dict:
    """
    Run a server command locally using subprocess in background.
    Creates a local workspace directory if it doesn't exist.
    
    Args:
        command: The command to run
        project_id: The project ID
        conversation_id: The conversation ID  
        application_port: The port the application listens on locally
        type: The type of application (frontend, backend, etc.)
        
    Returns:
        Dict containing command output and local server information
    """
    print(f"\n\nLocal Application port: {application_port}")
    print(f"\n\nLocal Type: {type}")

    # Create workspace directory if it doesn't exist
    workspace_path = Path.home() / "LFG" / "workspace"
    workspace_path.mkdir(parents=True, exist_ok=True)
    
    # Handle application port validation if provided
    if application_port:
        try:
            # Convert application_port to integer if it's a string
            application_port = int(application_port)
            
            # Check if port is in valid range
            if application_port < 1 or application_port > 65535:
                return {
                    "is_notification": True,
                    "notification_type": "command_error",
                    "message_to_agent": f"Invalid application port: {application_port}. Port must be between 1 and 65535."
                }
        except (ValueError, TypeError):
            return {
                "is_notification": True,
                "notification_type": "command_error",
                "message_to_agent": f"Invalid application port: {application_port}. Must be a valid integer."
            }
            
        # Standardize port type
        port_type = type.lower() if type else "application"
        if port_type not in ["frontend", "backend", "application"]:
            port_type = "application"
    
    print(f"\n\nLocal Server Command: {command}")

    # Create command record in database
    cmd_record = await sync_to_async(lambda: (
        CommandExecution.objects.create(
            project_id=project_id,
            command=command,
            output=None  # Will update after execution
        )
    ))()

    success = False
    stdout = ""
    stderr = ""

    try:
        # Execute the server command locally using subprocess in thread pool (background)
        success, stdout, stderr = await asyncio.get_event_loop().run_in_executor(
            None, execute_local_server_command, command, str(workspace_path)
        )

        print(f"\n\nLocal Server Command output: {stdout}")
        if stderr:
            print(f"\n\nLocal Server Command stderr: {stderr}")

        # Update command record with output
        await sync_to_async(lambda: (
            setattr(cmd_record, 'output', stdout if success else stderr),
            cmd_record.save()
        )[1])()

    except Exception as e:
        error_msg = f"Failed to execute server command locally: {str(e)}"
        stderr = error_msg
        
        # Update command record with error
        await sync_to_async(lambda: (
            setattr(cmd_record, 'output', error_msg),
            cmd_record.save()
        )[1])()

    if not success:
        return {
            "is_notification": True,
            "notification_type": "command_error",
            "message_to_agent": f"{stderr}\n\nThe local server command execution failed. Stop generating further steps and inform the user that the command could not be executed.",
        }
    
    # Prepare success message with port information if applicable
    message = f"{stdout}\n\nLocal server command executed successfully."
    
    if application_port:
        # For local execution, the server will be accessible on localhost
        local_url = f"http://localhost:{application_port}"
        
        # Add URL information to the message
        message += f"\n\n{port_type.capitalize()} is running on port {application_port} locally."
        message += f"\nYou can access it at: {local_url}"
        message += f"\nServer logs are available at: {workspace_path}/tmp/server_output.log"
    else:
        message += f"\nServer logs are available at: {workspace_path}/tmp/server_output.log"
    
    return {
        "is_notification": True,
        "notification_type": "command_output",
        "message_to_agent": message + "\n\nProceed to next step",
    }
    