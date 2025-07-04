/**
 * Debug helper for PRD streaming state
 */

window.debugPRDState = function() {
    console.log("\n🔍 === PRD STATE DEBUG ===");
    
    // 1. Check elements
    console.log("\n1️⃣ DOM Elements:");
    const elements = {
        'prd-empty-state': document.getElementById('prd-empty-state'),
        'prd-container': document.getElementById('prd-container'),
        'prd-streaming-status': document.getElementById('prd-streaming-status'),
        'prd-streaming-content': document.getElementById('prd-streaming-content')
    };
    
    for (const [id, elem] of Object.entries(elements)) {
        if (elem) {
            console.log(`✅ ${id}:`, {
                exists: true,
                display: elem.style.display || 'default',
                innerHTML_length: elem.innerHTML?.length || 0,
                visible: elem.offsetParent !== null
            });
        } else {
            console.log(`❌ ${id}: NOT FOUND`);
        }
    }
    
    // 2. Check streaming state
    console.log("\n2️⃣ Streaming State:");
    if (window.prdStreamingState) {
        console.log("prdStreamingState:", {
            isStreaming: window.prdStreamingState.isStreaming,
            contentLength: window.prdStreamingState.fullContent?.length || 0,
            projectId: window.prdStreamingState.projectId
        });
        
        if (window.prdStreamingState.fullContent) {
            console.log("Content preview:", window.prdStreamingState.fullContent.substring(0, 100) + "...");
        }
    } else {
        console.log("❌ No prdStreamingState found");
    }
    
    // 3. Check PRD tab
    console.log("\n3️⃣ PRD Tab State:");
    const prdTab = document.getElementById('prd');
    if (prdTab) {
        console.log("PRD tab:", {
            exists: true,
            className: prdTab.className,
            isActive: prdTab.classList.contains('active'),
            childrenCount: prdTab.children.length
        });
    }
    
    // 4. Check artifacts panel
    console.log("\n4️⃣ Artifacts Panel:");
    const panel = document.getElementById('artifacts-panel');
    if (panel) {
        console.log("Panel:", {
            exists: true,
            isExpanded: panel.classList.contains('expanded')
        });
    }
    
    console.log("\n=== END DEBUG ===\n");
};

// Also create a function to manually clear PRD state
window.clearPRDState = function() {
    console.log("🗑️ Clearing PRD state...");
    
    // Reset streaming state
    if (window.prdStreamingState) {
        window.prdStreamingState.isStreaming = false;
        window.prdStreamingState.fullContent = '';
    }
    
    // Clear content
    const streamingContent = document.getElementById('prd-streaming-content');
    if (streamingContent) {
        streamingContent.innerHTML = '';
    }
    
    // Reset status
    const status = document.getElementById('prd-streaming-status');
    if (status) {
        status.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Generating PRD...';
    }
    
    console.log("✅ PRD state cleared");
};

console.log("🛠️ Debug helpers loaded:");
console.log("- debugPRDState() : Check current PRD state");
console.log("- clearPRDState() : Clear PRD content and state");

// Run initial state check
debugPRDState();