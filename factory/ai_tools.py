create_prd = {
    "type": "function",
    "function": 
        {
            "name": "create_prd",
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

stream_prd_content = {
    "type": "function",
    "function": {
        "name": "stream_prd_content",
        "description": "Stream PRD content chunk by chunk to provide live updates while generating the PRD. Call this function multiple times during PRD generation to show progress to the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "content_chunk": {
                    "type": "string",
                    "description": "A chunk of PRD content to stream (e.g., a section or paragraph)"
                },
                "is_complete": {
                    "type": "boolean",
                    "description": "Whether this is the final chunk of the PRD"
                }
            },
            "required": ["content_chunk", "is_complete"],
            "additionalProperties": False,
        }
    }
}

stream_implementation_content = {
    "type": "function",
    "function": {
        "name": "stream_implementation_content",
        "description": "Stream implementation content chunk by chunk to provide live updates while generating the implementation. Call this function multiple times during implementation generation to show progress to the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "content_chunk": {
                    "type": "string",
                    "description": "A chunk of implementation content to stream (e.g., a section or paragraph)"
                },
                "is_complete": {
                    "type": "boolean",
                    "description": "Whether this is the final chunk of the implementation"
                }
            },
            "required": ["content_chunk", "is_complete"],
            "additionalProperties": False,
        }
    }
}

stream_document_content = {
    "type": "function",
    "function": {
        "name": "stream_document_content",
        "description": "Stream generic document content chunk by chunk to provide live updates while generating any type of document (e.g., competitor analysis, market research, design docs, etc.). Use this for any document that is NOT a PRD or Implementation Plan.",
        "parameters": {
            "type": "object",
            "properties": {
                "content_chunk": {
                    "type": "string",
                    "description": "A chunk of document content to stream (e.g., a section or paragraph)"
                },
                "is_complete": {
                    "type": "boolean",
                    "description": "Whether this is the final chunk of the document"
                },
                "document_type": {
                    "type": "string",
                    "description": "The type of document being streamed (e.g., 'competitor_analysis', 'market_research', 'design_doc', 'api_spec', etc.). Default to 'document' if unsure."
                },
                "document_name": {
                    "type": "string",
                    "description": "The name/title of the document being streamed (e.g., 'Competitor Analysis Report', 'API Specification', etc.)"
                }
            },
            "required": ["content_chunk", "is_complete", "document_type", "document_name"],
            "additionalProperties": False,
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
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

save_personas = {
    "type": "function",
    "function": {
        "name": "save_personas",
        "description": "Call this function to save the personas from the PRD into a different list",
        "parameters": {
            "type": "object",
            "properties": {}
        }
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
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
    }

get_personas = {
        "type": "function",
        "function":
            {
                "name": "get_personas",
                "description": "Call this function to check if Personas already exist. If they do, it will return the list of personas",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
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

create_tickets = {
    "type": "function",
    "function": {
        "name": "create_tickets",
        "description": "Call this function to generate the checklist tickets for the project. You will review the implementation plan for this.",
        "parameters": {
            "type": "object",
            "properties": {
                "tickets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string", "description": "Detailed description as to all the details that needs to be implemented"},
                            "role": {"type": "string", "enum": ["agent", "user"]},
                            "ui_requirements": {"type": "object", "description": "UI requirements for this ticket if applicable"},
                            "component_specs": {"type": "object", "description": "Component specifications for this ticket if applicable"},
                            "acceptance_criteria": {"type": "array", "items": {"type": "string"}, "description": "Acceptance criteria for this ticket"},
                            "dependencies": {"type": "array", "items": {"type": "string"}, "description": "Is this ticket dependent on any other ticket? If yes, pass the ticket id"},
                            "priority": {"type": "string", "enum": ["High", "Medium", "Low"]}
                        },
                        "required": ["name", "description", "role", "ui_requirements", "component_specs", "acceptance_criteria", "dependencies", "priority"]
                    }
                }
            },
            "required": ["tickets"]
        }
    }
}

update_ticket = {
    "type": "function",
    "function": {
        "name": "update_ticket",
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
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

get_pending_tickets = {
    "type": "function",
    "function": {
        "name": "get_pending_tickets",
        "description": "Call this function to get the pending tickets for the project",
        "parameters": {
            "type": "object",
            "properties": {}
        }
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
                        "project_name": {"type": "string", "description": "Pass the name of the application"},
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
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

copy_boilerplate_code = {
    "type": "function",
    "function": {
        "name": "copy_boilerplate_code",
        "description": "Call this function to copy over the boilerplate code from the project",
        "parameters": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "The name of the project to copy the boilerplate code from"}
            },
            "required": ["project_name"]
        }
    }
}

# tools = [create_prd, get_prd, save_features, save_personas, design_schema, generate_tickets, write_code_file, read_code_file]

capture_name = {
    "type": "function",
    "function": {
        "name": "capture_name",
        "description": "Save or retrieve the project name. Use this to store the project name when confirmed by the user or to get the stored project name.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["save", "get"],
                    "description": "Action to perform: 'save' to store project name, 'get' to retrieve project name"
                },
                "project_name": {
                    "type": "string",
                    "description": "The project name to save (required when action is 'save')"
                }
            },
            "required": ["action"],
            "additionalProperties": False,
        }
    }
}

get_file_list = {
    "type": "function",
    "function": {
        "name": "get_file_list",
        "description": "Call this function to get the list of files in the project",
        "parameters": {
            "type": "object",
            "properties": {
                "file_type": {"type": "string", "enum": ["prd", "implementation", "design", "all"]},
                "limit": {"type": "integer", "description": "The number of files to return", "default": 10}
            },
            "required": ["file_type", "limit"]
        }
    }
}

get_file_content = {
    "type": "function",
    "function": {
        "name": "get_file_content",
        "description": "Call this function to get the content of one or more files in the project (max 5 files)",
        "parameters": {
            "type": "object",
            "properties": {
                "file_ids": {
                    "oneOf": [
                        {"type": "integer", "description": "A single file ID"},
                        {"type": "array", "items": {"type": "integer"}, "maxItems": 5, "description": "List of file IDs (max 5)"}
                    ],
                    "description": "The ID(s) of the file(s) to get the content of"
                }
            },
            "required": ["file_ids"]
        }
    }
}

tools_code = [get_prd, start_server, \
              get_github_access_token, \
              create_tickets, update_ticket, \
              get_next_ticket, get_pending_tickets, \
              create_implementation, get_implementation, update_implementation, stream_implementation_content, \
              stream_document_content, copy_boilerplate_code, capture_name]

tools_product = [get_file_list, get_file_content, create_tickets, get_pending_tickets]

tools_turbo = [get_prd, create_tickets, get_pending_tickets, update_ticket, execute_command]

# Codebase indexing tools
index_repository = {
    "type": "function",
    "function": {
        "name": "index_repository",
        "description": "Index a GitHub repository for the current project to enable context-aware feature development. This analyzes the codebase structure, extracts code patterns, and creates embeddings for intelligent code search.",
        "parameters": {
            "type": "object",
            "properties": {
                "github_url": {
                    "type": "string", 
                    "description": "The GitHub repository URL to index (e.g., https://github.com/owner/repo)"
                },
                "branch": {
                    "type": "string",
                    "description": "Git branch to index (defaults to 'main')"
                },
                "force_reindex": {
                    "type": "boolean",
                    "description": "Whether to force a complete reindex even if already indexed"
                }
            },
            "required": ["github_url"],
            "additionalProperties": False,
        }
    }
}

get_codebase_context = {
    "type": "function",
    "function": {
        "name": "get_codebase_context",
        "description": "Get relevant codebase context for a feature request or question. This searches the indexed codebase to find similar implementations, patterns, and architectural guidance.",
        "parameters": {
            "type": "object", 
            "properties": {
                "feature_description": {
                    "type": "string",
                    "description": "Description of the feature or functionality you want context for"
                },
                "search_type": {
                    "type": "string",
                    "enum": ["implementation", "patterns", "files", "all"],
                    "description": "Type of context to search for"
                }
            },
            "required": ["feature_description"],
            "additionalProperties": False,
        }
    }
}

search_existing_code = {
    "type": "function", 
    "function": {
        "name": "search_existing_code",
        "description": "Search for existing code implementations that are similar to what you want to build. Useful for finding patterns, reusable functions, and understanding current architecture.",
        "parameters": {
            "type": "object",
            "properties": {
                "functionality": {
                    "type": "string",
                    "description": "Description of the functionality to search for"
                },
                "chunk_types": {
                    "type": "array",
                    "items": {
                        "type": "string", 
                        "enum": ["function", "class", "file", "import"]
                    },
                    "description": "Types of code chunks to search (optional)"
                }
            },
            "required": ["functionality"],
            "additionalProperties": False,
        }
    }
}

get_repository_insights = {
    "type": "function",
    "function": {
        "name": "get_repository_insights",
        "description": "Get high-level insights about the indexed repository including languages used, architectural patterns, complexity distribution, and common dependencies.",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
    }
}

generate_codebase_summary = {
    "type": "function",
    "function": {
        "name": "generate_codebase_summary",
        "description": "Generate a comprehensive AI-powered summary of the entire codebase. This analyzes the complete AST structure and provides detailed information about: overall purpose and architecture, file organization, all functions/methods mapped by file, data models and structures, API endpoints, key dependencies, code flow, and entry points. Use this when you need a thorough understanding of what the codebase does and how it's organized.",
        "parameters": {
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "description": "Optional: AI model to use for summary generation (defaults to claude-3-5-sonnet)",
                }
            },
            "additionalProperties": False,
        }
    }
}

tools_ticket = [execute_command, get_prd, get_implementation, copy_boilerplate_code, start_server]

# Add codebase tools to appropriate tool sets
tools_codebase = [index_repository, get_codebase_context, search_existing_code, get_repository_insights, generate_codebase_summary]

tools_design = [get_prd, execute_command, start_server, get_github_access_token]