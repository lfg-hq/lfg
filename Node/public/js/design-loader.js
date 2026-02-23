/**
 * Design Schema Loader JavaScript
 * Handles loading design schema data from the server and updating the design tab with an iframe
 */
document.addEventListener('DOMContentLoaded', function() {
    // Add design schema loader to the ArtifactsLoader if it exists
    if (window.ArtifactsLoader) {
        /**
         * Load design schema from the API for the current project
         * @param {number} projectId - The ID of the current project
         */
        window.ArtifactsLoader.loadDesignSchema = function(projectId) {
            console.log(`[ArtifactsLoader] loadDesignSchema called with project ID: ${projectId}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading design schema');
                return;
            }
            
            // Get elements
            const designTab = document.getElementById('design');
            const designLoading = document.getElementById('design-loading');
            const designEmpty = document.getElementById('design-empty');
            const designFrameContainer = document.getElementById('design-frame-container');
            const designIframe = document.getElementById('design-iframe');
            
            if (!designTab || !designLoading || !designEmpty || !designFrameContainer || !designIframe) {
                console.warn('[ArtifactsLoader] One or more design tab elements not found');
                return;
            }
            
            // Show loading state
            designEmpty.style.display = 'none';
            designFrameContainer.style.display = 'none';
            designLoading.style.display = 'block';
            
            // Fetch design schema from API
            const url = `/projects/${projectId}/api/design-schema/`;
            console.log(`[ArtifactsLoader] Fetching design schema from API: ${url}`);
            
            fetch(url)
                .then(response => {
                    console.log(`[ArtifactsLoader] Design schema API response received, status: ${response.status}`);
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('[ArtifactsLoader] Design schema API data received:', data);
                    // Process design schema data
                    const designContent = data.content || '';
                    
                    if (!designContent) {
                        // Show empty state if no design schema found
                        console.log('[ArtifactsLoader] No design schema found, showing empty state');
                        designLoading.style.display = 'none';
                        designEmpty.style.display = 'block';
                        return;
                    }
                    
                    // Setup iframe content
                    const iframeDoc = designIframe.contentWindow.document;
                    
                    // Write content to the iframe
                    iframeDoc.open();
                    iframeDoc.write(designContent);
                    iframeDoc.close();
                    
                    // Make sure the iframe body takes up full height
                    const style = iframeDoc.createElement('style');
                    style.textContent = `
                        html, body {
                            height: 100%;
                            margin: 0;
                            padding: 0;
                            overflow: auto;
                        }
                        body {
                            min-height: 100%;
                        }
                    `;
                    iframeDoc.head.appendChild(style);
                    
                    // Show iframe container
                    designLoading.style.display = 'none';
                    designFrameContainer.style.display = 'block';
                    
                    // Adjust the container to fill available space
                    designTab.style.overflow = 'hidden';
                })
                .catch(error => {
                    console.error('Error fetching design schema:', error);
                    designLoading.style.display = 'none';
                    designEmpty.innerHTML = `
                        <div class="error-state">
                            <div class="error-state-icon">
                                <i class="fas fa-exclamation-triangle"></i>
                            </div>
                            <div class="error-state-text">
                                Error loading design schema. Please try again.
                            </div>
                        </div>
                    `;
                    designEmpty.style.display = 'block';
                });
        };
    }
    
    // Update the loadTabData function in artifacts.js if it exists
    const originalLoadTabData = window.loadTabData;
    if (typeof originalLoadTabData === 'function') {
        window.loadTabData = function(tabId) {
            // Call the original function
            originalLoadTabData(tabId);
            
            // Add support for design tab
            const projectId = window.getCurrentProjectId();
            if (tabId === 'design' && projectId && window.ArtifactsLoader && typeof window.ArtifactsLoader.loadDesignSchema === 'function') {
                window.ArtifactsLoader.loadDesignSchema(projectId);
            }
        };
    }
}); 