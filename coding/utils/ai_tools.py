save_prd = {
    "type": "function",
    "function": 
        {
            "name": "save_prd",
            "description": "Summarize the project based on the provided requirements and save the PRD in Markdown format. This could be an updated PRD either",
            "parameters": {
                "type": "object",
                "properties": {
                    "prd": {
                        "type": "string",
                        "description": "A detailed project PRD in markdown format or the update version of the existing PRD"
                    }
                },
                "required": ["prd"],
                "additionalProperties": False,
            }
        }
}

get_prd = {
    "type": "function",
    "function": {
        "name": "get_prd",
        "description": "Call this function to check if PRD already exists. If it does, it will return the PRD",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

create_implementation = {
    "type": "function",
    "function": {
        "name": "create_implementation",
        "description": "Save the implementation details and technical specifications for the project in Markdown format. This could be an updated implementation document",
        "parameters": {
            "type": "object",
            "properties": {
                "implementation": {
                    "type": "string",
                    "description": "A detailed implementation document in markdown format containing technical specifications, architecture, and implementation details"
                }
            },
            "required": ["implementation"],
            "additionalProperties": False,
        }
    }
}

get_implementation = {
    "type": "function",
    "function": {
        "name": "get_implementation",
        "description": "Call this function to check if implementation document already exists. If it does, it will return the implementation details",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

update_implementation = {
    "type": "function",
    "function": {
        "name": "update_implementation",
        "description": "Update the existing implementation document by adding new sections or modifications. Updates are added to the top of the document with timestamps. Use this for incremental changes or additions to the implementation plan.",
        "parameters": {
            "type": "object",
            "properties": {
                "update_type": {
                    "type": "string",
                    "enum": ["addition", "modification", "complete_rewrite"],
                    "description": "Type of update: 'addition' for new sections, 'modification' for changes to existing content, 'complete_rewrite' for replacing entire document"
                },
                "update_content": {
                    "type": "string",
                    "description": "The update content in markdown format. For additions/modifications, this will be prepended to the existing document with a timestamp."
                },
                "update_summary": {
                    "type": "string",
                    "description": "Brief summary of what was updated or added"
                }
            },
            "required": ["update_type", "update_content", "update_summary"],
            "additionalProperties": False,
        }
    }
}

save_features = {
    "type": "function",
    "function": {
        "name": "save_features",
        "description": "Call this function to save the features from the PRD into a different list",
    }
}

save_personas = {
    "type": "function",
    "function": {
        "name": "save_personas",
        "description": "Call this function to save the personas from the PRD into a different list",
    }
}

extract_features = {
    "type": "function",
    "function": {
        "name": "extract_features",
        "description": "Call this function to extract the features from the project into a different list",
        "parameters": {
            "type": "object",
            "properties": {
                "features": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string", "description": "A short description of this feature"},
                            "details": {"type": "string", "description": "You will provide a detailed description with at least 3-4 lines"},
                            "priority": {"type": "string", "enum": ["High", "Medium", "Low"]}
                        },
                        "required": ["name", "description", "details", "priority"]
                    }
                }
            },
            "required": ["features"]
        }
    }
}
    
get_features = {
        "type": "function",
        "function":
            {
                "name": "get_features",
                "description": "Call this function to check if Features already exist. If they do, it will return the list of features",
            }
    }

get_personas = {
        "type": "function",
        "function":
            {
                "name": "get_personas",
                "description": "Call this function to check if Personas already exist. If they do, it will return the list of personas",
            }
    }

extract_personas = {
    "type": "function",
    "function": {
        "name": "extract_personas",
        "description": "Call this function to extract the Personas",
        "parameters": {
            "type": "object",
            "properties": {
                "personas": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "role": {"type": "string"},
                            "description": {"type": "string"}
                        },
                        "required": ["name", "role", "description"]
                    }
                }
            },
            "required": ["personas"]
        }
    }
}

design_schema = {
    "type": "function",
    "function": {
        "name": "design_schema",
        "description": "Call this function with the detailed design schema for the project",
        "parameters": {
                "type": "object",
                "properties": {
                    "user_input": {
                        "type": "string",
                        "description": "This includes the design request provided by user, whether it is related to colors or fonts, etc."
                    }
                },
                "required": ["user_input"],
                "additionalProperties": False,
        }
    }
}

generate_tickets = {
    "type": "function",
    "function": {
        "name": "generate_tickets",
        "description": "Call this function to generate the tickets for the project",
        "parameters": {
            "type": "object",
            "properties": {
                "tickets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "priority": {"type": "string", "enum": ["High", "Medium", "Low"]}
                        },
                        "required": ["name", "description", "priority"]
                    }
                }
            },
            "required": ["tickets"]
        }
    }
}

checklist_tickets = {
    "type": "function",
    "function": {
        "name": "checklist_tickets",
        "description": "Call this function to generate the checklist tickets for the project",
        "parameters": {
            "type": "object",
            "properties": {
                "tickets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "role": {"type": "string", "enum": ["agent", "user"]},
                            "priority": {"type": "string", "enum": ["High", "Medium", "Low"]}
                        },
                        "required": ["name", "description", "priority"]
                    }
                }
            },
            "required": ["tickets"]
        }
    }
}

update_checklist_ticket = {

    "type": "function",
    "function": {
        "name": "update_checklist_ticket",
        "description": "Call this function to update the status of a checklist ticket to done. You need to pass the id.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string"},
                "status": {"type": "string", "enum": ["done", "in_progress", "agent", "open"]}
            },
            "required": ["ticket_id", "status"]
        }
    }
}

get_next_ticket = {
    "type": "function",
    "function": {
        "name": "get_next_ticket",
        "description": "Call this function to get the next available ticket for the project",
    }
}

get_pending_tickets = {
    "type": "function",
    "function": {
        "name": "get_pending_tickets",
        "description": "Call this function to get the pending tickets for the project",
    }
}

implement_ticket = {
    "type": "function",
    "function": {
        "name": "implement_ticket",
        "description": "Implement a specific ticket with all its requirements",
        "parameters": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "integer"},
                "ticket_details": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "files_to_create": {"type": "array", "items": {"type": "string"}},
                        "files_to_modify": {"type": "array", "items": {"type": "string"}},
                        "requires_worktree": {"type": "boolean"},
                        "branch_name": {"type": "string"},
                        "ui_requirements": {"type": "object"},
                        "component_specs": {"type": "object"},
                        "acceptance_criteria": {"type": "array", "items": {"type": "string"}}
                    }
                },
                "implementation_plan": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step": {"type": "integer"},
                            "action": {"type": "string"},
                            "files": {"type": "array", "items": {"type": "string"}},
                            "code_snippets": {"type": "object"}
                        }
                    }
                }
            },
            "required": ["ticket_id", "ticket_details", "implementation_plan"]
        }
    }
}

execute_tickets_in_parallel = {
    "type": "function",
    "function": {
        "name": "execute_tickets_in_parallel",
        "description": "Execute multiple tickets in parallel using Django-Q. Automatically groups tickets by priority and dependencies.",
        "parameters": {
            "type": "object",
            "properties": {
                "max_workers": {
                    "type": "integer",
                    "description": "Maximum number of tickets to execute in parallel (default: 3)",
                    "default": 3
                }
            }
        }
    }
}

get_ticket_execution_status = {
    "type": "function",
    "function": {
        "name": "get_ticket_execution_status",
        "description": "Get the execution status of tickets being processed by Django-Q",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Optional: specific Django-Q task ID to check. If not provided, returns all project ticket statuses."
                }
            }
        }
    }
}

generate_code = {
    "type": "function",
    "function": {
        "name": "generate_code",
        "description": "Call this function to generate the code based on the user input",
        "parameters": {
            "type": "object",
            "properties": {
                "user_input": {
                    "type": "string",
                    "description": "This includes the code request provided by user, it could be related to building features, projects, fixing bugs, or analysing data"
                }
            },
            "required": ["user_input"],
            "additionalProperties": False,
        }
    }
}

write_code_file = {
    "type": "function",
    "function": {
        "name": "write_code_file",
        "description": "Write the source code files to app directory. This includes file path and the source-code in patch-diff mode for the files sent.",
        "parameters": {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string", "description": "The path of the file to write to"},
                            "source_code": {"type": "string", "description": "The source code of the file in patch-diff mode"},
                        },
                        "required": ["file_path", "source_code"]
                    }
                }
            },
            "required": ["files"]
        }
    }
}

read_code_file = {
    "type": "function",
    "function": {
        "name": "read_code_file",
        "description": "Read the source code files from app directory. This includes file path",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "The path of the file to read from"},
            },
            "required": ["file_path"]
        }
    }
}

execute_command = {
    "type": "function",
    "function": {
        "name": "execute_command",
        "description": "The command that needs to be executed in the terminal. This includes either the command to fetch files, file directory tree, write code via git patch, execute commands, etc. ",
        "parameters": {
            "type": "object",
            "properties": {
                "commands": {"type": "string", "description": "The command that needs to be executed."},
                "explaination": {"type": "string", "description": "A short explaination of this task, along with the `command` in the Markdown format"}
            },
            "required": ["commands", "explaination"]
        }
    }
}

start_server = {
    "type": "function",
    "function": {
        "name": "start_server",
        "description": "Start the server at port 8000 for backend applications or 3000 for frontend applications. Install dependencies if needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "application_port": {"type": "integer", "description": "The port number at which the application is being run"},
                "type": {"type": "string", "enum": ["backend", "frontend", "background", "design"], "description": "The type of the service to start (backend, frontend, background worker)"},
                "start_server_command": {"type": "string", "description": "The command to run the server, or install dependencies, etc."},
                "explaination": {"type": "string", "description": "A short explaination of this task, along with the `command` in the Markdown format"}
            },
            "required": ["container_port", "start_server_command", "explaination"]
        }
    }
}

get_github_access_token = {
    "type": "function",
    "function": {
        "name": "get_github_access_token",
        "description": "Call this function to get the Github access token",
    }
}

# tools = [save_prd, get_prd, save_features, save_personas, design_schema, generate_tickets, write_code_file, read_code_file]

tools_code = [save_prd, get_prd, execute_command, start_server, \
              get_github_access_token, \
              checklist_tickets, update_checklist_ticket, \
              get_next_ticket, get_pending_tickets, \
              create_implementation, get_implementation, update_implementation, \
              implement_ticket]

tools_product = [save_prd, get_prd, save_features, save_personas, extract_features, extract_personas, design_schema, generate_tickets]

tools_ticket = [execute_command, get_prd, get_implementation]

tools_design = [get_prd, execute_command, start_server, get_github_access_token]