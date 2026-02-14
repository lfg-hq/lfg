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
        "description": "Call this function to generate the tickets for the project. This is based of the referred PRD or technical analysis or provided context in markdown format. \
                        This will include user-story and UI Requirements, and Acceptance Criteria. If creating tickets from a PRD, always pass the source_document_id to link tickets to the PRD.",
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
                            "dependencies": {"type": "array", "items": {"type": "string"}, "description": "List of ticket dependencies using 1-based position numbers (e.g., ['1', '2'] means this ticket depends on the 1st and 2nd tickets in this batch). Use empty array [] if no dependencies."},
                            "priority": {"type": "string", "enum": ["High", "Medium", "Low"]},
                            "acceptance_criteria": {"type": "array", "items": {"type": "string"}, "description": "List of testable acceptance criteria. Always provide at least 2-3 per ticket."},
                            "complexity": {"type": "string", "enum": ["simple", "medium", "complex"], "description": "Estimated complexity of the ticket"},
                            "details": {"type": "object", "description": "Technical context: files to modify, patterns to follow, dependencies to install, etc."}
                        },
                        "required": ["name", "description", "role", "dependencies", "priority"]
                    }
                },
                "source_document_id": {
                    "type": "integer",
                    "description": "The ID of the PRD or document these tickets are being created from. Use this to link tickets to their source document."
                },
                "source_document_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "IDs of PRDs/documents these tickets are being created from. Links all to each ticket. Use this when tickets reference multiple documents (e.g. a PRD and a technical plan)."
                },
                "conversation_id": {
                    "type": "integer",
                    "description": "The ID of the current conversation. Use this to link tickets to the conversation they were created in for filtering purposes."
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

get_ticket_details = {
    "type": "function",
    "function": {
        "name": "get_ticket_details",
        "description": "Get full ticket state including status, description, notes, acceptance_criteria, todos, linked documents, and recent execution logs. Use this to understand a ticket before updating, retrying, or diagnosing issues.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "integer",
                    "description": "The ID of the ticket to get details for"
                }
            },
            "required": ["ticket_id"]
        }
    }
}

set_project_stack = {
    "type": "function",
    "function": {
        "name": "set_project_stack",
        "description": "Set the technology stack for the current project. Call this BEFORE creating tickets when you've determined the tech stack (from PRD, user request, or technical spec). This configures the workspace with the correct install commands, dev server, port, and bootstrap scripts.",
        "parameters": {
            "type": "object",
            "properties": {
                "stack": {
                    "type": "string",
                    "enum": ["nextjs", "astro", "python-django", "python-fastapi", "go", "rust", "ruby-rails", "custom"],
                    "description": "Technology stack identifier. Use 'custom' if the stack is not in the list."
                }
            },
            "required": ["stack"]
        }
    }
}

get_project_dashboard = {
    "type": "function",
    "function": {
        "name": "get_project_dashboard",
        "description": "Get a dashboard view of the project: all tickets grouped by status, completion percentage, and list of project documents. Use this at the start of every conversation to assess project state.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}

get_ticket_execution_log = {
    "type": "function",
    "function": {
        "name": "get_ticket_execution_log",
        "description": "Read execution log entries (commands, AI responses) for a ticket. Use this to diagnose failures, understand what happened during execution, and decide whether to retry.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "integer",
                    "description": "The ID of the ticket to get logs for"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of log entries to return (default 20)",
                    "default": 20
                },
                "log_type": {
                    "type": "string",
                    "enum": ["all", "command", "ai_response", "user_message"],
                    "description": "Filter logs by type. Use 'all' for everything (default)",
                    "default": "all"
                }
            },
            "required": ["ticket_id"]
        }
    }
}

retry_ticket = {
    "type": "function",
    "function": {
        "name": "retry_ticket",
        "description": "Reset a failed or blocked ticket, optionally append additional context, and re-queue it for execution. Use this after diagnosing failures via get_ticket_execution_log.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "integer",
                    "description": "The ID of the ticket to retry"
                },
                "additional_context": {
                    "type": "string",
                    "description": "Optional additional context or instructions to append to the ticket description before retrying (e.g., 'Use port 3001 instead of 3000', 'Skip database seeding step')"
                }
            },
            "required": ["ticket_id"]
        }
    }
}

schedule_tickets = {
    "type": "function",
    "function": {
        "name": "schedule_tickets",
        "description": "Schedule tickets for execution with dependency awareness. Checks if each ticket's dependencies are satisfied before queueing. Use this instead of queue_ticket_execution when tickets have dependencies.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticket_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of ticket IDs to schedule for execution"
                },
                "strategy": {
                    "type": "string",
                    "enum": ["sequential", "parallel", "dependency_wave"],
                    "description": "Scheduling strategy: 'sequential' queues only the first ready ticket, 'parallel' queues all ready tickets at once, 'dependency_wave' queues all tickets whose dependencies are met (default)",
                    "default": "dependency_wave"
                }
            },
            "required": ["ticket_ids"]
        }
    }
}

update_ticket_details = {
    "type": "function",
    "function": {
        "name": "update_ticket_details",
        "description": "Update ticket fields: description, acceptance_criteria, priority, complexity, status, or append notes. Notes are appended with a timestamp, never replaced. Use this for enriching tickets with more detail or correcting information.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "integer",
                    "description": "The ID of the ticket to update"
                },
                "description": {
                    "type": "string",
                    "description": "New ticket description (replaces existing)"
                },
                "acceptance_criteria": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of testable acceptance criteria"
                },
                "priority": {
                    "type": "string",
                    "enum": ["High", "Medium", "Low"],
                    "description": "Ticket priority"
                },
                "complexity": {
                    "type": "string",
                    "enum": ["simple", "medium", "complex"],
                    "description": "Estimated ticket complexity"
                },
                "status": {
                    "type": "string",
                    "enum": ["open", "in_progress", "review", "done", "failed", "blocked"],
                    "description": "Ticket status"
                },
                "notes": {
                    "type": "string",
                    "description": "Notes to append (with timestamp) to existing notes, not replace"
                }
            },
            "required": ["ticket_id"]
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
        "description": "Execute a shell command inside the remote workspace via SSH. Use this for writing files, installing dependencies, running Prisma migrations, and verifying the app. The workspace is automatically determined from execution context.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to run inside /root. Favor heredocs for file writes and descriptive scripts."
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
                    }
    }
}

new_dev_sandbox = {
    "type": "function",
    "function": {
        "name": "new_dev_sandbox",
        "description": "Clone the Next.js template project and start the dev server on the remote workspace. Returns connection details plus recent logs.",
        "parameters": {
            "type": "object",
            "properties": {
                "workspace_id": {
                    "type": "string",
                    "description": "Workspace identifier for the remote VM."
                },
                "log_tail_lines": {
                    "type": "integer",
                    "description": "Number of lines to tail from /root/project/dev.log after startup (default 60)."
                },
                "environment": {
                    "type": "string",
                    "description": "Optional label describing the environment context (e.g., 'feature-update', 'hotfix')."
                }
            },
            "required": ["workspace_id"],
                    }
    }
}

queue_ticket_execution = {
    "type": "function",
    "function": {
        "name": "queue_ticket_execution",
        "description": "Queue all open agent tickets for background execution in creation order. This schedules a Django-Q worker to process tickets sequentially and stream progress updates. If no ticket_ids are provided, automatically queues all open agent tickets for the project.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticket_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Optional: Explicit list of ticket IDs to execute. If omitted, defaults to all open agent tickets."
                }
            }
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
                            "path": {"type": "string", "description": "Full path to the file (e.g., '/root/project/src/components/index.tsx')"},
                            "action": {"type": "string", "enum": ["created", "modified", "deleted"], "description": "What was done to the file"}
                        },
                        "required": ["filename", "path"]
                    },
                    "description": "List of files that were created, modified, or deleted with their full paths"
                }
            },
            "required": ["ticket_id", "summary"],
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
                    }
    }
}

run_code_server = {
    "type": "function",
    "function": {
        "name": "run_code_server",
        "description": "Execute code/commands via SSH on the remote server and start a development server. This will run the specified command and make the app available at the given port. The app URL will be opened in the artifacts browser panel.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute (e.g., 'cd /root/project && npm run dev'). Default: 'cd /root/project && npm run dev'"
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
                    }
    }
}

ask_codebase = {
    "type": "function",
    "function": {
        "name": "ask_codebase",
        "description": "Ask questions about the indexed codebase or get detailed context for creating tickets. Use this to: (1) Answer user questions about how something works in the codebase, (2) Find where specific functionality is implemented, (3) Get detailed context to create specific and accurate tickets, (4) Understand code patterns and architecture. Returns relevant code snippets, file paths, function names, and implementation details.",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask about the codebase (e.g., 'How does authentication work?', 'Where is the payment processing implemented?', 'What API endpoints exist for user management?')"
                },
                "intent": {
                    "type": "string",
                    "enum": ["answer_question", "ticket_context", "find_implementation"],
                    "description": "The purpose of the query: 'answer_question' to answer a user's question about the code, 'ticket_context' to get detailed context for creating a ticket, 'find_implementation' to locate where something is implemented. Defaults to 'answer_question'."
                },
                "include_code_snippets": {
                    "type": "boolean",
                    "description": "Whether to include actual code snippets in the response (default: true)"
                }
            },
            "required": ["question"]
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
                    }
    }
}

# Technology lookup tool
lookup_technology_specs = {
    "type": "function",
    "function": {
        "name": "lookup_technology_specs",
        # "description": "Look up technology specifications before creating technical analysis. Returns tech name, provider, description, documentation URL, and rationale. Available categories: image_generation, text_generation, embeddings, payments, authentication, database, vector_database, file_storage, cdn, hosting_frontend, hosting_backend, containers, orchestration, analytics, email_transactional, email_marketing, framework_frontend, framework_backend, realtime, search, monitoring, cache, queue. Use 'all' to get everything.",
        "description": "Look up technology specifications before creating technical analysis. Use this to call web search and look up more information",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "The technology category to look up (e.g., 'payments', 'file_storage', 'database'). Use 'all' to get all categories."
                }
            },
            "required": ["category"],
                    }
    }
}

generate_design_preview = {
    "type": "function",
    "function": {
        "name": "generate_design_preview",
        "description": "Generate a rich, visually polished design preview for a feature. Creates professional-quality mockups with modern UI patterns, smooth animations, and proper responsive behavior. For web: fully responsive from mobile to desktop. For mobile (iOS): native iPhone app styling with iOS design patterns.",
        "parameters": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["web", "mobile"],
                    "description": "Target platform. 'web' = responsive website (mobile-first, works on all screen sizes). 'mobile' = native iOS iPhone app design (fixed 390x844 viewport, iOS design patterns, SF Pro font, native iOS components)."
                },
                "feature_name": {
                    "type": "string",
                    "description": "Name of the feature being designed (e.g., 'Authentication', 'Dashboard', 'User Profile', 'Settings')"
                },
                "feature_description": {
                    "type": "string",
                    "description": "Brief description of what this feature does and its purpose in the application"
                },
                "explainer": {
                    "type": "string",
                    "description": "Detailed explanation of how the feature works, including user interactions, navigation flow, and key functionality. List the screens needed for this feature"
                },
                "css_style": {
                    "type": "string",
                    "description": "Complete, production-quality CSS stylesheet. MUST include: (1) CSS custom properties for colors, spacing, typography (2) Modern design tokens with cohesive color palette (3) For web: mobile-first responsive breakpoints (@media min-width: 640px, 768px, 1024px, 1280px) (4) For mobile: iOS-specific styling with -webkit prefixes, safe-area-inset padding (5) Smooth transitions and micro-animations (transform, opacity transitions) (6) Box shadows, border-radius, gradients for depth (7) Proper typography scale with font-weights (8) Hover/focus/active states for interactive elements (9) Flexbox/Grid layouts"
                },
                "common_elements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "element_id": {
                                "type": "string",
                                "description": "Unique identifier for this element (e.g., 'main-header', 'main-footer', 'left-sidebar', 'top-nav', 'tab-bar' for mobile)"
                            },
                            "element_type": {
                                "type": "string",
                                "enum": ["header", "footer", "sidebar", "nav", "logo", "banner", "breadcrumb", "toolbar", "tab-bar", "status-bar"],
                                "description": "Type of common element. For mobile: use 'tab-bar' for bottom navigation, 'status-bar' for iOS status bar"
                            },
                            "element_name": {
                                "type": "string",
                                "description": "Display name for this element (e.g., 'Main Header', 'Footer Navigation', 'Left Sidebar', 'iOS Tab Bar')"
                            },
                            "html_content": {
                                "type": "string",
                                "description": "Rich, polished HTML content. Include: SVG icons (inline or from a CDN like Heroicons/Lucide), proper semantic HTML, ARIA labels for accessibility, realistic placeholder content. For mobile: use iOS-style components (large titles, rounded cards, SF Symbols-style icons)."
                            },
                            "position": {
                                "type": "string",
                                "enum": ["top", "bottom", "left", "right", "fixed-top", "fixed-bottom"],
                                "description": "Where this element is positioned in the layout"
                            },
                            "applies_to": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of page_ids this element applies to. Use ['all'] to apply to all pages, or specific page_ids like ['dashboard', 'settings']"
                            },
                            "exclude_from": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional: List of page_ids to exclude this element from (e.g., exclude header from login page)"
                            }
                        },
                        "required": ["element_id", "element_type", "element_name", "html_content", "position", "applies_to"]
                    },
                    "description": "Array of common/shared elements like header, footer, sidebar, navigation that are reused across pages. These are rendered separately and composed with page content."
                },
                "pages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "page_id": {
                                "type": "string",
                                "description": "Unique identifier for this page (e.g., 'login', 'register', 'forgot-password')"
                            },
                            "page_name": {
                                "type": "string",
                                "description": "Display name of the page (e.g., 'Login Page', 'Registration Form')"
                            },
                            "html_content": {
                                "type": "string",
                                "description": "Rich, visually polished main content HTML. MUST include: (1) Realistic placeholder content (real names, descriptions, not 'Lorem ipsum') (2) SVG icons from Heroicons/Lucide or inline SVGs (3) Proper semantic HTML (section, article, nav, etc.) (4) Visual hierarchy with headings, subtext, badges (5) Cards with shadows and rounded corners (6) Buttons with proper styling and icons (7) Form inputs with labels, placeholders, validation states (8) Images using placeholder services (picsum.photos, ui-avatars.com) (9) Grid/flex layouts for responsive content. Do NOT include header/footer - those are in common_elements."
                            },
                            "page_type": {
                                "type": "string",
                                "enum": ["screen", "modal", "drawer", "popup", "toast", "sheet"],
                                "description": "Type of UI component. For mobile: 'sheet' for iOS bottom sheets, 'modal' for centered modals"
                            },
                            "include_common_elements": {
                                "type": "boolean",
                                "description": "Whether to include common elements (header, footer, etc.) for this page. Default true. Set false for modals, popups, or standalone pages."
                            },
                            "navigates_to": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "target_page_id": {
                                            "type": "string",
                                            "description": "The page_id this navigation leads to"
                                        },
                                        "trigger": {
                                            "type": "string",
                                            "description": "What triggers this navigation (e.g., 'Click Submit button', 'Click Forgot Password link')"
                                        },
                                        "condition": {
                                            "type": "string",
                                            "description": "Optional condition for this navigation (e.g., 'On successful login', 'If validation fails')"
                                        }
                                    },
                                    "required": ["target_page_id", "trigger"]
                                },
                                "description": "List of pages this page can navigate to within the same feature"
                            }
                        },
                        "required": ["page_id", "page_name", "html_content", "page_type"]
                    },
                    "description": "Array of page content partials. Each page contains only the main content - common elements are composed automatically based on common_elements configuration."
                },
                "feature_connections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "from_page_id": {
                                "type": "string",
                                "description": "The page_id where navigation starts"
                            },
                            "to_feature": {
                                "type": "string",
                                "description": "The feature_name this navigation leads to (e.g., 'Dashboard', 'Settings')"
                            },
                            "to_page_id": {
                                "type": "string",
                                "description": "Optional: specific page_id in the target feature to navigate to"
                            },
                            "trigger": {
                                "type": "string",
                                "description": "What triggers this cross-feature navigation"
                            },
                            "condition": {
                                "type": "string",
                                "description": "Optional condition for this navigation"
                            }
                        },
                        "required": ["from_page_id", "to_feature", "trigger"]
                    },
                    "description": "List of connections from this feature to other features in the application"
                },
                "entry_page_id": {
                    "type": "string",
                    "description": "The page_id that serves as the entry point for this feature"
                },
                "canvas_position": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number", "description": "X position on the design canvas"},
                        "y": {"type": "number", "description": "Y position on the design canvas"}
                    },
                    "description": "Optional: suggested position for this feature on the design canvas"
                }
            },
            "required": ["platform", "feature_name", "feature_description", "explainer", "css_style", "common_elements", "pages", "entry_page_id"],
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
              get_linear_issues, get_linear_issue_details, queue_ticket_execution, lookup_technology_specs]

tools_product_ = [get_file_list, get_codebase_summary, search_existing_code, get_file_content, create_tickets, get_pending_tickets, \
                 connect_notion, search_notion, get_notion_page, list_notion_databases, query_notion_database, \
                 get_linear_issues, get_linear_issue_details]

tools_product = [
    # Project state
    get_file_list,
    get_file_content,
    get_project_dashboard,
    set_project_stack,
    # Documents
    create_prd,
    get_prd,
    create_implementation,
    get_implementation,
    extract_features,
    extract_personas,
    # Tickets
    create_tickets,
    get_pending_tickets,
    get_ticket_details,
    update_ticket,
    update_ticket_details,
    update_all_tickets,
    # Orchestration
    queue_ticket_execution,
    schedule_tickets,
    retry_ticket,
    get_ticket_execution_log,
    # Codebase
    search_existing_code,
    get_codebase_summary,
    ask_codebase,
    # Research
    lookup_technology_specs,
]

tools_turbo_ = [
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
    queue_ticket_execution,
    lookup_technology_specs
]

# Tool for getting existing environment variables (OpenAI format)
get_project_env_vars = {
    "type": "function",
    "function": {
        "name": "get_project_env_vars",
        "description": "Get the list of environment variables configured for this project. Returns variable names, whether they have values set, and their descriptions. Does NOT return actual secret values - only metadata. Use this to check what env vars already exist before registering new ones.",
        "parameters": {
            "type": "object",
            "properties": {
                "include_values": {
                    "type": "boolean",
                    "description": "If true, include masked values for non-secret variables. Default false."
                }
            },
            "required": []
        }
    }
}

# Tool for registering required environment variables (OpenAI format)
register_required_env_vars = {
    "type": "function",
    "function": {
        "name": "register_required_env_vars",
        "description": "Register required environment variables that the application needs to run. Use this when you detect that new environment variables are needed (e.g., from package installation, config files, API integrations). This will create placeholder entries in the project's environment settings (marked as missing) and create a ticket to remind the user to provide values.",
        "parameters": {
            "type": "object",
            "properties": {
                "env_vars": {
                    "type": "array",
                    "description": "List of environment variables that are required",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string",
                                "description": "Environment variable name (e.g., DATABASE_URL, API_KEY, AUTH_SECRET)"
                            },
                            "description": {
                                "type": "string",
                                "description": "Description of what this variable is for and how to obtain it"
                            },
                            "example": {
                                "type": "string",
                                "description": "Example value format (e.g., 'postgresql://user:pass@host/db', 'sk-xxxx')"
                            },
                            "is_secret": {
                                "type": "boolean",
                                "description": "Whether this is a sensitive value that should be masked. Default true."
                            }
                        },
                        "required": ["key", "description"]
                    }
                },
                "reason": {
                    "type": "string",
                    "description": "Brief explanation of why these environment variables are needed (e.g., 'Required for NextAuth.js authentication', 'Needed for Stripe payment integration')"
                },
                "create_ticket": {
                    "type": "boolean",
                    "description": "Whether to create a ticket reminding the user to provide values. Default true."
                }
            },
            "required": ["env_vars", "reason"]
        }
    }
}

# Tool for agent to create a single ticket (OpenAI format)
agent_create_ticket = {
    "type": "function",
    "function": {
        "name": "agent_create_ticket",
        "description": "Create a single ticket/task for the project. Use this when you need to create a follow-up task, document something that needs to be done later, or flag an issue for the user to address.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Short, descriptive title for the ticket (e.g., 'Configure SendGrid API credentials', 'Add error handling for payment flow')"
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of what needs to be done. Can include markdown formatting, code snippets, or step-by-step instructions."
                },
                "priority": {
                    "type": "string",
                    "enum": ["High", "Medium", "Low"],
                    "description": "Priority level. Use High for blockers/critical issues, Medium for important tasks, Low for nice-to-haves."
                },
                "status": {
                    "type": "string",
                    "enum": ["open", "in_progress", "done", "blocked"],
                    "description": "Initial status. Usually 'open' for new tickets. Default: open"
                }
            },
            "required": ["name", "description"]
        }
    }
}

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
    broadcast_to_user,
    get_project_env_vars,
    register_required_env_vars,
    agent_create_ticket
]

# Anthropic native format for direct API calls
edit_design_screen_anthropic = {
    "name": "edit_design_screen",
    "description": "Edit a specific component of the design. Can edit either a page's main content partial OR a common element (header, footer, sidebar). Use edit_target to specify what you're editing.",
    "input_schema": {
        "type": "object",
        "properties": {
            "edit_target": {
                "type": "string",
                "enum": ["page_content", "common_element"],
                "description": "What type of component you're editing: 'page_content' for the page's main content partial, 'common_element' for shared elements like header/footer/sidebar"
            },
            "element_id": {
                "type": "string",
                "description": "Required when edit_target is 'common_element'. The element_id of the common element to edit (e.g., 'main-header', 'main-footer', 'left-sidebar')"
            },
            "updated_html": {
                "type": "string",
                "description": "The complete updated HTML content. For page_content: the main content partial only (no header/footer). For common_element: the updated common element HTML."
            },
            "updated_css": {
                "type": "string",
                "description": "Optional: Updated CSS if the changes require new styles. Only include if CSS changes are needed."
            },
            "change_summary": {
                "type": "string",
                "description": "Brief summary of what was changed in the design"
            }
        },
        "required": ["edit_target", "updated_html", "change_summary"]
    }
}

# OpenAI format (kept for compatibility)
edit_design_screen = {
    "type": "function",
    "function": {
        "name": "edit_design_screen",
        "description": "Edit a specific component of the design. Can edit either a page's main content partial OR a common element (header, footer, sidebar). Use edit_target to specify what you're editing.",
        "parameters": {
            "type": "object",
            "properties": {
                "edit_target": {
                    "type": "string",
                    "enum": ["page_content", "common_element"],
                    "description": "What type of component you're editing: 'page_content' for the page's main content partial, 'common_element' for shared elements like header/footer/sidebar"
                },
                "element_id": {
                    "type": "string",
                    "description": "Required when edit_target is 'common_element'. The element_id of the common element to edit (e.g., 'main-header', 'main-footer', 'left-sidebar')"
                },
                "updated_html": {
                    "type": "string",
                    "description": "The complete updated HTML content. For page_content: the main content partial only (no header/footer). For common_element: the updated common element HTML."
                },
                "updated_css": {
                    "type": "string",
                    "description": "Optional: Updated CSS if the changes require new styles. Only include if CSS changes are needed."
                },
                "change_summary": {
                    "type": "string",
                    "description": "Brief summary of what was changed in the design"
                }
            },
            "required": ["edit_target", "updated_html", "change_summary"],
                    }
    }
}

# Tool for generating a single screen from a description
generate_single_screen_anthropic = {
    "name": "generate_single_screen",
    "description": "Generate a rich, visually polished single screen/page for an existing feature. Match the existing feature's design language and platform (web/mobile). Create professional-quality mockup with modern UI patterns.",
    "input_schema": {
        "type": "object",
        "properties": {
            "page_id": {
                "type": "string",
                "description": "Unique identifier for this page (e.g., 'settings-page', 'user-profile', 'analytics-dashboard')"
            },
            "page_name": {
                "type": "string",
                "description": "Display name of the page (e.g., 'Settings Page', 'User Profile', 'Analytics Dashboard')"
            },
            "html_content": {
                "type": "string",
                "description": "Rich, visually polished main content HTML matching the feature's existing style. MUST include: (1) Realistic placeholder content (2) SVG icons (Heroicons/Lucide) (3) Proper semantic HTML (4) Visual hierarchy with headings, subtext, badges (5) Cards with shadows and rounded corners (6) Styled buttons with icons (7) Form inputs with proper styling (8) Images from placeholder services (9) Grid/flex layouts. Do NOT include header/footer."
            },
            "page_type": {
                "type": "string",
                "enum": ["screen", "modal", "drawer", "popup", "toast", "sheet"],
                "description": "Type of UI component. For mobile: 'sheet' for iOS bottom sheets"
            },
            "css_additions": {
                "type": "string",
                "description": "Optional: Additional CSS styles specific to this page. Include transitions, hover states, and responsive adjustments. Will be appended to the feature's existing CSS."
            }
        },
        "required": ["page_id", "page_name", "html_content", "page_type"]
    }
}

tools_turbo = [
    get_file_content,
    get_pending_tickets,
    generate_design_preview
]

tools_design = [
    get_prd,
    execute_command,
    start_server,
    generate_design_preview
]

tools_design_chat = [
    edit_design_screen_anthropic
]

tools_generate_single_screen = [
    generate_single_screen_anthropic
]
