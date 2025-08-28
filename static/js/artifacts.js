/**
 * Artifacts Panel JavaScript
 * Handles the functionality for the resizable and collapsible artifacts panel
 */
document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const appContainer = document.querySelector('.app-container');
    const artifactsPanel = document.getElementById('artifacts-panel');
    const artifactsToggle = document.getElementById('artifacts-toggle');
    const resizeHandle = document.getElementById('resize-handle');
    const chatContainer = document.querySelector('.chat-container');
    
    // Get the artifacts button (now in HTML header)
    const artifactsButton = document.getElementById('artifacts-button');
    
    // If elements don't exist, exit early
    if (!artifactsPanel || !artifactsToggle || !resizeHandle || !artifactsButton) {
        console.warn('Artifacts panel elements not found');
        return;
    }
    
    // Initialize state
    let isResizing = false;
    let lastDownX = 0;
    let panelWidth = parseInt(getComputedStyle(artifactsPanel).width) || 350;
    
    // Check if panel should start expanded (from localStorage)
    const shouldBeExpanded = localStorage.getItem('artifacts_expanded') === 'true';
    if (shouldBeExpanded) {
        artifactsPanel.classList.add('expanded');
        appContainer.classList.add('artifacts-expanded');
        artifactsButton.classList.add('active');
        updateChatContainerPosition(true);
    }
    
    // Toggle panel visibility when floating button is clicked
    artifactsButton.addEventListener('click', function() {
        const isExpanded = artifactsPanel.classList.toggle('expanded');
        artifactsButton.classList.toggle('active');
        
        // Update app container class to adjust chat container
        if (isExpanded) {
            appContainer.classList.add('artifacts-expanded');
            
            // When opening the panel, load data for the currently active tab
            const activeTab = document.querySelector('.tab-button.active');
            if (activeTab) {
                const tabId = activeTab.getAttribute('data-tab');
                console.log(`[ArtifactsPanel] Panel opened, loading data for active tab: ${tabId}`);
                if (window.switchTab) {
                    window.switchTab(tabId);
                }
            }
        } else {
            appContainer.classList.remove('artifacts-expanded');
        }
        
        // Store state in localStorage
        localStorage.setItem('artifacts_expanded', isExpanded);
        
        // Update chat container position
        updateChatContainerPosition(isExpanded);
    });
    
    // Close panel when toggle button inside panel is clicked
    artifactsToggle.addEventListener('click', function() {
        artifactsPanel.classList.remove('expanded');
        artifactsButton.classList.remove('active');
        appContainer.classList.remove('artifacts-expanded');
        
        // Store state in localStorage
        localStorage.setItem('artifacts_expanded', false);
        
        // Update chat container position
        updateChatContainerPosition(false);
    });
    
    // Resize functionality
    resizeHandle.addEventListener('mousedown', function(e) {
        // Only allow resizing when panel is expanded
        if (!artifactsPanel.classList.contains('expanded')) {
            return;
        }
        
        isResizing = true;
        lastDownX = e.clientX;
        resizeHandle.classList.add('active');
        
        // Prevent text selection during resize
        document.body.style.userSelect = 'none';
        
        // Add event listeners for mouse movement and release
        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
        
        e.preventDefault();
    });
    
    // Set up tab switching event listeners - direct implementation
    document.querySelectorAll('.tab-button').forEach(button => {
        button.addEventListener('click', function() {
            const tabId = this.getAttribute('data-tab');
            
            // If switchTab is available in the window object, use it
            if (window.switchTab) {
                window.switchTab(tabId);
            } else {
                // Otherwise, use a simple tab switching implementation
                const tabButtons = document.querySelectorAll('.tab-button');
                const tabPanes = document.querySelectorAll('.tab-pane');
                
                // Remove active class from all buttons and panes
                tabButtons.forEach(btn => btn.classList.remove('active'));
                tabPanes.forEach(pane => pane.classList.remove('active'));
                
                // Add active class to the selected button and pane
                this.classList.add('active');
                const selectedPane = document.getElementById(tabId);
                if (selectedPane) {
                    selectedPane.classList.add('active');
                }
            }
        });
    });
    
    // Function to handle markdown rendering of content
    function renderMarkdownContent() {
        if (typeof marked !== 'undefined') {
            // Find all markdown-content elements in the artifacts panel
            const markdownElements = artifactsPanel.querySelectorAll('.markdown-content');
            
            markdownElements.forEach(element => {
                const rawContent = element.getAttribute('data-raw-content');
                if (rawContent) {
                    // Render the raw content as markdown
                    element.innerHTML = marked.parse(rawContent);
                }
            });
        }
    }
    
    // Event listener for when content is dynamically added to the panel
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.type === 'childList') {
                // Check if any new markdown content was added
                renderMarkdownContent();
            }
        });
    });
    
    // Start observing changes to the artifacts content
    const artifactsContent = document.querySelector('.artifacts-content');
    if (artifactsContent) {
        observer.observe(artifactsContent, { childList: true, subtree: true });
    }
    
    function handleMouseMove(e) {
        if (!isResizing) return;
        
        // Calculate new width (right panel, so we subtract)
        const offsetX = lastDownX - e.clientX;
        const newWidth = panelWidth + offsetX;
        
        // Calculate maximum width (75% of window width)
        const maxWidth = window.innerWidth * 0.75;
        
        // Limit minimum and maximum width
        if (newWidth >= 250 && newWidth <= maxWidth) {
            artifactsPanel.style.width = newWidth + 'px';
            
            // Update chat container position
            updateChatContainerPosition(true, newWidth);
        }
    }
    
    function handleMouseUp() {
        if (isResizing) {
            isResizing = false;
            resizeHandle.classList.remove('active');
            
            // Update stored width
            panelWidth = parseInt(getComputedStyle(artifactsPanel).width);
            
            // Store width in localStorage
            localStorage.setItem('artifacts_width', panelWidth);
            
            // Re-enable text selection
            document.body.style.userSelect = '';
            
            // Remove event listeners
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
        }
    }
    
    // Touch support for mobile
    resizeHandle.addEventListener('touchstart', function(e) {
        // Only allow resizing when panel is expanded
        if (!artifactsPanel.classList.contains('expanded')) {
            return;
        }
        
        isResizing = true;
        lastDownX = e.touches[0].clientX;
        resizeHandle.classList.add('active');
        
        document.addEventListener('touchmove', handleTouchMove);
        document.addEventListener('touchend', handleTouchEnd);
        e.preventDefault();
    });
    
    function handleTouchMove(e) {
        if (!isResizing) return;
        
        const offsetX = lastDownX - e.touches[0].clientX;
        const newWidth = panelWidth + offsetX;
        const maxWidth = window.innerWidth * 0.75;
        
        if (newWidth >= 250 && newWidth <= maxWidth) {
            artifactsPanel.style.width = newWidth + 'px';
            updateChatContainerPosition(true, newWidth);
        }
        
        e.preventDefault();
    }
    
    function handleTouchEnd() {
        if (isResizing) {
            isResizing = false;
            resizeHandle.classList.remove('active');
            
            panelWidth = parseInt(getComputedStyle(artifactsPanel).width);
            localStorage.setItem('artifacts_width', panelWidth);
            
            document.removeEventListener('touchmove', handleTouchMove);
            document.removeEventListener('touchend', handleTouchEnd);
        }
    }
    
    // Function to update chat container position based on artifacts panel
    function updateChatContainerPosition(isExpanded, width) {
        if (!chatContainer) return;
        
        if (isExpanded) {
            const panelWidth = width || parseInt(getComputedStyle(artifactsPanel).width);
            // Update width and margin instead of right position
            chatContainer.style.width = `calc(100% - ${panelWidth}px)`;
            chatContainer.style.marginRight = `${panelWidth}px`;
        } else {
            // Reset to full width when panel is hidden
            chatContainer.style.width = '100%';
            chatContainer.style.marginRight = '0';
        }
    }
    
    // Load saved width from localStorage if available
    const savedWidth = localStorage.getItem('artifacts_width');
    if (savedWidth && !isNaN(parseInt(savedWidth))) {
        panelWidth = parseInt(savedWidth);
        artifactsPanel.style.width = panelWidth + 'px';
        
        // Only update chat container if panel is expanded
        if (artifactsPanel.classList.contains('expanded')) {
            updateChatContainerPosition(true, panelWidth);
        }
    }
    
    // Window resize handler
    window.addEventListener('resize', function() {
        const maxWidth = window.innerWidth * 0.75;
        
        // On mobile, reset panel width to full width
        if (window.innerWidth <= 768) {
            artifactsPanel.style.width = '100%';
            panelWidth = window.innerWidth;
        } else if (!isResizing) {
            // On desktop, ensure panel width is within bounds
            if (panelWidth > maxWidth) {
                panelWidth = maxWidth;
                artifactsPanel.style.width = maxWidth + 'px';
            }
        }
        
        // Update chat container position based on current state
        updateChatContainerPosition(artifactsPanel.classList.contains('expanded'), panelWidth);
    });
    
    // Public API for artifacts panel
    window.ArtifactsPanel = {
        /**
         * Add a new artifact to the panel
         * @param {Object} artifact - The artifact to add
         * @param {string} artifact.title - The title of the artifact
         * @param {string} artifact.description - The description of the artifact
         * @param {string} artifact.type - The type of artifact (image, code, etc.)
         * @param {string} artifact.content - The content or URL of the artifact
         */
        addArtifact: function(artifact) {
            const artifactsContent = document.querySelector('.artifacts-content');
            const emptyState = document.querySelector('.empty-state');
            
            if (!artifactsContent) return;
            
            // Hide empty state if it exists
            if (emptyState) {
                emptyState.style.display = 'none';
            }
            
            // Create artifact item
            const artifactItem = document.createElement('div');
            artifactItem.className = 'artifact-item';
            
            // Create title
            const title = document.createElement('div');
            title.className = 'artifact-title';
            title.textContent = artifact.title;
            
            // Create description
            const description = document.createElement('div');
            description.className = 'artifact-description';
            description.textContent = artifact.description;
            
            // Add to DOM
            artifactItem.appendChild(title);
            artifactItem.appendChild(description);
            
            // Add content based on type
            if (artifact.type === 'image' && artifact.content) {
                const img = document.createElement('img');
                img.src = artifact.content;
                img.alt = artifact.title;
                img.style.width = '100%';
                img.style.marginTop = '10px';
                img.style.borderRadius = '4px';
                artifactItem.appendChild(img);
            } else if (artifact.type === 'code' && artifact.content) {
                const pre = document.createElement('pre');
                pre.style.marginTop = '10px';
                pre.style.padding = '10px';
                pre.style.backgroundColor = 'rgba(0, 0, 0, 0.2)';
                pre.style.borderRadius = '4px';
                pre.style.overflow = 'auto';
                pre.style.fontSize = '0.85rem';
                
                const code = document.createElement('code');
                code.textContent = artifact.content;
                
                pre.appendChild(code);
                artifactItem.appendChild(pre);
            }
            
            // Add to the beginning of the list
            if (artifactsContent.firstChild) {
                artifactsContent.insertBefore(artifactItem, artifactsContent.firstChild);
            } else {
                artifactsContent.appendChild(artifactItem);
            }
            
            // Show panel if not expanded
            if (!artifactsPanel.classList.contains('expanded')) {
                artifactsButton.click();
            }
            
            return artifactItem;
        },
        
        /**
         * Clear all artifacts from the panel
         */
        clearArtifacts: function() {
            const artifactsContent = document.querySelector('.artifacts-content');
            const emptyState = document.querySelector('.empty-state');
            
            if (!artifactsContent) return;
            
            // Remove all artifact items
            const items = artifactsContent.querySelectorAll('.artifact-item');
            items.forEach(item => item.remove());
            
            // Show empty state if it exists
            if (emptyState) {
                emptyState.style.display = 'flex';
            }
        },
        
        /**
         * Check if the artifacts panel is currently open
         * @returns {boolean} True if the panel is open, false otherwise
         */
        isOpen: function() {
            return artifactsPanel.classList.contains('expanded');
        },
        
        /**
         * Open the artifacts panel
         */
        open: function() {
            this.toggle(true);
        },
        
        /**
         * Close the artifacts panel
         */
        close: function() {
            this.toggle(false);
        },
        
        /**
         * Toggle the artifacts panel visibility
         * If forceOpen is true, ensures the panel is opened
         */
        toggle: function(forceOpen) {
            console.log('[ArtifactsPanel] Toggle called with forceOpen:', forceOpen);
            
            // Get current state
            const isCurrentlyExpanded = artifactsPanel.classList.contains('expanded');
            console.log('[ArtifactsPanel] Current panel state - expanded:', isCurrentlyExpanded);
            
            // Determine if we should open, close, or toggle
            let shouldBeExpanded;
            if (forceOpen === true) {
                shouldBeExpanded = true; // Force open
            } else if (forceOpen === false) {
                shouldBeExpanded = false; // Force close
            } else {
                shouldBeExpanded = !isCurrentlyExpanded; // Toggle
            }
            
            console.log('[ArtifactsPanel] Should be expanded:', shouldBeExpanded);
            
            // Apply the state directly
            if (shouldBeExpanded) {
                // Open the panel
                artifactsPanel.classList.add('expanded');
                appContainer.classList.add('artifacts-expanded');
                artifactsButton.classList.add('active');
                
                // Update chat container
                updateChatContainerPosition(true);
                
                // When opening the panel, load data for the currently active tab
                const activeTab = document.querySelector('.tab-button.active');
                if (activeTab) {
                    const tabId = activeTab.getAttribute('data-tab');
                    console.log(`[ArtifactsPanel] Panel opened, loading data for active tab: ${tabId}`);
                    loadTabData(tabId);
                }
                
                console.log('[ArtifactsPanel] Panel opened');
            } else {
                // Close the panel
                artifactsPanel.classList.remove('expanded');
                appContainer.classList.remove('artifacts-expanded');
                artifactsButton.classList.remove('active');
                
                // Update chat container
                updateChatContainerPosition(false);
                
                console.log('[ArtifactsPanel] Panel closed');
            }
            
            // Store state in localStorage
            localStorage.setItem('artifacts_expanded', shouldBeExpanded);
        }
    };

    // Tab switching functionality
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabPanes = document.querySelectorAll('.tab-pane');

    function switchTab(tabId) {
        console.log(`[ArtifactsPanel] Switching to tab: ${tabId}`);
        console.log(`[ArtifactsPanel] Tab switching called at:`, new Date().toISOString());
        
        // Remove active class from all buttons and panes
        tabButtons.forEach(button => button.classList.remove('active'));
        tabPanes.forEach(pane => pane.classList.remove('active'));

        // Add active class to clicked button and corresponding pane
        const activeButton = document.querySelector(`[data-tab="${tabId}"]`);
        const activePane = document.getElementById(tabId);
        
        console.log(`[ArtifactsPanel] Active button found:`, !!activeButton);
        console.log(`[ArtifactsPanel] Active pane found:`, !!activePane);
        
        if (activeButton && activePane) {
            activeButton.classList.add('active');
            activePane.classList.add('active');
            
            console.log(`[ArtifactsPanel] About to call loadTabData for tab: ${tabId}`);
            // Automatically load data when switching to certain tabs
            loadTabData(tabId);
        } else {
            console.error(`[ArtifactsPanel] Could not find elements for tab: ${tabId}`);
        }
    }
    
    // Function to load data for specific tabs
    function loadTabData(tabId) {
        console.log(`[ArtifactsPanel] loadTabData called for tab: ${tabId}`);
        
        // Get the current project ID from the URL or data attribute
        const projectId = getCurrentProjectId();
        console.log(`[ArtifactsPanel] Current project ID: ${projectId}`);
        
        if (!projectId) {
            console.warn('[ArtifactsPanel] No project ID found, cannot load tab data');
            return;
        }
        
        // Load different data based on tab ID
        switch (tabId) {
            case 'features':
                if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadFeatures === 'function') {
                    window.ArtifactsLoader.loadFeatures(projectId);
                } else {
                    console.warn('[ArtifactsPanel] ArtifactsLoader.loadFeatures not found');
                }
                break;
            case 'personas':
                if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadPersonas === 'function') {
                    window.ArtifactsLoader.loadPersonas(projectId);
                } else {
                    console.warn('[ArtifactsPanel] ArtifactsLoader.loadPersonas not found');
                }
                break;
            case 'tickets':
                if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadTickets === 'function') {
                    window.ArtifactsLoader.loadTickets(projectId);
                } else {
                    console.warn('[ArtifactsPanel] ArtifactsLoader.loadTickets not found');
                }
                break;
            case 'filebrowser':
                if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadFileBrowser === 'function') {
                    window.ArtifactsLoader.loadFileBrowser(projectId);
                } else {
                    console.warn('[ArtifactsPanel] ArtifactsLoader.loadFileBrowser not found');
                }
                break;
            case 'checklist':
                if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadChecklist === 'function') {
                    window.ArtifactsLoader.loadChecklist(projectId);
                } else {
                    console.warn('[ArtifactsPanel] ArtifactsLoader.loadChecklist not found');
                }
                break;
            case 'codebase':
                console.log('[ArtifactsPanel] Codebase tab selected');
                console.log('[ArtifactsPanel] ArtifactsLoader available:', !!window.ArtifactsLoader);
                console.log('[ArtifactsPanel] loadCodebase function available:', !!(window.ArtifactsLoader && typeof window.ArtifactsLoader.loadCodebase === 'function'));
                
                // Load codebase explorer in iframe
                if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadCodebase === 'function') {
                    console.log('[ArtifactsPanel] Calling ArtifactsLoader.loadCodebase with project ID:', projectId);
                    window.ArtifactsLoader.loadCodebase(projectId);
                } else {
                    // Fallback to internal function if loader not available
                    console.log('[ArtifactsPanel] ArtifactsLoader not available, using fallback function');
                    loadCodebaseExplorer(projectId);
                }
                break;
            case 'apps':
                if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadAppPreview === 'function') {
                    console.log('[ArtifactsPanel] Loading app preview from artifacts.js');
                    window.ArtifactsLoader.loadAppPreview(projectId, null);
                } else {
                    console.warn('[ArtifactsPanel] ArtifactsLoader.loadAppPreview not found');
                }
                break;
            // case 'toolhistory':
            //     if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadToolHistory === 'function') {
            //         console.log('[ArtifactsPanel] Loading tool history from artifacts.js');
            //         window.ArtifactsLoader.loadToolHistory(projectId);
            //     } else {
            //         console.warn('[ArtifactsPanel] ArtifactsLoader.loadToolHistory not found');
            //     }
            //     break;
            case 'filebrowser':
                if (window.ArtifactsLoader && typeof window.ArtifactsLoader.loadFileBrowser === 'function') {
                    console.log('[ArtifactsPanel] Loading file browser from artifacts.js');
                    window.ArtifactsLoader.loadFileBrowser(projectId);
                } else {
                    console.warn('[ArtifactsPanel] ArtifactsLoader.loadFileBrowser not found');
                }
                break;
            // Add more cases as needed for other tabs
        }
    }
    
    // Function to load the codebase explorer in an iframe
    function loadCodebaseExplorer(projectId) {
        console.log(`[ArtifactsPanel] Loading codebase explorer for project ID: ${projectId}`);
        
        const codebaseTab = document.getElementById('codebase');
        const codebaseLoading = document.getElementById('codebase-loading');
        const codebaseEmpty = document.getElementById('codebase-empty');
        const codebaseFrameContainer = document.getElementById('codebase-frame-container');
        const codebaseIframe = document.getElementById('codebase-iframe');
        
        if (!codebaseTab || !codebaseLoading || !codebaseEmpty || !codebaseFrameContainer || !codebaseIframe) {
            console.warn('[ArtifactsPanel] Codebase UI elements not found');
            return;
        }
        
        // Show loading state
        codebaseLoading.style.display = 'block';
        codebaseEmpty.style.display = 'none';
        codebaseFrameContainer.style.display = 'none';
        
        // Set the iframe source to the development editor page
        const editorUrl = `/development/editor/?project_id=${projectId}`;
        console.log(`[ArtifactsPanel] Loading codebase from URL: ${editorUrl}`);
        
        codebaseIframe.onload = function() {
            // Hide loading and show iframe when loaded
            codebaseLoading.style.display = 'none';
            codebaseFrameContainer.style.display = 'block';
            console.log('[ArtifactsPanel] Codebase iframe loaded successfully');
        };
        
        codebaseIframe.onerror = function() {
            // Show error state if loading fails
            codebaseLoading.style.display = 'none';
            codebaseEmpty.style.display = 'block';
            codebaseEmpty.innerHTML = `
                <div class="error-state">
                    <div class="error-state-icon">
                        <i class="fas fa-exclamation-triangle"></i>
                    </div>
                    <div class="error-state-text">
                        Error loading codebase explorer. Please try again.
                    </div>
                </div>
            `;
            console.error('[ArtifactsPanel] Error loading codebase iframe');
        };
        
        codebaseIframe.src = editorUrl;
    }
    
    // Helper function to get current project ID from URL path only
    function getCurrentProjectId() {
        // Use the same logic as extractProjectIdFromPath in chat.js
        const pathParts = window.location.pathname.split('/').filter(part => part);
        if (pathParts.length >= 3 && pathParts[0] === 'chat' && pathParts[1] === 'project') {
            return pathParts[2];
        }
        
        throw new Error('No project ID found in path. Expected format: /chat/project/{id}/');
    }

    // Make switchTab function available globally
    window.switchTab = switchTab;

    // Add click event listeners to all tab buttons
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabId = button.getAttribute('data-tab');
            switchTab(tabId);
        });
    });
    
    // Load data for the initially active tab when ArtifactsLoader is ready
    function loadInitialTab() {
        const activeTab = document.querySelector('.tab-button.active');
        if (activeTab) {
            const tabId = activeTab.getAttribute('data-tab');
            const projectId = getCurrentProjectId();
            console.log(`[ArtifactsPanel] Initial load - loading data for active tab: ${tabId}, projectId: ${projectId}`);
            if (projectId) {
                loadTabData(tabId);
            } else {
                console.warn('[ArtifactsPanel] No project ID found on initial load');
            }
        }
    }
    
    // Check if ArtifactsLoader is already available
    if (window.ArtifactsLoader) {
        loadInitialTab();
    } else {
        // Wait for ArtifactsLoader to be ready
        const checkInterval = setInterval(() => {
            if (window.ArtifactsLoader) {
                clearInterval(checkInterval);
                loadInitialTab();
            }
        }, 50); // Check every 50ms
        
        // Stop checking after 5 seconds
        setTimeout(() => {
            clearInterval(checkInterval);
            console.error('[ArtifactsPanel] ArtifactsLoader not found after 5 seconds');
        }, 5000);
    }
}); 