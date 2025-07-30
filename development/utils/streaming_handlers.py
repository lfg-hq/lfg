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
        
    def process_text_chunk(self, text: str, project_id: str = None) -> Tuple[str, Optional[Dict[str, Any]], Optional[str]]:
        """
        Process a text chunk and detect/handle LFG tags
        
        Returns:
            - output_text: Text to yield to the user (empty string if in special mode)
            - notification: Notification data to send (None if no notification)
            - mode_message: Message to show when entering a mode (None if not entering mode)
        """
        self.buffer += text
        notification = None
        mode_message = None
        output_text = ""
        
        # Check for file tag opening
        if "<lfg-file" in self.buffer and self.current_mode != "file":
            tag_match = re.search(r'<lfg-file\s+type="([^"]+)"(?:\s+name="([^"]+)")?\s*>', self.buffer)
            if tag_match:
                self.current_mode = "file"
                self.current_file_type = tag_match.group(1)
                self.current_file_name = tag_match.group(2) if tag_match.group(2) else self._get_default_file_name(self.current_file_type)
                logger.info(f"[FILE MODE ACTIVATED] - Type: {self.current_file_type}, Name: {self.current_file_name}")
                
                # Find where the tag ends
                tag_end = self.buffer.find(tag_match.group(0)) + len(tag_match.group(0))
                
                # Everything after the tag is file content
                self.current_file_data = self.buffer[tag_end:]
                
                # Clear the buffer
                self.buffer = ""
                
                # Generate appropriate mode message
                file_type_display = self._get_file_type_display(self.current_file_type)
                mode_message = f"\n\n*Generating {file_type_display} '{self.current_file_name}'...*\n\n"
                
                # If we already have content, stream it
                if self.current_file_data:
                    notification = {
                        "is_notification": True,
                        "notification_type": "file_stream",
                        "content_chunk": self.current_file_data,
                        "is_complete": False,
                        "file_name": self.current_file_name,
                        "file_type": self.current_file_type,
                        "notification_marker": "__NOTIFICATION__"
                    }
        
        # Check for file tag closing
        elif "</lfg-file>" in self.buffer and self.current_mode == "file":
            logger.info(f"[FILE MODE DEACTIVATED] - Type: {self.current_file_type}")
            
            # Find where the closing tag starts
            tag_pos = self.buffer.find("</lfg-file>")
            
            # Everything before the tag is file content
            if tag_pos > 0:
                remaining_content = self.buffer[:tag_pos]
                self.current_file_data += remaining_content
                
                # Stream the remaining content first
                if remaining_content:
                    pre_notification = {
                        "is_notification": True,
                        "notification_type": "file_stream",
                        "content_chunk": remaining_content,
                        "is_complete": False,
                        "file_name": self.current_file_name,
                        "file_type": self.current_file_type,
                        "notification_marker": "__NOTIFICATION__"
                    }
                    # We'll return this as part of a list in the refactored version
            
            # Clear buffer after the closing tag
            self.buffer = self.buffer[tag_pos + len("</lfg-file>"):]
            
            # Clean any incomplete closing tags from file data
            self.current_file_data = self._clean_incomplete_tags(self.current_file_data, "file")
            
            # Store the captured file
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
                # Note: file_id will be added after save completes
            }
            
            # IMPORTANT: Also trigger immediate save of the file
            logger.info(f"[FILE COMPLETE] Triggering immediate save for {self.current_file_type}: {self.current_file_name}")
            
            # Create a save request that will be processed later
            if project_id and self.current_file_data:
                self.pending_save_notifications.append({
                    'file_type': self.current_file_type,
                    'file_name': self.current_file_name,
                    'content': self.current_file_data,
                    'project_id': project_id
                })
                logger.info(f"[FILE COMPLETE] Added save request to pending queue")
            
            # Reset current file tracking
            self.current_mode = ""
            self.current_file_type = ""
            self.current_file_name = ""
            self.current_file_data = ""
        
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
            # We're in file mode, capture everything
            self.current_file_data += text
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
            "competitor_analysis": "Competitor Analysis",
            "market-analysis": "Market Analysis",
            "market_analysis": "Market Analysis",
            "technical-research": "Technical Research",
            "technical_research": "Technical Research",
            "user-research": "User Research",
            "user_research": "User Research",
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
            "competitor_analysis": "competitor analysis",
            "market-analysis": "market analysis",
            "market_analysis": "market analysis",
            "technical-research": "technical research",
            "technical_research": "technical research",
            "user-research": "user research",
            "user_research": "user research",
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
            
        from development.utils.ai_functions import save_file_from_stream
        
        # Save all captured files
        for file_type, file_name, content in self.captured_files:
            if content:
                logger.info(f"[SAVING FILE]: Type: {file_type}, Name: {file_name}, Size: {len(content)} characters")
                
                try:
                    save_result = await save_file_from_stream(content, project_id, file_type, file_name)
                    logger.info(f"[SAVE RESULT]: {save_result}")
                    
                    if save_result.get("is_notification"):
                        logger.info(f"[NOTIFICATION] Adding notification to list: {save_result}")
                        notifications.append(save_result)
                except Exception as e:
                    logger.error(f"Error saving file from stream: {str(e)}")
        
        return notifications
    
    async def check_and_save_pending_files(self) -> list:
        """Check if there are any pending files to save and save them immediately"""
        notifications = []
        
        if not self.pending_save_notifications:
            return notifications
            
        from development.utils.ai_functions import save_file_from_stream
        
        # Process all pending saves
        for save_request in self.pending_save_notifications:
            try:
                logger.info(f"[IMMEDIATE SAVE] Processing pending save: {save_request['file_type']}")
                save_result = await save_file_from_stream(
                    save_request['content'],
                    save_request['project_id'], 
                    save_request['file_type'],
                    save_request['file_name']
                )
                logger.info(f"[IMMEDIATE SAVE] Result: {save_result}")
                
                if save_result.get("is_notification"):
                    notifications.append(save_result)
            except Exception as e:
                logger.error(f"Error in immediate save: {str(e)}")
        
        # Clear pending saves
        self.pending_save_notifications = []
        
        return notifications


def format_notification(notification_data: Dict[str, Any]) -> str:
    """Format notification data as a string for yielding"""
    logger.info(f"[FORMAT_NOTIFICATION] Formatting notification: {notification_data}")
    notification_json = json.dumps(notification_data)
    formatted = f"__NOTIFICATION__{notification_json}__NOTIFICATION__"
    logger.info(f"[FORMAT_NOTIFICATION] Formatted: {formatted[:100]}...")
    return formatted