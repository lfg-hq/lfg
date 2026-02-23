// Editor.js tools loader with promise-based loading confirmation
(function() {
    'use strict';
    
    // Track loading state
    window.editorJSToolsLoaded = false;
    window.editorJSLoadPromise = null;
    
    // Define the tools we expect to load
    const expectedTools = [
        'EditorJS',
        'Header', 
        'List',
        'CodeTool',
        'InlineCode',
        'Delimiter',
        'Marker',
        'Underline',
        'Quote',
        'Table'
    ];
    
    // Create a promise that resolves when all tools are loaded
    window.editorJSLoadPromise = new Promise((resolve) => {
        let checkInterval;
        let checkCount = 0;
        const maxChecks = 100; // 10 seconds max wait (100 * 100ms)
        
        const checkToolsLoaded = () => {
            checkCount++;
            
            // Check if all expected tools are available
            const loadedTools = expectedTools.filter(tool => window[tool] !== undefined);
            const allLoaded = loadedTools.length === expectedTools.length;
            
            console.log(`[EditorJS Loader] Check ${checkCount}: ${loadedTools.length}/${expectedTools.length} tools loaded`);
            
            if (allLoaded || checkCount >= maxChecks) {
                clearInterval(checkInterval);
                window.editorJSToolsLoaded = true;
                
                if (allLoaded) {
                    console.log('[EditorJS Loader] All tools loaded successfully:', loadedTools);
                } else {
                    console.warn('[EditorJS Loader] Timeout waiting for tools. Loaded:', loadedTools);
                }
                
                resolve({
                    success: allLoaded,
                    loadedTools: loadedTools,
                    missingTools: expectedTools.filter(tool => window[tool] === undefined)
                });
            }
        };
        
        // Start checking every 100ms
        checkInterval = setInterval(checkToolsLoaded, 100);
        
        // Also check immediately
        checkToolsLoaded();
    });
    
    // Helper function to wait for tools to load
    window.waitForEditorJSTools = function() {
        return window.editorJSLoadPromise;
    };
    
    // Helper to get available tools configuration
    window.getEditorJSToolsConfig = function() {
        const tools = {};
        
        if (window['Header']) {
            tools.header = {
                class: window['Header'],
                config: {
                    levels: [1, 2, 3, 4, 5, 6],
                    defaultLevel: 2
                }
            };
        }
        if (window['List']) {
            tools.list = {
                class: window['List'],
                inlineToolbar: true
            };
        }
        if (window['CodeTool']) {
            tools.code = window['CodeTool'];
        }
        if (window['InlineCode']) {
            tools.inlineCode = window['InlineCode'];
        }
        if (window['Delimiter']) {
            tools.delimiter = window['Delimiter'];
        }
        if (window['Marker']) {
            tools.marker = window['Marker'];
        }
        if (window['Underline']) {
            tools.underline = window['Underline'];
        }
        if (window['Quote']) {
            tools.quote = window['Quote'];
        }
        if (window['Table']) {
            tools.table = window['Table'];
        }
        
        return tools;
    };
})();