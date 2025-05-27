// Configure the marked library for proper markdown rendering including tables
document.addEventListener('DOMContentLoaded', () => {
    if (typeof marked !== 'undefined') {
        // Enable GitHub Flavored Markdown
        marked.setOptions({
            gfm: true,          // Enable GitHub Flavored Markdown
            breaks: true,       // Add <br> on line breaks
            headerIds: true,    // Add IDs to headers
            mangle: false,      // Don't mangle header IDs
            tables: true,       // Enable table support
            smartLists: true,   // Improve behavior of lists
            xhtml: false,       // Don't use XHTML compatible tags
            
            // Add syntax highlighting if needed
            highlight: function(code, lang) {
                if (typeof Prism !== 'undefined' && Prism.languages[lang]) {
                    return Prism.highlight(code, Prism.languages[lang], lang);
                }
                return code;
            }
        });
        
        console.log('Marked.js configured with table support and other extensions');
    } else {
        console.error('Marked.js library not found. Markdown may not render correctly.');
    }
}); 