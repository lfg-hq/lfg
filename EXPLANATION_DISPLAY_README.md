# Tool Call Explanation Display Enhancement

## Overview
Enhanced the tool call functionality to display the actual explanation text instead of just showing `*` when AI provides an explanation for why it's using a particular tool.

## Changes Made

### 1. **coding/utils/ai_providers.py** - execute_tool_call function (lines 87-91)

#### Before:
```python
if explanation:
    logger.debug(f"Found explanation: {explanation}")
    # Return "*" to be yielded for explanations
    yielded_content = "*"
```

#### After:
```python
if explanation:
    logger.debug(f"Found explanation: {explanation}")
    # Return the actual explanation to be yielded with formatting
    # Add a newline before and after for better readability
    yielded_content = f"\n*{explanation}*\n"
```

## How It Works

1. **Tool Call with Explanation**: When the AI calls a tool and includes an explanation field:
   ```json
   {
     "tool": "execute_command",
     "arguments": {
       "command": "npm install",
       "explanation": "Installing project dependencies to ensure all required packages are available"
     }
   }
   ```

2. **Processing Flow**:
   - `execute_tool_call` extracts the explanation from the arguments
   - The explanation is formatted with italics (`*explanation*`) and newlines
   - The formatted explanation is returned as `yielded_content`

3. **Display Flow**:
   - OpenAI/Anthropic providers yield the explanation immediately (before tool execution)
   - The explanation appears in the chat stream
   - The explanation is included in `full_response` and saved to the database

4. **Result in Chat**:
   ```
   User: Please install the dependencies
   
   Assistant: I'll install the project dependencies for you.
   
   *Installing project dependencies to ensure all required packages are available*
   
   [execute_command animation/indicator]
   
   Command output: Successfully installed 47 packages...
   ```

## Benefits

1. **Transparency**: Users can see why the AI is performing each action
2. **Context**: Explanations provide context before tool execution
3. **Persistence**: Explanations are saved to the database and appear on page refresh
4. **Formatting**: Italicized text with spacing makes explanations visually distinct

## Note
The code handles both spellings: "explanation" and "explaination" (typo fallback) to ensure robustness.