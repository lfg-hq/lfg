/**
 * Artifacts Loader JavaScript
 * Handles loading artifact data from the server and updating the artifacts panel
 */

// Global helper functions
window.showToast = function(message, type = 'info') {
    // Get or create toast container
    let toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.className = 'messages';
        document.body.appendChild(toastContainer);
    }
    
    const toast = document.createElement('div');
    toast.className = `alert alert-${type}`;
    toast.textContent = message;
    
    // Make toast clickable to dismiss
    toast.addEventListener('click', function() {
        this.style.animation = 'fadeOut 0.3s ease-out forwards';
        setTimeout(() => this.remove(), 300);
    });
    
    toastContainer.appendChild(toast);
    
    // Auto-remove toast after 5 seconds (CSS animation handles the fade out)
    setTimeout(() => {
        if (toast.parentNode) {
            toast.remove();
        }
    }, 5500); // 5s display + 0.5s fade out
};

window.getCookie = function(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
};

// Make showLinearProjectSelectionPopup globally accessible
window.showLinearProjectSelectionPopup = async function(projectId, teams) {
    const showToast = window.showToast;
    const getCookie = window.getCookie;
    
    // Create popup overlay
    const overlay = document.createElement('div');
    overlay.className = 'linear-popup-overlay';
    overlay.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 10000; display: flex; align-items: center; justify-content: center;';
    
    // Create popup container
    const popup = document.createElement('div');
    popup.className = 'linear-popup';
    popup.style.cssText = 'background: #2a2a2a; padding: 30px; border-radius: 8px; max-width: 500px; width: 90%; max-height: 80vh; overflow-y: auto; box-shadow: 0 4px 20px rgba(0,0,0,0.5);';
    
    // Check if we have teams
    if (!teams || teams.length === 0) {
        popup.innerHTML = `
            <h3 style="color: #fff; margin-bottom: 20px;">No Linear Teams Found</h3>
            <p style="color: #ccc; margin-bottom: 20px;">Please make sure your Linear API key has access to at least one team.</p>
            <button class="close-popup-btn" style="background: #666; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer;">Close</button>
        `;
        overlay.appendChild(popup);
        document.body.appendChild(overlay);
        
        popup.querySelector('.close-popup-btn').addEventListener('click', () => {
            overlay.remove();
        });
        return;
    }
    
    // Get current project info
    const projectResponse = await fetch(`/projects/${projectId}/?format=json`);
    const projectData = await projectResponse.json();
    const currentLinearProjectId = projectData.linear_project_id;
    
    let popupHTML = `
        <h3 style="color: #fff; margin-bottom: 20px;">Sync with Linear Team</h3>
        <div class="linear-teams-container">
    `;
    
    // Always show team selection
    popupHTML += `
        <div style="margin-bottom: 20px;">
            <label style="color: #ccc; display: block; margin-bottom: 8px;">Select Team:</label>
            <select id="linear-team-select" style="width: 100%; padding: 8px; background: #1a1a1a; border: 1px solid #444; color: #fff; border-radius: 4px;">
                ${teams.map(team => `<option value="${team.id}">${team.name}</option>`).join('')}
            </select>
        </div>
    `;
    
    popupHTML += `
        <div style="display: flex; justify-content: flex-end; gap: 10px;">
            <button class="cancel-popup-btn" style="background: #666; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer;">Cancel</button>
            <button class="confirm-popup-btn" style="background: #5856d6; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer;">Sync with Selected Team</button>
        </div>
    </div>
    `;
    
    popup.innerHTML = popupHTML;
    overlay.appendChild(popup);
    document.body.appendChild(overlay);
    
    // Elements
    const teamSelect = popup.querySelector('#linear-team-select');
    // Project-related elements removed - syncing with teams only
    const confirmBtn = popup.querySelector('.confirm-popup-btn');
    const cancelBtn = popup.querySelector('.cancel-popup-btn');
    
    // Project-related code removed - syncing directly with teams
    
    // No team change handler needed since we're syncing with the selected team
    
    // Create project functionality removed - syncing with teams only
    /* Removed create project handler */
    
    // Cancel handler
    cancelBtn.addEventListener('click', () => {
        overlay.remove();
    });
    
    // Confirm handler
    confirmBtn.addEventListener('click', async () => {
        const selectedTeamId = teams.length === 1 ? teams[0].id : teamSelect.value;
        
        if (!selectedTeamId) {
            showToast('Please select a team', 'error');
            return;
        }
        
        // Save the selected team to the backend
        const saveResponse = await fetch(`/projects/${projectId}/update/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: new URLSearchParams({
                'name': projectData.name || '',
                'description': projectData.description || '',
                'linear_sync_enabled': 'on',
                'linear_team_id': selectedTeamId,
                'linear_project_id': ''
            })
        });
        
        if (saveResponse.ok) {
            // Close popup
            overlay.remove();
            
            // Show progress overlay
            const progressOverlay = document.createElement('div');
            progressOverlay.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); display: flex; align-items: center; justify-content: center; z-index: 10000;';
            
            const progressContainer = document.createElement('div');
            progressContainer.style.cssText = 'background: #2a2a2a; padding: 30px; border-radius: 8px; min-width: 400px; text-align: center;';
            
            progressContainer.innerHTML = `
                <h3 style="color: #fff; margin-bottom: 20px;">Syncing with Linear</h3>
                <div style="margin-bottom: 15px;">
                    <div style="background: #444; height: 20px; border-radius: 10px; overflow: hidden;">
                        <div id="sync-progress-bar" style="background: #5856d6; height: 100%; width: 0%; transition: width 0.3s ease;"></div>
                    </div>
                </div>
                <p id="sync-progress-text" style="color: #ccc; margin: 0;">Initializing sync...</p>
            `;
            
            progressOverlay.appendChild(progressContainer);
            document.body.appendChild(progressOverlay);
            
            // Simulate progress while waiting for response
            const progressBar = document.getElementById('sync-progress-bar');
            const progressText = document.getElementById('sync-progress-text');
            
            progressBar.style.width = '20%';
            progressText.textContent = 'Connecting to Linear...';
            
            try {
                const syncResponse = await fetch(`/projects/${projectId}/api/linear/sync/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken')
                    },
                });
                
                progressBar.style.width = '60%';
                progressText.textContent = 'Processing items...';
                
                const syncData = await syncResponse.json();
                
                progressBar.style.width = '100%';
                
                if (syncData.success) {
                    progressText.textContent = `Synced ${syncData.results?.created || 0} items successfully!`;
                    
                    // Show completion for a moment
                    setTimeout(() => {
                        progressOverlay.remove();
                        showToast(syncData.message || 'Tasks synced successfully!', 'success');
                        // Reload the checklist if ArtifactsLoader is available
                        if (window.ArtifactsLoader && window.ArtifactsLoader.loadChecklist) {
                            window.ArtifactsLoader.loadChecklist(projectId);
                        }
                    }, 1500);
                } else {
                    progressText.textContent = 'Sync failed!';
                    progressBar.style.background = '#f44336';
                    
                    setTimeout(() => {
                        progressOverlay.remove();
                        showToast(syncData.error || 'Failed to sync tasks', 'error');
                    }, 1500);
                }
            } catch (error) {
                progressBar.style.width = '100%';
                progressBar.style.background = '#f44336';
                progressText.textContent = 'Network error!';
                
                setTimeout(() => {
                    progressOverlay.remove();
                    showToast('Network error during sync', 'error');
                }, 1500);
            }
        } else {
            showToast('Failed to save Linear team selection', 'error');
        }
    });
    
    // Close on overlay click
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            overlay.remove();
        }
    });
};

document.addEventListener('DOMContentLoaded', function() {
    
    // Helper function to get current conversation ID from URL or global variables
    function getCurrentConversationId() {
        // Try to get conversation ID from URL first
        const urlParams = new URLSearchParams(window.location.search);
        const urlConversationId = urlParams.get('conversation_id');
        
        if (urlConversationId) {
            return urlConversationId;
        }
        
        // Then try from path (format: /chat/conversation/{id}/)
        const pathMatch = window.location.pathname.match(/\/chat\/conversation\/(\d+)\//);
        if (pathMatch && pathMatch[1]) {
            return pathMatch[1];
        }
        
        // Try global variables if available
        if (window.conversation_id) {
            return window.conversation_id;
        }
        
        if (window.CONVERSATION_DATA && window.CONVERSATION_DATA.id) {
            return window.CONVERSATION_DATA.id;
        }
        
        return null;
    }
    
    // Helper function to get current project ID from URL or global variables
    function getCurrentProjectId() {
        // Try several methods to get the project ID
        
        // Method 1: URL pathname (for direct project URLs with UUID)
        const pathMatch = window.location.pathname.match(/\/chat\/project\/([a-f0-9-]+)\//);
        if (pathMatch) {
            console.log('[ArtifactsLoader] Found project ID (UUID) in URL path:', pathMatch[1]);
            return pathMatch[1];
        }
        
        // Method 2: URL parameters
        const urlParams = new URLSearchParams(window.location.search);
        const projectIdParam = urlParams.get('project_id');
        if (projectIdParam) {
            console.log('[ArtifactsLoader] Found project ID in URL params:', projectIdParam);
            return projectIdParam;
        }
        
        // Method 3: File browser project ID
        if (window.currentFileBrowserProjectId) {
            console.log('[ArtifactsLoader] Found project ID from file browser:', window.currentFileBrowserProjectId);
            return window.currentFileBrowserProjectId;
        }
        
        // Method 4: Global variables
        if (window.project_id) {
            console.log('[ArtifactsLoader] Found project ID in global variable:', window.project_id);
            return window.project_id;
        }
        
        // Method 5: Data attributes on body or main container
        const bodyProjectId = document.body.getAttribute('data-project-id');
        if (bodyProjectId) {
            console.log('[ArtifactsLoader] Found project ID in body data attribute:', bodyProjectId);
            return bodyProjectId;
        }
        
        console.warn('[ArtifactsLoader] Could not find project ID using any method');
        return null;
    }

    // Helper function to get CSRF token
    function getCsrfToken() {
        // Try to get it from the meta tag first (Django's standard location)
        const metaToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        if (metaToken) {
            return metaToken;
        }
        
        // Then try the input field (another common location)
        const inputToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        if (inputToken) {
            return inputToken;
        }
        
        // Finally try to get it from cookies
        const cookieValue = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrftoken='))
            ?.split('=')[1];
        
        if (cookieValue) {
            return cookieValue;
        }
        
        console.error('[ArtifactsLoader] CSRF token not found in any location');
        return '';
    }

    // Initialize the artifact loaders
    window.ArtifactsLoader = {
        /**
         * Get the current project ID from various sources
         * @returns {number|null} The current project ID or null if not found
         */
        getCurrentProjectId: getCurrentProjectId,
        
        /**
         * Load features from the API for the current project
         * @param {number} projectId - The ID of the current project
         */
        loadFeatures: function(projectId) {
            console.log(`[ArtifactsLoader] loadFeatures called with project ID: ${projectId}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading features');
                return;
            }
            
            // Get features tab content element
            const featuresTab = document.getElementById('features');
            if (!featuresTab) {
                console.warn('[ArtifactsLoader] Features tab element not found');
                return;
            }
            
            // Show loading state
            console.log('[ArtifactsLoader] Showing loading state');
            featuresTab.innerHTML = '<div class="loading-state"><div class="spinner"></div><div>Loading features...</div></div>';
            
            // Fetch features from API
            const url = `/projects/${projectId}/api/features/`;
            console.log(`[ArtifactsLoader] Fetching features from API: ${url}`);
            
            fetch(url)
                .then(response => {
                    console.log(`[ArtifactsLoader] API response received, status: ${response.status}`);
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('[ArtifactsLoader] API data received:', data);
                    // Process features data
                    const features = data.features || [];
                    console.log(`[ArtifactsLoader] Found ${features.length} features`);
                    
                    if (features.length === 0) {
                        // Show empty state if no features found
                        console.log('[ArtifactsLoader] No features found, showing empty state');
                        featuresTab.innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">
                                    <i class="fas fa-list-check"></i>
                                </div>
                                <div class="empty-state-text">
                                    No features defined yet.
                                </div>
                            </div>
                        `;
                        return;
                    }
                    
                    // Create features content
                    console.log('[ArtifactsLoader] Rendering features to UI');
                    let featuresHtml = '<div class="features-list">';
                    
                    features.forEach(feature => {
                        const priorityClass = feature.priority.toLowerCase().replace(' ', '-');
                        
                        featuresHtml += `
                            <div class="feature-item">
                                <div class="feature-header">
                                    <h3 class="feature-name">${feature.name}</h3>
                                    <span class="feature-priority ${priorityClass}">${feature.priority}</span>
                                </div>
                                <div class="feature-description">${feature.description}</div>
                                <div class="feature-details markdown-content">
                                    ${typeof marked !== 'undefined' ? marked.parse(feature.details) : feature.details}
                                </div>
                            </div>
                        `;
                    });
                    
                    featuresHtml += '</div>';
                    featuresTab.innerHTML = featuresHtml;
                    
                    // Switch to the features tab to show the newly loaded content
                    if (window.switchTab) {
                        window.switchTab('features');
                    } else if (window.ArtifactsPanel && typeof window.ArtifactsPanel.toggle === 'function') {
                        // Make the artifacts panel visible if it's not
                        window.ArtifactsPanel.toggle();
                    }
                })
                .catch(error => {
                    console.error('Error fetching features:', error);
                    featuresTab.innerHTML = `
                        <div class="error-state">
                            <div class="error-state-icon">
                                <i class="fas fa-exclamation-triangle"></i>
                            </div>
                            <div class="error-state-text">
                                Error loading features. Please try again.
                            </div>
                        </div>
                    `;
                });
        },
        
        /**
         * Load personas from the API for the current project
         * @param {number} projectId - The ID of the current project
         */
        loadPersonas: function(projectId) {
            console.log(`[ArtifactsLoader] loadPersonas called with project ID: ${projectId}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading personas');
                return;
            }
            
            // Get personas tab content element
            const personasTab = document.getElementById('personas');
            if (!personasTab) {
                console.warn('[ArtifactsLoader] Personas tab element not found');
                return;
            }
            
            // Show loading state
            console.log('[ArtifactsLoader] Showing loading state for personas');
            personasTab.innerHTML = '<div class="loading-state"><div class="spinner"></div><div>Loading personas...</div></div>';
            
            // Fetch personas from API
            const url = `/projects/${projectId}/api/personas/`;
            console.log(`[ArtifactsLoader] Fetching personas from API: ${url}`);
            
            fetch(url)
                .then(response => {
                    console.log(`[ArtifactsLoader] Personas API response received, status: ${response.status}`);
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('[ArtifactsLoader] Personas API data received:', data);
                    // Process personas data
                    const personas = data.personas || [];
                    console.log(`[ArtifactsLoader] Found ${personas.length} personas`);
                    
                    if (personas.length === 0) {
                        // Show empty state if no personas found
                        console.log('[ArtifactsLoader] No personas found, showing empty state');
                        personasTab.innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">
                                    <i class="fas fa-users"></i>
                                </div>
                                <div class="empty-state-text">
                                    No personas defined yet.
                                </div>
                            </div>
                        `;
                        return;
                    }
                    
                    // Create personas content
                    console.log('[ArtifactsLoader] Rendering personas to UI');
                    let personasHtml = '<div class="personas-list">';
                    
                    personas.forEach(persona => {
                        personasHtml += `
                            <div class="persona-item">
                                <div class="persona-header">
                                    <h3 class="persona-name">${persona.name}</h3>
                                    <span class="persona-role">${persona.role}</span>
                                </div>
                                <div class="persona-description markdown-content">
                                    ${typeof marked !== 'undefined' ? marked.parse(persona.description) : persona.description}
                                </div>
                            </div>
                        `;
                    });
                    
                    personasHtml += '</div>';
                    personasTab.innerHTML = personasHtml;
                })
                .catch(error => {
                    console.error('Error fetching personas:', error);
                    personasTab.innerHTML = `
                        <div class="error-state">
                            <div class="error-state-icon">
                                <i class="fas fa-exclamation-triangle"></i>
                            </div>
                            <div class="error-state-text">
                                Error loading personas. Please try again.
                            </div>
                        </div>
                    `;
                });
        },
        
        /**
         * Load PRD from the API for the current project
         * @param {number} projectId - The ID of the current project
         * @param {string} prdName - Optional PRD name to load (defaults to currently selected)
         */
        loadPRD: function(projectId, prdName = null) {
            console.log(`[ArtifactsLoader] loadPRD called with project ID: ${projectId}, PRD name: ${prdName}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading PRD');
                return;
            }
            
            // Check if we're currently streaming PRD content
            if (window.prdStreamingState && window.prdStreamingState.isStreaming) {
                console.log('[ArtifactsLoader] PRD is currently streaming, skipping loadPRD');
                return;
            }
            
            // Get PRD tab content element
            const prdTab = document.getElementById('prd');
            if (!prdTab) {
                console.warn('[ArtifactsLoader] PRD tab element not found');
                return;
            }
            
            // Get the existing elements
            const prdContainer = document.getElementById('prd-container');
            const emptyState = document.getElementById('prd-empty-state');
            const streamingContent = document.getElementById('prd-streaming-content');
            const streamingStatus = document.getElementById('prd-streaming-status');
            const prdSelector = document.getElementById('prd-selector');
            
            // Clear any existing content first
            if (streamingContent) {
                streamingContent.innerHTML = '';
            }
            
            // Hide both container and empty state initially
            if (prdContainer) prdContainer.style.display = 'none';
            if (emptyState) emptyState.style.display = 'none';
            
            // Show loading state using the existing streaming status element
            console.log('[ArtifactsLoader] Showing loading state for PRD');
            if (prdContainer && streamingStatus) {
                prdContainer.style.display = 'block';
                streamingStatus.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Loading PRDs...';
                streamingStatus.style.color = '#8b5cf6';
            }
            
            // First fetch the list of PRDs
            const listUrl = `/projects/${projectId}/api/prd/?list=1`;
            console.log(`[ArtifactsLoader] Fetching PRD list from API: ${listUrl}`);
            
            fetch(listUrl)
                .then(response => response.json())
                .then(listData => {
                    console.log('[ArtifactsLoader] PRD list received:', listData);
                    const prds = listData.prds || [];
                    
                    // Update PRD selector
                    if (prdSelector) {
                        const selectorWrapper = document.querySelector('.prd-selector-wrapper');
                        const selectorButton = document.getElementById('prd-selector-button');
                        const selectorText = document.getElementById('prd-selector-text');
                        const selectorDropdown = document.getElementById('prd-selector-dropdown');
                        
                        if (prds.length > 1) {
                            // Show custom selector if there are multiple PRDs
                            if (selectorWrapper) selectorWrapper.style.display = 'block';
                            
                            // Update hidden select options
                            prdSelector.innerHTML = prds.map(prd => 
                                `<option value="${prd.name}">${prd.name}</option>`
                            ).join('');
                            
                            // Build custom dropdown options
                            if (selectorDropdown) {
                                selectorDropdown.innerHTML = prds.map(prd => 
                                    `<div class="prd-dropdown-option ${prd.name === prdName ? 'selected' : ''}" data-value="${prd.name}">
                                        <span class="prd-name">${prd.name}</span>
                                    </div>`
                                ).join('');
                            }
                            
                            console.log(`[ArtifactsLoader] Showing PRD selector with ${prds.length} PRDs`);
                        } else {
                            // Hide selector if only one PRD
                            if (selectorWrapper) selectorWrapper.style.display = 'none';
                            console.log('[ArtifactsLoader] Hiding PRD selector - only one PRD exists');
                        }
                        
                        // Set the current PRD name
                        if (!prdName && prds.length > 0) {
                            prdName = prds[0].name;
                        }
                        if (prds.length > 0) {
                            prdSelector.value = prdName;
                            if (selectorText) selectorText.textContent = prdName;
                        }
                    }
                    
                    
                    // Now fetch the specific PRD content
                    const url = `/projects/${projectId}/api/prd/?prd_name=${encodeURIComponent(prdName || 'Main PRD')}`;
                    console.log(`[ArtifactsLoader] Fetching PRD from API: ${url}`);
                    
                    return fetch(url);
                })
                .then(response => {
                    console.log(`[ArtifactsLoader] PRD API response received, status: ${response.status}`);
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('[ArtifactsLoader] PRD API data received:', data);
                    // Process PRD data
                    const prdContent = data.content || '';
                    
                    if (!prdContent) {
                        // Show empty state if no PRD found
                        console.log('[ArtifactsLoader] No PRD found, showing empty state');
                        const emptyState = document.getElementById('prd-empty-state');
                        const prdContainer = document.getElementById('prd-container');
                        
                        if (emptyState) emptyState.style.display = 'block';
                        if (prdContainer) prdContainer.style.display = 'none';
                        return;
                    }
                    
                    // Use existing containers to display PRD content
                    const emptyState = document.getElementById('prd-empty-state');
                    const prdContainer = document.getElementById('prd-container');
                    const streamingContent = document.getElementById('prd-streaming-content');
                    const streamingStatus = document.getElementById('prd-streaming-status');
                    
                    if (emptyState) emptyState.style.display = 'none';
                    if (prdContainer) prdContainer.style.display = 'block';
                    
                    // Update status to show it's a loaded PRD
                    if (streamingStatus) {
                        streamingStatus.textContent = data.updated_at ? `Last updated: ${data.updated_at}` : 'Loaded from server';
                    }
                    
                    // Add action buttons to the prd-actions-container
                    const prdActionsContainer = document.querySelector('.prd-actions-container');
                    if (prdActionsContainer) {
                        // Get current PRD name
                        const currentPrdName = data.name || 'Main PRD';
                        
                        // Clear any existing content and add the action buttons
                        prdActionsContainer.innerHTML = `
                            <div class="prd-actions" style="display: flex; gap: 4px;">
                                <button class="artifact-edit-btn" id="prd-edit-btn" data-project-id="${projectId}" title="Edit" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.7'">
                                    <i class="fas fa-edit"></i>
                                </button>
                                <button class="artifact-copy-btn" id="prd-copy-btn" data-project-id="${projectId}" title="Copy" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.7'">
                                    <i class="fas fa-copy"></i>
                                </button>
                                <button class="artifact-download-btn" id="prd-download-btn" data-project-id="${projectId}" title="Download PDF" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.7'">
                                    <i class="fas fa-download"></i>
                                </button>
                                <button class="artifact-delete-btn" id="prd-delete-action-btn" data-project-id="${projectId}" data-prd-name="${currentPrdName}" title="Delete PRD" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'; this.style.color='#ef4444'" onmouseout="this.style.opacity='0.7'; this.style.color='#fff'">
                                    <i class="fas fa-trash"></i>
                                </button>
                                
                            </div>
                        `;
                    }
                    
                    // Render the PRD content
                    if (streamingContent) {
                        let parsedContent = prdContent;
                        
                        // Ensure marked is loaded and configured
                        if (typeof marked !== 'undefined') {
                            try {
                                // Configure marked if not already done
                                if (!window.markedConfigured) {
                                    marked.setOptions({
                                        gfm: true,          // Enable GitHub Flavored Markdown
                                        breaks: true,       // Add <br> on line breaks
                                        headerIds: true,    // Add IDs to headers
                                        mangle: false,      // Don't mangle header IDs
                                        tables: true,       // Enable table support
                                        smartLists: true,   // Improve behavior of lists
                                        xhtml: false        // Don't use XHTML compatible tags
                                    });
                                    window.markedConfigured = true;
                                    console.log('[ArtifactsLoader] Marked.js configured for PRD rendering');
                                }
                                
                                parsedContent = marked.parse(prdContent);
                                console.log('[ArtifactsLoader] PRD markdown parsed successfully');
                            } catch (e) {
                                console.error('[ArtifactsLoader] Error parsing PRD markdown:', e);
                                // Fallback to basic line break conversion
                                parsedContent = prdContent
                                    .replace(/##/g, '\n##')
                                    .replace(/\n/g, '<br>');
                            }
                        } else {
                            console.warn('[ArtifactsLoader] Marked.js not available for PRD, using fallback rendering');
                            // Basic fallback rendering
                            parsedContent = prdContent
                                .replace(/##/g, '\n##')
                                .replace(/\n/g, '<br>');
                        }
                        
                        streamingContent.innerHTML = parsedContent;
                    }
                    
                    // Clear streaming state since we're loading saved content
                    if (window.prdStreamingState) {
                        window.prdStreamingState.isStreaming = false;
                        window.prdStreamingState.fullContent = prdContent;
                    }
                    
                    // Add click event listener for the edit button
                    const editBtn = document.getElementById('prd-edit-btn');
                    if (editBtn) {
                        editBtn.addEventListener('click', function() {
                            ArtifactsEditor.enablePRDEdit(projectId, prdContent);
                        });
                    }
                    
                    // Add click event listener for the PDF download button
                    const downloadBtn = document.getElementById('prd-download-btn');
                    if (downloadBtn) {
                        downloadBtn.addEventListener('click', function() {
                            ArtifactsLoader.downloadPRDAsPDF(projectId, data.title || 'Product Requirement Document', prdContent);
                        });
                    }
                    
                    // Add click event listener for the copy button
                    const copyBtn = document.getElementById('prd-copy-btn');
                    if (copyBtn) {
                        copyBtn.addEventListener('click', function() {
                            ArtifactsLoader.copyToClipboard(prdContent, 'PRD content');
                        });
                    }
                    
                    // Add click event listener for the delete button
                    const deleteActionBtn = document.getElementById('prd-delete-action-btn');
                    if (deleteActionBtn) {
                        deleteActionBtn.addEventListener('click', function() {
                            const prdNameToDelete = this.getAttribute('data-prd-name');
                            if (confirm(`Are you sure you want to delete the PRD "${prdNameToDelete}"?`)) {
                                // Delete the PRD
                                fetch(`/projects/${projectId}/api/prd/?prd_name=${encodeURIComponent(prdNameToDelete)}`, {
                                    method: 'DELETE',
                                    headers: {
                                        'X-CSRFToken': getCsrfToken()
                                    }
                                })
                                .then(response => response.json())
                                .then(deleteData => {
                                    if (deleteData.success) {
                                        window.showToast(`PRD "${prdNameToDelete}" deleted successfully`, 'success');
                                        // Load Main PRD after deletion
                                        window.ArtifactsLoader.loadPRD(projectId, 'Main PRD');
                                    } else {
                                        window.showToast(`Error deleting PRD: ${deleteData.error || 'Unknown error'}`, 'error');
                                    }
                                })
                                .catch(error => {
                                    console.error('[ArtifactsLoader] Error deleting PRD:', error);
                                    window.showToast('Error deleting PRD', 'error');
                                });
                            }
                        });
                    }
                })
                .catch(error => {
                    console.error('Error fetching PRD:', error);
                    
                    // Hide container and show empty state with error
                    if (prdContainer) prdContainer.style.display = 'none';
                    if (emptyState) {
                        emptyState.style.display = 'block';
                        emptyState.innerHTML = `
                            <div class="error-state">
                                <div class="error-state-icon">
                                    <i class="fas fa-exclamation-triangle"></i>
                                </div>
                                <div class="error-state-text">
                                    Error loading PRD. Please try again.
                                </div>
                            </div>
                        `;
                    }
                });
        },
        
        /**
         * Stream PRD content live as it's being generated
         * @param {string} contentChunk - The chunk of PRD content to append
         * @param {boolean} isComplete - Whether this is the final chunk
         * @param {number} projectId - The ID of the current project
         * @param {string} prdName - The name of the PRD being streamed
         */
        streamPRDContent: function(contentChunk, isComplete, projectId, prdName = 'Main PRD') {
            console.log(`[ArtifactsLoader] streamPRDContent called with chunk length: ${contentChunk ? contentChunk.length : 0}, isComplete: ${isComplete}`);
            console.log(`[ArtifactsLoader] Content chunk preview: ${contentChunk ? contentChunk.substring(0, 100) : 'null/undefined'}...`);
            console.log(`[ArtifactsLoader] Project ID: ${projectId}, PRD Name: ${prdName}`);
            
            // Debug: Show if content has line breaks
            if (contentChunk) {
                const lineBreakCount = (contentChunk.match(/\n/g) || []).length;
                console.log(`[ArtifactsLoader] Line breaks in chunk: ${lineBreakCount}`);
                console.log(`[ArtifactsLoader] Raw chunk (first 200 chars):`, JSON.stringify(contentChunk.substring(0, 200)));
            }
            
            // CONSOLE STREAMING OUTPUT IN ARTIFACTS LOADER
            console.log('\n' + '='.repeat(80));
            console.log('🟡 PRD STREAM IN ARTIFACTS LOADER');
            console.log(`📅 Time: ${new Date().toISOString()}`);
            console.log(`📏 Length: ${contentChunk ? contentChunk.length : 0} chars`);
            console.log(`✅ Complete: ${isComplete}`);
            if (contentChunk) {
                console.log(`📝 Content: ${contentChunk.substring(0, 200)}${contentChunk.length > 200 ? '...' : ''}`);
            }
            console.log('='.repeat(80) + '\n');
            
            // Initialize PRD streaming state if not exists
            if (!window.prdStreamingState) {
                window.prdStreamingState = {
                    fullContent: '',
                    isStreaming: false,
                    projectId: projectId,
                    prdName: prdName
                };
            }
            
            // Ensure PRD tab is active FIRST before getting elements
            const prdTabButton = document.querySelector('.tab-button[data-tab="prd"]');
            const prdTabPane = document.getElementById('prd');
            if (prdTabButton && !prdTabButton.classList.contains('active')) {
                console.log('[ArtifactsLoader] Activating PRD tab for streaming');
                // Remove active class from all tabs and panes
                document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
                document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
                // Activate PRD tab
                prdTabButton.classList.add('active');
                if (prdTabPane) prdTabPane.classList.add('active');
            }
            
            // Get the elements from the template AFTER ensuring tab is active
            const emptyState = document.getElementById('prd-empty-state');
            const prdContainer = document.getElementById('prd-container');
            const streamingStatus = document.getElementById('prd-streaming-status');
            const streamingContent = document.getElementById('prd-streaming-content');
            
            console.log('[ArtifactsLoader] Element check:', {
                emptyState: !!emptyState,
                prdContainer: !!prdContainer,
                streamingStatus: !!streamingStatus,
                streamingContent: !!streamingContent
            });
            
            if (!prdContainer || !streamingContent) {
                console.error('[ArtifactsLoader] PRD container or streaming content element not found');
                console.error('[ArtifactsLoader] prdContainer:', prdContainer);
                console.error('[ArtifactsLoader] streamingContent:', streamingContent);
                
                // Try to restore the HTML structure if elements are missing
                const prdTab = document.getElementById('prd');
                if (prdTab && !prdContainer) {
                    console.log('[ArtifactsLoader] Attempting to restore PRD HTML structure');
                    prdTab.innerHTML = `
                        <!-- Empty state (shown by default) -->
                        <div class="empty-state" id="prd-empty-state" style="display: none;">
                            <div class="empty-state-icon">
                                <i class="fas fa-file-alt"></i>
                            </div>
                            <div class="empty-state-text">
                                No PRD content available yet.
                            </div>
                        </div>
                        
                        <!-- PRD Container (hidden by default, shown during streaming) -->
                        <div class="prd-container" id="prd-container" style="display: block;">
                            <div class="prd-header">
                                <h2>Product Requirement Document</h2>
                                <div class="prd-meta" style="display: flex; justify-content: space-between; align-items: center;">
                                    <span class="streaming-status" id="prd-streaming-status" style="color: #8b5cf6;">
                                        <i class="fas fa-circle-notch fa-spin"></i> Generating PRD...
                                    </span>
                                </div>
                            </div>
                            <div class="prd-streaming-container prd-content markdown-content" id="prd-streaming-content" style="color: #e2e8f0; padding: 20px;">
                                <!-- Content will be streamed here -->
                            </div>
                        </div>
                    `;
                    
                    // Re-get the elements after restoration
                    const newPrdContainer = document.getElementById('prd-container');
                    const newStreamingContent = document.getElementById('prd-streaming-content');
                    if (newPrdContainer && newStreamingContent) {
                        console.log('[ArtifactsLoader] HTML structure restored successfully');
                        // Continue with the restored elements
                        return this.streamPRDContent(contentChunk, isComplete, projectId);
                    }
                }
                
                return;
            }
            
            // Start streaming if not already started
            if (!window.prdStreamingState.isStreaming) {
                window.prdStreamingState.isStreaming = true;
                window.prdStreamingState.fullContent = '';
                window.prdStreamingState.projectId = projectId;
                
                // Ensure empty state is hidden and container is visible
                if (emptyState) {
                    emptyState.style.display = 'none';
                    console.log('[ArtifactsLoader] Empty state hidden');
                }
                if (prdContainer) {
                    prdContainer.style.display = 'block';
                    console.log('[ArtifactsLoader] PRD container shown');
                }
                
                // Reset streaming status
                if (streamingStatus) {
                    streamingStatus.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Generating PRD...';
                    streamingStatus.style.color = '#8b5cf6';
                }
                
                console.log('[ArtifactsLoader] PRD Streaming started - showing streaming container');
            }
            
            // Append the new content chunk
            if (contentChunk) {
                console.log('[ArtifactsLoader] Appending content chunk to streaming container');
                console.log('[DEBUG] streamingContent element exists:', !!streamingContent);
                console.log('[DEBUG] streamingContent ID:', streamingContent?.id);
                
                // Ensure visibility is maintained during streaming
                if (emptyState && emptyState.style.display !== 'none') {
                    emptyState.style.display = 'none';
                    console.log('[ArtifactsLoader] Empty state was visible during streaming, hiding it');
                }
                if (prdContainer && prdContainer.style.display !== 'block') {
                    prdContainer.style.display = 'block';
                    console.log('[ArtifactsLoader] PRD container was hidden during streaming, showing it');
                }
                
                // Store the raw content
                window.prdStreamingState.fullContent += contentChunk;
                
                // For better streaming experience, we'll render the full content each time
                // This ensures markdown formatting is properly applied across chunks
                let fullParsedContent = window.prdStreamingState.fullContent;
                
                // Ensure marked is loaded and configured
                if (typeof marked !== 'undefined') {
                    try {
                        // Configure marked if not already done
                        if (!window.markedConfigured) {
                            marked.setOptions({
                                gfm: true,          // Enable GitHub Flavored Markdown
                                breaks: true,       // Add <br> on line breaks
                                headerIds: true,    // Add IDs to headers
                                mangle: false,      // Don't mangle header IDs
                                tables: true,       // Enable table support
                                smartLists: true,   // Improve behavior of lists
                                xhtml: false        // Don't use XHTML compatible tags
                            });
                            window.markedConfigured = true;
                            console.log('[ArtifactsLoader] Marked.js configured for PRD rendering');
                        }
                        
                        fullParsedContent = marked.parse(window.prdStreamingState.fullContent);
                        console.log('[ArtifactsLoader] Markdown parsed successfully');
                    } catch (e) {
                        console.error('[ArtifactsLoader] Error parsing markdown:', e);
                        // Fallback to basic line break conversion
                        fullParsedContent = window.prdStreamingState.fullContent
                            .replace(/##/g, '\n##')
                            .replace(/\n/g, '<br>');
                    }
                } else {
                    console.warn('[ArtifactsLoader] Marked.js not available, using fallback rendering');
                    // Basic fallback rendering
                    fullParsedContent = window.prdStreamingState.fullContent
                        .replace(/##/g, '\n##')
                        .replace(/\n/g, '<br>');
                }
                
                console.log('[DEBUG] About to set innerHTML, parsed content length:', fullParsedContent.length);
                streamingContent.innerHTML = fullParsedContent;
                console.log('[DEBUG] innerHTML set successfully');
                console.log('[ArtifactsLoader] Total content length now:', window.prdStreamingState.fullContent.length);
                
                // Auto-scroll to show new content
                if (prdContainer) {
                    prdContainer.scrollTop = prdContainer.scrollHeight;
                }
            } else if (!isComplete) {
                console.warn('[ArtifactsLoader] Empty content chunk received (not complete)');
            }
            
            // If streaming is complete, update the status
            if (isComplete) {
                if (streamingStatus) {
                    streamingStatus.innerHTML = '<i class="fas fa-check-circle" style="color: #10b981;"></i> PRD generation complete';
                }
                
                // Mark streaming as complete but keep the content visible
                window.prdStreamingState.isStreaming = false;
                
                // Update status text to show generation is complete
                if (streamingStatus) {
                    streamingStatus.innerHTML = '<i class="fas fa-check-circle" style="color: #10b981;"></i> PRD generation complete';
                }
                
                // Refresh PRD list to include the new PRD
                const prdSelector = document.getElementById('prd-selector');
                    if (projectId) {
                    fetch(`/projects/${projectId}/api/prd/?list=1`)
                        .then(response => response.json())
                        .then(listData => {
                            const prds = listData.prds || [];
                            if (prdSelector) {
                                const selectorWrapper = document.querySelector('.prd-selector-wrapper');
                                const selectorText = document.getElementById('prd-selector-text');
                                const selectorDropdown = document.getElementById('prd-selector-dropdown');
                                
                                if (prds.length > 1) {
                                    // Show custom selector if there are multiple PRDs
                                    if (selectorWrapper) selectorWrapper.style.display = 'block';
                                    
                                    // Update hidden select options
                                    prdSelector.innerHTML = prds.map(prd => 
                                        `<option value="${prd.name}" ${prd.name === prdName ? 'selected' : ''}>${prd.name}</option>`
                                    ).join('');
                                    
                                    // Build custom dropdown options
                                    if (selectorDropdown) {
                                        selectorDropdown.innerHTML = prds.map(prd => 
                                            `<div class="prd-dropdown-option ${prd.name === prdName ? 'selected' : ''}" data-value="${prd.name}">
                                                <span class="prd-name">${prd.name}</span>
                                            </div>`
                                        ).join('');
                                    }
                                    
                                    // Update displayed text
                                    if (selectorText) selectorText.textContent = prdName;
                                    
                                    console.log(`[ArtifactsLoader] Updated PRD selector with ${prds.length} PRDs after completion`);
                                } else {
                                    // Hide selector if only one PRD
                                    if (selectorWrapper) selectorWrapper.style.display = 'none';
                                }
                            }
                        })
                        .catch(error => {
                            console.error('[ArtifactsLoader] Error refreshing PRD list:', error);
                        });
                }
                
                // Add action buttons after completion
                const prdActionsContainer = document.querySelector('.prd-actions-container');
                if (prdActionsContainer && projectId) {
                    // Clear any existing content and add the action buttons
                    prdActionsContainer.innerHTML = `
                        <div class="prd-actions" style="display: flex; gap: 4px;">
                            <button class="artifact-edit-btn" id="prd-edit-btn" data-project-id="${projectId}" title="Edit" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.7'">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="artifact-delete-btn" id="prd-delete-action-btn" data-project-id="${projectId}" data-prd-name="${prdName}" title="Delete PRD" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'; this.style.color='#ef4444'" onmouseout="this.style.opacity='0.7'; this.style.color='#fff'">
                                <i class="fas fa-trash"></i>
                            </button>
                            <button class="artifact-download-btn" id="prd-download-btn" data-project-id="${projectId}" title="Download PDF" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.7'">
                                <i class="fas fa-download"></i>
                            </button>
                            <button class="artifact-copy-btn" id="prd-copy-btn" data-project-id="${projectId}" title="Copy" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.7'">
                                <i class="fas fa-copy"></i>
                            </button>
                        </div>
                    `;
                    
                    // Add event listeners for buttons
                    const editBtn = document.getElementById('prd-edit-btn');
                    if (editBtn) {
                        editBtn.addEventListener('click', () => {
                            if (window.ArtifactsEditor && window.ArtifactsEditor.enablePRDEdit) {
                                window.ArtifactsEditor.enablePRDEdit(projectId, window.prdStreamingState.fullContent);
                            }
                        });
                    }
                    
                    const downloadBtn = document.getElementById('prd-download-btn');
                    if (downloadBtn) {
                        downloadBtn.addEventListener('click', () => {
                            this.downloadPRDAsPDF(projectId, 'Product Requirement Document', window.prdStreamingState.fullContent);
                        });
                    }
                    
                    const copyBtn = document.getElementById('prd-copy-btn');
                    if (copyBtn) {
                        copyBtn.addEventListener('click', () => {
                            this.copyToClipboard(window.prdStreamingState.fullContent, 'PRD content');
                        });
                    }
                }
            }
        },
        
        /**
         * Stream implementation content chunk by chunk
         * @param {string} contentChunk - The content chunk to add
         * @param {boolean} isComplete - Whether streaming is complete
         * @param {number} projectId - The project ID
         */
        streamImplementationContent: function(contentChunk, isComplete, projectId) {
            console.log(`[ArtifactsLoader] streamImplementationContent called with chunk length: ${contentChunk ? contentChunk.length : 0}, isComplete: ${isComplete}`);
            console.log(`[ArtifactsLoader] Content chunk preview: ${contentChunk ? contentChunk.substring(0, 100) : 'null/undefined'}...`);
            console.log(`[ArtifactsLoader] Project ID: ${projectId}`);
            
            // CONSOLE STREAMING OUTPUT IN ARTIFACTS LOADER
            console.log('\n' + '='.repeat(80));
            console.log('🟢 IMPLEMENTATION STREAM IN ARTIFACTS LOADER');
            console.log(`📅 Time: ${new Date().toISOString()}`);
            console.log(`📏 Length: ${contentChunk ? contentChunk.length : 0} chars`);
            console.log(`✅ Complete: ${isComplete}`);
            if (contentChunk) {
                console.log(`📝 Content: ${contentChunk.substring(0, 200)}${contentChunk.length > 200 ? '...' : ''}`);
            }
            console.log('='.repeat(80) + '\n');
            
            // Initialize Implementation streaming state if not exists
            if (!window.implementationStreamingState) {
                window.implementationStreamingState = {
                    fullContent: '',
                    isStreaming: false,
                    projectId: projectId
                };
            }
            
            // Ensure Implementation tab is active FIRST before getting elements
            const implementationTabButton = document.querySelector('.tab-button[data-tab="implementation"]');
            const implementationTabPane = document.getElementById('implementation');
            if (implementationTabButton && !implementationTabButton.classList.contains('active')) {
                console.log('[ArtifactsLoader] Activating Implementation tab for streaming');
                // Remove active class from all tabs and panes
                document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
                document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
                // Activate Implementation tab
                implementationTabButton.classList.add('active');
                if (implementationTabPane) implementationTabPane.classList.add('active');
            }
            
            // Get the elements from the template AFTER ensuring tab is active
            const emptyState = document.getElementById('implementation-empty-state');
            const implementationContainer = document.getElementById('implementation-container');
            const streamingStatus = document.getElementById('implementation-streaming-status');
            const streamingContent = document.getElementById('implementation-streaming-content');
            
            console.log('[ArtifactsLoader] Element check:', {
                emptyState: !!emptyState,
                implementationContainer: !!implementationContainer,
                streamingStatus: !!streamingStatus,
                streamingContent: !!streamingContent
            });
            
            if (!implementationContainer || !streamingContent) {
                console.log('[ArtifactsLoader] Implementation container not found, creating structure');
                
                // Try to create the HTML structure if elements are missing
                const implementationTab = document.getElementById('implementation');
                if (implementationTab) {
                    console.log('[ArtifactsLoader] Creating Implementation HTML structure');
                    implementationTab.innerHTML = `
                        <!-- Empty state (shown by default) -->
                        <div class="empty-state" id="implementation-empty-state" style="display: none;">
                            <div class="empty-state-icon">
                                <i class="fas fa-code"></i>
                            </div>
                            <div class="empty-state-text">
                                No implementation plan available yet.
                            </div>
                        </div>
                        
                        <!-- Implementation Container (hidden by default, shown during streaming) -->
                        <div class="implementation-container" id="implementation-container" style="display: block;">
                            <div class="implementation-header">
                                <h2>Implementation Plan</h2>
                                <div class="implementation-meta" style="display: flex; justify-content: space-between; align-items: center;">
                                    <span class="streaming-status" id="implementation-streaming-status" style="color: #8b5cf6;">
                                        <i class="fas fa-circle-notch fa-spin"></i> Generating implementation plan...
                                    </span>
                                </div>
                            </div>
                            <div class="implementation-streaming-container implementation-content markdown-content" id="implementation-streaming-content" style="color: #e2e8f0; padding: 20px;">
                                <!-- Content will be streamed here -->
                            </div>
                        </div>
                    `;
                    
                    // Re-get the elements after creation
                    const newImplementationContainer = document.getElementById('implementation-container');
                    const newStreamingContent = document.getElementById('implementation-streaming-content');
                    if (newImplementationContainer && newStreamingContent) {
                        console.log('[ArtifactsLoader] HTML structure created successfully');
                        // Continue with the created elements
                        return this.streamImplementationContent(contentChunk, isComplete, projectId);
                    }
                }
                
                return;
            }
            
            // Start streaming if not already started
            if (!window.implementationStreamingState.isStreaming) {
                window.implementationStreamingState.isStreaming = true;
                window.implementationStreamingState.fullContent = '';
                window.implementationStreamingState.projectId = projectId;
                
                // Ensure empty state is hidden and container is visible
                if (emptyState) {
                    emptyState.style.display = 'none';
                    console.log('[ArtifactsLoader] Empty state hidden');
                }
                if (implementationContainer) {
                    implementationContainer.style.display = 'block';
                    console.log('[ArtifactsLoader] Implementation container shown');
                }
                
                // Reset streaming status
                if (streamingStatus) {
                    streamingStatus.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Generating implementation plan...';
                    streamingStatus.style.color = '#8b5cf6';
                }
                
                // Clear content for new streaming
                if (streamingContent) {
                    streamingContent.innerHTML = '';
                    console.log('[ArtifactsLoader] Cleared existing content for new stream');
                }
                
                // Open artifacts panel if not already open
                if (window.ArtifactsPanel && !window.ArtifactsPanel.isOpen()) {
                    window.ArtifactsPanel.open();
                    console.log('[ArtifactsLoader] Opened artifacts panel for implementation streaming');
                }
            }
            
            // Append content chunk
            if (contentChunk && streamingContent) {
                // Ensure visibility is maintained during streaming
                if (emptyState && emptyState.style.display !== 'none') {
                    emptyState.style.display = 'none';
                    console.log('[ArtifactsLoader] Empty state was visible during streaming, hiding it');
                }
                if (implementationContainer && implementationContainer.style.display !== 'block') {
                    implementationContainer.style.display = 'block';
                    console.log('[ArtifactsLoader] Implementation container was hidden during streaming, showing it');
                }
                
                window.implementationStreamingState.fullContent += contentChunk;
                
                console.log('[ArtifactsLoader] Before rendering:');
                console.log('  - streamingContent element exists:', !!streamingContent);
                console.log('  - streamingContent id:', streamingContent.id);
                console.log('  - Full content length:', window.implementationStreamingState.fullContent.length);
                console.log('  - marked available:', typeof marked !== 'undefined');
                
                // Render markdown content if marked is available
                if (typeof marked !== 'undefined') {
                    const renderedHTML = marked.parse(window.implementationStreamingState.fullContent);
                    streamingContent.innerHTML = renderedHTML;
                    console.log('  - Rendered with marked, HTML length:', renderedHTML.length);
                } else {
                    // Fallback to plain text with basic formatting
                    const formattedContent = window.implementationStreamingState.fullContent
                        .replace(/\n/g, '<br>')
                        .replace(/\t/g, '&nbsp;&nbsp;&nbsp;&nbsp;');
                    streamingContent.innerHTML = formattedContent;
                    console.log('  - Rendered with fallback formatting, HTML length:', formattedContent.length);
                }
                
                console.log('[ArtifactsLoader] After rendering:');
                console.log('  - innerHTML length:', streamingContent.innerHTML.length);
                console.log('  - Parent visible:', streamingContent.parentElement && window.getComputedStyle(streamingContent.parentElement).display !== 'none');
                console.log('  - Element visible:', window.getComputedStyle(streamingContent).display !== 'none');
                
                console.log(`[ArtifactsLoader] Appended chunk, total content length: ${window.implementationStreamingState.fullContent.length}`);
                
                // Auto-scroll to show new content
                if (implementationContainer) {
                    implementationContainer.scrollTop = implementationContainer.scrollHeight;
                }
            } else if (!contentChunk && !isComplete) {
                console.warn('[ArtifactsLoader] Empty content chunk received (not complete)');
            }
            
            // If streaming is complete, update the status
            if (isComplete) {
                if (streamingStatus) {
                    streamingStatus.innerHTML = '<i class="fas fa-check-circle" style="color: #10b981;"></i> Implementation plan generation complete';
                }
                
                // Mark streaming as complete but keep the content visible
                window.implementationStreamingState.isStreaming = false;
                
                // Add action buttons after completion
                const implementationMeta = document.querySelector('.implementation-meta');
                if (implementationMeta && projectId) {
                    // Check if actions already exist
                    let implementationActions = implementationMeta.querySelector('.implementation-actions');
                    if (!implementationActions) {
                        implementationActions = document.createElement('div');
                        implementationActions.className = 'implementation-actions';
                        implementationActions.style.cssText = 'display: flex; gap: 4px;';
                        implementationActions.innerHTML = `
                            <button class="artifact-edit-btn" id="implementation-edit-btn" data-project-id="${projectId}" title="Edit" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.7'">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="artifact-download-btn" id="implementation-download-btn" data-project-id="${projectId}" title="Download PDF" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.7'">
                                <i class="fas fa-download"></i>
                            </button>
                            <button class="artifact-copy-btn" id="implementation-copy-btn" data-project-id="${projectId}" title="Copy" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.7'">
                                <i class="fas fa-copy"></i>
                            </button>
                            <button class="artifact-delete-btn" id="implementation-delete-btn" data-project-id="${projectId}" title="Delete Implementation" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'; this.style.color='#ef4444'" onmouseout="this.style.opacity='0.7'; this.style.color='#fff'">
                                <i class="fas fa-trash"></i>
                            </button>
                        `;
                        implementationMeta.appendChild(implementationActions);
                    }
                    
                    // Add event listeners for buttons
                    const editBtn = document.getElementById('implementation-edit-btn');
                    if (editBtn) {
                        editBtn.addEventListener('click', () => {
                            if (window.ArtifactsEditor && window.ArtifactsEditor.enableImplementationEdit) {
                                window.ArtifactsEditor.enableImplementationEdit(projectId, window.implementationStreamingState.fullContent);
                            }
                        });
                    }
                    
                    const downloadBtn = document.getElementById('implementation-download-btn');
                    if (downloadBtn) {
                        downloadBtn.addEventListener('click', () => {
                            this.downloadImplementationAsPDF(projectId);
                        });
                    }
                    
                    const copyBtn = document.getElementById('implementation-copy-btn');
                    if (copyBtn) {
                        copyBtn.addEventListener('click', () => {
                            this.copyToClipboard(window.implementationStreamingState.fullContent, 'Implementation content');
                        });
                    }
                    
                    const deleteBtn = document.getElementById('implementation-delete-btn');
                    if (deleteBtn) {
                        deleteBtn.addEventListener('click', function() {
                            if (confirm('Are you sure you want to delete the implementation plan?')) {
                                // Delete the implementation
                                fetch(`/projects/${projectId}/api/implementation/`, {
                                    method: 'DELETE',
                                    headers: {
                                        'X-CSRFToken': getCsrfToken()
                                    }
                                })
                                .then(response => response.json())
                                .then(deleteData => {
                                    if (deleteData.success) {
                                        window.showToast('Implementation plan deleted successfully', 'success');
                                        // Clear the implementation content
                                        const implementationContainer = document.getElementById('implementation-container');
                                        const emptyState = document.getElementById('implementation-empty-state');
                                        if (implementationContainer) implementationContainer.style.display = 'none';
                                        if (emptyState) emptyState.style.display = 'block';
                                        // Clear the streaming state
                                        window.implementationStreamingState = {
                                            fullContent: '',
                                            isStreaming: false
                                        };
                                    } else {
                                        window.showToast(`Error deleting implementation: ${deleteData.error || 'Unknown error'}`, 'error');
                                    }
                                })
                                .catch(error => {
                                    console.error('[ArtifactsLoader] Error deleting implementation:', error);
                                    window.showToast('Error deleting implementation plan', 'error');
                                });
                            }
                        });
                    }
                }
            }
        },
        
        /**
         * Load implementation from the API for the current project
         * @param {number} projectId - The ID of the current project
         */
        loadImplementation: function(projectId) {
            console.log(`[ArtifactsLoader] loadImplementation called with project ID: ${projectId}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading implementation');
                return;
            }
            
            // Get implementation tab content element
            const implementationTab = document.getElementById('implementation');
            if (!implementationTab) {
                console.warn('[ArtifactsLoader] Implementation tab element not found');
                return;
            }
            
            // Show loading state
            console.log('[ArtifactsLoader] Showing loading state for implementation');
            implementationTab.innerHTML = '<div class="loading-state"><div class="spinner"></div><div>Loading implementation...</div></div>';
            
            // Fetch implementation from API
            const url = `/projects/${projectId}/api/implementation/`;
            console.log(`[ArtifactsLoader] Fetching implementation from API: ${url}`);
            
            fetch(url)
                .then(response => {
                    console.log(`[ArtifactsLoader] Implementation API response received, status: ${response.status}`);
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('[ArtifactsLoader] Implementation API data received:', data);
                    // Process implementation data
                    const implementationContent = data.content || '';
                    
                    if (!implementationContent) {
                        // Show empty state if no implementation found
                        console.log('[ArtifactsLoader] No implementation found, showing empty state');
                        implementationTab.innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">
                                    <i class="fas fa-code"></i>
                                </div>
                                <div class="empty-state-text">
                                    No implementation plan available yet.
                                </div>
                            </div>
                        `;
                        return;
                    }
                    
                    // Render implementation content with markdown
                    implementationTab.innerHTML = `
                        <div class="implementation-container">
                            <div class="implementation-header">
                                <h2>${data.title || 'Implementation Plan'}</h2>
                                <div class="implementation-meta" style="display: flex; justify-content: space-between; align-items: center;">
                                    <span>${data.updated_at ? `Last updated: ${data.updated_at}` : ''}</span>
                                    <div class="implementation-actions" style="display: flex; gap: 4px;">
                                        <button class="artifact-edit-btn" id="implementation-edit-btn" data-project-id="${projectId}" title="Edit" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.7'">
                                            <i class="fas fa-edit"></i>
                                        </button>
                                        <button class="artifact-copy-btn" id="implementation-copy-btn" data-project-id="${projectId}" title="Copy" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.7'">
                                            <i class="fas fa-copy"></i>
                                        </button>
                                        <button class="artifact-delete-btn" id="implementation-delete-btn" data-project-id="${projectId}" title="Delete Implementation" style="padding: 4px 6px; background: transparent; border: none; color: #fff; cursor: pointer; transition: all 0.2s; opacity: 0.7;" onmouseover="this.style.opacity='1'; this.style.color='#ef4444'" onmouseout="this.style.opacity='0.7'; this.style.color='#fff'">
                                            <i class="fas fa-trash"></i>
                                        </button>
                                    </div>
                                </div>
                            </div>
                            <div class="implementation-content markdown-content">
                                ${typeof marked !== 'undefined' ? marked.parse(implementationContent) : implementationContent}
                            </div>
                        </div>
                    `;
                    
                    // Add click event listener for the edit button
                    const editBtn = document.getElementById('implementation-edit-btn');
                    if (editBtn) {
                        editBtn.addEventListener('click', function() {
                            ArtifactsEditor.enableImplementationEdit(projectId, implementationContent);
                        });
                    }
                    
                    // Add click event listener for the copy button
                    const copyBtn = document.getElementById('implementation-copy-btn');
                    if (copyBtn) {
                        copyBtn.addEventListener('click', function() {
                            ArtifactsLoader.copyToClipboard(implementationContent, 'Implementation plan');
                        });
                    }
                    
                    // Add click event listener for the delete button
                    const deleteBtn = document.getElementById('implementation-delete-btn');
                    if (deleteBtn) {
                        deleteBtn.addEventListener('click', function() {
                            if (confirm('Are you sure you want to delete the implementation plan?')) {
                                // Delete the implementation
                                fetch(`/projects/${projectId}/api/implementation/`, {
                                    method: 'DELETE',
                                    headers: {
                                        'X-CSRFToken': getCsrfToken()
                                    }
                                })
                                .then(response => response.json())
                                .then(deleteData => {
                                    if (deleteData.success) {
                                        window.showToast('Implementation plan deleted successfully', 'success');
                                        // Show empty state
                                        implementationTab.innerHTML = `
                                            <div class="empty-state" id="implementation-empty-state">
                                                <div class="empty-state-icon">
                                                    <i class="fas fa-code"></i>
                                                </div>
                                                <div class="empty-state-text">
                                                    No implementation plan available yet.
                                                </div>
                                            </div>
                                        `;
                                    } else {
                                        window.showToast(`Error deleting implementation: ${deleteData.error || 'Unknown error'}`, 'error');
                                    }
                                })
                                .catch(error => {
                                    console.error('[ArtifactsLoader] Error deleting implementation:', error);
                                    window.showToast('Error deleting implementation plan', 'error');
                                });
                            }
                        });
                    }
                })
                .catch(error => {
                    console.error('Error fetching implementation:', error);
                    implementationTab.innerHTML = `
                        <div class="error-state">
                            <div class="error-state-icon">
                                <i class="fas fa-exclamation-triangle"></i>
                            </div>
                            <div class="error-state-text">
                                Error loading implementation. Please try again.
                            </div>
                        </div>
                    `;
                });
        },
        
        /**
         * Load tickets from the API for the current project
         * @param {number} projectId - The ID of the current project
         */
        loadTickets: function(projectId) {
            console.log(`[ArtifactsLoader] loadTickets called with project ID: ${projectId}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading tickets');
                return;
            }
            
            // Get tickets tab content element
            const ticketsTab = document.getElementById('tickets');
            if (!ticketsTab) {
                console.warn('[ArtifactsLoader] Tickets tab element not found');
                return;
            }
            
            // Show loading state
            console.log('[ArtifactsLoader] Showing loading state for tickets');
            ticketsTab.innerHTML = '<div class="loading-state"><div class="spinner"></div><div>Loading tickets...</div></div>';
            
            // Fetch tickets from API - updated to new endpoint in projects app
            const url = `/projects/${projectId}/api/checklist/`;
            console.log(`[ArtifactsLoader] Fetching tickets from API: ${url}`);
            
            fetch(url)
                .then(response => {
                    console.log(`[ArtifactsLoader] Tickets API response received, status: ${response.status}`);
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('[ArtifactsLoader] Tickets API data received:', data);
                    // Process tickets data - checklist items are returned as 'checklist'
                    const tickets = data.checklist || [];
                    console.log(`[ArtifactsLoader] Found ${tickets.length} tickets`);
                    
                    if (tickets.length === 0) {
                        // Show empty state if no tickets found
                        console.log('[ArtifactsLoader] No tickets found, showing empty state');
                        ticketsTab.innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">
                                    <i class="fas fa-ticket"></i>
                                </div>
                                <div class="empty-state-text">
                                    No tickets created yet.
                                </div>
                            </div>
                        `;
                        return;
                    }
                    
                    // Extract unique priorities for filter dropdown
                    const priorities = [...new Set(tickets.map(ticket => 
                        ticket.priority || 'Medium'
                    ))].sort();
                    
                    // Create container for tickets with filter
                    ticketsTab.innerHTML = `
                        <div class="tickets-container">
                            <div class="ticket-filters">
                                <div class="filter-options">
                                    <div class="filter-group">
                                        <select id="priority-filter" class="priority-filter-dropdown">
                                            <option value="all">All Priorities</option>
                                            ${priorities.map(priority => `<option value="${priority}">${priority}</option>`).join('')}
                                        </select>
                                        <button id="clear-filters" class="clear-filters-btn" title="Clear filters">
                                            <i class="fas fa-times"></i>
                                        </button>
                                        <button id="sync-linear" class="sync-linear-btn" title="Sync with Linear">
                                            <i class="fas fa-sync"></i> Sync with Linear
                                        </button>
                                    </div>
                                </div>
                            </div>
                            <div class="tickets-content" id="tickets-content">
                                <!-- Tickets will be loaded here -->
                            </div>
                        </div>
                        
                        <!-- Right Drawer for Ticket Details -->
                        <div class="ticket-details-drawer" id="ticket-details-drawer">
                            <div class="drawer-header">
                                <h3 class="drawer-title">Ticket Details</h3>
                                <button class="close-drawer-btn" id="close-drawer-btn">
                                    <i class="fas fa-times"></i>
                                </button>
                            </div>
                            <div class="drawer-content" id="drawer-content">
                                <!-- Ticket details will be loaded here -->
                            </div>
                        </div>
                        
                        <!-- Overlay for drawer -->
                        <div class="drawer-overlay" id="drawer-overlay"></div>
                    `;
                    
                    const ticketsContent = document.getElementById('tickets-content');
                    const priorityFilter = document.getElementById('priority-filter');
                    const clearFiltersBtn = document.getElementById('clear-filters');
                    
                    // Group tickets by status for potential future use
                    const ticketsByStatus = {
                        open: [],
                        in_progress: [],
                        agent: [],
                        closed: []
                    };
                    
                    tickets.forEach(ticket => {
                        const status = ticket.status || 'open';
                        if (ticketsByStatus[status]) {
                            ticketsByStatus[status].push(ticket);
                        } else {
                            ticketsByStatus.open.push(ticket);
                        }
                    });
                    
                    // Function to render tickets based on filter
                    const renderTickets = (filterPriority = 'all') => {
                        let filteredTickets = [...tickets];
                        
                        // Apply priority filter if not 'all'
                        if (filterPriority !== 'all') {
                            filteredTickets = filteredTickets.filter(ticket => 
                                (ticket.priority || 'Medium') === filterPriority
                            );
                        }
                        
                        // Create HTML for filtered tickets
                        let ticketsHTML = `<div class="tickets-by-status">`;
                        
                        if (filteredTickets.length === 0) {
                            ticketsHTML += `
                                <div class="no-results">
                                    <div class="empty-state-icon">
                                        <i class="fas fa-filter"></i>
                                    </div>
                                    <div class="empty-state-text">
                                        No tickets match your filter criteria.
                                    </div>
                                </div>
                            `;
                        } else {
                            filteredTickets.forEach(ticket => {
                                const priorityLevel = (ticket.priority || 'Medium').toLowerCase();
                                const priorityClass = `${priorityLevel}-priority`;
                                const status = ticket.status || 'open';
                                const isHighlighted = filterPriority !== 'all' && ticket.priority === filterPriority;
                                
                                // Process description for better display
                                let displayDescription = ticket.description || '';
                                const descriptionLimit = 300; // Increased character limit
                                const isTruncated = displayDescription.length > descriptionLimit;
                                
                                if (isTruncated) {
                                    // Find the last space before the limit to avoid cutting words
                                    const lastSpaceIndex = displayDescription.lastIndexOf(' ', descriptionLimit);
                                    const truncateIndex = lastSpaceIndex > 0 ? lastSpaceIndex : descriptionLimit;
                                    displayDescription = displayDescription.substring(0, truncateIndex) + '...';
                                }
                                
                                // Replace newlines with <br> tags for proper formatting
                                displayDescription = displayDescription.replace(/\n/g, '<br>');
                                
                                ticketsHTML += `
                                    <div class="ticket-card" data-ticket-id="${ticket.id}" data-priority="${ticket.priority || 'Medium'}">
                                        <div class="card-header ${status}">
                                            <h4 class="card-title">${ticket.name}</h4>
                                        </div>
                                        <div class="card-body">
                                            <div class="card-description">${displayDescription}</div>
                                            
                                            <div class="card-meta">
                                                <div class="card-tags">
                                                    <span class="priority-tag ${priorityClass} ${isHighlighted ? 'filter-active' : ''}">
                                                        <i class="fas fa-flag"></i> ${ticket.priority || 'Medium'} Priority
                                                    </span>
                                                    <span class="status-tag status-${status}">
                                                        ${status.replace('_', ' ').charAt(0).toUpperCase() + status.replace('_', ' ').slice(1)}
                                                    </span>
                                                    ${ticket.linear_issue_id ? `
                                                    <span class="linear-sync-tag" title="Synced with Linear">
                                                        <svg viewBox="0 0 32 32" width="14" height="14" fill="currentColor">
                                                            <path d="M2.66675 2.66699H29.3334V7.46732H2.66675V2.66699Z"/>
                                                            <path d="M2.66675 9.86719H29.3334V14.6675H2.66675V9.86719Z"/>
                                                            <path d="M2.66675 17.0674H29.3334V21.8677H2.66675V17.0674Z"/>
                                                            <path d="M2.66675 24.2676H17.0668V29.0679H2.66675V24.2676Z"/>
                                                        </svg>
                                                        Synced
                                                    </span>
                                                    ` : ''}
                                                </div>
                                                <button class="view-details-btn" data-ticket-id="${ticket.id}" title="View details">
                                                    <i class="fas fa-info-circle"></i>
                                                </button>
                                                <button class="delete-ticket-btn" data-ticket-id="${ticket.id}" title="Delete ticket">
                                                    <i class="fas fa-trash"></i>
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                `;
                            });
                        }
                        
                        ticketsHTML += `</div>`;
                        ticketsContent.innerHTML = ticketsHTML;
                        
                        // Reattach event listeners after rendering
                        attachDetailViewListeners();
                    };
                    
                    // Function to attach event listeners for detail view buttons
                    const attachDetailViewListeners = () => {
                        // Add event listeners for the details buttons
                        const detailsButtons = document.querySelectorAll('.view-details-btn');
                        const detailsDrawer = document.getElementById('ticket-details-drawer');
                        const drawerOverlay = document.getElementById('drawer-overlay');
                        const closeDrawerBtn = document.getElementById('close-drawer-btn');
                        
                        detailsButtons.forEach(button => {
                            button.addEventListener('click', function(e) {
                                const ticketId = this.getAttribute('data-ticket-id');
                                const ticket = tickets.find(t => t.id == ticketId);
                                
                                if (ticket) {
                                    // Populate drawer with ticket details
                                    const drawerContent = document.getElementById('drawer-content');
                                    drawerContent.innerHTML = `
                                        <div class="drawer-section">
                                            <h4 class="section-title">Ticket Information</h4>
                                            <p class="ticket-id"><strong>ID:</strong> ${ticket.id}</p>
                                            <p class="ticket-title"><strong>Title:</strong> ${ticket.name}</p>
                                            <p class="ticket-status"><strong>Status:</strong> ${ticket.status.replace('_', ' ').charAt(0).toUpperCase() + ticket.status.replace('_', ' ').slice(1)}</p>
                                            <p class="ticket-priority"><strong>Priority:</strong> ${ticket.priority || 'Medium'}</p>
                                        </div>
                                        
                                        ${ticket.linear_issue_id ? `
                                        <div class="drawer-section">
                                            <h4 class="section-title">Linear Integration</h4>
                                            <p class="linear-info"><strong>Linear State:</strong> ${ticket.linear_state || 'Unknown'}</p>
                                            ${ticket.linear_issue_url ? `
                                            <p class="linear-link">
                                                <a href="${ticket.linear_issue_url}" target="_blank" class="linear-issue-link">
                                                    <svg viewBox="0 0 32 32" width="16" height="16" fill="currentColor">
                                                        <path d="M2.66675 2.66699H29.3334V7.46732H2.66675V2.66699Z"/>
                                                        <path d="M2.66675 9.86719H29.3334V14.6675H2.66675V9.86719Z"/>
                                                        <path d="M2.66675 17.0674H29.3334V21.8677H2.66675V17.0674Z"/>
                                                        <path d="M2.66675 24.2676H17.0668V29.0679H2.66675V24.2676Z"/>
                                                    </svg>
                                                    View in Linear
                                                </a>
                                            </p>
                                            ` : ''}
                                            ${ticket.linear_synced_at ? `<p class="linear-sync-info"><small>Last synced: ${new Date(ticket.linear_synced_at).toLocaleString()}</small></p>` : ''}
                                        </div>
                                        ` : ''}
                                        
                                        <div class="drawer-section">
                                            <h4 class="section-title">Description</h4>
                                            <div class="section-content description-content">
                                                ${ticket.description.replace(/\n/g, '<br>')}
                                            </div>
                                        </div>
                                        
                                        ${ticket.details && Object.keys(ticket.details).length > 0 ? `
                                        <div class="drawer-section">
                                            <h4 class="section-title">Technical Details</h4>
                                            <div class="section-content">
                                                <pre style="background: #1a1a1a; padding: 10px; border-radius: 4px; overflow-x: auto;">${JSON.stringify(ticket.details, null, 2)}</pre>
                                            </div>
                                        </div>
                                        ` : ''}
                                        
                                        ${ticket.acceptance_criteria && ticket.acceptance_criteria.length > 0 ? `
                                        <div class="drawer-section">
                                            <h4 class="section-title">Acceptance Criteria</h4>
                                            <div class="section-content">
                                                <ul>
                                                    ${ticket.acceptance_criteria.map(criteria => `<li>${criteria}</li>`).join('')}
                                                </ul>
                                            </div>
                                        </div>
                                        ` : ''}
                                        
                                        <div class="drawer-section">
                                            <h4 class="section-title">Metadata</h4>
                                            <div class="section-content">
                                                <p><strong>Complexity:</strong> ${ticket.complexity || 'medium'}</p>
                                                <p><strong>Role:</strong> ${ticket.role || 'user'}</p>
                                                <p><strong>Requires Worktree:</strong> ${ticket.requires_worktree ? 'Yes' : 'No'}</p>
                                            </div>
                                        </div>
                                        
                                        <div class="drawer-section" style="margin-top: 20px;">
                                            <button class="execute-ticket-btn" onclick="ArtifactsLoader.executeTicket(${ticket.id})" style="width: 100%; padding: 12px; background: #8b5cf6; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; display: flex; align-items: center; justify-content: center; gap: 8px;">
                                                <i class="fas fa-play"></i> Execute (Build Now)
                                            </button>
                                        </div>
                                    `;
                                    
                                    // Show the drawer
                                    detailsDrawer.classList.add('open');
                                    drawerOverlay.classList.add('active');
                                }
                            });
                        });
                        
                        // Add event listeners for delete buttons
                        const deleteButtons = document.querySelectorAll('.delete-ticket-btn');
                        deleteButtons.forEach(button => {
                            button.addEventListener('click', function(e) {
                                e.stopPropagation(); // Prevent any parent click handlers
                                const ticketId = this.getAttribute('data-ticket-id');
                                const ticket = tickets.find(t => t.id == ticketId);
                                
                                if (ticket && confirm(`Are you sure you want to delete the ticket "${ticket.name}"?`)) {
                                    // Call delete API
                                    fetch(`/projects/${projectId}/api/checklist/${ticketId}/delete/`, {
                                        method: 'DELETE',
                                        headers: {
                                            'X-CSRFToken': getCookie('csrftoken')
                                        }
                                    })
                                    .then(response => {
                                        if (!response.ok) {
                                            throw new Error('Failed to delete ticket');
                                        }
                                        return response.json();
                                    })
                                    .then(data => {
                                        if (data.success) {
                                            showToast('Ticket deleted successfully', 'success');
                                            // Reload tickets to reflect the deletion
                                            ArtifactsLoader.loadTickets(projectId);
                                        } else {
                                            showToast(data.error || 'Failed to delete ticket', 'error');
                                        }
                                    })
                                    .catch(error => {
                                        console.error('Error deleting ticket:', error);
                                        showToast('Error deleting ticket', 'error');
                                    });
                                }
                            });
                        });
                        
                        // Close drawer when clicking close button or overlay
                        if (closeDrawerBtn) {
                            closeDrawerBtn.addEventListener('click', function() {
                                detailsDrawer.classList.remove('open');
                                drawerOverlay.classList.remove('active');
                            });
                        }
                        
                        if (drawerOverlay) {
                            drawerOverlay.addEventListener('click', function() {
                                detailsDrawer.classList.remove('open');
                                drawerOverlay.classList.remove('active');
                            });
                        }
                    };
                    
                    // Add event listeners for filters
                    if (priorityFilter) {
                        priorityFilter.addEventListener('change', function() {
                            renderTickets(this.value);
                        });
                    }
                    
                    if (clearFiltersBtn) {
                        clearFiltersBtn.addEventListener('click', function() {
                            priorityFilter.value = 'all';
                            renderTickets('all');
                        });
                    }
                    
                    // Add Linear sync button event listener
                    const syncLinearBtn = document.getElementById('sync-linear');
                    if (syncLinearBtn) {
                        syncLinearBtn.addEventListener('click', function() {
                            // Show confirmation or instructions if not configured
                            if (!data.linear_sync_enabled) {
                                showToast('Linear sync is not enabled for this project. Please go to project settings to configure Linear integration.', 'error');
                                return;
                            }
                            
                            this.disabled = true;
                            this.innerHTML = '<i class="fas fa-sync fa-spin"></i> Syncing...';
                            
                            // Call Linear sync API
                            fetch(`/projects/${projectId}/api/linear/sync/`, {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                    'X-CSRFToken': getCookie('csrftoken')
                                },
                            })
                            .then(response => response.json())
                            .then(data => {
                                if (data.success) {
                                    // Show success message
                                    showToast(data.message || 'Tickets synced successfully!', 'success');
                                    // Reload tickets to show updated sync status
                                    ArtifactsLoader.loadTickets(projectId);
                                } else {
                                    // Check if it's a configuration error
                                    if (data.error && data.error.includes('API key not configured')) {
                                        showToast('Linear API key not configured. Please go to Integrations to add your Linear API key.', 'error');
                                    } else if (data.error && data.error.includes('team ID not set')) {
                                        showToast('Linear team ID not set. Please go to project settings to configure Linear integration.', 'error');
                                    } else {
                                        showToast(data.error || 'Failed to sync tickets', 'error');
                                    }
                                    // Re-enable button
                                    this.disabled = false;
                                    this.innerHTML = '<i class="fas fa-sync"></i> Sync with Linear';
                                }
                            })
                            .catch(error => {
                                console.error('Error syncing with Linear:', error);
                                showToast('Error syncing with Linear', 'error');
                                // Re-enable button
                                this.disabled = false;
                                this.innerHTML = '<i class="fas fa-sync"></i> Sync with Linear';
                            });
                        });
                    }
                    
                    // Helper function to show toast notifications
                    function showToast(message, type = 'info') {
                        // Create toast element if it doesn't exist
                        let toastContainer = document.getElementById('toast-container');
                        if (!toastContainer) {
                            toastContainer = document.createElement('div');
                            toastContainer.id = 'toast-container';
                            toastContainer.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 9999;';
                            document.body.appendChild(toastContainer);
                        }
                        
                        const toast = document.createElement('div');
                        toast.className = `toast toast-${type}`;
                        toast.style.cssText = 'background: #333; color: white; padding: 12px 24px; border-radius: 4px; margin-bottom: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.2); animation: slideIn 0.3s ease;';
                        
                        if (type === 'success') {
                            toast.style.background = '#4CAF50';
                        } else if (type === 'error') {
                            toast.style.background = '#f44336';
                        }
                        
                        toast.textContent = message;
                        toastContainer.appendChild(toast);
                        
                        // Remove toast after 5 seconds
                        setTimeout(() => {
                            toast.style.animation = 'slideOut 0.3s ease';
                            setTimeout(() => toast.remove(), 300);
                        }, 5000);
                    }
                    
                    // Helper function to get CSRF token
                    function getCookie(name) {
                        let cookieValue = null;
                        if (document.cookie && document.cookie !== '') {
                            const cookies = document.cookie.split(';');
                            for (let i = 0; i < cookies.length; i++) {
                                const cookie = cookies[i].trim();
                                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                                    break;
                                }
                            }
                        }
                        return cookieValue;
                    }
                    
                    // Initial render with all tickets
                    renderTickets();
                })
                .catch(error => {
                    console.error('Error fetching tickets:', error);
                    ticketsTab.innerHTML = `
                        <div class="error-state">
                            <div class="error-state-icon">
                                <i class="fas fa-exclamation-triangle"></i>
                            </div>
                            <div class="error-state-text">
                                Error loading tickets. Please try again.
                            </div>
                        </div>
                    `;
                });
        },
        
        /**
         * Load design schema from the API for the current project
         * @param {number} projectId - The ID of the current project
         */
        loadDesignSchema: function(projectId) {
            console.log(`[ArtifactsLoader] loadDesignSchema called with project ID: ${projectId}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading design schema');
                return;
            }
            
            // Get design schema tab content element
            const designTab = document.getElementById('design');
            if (!designTab) {
                console.warn('[ArtifactsLoader] Design tab element not found');
                return;
            }
            
            // Show loading state
            console.log('[ArtifactsLoader] Showing loading state for design schema');
            designTab.innerHTML = '<div class="loading-state"><div class="spinner"></div><div>Loading design schema...</div></div>';
            
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
                    const designSchemaContent = data.content || '';
                    
                    if (!designSchemaContent) {
                        // Show empty state if no design schema found
                        console.log('[ArtifactsLoader] No design schema found, showing empty state');
                        designTab.innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">
                                    <i class="fas fa-file-alt"></i>
                                </div>
                                <div class="empty-state-text">
                                    No design schema available yet.
                                </div>
                            </div>
                        `;
                        return;
                    }
                    
                    // Render design schema content with markdown
                    designTab.innerHTML = `
                        <div class="design-schema-container">
                            <div class="design-schema-header">
                                <h2>${data.title || 'Design Schema'}</h2>
                                <div class="design-schema-meta">
                                    ${data.updated_at ? `<span>Last updated: ${data.updated_at}</span>` : ''}
                                </div>
                            </div>
                            <div class="design-schema-content markdown-content">
                                ${typeof marked !== 'undefined' ? marked.parse(designSchemaContent) : designSchemaContent}
                            </div>
                        </div>
                    `;
                })
                .catch(error => {
                    console.error('Error fetching design schema:', error);
                    designTab.innerHTML = `
                        <div class="error-state">
                            <div class="error-state-icon">
                                <i class="fas fa-exclamation-triangle"></i>
                            </div>
                            <div class="error-state-text">
                                Error loading design schema. Please try again.
                            </div>
                        </div>
                    `;
                });
        },
        
        /**
         * Load codebase explorer from the development module for the current project
         * @param {number} projectId - The ID of the current project
         */
        loadCodebase: function(projectId) {
            console.log(`[ArtifactsLoader] loadCodebase called with project ID: ${projectId}`);
            console.log(`[ArtifactsLoader] Project ID type: ${typeof projectId}`);
            console.log(`[ArtifactsLoader] Project ID truthy: ${!!projectId}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading codebase');
                return;
            }
            
            // Get codebase tab content element
            const codebaseTab = document.getElementById('codebase');
            if (!codebaseTab) {
                console.warn('[ArtifactsLoader] Codebase tab element not found');
                return;
            }
            
            // Get codebase UI elements
            const codebaseLoading = document.getElementById('codebase-loading');
            const codebaseEmpty = document.getElementById('codebase-empty');
            const codebaseFrameContainer = document.getElementById('codebase-frame-container');
            const codebaseIframe = document.getElementById('codebase-iframe');
            
            console.log('[ArtifactsLoader] UI Elements found:', {
                codebaseLoading: !!codebaseLoading,
                codebaseEmpty: !!codebaseEmpty,
                codebaseFrameContainer: !!codebaseFrameContainer,
                codebaseIframe: !!codebaseIframe
            });
            
            if (!codebaseLoading || !codebaseEmpty || !codebaseFrameContainer || !codebaseIframe) {
                console.warn('[ArtifactsLoader] Codebase UI elements not found');
                return;
            }
            
            // Show loading state
            console.log('[ArtifactsLoader] Showing loading state for codebase');
            codebaseLoading.style.display = 'block';
            codebaseEmpty.style.display = 'none';
            codebaseFrameContainer.style.display = 'none';
            
            // Get conversation ID using the helper function
            const conversationId = getCurrentConversationId();
            console.log(`[ArtifactsLoader] Conversation ID: ${conversationId}`);
            
            // Build the editor URL with appropriate parameters
            let editorUrl = `/development/editor/?project_id=${projectId}`;
            
            // Add conversation ID if available
            if (conversationId) {
                editorUrl += `&conversation_id=${conversationId}`;
                console.log(`[ArtifactsLoader] Including conversation ID: ${conversationId}`);
            }
            
            console.log(`[ArtifactsLoader] Loading codebase explorer from URL: ${editorUrl}`);
            console.log(`[ArtifactsLoader] About to set iframe.src - this should trigger network request`);
            
            // Set up iframe event handlers
            codebaseIframe.onload = function() {
                // Hide loading and show iframe when loaded
                codebaseLoading.style.display = 'none';
                codebaseFrameContainer.style.display = 'block';
                console.log('[ArtifactsLoader] Codebase iframe loaded successfully');
                console.log('[ArtifactsLoader] Iframe content window:', codebaseIframe.contentWindow);
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
                console.error('[ArtifactsLoader] Error loading codebase iframe');
            };
            
            // Set the iframe source to load the editor
            console.log('[ArtifactsLoader] Setting iframe src now...');
            codebaseIframe.src = editorUrl;
            console.log('[ArtifactsLoader] Iframe src set to:', codebaseIframe.src);
        },
        
        /**
         * Render implementation content properly handling XML/HTML-like content
         * @param {string} content - The implementation content to render
         * @returns {string} The rendered HTML content
         */
        renderImplementationContent: function(content) {
            if (!content) return '';
            
            // Check if content looks like XML/HTML (contains tags)
            if (content.includes('<') && content.includes('>')) {
                // If it looks like structured data, wrap it in a code block
                const escapedContent = content
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#39;');
                
                return `<pre><code>${escapedContent}</code></pre>`;
            }
            
            // Otherwise, render as markdown
            if (typeof marked !== 'undefined') {
                return marked.parse(content);
            }
            
            // Fallback to plain text with basic escaping
            return content.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        },
        
        /**
         * Load checklist items from the API for the current project
         * @param {number} projectId - The ID of the current project
         */
        loadChecklist: function(projectId) {
            console.log(`[ArtifactsLoader] loadChecklist called with project ID: ${projectId}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading checklist');
                return;
            }
            
            // Get checklist tab content element
            const checklistTab = document.getElementById('checklist');
            if (!checklistTab) {
                console.warn('[ArtifactsLoader] Checklist tab element not found');
                return;
            }
            
            // Show loading state
            console.log('[ArtifactsLoader] Showing loading state for checklist');
            checklistTab.innerHTML = '<div class="loading-state"><div class="spinner"></div><div>Loading checklist...</div></div>';
            
            // Fetch checklist from API
            const checklistUrl = `/projects/${projectId}/api/checklist/`;
            console.log(`[ArtifactsLoader] Fetching checklist from API: ${checklistUrl}`);
            
            fetch(checklistUrl)
                .then(response => {
                    console.log(`[ArtifactsLoader] Checklist API response received, status: ${response.status}`);
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('[ArtifactsLoader] Checklist API data received:', data);
                    // Process checklist data
                    const checklist = data.checklist || [];
                    console.log(`[ArtifactsLoader] Found ${checklist.length} checklist items`);
                    
                    if (checklist.length === 0) {
                        // Show empty state if no checklist items found
                        console.log('[ArtifactsLoader] No checklist items found, showing empty state');
                        checklistTab.innerHTML = `
                            <div class="checklist-empty-state">
                                <div class="empty-state-icon">
                                    <i class="fas fa-check-square"></i>
                                </div>
                                <div class="empty-state-text">
                                    No checklist items created yet.
                                </div>
                            </div>
                        `;
                        return;
                    }

                    // Extract unique statuses and roles for filter dropdowns
                    const statuses = [...new Set(checklist.map(item => item.status || 'open'))].sort();
                    const roles = [...new Set(checklist.map(item => item.role || 'user'))].sort();

                    // Create container with filters
                    let checklistHTML = `
                        <div class="checklist-wrapper">
                            <div class="checklist-header" style="display: flex; align-items: center; justify-content: flex-end; padding: 12px 16px;">
                                <div class="checklist-filters" style="margin-right: 12px;">
                                    <div class="filter-options">
                                        <div class="filter-group">
                                            <select id="status-filter" class="checklist-filter-dropdown">
                                                <option value="all">All Statuses</option>
                                                ${statuses.map(status => `<option value="${status}">${status.replace('_', ' ').charAt(0).toUpperCase() + status.replace('_', ' ').slice(1)}</option>`).join('')}
                                            </select>
                                            <select id="role-filter" class="checklist-filter-dropdown">
                                                <option value="all">All Assigned</option>
                                                ${roles.map(role => `<option value="${role}">${role.charAt(0).toUpperCase() + role.slice(1)}</option>`).join('')}
                                            </select>
                                            <button id="clear-checklist-filters" class="clear-filters-btn" title="Clear filters">
                                                <i class="fas fa-times"></i>
                                            </button>
                                        </div>
                                    </div>
                                </div>
                                <div class="dropdown" style="position: relative;">
                                    <button class="dropdown-toggle" id="checklist-actions-dropdown" style="background: rgba(40, 40, 40, 0.8); color: #888; border: 1px solid rgba(255, 255, 255, 0.08); width: 24px; height: 24px; border-radius: 50%; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.15s ease; padding: 0;"
                                            onmouseover="this.style.background='rgba(60, 60, 60, 0.9)'; this.style.color='#8b5cf6'; this.style.transform='scale(1.05)';" 
                                            onmouseout="this.style.background='rgba(40, 40, 40, 0.8)'; this.style.color='#888'; this.style.transform='scale(1)';">
                                        <i class="fas fa-ellipsis-v" style="font-size: 9px;"></i>
                                    </button>
                                    <div class="dropdown-menu" id="checklist-actions-menu" style="display: none; position: absolute; top: 100%; right: 0; background: #1e1e2e; border: 1px solid #313244; border-radius: 8px; min-width: 180px; box-shadow: 0 8px 16px rgba(0, 0, 0, 0.3); z-index: 1000; margin-top: 8px; overflow: hidden;">
                                        <button id="sync-checklist-linear" class="dropdown-item" style="display: block; width: 100%; text-align: left; padding: 12px 16px; background: none; border: none; color: #cdd6f4; cursor: pointer; transition: all 0.2s; font-size: 14px;" 
                                                onmouseover="this.style.background='#313244'; this.style.color='#b4befe';" onmouseout="this.style.background='none'; this.style.color='#cdd6f4';">
                                            <i class="fas fa-sync" style="margin-right: 10px; width: 14px; text-align: center; color: #8b5cf6;"></i> Sync with Linear
                                        </button>
                                        <div style="height: 1px; background: #313244;"></div>
                                        <button id="delete-all-checklist" class="dropdown-item" style="display: block; width: 100%; text-align: left; padding: 12px 16px; background: none; border: none; color: #f38ba8; cursor: pointer; transition: all 0.2s; font-size: 14px;"
                                                onmouseover="this.style.background='#313244'; this.style.color='#eba0ac';" onmouseout="this.style.background='none'; this.style.color='#f38ba8';">
                                            <i class="fas fa-trash-alt" style="margin-right: 10px; width: 14px; text-align: center;"></i> Delete All
                                        </button>
                                    </div>
                                </div>
                            </div>
                            <div class="checklist-container" id="checklist-content">
                                <!-- Checklist items will be loaded here -->
                            </div>
                        </div>
                    `;

                    // Add drawer HTML for checklist details
                    checklistHTML += `
                        <!-- Checklist Details Drawer -->
                        <div class="checklist-details-drawer" id="checklist-details-drawer">
                            <div class="drawer-header">
                                <h3 class="drawer-title">Checklist Item Details</h3>
                                <button class="close-drawer-btn" id="close-checklist-drawer-btn">
                                    <i class="fas fa-times"></i>
                                </button>
                            </div>
                            <div class="drawer-content" id="checklist-drawer-content">
                                <!-- Checklist details will be loaded here -->
                            </div>
                        </div>
                        
                        <!-- Overlay for drawer -->
                        <div class="drawer-overlay" id="checklist-drawer-overlay"></div>
                    `;
                    
                    checklistTab.innerHTML = checklistHTML;

                    // Get filter elements and content container
                    const checklistContent = document.getElementById('checklist-content');
                    const statusFilter = document.getElementById('status-filter');
                    const roleFilter = document.getElementById('role-filter');
                    const clearFiltersBtn = document.getElementById('clear-checklist-filters');

                    // Function to render checklist items based on filters
                    const renderChecklist = (filterStatus = 'all', filterRole = 'all') => {
                        let filteredChecklist = [...checklist];
                        
                        // Apply status filter
                        if (filterStatus !== 'all') {
                            filteredChecklist = filteredChecklist.filter(item => 
                                (item.status || 'open') === filterStatus
                            );
                        }
                        
                        // Apply role filter
                        if (filterRole !== 'all') {
                            filteredChecklist = filteredChecklist.filter(item => 
                                (item.role || 'user') === filterRole
                            );
                        }

                        if (filteredChecklist.length === 0) {
                            checklistContent.innerHTML = `
                                <div class="no-results">
                                    <div class="empty-state-icon">
                                        <i class="fas fa-filter"></i>
                                    </div>
                                    <div class="empty-state-text">
                                        No checklist items match your filter criteria.
                                    </div>
                                </div>
                            `;
                            return;
                        }

                        // Build checklist HTML with filtered items
                        let itemsHTML = '';
                        
                        filteredChecklist.forEach(item => {
                            const statusClass = item.status ? item.status.toLowerCase().replace(' ', '-') : 'open';
                            const priorityClass = item.priority ? item.priority.toLowerCase() : 'medium';
                            const roleClass = item.role ? item.role.toLowerCase() : 'user';
                            
                            // Get status icon
                            let statusIcon = 'fas fa-circle';
                            switch(statusClass) {
                                case 'open':
                                    statusIcon = 'fas fa-circle';
                                    break;
                                case 'in-progress':
                                    statusIcon = 'fas fa-play-circle';
                                    break;
                                case 'agent':
                                    statusIcon = 'fas fa-robot';
                                    break;
                                case 'closed':
                                    statusIcon = 'fas fa-check-circle';
                                    break;
                                case 'done':
                                    statusIcon = 'fas fa-check-circle';
                                    break;
                                case 'failed':
                                    statusIcon = 'fas fa-times-circle';
                                    break;
                                case 'blocked':
                                    statusIcon = 'fas fa-ban';
                                    break;
                            }
                            
                            // Check if this item matches active filters for highlighting
                            const isStatusHighlighted = filterStatus !== 'all' && (item.status || 'open') === filterStatus;
                            const isRoleHighlighted = filterRole !== 'all' && (item.role || 'user') === filterRole;
                            
                            // Extract dependencies if available
                            let dependenciesHtml = '';
                            if (item.dependencies && item.dependencies.length > 0) {
                                dependenciesHtml = `
                                    <div class="card-dependencies">
                                        <span class="dependencies-label"><i class="fas fa-link"></i> Dependencies:</span>
                                        ${item.dependencies.map(dep => `<span class="dependency-tag">${dep}</span>`).join('')}
                                    </div>
                                `;
                            }
                            
                            // Extract details if available
                            let detailsPreview = '';
                            if (item.details && Object.keys(item.details).length > 0) {
                                // Show a preview of details
                                const detailKeys = Object.keys(item.details);
                                const previewKeys = detailKeys.slice(0, 2);
                                detailsPreview = `
                                    <div class="card-details-preview">
                                        ${previewKeys.map(key => {
                                            const value = item.details[key];
                                            if (Array.isArray(value) && value.length > 0) {
                                                return `<span class="detail-item"><i class="fas fa-info-circle"></i> ${key}: ${value.length} items</span>`;
                                            } else if (typeof value === 'object' && value !== null) {
                                                return `<span class="detail-item"><i class="fas fa-info-circle"></i> ${key}: ${Object.keys(value).length} properties</span>`;
                                            } else if (value) {
                                                return `<span class="detail-item"><i class="fas fa-info-circle"></i> ${key}</span>`;
                                            }
                                            return '';
                                        }).filter(Boolean).join('')}
                                        ${detailKeys.length > 2 ? `<span class="more-details">+${detailKeys.length - 2} more...</span>` : ''}
                                    </div>
                                `;
                            }
                            
                            itemsHTML += `
                                <div class="checklist-card ${statusClass}" data-id="${item.id}">
                                    <div class="card-header">
                                        <div class="card-status">
                                            <i class="${statusIcon} status-icon"></i>
                                            <h3 class="card-title">${item.name}</h3>
                                        </div>
                                        <div class="card-badges">
                                            <span class="priority-badge ${priorityClass} ${isStatusHighlighted ? 'filter-active' : ''}">${item.priority || 'Medium'}</span>
                                            <span class="role-badge ${roleClass} ${isRoleHighlighted ? 'filter-active' : ''}">${item.role || 'User'}</span>
                                        </div>
                                    </div>
                                    
                                    <div class="card-body">
                                        <div class="card-description">
                                            ${item.description || 'No description provided.'}
                                        </div>
                                        ${dependenciesHtml}
                                        ${detailsPreview}
                                    </div>
                                    
                                    <div class="card-footer">
                                        <div class="card-meta">
                                            <small class="created-date">
                                                <i class="fas fa-calendar-plus"></i>
                                                Created: ${new Date(item.created_at).toLocaleDateString()}
                                            </small>
                                            <small class="updated-date">
                                                <i class="fas fa-calendar-check"></i>
                                                Updated: ${new Date(item.updated_at).toLocaleDateString()}
                                            </small>
                                        </div>
                                        <div class="card-actions">
                                            <button class="action-btn view-details-btn" data-item-id="${item.id}" title="View Details">
                                                <i class="fas fa-eye"></i>
                                            </button>
                                            <button class="action-btn edit-btn" onclick="editChecklistItem(${item.id})" title="Edit">
                                                <i class="fas fa-edit"></i>
                                            </button>
                                            <button class="action-btn toggle-btn" onclick="toggleChecklistStatus(${item.id}, '${item.status}')" title="Toggle Status">
                                                <i class="fas fa-sync-alt"></i>
                                            </button>
                                            <button class="action-btn delete-checklist-btn" data-item-id="${item.id}" title="Delete">
                                                <i class="fas fa-trash"></i>
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            `;
                        });
                        
                        checklistContent.innerHTML = itemsHTML;
                        
                        // Reattach event listeners after rendering
                        attachChecklistDetailListeners();
                    };

                    // Function to attach event listeners for checklist detail view
                    const attachChecklistDetailListeners = () => {
                        // Add click handlers for opening drawer
                        console.log('[ArtifactsLoader] Adding click handlers to checklist items for drawer');
                        const checklistCards = checklistContent.querySelectorAll('.checklist-card');
                        const viewDetailsButtons = checklistContent.querySelectorAll('.view-details-btn');
                        const checklistDrawer = document.getElementById('checklist-details-drawer');
                        const checklistDrawerOverlay = document.getElementById('checklist-drawer-overlay');
                        const closeChecklistDrawerBtn = document.getElementById('close-checklist-drawer-btn');
                        const checklistDrawerContent = document.getElementById('checklist-drawer-content');
                        
                        console.log(`[ArtifactsLoader] Found ${checklistCards.length} checklist cards`);
                        
                        checklistCards.forEach((card, index) => {
                            console.log(`[ArtifactsLoader] Adding click handler to card ${index}`);
                            
                            card.addEventListener('click', function(e) {
                                console.log('[ArtifactsLoader] Card clicked', e.target);
                                
                                // Don't open drawer if clicking on action buttons
                                if (e.target.closest('.action-btn')) {
                                    console.log('[ArtifactsLoader] Action button clicked, not opening drawer');
                                    return;
                                }
                                
                                // Get the item data
                                const itemId = card.getAttribute('data-id');
                                const item = checklist.find(i => i.id == itemId);
                                
                                if (item) {
                                    console.log('[ArtifactsLoader] Opening drawer for item:', item);
                                    
                                    // Get status display text
                                    const statusText = item.status ? item.status.replace('_', ' ').charAt(0).toUpperCase() + item.status.replace('_', ' ').slice(1) : 'Open';
                                    
                                    // Build dependencies section
                                    let dependenciesSection = '';
                                    if (item.dependencies && item.dependencies.length > 0) {
                                        dependenciesSection = `
                                            <div class="drawer-section">
                                                <h4 class="section-title">Dependencies</h4>
                                                <div class="dependencies-list">
                                                    ${item.dependencies.map(dep => `
                                                        <div class="dependency-item">
                                                            <i class="fas fa-link"></i> ${dep}
                                                        </div>
                                                    `).join('')}
                                                </div>
                                            </div>
                                        `;
                                    }
                                    
                                    // Build combined specifications section
                                    let specificationsSection = '';
                                    let hasSpecs = false;
                                    
                                    let specsContent = '';
                                    
                                    // Add component specs section
                                    if (item.component_specs && Object.keys(item.component_specs).length > 0) {
                                        specsContent += `
                                            <div class="spec-subsection">
                                                <h5 class="spec-heading">Component Specifications:</h5>
                                                <ul class="spec-list">
                                                    ${Object.entries(item.component_specs).map(([key, value]) => `
                                                        <li>${key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}: ${value}</li>
                                                    `).join('')}
                                                </ul>
                                            </div>
                                        `;
                                        hasSpecs = true;
                                    }
                                    
                                    // Add acceptance criteria section
                                    if (item.acceptance_criteria && item.acceptance_criteria.length > 0) {
                                        specsContent += `
                                            <div class="spec-subsection">
                                                <h5 class="spec-heading">Acceptance Criteria:</h5>
                                                <ul class="spec-list">
                                                    ${item.acceptance_criteria.map(criteria => `
                                                        <li>${criteria}</li>
                                                    `).join('')}
                                                </ul>
                                            </div>
                                        `;
                                        hasSpecs = true;
                                    }
                                    
                                    // Add UI requirements section
                                    if (item.ui_requirements && Object.keys(item.ui_requirements).length > 0) {
                                        specsContent += `
                                            <div class="spec-subsection">
                                                <h5 class="spec-heading">UI Requirements:</h5>
                                                <ul class="spec-list">
                                                    ${Object.entries(item.ui_requirements).map(([key, value]) => `
                                                        <li>${key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}: ${value}</li>
                                                    `).join('')}
                                                </ul>
                                            </div>
                                        `;
                                        hasSpecs = true;
                                    }
                                    
                                    if (hasSpecs) {
                                        specificationsSection = `
                                            <div class="drawer-section">
                                                <h4 class="section-title">Specifications</h4>
                                                <div class="specifications-content">
                                                    ${specsContent}
                                                </div>
                                            </div>
                                        `;
                                    }
                                    
                                    // Build details section
                                    let detailsSection = '';
                                    if (item.details && Object.keys(item.details).length > 0) {
                                        detailsSection = `
                                            <div class="drawer-section">
                                                <h4 class="section-title">Technical Details</h4>
                                                <div class="details-content">
                                                    ${Object.entries(item.details).map(([key, value]) => {
                                                        let valueHtml = '';
                                                        if (Array.isArray(value)) {
                                                            if (value.length > 0) {
                                                                valueHtml = `
                                                                    <ul class="detail-list">
                                                                        ${value.map(v => `<li>${typeof v === 'object' ? JSON.stringify(v, null, 2) : v}</li>`).join('')}
                                                                    </ul>
                                                                `;
                                                            } else {
                                                                valueHtml = '<em>Empty list</em>';
                                                            }
                                                        } else if (typeof value === 'object' && value !== null) {
                                                            valueHtml = `<pre class="detail-object">${JSON.stringify(value, null, 2)}</pre>`;
                                                        } else {
                                                            valueHtml = value || '<em>Not specified</em>';
                                                        }
                                                        
                                                        return `
                                                            <div class="detail-item">
                                                                <h5 class="detail-key">${key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</h5>
                                                                <div class="detail-value">${valueHtml}</div>
                                                            </div>
                                                        `;
                                                    }).join('')}
                                                </div>
                                            </div>
                                        `;
                                    }
                                    
                                    // Populate drawer with item details
                                    checklistDrawerContent.innerHTML = `
                                        <div class="drawer-section">
                                            <h4 class="section-title">Item Information</h4>
                                            <div class="checklist-detail-info">
                                                <p class="detail-row"><strong>Name:</strong> ${item.name}</p>
                                                <div class="detail-row">
                                                    <strong>Status:</strong> 
                                                    <select class="status-dropdown" data-item-id="${item.id}" data-current-status="${item.status || 'open'}">
                                                        <option value="open" ${(item.status || 'open') === 'open' ? 'selected' : ''}>Open</option>
                                                        <option value="in_progress" ${item.status === 'in_progress' ? 'selected' : ''}>In Progress</option>
                                                        <option value="done" ${item.status === 'done' ? 'selected' : ''}>Done</option>
                                                        <option value="failed" ${item.status === 'failed' ? 'selected' : ''}>Failed</option>
                                                        <option value="blocked" ${item.status === 'blocked' ? 'selected' : ''}>Blocked</option>
                                                    </select>
                                                </div>
                                                <p class="detail-row"><strong>Priority:</strong> <span class="priority-badge ${(item.priority || 'medium').toLowerCase()}">${item.priority || 'Medium'}</span></p>
                                                <div class="detail-row">
                                                    <strong>Assigned to:</strong> 
                                                    <select class="role-dropdown" data-item-id="${item.id}" data-current-role="${item.role || 'user'}">
                                                        <option value="user" ${(item.role || 'user') === 'user' ? 'selected' : ''}>User</option>
                                                        <option value="agent" ${item.role === 'agent' ? 'selected' : ''}>Agent</option>
                                                    </select>
                                                </div>
                                                ${item.complexity ? `<p class="detail-row"><strong>Complexity:</strong> <span class="complexity-badge ${item.complexity}">${item.complexity}</span></p>` : ''}
                                                ${item.requires_worktree !== undefined ? `<p class="detail-row"><strong>Requires Worktree:</strong> ${item.requires_worktree ? 'Yes' : 'No'}</p>` : ''}
                                            </div>
                                        </div>
                                        
                                        <div class="drawer-section">
                                            <h4 class="section-title">Description</h4>
                                            <div class="section-content description-content">
                                                ${item.description ? item.description.replace(/\n/g, '<br>') : 'No description provided.'}
                                            </div>
                                        </div>
                                        
                                        ${dependenciesSection}
                                        ${specificationsSection}
                                        ${detailsSection}
                                        
                                        <div class="drawer-section">
                                            <h4 class="section-title">Timeline</h4>
                                            <div class="section-content">
                                                <p class="detail-row"><strong>Created:</strong> ${new Date(item.created_at).toLocaleDateString()} at ${new Date(item.created_at).toLocaleTimeString()}</p>
                                                <p class="detail-row"><strong>Last Updated:</strong> ${new Date(item.updated_at).toLocaleDateString()} at ${new Date(item.updated_at).toLocaleTimeString()}</p>
                                            </div>
                                        </div>
                                        
                                        <div class="drawer-section">
                                            <h4 class="section-title">Actions</h4>
                                            <div class="drawer-actions">
                                                <button class="drawer-action-btn edit-btn" onclick="editChecklistItem(${item.id})" title="Edit Item" style="padding: 8px 10px;">
                                                    <i class="fas fa-edit"></i>
                                                </button>
                                                <button class="drawer-action-btn toggle-btn" onclick="toggleChecklistStatus(${item.id}, '${item.status}')" title="Toggle Status" style="padding: 8px 10px;">
                                                    <i class="fas fa-sync-alt"></i>
                                                </button>
                                                <button class="drawer-action-btn delete-btn" data-item-id="${item.id}" title="Delete Item" style="padding: 8px 10px; background: rgba(239, 68, 68, 0.2); color: #f87171;">
                                                    <i class="fas fa-trash"></i>
                                                </button>
                                            </div>
                                        </div>
                                    `;
                                    
                                    // Show the drawer
                                    checklistDrawer.classList.add('open');
                                    checklistDrawerOverlay.classList.add('active');
                                    
                                    // Add event listeners for the dropdowns
                                    attachDropdownListeners();
                                }
                            });
                        });
                        
                        // Function to attach dropdown event listeners
                        const attachDropdownListeners = () => {
                            const statusDropdowns = document.querySelectorAll('.status-dropdown');
                            const roleDropdowns = document.querySelectorAll('.role-dropdown');
                            
                            statusDropdowns.forEach(dropdown => {
                                dropdown.addEventListener('change', function() {
                                    const itemId = this.getAttribute('data-item-id');
                                    const newStatus = this.value;
                                    const oldStatus = this.getAttribute('data-current-status');
                                    
                                    updateChecklistItemStatus(itemId, newStatus, oldStatus);
                                });
                            });
                            
                            roleDropdowns.forEach(dropdown => {
                                dropdown.addEventListener('change', function() {
                                    const itemId = this.getAttribute('data-item-id');
                                    const newRole = this.value;
                                    const oldRole = this.getAttribute('data-current-role');
                                    
                                    updateChecklistItemRole(itemId, newRole, oldRole);
                                });
                            });
                            
                            // Add delete button listener in drawer
                            const deleteBtn = document.querySelector('.drawer-action-btn.delete-btn');
                            if (deleteBtn) {
                                deleteBtn.addEventListener('click', function() {
                                    const itemId = this.getAttribute('data-item-id');
                                    const item = checklist.find(i => i.id == itemId);
                                    
                                    if (item && confirm(`Are you sure you want to delete "${item.name}"?`)) {
                                        // Close the drawer first
                                        checklistDrawer.classList.remove('open');
                                        checklistDrawerOverlay.classList.remove('active');
                                        
                                        // Call delete API
                                        fetch(`/projects/${projectId}/api/checklist/${itemId}/delete/`, {
                                            method: 'DELETE',
                                            headers: {
                                                'X-CSRFToken': getCsrfToken()
                                            }
                                        })
                                        .then(response => {
                                            if (!response.ok) {
                                                throw new Error('Failed to delete item');
                                            }
                                            return response.json();
                                        })
                                        .then(data => {
                                            if (data.success) {
                                                showToast('Item deleted successfully', 'success');
                                                // Reload checklist to reflect the deletion
                                                ArtifactsLoader.loadChecklist(projectId);
                                            } else {
                                                showToast(data.error || 'Failed to delete item', 'error');
                                            }
                                        })
                                        .catch(error => {
                                            console.error('Error deleting item:', error);
                                            showToast('Error deleting item', 'error');
                                        });
                                    }
                                });
                            }
                        };
                        
                        // Add click handlers for view details buttons
                        viewDetailsButtons.forEach(button => {
                            button.addEventListener('click', function(e) {
                                e.stopPropagation(); // Prevent card click event
                                const itemId = this.getAttribute('data-item-id');
                                const item = checklist.find(i => i.id == itemId);
                                
                                if (item) {
                                    // Trigger the same drawer opening logic
                                    const card = this.closest('.checklist-card');
                                    if (card) {
                                        card.click();
                                    }
                                }
                            });
                        });
                        
                        // Add event listeners for delete buttons
                        const deleteButtons = document.querySelectorAll('.delete-checklist-btn');
                        deleteButtons.forEach(button => {
                            button.addEventListener('click', function(e) {
                                e.stopPropagation(); // Prevent card click
                                const itemId = this.getAttribute('data-item-id');
                                const item = checklist.find(i => i.id == itemId);
                                
                                if (item && confirm(`Are you sure you want to delete "${item.name}"?`)) {
                                    // Call delete API
                                    fetch(`/projects/${projectId}/api/checklist/${itemId}/delete/`, {
                                        method: 'DELETE',
                                        headers: {
                                            'X-CSRFToken': getCsrfToken()
                                        }
                                    })
                                    .then(response => {
                                        if (!response.ok) {
                                            throw new Error('Failed to delete item');
                                        }
                                        return response.json();
                                    })
                                    .then(data => {
                                        if (data.success) {
                                            showToast('Item deleted successfully', 'success');
                                            // Reload checklist to reflect the deletion
                                            ArtifactsLoader.loadChecklist(projectId);
                                        } else {
                                            showToast(data.error || 'Failed to delete item', 'error');
                                        }
                                    })
                                    .catch(error => {
                                        console.error('Error deleting item:', error);
                                        showToast('Error deleting item', 'error');
                                    });
                                }
                            });
                        });
                        
                        // Close drawer event handlers
                        if (closeChecklistDrawerBtn) {
                            closeChecklistDrawerBtn.addEventListener('click', function() {
                                checklistDrawer.classList.remove('open');
                                checklistDrawerOverlay.classList.remove('active');
                            });
                        }
                        
                        if (checklistDrawerOverlay) {
                            checklistDrawerOverlay.addEventListener('click', function() {
                                checklistDrawer.classList.remove('open');
                                checklistDrawerOverlay.classList.remove('active');
                            });
                        }
                    };

                    // Function to update checklist item status
                    const updateChecklistItemStatus = (itemId, newStatus, oldStatus) => {
                        console.log(`[ArtifactsLoader] Updating checklist item ${itemId} status from ${oldStatus} to ${newStatus}`);
                        const projectId = getCurrentProjectId();
                        if (!projectId) {
                            console.warn('[ArtifactsLoader] No project ID available for status update');
                            showStatusUpdateError('Project ID not available');
                            return;
                        }
                        const dropdown = document.querySelector(`.status-dropdown[data-item-id="${itemId}"]`);
                        if (dropdown) {
                            dropdown.disabled = true;
                            dropdown.style.opacity = '0.6';
                        }
                        // Call backend API
                        fetch(`/projects/${projectId}/api/checklist/update/`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRFToken': getCsrfToken(),
                            },
                            body: JSON.stringify({ item_id: itemId, status: newStatus })
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                if (dropdown) {
                                    dropdown.disabled = false;
                                    dropdown.style.opacity = '1';
                                    dropdown.setAttribute('data-current-status', newStatus);
                                }
                                // Update the item in the checklist array (if available)
                                const item = checklist.find(i => i.id == itemId);
                                if (item) {
                                    item.status = newStatus;
                                    item.updated_at = data.updated_at || new Date().toISOString();
                                }
                                // Update the visual state in the main list
                                const itemElement = document.querySelector(`[data-id="${itemId}"]`);
                                if (itemElement) {
                                    itemElement.classList.remove('open', 'in-progress', 'done', 'failed', 'blocked');
                                    itemElement.classList.add(newStatus.replace('_', '-'));
                                    const statusIcon = itemElement.querySelector('.status-icon');
                                    if (statusIcon) {
                                        let newIconClass = 'fas fa-circle';
                                        switch(newStatus) {
                                            case 'open': newIconClass = 'fas fa-circle'; break;
                                            case 'in_progress': newIconClass = 'fas fa-play-circle'; break;
                                            case 'done': newIconClass = 'fas fa-check-circle'; break;
                                            case 'failed': newIconClass = 'fas fa-times-circle'; break;
                                            case 'blocked': newIconClass = 'fas fa-ban'; break;
                                        }
                                        statusIcon.className = `${newIconClass} status-icon`;
                                    }
                                }
                                console.log(`[ArtifactsLoader] Status updated successfully to: ${newStatus}`);
                                showStatusUpdateSuccess(newStatus);
                            } else {
                                showStatusUpdateError(data.error || 'Failed to update status');
                                if (dropdown) {
                                    dropdown.disabled = false;
                                    dropdown.style.opacity = '1';
                                }
                            }
                        })
                        .catch(error => {
                            showStatusUpdateError(error.message || 'Failed to update status');
                            if (dropdown) {
                                dropdown.disabled = false;
                                dropdown.style.opacity = '1';
                            }
                        });
                    };

                    // Function to update checklist item role/assignment
                    const updateChecklistItemRole = (itemId, newRole, oldRole) => {
                        console.log(`[ArtifactsLoader] Updating checklist item ${itemId} role from ${oldRole} to ${newRole}`);
                        const projectId = getCurrentProjectId();
                        if (!projectId) {
                            console.warn('[ArtifactsLoader] No project ID available for role update');
                            showRoleUpdateError('Project ID not available');
                            return;
                        }
                        const dropdown = document.querySelector(`.role-dropdown[data-item-id="${itemId}"]`);
                        if (dropdown) {
                            dropdown.disabled = true;
                            dropdown.style.opacity = '0.6';
                        }
                        // Call backend API
                        fetch(`/projects/${projectId}/api/checklist/update/`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRFToken': getCsrfToken(),
                            },
                            body: JSON.stringify({ item_id: itemId, role: newRole })
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                if (dropdown) {
                                    dropdown.disabled = false;
                                    dropdown.style.opacity = '1';
                                    dropdown.setAttribute('data-current-role', newRole);
                                }
                                // Update the item in the checklist array (if available)
                                const item = checklist.find(i => i.id == itemId);
                                if (item) {
                                    item.role = newRole;
                                    item.updated_at = data.updated_at || new Date().toISOString();
                                }
                                // Update the visual state in the main list
                                const itemElement = document.querySelector(`[data-id="${itemId}"]`);
                                if (itemElement) {
                                    itemElement.classList.remove('user', 'agent');
                                    itemElement.classList.add(newRole);
                                    const roleBadge = itemElement.querySelector('.role-badge');
                                    if (roleBadge) {
                                        roleBadge.className = `role-badge ${newRole}`;
                                        roleBadge.textContent = newRole.charAt(0).toUpperCase() + newRole.slice(1);
                                    }
                                }
                                console.log(`[ArtifactsLoader] Role updated successfully to: ${newRole}`);
                                showRoleUpdateSuccess(newRole);
                            } else {
                                showRoleUpdateError(data.error || 'Failed to update role');
                                if (dropdown) {
                                    dropdown.disabled = false;
                                    dropdown.style.opacity = '1';
                                }
                            }
                        })
                        .catch(error => {
                            showRoleUpdateError(error.message || 'Failed to update role');
                            if (dropdown) {
                                dropdown.disabled = false;
                                dropdown.style.opacity = '1';
                            }
                        });
                    };

                    // Function to show status update success message
                    const showStatusUpdateSuccess = (newStatus) => {
                        const statusUpdateMessage = document.getElementById('status-update-message');
                        if (statusUpdateMessage) {
                            statusUpdateMessage.textContent = `Status updated to: ${newStatus}`;
                            statusUpdateMessage.style.display = 'block';
                            setTimeout(() => {
                                statusUpdateMessage.style.display = 'none';
                            }, 3000);
                        }
                    };

                    // Function to show role update success message
                    const showRoleUpdateSuccess = (newRole) => {
                        const roleUpdateMessage = document.getElementById('role-update-message');
                        if (roleUpdateMessage) {
                            roleUpdateMessage.textContent = `Role updated to: ${newRole}`;
                            roleUpdateMessage.style.display = 'block';
                            setTimeout(() => {
                                roleUpdateMessage.style.display = 'none';
                            }, 3000);
                        }
                    };

                    // Function to show status update error message
                    const showStatusUpdateError = (errorMessage) => {
                        const statusUpdateError = document.getElementById('status-update-error');
                        if (statusUpdateError) {
                            statusUpdateError.textContent = `Error updating status: ${errorMessage}`;
                            statusUpdateError.style.display = 'block';
                            setTimeout(() => {
                                statusUpdateError.style.display = 'none';
                            }, 5000);
                        }
                    };

                    // Function to show role update error message
                    const showRoleUpdateError = (errorMessage) => {
                        const roleUpdateError = document.getElementById('role-update-error');
                        if (roleUpdateError) {
                            roleUpdateError.textContent = `Error updating role: ${errorMessage}`;
                            roleUpdateError.style.display = 'block';
                            setTimeout(() => {
                                roleUpdateError.style.display = 'none';
                            }, 5000);
                        }
                    };

                    // Attach event listeners for filters
                    statusFilter.addEventListener('change', function() {
                        const filterStatus = this.value;
                        const filterRole = roleFilter.value;
                        renderChecklist(filterStatus, filterRole);
                    });
                    
                    roleFilter.addEventListener('change', function() {
                        const filterStatus = statusFilter.value;
                        const filterRole = this.value;
                        renderChecklist(filterStatus, filterRole);
                    });
                    
                    clearFiltersBtn.addEventListener('click', function() {
                        statusFilter.value = 'all';
                        roleFilter.value = 'all';
                        renderChecklist();
                    });
                    
                    // Add delete all button event listener
                    const deleteAllBtn = document.getElementById('delete-all-checklist');
                    if (deleteAllBtn) {
                        deleteAllBtn.addEventListener('click', function() {
                            if (checklist.length === 0) {
                                showToast('No items to delete', 'info');
                                return;
                            }
                            
                            if (confirm(`Are you sure you want to delete ALL ${checklist.length} checklist items? This action cannot be undone.`)) {
                                // Show loading state
                                this.disabled = true;
                                this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Deleting...';
                                
                                // Delete all items
                                const deletePromises = checklist.map(item => 
                                    fetch(`/projects/${projectId}/api/checklist/${item.id}/delete/`, {
                                        method: 'DELETE',
                                        headers: {
                                            'X-CSRFToken': getCsrfToken()
                                        }
                                    })
                                );
                                
                                Promise.all(deletePromises)
                                    .then(responses => {
                                        const failedDeletions = responses.filter(r => !r.ok).length;
                                        if (failedDeletions === 0) {
                                            showToast('All checklist items deleted successfully', 'success');
                                        } else {
                                            showToast(`Deleted ${checklist.length - failedDeletions} items. ${failedDeletions} failed.`, 'warning');
                                        }
                                        // Reload the checklist
                                        ArtifactsLoader.loadChecklist(projectId);
                                    })
                                    .catch(error => {
                                        console.error('Error deleting items:', error);
                                        showToast('Error deleting items', 'error');
                                        // Re-enable button
                                        this.disabled = false;
                                        this.innerHTML = '<i class="fas fa-trash-alt"></i> Delete All';
                                    });
                            }
                        });
                    }

                    // Add Linear sync button event listener for checklist
                    const syncChecklistLinearBtn = document.getElementById('sync-checklist-linear');
                    if (syncChecklistLinearBtn) {
                        syncChecklistLinearBtn.addEventListener('click', async function() {
                            try {
                                // First check if Linear API key is configured
                                const configResponse = await fetch(`/projects/${projectId}/api/linear/teams/`);
                                const configData = await configResponse.json();
                                
                                if (!configData.success) {
                                    window.showToast(configData.error || 'Linear API key not configured. Please go to Integrations to add your Linear API key.', 'error');
                                    return;
                                }
                                
                                // Show project selection popup
                                window.showLinearProjectSelectionPopup(projectId, configData.teams);
                            } catch (error) {
                                console.error('Error checking Linear configuration:', error);
                                window.showToast('Error connecting to Linear. Please check your configuration.', 'error');
                            }
                        });
                    }
                    
                    // Add dropdown toggle functionality
                    const dropdownToggle = document.getElementById('checklist-actions-dropdown');
                    const dropdownMenu = document.getElementById('checklist-actions-menu');
                    
                    if (dropdownToggle && dropdownMenu) {
                        // Toggle dropdown on button click
                        dropdownToggle.addEventListener('click', function(e) {
                            e.stopPropagation();
                            const isVisible = dropdownMenu.style.display === 'block';
                            dropdownMenu.style.display = isVisible ? 'none' : 'block';
                        });
                        
                        // Close dropdown when clicking outside
                        document.addEventListener('click', function(e) {
                            if (!dropdownToggle.contains(e.target) && !dropdownMenu.contains(e.target)) {
                                dropdownMenu.style.display = 'none';
                            }
                        });
                        
                        // Prevent dropdown from closing when clicking inside the menu
                        dropdownMenu.addEventListener('click', function(e) {
                            e.stopPropagation();
                        });
                    }
                    
                    // Helper function to show toast notifications
                    function showToast(message, type = 'info') {
                        // Create toast element if it doesn't exist
                        let toastContainer = document.getElementById('toast-container');
                        if (!toastContainer) {
                            toastContainer = document.createElement('div');
                            toastContainer.id = 'toast-container';
                            toastContainer.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 9999;';
                            document.body.appendChild(toastContainer);
                        }
                        
                        const toast = document.createElement('div');
                        toast.className = `toast toast-${type}`;
                        toast.style.cssText = 'background: #333; color: white; padding: 12px 24px; border-radius: 4px; margin-bottom: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.2); animation: slideIn 0.3s ease;';
                        
                        if (type === 'success') {
                            toast.style.background = '#4CAF50';
                        } else if (type === 'error') {
                            toast.style.background = '#f44336';
                        }
                        
                        toast.textContent = message;
                        toastContainer.appendChild(toast);
                        
                        // Remove toast after 5 seconds
                        setTimeout(() => {
                            toast.style.animation = 'slideOut 0.3s ease';
                            setTimeout(() => toast.remove(), 300);
                        }, 5000);
                    }
                    
                    // Helper function to get CSRF token
                    function getCookie(name) {
                        let cookieValue = null;
                        if (document.cookie && document.cookie !== '') {
                            const cookies = document.cookie.split(';');
                            for (let i = 0; i < cookies.length; i++) {
                                const cookie = cookies[i].trim();
                                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                                    break;
                                }
                            }
                        }
                        return cookieValue;
                    }
                    
                    // Function to show Linear project selection popup
                    async function showLinearProjectSelectionPopup(projectId, teams) {
                        // Create popup overlay
                        const overlay = document.createElement('div');
                        overlay.className = 'linear-popup-overlay';
                        overlay.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 10000; display: flex; align-items: center; justify-content: center;';
                        
                        // Create popup container
                        const popup = document.createElement('div');
                        popup.className = 'linear-popup';
                        popup.style.cssText = 'background: #2a2a2a; padding: 30px; border-radius: 8px; max-width: 500px; width: 90%; max-height: 80vh; overflow-y: auto; box-shadow: 0 4px 20px rgba(0,0,0,0.5);';
                        
                        // Check if we have teams
                        if (!teams || teams.length === 0) {
                            popup.innerHTML = `
                                <h3 style="color: #fff; margin-bottom: 20px;">No Linear Teams Found</h3>
                                <p style="color: #ccc; margin-bottom: 20px;">Please make sure your Linear API key has access to at least one team.</p>
                                <button class="close-popup-btn" style="background: #666; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer;">Close</button>
                            `;
                            overlay.appendChild(popup);
                            document.body.appendChild(overlay);
                            
                            popup.querySelector('.close-popup-btn').addEventListener('click', () => {
                                overlay.remove();
                            });
                            return;
                        }
                        
                        // Get current project info
                        const projectResponse = await fetch(`/projects/${projectId}/`);
                        const projectData = await projectResponse.json();
                        const currentLinearProjectId = projectData.linear_project_id;
                        
                        let popupHTML = `
                            <h3 style="color: #fff; margin-bottom: 20px;">Sync with Linear Team</h3>
                            <div class="linear-teams-container">
                        `;
                        
                        // Add team selection if multiple teams
                        if (teams.length > 1) {
                            popupHTML += `
                                <div style="margin-bottom: 20px;">
                                    <label style="color: #ccc; display: block; margin-bottom: 8px;">Select Team:</label>
                                    <select id="linear-team-select" style="width: 100%; padding: 8px; background: #1a1a1a; border: 1px solid #444; color: #fff; border-radius: 4px;">
                                        ${teams.map(team => `<option value="${team.id}">${team.name}</option>`).join('')}
                                    </select>
                                </div>
                            `;
                        }
                        
                        popupHTML += `
                            <div style="margin-bottom: 20px;">
                                <label style="color: #ccc; display: block; margin-bottom: 8px;">Select Project:</label>
                                <div id="linear-projects-loading" style="color: #888; text-align: center; padding: 20px;">
                                    <i class="fas fa-spinner fa-spin"></i> Loading projects...
                                </div>
                                <select id="linear-project-select" style="width: 100%; padding: 8px; background: #1a1a1a; border: 1px solid #444; color: #fff; border-radius: 4px; display: none;">
                                    <option value="">Select a project...</option>
                                </select>
                            </div>
                            
                            <div style="margin-bottom: 20px;">
                                <button id="create-new-project-btn" style="background: #5856d6; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; margin-right: 10px;">
                                    <i class="fas fa-plus"></i> Create New Project
                                </button>
                            </div>
                            
                            <div id="new-project-form" style="display: none; margin-bottom: 20px; padding: 20px; background: #1a1a1a; border-radius: 4px;">
                                <h4 style="color: #fff; margin-bottom: 15px;">Create New Linear Project</h4>
                                <input type="text" id="new-project-name" placeholder="Project Name" style="width: 100%; padding: 8px; background: #2a2a2a; border: 1px solid #444; color: #fff; border-radius: 4px; margin-bottom: 10px;">
                                <textarea id="new-project-description" placeholder="Project Description (optional)" style="width: 100%; padding: 8px; background: #2a2a2a; border: 1px solid #444; color: #fff; border-radius: 4px; min-height: 80px; margin-bottom: 10px;"></textarea>
                                <button id="confirm-create-project" style="background: #4CAF50; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-right: 10px;">Create</button>
                                <button id="cancel-create-project" style="background: #666; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer;">Cancel</button>
                            </div>
                            
                            <div style="display: flex; justify-content: flex-end; gap: 10px;">
                                <button class="cancel-popup-btn" style="background: #666; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer;">Cancel</button>
                                <button class="confirm-popup-btn" style="background: #5856d6; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer;">Sync with Selected Team</button>
                            </div>
                        </div>
                        `;
                        
                        popup.innerHTML = popupHTML;
                        overlay.appendChild(popup);
                        document.body.appendChild(overlay);
                        
                        // Elements
                        const teamSelect = popup.querySelector('#linear-team-select');
                        const projectSelect = popup.querySelector('#linear-project-select');
                        const projectsLoading = popup.querySelector('#linear-projects-loading');
                        const createNewBtn = popup.querySelector('#create-new-project-btn');
                        const newProjectForm = popup.querySelector('#new-project-form');
                        const confirmBtn = popup.querySelector('.confirm-popup-btn');
                        const cancelBtn = popup.querySelector('.cancel-popup-btn');
                        
                        // Load projects for the selected team
                        async function loadProjects(teamId) {
                            projectsLoading.style.display = 'block';
                            projectSelect.style.display = 'none';
                            
                            const response = await fetch(`/projects/${projectId}/api/linear/projects/?team_id=${teamId}`);
                            const data = await response.json();
                            
                            if (data.success && data.projects) {
                                projectSelect.innerHTML = '<option value="">Select a project...</option>';
                                data.projects.forEach(project => {
                                    const selected = project.id === currentLinearProjectId ? 'selected' : '';
                                    projectSelect.innerHTML += `<option value="${project.id}" ${selected}>${project.name}</option>`;
                                });
                                projectsLoading.style.display = 'none';
                                projectSelect.style.display = 'block';
                                
                                // Enable confirm button if a project is already selected
                                if (currentLinearProjectId && projectSelect.value) {
                                    confirmBtn.disabled = false;
                                }
                            }
                        }
                        
                        // Initial load
                        const initialTeamId = teams.length === 1 ? teams[0].id : teamSelect.value;
                        loadProjects(initialTeamId);
                        
                        // Team change handler
                        if (teamSelect) {
                            teamSelect.addEventListener('change', (e) => {
                                loadProjects(e.target.value);
                            });
                        }
                        
                        // Project selection handler
                        projectSelect.addEventListener('change', (e) => {
                            confirmBtn.disabled = !e.target.value;
                        });
                        
                        // Create new project handlers
                        createNewBtn.addEventListener('click', () => {
                            newProjectForm.style.display = 'block';
                            createNewBtn.style.display = 'none';
                        });
                        
                        popup.querySelector('#cancel-create-project').addEventListener('click', () => {
                            newProjectForm.style.display = 'none';
                            createNewBtn.style.display = 'block';
                        });
                        
                        popup.querySelector('#confirm-create-project').addEventListener('click', async () => {
                            const projectName = popup.querySelector('#new-project-name').value;
                            const projectDescription = popup.querySelector('#new-project-description').value;
                            
                            if (!projectName) {
                                showToast('Please enter a project name', 'error');
                                return;
                            }
                            
                            const currentTeamId = teams.length === 1 ? teams[0].id : teamSelect.value;
                            
                            // Create the project via API
                            showToast('Creating new Linear project...', 'info');
                            
                            try {
                                const createResponse = await fetch(`/projects/${projectId}/api/linear/create-project/`, {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json',
                                        'X-CSRFToken': getCookie('csrftoken')
                                    },
                                    body: JSON.stringify({
                                        team_id: currentTeamId,
                                        name: projectName,
                                        description: projectDescription
                                    })
                                });
                                
                                const createData = await createResponse.json();
                                
                                if (createData.success) {
                                    showToast('Linear project created successfully!', 'success');
                                    
                                    // Hide the form
                                    newProjectForm.style.display = 'none';
                                    createNewBtn.style.display = 'block';
                                    
                                    // Clear form fields
                                    popup.querySelector('#new-project-name').value = '';
                                    popup.querySelector('#new-project-description').value = '';
                                    
                                    // Reload projects and select the new one
                                    await loadProjects(currentTeamId);
                                    
                                    // Select the newly created project
                                    if (createData.project && createData.project.id) {
                                        projectSelect.value = createData.project.id;
                                        confirmBtn.disabled = false;
                                    }
                                } else {
                                    showToast(createData.error || 'Failed to create Linear project', 'error');
                                }
                            } catch (error) {
                                console.error('Error creating Linear project:', error);
                                showToast('Error creating Linear project', 'error');
                            }
                        });
                        
                        // Cancel handler
                        cancelBtn.addEventListener('click', () => {
                            overlay.remove();
                        });
                        
                        // Confirm handler
                        confirmBtn.addEventListener('click', async () => {
                            const selectedTeamId = teams.length === 1 ? teams[0].id : teamSelect.value;
                            
                            if (!selectedTeamId) {
                                showToast('Please select a team', 'error');
                                return;
                            }
                            
                            // Save the selected team to the backend
                            const saveResponse = await fetch(`/projects/${projectId}/update/`, {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/x-www-form-urlencoded',
                                    'X-CSRFToken': getCookie('csrftoken')
                                },
                                body: new URLSearchParams({
                                    'name': projectData.name || '',
                                    'description': projectData.description || '',
                                    'linear_sync_enabled': 'on',
                                    'linear_team_id': selectedTeamId,
                                    'linear_project_id': ''
                                })
                            });
                            
                            if (saveResponse.ok) {
                                // Close popup
                                overlay.remove();
                                
                                // Show progress overlay
                                const progressOverlay = document.createElement('div');
                                progressOverlay.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); display: flex; align-items: center; justify-content: center; z-index: 10000;';
                                
                                const progressContainer = document.createElement('div');
                                progressContainer.style.cssText = 'background: #2a2a2a; padding: 30px; border-radius: 8px; min-width: 400px; text-align: center;';
                                
                                progressContainer.innerHTML = `
                                    <h3 style="color: #fff; margin-bottom: 20px;">Syncing with Linear</h3>
                                    <div style="margin-bottom: 15px;">
                                        <div style="background: #444; height: 20px; border-radius: 10px; overflow: hidden;">
                                            <div id="sync-progress-bar-2" style="background: #5856d6; height: 100%; width: 0%; transition: width 0.3s ease;"></div>
                                        </div>
                                    </div>
                                    <p id="sync-progress-text-2" style="color: #ccc; margin: 0;">Initializing sync...</p>
                                `;
                                
                                progressOverlay.appendChild(progressContainer);
                                document.body.appendChild(progressOverlay);
                                
                                // Simulate progress while waiting for response
                                const progressBar = document.getElementById('sync-progress-bar-2');
                                const progressText = document.getElementById('sync-progress-text-2');
                                
                                progressBar.style.width = '20%';
                                progressText.textContent = 'Connecting to Linear...';
                                
                                try {
                                    const syncResponse = await fetch(`/projects/${projectId}/api/linear/sync/`, {
                                        method: 'POST',
                                        headers: {
                                            'Content-Type': 'application/json',
                                            'X-CSRFToken': getCookie('csrftoken')
                                        },
                                    });
                                    
                                    progressBar.style.width = '60%';
                                    progressText.textContent = 'Processing items...';
                                    
                                    const syncData = await syncResponse.json();
                                    
                                    progressBar.style.width = '100%';
                                    
                                    if (syncData.success) {
                                        progressText.textContent = `Synced ${syncData.results?.created || 0} items successfully!`;
                                        
                                        // Show completion for a moment
                                        setTimeout(() => {
                                            progressOverlay.remove();
                                            showToast(syncData.message || 'Tasks synced successfully!', 'success');
                                            ArtifactsLoader.loadChecklist(projectId);
                                        }, 1500);
                                    } else {
                                        progressText.textContent = 'Sync failed!';
                                        progressBar.style.background = '#f44336';
                                        
                                        setTimeout(() => {
                                            progressOverlay.remove();
                                            showToast(syncData.error || 'Failed to sync tasks', 'error');
                                        }, 1500);
                                    }
                                } catch (error) {
                                    progressBar.style.width = '100%';
                                    progressBar.style.background = '#f44336';
                                    progressText.textContent = 'Network error!';
                                    
                                    setTimeout(() => {
                                        progressOverlay.remove();
                                        showToast('Network error during sync', 'error');
                                    }, 1500);
                                }
                            } else {
                                showToast('Failed to save Linear team selection', 'error');
                            }
                        });
                        
                        // Close on overlay click
                        overlay.addEventListener('click', (e) => {
                            if (e.target === overlay) {
                                overlay.remove();
                            }
                        });
                    }

                    // Initial render
                    renderChecklist();
                })
                .catch(error => {
                    console.error('[ArtifactsLoader] Error fetching checklist:', error);
                    checklistTab.innerHTML = `
                        <div class="error-state">
                            <div class="error-state-icon">
                                <i class="fas fa-exclamation-triangle"></i>
                            </div>
                            <div class="error-state-text">
                                Error loading checklist. Please try again.
                            </div>
                        </div>
                    `;
                });
        },

        /**
         * Load app preview from ServerConfig for the current project
         * @param {number} projectId - The ID of the current project
         * @param {number} conversationId - Optional conversation ID (not used for ServerConfig)
         */
        loadAppPreview: function(projectId, conversationId) {
            console.log(`[ArtifactsLoader] loadAppPreview called with project ID: ${projectId}, conversation ID: ${conversationId}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading app preview');
                return;
            }
            
            // Get app tab elements
            const appTab = document.getElementById('apps');
            const appLoading = document.getElementById('app-loading');
            const appEmpty = document.getElementById('app-empty');
            const appFrameContainer = document.getElementById('app-frame-container');
            const appIframe = document.getElementById('app-iframe');
            
            if (!appTab || !appLoading || !appEmpty || !appFrameContainer || !appIframe) {
                console.warn('[ArtifactsLoader] One or more app tab elements not found');
                return;
            }
            
            // Show loading state
            appEmpty.style.display = 'none';
            appFrameContainer.style.display = 'none';
            appLoading.style.display = 'block';
            
            // Fetch server configs from API
            const serverConfigsUrl = `/projects/${projectId}/api/server-configs/`;
            console.log(`[ArtifactsLoader] Fetching server configs from API: ${serverConfigsUrl}`);
            
            fetch(serverConfigsUrl)
                .then(response => {
                    console.log(`[ArtifactsLoader] Server configs API response received, status: ${response.status}`);
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('[ArtifactsLoader] Server configs API data received:', data);
                    
                    // Process server configs
                    const serverConfigs = data.server_configs || [];
                    console.log(`[ArtifactsLoader] Found ${serverConfigs.length} server configurations`);
                    
                    if (serverConfigs.length === 0) {
                        // Show empty state if no server configs found
                        console.log('[ArtifactsLoader] No server configs found, showing empty state');
                        showEmptyState("No application servers found. Start a server using the chat interface by running commands like 'npm start' or 'python manage.py runserver'.");
                        return;
                    }
                    
                    // Find the first application server or use the first config
                    let selectedConfig = serverConfigs.find(config => config.type === 'application') || serverConfigs[0];
                    console.log(`[ArtifactsLoader] Selected server config:`, selectedConfig);
                    
                    // If there are multiple configs, you could potentially show a selector here
                    if (serverConfigs.length > 1) {
                        console.log(`[ArtifactsLoader] Multiple server configs available, using: ${selectedConfig.type} on port ${selectedConfig.port}`);
                    }
                    
                    // Construct the URL for the iframe using localhost and the configured port
                    const appUrl = `http://localhost:${selectedConfig.port}/`;
                    console.log(`[ArtifactsLoader] Loading app from URL: ${appUrl}`);
                    
                    // First, check if the server is actually running by testing the URL
                    console.log(`[ArtifactsLoader] Testing server connectivity at: ${appUrl}`);
                    
                    // Test server connectivity before loading iframe
                    fetch(appUrl, {
                        method: 'GET',
                        mode: 'no-cors', // Avoid CORS issues for connectivity test
                        cache: 'no-cache'
                    })
                    .then(() => {
                        console.log(`[ArtifactsLoader] Server connectivity test passed for ${appUrl}`);
                        loadIframeApp(appUrl, selectedConfig);
                    })
                    .catch((error) => {
                        console.error(`[ArtifactsLoader] Server connectivity test failed for ${appUrl}:`, error);
                        showServerNotRunningError(selectedConfig.port);
                    });
                    
                    // Function to load the app in iframe after connectivity is confirmed
                    function loadIframeApp(iframeUrl, config) {
                        console.log(`[ArtifactsLoader] Loading verified server in iframe: ${iframeUrl}`);
                        
                        // Use setTimeout to ensure DOM is ready
                        setTimeout(() => {
                            // Show URL panel and update URL
                            const urlPanel = document.getElementById('app-url-panel');
                            const urlInput = document.getElementById('app-url-input');
                            const refreshBtn = document.getElementById('app-refresh-btn');
                            const restartServerBtn = document.getElementById('app-restart-server-btn');
                            
                            if (urlPanel && urlInput) {
                                console.log('[ArtifactsLoader] Setting URL in panel to:', iframeUrl);
                                urlPanel.style.display = 'block';
                                urlInput.value = iframeUrl;
                            
                            // Handle URL input
                            urlInput.onkeypress = function(e) {
                                if (e.key === 'Enter') {
                                    const newUrl = this.value.trim();
                                    if (newUrl) {
                                        console.log('[ArtifactsLoader] Navigating to:', newUrl);
                                        appIframe.src = newUrl;
                                    }
                                }
                            };
                            
                            // Select all on focus
                            urlInput.onfocus = function() {
                                this.select();
                            };
                        } else {
                            console.error('[ArtifactsLoader] URL panel elements not found', {urlPanel, urlInput});
                        }
                        
                        // Set up refresh button
                        if (refreshBtn) {
                            refreshBtn.onclick = function() {
                                console.log('[ArtifactsLoader] Refreshing iframe');
                                // Force reload by clearing and resetting src
                                const currentSrc = appIframe.src;
                                appIframe.src = '';
                                setTimeout(() => {
                                    appIframe.src = currentSrc;
                                }, 100);
                            };
                            
                            // Add hover effect
                            refreshBtn.onmouseover = function() {
                                this.style.background = '#5a6578';
                            };
                            refreshBtn.onmouseout = function() {
                                this.style.background = '#4a5568';
                            };
                        }
                        
                        // Set up restart server button
                        if (restartServerBtn) {
                            restartServerBtn.onclick = function() {
                                console.log('[ArtifactsLoader] Restarting server');
                                // Disable button and show loading state
                                this.disabled = true;
                                this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Restarting...';
                                window.ArtifactsLoader.checkAndRestartServers(projectId);
                            };
                            
                            // Add hover effect
                            restartServerBtn.onmouseover = function() {
                                if (!this.disabled) {
                                    this.style.background = '#7c3aed';
                                }
                            };
                            restartServerBtn.onmouseout = function() {
                                if (!this.disabled) {
                                    this.style.background = '#8b5cf6';
                                }
                            };
                        }
                        }, 100); // Small delay to ensure DOM is ready
                        
                        // Set up iframe load tracking
                        let hasLoaded = false;
                        let timeoutId = null;
                        
                        // Set up iframe event handlers
                        appIframe.onload = function() {
                            console.log('[ArtifactsLoader] Iframe onload event triggered');
                            hasLoaded = true;
                            clearTimeout(timeoutId);
                            
                            appLoading.style.display = 'none';
                            appFrameContainer.style.display = 'flex';
                            console.log('[ArtifactsLoader] App iframe loaded successfully');
                        };
                        
                        appIframe.onerror = function(e) {
                            console.error('[ArtifactsLoader] Error loading app iframe:', e);
                            hasLoaded = true;
                            clearTimeout(timeoutId);
                            showErrorState(`Failed to load application from port ${config.port}. The server may have stopped or encountered an error.`);
                        };
                        
                        // Set up timeout as fallback
                        timeoutId = setTimeout(() => {
                            if (!hasLoaded) {
                                console.warn('[ArtifactsLoader] App iframe taking too long to load');
                                showErrorState(`Application is taking too long to load from port ${config.port}. The server may be slow to respond.`);
                            }
                        }, 10000); // 10 second timeout for verified servers
                        
                        // Set the iframe source to load the app
                        appIframe.src = iframeUrl;
                        
                        // Adjust the container to fill available space
                        appTab.style.overflow = 'hidden';
                        
                        // Set up console functionality
                        setupConsole();
                    }
                    
                    // Function to set up console functionality
                    function setupConsole() {
                        const consolePanel = document.getElementById('console-panel');
                        const consoleOutput = document.getElementById('console-output');
                        const showConsoleBtn = document.getElementById('show-console-btn');
                        const toggleConsoleBtn = document.getElementById('toggle-console-btn');
                        const clearConsoleBtn = document.getElementById('clear-console-btn');
                        const pipeConsoleBtn = document.getElementById('pipe-console-btn');
                        
                        if (!consolePanel || !consoleOutput || !showConsoleBtn) {
                            console.warn('[ArtifactsLoader] Console elements not found');
                            return;
                        }
                        
                        // Show the console button
                        showConsoleBtn.style.display = 'block';
                        
                        // Console visibility state
                        let isConsoleVisible = false;
                        
                        // Store all console logs
                        const consoleLogs = [];
                        
                        // Function to toggle console visibility
                        function toggleConsole() {
                            isConsoleVisible = !isConsoleVisible;
                            if (isConsoleVisible) {
                                consolePanel.style.display = 'flex';
                                showConsoleBtn.style.display = 'none';
                                // Adjust iframe container height
                                const iframeContainer = appIframe.parentElement;
                                if (iframeContainer) {
                                    iframeContainer.style.height = 'calc(100% - 200px)';
                                }
                            } else {
                                consolePanel.style.display = 'none';
                                showConsoleBtn.style.display = 'block';
                                // Restore iframe container height
                                const iframeContainer = appIframe.parentElement;
                                if (iframeContainer) {
                                    iframeContainer.style.height = '100%';
                                }
                            }
                        }
                        
                        // Set up event handlers
                        showConsoleBtn.onclick = toggleConsole;
                        if (toggleConsoleBtn) {
                            toggleConsoleBtn.onclick = toggleConsole;
                        }
                        
                        if (clearConsoleBtn) {
                            clearConsoleBtn.onclick = function() {
                                consoleOutput.innerHTML = '';
                                consoleLogs.length = 0; // Clear the logs array
                            };
                        }
                        
                        if (pipeConsoleBtn) {
                            // Add hover effect
                            pipeConsoleBtn.onmouseover = function() {
                                this.style.color = '#8b5cf6';
                            };
                            pipeConsoleBtn.onmouseout = function() {
                                this.style.color = '#999';
                            };
                            
                            pipeConsoleBtn.onclick = function() {
                                if (consoleLogs.length === 0) {
                                    alert('No console logs to send');
                                    return;
                                }
                                
                                // Format logs for chat
                                let formattedLogs = "```console\n";
                                consoleLogs.forEach(log => {
                                    const typeIcon = {
                                        'error': '❌',
                                        'warn': '⚠️',
                                        'info': 'ℹ️',
                                        'log': '📝'
                                    }[log.type] || '';
                                    
                                    formattedLogs += `${typeIcon} [${log.type.toUpperCase()}] ${log.message}\n`;
                                });
                                formattedLogs += "```";
                                
                                // Get the chat input element
                                const chatInput = document.getElementById('chat-input');
                                if (chatInput) {
                                    // Set the formatted logs as the input value
                                    chatInput.value = `Here are the console logs from the preview:\n\n${formattedLogs}`;
                                    
                                    // Focus the input
                                    chatInput.focus();
                                    
                                    // Optionally scroll to the chat input
                                    chatInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                    
                                    // Add a visual feedback
                                    this.innerHTML = '<i class="fas fa-check"></i> Sent!';
                                    setTimeout(() => {
                                        this.innerHTML = '<i class="fas fa-paper-plane"></i> Send to Chat';
                                    }, 2000);
                                } else {
                                    alert('Could not find chat input');
                                }
                            };
                        }
                        
                        // Function to add log to console
                        function addLog(type, ...args) {
                            const logEntry = document.createElement('div');
                            logEntry.style.marginBottom = '4px';
                            logEntry.style.fontFamily = 'monospace';
                            logEntry.style.fontSize = '12px';
                            
                            // Format the log message
                            const message = args.map(arg => {
                                if (typeof arg === 'object') {
                                    try {
                                        return JSON.stringify(arg, null, 2);
                                    } catch (e) {
                                        return String(arg);
                                    }
                                }
                                return String(arg);
                            }).join(' ');
                            
                            // Store the log
                            consoleLogs.push({
                                type: type,
                                message: message,
                                timestamp: new Date().toISOString()
                            });
                            
                            // Style based on type
                            switch(type) {
                                case 'error':
                                    logEntry.style.color = '#ff6b6b';
                                    logEntry.innerHTML = `<span style="color: #ff4444;">✖</span> ${escapeHtml(message)}`;
                                    break;
                                case 'warn':
                                    logEntry.style.color = '#ffd93d';
                                    logEntry.innerHTML = `<span style="color: #ffaa00;">⚠</span> ${escapeHtml(message)}`;
                                    break;
                                case 'info':
                                    logEntry.style.color = '#6bcfff';
                                    logEntry.innerHTML = `<span style="color: #4444ff;">ℹ</span> ${escapeHtml(message)}`;
                                    break;
                                default:
                                    logEntry.style.color = '#e2e8f0';
                                    logEntry.textContent = message;
                            }
                            
                            consoleOutput.appendChild(logEntry);
                            consoleOutput.scrollTop = consoleOutput.scrollHeight;
                        }
                        
                        // Helper function to escape HTML
                        function escapeHtml(text) {
                            const div = document.createElement('div');
                            div.textContent = text;
                            return div.innerHTML;
                        }
                        
                        // Try to intercept console logs from the iframe
                        try {
                            // Store original console methods
                            const originalLog = appIframe.contentWindow.console.log;
                            const originalError = appIframe.contentWindow.console.error;
                            const originalWarn = appIframe.contentWindow.console.warn;
                            const originalInfo = appIframe.contentWindow.console.info;
                            
                            // Override console methods in iframe
                            appIframe.contentWindow.console.log = function(...args) {
                                addLog('log', ...args);
                                originalLog.apply(this, args);
                            };
                            
                            appIframe.contentWindow.console.error = function(...args) {
                                addLog('error', ...args);
                                originalError.apply(this, args);
                            };
                            
                            appIframe.contentWindow.console.warn = function(...args) {
                                addLog('warn', ...args);
                                originalWarn.apply(this, args);
                            };
                            
                            appIframe.contentWindow.console.info = function(...args) {
                                addLog('info', ...args);
                                originalInfo.apply(this, args);
                            };
                            
                            // Listen for errors in iframe
                            appIframe.contentWindow.addEventListener('error', function(event) {
                                addLog('error', `${event.message} at ${event.filename}:${event.lineno}:${event.colno}`);
                            });
                            
                        } catch (e) {
                            console.warn('[ArtifactsLoader] Cannot intercept iframe console due to cross-origin restrictions');
                            addLog('warn', 'Console interception not available due to cross-origin restrictions');
                        }
                    }
                    
                    // Function to show server not running error
                    function showServerNotRunningError(port) {
                        appLoading.style.display = 'none';
                        appEmpty.style.display = 'block';
                        
                        // Hide URL panel when showing error
                        const urlPanel = document.getElementById('app-url-panel');
                        if (urlPanel) {
                            urlPanel.style.display = 'none';
                        }
                        
                        // Hide console button
                        const showConsoleBtn = document.getElementById('show-console-btn');
                        if (showConsoleBtn) {
                            showConsoleBtn.style.display = 'none';
                        }
                        
                        appEmpty.innerHTML = `
                            <div class="error-state" style="display: flex; flex-direction: column; align-items: center; padding: 2rem;">
                                <div class="error-state-icon">
                                    <i class="fas fa-server" style="font-size: 3rem; color: #ff6b6b; margin-bottom: 1rem;"></i>
                                </div>
                                <div class="error-state-title" style="font-size: 1.2rem; font-weight: 600; margin-bottom: 0.5rem; color: #ff6b6b;">
                                    Server Not Running
                                </div>
                                <div class="error-state-text" style="color: #666; line-height: 1.5; margin-bottom: 1rem;">
                                    The application server on port <strong>${port}</strong> is not accessible.
                                </div>
                                 
                                <div style="margin-top: 1rem;">
                                    <button onclick="window.ArtifactsLoader.checkAndRestartServers(${projectId})" style="background: #007bff; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; margin-right: 0.5rem;">
                                        <i class="fas fa-refresh"></i> Check Again
                                    </button>
                                    <button onclick="window.open('http://localhost:${port}', '_blank')" style="background: #6c757d; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer;">
                                        <i class="fas fa-external-link-alt"></i> Open in New Tab
                                    </button>
                                </div>
                            </div>
                        `;
                    }
                })
                .catch(error => {
                    console.error('[ArtifactsLoader] Error fetching server configs:', error);
                    showErrorState(`Error loading server configurations: ${error.message}. Please try refreshing the page or check if the server is running.`);
                });
                
            // Helper function to show the empty state
            function showEmptyState(message) {
                appLoading.style.display = 'none';
                appEmpty.style.display = 'block';
                appEmpty.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">
                            <i class="fas fa-server" style="font-size: 3rem; color: #666; margin-bottom: 1rem;"></i>
                        </div>
                        <div class="empty-state-title" style="font-size: 1.2rem; font-weight: 600; margin-bottom: 0.5rem; color: #333;">
                            No Application Server Running
                        </div>
                        <div class="empty-state-text" style="color: #666; line-height: 1.5; white-space: pre-line;">
                            ${message}
                        </div>
                    </div>
                `;
            }
            
            // Helper function to show error state
            function showErrorState(message) {
                appLoading.style.display = 'none';
                appEmpty.style.display = 'block';
                
                // Hide URL panel when showing error
                const urlPanel = document.getElementById('app-url-panel');
                if (urlPanel) {
                    urlPanel.style.display = 'none';
                }
                
                // Hide console button
                const showConsoleBtn = document.getElementById('show-console-btn');
                if (showConsoleBtn) {
                    showConsoleBtn.style.display = 'none';
                }
                
                appEmpty.innerHTML = `
                    <div class="error-state">
                        <div class="error-state-icon">
                            <i class="fas fa-exclamation-triangle" style="font-size: 3rem; color: #ff6b6b; margin-bottom: 1rem;"></i>
                        </div>
                        <div class="error-state-title" style="font-size: 1.2rem; font-weight: 600; margin-bottom: 0.5rem; color: #ff6b6b;">
                            Server Connection Failed
                        </div>
                        <div class="error-state-text" style="color: #666; line-height: 1.5; white-space: pre-line;">
                            ${message}
                        </div>
                        <div style="margin-top: 1rem;">
                            <button onclick="window.ArtifactsLoader.loadAppPreview(${projectId})" style="background: #007bff; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer;">
                                <i class="fas fa-refresh"></i> Try Again
                            </button>
                        </div>
                    </div>
                `;
            }
        },

        /**
         * Check server status and restart if needed
         * @param {number} projectId - The ID of the current project
         */
        checkAndRestartServers: function(projectId) {
            console.log(`[ArtifactsLoader] checkAndRestartServers called with project ID: ${projectId}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for checking servers');
                return;
            }
            
            // Get app tab elements
            const appLoading = document.getElementById('app-loading');
            const appEmpty = document.getElementById('app-empty');
            const appFrameContainer = document.getElementById('app-frame-container');
            
            if (!appLoading || !appEmpty || !appFrameContainer) {
                console.warn('[ArtifactsLoader] One or more app tab elements not found');
                return;
            }
            
            // Show loading state
            appEmpty.style.display = 'none';
            appFrameContainer.style.display = 'none';
            appLoading.style.display = 'block';
            
            // Update loading message to indicate server check
            appLoading.innerHTML = '<div class="spinner"></div><div>Checking and restarting servers...</div>';
            
            // Call the new check servers API
            const url = `/projects/${projectId}/api/check-servers/`;
            console.log(`[ArtifactsLoader] Calling server check API: ${url}`);
            
            fetch(url, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                }
            })
            .then(response => {
                console.log(`[ArtifactsLoader] Server check API response received, status: ${response.status}`);
                if (!response.ok) {
                    throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                }
                return response.json();
            })
            .then(data => {
                console.log('[ArtifactsLoader] Server check API data received:', data);
                
                // Check the overall status
                if (data.status === 'all_running') {
                    // All servers are running, reload the app preview
                    console.log('[ArtifactsLoader] All servers running, reloading app preview');
                    setTimeout(() => {
                        this.loadAppPreview(projectId);
                    }, 1000); // Small delay to ensure servers are fully ready
                } else if (data.status === 'partial_running') {
                    // Some servers are running
                    this.showServerCheckResult(data, projectId);
                } else {
                    // Show error or status information
                    this.showServerCheckResult(data, projectId);
                }
            })
            .catch(error => {
                console.error('[ArtifactsLoader] Error checking servers:', error);
                appLoading.style.display = 'none';
                appEmpty.style.display = 'block';
                appEmpty.innerHTML = `
                    <div class="error-state">
                        <div class="error-state-icon">
                            <i class="fas fa-exclamation-triangle" style="font-size: 3rem; color: #ff6b6b; margin-bottom: 1rem;"></i>
                        </div>
                        <div class="error-state-title" style="font-size: 1.2rem; font-weight: 600; margin-bottom: 0.5rem; color: #ff6b6b;">
                            Server Check Failed
                        </div>
                        <div class="error-state-text" style="color: #666; line-height: 1.5; margin-bottom: 1rem;">
                            Error checking server status: ${error.message}
                        </div>
                        <div style="margin-top: 1rem;">
                            <button onclick="window.ArtifactsLoader.checkAndRestartServers(${projectId})" style="background: #007bff; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer;">
                                <i class="fas fa-refresh"></i> Try Again
                            </button>
                        </div>
                    </div>
                `;
            });
        },

        /**
         * Show server check results
         * @param {object} data - Server check result data
         * @param {number} projectId - The project ID
         */
        showServerCheckResult: function(data, projectId) {
            const appLoading = document.getElementById('app-loading');
            const appEmpty = document.getElementById('app-empty');
            
            appLoading.style.display = 'none';
            appEmpty.style.display = 'block';
            
            let statusIcon = 'fas fa-server';
            let statusColor = '#666';
            let statusTitle = 'Server Status';
            
            if (data.status === 'all_running') {
                statusIcon = 'fas fa-check-circle';
                statusColor = '#28a745';
                statusTitle = 'All Servers Running';
            } else if (data.status === 'partial_running') {
                statusIcon = 'fas fa-exclamation-triangle';
                statusColor = '#ffc107';
                statusTitle = 'Some Servers Running';
            } else if (data.status === 'none_running') {
                statusIcon = 'fas fa-times-circle';
                statusColor = '#dc3545';
                statusTitle = 'No Servers Running';
            } else if (data.status === 'error') {
                statusIcon = 'fas fa-exclamation-triangle';
                statusColor = '#dc3545';
                statusTitle = 'Server Check Error';
            }
            
            let serversHtml = '';
            if (data.servers && data.servers.length > 0) {
                serversHtml = '<div style="margin-top: 1rem; text-align: left;">';
                data.servers.forEach(server => {
                    let serverStatusColor = '#666';
                    let serverStatusIcon = 'fas fa-circle';
                    
                    switch(server.status) {
                        case 'running':
                            serverStatusColor = '#28a745';
                            serverStatusIcon = 'fas fa-check-circle';
                            break;
                        case 'restarted':
                            serverStatusColor = '#17a2b8';
                            serverStatusIcon = 'fas fa-sync';
                            break;
                        case 'failed':
                            serverStatusColor = '#dc3545';
                            serverStatusIcon = 'fas fa-times-circle';
                            break;
                        case 'no_command':
                            serverStatusColor = '#ffc107';
                            serverStatusIcon = 'fas fa-exclamation-circle';
                            break;
                    }
                    
                    serversHtml += `
                        <div style="margin-bottom: 0.5rem; padding: 0.5rem; background: #f8f9fa; border-radius: 4px;">
                            <div style="display: flex; align-items: center; margin-bottom: 0.25rem;">
                                <i class="${serverStatusIcon}" style="color: ${serverStatusColor}; margin-right: 0.5rem;"></i>
                                <strong>${server.type.charAt(0).toUpperCase() + server.type.slice(1)} Server (Port ${server.port})</strong>
                            </div>
                            <div style="color: #666; font-size: 0.9rem;">
                                ${server.message}
                            </div>
                            ${server.status === 'running' || server.status === 'restarted' ? 
                                `<div style="margin-top: 0.25rem;">
                                    <a href="${server.url}" target="_blank" style="color: #007bff; text-decoration: none; font-size: 0.9rem;">
                                        <i class="fas fa-external-link-alt"></i> Open ${server.url}
                                    </a>
                                </div>` : ''
                            }
                        </div>
                    `;
                });
                serversHtml += '</div>';
            }
            
            appEmpty.innerHTML = `
                <div class="server-status-state" style="display: flex; flex-direction: column; align-items: center; padding: 2rem;">
                    <div class="status-icon">
                        <i class="${statusIcon}" style="font-size: 3rem; color: ${statusColor}; margin-bottom: 1rem;"></i>
                    </div>
                    <div class="status-title" style="font-size: 1.2rem; font-weight: 600; margin-bottom: 0.5rem; color: ${statusColor};">
                        ${statusTitle}
                    </div>
                    <div class="status-message" style="color: #666; line-height: 1.5; margin-bottom: 1rem; text-align: center;">
                        ${data.message}
                    </div>
                    ${serversHtml}
                    <div style="margin-top: 1rem;">
                        <button onclick="window.ArtifactsLoader.checkAndRestartServers(${projectId})" style="background: #007bff; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; margin-right: 0.5rem;">
                            <i class="fas fa-refresh"></i> Check Again
                        </button>
                        ${data.status === 'all_running' || data.status === 'partial_running' ? 
                            `<button onclick="window.ArtifactsLoader.loadAppPreview(${projectId})" style="background: #28a745; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer;">
                                <i class="fas fa-eye"></i> View App
                            </button>` : ''
                        }
                    </div>
                </div>
            `;
        },

        /**
         * Load Tool Call History for a project
         * @param {number} projectId - The project ID
         */
        loadToolHistory: function(projectId) {
            console.log(`[ArtifactsLoader] Loading tool history for project ${projectId}`);
            
            const toolhistoryContainer = document.getElementById('toolhistory');
            const toolhistoryLoading = document.getElementById('toolhistory-loading');
            const toolhistoryEmpty = document.getElementById('toolhistory-empty');
            const toolhistoryList = document.getElementById('toolhistory-list');
            const toolFilter = document.getElementById('tool-filter');
            const refreshButton = document.getElementById('refresh-toolhistory');
            
            if (!toolhistoryContainer || !toolhistoryLoading || !toolhistoryEmpty || !toolhistoryList) {
                console.error('[ArtifactsLoader] Tool history UI elements not found');
                return;
            }
            
            // Function to fetch and display tool history
            const fetchToolHistory = (filterValue = '') => {
                // Show loading state
                toolhistoryLoading.style.display = 'block';
                toolhistoryEmpty.style.display = 'none';
                toolhistoryList.style.display = 'none';
                
                let url = `/projects/${projectId}/api/tool-call-history/`;
                if (filterValue) {
                    url += `?tool_name=${encodeURIComponent(filterValue)}`;
                }
                
                fetch(url, {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken(),
                    }
                })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    toolhistoryLoading.style.display = 'none';
                    
                    if (data.tool_call_history && data.tool_call_history.length > 0) {
                        toolhistoryList.style.display = 'block';
                        toolhistoryEmpty.style.display = 'none';
                        
                        // Build the HTML for tool history items
                        let html = '';
                        data.tool_call_history.forEach(item => {
                            const date = new Date(item.created_at);
                            const formattedDate = date.toLocaleString();
                            const hasError = item.metadata && item.metadata.has_error;
                            
                            html += `
                                <div class="tool-history-item" style="background: #2a2a2a; border: 1px solid #333; border-radius: 8px; padding: 15px; margin-bottom: 15px;">
                                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                        <h4 style="margin: 0; color: ${hasError ? '#ff6b6b' : '#8b5cf6'};">
                                            <i class="fas ${hasError ? 'fa-exclamation-circle' : 'fa-tools'}"></i> ${item.tool_name}
                                        </h4>
                                        <span style="color: #666; font-size: 0.875rem;">${formattedDate}</span>
                                    </div>
                                    ${item.tool_input && Object.keys(item.tool_input).length > 0 ? `
                                        <div style="margin-bottom: 10px;">
                                            <strong style="color: #999;">Input:</strong>
                                            <pre style="background: #1a1a1a; padding: 10px; border-radius: 4px; overflow-x: auto; margin-top: 5px; font-size: 0.875rem;">${JSON.stringify(item.tool_input, null, 2)}</pre>
                                        </div>
                                    ` : ''}
                                    <div>
                                        <strong style="color: #999;">Generated Content:</strong>
                                        <div style="background: #1a1a1a; padding: 10px; border-radius: 4px; margin-top: 5px; max-height: 300px; overflow-y: auto;">
                                            <pre style="white-space: pre-wrap; margin: 0; font-size: 0.875rem;">${item.generated_content}</pre>
                                        </div>
                                    </div>
                                </div>
                            `;
                        });
                        
                        toolhistoryList.innerHTML = html;
                        
                        // Add "Load More" button if there are more items
                        if (data.has_more) {
                            toolhistoryList.innerHTML += `
                                <div style="text-align: center; margin-top: 20px;">
                                    <button id="load-more-toolhistory" class="btn btn-primary" style="background: #8b5cf6; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer;">
                                        Load More
                                    </button>
                                </div>
                            `;
                            
                            // Add event listener for load more button
                            const loadMoreBtn = document.getElementById('load-more-toolhistory');
                            if (loadMoreBtn) {
                                loadMoreBtn.addEventListener('click', () => {
                                    const newOffset = data.offset + data.limit;
                                    fetchToolHistory(filterValue, newOffset);
                                });
                            }
                        }
                    } else {
                        toolhistoryList.style.display = 'none';
                        toolhistoryEmpty.style.display = 'block';
                    }
                })
                .catch(error => {
                    console.error('[ArtifactsLoader] Error loading tool history:', error);
                    toolhistoryLoading.style.display = 'none';
                    toolhistoryEmpty.style.display = 'block';
                    toolhistoryEmpty.innerHTML = `
                        <div class="empty-state-icon">
                            <i class="fas fa-exclamation-triangle"></i>
                        </div>
                        <div class="empty-state-text">
                            Error loading tool history: ${error.message}
                        </div>
                    `;
                });
            };
            
            // Initial load
            fetchToolHistory();
            
            // Add event listeners
            if (toolFilter) {
                let filterTimeout;
                toolFilter.addEventListener('input', (e) => {
                    clearTimeout(filterTimeout);
                    filterTimeout = setTimeout(() => {
                        fetchToolHistory(e.target.value);
                    }, 300);
                });
            }
            
            if (refreshButton) {
                refreshButton.addEventListener('click', () => {
                    fetchToolHistory(toolFilter ? toolFilter.value : '');
                });
            }
        },
        
        /**
         * Add a pending tool call to the history immediately
         * @param {string} toolName - The name of the tool being called
         * @param {object} toolInput - The input parameters for the tool
         * @returns {string} - The ID of the pending element
         */
        addPendingToolCall: function(toolName, toolInput) {
            console.log(`[ArtifactsLoader] Adding pending tool call: ${toolName}`);
            
            const toolhistoryList = document.getElementById('toolhistory-list');
            const toolhistoryEmpty = document.getElementById('toolhistory-empty');
            
            if (!toolhistoryList) {
                console.warn('[ArtifactsLoader] Tool history list not found');
                return;
            }
            
            // Hide empty state
            if (toolhistoryEmpty) {
                toolhistoryEmpty.style.display = 'none';
            }
            
            // Make sure list is visible
            toolhistoryList.style.display = 'block';
            
            // Create a unique ID for this pending call
            const pendingId = `pending-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
            
            // Create the pending tool call HTML
            const pendingHtml = `
                <div id="${pendingId}" class="tool-history-item pending-tool-call" style="background: #2a2a2a; border: 1px solid #666; border-radius: 8px; padding: 15px; margin-bottom: 15px; opacity: 0.8;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                        <h4 style="margin: 0; color: #fbbf24;">
                            <i class="fas fa-spinner fa-spin"></i> ${toolName}
                        </h4>
                        <span style="color: #666; font-size: 0.875rem;">Executing...</span>
                    </div>
                    ${toolInput && Object.keys(toolInput).length > 0 ? `
                        <div style="margin-bottom: 10px;">
                            <strong style="color: #999;">Input:</strong>
                            <pre style="background: #1a1a1a; padding: 10px; border-radius: 4px; overflow-x: auto; margin-top: 5px; font-size: 0.875rem;">${JSON.stringify(toolInput, null, 2)}</pre>
                        </div>
                    ` : ''}
                    <div>
                        <strong style="color: #999;">Generated Content:</strong>
                        <div style="background: #1a1a1a; padding: 10px; border-radius: 4px; margin-top: 5px;">
                            <div style="color: #666; font-style: italic;">
                                <i class="fas fa-hourglass-half"></i> Waiting for response...
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            // Prepend to the list
            toolhistoryList.insertAdjacentHTML('afterbegin', pendingHtml);
            
            // Return the pending ID so it can be updated later
            return pendingId;
        },
        
        /**
         * Execute a ticket by sending a command to build the feature
         * @param {number} ticketId - The ID of the ticket to execute
         */
        executeTicket: function(ticketId) {
            console.log(`[ArtifactsLoader] Executing ticket ${ticketId}`);
            
            // Find the ticket data
            const projectId = this.getCurrentProjectId();
            if (!projectId) {
                console.error('[ArtifactsLoader] No project ID found');
                alert('Unable to execute ticket: No project ID found');
                return;
            }
            
            // Get ticket details from the stored tickets data
            fetch(`/projects/${projectId}/api/checklist/`)
                .then(response => response.json())
                .then(data => {
                    const tickets = data.checklist || [];
                    const ticket = tickets.find(t => t.id == ticketId);
                    
                    if (!ticket) {
                        console.error('[ArtifactsLoader] Ticket not found:', ticketId);
                        alert('Unable to execute ticket: Ticket not found');
                        return;
                    }
                    
                    // Construct the command to send
                    let command = `Build the following feature from ticket #${ticket.id}: "${ticket.name}"\n\n`;
                    command += `Description: ${ticket.description}\n\n`;
                    
                    if (ticket.details && Object.keys(ticket.details).length > 0) {
                        command += `Technical Details:\n${JSON.stringify(ticket.details, null, 2)}\n\n`;
                    }
                    
                    if (ticket.acceptance_criteria && ticket.acceptance_criteria.length > 0) {
                        command += `Acceptance Criteria:\n`;
                        ticket.acceptance_criteria.forEach(criteria => {
                            command += `- ${criteria}\n`;
                        });
                        command += `\n`;
                    }
                    
                    command += `Please implement this feature following the specifications above.`;
                    
                    // Close the ticket drawer
                    const detailsDrawer = document.getElementById('ticket-details-drawer');
                    const drawerOverlay = document.getElementById('drawer-overlay');
                    if (detailsDrawer) detailsDrawer.classList.remove('open');
                    if (drawerOverlay) drawerOverlay.classList.remove('active');
                    
                    // Send the command to the chat
                    if (window.sendMessage && typeof window.sendMessage === 'function') {
                        console.log('[ArtifactsLoader] Sending ticket execution command to chat');
                        window.sendMessage(command);
                    } else {
                        // Fallback: try to find the chat input and trigger send
                        const chatInput = document.getElementById('chat-input');
                        const sendButton = document.getElementById('send-btn');
                        
                        if (chatInput && sendButton) {
                            chatInput.value = command;
                            // Trigger input event to update any listeners
                            chatInput.dispatchEvent(new Event('input', { bubbles: true }));
                            // Click the send button
                            sendButton.click();
                        } else {
                            console.error('[ArtifactsLoader] Unable to send message - no chat interface found');
                            alert('Unable to send command to chat. Please copy the command manually.');
                        }
                    }
                })
                .catch(error => {
                    console.error('[ArtifactsLoader] Error fetching ticket details:', error);
                    alert('Error executing ticket: ' + error.message);
                });
        },
        
        /**
         * Download PRD content as PDF
         * @param {number} projectId - The ID of the current project
         * @param {string} title - The title of the PRD document
         * @param {string} content - The markdown content of the PRD
         */
        downloadPRDAsPDF: function(projectId, title, content) {
            console.log('[ArtifactsLoader] downloadPRDAsPDF called');
            
            // Check if jsPDF is available
            if (typeof window.jspdf === 'undefined' || typeof window.jspdf.jsPDF === 'undefined') {
                console.error('[ArtifactsLoader] jsPDF library not loaded');
                alert('PDF generation library not loaded. Please refresh the page and try again.');
                return;
            }
            
            // Create progress indicator
            const progressOverlay = document.createElement('div');
            progressOverlay.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 10000;
            `;
            
            const progressContent = document.createElement('div');
            progressContent.style.cssText = `
                background: white;
                padding: 30px;
                border-radius: 8px;
                text-align: center;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            `;
            progressContent.innerHTML = `
                <div style="margin-bottom: 15px;">
                    <div class="spinner" style="border: 3px solid #f3f3f3; border-top: 3px solid #3498db; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto;"></div>
                </div>
                <div style="color: #333; font-family: Arial, sans-serif;">Generating PDF...</div>
            `;
            
            // Add spinner animation
            const style = document.createElement('style');
            style.textContent = `
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            `;
            document.head.appendChild(style);
            
            progressOverlay.appendChild(progressContent);
            document.body.appendChild(progressOverlay);
            
            // Use setTimeout to allow the progress indicator to render
            setTimeout(() => {
                try {
                    // Initialize jsPDF
                    const { jsPDF } = window.jspdf;
                    const doc = new jsPDF({
                        orientation: 'portrait',
                        unit: 'mm',
                        format: 'a4'
                    });
                    
                    // Parse markdown to plain text and HTML structure
                    const htmlContent = typeof marked !== 'undefined' ? marked.parse(content) : content;
                    
                    // Create temporary div to parse HTML
                    const tempDiv = document.createElement('div');
                    tempDiv.innerHTML = htmlContent;
                    
                    // Define margins and spacing
                    const leftMargin = 20;
                    const rightMargin = 20;
                    const topMargin = 25;  // Header space
                    const bottomMargin = 20;  // Footer space  
                    const pageWidth = 210 - leftMargin - rightMargin;
                    const pageHeight = 297;
                    const maxY = pageHeight - bottomMargin;
                    let currentY = topMargin;
                    let pageNumber = 1;
                    
                    // Function to check if we need a new page
                    const checkNewPage = (additionalHeight = 10) => {
                        if (currentY + additionalHeight > maxY) {
                            addPageNumber();
                            doc.addPage();
                            currentY = topMargin;
                            pageNumber++;
                            return true;
                        }
                        return false;
                    };
                    
                    // Function to add page number
                    const addPageNumber = () => {
                        doc.setFontSize(10);
                        doc.setTextColor(100, 100, 100);
                        const pageNumText = `Page ${pageNumber}`;
                        const textWidth = doc.getTextWidth(pageNumText);
                        doc.text(pageNumText, (210 - textWidth) / 2, pageHeight - 10);
                        doc.setTextColor(0, 0, 0); // Reset to black
                    };
                    
                    // Add title
                    doc.setFont('helvetica', 'bold');
                    doc.setFontSize(24);
                    doc.setTextColor(0, 0, 0);
                    const titleLines = doc.splitTextToSize(title, pageWidth);
                    titleLines.forEach(line => {
                        checkNewPage();
                        doc.text(line, leftMargin, currentY);
                        currentY += 10;
                    });
                    currentY += 15; // Extra space after title
                    
                    // Process content
                    const processNode = (node) => {
                        if (node.nodeType === Node.TEXT_NODE) {
                            const text = node.textContent.trim();
                            if (text) {
                                doc.setFont('helvetica', 'normal');
                                doc.setFontSize(11);
                                const lines = doc.splitTextToSize(text, pageWidth);
                                lines.forEach(line => {
                                    checkNewPage();
                                    doc.text(line, leftMargin, currentY);
                                    currentY += 6;
                                });
                            }
                        } else if (node.nodeType === Node.ELEMENT_NODE) {
                            const tagName = node.tagName.toLowerCase();
                            
                            switch (tagName) {
                                case 'h1':
                                case 'h2':
                                case 'h3':
                                case 'h4':
                                case 'h5':
                                case 'h6':
                                    currentY += 8; // Space before heading
                                    const headingSize = 20 - (parseInt(tagName.charAt(1)) * 2);
                                    doc.setFont('helvetica', 'bold');
                                    doc.setFontSize(headingSize);
                                    const headingLines = doc.splitTextToSize(node.textContent.trim(), pageWidth);
                                    headingLines.forEach(line => {
                                        checkNewPage();
                                        doc.text(line, leftMargin, currentY);
                                        currentY += headingSize * 0.4;
                                    });
                                    currentY += 6; // Space after heading
                                    doc.setFont('helvetica', 'normal');
                                    break;
                                    
                                case 'p':
                                    node.childNodes.forEach(child => processNode(child));
                                    currentY += 8; // Paragraph spacing
                                    break;
                                    
                                case 'ul':
                                case 'ol':
                                    currentY += 4; // Space before list
                                    Array.from(node.children).forEach((li, index) => {
                                        checkNewPage();
                                        const bullet = tagName === 'ol' ? `${index + 1}. ` : '• ';
                                        doc.setFont('helvetica', 'normal');
                                        doc.setFontSize(11);
                                        const text = li.textContent.trim();
                                        const bulletWidth = doc.getTextWidth(bullet);
                                        
                                        // Add bullet
                                        doc.text(bullet, leftMargin + 5, currentY);
                                        
                                        // Add text with indent
                                        const lines = doc.splitTextToSize(text, pageWidth - 10);
                                        lines.forEach((line, lineIndex) => {
                                            if (lineIndex > 0) {
                                                checkNewPage();
                                            }
                                            doc.text(line, leftMargin + 5 + bulletWidth, currentY);
                                            currentY += 6;
                                        });
                                        currentY += 2; // Space between list items
                                    });
                                    currentY += 4; // Space after list
                                    break;
                                    
                                case 'br':
                                    currentY += 6;
                                    break;
                                    
                                case 'strong':
                                case 'b':
                                    doc.setFont('helvetica', 'bold');
                                    node.childNodes.forEach(child => processNode(child));
                                    doc.setFont('helvetica', 'normal');
                                    break;
                                    
                                case 'em':
                                case 'i':
                                    doc.setFont('helvetica', 'italic');
                                    node.childNodes.forEach(child => processNode(child));
                                    doc.setFont('helvetica', 'normal');
                                    break;
                                    
                                case 'code':
                                    doc.setFont('courier', 'normal');
                                    doc.setFontSize(10);
                                    const codeText = node.textContent.trim();
                                    const codeLines = doc.splitTextToSize(codeText, pageWidth - 10);
                                    codeLines.forEach(line => {
                                        checkNewPage();
                                        doc.text(line, leftMargin + 5, currentY);
                                        currentY += 5;
                                    });
                                    doc.setFont('helvetica', 'normal');
                                    doc.setFontSize(11);
                                    break;
                                    
                                case 'pre':
                                    currentY += 4;
                                    doc.setFont('courier', 'normal');
                                    doc.setFontSize(9);
                                    const preText = node.textContent;
                                    const preLines = preText.split('\n');
                                    preLines.forEach(line => {
                                        const wrappedLines = doc.splitTextToSize(line || ' ', pageWidth - 10);
                                        wrappedLines.forEach(wrappedLine => {
                                            checkNewPage();
                                            doc.text(wrappedLine, leftMargin + 5, currentY);
                                            currentY += 5;
                                        });
                                    });
                                    doc.setFont('helvetica', 'normal');
                                    doc.setFontSize(11);
                                    currentY += 4;
                                    break;
                                    
                                default:
                                    // Process children for other elements
                                    node.childNodes.forEach(child => processNode(child));
                            }
                        }
                    };
                    
                    // Process all content nodes
                    tempDiv.childNodes.forEach(node => processNode(node));
                    
                    // Add page number to last page
                    addPageNumber();
                    
                    // Remove progress indicator
                    document.body.removeChild(progressOverlay);
                    document.head.removeChild(style);
                    
                    // Save the PDF
                    const fileName = `${title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_prd.pdf`;
                    doc.save(fileName);
                    
                } catch (error) {
                    console.error('[ArtifactsLoader] Error generating PDF:', error);
                    alert('Error generating PDF: ' + error.message);
                    
                    // Clean up
                    if (progressOverlay.parentNode) {
                        document.body.removeChild(progressOverlay);
                    }
                    if (style.parentNode) {
                        document.head.removeChild(style);
                    }
                }
            }, 100); // Small delay to show progress indicator
        },

        copyToClipboard: function(text, contentType) {
            if (!text) {
                console.error('No text to copy');
                return;
            }

            // Use the Clipboard API if available
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text)
                    .then(() => {
                        // Show success message
                        const message = document.createElement('div');
                        message.style.cssText = `
                            position: fixed;
                            top: 20px;
                            right: 20px;
                            background: #28a745;
                            color: white;
                            padding: 12px 20px;
                            border-radius: 4px;
                            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
                            z-index: 10000;
                            font-size: 14px;
                            animation: slideIn 0.3s ease-out;
                        `;
                        message.textContent = `${contentType || 'Content'} copied to clipboard!`;
                        document.body.appendChild(message);

                        // Remove the message after 3 seconds
                        setTimeout(() => {
                            message.style.animation = 'slideOut 0.3s ease-out';
                            setTimeout(() => document.body.removeChild(message), 300);
                        }, 3000);
                    })
                    .catch(err => {
                        console.error('Failed to copy text: ', err);
                        alert('Failed to copy to clipboard. Please try again.');
                    });
            } else {
                // Fallback for older browsers
                const textArea = document.createElement('textarea');
                textArea.value = text;
                textArea.style.position = 'fixed';
                textArea.style.left = '-9999px';
                document.body.appendChild(textArea);
                textArea.select();
                
                try {
                    document.execCommand('copy');
                    alert(`${contentType || 'Content'} copied to clipboard!`);
                } catch (err) {
                    console.error('Fallback copy failed: ', err);
                    alert('Failed to copy to clipboard. Please try again.');
                }
                
                document.body.removeChild(textArea);
            }
        },
        
        /**
         * Load File Browser for a project
         * @param {number} projectId - The project ID
         */
        loadFileBrowser: function(projectId) {
            console.log(`[ArtifactsLoader] Loading file browser for project ${projectId}`);
            
            // Store project ID for use in file operations
            window.currentFileBrowserProjectId = projectId;
            
            const fileBrowserContainer = document.getElementById('filebrowser');
            const fileBrowserMain = document.getElementById('filebrowser-main');
            const fileBrowserViewer = document.getElementById('filebrowser-viewer');
            const fileBrowserLoading = document.getElementById('filebrowser-loading');
            const fileBrowserEmpty = document.getElementById('filebrowser-empty');
            const fileBrowserList = document.getElementById('filebrowser-list');
            const fileBrowserPagination = document.getElementById('filebrowser-pagination');
            const fileSearch = document.getElementById('file-search');
            const fileTypeFilter = document.getElementById('file-type-filter');
            const refreshButton = document.getElementById('refresh-filebrowser');
            
            // Viewer elements
            const viewerBack = document.getElementById('viewer-back');
            const viewerTitle = document.getElementById('viewer-title');
            const viewerCopy = document.getElementById('viewer-copy');
            const viewerDelete = document.getElementById('viewer-delete');
            const viewerMarkdown = document.getElementById('viewer-markdown');
            
            if (!fileBrowserContainer || !fileBrowserLoading || !fileBrowserEmpty || !fileBrowserList) {
                console.error('[ArtifactsLoader] File browser UI elements not found', {
                    container: !!fileBrowserContainer,
                    loading: !!fileBrowserLoading,
                    empty: !!fileBrowserEmpty,
                    list: !!fileBrowserList
                });
                return;
            }
            
            let currentPage = 1;
            let currentSearch = '';
            let currentType = '';
            let currentSort = 'updated_at';
            let currentOrder = 'desc';
            let searchTimeout = null;
            
            // Function to fetch and display files
            const fetchFiles = (page = 1) => {
                // Show loading state
                fileBrowserLoading.style.display = 'block';
                fileBrowserEmpty.style.display = 'none';
                fileBrowserList.style.display = 'none';
                fileBrowserPagination.style.display = 'none';
                
                const params = new URLSearchParams({
                    page: page,
                    per_page: 10,
                    search: currentSearch,
                    type: currentType,
                    sort: currentSort,
                    order: currentOrder
                });
                
                fetch(`/projects/${projectId}/api/files/browser/?${params}`, {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken(),
                    }
                })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    fileBrowserLoading.style.display = 'none';
                    
                    // Update filter options if first load
                    if (page === 1 && data.filters && data.filters.types) {
                        updateTypeFilterOptions(data.filters.types);
                    }
                    
                    if (data.files && data.files.length > 0) {
                        fileBrowserList.style.display = 'block';
                        fileBrowserEmpty.style.display = 'none';
                        const tableHeader = document.getElementById('file-table-header');
                        if (tableHeader) {
                            tableHeader.style.display = 'grid';
                        } else {
                            console.error('[FileBrowser] Table header element not found');
                        }
                        
                        // Clear the list first
                        fileBrowserList.innerHTML = '';
                        
                        // Create file items with table-like layout
                        data.files.forEach(file => {
                            const icon = getFileIcon(file.type);
                            const typeClass = `file-type-${file.type}`;
                            
                            // Create the main container
                            const fileItem = document.createElement('div');
                            fileItem.className = `file-list-item ${typeClass}`;
                            fileItem.dataset.fileId = file.id;
                            
                            // Create icon
                            const fileIcon = document.createElement('div');
                            fileIcon.className = 'file-icon';
                            fileIcon.innerHTML = `<i class="${icon}"></i>`;
                            
                            // Create name element
                            const fileName = document.createElement('div');
                            fileName.className = 'file-name';
                            fileName.textContent = file.name || file.type_display || 'Unnamed File';
                            
                            // Create type cell with badge
                            const fileType = document.createElement('div');
                            fileType.className = 'file-type-cell';
                            const typeBadge = document.createElement('span');
                            typeBadge.className = 'file-type-badge';
                            // Use the raw type if type_display is not available
                            const displayType = file.type_display || file.type || 'Unknown';
                            typeBadge.textContent = displayType;
                            fileType.appendChild(typeBadge);
                            
                            // Create owner cell
                            const fileOwner = document.createElement('div');
                            fileOwner.className = 'file-owner-cell';
                            fileOwner.textContent = file.owner || 'System';
                            
                            // Create date cell
                            const fileDate = document.createElement('div');
                            fileDate.className = 'file-date-cell';
                            fileDate.textContent = formatRelativeTime(file.updated_at);
                            
                            // Create size cell
                            const fileSize = document.createElement('div');
                            fileSize.className = 'file-size-cell';
                            fileSize.textContent = file.size_display || '0 B';
                            
                            // Assemble the structure
                            fileItem.appendChild(fileIcon);
                            fileItem.appendChild(fileName);
                            fileItem.appendChild(fileType);
                            fileItem.appendChild(fileOwner);
                            fileItem.appendChild(fileDate);
                            fileItem.appendChild(fileSize);
                            
                            // Add to list
                            fileBrowserList.appendChild(fileItem);
                        });
                        
                        // Show pagination if needed
                        if (data.pagination && data.pagination.pages > 1) {
                            fileBrowserPagination.style.display = 'block';
                            fileBrowserPagination.innerHTML = buildPaginationHTML(data.pagination);
                            attachPaginationListeners();
                        } else {
                            fileBrowserPagination.style.display = 'none';
                        }
                        
                        // Attach event listeners to file items
                        attachFileItemListeners();
                        
                    } else {
                        fileBrowserList.style.display = 'none';
                        fileBrowserEmpty.style.display = 'block';
                        fileBrowserPagination.style.display = 'none';
                        document.getElementById('file-table-header').style.display = 'none';
                    }
                })
                .catch(error => {
                    console.error('[ArtifactsLoader] Error loading file browser:', error);
                    fileBrowserLoading.style.display = 'none';
                    fileBrowserEmpty.style.display = 'block';
                    showToast('Failed to load files', 'error');
                });
            };
            
            // Helper function to get file icon based on type
            const getFileIcon = (type) => {
                const icons = {
                    'prd': 'fas fa-file-alt',
                    'implementation': 'fas fa-code',
                    'design': 'fas fa-palette',
                    'test': 'fas fa-vial',
                    'other': 'fas fa-file'
                };
                return icons[type] || icons.other;
            };
            
            // Helper function to escape HTML
            const escapeHtml = (text) => {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            };
            
            // Helper function to format relative time
            const formatRelativeTime = (dateString) => {
                const date = new Date(dateString);
                const now = new Date();
                const diff = now - date;
                const minutes = Math.floor(diff / 60000);
                const hours = Math.floor(minutes / 60);
                const days = Math.floor(hours / 24);
                
                if (days > 0) return `${days}d ago`;
                if (hours > 0) return `${hours}h ago`;
                if (minutes > 0) return `${minutes}m ago`;
                return 'just now';
            };
            
            // Update type filter options
            const updateTypeFilterOptions = (types) => {
                let html = '<option value="">All Types</option>';
                Object.keys(types).forEach(type => {
                    html += `<option value="${type}">${types[type].name} (${types[type].count})</option>`;
                });
                fileTypeFilter.innerHTML = html;
            };
            
            // Build pagination HTML
            const buildPaginationHTML = (pagination) => {
                let html = '<div class="pagination-controls">';
                
                // Previous button
                html += `<button class="pagination-btn" data-page="${pagination.page - 1}" ${!pagination.has_previous ? 'disabled' : ''}>
                    <i class="fas fa-chevron-left"></i>
                </button>`;
                
                // Page numbers
                const maxPages = 5;
                let startPage = Math.max(1, pagination.page - Math.floor(maxPages / 2));
                let endPage = Math.min(pagination.pages, startPage + maxPages - 1);
                
                if (endPage - startPage < maxPages - 1) {
                    startPage = Math.max(1, endPage - maxPages + 1);
                }
                
                for (let i = startPage; i <= endPage; i++) {
                    html += `<button class="pagination-btn ${i === pagination.page ? 'active' : ''}" data-page="${i}">${i}</button>`;
                }
                
                // Next button
                html += `<button class="pagination-btn" data-page="${pagination.page + 1}" ${!pagination.has_next ? 'disabled' : ''}>
                    <i class="fas fa-chevron-right"></i>
                </button>`;
                
                html += `<span class="pagination-info">${pagination.total} files</span>`;
                html += '</div>';
                
                return html;
            };
            
            // Attach pagination event listeners
            const attachPaginationListeners = () => {
                document.querySelectorAll('.pagination-btn').forEach(btn => {
                    btn.addEventListener('click', function() {
                        if (!this.disabled) {
                            currentPage = parseInt(this.dataset.page);
                            fetchFiles(currentPage);
                        }
                    });
                });
            };
            
            // Attach file item event listeners
            const attachFileItemListeners = () => {
                // Click on file item to view
                document.querySelectorAll('.file-list-item').forEach(item => {
                    item.addEventListener('click', function(e) {
                        const fileId = this.dataset.fileId;
                        const fileName = this.querySelector('.file-name').textContent;
                        viewFileContent(fileId, fileName);
                    });
                    
                    // Add right-click context menu
                    item.addEventListener('contextmenu', function(e) {
                        e.preventDefault();
                        const fileId = this.dataset.fileId;
                        const fileName = this.querySelector('.file-name').textContent;
                        showContextMenu(e.pageX, e.pageY, fileId, fileName);
                    });
                });
            };
            
            // Context menu functionality
            let contextMenu = null;
            
            const showContextMenu = (x, y, fileId, fileName) => {
                // Remove existing menu
                if (contextMenu) {
                    contextMenu.remove();
                }
                
                // Create context menu
                contextMenu = document.createElement('div');
                contextMenu.className = 'file-context-menu';
                contextMenu.style.left = x + 'px';
                contextMenu.style.top = y + 'px';
                contextMenu.style.display = 'block';
                
                contextMenu.innerHTML = `
                    <div class="context-menu-item" data-action="view">
                        <i class="fas fa-eye"></i> View
                    </div>
                    <div class="context-menu-item" data-action="copy">
                        <i class="fas fa-copy"></i> Copy Content
                    </div>
                    <div class="context-menu-item" data-action="archive">
                        <i class="fas fa-archive"></i> Archive
                    </div>
                    <div class="context-menu-item delete" data-action="delete">
                        <i class="fas fa-trash"></i> Delete
                    </div>
                `;
                
                document.body.appendChild(contextMenu);
                
                // Handle menu item clicks
                contextMenu.querySelectorAll('.context-menu-item').forEach(item => {
                    item.addEventListener('click', function() {
                        const action = this.dataset.action;
                        contextMenu.remove();
                        
                        switch(action) {
                            case 'view':
                                viewFileContent(fileId, fileName);
                                break;
                            case 'copy':
                                copyFileContent(fileId);
                                break;
                            case 'archive':
                                if (confirm(`Are you sure you want to archive "${fileName}"?`)) {
                                    archiveFile(fileId);
                                }
                                break;
                            case 'delete':
                                if (confirm(`Are you sure you want to delete "${fileName}"? This action cannot be undone.`)) {
                                    deleteFile(fileId);
                                }
                                break;
                        }
                    });
                });
                
                // Close menu when clicking outside
                const closeMenu = (e) => {
                    if (contextMenu && !contextMenu.contains(e.target)) {
                        contextMenu.remove();
                        contextMenu = null;
                        document.removeEventListener('click', closeMenu);
                    }
                };
                
                setTimeout(() => {
                    document.addEventListener('click', closeMenu);
                }, 0);
            };
            
            // View file content in the viewer panel
            const viewFileContent = (fileId, fileName) => {
                const projectId = getCurrentProjectId();
                if (!projectId) {
                    console.error('[ArtifactsLoader] No project ID available for viewing file');
                    showToast('Error: No project ID available', 'error');
                    return;
                }
                
                console.log('[ArtifactsLoader] Viewing file:', { fileId, fileName, projectId });
                
                // Close any open version drawer when viewing a different file
                const existingDrawer = document.querySelector('.version-drawer');
                if (existingDrawer && existingDrawer.dataset.fileId !== String(fileId)) {
                    window.closeVersionDrawer();
                }
                
                fetch(`/projects/${projectId}/api/files/${fileId}/content/`, {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken(),
                    }
                })
                .then(response => response.json())
                .then(data => {
                    // Switch to viewer mode
                    fileBrowserMain.style.display = 'none';
                    fileBrowserViewer.style.display = 'flex';
                    
                    // Set title
                    viewerTitle.textContent = data.name || fileName;
                    
                    // Reset editor state
                    if (window.currentWysiwygEditor) {
                        window.currentWysiwygEditor = null;
                    }
                    window.currentFileData = {
                        fileId: fileId,
                        fileName: data.name || fileName,
                        content: data.content || '',
                        type: data.type
                    };
                    
                    // Render markdown content
                    const content = data.content || 'No content available';
                    
                    // Add edit button to header if not already there
                    let editButton = viewerDelete.parentElement.querySelector('#viewer-edit');
                    if (!editButton) {
                        editButton = document.createElement('button');
                        editButton.id = 'viewer-edit';
                        editButton.className = 'btn btn-sm';
                        editButton.style = 'padding: 8px 16px; background: #8b5cf6; color: white; border: none; border-radius: 6px; cursor: pointer;';
                        editButton.innerHTML = '<i class="fas fa-edit"></i> Edit';
                        viewerDelete.parentElement.insertBefore(editButton, viewerDelete);
                        
                        editButton.addEventListener('click', () => enableEditMode());
                    }
                    
                    // Add or update version history button
                    let versionButton = viewerDelete.parentElement.querySelector('#viewer-versions');
                    if (!versionButton) {
                        versionButton = document.createElement('button');
                        versionButton.id = 'viewer-versions';
                        versionButton.className = 'btn btn-sm';
                        versionButton.style = 'padding: 8px 16px; background: #4a5568; color: white; border: none; border-radius: 6px; cursor: pointer; margin-right: 10px;';
                        versionButton.innerHTML = '<i class="fas fa-history"></i> Versions';
                        viewerDelete.parentElement.insertBefore(versionButton, editButton);
                    }
                    
                    // Remove old event listeners and add new one for current file
                    const newVersionButton = versionButton.cloneNode(true);
                    versionButton.parentNode.replaceChild(newVersionButton, versionButton);
                    newVersionButton.addEventListener('click', () => {
                        const currentFileId = window.currentFileData ? window.currentFileData.fileId : fileId;
                        console.log('[VersionButton] Clicked for fileId:', currentFileId);
                        showVersionHistory(currentFileId);
                    });
                    
                    // For PRD and implementation files, render as markdown
                    if (data.type === 'prd' || data.type === 'implementation') {
                        // Use marked.js if available, otherwise basic rendering
                        if (typeof marked !== 'undefined') {
                            viewerMarkdown.innerHTML = marked.parse(content);
                        } else {
                            // Simple markdown rendering
                            let renderedContent = escapeHtml(content);
                            
                            // Convert markdown to HTML (basic conversion)
                            // Headers
                            renderedContent = renderedContent.replace(/^#### (.*$)/gim, '<h4>$1</h4>');
                            renderedContent = renderedContent.replace(/^### (.*$)/gim, '<h3>$1</h3>');
                            renderedContent = renderedContent.replace(/^## (.*$)/gim, '<h2>$1</h2>');
                            renderedContent = renderedContent.replace(/^# (.*$)/gim, '<h1>$1</h1>');
                            
                            // Bold and italic
                            renderedContent = renderedContent.replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>');
                            renderedContent = renderedContent.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                            renderedContent = renderedContent.replace(/\*(.*?)\*/g, '<em>$1</em>');
                            
                            // Links
                            renderedContent = renderedContent.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
                            
                            // Lists
                            renderedContent = renderedContent.replace(/^\* (.+)$/gim, '<li>$1</li>');
                            renderedContent = renderedContent.replace(/^\d+\. (.+)$/gim, '<li>$1</li>');
                            
                            // Wrap consecutive list items
                            renderedContent = renderedContent.replace(/(<li>.*?<\/li>\s*)+/gs, function(match) {
                                return '<ul>' + match + '</ul>';
                            });
                            
                            // Code blocks
                            renderedContent = renderedContent.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
                            renderedContent = renderedContent.replace(/`([^`]+)`/g, '<code>$1</code>');
                            
                            // Paragraphs
                            renderedContent = renderedContent.split('\n\n').map(para => {
                                if (para.trim() && !para.startsWith('<') && !para.match(/^[\*\d]/)) {
                                    return '<p>' + para + '</p>';
                                }
                                return para;
                            }).join('\n');
                            
                            viewerMarkdown.innerHTML = renderedContent;
                        }
                    } else {
                        // For other file types, display as preformatted text
                        viewerMarkdown.innerHTML = '<pre style="white-space: pre-wrap; word-wrap: break-word;">' + escapeHtml(content) + '</pre>';
                    }
                    
                    // Store current file info for actions
                    viewerCopy.dataset.fileId = fileId;
                    viewerCopy.dataset.content = content;
                    viewerDelete.dataset.fileId = fileId;
                    viewerDelete.dataset.fileName = data.name || fileName;
                })
                .catch(error => {
                    console.error('[ArtifactsLoader] Error loading file content:', error);
                    showToast('Failed to load file content', 'error');
                });
            };
            
            // Auto-save functionality
            let autoSaveTimer = null;
            let hasUnsavedChanges = false;
            
            // Function to perform auto-save
            const performAutoSave = async () => {
                if (hasUnsavedChanges && window.currentWysiwygEditor) {
                    console.log('[AutoSave] Performing auto-save...');
                    await saveFileContent(true); // true indicates auto-save
                    hasUnsavedChanges = false;
                }
            };
            
            // Start auto-save timer
            const startAutoSave = () => {
                // Clear existing timer
                if (autoSaveTimer) {
                    clearInterval(autoSaveTimer);
                }
                
                // Set up auto-save every 15 seconds
                autoSaveTimer = setInterval(performAutoSave, 15000);
            };
            
            // Stop auto-save timer
            const stopAutoSave = () => {
                if (autoSaveTimer) {
                    clearInterval(autoSaveTimer);
                    autoSaveTimer = null;
                }
            };
            
            // Create auto-save indicator
            const createAutoSaveIndicator = () => {
                const indicator = document.createElement('span');
                indicator.id = 'auto-save-indicator';
                indicator.style.cssText = `
                    display: none;
                    margin-left: 15px;
                    font-size: 14px;
                    color: #10b981;
                    font-weight: normal;
                `;
                
                // Add to viewer header
                const viewerTitle = document.getElementById('viewer-title');
                if (viewerTitle && viewerTitle.parentElement) {
                    viewerTitle.parentElement.appendChild(indicator);
                }
                
                return indicator;
            };
            
            // Enable edit mode with WYSIWYG editor
            const enableEditMode = () => {
                if (!window.currentFileData) return;
                
                const viewerMarkdown = document.getElementById('viewer-markdown');
                const viewerContent = document.querySelector('.viewer-content');
                const fileBrowserViewer = document.getElementById('filebrowser-viewer');
                
                if (!viewerMarkdown || !fileBrowserViewer) return;
                
                // Create container for WYSIWYG editor
                const editorContainer = document.createElement('div');
                editorContainer.id = 'wysiwyg-editor';
                editorContainer.style.cssText = 'flex: 1; height: calc(100% - 60px); position: relative;';
                
                // Hide the viewer-content to avoid nested scrolling
                if (viewerContent) {
                    viewerContent.style.display = 'none';
                }
                
                // Insert editor directly in the viewer, after header
                const viewerHeader = fileBrowserViewer.querySelector('.viewer-header');
                if (viewerHeader && viewerHeader.nextSibling) {
                    fileBrowserViewer.insertBefore(editorContainer, viewerHeader.nextSibling);
                } else {
                    fileBrowserViewer.appendChild(editorContainer);
                }
                
                // Load Jodit editor if not already loaded
                if (!window.Jodit) {
                    // Load Jodit CSS
                    const joditCss = document.createElement('link');
                    joditCss.rel = 'stylesheet';
                    joditCss.href = 'https://unpkg.com/jodit@3.24.9/build/jodit.min.css';
                    document.head.appendChild(joditCss);
                    
                    // Load Jodit JS
                    const joditScript = document.createElement('script');
                    joditScript.src = 'https://unpkg.com/jodit@3.24.9/build/jodit.min.js';
                    joditScript.onload = () => {
                        setTimeout(() => initializeWysiwygEditor(), 100);
                    };
                    document.head.appendChild(joditScript);
                } else {
                    // Initialize editor immediately
                    initializeWysiwygEditor();
                }
                
                // Update buttons
                const editButton = document.getElementById('viewer-edit');
                const deleteButton = document.getElementById('viewer-delete');
                const copyButton = document.getElementById('viewer-copy');
                
                if (editButton) editButton.style.display = 'none';
                if (deleteButton) deleteButton.style.display = 'none';
                if (copyButton) copyButton.style.display = 'none';
                
                // Add save and cancel buttons
                let saveButton = document.getElementById('viewer-save');
                let cancelButton = document.getElementById('viewer-cancel');
                
                if (!saveButton) {
                    saveButton = document.createElement('button');
                    saveButton.id = 'viewer-save';
                    saveButton.className = 'btn btn-sm';
                    saveButton.style = 'padding: 8px 16px; background: #10b981; color: white; border: none; border-radius: 6px; cursor: pointer;';
                    saveButton.innerHTML = '<i class="fas fa-save"></i> Save';
                    saveButton.addEventListener('click', () => saveFileContent());
                    deleteButton.parentElement.appendChild(saveButton);
                }
                
                if (!cancelButton) {
                    cancelButton = document.createElement('button');
                    cancelButton.id = 'viewer-cancel';
                    cancelButton.className = 'btn btn-sm';
                    cancelButton.style = 'padding: 8px 16px; background: #6b7280; color: white; border: none; border-radius: 6px; cursor: pointer; margin-left: 10px;';
                    cancelButton.innerHTML = '<i class="fas fa-times"></i> Cancel';
                    cancelButton.addEventListener('click', () => cancelEditMode());
                    deleteButton.parentElement.appendChild(cancelButton);
                }
                
                saveButton.style.display = 'inline-block';
                cancelButton.style.display = 'inline-block';
            };
            
            // Initialize the WYSIWYG editor
            const initializeWysiwygEditor = () => {
                const editorContainer = document.getElementById('wysiwyg-editor');
                if (!editorContainer) return;
                
                // Clear the container
                editorContainer.innerHTML = '';
                
                // Create textarea for Jodit
                const textarea = document.createElement('textarea');
                textarea.id = 'jodit-editor';
                editorContainer.appendChild(textarea);
                
                // Convert markdown to HTML
                let initialHTML = window.currentFileData.content;
                if (window.marked) {
                    marked.setOptions({
                        gfm: true,
                        breaks: true,
                        tables: true
                    });
                    initialHTML = marked.parse(window.currentFileData.content);
                }
                
                // Calculate height to fill the entire viewer area
                const viewerContainer = document.getElementById('filebrowser-viewer');
                const viewerHeader = viewerContainer ? viewerContainer.querySelector('.viewer-header') : null;
                const headerHeight = viewerHeader ? viewerHeader.offsetHeight : 60;
                // Subtract header height and some padding
                const viewerHeight = viewerContainer ? viewerContainer.offsetHeight - headerHeight - 20 : 600;
                
                // Initialize Jodit with dark theme
                try {
                    window.currentWysiwygEditor = Jodit.make('#jodit-editor', {
                    theme: 'dark',
                    height: '100%',
                    minHeight: 400,
                    toolbarSticky: true,
                    toolbarStickyOffset: 0,
                    showCharsCounter: false,
                    showWordsCounter: false,
                    showXPathInStatusbar: false,
                    // Add keyboard shortcuts
                    hotkeys: {
                        'ctrl+s,cmd+s': function(editor) {
                            saveFileContent();
                            return false; // Prevent default browser save
                        }
                    },
                    buttons: [
                        'bold', 'italic', 'underline', 'strikethrough', '|',
                        'ul', 'ol', '|',
                        'font', 'fontsize', 'paragraph', '|',
                        'table', 'link', 'image', '|',
                        'align', '|',
                        'undo', 'redo', '|',
                        'eraser', 'fullsize'
                    ],
                    buttonsMD: [
                        'bold', 'italic', 'underline', '|',
                        'ul', 'ol', '|',
                        'table', 'link', '|',
                        'dots'
                    ],
                    buttonsXS: [
                        'bold', 'italic', '|',
                        'ul', 'ol', '|',
                        'dots'
                    ],
                    style: {
                        background: '#1a1a1a',
                        color: '#e2e8f0'
                    },
                    editorCssClass: 'dark-editor',
                    toolbarAdaptive: false,
                    enter: 'p',
                    defaultMode: Jodit.MODE_WYSIWYG,
                    useSplitMode: false,
                    colors: {
                        greyscale: ['#000000', '#434343', '#666666', '#999999', '#B7B7B7', '#CCCCCC', '#D9D9D9', '#EFEFEF', '#F3F3F3', '#FFFFFF'],
                        palette: ['#8B5CF6', '#60A5FA', '#10B981', '#F59E0B', '#EF4444', '#EC4899', '#8B5CF6', '#3B82F6', '#06B6D4', '#84CC16']
                    },
                    controls: {
                        font: {
                            list: {
                                "'Open Sans', sans-serif": 'Open Sans',
                                'Helvetica, sans-serif': 'Helvetica',
                                'Arial, sans-serif': 'Arial',
                                'Georgia, serif': 'Georgia',
                                'Impact, sans-serif': 'Impact',
                                'Tahoma, sans-serif': 'Tahoma',
                                'Verdana, sans-serif': 'Verdana'
                            }
                        }
                    },
                    events: {
                        afterInit: function(editor) {
                            // Ensure text color persists
                            editor.editor.style.color = '#e2e8f0';
                            editor.editor.style.backgroundColor = '#1a1a1a';
                            
                            // Also set default paragraph style
                            const style = editor.createInside.element('style');
                            style.innerHTML = `
                                * { color: #e2e8f0 !important; }
                                p { color: #e2e8f0 !important; }
                                div { color: #e2e8f0 !important; }
                                span { color: #e2e8f0 !important; }
                            `;
                            editor.editor.appendChild(style);
                        },
                        change: function() {
                            // Mark as having unsaved changes
                            hasUnsavedChanges = true;
                            // Keep text color on change
                            const editor = this.editor;
                            if (editor) {
                                const walker = document.createTreeWalker(
                                    editor,
                                    NodeFilter.SHOW_ELEMENT,
                                    null,
                                    false
                                );
                                
                                let node;
                                while (node = walker.nextNode()) {
                                    if (!node.style.color || node.style.color === '') {
                                        node.style.color = '#e2e8f0';
                                    }
                                }
                            }
                        },
                        beforeEnter: function() {
                            // Ensure new paragraphs have the right color
                            const selection = this.selection;
                            if (selection.current()) {
                                const current = selection.current();
                                if (current && current.style) {
                                    current.style.color = '#e2e8f0';
                                }
                            }
                        }
                    }
                });
                } catch (error) {
                    console.error('[ArtifactsLoader] Error initializing Jodit editor:', error);
                    if (error.message && error.message.includes('plugin')) {
                        showToast('Editor initialization error: ' + error.message, 'error');
                    } else {
                        showToast('Failed to initialize editor', 'error');
                    }
                    // Fallback to textarea
                    const fallbackTextarea = document.createElement('textarea');
                    fallbackTextarea.id = 'fallback-editor';
                    fallbackTextarea.className = 'artifact-editor';
                    fallbackTextarea.value = window.currentFileData.content;
                    fallbackTextarea.style.cssText = 'width: 100%; height: ' + viewerHeight + 'px; background: #1a1a1a; color: #e2e8f0; border: 1px solid #333; padding: 20px; font-family: monospace;';
                    editorContainer.innerHTML = '';
                    editorContainer.appendChild(fallbackTextarea);
                    window.currentWysiwygEditor = {
                        value: fallbackTextarea.value,
                        get value() { return fallbackTextarea.value; },
                        set value(val) { fallbackTextarea.value = val; }
                    };
                    return;
                }
                
                // Set initial content
                window.currentWysiwygEditor.value = initialHTML;
                
                // Start auto-save timer
                startAutoSave();
                console.log('[AutoSave] Auto-save timer started');
                
                // Reset unsaved changes flag
                hasUnsavedChanges = false;
                
                // Force text color after content is set
                setTimeout(() => {
                    const editorBody = window.currentWysiwygEditor.editor;
                    if (editorBody) {
                        editorBody.style.color = '#e2e8f0';
                        // Apply color to all existing elements
                        const allElements = editorBody.querySelectorAll('*');
                        allElements.forEach(el => {
                            if (!el.style.color || el.style.color === '') {
                                el.style.color = '#e2e8f0';
                            }
                        });
                    }
                }, 100);
                
                // Apply custom dark theme styles
                const style = document.createElement('style');
                style.textContent = `
                    /* Jodit Dark Theme Overrides */
                    .jodit-container:not(.jodit_inline) {
                        border: 1px solid #333 !important;
                        background: #1a1a1a !important;
                        height: 100% !important;
                    }
                    
                    .jodit-toolbar__box {
                        background: #2a2a2a !important;
                        border-bottom: 1px solid #333 !important;
                    }
                    
                    .jodit-toolbar-button {
                        color: #e2e8f0 !important;
                    }
                    
                    .jodit-toolbar-button:hover {
                        background: #333 !important;
                    }
                    
                    .jodit-toolbar-button:active,
                    .jodit-toolbar-button[aria-pressed="true"] {
                        background: #8b5cf6 !important;
                    }
                    
                    .jodit-wysiwyg {
                        background: #1a1a1a !important;
                        color: #e2e8f0 !important;
                        padding: 20px !important;
                        min-height: calc(100% - 60px) !important;
                        line-height: 1.6 !important;
                    }
                    
                    /* Fix list formatting */
                    .jodit-wysiwyg ul,
                    .jodit-wysiwyg ol {
                        margin: 1em 0 !important;
                        padding-left: 2em !important;
                        line-height: 1.6 !important;
                    }
                    
                    .jodit-wysiwyg li {
                        margin: 0.5em 0 !important;
                        line-height: 1.6 !important;
                    }
                    
                    /* Fix paragraph spacing */
                    .jodit-wysiwyg p {
                        margin: 1em 0 !important;
                        line-height: 1.6 !important;
                    }
                    
                    /* Fix heading spacing */
                    .jodit-wysiwyg h1,
                    .jodit-wysiwyg h2,
                    .jodit-wysiwyg h3,
                    .jodit-wysiwyg h4,
                    .jodit-wysiwyg h5,
                    .jodit-wysiwyg h6 {
                        margin-top: 1.5em !important;
                        margin-bottom: 0.5em !important;
                        line-height: 1.3 !important;
                    }
                    
                    /* First heading should not have top margin */
                    .jodit-wysiwyg > h1:first-child,
                    .jodit-wysiwyg > h2:first-child,
                    .jodit-wysiwyg > h3:first-child {
                        margin-top: 0 !important;
                    }
                    
                    .jodit-wysiwyg,
                    .jodit-wysiwyg * {
                        color: #e2e8f0 !important;
                    }
                    
                    .jodit-wysiwyg p,
                    .jodit-wysiwyg div,
                    .jodit-wysiwyg span {
                        color: #e2e8f0 !important;
                    }
                    
                    .jodit-wysiwyg h1,
                    .jodit-wysiwyg h2,
                    .jodit-wysiwyg h3,
                    .jodit-wysiwyg h4,
                    .jodit-wysiwyg h5,
                    .jodit-wysiwyg h6 {
                        color: #e2e8f0 !important;
                    }
                    
                    .jodit-wysiwyg table {
                        border-collapse: collapse !important;
                        width: 100% !important;
                        margin: 1.5em 0 !important;
                    }
                    
                    .jodit-wysiwyg table td,
                    .jodit-wysiwyg table th {
                        border: 1px solid #444 !important;
                        padding: 10px 15px !important;
                        color: #e2e8f0 !important;
                        line-height: 1.5 !important;
                        vertical-align: top !important;
                    }
                    
                    .jodit-wysiwyg table th {
                        background: #2a2a2a !important;
                        font-weight: bold !important;
                    }
                    
                    .jodit-wysiwyg blockquote {
                        border-left: 4px solid #8b5cf6 !important;
                        background: rgba(139, 92, 246, 0.1) !important;
                        padding: 10px 20px !important;
                        margin: 10px 0 !important;
                        color: #e2e8f0 !important;
                    }
                    
                    .jodit-wysiwyg pre {
                        background: #0a0a0a !important;
                        border: 1px solid #333 !important;
                        border-radius: 4px !important;
                        padding: 1em !important;
                        color: #e2e8f0 !important;
                    }
                    
                    .jodit-wysiwyg code {
                        background: #2a2a2a !important;
                        color: #e2e8f0 !important;
                        padding: 0.2em 0.4em !important;
                        border-radius: 3px !important;
                    }
                    
                    .jodit-wysiwyg a {
                        color: #60a5fa !important;
                    }
                    
                    /* Status bar */
                    .jodit-status-bar {
                        background: #2a2a2a !important;
                        border-top: 1px solid #333 !important;
                        color: #9ca3af !important;
                    }
                    
                    /* Popup and dropdown styles */
                    .jodit-popup__content {
                        background: #2a2a2a !important;
                        border: 1px solid #444 !important;
                        color: #e2e8f0 !important;
                    }
                    
                    .jodit-dropdown__content {
                        background: #2a2a2a !important;
                        border: 1px solid #444 !important;
                    }
                    
                    .jodit-dropdown__item {
                        color: #e2e8f0 !important;
                    }
                    
                    .jodit-dropdown__item:hover {
                        background: #333 !important;
                    }
                    
                    /* Table selector */
                    .jodit-toolbar-button__button[aria-controls*="table"] {
                        color: #e2e8f0 !important;
                    }
                    
                    /* Color picker */
                    .jodit-color-picker__box {
                        background: #2a2a2a !important;
                        border: 1px solid #444 !important;
                    }
                    
                    /* Icons */
                    .jodit-icon {
                        fill: #e2e8f0 !important;
                    }
                    
                    .jodit-toolbar-button:hover .jodit-icon {
                        fill: #fff !important;
                    }
                    
                    .jodit-toolbar-button[aria-pressed="true"] .jodit-icon {
                        fill: #fff !important;
                    }
                `;
                document.head.appendChild(style);
                
                // Focus the editor
                window.currentWysiwygEditor.focus();
                
                // Additional style injection to ensure visibility
                const additionalStyles = document.createElement('style');
                additionalStyles.textContent = `
                    .jodit-wysiwyg[contenteditable="true"] {
                        color: #e2e8f0 !important;
                    }
                    
                    .jodit-wysiwyg[contenteditable="true"] * {
                        color: inherit !important;
                    }
                    
                    /* Force text color for all possible elements */
                    .jodit-wysiwyg p,
                    .jodit-wysiwyg div,
                    .jodit-wysiwyg span,
                    .jodit-wysiwyg h1,
                    .jodit-wysiwyg h2,
                    .jodit-wysiwyg h3,
                    .jodit-wysiwyg h4,
                    .jodit-wysiwyg h5,
                    .jodit-wysiwyg h6,
                    .jodit-wysiwyg li,
                    .jodit-wysiwyg td,
                    .jodit-wysiwyg th,
                    .jodit-wysiwyg a,
                    .jodit-wysiwyg strong,
                    .jodit-wysiwyg em,
                    .jodit-wysiwyg u,
                    .jodit-wysiwyg s {
                        color: #e2e8f0 !important;
                    }
                `;
                document.head.appendChild(additionalStyles);
            };
            
            
            // Save file content
            const saveFileContent = async (isAutoSave = false) => {
                if (!window.currentWysiwygEditor || !window.currentFileData) {
                    console.error('[ArtifactsLoader] Missing editor or file data');
                    return;
                }
                
                // Get project ID
                const projectId = getCurrentProjectId();
                if (!projectId) {
                    console.error('[ArtifactsLoader] No project ID available');
                    showToast('Error: No project ID available', 'error');
                    return;
                }
                
                // Show saving indicator
                const saveButton = document.getElementById('viewer-save');
                let originalText = saveButton ? saveButton.innerHTML : '';
                
                if (isAutoSave) {
                    // For auto-save, show a subtle indicator
                    const autoSaveIndicator = document.getElementById('auto-save-indicator') || createAutoSaveIndicator();
                    autoSaveIndicator.style.display = 'inline-block';
                    autoSaveIndicator.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Auto-saving...';
                } else {
                    // For manual save, update the save button
                    if (saveButton) {
                        originalText = saveButton.innerHTML;
                        saveButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
                        saveButton.disabled = true;
                    }
                }
                
                try {
                    // Get HTML content from Jodit editor
                    const htmlContent = window.currentWysiwygEditor.value;
                    
                    // Convert HTML back to markdown
                    let content = htmlContent;
                    
                    // Load Turndown if not available for better conversion
                    if (!window.TurndownService) {
                        // Load Turndown dynamically
                        await new Promise((resolve) => {
                            const script = document.createElement('script');
                            script.src = 'https://unpkg.com/turndown/dist/turndown.js';
                            script.onload = resolve;
                            document.head.appendChild(script);
                        });
                    }
                    
                    if (window.TurndownService) {
                        const turndownService = new TurndownService({
                            headingStyle: 'atx',
                            codeBlockStyle: 'fenced',
                            bulletListMarker: '-'
                        });
                        
                        // Add table support using the correct plugin format
                        turndownService.use(function(service) {
                            service.addRule('table', {
                                filter: 'table',
                                replacement: function(content, node) {
                                    // Convert HTML table back to markdown table
                                    const rows = Array.from(node.querySelectorAll('tr'));
                                    if (rows.length === 0) return '';
                                    
                                    let markdown = '';
                                    rows.forEach((row, index) => {
                                        const cells = Array.from(row.querySelectorAll('td, th'));
                                        markdown += '| ' + cells.map(cell => cell.textContent.trim()).join(' | ') + ' |\n';
                                        
                                        // Add separator after header row
                                        if (index === 0) {
                                            markdown += '|' + cells.map(() => '---').join('|') + '|\n';
                                        }
                                    });
                                    
                                    return '\n' + markdown + '\n';
                                }
                            });
                        });
                        
                        content = turndownService.turndown(htmlContent);
                    } else {
                        // Simple HTML to markdown conversion
                        content = htmlContent
                            .replace(/<h1[^>]*>(.*?)<\/h1>/gi, '# $1\n')
                            .replace(/<h2[^>]*>(.*?)<\/h2>/gi, '## $1\n')
                            .replace(/<h3[^>]*>(.*?)<\/h3>/gi, '### $1\n')
                            .replace(/<h4[^>]*>(.*?)<\/h4>/gi, '#### $1\n')
                            .replace(/<strong[^>]*>(.*?)<\/strong>/gi, '**$1**')
                            .replace(/<b[^>]*>(.*?)<\/b>/gi, '**$1**')
                            .replace(/<em[^>]*>(.*?)<\/em>/gi, '*$1*')
                            .replace(/<i[^>]*>(.*?)<\/i>/gi, '*$1*')
                            .replace(/<ul[^>]*>([\s\S]*?)<\/ul>/gi, function(match, content) {
                                return content.replace(/<li[^>]*>(.*?)<\/li>/gi, '- $1\n');
                            })
                            .replace(/<ol[^>]*>([\s\S]*?)<\/ol>/gi, function(match, content) {
                                let counter = 1;
                                return content.replace(/<li[^>]*>(.*?)<\/li>/gi, function(m, text) {
                                    return (counter++) + '. ' + text + '\n';
                                });
                            })
                            .replace(/<blockquote[^>]*>(.*?)<\/blockquote>/gi, '> $1\n')
                            .replace(/<br[^>]*>/gi, '\n')
                            .replace(/<p[^>]*>(.*?)<\/p>/gi, '$1\n\n')
                            .replace(/<[^>]+>/g, '')
                            .replace(/\n{3,}/g, '\n\n')
                            .trim();
                    }
                    
                    const { fileId, fileName, type } = window.currentFileData;
                    console.log('[ArtifactsLoader] Saving file:', { fileId, fileName, type, projectId });
                    
                    // Determine the correct API endpoint based on file type
                    let url, method, body;
                    
                    if (type === 'prd') {
                        url = `/projects/${projectId}/api/prd/?prd_name=${encodeURIComponent(fileName)}`;
                        method = 'POST';
                        body = JSON.stringify({ content: content });
                    } else if (type === 'implementation') {
                        url = `/projects/${projectId}/api/implementation/`;
                        method = 'POST';
                        body = JSON.stringify({ content: content });
                    } else {
                        // For other file types, use the generic files API
                        // The type should match the file_type in the model (e.g., 'design', 'test', 'other')
                        const fileType = type || 'other';
                        url = `/projects/${projectId}/api/files/?type=${fileType}&name=${encodeURIComponent(fileName)}`;
                        method = 'POST';
                        body = JSON.stringify({ content: content });
                    }
                    
                    console.log('[ArtifactsLoader] Request URL:', url);
                    console.log('[ArtifactsLoader] Request method:', method);
                    
                    const response = await fetch(url, {
                        method: method,
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken(),
                        },
                        body: body
                    });
                    
                    console.log('[ArtifactsLoader] Response status:', response.status);
                    
                    let data;
                    try {
                        data = await response.json();
                        console.log('[ArtifactsLoader] Response data:', data);
                    } catch (e) {
                        console.error('[ArtifactsLoader] Failed to parse response:', e);
                        data = { success: false, error: 'Failed to parse server response' };
                    }
                    
                    if (data.success || response.ok) {
                        // Show toast with proper function
                        if (isAutoSave) {
                            // For auto-save, show subtle indicator
                            const autoSaveIndicator = document.getElementById('auto-save-indicator');
                            if (autoSaveIndicator) {
                                autoSaveIndicator.innerHTML = '<i class="fas fa-check"></i> Auto-saved';
                                setTimeout(() => {
                                    autoSaveIndicator.style.display = 'none';
                                }, 2000);
                            }
                            console.log('[AutoSave] File auto-saved successfully');
                        } else {
                            // For manual save, show toast
                            if (typeof showToast === 'function') {
                                showToast('File saved successfully', 'success');
                            } else if (window.showToast && typeof window.showToast === 'function') {
                                window.showToast('File saved successfully', 'success');
                            } else {
                                alert('File saved successfully');
                            }
                        }
                        window.currentFileData.content = content;
                        
                        // Also save the file ID if it was created
                        if (data.file_id) {
                            window.currentFileData.fileId = data.file_id;
                        }
                        
                        // Exit edit mode and refresh view (only for manual save)
                        if (!isAutoSave) {
                            cancelEditMode(true);
                        }
                    } else {
                        console.error('[ArtifactsLoader] Save error:', data);
                        const errorMsg = 'Failed to save file: ' + (data.error || 'Unknown error');
                        
                        if (isAutoSave) {
                            console.error('[AutoSave] Auto-save failed:', errorMsg);
                            const autoSaveIndicator = document.getElementById('auto-save-indicator');
                            if (autoSaveIndicator) {
                                autoSaveIndicator.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Auto-save failed';
                                autoSaveIndicator.style.color = '#ef4444';
                                setTimeout(() => {
                                    autoSaveIndicator.style.display = 'none';
                                    autoSaveIndicator.style.color = '';
                                }, 3000);
                            }
                        } else {
                            if (typeof showToast === 'function') {
                                showToast(errorMsg, 'error');
                            } else if (window.showToast && typeof window.showToast === 'function') {
                                window.showToast(errorMsg, 'error');
                            } else {
                                alert(errorMsg);
                            }
                        }
                    }
                } catch (error) {
                    console.error('[ArtifactsLoader] Error saving file:', error);
                    const errorMsg = 'Failed to save file: ' + error.message;
                    
                    if (isAutoSave) {
                        console.error('[AutoSave] Auto-save error:', error);
                        const autoSaveIndicator = document.getElementById('auto-save-indicator');
                        if (autoSaveIndicator) {
                            autoSaveIndicator.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Auto-save failed';
                            autoSaveIndicator.style.color = '#ef4444';
                            setTimeout(() => {
                                autoSaveIndicator.style.display = 'none';
                                autoSaveIndicator.style.color = '';
                            }, 3000);
                        }
                    } else {
                        if (typeof showToast === 'function') {
                            showToast(errorMsg, 'error');
                        } else if (window.showToast && typeof window.showToast === 'function') {
                            window.showToast(errorMsg, 'error');
                        } else {
                            alert(errorMsg);
                        }
                    }
                } finally {
                    if (!isAutoSave && saveButton) {
                        saveButton.innerHTML = originalText;
                        saveButton.disabled = false;
                    }
                }
            };
            
            // Cancel edit mode
            const cancelEditMode = (skipConfirm = false) => {
                if (!skipConfirm && window.currentWysiwygEditor && hasUnsavedChanges) {
                    if (!confirm('Are you sure you want to cancel? Any unsaved changes will be lost.')) {
                        return;
                    }
                }
                
                // Stop auto-save timer
                stopAutoSave();
                console.log('[AutoSave] Auto-save timer stopped');
                
                // Clear reference
                if (window.currentWysiwygEditor) {
                    window.currentWysiwygEditor = null;
                }
                
                // Remove the editor container
                const editorContainer = document.getElementById('wysiwyg-editor');
                if (editorContainer) {
                    editorContainer.remove();
                }
                
                // Show the viewer-content again
                const viewerContent = document.querySelector('.viewer-content');
                if (viewerContent) {
                    viewerContent.style.display = '';
                }
                
                // Hide save/cancel buttons
                const saveButton = document.getElementById('viewer-save');
                const cancelButton = document.getElementById('viewer-cancel');
                if (saveButton) saveButton.style.display = 'none';
                if (cancelButton) cancelButton.style.display = 'none';
                
                // Show original buttons
                const editButton = document.getElementById('viewer-edit');
                const deleteButton = document.getElementById('viewer-delete');
                const copyButton = document.getElementById('viewer-copy');
                if (editButton) editButton.style.display = 'inline-block';
                if (deleteButton) deleteButton.style.display = 'inline-block';
                if (copyButton) copyButton.style.display = 'inline-block';
                
                // Refresh the file view
                if (window.currentFileData) {
                    viewFileContent(window.currentFileData.fileId, window.currentFileData.fileName);
                }
            };
            
            // Show version history in side drawer
            const showVersionHistory = async (fileId) => {
                const projectId = getCurrentProjectId();
                if (!projectId || !fileId) {
                    showToast('Error: Missing project or file ID', 'error');
                    return;
                }
                
                // Check if drawer already exists for this file
                const existingDrawer = document.querySelector('.version-drawer');
                if (existingDrawer && existingDrawer.dataset.fileId === String(fileId)) {
                    // Drawer already open for this file, do nothing
                    return;
                } else if (existingDrawer) {
                    // Close existing drawer for different file
                    window.closeVersionDrawer();
                }
                
                try {
                    const response = await fetch(`/projects/${projectId}/api/files/${fileId}/versions/`, {
                        method: 'GET',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken(),
                        }
                    });
                    
                    const data = await response.json();
                    if (!response.ok) {
                        throw new Error(data.error || 'Failed to load versions');
                    }
                    
                    console.log('[VersionHistory] API Response for file', fileId, ':', data);
                    
                    // Get filename from current file data
                    const fileName = window.currentFileData ? window.currentFileData.fileName : 'Unknown File';
                    
                    // Create version history drawer with fresh data
                    createVersionHistoryDrawer(fileId, fileName, data.versions || []);
                    
                } catch (error) {
                    console.error('[ArtifactsLoader] Error loading versions:', error);
                    showToast('Failed to load version history', 'error');
                }
            };
            
            // Create version history drawer
            const createVersionHistoryDrawer = (fileId, fileName, versions) => {
                console.log('[VersionDrawer] Creating drawer for file:', { fileId, fileName, versionCount: versions.length });
                
                // Remove existing drawer and overlay if any
                const existingDrawer = document.querySelector('.version-drawer');
                const existingOverlay = document.querySelector('.version-drawer-overlay');
                if (existingDrawer) {
                    existingDrawer.remove();
                }
                if (existingOverlay) {
                    existingOverlay.remove();
                }

                const drawer = document.createElement('div');
                drawer.className = 'version-drawer';
                
                // Group versions by date
                const versionsByDate = {};
                const today = new Date().toDateString();
                const yesterday = new Date(Date.now() - 86400000).toDateString();
                
                // Make sure we're using fresh version data
                const fileVersions = [...versions]; // Create a copy to avoid reference issues
                
                fileVersions.forEach(version => {
                    const versionDate = new Date(version.created_at);
                    const dateStr = versionDate.toDateString();
                    let groupLabel;
                    
                    if (dateStr === today) {
                        groupLabel = 'Today';
                    } else if (dateStr === yesterday) {
                        groupLabel = 'Yesterday';
                    } else {
                        groupLabel = versionDate.toLocaleDateString('en-US', { 
                            month: 'short', 
                            day: 'numeric',
                            year: versionDate.getFullYear() !== new Date().getFullYear() ? 'numeric' : undefined
                        });
                    }
                    
                    if (!versionsByDate[groupLabel]) {
                        versionsByDate[groupLabel] = [];
                    }
                    versionsByDate[groupLabel].push(version);
                });
                
                drawer.innerHTML = `
                    <div class="version-drawer-header">
                        <h5>Version History</h5>
                        <button class="btn btn-ghost btn-sm" onclick="closeVersionDrawer()">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div class="version-drawer-subheader">
                        <span class="file-name">${fileName}</span>
                        <span class="version-count">${fileVersions.length} version${fileVersions.length !== 1 ? 's' : ''}</span>
                    </div>
                    <div class="version-drawer-content">
                        ${fileVersions.length === 0 ? '<p class="no-versions">No version history available.</p>' : 
                            Object.entries(versionsByDate).map(([date, dateVersions]) => `
                                <div class="version-date-group">
                                    <div class="version-date-label">${date}</div>
                                    ${dateVersions.map(version => {
                                        const versionDate = new Date(version.created_at);
                                        const timeStr = versionDate.toLocaleTimeString('en-US', { 
                                            hour: 'numeric', 
                                            minute: '2-digit',
                                            hour12: true 
                                        });
                                        const isCurrentVersion = version.version_number === fileVersions[0].version_number;
                                        
                                        return `
                                            <div class="version-item ${isCurrentVersion ? 'current-version' : ''}" 
                                                 onclick="selectVersion(${fileId}, ${version.version_number}, this)">
                                                <div class="version-item-content">
                                                    <div class="version-item-header">
                                                        <span class="version-time">${timeStr}</span>
                                                        ${isCurrentVersion ? '<span class="current-badge">Current</span>' : ''}
                                                    </div>
                                                    <div class="version-item-info">
                                                        <span class="version-number">Version ${version.version_number}</span>
                                                        ${version.created_by ? `<span class="version-author">${version.created_by}</span>` : ''}
                                                    </div>
                                                    ${version.change_description ? 
                                                        `<div class="version-description">${version.change_description}</div>` : ''}
                                                </div>
                                                <div class="version-item-actions">
                                                    <button class="btn btn-ghost btn-sm" title="View this version" 
                                                            onclick="event.stopPropagation(); viewVersion(${fileId}, ${version.version_number})">
                                                        <i class="fas fa-eye"></i>
                                                    </button>
                                                    ${!isCurrentVersion ? `
                                                        <button class="btn btn-ghost btn-sm" title="Restore this version" 
                                                                onclick="event.stopPropagation(); restoreVersion(${fileId}, ${version.version_number}, '${fileName.replace(/'/g, "\\'")}')">  
                                                            <i class="fas fa-undo"></i>
                                                        </button>
                                                    ` : ''}
                                                </div>
                                            </div>
                                        `;
                                    }).join('')}
                                </div>
                            `).join('')
                        }
                    </div>
                `;
                
                document.body.appendChild(drawer);
                
                // Add styles if not already present
                addVersionDrawerStyles();
                
                // Create overlay for click outside functionality
                let overlay = document.querySelector('.version-drawer-overlay');
                if (!overlay) {
                    overlay = document.createElement('div');
                    overlay.className = 'version-drawer-overlay';
                    document.body.appendChild(overlay);
                }
                
                // Open drawer with animation
                setTimeout(() => {
                    drawer.classList.add('open');
                    overlay.classList.add('active');
                }, 10);
                
                // Store current file ID in drawer for verification
                drawer.dataset.fileId = String(fileId);
                console.log('[VersionDrawer] Drawer created with fileId:', drawer.dataset.fileId);
                
                // Close drawer function
                const closeDrawer = () => {
                    const drawer = document.querySelector('.version-drawer');
                    const overlay = document.querySelector('.version-drawer-overlay');
                    if (drawer) {
                        drawer.classList.remove('open');
                        if (overlay) overlay.classList.remove('active');
                        setTimeout(() => {
                            drawer.remove();
                            if (overlay) overlay.remove();
                        }, 300);
                    }
                };
                
                // Attach global functions for drawer
                window.closeVersionDrawer = closeDrawer;
                
                // Click outside to close
                overlay.addEventListener('click', closeDrawer);
                
                // ESC key to close
                const escHandler = (e) => {
                    if (e.key === 'Escape') {
                        closeDrawer();
                        document.removeEventListener('keydown', escHandler);
                    }
                };
                document.addEventListener('keydown', escHandler);
                
                window.selectVersion = (fileId, versionNumber, element) => {
                    // Remove previous selection
                    document.querySelectorAll('.version-item.selected').forEach(item => {
                        item.classList.remove('selected');
                    });
                    
                    // Add selection to clicked item
                    element.classList.add('selected');
                    
                    // View the version
                    viewVersion(fileId, versionNumber);
                };
                
                window.viewVersion = viewVersion;
                window.restoreVersion = restoreVersion;
            };
            
            // Add version drawer styles
            const addVersionDrawerStyles = () => {
                if (!document.querySelector('#versionDrawerStyles')) {
                    const style = document.createElement('style');
                    style.id = 'versionDrawerStyles';
                    style.textContent = `
                        .version-drawer {
                            position: fixed;
                            top: 0;
                            right: -400px;
                            width: 400px;
                            height: 100%;
                            background: #1a1a1a;
                            box-shadow: -2px 0 10px rgba(0,0,0,0.5);
                            z-index: 2050;
                            display: flex;
                            flex-direction: column;
                            transition: right 0.3s ease;
                        }
                        
                        .version-drawer.open {
                            right: 0;
                        }
                        
                        .version-drawer-header {
                            display: flex;
                            align-items: center;
                            justify-content: space-between;
                            padding: 1rem 1.5rem;
                            border-bottom: 1px solid #333;
                            background: #0a0a0a;
                        }
                        
                        .version-drawer-header h5 {
                            margin: 0;
                            font-size: 1.1rem;
                            font-weight: 600;
                            color: #e2e8f0;
                        }
                        
                        .version-drawer-subheader {
                            display: flex;
                            align-items: center;
                            justify-content: space-between;
                            padding: 0.75rem 1.5rem;
                            border-bottom: 1px solid #333;
                            background: #1a1a1a;
                        }
                        
                        .version-drawer-subheader .file-name {
                            font-weight: 500;
                            color: #94a3b8;
                            font-size: 0.9rem;
                        }
                        
                        .version-drawer-subheader .version-count {
                            font-size: 0.85rem;
                            color: #64748b;
                        }
                        
                        .version-drawer-content {
                            flex: 1;
                            overflow-y: auto;
                            padding: 1rem 0;
                        }
                        
                        .version-date-group {
                            margin-bottom: 1.5rem;
                        }
                        
                        .version-date-label {
                            font-size: 0.75rem;
                            font-weight: 600;
                            color: #64748b;
                            text-transform: uppercase;
                            letter-spacing: 0.5px;
                            padding: 0 1.5rem;
                            margin-bottom: 0.5rem;
                        }
                        
                        .version-item {
                            display: flex;
                            align-items: center;
                            justify-content: space-between;
                            padding: 0.75rem 1.5rem;
                            cursor: pointer;
                            transition: all 0.2s ease;
                            border-left: 3px solid transparent;
                        }
                        
                        .version-item:hover {
                            background-color: #262626;
                        }
                        
                        .version-item.selected {
                            background-color: #1e293b;
                            border-left-color: #3b82f6;
                        }
                        
                        .version-item.current-version {
                            background-color: #1e1e2e;
                        }
                        
                        .version-item-content {
                            flex: 1;
                            min-width: 0;
                        }
                        
                        .version-item-header {
                            display: flex;
                            align-items: center;
                            gap: 0.5rem;
                            margin-bottom: 0.25rem;
                        }
                        
                        .version-time {
                            font-size: 0.875rem;
                            font-weight: 500;
                            color: #e2e8f0;
                        }
                        
                        .current-badge {
                            font-size: 0.7rem;
                            font-weight: 600;
                            color: #3b82f6;
                            background: #1e293b;
                            padding: 0.125rem 0.5rem;
                            border-radius: 10px;
                            text-transform: uppercase;
                        }
                        
                        .version-item-info {
                            display: flex;
                            align-items: center;
                            gap: 0.5rem;
                            font-size: 0.8rem;
                            color: #94a3b8;
                        }
                        
                        .version-number {
                            font-weight: 500;
                        }
                        
                        .version-author::before {
                            content: '•';
                            margin-right: 0.5rem;
                        }
                        
                        .version-description {
                            font-size: 0.8rem;
                            color: #64748b;
                            margin-top: 0.25rem;
                            white-space: nowrap;
                            overflow: hidden;
                            text-overflow: ellipsis;
                        }
                        
                        .version-item-actions {
                            display: flex;
                            gap: 0.25rem;
                            opacity: 0;
                            transition: opacity 0.2s ease;
                        }
                        
                        .version-item:hover .version-item-actions {
                            opacity: 1;
                        }
                        
                        .btn-ghost {
                            background: transparent;
                            border: none;
                            color: #64748b;
                            padding: 0.25rem 0.5rem;
                            border-radius: 4px;
                            transition: all 0.2s ease;
                        }
                        
                        .btn-ghost:hover {
                            background: #334155;
                            color: #94a3b8;
                        }
                        
                        .no-versions {
                            text-align: center;
                            color: #64748b;
                            padding: 2rem;
                        }
                        
                        /* Overlay for click outside */
                        .version-drawer-overlay {
                            position: fixed;
                            top: 0;
                            left: 0;
                            right: 0;
                            bottom: 0;
                            background: rgba(0, 0, 0, 0.5);
                            z-index: 2049;
                            opacity: 0;
                            visibility: hidden;
                            transition: opacity 0.3s ease, visibility 0.3s ease;
                        }
                        
                        .version-drawer-overlay.active {
                            opacity: 1;
                            visibility: visible;
                        }
                    `;
                    document.head.appendChild(style);
                }
            };
            
            // View specific version
            const viewVersion = async (fileId, versionNumber) => {
                const projectId = getCurrentProjectId();
                if (!projectId || !fileId) return;
                
                try {
                    const response = await fetch(`/projects/${projectId}/api/files/${fileId}/versions/${versionNumber}/`, {
                        method: 'GET',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken(),
                        }
                    });
                    
                    const data = await response.json();
                    if (!data.success) {
                        throw new Error(data.error || 'Failed to load version');
                    }
                    
                    // Show version content in viewer
                    const viewerMarkdown = document.getElementById('viewer-markdown');
                    if (viewerMarkdown) {
                        // Add version notice
                        const versionNotice = document.createElement('div');
                        versionNotice.style.cssText = `
                            background: #333;
                            border: 1px solid #8b5cf6;
                            padding: 10px 15px;
                            margin-bottom: 20px;
                            border-radius: 6px;
                            color: #e2e8f0;
                            display: flex;
                            justify-content: space-between;
                            align-items: center;
                        `;
                        versionNotice.innerHTML = `
                            <span><i class="fas fa-info-circle"></i> Viewing version ${versionNumber} from ${new Date(data.created_at).toLocaleDateString()}</span>
                            <button id="close-version-view" style="background: #8b5cf6; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer;">
                                Back to Current
                            </button>
                        `;
                        
                        // Render version content
                        viewerMarkdown.innerHTML = '';
                        viewerMarkdown.appendChild(versionNotice);
                        
                        const contentDiv = document.createElement('div');
                        if (typeof marked !== 'undefined') {
                            contentDiv.innerHTML = marked.parse(data.content);
                        } else {
                            contentDiv.innerHTML = data.content.replace(/\n/g, '<br>');
                        }
                        viewerMarkdown.appendChild(contentDiv);
                        
                        // Style the viewer for version view
                        viewerMarkdown.style.opacity = '0.95';
                        
                        // Back to current button
                        document.getElementById('close-version-view').addEventListener('click', () => {
                            viewFileContent(fileId, window.currentFileData.fileName);
                        });
                    }
                    
                } catch (error) {
                    console.error('[ArtifactsLoader] Error viewing version:', error);
                    showToast('Failed to load version', 'error');
                }
            };
            
            // Restore version
            const restoreVersion = async (fileId, versionNumber) => {
                const projectId = getCurrentProjectId();
                if (!projectId || !fileId) return;
                
                try {
                    const response = await fetch(`/projects/${projectId}/api/files/${fileId}/versions/${versionNumber}/`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken(),
                        }
                    });
                    
                    const data = await response.json();
                    if (!data.success) {
                        throw new Error(data.error || 'Failed to restore version');
                    }
                    
                    showToast(data.message, 'success');
                    // Close the version drawer
                    closeVersionDrawer();
                    // Reload the file content
                    viewFileContent(fileId, window.currentFileData.fileName);
                    
                } catch (error) {
                    console.error('[ArtifactsLoader] Error restoring version:', error);
                    showToast('Failed to restore version', 'error');
                }
            };
            
            // Delete file
            const deleteFile = (fileId) => {
                // For now, we'll use the existing delete endpoint
                // In a real implementation, you'd create a proper delete endpoint
                const fileItem = document.querySelector(`[data-file-id="${fileId}"]`);
                const fileType = fileItem.classList.contains('file-type-prd') ? 'prd' : 
                               fileItem.classList.contains('file-type-implementation') ? 'implementation' :
                               fileItem.classList.contains('file-type-design') ? 'design' :
                               fileItem.classList.contains('file-type-test') ? 'test' : 'other';
                const fileName = fileItem.querySelector('.file-name').textContent;
                
                fetch(`/projects/${projectId}/api/files/?type=${fileType}&name=${encodeURIComponent(fileName)}`, {
                    method: 'DELETE',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken(),
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        showToast('File deleted successfully', 'success');
                        fetchFiles(currentPage);
                    } else {
                        showToast(data.error || 'Failed to delete file', 'error');
                    }
                })
                .catch(error => {
                    console.error('[ArtifactsLoader] Error deleting file:', error);
                    showToast('Failed to delete file', 'error');
                });
            };
            
            // Archive file (for now, same as delete but could be different)
            const archiveFile = (fileId) => {
                // In a real implementation, you'd have a separate archive endpoint
                // For now, we'll just show a message
                showToast('Archive feature coming soon', 'info');
            };
            
            // Copy file content to clipboard
            const copyFileContent = (fileId) => {
                fetch(`/projects/${projectId}/api/files/${fileId}/content/`, {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken(),
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.content) {
                        copyToClipboard(data.content);
                        showToast('Content copied to clipboard!', 'success');
                    }
                })
                .catch(error => {
                    console.error('[ArtifactsLoader] Error copying file content:', error);
                    showToast('Failed to copy file content', 'error');
                });
            };
            
            // Event listeners for search and filters
            if (fileSearch) {
                fileSearch.addEventListener('input', function() {
                    currentSearch = this.value;
                    
                    // Debounce search
                    clearTimeout(searchTimeout);
                    searchTimeout = setTimeout(() => {
                        currentPage = 1;
                        fetchFiles(currentPage);
                    }, 300);
                });
            }
            
            if (fileTypeFilter) {
                fileTypeFilter.addEventListener('change', function() {
                    currentType = this.value;
                    currentPage = 1;
                    fetchFiles(currentPage);
                });
            }
            
            if (refreshButton) {
                refreshButton.addEventListener('click', function() {
                    fetchFiles(currentPage);
                });
            }
            
            // Viewer event listeners
            if (viewerBack) {
                viewerBack.addEventListener('click', async function() {
                    // Check if we're in edit mode with unsaved changes
                    if (window.currentWysiwygEditor && hasUnsavedChanges) {
                        // Auto-save before going back
                        console.log('[FileBrowser] Auto-saving before navigating back...');
                        await saveFileContent(true); // true for auto-save
                    }
                    
                    // If still in edit mode, cancel it
                    if (window.currentWysiwygEditor) {
                        cancelEditMode(true); // true to skip confirmation
                    }
                    
                    // Navigate back to file list
                    fileBrowserViewer.style.display = 'none';
                    fileBrowserMain.style.display = 'flex';
                });
            }
            
            if (viewerCopy) {
                viewerCopy.addEventListener('click', function() {
                    const content = this.dataset.content;
                    if (content) {
                        copyToClipboard(content);
                        showToast('Content copied to clipboard!', 'success');
                    }
                });
            }
            
            if (viewerDelete) {
                viewerDelete.addEventListener('click', function() {
                    const fileId = this.dataset.fileId;
                    const fileName = this.dataset.fileName;
                    if (confirm(`Are you sure you want to delete "${fileName}"? This action cannot be undone.`)) {
                        deleteFile(fileId);
                        // Go back to list view
                        fileBrowserViewer.style.display = 'none';
                        fileBrowserMain.style.display = 'flex';
                    }
                });
            }
            
            // Initial load
            fetchFiles(1);
        } // End of loadFileBrowser function
    }; // End of ArtifactsLoader object

    // ArtifactsLoader is now ready to use
    console.log('[ArtifactsLoader] Loaded and ready');
    
    // Add event handlers for custom PRD selector
    setTimeout(() => {
        const prdSelector = document.getElementById('prd-selector');
        const selectorButton = document.getElementById('prd-selector-button');
        const selectorDropdown = document.getElementById('prd-selector-dropdown');
        const selectorText = document.getElementById('prd-selector-text');
        
        // Handle custom dropdown toggle
        if (selectorButton) {
            selectorButton.addEventListener('click', function(e) {
                e.stopPropagation();
                const isOpen = selectorDropdown.style.display === 'block';
                
                if (isOpen) {
                    selectorDropdown.style.display = 'none';
                    selectorButton.classList.remove('active');
                } else {
                    selectorDropdown.style.display = 'block';
                    selectorButton.classList.add('active');
                }
            });
        }
        
        // Handle option selection
        document.addEventListener('click', function(e) {
            // Handle PRD selection
            if (e.target.classList.contains('prd-dropdown-option') || e.target.closest('.prd-dropdown-option')) {
                const optionEl = e.target.classList.contains('prd-dropdown-option') ? e.target : e.target.closest('.prd-dropdown-option');
                const selectedValue = optionEl.getAttribute('data-value');
                
                // Update UI
                if (selectorText) selectorText.textContent = selectedValue;
                if (prdSelector) prdSelector.value = selectedValue;
                
                // Update selected state
                document.querySelectorAll('.prd-dropdown-option').forEach(opt => {
                    opt.classList.remove('selected');
                });
                optionEl.classList.add('selected');
                
                // Close dropdown
                if (selectorDropdown) selectorDropdown.style.display = 'none';
                if (selectorButton) selectorButton.classList.remove('active');
                
                // Get project ID and load PRD
                const urlParams = new URLSearchParams(window.location.search);
                const urlProjectId = urlParams.get('project_id');
                let projectId = urlProjectId;
                
                if (!projectId) {
                    const pathMatch = window.location.pathname.match(/\/chat\/project\/([a-f0-9-]+)\//);
                    if (pathMatch && pathMatch[1]) {
                        projectId = pathMatch[1];
                    }
                }
                
                if (projectId && selectedValue) {
                    console.log(`[ArtifactsLoader] PRD selection changed to: ${selectedValue} for project: ${projectId}`);
                    window.ArtifactsLoader.loadPRD(projectId, selectedValue);
                }
            }
        });
        
        // Close dropdown when clicking outside
        document.addEventListener('click', function(e) {
            if (!e.target.closest('.prd-selector-wrapper')) {
                if (selectorDropdown) selectorDropdown.style.display = 'none';
                if (selectorButton) selectorButton.classList.remove('active');
            }
        });
        
        // Handle keyboard navigation
        if (selectorButton) {
            selectorButton.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    selectorButton.click();
                }
            });
        }
    }, 500); // Small delay to ensure elements are loaded
    
}); // End of DOMContentLoaded