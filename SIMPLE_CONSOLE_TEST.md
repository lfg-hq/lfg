# Simple Console Test for PRD Streaming

## Quick Test Steps:

1. **Open your browser** and go to the chat interface

2. **Open Developer Console** (F12)

3. **Paste this code** in the console:
   ```javascript
   const script = document.createElement('script');
   script.src = '/static/js/test-prd-console.js';
   document.head.appendChild(script);
   ```

4. **Send a message** like:
   - "Create a PRD for a todo app"
   - "Generate a product requirements document"

5. **Watch the console** for output

## What You Should See:

### In Django Server Console:
```
================================================================================
🔵 PRD STREAM CHUNK - Project 1
📅 Time: 2024-01-15 10:30:45
📏 Length: 245 chars
✅ Complete: False
📝 Content: # Product Requirements Document...
================================================================================
```

### In Browser Console:
```
🎯🎯🎯🎯🎯🎯🎯🎯🎯🎯🎯🎯🎯🎯🎯🎯
🎯 PRD STREAM DETECTED! 🎯
Content: # Product Requirements Document...
🎯🎯🎯🎯🎯🎯🎯🎯🎯🎯🎯🎯🎯🎯🎯🎯
```

## If You See Nothing:

If there's NO console output in either place, it means:
1. The AI is not using the `stream_prd_content` function
2. The AI might be using the old `create_prd` function instead

## Debug the AI:

To see what function the AI is using, watch for messages like:
- "I'll use the stream_prd_content function" (good)
- "I'll use the create_prd function" (old method)

The AI's response will show which tool it's calling.