/**
 * Debug script to find why PRD content isn't visible
 */

console.log("🔍 Finding PRD visibility issue...\n");

// 1. Check all PRD-related elements
console.log("1️⃣ Checking PRD elements:");
const elements = {
    'prd tab': document.getElementById('prd'),
    'prd-empty-state': document.getElementById('prd-empty-state'),
    'prd-container': document.getElementById('prd-container'),
    'prd-streaming-content': document.getElementById('prd-streaming-content')
};

for (const [name, elem] of Object.entries(elements)) {
    if (elem) {
        const computed = window.getComputedStyle(elem);
        console.log(`\n${name}:`, {
            exists: true,
            display: computed.display,
            visibility: computed.visibility,
            opacity: computed.opacity,
            position: computed.position,
            zIndex: computed.zIndex,
            width: elem.offsetWidth,
            height: elem.offsetHeight,
            hasContent: elem.innerHTML.length > 0,
            contentLength: elem.innerHTML.length
        });
        
        // Check if element is actually visible
        const rect = elem.getBoundingClientRect();
        console.log(`  Bounding rect:`, {
            top: rect.top,
            left: rect.left,
            width: rect.width,
            height: rect.height,
            isVisible: rect.width > 0 && rect.height > 0
        });
        
        // Check parent visibility
        let parent = elem.parentElement;
        let hiddenParent = null;
        while (parent && parent !== document.body) {
            const parentStyle = window.getComputedStyle(parent);
            if (parentStyle.display === 'none' || parentStyle.visibility === 'hidden') {
                hiddenParent = parent;
                break;
            }
            parent = parent.parentElement;
        }
        
        if (hiddenParent) {
            console.log(`  ⚠️ Hidden parent found:`, hiddenParent.id || hiddenParent.className);
        }
    } else {
        console.log(`\n${name}: ❌ NOT FOUND`);
    }
}

// 2. Check tab visibility
console.log("\n2️⃣ Checking tab visibility:");
const prdTabPane = document.getElementById('prd');
if (prdTabPane) {
    console.log("PRD tab pane:", {
        hasActiveClass: prdTabPane.classList.contains('active'),
        classes: prdTabPane.className
    });
}

// 3. Check if content is being overwritten
console.log("\n3️⃣ Setting up content monitor:");
const contentElement = document.getElementById('prd-streaming-content');
if (contentElement) {
    // Store current content
    const currentContent = contentElement.innerHTML;
    console.log(`Current content length: ${currentContent.length}`);
    
    // Monitor for changes
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            console.log('🚨 PRD content changed!', {
                type: mutation.type,
                addedNodes: mutation.addedNodes.length,
                removedNodes: mutation.removedNodes.length,
                newLength: contentElement.innerHTML.length
            });
            console.trace('Content change stack trace');
        });
    });
    
    observer.observe(contentElement, {
        childList: true,
        characterData: true,
        subtree: true
    });
    
    console.log("✅ Monitoring PRD content for changes...");
}

// 4. Check z-index stacking
console.log("\n4️⃣ Checking z-index stacking:");
const allElements = document.querySelectorAll('*');
const highZIndexElements = Array.from(allElements).filter(el => {
    const zIndex = window.getComputedStyle(el).zIndex;
    return zIndex !== 'auto' && parseInt(zIndex) > 100;
}).map(el => ({
    element: el.id || el.className,
    zIndex: window.getComputedStyle(el).zIndex
}));

if (highZIndexElements.length > 0) {
    console.log("Elements with high z-index:", highZIndexElements);
}

console.log("\n✅ Debug complete. Check the output above for issues.");