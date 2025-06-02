/**
 * Artifacts Loader JavaScript
 * Handles loading artifact data from the server and updating the artifacts panel
 */
document.addEventListener('DOMContentLoaded', function() {
    // Initialize the artifact loaders
    window.ArtifactsLoader = {
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
         */
        loadPRD: function(projectId) {
            console.log(`[ArtifactsLoader] loadPRD called with project ID: ${projectId}`);
            
            if (!projectId) {
                console.warn('[ArtifactsLoader] No project ID provided for loading PRD');
                return;
            }
            
            // Get PRD tab content element
            const prdTab = document.getElementById('prd');
            if (!prdTab) {
                console.warn('[ArtifactsLoader] PRD tab element not found');
                return;
            }
            
            // Show loading state
            console.log('[ArtifactsLoader] Showing loading state for PRD');
            prdTab.innerHTML = '<div class="loading-state"><div class="spinner"></div><div>Loading PRD...</div></div>';
            
            // Fetch PRD from API
            const url = `/projects/${projectId}/api/prd/`;
            console.log(`[ArtifactsLoader] Fetching PRD from API: ${url}`);
            
            fetch(url)
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
                        prdTab.innerHTML = `
                            <div class="empty-state">
                                <div class="empty-state-icon">
                                    <i class="fas fa-file-alt"></i>
                                </div>
                                <div class="empty-state-text">
                                    No PRD available yet.
                                </div>
                            </div>
                        `;
                        return;
                    }
                    
                    // Render PRD content with markdown
                    prdTab.innerHTML = `
                        <div class="prd-container">
                            <div class="prd-header">
                                <h2>${data.title || 'Product Requirement Document'}</h2>
                                <div class="prd-meta">
                                    ${data.updated_at ? `<span>Last updated: ${data.updated_at}</span>` : ''}
                                </div>
                            </div>
                            <div class="prd-content markdown-content">
                                ${typeof marked !== 'undefined' ? marked.parse(prdContent) : prdContent}
                            </div>
                        </div>
                    `;
                })
                .catch(error => {
                    console.error('Error fetching PRD:', error);
                    prdTab.innerHTML = `
                        <div class="error-state">
                            <div class="error-state-icon">
                                <i class="fas fa-exclamation-triangle"></i>
                            </div>
                            <div class="error-state-text">
                                Error loading PRD. Please try again.
                            </div>
                        </div>
                    `;
                });
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
                                <div class="implementation-meta">
                                    ${data.updated_at ? `<span>Last updated: ${data.updated_at}</span>` : ''}
                                </div>
                            </div>
                            <div class="implementation-content markdown-content">
                                ${typeof marked !== 'undefined' ? marked.parse(implementationContent) : implementationContent}
                            </div>
                        </div>
                    `;
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
            const url = `/projects/${projectId}/api/tickets/`;
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
                    // Process tickets data
                    const tickets = data.tickets || [];
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
                    
                    // Extract unique features for filter dropdown
                    const features = [...new Set(tickets.map(ticket => 
                        ticket.feature ? ticket.feature.name : 'Unknown'
                    ))].sort();
                    
                    // Create container for tickets with filter
                    ticketsTab.innerHTML = `
                        <div class="tickets-container">
                            <div class="ticket-filters">
                                <div class="filter-options">
                                    <div class="filter-group">
                                        <select id="feature-filter" class="feature-filter-dropdown">
                                            <option value="all">All Features</option>
                                            ${features.map(feature => `<option value="${feature}">${feature}</option>`).join('')}
                                        </select>
                                        <button id="clear-filters" class="clear-filters-btn" title="Clear filters">
                                            <i class="fas fa-times"></i>
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
                    const featureFilter = document.getElementById('feature-filter');
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
                    const renderTickets = (filterFeature = 'all') => {
                        let filteredTickets = [...tickets];
                        
                        // Apply feature filter if not 'all'
                        if (filterFeature !== 'all') {
                            filteredTickets = filteredTickets.filter(ticket => 
                                ticket.feature && ticket.feature.name === filterFeature
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
                                const featurePriority = ticket.feature ? ticket.feature.priority || 'medium' : 'medium';
                                const priorityClass = `${featurePriority}-priority`;
                                const status = ticket.status || 'open';
                                const isHighlighted = filterFeature !== 'all' && ticket.feature && ticket.feature.name === filterFeature;
                                
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
                                    <div class="ticket-card" data-ticket-id="${ticket.id}" data-feature="${ticket.feature ? ticket.feature.name : 'Unknown'}">
                                        <div class="card-header ${status}">
                                            <h4 class="card-title">${ticket.title}</h4>
                                        </div>
                                        <div class="card-body">
                                            <div class="card-description">${displayDescription}</div>
                                            
                                            <div class="card-meta">
                                                <div class="card-tags">
                                                    <span class="feature-tag ${priorityClass} ${isHighlighted ? 'filter-active' : ''}">
                                                        <i class="fas fa-tag"></i> ${ticket.feature ? ticket.feature.name : 'Unknown Feature'}
                                                    </span>
                                                    <span class="status-tag status-${status}">
                                                        ${status.replace('_', ' ').charAt(0).toUpperCase() + status.replace('_', ' ').slice(1)}
                                                    </span>
                                                </div>
                                                <button class="view-details-btn" data-ticket-id="${ticket.id}" title="View details">
                                                    <i class="fas fa-info-circle"></i>
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
                                            <p class="ticket-id"><strong>ID:</strong> ${ticket.ticket_id}</p>
                                            <p class="ticket-title"><strong>Title:</strong> ${ticket.title}</p>
                                            <p class="ticket-status"><strong>Status:</strong> ${ticket.status.replace('_', ' ').charAt(0).toUpperCase() + ticket.status.replace('_', ' ').slice(1)}</p>
                                            <p class="ticket-feature"><strong>Feature:</strong> ${ticket.feature.name}</p>
                                        </div>
                                        
                                        <div class="drawer-section">
                                            <h4 class="section-title">Description</h4>
                                            <div class="section-content description-content">
                                                ${ticket.description.replace(/\n/g, '<br>')}
                                            </div>
                                        </div>
                                        
                                        <div class="drawer-section">
                                            <h4 class="section-title">Frontend Tasks</h4>
                                            <div class="section-content">
                                                ${ticket.frontend_tasks ? ticket.frontend_tasks.replace(/\n/g, '<br>') : 'No frontend tasks specified.'}
                                            </div>
                                        </div>
                                        
                                        <div class="drawer-section">
                                            <h4 class="section-title">Backend Tasks</h4>
                                            <div class="section-content">
                                                ${ticket.backend_tasks ? ticket.backend_tasks.replace(/\n/g, '<br>') : 'No backend tasks specified.'}
                                            </div>
                                        </div>
                                        
                                        <div class="drawer-section">
                                            <h4 class="section-title">Implementation Steps</h4>
                                            <div class="section-content">
                                                ${ticket.implementation_steps ? ticket.implementation_steps.replace(/\n/g, '<br>') : 'No implementation steps specified.'}
                                            </div>
                                        </div>
                                    `;
                                    
                                    // Show the drawer
                                    detailsDrawer.classList.add('open');
                                    drawerOverlay.classList.add('active');
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
                    if (featureFilter) {
                        featureFilter.addEventListener('change', function() {
                            renderTickets(this.value);
                        });
                    }
                    
                    if (clearFiltersBtn) {
                        clearFiltersBtn.addEventListener('click', function() {
                            featureFilter.value = 'all';
                            renderTickets('all');
                        });
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
         * Load codebase explorer from the coding module for the current project
         * @param {number} projectId - The ID of the current project
         */
        loadCodebase: function(projectId) {
            console.log(`[ArtifactsLoader] loadCodebase called with project ID: ${projectId}`);
            
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
            
            // Build the editor URL with appropriate parameters
            let editorUrl = `/coding/editor/?project_id=${projectId}`;
            
            // Add conversation ID if available
            if (conversationId) {
                editorUrl += `&conversation_id=${conversationId}`;
                console.log(`[ArtifactsLoader] Including conversation ID: ${conversationId}`);
            }
            
            console.log(`[ArtifactsLoader] Loading codebase explorer from URL: ${editorUrl}`);
            
            // Set up iframe event handlers
            codebaseIframe.onload = function() {
                // Hide loading and show iframe when loaded
                codebaseLoading.style.display = 'none';
                codebaseFrameContainer.style.display = 'block';
                console.log('[ArtifactsLoader] Codebase iframe loaded successfully');
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
            const url = `/projects/${projectId}/api/checklist/`;
            console.log(`[ArtifactsLoader] Fetching checklist from API: ${url}`);
            
            fetch(url)
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
                            <div class="checklist-filters">
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
                                            ${item.complexity ? `<span class="complexity-badge ${item.complexity}">${item.complexity}</span>` : ''}
                                            ${item.requires_worktree ? '<span class="worktree-badge"><i class="fas fa-code-branch"></i> Worktree</span>' : ''}
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
                                    
                                    // Build UI requirements section if available
                                    let uiRequirementsSection = '';
                                    if (item.ui_requirements && Object.keys(item.ui_requirements).length > 0) {
                                        uiRequirementsSection = `
                                            <div class="drawer-section">
                                                <h4 class="section-title">UI Requirements</h4>
                                                <div class="ui-requirements-content">
                                                    ${Object.entries(item.ui_requirements).map(([key, value]) => `
                                                        <div class="ui-requirement-item">
                                                            <strong>${key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}:</strong> ${value}
                                                        </div>
                                                    `).join('')}
                                                </div>
                                            </div>
                                        `;
                                    }
                                    
                                    // Build component specs section if available
                                    let componentSpecsSection = '';
                                    if (item.component_specs && Object.keys(item.component_specs).length > 0) {
                                        componentSpecsSection = `
                                            <div class="drawer-section">
                                                <h4 class="section-title">Component Specifications</h4>
                                                <div class="component-specs-content">
                                                    ${Object.entries(item.component_specs).map(([key, value]) => `
                                                        <div class="component-spec-item">
                                                            <strong>${key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}:</strong> ${value}
                                                        </div>
                                                    `).join('')}
                                                </div>
                                            </div>
                                        `;
                                    }
                                    
                                    // Build acceptance criteria section if available
                                    let acceptanceCriteriaSection = '';
                                    if (item.acceptance_criteria && item.acceptance_criteria.length > 0) {
                                        acceptanceCriteriaSection = `
                                            <div class="drawer-section">
                                                <h4 class="section-title">Acceptance Criteria</h4>
                                                <ul class="acceptance-criteria-list">
                                                    ${item.acceptance_criteria.map(criteria => `
                                                        <li class="criteria-item">
                                                            <i class="fas fa-check-circle"></i> ${criteria}
                                                        </li>
                                                    `).join('')}
                                                </ul>
                                            </div>
                                        `;
                                    }
                                    
                                    // Populate drawer with item details
                                    checklistDrawerContent.innerHTML = `
                                        <div class="drawer-section">
                                            <h4 class="section-title">Item Information</h4>
                                            <div class="checklist-detail-info">
                                                <p class="detail-row"><strong>Name:</strong> ${item.name}</p>
                                                <p class="detail-row"><strong>Status:</strong> <span class="status-badge status-${item.status || 'open'}">${statusText}</span></p>
                                                <p class="detail-row"><strong>Priority:</strong> <span class="priority-badge ${(item.priority || 'medium').toLowerCase()}">${item.priority || 'Medium'}</span></p>
                                                <p class="detail-row"><strong>Role:</strong> <span class="role-badge ${(item.role || 'user').toLowerCase()}">${item.role || 'User'}</span></p>
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
                                        ${detailsSection}
                                        ${uiRequirementsSection}
                                        ${componentSpecsSection}
                                        ${acceptanceCriteriaSection}
                                        
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
                                                <button class="drawer-action-btn edit-btn" onclick="editChecklistItem(${item.id})">
                                                    <i class="fas fa-edit"></i> Edit Item
                                                </button>
                                                <button class="drawer-action-btn toggle-btn" onclick="toggleChecklistStatus(${item.id}, '${item.status}')">
                                                    <i class="fas fa-sync-alt"></i> Toggle Status
                                                </button>
                                            </div>
                                        </div>
                                    `;
                                    
                                    // Show the drawer
                                    checklistDrawer.classList.add('open');
                                    checklistDrawerOverlay.classList.add('active');
                                }
                            });
                        });
                        
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

                    // Add event listeners for filters
                    if (statusFilter) {
                        statusFilter.addEventListener('change', function() {
                            renderChecklist(this.value, roleFilter.value);
                        });
                    }

                    if (roleFilter) {
                        roleFilter.addEventListener('change', function() {
                            renderChecklist(statusFilter.value, this.value);
                        });
                    }

                    if (clearFiltersBtn) {
                        clearFiltersBtn.addEventListener('click', function() {
                            statusFilter.value = 'all';
                            roleFilter.value = 'all';
                            renderChecklist('all', 'all');
                        });
                    }

                    // Initial render with all items
                    renderChecklist();
                })
                .catch(error => {
                    console.error('Error fetching checklist:', error);
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
        }
    };
    
    // Switch tab helper function
    window.switchTab = function(tabId) {
        console.log(`[ArtifactsLoader] Switching to tab: ${tabId}`);
        
        // Get tab elements
        const tabButtons = document.querySelectorAll('.tab-button');
        const tabPanes = document.querySelectorAll('.tab-pane');
        
        // Remove active class from all buttons and panes
        tabButtons.forEach(button => button.classList.remove('active'));
        tabPanes.forEach(pane => pane.classList.remove('active'));
        
        // Add active class to the selected tab
        const selectedButton = document.querySelector(`.tab-button[data-tab="${tabId}"]`);
        const selectedPane = document.getElementById(tabId);
        
        if (selectedButton && selectedPane) {
            selectedButton.classList.add('active');
            selectedPane.classList.add('active');
            
            // Load data for the tab if it's empty
            if (selectedPane.querySelector('.empty-state')) {
                loadTabData(tabId);
            }
        }
    };
    
    // Set up tab switching event listeners
    document.querySelectorAll('.tab-button').forEach(button => {
        button.addEventListener('click', function() {
            const tabId = this.getAttribute('data-tab');
            window.switchTab(tabId);
        });
    });
    
    // Function to load data for a tab
    function loadTabData(tabId) {
        const projectId = getCurrentProjectId();
        if (!projectId) {
            console.warn('[ArtifactsLoader] No project ID available for loading tab data');
            return;
        }
        
        console.log(`[ArtifactsLoader] Loading data for tab: ${tabId}`);
        
        switch (tabId) {
            case 'prd':
                window.ArtifactsLoader.loadPRD(projectId);
                break;
            case 'implementation':
                window.ArtifactsLoader.loadImplementation(projectId);
                break;
            case 'features':
                window.ArtifactsLoader.loadFeatures(projectId);
                break;
            case 'personas':
                window.ArtifactsLoader.loadPersonas(projectId);
                break;
            case 'design':
                if (window.ArtifactsLoader.loadDesignSchema) {
                    window.ArtifactsLoader.loadDesignSchema(projectId);
                }
                break;
            case 'tickets':
                window.ArtifactsLoader.loadTickets(projectId);
                break;
            case 'codebase':
                window.ArtifactsLoader.loadCodebase(projectId);
                break;
            case 'apps':
                console.log('[ArtifactsLoader] Attempting to load app preview');
                if (window.ArtifactsLoader.loadAppPreview) {
                    window.ArtifactsLoader.loadAppPreview(projectId, null);
                } else {
                    console.warn('[ArtifactsLoader] loadAppPreview function not available');
                }
                break;
            case 'checklist':
                window.ArtifactsLoader.loadChecklist(projectId);
                break;
            // Add more cases as needed for other tabs
        }
    }
    
    // Function to get current project ID from URL or stored value
    function getCurrentProjectId() {
        // Try to get from URL path (e.g. /chat/project/123/)
        const pathMatch = window.location.pathname.match(/\/project\/(\d+)/);
        if (pathMatch && pathMatch[1]) {
            return pathMatch[1];
        }
        
        // Try to get from URL query parameter
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has('project_id')) {
            return urlParams.get('project_id');
        }
        
        // Try to get from stored value in localStorage
        return localStorage.getItem('current_project_id');
    }
    
    // Function to get current conversation ID from URL
    function getCurrentConversationId() {
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has('conversation_id')) {
            return urlParams.get('conversation_id');
        }
        return null;
    }
    
    // Expose these functions globally for other modules to use
    window.ArtifactsHelper = {
        getCurrentProjectId: getCurrentProjectId,
        getCurrentConversationId: getCurrentConversationId
    };

    // Checklist action functions
    window.editChecklistItem = function(itemId) {
        console.log(`[ArtifactsLoader] Edit checklist item: ${itemId}`);
        // TODO: Implement edit functionality
        alert('Edit functionality coming soon!');
    };

    window.toggleChecklistStatus = function(itemId, currentStatus) {
        console.log(`[ArtifactsLoader] Toggle checklist status for item: ${itemId}, current: ${currentStatus}`);
        
        const projectId = getCurrentProjectId();
        if (!projectId) {
            console.warn('[ArtifactsLoader] No project ID available for status toggle');
            return;
        }

        const newStatus = currentStatus === 'closed' ? 'open' : 'closed';
        
        // TODO: Implement API call to update status
        // For now, just show a message
        const itemElement = document.querySelector(`[data-id="${itemId}"]`);
        if (itemElement) {
            // Update the visual state immediately for better UX
            itemElement.classList.remove('open', 'in-progress', 'agent', 'closed');
            itemElement.classList.add(newStatus);
            
            const statusIcon = itemElement.querySelector('.status-icon');
            const statusText = itemElement.querySelector('.checklist-status-text');
            const actionBtn = itemElement.querySelector('.checklist-actions button:last-child');
            
            if (newStatus === 'closed') {
                statusIcon.className = 'fas fa-check-circle status-icon';
                statusText.textContent = 'CLOSED';
                actionBtn.innerHTML = '<i class="fas fa-undo"></i> Reopen';
            } else {
                statusIcon.className = 'fas fa-circle status-icon';
                statusText.textContent = 'OPEN';
                actionBtn.innerHTML = '<i class="fas fa-check"></i> Complete';
            }
        }
        
        console.log(`[ArtifactsLoader] Status toggled to: ${newStatus}`);
    };

    // Auto-load content for the initially active tab when page loads
    setTimeout(() => {
        const activeTab = document.querySelector('.tab-button.active');
        if (activeTab) {
            const activeTabId = activeTab.getAttribute('data-tab');
            const activePane = document.getElementById(activeTabId);
            
            // Check if the active pane has empty state and load data if needed
            if (activePane && activePane.querySelector('.empty-state')) {
                console.log(`[ArtifactsLoader] Auto-loading data for initially active tab: ${activeTabId}`);
                loadTabData(activeTabId);
            }
        }
    }, 100); // Small delay to ensure DOM is fully ready
});