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
            
            const prdContainer = document.getElementById('prd-container');
            if (!prdContainer) return;
            
            // Get existing PRD selector HTML if it exists
            const prdMeta = prdContainer.querySelector('.prd-meta');
            const existingSelectorHTML = prdMeta ? prdMeta.innerHTML : '';
            
            // Replace the PRD content area with editor
            const streamingContainer = document.getElementById('prd-streaming-content');
            if (streamingContainer) {
                streamingContainer.innerHTML = `<textarea id="prd-editor" class="artifact-editor">${currentContent}</textarea>`;
            }
            
            // Clear the actions container
            const prdActionsContainer = prdContainer.querySelector('.prd-actions-container');
            if (prdActionsContainer) {
                prdActionsContainer.innerHTML = `
                    <div class="artifact-edit-controls">
                        <div class="saving-indicator" id="prd-saving-indicator">
                            <div class="spinner"></div>
                            <span>Saving...</span>
                        </div>
                        <button class="artifact-edit-btn cancel" id="prd-cancel-btn">
                            <i class="fas fa-times"></i> Cancel
                        </button>
                        <button class="artifact-edit-btn save" id="prd-save-btn">
                            <i class="fas fa-save"></i> Save
                        </button>
                    </div>
                `;
                
                // Add event listeners
                const saveBtn = document.getElementById('prd-save-btn');
                const cancelBtn = document.getElementById('prd-cancel-btn');
                
                if (saveBtn) {
                    console.log('[ArtifactsEditor] Adding save button listener, projectId:', projectId);
                    saveBtn.addEventListener('click', () => {
                        console.log('[ArtifactsEditor] Save button clicked, projectId:', projectId);
                        window.ArtifactsEditor.savePRD(projectId);
                    });
                } else {
                    console.error('[ArtifactsEditor] Save button not found!');
                }
                
                if (cancelBtn) {
                    cancelBtn.addEventListener('click', () => {
                        window.ArtifactsEditor.cancelPRDEdit();
                    });
                }
            }
            
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
            console.log('[ArtifactsEditor] Saving PRD, projectId:', projectId);
            const editor = document.getElementById('prd-editor');
            const savingIndicator = document.getElementById('prd-saving-indicator');
            
            if (!editor) {
                console.error('[ArtifactsEditor] PRD editor not found!');
                return;
            }
            
            if (!projectId) {
                console.error('[ArtifactsEditor] Project ID is missing!');
                return;
            }
            
            const content = editor.value;
            if (savingIndicator) {
                savingIndicator.classList.add('active');
            }
            
            // Get the current PRD name from the selector if it exists
            const prdSelector = document.getElementById('prd-selector');
            const prdName = prdSelector ? prdSelector.value : 'Main PRD';
            
            console.log('[ArtifactsEditor] PRD content length:', content.length);
            console.log('[ArtifactsEditor] PRD name:', prdName);
            
            try {
                const response = await fetch(`/projects/${projectId}/api/prd/?prd_name=${encodeURIComponent(prdName)}`, {
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
                        console.log('[ArtifactsEditor] PRD is currently streaming, skipping reload');
                        return;
                    }
                    
                    // Reload the PRD content with the correct PRD name
                    if (window.ArtifactsLoader && window.ArtifactsLoader.loadPRD) {
                        console.log('[ArtifactsEditor] Reloading PRD after save');
                        window.ArtifactsLoader.loadPRD(projectId, prdName);
                    }
                } else {
                    console.error('[ArtifactsEditor] Error saving PRD:', data.error);
                    alert('Error saving PRD: ' + (data.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('[ArtifactsEditor] Error saving PRD:', error);
                alert('Error saving PRD: ' + error.message);
            } finally {
                if (savingIndicator) {
                    savingIndicator.classList.remove('active');
                }
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
                console.log('[ArtifactsEditor] PRD is currently streaming, skipping reload');
                return;
            }
            
            // Get the current PRD name from the selector if it exists
            const prdSelector = document.getElementById('prd-selector');
            const prdName = prdSelector ? prdSelector.value : 'Main PRD';
            
            // Now reload the PRD content
            const projectId = window.ArtifactsLoader.getCurrentProjectId();
            console.log('[ArtifactsEditor] Project ID for cancel:', projectId);
            if (projectId && window.ArtifactsLoader && window.ArtifactsLoader.loadPRD) {
                console.log('[ArtifactsEditor] Calling loadPRD to restore content');
                window.ArtifactsLoader.loadPRD(projectId, prdName);
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