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
        "description": "Call this function to generate the tickets for the project. This is based of the referred PRD or technical analysis or provided contenxt in markedown format \
                        This will include user-story and UI Requirements, and Acceptance Criteria",
        "parameters": {
            "type": "object",
            "properties": {
                "tickets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string", "description": "The user-story of the ticket to be implemented"},
                            "role": {"type": "string", "enum": ["agent", "user"]},
                            "dependencies": {"type": "array", "items": {"type": "string"}, "description": "Is this ticket dependent on any other ticket? If yes, pass the ticket id"},
                            "priority": {"type": "string", "enum": ["High", "Medium", "Low"]}
                        },
                        "required": ["name", "description", "role", "dependencies", "priority"]
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

update_all_tickets = {
    "type": "function",
    "function": {
        "name": "update_all_tickets",
        "description": "Call this function to update the status of all checklist tickets. You need to pass the status.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticket_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Optional explicit list of ticket IDs to execute. Defaults to all open agent tickets when omitted."
                },
                "status": {"type": "string", "enum": ["done", "in_progress", "agent", "open"]}
            },
            "required": ["ticket_ids", "status"]
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

ssh_command = {
    "type": "function",
    "function": {
        "name": "ssh_command",
        "description": "Execute a shell command inside the Magpie workspace via SSH. Use this for writing files, installing dependencies, running Prisma migrations, and verifying the app. The workspace is automatically determined from execution context.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to run inside /workspace. Favor heredocs for file writes and descriptive scripts."
                },
                "explanation": {
                    "type": "string",
                    "description": "Brief natural-language explanation of the command purpose and expected changes or outputs."
                },
                "timeout": {
                    "type": "integer",
                    "description": "Optional timeout for the command in seconds (default 300)."
                },
                "with_node_env": {
                    "type": "boolean",
                    "description": "Whether to load the Node.js environment helpers before running the command. Defaults to true."
                }
            },
            "required": ["command", "explanation"],
            "additionalProperties": False,
        }
    }
}

new_dev_sandbox = {
    "type": "function",
    "function": {
        "name": "new_dev_sandbox",
        "description": "Clone the Next.js template project and start the dev server on the Magpie workspace. Returns connection details plus recent logs.",
        "parameters": {
            "type": "object",
            "properties": {
                "workspace_id": {
                    "type": "string",
                    "description": "Workspace identifier for the Magpie VM."
                },
                "log_tail_lines": {
                    "type": "integer",
                    "description": "Number of lines to tail from /workspace/nextjs-app/dev.log after startup (default 60)."
                },
                "environment": {
                    "type": "string",
                    "description": "Optional label describing the environment context (e.g., 'feature-update', 'hotfix')."
                }
            },
            "required": ["workspace_id"],
            "additionalProperties": False,
        }
    }
}

queue_ticket_execution = {
    "type": "function",
    "function": {
        "name": "queue_ticket_execution",
        "description": "Queue all open agent tickets for background execution in creation order. This schedules a Django-Q worker to process tickets sequentially and stream progress updates.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticket_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Explicit list of ticket IDs to execute. Defaults to all open agent tickets when omitted."
                }
            },
            "required": ["ticket_ids"],
            "additionalProperties": False,
        }
    }
}

update_todo_status = {
    "type": "function",
    "function": {
        "name": "update_todo_status",
        "description": "Update the status of a todo by its todo_id. Use this to mark todos as in_progress, success, or fail as you work through them. Get the todo_id first.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "integer",
                    "description": "The ID of the ticket this todo belongs to"
                },
                "todo_id": {
                    "type": "integer",
                    "description": "The database ID of the todo to update (get this from get_ticket_todos)"
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "success", "fail"],
                    "description": "The new status for the todo"
                }
            },
            "required": ["ticket_id", "todo_id", "status"],
            "additionalProperties": False,
        }
    }
}

create_ticket_todos = {
    "type": "function",
    "function": {
        "name": "create_ticket_todos",
        "description": "Create todos for a ticket. Call this at the start of ticket implementation to break down the work into trackable todos.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "integer",
                    "description": "The ID of the ticket to create todos for"
                },
                "todos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {
                                "type": "string",
                                "description": "Todo description (what needs to be done)"
                            }
                        },
                        "required": ["description"]
                    },
                    "description": "Array of todo descriptions to create in order. They will be numbered 0, 1, 2... automatically."
                }
            },
            "required": ["ticket_id", "todos"],
            "additionalProperties": False,
        }
    }
}

get_ticket_todos = {
    "type": "function",
    "function": {
        "name": "get_ticket_todos",
        "description": "Get all todos for a ticket with their current status and order. Use this to see what todos exist and their progress.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "integer",
                    "description": "The ID of the ticket to get todos for"
                }
            },
            "required": ["ticket_id"],
            "additionalProperties": False,
        }
    }
}

record_ticket_summary = {
    "type": "function",
    "function": {
        "name": "record_ticket_summary",
        "description": "Record a summary of changes made during ticket execution. Use this instead of writing to .md files. Summaries are appended to the ticket's notes with timestamps, preserving previous entries. Call this at the end of ticket implementation to document what was done.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "integer",
                    "description": "The ID of the ticket to record the summary for"
                },
                "summary": {
                    "type": "string",
                    "description": "A concise summary of the changes made during ticket execution (files created/modified, features implemented, issues resolved, etc.)"
                },
                "files_modified": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string", "description": "Name of the file (e.g., 'index.tsx')"},
                            "path": {"type": "string", "description": "Full path to the file (e.g., '/workspace/nextjs-app/src/components/index.tsx')"},
                            "action": {"type": "string", "enum": ["created", "modified", "deleted"], "description": "What was done to the file"}
                        },
                        "required": ["filename", "path"]
                    },
                    "description": "List of files that were created, modified, or deleted with their full paths"
                }
            },
            "required": ["ticket_id", "summary"],
            "additionalProperties": False,
        }
    }
}

broadcast_to_user = {
    "type": "function",
    "function": {
        "name": "broadcast_to_user",
        "description": "Broadcast the message to the user. Use this to answer their requests or question, communicate progress, completion status, or when you need manual intervention. This is one-way communication - it informs the user but does not continue the conversation loop. Use this when: (0) When replying to user's request (1) Task is complete, (2) You've tried multiple times to fix an issue without success, (3) Manual intervention is needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The message to broadcast to the user"
                },
                "status": {
                    "type": "string",
                    "enum": ["progress", "complete", "blocked", "error"],
                    "description": "Status type: 'progress' for updates, 'complete' when done, 'blocked' when manual help needed, 'error' for failures"
                },
                "summary": {
                    "type": "object",
                    "properties": {
                        "completed_tasks": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of tasks that were completed"
                        },
                        "pending_issues": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of issues that still need attention"
                        },
                        "files_modified": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of files that were modified"
                        }
                    },
                    "description": "Optional structured summary of work done"
                }
            },
            "required": ["message", "status"],
            "additionalProperties": False,
        }
    }
}

run_code_server = {
    "type": "function",
    "function": {
        "name": "run_code_server",
        "description": "Execute code/commands via SSH on the remote Magpie server and start a development server. This will run the specified command and make the app available at the given port. The app URL will be opened in the artifacts browser panel.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute (e.g., 'cd /workspace/nextjs-app && npm run dev'). Default: 'cd /workspace/nextjs-app && npm run dev'"
                },
                "port": {
                    "type": "integer",
                    "description": "The port where the application will be running. Default: 3000"
                },
                "description": {
                    "type": "string",
                    "description": "A brief description of what this command does (e.g., 'Starting Next.js development server')"
                }
            },
            "required": [],
            "additionalProperties": False,
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
        "description": "Search the codebase vector store for specific code implementations using semantic search. Use this AFTER get_codebase_summary to find detailed implementations, patterns, similar functions, and specific code examples. This performs semantic search on the indexed code chunks to find relevant implementations based on functionality description.",
        "parameters": {
            "type": "object",
            "properties": {
                "functionality": {
                    "type": "string",
                    "description": "Description of the functionality or code pattern to search for (e.g., 'authentication middleware', 'database connection', 'API endpoint handlers')"
                },
                "chunk_types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["function", "class", "file", "import"]
                    },
                    "description": "Types of code chunks to search (optional, filters results by entity type)"
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

get_codebase_summary = {
    "type": "function",
    "function": {
        "name": "get_codebase_summary",
        "description": "Retrieve the comprehensive AI-generated summary of the entire codebase. This summary was created during indexing and includes: overall purpose and architecture, file organization, all functions/methods mapped by file, data models and structures, API endpoints, key dependencies, code flow, and entry points. Use this FIRST when you need to understand what the codebase does and how it's organized, then follow up with search_existing_code for specific implementation details.",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
    }
}

tools_ticket = [execute_command, get_prd, get_implementation, copy_boilerplate_code, start_server]

# Add codebase tools to appropriate tool sets
tools_codebase = [index_repository, get_codebase_context, search_existing_code, get_repository_insights, get_codebase_summary]

# Notion integration tools
connect_notion = {
    "type": "function",
    "function": {
        "name": "connect_notion",
        "description": "Test connection to Notion workspace using the configured API key",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
    }
}

search_notion = {
    "type": "function",
    "function": {
        "name": "search_notion",
        "description": "Search for pages and databases in Notion workspace. Use empty string or omit query to list ALL accessible pages. Returns a list of matching pages with their titles, IDs, and URLs.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query string to find pages and databases. Use empty string \"\" to list all accessible pages.",
                    "default": ""
                },
                "page_size": {
                    "type": "integer",
                    "description": "Number of results to return (default: 10, max: 100)",
                    "default": 10
                }
            },
            "additionalProperties": False,
        }
    }
}

get_notion_page = {
    "type": "function",
    "function": {
        "name": "get_notion_page",
        "description": "Retrieve the full content of a specific Notion page including all blocks and text. Use this to fetch Notion documentation, specs, or notes to use as context in your responses.",
        "parameters": {
            "type": "object",
            "properties": {
                "page_id": {
                    "type": "string",
                    "description": "The Notion page ID (can be obtained from search_notion results)"
                }
            },
            "required": ["page_id"],
            "additionalProperties": False,
        }
    }
}

list_notion_databases = {
    "type": "function",
    "function": {
        "name": "list_notion_databases",
        "description": "List all accessible databases in the Notion workspace",
        "parameters": {
            "type": "object",
            "properties": {
                "page_size": {
                    "type": "integer",
                    "description": "Number of results to return (default: 10, max: 100)",
                    "default": 10
                }
            },
            "additionalProperties": False,
        }
    }
}

query_notion_database = {
    "type": "function",
    "function": {
        "name": "query_notion_database",
        "description": "Query a specific Notion database and retrieve its entries/rows",
        "parameters": {
            "type": "object",
            "properties": {
                "database_id": {
                    "type": "string",
                    "description": "The Notion database ID (can be obtained from list_notion_databases)"
                },
                "page_size": {
                    "type": "integer",
                    "description": "Number of entries to return (default: 10, max: 100)",
                    "default": 10
                }
            },
            "required": ["database_id"],
            "additionalProperties": False,
        }
    }
}

# Linear integration tools
get_linear_issues = {
    "type": "function",
    "function": {
        "name": "get_linear_issues",
        "description": "Fetch all Linear issues/tickets accessible to the user. Returns issue details including title, description, status, assignee, priority, and links.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of issues to return (default: 50, max: 250)",
                    "default": 50
                },
                "team_id": {
                    "type": "string",
                    "description": "Optional team ID to filter issues by specific team"
                }
            },
            "additionalProperties": False,
        }
    }
}

get_linear_issue_details = {
    "type": "function",
    "function": {
        "name": "get_linear_issue_details",
        "description": "Get detailed information for a specific Linear issue including full description, comments, labels, subtasks, and relationships. Use this to get complete context about a ticket.",
        "parameters": {
            "type": "object",
            "properties": {
                "issue_id": {
                    "type": "string",
                    "description": "Linear issue ID or identifier (e.g., 'PED-8', 'ENG-123')"
                }
            },
            "required": ["issue_id"],
            "additionalProperties": False,
        }
    }
}

# Main tool lists
tools_code = [get_prd, start_server, \
              get_github_access_token, \
              create_tickets, update_ticket, \
              get_next_ticket, get_pending_tickets, \
              create_implementation, get_implementation, update_implementation, stream_implementation_content, \
              stream_document_content, copy_boilerplate_code, capture_name, \
              index_repository, get_codebase_context, search_existing_code, get_repository_insights, get_codebase_summary, \
              connect_notion, search_notion, get_notion_page, list_notion_databases, query_notion_database, \
              get_linear_issues, get_linear_issue_details, queue_ticket_execution]

tools_product = [get_file_list, get_codebase_summary, search_existing_code, get_file_content, create_tickets, get_pending_tickets, \
                 connect_notion, search_notion, get_notion_page, list_notion_databases, query_notion_database, \
                 get_linear_issues, get_linear_issue_details]

tools_turbo = [
    get_file_list,
    get_file_content,
    create_tickets,
    search_existing_code,
    get_pending_tickets,
    update_ticket,
    update_all_tickets,
    # provision_workspace,
    # ssh_command,
    # new_dev_sandbox,
    queue_ticket_execution
]

tools_builder = [
    get_file_list,
    get_file_content,
    get_pending_tickets,
    update_ticket,
    ssh_command,
    get_ticket_todos,
    create_ticket_todos,
    update_todo_status,
    run_code_server,
    record_ticket_summary,
    broadcast_to_user
]

tools_design = [get_prd, execute_command, start_server, get_github_access_token]
