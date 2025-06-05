# Fix for Notification Strings Being Saved to Database

## Summary of Changes Made

### Fixed: chat/consumers.py - process_ai_stream method (lines 711-816)

The issue was that notification content was being added to `self.pending_message` before checking if it was a notification. This caused notification JSON to be saved to the database.

#### Changes:
1. **Moved notification detection to happen FIRST** (before adding to pending_message)
2. **Skip adding notification content to pending_message**
3. **Only add normal content to pending_message**

#### Before (WRONG):
```python
# Content was added to pending_message BEFORE checking if it's a notification
self.pending_message += content

# Then check if it's a notification
if isinstance(content, str) and content.startswith("__NOTIFICATION__"):
    # Handle notification
    yield content
    continue
```

#### After (CORRECT):
```python
# Check if it's a notification FIRST
if isinstance(content, str) and content.startswith("__NOTIFICATION__"):
    # Handle notification
    yield content
    continue  # Skip adding to pending_message

# Only add normal content to pending_message
self.pending_message += content
```

### Result:
- Notifications are still sent to the frontend for animations
- Notifications are NOT saved to the database
- Normal AI response content is saved correctly

## Problem
When the AI uses tools like `execute_command`, notification strings are being saved to the database along with the actual response content. This causes the following to appear when the page is refreshed:

```
OTIFICATION{"is_notification": true, "notification_type": "execute_command", ...}NOTIFICATION
```

## Root Cause
The issue occurs in `consumers.py` in the `generate_ai_response` method. The notification strings are being added to `full_response` which is then saved to the database.

## Solution

### 1. **chat/consumers.py** - Skip notifications from being added to full_response

In the `generate_ai_response` method (around line 517-561), notifications are detected and sent to the frontend, but they should NOT be added to `full_response`.

The current code already has logic to skip notifications (line 558: `continue`), but there's an issue with the flow.

#### Key Fix Areas:

1. **Line 517-559**: When a `__NOTIFICATION__` wrapped string is detected, it should:
   - Send the notification to the frontend ✓ (already done)
   - Continue without adding to full_response ✓ (already done)
   - BUT: The notification content is still being added before the check

2. **Line 561**: The content is being added to `full_response` BEFORE checking if it's a notification

### Current Flow (WRONG):
```python
# Line 483-561
async for content in self.process_ai_stream(provider, messages, project_id, tools):
    # ... stop generation check ...
    
    # Check if this is a notification
    if isinstance(content, str) and content.startswith("__NOTIFICATION__") and content.endswith("__NOTIFICATION__"):
        # Parse and send notification
        # ... notification handling ...
        continue  # Skip adding to full_response
    
    # ... other notification format check ...
    
    full_response += content  # THIS IS THE PROBLEM - happens before notification check
```

### Correct Flow:
The notification check should happen BEFORE adding content to full_response.

## Files to Modify

### 1. **chat/consumers.py**
Move the `full_response += content` line to AFTER all notification checks.

The logic should be:
1. Check if content is a notification
2. If yes, handle it and continue (skip adding to full_response)
3. If no, add to full_response

### 2. **process_ai_stream** method (line 693)
The method already yields notification strings, but we need to ensure they're not accumulated in `pending_message` which is used for auto-save.

Current code (line 206):
```python
self.pending_message += content  # This happens before notification check
```

This should also skip notification content.

## Implementation

The fix requires reordering the logic in `generate_ai_response` to check for notifications BEFORE accumulating content.