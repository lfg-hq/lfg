write_file = {
    "type": "function",
    "function": {
        "name": "write_file",
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

read_file = {
    "type": "function",
    "function": {
        "name": "read_file",
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