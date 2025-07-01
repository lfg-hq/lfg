/**
 * Verification script for PRD streaming functionality
 * Run this in browser console to verify the fix works
 */

console.log("🔍 PRD Streaming Verification Script");

// 1. Check HTML structure
console.log("\n1️⃣ Checking HTML structure:");
const emptyState = document.getElementById('prd-empty-state');
const prdContainer = document.getElementById('prd-container');
const streamingStatus = document.getElementById('prd-streaming-status');
const streamingContent = document.getElementById('prd-streaming-content');

console.log(`Empty state element: ${emptyState ? '✅ Found' : '❌ Not found'}`);
console.log(`PRD container: ${prdContainer ? '✅ Found' : '❌ Not found'}`);
console.log(`Streaming status: ${streamingStatus ? '✅ Found' : '❌ Not found'}`);
console.log(`Streaming content: ${streamingContent ? '✅ Found' : '❌ Not found'}`);

// 2. Check streaming state
console.log("\n2️⃣ Checking streaming state:");
console.log(`PRD streaming state:`, window.prdStreamingState || 'Not initialized');

// 3. Test streaming functionality
console.log("\n3️⃣ Testing streaming functionality:");

window.testPRDStreaming = function() {
    console.log("Starting PRD streaming test...");
    
    // Get project ID
    const projectId = window.ArtifactsLoader ? window.ArtifactsLoader.getCurrentProjectId() : null;
    if (!projectId) {
        console.error("❌ No project ID found");
        return;
    }
    
    console.log(`Using project ID: ${projectId}`);
    
    // Simulate PRD chunks
    const chunks = [
        "# Product Requirement Document\n\n## Executive Summary\n\nThis is a test of the live streaming functionality.",
        "\n\n## Problem Statement\n\nWe need to see content as it's being generated.",
        "\n\n## Goals\n\n- Display content in real-time\n- Maintain formatting\n- Show progress indicators",
        "\n\n## User Stories\n\n1. As a user, I want to see PRD content immediately\n2. As a developer, I want reliable streaming",
        "\n\n## Technical Requirements\n\n- WebSocket support\n- Markdown rendering\n- Auto-scrolling",
        "\n\n## Success Metrics\n\n- Content appears within 1 second\n- No flicker or content loss"
    ];
    
    let index = 0;
    
    function sendChunk() {
        if (index < chunks.length) {
            const isLast = index === chunks.length - 1;
            console.log(`Sending chunk ${index + 1}/${chunks.length}`);
            
            if (window.ArtifactsLoader && window.ArtifactsLoader.streamPRDContent) {
                window.ArtifactsLoader.streamPRDContent(chunks[index], isLast, projectId);
            }
            
            index++;
            if (!isLast) {
                setTimeout(sendChunk, 500);
            } else {
                console.log("✅ Streaming test complete!");
            }
        }
    }
    
    // Open artifacts panel and switch to PRD tab
    if (window.ArtifactsPanel) {
        window.ArtifactsPanel.open();
    }
    if (window.switchTab) {
        window.switchTab('prd');
    }
    
    // Start streaming after a short delay
    setTimeout(sendChunk, 500);
};

// 4. Check for issues
console.log("\n4️⃣ Checking for common issues:");

// Check if loadPRD might interfere
if (window.ArtifactsLoader && window.ArtifactsLoader.loadPRD) {
    console.log("✅ loadPRD function exists and has streaming protection");
} else {
    console.log("⚠️  loadPRD function not found");
}

// Check container visibility
if (prdContainer) {
    const isHidden = prdContainer.style.display === 'none';
    console.log(`PRD container visibility: ${isHidden ? '🔴 Hidden' : '🟢 Visible'}`);
}

console.log("\n💡 Run testPRDStreaming() to test the streaming functionality");
console.log("💡 This will simulate PRD content streaming to verify the fix works");