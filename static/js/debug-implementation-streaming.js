// Debug script for implementation streaming
console.log('=== IMPLEMENTATION STREAMING DEBUG ===');

// Check if artifacts panel is open
const artifactsPanel = document.getElementById('artifacts-panel');
const isPanelOpen = artifactsPanel && artifactsPanel.classList.contains('expanded');
console.log('1. Artifacts panel open:', isPanelOpen);

// Check if implementation tab is active
const implementationTab = document.getElementById('implementation');
const implementationTabButton = document.querySelector('.tab-button[data-tab="implementation"]');
const isTabActive = implementationTab && implementationTab.classList.contains('active');
console.log('2. Implementation tab active:', isTabActive);
console.log('   Tab button active:', implementationTabButton && implementationTabButton.classList.contains('active'));

// Check element visibility
const emptyState = document.getElementById('implementation-empty-state');
const container = document.getElementById('implementation-container');
const streamingContent = document.getElementById('implementation-streaming-content');

console.log('3. Element display states:');
console.log('   Empty state display:', emptyState ? emptyState.style.display : 'NOT FOUND');
console.log('   Container display:', container ? container.style.display : 'NOT FOUND');
console.log('   Container computed display:', container ? window.getComputedStyle(container).display : 'NOT FOUND');

// Check content
console.log('4. Streaming content:');
console.log('   Content element exists:', !!streamingContent);
console.log('   Content innerHTML length:', streamingContent ? streamingContent.innerHTML.length : 0);
console.log('   Content preview:', streamingContent ? streamingContent.innerHTML.substring(0, 200) : 'NO CONTENT');

// Check streaming state
console.log('5. Streaming state:');
console.log('   Window state exists:', !!window.implementationStreamingState);
console.log('   Is streaming:', window.implementationStreamingState?.isStreaming);
console.log('   Full content length:', window.implementationStreamingState?.fullContent?.length || 0);

// Force visibility as a test
console.log('\n=== FORCING VISIBILITY TEST ===');
if (!isPanelOpen && window.ArtifactsPanel) {
    console.log('Opening artifacts panel...');
    window.ArtifactsPanel.open();
}

if (!isTabActive && window.switchTab) {
    console.log('Switching to implementation tab...');
    window.switchTab('implementation');
}

setTimeout(() => {
    if (container) {
        console.log('Setting container display to block...');
        container.style.display = 'block';
    }
    if (emptyState) {
        console.log('Hiding empty state...');
        emptyState.style.display = 'none';
    }
    
    // Final check
    console.log('\n=== FINAL STATE ===');
    console.log('Container visible:', container && window.getComputedStyle(container).display !== 'none');
    console.log('Content exists:', streamingContent && streamingContent.innerHTML.length > 0);
    
    // Check if marked.js is available
    console.log('Marked.js available:', typeof marked !== 'undefined');
    
    // If content exists in state but not in DOM, try to render it
    if (window.implementationStreamingState?.fullContent && streamingContent) {
        console.log('Attempting to render content from state...');
        if (typeof marked !== 'undefined') {
            streamingContent.innerHTML = marked.parse(window.implementationStreamingState.fullContent);
        } else {
            streamingContent.innerHTML = window.implementationStreamingState.fullContent
                .replace(/\n/g, '<br>')
                .replace(/\t/g, '&nbsp;&nbsp;&nbsp;&nbsp;');
        }
        console.log('Content rendered, length:', streamingContent.innerHTML.length);
    }
}, 500);