// Test function to manually display implementation content
window.testImplementationDisplay = function() {
    console.log('=== TESTING IMPLEMENTATION DISPLAY ===');
    
    // 1. Open artifacts panel
    const artifactsPanel = document.getElementById('artifacts-panel');
    const appContainer = document.querySelector('.app-container');
    const artifactsButton = document.getElementById('artifacts-button');
    
    if (artifactsPanel) {
        artifactsPanel.classList.add('expanded');
        if (appContainer) appContainer.classList.add('artifacts-expanded');
        if (artifactsButton) artifactsButton.classList.add('active');
        console.log('✓ Artifacts panel opened');
    }
    
    // 2. Switch to implementation tab
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabPanes = document.querySelectorAll('.tab-pane');
    
    tabButtons.forEach(btn => btn.classList.remove('active'));
    tabPanes.forEach(pane => pane.classList.remove('active'));
    
    const implButton = document.querySelector('.tab-button[data-tab="implementation"]');
    const implPane = document.getElementById('implementation');
    
    if (implButton) implButton.classList.add('active');
    if (implPane) implPane.classList.add('active');
    console.log('✓ Implementation tab activated');
    
    // 3. Show container and hide empty state
    const emptyState = document.getElementById('implementation-empty-state');
    const container = document.getElementById('implementation-container');
    const streamingContent = document.getElementById('implementation-streaming-content');
    
    if (emptyState) {
        emptyState.style.display = 'none';
        console.log('✓ Empty state hidden');
    }
    
    if (container) {
        container.style.display = 'block';
        console.log('✓ Container shown');
    }
    
    // 4. Add test content
    if (streamingContent) {
        const testContent = `# Test Implementation Plan\n\nThis is a test to verify that content can be displayed in the implementation panel.\n\n## Features\n- Feature 1\n- Feature 2\n- Feature 3\n\n## Technical Details\nIf you can see this, the display is working correctly.`;
        
        if (typeof marked !== 'undefined') {
            streamingContent.innerHTML = marked.parse(testContent);
            console.log('✓ Test content added with marked.js');
        } else {
            streamingContent.innerHTML = testContent.replace(/\n/g, '<br>');
            console.log('✓ Test content added with basic formatting');
        }
        
        console.log('Content innerHTML length:', streamingContent.innerHTML.length);
    }
    
    // 5. Check final state
    console.log('\n=== FINAL STATE CHECK ===');
    console.log('Panel expanded:', artifactsPanel && artifactsPanel.classList.contains('expanded'));
    console.log('Tab active:', implPane && implPane.classList.contains('active'));
    console.log('Container display:', container && container.style.display);
    console.log('Container computed display:', container && window.getComputedStyle(container).display);
    console.log('Content exists:', streamingContent && streamingContent.innerHTML.length > 0);
    
    // 6. Check if content from streaming state exists
    if (window.implementationStreamingState && window.implementationStreamingState.fullContent) {
        console.log('\n=== STREAMING STATE CONTENT ===');
        console.log('Full content length:', window.implementationStreamingState.fullContent.length);
        console.log('Content preview:', window.implementationStreamingState.fullContent.substring(0, 200));
        
        // Try to render the actual streaming content
        if (streamingContent) {
            if (typeof marked !== 'undefined') {
                streamingContent.innerHTML = marked.parse(window.implementationStreamingState.fullContent);
            } else {
                streamingContent.innerHTML = window.implementationStreamingState.fullContent.replace(/\n/g, '<br>');
            }
            console.log('✓ Rendered actual streaming content');
        }
    }
};

// Also create a function to check the current state
window.checkImplementationState = function() {
    const state = {
        artifactsPanel: {
            exists: !!document.getElementById('artifacts-panel'),
            expanded: document.getElementById('artifacts-panel')?.classList.contains('expanded')
        },
        implementationTab: {
            button: {
                exists: !!document.querySelector('.tab-button[data-tab="implementation"]'),
                active: document.querySelector('.tab-button[data-tab="implementation"]')?.classList.contains('active')
            },
            pane: {
                exists: !!document.getElementById('implementation'),
                active: document.getElementById('implementation')?.classList.contains('active')
            }
        },
        elements: {
            emptyState: {
                exists: !!document.getElementById('implementation-empty-state'),
                display: document.getElementById('implementation-empty-state')?.style.display,
                computedDisplay: document.getElementById('implementation-empty-state') ? window.getComputedStyle(document.getElementById('implementation-empty-state')).display : null
            },
            container: {
                exists: !!document.getElementById('implementation-container'),
                display: document.getElementById('implementation-container')?.style.display,
                computedDisplay: document.getElementById('implementation-container') ? window.getComputedStyle(document.getElementById('implementation-container')).display : null
            },
            streamingContent: {
                exists: !!document.getElementById('implementation-streaming-content'),
                htmlLength: document.getElementById('implementation-streaming-content')?.innerHTML.length || 0
            }
        },
        streamingState: {
            exists: !!window.implementationStreamingState,
            isStreaming: window.implementationStreamingState?.isStreaming,
            contentLength: window.implementationStreamingState?.fullContent?.length || 0
        }
    };
    
    console.table(state.artifactsPanel);
    console.table(state.implementationTab.button);
    console.table(state.implementationTab.pane);
    console.table(state.elements.emptyState);
    console.table(state.elements.container);
    console.table(state.elements.streamingContent);
    console.table(state.streamingState);
    
    return state;
};

console.log('Test functions loaded. Use:');
console.log('- testImplementationDisplay() to test display');
console.log('- checkImplementationState() to check current state');