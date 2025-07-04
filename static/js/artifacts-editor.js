/**
 * Artifacts Editor JavaScript
 * Handles editing functionality for PRD and Implementation in the artifacts panel
 */

(function() {
    window.ArtifactsEditor = {
        // Track current editing states
        editingStates: {
            prd: false,
            implementation: false
        },
        
        // Original content for cancel functionality
        originalContent: {
            prd: '',
            implementation: ''
        },
        
        // Initialize editor functionality
        init: function() {
            console.log('[ArtifactsEditor] Initializing editor functionality');
            this.setupStyles();
        },
        
        // Add required styles for editor
        setupStyles: function() {
            const style = document.createElement('style');
            style.textContent = `
                .artifact-edit-controls {
                    display: flex;
                    gap: 10px;
                    margin-bottom: 15px;
                    justify-content: flex-end;
                }
                
                .artifact-edit-btn {
                    padding: 6px 12px;
                    background: #8b5cf6;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    gap: 5px;
                    font-size: 14px;
                    transition: background 0.2s;
                }
                
                .artifact-edit-btn:hover {
                    background: #7c3aed;
                }
                
                .artifact-edit-btn.cancel {
                    background: #6b7280;
                }
                
                .artifact-edit-btn.cancel:hover {
                    background: #4b5563;
                }
                
                .artifact-edit-btn.save {
                    background: #10b981;
                }
                
                .artifact-edit-btn.save:hover {
                    background: #059669;
                }
                
                .artifact-editor {
                    width: 100%;
                    min-height: 400px;
                    padding: 15px;
                    background: #1a1a1a;
                    border: 1px solid #333;
                    border-radius: 4px;
                    color: #e2e8f0;
                    font-family: 'Monaco', 'Consolas', monospace;
                    font-size: 14px;
                    line-height: 1.6;
                    resize: vertical;
                }
                
                .artifact-editor:focus {
                    outline: none;
                    border-color: #8b5cf6;
                }
                
                .saving-indicator {
                    display: none;
                    align-items: center;
                    gap: 8px;
                    color: #8b5cf6;
                    font-size: 14px;
                }
                
                .saving-indicator.active {
                    display: flex;
                }
                
                .saving-indicator .spinner {
                    width: 16px;
                    height: 16px;
                    border: 2px solid #8b5cf6;
                    border-top-color: transparent;
                    border-radius: 50%;
                    animation: spin 0.8s linear infinite;
                }
                
                @keyframes spin {
                    to { transform: rotate(360deg); }
                }
            `;
            document.head.appendChild(style);
        },
        
        // Enable edit mode for PRD
        enablePRDEdit: function(projectId, currentContent) {
            console.log('[ArtifactsEditor] Enabling PRD edit mode');
            this.editingStates.prd = true;
            this.originalContent.prd = currentContent;
            
            const prdTab = document.getElementById('prd');
            if (!prdTab) return;
            
            prdTab.innerHTML = `
                <div class="prd-container">
                    <div class="prd-header">
                        <h2>Product Requirement Document</h2>
                        <div class="artifact-edit-controls">
                            <div class="saving-indicator" id="prd-saving-indicator">
                                <div class="spinner"></div>
                                <span>Saving...</span>
                            </div>
                            <button class="artifact-edit-btn cancel" onclick="ArtifactsEditor.cancelPRDEdit()">
                                <i class="fas fa-times"></i> Cancel
                            </button>
                            <button class="artifact-edit-btn save" onclick="ArtifactsEditor.savePRD(${projectId})">
                                <i class="fas fa-save"></i> Save
                            </button>
                        </div>
                    </div>
                    <textarea id="prd-editor" class="artifact-editor">${currentContent}</textarea>
                </div>
            `;
            
            // Focus on the editor
            setTimeout(() => {
                const editor = document.getElementById('prd-editor');
                if (editor) {
                    editor.focus();
                    editor.setSelectionRange(0, 0);
                }
            }, 100);
        },
        
        // Enable edit mode for Implementation
        enableImplementationEdit: function(projectId, currentContent) {
            console.log('[ArtifactsEditor] Enabling Implementation edit mode');
            this.editingStates.implementation = true;
            this.originalContent.implementation = currentContent;
            
            const implementationTab = document.getElementById('implementation');
            if (!implementationTab) return;
            
            implementationTab.innerHTML = `
                <div class="implementation-container">
                    <div class="implementation-header">
                        <h2>Implementation Plan</h2>
                        <div class="artifact-edit-controls">
                            <div class="saving-indicator" id="implementation-saving-indicator">
                                <div class="spinner"></div>
                                <span>Saving...</span>
                            </div>
                            <button class="artifact-edit-btn cancel" onclick="ArtifactsEditor.cancelImplementationEdit()">
                                <i class="fas fa-times"></i> Cancel
                            </button>
                            <button class="artifact-edit-btn save" onclick="ArtifactsEditor.saveImplementation(${projectId})">
                                <i class="fas fa-save"></i> Save
                            </button>
                        </div>
                    </div>
                    <textarea id="implementation-editor" class="artifact-editor">${currentContent}</textarea>
                </div>
            `;
            
            // Focus on the editor
            setTimeout(() => {
                const editor = document.getElementById('implementation-editor');
                if (editor) {
                    editor.focus();
                    editor.setSelectionRange(0, 0);
                }
            }, 100);
        },
        
        // Save PRD content
        savePRD: async function(projectId) {
            console.log('[ArtifactsEditor] Saving PRD');
            const editor = document.getElementById('prd-editor');
            const savingIndicator = document.getElementById('prd-saving-indicator');
            
            if (!editor || !projectId) return;
            
            const content = editor.value;
            savingIndicator.classList.add('active');
            
            try {
                const response = await fetch(`/projects/${projectId}/api/prd/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    body: JSON.stringify({ content: content })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    console.log('[ArtifactsEditor] PRD saved successfully');
                    this.editingStates.prd = false;
                    
                    // Check if PRD is currently streaming
                    if (window.prdStreamingState && window.prdStreamingState.isStreaming) {
                        console.log('[ArtifactsEditor] PRD is currently streaming, skipping HTML restoration');
                        return;
                    }
                    
                    // First restore the original HTML structure
                    const prdTab = document.getElementById('prd');
                    if (prdTab) {
                        prdTab.innerHTML = `
                            <!-- Empty state (shown by default) -->
                            <div class="empty-state" id="prd-empty-state">
                                <div class="empty-state-icon">
                                    <i class="fas fa-file-alt"></i>
                                </div>
                                <div class="empty-state-text">
                                    No PRD content available yet.
                                </div>
                            </div>
                            
                            <!-- PRD Container (hidden by default, shown during streaming) -->
                            <div class="prd-container" id="prd-container" style="display: none;">
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
                    }
                    
                    // Reload the PRD content
                    if (window.ArtifactsLoader && window.ArtifactsLoader.loadPRD) {
                        console.log('[ArtifactsEditor] Reloading PRD after save');
                        window.ArtifactsLoader.loadPRD(projectId);
                    }
                } else {
                    console.error('[ArtifactsEditor] Error saving PRD:', data.error);
                    alert('Error saving PRD: ' + (data.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('[ArtifactsEditor] Error saving PRD:', error);
                alert('Error saving PRD: ' + error.message);
            } finally {
                savingIndicator.classList.remove('active');
            }
        },
        
        // Save Implementation content
        saveImplementation: async function(projectId) {
            console.log('[ArtifactsEditor] Saving Implementation');
            const editor = document.getElementById('implementation-editor');
            const savingIndicator = document.getElementById('implementation-saving-indicator');
            
            if (!editor || !projectId) return;
            
            const content = editor.value;
            savingIndicator.classList.add('active');
            
            try {
                const response = await fetch(`/projects/${projectId}/api/implementation/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    body: JSON.stringify({ content: content })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    console.log('[ArtifactsEditor] Implementation saved successfully');
                    this.editingStates.implementation = false;
                    // Reload the Implementation content
                    if (window.ArtifactsLoader && window.ArtifactsLoader.loadImplementation) {
                        window.ArtifactsLoader.loadImplementation(projectId);
                    }
                } else {
                    console.error('[ArtifactsEditor] Error saving Implementation:', data.error);
                    alert('Error saving Implementation: ' + (data.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('[ArtifactsEditor] Error saving Implementation:', error);
                alert('Error saving Implementation: ' + error.message);
            } finally {
                savingIndicator.classList.remove('active');
            }
        },
        
        // Cancel PRD edit
        cancelPRDEdit: function() {
            console.log('[ArtifactsEditor] Cancelling PRD edit');
            this.editingStates.prd = false;
            
            // Check if PRD is currently streaming
            if (window.prdStreamingState && window.prdStreamingState.isStreaming) {
                console.log('[ArtifactsEditor] PRD is currently streaming, skipping HTML restoration');
                return;
            }
            
            // First restore the original HTML structure
            const prdTab = document.getElementById('prd');
            if (prdTab) {
                prdTab.innerHTML = `
                    <!-- Empty state (shown by default) -->
                    <div class="empty-state" id="prd-empty-state">
                        <div class="empty-state-icon">
                            <i class="fas fa-file-alt"></i>
                        </div>
                        <div class="empty-state-text">
                            No PRD content available yet.
                        </div>
                    </div>
                    
                    <!-- PRD Container (hidden by default, shown during streaming) -->
                    <div class="prd-container" id="prd-container" style="display: none;">
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
            }
            
            // Now reload the PRD content
            const projectId = window.ArtifactsLoader.getCurrentProjectId();
            console.log('[ArtifactsEditor] Project ID for cancel:', projectId);
            if (projectId && window.ArtifactsLoader && window.ArtifactsLoader.loadPRD) {
                console.log('[ArtifactsEditor] Calling loadPRD to restore content');
                window.ArtifactsLoader.loadPRD(projectId);
            }
        },
        
        // Cancel Implementation edit
        cancelImplementationEdit: function() {
            console.log('[ArtifactsEditor] Cancelling Implementation edit');
            this.editingStates.implementation = false;
            const projectId = window.ArtifactsLoader.getCurrentProjectId();
            if (projectId && window.ArtifactsLoader && window.ArtifactsLoader.loadImplementation) {
                window.ArtifactsLoader.loadImplementation(projectId);
            }
        },
        
        // Get CSRF token
        getCsrfToken: function() {
            const metaToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            if (metaToken) return metaToken;
            
            const inputToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
            if (inputToken) return inputToken;
            
            const cookieValue = document.cookie
                .split('; ')
                .find(row => row.startsWith('csrftoken='))
                ?.split('=')[1];
            
            return cookieValue || '';
        }
    };
    
    // Initialize on DOM load
    document.addEventListener('DOMContentLoaded', function() {
        window.ArtifactsEditor.init();
    });
})();