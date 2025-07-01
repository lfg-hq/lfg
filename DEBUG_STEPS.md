# PRD Streaming Debug Steps

## Step 1: Clear Everything
1. **Reload the page** (Ctrl+R or Cmd+R)
2. **Clear console** (click the 🚫 icon in console or type `clear()`)

## Step 2: Check System Status
Paste this in console:
```javascript
const script = document.createElement('script');
script.src = '/static/js/check-prd-status.js';
document.head.appendChild(script);
```

This will show:
- WebSocket connection status
- Required functions availability  
- Project ID context

## Step 3: Test the UI Manually
Paste this in console:
```javascript
const script2 = document.createElement('script');
script2.src = '/static/js/manual-prd-test.js';
document.head.appendChild(script2);
```

This will:
- Open the artifacts panel
- Switch to PRD tab
- Stream test content
- You should see "Test PRD Document" appear in the PRD tab

## Step 4: Test Real PRD Generation
If the UI test works, send this message in chat:
> Create a PRD for a todo app

## What to Look For:

### In Django Console (Terminal):
You should see:
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
After running the status check, you should see:
```
🎯 PRD STREAM DETECTED!
- has content_chunk: true
- content length: 245
- is_complete: false
```

## Debugging Results:

### If UI test works but real PRD doesn't:
- WebSocket issue - messages not reaching browser
- Check `window._prdMessages` to see all captured messages

### If nothing works:
- Share the output from Step 2 (status check)
- Share Django console output
- Share browser console errors

### If Django shows logs but browser doesn't:
- WebSocket connection issue
- The manual test in Step 3 should still work

## Quick Checks:
```javascript
// See all captured messages
console.log('Captured messages:', window._prdMessages);

// Check WebSocket state
console.log('WebSocket state:', window.socket?.readyState);

// Check if PRD content exists in UI
console.log('PRD container:', document.querySelector('.prd-streaming-container'));
```