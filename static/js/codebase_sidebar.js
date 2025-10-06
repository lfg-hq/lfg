// Codebase Sidebar JavaScript
let currentProjectId = null;
let currentRepositoryId = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Get project ID from URL or data attribute
    const urlParts = window.location.pathname.split('/');
    const projectIndex = urlParts.indexOf('projects');
    if (projectIndex !== -1 && urlParts[projectIndex + 1]) {
        currentProjectId = urlParts[projectIndex + 1];
    }
    
    // Set repository ID if available
    const repoIdElement = document.querySelector('[data-repository-id]');
    if (repoIdElement) {
        currentRepositoryId = repoIdElement.getAttribute('data-repository-id');
    }
    
    // Close sidebar on escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeCodebaseSidebar();
        }
    });
});

// Open codebase sidebar
function openCodebaseSidebar() {
    const sidebar = document.getElementById('codebaseSidebar');
    
    if (sidebar) {
        sidebar.classList.add('active');
        document.body.style.overflow = 'hidden';
        
        // Load fresh data when opening
        if (currentRepositoryId) {
            refreshSidebarData();
        }
    }
}

// Close sidebar
function closeCodebaseSidebar() {
    const sidebar = document.getElementById('codebaseSidebar');
    
    if (sidebar) {
        sidebar.classList.remove('active');
        document.body.style.overflow = '';
    }
}

// Connect new repository
async function connectRepository() {
    const githubUrl = document.getElementById('githubUrl').value;
    const githubBranch = document.getElementById('githubBranch').value || 'main';
    
    if (!githubUrl) {
        showNotification('Please enter a GitHub repository URL', 'error');
        return;
    }
    
    if (!currentProjectId) {
        showNotification('Project ID not found', 'error');
        return;
    }
    
    try {
        showLoading('Connecting repository...');
        
        const response = await fetch('/codebase/api/repositories/add/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                project_id: currentProjectId,
                github_url: githubUrl,
                branch: githubBranch
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification('Repository connected successfully! Indexing in progress...', 'success');
            currentRepositoryId = data.repository_id;
            
            // Reload page to show new repository
            setTimeout(() => {
                window.location.reload();
            }, 2000);
        } else {
            showNotification('Failed to connect repository: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('Error connecting repository: ' + error.message, 'error');
    } finally {
        hideLoading();
    }
}

// Edit repository URL
function editRepositoryUrl() {
    const urlDisplay = document.querySelector('.url-display');
    const editForm = document.getElementById('editUrlForm');
    
    if (urlDisplay && editForm) {
        urlDisplay.style.display = 'none';
        editForm.style.display = 'block';
        document.getElementById('newGithubUrl').focus();
    }
}

// Cancel URL edit
function cancelEditUrl() {
    const urlDisplay = document.querySelector('.url-display');
    const editForm = document.getElementById('editUrlForm');
    
    if (urlDisplay && editForm) {
        urlDisplay.style.display = 'flex';
        editForm.style.display = 'none';
    }
}

// Update repository URL
async function updateRepositoryUrl() {
    const newUrl = document.getElementById('newGithubUrl').value;
    
    if (!newUrl) {
        showNotification('Please enter a GitHub repository URL', 'error');
        return;
    }
    
    if (!currentRepositoryId) {
        showNotification('Repository ID not found', 'error');
        return;
    }
    
    try {
        showLoading('Updating repository URL...');
        
        const response = await fetch(`/codebase/api/repositories/${currentRepositoryId}/update-url/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                github_url: newUrl
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification('Repository URL updated successfully!', 'success');
            
            // Reload page to show updated repository
            setTimeout(() => {
                window.location.reload();
            }, 1500);
        } else {
            showNotification('Failed to update repository URL: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('Error updating repository URL: ' + error.message, 'error');
    } finally {
        hideLoading();
    }
}

// Re-index repository
async function reindexRepository(repositoryId) {
    const repoId = repositoryId || currentRepositoryId;
    
    if (!repoId) {
        showNotification('Repository ID not found', 'error');
        return;
    }
    
    if (!confirm('This will re-index the entire repository. This may take several minutes. Continue?')) {
        return;
    }
    
    try {
        showLoading('Starting re-indexing...');
        
        const response = await fetch(`/codebase/api/repositories/${repoId}/reindex/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken()
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification('Re-indexing started. Check back in a few minutes for progress.', 'success');
            
            // Start polling for status updates
            startStatusPolling();
        } else {
            showNotification('Failed to start re-indexing: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('Error starting re-indexing: ' + error.message, 'error');
    } finally {
        hideLoading();
    }
}

// Disconnect repository
async function disconnectRepository() {
    if (!currentRepositoryId) {
        showNotification('Repository ID not found', 'error');
        return;
    }
    
    if (!confirm('This will disconnect the repository and remove all indexed data. Are you sure?')) {
        return;
    }
    
    try {
        showLoading('Disconnecting repository...');
        
        const response = await fetch(`/codebase/api/repositories/${currentRepositoryId}/delete/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken()
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification('Repository disconnected successfully!', 'success');
            
            // Reload page to show updated state
            setTimeout(() => {
                window.location.reload();
            }, 2000);
        } else {
            showNotification('Failed to disconnect repository: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('Error disconnecting repository: ' + error.message, 'error');
    } finally {
        hideLoading();
    }
}

// Delete repository index
async function deleteIndex() {
    if (!currentRepositoryId) {
        showNotification('Repository ID not found', 'error');
        return;
    }
    
    if (!confirm('This will permanently delete all indexed data for this repository. Are you sure?')) {
        return;
    }
    
    try {
        showLoading('Deleting index...');
        
        const response = await fetch(`/codebase/api/repositories/${currentRepositoryId}/delete/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken()
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification('Repository index deleted successfully!', 'success');
            
            // Reload page to show updated state
            setTimeout(() => {
                window.location.reload();
            }, 2000);
        } else {
            showNotification('Failed to delete index: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('Error deleting index: ' + error.message, 'error');
    } finally {
        hideLoading();
    }
}

// Search codebase
async function searchCodebase() {
    const query = prompt('Enter your search query (e.g., "authentication logic" or "user model"):');
    
    if (!query || !query.trim()) {
        return;
    }
    
    if (!currentProjectId) {
        showNotification('Project ID not found', 'error');
        return;
    }
    
    try {
        showLoading('Searching codebase...');
        
        const response = await fetch('/codebase/api/search/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                project_id: currentProjectId,
                query: query.trim()
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showSearchResults(data.context, data.relevant_files, data.retrieval_meta);
        } else {
            showNotification('Search failed: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('Error searching codebase: ' + error.message, 'error');
    } finally {
        hideLoading();
    }
}

// Show search results in a modal or new section
function showSearchResults(context, relevantFiles, meta) {
    // Create a simple results display
    const resultsHtml = `
        <div class="search-results-modal">
            <div class="search-results-content">
                <div class="search-results-header">
                    <h4>Search Results</h4>
                    <button onclick="closeSearchResults()" class="close-btn">&times;</button>
                </div>
                <div class="search-results-body">
                    <div class="search-meta">
                        <span>Found ${meta.chunks_retrieved} relevant code chunks in ${meta.files_found} files</span>
                    </div>
                    <div class="search-context">
                        <h5>Context:</h5>
                        <pre class="context-text">${context}</pre>
                    </div>
                    <div class="relevant-files">
                        <h5>Relevant Files:</h5>
                        <ul>
                            ${relevantFiles.map(file => `<li>${file}</li>`).join('')}
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Add to page
    document.body.insertAdjacentHTML('beforeend', resultsHtml);
}

// Close search results
function closeSearchResults() {
    const modal = document.querySelector('.search-results-modal');
    if (modal) {
        modal.remove();
    }
}

// Refresh code preview
async function refreshPreview() {
    if (!currentRepositoryId) {
        return;
    }
    
    try {
        const response = await fetch(`/codebase/api/repositories/${currentRepositoryId}/preview/`);
        const data = await response.json();
        
        if (data.success) {
            updateCodePreview(data.chunks, data.total_chunks);
        }
    } catch (error) {
        console.error('Error refreshing preview:', error);
    }
}

// Update code preview content
function updateCodePreview(chunks, totalChunks) {
    const previewContent = document.getElementById('codePreviewContent');
    if (!previewContent || !chunks) return;
    
    let html = '';
    
    if (chunks.length > 0) {
        html = '<div class="code-chunks-list">';
        chunks.forEach(chunk => {
            html += `
                <div class="code-chunk-item">
                    <div class="chunk-header">
                        <div class="chunk-info">
                            <span class="chunk-type chunk-type-${chunk.chunk_type}">${chunk.chunk_type}</span>
                            ${chunk.function_name ? `<span class="function-name">${chunk.function_name}</span>` : ''}
                        </div>
                        <div class="chunk-meta">
                            <span class="file-path">${chunk.file_path}</span>
                            <span class="line-numbers">${chunk.start_line}-${chunk.end_line}</span>
                        </div>
                    </div>
                    <div class="chunk-preview">
                        <pre><code class="language-${chunk.language}">${escapeHtml(chunk.content_preview)}</code></pre>
                    </div>
                    <div class="chunk-footer">
                        <span class="complexity complexity-${chunk.complexity}">${chunk.complexity} complexity</span>
                        ${chunk.tags ? `
                            <div class="chunk-tags">
                                ${chunk.tags.slice(0, 3).map(tag => `<span class="tag">${tag}</span>`).join('')}
                            </div>
                        ` : ''}
                    </div>
                </div>
            `;
        });
        html += '</div>';
        
        if (chunks.length >= 5) {
            html += `
                <div class="preview-footer">
                    <button type="button" class="btn btn-sm btn-outline" onclick="viewAllChunks()">
                        View All ${totalChunks} Chunks
                    </button>
                </div>
            `;
        }
    } else {
        html = '<div class="no-chunks"><p class="text-muted">No code chunks available</p></div>';
    }
    
    previewContent.innerHTML = html;
}

// View all chunks (placeholder)
function viewAllChunks() {
    // Could open a modal or navigate to a dedicated page
    showNotification('Feature coming soon: View all chunks', 'info');
}

// Refresh sidebar data
async function refreshSidebarData() {
    if (!currentRepositoryId) return;
    
    try {
        // Get repository status
        const statusResponse = await fetch(`/codebase/api/repositories/${currentRepositoryId}/status/`);
        const statusData = await statusResponse.json();
        
        // Update status display and stats
        updateRepositoryStats(statusData);
        
        // Load code insights
        loadCodeInsights();
        
        // Load recent files
        loadRecentFiles();
        
    } catch (error) {
        console.error('Error refreshing sidebar data:', error);
    }
}

// Update repository statistics
function updateRepositoryStats(statusData) {
    // Update total chunks
    const totalChunksElement = document.getElementById('totalChunks');
    if (totalChunksElement) {
        totalChunksElement.textContent = statusData.total_chunks || '-';
    }
    
    // Update total functions
    const totalFunctionsElement = document.getElementById('totalFunctions');
    if (totalFunctionsElement) {
        totalFunctionsElement.textContent = statusData.functions_count || '-';
    }
    
    // Update total classes
    const totalClassesElement = document.getElementById('totalClasses');
    if (totalClassesElement) {
        totalClassesElement.textContent = statusData.classes_count || '-';
    }
}

// Load code insights
async function loadCodeInsights() {
    const insightsContent = document.getElementById('codeInsights');
    if (!insightsContent || !currentRepositoryId) return;
    
    try {
        const response = await fetch(`/codebase/api/repositories/${currentRepositoryId}/insights/`);
        const data = await response.json();
        
        if (data.success && data.insights) {
            let html = '';
            
            // Most complex functions
            if (data.insights.most_complex_functions && data.insights.most_complex_functions.length > 0) {
                html += `
                    <div class="insight-item">
                        <div class="insight-icon warning">
                            <i class="fas fa-exclamation-triangle"></i>
                        </div>
                        <div class="insight-content">
                            <h6>Complex Functions Found</h6>
                            <p>Found ${data.insights.most_complex_functions.length} functions with high complexity</p>
                        </div>
                    </div>
                `;
            }
            
            // Language distribution
            if (data.insights.languages && Object.keys(data.insights.languages).length > 1) {
                const primaryLang = Object.keys(data.insights.languages)[0];
                html += `
                    <div class="insight-item">
                        <div class="insight-icon info">
                            <i class="fas fa-code"></i>
                        </div>
                        <div class="insight-content">
                            <h6>Multi-Language Codebase</h6>
                            <p>Primary language: ${primaryLang}, with ${Object.keys(data.insights.languages).length - 1} other languages</p>
                        </div>
                    </div>
                `;
            }
            
            // Test coverage insight
            if (data.insights.has_tests) {
                html += `
                    <div class="insight-item">
                        <div class="insight-icon success">
                            <i class="fas fa-check-circle"></i>
                        </div>
                        <div class="insight-content">
                            <h6>Tests Detected</h6>
                            <p>Found test files and testing patterns in your codebase</p>
                        </div>
                    </div>
                `;
            }
            
            // Default insight if no specific insights
            if (!html) {
                html = `
                    <div class="insight-item">
                        <div class="insight-icon info">
                            <i class="fas fa-info-circle"></i>
                        </div>
                        <div class="insight-content">
                            <h6>Repository Indexed</h6>
                            <p>Your repository has been successfully indexed and is ready for AI-powered analysis</p>
                        </div>
                    </div>
                `;
            }
            
            insightsContent.innerHTML = html;
        }
    } catch (error) {
        console.error('Error loading code insights:', error);
        insightsContent.innerHTML = `
            <div class="insight-item">
                <div class="insight-icon warning">
                    <i class="fas fa-exclamation-circle"></i>
                </div>
                <div class="insight-content">
                    <h6>Unable to Load Insights</h6>
                    <p>Error loading code insights. Please try again.</p>
                </div>
            </div>
        `;
    }
}

// Load recent files
async function loadRecentFiles() {
    const recentFilesContainer = document.getElementById('recentFiles');
    if (!recentFilesContainer || !currentRepositoryId) return;
    
    try {
        const response = await fetch(`/codebase/api/repositories/${currentRepositoryId}/recent-files/`);
        const data = await response.json();
        
        if (data.success && data.files && data.files.length > 0) {
            let html = '';
            
            data.files.slice(0, 5).forEach(file => {
                const fileExtension = file.file_path.split('.').pop().toLowerCase();
                let iconClass = 'fas fa-file-code';
                
                // Set appropriate icon based on file type
                if (['js', 'jsx', 'ts', 'tsx'].includes(fileExtension)) {
                    iconClass = 'fab fa-js-square';
                } else if (['py'].includes(fileExtension)) {
                    iconClass = 'fab fa-python';
                } else if (['html', 'htm'].includes(fileExtension)) {
                    iconClass = 'fab fa-html5';
                } else if (['css', 'scss', 'sass'].includes(fileExtension)) {
                    iconClass = 'fab fa-css3-alt';
                } else if (['json'].includes(fileExtension)) {
                    iconClass = 'fas fa-brackets-curly';
                } else if (['md', 'txt'].includes(fileExtension)) {
                    iconClass = 'fas fa-file-text';
                }
                
                html += `
                    <div class="file-item">
                        <div class="file-icon">
                            <i class="${iconClass}"></i>
                        </div>
                        <div class="file-info">
                            <div class="file-name">${file.file_path.split('/').pop()}</div>
                            <div class="file-path">${file.file_path}</div>
                        </div>
                        <div class="file-chunks">${file.chunks_count}</div>
                    </div>
                `;
            });
            
            recentFilesContainer.innerHTML = html;
        } else {
            recentFilesContainer.innerHTML = `
                <div class="loading-placeholder">
                    <i class="fas fa-file"></i>
                    <span>No files indexed yet</span>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading recent files:', error);
        recentFilesContainer.innerHTML = `
            <div class="loading-placeholder">
                <i class="fas fa-exclamation-triangle"></i>
                <span>Error loading files</span>
            </div>
        `;
    }
}

// Update repository status in sidebar
function updateRepositoryStatus(statusData) {
    const statusBadge = document.querySelector('.status-badge');
    if (statusBadge) {
        statusBadge.className = `status-badge status-${statusData.status}`;
        statusBadge.textContent = statusData.status.charAt(0).toUpperCase() + statusData.status.slice(1);
    }
    
    // Update stats
    const statNumbers = document.querySelectorAll('.stat-number');
    if (statNumbers.length >= 3) {
        statNumbers[0].textContent = statusData.total_files || 0;
        statNumbers[1].textContent = statusData.indexed_files || 0;
        statNumbers[2].textContent = statusData.total_chunks || 0;
    }
}

// Update repository insights
function updateRepositoryInsights(insights) {
    const insightsContent = document.querySelector('.insights-content');
    if (!insightsContent || !insights) return;
    
    let html = `
        <div class="insight-item">
            <label>Primary Language:</label>
            <span class="language-tag">${insights.primary_language ? insights.primary_language.charAt(0).toUpperCase() + insights.primary_language.slice(1) : 'Unknown'}</span>
        </div>
        <div class="insight-item">
            <label>Functions:</label>
            <span>${insights.functions_count || 0}</span>
        </div>
        <div class="insight-item">
            <label>Classes:</label>
            <span>${insights.classes_count || 0}</span>
        </div>
    `;
    
    if (insights.average_complexity) {
        html += `
            <div class="insight-item">
                <label>Avg. Complexity:</label>
                <span class="complexity-score">${parseFloat(insights.average_complexity).toFixed(1)}</span>
            </div>
        `;
    }
    
    insightsContent.innerHTML = html;
}

// Start polling for indexing status
function startStatusPolling() {
    if (!currentRepositoryId) return;
    
    const pollInterval = setInterval(async () => {
        try {
            const response = await fetch(`/codebase/api/repositories/${currentRepositoryId}/status/`);
            const data = await response.json();
            
            updateRepositoryStatus(data);
            
            // Stop polling if indexing is complete
            if (data.status === 'completed' || data.status === 'error') {
                clearInterval(pollInterval);
                refreshSidebarData(); // Final refresh
                
                if (data.status === 'completed') {
                    showNotification('Repository indexing completed successfully!', 'success');
                } else if (data.status === 'error') {
                    showNotification('Repository indexing failed. Check the error details.', 'error');
                }
            }
        } catch (error) {
            console.error('Error polling status:', error);
            clearInterval(pollInterval);
        }
    }, 5000); // Poll every 5 seconds
    
    // Stop polling after 10 minutes
    setTimeout(() => {
        clearInterval(pollInterval);
    }, 600000);
}

// Utility functions
function getCSRFToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]').value;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showLoading(message = 'Loading...') {
    // Simple loading notification
    showNotification(message, 'info', false);
}

function hideLoading() {
    // Remove loading notifications
    const notifications = document.querySelectorAll('.notification.info');
    notifications.forEach(n => n.remove());
}

function showNotification(message, type = 'info', autoHide = true) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.innerHTML = `
        <div class="notification-content">
            <span>${message}</span>
            <button onclick="this.parentElement.parentElement.remove()">&times;</button>
        </div>
    `;
    
    // Add to page
    document.body.appendChild(notification);
    
    // Auto-hide after 5 seconds
    if (autoHide) {
        setTimeout(() => {
            if (notification.parentElement) {
                notification.remove();
            }
        }, 5000);
    }
}