# PRD Streaming Test Instructions

## Testing Steps:

1. **Open your browser and navigate to the chat interface**

2. **Open Developer Console** (F12 or right-click → Inspect → Console)

3. **Load the debug script** by pasting this in the console:
   ```javascript
   const script = document.createElement('script');
   script.src = '/static/js/final-prd-debug.js';
   document.head.appendChild(script);
   ```

4. **Run the direct test** to verify the UI works:
   ```javascript
   testFullFlow()
   ```
   
   You should see "Full Flow Test" appear in the PRD tab if everything is working.

5. **Send a message to generate a PRD**, for example:
   - "Create a PRD for a todo app"
   - "Generate a product requirements document for a task management system"

6. **Watch the console output** for:
   - 🎯 PRD STREAM DETECTED! messages
   - Notification details
   - Any errors

7. **Check the PRD state** at any time:
   ```javascript
   checkPRDState()
   ```

## What to Look For:

### If Working Correctly:
- PRD content should appear live in the artifacts panel
- Console should show "PRD STREAM DETECTED!" messages
- Content should accumulate as chunks arrive
- Status should change to "complete" when done

### If Not Working:
- Check console for error messages
- Look for "content_chunk" field in notifications
- Verify project ID is available
- Check if handleAIChunk is being called

## Debug Information to Share:

If it's not working, please share:
1. Console output from the debug script
2. Any error messages
3. Output of `checkPRDState()`
4. Screenshot of the artifacts panel

## Additional Debug Commands:

```javascript
// Check if components exist
console.log('ArtifactsLoader:', window.ArtifactsLoader);
console.log('streamPRDContent:', window.ArtifactsLoader?.streamPRDContent);

// Manually open artifacts panel
window.ArtifactsPanel.toggle(true);

// Switch to PRD tab
document.querySelector('.tab-button[data-tab="prd"]').click();

// Check current project ID
console.log('Project ID:', window.currentProjectId);
```