import json
import os
import asyncio
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from asgiref.sync import sync_to_async
from projects.models import Project, ProjectFeature, ProjectPersona, \
                            ProjectPRD, ProjectDesignSchema, ProjectChecklist, \
                            ProjectImplementation, ProjectFile
from development.utils.prd_functions import analyze_features, analyze_personas, \
                    design_schema
from development.models import ServerConfig

from django.conf import settings
from django.core.cache import cache
from development.k8s_manager.manage_pods import execute_command_in_pod

from development.models import KubernetesPod
from development.models import CommandExecution
from accounts.models import GitHubToken
from chat.models import Conversation

# Configure logger
logger = logging.getLogger(__name__)


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
        return await sync_to_async(Project.objects.get)(project_id=project_id)
    except Project.DoesNotExist:
        return None

async def get_project_with_relations(project_id, *relations):
    """Get project with select_related for avoiding additional queries"""
    try:
        return await sync_to_async(
            lambda: Project.objects.select_related(*relations).get(project_id=project_id)
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
    logger.info(f"Function name: {function_name}")
    logger.debug(f"Function args: {function_args}")

    # Validate project_id for most functions
    if function_name not in ["get_github_access_token", "web_search"] and project_id:
        error_response = validate_project_id(project_id)
        if error_response:
            return error_response

    match function_name:
        case "extract_features":
            return await extract_features(function_args, project_id, conversation_id)
        case "extract_personas":
            return await extract_personas(function_args, project_id, conversation_id)
        case "get_features":
            return await get_features(project_id)
        case "get_personas":
            return await get_personas(project_id)
        case "create_prd":
            return await create_prd(function_args, project_id)
        case "get_prd":
            return await get_prd(project_id)
        case "stream_prd_content":
            return await stream_prd_content(function_args, project_id)
        case "stream_implementation_content":
            return await stream_implementation_content(function_args, project_id)
        case "stream_document_content":
            return await stream_document_content(function_args, project_id)
        case "create_implementation":
            return await create_implementation(function_args, project_id)
        case "get_implementation":
            return await get_implementation(project_id)
        case "update_implementation":
            return await update_implementation(function_args, project_id)
        case "save_features":
            return await save_features(project_id)
        case "save_personas":
            return await save_personas(project_id)
        case "design_schema":
            return await save_design_schema(function_args, project_id)
        case "create_tickets":
            return await create_tickets(function_args, project_id)
        case "update_ticket":
            return await update_individual_checklist_ticket(project_id, function_args.get('ticket_id'), function_args.get('status'))
        case "get_pending_tickets":
            return await get_pending_tickets(project_id)
        case "get_next_ticket":
            return await get_next_ticket(project_id)
        
        case "execute_command":
            command = function_args.get('commands', '')
            logger.debug(f"Running command: {command}")
            if settings.ENVIRONMENT == "local":
                result = await run_command_locally(command, project_id=project_id, conversation_id=conversation_id)
            else:
                result = await run_command_in_k8s(command, project_id=project_id, conversation_id=conversation_id)
            return result
        
        case "start_server":
            command = function_args.get('start_server_command', '')
            application_port = function_args.get('application_port', '')
            type = function_args.get('type', '')
            logger.debug(f"Running server: {command}")
            if settings.ENVIRONMENT == "local":
                result = await run_server_locally(command, project_id=project_id, conversation_id=conversation_id, application_port=application_port, type=type)
            else:
                result = await server_command_in_k8s(command, project_id=project_id, conversation_id=conversation_id, application_port=application_port, type=type)
            return result
        
        case "start_server_local":
            command = function_args.get('start_server_command', '')
            application_port = function_args.get('application_port', '')
            type = function_args.get('type', '')
            logger.debug(f"Running local server: {command}")
            result = await run_server_locally(command, project_id=project_id, conversation_id=conversation_id, application_port=application_port, type=type)
            return result
        
        case "get_github_access_token":
            return await get_github_access_token(project_id=project_id, conversation_id=conversation_id)
        
        case "implement_ticket":
            ticket_id = function_args.get('ticket_id')
            ticket_details = function_args.get('ticket_details')
            logger.debug(f"Ticket details: {ticket_details}")
            implementation_plan = function_args.get('implementation_plan')
            return await implement_ticket(ticket_id, project_id, conversation_id, ticket_details, implementation_plan)
        
        case "copy_boilerplate_code":
            project_name = function_args.get('project_name')
            return await copy_boilerplate_code(project_id, project_name)
        
        case "capture_name":
            action = function_args.get('action')
            project_name = function_args.get('project_name')
            return await capture_name(action, project_name, project_id)
        
        case "web_search":
            query = function_args.get('query')
            logger.debug(f"Search Query: {query}")
            return await web_search(query, conversation_id)
        
        case "get_file_list":
            file_type = function_args.get('file_type', 'all')
            limit = function_args.get('limit', 10)
            return await get_file_list(project_id, file_type, limit)
        
        case "get_file_content":
            file_ids = function_args.get('file_ids') or function_args.get('file_id')  # Support both for backwards compatibility
            return await get_file_content(project_id, file_ids)

        # case "implement_ticket_async":
        #     ticket_id = function_args.get('ticket_id')
        #     return await implement_ticket_async(ticket_id, project_id, conversation_id)
        
        # case "execute_tickets_in_parallel":
        #     max_workers = function_args.get('max_workers', 3)
        #     return await execute_tickets_in_parallel(project_id, conversation_id, max_workers)
        
        # case "get_ticket_execution_status":
        #     task_id = function_args.get('task_id')
        #     return await get_ticket_execution_status(project_id, task_id)

    return None

# ============================================================================
# FEATURE FUNCTIONS
# ============================================================================

async def save_features(project_id):
    """
    Save the features from the PRD into a different list
    """
    logger.info("Save features function called ")
    
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
        # Check if project has PRD - get the most recent one
        try:
            latest_prd = await sync_to_async(
                lambda: ProjectPRD.objects.filter(project=project).order_by('-updated_at').first()
            )()
            if not latest_prd:
                raise ProjectPRD.DoesNotExist
            prd_content = latest_prd.prd
        except (ProjectPRD.DoesNotExist, AttributeError):
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

        logger.debug(f" New features: {new_features}")
    
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
        logger.error(f"Error saving features: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving features: {str(e)}"
        }

async def save_personas(project_id):
    """
    Save the personas from the PRD into a different list
    """
    logger.info("Save personas function called ")
    
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
        # Check if project has PRD - get the most recent one
        try:
            latest_prd = await sync_to_async(
                lambda: ProjectPRD.objects.filter(project=project).order_by('-updated_at').first()
            )()
            if not latest_prd:
                raise ProjectPRD.DoesNotExist
            prd_content = latest_prd.prd
        except (ProjectPRD.DoesNotExist, AttributeError):
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

        logger.debug(f" New personas: {new_personas}")
    
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
        logger.error(f"Error saving personas: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving personas: {str(e)}"
        }

async def extract_features(function_args, project_id, conversation_id=None):
    """
    Extract the features from the project into a different list and save them to the database
    """
    logger.info("Feature extraction function called ")
    
    # Import progress utility
    from coding.utils.progress_utils import send_tool_progress
    
    # Step 1: Start
    if conversation_id:
        await send_tool_progress(
            conversation_id, 
            "extract_features", 
            "Starting feature extraction...", 
            10
        )
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    validation_error = validate_function_args(function_args, ['features'])
    if validation_error:
        return validation_error
    
    # Step 2: Validate project
    if conversation_id:
        await send_tool_progress(
            conversation_id, 
            "extract_features", 
            "Validating project information...", 
            30
        )
    
    project = await get_project(project_id)
    if not project:
        if conversation_id:
            await send_tool_progress(
                conversation_id, 
                "extract_features", 
                f"Error: Project with ID {project_id} does not exist", 
                -1  # Error state
            )
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    features = function_args.get('features', [])
    
    if not isinstance(features, list):
        if conversation_id:
            await send_tool_progress(
                conversation_id, 
                "extract_features", 
                "Error: features must be a list", 
                -1  # Error state
            )
        return {
            "is_notification": False,
            "message_to_agent": "Error: features must be a list"
        }
    
    # Step 3: Extract and categorize features
    if conversation_id:
        await send_tool_progress(
            conversation_id, 
            "extract_features", 
            f"Processing {len(features)} features...", 
            60
        )
    
    try:
        # Step 4: Save to database
        if conversation_id:
            await send_tool_progress(
                conversation_id, 
                "extract_features", 
                "Saving features to project database...", 
                90
            )
        
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
        
        # Step 5: Complete
        if conversation_id:
            await send_tool_progress(
                conversation_id, 
                "extract_features", 
                f"Successfully saved {len(features)} features!", 
                100
            )
        
        return {
            "is_notification": True,
            "notification_type": "features",
            "message_to_agent": f"Features have been saved in the database"
        }
    except Exception as e:
        logger.error(f"Error saving features: {str(e)}")
        if conversation_id:
            await send_tool_progress(
                conversation_id, 
                "extract_features", 
                f"Error: {str(e)}", 
                -1  # Error state
            )
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving features: {str(e)}"
        }

async def extract_personas(function_args, project_id, conversation_id=None):
    """
    Extract the personas from the project and save them to the database
    """
    logger.info("Persona extraction function called ")
    
    # Import progress utility
    from coding.utils.progress_utils import send_tool_progress
    
    # Step 1: Start
    if conversation_id:
        await send_tool_progress(
            conversation_id, 
            "extract_personas", 
            "Starting persona extraction...", 
            10
        )
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    validation_error = validate_function_args(function_args, ['personas'])
    if validation_error:
        return validation_error
    
    # Step 2: Validate project
    if conversation_id:
        await send_tool_progress(
            conversation_id, 
            "extract_personas", 
            "Validating project information...", 
            30
        )
    
    project = await get_project(project_id)
    if not project:
        if conversation_id:
            await send_tool_progress(
                conversation_id, 
                "extract_personas", 
                f"Error: Project with ID {project_id} does not exist", 
                -1  # Error state
            )
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    personas = function_args.get('personas', [])
    
    if not isinstance(personas, list):
        if conversation_id:
            await send_tool_progress(
                conversation_id, 
                "extract_personas", 
                "Error: personas must be a list", 
                -1  # Error state
            )
        return {
            "is_notification": False,
            "message_to_agent": "Error: personas must be a list"
        }
    
    # Step 3: Extract and categorize personas
    if conversation_id:
        await send_tool_progress(
            conversation_id, 
            "extract_personas", 
            f"Processing {len(personas)} personas...", 
            60
        )
    
    try:
        # Step 4: Save to database
        if conversation_id:
            await send_tool_progress(
                conversation_id, 
                "extract_personas", 
                "Saving personas to project database...", 
                90
            )
        
        # Create new personas using async database operations
        await sync_to_async(lambda: [
            ProjectPersona.objects.create(
                project=project,
                name=persona.get('name', ''),
                role=persona.get('role', ''),
                description=persona.get('description', '')
            ) for persona in personas if isinstance(persona, dict)
        ])()
        
        # Step 5: Complete
        if conversation_id:
            await send_tool_progress(
                conversation_id, 
                "extract_personas", 
                f"Successfully saved {len(personas)} personas!", 
                100
            )
        
        return {
            "is_notification": True,
            "notification_type": "personas",
            "message_to_agent": f"Personas have been saved in the database"
        }
    except Exception as e:
        logger.error(f"Error saving personas: {str(e)}")
        if conversation_id:
            await send_tool_progress(
                conversation_id, 
                "extract_personas", 
                f"Error: {str(e)}", 
                -1  # Error state
            )
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving personas: {str(e)}"
        }

async def get_features(project_id):
    """
    Retrieve existing features for a project
    """
    logger.info("Get features function called ")
    
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
    logger.info("Get personas function called ")
    
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

async def create_prd(function_args, project_id):
    """
    Save the PRD for a project
    """
    logger.info(f"PRD saving function called : {function_args}")
    
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
    prd_name = function_args.get('prd_name', 'Main PRD')

    if not prd_content:
        return {
            "is_notification": False,
            "message_to_agent": "Error: PRD content cannot be empty"
        }

    logger.debug(f"\nPRD Name: {prd_name}")
    logger.debug(f"\nPRD Content: {prd_content}")

    try:
        # Save PRD to database with name
        created = await sync_to_async(lambda: (
            lambda: (
                lambda prd, created: created
            )(*ProjectPRD.objects.get_or_create(
                project=project, 
                name=prd_name,
                defaults={'prd': prd_content}
            ))
        )())()
        
        # Update existing PRD if it wasn't created
        if not created:
            await sync_to_async(lambda: (
                ProjectPRD.objects.filter(project=project, name=prd_name).update(prd=prd_content)
            ))()
        
        action = "created" if created else "updated"

        # Save features and personas
        await save_features(project_id)
        await save_personas(project_id)
        
        return {
            "is_notification": True,
            "notification_type": "prd",
            "message_to_agent": f"PRD '{prd_name}' {action} successfully in the database",
            "prd_name": prd_name
        }
        
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving PRD: {str(e)}"
        }

async def get_prd(project_id, prd_name=None):
    """
    Retrieve a specific PRD or all PRDs for a project
    """
    logger.info(f"Get PRD function called for project {project_id}, PRD name: {prd_name}")
    
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
        if prd_name:
            # Get specific PRD by name
            prd = await sync_to_async(
                lambda: ProjectPRD.objects.get(project=project, name=prd_name)
            )()
            return {
                "is_notification": True,
                "notification_type": "prd",
                "message_to_agent": f"Here is the PRD '{prd_name}': {prd.prd}. Please proceed with users request.",
                "prd_name": prd_name
            }
        else:
            # Get all PRDs for the project
            prds = await sync_to_async(
                lambda: list(ProjectPRD.objects.filter(project=project).values('name', 'created_at', 'updated_at'))
            )()
            
            if not prds:
                return {
                    "is_notification": False,
                    "message_to_agent": "No PRDs found for this project. Please create a PRD first."
                }
            
            # Get the most recent PRD content as well
            latest_prd = await sync_to_async(
                lambda: ProjectPRD.objects.filter(project=project).order_by('-updated_at').first()
            )()
            
            prd_list = "\n".join([f"- {prd['name']} (Created: {prd['created_at']}, Updated: {prd['updated_at']})" for prd in prds])
            
            return {
                "is_notification": True,
                "notification_type": "prd_list",
                "message_to_agent": f"Found {len(prds)} PRD(s) for this project:\n{prd_list}\n\nLatest PRD '{latest_prd.name}' content: {latest_prd.prd}",
                "prds": prds,
                "latest_prd_name": latest_prd.name
            }
    except ProjectPRD.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": f"No PRD with name '{prd_name}' found for this project." if prd_name else "No PRDs found for this project."
        }
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error retrieving PRD: {str(e)}"
        }

async def stream_prd_content(function_args, project_id):
    """
    Stream PRD content chunk by chunk as it's being generated
    This function is called multiple times during PRD generation to provide live updates
    """
    logger.info(f"Stream PRD content function called with args: {function_args}")
    logger.info(f"Project ID: {project_id}")
    
    error_response = validate_project_id(project_id)
    if error_response:
        logger.error(f"Project ID validation failed: {error_response}")
        return error_response
    
    validation_error = validate_function_args(function_args, ['content_chunk', 'is_complete'])
    if validation_error:
        logger.error(f"Function args validation failed: {validation_error}")
        return validation_error
    
    project = await get_project(project_id)
    if not project:
        logger.error(f"Project not found for ID: {project_id}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    content_chunk = function_args.get('content_chunk', '')
    is_complete = function_args.get('is_complete', False)
    prd_name = function_args.get('prd_name', 'Main PRD')
    
    logger.info(f"Streaming PRD chunk - Length: {len(content_chunk)}, Is Complete: {is_complete}")
    logger.info(f"First 100 chars of chunk: {content_chunk[:100]}...")
    
    # CONSOLE OUTPUT FOR DEBUGGING
    logger.info(f"PRD STREAM CHUNK - Project {project_id}", 
             extra={'easylogs_metadata': {
                 'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                 'length': len(content_chunk),
                 'complete': is_complete,
                 'project_id': project_id
             }})
    if content_chunk:
        logger.debug(f"Content Preview: {content_chunk[:200]}..." if len(content_chunk) > 200 else f"Content: {content_chunk}")
    
    # Create cache key for this project and PRD name
    cache_key = f"streaming_prd_content_{project_id}_{prd_name.replace(' ', '_')}"
    
    # Get existing content from cache or initialize
    existing_content = cache.get(cache_key, "")
    if not existing_content:
        logger.info(f"Initialized PRD content storage for project {project_id}")
    
    # Accumulate content
    if content_chunk:
        existing_content += content_chunk
        # Store updated content in cache with 1 hour timeout
        cache.set(cache_key, existing_content, timeout=3600)
        logger.info(f"Accumulated PRD content length: {len(existing_content)}")
    
    # If streaming is complete, save the PRD to database
    if is_complete:
        full_prd_content = cache.get(cache_key, "")
        logger.info(f"Streaming complete. Saving PRD with total length: {len(full_prd_content)}")
        
        # CONSOLE OUTPUT FOR COMPLETION
        logger.info(f"PRD STREAM COMPLETE - Project {project_id}",
                 extra={'easylogs_metadata': {
                     'total_length': len(full_prd_content),
                     'status': "saving_to_database",
                     'project_id': project_id
                 }})
        
        file_id = None
        if full_prd_content:
            try:
                # Save PRD to database with name
                created = await sync_to_async(lambda: (
                    lambda: (
                        lambda prd, created: created
                    )(*ProjectPRD.objects.get_or_create(
                        project=project, 
                        name=prd_name,
                        defaults={'prd': full_prd_content}
                    ))
                )())()
                
                # Update existing PRD if it wasn't created
                if not created:
                    await sync_to_async(lambda: (
                        ProjectPRD.objects.filter(project=project, name=prd_name).update(prd=full_prd_content)
                    ))()
                
                logger.info(f"PRD '{prd_name}' {'created' if created else 'updated'} successfully in database")
                
                # Save to ProjectFile and get the file_id
                try:
                    file_obj, file_created = await sync_to_async(
                        lambda: ProjectFile.objects.update_or_create(
                            project=project,
                            name=prd_name,
                            file_type='prd',
                            defaults={'content': full_prd_content}
                        )
                    )()
                    file_id = file_obj.id
                    logger.info(f"PRD saved to ProjectFile with ID: {file_id}")
                except Exception as e:
                    logger.error(f"Error saving PRD to ProjectFile: {str(e)}")
                
                # Clear the cache
                cache.delete(cache_key)
                
                # Also save features and personas
                # await save_features(project_id)
                # await save_personas(project_id)
                
            except Exception as e:
                logger.error(f"Error saving streamed PRD: {str(e)}")
                return {
                    "is_notification": True,
                    "notification_type": "prd_stream",
                    "content_chunk": "",
                    "is_complete": True,
                    "message_to_agent": f"PRD streaming complete but error saving: {str(e)}"
                }
    
    # Return notification to stream the chunk to frontend
    result = {
        "is_notification": True,
        "notification_type": "prd_stream",
        "content_chunk": content_chunk,
        "is_complete": is_complete,
        "prd_name": prd_name,
        "message_to_agent": f"PRD '{prd_name}' content chunk streamed" if not is_complete else f"PRD '{prd_name}' streaming complete and saved"
    }
    
    # Add file_id to result if streaming is complete and we have a file_id
    if is_complete and file_id:
        result["file_id"] = file_id
        logger.info(f"[PRD_STREAM] Including file_id {file_id} in completion notification")
    elif is_complete:
        logger.warning(f"[PRD_STREAM] Completion notification but no file_id available")
    
    logger.info(f"[PRD_STREAM] Returning stream result: is_complete={is_complete}, has_file_id={'file_id' in result}, keys={list(result.keys())}")
    return result

async def create_implementation(function_args, project_id):
    """
    Save the implementation for a project
    """
    logger.info(f"Implementation saving function called : {function_args}")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    validation_error = validate_function_args(function_args, ['implementation'])
    if validation_error:
        return validation_error
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    implementation_content = function_args.get('implementation', '')

    if not implementation_content:
        return {
            "is_notification": False,
            "message_to_agent": "Error: PRD content cannot be empty"
        }

    logger.debug(f"\nImplementation Content: {implementation_content}")

    try:
        # Save PRD to database
        created = await sync_to_async(lambda: (
            lambda: (
                lambda prd, created: created
            )(*ProjectImplementation.objects.get_or_create(project=project, defaults={'implementation': implementation_content}))
        )())()
        
        # Update existing PRD if it wasn't created
        if not created:
            await sync_to_async(lambda: (
                ProjectImplementation.objects.filter(project=project).update(implementation=implementation_content)
            ))()
        
        action = "created" if created else "updated"
        
        return {
            "is_notification": True,
            "notification_type": "implementation",
            "message_to_agent": f"Implementation {action} successfully in the database"
        }
        
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving Implementation: {str(e)}"
        }

async def get_implementation(project_id):
    """
    Retrieve the Implementation for a project
    """
    logger.info("Get Implementation function called ")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required to retrieve Implementation"
        }
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    try:
        # Check if project has PRD and get content
        implementation_content = await sync_to_async(lambda: project.implementation.implementation)()
        return {
            "is_notification": True,
            "notification_type": "implementation",
            "message_to_agent": f"Here is the existing version of the Implementation: {implementation_content}. Proceed with user's request."
        }
    except ProjectImplementation.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": "No Implementation found for this project. Please create a Implementation first."
        }
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error retrieving Implementation: {str(e)}"
        }

async def update_implementation(function_args, project_id):
    """
    Update the implementation for a project by adding new sections or modifications
    """
    logger.info(f"Update Implementation function called : {function_args}")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    validation_error = validate_function_args(function_args, ['update_type', 'update_content', 'update_summary'])
    if validation_error:
        return validation_error
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    update_type = function_args.get('update_type', '')
    update_content = function_args.get('update_content', '')
    update_summary = function_args.get('update_summary', '')

    if not update_content:
        return {
            "is_notification": False,
            "message_to_agent": "Error: Update content cannot be empty"
        }

    logger.debug(f"\nUpdate Type: {update_type}")
    logger.debug(f"Update Summary: {update_summary}")

    try:
        # Get existing implementation or create new one
        try:
            implementation = await sync_to_async(lambda: project.implementation)()
            existing_content = implementation.implementation
        except ProjectImplementation.DoesNotExist:
            # Create new implementation if it doesn't exist
            implementation = await sync_to_async(ProjectImplementation.objects.create)(
                project=project,
                implementation=""
            )
            existing_content = ""
        
        # Format the update based on type
        from datetime import datetime
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        if update_type == "complete_rewrite":
            # Replace entire document
            new_content = update_content
            action = "completely rewritten"
        else:
            # Add update to the top of the document
            update_header = f"""# Implementation Update - {timestamp}
**Update Type:** {update_type.replace('_', ' ').title()}
**Summary:** {update_summary}

---

{update_content}

---

# Previous Implementation Content
"""
            if existing_content:
                new_content = update_header + "\n" + existing_content
            else:
                new_content = update_header + "\n(No previous implementation content)"
            
            action = "updated with new " + ("additions" if update_type == "addition" else "modifications")
        
        # Save the updated implementation
        await sync_to_async(lambda: (
            setattr(implementation, 'implementation', new_content),
            implementation.save()
        )[1])()
        
        return {
            "is_notification": True,
            "notification_type": "implementation",
            "message_to_agent": f"Implementation {action} successfully. The update has been added to the document with timestamp {timestamp}."
        }
        
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error updating Implementation: {str(e)}"
        }

async def stream_implementation_content(function_args, project_id):
    """
    Stream Implementation content chunk by chunk as it's being generated
    This function is called multiple times during Implementation generation to provide live updates
    """
    logger.info(f"Stream Implementation content function called with args: {function_args}")
    logger.info(f"Project ID: {project_id}")
    
    error_response = validate_project_id(project_id)
    if error_response:
        logger.error(f"Project ID validation failed: {error_response}")
        return error_response
    
    validation_error = validate_function_args(function_args, ['content_chunk', 'is_complete'])
    if validation_error:
        logger.error(f"Function args validation failed: {validation_error}")
        return validation_error
    
    project = await get_project(project_id)
    if not project:
        logger.error(f"Project not found for ID: {project_id}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    content_chunk = function_args.get('content_chunk', '')
    is_complete = function_args.get('is_complete', False)
    
    logger.info(f"Streaming Implementation chunk - Length: {len(content_chunk)}, Is Complete: {is_complete}")
    logger.info(f"First 100 chars of chunk: {content_chunk[:100]}...")
    
    # CONSOLE OUTPUT FOR DEBUGGING
    logger.info(f"IMPLEMENTATION STREAM CHUNK - Project {project_id}",
             extra={'easylogs_metadata': {
                 'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                 'length': len(content_chunk),
                 'complete': is_complete,
                 'project_id': project_id
             }})
    if content_chunk:
        logger.debug(f"Content Preview: {content_chunk[:200]}..." if len(content_chunk) > 200 else f"Content: {content_chunk}")
    
    # Create cache key for this project
    cache_key = f"streaming_implementation_content_{project_id}"
    
    # Get existing content from cache or initialize
    existing_content = cache.get(cache_key, "")
    if not existing_content:
        logger.info(f"Initialized Implementation content storage for project {project_id}")
    
    # Accumulate content
    if content_chunk:
        existing_content += content_chunk
        # Store updated content in cache with 1 hour timeout
        cache.set(cache_key, existing_content, timeout=3600)
        logger.info(f"Accumulated Implementation content length: {len(existing_content)}")
    
    # If streaming is complete, save the Implementation to database
    if is_complete:
        full_implementation_content = cache.get(cache_key, "")
        logger.info(f"Streaming complete. Saving Implementation with total length: {len(full_implementation_content)}")
        
        # CONSOLE OUTPUT FOR COMPLETION
        logger.info(f"IMPLEMENTATION STREAM COMPLETE - Project {project_id}",
                 extra={'easylogs_metadata': {
                     'total_length': len(full_implementation_content),
                     'status': "saving_to_database",
                     'project_id': project_id
                 }})
        
        file_id = None
        if full_implementation_content:
            try:
                # Save Implementation to database
                created = await sync_to_async(lambda: (
                    lambda: (
                        lambda implementation, created: created
                    )(*ProjectImplementation.objects.get_or_create(project=project, defaults={'implementation': full_implementation_content}))
                )())()
                
                # Update existing Implementation if it wasn't created
                if not created:
                    await sync_to_async(lambda: (
                        ProjectImplementation.objects.filter(project=project).update(implementation=full_implementation_content)
                    ))()
                
                logger.info(f"Implementation {'created' if created else 'updated'} successfully in database")
                
                # Save to ProjectFile and get the file_id
                try:
                    file_obj, file_created = await sync_to_async(
                        lambda: ProjectFile.objects.update_or_create(
                            project=project,
                            name='Implementation Plan',
                            file_type='implementation',
                            defaults={'content': full_implementation_content}
                        )
                    )()
                    file_id = file_obj.id
                    logger.info(f"Implementation saved to ProjectFile with ID: {file_id}")
                except Exception as e:
                    logger.error(f"Error saving Implementation to ProjectFile: {str(e)}")
                
                # Clear the cache
                cache.delete(cache_key)
                
            except Exception as e:
                logger.error(f"Error saving streamed Implementation: {str(e)}")
                return {
                    "is_notification": True,
                    "notification_type": "implementation_stream",
                    "content_chunk": "",
                    "is_complete": True,
                    "message_to_agent": f"Implementation streaming complete but error saving: {str(e)}"
                }
    
    # Return notification to stream the chunk to frontend
    result = {
        "is_notification": True,
        "notification_type": "implementation_stream",
        "content_chunk": content_chunk,
        "is_complete": is_complete,
        "message_to_agent": "Implementation content chunk streamed" if not is_complete else "Implementation streaming complete and saved"
    }
    
    # Add file_id to result if streaming is complete and we have a file_id
    if is_complete and file_id:
        result["file_id"] = file_id
        logger.info(f"[IMPLEMENTATION_STREAM] Including file_id {file_id} in completion notification")
    elif is_complete:
        logger.warning(f"[IMPLEMENTATION_STREAM] Completion notification but no file_id available")
    
    logger.info(f"[IMPLEMENTATION_STREAM] Returning stream result: is_complete={is_complete}, has_file_id={'file_id' in result}, keys={list(result.keys())}")
    return result

async def stream_document_content(function_args, project_id):
    """
    Stream generic document content chunk by chunk as it's being generated
    This function is called multiple times during document generation to provide live updates
    Supports any document type including competitor analysis, market research, etc.
    """
    logger.info(f"Stream document content function called with args: {function_args}")
    logger.info(f"Project ID: {project_id}")
    
    error_response = validate_project_id(project_id)
    if error_response:
        logger.error(f"Project ID validation failed: {error_response}")
        return error_response
    
    validation_error = validate_function_args(function_args, ['content_chunk', 'is_complete', 'document_type', 'document_name'])
    if validation_error:
        logger.error(f"Function args validation failed: {validation_error}")
        return validation_error
    
    project = await get_project(project_id)
    if not project:
        logger.error(f"Project not found for ID: {project_id}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    content_chunk = function_args.get('content_chunk', '')
    is_complete = function_args.get('is_complete', False)
    document_type = function_args.get('document_type', 'document')
    document_name = function_args.get('document_name', 'Document')
    
    logger.info(f"Streaming {document_type} chunk - Length: {len(content_chunk)}, Is Complete: {is_complete}, Name: {document_name}")
    logger.info(f"First 100 chars of chunk: {content_chunk[:100]}...")
    
    # CONSOLE OUTPUT FOR DEBUGGING
    logger.info(f"DOCUMENT STREAM CHUNK - Project {project_id} - Type: {document_type}",
             extra={'easylogs_metadata': {
                 'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                 'length': len(content_chunk),
                 'complete': is_complete,
                 'project_id': project_id,
                 'document_type': document_type,
                 'document_name': document_name
             }})
    if content_chunk:
        logger.debug(f"Content Preview: {content_chunk[:200]}..." if len(content_chunk) > 200 else f"Content: {content_chunk}")
    
    # Create cache key for this project and document
    cache_key = f"streaming_document_content_{project_id}_{document_type}_{document_name.replace(' ', '_')}"
    
    # Get existing content from cache or initialize
    existing_content = cache.get(cache_key, "")
    if not existing_content:
        logger.info(f"Initialized document content storage for project {project_id}, type: {document_type}")
    
    # Accumulate content
    if content_chunk:
        existing_content += content_chunk
        # Store updated content in cache with 1 hour timeout
        cache.set(cache_key, existing_content, timeout=3600)
        logger.info(f"Accumulated document content length: {len(existing_content)}")
    
    # If streaming is complete, save the document to database
    file_id = None
    if is_complete:
        full_document_content = cache.get(cache_key, "")
        logger.info(f"Streaming complete. Saving document with total length: {len(full_document_content)}")
        
        # CONSOLE OUTPUT FOR COMPLETION
        logger.info(f"DOCUMENT STREAM COMPLETE - Project {project_id} - Type: {document_type}",
                 extra={'easylogs_metadata': {
                     'total_length': len(full_document_content),
                     'status': "saving_to_database",
                     'project_id': project_id,
                     'document_type': document_type
                 }})
        
        if full_document_content:
            try:
                # Save to ProjectFile
                file_obj, file_created = await sync_to_async(
                    lambda: ProjectFile.objects.update_or_create(
                        project=project,
                        name=document_name,
                        file_type=document_type,
                        defaults={
                            'content': full_document_content,
                            'mime_type': 'text/markdown'
                        }
                    )
                )()
                
                file_id = file_obj.id
                logger.info(f"Document file {'created' if file_created else 'updated'} with ID: {file_id}")
                
                # Clear the cache
                cache.delete(cache_key)
                logger.info(f"Cleared cache for document stream: {cache_key}")
                
            except Exception as e:
                logger.error(f"Error saving document to database: {str(e)}", exc_info=True)
                # Don't fail the stream, just log the error
    
    # Build the result for streaming notification
    result = {
        "is_notification": True,
        "notification_type": "file_stream",
        "content_chunk": content_chunk,
        "is_complete": is_complete,
        "file_type": document_type,
        "file_name": document_name
    }
    
    # Add file_id to result if streaming is complete and we have a file_id
    if is_complete and file_id:
        result["file_id"] = file_id
        logger.info(f"[DOCUMENT_STREAM] Including file_id {file_id} in completion notification")
    elif is_complete:
        logger.warning(f"[DOCUMENT_STREAM] Completion notification but no file_id available")
    
    logger.info(f"[DOCUMENT_STREAM] Returning stream result: is_complete={is_complete}, has_file_id={'file_id' in result}, keys={list(result.keys())}")
    return result

async def save_design_schema(function_args, project_id):
    """
    Save the design schema for a project
    """
    logger.info("Save design schema function called ")
    
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
        # Check if project has PRD - get the most recent one
        try:
            latest_prd = await sync_to_async(
                lambda: ProjectPRD.objects.filter(project=project).order_by('-updated_at').first()
            )()
            if not latest_prd:
                raise ProjectPRD.DoesNotExist
            prd_content = latest_prd.prd
        except (ProjectPRD.DoesNotExist, AttributeError):
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

async def create_tickets(function_args, project_id):
    """
    Generate checklist tickets for a project
    """
    logger.info("Checklist tickets function called ")
    
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
        # Create tickets with enhanced details
        created_tickets = []
        for ticket in checklist_tickets:
            if isinstance(ticket, dict):
                # Extract details from the ticket
                details = ticket.get('details', {})
                
                new_ticket = await sync_to_async(ProjectChecklist.objects.create)(
                    project=project,
                    name=ticket.get('name', ''),
                    description=ticket.get('description', ''),
                    priority=ticket.get('priority', 'Medium'),
                    status='open',
                    role=ticket.get('role', 'agent'),
                    # Enhanced fields
                    # details=details,
                    ui_requirements=ticket.get('ui_requirements', {}),
                    component_specs=ticket.get('component_specs', {}),
                    acceptance_criteria=ticket.get('acceptance_criteria', []),
                    dependencies=ticket.get('dependencies', []),
                    # complexity=details.get('complexity', 'medium'),
                    # requires_worktree=details.get('requires_worktree', True)
                )
                created_tickets.append(new_ticket.id)
        
        return {
            "is_notification": True,
            "notification_type": "create_tickets",
            "message_to_agent": f"Successfully created {len(created_tickets)} detailed tickets with design specifications"
        }
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error creating checklist tickets: {str(e)}"
        }

async def get_next_ticket(project_id):
    """
    Get the latest ticket for a project
    """
    logger.info("Get pending tickets function called ")

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
    logger.debug(f"Pending ticket ID: {pending_ticket.id if pending_ticket else None}")

    if pending_ticket:
        # Access the fields directly without triggering related queries
        message_to_agent = f"Pending ticket: \nTicket Id: {pending_ticket.id}, \nTicket Name: {pending_ticket.name},\
              \nTicket Description: {pending_ticket.description}, \nTicket Priority: {pending_ticket.priority}. Build this ticket first."
    else:
        message_to_agent = "No pending tickets found"

    logger.debug(f"Message to agent: {message_to_agent}")

    return {
        "is_notification": True,
        "notification_type": "get_pending_tickets",
        "message_to_agent": message_to_agent
    }

async def update_individual_checklist_ticket(project_id, ticket_id, status):
    """
    Update an individual checklist ticket for a project
    """
    logger.info("Update individual checklist ticket function called ")
    logger.debug(f"Ticket ID: {ticket_id} and status: {status}")
    
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

        logger.info(f"Checklist ticket {ticket_id} has been successfully updated in the database. Proceed to next checklist item, unless otherwise specified by the user")

        return {
            "is_notification": True,
            "notification_type": "create_tickets",
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
    logger.info("Get pending tickets function called ")

    error_response = validate_project_id(project_id)
    if error_response:
        return error_response

    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    project_tickets = await sync_to_async(
        lambda: list(ProjectChecklist.objects.filter(project=project, status='open', role='agent').values('id', 'name', 'description', 'status', 'priority'))
    )()

    if project_tickets:
        # Format all pending tickets with their details
        ticket_details = []
        for ticket in project_tickets:
            ticket_details.append(
                f"Ticket ID: {ticket['id']}, Name: {ticket['name']}, "
                f"Description: {ticket['description']}, Status: {ticket['status']}, "
                f"Priority: {ticket['priority']}"
            )
        message_content = "\n".join(ticket_details)
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
    logger.debug(f"Command: {command_to_run}")

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

        logger.debug(f"Command output: {stdout}")

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
            "message_to_agent": f"{stderr}The command execution failed. Stop generating further steps and inform the user that the command could not be executed.",
        }
    
    return {
        "is_notification": True,
        "notification_type": "command_output", 
        "message_to_agent": f"Command output: {stdout}Fix if there is any error, otherwise you can proceed to next step",
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
    from development.k8s_manager.manage_pods import execute_command_in_pod, get_k8s_api_client
    from coding.models import KubernetesPod, KubernetesPortMapping
    from kubernetes import client as k8s_client
    from kubernetes.client.rest import ApiException

    logger.debug(f"Application port: {application_port}")
    logger.debug(f"Type: {type}")

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
            logger.debug(f"Using existing port mapping for {port_type} port {application_port}")
            node_port = existing_mapping.node_port
        else:
            # Need to add port to service and create mapping using Kubernetes API
            logger.debug(f"Creating new port mapping for {port_type} port {application_port}")
            
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
                    logger.debug(f"Port {application_port} already exists in service with nodePort {node_port}")
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
                    
                    logger.debug(f"Kubernetes assigned nodePort {node_port} for {port_type} port {application_port}")
                
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
                    logger.warning(f"Could not get node IP: {e}")
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
    logger.debug(f"Command: {full_command}")

    # Execute the command using the Kubernetes API function in thread pool
    success, stdout, stderr = await asyncio.get_event_loop().run_in_executor(
        None, execute_command_in_pod, project_id, conversation_id, full_command
    )
    
    logger.debug(f"Command output: {stdout}")

    if not success:
        return {
            "is_notification": True,
            "notification_type": "command_error",
            "message_to_agent": f"{stderr}The command execution failed. Stop generating further steps and inform the user that the command could not be executed.",
        }
    
    # Prepare success message with port information if applicable
    message = f"{stdout}Command to run server is successful."
    
    if application_port:
        # Get the pod's service details
        service_details = pod.service_details or {}
        node_ip = service_details.get('nodeIP', 'localhost')
        
        # Add URL information to the message
        message += f"{port_type.capitalize()} is running on port {application_port} inside the container."
        message += f"\nYou can access it at: [http://{node_ip}:{node_port}](http://{node_ip}:{node_port})"
    
    return {
        "is_notification": True,
        "notification_type": "command_output",
        "message_to_agent": message + "Proceed to next step",
    }

async def run_command_locally(command: str, project_id: int | str = None, conversation_id: int | str = None) -> dict:
    """
    Run a command in the local terminal using subprocess.
    Creates a local workspace directory if it doesn't exist.
    """
    project = await get_project(project_id)
    # Create workspace directory if it doesn't exist
    workspace_path = Path.home() / "LFG" / "workspace" / project.name
    workspace_path.mkdir(parents=True, exist_ok=True)
    
    command_to_run = f"cd {workspace_path} && {command}"
    logger.debug(f"Local Command: {command_to_run}")

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

        logger.debug(f"Local Command output: {stdout}")
        if stderr:
            logger.warning(f"Local Command stderr: {stderr}")

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
            "message_to_agent": f"{stderr}The local command execution failed. Stop generating further steps and inform the user that the command could not be executed.",
        }
    
    return {
        "is_notification": True,
        "notification_type": "command_output", 
        "message_to_agent": f"Local command output: {stdout}Fix if there is any error, otherwise you can proceed to next step",
    }

# Updated run_server_locally function
async def run_server_locally(command: str, project_id: int | str = None, 
                           conversation_id: int | str = None, 
                           application_port: int | str = None, 
                           type: str = None) -> dict:
    """
    Run a server command locally in background.
    """
    logger.debug(f"Local Application port: {application_port}")
    logger.debug(f"Local Type: {type}")

    # Create workspace directory if it doesn't exist
    workspace_path = Path.home() / "LFG" / "workspace"
    workspace_path.mkdir(parents=True, exist_ok=True)
    
    # Validate port
    if not application_port:
        return {
            "is_notification": True,
            "notification_type": "command_error",
            "message_to_agent": "Port is required to run a server."
        }
    
    try:
        application_port = int(application_port)
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
    
    # 1. Save server config to database
    await sync_to_async(lambda: ServerConfig.objects.update_or_create(
        project_id=project_id,
        port=application_port,
        defaults={
            'command': command,
            'start_server_command': command,
            'type': type or 'application'
        }
    ))()
    
    # 2. Check if server is running on the port and kill it
    kill_command = f"lsof -ti:{application_port} | xargs kill -9 2>/dev/null || true"
    success, stdout, stderr = execute_local_command(kill_command, str(workspace_path))
    logger.info(f"Killed existing process on port {application_port}")
    
    # Wait a moment for port to be freed
    await asyncio.sleep(1)
    
    # 3. Run the server command in background using nohup
    # Create a log file for the server
    log_file = workspace_path / f"server_{project_id}_{application_port}.log"
    
    # Use nohup to run in background and redirect output to log file
    background_command = f"nohup {command} > {log_file} 2>&1 &"
    
    success, stdout, stderr = execute_local_command(background_command, str(workspace_path))
    
    if not success:
        return {
            "is_notification": True,
            "notification_type": "command_error",
            "message_to_agent": f"Failed to start server: {stderr}"
        }
    
    # 4. Wait a bit for server to start
    await asyncio.sleep(3)
    
    # 5. Check if server is running by checking if port is listening
    check_command = f"lsof -i:{application_port} | grep LISTEN"
    success, stdout, stderr = execute_local_command(check_command, str(workspace_path))
    
    if success and stdout:
        # Server is running
        return {
            "is_notification": True,
            "notification_type": "server_started",
            "message_to_agent": f"✅ Server started successfully!"
                               f"📍 Running on port {application_port}\n"
                               f"🔗 URL: [http://localhost:{application_port}](http://localhost:{application_port})\n"
                               f"📄 Logs: {log_file}"
                               f"The server is running in the background. Proceed with next steps.\n"
                               f"To view logs: tail -f {log_file}"
        }
    else:
        # Check logs for errors
        try:
            with open(log_file, 'r') as f:
                log_content = f.read()
                last_lines = '\n'.join(log_content.split('\n')[-20:])
        except:
            last_lines = "Could not read log file"
        
        return {
            "is_notification": True,
            "notification_type": "server_error",
            "message_to_agent": f"⚠️ Server may not have started properly."
                               f"Recent logs:\n```\n{last_lines}\n```"
                               f"Please check the logs and fix any issues."
        }


# Simple helper function to stop a server
async def stop_server(project_id: int, port: int) -> dict:
    """Stop a server running on a specific port"""
    workspace_path = Path.home() / "LFG" / "workspace"
    
    kill_command = f"lsof -ti:{port} | xargs kill -9 2>/dev/null || true"
    success, stdout, stderr = execute_local_command(kill_command, str(workspace_path))
    
    return {
        "is_notification": True,
        "notification_type": "server_stopped",
        "message_to_agent": f"Server on port {port} has been stopped."
    }


# Function to restart server (can be called from a button)
async def restart_server_from_config(project_id: int) -> dict:
    """Restart all servers for a project using saved config"""
    
    configs = await sync_to_async(list)(
        ServerConfig.objects.filter(project_id=project_id)
    )
    
    results = []
    for config in configs:
        # Use start_server_command if available, otherwise fall back to command
        server_command = config.start_server_command or config.command
        result = await run_server_locally(
            command=server_command,
            project_id=project_id,
            application_port=config.port,
            type=config.type
        )
        # results.append(f"Port {config.port}: {result['message_to_agent'].split('\\n')[0]}")
        results.append(result['message_to_agent'])
    
    return {
        "is_notification": True,
        "notification_type": "servers_restarted",
        "message_to_agent": "\n".join(results)
    }

async def copy_boilerplate_code(project_id, project_name):
    """Copy the boilerplate code from the project"""
    logger.info("Copy boilerplate code function called ")
    logger.debug(f"Project name: {project_name}")
    
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
        # Use provided_name if available, otherwise use the passed project_name
        folder_name = project.provided_name if project.provided_name else project_name
        
        # Define source and destination paths
        source_path = os.path.join(os.getcwd(), "boilerplate", "lfg-template")
        dest_path = os.path.join(os.path.expanduser("~"), "LFG", "workspace", folder_name)
        logger.debug(f"Source path: {source_path}")
        logger.debug(f"Destination path: {dest_path}")
        
        # Create destination directory if it doesn't exist
        os.makedirs(dest_path, exist_ok=True)
        
        # Copy files using shutil
        import shutil
        shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
        
        # Initialize git repository if not already initialized
        if not os.path.exists(os.path.join(dest_path, ".git")):
            subprocess.run(["git", "init"], cwd=dest_path, check=True)
            
            # Create initial commit
            subprocess.run(["git", "add", "."], cwd=dest_path, check=True)
            subprocess.run(["git", "commit", "-m", "Initial commit: Copy boilerplate code"], cwd=dest_path, check=True)
        
        return {
            "is_notification": True,
            "notification_type": "boilerplate_code_copied",
            "message_to_agent": f"Boilerplate code has been successfully copied to ~/LFG/workspace/{folder_name}. The project has been initialized with git."
        }
    except Exception as e:
        logger.error(f"Error copying boilerplate code: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error copying boilerplate code: {str(e)}"
        }

async def capture_name(action, project_name, project_id):
    """
    Save or retrieve the project name
    """
    logger.info(f"Capture name function called with action: {action}, project_name: {project_name}")
    
    if action == "save":
        return await save_project_name(project_name, project_id)
    elif action == "get":
        return await get_project_name(project_id)
    else:
        return {
            "is_notification": False,
            "message_to_agent": "Error: Invalid action. Must be 'save' or 'get'"
        }

async def save_project_name(project_name, project_id):
    """
    Save the project name to the project model
    """
    logger.info(f"Save project name function called: {project_name}")
    
    if not project_name:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_name is required when action is 'save'"
        }
    
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
        # Update the provided_name field with user-confirmed name
        await sync_to_async(lambda: (
            setattr(project, 'provided_name', project_name),
            project.save()
        )[1])()
        
        return {
            "is_notification": True,
            "notification_type": "project_name_saved",
            "message_to_agent": f"Project name '{project_name}' has been saved successfully as provided_name"
        }
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving project name: {str(e)}"
        }

async def get_project_name(project_id):
    """
    Retrieve the project name from the project model
    """
    logger.info(f"Get project name function called for project_id: {project_id}")
    
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
        if project.provided_name:
            return {
                "is_notification": True,
                "notification_type": "project_name_retrieved",
                "message_to_agent": f"Project name is: {project.provided_name}"
            }
        else:
            current_project_name = project.name.replace(' ', '-').lower()
            # Remove all special characters except alphanumeric and dashes
            import re
            current_project_name = re.sub(r'[^a-z0-9-]', '', current_project_name)
            return {
                "is_notification": True,
                "notification_type": "project_name_not_confirmed",
                "message_to_agent": f"Ask the user if they wish to use the name. You can ask user if they want to save this name: '{current_project_name}'? Do not proceed until user responds."
            }
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error retrieving project name: {str(e)}"
        }

async def implement_ticket(ticket_id, project_id, conversation_id, ticket_details, implementation_plan):
    """
    Implement a specific ticket with all its requirements
    Returns a special marker that indicates this tool should stream its implementation
    """
    try:
        logger.debug(f"\nTicket details: {ticket_details}")
        
        # Extract key details
        ticket_name = ticket_details.get('name', 'Unknown')
        project_name = ticket_details.get('project_name', 'Unknown')
        requires_worktree = ticket_details.get('details', {}).get('requires_worktree', False)
        
        # Instead of executing here, return a special response that tells the system
        # to create a streaming implementation
        return {
            "is_streaming_tool": True,
            "tool_name": "implement_ticket",
            "streaming_config": {
                "ticket_id": ticket_id,
                "ticket_name": ticket_name,
                "project_name": project_name,
                "requires_worktree": requires_worktree,
                "ticket_details": ticket_details,
                "implementation_plan": implementation_plan
            },
            "message_to_agent": f"I'll now implement ticket #{ticket_id}: {ticket_name}. Let me work through this step by step..."
        }
        
    except Exception as e:
        logger.error(f"Error setting up ticket implementation {ticket_id}: {str(e)}")
        return {
            "is_notification": True,
            "notification_type": "ticket_error",
            "message_to_agent": f"Error setting up ticket implementation {ticket_id}: {str(e)}",
            "error": str(e)
        }

async def save_file_from_stream(file_content, project_id, file_type, file_name):
    """
    Save file content that was captured from the streaming response.
    This function is called from streaming_handlers.py when file generation is complete.
    
    Args:
        file_content: The complete file content captured from streaming
        project_id: The project ID to save the file for
        file_type: Type of file (prd, implementation, design, test, etc.)
        file_name: Name of the file
        
    Returns:
        Dict with notification data
    """
    logger.info(f"Saving file from stream for project {project_id}")
    logger.info(f"File type: {file_type}, Name: {file_name}, Size: {len(file_content)} characters")
    
    # Validate project ID
    if not project_id:
        logger.error("No project_id provided")
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required"
        }
    
    # Get the project
    try:
        project = await get_project(project_id)
        if not project:
            logger.error(f"Project with ID {project_id} not found")
            return {
                "is_notification": False,
                "message_to_agent": f"Error: Project with ID {project_id} does not exist"
            }
    except Exception as e:
        logger.error(f"Error fetching project: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error fetching project: {str(e)}"
        }
    
    # Validate file content
    if not file_content or not file_content.strip():
        logger.error("File content is empty")
        return {
            "is_notification": False,
            "message_to_agent": "Error: File content cannot be empty"
        }
    
    # Clean up any residual artifacts
    file_content = file_content.strip()
    
    # Remove leading '>' if present
    if file_content.startswith('>'):
        file_content = file_content[1:].strip()
    
    # Remove any trailing tag fragments
    if '</lfg-file' in file_content:
        file_content = file_content[:file_content.rfind('</lfg-file')].strip()
    
    # Remove opening tag if it somehow got included
    if '<lfg-file' in file_content:
        import re
        file_content = re.sub(r'<lfg-file[^>]*>', '', file_content, count=1).lstrip()
    
    try:
        # Save file to database
        file_obj, created = await sync_to_async(
            ProjectFile.objects.get_or_create
        )(
            project=project,
            name=file_name,
            file_type=file_type,
            defaults={}  # Don't set content in defaults
        )
        
        # Save content using the model's save_content method
        await sync_to_async(file_obj.save_content)(file_content)
        await sync_to_async(file_obj.save)()
        
        if not created:
            logger.info(f"Updated existing {file_type} file '{file_name}' for project {project_id}")
        else:
            logger.info(f"Created new {file_type} file '{file_name}' for project {project_id}")
        
        action = "created" if created else "updated"
        
        # Get display name for notification
        file_type_display = {
            'prd': 'PRD',
            'implementation': 'Implementation',
            'design': 'Design Document',
            'test': 'Test Plan'
        }.get(file_type, 'File')
        
        logger.info(f"Returning notification with file_id: {file_obj.id}")
        logger.info(f"[SAVE NOTIFICATION] Type: {file_type}, Name: {file_name}, ID: {file_obj.id}")
        
        notification = {
            "is_notification": True,
            "notification_type": "file_saved",  # Use a generic notification type for all saved files
            "message_to_agent": f"{file_type_display} '{file_name}' {action} successfully in the database",
            "file_name": file_name,
            "file_type": file_type,
            "file_id": file_obj.id,
            "project_id": str(project.project_id) if project else None,  # Include project_id
            "notification_marker": "__NOTIFICATION__"  # Add this marker
        }
        
        logger.info(f"[SAVE NOTIFICATION] Full notification data: {notification}")
        return notification
        
    except Exception as e:
        logger.error(f"Error saving file: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving file: {str(e)}"
        }

async def edit_file_content(file_id, edit_operations, project_id):
    """
    Edit an existing file with specified operations
    
    Args:
        file_id: The ID of the file to edit
        edit_operations: List of edit operations to apply
        project_id: The project ID
    
    Returns:
        Dict with operation result
    """
    logger.info(f"[edit_file_content] Starting edit for file {file_id} with {len(edit_operations)} operations")
    logger.info(f"[edit_file_content] Project ID: {project_id}")
    
    # Validate inputs
    if not file_id:
        return {
            "is_notification": False,
            "message_to_agent": "Error: file_id is required for editing"
        }
    
    if not edit_operations or not isinstance(edit_operations, list):
        return {
            "is_notification": False,
            "message_to_agent": "Error: edit_operations must be a non-empty list"
        }
    
    # Get the file
    try:
        logger.info(f"[edit_file_content] Fetching file with ID {file_id} from project {project_id}")
        file_obj = await sync_to_async(
            ProjectFile.objects.get
        )(id=file_id, project_id=project_id)
        logger.info(f"[edit_file_content] Found file: {file_obj.name} (Type: {file_obj.file_type})")
    except ProjectFile.DoesNotExist:
        logger.error(f"[edit_file_content] File with ID {file_id} not found in project {project_id}")
        return {
            "is_notification": False,
            "message_to_agent": f"File with ID {file_id} not found in project {project_id}"
        }
    
    # Get current content and split into lines
    current_content = file_obj.content
    lines = current_content.split('\n')
    original_line_count = len(lines)
    logger.info(f"[edit_file_content] Current file has {original_line_count} lines")
    
    # Sort operations by type and position to apply them in order
    # Apply replacements first, then insertions
    replace_ops = [op for op in edit_operations if op.get('type') == 'replace_lines']
    insert_ops = [op for op in edit_operations if op.get('type') == 'insert_after']
    pattern_ops = [op for op in edit_operations if op.get('type') == 'pattern_replace']
    
    # Sort replace operations by start line (descending) to avoid index shifting
    replace_ops.sort(key=lambda x: x.get('start', 0), reverse=True)
    # Sort insert operations by line number (descending) to avoid index shifting
    insert_ops.sort(key=lambda x: x.get('line', 0), reverse=True)
    
    # Apply replace operations
    logger.info(f"[edit_file_content] Applying {len(replace_ops)} replace operations")
    for i, operation in enumerate(replace_ops):
        try:
            start = operation['start'] - 1  # Convert to 0-based index
            end = operation['end']  # End is inclusive in 1-based, exclusive in slice
            new_lines = operation['content'].split('\n')
            
            logger.info(f"[edit_file_content] Replace op {i+1}: lines {start+1}-{end} with {len(new_lines)} new lines")
            
            # Validate line numbers
            if start < 0 or end > len(lines):
                logger.warning(f"[edit_file_content] Invalid line range: {start+1}-{end} for file with {len(lines)} lines")
                continue
                
            lines[start:end] = new_lines
            logger.info(f"[edit_file_content] Successfully replaced lines {start+1}-{end} with {len(new_lines)} new lines")
        except Exception as e:
            logger.error(f"[edit_file_content] Error applying replace operation: {str(e)}", exc_info=True)
    
    # Apply insert operations
    logger.info(f"[edit_file_content] Applying {len(insert_ops)} insert operations")
    for i, operation in enumerate(insert_ops):
        try:
            line_num = operation['line']  # Insert after this line
            new_lines = operation['content'].split('\n')
            
            logger.info(f"[edit_file_content] Insert op {i+1}: {len(new_lines)} lines after line {line_num}")
            
            # Validate line number
            if line_num < 0 or line_num > len(lines):
                logger.warning(f"[edit_file_content] Invalid insert position: after line {line_num} for file with {len(lines)} lines")
                continue
            
            # Insert after the specified line (Python slice insert at position inserts BEFORE that position)
            # So to insert after line N, we insert at position N+1
            insert_position = line_num + 1 if line_num < len(lines) else len(lines)
            lines[insert_position:insert_position] = new_lines
            logger.info(f"[edit_file_content] Successfully inserted {len(new_lines)} lines after line {line_num} (at position {insert_position})")
        except Exception as e:
            logger.error(f"[edit_file_content] Error applying insert operation: {str(e)}", exc_info=True)
    
    # Apply pattern replacements
    logger.info(f"[edit_file_content] Applying {len(pattern_ops)} pattern operations")
    for i, operation in enumerate(pattern_ops):
        try:
            pattern = operation['pattern']
            content = operation['content']
            
            logger.info(f"[edit_file_content] Pattern op {i+1}: replacing '{pattern[:30]}...' with '{content[:30]}...'")
            
            # Join lines, replace pattern, split again
            full_content = '\n'.join(lines)
            occurrences = full_content.count(pattern)
            full_content = full_content.replace(pattern, content)
            lines = full_content.split('\n')
            
            logger.info(f"[edit_file_content] Replaced {occurrences} occurrences of pattern '{pattern[:30]}...'")
        except Exception as e:
            logger.error(f"[edit_file_content] Error applying pattern operation: {str(e)}", exc_info=True)
    
    # Save the edited content
    new_content = '\n'.join(lines)
    new_line_count = len(lines)
    
    logger.info(f"[edit_file_content] Saving edited content. New line count: {new_line_count}")
    
    # Update the file
    await sync_to_async(file_obj.save_content)(new_content)
    await sync_to_async(file_obj.save)()
    
    logger.info(f"[edit_file_content] File '{file_obj.name}' edited successfully. Lines changed from {original_line_count} to {new_line_count}")
    
    result = {
        "is_notification": True,
        "notification_type": "file_edited",
        "message_to_agent": f"File '{file_obj.name}' edited successfully. Applied {len(edit_operations)} operations. Lines: {original_line_count} → {new_line_count}",
        "file_id": file_id,
        "file_name": file_obj.name,
        "file_type": file_obj.file_type,
        "operations_applied": len(edit_operations),
        "line_count_before": original_line_count,
        "line_count_after": new_line_count,
        "notification_marker": "__NOTIFICATION__"  # Important for UI processing
    }
    
    logger.info(f"[edit_file_content] Returning result: {result}")
    return result

async def save_implementation_from_stream(implementation_content, project_id):
    """
    Save implementation content that was captured from the streaming response.
    This function is called from ai_providers.py when implementation generation is complete.
    
    Args:
        implementation_content: The complete implementation content captured from streaming
        project_id: The project ID to save the implementation for
        
    Returns:
        Dict with notification data
    """
    logger.info(f"Saving implementation from stream for project {project_id}")
    logger.info(f"Implementation content length: {len(implementation_content)} characters")
    
    # Validate project ID
    if not project_id:
        logger.error("No project_id provided")
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required"
        }
    
    # Get the project
    try:
        project = await get_project(project_id)
        if not project:
            logger.error(f"Project with ID {project_id} not found")
            return {
                "is_notification": False,
                "message_to_agent": f"Error: Project with ID {project_id} does not exist"
            }
    except Exception as e:
        logger.error(f"Error fetching project: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error fetching project: {str(e)}"
        }
    
    # Validate implementation content
    if not implementation_content or not implementation_content.strip():
        logger.error("Implementation content is empty")
        return {
            "is_notification": False,
            "message_to_agent": "Error: Implementation content cannot be empty"
        }
    
    # Clean up any residual artifacts
    implementation_content = implementation_content.strip()
    # Remove leading '>' if present
    if implementation_content.startswith('>'):
        implementation_content = implementation_content[1:].strip()
    # Remove any trailing tag fragments
    if '</lfg-plan' in implementation_content:
        implementation_content = implementation_content[:implementation_content.rfind('</lfg-plan')].strip()
    
    try:
        # Save implementation to database
        impl_obj, created = await sync_to_async(
            ProjectImplementation.objects.get_or_create
        )(
            project=project,
            defaults={'implementation': implementation_content}
        )
        
        # Update if it already existed
        if not created:
            impl_obj.implementation = implementation_content
            await sync_to_async(impl_obj.save)()
            logger.info(f"Updated existing implementation for project {project_id}")
        else:
            logger.info(f"Created new implementation for project {project_id}")
        
        action = "created" if created else "updated"
        
        return {
            "is_notification": True,
            "notification_type": "implementation",
            "message_to_agent": f"Implementation {action} successfully in the database"
        }
        
    except Exception as e:
        logger.error(f"Error saving implementation: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving implementation: {str(e)}"
        }

async def save_prd_from_stream(prd_content, project_id, prd_name=None):
    """
    Save PRD content that was captured from the streaming response.
    This function is called from ai_providers.py when PRD generation is complete.
    
    Args:
        prd_content: The complete PRD content captured from streaming
        project_id: The project ID to save the PRD for
        prd_name: Optional name for the PRD (defaults to "Main PRD")
        
    Returns:
        Dict with notification data
    """
    logger.info(f"Saving PRD from stream for project {project_id}")
    logger.info(f"PRD content length: {len(prd_content)} characters")
    logger.info(f"PRD name: {prd_name}")
    
    # Validate project ID
    if not project_id:
        logger.error("No project_id provided")
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required"
        }
    
    # Get the project
    try:
        project = await get_project(project_id)
        if not project:
            logger.error(f"Project with ID {project_id} not found")
            return {
                "is_notification": False,
                "message_to_agent": f"Error: Project with ID {project_id} does not exist"
            }
    except Exception as e:
        logger.error(f"Error fetching project: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error fetching project: {str(e)}"
        }
    
    # Validate PRD content
    if not prd_content or not prd_content.strip():
        logger.error("PRD content is empty")
        return {
            "is_notification": False,
            "message_to_agent": "Error: PRD content cannot be empty"
        }
    
    # Clean up any residual artifacts
    prd_content = prd_content.strip()
    
    # Remove leading '>' if present (but preserve line breaks)
    if prd_content.startswith('>'):
        prd_content = prd_content[1:].lstrip(' \t')  # Only strip spaces and tabs, not newlines
    
    # Remove any trailing tag fragments more carefully
    if '</lfg-prd' in prd_content:
        # Find the last occurrence and remove everything from there
        last_tag_pos = prd_content.rfind('</lfg-prd')
        prd_content = prd_content[:last_tag_pos].rstrip()
    
    # Remove opening tag if it somehow got included
    if '<lfg-prd' in prd_content:
        # Find the tag and remove it
        import re
        prd_content = re.sub(r'<lfg-prd[^>]*>', '', prd_content, count=1).lstrip()
    
    # Ensure the content is not empty after cleaning
    prd_content = prd_content.strip()
    
    # Set default name if not provided
    if not prd_name:
        prd_name = "Main PRD"
    
    try:
        # Save PRD to database with name
        prd_obj, created = await sync_to_async(
            ProjectPRD.objects.get_or_create
        )(
            project=project, 
            name=prd_name,
            defaults={'prd': prd_content}
        )
        
        # Update existing PRD if it wasn't created
        if not created:
            prd_obj.prd = prd_content
            await sync_to_async(prd_obj.save)()
        
        action = "created" if created else "updated"
        logger.info(f"PRD '{prd_name}' {action} successfully for project {project_id}")
        
        return {
            "is_notification": True,
            "notification_type": "prd",
            "message_to_agent": f"PRD '{prd_name}' {action} successfully in the database",
            "prd_name": prd_name
        }
        
    except Exception as e:
        logger.error(f"Error saving PRD from stream: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving PRD: {str(e)}"
        }

async def save_ticket_from_stream(ticket_data, project_id):
    """
    Save a single ticket that was captured from the streaming response.
    This function is called from ai_providers.py when a complete ticket is parsed.
    
    Args:
        ticket_data: The complete ticket data parsed from <lfg-ticket> tags
        project_id: The project ID to save the ticket for
        
    Returns:
        Dict with notification data
    """
    logger.info(f"Saving ticket from stream for project {project_id}")
    logger.debug(f"Ticket data: {ticket_data}")
    
    # Validate project ID
    if not project_id:
        logger.error("No project_id provided")
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required"
        }
    
    # Get project
    project = await get_project(project_id)
    if not project:
        logger.error(f"Project with ID {project_id} not found")
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    try:
        # Create ticket with enhanced details
        new_ticket = await sync_to_async(ProjectChecklist.objects.create)(
            project=project,
            name=ticket_data.get('name', ''),
            description=ticket_data.get('description', ''),
            priority=ticket_data.get('priority', 'Medium'),
            status='open',
            role=ticket_data.get('role', 'agent'),
            ui_requirements=ticket_data.get('ui_requirements', {}),
            component_specs=ticket_data.get('component_specs', {}),
            acceptance_criteria=ticket_data.get('acceptance_criteria', []),
            dependencies=ticket_data.get('dependencies', [])
        )
        
        logger.info(f"Ticket created successfully with ID {new_ticket.id}")
        
        return {
            "is_notification": True,
            "notification_type": "checklist",
            "message_to_agent": f"Ticket '{ticket_data.get('name', 'Unnamed')}' created successfully"
        }
        
    except Exception as e:
        logger.error(f"Error saving ticket from stream: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving ticket: {str(e)}"
        }


# Only to be used with OpenAIProvider
# As OpenAI doesn't support web search tool yet
# Claude does.
async def web_search(query, conversation_id=None):
    """
    Perform a web search using OpenAI's web search capabilities.
    This function is only available for OpenAI provider.
    
    Args:
        query: The search query string
        conversation_id: The conversation ID (optional)
        
    Returns:
        Dict with search results or error message
    """
    logger.info(f"Web search function called with query: {query}")
    
    if not query:
        return {
            "is_notification": False,
            "message_to_agent": "Error: query is required for web search"
        }
    
    try:
        # Get user and conversation details
        model = "gpt-4.1"  # Default model
        
        # Get OpenAI API key
        openai_api_key = os.environ.get('OPENAI_API_KEY')
        
        # Initialize OpenAI client
        import openai
        client = openai.OpenAI(api_key=openai_api_key)
        
        logger.info(f"Using model {model} for web search")
        
        # Make the search request using OpenAI's responses.create API
        response = client.responses.create(
            model=model,
            tools=[{"type": "web_search_preview"}],
            input=query
        )
        
        # Extract the search results from the response
        if response:
            # Convert response to string format
            search_results = str(response)
            
            logger.info(f"Web search completed successfully for query: {query}")
            
            return {
                "is_notification": True,
                "notification_type": "toolhistory",
                "message_to_agent": f"Web search results for '{query}':\n\n{search_results}"
            }
        else:
            return {
                "is_notification": False,
                "message_to_agent": "No search results found"
            }
            
    except Exception as e:
        logger.error(f"Error performing web search: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error performing web search: {str(e)}"
        }

async def get_file_list(project_id, file_type="all", limit=10):
    """
    Get the list of files in the project
    
    Args:
        project_id: The project ID
        file_type: Type of files to retrieve ("prd", "implementation", "design", "all")
        limit: Number of files to return (default: 10)
        
    Returns:
        Dict with list of files or error message
    """
    logger.info(f"Get file list function called for project {project_id}, file_type: {file_type}")
    
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
        # Build query based on file_type
        query_kwargs = {"project": project}
        if file_type != "all":
            query_kwargs["file_type"] = file_type
        
        # Get files from ProjectFile model
        files = await sync_to_async(
            lambda: list(ProjectFile.objects.filter(**query_kwargs).order_by("-updated_at")[:limit])
        )()
        
        if not files:
            return {
                "is_notification": True,
                "notification_type": "file_list",
                "message_to_agent": f"No {file_type} files found for this project"
            }
        
        # Format file list
        file_list = []
        for file in files:
            file_list.append({
                "file_id": file.id,
                "name": file.name,
                "file_type": file.file_type,
                "created_at": file.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": file.updated_at.strftime("%Y-%m-%d %H:%M:%S")
            })
        
        return {
            "is_notification": True,
            "notification_type": "file_list",
            "message_to_agent": f"Found {len(file_list)} {file_type} files. Here are the file details {file_list}",
            "files": file_list
        }
        
    except Exception as e:
        logger.error(f"Error getting file list: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error getting file list: {str(e)}"
        }

async def get_file_content(project_id, file_ids):
    """
    Get the content of multiple files in the project
    
    Args:
        project_id: The project ID
        file_ids: A single file ID or list of file IDs to retrieve (max 5)
        
    Returns:
        Dict with file contents or error message
    """
    logger.info(f"Get file content function called for project {project_id}, file_ids: {file_ids}")
    
    error_response = validate_project_id(project_id)
    if error_response:
        return error_response
    
    # Handle both single file_id and list of file_ids
    if isinstance(file_ids, (int, str)):
        file_ids = [file_ids]
    elif not isinstance(file_ids, list):
        return {
            "is_notification": False,
            "message_to_agent": "Error: file_ids must be an integer, string, or list"
        }
    
    if not file_ids:
        return {
            "is_notification": False,
            "message_to_agent": "Error: at least one file_id is required"
        }
    
    # Limit to 5 files
    if len(file_ids) > 5:
        return {
            "is_notification": False,
            "message_to_agent": "Error: Maximum 5 files can be retrieved at once"
        }
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    try:
        # Get multiple files by IDs and ensure they belong to the project
        files = await sync_to_async(
            lambda: list(ProjectFile.objects.filter(id__in=file_ids, project=project))
        )()
        
        if not files:
            return {
                "is_notification": False,
                "message_to_agent": f"Error: No files found with the provided IDs in project {project_id}"
            }
        
        # Check which file IDs were not found
        found_ids = {file.id for file in files}
        missing_ids = set(file_ids) - found_ids
        
        # Format file contents
        file_contents = []
        for file_obj in files:
            file_contents.append({
                "file_id": file_obj.id,
                "name": file_obj.name,
                "file_type": file_obj.file_type,
                "content": file_obj.file_content,
                "created_at": file_obj.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": file_obj.updated_at.strftime("%Y-%m-%d %H:%M:%S")
            })
        
        response = {
            "is_notification": True,
            "notification_type": "file_content",
            "message_to_agent": f"Retrieved {len(files)} file(s). Here are the file contents: {file_contents}. You can proceed to the next step.",
            "files": file_contents
        }
        
        if missing_ids:
            response["missing_file_ids"] = list(missing_ids)
            response["message_to_agent"] += f". Warning: File IDs not found: {missing_ids}"
        
        return response
        
    except Exception as e:
        logger.error(f"Error getting file content: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error getting file content: {str(e)}"
        }
        

# Add this function to ai_functions.py

async def update_file_content(file_id, updated_content, project_id):
    """
    Update an existing file with new content (complete replacement)
    
    Args:
        file_id: The ID of the file to update
        updated_content: The complete new content for the file
        project_id: The project ID
    
    Returns:
        Dict with operation result
    """
    logger.info(f"Updating file {file_id} with new content ({len(updated_content)} characters)")

    logger.info(f"Updated Content: {updated_content}")
    
    # Validate inputs
    if not file_id:
        return {
            "is_notification": False,
            "message_to_agent": "Error: file_id is required for updating"
        }
    
    if not updated_content:
        return {
            "is_notification": False,
            "message_to_agent": "Error: updated_content cannot be empty"
        }
    
    project = await get_project(project_id)
    if not project:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    # Get the file
    try:
        file_obj = await sync_to_async(
            ProjectFile.objects.get
        )(id=file_id, project=project)
    except ProjectFile.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": f"File with ID {file_id} not found in project {project_id}"
        }
    
    # Store old content length for comparison
    old_content_length = len(file_obj.content) if file_obj.content else 0
    new_content_length = len(updated_content)
    
    # Update the file content
    try:
        # Update content using the model's method
        await sync_to_async(file_obj.save_content)(updated_content)
        await sync_to_async(file_obj.save)()
        
        logger.info(f"File '{file_obj.name}' updated successfully. Content size: {old_content_length} → {new_content_length} characters")
        
        return {
            "is_notification": True,
            "notification_type": "file_edited",
            "message_to_agent": f"File '{file_obj.name}' updated successfully. Content updated from {old_content_length} to {new_content_length} characters.",
            "file_id": file_id,
            "file_name": file_obj.name,
            "file_type": file_obj.file_type,
            "old_size": old_content_length,
            "new_size": new_content_length
        }
        
    except Exception as e:
        logger.error(f"Error updating file content: {str(e)}")
        return {
            "is_notification": False,
            "message_to_agent": f"Error updating file: {str(e)}"
        }