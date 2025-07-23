import re
import json
from typing import Dict, List, Any

class MarkdownToEditorJS:
    """Convert markdown text to Editor.js JSON format"""
    
    def __init__(self):
        self.blocks = []
        self.current_list = None
        self.current_list_type = None
    
    def convert(self, markdown_text: str) -> Dict[str, Any]:
        """Convert markdown text to Editor.js format"""
        if not markdown_text:
            return {"time": 0, "blocks": [], "version": "2.28.0"}
        
        lines = markdown_text.split('\n')
        self.blocks = []
        self.current_list = None
        self.current_list_type = None
        
        i = 0
        while i < len(lines):
            line = lines[i].rstrip()
            
            # Skip empty lines unless we're in a list
            if not line and not self.current_list:
                i += 1
                continue
            
            # Headers
            if line.startswith('#'):
                self._add_header(line)
                i += 1
            
            # Code blocks
            elif line.startswith('```'):
                i = self._add_code_block(lines, i)
            
            # Unordered lists
            elif re.match(r'^[\*\-\+]\s+', line):
                self._add_list_item(line, 'unordered')
                i += 1
            
            # Ordered lists
            elif re.match(r'^\d+\.\s+', line):
                self._add_list_item(line, 'ordered')
                i += 1
            
            # Horizontal rule
            elif re.match(r'^[\*\-_]{3,}$', line):
                self._finalize_current_list()
                self.blocks.append({
                    "type": "delimiter",
                    "data": {}
                })
                i += 1
            
            # Blockquote
            elif line.startswith('>'):
                self._add_quote(line)
                i += 1
            
            # Table (simple detection)
            elif '|' in line and i + 1 < len(lines) and re.match(r'^[\|\s\-:]+$', lines[i + 1]):
                i = self._add_table(lines, i)
            
            # Regular paragraph
            elif line:
                self._finalize_current_list()
                self._add_paragraph(line)
                i += 1
            else:
                i += 1
        
        # Finalize any remaining list
        self._finalize_current_list()
        
        return {
            "time": 0,
            "blocks": self.blocks,
            "version": "2.28.0"
        }
    
    def _add_header(self, line: str):
        """Add a header block"""
        self._finalize_current_list()
        
        level = len(line) - len(line.lstrip('#'))
        text = line.lstrip('#').strip()
        
        # Convert inline markdown in header
        text = self._convert_inline_markdown(text)
        
        self.blocks.append({
            "type": "header",
            "data": {
                "text": text,
                "level": min(level, 6)  # Editor.js supports h1-h6
            }
        })
    
    def _add_code_block(self, lines: List[str], start_idx: int) -> int:
        """Add a code block and return the new index"""
        self._finalize_current_list()
        
        i = start_idx + 1
        code_lines = []
        
        # Extract language if specified
        lang_match = re.match(r'^```(\w+)?', lines[start_idx])
        language = lang_match.group(1) if lang_match and lang_match.group(1) else ''
        
        # Collect code lines until closing ```
        while i < len(lines) and not lines[i].rstrip().startswith('```'):
            code_lines.append(lines[i].rstrip())
            i += 1
        
        code_text = '\n'.join(code_lines)
        
        self.blocks.append({
            "type": "code",
            "data": {
                "code": code_text
            }
        })
        
        return i + 1 if i < len(lines) else i
    
    def _add_list_item(self, line: str, list_type: str):
        """Add an item to a list"""
        # Extract the list item text
        if list_type == 'unordered':
            text = re.sub(r'^[\*\-\+]\s+', '', line).strip()
        else:
            text = re.sub(r'^\d+\.\s+', '', line).strip()
        
        # Convert inline markdown
        text = self._convert_inline_markdown(text)
        
        # If we're starting a new list or changing list type
        if not self.current_list or self.current_list_type != list_type:
            self._finalize_current_list()
            self.current_list = []
            self.current_list_type = list_type
        
        self.current_list.append(text)
    
    def _finalize_current_list(self):
        """Finalize the current list and add it to blocks"""
        if self.current_list:
            self.blocks.append({
                "type": "list",
                "data": {
                    "style": self.current_list_type,
                    "items": self.current_list
                }
            })
            self.current_list = None
            self.current_list_type = None
    
    def _add_quote(self, line: str):
        """Add a quote block"""
        self._finalize_current_list()
        
        text = line.lstrip('>').strip()
        text = self._convert_inline_markdown(text)
        
        self.blocks.append({
            "type": "quote",
            "data": {
                "text": text,
                "caption": "",
                "alignment": "left"
            }
        })
    
    def _add_table(self, lines: List[str], start_idx: int) -> int:
        """Add a table block and return the new index"""
        self._finalize_current_list()
        
        i = start_idx
        table_content = []
        
        # Parse table rows
        while i < len(lines) and '|' in lines[i]:
            # Skip separator line
            if re.match(r'^[\|\s\-:]+$', lines[i]):
                i += 1
                continue
            
            # Parse cells
            cells = [cell.strip() for cell in lines[i].split('|')[1:-1]]  # Remove empty first/last
            cells = [self._convert_inline_markdown(cell) for cell in cells]
            table_content.append(cells)
            i += 1
        
        if table_content:
            self.blocks.append({
                "type": "table",
                "data": {
                    "withHeadings": True,
                    "content": table_content
                }
            })
        
        return i
    
    def _add_paragraph(self, line: str):
        """Add a paragraph block"""
        text = self._convert_inline_markdown(line)
        
        self.blocks.append({
            "type": "paragraph",
            "data": {
                "text": text
            }
        })
    
    def _convert_inline_markdown(self, text: str) -> str:
        """Convert inline markdown to HTML tags supported by Editor.js"""
        # Bold
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'__(.*?)__', r'<b>\1</b>', text)
        
        # Italic
        text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
        text = re.sub(r'_(.*?)_', r'<i>\1</i>', text)
        
        # Inline code
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        
        # Links
        text = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2">\1</a>', text)
        
        # Strikethrough
        text = re.sub(r'~~(.*?)~~', r'<s>\1</s>', text)
        
        return text


class EditorJSToMarkdown:
    """Convert Editor.js JSON format to markdown text"""
    
    def convert(self, editorjs_data: Dict[str, Any]) -> str:
        """Convert Editor.js data to markdown"""
        if not editorjs_data or 'blocks' not in editorjs_data:
            return ""
        
        markdown_lines = []
        
        for block in editorjs_data['blocks']:
            block_type = block.get('type', '')
            data = block.get('data', {})
            
            if block_type == 'header':
                level = data.get('level', 1)
                text = self._convert_html_to_markdown(data.get('text', ''))
                markdown_lines.append(f"{'#' * level} {text}")
                
            elif block_type == 'paragraph':
                text = self._convert_html_to_markdown(data.get('text', ''))
                if text:  # Only add non-empty paragraphs
                    markdown_lines.append(text)
                
            elif block_type == 'list':
                style = data.get('style', 'unordered')
                items = data.get('items', [])
                
                for i, item in enumerate(items):
                    item_text = self._convert_html_to_markdown(item)
                    if style == 'ordered':
                        markdown_lines.append(f"{i + 1}. {item_text}")
                    else:
                        markdown_lines.append(f"- {item_text}")
                
            elif block_type == 'code':
                code = data.get('code', '')
                markdown_lines.append('```')
                markdown_lines.append(code)
                markdown_lines.append('```')
                
            elif block_type == 'quote':
                text = self._convert_html_to_markdown(data.get('text', ''))
                markdown_lines.append(f"> {text}")
                
            elif block_type == 'delimiter':
                markdown_lines.append('---')
                
            elif block_type == 'table':
                content = data.get('content', [])
                if content:
                    # Add header row
                    if len(content) > 0:
                        markdown_lines.append('| ' + ' | '.join(content[0]) + ' |')
                        markdown_lines.append('|' + '---|' * len(content[0]))
                    
                    # Add data rows
                    for row in content[1:]:
                        markdown_lines.append('| ' + ' | '.join(row) + ' |')
            
            # Add empty line between blocks (except between list items)
            if block_type != 'list' or block == editorjs_data['blocks'][-1]:
                markdown_lines.append('')
        
        # Join lines and clean up extra blank lines
        markdown = '\n'.join(markdown_lines)
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        return markdown.strip()
    
    def _convert_html_to_markdown(self, html_text: str) -> str:
        """Convert HTML tags back to markdown"""
        text = html_text
        
        # Bold
        text = re.sub(r'<b>(.*?)</b>', r'**\1**', text)
        text = re.sub(r'<strong>(.*?)</strong>', r'**\1**', text)
        
        # Italic
        text = re.sub(r'<i>(.*?)</i>', r'*\1*', text)
        text = re.sub(r'<em>(.*?)</em>', r'*\1*', text)
        
        # Inline code
        text = re.sub(r'<code>(.*?)</code>', r'`\1`', text)
        
        # Links
        text = re.sub(r'<a href="([^"]+)">([^<]+)</a>', r'[\2](\1)', text)
        
        # Strikethrough
        text = re.sub(r'<s>(.*?)</s>', r'~~\1~~', text)
        text = re.sub(r'<del>(.*?)</del>', r'~~\1~~', text)
        
        # Underline (convert to bold as markdown doesn't have underline)
        text = re.sub(r'<u>(.*?)</u>', r'**\1**', text)
        
        # Mark/highlight (convert to bold)
        text = re.sub(r'<mark>(.*?)</mark>', r'**\1**', text)
        
        return text