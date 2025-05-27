feature_difference = {
    "type": "function",
    "function": {
        "name": "feature_difference",
        "description": "Extract the missing features from the provided list. Only the missing features",
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

persona_difference = {
    "type": "function",
    "function": {
        "name": "persona_difference",
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

generate_design_schema = {
    "type": "function",
    "function": {
        "name": "generate_design_schema",
        "description": "Return ONE complete, standalone HTML document for the style guide.",
        "parameters": {
            "type": "object",
            "properties": {
                "design_schema": {"type": "string"}
            },
            "required": ["design_schema"]
        }
    }   
}

generate_ticket_tools = {
    "type": "function",
    "function": {
        "name": "generate_ticket_tools",
        "description": "Generate tickets for a project based on the PRD and user input.",
        "parameters": {
            "type": "object",
            "properties": {
                "tickets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string", "description": "A detailed description of this task"},
                            "implementation_steps": {"type": "string", "description": "A detailed implementation steps for this task"},
                            "status": {"type": "string", "enum": ["Open", "In Progress", "Agent", "Closed",]},
                            "backend_tasks": {"type": "string", "description": "A detailed implementation steps for the backend tasks"},
                            "frontend_tasks": {"type": "string", "description": "A detailed implementation steps for the frontend tasks"},
                        },
                        "required": ["title", "description", "status", "backend_tasks", "frontend_tasks"]
                    }
                }
            },
            "required": ["tickets"]
        }
    }
}