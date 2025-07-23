/**
 * Markdown to Editor.js converter for client-side use
 */

class MarkdownToEditorJS {
    constructor() {
        this.blocks = [];
        this.currentList = null;
        this.currentListType = null;
    }
    
    convert(markdownText) {
        if (!markdownText) {
            return { time: 0, blocks: [], version: "2.28.0" };
        }
        
        const lines = markdownText.split('\n');
        this.blocks = [];
        this.currentList = null;
        this.currentListType = null;
        
        let i = 0;
        while (i < lines.length) {
            const line = lines[i].trimEnd();
            
            // Skip empty lines unless we're in a list
            if (!line && !this.currentList) {
                i++;
                continue;
            }
            
            // Headers
            if (line.startsWith('#')) {
                this._addHeader(line);
                i++;
            }
            // Code blocks
            else if (line.startsWith('```')) {
                i = this._addCodeBlock(lines, i);
            }
            // Unordered lists
            else if (/^[\*\-\+]\s+/.test(line)) {
                this._addListItem(line, 'unordered');
                i++;
            }
            // Ordered lists
            else if (/^\d+\.\s+/.test(line)) {
                this._addListItem(line, 'ordered');
                i++;
            }
            // Horizontal rule
            else if (/^[\*\-_]{3,}$/.test(line)) {
                this._finalizeCurrentList();
                this.blocks.push({
                    type: "delimiter",
                    data: {}
                });
                i++;
            }
            // Blockquote
            else if (line.startsWith('>')) {
                this._addQuote(line);
                i++;
            }
            // Table (simple detection)
            else if (line.includes('|') && i + 1 < lines.length && /^[\|\s\-:]+$/.test(lines[i + 1])) {
                i = this._addTable(lines, i);
            }
            // Regular paragraph
            else if (line) {
                this._finalizeCurrentList();
                this._addParagraph(line);
                i++;
            } else {
                i++;
            }
        }
        
        // Finalize any remaining list
        this._finalizeCurrentList();
        
        return {
            time: Date.now(),
            blocks: this.blocks,
            version: "2.28.0"
        };
    }
    
    _addHeader(line) {
        this._finalizeCurrentList();
        
        const level = line.match(/^#+/)[0].length;
        const text = line.replace(/^#+\s*/, '').trim();
        
        this.blocks.push({
            type: "header",
            data: {
                text: this._convertInlineMarkdown(text),
                level: Math.min(level, 6)
            }
        });
    }
    
    _addCodeBlock(lines, startIdx) {
        this._finalizeCurrentList();
        
        let i = startIdx + 1;
        const codeLines = [];
        
        // Extract language if specified
        const langMatch = lines[startIdx].match(/^```(\w+)?/);
        const language = langMatch && langMatch[1] ? langMatch[1] : '';
        
        // Collect code lines until closing ```
        while (i < lines.length && !lines[i].trimEnd().startsWith('```')) {
            codeLines.push(lines[i].trimEnd());
            i++;
        }
        
        const codeText = codeLines.join('\n');
        
        this.blocks.push({
            type: "code",
            data: {
                code: codeText
            }
        });
        
        return i + 1 < lines.length ? i + 1 : i;
    }
    
    _addListItem(line, listType) {
        // Extract the list item text
        let text;
        if (listType === 'unordered') {
            text = line.replace(/^[\*\-\+]\s+/, '').trim();
        } else {
            text = line.replace(/^\d+\.\s+/, '').trim();
        }
        
        // Convert inline markdown
        text = this._convertInlineMarkdown(text);
        
        // If we're starting a new list or changing list type
        if (!this.currentList || this.currentListType !== listType) {
            this._finalizeCurrentList();
            this.currentList = [];
            this.currentListType = listType;
        }
        
        this.currentList.push(text);
    }
    
    _finalizeCurrentList() {
        if (this.currentList) {
            this.blocks.push({
                type: "list",
                data: {
                    style: this.currentListType,
                    items: this.currentList
                }
            });
            this.currentList = null;
            this.currentListType = null;
        }
    }
    
    _addQuote(line) {
        this._finalizeCurrentList();
        
        const text = line.replace(/^>\s*/, '').trim();
        
        this.blocks.push({
            type: "quote",
            data: {
                text: this._convertInlineMarkdown(text),
                caption: "",
                alignment: "left"
            }
        });
    }
    
    _addTable(lines, startIdx) {
        this._finalizeCurrentList();
        
        let i = startIdx;
        const tableContent = [];
        
        // Parse table rows
        while (i < lines.length && lines[i].includes('|')) {
            // Skip separator line
            if (/^[\|\s\-:]+$/.test(lines[i])) {
                i++;
                continue;
            }
            
            // Parse cells
            const cells = lines[i].split('|')
                .slice(1, -1) // Remove empty first/last
                .map(cell => this._convertInlineMarkdown(cell.trim()));
            
            tableContent.push(cells);
            i++;
        }
        
        if (tableContent.length > 0) {
            this.blocks.push({
                type: "table",
                data: {
                    withHeadings: true,
                    content: tableContent
                }
            });
        }
        
        return i;
    }
    
    _addParagraph(line) {
        const text = this._convertInlineMarkdown(line);
        
        this.blocks.push({
            type: "paragraph",
            data: {
                text: text
            }
        });
    }
    
    _convertInlineMarkdown(text) {
        // Bold
        text = text.replace(/\*\*(.*?)\*\*/g, '<b>$1</b>');
        text = text.replace(/__(.*?)__/g, '<b>$1</b>');
        
        // Italic
        text = text.replace(/\*(.*?)\*/g, '<i>$1</i>');
        text = text.replace(/_(.*?)_/g, '<i>$1</i>');
        
        // Inline code
        text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
        
        // Links
        text = text.replace(/\[([^\]]+)\]\(([^\)]+)\)/g, '<a href="$2">$1</a>');
        
        // Strikethrough
        text = text.replace(/~~(.*?)~~/g, '<s>$1</s>');
        
        return text;
    }
}

class EditorJSToMarkdown {
    convert(editorjsData) {
        if (!editorjsData || !editorjsData.blocks) {
            return "";
        }
        
        const markdownLines = [];
        
        for (const block of editorjsData.blocks) {
            const blockType = block.type || '';
            const data = block.data || {};
            
            switch (blockType) {
                case 'header':
                    const level = data.level || 1;
                    const headerText = this._convertHtmlToMarkdown(data.text || '');
                    markdownLines.push('#'.repeat(level) + ' ' + headerText);
                    break;
                    
                case 'paragraph':
                    const paragraphText = this._convertHtmlToMarkdown(data.text || '');
                    if (paragraphText) {
                        markdownLines.push(paragraphText);
                    }
                    break;
                    
                case 'list':
                    const style = data.style || 'unordered';
                    const items = data.items || [];
                    
                    items.forEach((item, i) => {
                        const itemText = this._convertHtmlToMarkdown(item);
                        if (style === 'ordered') {
                            markdownLines.push(`${i + 1}. ${itemText}`);
                        } else {
                            markdownLines.push(`- ${itemText}`);
                        }
                    });
                    break;
                    
                case 'code':
                    const code = data.code || '';
                    markdownLines.push('```');
                    markdownLines.push(code);
                    markdownLines.push('```');
                    break;
                    
                case 'quote':
                    const quoteText = this._convertHtmlToMarkdown(data.text || '');
                    markdownLines.push(`> ${quoteText}`);
                    break;
                    
                case 'delimiter':
                    markdownLines.push('---');
                    break;
                    
                case 'table':
                    const content = data.content || [];
                    if (content.length > 0) {
                        // Add header row
                        if (content[0]) {
                            markdownLines.push('| ' + content[0].join(' | ') + ' |');
                            markdownLines.push('|' + '---|'.repeat(content[0].length));
                        }
                        
                        // Add data rows
                        for (let i = 1; i < content.length; i++) {
                            markdownLines.push('| ' + content[i].join(' | ') + ' |');
                        }
                    }
                    break;
            }
            
            // Add empty line between blocks (except between list items)
            if (blockType !== 'list' || block === editorjsData.blocks[editorjsData.blocks.length - 1]) {
                markdownLines.push('');
            }
        }
        
        // Join lines and clean up extra blank lines
        let markdown = markdownLines.join('\n');
        markdown = markdown.replace(/\n{3,}/g, '\n\n');
        return markdown.trim();
    }
    
    _convertHtmlToMarkdown(htmlText) {
        let text = htmlText;
        
        // Bold
        text = text.replace(/<b>(.*?)<\/b>/g, '**$1**');
        text = text.replace(/<strong>(.*?)<\/strong>/g, '**$1**');
        
        // Italic
        text = text.replace(/<i>(.*?)<\/i>/g, '*$1*');
        text = text.replace(/<em>(.*?)<\/em>/g, '*$1*');
        
        // Inline code
        text = text.replace(/<code>(.*?)<\/code>/g, '`$1`');
        
        // Links
        text = text.replace(/<a href="([^"]+)">([^<]+)<\/a>/g, '[$2]($1)');
        
        // Strikethrough
        text = text.replace(/<s>(.*?)<\/s>/g, '~~$1~~');
        text = text.replace(/<del>(.*?)<\/del>/g, '~~$1~~');
        
        // Underline (convert to bold as markdown doesn't have underline)
        text = text.replace(/<u>(.*?)<\/u>/g, '**$1**');
        
        // Mark/highlight (convert to bold)
        text = text.replace(/<mark>(.*?)<\/mark>/g, '**$1**');
        
        return text;
    }
}

// Make classes available globally
window.MarkdownToEditorJS = MarkdownToEditorJS;
window.EditorJSToMarkdown = EditorJSToMarkdown;