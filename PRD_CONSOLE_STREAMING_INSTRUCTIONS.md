# PRD Console Streaming Instructions

## How to Test PRD Streaming with Console Output

### 1. Server Console Output
When you generate a PRD, you should see console output in your Django server terminal like this:

```
================================================================================
🔵 PRD STREAM CHUNK - Project 1
📅 Time: 2024-01-15 10:30:45
📏 Length: 245 chars
✅ Complete: False
📝 Content: # Product Requirements Document

## Overview

This document outlines the requirements for...
================================================================================
```

### 2. Browser Console Output
Open your browser's Developer Console (F12) and you should see:

```
================================================================================
🔵 PRD STREAM RECEIVED IN BROWSER
📅 Time: 2024-01-15T10:30:45.123Z
📏 Length: 245 chars
✅ Complete: false
📝 Content: # Product Requirements Document

## Overview

This document outlines the requirements for...
================================================================================
```

And also:

```
================================================================================
🟡 PRD STREAM IN ARTIFACTS LOADER
📅 Time: 2024-01-15T10:30:45.125Z
📏 Length: 245 chars
✅ Complete: false
📝 Content: # Product Requirements Document

## Overview

This document outlines the requirements for...
================================================================================
```

### 3. WebSocket Consumer Output
In your Django server console, you should also see:

```
================================================================================
🟣 PRD STREAM IN WEBSOCKET CONSUMER
📅 Time: 2024-01-15T10:30:45.120000
📏 Content Length: 245 chars
✅ Complete: False
📝 Content: # Product Requirements Document

## Overview

This document outlines the requirements for...
================================================================================
```

## Testing Steps:

1. **Start your Django server** and watch the console output

2. **Open your browser** and navigate to the chat interface

3. **Open Browser Developer Console** (F12)

4. **Send a message to generate a PRD**, for example:
   - "Create a PRD for a todo app"
   - "Generate a product requirements document for a task management system"

5. **Watch both consoles** (server and browser) for the streaming output

## What to Look For:

### If Working:
- You'll see 🔵 (blue circle) messages in the server console showing PRD chunks
- You'll see 🟣 (purple circle) messages showing WebSocket transmission
- You'll see 🔵 (blue circle) and 🟡 (yellow circle) messages in browser console
- When complete, you'll see 🟢 (green circle) completion message

### If Not Working:
- No console output means the AI isn't using `stream_prd_content` function
- Console output in server but not browser means WebSocket issue
- Console output in browser but no UI update means frontend rendering issue

## Quick Debug Commands:

Run these in your browser console:

```javascript
// Check if streaming function exists
console.log('streamPRDContent exists:', !!window.ArtifactsLoader?.streamPRDContent);

// Check current project ID
console.log('Current project ID:', window.currentProjectId);

// Manually test streaming
if (window.ArtifactsLoader?.streamPRDContent) {
    window.ArtifactsLoader.streamPRDContent("# Manual Test\n\nThis is a test", false, window.currentProjectId || 1);
}
```

## Share Debug Info:

If it's not working, please share:
1. **Server console output** (or lack thereof)
2. **Browser console output** (or lack thereof)
3. Screenshot of both consoles during PRD generation
4. The exact message you sent to trigger PRD generation