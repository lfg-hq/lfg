/**
 * App Loader JavaScript
 * Handles loading the app running on the sandbox port into an iframe
 */

// Create a self-contained module for the app loader to avoid scope issues
(function() {
    // Flag to track if loadAppPreview has been defined
    let isAppPreviewDefined = false;

    // Main initialization function
    function initAppLoader() {
        console.log('[AppLoader] Initializing app loader...');
        
        // Define loadAppPreview function on ArtifactsLoader if it exists
        if (window.ArtifactsLoader && !isAppPreviewDefined) {
            console.log('[AppLoader] ArtifactsLoader found, adding loadAppPreview function');
            
            /**
             * Load running app from the sandbox port for the current project or conversation
             * @param {number} projectId - The ID of the current project
             * @param {number} conversationId - The ID of the current conversation (optional)
             */
            window.ArtifactsLoader.loadAppPreview = function(projectId, conversationId) {
                console.log(`[AppLoader] loadAppPreview called with project ID: ${projectId}, conversation ID: ${conversationId}`);
                
                if (!projectId && !conversationId) {
                    console.warn('[AppLoader] No project ID or conversation ID provided for loading app');
                    return;
                }
                
                // Get elements
                const appTab = document.getElementById('apps');
                const appLoading = document.getElementById('app-loading');
                const appEmpty = document.getElementById('app-empty');
                const appFrameContainer = document.getElementById('app-frame-container');
                const appIframe = document.getElementById('app-iframe');
                
                if (!appTab || !appLoading || !appEmpty || !appFrameContainer || !appIframe) {
                    console.warn('[AppLoader] One or more app tab elements not found');
                    return;
                }
                
                // Show loading state
                appEmpty.style.display = 'none';
                appFrameContainer.style.display = 'none';
                appLoading.style.display = 'block';
                
                // Build the request data
                const requestData = {};
                if (projectId) {
                    requestData.project_id = projectId;
                } else if (conversationId) {
                    requestData.conversation_id = conversationId;
                }
                
                // Fetch sandbox information from the API
                const url = '/coding/get_sandbox_info/';
                console.log(`[AppLoader] Fetching sandbox info from API: ${url}`, requestData);
                
                fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCSRFToken(),
                    },
                    body: JSON.stringify(requestData)
                })
                .then(response => {
                    console.log(`[AppLoader] Sandbox info API response received, status: ${response.status}`);
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('[AppLoader] Sandbox info API data received:', data);
                    
                    // Check if port mappings exist and not empty
                    if (!data.port_mappings || data.port_mappings.length === 0) {
                        console.warn('[AppLoader] No port mappings found in API response');
                        showEmptyState("No port mappings available. Make sure your app is running on port 8000 in the sandbox.");
                        return;
                    }
                    
                    // Get the port from port mappings
                    const port = data.port_mappings[0].host_port;
                    
                    if (!port) {
                        // Show empty state if no port is available
                        console.warn('[AppLoader] Port value is missing or invalid in API response');
                        showEmptyState("No running app available. Make sure your app is running on port 8000 in the sandbox.");
                        return;
                    }
                    
                    // Construct the URL for the iframe
                    const appUrl = `http://${window.location.hostname}:${port}/`;
                    console.log(`[AppLoader] Loading app from URL: ${appUrl}`);
                    
                    // Set iframe source
                    appIframe.src = appUrl;
                    
                    // Add load event listeners
                    appIframe.onload = function() {
                        appLoading.style.display = 'none';
                        appFrameContainer.style.display = 'block';
                        console.log('[AppLoader] App iframe loaded successfully');
                    };
                    
                    appIframe.onerror = function(e) {
                        console.error('[AppLoader] Error loading app iframe:', e);
                        showErrorState("Error loading app. Please check if your app is running.");
                    };
                    
                    // Adjust the container to fill available space
                    appTab.style.overflow = 'hidden';
                })
                .catch(error => {
                    console.error('[AppLoader] Error fetching sandbox info:', error);
                    showErrorState(`Error loading app: ${error.message}`);
                });
                
                // Helper function to show the empty state
                function showEmptyState(message) {
                    appLoading.style.display = 'none';
                    appEmpty.style.display = 'block';
                    appEmpty.innerHTML = `
                        <div class="empty-state">
                            <div class="empty-state-icon">
                                <i class="fas fa-cube"></i>
                            </div>
                            <div class="empty-state-text">
                                ${message}
                            </div>
                        </div>
                    `;
                }
                
                // Helper function to show error state
                function showErrorState(message) {
                    appLoading.style.display = 'none';
                    appEmpty.style.display = 'block';
                    appEmpty.innerHTML = `
                        <div class="error-state">
                            <div class="error-state-icon">
                                <i class="fas fa-exclamation-triangle"></i>
                            </div>
                            <div class="error-state-text">
                                ${message}
                            </div>
                        </div>
                    `;
                }
            };
            
            isAppPreviewDefined = true;
            console.log('[AppLoader] loadAppPreview function has been defined');
        } else if (!window.ArtifactsLoader) {
            console.warn('[AppLoader] ArtifactsLoader not found, will try again later');
        }
    }

    // Setup tab handler with better checking
    function setupTabHandler() {
        if (typeof window.loadTabData === 'function') {
            console.log('[AppLoader] Found loadTabData function, extending it to handle apps tab');
            
            const originalLoadTabData = window.loadTabData;
            window.loadTabData = function(tabId) {
                // Call the original function
                originalLoadTabData(tabId);
                
                console.log(`[AppLoader] Tab changed to: ${tabId}`);
                
                // Add support for app tab
                if (tabId === 'apps') {
                    console.log('[AppLoader] Apps tab selected, loading app preview');
                    
                    // If ArtifactsLoader doesn't exist yet or loadAppPreview isn't defined, try to initialize
                    if (!window.ArtifactsLoader || !window.ArtifactsLoader.loadAppPreview) {
                        console.log('[AppLoader] ArtifactsLoader or loadAppPreview not ready, initializing now');
                        initAppLoader();
                    }
                    
                    // Get project or conversation ID
                    const projectId = window.getCurrentProjectId ? window.getCurrentProjectId() : null;
                    const conversationId = window.getCurrentConversationId ? window.getCurrentConversationId() : null;
                    
                    console.log(`[AppLoader] Project ID: ${projectId}, Conversation ID: ${conversationId}`);
                    
                    if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadAppPreview === 'function') {
                        window.ArtifactsLoader.loadAppPreview(projectId, conversationId);
                    } else {
                        console.error('[AppLoader] loadAppPreview function not available despite initialization attempt');
                        // Create ArtifactsLoader if it doesn't exist as a fallback
                        if (!window.ArtifactsLoader) {
                            console.log('[AppLoader] Creating ArtifactsLoader as fallback');
                            window.ArtifactsLoader = {};
                            initAppLoader();
                            if (typeof window.ArtifactsLoader.loadAppPreview === 'function') {
                                window.ArtifactsLoader.loadAppPreview(projectId, conversationId);
                            }
                        }
                    }
                }
            };
            
            return true;
        }
        
        return false;
    }

    // Helper function to get CSRF token
    function getCSRFToken() {
        let csrfToken = null;
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const cookiePair = cookie.trim().split('=');
            if (cookiePair[0] === 'csrftoken') {
                csrfToken = decodeURIComponent(cookiePair[1]);
                break;
            }
        }
        return csrfToken;
    }

    // Helper functions to get project and conversation IDs
    function getCurrentProjectId() {
        return window.getCurrentProjectId ? window.getCurrentProjectId() : 
               (window.project_id || (window.PROJECT_DATA && window.PROJECT_DATA.id));
    }

    function getCurrentConversationId() {
        return window.getCurrentConversationId ? window.getCurrentConversationId() : 
               (window.conversation_id || (window.CONVERSATION_DATA && window.CONVERSATION_DATA.id));
    }

    // Initialize on DOMContentLoaded
    document.addEventListener('DOMContentLoaded', function() {
        // Initial attempt to initialize
        initAppLoader();
        
        // Try to set up the tab handler 
        if (!setupTabHandler()) {
            console.log('[AppLoader] loadTabData not available yet, will retry shortly');
            
            // If not available, try again in a short while
            let attempts = 0;
            const maxAttempts = 5;
            const checkInterval = setInterval(function() {
                attempts++;
                if (setupTabHandler()) {
                    console.log('[AppLoader] Successfully set up tab handler after waiting');
                    clearInterval(checkInterval);
                } else if (attempts >= maxAttempts) {
                    console.error('[AppLoader] loadTabData still not available after maximum attempts');
                    clearInterval(checkInterval);
                }
            }, 1000);
        }
        
        // Add direct click handler to the apps tab button as a backup
        document.addEventListener('click', function(event) {
            const target = event.target.closest('.tab-button[data-tab="apps"]');
            if (target) {
                console.log('[AppLoader] Apps tab button clicked directly');
                
                // Try to initialize if not already done
                if (!window.ArtifactsLoader || !window.ArtifactsLoader.loadAppPreview) {
                    console.log('[AppLoader] Initializing from click handler');
                    initAppLoader();
                }
                
                // Get project or conversation ID
                const projectId = getCurrentProjectId();
                const conversationId = getCurrentConversationId();
                
                if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadAppPreview === 'function') {
                    console.log('[AppLoader] Calling loadAppPreview from direct click handler');
                    window.ArtifactsLoader.loadAppPreview(projectId, conversationId);
                } else {
                    console.error('[AppLoader] loadAppPreview still not available after direct click');
                }
            }
        });
        
        // Additional safety: check every few seconds until ArtifactsLoader is available
        // This helps with pages where the ArtifactsLoader is loaded after our script
        if (!window.ArtifactsLoader) {
            console.log('[AppLoader] Setting up interval to check for ArtifactsLoader');
            let loaderAttempts = 0;
            const maxLoaderAttempts = 10;
            const loaderInterval = setInterval(function() {
                loaderAttempts++;
                if (window.ArtifactsLoader && !isAppPreviewDefined) {
                    console.log('[AppLoader] ArtifactsLoader found through interval check');
                    initAppLoader();
                    clearInterval(loaderInterval);
                } else if (isAppPreviewDefined || loaderAttempts >= maxLoaderAttempts) {
                    console.log('[AppLoader] Stopping interval checks - found:', isAppPreviewDefined);
                    clearInterval(loaderInterval);
                }
            }, 2000);
        }
    });
})(); 