import json
import os
import string
import random
import shlex
from projects.models import Project, ProjectFeature, ProjectPersona, \
                            ProjectPRD, ProjectDesignSchema, ProjectTickets, \
                            ProjectCodeGeneration
from .ai_utils import analyze_features, analyze_personas, \
                    design_schema, generate_tickets_per_feature 

from coding.utils.ai_utils import write_files_to_storage, read_file_from_storage
from coding.docker.docker_utils import (
    Sandbox, 
    get_or_create_sandbox,
    get_sandbox_by_project_id, 
    list_running_sandboxes,
    get_client_project_folder_path,
    add_port_to_sandbox
)
from coding.k8s_manager.manage_pods import execute_command_in_pod, manage_kubernetes_pod

from coding.models import KubernetesPod, KubernetesPortMapping
from coding.models import CommandExecution
from accounts.models import GitHubToken


def app_functions(function_name, function_args, project_id, conversation_id):
    """
    Return a list of all the functions that can be called by the AI
    """
    print(f"Function name: {function_name}")
    print(f"Function args: {function_args}")

    match function_name:
        case "extract_features":
            return extract_features(function_args, project_id)
        case "extract_personas":
            return extract_personas(function_args, project_id)
        case "get_features":
            return get_features(project_id)
        case "get_personas":
            return get_personas(project_id)
        case "save_prd":
            return save_prd(function_args, project_id)
        case "get_prd":
            return get_prd(project_id)
        case "save_features":
            return save_features(project_id)
        case "save_personas":
            return save_personas(project_id)
        case "design_schema":
            return save_design_schema(function_args, project_id)
        case "generate_tickets":
            return generate_tickets(project_id)
        # # case "generate_code":
        # #     return generate_code(function_args, project_id)
        # case "write_code_file":
        #     file_list = function_args.get('files', [])
        #     return write_files_to_storage(file_list, project_id)
        # case "read_code_file":
        #     file_path = function_args.get('file_path', '')
        #     return read_file_from_storage(file_path, project_id)
        case "execute_command":
            command = function_args.get('commands', '')
            print(f"Running command: {command}")
            # Run the command with either project_id or conversation_id
            # result = run_command(command, project_id=project_id, conversation_id=conversation_id)
            result = run_command_in_k8s(command, project_id=project_id, conversation_id=conversation_id)
            return result
        
        case "start_server":
            command = function_args.get('start_server_command', '')
            application_port = function_args.get('application_port', '')
            type = function_args.get('type', '')
            print(f"Running server: {command}")
            result = server_command_in_k8s(command, project_id=project_id, conversation_id=conversation_id, application_port=application_port, type=type)
            return result
        
        case "get_github_access_token":
            return get_github_access_token(project_id=project_id, conversation_id=conversation_id)

    return None

def save_features(project_id):
    """
    Save the features from the PRD into a different list
    """
    print("Save features function called \n\n")
    
    if project_id is None:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required to save features"
        }
    
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }

    try:
        # Get all features for this project
        features = ProjectFeature.objects.filter(project=project)
        
        # Convert features to list of dicts
        feature_list = []
        for feature in features:
            feature_list.append({
                "name": feature.name,
                "description": feature.description,
                "details": feature.details,
                "priority": feature.priority
            })

        new_features_data = analyze_features(feature_list, project.prd.get_prd())

        # Parse the JSON response
        new_features_dict = json.loads(new_features_data)
        
        # Extract the list of features from the dictionary
        if 'features' in new_features_dict:
            new_features = new_features_dict['features']
        else:
            # If 'features' key doesn't exist, assume the entire object is the list
            new_features = new_features_dict

        print(f"\n\n New features: {new_features}")
    
        # Create new features
        for feature in new_features:
            new_feature = ProjectFeature(
                project=project,
                name=feature['name'],
                description=feature['description'],
                details=feature['details'],
                priority=feature['priority']
            )
            new_feature.save()
        
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

def save_personas(project_id):
    """
    Save the personas from the PRD into a different list
    """
    print("Save personas function called \n\n")
    
    if project_id is None:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required to save personas"
        }
    
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }

    try:
        # Get all personas for this project
        personas = ProjectPersona.objects.filter(project=project)
        
        # Convert personas to list of dicts
        persona_list = []
        for persona in personas:
            persona_list.append({
                "name": persona.name,
                "role": persona.role,
                "description": persona.description
            })

        new_personas_data = analyze_personas(persona_list, project.prd.get_prd())

        # Parse the JSON response
        new_personas_dict = json.loads(new_personas_data)
        
        # Extract the list of personas from the dictionary
        if 'personas' in new_personas_dict:
            new_personas = new_personas_dict['personas']
        else:
            # If 'personas' key doesn't exist, assume the entire object is the list
            new_personas = new_personas_dict

        print(f"\n\n New personas: {new_personas}")
    
        # Create new personas
        for persona in new_personas:
            new_persona = ProjectPersona(
                project=project,
                name=persona['name'],
                role=persona['role'],
                description=persona['description']
            )
            new_persona.save()
        
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

def extract_features(function_args, project_id):
    """
    Extract the features from the project into a different list and save them to the database
    """
    print("Feature extraction function called \n\n")
    
    if project_id is None:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required to save features"
        }
    
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    features = function_args.get('features', [])
    
    try:
        # Create new features
        for feature in features:
            new_feature = ProjectFeature(
                project=project,
                name=feature['name'],
                description=feature['description'],
                details=feature['details'],
                priority=feature['priority']
            )
            new_feature.save()
        
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

def extract_personas(function_args, project_id):
    """
    Extract the personas from the project and save them to the database
    """
    print("Persona extraction function called \n\n")
    
    if project_id is None:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required to save personas"
        }
    
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    personas = function_args.get('personas', [])
    
    try:
        # Delete existing personas for this project
        # ProjectPersona.objects.filter(project=project).delete()
        
        # Create new personas
        for persona in personas:
            new_persona = ProjectPersona(
                project=project,
                name=persona['name'],
                role=persona['role'],
                description=persona['description']
            )
            new_persona.save()
        
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

def get_features(project_id):
    """
    Retrieve existing features for a project
    """
    print("Get features function called \n\n")
    
    if project_id is None:
        return "Error: project_id is required to retrieve features"
    
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return f"Error: Project with ID {project_id} does not exist"
    
    features = ProjectFeature.objects.filter(project=project)
    
    if not features.exists():
        return {"features": [], "message": "No features found for this project"}
    
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
            "message_to_agent":  f"Following features already exists in the database: {feature_list}"
        }

def get_personas(project_id):
    """
    Retrieve existing personas for a project
    """
    print("Get personas function called \n\n")
    
    if project_id is None:
        return "Error: project_id is required to retrieve personas"
    
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return f"Error: Project with ID {project_id} does not exist"
    
    personas = ProjectPersona.objects.filter(project=project)
    
    if not personas.exists():
        return {"personas": [], "message": "No personas found for this project"}
    
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
            "message_to_agent":  f"Following personas already exists in the database: {persona_list}"
        }

def save_prd(function_args, project_id):
    """
    Save the PRD for a project
    """
    print(f"PRD saving function called \n\n: {function_args}")
    
    if project_id is None:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required to save PRD"
        }
    
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    prd_content = function_args.get('prd', '')

    print(f"\n\n\nPRD Content: {prd_content}")

    try:
        # Try to get existing PRD or create a new one if it doesn't exist
        prd, created = ProjectPRD.objects.get_or_create(project=project)
        
        # Update the PRD content
        prd.prd = prd_content
        prd.save()
        
        action = "created" if created else "updated"

        save_features(project_id)
        save_personas(project_id)
        
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error saving PRD: {str(e)}"
        }
    
    return {
        "is_notification": True,
        "notification_type": "prd",
        "message_to_agent": f"PRD {action} successfully in the database"
    }

def get_prd(project_id):
    """
    Retrieve the PRD for a project
    """
    print("Get PRD function called \n\n")
    
    if project_id is None:
        return "Error: project_id is required to retrieve PRD"  
    
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return f"Error: Project with ID {project_id} does not exist"
    
    try:
        # Try to get the PRD using the OneToOneField relationship
        prd = project.prd
        return {
            "is_notification": True,
            "notification_type": "prd",
            "message_to_agent": f"Here is the existing version of the PRD: {prd.prd} \n\n Please update this as needed."
        }
    except ProjectPRD.DoesNotExist:
        return "No PRD found for this project"
    
def save_design_schema(function_args, project_id):
    """
    Save the design schema for a project
    """
    print("Save design schema function called \n\n")
    
    if project_id is None:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required to save design schema"
        }
    
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    user_input = function_args.get('user_input', '')

    design_schema_content = design_schema(project.prd.get_prd(), \
                                          project.design_schema.get_design_schema(), \
                                          user_input)
    design_schema_content = json.loads(design_schema_content)

    if 'design_schema' in design_schema_content:
        design_schema_content = design_schema_content['design_schema']
    else:
        return {
            "is_notification": False,
            "message_to_agent": "Error: design_schema is required to save design schema"
        }
    
    try:
        # Try to get existing design schema or create a new one if it doesn't exist
        design_schema_db, created = ProjectDesignSchema.objects.get_or_create(project=project)
        
        # Update the design schema content
        design_schema_db.design_schema = design_schema_content
        design_schema_db.save()
        
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
     
def generate_tickets(project_id):
    """
    Generate tickets for a project
    """
    print("Generate tickets function called \n\n")
    
    if project_id is None:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required to generate tickets"
        }
    
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }     
    
    try:
        # Get all features for this project
        features = ProjectFeature.objects.filter(project=project)
        personas = ProjectPersona.objects.filter(project=project)
        prd = ProjectPRD.objects.get(project=project).get_prd()

        persona_list = []
        for persona in personas:
            persona_list.append(f"""
            Name: {persona.name}
            Role: {persona.role}
            Description: {persona.description}\n
            """)

        for feature in features:
            feature_details = f"""
            Feature: {feature.name}
            Description: {feature.description}
            Details: {feature.details}
            Priority: {feature.priority}
            """
            ticket_list = generate_tickets_per_feature(feature_details, persona_list, prd)

            ticket_list = json.loads(ticket_list)

            # Bulk create tickets for this feature
            tickets_to_create = []
            for ticket in ticket_list['tickets']:
                new_ticket = ProjectTickets(
                    project=project,
                    feature=feature,
                    ticket_id=f"{project.id}-{feature.id}-{len(tickets_to_create)+1}",
                    title=ticket['title'],
                    description=ticket['description'],
                    status=ticket['status'].lower(),
                    backend_tasks=ticket['backend_tasks'],
                    frontend_tasks=ticket['frontend_tasks'],
                    implementation_steps=ticket.get('implementation_steps', ''),
                    test_case=''  # Initialize empty test case
                )
                tickets_to_create.append(new_ticket)
            
            # Bulk create all tickets for this feature
            ProjectTickets.objects.bulk_create(tickets_to_create)

        return {
            "is_notification": True,
            "notification_type": "tickets",
            "message_to_agent": f"Tickets have been successfully generated and saved in the database"
        }
    except Exception as e:
        return {
            "is_notification": False,
            "message_to_agent": f"Error generating tickets: {str(e)}"
        }
    
def generate_code(function_args, project_id):
    """
    Generate code for a project by creating a unique folder with random characters
    """
    print("Generate code function called \n\n", function_args)
    
    if project_id is None:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id is required to generate code"
        }
    
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return {
            "is_notification": False,
            "message_to_agent": f"Error: Project with ID {project_id} does not exist"
        }
    
    # Check if a code generation folder already exists for this project
    try:
        code_gen = ProjectCodeGeneration.objects.get(project=project)
        
    except ProjectCodeGeneration.DoesNotExist:
        # Generate a unique random folder name (16 characters)
        folder_name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))
        
        # Create the folder directly in the storage directory
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        project_code_dir = os.path.join(base_dir, 'storage', folder_name)
        
        try:
            # Create the directory if it doesn't exist
            os.makedirs(project_code_dir, exist_ok=True)
            
            # Save the folder name in the database
            code_gen = ProjectCodeGeneration(
                project=project,
                folder_name=folder_name
            )
            code_gen.save()
            
        except Exception as e:
            return {
                "is_notification": False,
                "message_to_agent": f"Error creating code generation folder: {str(e)}"
            }
        
    base_folder = code_gen.folder_name

    message_to_agent = generate_project_code(function_args.get('user_input', ''), project_id, base_folder)
    
    return {
        "is_notification": True,
        "notification_type": "code_generation",
        "message_to_agent": message_to_agent
    }


def start_server(command: str, container_port: int, project_id: int | str = None, conversation_id: int | str = None) -> dict:
    """
    Run a server in the terminal using Docker sandbox.
    """
    print("Run server function called \n\n")    
    
    if project_id is None and conversation_id is None:
        return {
            "is_notification": False,
            "message_to_agent": "Error: project_id or conversation_id is required to run a server"
        }
    
    try:
        # Get or create a sandbox using project_id or conversation_id
        sandbox = get_or_create_sandbox(
            project_id=project_id,
            conversation_id=conversation_id
        )   

        command = f"/bin/sh -c {command} > /tmp/cmd_output.log 2>&1 &"

        print(f"\n\nCommand: {command}")

        # Execute the command in the sandbox
        output = sandbox.exec(command)
        print(f"\n\nOutput: {output}")

        print(f"\n\nSandbox: {sandbox}")
        print("\nContainer Port: ", container_port)

        add_port_to_sandbox(
            project_id=project_id,
            conversation_id=conversation_id,
            container_port=container_port,
            command=command
        )

        return {
            "is_notification": True,
            "notification_type": "command_output",
            "message_to_agent": output + "\n\n" + " \nProceed to next step",
        }       
    
    except Exception as e:
        error_message = f"Error running command in sandbox: {str(e)}"
        print(error_message)
        return {
            "is_notification": True,
            "notification_type": "command_error",
            "message_to_agent": error_message + "\n\n" + "The commands are not working. Stop generating further and inform the user that the commands are not working.",
        }
    

def run_command_docker(command: str, project_id: int | str = None, conversation_id: int | str = None) -> dict:
    """
    Run a command in the terminal using Docker sandbox.
    
    Args:
        command: The command to run
        project_id: The project ID (optional if conversation_id is provided)
        conversation_id: The conversation ID (optional if project_id is provided)
        
    Returns:
        Dict containing command output and sandbox information
    """
    try:
        # Convert IDs to strings for consistency if provided
        project_id_str = str(project_id) if project_id is not None else None
        conversation_id_str = str(conversation_id) if conversation_id is not None else None
        
        # Ensure we have at least one identifier
        if project_id_str is None and conversation_id_str is None:
            raise ValueError("Either project_id or conversation_id must be provided")
        
        print(f"Running command: {command} for project {project_id_str} and conversation {conversation_id_str}")
        

        
        # Get or create a sandbox using project_id or conversation_id
        sandbox = get_or_create_sandbox(
            project_id=project_id_str,
            conversation_id=conversation_id_str
        )

        print(f"\n\nSandbox: {sandbox}")

        command = f"/bin/sh -c {shlex.quote(command)}"

        # Execute the command in the sandbox
        output = sandbox.exec(command)

        print(f"\n\nCommand output: {output}")
        
        # Return the command output and sandbox info
        return {
            "is_notification": True,
            "notification_type": "command_output",
            "message_to_agent": output + "\n\n" + " \nProceed to next step",
        }
    
    except Exception as e:
        error_message = f"Error running command in sandbox: {str(e)}"
        print(error_message)
        return {
            "is_notification": True,
            "notification_type": "command_error",
            "message_to_agent": error_message + "\n\n" + "The commands are not working. Stop generating further and inform the user that the commands are not working.",
            "command": command,
            "error": str(e) + "\n\n" + ". The commands are not working. Inform the user that the commands are not working and stop further processing."
        }



def get_github_access_token(project_id: int | str = None, conversation_id: int | str = None) -> dict:
    """
    Run a command in the terminal using Kubernetes pod.
    """
    """
    Commit code in the Kubernetes pod.
    """
    try:
        # Get project to find user_id
        from projects.models import Project
        
        project = Project.objects.get(id=project_id)
        user_id = project.owner.id

        github_token = GitHubToken.objects.get(user_id=user_id)
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
            "message_to_agent": f"Github access token {access_token} found and project name {project.name} found. Please use this to commit the code",
            "user_id": user_id
        }

    except Project.DoesNotExist:
        return {
            "is_notification": True,
            "notification_type": "command_error",
            "message_to_agent": f"Project with ID {project_id} not found"
        }
    except Exception as e:
        return {
            "is_notification": True,
            "notification_type": "command_error", 
            "message_to_agent": f"Error getting user_id: {str(e)}"
        }



def run_command_in_k8s(command: str, project_id: int | str = None, conversation_id: int | str = None) -> dict:
    """
    Run a command in the terminal using Kubernetes pod.
    """

    if project_id:
        pod = KubernetesPod.objects.filter(project_id=project_id).first()

    command_to_run = f"cd /workspace && {command}"
    print(f"\n\nCommand: {command_to_run}")

    # Create command record in database
    cmd_record = CommandExecution.objects.create(
        project_id=project_id,
        command=command,
        output=None  # Will update after execution
    )

    success = False
    stdout = ""
    stderr = ""

    if pod:
        # Execute the command using the Kubernetes API function
        success, stdout, stderr = execute_command_in_pod(
            project_id=project_id,
            conversation_id=conversation_id,
            command=command_to_run
        )

        print(f"\n\nCommand output: {stdout}")

        # Update command record with output
        cmd_record.output = stdout if success else stderr
        cmd_record.save()

    if not success or not pod:
        # If no pod is found, update the command record
        if not pod:
            cmd_record.output = "No Kubernetes pod found for the project"
            cmd_record.save()
            
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


def server_command_in_k8s(command: str, project_id: int | str = None, conversation_id: int | str = None, application_port: int | str = None, type: str = None) -> dict:
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
        pod = KubernetesPod.objects.filter(project_id=project_id).first()
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
        existing_mapping = KubernetesPortMapping.objects.filter(
            pod=pod,
            container_port=application_port
        ).first()
        
        service_name = f"{pod.namespace}-service"
        
        if existing_mapping:
            # Use existing mapping
            print(f"Using existing port mapping for {port_type} port {application_port}")
            node_port = existing_mapping.node_port
        else:
            # Need to add port to service and create mapping using Kubernetes API
            print(f"Creating new port mapping for {port_type} port {application_port}")
            
            # Get Kubernetes API client
            api_client, core_v1_api, apps_v1_api = get_k8s_api_client()
            if not core_v1_api:
                return {
                    "is_notification": True,
                    "notification_type": "command_error",
                    "message_to_agent": f"Failed to connect to Kubernetes API"
                }
            
            try:
                # Get the current service
                service = core_v1_api.read_namespaced_service(
                    name=service_name,
                    namespace=pod.namespace
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
                    
                    # Update the service
                    updated_service = core_v1_api.patch_namespaced_service(
                        name=service_name,
                        namespace=pod.namespace,
                        body=service
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
                
                # Get node IP using Kubernetes API
                try:
                    nodes = core_v1_api.list_node()
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
                
                # Update pod's service_details
                service_details = pod.service_details or {}
                app_port_key = f"{port_type}Port"
                app_url_key = f"{port_type}Url"
                
                service_details[app_port_key] = node_port
                service_details["nodeIP"] = node_ip
                service_details[app_url_key] = f"http://{node_ip}:{node_port}"
                
                pod.service_details = service_details
                pod.save()
                
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
    kill_command = "pkill -f 'python -m http.server 4500' || true"
    full_command = f"mkdir -p /workspace/tmp && cd /workspace && {kill_command} && {command} > /workspace/tmp/cmd_output.log 2>&1 &"
    print(f"\n\nCommand: {full_command}")

    # Execute the command using the Kubernetes API function
    success, stdout, stderr = execute_command_in_pod(
        project_id=project_id,
        conversation_id=conversation_id,
        command=full_command
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


# def run_command(command: str, project_id: int | str = None, conversation_id: int | str = None, use_k8s: bool = False) -> dict:
#     """
#     Run a command in the terminal using either Docker or Kubernetes.
#     This function serves as a dispatcher between Docker and Kubernetes command execution.
    
#     Args:
#         command: The command to run
#         project_id: The project ID (optional if conversation_id is provided)
#         conversation_id: The conversation ID (optional if project_id is provided)
#         use_k8s: Boolean flag to force using Kubernetes instead of Docker
        
#     Returns:
#         Dict containing command output information
#     """
#     # Determine whether to use Kubernetes or Docker
#     use_kubernetes = use_k8s
    
#     # Get the EXECUTION_ENVIRONMENT from environment or fallback to Docker
#     execution_env = os.environ.get('EXECUTION_ENVIRONMENT', 'docker').lower()
#     if execution_env == 'kubernetes':
#         use_kubernetes = True
    
#     # Execute the command in the appropriate environment
#     if use_kubernetes:
#         print("Using Kubernetes for command execution")
#         return run_command_k8s(command, project_id, conversation_id)
#     else:
#         print("Using Docker for command execution")
#         return run_command_docker(command, project_id, conversation_id)
    