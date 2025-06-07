# Tool Call Animation Debug Summary

This document explains the changes made to enable tool call animations in the chat interface, specifically for debugging the `execute_command` function animations.

## REAL AI TOOL CALL FLOW

When the AI (Anthropic/OpenAI) decides to use a tool like `execute_command`, here's the actual flow:

1. **AI Provider detects tool call** (`ai_providers.py`):
   - Line 356: Gets notification type via `get_notification_type_for_tool()`
   - Line 359-372: Sends early notification if tool is in mapping:
     ```python
     yield f"__NOTIFICATION__{
         "is_notification": True,
         "notification_type": "execute_command",
         "early_notification": True,
         "function_name": "execute_command"
     }__NOTIFICATION__"
     ```

2. **Tool executes** (`ai_providers.py`):
   - Line 410: Calls `execute_tool_call()`
   - Line 107: After execution, forces completion notification for certain tools
   - **IMPORTANT**: Added `"execute_command"` to the list of tools that force notifications

3. **Completion notification sent** (`ai_providers.py`):
   - Line 109-115: Creates completion notification:
     ```python
     notification_data = {
         "is_notification": True,
         "notification_type": "execute_command",  # Same as early!
         "function_name": "execute_command"
     }
     ```
   - Line 430: Yields the notification

4. **WebSocket processes notifications** (`consumers.py`):
   - Line 518-559: Detects `__NOTIFICATION__` wrapped strings
   - Parses JSON and sends to frontend with all fields
   - Uses either group send or direct WebSocket send

## Overview

The goal was to show visual indicators (spinning animations) when AI tools are being executed. The flow is:
1. AI decides to use a tool (e.g., `execute_command`)
2. Backend sends an "early notification" to show the tool is starting
3. Frontend displays a spinning indicator with the tool name
4. Tool executes and produces output
5. Backend sends a "completion notification" 
6. Frontend shows a success indicator

## Backend Changes

### 1. **chat/consumers.py** - WebSocket Message Handler

Added a test handler to simulate the `execute_command` tool execution:

```python
# Lines 194-234
if message_type == 'test_execute_command':
    # Send early notification first
    early_notification = {
        'type': 'ai_chunk',
        'chunk': '',
        'is_final': False,
        'is_notification': True,
        'notification_type': 'execute_command',
        'early_notification': True,
        'function_name': 'execute_command'
    }
    await self.send(text_data=json.dumps(early_notification))
    
    # Send command output
    await asyncio.sleep(0.5)
    output_chunk = {
        'type': 'ai_chunk',
        'chunk': 'Command output: Successfully executed command\n',
        'is_final': False
    }
    await self.send(text_data=json.dumps(output_chunk))
    
    # Send completion notification
    completion_notification = {
        'type': 'ai_chunk',
        'chunk': '',
        'is_final': False,
        'is_notification': True,
        'notification_type': 'command_output',  # Note: different from early notification
        'early_notification': False,
        'function_name': 'execute_command'
    }
    await self.send(text_data=json.dumps(completion_notification))
```

### Key Backend Flow:
1. **Early Notification**: Sent when tool starts executing
   - `is_notification: true`
   - `early_notification: true`
   - `function_name: 'execute_command'`
   - `notification_type: 'execute_command'`

2. **Completion Notification**: Sent when tool finishes
   - `is_notification: true`
   - `early_notification: false`
   - `notification_type: 'command_output'` (different from early!)

## Frontend Changes

### 1. **static/js/chat.js** - WebSocket Handler

#### Added Test Function (lines 96-107):
```javascript
window.testExecuteCommand = function() {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
            type: 'test_execute_command'
        }));
    }
};
```

#### Fixed Empty Chunk Filter (line 645):
```javascript
// Don't skip notifications even if they have empty chunks
if (data.chunk === '' && !data.is_final && 
    document.querySelector('.message.assistant:last-child') && 
    !data.is_notification) {
    console.log('Skipping empty non-final chunk...');
    break;
}
```

#### Added Notification Type Mapping (line 871):
```javascript
// Map command_output notification type to execute_command function
const functionName = data.notification_type === 'features' ? 'extract_features' : 
                   data.notification_type === 'personas' ? 'extract_personas' : 
                   data.notification_type === 'execute_command' ? 'execute_command' : 
                   data.notification_type === 'command_output' ? 'execute_command' :  // NEW
                   data.notification_type === 'start_server' ? 'start_server' : 
                   data.notification_type === 'implementation' ? 'save_implementation' : 
                   data.function_name || data.notification_type;
```

#### Enhanced Function Indicators with CSS Classes:

**showFunctionCallIndicator** (lines 1795-1802):
```javascript
// Add function-specific class for styling
const functionType = functionName.includes('features') ? 'features' :
                   functionName.includes('personas') ? 'personas' :
                   functionName.includes('implementation') ? 'implementation' :
                   functionName === 'execute_command' ? 'execute_command' :
                   functionName === 'start_server' ? 'start_server' :
                   'generic';
indicator.classList.add(`function-${functionType}`);
```

**showFunctionCallSuccess** (lines 1833-1840, 1849-1850):
```javascript
// Add function-specific class for styling
successElement.classList.add(`function-${functionType}`);

// Add success message for command execution
} else if (type === 'command_output' || functionName === 'execute_command') {
    message = 'Command executed successfully!';
```

### 2. **static/css/chat.css** - Styles

Already contains the necessary styles:
```css
/* Lines 100-106 */
.function-execute_command .function-call-indicator,
.function-execute_command .function-mini-indicator,
.function-command .function-call-indicator,
.function-command .function-mini-indicator {
    background-color: rgba(245, 158, 11, 0.3) !important; /* Subtle orange */
    border-left: 2px solid #fbbf24 !important;
}
```

## How It Should Work

1. **User runs `testExecuteCommand()` in browser console**

2. **Backend receives test request and sends:**
   - Early notification (triggers spinner)
   - Command output text
   - Completion notification (triggers success indicator)

3. **Frontend processes messages:**
   - WebSocket handler receives `ai_chunk` messages
   - Checks if `is_notification` is true
   - For early notifications: Shows spinning indicator with orange styling
   - For completion notifications: Shows success message

## Current Issue

The notifications are being sent correctly from the backend (visible in logs), but the frontend is not displaying the animations. The logs show:
- Early notification has fields as `undefined` in first message
- Completion notification shows fields correctly
- The animation logic is not being triggered despite correct data

## Testing

To test the animation:
1. Open browser console
2. Run: `testExecuteCommand()`
3. Watch for:
   - Orange spinner with "execute_command()" text
   - Command output text
   - Success indicator

The animation should appear in the chat message area where AI responses are displayed.