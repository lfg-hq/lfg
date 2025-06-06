# Fix for Duplicate Message Storage

## Problem
The last assistant message was being saved twice to the database every time.

## Root Cause
There were two competing save mechanisms:

1. **In `process_ai_stream`**: 
   - Accumulated content in `self.pending_message`
   - Auto-saved partial messages every 500 chars or 5 seconds
   - Called `finalize_message()` in the finally block

2. **In `generate_ai_response`**:
   - Accumulated content in `full_response`
   - Saved the complete message after streaming finished

Both were saving the same content, resulting in duplicate messages.

## Solution
Removed the auto-save mechanism from `process_ai_stream` and rely solely on the save in `generate_ai_response`.

### Changes Made in `chat/consumers.py`:

1. **Removed pending_message accumulation** (lines 800-805):
   - No longer accumulating content in `self.pending_message`
   - Just yielding content for streaming

2. **Removed auto-save logic** (lines 803-813):
   - Removed the 500 character / 5 second auto-save
   - Removed `auto_save_partial_message()` calls

3. **Removed finalize_message in finally block** (lines 810-812):
   - No longer calling `finalize_message()` at the end
   - Just cleaning up by setting `self.pending_message = None`

4. **Kept single save point** (line 600):
   - Message is saved once in `generate_ai_response`
   - After all streaming is complete

## Result
- Assistant messages are saved exactly once
- No more duplicates in the database
- Streaming still works as expected
- Simpler, cleaner code flow

## Note
The auto-save feature was originally intended for connection stability (saving partial messages if connection drops). If this feature is needed in the future, it should be reimplemented with proper deduplication logic.