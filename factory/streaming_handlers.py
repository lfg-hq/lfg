import re
import json
import logging
from typing import Tuple, Optional, Dict, Any

logger = logging.getLogger(__name__)


class StreamingTagHandler:
    """Handles detection and processing of LFG tags in streaming AI responses"""
    
    def __init__(self):
        self.buffer = ""
        self.current_mode = ""
        self.current_file_type = ""
        self.current_file_name = ""
        self.current_file_data = ""
        self.captured_files = []  # List of (file_type, file_name, content) tuples
        self.pending_save_notifications = []  # List of save notifications to send
        
        # Edit mode fields
        self.edit_mode = False
        self.file_id = None
        self.file_mode = "create"  # "create" or "edit"
        
    def process_text_chunk(self, text: str, project_id: str = None) -> Tuple[str, Optional[Dict[str, Any]], Optional[str]]:
        """
        Process a text chunk and detect/handle LFG tags
        
        Returns:
            - output_text: Text to yield to the user (empty string if in special mode)
            - notification: Notification data to send (None if no notification)
            - mode_message: Message to show when entering a mode (None if not entering mode)
        """
        # When in file mode, don't add to buffer - process directly
        if self.current_mode != "file":
            self.buffer += text
            
        notification = None
        mode_message = None
        output_text = ""
        
        # Check for file tag opening (handles both create and edit modes)
        if "<lfg-file" in self.buffer and self.current_mode != "file":
            # Enhanced regex to capture mode and file_id
            tag_match = re.search(
                r'<lfg-file\s+(?:mode="([^"]+)"\s+)?(?:file_id="([^"]+)"\s+)?type="([^"]+)"(?:\s+name="([^"]+)")?\s*>', 
                self.buffer
            )
            if tag_match:
                self.current_mode = "file"
                self.file_mode = tag_match.group(1) or "create"
                self.file_id = tag_match.group(2)
                self.current_file_type = tag_match.group(3)
                self.current_file_name = tag_match.group(4) if tag_match.group(4) else self._get_default_file_name(self.current_file_type)
                
                if self.file_mode == "edit":
                    self.edit_mode = True
                    logger.info(f"[EDIT MODE ACTIVATED] - Type: {self.current_file_type}, Name: {self.current_file_name}, File ID: {self.file_id}")
                    mode_message = f"\n\n*Editing {self._get_file_type_display(self.current_file_type)} '{self.current_file_name}'...*\n\n"
                    
                    # For edit mode, we'll capture the complete updated content
                    notification = {
                        "is_notification": True,
                        "notification_type": "file_stream",
                        "content_chunk": "",
                        "is_complete": False,
                        "file_name": self.current_file_name,
                        "file_type": self.current_file_type,
                        "file_id": self.file_id,
                        "notification_marker": "__NOTIFICATION__"
                    }
                else:
                    logger.info(f"[FILE MODE ACTIVATED] - Type: {self.current_file_type}, Name: {self.current_file_name}")
                    mode_message = f"\n\n*Generating {self._get_file_type_display(self.current_file_type)} '{self.current_file_name}'...*\n\n"
                
                # Find where the tag ends
                tag_end = self.buffer.find(tag_match.group(0)) + len(tag_match.group(0))
                
                # Everything after the tag is file content
                self.current_file_data = self.buffer[tag_end:]
                
                # Clear the buffer completely - we've extracted what we need
                self.buffer = ""
                
                # Log what we captured initially
                logger.info(f"[FILE TAG OPENED] Initial content captured: {len(self.current_file_data)} chars")
                
                # For create mode, stream the content
                if not self.edit_mode and self.current_file_data:
                    notification = {
                        "is_notification": True,
                        "notification_type": "file_stream",
                        "content_chunk": self.current_file_data,
                        "is_complete": False,
                        "file_name": self.current_file_name,
                        "file_type": self.current_file_type,
                        "notification_marker": "__NOTIFICATION__"
                    }
        
        # Check for file tag closing (check both buffer and text when in file mode)
        elif (("</lfg-file>" in self.buffer) or (self.current_mode == "file" and "</lfg-file>" in text)) and self.current_mode == "file":
            logger.info(f"[FILE MODE DEACTIVATED] - Type: {self.current_file_type}, Edit Mode: {self.edit_mode}")
            
            # Handle closing tag based on where it was found
            if "</lfg-file>" in text:
                # Tag is in the current text chunk
                tag_pos = text.find("</lfg-file>")
                
                # Everything before the tag is file content
                if tag_pos > 0:
                    remaining_content = text[:tag_pos]
                    self.current_file_data += remaining_content
                    
                    # Stream the remaining content for create mode
                    if not self.edit_mode and remaining_content:
                        pre_notification = {
                            "is_notification": True,
                            "notification_type": "file_stream",
                            "content_chunk": remaining_content,
                            "is_complete": False,
                            "file_name": self.current_file_name,
                            "file_type": self.current_file_type,
                            "notification_marker": "__NOTIFICATION__"
                        }
                
                # Put anything after the closing tag into buffer for normal processing
                self.buffer = text[tag_pos + len("</lfg-file>"):]
            else:
                # Tag is in the buffer (shouldn't happen in file mode, but handle it)
                tag_pos = self.buffer.find("</lfg-file>")
                
                # Everything before the tag is file content
                if tag_pos > 0:
                    remaining_content = self.buffer[:tag_pos]
                    self.current_file_data += remaining_content
                    
                    # Stream the remaining content for create mode
                    if not self.edit_mode and remaining_content:
                        pre_notification = {
                            "is_notification": True,
                            "notification_type": "file_stream",
                            "content_chunk": remaining_content,
                            "is_complete": False,
                            "file_name": self.current_file_name,
                            "file_type": self.current_file_type,
                            "notification_marker": "__NOTIFICATION__"
                        }
                
                # Clear buffer after the closing tag
                self.buffer = self.buffer[tag_pos + len("</lfg-file>"):]
            
            # Clean any incomplete closing tags from file data
            self.current_file_data = self._clean_incomplete_tags(self.current_file_data, "file")
            
            # Log final content before saving
            logger.info(f"[FILE COMPLETE] Final content length: {len(self.current_file_data)} chars")
            logger.info(f"[FILE COMPLETE] First 200 chars: {self.current_file_data[:200]}")
            logger.info(f"[FILE COMPLETE] Last 200 chars: {self.current_file_data[-200:]}")
            
            # Only store in captured_files if no project_id (for backward compatibility)
            # Otherwise, use pending_save_notifications to avoid duplicates
            if not project_id:
                if self.edit_mode:
                    # Store the edit request with the complete updated content
                    logger.info(f"[EDIT MODE] Storing edit request for file ID: {self.file_id}")
                    self.captured_files.append(("edit", self.current_file_name, {
                        "file_id": self.file_id,
                        "updated_content": self.current_file_data,  # Complete updated content
                        "file_type": self.current_file_type
                    }))
                else:
                    # Store the captured file for creation
                    self.captured_files.append((self.current_file_type, self.current_file_name, self.current_file_data))
            
            # Send completion notification
            notification = {
                "is_notification": True,
                "notification_type": "file_stream",
                "content_chunk": "",
                "is_complete": True,
                "file_name": self.current_file_name,
                "file_type": self.current_file_type,
                "notification_marker": "__NOTIFICATION__",
            }
            if self.edit_mode:
                notification["file_id"] = self.file_id
            
            # Trigger save/edit
            if project_id:
                if self.edit_mode:
                    self.pending_save_notifications.append({
                        'mode': 'edit',
                        'file_id': self.file_id,
                        'file_type': self.current_file_type,
                        'file_name': self.current_file_name,
                        'updated_content': self.current_file_data,  # Complete updated content
                        'project_id': project_id
                    })
                else:
                    self.pending_save_notifications.append({
                        'mode': 'create',
                        'file_type': self.current_file_type,
                        'file_name': self.current_file_name,
                        'content': self.current_file_data,
                        'project_id': project_id
                    })
                logger.info(f"[FILE COMPLETE] Added {'edit' if self.edit_mode else 'save'} request to pending queue")
            
            # Reset current file tracking
            self.current_mode = ""
            self.current_file_type = ""
            self.current_file_name = ""
            self.current_file_data = ""
            self.edit_mode = False
            self.file_id = None
            self.file_mode = "create"
        
        # Legacy tag support - convert old tags to new format
        elif "<lfg-prd" in self.buffer and self.current_mode != "file":
            # Convert old PRD tag to new file tag
            old_tag_match = re.search(r'<lfg-prd(?:\s+name="([^"]+)")?\s*>', self.buffer)
            if old_tag_match:
                old_tag = old_tag_match.group(0)
                prd_name = old_tag_match.group(1) if old_tag_match.group(1) else "Main PRD"
                new_tag = f'<lfg-file type="prd" name="{prd_name}">'
                self.buffer = self.buffer.replace(old_tag, new_tag)
                # Continue processing with the converted tag
        
        elif "</lfg-prd>" in self.buffer:
            # Convert old closing PRD tag
            self.buffer = self.buffer.replace("</lfg-prd>", "</lfg-file>")
        
        elif "<lfg-plan>" in self.buffer and self.current_mode != "file":
            # Convert old implementation tag to new file tag
            old_tag_match = re.search(r'<lfg-plan\s*>', self.buffer)
            if old_tag_match:
                old_tag = old_tag_match.group(0)
                new_tag = '<lfg-file type="implementation" name="Technical Implementation Plan">'
                self.buffer = self.buffer.replace(old_tag, new_tag)
                # Continue processing with the converted tag
        
        elif "</lfg-plan>" in self.buffer:
            # Convert old closing implementation tag
            self.buffer = self.buffer.replace("</lfg-plan>", "</lfg-file>")
        
        # Handle content based on current mode
        elif self.current_mode == "file":
            # When in file mode, we need to handle the buffer differently
            # The buffer should be empty since we cleared it when entering file mode
            # So we can safely add new text to current_file_data
            
            # Important: Only add text that's actually new, not from buffer
            self.current_file_data += text
            
            logger.debug(f"[FILE MODE] Added {len(text)} chars, total content: {len(self.current_file_data)} chars")
            
            if self.edit_mode:
                # In edit mode, we capture but don't stream (showing "Editing..." is enough)
                logger.debug(f"[CAPTURING EDIT DATA]: Added {len(text)} chars, total: {len(self.current_file_data)}")
                # Optionally stream progress for edit mode
                notification = {
                    "is_notification": True,
                    "notification_type": "file_stream",
                    "content_chunk": text,  # Show what's being edited
                    "is_complete": False,
                    "file_name": self.current_file_name,
                    "file_type": self.current_file_type,
                    "file_id": self.file_id,
                    "notification_marker": "__NOTIFICATION__"
                }
            else:
                # In create mode, stream content as before
                logger.debug(f"[CAPTURING FILE DATA]: Type: {self.current_file_type}, Added {len(text)} chars")
                
                # Stream file content to the appropriate panel
                notification = {
                    "is_notification": True,
                    "notification_type": "file_stream",
                    "content_chunk": text,
                    "is_complete": False,
                    "file_name": self.current_file_name,
                    "file_type": self.current_file_type,
                    "notification_marker": "__NOTIFICATION__"
                }
        
        else:
            # Normal mode - keep buffer reasonable and return text for user
            if len(self.buffer) > 100:
                # Check if we might be building up to a tag
                if not any(tag in self.buffer[-50:] for tag in ["<lfg", "</lfg"]):
                    # Safe to output most of the buffer
                    output_text = self.buffer[:-50]
                    self.buffer = self.buffer[-50:]
                    
                    # Clean any stray XML tags before yielding
                    output_text = self._clean_xml_fragments(output_text)
        
        return output_text, notification, mode_message
    
    def _clean_incomplete_tags(self, data: str, tag_type: str) -> str:
        """Clean incomplete closing tags from data"""
        incomplete_patterns = ["<", "</", "</l", "</lf", "</lfg", "</lfg-", "</lfg-f", "</lfg-fi", "</lfg-fil", "</lfg-file"]
        
        for pattern in reversed(incomplete_patterns):
            if data.endswith(pattern):
                return data[:-len(pattern)]
        
        return data
    
    def _get_default_file_name(self, file_type: str) -> str:
        """Get default file name based on file type"""
        defaults = {
            "prd": "Main PRD",
            "implementation": "Technical Implementation Plan",
            "design": "Design Document",
            "test": "Test Plan",
            "research": "Research Document",
            "competitor-analysis": "Competitor Analysis",
            "market-analysis": "Market Analysis",
            "technical-research": "Technical Research",
            "user-research": "User Research",
            "pricing": "Pricing Document",
            "quotation": "Project Quotation",
            "proposal": "Project Proposal",
            "specification": "Technical Specification",
            "roadmap": "Product Roadmap",
            "report": "Analysis Report",
            "strategy": "Strategic Plan",
            "document": "Document",
        }
        return defaults.get(file_type, "Document")
    
    def _get_file_type_display(self, file_type: str) -> str:
        """Get display name for file type"""
        displays = {
            "prd": "PRD",
            "implementation": "implementation plan",
            "design": "design document",
            "test": "test plan",
            "research": "research document",
            "competitor-analysis": "competitor analysis",
            "market-analysis": "market analysis",
            "technical-research": "technical research",
            "user-research": "user research",
            "pricing": "pricing document",
            "quotation": "quotation",
            "proposal": "proposal",
            "specification": "specification",
            "roadmap": "roadmap",
            "report": "report",
            "strategy": "strategy document",
            "document": "document",
        }
        return displays.get(file_type, "document")
    
    def _clean_xml_fragments(self, text: str) -> str:
        """Clean XML fragments from text"""
        if not text:
            return text
        
        # Remove complete lfg tags
        text = re.sub(r'</?lfg[^>]*>', '', text)
        # Remove incomplete lfg tags at the end
        text = re.sub(r'</?lfg[^>]*$', '', text)
        # Remove priority tags
        text = re.sub(r'</?priority[^>]*>', '', text)
        
        return text
    
    def flush_buffer(self) -> str:
        """Flush any remaining buffer content (used at stream end)"""
        if self.buffer and self.current_mode == "":
            # Clean any stray XML tags before yielding
            clean_output = self._clean_xml_fragments(self.buffer)
            self.buffer = ""
            return clean_output
        return ""
    
    async def save_captured_data(self, project_id: str) -> list:
        """Save any captured file data"""
        notifications = []
        
        if not project_id or not self.captured_files:
            return notifications
            
        from factory.ai_functions import save_file_from_stream, update_file_content
        
        # Save all captured files
        for file_type_or_mode, file_name, content_or_config in self.captured_files:
            if file_type_or_mode == "edit":
                # Handle edit mode - update with complete new content
                config = content_or_config
                logger.info(f"[EDITING FILE]: ID: {config['file_id']}, Name: {file_name}")
                
                try:
                    # Call a simpler update function that replaces content
                    edit_result = await update_file_content(
                        config['file_id'],
                        config['updated_content'],  # Complete updated content
                        project_id
                    )
                    logger.info(f"[EDIT RESULT]: {edit_result}")
                    
                    if edit_result.get("is_notification"):
                        notifications.append(edit_result)
                except Exception as e:
                    logger.error(f"Error editing file: {str(e)}", exc_info=True)
            else:
                # Handle create mode (existing logic)
                if content_or_config:
                    logger.info(f"[SAVING FILE]: Type: {file_type_or_mode}, Name: {file_name}, Size: {len(content_or_config)} characters")
                    logger.info(f"[SAVE_CAPTURED CONTENT DEBUG] First 500 chars: {content_or_config[:500]}")
                    logger.info(f"[SAVE_CAPTURED CONTENT DEBUG] Last 500 chars: {content_or_config[-500:]}")
                    
                    try:
                        save_result = await save_file_from_stream(
                            content_or_config, 
                            project_id, 
                            file_type_or_mode, 
                            file_name
                        )
                        logger.info(f"[SAVE RESULT]: {save_result}")
                        
                        if save_result.get("is_notification"):
                            notifications.append(save_result)
                    except Exception as e:
                        logger.error(f"Error saving file from stream: {str(e)}")
        
        # Clear captured files after processing to prevent duplicate saves
        self.captured_files = []
        logger.info("[SAVE_CAPTURED_DATA] Cleared captured files after processing")
        
        return notifications
    
    async def check_and_save_pending_files(self) -> list:
        """Check if there are any pending files to save and save them immediately"""
        notifications = []
        
        if not self.pending_save_notifications:
            return notifications
            
        from factory.ai_functions import save_file_from_stream, update_file_content
        
        # Copy the list to avoid issues with clearing during iteration
        pending_saves = list(self.pending_save_notifications)
        
        # Clear pending saves immediately to prevent duplicate processing
        self.pending_save_notifications = []
        logger.info(f"[CHECK_AND_SAVE] Processing {len(pending_saves)} pending saves/edits")
        
        # Process all pending saves/edits
        for request in pending_saves:
            try:
                if request.get('mode') == 'edit':
                    logger.info(f"[IMMEDIATE EDIT] Processing pending edit: {request['file_id']}")
                    # Use simpler update with complete content
                    edit_result = await update_file_content(
                        request['file_id'],
                        request['updated_content'],  # Complete updated content
                        request['project_id']
                    )
                    logger.info(f"[IMMEDIATE EDIT] Result: {edit_result}")
                    
                    if edit_result.get("is_notification"):
                        notifications.append(edit_result)
                else:
                    logger.info(f"[IMMEDIATE SAVE] Processing pending save: {request['file_type']}")
                    logger.info(f"[CONTENT DEBUG] File name: {request['file_name']}")
                    logger.info(f"[CONTENT DEBUG] Content length: {len(request['content'])} characters")
                    logger.info(f"[CONTENT DEBUG] First 500 chars: {request['content'][:500]}")
                    logger.info(f"[CONTENT DEBUG] Last 500 chars: {request['content'][-500:]}")
                    
                    save_result = await save_file_from_stream(
                        request['content'],
                        request['project_id'], 
                        request['file_type'],
                        request['file_name']
                    )
                    logger.info(f"[IMMEDIATE SAVE] Result: {save_result}")
                    
                    if save_result.get("is_notification"):
                        notifications.append(save_result)
            except Exception as e:
                logger.error(f"Error in immediate save/edit: {str(e)}")
        
        return notifications


def format_notification(notification_data: Dict[str, Any]) -> str:
    """Format notification data as a string for yielding"""
    logger.info(f"[FORMAT_NOTIFICATION] Formatting notification: {notification_data}")
    notification_json = json.dumps(notification_data)
    formatted = f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
    logger.info(f"[FORMAT_NOTIFICATION] Formatted: {formatted[:100]}...")
    return formatted