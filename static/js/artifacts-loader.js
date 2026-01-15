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
    
    // Helper function to get current project ID from URL path only
    function getCurrentProjectId() {
        // Use the same logic as extractProjectIdFromPath in chat.js
        const pathParts = window.location.pathname.split('/').filter(part => part);
        if (pathParts.length >= 3 && pathParts[0] === 'chat' && pathParts[1] === 'project') {
            const projectId = pathParts[2];
            return projectId;
        }
        
        console.error('[ArtifactsLoader] No project ID found in path. Expected format: /chat/project/{id}/');
        throw new Error('No project ID found in path. Expected format: /chat/project/{id}/');
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

    // Initialize the artifact loaders immediately
    window.ArtifactsLoader = {
        /**
         * Get the current project ID from various sources
         * @returns {number|null} The current project ID or null if not found
         */
        getCurrentProjectId: getCurrentProjectId,
        ticketModalState: {
            list: [],
            index: -1,
            projectId: null,
            onEdit: null,
            onDelete: null,
            onExecute: null
        },
        _ticketModalElements: null,
        _ticketModalHelpers: null,
        getTicketModalHelpers: function() {
            if (this._ticketModalHelpers) {
                return this._ticketModalHelpers;
            }

            const self = this;
            const modalState = this.ticketModalState;
            let modalElements = this._ticketModalElements || {};
            let eventsBound = false;

            function escapeHtml(value) {
                if (value === null || value === undefined) {
                    return '';
                }
                return String(value)
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#39;');
            }

            function renderMarkdownContent(content) {
                if (!content) {
                    return '<p class="ticket-modal-empty">No description provided.</p>';
                }
                try {
                    if (typeof marked !== 'undefined') {
                        return marked.parse(content);
                    }
                } catch (error) {
                    console.error('[ArtifactsLoader] Error parsing markdown content:', error);
                }
                return escapeHtml(content).replace(/\n/g, '<br>');
            }

            function renderValueBlock(value) {
                if (value === null || value === undefined) {
                    return '';
                }
                if (Array.isArray(value)) {
                    if (value.length === 0) {
                        return '';
                    }
                    return `<ul>${value.map(item => `<li>${escapeHtml(typeof item === 'string' ? item : JSON.stringify(item))}</li>`).join('')}</ul>`;
                }
                if (typeof value === 'object') {
                    if (Object.keys(value).length === 0) {
                        return '';
                    }
                    return `<pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre>`;
                }
                if (typeof value === 'string') {
                    const trimmed = value.trim();
                    if (!trimmed || trimmed === '{}' || trimmed === '[]' || trimmed === 'null' || trimmed === 'undefined') {
                        return '';
                    }
                    return renderMarkdownContent(value);
                }
                return escapeHtml(String(value));
            }

            function formatExecutionNotes(notes) {
                if (!notes || !notes.trim()) {
                    return '<p class="ticket-modal-empty">No execution notes available.</p>';
                }

                const lines = notes.split('\n');
                let formattedHtml = '<div class="execution-notes-timeline">';

                for (let i = 0; i < lines.length; i++) {
                    const line = lines[i];

                    // Check if this line is a timestamp header like "[2025-01-04 12:30] Message"
                    const timestampMatch = line.match(/^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\]\s*(.+)$/);

                    if (timestampMatch) {
                        const timestamp = timestampMatch[1];
                        const message = timestampMatch[2];

                        // Determine the icon and class based on the message content
                        let icon = 'circle';
                        let itemClass = 'note-item';

                        if (message.toLowerCase().includes('started') || message.toLowerCase().includes('beginning')) {
                            icon = 'play-circle';
                            itemClass += ' note-item-start';
                        } else if (message.toLowerCase().includes('completed') || message.toLowerCase().includes('finished') || message.toLowerCase().includes('success')) {
                            icon = 'check-circle';
                            itemClass += ' note-item-success';
                        } else if (message.toLowerCase().includes('error') || message.toLowerCase().includes('failed')) {
                            icon = 'exclamation-circle';
                            itemClass += ' note-item-error';
                        } else if (message.toLowerCase().includes('iteration')) {
                            icon = 'sync';
                            itemClass += ' note-item-iteration';
                        } else if (message.toLowerCase().includes('workspace') || message.toLowerCase().includes('provisioning')) {
                            icon = 'server';
                            itemClass += ' note-item-workspace';
                        }

                        formattedHtml += `
                            <div class="${itemClass}">
                                <div class="note-icon">
                                    <i class="fas fa-${icon}"></i>
                                </div>
                                <div class="note-content">
                                    <div class="note-timestamp">${escapeHtml(timestamp)}</div>
                                    <div class="note-message">${escapeHtml(message)}</div>
                                </div>
                            </div>
                        `;
                    } else if (line.trim().startsWith('=') || line.trim().startsWith('-')) {
                        // Separator lines
                        if (line.trim().length > 10) {
                            formattedHtml += `<div class="note-separator"></div>`;
                        }
                    } else if (line.trim()) {
                        // Regular content lines (could be part of a multi-line note)
                        formattedHtml += `
                            <div class="note-item note-item-content">
                                <div class="note-content">
                                    <div class="note-message">${escapeHtml(line)}</div>
                                </div>
                            </div>
                        `;
                    }
                }

                formattedHtml += '</div>';
                return formattedHtml;
            }

            function formatStatus(value) {
                if (!value) {
                    return 'Open';
                }
                return value.replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase());
            }

            function formatTitleCase(value, fallback = '') {
                const source = value || fallback;
                if (!source) {
                    return '';
                }
                return String(source)
                    .toLowerCase()
                    .replace(/(^|\s|[_-])(\w)/g, (_, sep, char) => `${sep === '_' || sep === '-' ? ' ' : sep}${char.toUpperCase()}`)
                    .trim();
            }

            function slugify(value) {
                return String(value || '')
                    .toLowerCase()
                    .replace(/[^a-z0-9]+/g, '-')
                    .replace(/^-+|-+$/g, '') || 'default';
            }

            function applyPill(element, value, formatter, datasetKey) {
                if (!element) {
                    return;
                }
                if (!value) {
                    element.style.display = 'none';
                    element.textContent = '';
                    if (datasetKey) {
                        element.dataset[datasetKey] = '';
                    }
                    return;
                }
                const formatted = formatter ? formatter(value) : value;
                element.style.display = '';
                element.textContent = formatted;
                if (datasetKey) {
                    element.dataset[datasetKey] = slugify(value);
                }
            }

            function cacheModalElements() {
                const priorityElement = document.getElementById('ticket-modal-priority-text');

                modalElements = {
                    overlay: document.getElementById('ticket-modal-overlay'),
                    container: document.getElementById('ticket-modal'),
                    closeBtn: document.getElementById('ticket-modal-close'),
                    prevBtn: document.getElementById('ticket-modal-prev'),
                    nextBtn: document.getElementById('ticket-modal-next'),
                    editBtn: document.getElementById('ticket-modal-edit'),
                    logsBtn: document.getElementById('ticket-modal-logs'),
                    deleteBtn: document.getElementById('ticket-modal-delete'),
                    executeBtn: document.getElementById('ticket-modal-execute'),
                    name: document.getElementById('ticket-modal-name'),
                    subtitle: document.getElementById('ticket-modal-subtitle'),
                    status: document.getElementById('ticket-modal-status-chip'),
                    complexityChip: document.getElementById('ticket-modal-complexity-chip'),
                    priorityText: priorityElement,
                    priorityWrapper: priorityElement ? priorityElement.closest('.ticket-meta-inline-item') : null,
                    assigned: document.getElementById('ticket-modal-assigned'),
                    worktree: document.getElementById('ticket-modal-worktree'),
                    description: document.getElementById('ticket-modal-description'),
                    acceptanceSection: document.getElementById('ticket-modal-acceptance-section'),
                    acceptance: document.getElementById('ticket-modal-acceptance'),
                    detailsSection: document.getElementById('ticket-modal-details-section'),
                    details: document.getElementById('ticket-modal-details'),
                    uiSection: document.getElementById('ticket-modal-ui-section'),
                    ui: document.getElementById('ticket-modal-ui'),
                    specSection: document.getElementById('ticket-modal-spec-section'),
                    spec: document.getElementById('ticket-modal-spec'),
                    dependenciesSection: document.getElementById('ticket-modal-dependencies-section'),
                    dependencies: document.getElementById('ticket-modal-dependencies'),
                    linearSection: document.getElementById('ticket-modal-linear-section'),
                    linear: document.getElementById('ticket-modal-linear'),
                    notesSection: document.getElementById('ticket-modal-notes-section'),
                    notes: document.getElementById('ticket-modal-notes')
                };
                self._ticketModalElements = modalElements;
            }

            function updateNavigationControls() {
                if (!modalElements.prevBtn || !modalElements.nextBtn) {
                    return;
                }
                modalElements.prevBtn.disabled = modalState.index <= 0;
                modalElements.nextBtn.disabled = modalState.index >= modalState.list.length - 1 || modalState.list.length === 0;
            }

            function updateActionVisibility() {
                if (modalElements.editBtn) {
                    modalElements.editBtn.style.display = modalState.onEdit ? '' : 'none';
                }
                if (modalElements.deleteBtn) {
                    modalElements.deleteBtn.style.display = modalState.onDelete ? '' : 'none';
                }
                if (modalElements.executeBtn) {
                    modalElements.executeBtn.style.display = modalState.onExecute ? '' : 'none';
                }
            }

            function populateModal(ticket) {
                if (!ticket || !modalElements.container) {
                    return;
                }

                if (modalElements.name) {
                    modalElements.name.textContent = ticket.name || 'Untitled Ticket';
                }
                if (modalElements.subtitle) {
                    modalElements.subtitle.textContent = ticket.id ? `Ticket #${ticket.id}` : '';
                }
                if (modalElements.status) {
                    applyPill(modalElements.status, ticket.status || 'open', value => formatStatus(value).toUpperCase(), 'state');
                }
                if (modalElements.complexityChip) {
                    const complexityLabel = ticket.complexity || 'medium';
                    applyPill(modalElements.complexityChip, complexityLabel, value => formatTitleCase(value, 'Medium').toUpperCase(), 'level');
                }
                if (modalElements.priorityText) {
                    const priorityValue = formatTitleCase(ticket.priority, '');
                    if (priorityValue) {
                        modalElements.priorityText.textContent = priorityValue;
                        if (modalElements.priorityWrapper) {
                            modalElements.priorityWrapper.style.display = 'inline-flex';
                        }
                    } else {
                        modalElements.priorityText.textContent = '';
                        if (modalElements.priorityWrapper) {
                            modalElements.priorityWrapper.style.display = 'none';
                        }
                    }
                }
                if (modalElements.assigned) {
                    modalElements.assigned.textContent = formatTitleCase(ticket.role, 'Agent');
                }
                if (modalElements.worktree) {
                    modalElements.worktree.textContent = ticket.requires_worktree ? 'Required' : 'Not Required';
                }
                if (modalElements.description) {
                    modalElements.description.innerHTML = renderMarkdownContent(ticket.description || '');
                }

                if (modalElements.acceptanceSection) {
                    if (ticket.acceptance_criteria && ticket.acceptance_criteria.length > 0) {
                        modalElements.acceptanceSection.style.display = '';
                        modalElements.acceptance.innerHTML = `<ul>${ticket.acceptance_criteria.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`;
                    } else {
                        modalElements.acceptanceSection.style.display = 'none';
                        modalElements.acceptance.innerHTML = '';
                    }
                }

                if (modalElements.detailsSection) {
                    if (ticket.details && Object.keys(ticket.details || {}).length > 0) {
                        modalElements.detailsSection.style.display = '';
                        modalElements.details.innerHTML = `<pre>${escapeHtml(JSON.stringify(ticket.details, null, 2))}</pre>`;
                    } else {
                        modalElements.detailsSection.style.display = 'none';
                        modalElements.details.innerHTML = '';
                    }
                }

                if (modalElements.uiSection) {
                    const uiContent = renderValueBlock(ticket.ui_requirements);
                    if (uiContent) {
                        modalElements.uiSection.style.display = '';
                        modalElements.ui.innerHTML = uiContent;
                    } else {
                        modalElements.uiSection.style.display = 'none';
                        modalElements.ui.innerHTML = '';
                    }
                }

                if (modalElements.specSection) {
                    const specContent = renderValueBlock(ticket.component_specs);
                    if (specContent) {
                        modalElements.specSection.style.display = '';
                        modalElements.spec.innerHTML = specContent;
                    } else {
                        modalElements.specSection.style.display = 'none';
                        modalElements.spec.innerHTML = '';
                    }
                }

                if (modalElements.dependenciesSection) {
                    if (ticket.dependencies && ticket.dependencies.length > 0) {
                        modalElements.dependenciesSection.style.display = '';
                        modalElements.dependencies.innerHTML = `<ul>${ticket.dependencies.map(dep => `<li>${escapeHtml(dep)}</li>`).join('')}</ul>`;
                    } else {
                        modalElements.dependenciesSection.style.display = 'none';
                        modalElements.dependencies.innerHTML = '';
                    }
                }

                if (modalElements.linearSection) {
                    if (ticket.linear_issue_id) {
                        modalElements.linearSection.style.display = '';
                        const parts = [];
                        if (ticket.linear_state) {
                            parts.push(`<p><strong>State:</strong> ${escapeHtml(ticket.linear_state)}</p>`);
                        }
                        if (ticket.linear_issue_url) {
                            parts.push(`<p><a href="${escapeHtml(ticket.linear_issue_url)}" target="_blank" rel="noopener" class="ticket-modal-link">View in Linear</a></p>`);
                        }
                        if (ticket.linear_synced_at) {
                            parts.push(`<p class="ticket-modal-subtext">Last synced: ${new Date(ticket.linear_synced_at).toLocaleString()}</p>`);
                        }
                        modalElements.linear.innerHTML = parts.join('') || '<p>No Linear metadata available.</p>';
                    } else {
                        modalElements.linearSection.style.display = 'none';
                        modalElements.linear.innerHTML = '';
                    }
                }

                if (modalElements.notesSection) {
                    if (ticket.notes && ticket.notes.trim()) {
                        modalElements.notesSection.style.display = '';
                        modalElements.notes.innerHTML = formatExecutionNotes(ticket.notes);
                    } else {
                        modalElements.notesSection.style.display = 'none';
                        modalElements.notes.innerHTML = '';
                    }
                }

                modalElements.container.scrollTop = 0;
                if (modalElements.description && modalElements.description.classList.contains('markdown-content')) {
                    modalElements.description.setAttribute('data-raw-content', ticket.description || '');
                }
            }

            function ensureModal() {
                if (!document.getElementById('ticket-modal-overlay')) {
                    const overlay = document.createElement('div');
                    overlay.id = 'ticket-modal-overlay';
                    overlay.className = 'ticket-modal-overlay';
                    overlay.setAttribute('aria-hidden', 'true');
                    overlay.innerHTML = `
                        <div class="ticket-modal" id="ticket-modal" role="dialog" aria-modal="true" aria-labelledby="ticket-modal-name" tabindex="-1">
                            <div class="ticket-modal-header">
                                <div class="ticket-modal-nav">
                                    <button type="button" class="ticket-modal-nav-btn" id="ticket-modal-prev" title="Previous ticket">
                                        <i class="fas fa-chevron-left"></i>
                                    </button>
                                    <button type="button" class="ticket-modal-nav-btn" id="ticket-modal-next" title="Next ticket">
                                        <i class="fas fa-chevron-right"></i>
                                    </button>
                                </div>
                                <div class="ticket-modal-header-actions">
                                    <div class="ticket-chip-group">
                                        <span class="ticket-chip ticket-status-chip" id="ticket-modal-status-chip"></span>
                                        <span class="ticket-chip ticket-complexity-chip" id="ticket-modal-complexity-chip"></span>
                                    </div>
                                    <button type="button" class="ticket-modal-close" id="ticket-modal-close" title="Close ticket details">
                                        <i class="fas fa-times"></i>
                                    </button>
                                </div>
                            </div>
                            <div class="ticket-modal-header-content">
                                <div class="ticket-modal-title-group">
                                    <p class="ticket-modal-context">Ticket overview</p>
                                    <h2 class="ticket-modal-name" id="ticket-modal-name"></h2>
                                    <p class="ticket-modal-subtitle" id="ticket-modal-subtitle"></p>
                                </div>
                                <div class="ticket-meta-inline" id="ticket-modal-summary">
                                    <div class="ticket-meta-inline-item">
                                        <span class="ticket-meta-inline-label">Assignee</span>
                                        <span class="ticket-meta-inline-value" id="ticket-modal-assigned"></span>
                                    </div>
                                    <div class="ticket-meta-inline-item">
                                        <span class="ticket-meta-inline-label">Worktree</span>
                                        <span class="ticket-meta-inline-value" id="ticket-modal-worktree"></span>
                                    </div>
                                    <div class="ticket-meta-inline-item">
                                        <span class="ticket-meta-inline-label">Priority</span>
                                        <span class="ticket-meta-inline-value" id="ticket-modal-priority-text"></span>
                                    </div>
                                </div>
                            </div>
                            <div class="ticket-modal-body">
                                <section class="ticket-modal-section">
                                    <header class="ticket-section-header">
                                        <div class="ticket-section-title">
                                            <i class="fas fa-align-left"></i>
                                            <h4>Description</h4>
                                        </div>
                                        <span class="ticket-section-label">Rich markdown</span>
                                    </header>
                                    <div id="ticket-modal-description" class="ticket-modal-description markdown-content"></div>
                                </section>
                                <section class="ticket-modal-section" id="ticket-modal-acceptance-section">
                                    <header class="ticket-section-header">
                                        <div class="ticket-section-title">
                                            <i class="fas fa-clipboard-check"></i>
                                            <h4>Acceptance Criteria</h4>
                                        </div>
                                        <span class="ticket-section-label">Delivery checklist</span>
                                    </header>
                                    <div id="ticket-modal-acceptance"></div>
                                </section>
                                <section class="ticket-modal-section" id="ticket-modal-details-section">
                                    <header class="ticket-section-header">
                                        <div class="ticket-section-title">
                                            <i class="fas fa-microchip"></i>
                                            <h4>Technical Details</h4>
                                        </div>
                                        <span class="ticket-section-label">Implementation notes</span>
                                    </header>
                                    <div id="ticket-modal-details"></div>
                                </section>
                                <section class="ticket-modal-section" id="ticket-modal-ui-section">
                                    <header class="ticket-section-header">
                                        <div class="ticket-section-title">
                                            <i class="fas fa-layer-group"></i>
                                            <h4>UI Requirements</h4>
                                        </div>
                                        <span class="ticket-section-label">Screens & flows</span>
                                    </header>
                                    <div id="ticket-modal-ui"></div>
                                </section>
                                <section class="ticket-modal-section" id="ticket-modal-spec-section">
                                    <header class="ticket-section-header">
                                        <div class="ticket-section-title">
                                            <i class="fas fa-project-diagram"></i>
                                            <h4>Component Specs</h4>
                                        </div>
                                        <span class="ticket-section-label">Interfaces & contracts</span>
                                    </header>
                                    <div id="ticket-modal-spec"></div>
                                </section>
                                <section class="ticket-modal-section" id="ticket-modal-dependencies-section">
                                    <header class="ticket-section-header">
                                        <div class="ticket-section-title">
                                            <i class="fas fa-link"></i>
                                            <h4>Dependencies</h4>
                                        </div>
                                        <span class="ticket-section-label">Prerequisites</span>
                                    </header>
                                    <div id="ticket-modal-dependencies"></div>
                                </section>
                                <section class="ticket-modal-section" id="ticket-modal-linear-section">
                                    <header class="ticket-section-header">
                                        <div class="ticket-section-title">
                                            <i class="fas fa-plug"></i>
                                            <h4>Linear Integration</h4>
                                        </div>
                                        <span class="ticket-section-label">Sync state</span>
                                    </header>
                                    <div id="ticket-modal-linear"></div>
                                </section>
                                <section class="ticket-modal-section" id="ticket-modal-notes-section">
                                    <header class="ticket-section-header">
                                        <div class="ticket-section-title">
                                            <i class="fas fa-clipboard-list"></i>
                                            <h4>Execution Notes</h4>
                                        </div>
                                        <span class="ticket-section-label">Build logs & progress</span>
                                    </header>
                                    <div id="ticket-modal-notes" class="ticket-execution-notes"></div>
                                </section>
                            </div>
                            <div class="ticket-modal-footer">
                                <button type="button" class="ticket-modal-secondary" id="ticket-modal-edit">
                                    <i class="fas fa-pen"></i> Edit ticket
                                </button>
                                <button type="button" class="ticket-modal-info" id="ticket-modal-logs" title="View execution logs">
                                    <i class="fas fa-terminal"></i> View Logs
                                </button>
                                <button type="button" class="ticket-modal-danger" id="ticket-modal-delete">
                                    <i class="fas fa-trash"></i> Delete
                                </button>
                                <button type="button" class="ticket-modal-primary" id="ticket-modal-execute">
                                    <i class="fas fa-play"></i> Execute (Build Now)
                                </button>
                            </div>
                        </div>
                    `;
                    document.body.appendChild(overlay);
                }

                cacheModalElements();

                if (!eventsBound && modalElements.overlay) {
                    eventsBound = true;

                    modalElements.overlay.addEventListener('click', function(event) {
                        if (event.target === modalElements.overlay) {
                            helpers.close();
                        }
                    });

                    if (modalElements.closeBtn) {
                        modalElements.closeBtn.addEventListener('click', function() {
                            helpers.close();
                        });
                    }

                    if (modalElements.prevBtn) {
                        modalElements.prevBtn.addEventListener('click', function() {
                            helpers.openAtIndex(modalState.index - 1);
                        });
                    }

                    if (modalElements.nextBtn) {
                        modalElements.nextBtn.addEventListener('click', function() {
                            helpers.openAtIndex(modalState.index + 1);
                        });
                    }

                    if (modalElements.editBtn) {
                        modalElements.editBtn.addEventListener('click', function() {
                            if (modalState.onEdit) {
                                modalState.onEdit(helpers.getCurrentTicket(), helpers);
                            }
                        });
                    }

                    if (modalElements.deleteBtn) {
                        modalElements.deleteBtn.addEventListener('click', function() {
                            if (!modalState.onDelete) {
                                return;
                            }
                            const result = modalState.onDelete(helpers.getCurrentTicket(), helpers);
                            if (result && typeof result.then === 'function') {
                                modalElements.deleteBtn.disabled = true;
                                result.finally(() => {
                                    modalElements.deleteBtn.disabled = false;
                                });
                            }
                        });
                    }

                    if (modalElements.executeBtn) {
                        modalElements.executeBtn.addEventListener('click', function() {
                            if (modalState.onExecute) {
                                modalState.onExecute(helpers.getCurrentTicket(), helpers);
                            }
                        });
                    }

                    if (modalElements.logsBtn) {
                        modalElements.logsBtn.addEventListener('click', function() {
                            const ticket = helpers.getCurrentTicket();
                            if (modalState.onViewLogs) {
                                modalState.onViewLogs(ticket, helpers);
                            } else {
                                console.warn('[TicketModal] No onViewLogs handler registered');
                            }
                        });
                    } else {
                        console.warn('[TicketModal] Logs button element not found');
                    }

                    document.addEventListener('keydown', function(event) {
                        if (!modalElements.overlay || !modalElements.overlay.classList.contains('active')) {
                            return;
                        }
                        if (event.key === 'Escape') {
                            helpers.close();
                        } else if (event.key === 'ArrowRight') {
                            helpers.openAtIndex(modalState.index + 1);
                        } else if (event.key === 'ArrowLeft') {
                            helpers.openAtIndex(modalState.index - 1);
                        }
                    });
                }

                updateActionVisibility();
                return modalElements;
            }

            const helpers = {
                escapeHtml,
                renderMarkdownContent,
                setProjectId(projectId) {
                    modalState.projectId = projectId;
                },
                setHandlers(handlers = {}) {
                    modalState.onEdit = handlers.onEdit || null;
                    modalState.onDelete = handlers.onDelete || null;
                    modalState.onExecute = handlers.onExecute || null;
                    modalState.onViewLogs = handlers.onViewLogs || null;
                    ensureModal();
                    updateActionVisibility();
                },
                ensure: ensureModal,
                getCurrentTicket() {
                    if (modalState.index < 0 || modalState.index >= modalState.list.length) {
                        return null;
                    }
                    return modalState.list[modalState.index];
                },
                open(list, index) {
                    ensureModal();
                    modalState.list = Array.isArray(list) ? list.slice() : [];
                    this.openAtIndex(index);
                },
                openAtIndex(index) {
                    ensureModal();
                    if (index < 0 || index >= modalState.list.length) {
                        return;
                    }
                    modalState.index = index;
                    populateModal(this.getCurrentTicket());
                    updateNavigationControls();
                    if (modalElements.overlay) {
                        modalElements.overlay.classList.add('active');
                        modalElements.overlay.setAttribute('aria-hidden', 'false');
                    }
                    if (modalElements.container) {
                        modalElements.container.focus({ preventScroll: true });
                    }
                    document.body.classList.add('ticket-modal-open');
                },
                close() {
                    ensureModal();
                    if (modalElements.overlay) {
                        modalElements.overlay.classList.remove('active');
                        modalElements.overlay.setAttribute('aria-hidden', 'true');
                    }
                    document.body.classList.remove('ticket-modal-open');
                    modalState.index = -1;
                }
            };

            this._ticketModalElements = modalElements;
            this._ticketModalHelpers = helpers;
            return helpers;
        },
        
        /**
         * Load features from the API for the current project
         * @param {number} projectId - The ID of the current project
         */
        loadFeatures: function(projectId) {
            
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
            featuresTab.innerHTML = '<div class="loading-state"><div class="spinner"></div><div>Loading features...</div></div>';
            
            // Fetch features from API
            const url = `/projects/${projectId}/api/features/`;
            
            fetch(url)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    // Process features data
                    const features = data.features || [];
                    
                    if (features.length === 0) {
                        // Show empty state if no features found
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
            personasTab.innerHTML = '<div class="loading-state"><div class="spinner"></div><div>Loading personas...</div></div>';
            
            // Fetch personas from API
            const url = `/projects/${projectId}/api/personas/`;
            
            fetch(url)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    // Process personas data
                    const personas = data.personas || [];
                    
                    if (personas.length === 0) {
                        // Show empty state if no personas found
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
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading PRD');
                return;
            }
            
            // Check if we're currently streaming PRD content
            if (window.prdStreamingState && window.prdStreamingState.isStreaming) {
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
            if (prdContainer && streamingStatus) {
                prdContainer.style.display = 'block';
                streamingStatus.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Loading PRDs...';
                streamingStatus.style.color = '#8b5cf6';
            }
            
            // First fetch the list of PRDs
            const listUrl = `/projects/${projectId}/api/prd/?list=1`;
            
            fetch(listUrl)
                .then(response => response.json())
                .then(listData => {
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
                            
                        } else {
                            // Hide selector if only one PRD
                            if (selectorWrapper) selectorWrapper.style.display = 'none';
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
                    
                    return fetch(url);
                })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    // Process PRD data
                    const prdContent = data.content || '';
                    
                    if (!prdContent) {
                        // Show empty state if no PRD found
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
                                }
                                
                                parsedContent = marked.parse(prdContent);
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
                            ArtifactsLoader.downloadFileAsPDF(projectId, data.title || 'Product Requirement Document', prdContent);
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
         * Unified document streaming function for PRD and Implementation
         * @param {string} contentChunk - The chunk of content to append
         * @param {boolean} isComplete - Whether this is the final chunk
         * @param {number} projectId - The ID of the current project
         * @param {string} documentType - Type of document ('prd' or 'implementation')
         * @param {string} documentName - Name of the document
         * @param {number} fileId - The file ID (optional, provided when document is saved)
         */
        streamDocumentContent: function(contentChunk, isComplete, projectId, documentType, documentName) {
            console.log(`  Type: ${documentType}, Name: ${documentName}`);
            console.log(`  Chunk length: ${contentChunk ? contentChunk.length : 0}, isComplete: ${isComplete}`);
            console.log(`  Project ID: ${projectId}`);
            
        
            // Ensure filebrowser tab is active
            const filebrowserTab = document.querySelector('.tab-button[data-tab="filebrowser"]');
            const filebrowserPane = document.getElementById('filebrowser');
            if (filebrowserTab && !filebrowserTab.classList.contains('active')) {
                document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
                document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
                filebrowserTab.classList.add('active');
                if (filebrowserPane) filebrowserPane.classList.add('active');
            }
            
            // Initialize streaming state
            const stateKey = `${documentType}StreamingState`;
            if (!window[stateKey]) {
                window[stateKey] = {
                    fullContent: '',
                    isStreaming: false,
                    projectId: projectId,
                    documentName: documentName,
                    documentType: documentType
                };
            }
            
            // Get or create streaming viewer
            const filebrowserViewer = document.getElementById('filebrowser-viewer');
            const filebrowserMain = document.getElementById('filebrowser-main');
            
            if (!filebrowserViewer || !filebrowserMain) {
                console.error('[ArtifactsLoader] File browser elements not found');
                return;
            }
            
            // Start streaming if not already started
            if (!window[stateKey].isStreaming) {
                window[stateKey].isStreaming = true;
                window[stateKey].fullContent = '';
                window[stateKey].projectId = projectId;
                
                // Switch to viewer mode
                filebrowserMain.style.display = 'none';
                filebrowserViewer.style.display = 'flex';
                
                // Set viewer title with edit button
                const viewerTitle = document.getElementById('viewer-title');
                if (viewerTitle) {
                    viewerTitle.innerHTML = `
                        <span id="viewer-title-text">Generating...</span>
                        <button id="viewer-title-edit" style="background: none; border: none; color: #9ca3af; cursor: pointer; margin-left: 8px; padding: 4px; opacity: 0.7;" title="Edit name" disabled>
                            <i class="fas fa-pencil" style="font-size: 12px;"></i>
                        </button>
                    `;
                }
                
                // Clear viewer content but keep the structure
                const viewerMarkdown = document.getElementById('viewer-markdown');
                if (viewerMarkdown) {
                    viewerMarkdown.innerHTML = '';
                }
                
                // Hide action buttons during streaming
                const viewerActions = document.querySelector('.viewer-actions');
                if (viewerActions) {
                    viewerActions.style.display = 'none';
                }
                
                // Show streaming status in metadata area
                const viewerMeta = document.getElementById('viewer-meta');
                if (viewerMeta) {
                    viewerMeta.innerHTML = `
                        <span style="color: #8b5cf6;"><i class="fas fa-circle-notch fa-spin"></i> Generating ${documentType}...</span>
                    `;
                    viewerMeta.style.display = 'flex';
                }
                
                // Make sure back button is visible
                const backButton = document.querySelector('.viewer-back');
                if (backButton) {
                    backButton.style.display = 'flex';
                }
                
                // Open artifacts panel if not already open
                if (window.ArtifactsPanel && !window.ArtifactsPanel.isOpen()) {
                    window.ArtifactsPanel.open();
                }
            }
            
            // Append content chunk
            if (contentChunk) {
                window[stateKey].fullContent += contentChunk;
                
                // Update viewer content
                const viewerMarkdown = document.getElementById('viewer-markdown');
                if (viewerMarkdown && typeof marked !== 'undefined') {
                    const renderedHTML = marked.parse(window[stateKey].fullContent);
                    viewerMarkdown.innerHTML = renderedHTML;
                } else if (viewerMarkdown) {
                    // Fallback to plain text
                    viewerMarkdown.innerHTML = window[stateKey].fullContent
                        .replace(/\n/g, '<br>')
                        .replace(/\t/g, '&nbsp;&nbsp;&nbsp;&nbsp;');
                }
                
                // Auto-scroll to show new content
                if (viewerMarkdown) {
                    // Use requestAnimationFrame to ensure DOM has updated before scrolling
                    // Use instant scroll (not smooth) during streaming for better UX
                    requestAnimationFrame(() => {
                        requestAnimationFrame(() => {
                            const before = viewerMarkdown.scrollTop;
                            const scrollHeight = viewerMarkdown.scrollHeight;
                            viewerMarkdown.scrollTop = scrollHeight;
                        });
                    });
                }
            }
            
            // Store streaming info for handleDocumentSaved to use later
            // This is crucial for the save notification to work properly
            window[`${documentType}StreamingInfo`] = {
                projectId: projectId,
                documentName: documentName,
                documentType: documentType,
                viewerTitle: `${documentType.toUpperCase()} - ${documentName}`
            };
        },
        
        /**
         * Handle save notification after document is saved
         */
        handleDocumentSaved: function(notification) {
            
            const documentType = notification.file_type || notification.notification_type;
            console.log('[ArtifactsLoader] Available streaming info keys:', Object.keys(window).filter(k => k.includes('StreamingInfo')));
            
            // Also check for all possible streaming info variations
            
            const streamingInfo = window[`${documentType}StreamingInfo`];
            
            if (!streamingInfo) {
                // Don't return, continue to load the file
            }
            
            // Clear the streaming info if it exists
            if (streamingInfo) {
                window[`${documentType}StreamingInfo`] = null;
            }
            
            // Get project ID and file ID
            // Priority: notification.project_id > streamingInfo.projectId > window.currentProjectId
            const projectId = notification.project_id || streamingInfo?.projectId || window.currentProjectId;
            const documentName = streamingInfo?.documentName || notification.file_name;
            const viewerTitle = streamingInfo?.viewerTitle || `${documentType.toUpperCase()} - ${documentName}`;
            const fileId = notification.file_id;
            
            console.log(`[ArtifactsLoader] Using project ID: ${projectId} (from: ${notification.project_id ? 'notification' : streamingInfo?.projectId ? 'streamingInfo' : 'window.currentProjectId'})`)
            
            if (!fileId) {
                console.error('[ArtifactsLoader] No file_id in save notification');
                return;
            }
            
            
            // Ensure the viewFileContent function is available globally
            if (window.viewFileContent) {
                // Add a small delay to ensure UI is ready after streaming completes
                setTimeout(() => {
                    window.viewFileContent(fileId, documentName);
                }, 100);
            } else {
                console.error('[ArtifactsLoader] viewFileContent function not available globally');
            }
            
        },
        
        
        /**
         * Save streamed document to the server
         */
        saveStreamedDocument: function(documentType, projectId) {
            const stateKey = `${documentType}StreamingState`;
            const state = window[stateKey];
            
            if (!state || !state.fullContent) {
                console.error('No content to save');
                return;
            }
            
            // Show saving indicator
            const viewerTitle = document.getElementById('viewer-title');
            if (viewerTitle) {
                viewerTitle.textContent = `${state.documentName} (Saving...)`;
            }
            
            // Create document via API
            const payload = {
                name: state.documentName,
                type: documentType,
                content: state.fullContent,
                project_id: projectId
            };
            
            fetch(`/projects/${projectId}/documents/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify(payload)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success && data.file_id) {
                    window.showToast('Document saved successfully', 'success');
                    // Clear the streaming state
                    window[stateKey] = null;
                    
                    // Reload the file browser and open the saved document
                    this.loadFileBrowser(projectId, {
                        openFileId: data.file_id,
                        openFileName: state.documentName
                    });
                } else {
                    window.showToast('Error saving document', 'error');
                    if (viewerTitle) {
                        viewerTitle.textContent = state.documentName;
                    }
                }
            })
            .catch(error => {
                console.error('Error saving document:', error);
                window.showToast('Error saving document', 'error');
                if (viewerTitle) {
                    viewerTitle.textContent = state.documentName;
                }
            });
        },
        
        /**
         * Download streamed document
         */
        downloadStreamedDocument: function(documentType, documentName) {
            const stateKey = `${documentType}StreamingState`;
            const state = window[stateKey];
            
            if (!state || !state.fullContent) {
                console.error('No content to download');
                return;
            }
            
            // Create a blob and download
            const blob = new Blob([state.fullContent], { type: 'text/markdown' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${documentName}.md`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        },
        
        /**
         * Load implementation from the API for the current project
         * @param {number} projectId - The ID of the current project
         */
        loadImplementation: function(projectId) {
            
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
            implementationTab.innerHTML = '<div class="loading-state"><div class="spinner"></div><div>Loading implementation...</div></div>';
            
            // Fetch implementation from API
            const url = `/projects/${projectId}/api/implementation/`;
            
            fetch(url)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    // Process implementation data
                    const implementationContent = data.content || '';
                    
                    if (!implementationContent) {
                        // Show empty state if no implementation found
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

            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading tickets');
                return;
            }

            const ticketsTab = document.getElementById('tickets');
            if (!ticketsTab) {
                console.warn('[ArtifactsLoader] Tickets tab element not found');
                return;
            }

            const modalHelpers = this.getTicketModalHelpers();
            modalHelpers.setProjectId(projectId);

            const getCsrfToken = () => {
                if (typeof getCookie === 'function') {
                    return getCookie('csrftoken');
                }
                if (typeof window.getCookie === 'function') {
                    return window.getCookie('csrftoken');
                }
                return '';
            };

            const deleteTicket = (ticket) => {
                if (!ticket) {
                    console.warn('[ArtifactsLoader] Attempted to delete an unknown ticket');
                    return Promise.resolve(false);
                }

                if (!confirm(`Are you sure you want to delete the ticket "${ticket.name}"?`)) {
                    return Promise.resolve(false);
                }

                return fetch(`/projects/${projectId}/api/checklist/${ticket.id}/delete/`, {
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': getCsrfToken()
                    }
                })
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Failed to delete ticket');
                    }
                    return response.json().catch(() => ({}));
                })
                .then(() => {
                    window.showToast('Ticket deleted successfully', 'success');
                    ArtifactsLoader.loadTickets(projectId);
                    return true;
                })
                .catch(error => {
                    console.error('Error deleting ticket:', error);
                    window.showToast('Error deleting ticket', 'error');
                    return false;
                });
            };

            ticketsTab.innerHTML = '<div class="loading-state"><div class="spinner"></div><div>Loading tickets...</div></div>';

            const url = `/projects/${projectId}/api/checklist/`;

            fetch(url)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    const tickets = data.tickets || [];

                    if (tickets.length === 0) {
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
                        modalHelpers.setHandlers();
                        return;
                    }

                    const priorities = [...new Set(tickets.map(ticket => ticket.priority || 'Medium'))].sort();

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
                            <div class="tickets-content" id="tickets-content"></div>
                        </div>
                    `;

                    const ticketsContent = document.getElementById('tickets-content');
                    const priorityFilter = document.getElementById('priority-filter');
                    const clearFiltersBtn = document.getElementById('clear-filters');
                    const syncLinearBtn = document.getElementById('sync-linear');

                    modalHelpers.ensure();
                    modalHelpers.setHandlers({
                        onEdit: (ticket) => {
                            modalHelpers.close();
                            if (typeof window.editChecklistItem === 'function' && ticket) {
                                window.editChecklistItem(ticket.id);
                            }
                        },
                        onDelete: (ticket) => deleteTicket(ticket).then((removed) => {
                            if (removed) {
                                modalHelpers.close();
                            }
                            return removed;
                        }),
                        onExecute: (ticket) => {
                            if (ticket) {
                                ArtifactsLoader.executeTicket(ticket.id);
                            }
                        },
                        onViewLogs: (ticket) => {
                            if (ticket) {
                                ArtifactsLoader.showTicketLogs(ticket.id);
                            }
                        }
                    });

                    const renderTickets = (filterPriority = 'all') => {
                        let filteredTickets = [...tickets];
                        if (filterPriority !== 'all') {
                            filteredTickets = filteredTickets.filter(ticket => (ticket.priority || 'Medium') === filterPriority);
                        }

                        let html = '<div class="tickets-by-status">';

                        if (filteredTickets.length === 0) {
                            html += `
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
                                const isHighlighted = filterPriority !== 'all' && (ticket.priority || 'Medium') === filterPriority;

                                let summary = ticket.description || '';
                                const descriptionLimit = 300;
                                if (summary.length > descriptionLimit) {
                                    const lastSpaceIndex = summary.lastIndexOf(' ', descriptionLimit);
                                    const truncateIndex = lastSpaceIndex > 0 ? lastSpaceIndex : descriptionLimit;
                                    summary = `${summary.substring(0, truncateIndex)}...`;
                                }
                                summary = modalHelpers.escapeHtml(summary).replace(/\n/g, '<br>');

                                html += `
                                    <div class="ticket-card" data-ticket-id="${ticket.id}" data-priority="${ticket.priority || 'Medium'}">
                                        <div class="card-header ${status}">
                                            <h4 class="card-title">${modalHelpers.escapeHtml(ticket.name || 'Untitled Ticket')}</h4>
                                        </div>
                                        <div class="card-body">
                                            <div class="card-description">${summary}</div>
                                            <div class="card-meta">
                                                <div class="card-tags">
                                                    <span class="priority-tag ${priorityClass} ${isHighlighted ? 'filter-active' : ''}">
                                                        <i class="fas fa-flag"></i> ${modalHelpers.escapeHtml(ticket.priority || 'Medium')} Priority
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
                                                <button class="view-details-btn" data-index="${filteredTickets.indexOf(ticket)}" title="View details">
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

                        html += '</div>';
                        ticketsContent.innerHTML = html;

                        const detailButtons = ticketsContent.querySelectorAll('.view-details-btn');
                        detailButtons.forEach((button, index) => {
                            button.addEventListener('click', function(event) {
                                event.stopPropagation();
                                modalHelpers.open(filteredTickets, index);
                            });
                        });

                        const deleteButtons = ticketsContent.querySelectorAll('.delete-ticket-btn');
                        deleteButtons.forEach(button => {
                            button.addEventListener('click', function(event) {
                                event.stopPropagation();
                                const ticketId = parseInt(this.getAttribute('data-ticket-id'), 10);
                                const ticket = tickets.find(t => t.id === ticketId);
                                deleteTicket(ticket);
                            });
                        });
                    };

                    if (priorityFilter) {
                        priorityFilter.addEventListener('change', function() {
                            renderTickets(this.value);
                        });
                    }

                    if (clearFiltersBtn) {
                        clearFiltersBtn.addEventListener('click', function() {
                            if (priorityFilter) {
                                priorityFilter.value = 'all';
                            }
                            renderTickets('all');
                        });
                    }

                    if (syncLinearBtn) {
                        syncLinearBtn.addEventListener('click', function() {
                            if (!data.linear_sync_enabled) {
                                window.showToast('Linear sync is not enabled for this project. Please go to project settings to configure Linear integration.', 'error');
                                return;
                            }

                            const button = this;
                            button.disabled = true;
                            button.innerHTML = '<i class="fas fa-sync fa-spin"></i> Syncing...';

                            fetch(`/projects/${projectId}/api/linear/sync/`, {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                    'X-CSRFToken': getCsrfToken()
                                }
                            })
                            .then(response => response.json())
                            .then(syncData => {
                                if (syncData.success) {
                                    window.showToast(syncData.message || 'Tickets synced successfully!', 'success');
                                    ArtifactsLoader.loadTickets(projectId);
                                } else {
                                    if (syncData.error && syncData.error.includes('API key not configured')) {
                                        window.showToast('Linear API key not configured. Please go to Integrations to add your Linear API key.', 'error');
                                    } else if (syncData.error && syncData.error.includes('team ID not set')) {
                                        window.showToast('Linear team ID not set. Please go to project settings to configure Linear integration.', 'error');
                                    } else {
                                        window.showToast(syncData.error || 'Failed to sync tickets', 'error');
                                    }
                                    button.disabled = false;
                                    button.innerHTML = '<i class="fas fa-sync"></i> Sync with Linear';
                                }
                            })
                            .catch(error => {
                                console.error('Error syncing with Linear:', error);
                                window.showToast('Error syncing with Linear', 'error');
                                button.disabled = false;
                                button.innerHTML = '<i class="fas fa-sync"></i> Sync with Linear';
                            });
                        });
                    }

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
        
        closeTicketModal: function() {
            const helpers = this.getTicketModalHelpers();
            helpers.close();
        },
        
        /**
         * Load design schema from the API for the current project
         * @param {number} projectId - The ID of the current project
         */
        loadDesignSchema: function(projectId) {
            
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
            designTab.innerHTML = '<div class="loading-state"><div class="spinner"></div><div>Loading design schema...</div></div>';
            
            // Fetch design schema from API
            const url = `/projects/${projectId}/api/design-schema/`;
            
            fetch(url)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    // Process design schema data
                    const designSchemaContent = data.content || '';
                    
                    if (!designSchemaContent) {
                        // Show empty state if no design schema found
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
            codebaseLoading.style.display = 'block';
            codebaseEmpty.style.display = 'none';
            codebaseFrameContainer.style.display = 'none';
            
            // Get conversation ID using the helper function
            const conversationId = getCurrentConversationId();
            
            // Build the editor URL with appropriate parameters
            let editorUrl = `/development/editor/?project_id=${projectId}`;
            
            // Add conversation ID if available
            if (conversationId) {
                editorUrl += `&conversation_id=${conversationId}`;
            }
            
            
            // Set up iframe event handlers
            codebaseIframe.onload = function() {
                // Hide loading and show iframe when loaded
                codebaseLoading.style.display = 'none';
                codebaseFrameContainer.style.display = 'block';
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
            codebaseIframe.src = editorUrl;
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
            checklistTab.innerHTML = '<div class="loading-state"><div class="spinner"></div><div>Loading checklist...</div></div>';
            
            // Fetch checklist from API
            const checklistUrl = `/projects/${projectId}/api/checklist/`;
            
            fetch(checklistUrl)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    // Process checklist data
                    const checklist = data.tickets || [];

                    const modalHelpers = this.getTicketModalHelpers();
                    modalHelpers.setProjectId(projectId);
                    
                    if (checklist.length === 0) {
                        // Show empty state if no checklist items found
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
                    // Check current theme for styling
                    const isLightTheme = document.documentElement.getAttribute('data-theme') === 'light';
                    const headerBtnBg = isLightTheme ? '#f1f5f9' : 'rgba(40, 40, 40, 0.8)';
                    const headerBtnColor = isLightTheme ? '#64748b' : '#888';
                    const headerBtnBorder = isLightTheme ? '1px solid #e2e8f0' : '1px solid rgba(255, 255, 255, 0.08)';
                    const headerBtnHoverBg = isLightTheme ? '#e2e8f0' : 'rgba(60, 60, 60, 0.9)';
                    const dropdownBg = isLightTheme ? '#ffffff' : '#1e1e2e';
                    const dropdownBorder = isLightTheme ? '1px solid #e2e8f0' : '1px solid #313244';
                    const dropdownItemColor = isLightTheme ? '#374151' : '#cdd6f4';
                    const dropdownItemHoverBg = isLightTheme ? '#f1f5f9' : '#313244';
                    const dropdownDividerBg = isLightTheme ? '#e2e8f0' : '#313244';

                    let checklistHTML = `
                        <style>
                            /* Default: hide checkbox */
                            .checklist-wrapper .ticket-select-checkbox { display: none !important; }

                            /* Select mode: show checkbox, hide the ::before status indicator */
                            .checklist-wrapper[data-selection-mode="true"] .ticket-select-checkbox {
                                display: inline-block !important;
                                width: 14px;
                                height: 14px;
                                accent-color: #8b5cf6;
                                cursor: pointer;
                                flex-shrink: 0;
                            }
                            .checklist-wrapper[data-selection-mode="true"] .checklist-card::before { display: none !important; }

                            /* Checkbox positioning in selection mode */
                            .checklist-wrapper[data-selection-mode="true"] .checklist-card {
                                padding-left: 12px !important;
                            }
                            .checklist-wrapper[data-selection-mode="true"] .ticket-select-checkbox {
                                position: absolute !important;
                                left: 12px !important;
                                top: 50% !important;
                                transform: translateY(-50%) !important;
                            }
                            .checklist-wrapper[data-selection-mode="true"] .card-header {
                                margin-left: 24px !important;
                            }
                        </style>
                        <div class="checklist-wrapper" data-selection-mode="false">
                            <div class="checklist-header" style="display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; background: transparent; border: none;">
                                <!-- Select All (hidden by default, shown in selection mode) -->
                                <div id="select-all-container" style="display: none; align-items: center; gap: 6px;">
                                    <input type="checkbox" id="select-all-tickets" class="ticket-checkbox" style="width: 16px; height: 16px; cursor: pointer; accent-color: #8b5cf6;">
                                    <label for="select-all-tickets" style="font-size: 12px; color: ${isLightTheme ? '#64748b' : '#888'}; cursor: pointer;">Select All</label>
                                </div>
                                <div id="header-spacer" style="flex: 1;"></div>
                                <div style="display: flex; align-items: center;">
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
                                        <button class="dropdown-toggle" id="checklist-actions-dropdown" style="background: ${headerBtnBg}; color: ${headerBtnColor}; border: ${headerBtnBorder}; width: 24px; height: 24px; border-radius: 50%; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.15s ease; padding: 0;"
                                                onmouseover="this.style.background='${headerBtnHoverBg}'; this.style.color='#8b5cf6'; this.style.transform='scale(1.05)';"
                                                onmouseout="this.style.background='${headerBtnBg}'; this.style.color='${headerBtnColor}'; this.style.transform='scale(1)';">
                                            <i class="fas fa-ellipsis-v" style="font-size: 9px;"></i>
                                        </button>
                                        <div class="dropdown-menu" id="checklist-actions-menu" style="display: none; position: absolute; top: 100%; right: 0; background: ${dropdownBg}; border: ${dropdownBorder}; border-radius: 8px; min-width: 180px; box-shadow: 0 8px 16px rgba(0, 0, 0, ${isLightTheme ? '0.1' : '0.3'}); z-index: 1000; margin-top: 8px; overflow: hidden;">
                                            <button id="toggle-select-mode" class="dropdown-item" style="display: block; width: 100%; text-align: left; padding: 12px 16px; background: none; border: none; color: ${dropdownItemColor}; cursor: pointer; transition: all 0.2s; font-size: 14px;"
                                                    onmouseover="this.style.background='${dropdownItemHoverBg}'; this.style.color='${isLightTheme ? '#7c3aed' : '#b4befe'}';" onmouseout="this.style.background='none'; this.style.color='${dropdownItemColor}';">
                                                <i class="fas fa-check-square" style="margin-right: 10px; width: 14px; text-align: center; color: #8b5cf6;"></i> Select
                                            </button>
                                            <div style="height: 1px; background: ${dropdownDividerBg};"></div>
                                            <button id="sync-checklist-linear" class="dropdown-item" style="display: block; width: 100%; text-align: left; padding: 12px 16px; background: none; border: none; color: ${dropdownItemColor}; cursor: pointer; transition: all 0.2s; font-size: 14px;"
                                                    onmouseover="this.style.background='${dropdownItemHoverBg}'; this.style.color='${isLightTheme ? '#7c3aed' : '#b4befe'}';" onmouseout="this.style.background='none'; this.style.color='${dropdownItemColor}';">
                                                <i class="fas fa-sync" style="margin-right: 10px; width: 14px; text-align: center; color: #8b5cf6;"></i> Sync with Linear
                                            </button>
                                            <div style="height: 1px; background: ${dropdownDividerBg};"></div>
                                            <button id="delete-all-checklist" class="dropdown-item" style="display: block; width: 100%; text-align: left; padding: 12px 16px; background: none; border: none; color: ${isLightTheme ? '#dc2626' : '#f38ba8'}; cursor: pointer; transition: all 0.2s; font-size: 14px;"
                                                    onmouseover="this.style.background='${isLightTheme ? '#fef2f2' : '#313244'}'; this.style.color='${isLightTheme ? '#b91c1c' : '#eba0ac'}';" onmouseout="this.style.background='none'; this.style.color='${isLightTheme ? '#dc2626' : '#f38ba8'}';">
                                                <i class="fas fa-trash-alt" style="margin-right: 10px; width: 14px; text-align: center;"></i> Delete All
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <!-- Floating action bar for selected items (shown when items selected) -->
                            <div id="checklist-action-bar" class="checklist-action-bar" style="display: none; position: sticky; top: 0; z-index: 100; background: ${isLightTheme ? 'linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)' : 'linear-gradient(135deg, #1e1e2e 0%, #2a2a3e 100%)'}; border: 1px solid ${isLightTheme ? '#e2e8f0' : '#313244'}; border-radius: 8px; padding: 12px 16px; margin: 0 16px 12px 16px; box-shadow: 0 4px 12px rgba(0, 0, 0, ${isLightTheme ? '0.1' : '0.3'});">
                                <div style="display: flex; align-items: center; justify-content: space-between;">
                                    <span id="selected-count" style="font-size: 14px; color: ${isLightTheme ? '#374151' : '#cdd6f4'}; font-weight: 500;">
                                        <i class="fas fa-check-square" style="margin-right: 8px; color: #8b5cf6;"></i>
                                        <span id="selected-count-number">0</span> selected
                                    </span>
                                    <div style="display: flex; gap: 10px;">
                                        <button id="queue-selected-btn" class="action-bar-btn" style="display: flex; align-items: center; gap: 6px; padding: 8px 16px; background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%); color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500; transition: all 0.2s ease;"
                                                onmouseover="this.style.transform='translateY(-1px)'; this.style.boxShadow='0 4px 12px rgba(139, 92, 246, 0.4)';"
                                                onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='none';">
                                            <i class="fas fa-play"></i> Queue for Build
                                        </button>
                                        <button id="delete-selected-btn" class="action-bar-btn" style="display: flex; align-items: center; gap: 6px; padding: 8px 16px; background: ${isLightTheme ? '#fee2e2' : '#3d2a2a'}; color: ${isLightTheme ? '#dc2626' : '#f38ba8'}; border: 1px solid ${isLightTheme ? '#fecaca' : '#5c3a3a'}; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500; transition: all 0.2s ease;"
                                                onmouseover="this.style.background='${isLightTheme ? '#fecaca' : '#4d3a3a'}';"
                                                onmouseout="this.style.background='${isLightTheme ? '#fee2e2' : '#3d2a2a'}';">
                                            <i class="fas fa-trash"></i> Delete
                                        </button>
                                        <button id="cancel-selection-btn" class="action-bar-btn" style="display: flex; align-items: center; gap: 6px; padding: 8px 12px; background: transparent; color: ${isLightTheme ? '#64748b' : '#888'}; border: 1px solid ${isLightTheme ? '#e2e8f0' : '#313244'}; border-radius: 6px; cursor: pointer; font-size: 13px; transition: all 0.2s ease;"
                                                onmouseover="this.style.background='${isLightTheme ? '#f1f5f9' : '#313244'}';"
                                                onmouseout="this.style.background='transparent';">
                                            <i class="fas fa-times"></i> Cancel
                                        </button>
                                    </div>
                                </div>
                            </div>
                            <div class="checklist-container" id="checklist-content">
                                <!-- Checklist items will be loaded here -->
                            </div>
                        </div>
                    `;

                    checklistTab.innerHTML = checklistHTML;

                    // Get filter elements and content container
                    const checklistContent = document.getElementById('checklist-content');
                    const statusFilter = document.getElementById('status-filter');
                    const roleFilter = document.getElementById('role-filter');
                    const clearFiltersBtn = document.getElementById('clear-checklist-filters');

                    const deleteChecklistItem = (item) => {
                        if (!item) {
                            console.warn('[ArtifactsLoader] Attempted to delete an unknown checklist item');
                            return Promise.resolve(false);
                        }

                        if (!confirm(`Are you sure you want to delete "${item.name}"?`)) {
                            return Promise.resolve(false);
                        }

                        return fetch(`/projects/${projectId}/api/checklist/${item.id}/delete/`, {
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
                                window.showToast('Item deleted successfully', 'success');
                                ArtifactsLoader.loadChecklist(projectId);
                                return true;
                            }
                            window.showToast(data.error || 'Failed to delete item', 'error');
                            return false;
                        })
                        .catch(error => {
                            console.error('Error deleting item:', error);
                            window.showToast('Error deleting item', 'error');
                            return false;
                        });
                    };

                    modalHelpers.setHandlers({
                        onEdit: (item) => {
                            modalHelpers.close();
                            if (item && typeof window.editChecklistItem === 'function') {
                                window.editChecklistItem(item.id);
                            }
                        },
                        onDelete: (item) => deleteChecklistItem(item).then(removed => {
                            if (removed) {
                                modalHelpers.close();
                            }
                            return removed;
                        }),
                        onExecute: (item) => {
                            if (item) {
                                ArtifactsLoader.executeTicket(item.id);
                            }
                        },
                        onViewLogs: (item) => {
                            if (item) {
                                ArtifactsLoader.showTicketLogs(item.id);
                            }
                        }
                    });

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
                            
                            // Check if this item matches active filters for highlighting
                            const isStatusHighlighted = filterStatus !== 'all' && (item.status || 'open') === filterStatus;
                            const isRoleHighlighted = filterRole !== 'all' && (item.role || 'user') === filterRole;
                            
                            // Extract dependencies if available
                            let dependenciesHtml = '';
                            if (item.dependencies && item.dependencies.length > 0) {
                                dependenciesHtml = `
                                    <div class="card-dependencies">
                                        <span class="dependencies-label"><i class="fas fa-link"></i> Dependencies:</span>
                                        ${item.dependencies.map(dep => `<span class="dependency-tag">${modalHelpers.escapeHtml(dep)}</span>`).join('')}
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
                                            const safeKey = modalHelpers.escapeHtml(key);
                                            if (Array.isArray(value) && value.length > 0) {
                                                return `<span class="detail-item"><i class="fas fa-info-circle"></i> ${safeKey}: ${value.length} items</span>`;
                                            } else if (typeof value === 'object' && value !== null) {
                                                return `<span class="detail-item"><i class="fas fa-info-circle"></i> ${safeKey}: ${Object.keys(value).length} properties</span>`;
                                            } else if (value) {
                                                return `<span class="detail-item"><i class="fas fa-info-circle"></i> ${safeKey}</span>`;
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
                                        <div class="card-status" style="display: flex; align-items: center; gap: 8px;">
                                            <input type="checkbox" class="ticket-select-checkbox" data-ticket-id="${item.id}" style="display: none; width: 14px; height: 14px; accent-color: #8b5cf6; cursor: pointer; flex-shrink: 0;" onclick="event.stopPropagation();">
                                            <h3 class="card-title">${modalHelpers.escapeHtml(item.name || 'Untitled Item')}</h3>
                                        </div>
                                        <div class="card-badges">
                                            <span class="priority-badge ${priorityClass} ${isStatusHighlighted ? 'filter-active' : ''}">${modalHelpers.escapeHtml(item.priority || 'Medium')}</span>
                                            <span class="role-badge ${roleClass} ${isRoleHighlighted ? 'filter-active' : ''}">${modalHelpers.escapeHtml(item.role || 'User')}</span>
                                        </div>
                                    </div>
                                    
                                    <div class="card-body">
                                        <div class="card-description">
                                            ${(() => {
                                                const summaryText = (item.description || '').trim();
                                                if (!summaryText) {
                                                    return 'No description provided.';
                                                }
                                                return modalHelpers.escapeHtml(summaryText).replace(/\n/g, '<br>');
                                            })()}
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
                        attachChecklistDetailListeners(filteredChecklist);

                        const deleteButtons = checklistContent.querySelectorAll('.delete-checklist-btn');
                        deleteButtons.forEach(button => {
                            button.addEventListener('click', function(e) {
                                e.stopPropagation();
                                const itemId = parseInt(this.getAttribute('data-item-id'), 10);
                                const item = checklist.find(i => i.id === itemId);
                                deleteChecklistItem(item);
                            });
                        });
                    };

                    // Function to attach event listeners for checklist detail view
                    const attachChecklistDetailListeners = (currentItems) => {
                        const checklistCards = checklistContent.querySelectorAll('.checklist-card');
                        const viewDetailsButtons = checklistContent.querySelectorAll('.view-details-btn');

                        checklistCards.forEach((card, index) => {
                            card.addEventListener('click', function(e) {
                                if (e.target.closest('.action-btn') || e.target.closest('.ticket-select-checkbox')) {
                                    return;
                                }

                                modalHelpers.open(currentItems, index);
                            });
                        });

                        viewDetailsButtons.forEach((button) => {
                            button.addEventListener('click', function(e) {
                                e.stopPropagation();
                                const card = this.closest('.checklist-card');
                                if (!card) {
                                    return;
                                }
                                const cardIndex = Array.from(checklistCards).indexOf(card);
                                if (cardIndex >= 0) {
                                    modalHelpers.open(currentItems, cardIndex);
                                }
                            });
                        });

                        // Multi-select functionality
                        const wrapper = document.querySelector('.checklist-wrapper');
                        const actionBar = document.getElementById('checklist-action-bar');
                        const selectedCountEl = document.getElementById('selected-count-number');
                        const selectAllCheckbox = document.getElementById('select-all-tickets');
                        const selectAllContainer = document.getElementById('select-all-container');
                        const toggleSelectModeBtn = document.getElementById('toggle-select-mode');
                        const ticketCheckboxes = checklistContent.querySelectorAll('.ticket-select-checkbox');

                        let selectionMode = false;

                        const setSelectionMode = (enabled) => {
                            selectionMode = enabled;
                            wrapper.setAttribute('data-selection-mode', enabled ? 'true' : 'false');

                            // Show/hide select all container
                            if (selectAllContainer) {
                                selectAllContainer.style.display = enabled ? 'flex' : 'none';
                            }

                            // Toggle checkbox visibility (status circle hidden via CSS ::before selector)
                            const checkboxes = checklistContent.querySelectorAll('.ticket-select-checkbox');

                            checkboxes.forEach(checkbox => {
                                checkbox.style.display = enabled ? 'inline-block' : 'none';
                                if (!enabled) {
                                    checkbox.checked = false;
                                }
                            });

                            // Reset select all checkbox
                            if (selectAllCheckbox) {
                                selectAllCheckbox.checked = false;
                                selectAllCheckbox.indeterminate = false;
                            }

                            // Update toggle button text in dropdown
                            if (toggleSelectModeBtn) {
                                if (enabled) {
                                    toggleSelectModeBtn.innerHTML = '<i class="fas fa-times" style="margin-right: 10px; width: 14px; text-align: center; color: #8b5cf6;"></i> Cancel Selection';
                                } else {
                                    toggleSelectModeBtn.innerHTML = '<i class="fas fa-check-square" style="margin-right: 10px; width: 14px; text-align: center; color: #8b5cf6;"></i> Select';
                                }
                            }

                            // Hide action bar when exiting selection mode
                            if (!enabled && actionBar) {
                                actionBar.style.display = 'none';
                            }
                        };

                        const updateActionBar = () => {
                            if (!selectionMode) return;

                            const selectedCheckboxes = checklistContent.querySelectorAll('.ticket-select-checkbox:checked');
                            const count = selectedCheckboxes.length;

                            if (count > 0) {
                                actionBar.style.display = 'block';
                                selectedCountEl.textContent = count;
                            } else {
                                actionBar.style.display = 'none';
                            }

                            // Update select all checkbox state
                            if (selectAllCheckbox) {
                                selectAllCheckbox.checked = count > 0 && count === ticketCheckboxes.length;
                                selectAllCheckbox.indeterminate = count > 0 && count < ticketCheckboxes.length;
                            }
                        };

                        // Toggle selection mode button (in dropdown menu)
                        if (toggleSelectModeBtn) {
                            toggleSelectModeBtn.addEventListener('click', function() {
                                // Close the dropdown menu
                                const dropdownMenu = document.getElementById('checklist-actions-menu');
                                if (dropdownMenu) {
                                    dropdownMenu.style.display = 'none';
                                }
                                setSelectionMode(!selectionMode);
                            });
                        }

                        // Individual checkbox listeners
                        ticketCheckboxes.forEach(checkbox => {
                            checkbox.addEventListener('change', updateActionBar);
                        });

                        // Select all checkbox listener
                        if (selectAllCheckbox) {
                            selectAllCheckbox.addEventListener('change', function() {
                                ticketCheckboxes.forEach(checkbox => {
                                    checkbox.checked = this.checked;
                                });
                                updateActionBar();
                            });
                        }

                        // Cancel selection button (in action bar)
                        const cancelSelectionBtn = document.getElementById('cancel-selection-btn');
                        if (cancelSelectionBtn) {
                            cancelSelectionBtn.addEventListener('click', function() {
                                setSelectionMode(false);
                            });
                        }

                        // Queue selected button
                        const queueSelectedBtn = document.getElementById('queue-selected-btn');
                        if (queueSelectedBtn) {
                            queueSelectedBtn.addEventListener('click', function() {
                                const selectedIds = Array.from(checklistContent.querySelectorAll('.ticket-select-checkbox:checked'))
                                    .map(cb => parseInt(cb.getAttribute('data-ticket-id'), 10));

                                if (selectedIds.length === 0) {
                                    window.showToast('No tickets selected', 'warning');
                                    return;
                                }

                                if (!confirm(`Queue ${selectedIds.length} ticket(s) for build?`)) {
                                    return;
                                }

                                // Call queue API
                                fetch(`/projects/${projectId}/api/checklist/queue/`, {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json',
                                        'X-CSRFToken': getCsrfToken()
                                    },
                                    body: JSON.stringify({ ticket_ids: selectedIds })
                                })
                                .then(response => response.json())
                                .then(data => {
                                    if (data.success) {
                                        window.showToast(`${selectedIds.length} ticket(s) queued for build`, 'success');
                                        // Clear selection
                                        ticketCheckboxes.forEach(checkbox => {
                                            checkbox.checked = false;
                                        });
                                        if (selectAllCheckbox) {
                                            selectAllCheckbox.checked = false;
                                        }
                                        updateActionBar();
                                        // Reload checklist to show updated status
                                        ArtifactsLoader.loadChecklist(projectId);
                                    } else {
                                        window.showToast(data.error || 'Failed to queue tickets', 'error');
                                    }
                                })
                                .catch(error => {
                                    console.error('Error queueing tickets:', error);
                                    window.showToast('Error queueing tickets', 'error');
                                });
                            });
                        }

                        // Delete selected button
                        const deleteSelectedBtn = document.getElementById('delete-selected-btn');
                        if (deleteSelectedBtn) {
                            deleteSelectedBtn.addEventListener('click', function() {
                                const selectedIds = Array.from(checklistContent.querySelectorAll('.ticket-select-checkbox:checked'))
                                    .map(cb => parseInt(cb.getAttribute('data-ticket-id'), 10));

                                if (selectedIds.length === 0) {
                                    window.showToast('No tickets selected', 'warning');
                                    return;
                                }

                                if (!confirm(`Delete ${selectedIds.length} ticket(s)? This action cannot be undone.`)) {
                                    return;
                                }

                                // Call bulk delete API
                                fetch(`/projects/${projectId}/api/checklist/bulk-delete/`, {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json',
                                        'X-CSRFToken': getCsrfToken()
                                    },
                                    body: JSON.stringify({ ticket_ids: selectedIds })
                                })
                                .then(response => response.json())
                                .then(data => {
                                    if (data.success) {
                                        window.showToast(`${data.deleted_count} ticket(s) deleted`, 'success');
                                        // Reload checklist
                                        ArtifactsLoader.loadChecklist(projectId);
                                    } else {
                                        window.showToast(data.error || 'Failed to delete tickets', 'error');
                                    }
                                })
                                .catch(error => {
                                    console.error('Error deleting tickets:', error);
                                    window.showToast('Error deleting tickets', 'error');
                                });
                            });
                        }
                    };

                    // Function to update checklist item status
                    const updateChecklistItemStatus = (itemId, newStatus, oldStatus) => {
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
                                // Update the visual state in the main list (status circle color is handled by CSS)
                                const itemElement = document.querySelector(`[data-id="${itemId}"]`);
                                if (itemElement) {
                                    itemElement.classList.remove('open', 'in-progress', 'done', 'failed', 'blocked');
                                    itemElement.classList.add(newStatus.replace('_', '-'));
                                }
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
            
            fetch(serverConfigsUrl)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    
                    // Process server configs
                    const serverConfigs = data.server_configs || [];
                    
                    if (serverConfigs.length === 0) {
                        // Show empty state if no server configs found
                        showEmptyState("No application servers found. Start a server using the chat interface by running commands like 'npm start' or 'python manage.py runserver'.");
                        return;
                    }
                    
                    // Find the first application server or use the first config
                    let selectedConfig = serverConfigs.find(config => config.type === 'application') || serverConfigs[0];
                    
                    // If there are multiple configs, you could potentially show a selector here
                    if (serverConfigs.length > 1) {
                    }
                    
                    // Construct the URL for the iframe using localhost and the configured port
                    const appUrl = `http://localhost:${selectedConfig.port}/`;
                    
                    // First, check if the server is actually running by testing the URL
                    
                    // Test server connectivity before loading iframe
                    fetch(appUrl, {
                        method: 'GET',
                        mode: 'no-cors', // Avoid CORS issues for connectivity test
                        cache: 'no-cache'
                    })
                    .then(() => {
                        loadIframeApp(appUrl, selectedConfig);
                    })
                    .catch((error) => {
                        console.error(`[ArtifactsLoader] Server connectivity test failed for ${appUrl}:`, error);
                        showServerNotRunningError(selectedConfig.port);
                    });
                    
                    // Function to load the app in iframe after connectivity is confirmed
                    function loadIframeApp(iframeUrl, config) {
                        
                        // Use setTimeout to ensure DOM is ready
                        setTimeout(() => {
                            // Show URL panel and update URL
                            const urlPanel = document.getElementById('app-url-panel');
                            const urlInput = document.getElementById('app-url-input');
                            const refreshBtn = document.getElementById('app-refresh-btn');
                            const restartServerBtn = document.getElementById('app-restart-server-btn');
                            
                            if (urlPanel && urlInput) {
                                urlPanel.style.display = 'block';
                                urlInput.value = iframeUrl;
                            
                            // Handle URL input
                            urlInput.onkeypress = function(e) {
                                if (e.key === 'Enter') {
                                    const newUrl = this.value.trim();
                                    if (newUrl) {
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
                            hasLoaded = true;
                            clearTimeout(timeoutId);
                            
                            appLoading.style.display = 'none';
                            appFrameContainer.style.display = 'flex';
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
            
            fetch(url, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                }
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
                }
                return response.json();
            })
            .then(data => {
                
                // Check the overall status
                if (data.status === 'all_running') {
                    // All servers are running, reload the app preview
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
         * Open app in artifacts panel with the given URL
         * @param {string} appUrl - The URL of the app (with IPv6)
         * @param {string} workspaceId - The workspace ID
         * @param {number} port - The port number
         */
        openAppInArtifacts: function(appUrl, workspaceId, port) {

            if (!appUrl) {
                console.error('[ArtifactsLoader] No app URL provided');
                return;
            }

            // Switch to the apps tab
            if (window.switchTab) {
                window.switchTab('apps');
            }

            // Open the artifacts panel if not already open
            const artifactsPanel = document.getElementById('artifacts-panel');
            const artifactsToggle = document.getElementById('artifacts-toggle');
            const appContainer = document.querySelector('.app-container');

            if (artifactsPanel && !artifactsPanel.classList.contains('open')) {
                artifactsPanel.classList.add('open');
                if (appContainer) appContainer.classList.add('artifacts-expanded');
                if (artifactsToggle) artifactsToggle.classList.add('active');
            }

            // Get UI elements
            const appUrlPanel = document.getElementById('app-url-panel');
            const appUrlInput = document.getElementById('app-url-input');
            const appIframe = document.getElementById('app-iframe');
            const appLoading = document.getElementById('app-loading');
            const appEmpty = document.getElementById('app-empty');
            const appFrameContainer = document.getElementById('app-frame-container');

            if (!appIframe || !appUrlInput || !appFrameContainer) {
                console.error('[ArtifactsLoader] Required app UI elements not found');
                return;
            }

            // Show URL panel
            if (appUrlPanel) {
                appUrlPanel.style.display = 'block';
            }

            // Set the URL in the input field
            appUrlInput.value = appUrl;

            // Show loading state
            if (appLoading) appLoading.style.display = 'block';
            if (appEmpty) appEmpty.style.display = 'none';
            appFrameContainer.style.display = 'none';

            // Set up iframe load handlers
            let hasLoaded = false;
            let timeoutId = null;

            appIframe.onload = function() {
                hasLoaded = true;
                clearTimeout(timeoutId);

                if (appLoading) appLoading.style.display = 'none';
                appFrameContainer.style.display = 'flex';
            };

            appIframe.onerror = function(e) {
                console.error('[ArtifactsLoader] Error loading app iframe:', e);
                hasLoaded = true;
                clearTimeout(timeoutId);

                if (appLoading) appLoading.style.display = 'none';
                if (appEmpty) {
                    appEmpty.style.display = 'flex';
                    appEmpty.querySelector('.empty-state-text').textContent =
                        `Failed to load app from ${appUrl}. The server may not be running.`;
                }
            };

            // Set timeout
            timeoutId = setTimeout(() => {
                if (!hasLoaded) {
                    console.warn('[ArtifactsLoader] App iframe taking too long to load');
                    if (appLoading) appLoading.style.display = 'none';
                    appFrameContainer.style.display = 'flex';
                }
            }, 15000); // 15 second timeout

            // Load the app in the iframe
            appIframe.src = appUrl;

            // Set up refresh button
            const refreshBtn = document.getElementById('app-refresh-btn');
            if (refreshBtn) {
                refreshBtn.onclick = function() {
                    appIframe.src = appIframe.src; // Reload iframe
                };
            }

            // Set up restart server button
            const restartBtn = document.getElementById('app-restart-server-btn');
            if (restartBtn) {
                restartBtn.onclick = function() {
                    // TODO: Implement server restart logic
                    if (window.showToast) {
                        window.showToast('Server restart functionality coming soon', 'info');
                    }
                };
            }
        },

        /**
         * Load Tool Call History for a project
         * @param {number} projectId - The project ID
         */
        loadToolHistory: function(projectId) {
            
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

            // Find the ticket data
            const projectId = this.getCurrentProjectId();
            if (!projectId) {
                console.error('[ArtifactsLoader] No project ID found');
                if (window.showToast && typeof window.showToast === 'function') {
                    window.showToast('Unable to execute ticket: No project ID found', 'error');
                }
                return;
            }

            // Get the execute button to update its state
            const executeBtn = document.getElementById('ticket-modal-execute');
            const originalBtnHTML = executeBtn ? executeBtn.innerHTML : null;

            // Show loading state
            if (executeBtn) {
                executeBtn.disabled = true;
                executeBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Queueing...';
            }

            // Get conversation ID if available
            const conversationId = window.conversationId || null;

            // Queue the ticket for execution via API
            fetch(`/api/v1/project-tickets/${ticketId}/queue-execution/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                credentials: 'same-origin',
                body: JSON.stringify({
                    conversation_id: conversationId
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'queued') {

                    // Show success feedback
                    if (executeBtn) {
                        executeBtn.innerHTML = '<i class="fas fa-check"></i> Queued!';
                        executeBtn.classList.add('success');

                        // Reset button after 2 seconds
                        setTimeout(() => {
                            executeBtn.innerHTML = originalBtnHTML;
                            executeBtn.disabled = false;
                            executeBtn.classList.remove('success');
                        }, 2000);
                    }

                    // Show toast notification
                    if (window.showToast && typeof window.showToast === 'function') {
                        window.showToast(`Ticket #${ticketId} has been queued for execution`, 'success');
                    }
                } else {
                    throw new Error(data.message || 'Failed to queue ticket');
                }
            })
            .catch(error => {
                console.error('[ArtifactsLoader] Error queueing ticket:', error);

                // Show error feedback
                if (executeBtn) {
                    executeBtn.innerHTML = '<i class="fas fa-times"></i> Failed';
                    executeBtn.classList.add('error');

                    // Reset button after 2 seconds
                    setTimeout(() => {
                        executeBtn.innerHTML = originalBtnHTML;
                        executeBtn.disabled = false;
                        executeBtn.classList.remove('error');
                    }, 2000);
                }

                // Show error notification
                if (window.showNotification && typeof window.showNotification === 'function') {
                    window.showNotification(`Failed to queue ticket: ${error.message}`, 'error');
                } else {
                    alert(`Failed to queue ticket: ${error.message}`);
                }
            });
        },

        /**
         * Show execution logs for a ticket in a side drawer
         * @param {number} ticketId - The ID of the ticket to show logs for
         */
        showTicketLogs: function(ticketId) {

            const projectId = this.getCurrentProjectId();
            if (!projectId) {
                console.error('[ArtifactsLoader] No project ID found');
                return;
            }

            // Create side drawer overlay
            const drawer = document.createElement('div');
            drawer.id = 'ticket-logs-drawer';
            drawer.className = 'logs-drawer-overlay';
            drawer.innerHTML = `
                <div class="logs-drawer">
                    <div class="logs-drawer-header">
                        <h3><i class="fas fa-terminal"></i> Ticket Details</h3>
                        <div class="logs-drawer-actions">
                            <button class="logs-drawer-refresh" title="Refresh">
                                <i class="fas fa-sync-alt"></i>
                            </button>
                            <button class="logs-drawer-close" title="Close">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    </div>
                    <div class="logs-drawer-tabs">
                        <button class="logs-tab-btn active" data-tab="logs">
                            <i class="fas fa-terminal"></i> Logs
                        </button>
                        <button class="logs-tab-btn" data-tab="tasks">
                            <i class="fas fa-list-check"></i> Tasks
                        </button>
                    </div>
                    <div class="logs-drawer-content">
                        <div id="logs-tab-content" class="tab-content-panel active">
                            <div class="logs-loading">
                                <i class="fas fa-spinner fa-spin"></i> Loading logs...
                            </div>
                        </div>
                        <div id="tasks-tab-content" class="tab-content-panel">
                            <div class="logs-loading">
                                <i class="fas fa-spinner fa-spin"></i> Loading tasks...
                            </div>
                        </div>
                    </div>
                </div>
            `;
            document.body.appendChild(drawer);

            // Add styles if not already present
            if (!document.getElementById('ticket-logs-styles')) {
                const style = document.createElement('style');
                style.id = 'ticket-logs-styles';
                style.textContent = `
                    .logs-drawer-overlay {
                        position: fixed;
                        top: 0;
                        left: 0;
                        right: 0;
                        bottom: 0;
                        background: rgba(0, 0, 0, 0.5);
                        z-index: 10001;
                        display: flex;
                        align-items: center;
                        justify-content: flex-end;
                        animation: fadeIn 0.2s ease;
                    }
                    .logs-drawer {
                        background: #1a1a1a;
                        width: 60%;
                        max-width: 900px;
                        height: 100%;
                        display: flex;
                        flex-direction: column;
                        box-shadow: -4px 0 20px rgba(0, 0, 0, 0.5);
                        animation: slideInRight 0.3s ease;
                    }
                    @keyframes slideInRight {
                        from { transform: translateX(100%); }
                        to { transform: translateX(0); }
                    }
                    .logs-drawer-header {
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        padding: 20px;
                        border-bottom: 1px solid #333;
                        background: #222;
                    }
                    .logs-drawer-header h3 {
                        margin: 0;
                        color: #fff;
                        font-size: 18px;
                        display: flex;
                        align-items: center;
                        gap: 10px;
                    }
                    .logs-drawer-tabs {
                        display: flex;
                        gap: 0;
                        background: #1a1a1a;
                        border-bottom: 1px solid #333;
                        padding: 0 20px;
                    }
                    .logs-tab-btn {
                        background: none;
                        border: none;
                        color: #999;
                        padding: 12px 20px;
                        cursor: pointer;
                        font-size: 14px;
                        display: flex;
                        align-items: center;
                        gap: 8px;
                        border-bottom: 2px solid transparent;
                        transition: all 0.2s;
                    }
                    .logs-tab-btn:hover {
                        color: #fff;
                        background: rgba(255, 255, 255, 0.05);
                    }
                    .logs-tab-btn.active {
                        color: #4a9eff;
                        border-bottom-color: #4a9eff;
                    }
                    .tab-content-panel {
                        display: none;
                    }
                    .tab-content-panel.active {
                        display: block;
                    }
                    .logs-drawer-actions {
                        display: flex;
                        align-items: center;
                        gap: 10px;
                    }
                    .logs-drawer-refresh,
                    .logs-drawer-close {
                        background: none;
                        border: none;
                        color: #999;
                        font-size: 20px;
                        cursor: pointer;
                        padding: 8px 12px;
                        transition: all 0.2s;
                        border-radius: 6px;
                    }
                    .logs-drawer-refresh:hover {
                        color: #4a9eff;
                        background: rgba(74, 158, 255, 0.1);
                    }
                    .logs-drawer-refresh:active {
                        transform: rotate(180deg);
                    }
                    .logs-drawer-refresh.refreshing {
                        animation: spin 1s linear infinite;
                    }
                    @keyframes spin {
                        from { transform: rotate(0deg); }
                        to { transform: rotate(360deg); }
                    }
                    .logs-drawer-close:hover {
                        color: #fff;
                    }
                    .logs-drawer-content {
                        flex: 1;
                        overflow-y: auto;
                        padding: 20px;
                        font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
                        font-size: 13px;
                        line-height: 1.6;
                    }
                    .logs-loading {
                        color: #999;
                        text-align: center;
                        padding: 40px;
                    }
                    .logs-section {
                        margin-bottom: 30px;
                        background: #0d0d0d;
                        border: 1px solid #333;
                        border-radius: 6px;
                        overflow: hidden;
                    }
                    .logs-section-header {
                        background: #1a1a1a;
                        padding: 12px 16px;
                        border-bottom: 1px solid #333;
                        color: #fff;
                        font-weight: 600;
                        display: flex;
                        align-items: center;
                        gap: 8px;
                    }
                    .logs-section-content {
                        padding: 16px;
                        color: #ddd;
                        white-space: pre-wrap;
                        word-wrap: break-word;
                    }
                    .log-command {
                        color: #4a9eff;
                        margin-bottom: 8px;
                    }
                    .log-output {
                        color: #9f9;
                        margin-left: 20px;
                    }
                    .log-error {
                        color: #f99;
                    }
                    .log-timestamp {
                        color: #888;
                        font-size: 11px;
                    }
                    .logs-empty {
                        text-align: center;
                        color: #666;
                        padding: 60px 20px;
                    }
                    .task-item {
                        background: #0d0d0d;
                        border: 1px solid #333;
                        border-radius: 6px;
                        padding: 16px;
                        margin-bottom: 12px;
                        display: flex;
                        align-items: flex-start;
                        gap: 12px;
                        transition: all 0.2s;
                    }
                    .task-item:hover {
                        border-color: #4a9eff;
                        background: #111;
                    }
                    .task-icon {
                        width: 24px;
                        height: 24px;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        flex-shrink: 0;
                        font-size: 12px;
                        margin-top: 2px;
                    }
                    .task-icon.pending {
                        background: rgba(156, 163, 175, 0.2);
                        color: #9ca3af;
                        border: 2px solid #4b5563;
                    }
                    .task-icon.in_progress {
                        background: rgba(59, 130, 246, 0.2);
                        color: #60a5fa;
                        border: 2px solid #3b82f6;
                    }
                    .task-icon.success {
                        background: rgba(16, 185, 129, 0.2);
                        color: #10b981;
                        border: 2px solid #10b981;
                    }
                    .task-icon.fail {
                        background: rgba(239, 68, 68, 0.2);
                        color: #ef4444;
                        border: 2px solid #ef4444;
                    }
                    .task-content {
                        flex: 1;
                    }
                    .task-name {
                        color: #fff;
                        font-weight: 600;
                        margin-bottom: 6px;
                        font-size: 14px;
                    }
                    .task-description {
                        color: #999;
                        font-size: 13px;
                        line-height: 1.5;
                    }
                    .task-status-badge {
                        display: inline-flex;
                        align-items: center;
                        gap: 6px;
                        padding: 4px 10px;
                        border-radius: 12px;
                        font-size: 11px;
                        font-weight: 600;
                        text-transform: uppercase;
                        letter-spacing: 0.5px;
                        margin-top: 8px;
                    }
                    .task-status-badge.pending {
                        background: rgba(156, 163, 175, 0.15);
                        color: #9ca3af;
                    }
                    .task-status-badge.in_progress {
                        background: rgba(59, 130, 246, 0.15);
                        color: #60a5fa;
                    }
                    .task-status-badge.success {
                        background: rgba(16, 185, 129, 0.15);
                        color: #10b981;
                    }
                    .task-status-badge.fail {
                        background: rgba(239, 68, 68, 0.15);
                        color: #ef4444;
                    }
                `;
                document.head.appendChild(style);
            }

            // Function to load/reload logs
            const loadLogs = () => {
                const content = drawer.querySelector('#logs-tab-content');
                const refreshBtn = drawer.querySelector('.logs-drawer-refresh');

                if (!content) {
                    console.error('[ArtifactsLoader] #logs-tab-content element not found at start of loadLogs');
                    return;
                }

                // Show loading state
                content.innerHTML = '<div class="logs-loading"><i class="fas fa-spinner fa-spin"></i> Loading logs...</div>';

                // Add refreshing animation
                if (refreshBtn) {
                    refreshBtn.classList.add('refreshing');
                }

                fetch(`/api/v1/project-tickets/${ticketId}/logs/`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {

                    // Update drawer header with ticket name
                    const header = drawer.querySelector('.logs-drawer-header h3');
                    if (header && data.ticket_name) {
                        header.innerHTML = `<i class="fas fa-terminal"></i> ${data.ticket_name} - Execution Logs`;
                    }

                    const content = drawer.querySelector('#logs-tab-content');
                    if (!content) {
                        console.error('[ArtifactsLoader] #logs-tab-content element not found');
                        if (refreshBtn) {
                            refreshBtn.classList.remove('refreshing');
                        }
                        return;
                    }

                    if (!data.commands || data.commands.length === 0) {
                        content.innerHTML = `
                            <div class="logs-empty">
                                <i class="fas fa-inbox" style="font-size: 48px; margin-bottom: 16px; opacity: 0.3;"></i>
                                <p>No execution logs available for this ticket yet.</p>
                                <p style="font-size: 12px; color: #555;">Logs will appear here after the ticket is executed.</p>
                            </div>
                        `;

                        // Remove refreshing animation
                        if (refreshBtn) {
                            refreshBtn.classList.remove('refreshing');
                        }
                        return;
                    }

                    let html = '';

                    // Helper function to escape HTML
                    const escapeHtml = (text) => {
                        if (!text) return '';
                        const div = document.createElement('div');
                        div.textContent = text;
                        return div.innerHTML;
                    };

                    // Show ticket notes if available
                    // if (data.ticket_notes) {
                    //     html += `
                    //         <div class="logs-section">
                    //             <div class="logs-section-header">
                    //                 <i class="fas fa-clipboard-list"></i> Execution Summary
                    //             </div>
                    //             <div class="logs-section-content">${escapeHtml(data.ticket_notes)}</div>
                    //         </div>
                    //     `;
                    // }

                    // Show command history
                    data.commands.forEach((cmd, index) => {
                        const timestamp = new Date(cmd.created_at).toLocaleString();
                        html += `
                            <div class="logs-section">
                                <div class="logs-section-header">
                                    <i class="fas fa-terminal"></i> Command ${index + 1}
                                    <span class="log-timestamp" style="margin-left: auto;">${timestamp}</span>
                                </div>
                                <div class="logs-section-content">
                                    <div class="log-command">$ ${escapeHtml(cmd.command)}</div>
                                    ${cmd.output ? `<div class="log-output">${escapeHtml(cmd.output)}</div>` : '<div class="log-output" style="color: #666;">(no output)</div>'}
                                </div>
                            </div>
                        `;
                    });

                    content.innerHTML = html;

                    // Remove refreshing animation
                    if (refreshBtn) {
                        refreshBtn.classList.remove('refreshing');
                    }
                })
                .catch(error => {
                    console.error('[ArtifactsLoader] Error fetching logs:', error);
                    const content = drawer.querySelector('#logs-tab-content');
                    if (content) {
                        content.innerHTML = `
                            <div class="logs-empty">
                                <i class="fas fa-exclamation-triangle" style="font-size: 48px; margin-bottom: 16px; color: #f99;"></i>
                                <p class="log-error">Failed to load execution logs</p>
                                <p style="font-size: 12px; color: #888;">${error.message}</p>
                            </div>
                        `;
                    }

                    // Remove refreshing animation
                    if (refreshBtn) {
                        refreshBtn.classList.remove('refreshing');
                    }
                });
            };

            // Function to load/reload tasks
            const loadTasks = () => {
                const tasksContent = drawer.querySelector('#tasks-tab-content');
                const refreshBtn = drawer.querySelector('.logs-drawer-refresh');

                if (!tasksContent) {
                    console.error('[ArtifactsLoader] #tasks-tab-content element not found');
                    if (refreshBtn) {
                        refreshBtn.classList.remove('refreshing');
                    }
                    return;
                }

                if (refreshBtn) {
                    refreshBtn.classList.add('refreshing');
                }

                tasksContent.innerHTML = '<div class="logs-loading"><i class="fas fa-spinner fa-spin"></i> Loading tasks...</div>';

                fetch(`/api/v1/project-tickets/${ticketId}/tasks/`)
                    .then(response => {
                        if (!response.ok) {
                            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                        }
                        return response.json();
                    })
                    .then(data => {

                        if (!data.tasks || data.tasks.length === 0) {
                            tasksContent.innerHTML = '<div class="logs-empty"><i class="fas fa-info-circle" style="font-size: 32px; margin-bottom: 12px; color: #888;"></i><p>No tasks defined for this ticket yet.</p></div>';
                            if (refreshBtn) {
                                refreshBtn.classList.remove('refreshing');
                            }
                            return;
                        }

                        let html = '';
                        data.tasks.forEach(task => {
                            const statusIcon = {
                                'pending': '○',
                                'in_progress': '◐',
                                'success': '✓',
                                'fail': '✗'
                            }[task.status] || '○';

                            const escapedName = (task.name || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                            const escapedDescription = (task.description || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');

                            html += `
                                <div class="task-item">
                                    <div class="task-icon ${task.status}">${statusIcon}</div>
                                    <div class="task-content">
                                        <div class="task-name">${escapedName}</div>
                                        ${escapedDescription ? `<div class="task-description">${escapedDescription}</div>` : ''}
                                        <span class="task-status-badge ${task.status}">${task.status.replace('_', ' ')}</span>
                                    </div>
                                </div>
                            `;
                        });

                        tasksContent.innerHTML = html;

                        if (refreshBtn) {
                            refreshBtn.classList.remove('refreshing');
                        }
                    })
                    .catch(error => {
                        console.error('[ArtifactsLoader] Error loading tasks:', error);
                        if (tasksContent) {
                            tasksContent.innerHTML = `
                                <div class="logs-empty">
                                    <i class="fas fa-exclamation-triangle" style="font-size: 48px; margin-bottom: 16px; color: #f99;"></i>
                                    <p class="log-error">Failed to load tasks</p>
                                    <p style="font-size: 12px; color: #888;">${error.message}</p>
                                </div>
                            `;
                        }

                        if (refreshBtn) {
                            refreshBtn.classList.remove('refreshing');
                        }
                    });
            };

            // Tab switching logic
            drawer.querySelectorAll('.logs-tab-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const tab = btn.dataset.tab;

                    // Update active states
                    drawer.querySelectorAll('.logs-tab-btn').forEach(b => b.classList.remove('active'));
                    drawer.querySelectorAll('.tab-content-panel').forEach(p => p.classList.remove('active'));
                    btn.classList.add('active');

                    const tabContent = drawer.querySelector(`#${tab}-tab-content`);
                    if (tabContent) {
                        tabContent.classList.add('active');
                    } else {
                        console.error(`[ArtifactsLoader] Tab content #${tab}-tab-content not found`);
                    }

                    // Load tasks when switching to tasks tab for the first time
                    if (tab === 'tasks') {
                        const tasksContent = drawer.querySelector('#tasks-tab-content');
                        if (tasksContent && (!tasksContent.hasChildNodes() || tasksContent.innerHTML.trim() === '')) {
                            loadTasks();
                        }
                    }
                });
            });

            // Close button handler
            drawer.querySelector('.logs-drawer-close').addEventListener('click', () => {
                drawer.style.animation = 'fadeOut 0.2s ease';
                drawer.querySelector('.logs-drawer').style.animation = 'slideOutRight 0.3s ease';
                setTimeout(() => drawer.remove(), 300);
            });

            // Refresh button handler - updated to work with both tabs
            const refreshBtn = drawer.querySelector('.logs-drawer-refresh');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => {
                    const activeTabBtn = drawer.querySelector('.logs-tab-btn.active');
                    if (!activeTabBtn) {
                        console.error('[ArtifactsLoader] No active tab button found');
                        return;
                    }
                    const activeTab = activeTabBtn.dataset.tab;

                    if (activeTab === 'logs') {
                        loadLogs();
                    } else if (activeTab === 'tasks') {
                        loadTasks();
                    }
                });
            }

            // Click outside to close
            drawer.addEventListener('click', (e) => {
                if (e.target === drawer) {
                    drawer.querySelector('.logs-drawer-close').click();
                }
            });

            // Initial load - wait for DOM to be ready
            setTimeout(() => loadLogs(), 100);
        },

        /**
         * Download file content as PDF
         * @param {number} projectId - The ID of the current project
         * @param {string} title - The title of the document
         * @param {string} content - The markdown content
         */
        downloadFileAsPDF: function(projectId, title, content) {
            
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
                                    
                                case 'table':
                                    currentY += 8; // Space before table
                                    
                                    // Extract table data first
                                    const rows = node.querySelectorAll('tr');
                                    const tableRows = [];
                                    let maxColumns = 0;
                                    
                                    // Process all rows to get data and find max columns
                                    rows.forEach((row) => {
                                        const cells = row.querySelectorAll('td, th');
                                        const rowData = [];
                                        cells.forEach(cell => {
                                            rowData.push(cell.textContent.trim());
                                        });
                                        if (rowData.length > maxColumns) {
                                            maxColumns = rowData.length;
                                        }
                                        tableRows.push({
                                            data: rowData,
                                            isHeader: row.querySelector('th') !== null || row.parentElement.tagName === 'THEAD'
                                        });
                                    });
                                    
                                    if (tableRows.length > 0 && maxColumns > 0) {
                                        // Calculate column widths
                                        const totalTableWidth = pageWidth;
                                        const columnWidth = totalTableWidth / maxColumns;
                                        const cellPadding = 3;
                                        
                                        // Draw the table
                                        doc.setFontSize(9);
                                        
                                        // First, calculate all row heights
                                        const rowHeights = [];
                                        tableRows.forEach((row) => {
                                            let maxHeight = 10; // minimum row height
                                            row.data.forEach((cellText) => {
                                                const cellTextLines = doc.splitTextToSize(cellText, columnWidth - (cellPadding * 2));
                                                const cellHeight = cellTextLines.length * 4 + 6;
                                                if (cellHeight > maxHeight) {
                                                    maxHeight = cellHeight;
                                                }
                                            });
                                            rowHeights.push(maxHeight);
                                        });
                                        
                                        // Calculate total table height
                                        const totalTableHeight = rowHeights.reduce((sum, height) => sum + height, 0);
                                        
                                        // Check if entire table fits on current page
                                        if (checkNewPage(totalTableHeight + 10)) {
                                            currentY += 10; // Add some space at top of new page
                                        }
                                        
                                        const tableStartY = currentY;
                                        
                                        // Draw table
                                        tableRows.forEach((row, rowIndex) => {
                                            const rowHeight = rowHeights[rowIndex];
                                            const rowY = currentY;
                                            
                                            // Draw background for entire row first
                                            if (row.isHeader) {
                                                doc.setFillColor(66, 66, 66);
                                                doc.rect(leftMargin, rowY, totalTableWidth, rowHeight, 'F');
                                            } else if (rowIndex % 2 === 1) {
                                                doc.setFillColor(245, 245, 245);
                                                doc.rect(leftMargin, rowY, totalTableWidth, rowHeight, 'F');
                                            }
                                            
                                            // Draw cells
                                            row.data.forEach((cellText, colIndex) => {
                                                const cellX = leftMargin + (colIndex * columnWidth);
                                                
                                                // Set font style
                                                if (row.isHeader) {
                                                    doc.setFont('helvetica', 'bold');
                                                    doc.setTextColor(255, 255, 255);
                                                } else {
                                                    doc.setFont('helvetica', 'normal');
                                                    doc.setTextColor(0, 0, 0);
                                                }
                                                
                                                // Split text to fit in cell
                                                const cellTextLines = doc.splitTextToSize(cellText, columnWidth - (cellPadding * 2));
                                                
                                                // Draw text vertically centered in cell
                                                const textStartY = rowY + ((rowHeight - (cellTextLines.length * 4)) / 2) + 4;
                                                cellTextLines.forEach((line, lineIndex) => {
                                                    doc.text(line, cellX + cellPadding, textStartY + (lineIndex * 4));
                                                });
                                                
                                                // Draw vertical cell border
                                                if (colIndex < row.data.length - 1) {
                                                    doc.setDrawColor(200, 200, 200);
                                                    doc.setLineWidth(0.1);
                                                    doc.line(cellX + columnWidth, rowY, cellX + columnWidth, rowY + rowHeight);
                                                }
                                            });
                                            
                                            // Draw horizontal border after row
                                            doc.setDrawColor(200, 200, 200);
                                            doc.setLineWidth(0.1);
                                            doc.line(leftMargin, rowY + rowHeight, leftMargin + totalTableWidth, rowY + rowHeight);
                                            
                                            // Reset text color
                                            doc.setTextColor(0, 0, 0);
                                            
                                            // Move to next row
                                            currentY += rowHeight;
                                        });
                                        
                                        // Draw outer table border
                                        doc.setDrawColor(0, 0, 0);
                                        doc.setLineWidth(0.3);
                                        doc.rect(leftMargin, tableStartY, totalTableWidth, totalTableHeight, 'S');
                                        
                                        doc.setFontSize(11); // Reset font size
                                    }
                                    
                                    currentY += 8; // Space after table
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
                    const fileName = `${title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}.pdf`;
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
         * Download content as Word document
         * @param {string} fileName - The name of the file (without extension)
         * @param {string} content - The markdown content
         */
        downloadAsDoc: function(fileName, content) {
            if (!content) {
                console.error('No content to download');
                return;
            }
            
            // Convert markdown to HTML for better formatting in Word
            let htmlContent = content;
            if (typeof marked !== 'undefined') {
                htmlContent = marked.parse(content);
            }
            
            // Create a blob with HTML content that Word can understand
            const html = `
                <html xmlns:o='urn:schemas-microsoft-com:office:office' 
                      xmlns:w='urn:schemas-microsoft-com:office:word' 
                      xmlns='http://www.w3.org/TR/REC-html40'>
                <head>
                    <meta charset='utf-8'>
                    <title>${fileName}</title>
                    <style>
                        body { font-family: Arial, sans-serif; line-height: 1.6; }
                        h1 { font-size: 24pt; font-weight: bold; }
                        h2 { font-size: 18pt; font-weight: bold; }
                        h3 { font-size: 14pt; font-weight: bold; }
                        p { margin: 10pt 0; }
                        pre { background: #f4f4f4; padding: 10pt; }
                        code { background: #f4f4f4; padding: 2pt 4pt; }
                    </style>
                </head>
                <body>
                    ${htmlContent}
                </body>
                </html>
            `;
            
            const blob = new Blob(['\ufeff', html], { 
                type: 'application/msword' 
            });
            
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${fileName}.doc`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            window.showToast('Document downloaded successfully', 'success');
        },
        
        /**
         * Download content as Markdown file
         * @param {string} fileName - The name of the file (without extension)
         * @param {string} content - The markdown content
         */
        downloadAsMarkdown: function(fileName, content) {
            if (!content) {
                console.error('No content to download');
                return;
            }
            
            const blob = new Blob([content], { type: 'text/markdown' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${fileName}.md`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            window.showToast('Markdown file downloaded successfully', 'success');
        },
        
        /**
         * Load File Browser for a project
         * @param {number} projectId - The project ID
         * @param {object} options - Optional settings
         * @param {string} options.openFileId - File ID to open after loading
         * @param {string} options.openFileName - File name to open after loading
         */
        loadFileBrowser: function(projectId, options = {}) {
            
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
                            fileItem.dataset.fileType = file.type;
                            fileItem.dataset.fileName = file.name;
                            
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
                            typeBadge.title = displayType;
                            fileType.appendChild(typeBadge);
                            
                            // Create owner cell
                            const fileOwner = document.createElement('div');
                            fileOwner.className = 'file-owner-cell';
                            fileOwner.textContent = file.owner || 'System';
                            
                            // Create date cell
                            const fileDate = document.createElement('div');
                            fileDate.className = 'file-date-cell';
                            fileDate.textContent = formatRelativeTime(file.updated_at);
                            
                            // Create context menu button (three dots)
                            const contextMenuBtn = document.createElement('button');
                            contextMenuBtn.className = 'file-context-menu-btn';
                            contextMenuBtn.innerHTML = '<i class="fas fa-ellipsis-v"></i>';
                            contextMenuBtn.style.cssText = `
                                background: none;
                                border: none;
                                color: #9ca3af;
                                cursor: pointer;
                                padding: 4px 8px;
                                opacity: 0;
                                transition: opacity 0.2s;
                                position: absolute;
                                right: 10px;
                                top: 50%;
                                transform: translateY(-50%);
                            `;
                            
                            // Show context button on hover
                            fileItem.addEventListener('mouseenter', () => {
                                contextMenuBtn.style.opacity = '0.7';
                            });
                            fileItem.addEventListener('mouseleave', (e) => {
                                // Check if we're moving to the context menu or its button
                                const relatedTarget = e.relatedTarget;
                                const contextMenu = document.querySelector('.file-context-dropdown');
                                
                                // Don't hide if moving to context button or menu
                                if (relatedTarget && (
                                    relatedTarget === contextMenuBtn ||
                                    relatedTarget.closest('.file-context-dropdown') ||
                                    (contextMenu && contextMenu.contains(relatedTarget))
                                )) {
                                    return;
                                }
                                
                                contextMenuBtn.style.opacity = '0';
                            });
                            
                            // Context menu click handler
                            contextMenuBtn.addEventListener('click', (e) => {
                                e.stopPropagation();
                                
                                // Remove any existing context menu
                                const existingMenu = document.querySelector('.file-context-dropdown');
                                if (existingMenu) {
                                    existingMenu.remove();
                                }
                                
                                // Create context menu
                                const contextMenu = document.createElement('div');
                                contextMenu.className = 'file-context-dropdown';
                                
                                // Get button position
                                const btnRect = contextMenuBtn.getBoundingClientRect();
                                const menuTop = btnRect.bottom + window.scrollY + 5;
                                const menuLeft = btnRect.right + window.scrollX - 160;
                                
                                contextMenu.style.cssText = `
                                    position: fixed;
                                    top: ${btnRect.bottom + 5}px;
                                    left: ${btnRect.right - 160}px;
                                    background: #2a2a2a;
                                    border: 1px solid #444;
                                    border-radius: 6px;
                                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
                                    z-index: 1000;
                                    min-width: 150px;
                                    padding: 4px;
                                `;
                                
                                // Delete option
                                const deleteOption = document.createElement('button');
                                deleteOption.style.cssText = `
                                    display: flex;
                                    align-items: center;
                                    gap: 8px;
                                    width: 100%;
                                    padding: 8px 12px;
                                    background: none;
                                    border: none;
                                    color: #e2e8f0;
                                    cursor: pointer;
                                    text-align: left;
                                    font-size: 14px;
                                    transition: background 0.2s;
                                    border-radius: 4px;
                                `;
                                deleteOption.innerHTML = '<i class="fas fa-trash"></i> Delete';
                                deleteOption.onmouseover = function() { this.style.background = 'rgba(239, 68, 68, 0.1)'; this.style.color = '#ef4444'; };
                                deleteOption.onmouseout = function() { this.style.background = 'transparent'; this.style.color = '#e2e8f0'; };
                                deleteOption.addEventListener('click', () => {
                                    contextMenu.remove();
                                    if (confirm(`Are you sure you want to delete "${file.name}"? This action cannot be undone.`)) {
                                        deleteFile(file.id);
                                    }
                                });
                                
                                contextMenu.appendChild(deleteOption);
                                document.body.appendChild(contextMenu);
                                
                                // Keep context button visible when hovering over the menu
                                contextMenu.addEventListener('mouseenter', () => {
                                    contextMenuBtn.style.opacity = '0.7';
                                });
                                
                                contextMenu.addEventListener('mouseleave', (e) => {
                                    // Check if we're going back to the file item
                                    if (!fileItem.contains(e.relatedTarget)) {
                                        contextMenuBtn.style.opacity = '0';
                                        contextMenu.remove();
                                    }
                                });
                                
                                // Close menu when clicking outside
                                const closeMenu = (event) => {
                                    if (!contextMenu.contains(event.target) && event.target !== contextMenuBtn) {
                                        contextMenu.remove();
                                        document.removeEventListener('click', closeMenu);
                                    }
                                };
                                setTimeout(() => document.addEventListener('click', closeMenu), 0);
                            });
                            
                            // Make file item container relative for absolute positioning
                            fileItem.style.position = 'relative';
                            
                            // Assemble the structure
                            fileItem.appendChild(fileIcon);
                            fileItem.appendChild(fileName);
                            fileItem.appendChild(fileType);
                            fileItem.appendChild(fileOwner);
                            fileItem.appendChild(fileDate);
                            fileItem.appendChild(contextMenuBtn);
                            
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
                        
                        // Auto-open file if specified
                        if (options.openFileId && options.openFileName) {
                            // Directly call the API to load the file content
                            setTimeout(() => {
                                
                                // Call the file content API directly
                                fetch(`/projects/${projectId}/api/files/${options.openFileId}/content/`, {
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
                                    const viewerTitle = document.getElementById('viewer-title');
                                    if (viewerTitle) {
                                        viewerTitle.innerHTML = `
                                            <span id="viewer-title-text">${data.name || options.openFileName}</span>
                                            <button id="viewer-title-edit" style="background: none; border: none; color: #9ca3af; cursor: pointer; margin-left: 8px; padding: 4px; opacity: 0.7;" title="Edit name">
                                                <i class="fas fa-pencil" style="font-size: 12px;"></i>
                                            </button>
                                        `;
                                    }
                                    
                                    // Store current file data
                                    window.currentFileData = {
                                        fileId: options.openFileId,
                                        fileName: data.name || options.openFileName,
                                        fileType: data.type,
                                        content: data.content
                                    };
                                    
                                    // Render the content
                                    const viewerMarkdown = document.getElementById('viewer-markdown');
                                    if (viewerMarkdown) {
                                        // Configure marked if not already configured
                                        if (typeof marked !== 'undefined' && !window.markedConfigured) {
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
                                        }
                                        
                                        // Check if content appears to be markdown by looking for common markdown patterns
                                        const isMarkdownContent = (content) => {
                                            if (!content) return false;
                                            // Check for headers, lists, code blocks, tables, links, or emphasis
                                            return /^#{1,6}\s|^\*\s|^\-\s|^\d+\.\s|```|^\|.*\|$|\[.*\]\(.*\)|\*\*.*\*\*|\*.*\*/m.test(content);
                                        };
                                        
                                        // Always render as markdown if it contains markdown patterns or is a known markdown type
                                        const knownMarkdownTypes = ['prd', 'implementation', 'design', 'analysis', 'documentation', 'readme'];
                                        if (knownMarkdownTypes.includes(data.type) || isMarkdownContent(data.content)) {
                                            // Render as markdown
                                            viewerMarkdown.innerHTML = marked.parse(data.content || '');
                                        } else {
                                            // Render as plain text
                                            viewerMarkdown.innerHTML = (data.content || '').replace(/\n/g, '<br>').replace(/\t/g, '&nbsp;&nbsp;&nbsp;&nbsp;');
                                        }
                                    }
                                    
                                    // Set metadata
                                    const viewerMeta = document.getElementById('viewer-meta');
                                    if (viewerMeta) {
                                        viewerMeta.innerHTML = `
                                            <span><i class="fas fa-user"></i> ${data.owner || 'Unknown'}</span>
                                            <span><i class="fas fa-calendar"></i> ${data.created_at ? new Date(data.created_at).toLocaleDateString() : 'Unknown'}</span>
                                            <span><i class="fas fa-tag"></i> ${data.type_display || data.type || 'Document'}</span>
                                        `;
                                    }
                                    
                                })
                                .catch(error => {
                                    console.error('[ArtifactsLoader] Error loading file content:', error);
                                    showToast('Failed to load file content', 'error');
                                });
                            }, 100); // Small delay to ensure DOM is ready
                        }
                        
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
                    'analysis': 'fas fa-chart-line',
                    'documentation': 'fas fa-book',
                    'readme': 'fas fa-info-circle',
                    'report': 'fas fa-file-contract',
                    'research': 'fas fa-microscope',
                    'spec': 'fas fa-clipboard-list',
                    'other': 'fas fa-file'
                };
                // Return specific icon if available, otherwise return generic file icon
                return icons[type.toLowerCase()] || icons.other;
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
                
                
                // Ensure artifacts panel is open and documents tab is active
                const artifactsPanel = document.getElementById('artifacts-panel');
                const isArtifactsPanelOpen = artifactsPanel && artifactsPanel.classList.contains('expanded');
                
                if (!isArtifactsPanelOpen) {
                    if (window.ArtifactsPanel && typeof window.ArtifactsPanel.toggle === 'function') {
                        window.ArtifactsPanel.toggle(true); // Force open
                    }
                }
                
                // Switch to filebrowser tab instead of documents
                const filebrowserTab = document.querySelector('[data-tab="filebrowser"]');
                if (filebrowserTab && !filebrowserTab.classList.contains('active')) {
                    
                    // Try multiple methods to switch tab
                    if (window.switchTab) {
                        window.switchTab('filebrowser');
                    } else {
                        // Fallback: manually trigger tab switch
                        
                        // Remove active class from all tabs and panes
                        document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
                        document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
                        
                        // Activate filebrowser tab
                        filebrowserTab.classList.add('active');
                        const filebrowserPane = document.getElementById('filebrowser');
                        if (filebrowserPane) {
                            filebrowserPane.classList.add('active');
                        }
                    }
                }
                
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
                    
                    // Set title with inline edit capability
                    viewerTitle.innerHTML = `
                        <span id="viewer-title-text" title="${data.name || fileName}">${data.name || fileName}</span>
                        <button id="viewer-title-edit" title="Edit name">
                            <i class="fas fa-pencil" style="font-size: 12px;"></i>
                        </button>
                    `;
                    
                    // Add inline edit functionality
                    const titleEditBtn = document.getElementById('viewer-title-edit');
                    const titleText = document.getElementById('viewer-title-text');
                    
                    if (titleEditBtn && titleText) {
                        titleEditBtn.addEventListener('click', function(e) {
                            e.stopPropagation();
                            
                            // Get current name
                            const currentName = titleText.textContent;
                            
                            // Create input field
                            const input = document.createElement('input');
                            input.type = 'text';
                            input.value = currentName;
                            input.style.cssText = `
                                background: #1a1a1a;
                                border: 1px solid #333;
                                border-radius: 4px;
                                color: #e2e8f0;
                                padding: 4px 8px;
                                font-size: 16px;
                                font-weight: 600;
                                width: 300px;
                            `;
                            
                            // Replace text with input
                            titleText.style.display = 'none';
                            titleEditBtn.style.display = 'none';
                            viewerTitle.insertBefore(input, titleText);
                            input.focus();
                            input.select();
                            
                            // Handle save
                            const saveTitle = async () => {
                                const newName = input.value.trim();
                                if (newName && newName !== currentName) {
                                    try {
                                        const response = await fetch(`/projects/${projectId}/api/files/${fileId}/rename/`, {
                                            method: 'POST',
                                            headers: {
                                                'Content-Type': 'application/json',
                                                'X-CSRFToken': getCsrfToken(),
                                            },
                                            body: JSON.stringify({ name: newName })
                                        });
                                        
                                        const result = await response.json();
                                        if (result.success) {
                                            titleText.textContent = newName;
                                            window.currentFileData.fileName = newName;
                                            showToast('File renamed successfully', 'success');
                                            // Refresh file list
                                            fetchFiles(currentPage);
                                        } else {
                                            showToast('Failed to rename file: ' + (result.error || 'Unknown error'), 'error');
                                        }
                                    } catch (error) {
                                        console.error('Error renaming file:', error);
                                        showToast('Failed to rename file', 'error');
                                    }
                                }
                                
                                // Restore original view
                                input.remove();
                                titleText.style.display = '';
                                titleEditBtn.style.display = '';
                            };
                            
                            // Handle cancel
                            const cancelEdit = () => {
                                input.remove();
                                titleText.style.display = '';
                                titleEditBtn.style.display = '';
                            };
                            
                            // Event listeners
                            input.addEventListener('blur', saveTitle);
                            input.addEventListener('keydown', function(e) {
                                if (e.key === 'Enter') {
                                    e.preventDefault();
                                    saveTitle();
                                } else if (e.key === 'Escape') {
                                    e.preventDefault();
                                    cancelEdit();
                                }
                            });
                        });
                    }
                    
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

                    
                    // Create compact action buttons
                    const viewerActions = document.getElementById('viewer-actions');


                    if (viewerActions) {
                        // Clear existing buttons
                        viewerActions.innerHTML = '';

                        
                        // Common button style
                        const buttonStyle = `
                            background: transparent;
                            border: none;
                            color: #9ca3af;
                            cursor: pointer;
                            padding: 6px;
                            font-size: 14px;
                            transition: all 0.2s;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                        `;
                        

                        // Edit button with full text
                        const editButton = document.createElement('button');
                        editButton.id = 'viewer-edit';
                        editButton.style.cssText = buttonStyle + 'padding: 6px; gap: 6px;';
                        editButton.innerHTML = '<i class="fas fa-edit"></i>';
                        editButton.title = 'Edit full text';
                        editButton.onmouseover = function() { this.style.color = '#e2e8f0'; };
                        editButton.onmouseout = function() { this.style.color = '#9ca3af'; };
                        editButton.addEventListener('click', () => enableEditMode());
                        
                        // Copy button
                        const copyButton = document.createElement('button');
                        copyButton.id = 'viewer-copy';
                        copyButton.style.cssText = buttonStyle;
                        copyButton.innerHTML = '<i class="fas fa-copy"></i>';
                        copyButton.title = 'Copy';
                        copyButton.onmouseover = function() { this.style.color = '#e2e8f0'; };
                        copyButton.onmouseout = function() { this.style.color = '#9ca3af'; };
                        copyButton.addEventListener('click', () => {
                            if (window.currentFileData && window.currentFileData.content) {
                                ArtifactsLoader.copyToClipboard(window.currentFileData.content, 'Markdown content');
                            }
                        });
                        
                        // Options dropdown button
                        const optionsButton = document.createElement('button');
                        optionsButton.id = 'viewer-options';
                        optionsButton.style.cssText = buttonStyle + 'position: relative;';
                        optionsButton.innerHTML = '<i class="fas fa-ellipsis-v"></i>';
                        optionsButton.title = 'More options';
                        optionsButton.onmouseover = function() { this.style.color = '#e2e8f0'; };
                        optionsButton.onmouseout = function() { this.style.color = '#9ca3af'; };
                        
                        // Create dropdown menu
                        const dropdownMenu = document.createElement('div');
                        dropdownMenu.id = 'viewer-options-dropdown';
                        dropdownMenu.style.cssText = `
                            position: absolute;
                            top: 100%;
                            right: 0;
                            background: #1a1a1a;
                            border: 1px solid #333;
                            border-radius: 6px;
                            min-width: 160px;
                            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                            display: none;
                            z-index: 1000;
                            margin-top: 4px;
                        `;
                        
                        // Download option with submenu
                        const downloadOption = document.createElement('div');
                        downloadOption.style.cssText = `
                            position: relative;
                        `;
                        
                        const downloadButton = document.createElement('button');
                        downloadButton.style.cssText = `
                            display: flex;
                            align-items: center;
                            gap: 8px;
                            width: 100%;
                            padding: 8px 12px;
                            background: transparent;
                            border: none;
                            color: #e2e8f0;
                            cursor: pointer;
                            text-align: left;
                            font-size: 14px;
                            transition: background 0.2s;
                        `;
                        downloadButton.innerHTML = '<span><i class="fas fa-download"></i> Download</span>';
                        downloadButton.onmouseover = function() { this.style.background = '#2a2a2a'; };
                        downloadButton.onmouseout = function() { this.style.background = 'transparent'; };
                        
                        // Create download format submenu
                        const downloadSubmenu = document.createElement('div');
                        downloadSubmenu.style.cssText = `
                            position: absolute;
                            right: 100%;
                            top: 0;
                            background: #1a1a1a;
                            border: 1px solid #333;
                            border-radius: 6px;
                            min-width: 120px;
                            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                            display: none;
                            margin-right: 4px;
                        `;
                        
                        // PDF option
                        const pdfOption = document.createElement('button');
                        pdfOption.style.cssText = `
                            display: flex;
                            align-items: center;
                            gap: 8px;
                            width: 100%;
                            padding: 8px 12px;
                            background: transparent;
                            border: none;
                            color: #e2e8f0;
                            cursor: pointer;
                            text-align: left;
                            font-size: 14px;
                            transition: background 0.2s;
                        `;
                        pdfOption.innerHTML = '<i class="fas fa-file-pdf"></i> PDF';
                        pdfOption.onmouseover = function() { this.style.background = '#2a2a2a'; };
                        pdfOption.onmouseout = function() { this.style.background = 'transparent'; };
                        pdfOption.addEventListener('click', () => {
                            dropdownMenu.style.display = 'none';
                            if (window.currentFileData) {
                                const title = window.currentFileData.fileName || 'Document';
                                const content = window.currentFileData.content || '';
                                ArtifactsLoader.downloadFileAsPDF(projectId, title, content);
                            }
                        });
                        
                        // DOC option
                        const docOption = document.createElement('button');
                        docOption.style.cssText = `
                            display: flex;
                            align-items: center;
                            gap: 8px;
                            width: 100%;
                            padding: 8px 12px;
                            background: transparent;
                            border: none;
                            color: #e2e8f0;
                            cursor: pointer;
                            text-align: left;
                            font-size: 14px;
                            transition: background 0.2s;
                        `;
                        docOption.innerHTML = '<i class="fas fa-file-word"></i> DOC';
                        docOption.onmouseover = function() { this.style.background = '#2a2a2a'; };
                        docOption.onmouseout = function() { this.style.background = 'transparent'; };
                        docOption.addEventListener('click', () => {
                            dropdownMenu.style.display = 'none';
                            if (window.currentFileData) {
                                const fileName = window.currentFileData.fileName || 'document';
                                const content = window.currentFileData.content || '';
                                ArtifactsLoader.downloadAsDoc(fileName, content);
                            }
                        });
                        
                        // Markdown option
                        const mdOption = document.createElement('button');
                        mdOption.style.cssText = `
                            display: flex;
                            align-items: center;
                            gap: 8px;
                            width: 100%;
                            padding: 8px 12px;
                            background: transparent;
                            border: none;
                            color: #e2e8f0;
                            cursor: pointer;
                            text-align: left;
                            font-size: 14px;
                            transition: background 0.2s;
                        `;
                        mdOption.innerHTML = '<i class="fas fa-file-code"></i> Markdown';
                        mdOption.onmouseover = function() { this.style.background = '#2a2a2a'; };
                        mdOption.onmouseout = function() { this.style.background = 'transparent'; };
                        mdOption.addEventListener('click', () => {
                            dropdownMenu.style.display = 'none';
                            if (window.currentFileData) {
                                const fileName = window.currentFileData.fileName || 'document';
                                const content = window.currentFileData.content || '';
                                ArtifactsLoader.downloadAsMarkdown(fileName, content);
                            }
                        });
                        
                        downloadSubmenu.appendChild(pdfOption);
                        downloadSubmenu.appendChild(docOption);
                        downloadSubmenu.appendChild(mdOption);
                        
                        downloadOption.appendChild(downloadButton);
                        downloadOption.appendChild(downloadSubmenu);
                        
                        // Show submenu on hover - use the parent div for better hover handling
                        downloadOption.addEventListener('mouseenter', () => {
                            downloadSubmenu.style.display = 'block';
                        });
                        
                        downloadOption.addEventListener('mouseleave', () => {
                            downloadSubmenu.style.display = 'none';
                        });
                        
                        // Delete option
                        const deleteOption = document.createElement('button');
                        deleteOption.style.cssText = `
                            display: flex;
                            align-items: center;
                            gap: 8px;
                            width: 100%;
                            padding: 8px 12px;
                            background: transparent;
                            border: none;
                            color: #ef4444;
                            cursor: pointer;
                            text-align: left;
                            font-size: 14px;
                            transition: background 0.2s;
                        `;
                        deleteOption.innerHTML = '<i class="fas fa-trash"></i> Delete';
                        deleteOption.onmouseover = function() { this.style.background = 'rgba(239, 68, 68, 0.1)'; };
                        deleteOption.onmouseout = function() { this.style.background = 'transparent'; };
                        deleteOption.addEventListener('click', () => {
                            dropdownMenu.style.display = 'none';
                            const fileName = data.name || window.currentFileData.fileName;
                            if (confirm(`Are you sure you want to delete "${fileName}"? This action cannot be undone.`)) {
                                deleteFile(fileId);
                            }
                        });
                        
                        // Version history option
                        const versionOption = document.createElement('button');
                        versionOption.style.cssText = `
                            display: flex;
                            align-items: center;
                            gap: 8px;
                            width: 100%;
                            padding: 8px 12px;
                            background: transparent;
                            border: none;
                            color: #e2e8f0;
                            cursor: pointer;
                            text-align: left;
                            font-size: 14px;
                            transition: background 0.2s;
                        `;
                        versionOption.innerHTML = '<i class="fas fa-history"></i> Version History';
                        versionOption.onmouseover = function() { this.style.background = '#2a2a2a'; };
                        versionOption.onmouseout = function() { this.style.background = 'transparent'; };
                        versionOption.addEventListener('click', () => {
                            dropdownMenu.style.display = 'none';
                            const currentFileId = window.currentFileData ? window.currentFileData.fileId : fileId;
                            showVersionHistory(currentFileId);
                        });
                        
                        dropdownMenu.appendChild(versionOption);
                        dropdownMenu.appendChild(downloadOption);
                        dropdownMenu.appendChild(deleteOption);
                        
                        // Toggle dropdown
                        optionsButton.addEventListener('click', (e) => {
                            e.stopPropagation();
                            const isOpen = dropdownMenu.style.display === 'block';
                            dropdownMenu.style.display = isOpen ? 'none' : 'block';
                        });
                        
                        // Close dropdown when clicking outside
                        document.addEventListener('click', () => {
                            dropdownMenu.style.display = 'none';
                        });
                        
                        // Create wrapper for options button with dropdown
                        const optionsWrapper = document.createElement('div');
                        optionsWrapper.style.cssText = 'position: relative; display: flex;';
                        optionsWrapper.appendChild(optionsButton);
                        optionsWrapper.appendChild(dropdownMenu);
                        
                        // Append buttons to actions container
                        viewerActions.appendChild(editButton);
                        viewerActions.appendChild(copyButton);
                        viewerActions.appendChild(optionsWrapper);
                        
                        // Ensure viewer actions are always visible
                        viewerActions.style.display = 'flex';
                    }
                    
                    // Configure marked if not already configured
                    if (typeof marked !== 'undefined' && !window.markedConfigured) {
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
                    }
                    
                    // Check if content appears to be markdown by looking for common markdown patterns
                    const isMarkdownContent = (content) => {
                        if (!content) return false;
                        // Check for headers, lists, code blocks, tables, links, or emphasis
                        return /^#{1,6}\s|^\*\s|^\-\s|^\d+\.\s|```|^\|.*\|$|\[.*\]\(.*\)|\*\*.*\*\*|\*.*\*/m.test(content);
                    };
                    
                    // Always render as markdown if it contains markdown patterns or is a known markdown type
                    const knownMarkdownTypes = ['prd', 'implementation', 'design', 'analysis', 'documentation', 'readme'];
                    if (knownMarkdownTypes.includes(data.type) || isMarkdownContent(content)) {
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
                    
                    // File info is now stored in window.currentFileData and used by action buttons
                })
                .catch(error => {
                    console.error('[ArtifactsLoader] Error loading file content:', error);
                    showToast('Failed to load file content', 'error');
                });
            };
            window.viewFileContent = viewFileContent;
            
            // Auto-save functionality
            let autoSaveTimer = null;
            let hasUnsavedChanges = false;
            
            // Function to perform auto-save
            const performAutoSave = async () => {
                if (hasUnsavedChanges && window.currentWysiwygEditor) {
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
                
                // Hide all viewer buttons
                const editButton = document.getElementById('viewer-edit');
                const copyButton = document.getElementById('viewer-copy');
                const versionButton = document.getElementById('viewer-versions');
                const optionsButton = document.getElementById('viewer-options');
                
                if (editButton) editButton.style.display = 'none';
                if (copyButton) copyButton.style.display = 'none';
                if (versionButton) versionButton.style.display = 'none';
                if (optionsButton) optionsButton.style.display = 'none';
                
                // Add save and cancel buttons
                let saveButton = document.getElementById('viewer-save');
                let cancelButton = document.getElementById('viewer-cancel');
                
                if (!saveButton) {
                    saveButton = document.createElement('button');
                    saveButton.id = 'viewer-save';
                    saveButton.className = 'btn btn-sm';
                    saveButton.style = 'padding: 8px 16px; background: #10b981; color: white; border: none; border-radius: 6px; cursor: pointer; display: flex; align-items: center; gap: 6px;';
                    saveButton.innerHTML = '<i class="fas fa-save"></i> Save';
                    saveButton.title = 'Save changes';
                    saveButton.addEventListener('click', () => saveFileContent());
                    const viewerActions = document.getElementById('viewer-actions');
                    if (viewerActions) viewerActions.appendChild(saveButton);
                }
                
                if (!cancelButton) {
                    cancelButton = document.createElement('button');
                    cancelButton.id = 'viewer-cancel';
                    cancelButton.className = 'btn btn-sm';
                    cancelButton.style = 'padding: 8px 16px; background: #6b7280; color: white; border: none; border-radius: 6px; cursor: pointer; margin-left: 10px; display: flex; align-items: center; gap: 6px;';
                    cancelButton.innerHTML = '<i class="fas fa-times"></i> Cancel';
                    cancelButton.title = 'Cancel editing';
                    cancelButton.addEventListener('click', () => cancelEditMode());
                    if (viewerActions) viewerActions.appendChild(cancelButton);
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
                    
                    
                    const response = await fetch(url, {
                        method: method,
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken(),
                        },
                        body: body
                    });
                    
                    
                    let data;
                    try {
                        data = await response.json();
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
                const copyButton = document.getElementById('viewer-copy');
                const versionButton = document.getElementById('viewer-versions');
                const optionsButton = document.getElementById('viewer-options');
                if (editButton) editButton.style.display = 'flex';
                if (copyButton) copyButton.style.display = 'flex';
                if (versionButton) versionButton.style.display = 'flex';
                if (optionsButton) optionsButton.style.display = 'flex';
                
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
                // Get the file information from the DOM data attributes
                const fileItem = document.querySelector(`[data-file-id="${fileId}"]`);
                let fileType = 'other';
                let fileName = '';
                
                if (fileItem) {
                    // Use data attributes which have the actual backend values
                    fileType = fileItem.dataset.fileType || 'other';
                    fileName = fileItem.dataset.fileName || '';
                    
                    console.log('[ArtifactsLoader] Delete - Using data attributes:', {
                        fileType: fileType,
                        fileName: fileName
                    });
                }
                
                console.log('[ArtifactsLoader] Deleting file:', {
                    fileId: fileId,
                    fileName: fileName,
                    fileType: fileType,
                    url: `/projects/${projectId}/api/files/?type=${fileType}&name=${encodeURIComponent(fileName)}`
                });
                
                // Use the unified files API with query parameters
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
                        // Go back to file browser
                        const fileBrowserViewer = document.getElementById('filebrowser-viewer');
                        const fileBrowserMain = document.getElementById('filebrowser-main');
                        if (fileBrowserViewer && fileBrowserMain) {
                            fileBrowserViewer.style.display = 'none';
                            fileBrowserMain.style.display = 'flex';
                        }
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
                        await saveFileContent(true); // true for auto-save
                    }
                    
                    // If still in edit mode, cancel it without refreshing
                    if (window.currentWysiwygEditor) {
                        // Stop auto-save timer
                        if (window.autoSaveTimer) {
                            clearInterval(window.autoSaveTimer);
                            window.autoSaveTimer = null;
                        }
                        
                        // Clear reference
                        window.currentWysiwygEditor = null;
                        
                        // Remove the editor container
                        const editorContainer = document.getElementById('wysiwyg-editor');
                        if (editorContainer) {
                            editorContainer.remove();
                        }
                        
                        // Show viewer content again
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
                        const copyButton = document.getElementById('viewer-copy');
                        const versionButton = document.getElementById('viewer-versions');
                        const optionsButton = document.getElementById('viewer-options');
                        if (editButton) editButton.style.display = 'flex';
                        if (copyButton) copyButton.style.display = 'flex';
                        if (versionButton) versionButton.style.display = 'flex';
                        if (optionsButton) optionsButton.style.display = 'flex';
                    }
                    
                    // Navigate back to file list
                    fileBrowserViewer.style.display = 'none';
                    fileBrowserMain.style.display = 'flex';
                    
                    // Refresh the file list
                    fetchFiles(currentPage);
                });
            }
            
            // Event listeners for viewer buttons are now attached when buttons are created dynamically
            
            // Initial load
            fetchFiles(1);
        } // End of loadFileBrowser function
    }; // End of ArtifactsLoader object

    // ArtifactsLoader is now ready to use
    
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

// Global functions for checklist item editing (accessible from inline onclick handlers)
window.editChecklistItem = function(itemId) {
    const projectId = window.getCurrentProjectId ? window.getCurrentProjectId() : window.ArtifactsLoader?.getCurrentProjectId();
    if (!projectId) {
        console.error('[EditChecklistItem] No project ID available');
        alert('Unable to edit item: No project ID found');
        return;
    }

    // Fetch current checklist data
    fetch(`/projects/${projectId}/api/checklist/`)
        .then(response => response.json())
        .then(data => {
            const checklist = data.tickets || [];
            const item = checklist.find(i => i.id == itemId);

            if (!item) {
                alert('Checklist item not found');
                return;
            }

            const escapeHtml = (value) => {
                if (value === null || value === undefined) {
                    return '';
                }
                return String(value)
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#39;');
            };

            const formatStatusText = (value) => {
                if (!value) {
                    return 'OPEN';
                }
                return value.replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase()).toUpperCase();
            };

            const formatTitleUpper = (value, fallback = '') => {
                const source = value || fallback;
                if (!source) {
                    return fallback.toUpperCase();
                }
                return String(source)
                    .toLowerCase()
                    .replace(/(^|\s|[_-])(\w)/g, (_, sep, char) => `${sep === '_' || sep === '-' ? ' ' : sep}${char.toUpperCase()}`)
                    .trim()
                    .toUpperCase();
            };

            // Create modal overlay
            const overlay = document.createElement('div');
            overlay.className = 'edit-checklist-overlay';
            overlay.style.cssText = 'position: fixed; inset: 0; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(12px); background: rgba(5,7,12,0.55); z-index: 10000; padding: 24px;';

            // Create modal container
            const modal = document.createElement('div');
            modal.className = 'edit-checklist-modal';
            modal.style.cssText = 'background: rgba(30,30,30,0.88); border: 1px solid rgba(255,255,255,0.05); border-radius: 18px; max-width: 700px; width: 100%; max-height: 92vh; overflow-y: auto; box-shadow: 0 28px 60px rgba(0,0,0,0.55); color: #e2e8f0; padding: 32px; display: flex; flex-direction: column; gap: 24px;';

            const sanitizedDescription = escapeHtml(item.description || '');

            modal.innerHTML = `
                <header style="display: flex; flex-direction: column; gap: 12px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px;">
                        <div style="display: flex; flex-direction: column; gap: 4px;">
                            <span style="font-size: 11px; letter-spacing: 0.18em; text-transform: uppercase; color: rgba(148, 163, 184, 0.6);">Edit Ticket</span>
                            <h3 style="margin: 0; font-size: 22px; font-weight: 600; color: #f8fafc;">${escapeHtml(item.name || 'Checklist Item')}</h3>
                            <span style="font-size: 13px; color: rgba(203, 213, 225, 0.65);">Update ticket details to keep the plan in sync.</span>
                        </div>
                        <button type="button" id="close-edit-modal" style="width: 34px; height: 34px; border-radius: 10px; border: 1px solid rgba(148,163,184,0.2); background: rgba(148,163,184,0.09); color: #ccd3f6; display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 16px;">
                            <span style="transform: translateY(-1px);">×</span>
                        </button>
                    </div>
                    <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                        <span class="ticket-chip" style="padding: 6px 12px; min-height: 26px; border-radius: 9px; font-size: 11px; letter-spacing: 0.09em;">${formatStatusText(item.status)}</span>
                        <span class="ticket-chip" style="padding: 6px 12px; min-height: 26px; border-radius: 9px; font-size: 11px; letter-spacing: 0.09em;">${formatTitleUpper(item.complexity, 'Medium')}</span>
                        <span class="ticket-chip" style="padding: 6px 12px; min-height: 26px; border-radius: 9px; font-size: 11px; letter-spacing: 0.09em;">${formatTitleUpper(item.priority, 'Medium')}</span>
                    </div>
                </header>
                <form id="edit-checklist-form" style="display: flex; flex-direction: column; gap: 20px;">
                    <div style="display: flex; flex-direction: column; gap: 10px;">
                        <label style="font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: rgba(148,163,184,0.65);">Name *</label>
                        <input type="text" id="edit-name" value="${(item.name || '').replace(/"/g, '&quot;')}"
                            style="width: 100%; padding: 12px 14px; background: rgba(12,12,16,0.75); border: 1px solid rgba(71,85,105,0.45); color: #f8fafc; border-radius: 12px; font-size: 15px; font-weight: 500;" required>
                    </div>

                    <div style="display: flex; flex-direction: column; gap: 10px;">
                        <label style="font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: rgba(148,163,184,0.65);">Description</label>
                        <textarea id="edit-description" rows="6"
                            style="width: 100%; padding: 14px; background: rgba(12,12,16,0.75); border: 1px solid rgba(71,85,105,0.45); color: #f1f5f9; border-radius: 12px; font-size: 14px; line-height: 1.6; resize: vertical; min-height: 160px;">${sanitizedDescription}</textarea>
                    </div>

                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(160px,1fr)); gap: 10px; align-items: flex-end;">
                        <div style="display: flex; flex-direction: column; gap: 6px;">
                            <label style="font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: rgba(148,163,184,0.65);">Status</label>
                            <select id="edit-status" class="ticket-form-select">
                                <option value="open" ${item.status === 'open' ? 'selected' : ''}>Open</option>
                                <option value="in_progress" ${item.status === 'in_progress' ? 'selected' : ''}>In Progress</option>
                                <option value="done" ${item.status === 'done' ? 'selected' : ''}>Done</option>
                                <option value="failed" ${item.status === 'failed' ? 'selected' : ''}>Failed</option>
                                <option value="blocked" ${item.status === 'blocked' ? 'selected' : ''}>Blocked</option>
                            </select>
                        </div>
                        <div style="display: flex; flex-direction: column; gap: 6px;">
                            <label style="font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: rgba(148,163,184,0.65);">Priority</label>
                            <select id="edit-priority" class="ticket-form-select">
                                <option value="High" ${item.priority === 'High' ? 'selected' : ''}>High</option>
                                <option value="Medium" ${item.priority === 'Medium' ? 'selected' : ''}>Medium</option>
                                <option value="Low" ${item.priority === 'Low' ? 'selected' : ''}>Low</option>
                            </select>
                        </div>
                        <div style="display: flex; flex-direction: column; gap: 6px;">
                            <label style="font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: rgba(148,163,184,0.65);">Role</label>
                            <select id="edit-role" class="ticket-form-select">
                                <option value="agent" ${item.role === 'agent' ? 'selected' : ''}>Agent</option>
                                <option value="user" ${item.role === 'user' ? 'selected' : ''}>User</option>
                            </select>
                        </div>
                        <div style="display: flex; flex-direction: column; gap: 6px;">
                            <label style="font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: rgba(148,163,184,0.65);">Complexity</label>
                            <select id="edit-complexity" class="ticket-form-select">
                                <option value="simple" ${item.complexity === 'simple' ? 'selected' : ''}>Simple</option>
                                <option value="medium" ${item.complexity === 'medium' ? 'selected' : ''}>Medium</option>
                                <option value="complex" ${item.complexity === 'complex' ? 'selected' : ''}>Complex</option>
                            </select>
                        </div>
                    </div>

                    <label style="display: inline-flex; align-items: center; gap: 10px; padding: 14px; border-radius: 12px; background: rgba(15,23,42,0.4); border: 1px solid rgba(71,85,105,0.45); color: rgba(226,232,240,0.8); font-size: 13px;">
                        <input type="checkbox" id="edit-requires-worktree" ${item.requires_worktree ? 'checked' : ''}
                            style="width: 18px; height: 18px; border-radius: 4px; border: 1px solid rgba(71,85,105,0.6); background: rgba(12,12,16,0.75);">
                        Requires git worktree for code changes
                    </label>

                    <div style="display: flex; justify-content: flex-end; gap: 10px;">
                        <button type="button" id="cancel-edit-btn"
                            style="padding: 12px 20px; border-radius: 10px; border: 1px solid rgba(148,163,184,0.25); background: rgba(51,65,85,0.35); color: #e2e8f0; font-size: 14px; font-weight: 600; cursor: pointer;">
                            Cancel
                        </button>
                        <button type="submit" id="save-edit-btn"
                            style="padding: 12px 20px; border-radius: 10px; border: none; background: linear-gradient(135deg, #7c3aed, #a855f7); color: #f8fafc; font-size: 14px; font-weight: 600; cursor: pointer; box-shadow: 0 10px 26px rgba(124,58,237,0.28);">
                            Save Changes
                        </button>
                    </div>
                </form>
            `;

            overlay.appendChild(modal);
            document.body.appendChild(overlay);

            const cancelBtn = modal.querySelector('#cancel-edit-btn');
            const saveBtn = modal.querySelector('#save-edit-btn');
            const originalSaveLabel = saveBtn.innerHTML;
            const closeBtn = modal.querySelector('#close-edit-modal');

            const removeModal = () => overlay.remove();

            cancelBtn.addEventListener('click', removeModal);
            closeBtn.addEventListener('click', removeModal);
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    removeModal();
                }
            });

            // Handle form submission
            const form = modal.querySelector('#edit-checklist-form');
            form.addEventListener('submit', async (e) => {
                e.preventDefault();

                const updatedData = {
                    item_id: itemId,
                    name: document.getElementById('edit-name').value,
                    description: document.getElementById('edit-description').value,
                    status: document.getElementById('edit-status').value,
                    priority: document.getElementById('edit-priority').value,
                    role: document.getElementById('edit-role').value,
                    complexity: document.getElementById('edit-complexity').value,
                    requires_worktree: document.getElementById('edit-requires-worktree').checked
                };

                // Disable submit button and show loading state
                saveBtn.disabled = true;
                saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';

                try {
                    const getCsrfToken = () => {
                        return document.querySelector('[name=csrfmiddlewaretoken]')?.value
                            || document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1]
                            || '';
                    };

                    const response = await fetch(`/projects/${projectId}/api/checklist/update/`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken()
                        },
                        body: JSON.stringify(updatedData)
                    });

                    const result = await response.json();

                    if (result.success) {
                        if (window.showToast) {
                            window.showToast('Checklist item updated successfully', 'success');
                        }
                        overlay.remove();

                        // Reload checklist to show updated data
                        if (window.ArtifactsLoader && window.ArtifactsLoader.loadChecklist) {
                            window.ArtifactsLoader.loadChecklist(projectId);
                        }
                    } else {
                        throw new Error(result.error || 'Failed to update item');
                    }
                } catch (error) {
                    console.error('Error updating checklist item:', error);
                    if (window.showToast) {
                        window.showToast('Error updating item: ' + error.message, 'error');
                    } else {
                        alert('Error updating item: ' + error.message);
                    }
                    // Re-enable button
                    saveBtn.disabled = false;
                    saveBtn.innerHTML = originalSaveLabel;
                }
            });
        })
        .catch(error => {
            console.error('Error fetching checklist data:', error);
            alert('Error loading checklist data: ' + error.message);
        });
};

window.toggleChecklistStatus = function(itemId, currentStatus) {
    const projectId = window.getCurrentProjectId ? window.getCurrentProjectId() : window.ArtifactsLoader?.getCurrentProjectId();
    if (!projectId) {
        console.error('[ToggleChecklistStatus] No project ID available');
        alert('Unable to toggle status: No project ID found');
        return;
    }

    // Define status cycle: open -> in_progress -> done -> open
    const statusCycle = {
        'open': 'in_progress',
        'in_progress': 'done',
        'done': 'open',
        'failed': 'open',
        'blocked': 'open'
    };

    const newStatus = statusCycle[currentStatus] || 'in_progress';

    const getCsrfToken = () => {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value
            || document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1]
            || '';
    };

    // Update status via API
    fetch(`/projects/${projectId}/api/checklist/update/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({ item_id: itemId, status: newStatus })
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            if (window.showToast) {
                window.showToast(`Status updated to ${newStatus.replace('_', ' ')}`, 'success');
            }

            // Reload checklist to show updated data
            if (window.ArtifactsLoader && window.ArtifactsLoader.loadChecklist) {
                window.ArtifactsLoader.loadChecklist(projectId);
            }
        } else {
            throw new Error(result.error || 'Failed to update status');
        }
    })
    .catch(error => {
        console.error('Error toggling status:', error);
        if (window.showToast) {
            window.showToast('Error updating status: ' + error.message, 'error');
        } else {
            alert('Error updating status: ' + error.message);
        }
    });
};
