/**
 * Design Canvas - Figma-like screen flow visualization
 * Displays all screens as individual cards with preview thumbnails
 */

class DesignCanvas {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.canvas = document.getElementById('design-canvas');
        this.wrapper = document.getElementById('design-canvas-wrapper');
        this.featuresContainer = document.getElementById('features-container');
        this.emptyState = document.getElementById('design-canvas-empty');
        this.loadingState = document.getElementById('design-canvas-loading');
        this.previewModal = document.getElementById('page-preview-modal');

        this.features = new Map();
        this.pageElements = new Map();

        // Canvas management
        this.canvases = [];
        this.currentCanvas = null;
        this.currentCanvasId = null;

        this.zoom = 0.7;
        this.targetZoom = 0.7;
        this.panX = 0;
        this.panY = 0;
        this.isDragging = false;
        this.dragTarget = null;
        this.dragOffset = { x: 0, y: 0 };
        this.dragStartPos = { x: 0, y: 0 };
        this.hasDragged = false;
        this.isPanning = false;
        this.panStart = { x: 0, y: 0 };
        this.isFullscreen = false;

        // Screen card dimensions
        this.cardWidth = 280;
        this.cardHeight = 220;
        this.cardGap = 40;

        // Smooth zoom animation
        this.zoomAnimationId = null;

        // Tools panel state
        this.currentTool = 'select';
        this.selectedScreens = new Set();

        this.init();
    }

    async init() {
        this.createCanvasSelector();
        this.bindEvents();
        this.listenForDesignUpdates();
        await this.loadCanvases();
        this.loadFeatures();
    }

    listenForDesignUpdates() {
        // Listen for design preview notifications to auto-refresh
        document.addEventListener('designPreviewGenerated', () => {
            console.log('Design preview generated, refreshing canvas...');
            this.loadCanvases().then(() => this.loadFeatures());
        });

        // Also listen for WebSocket notifications
        if (window.notificationHandler) {
            const originalHandler = window.notificationHandler;
            window.notificationHandler = (notification) => {
                if (notification?.type === 'design_preview') {
                    console.log('Design preview notification received, refreshing...');
                    setTimeout(() => {
                        this.loadCanvases().then(() => this.loadFeatures());
                    }, 500);
                }
                originalHandler(notification);
            };
        }
    }

    createCanvasSelector() {
        // Find or create the canvas selector in the toolbar
        const toolbarRight = document.querySelector('.design-canvas-toolbar .toolbar-right');
        if (!toolbarRight) return;

        // Create canvas selector container
        const selectorContainer = document.createElement('div');
        selectorContainer.className = 'canvas-selector-container';
        selectorContainer.innerHTML = `
            <select class="canvas-selector" id="canvas-selector" title="Select Canvas">
                <option value="">Loading...</option>
            </select>
            <button class="toolbar-btn canvas-btn" id="canvas-save" title="Save Canvas">
                <i class="fas fa-save"></i>
            </button>
            <button class="toolbar-btn canvas-btn" id="canvas-new" title="New Canvas">
                <i class="fas fa-plus"></i>
            </button>
            <button class="toolbar-btn canvas-btn" id="canvas-delete" title="Delete Canvas">
                <i class="fas fa-trash"></i>
            </button>
        `;

        // Insert before the refresh button
        const refreshBtn = document.getElementById('canvas-refresh');
        if (refreshBtn) {
            toolbarRight.insertBefore(selectorContainer, refreshBtn);
        } else {
            toolbarRight.prepend(selectorContainer);
        }

        // Bind canvas selector events
        document.getElementById('canvas-selector')?.addEventListener('change', (e) => {
            this.switchCanvas(e.target.value);
        });
        document.getElementById('canvas-save')?.addEventListener('click', () => this.saveCurrentCanvas());
        document.getElementById('canvas-new')?.addEventListener('click', () => this.createNewCanvas());
        document.getElementById('canvas-delete')?.addEventListener('click', () => this.deleteCurrentCanvas());
    }

    async loadCanvases() {
        const projectId = this.getProjectId();
        if (!projectId) return;

        try {
            const response = await fetch(`/projects/${projectId}/api/canvases/`);
            if (!response.ok) throw new Error('Failed to load canvases');

            const data = await response.json();
            this.canvases = data.canvases || [];

            // If no canvases exist, create a default one
            if (this.canvases.length === 0) {
                await this.createDefaultCanvas();
                return;  // createDefaultCanvas will call loadCanvases again
            }

            // Update selector
            this.updateCanvasSelector();

            // Try to load the canvas linked to the current conversation
            const linkedCanvasId = await this.getConversationLinkedCanvas();
            let selectedCanvas = null;

            if (linkedCanvasId) {
                selectedCanvas = this.canvases.find(c => c.id == linkedCanvasId);
            }

            // Fall back to default canvas or first one
            if (!selectedCanvas) {
                selectedCanvas = this.canvases.find(c => c.is_default) || this.canvases[0];
            }

            if (selectedCanvas) {
                this.currentCanvas = selectedCanvas;
                this.currentCanvasId = selectedCanvas.id;
                window.currentDesignCanvasId = selectedCanvas.id;  // Store globally
                console.log('[DesignCanvas] init - Set currentDesignCanvasId:', selectedCanvas.id, 'canvas name:', selectedCanvas.name, 'is_default:', selectedCanvas.is_default);
                const selector = document.getElementById('canvas-selector');
                if (selector) selector.value = selectedCanvas.id;
            } else {
                console.log('[DesignCanvas] init - No canvas selected');
            }

        } catch (error) {
            console.error('Error loading canvases:', error);
        }
    }

    async getConversationLinkedCanvas() {
        const conversationId = this.getConversationId();
        if (!conversationId) return null;

        try {
            const response = await fetch(`/api/conversations/${conversationId}/`);
            if (!response.ok) return null;

            const data = await response.json();
            return data.design_canvas_id || null;
        } catch (error) {
            console.error('Error fetching conversation canvas:', error);
            return null;
        }
    }

    async createDefaultCanvas() {
        const projectId = this.getProjectId();
        if (!projectId) return;

        try {
            const response = await fetch(`/projects/${projectId}/api/canvases/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    name: 'Canvas 1',
                    feature_positions: {},
                    is_default: true
                })
            });

            if (response.ok) {
                // Reload canvases
                await this.loadCanvases();
            }
        } catch (error) {
            console.error('Error creating default canvas:', error);
        }
    }

    updateCanvasSelector() {
        const selector = document.getElementById('canvas-selector');
        if (!selector) return;

        if (this.canvases.length === 0) {
            selector.innerHTML = '<option value="">No canvases</option>';
        } else {
            selector.innerHTML = this.canvases.map(c =>
                `<option value="${c.id}" ${c.is_default ? 'data-default="true"' : ''}>${c.name}${c.is_default ? ' (default)' : ''}</option>`
            ).join('');
        }

        // Update delete button state
        const deleteBtn = document.getElementById('canvas-delete');
        if (deleteBtn) {
            deleteBtn.disabled = this.canvases.length <= 1;
        }
    }

    async switchCanvas(canvasId) {
        console.log('[DesignCanvas] switchCanvas called with:', canvasId);
        if (!canvasId) return;

        const canvas = this.canvases.find(c => c.id == canvasId);
        if (!canvas) {
            console.log('[DesignCanvas] switchCanvas - canvas not found');
            return;
        }

        this.currentCanvas = canvas;
        this.currentCanvasId = canvas.id;

        // Store globally for design agent to use
        window.currentDesignCanvasId = canvas.id;
        console.log('[DesignCanvas] switchCanvas - Set window.currentDesignCanvasId:', canvas.id, 'name:', canvas.name);

        // Link canvas to current conversation
        this.linkCanvasToConversation(canvas.id);

        // Re-render with canvas positions
        this.render();
        setTimeout(() => this.fitToScreen(), 50);
    }

    async linkCanvasToConversation(canvasId) {
        // Get current conversation ID from URL or global
        const conversationId = this.getConversationId();
        if (!conversationId) return;

        try {
            await fetch(`/api/conversations/${conversationId}/`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({ design_canvas_id: canvasId })
            });
            console.log(`Canvas ${canvasId} linked to conversation ${conversationId}`);
        } catch (error) {
            console.error('Error linking canvas to conversation:', error);
        }
    }

    getConversationId() {
        // Try to get from URL
        const urlMatch = window.location.href.match(/conversation_id=(\d+)/);
        if (urlMatch) return parseInt(urlMatch[1]);

        // Try to get from global
        if (window.currentConversationId) return window.currentConversationId;

        return null;
    }

    async saveCurrentCanvas() {
        if (!this.currentCanvasId) {
            // No canvas selected, create a new one
            return this.createNewCanvas();
        }

        const projectId = this.getProjectId();
        if (!projectId) return;

        // Collect current positions
        const positions = {};
        this.pageElements.forEach((el, pageId) => {
            const featureId = el.dataset.featureId;
            const key = `${featureId}_${pageId}`;
            positions[key] = {
                x: parseFloat(el.style.left) || 0,
                y: parseFloat(el.style.top) || 0
            };
        });

        try {
            const response = await fetch(`/projects/${projectId}/api/canvases/${this.currentCanvasId}/positions/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({ positions })
            });

            if (response.ok) {
                // Update local canvas data
                this.currentCanvas.feature_positions = positions;
                this.showToast('Canvas saved successfully!');
            } else {
                throw new Error('Failed to save');
            }
        } catch (error) {
            console.error('Error saving canvas:', error);
            this.showToast('Failed to save canvas', 'error');
        }
    }

    async createNewCanvas() {
        const name = prompt('Enter canvas name:', `Canvas ${this.canvases.length + 1}`);
        if (!name) return;

        const projectId = this.getProjectId();
        if (!projectId) return;

        try {
            const response = await fetch(`/projects/${projectId}/api/canvases/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    name,
                    feature_positions: {},  // Empty - no screens
                    visible_features: [],   // Empty - no screens visible
                    is_default: this.canvases.length === 0
                })
            });

            if (response.ok) {
                const data = await response.json();
                this.canvases.push(data.canvas);
                this.currentCanvas = data.canvas;
                this.currentCanvasId = data.canvas.id;
                window.currentDesignCanvasId = data.canvas.id;  // Store globally
                this.updateCanvasSelector();
                document.getElementById('canvas-selector').value = data.canvas.id;

                // Link new canvas to conversation
                await this.linkCanvasToConversation(data.canvas.id);

                this.render();  // Re-render to show empty canvas
                this.showToast(`Canvas "${name}" created!`);
            } else {
                const errData = await response.json();
                throw new Error(errData.error || 'Failed to create');
            }
        } catch (error) {
            console.error('Error creating canvas:', error);
            this.showToast(error.message || 'Failed to create canvas', 'error');
        }
    }

    async deleteCurrentCanvas() {
        if (!this.currentCanvasId || this.canvases.length <= 1) {
            this.showToast('Cannot delete the only canvas', 'error');
            return;
        }

        if (!confirm(`Delete canvas "${this.currentCanvas.name}"?`)) return;

        const projectId = this.getProjectId();
        if (!projectId) return;

        try {
            const response = await fetch(`/projects/${projectId}/api/canvases/${this.currentCanvasId}/`, {
                method: 'DELETE',
                headers: {
                    'X-CSRFToken': this.getCSRFToken()
                }
            });

            if (response.ok) {
                // Remove from list
                this.canvases = this.canvases.filter(c => c.id !== this.currentCanvasId);

                // Switch to first available canvas
                const firstCanvas = this.canvases[0];
                this.currentCanvas = firstCanvas;
                this.currentCanvasId = firstCanvas?.id || null;

                this.updateCanvasSelector();
                if (firstCanvas) {
                    document.getElementById('canvas-selector').value = firstCanvas.id;
                    this.render();
                }
                this.showToast('Canvas deleted');
            } else {
                throw new Error('Failed to delete');
            }
        } catch (error) {
            console.error('Error deleting canvas:', error);
            this.showToast('Failed to delete canvas', 'error');
        }
    }

    showToast(message, type = 'success') {
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `canvas-toast ${type}`;
        toast.textContent = message;
        document.body.appendChild(toast);

        // Animate in
        setTimeout(() => toast.classList.add('show'), 10);

        // Remove after delay
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    bindEvents() {
        // Back button - switch to Docs tab
        document.getElementById('canvas-back')?.addEventListener('click', () => this.goBack());

        // Zoom controls - smaller increments
        document.getElementById('canvas-zoom-in')?.addEventListener('click', () => this.animateZoom(this.zoom + 0.1));
        document.getElementById('canvas-zoom-out')?.addEventListener('click', () => this.animateZoom(this.zoom - 0.1));
        document.getElementById('canvas-fit')?.addEventListener('click', () => this.fitToScreen());
        document.getElementById('canvas-refresh')?.addEventListener('click', () => this.loadFeatures());

        // Load URL functionality
        this.bindLoadUrlEvents();

        // Tools panel buttons
        this.bindToolsPanelEvents();

        // Fullscreen toggle
        const fullscreenBtn = document.getElementById('canvas-fullscreen');
        if (fullscreenBtn) {
            fullscreenBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.toggleFullscreen();
            });
        }

        // Very slow mouse wheel zoom
        this.wrapper?.addEventListener('wheel', (e) => {
            e.preventDefault();
            // Much smaller delta for slower zoom
            const delta = e.deltaY > 0 ? -0.03 : 0.03;
            const newZoom = Math.max(0.2, Math.min(1.5, this.zoom + delta));

            // Zoom towards mouse position
            const rect = this.wrapper.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;

            const zoomFactor = newZoom / this.zoom;
            this.panX = mouseX - (mouseX - this.panX) * zoomFactor;
            this.panY = mouseY - (mouseY - this.panY) * zoomFactor;

            this.zoom = newZoom;
            this.updateTransform();
            document.getElementById('canvas-zoom-level').textContent = `${Math.round(this.zoom * 100)}%`;
        }, { passive: false });

        // Pan with mouse drag on canvas background
        this.wrapper?.addEventListener('mousedown', (e) => {
            const isBackground = e.target === this.wrapper ||
                e.target === this.canvas ||
                e.target.classList.contains('features-container') ||
                e.target.tagName === 'svg';

            if (isBackground) {
                this.isPanning = true;
                this.panStart = { x: e.clientX - this.panX, y: e.clientY - this.panY };
                this.wrapper.style.cursor = 'grabbing';
                e.preventDefault();
            }
        });

        document.addEventListener('mousemove', (e) => {
            if (this.isPanning) {
                this.panX = e.clientX - this.panStart.x;
                this.panY = e.clientY - this.panStart.y;
                this.updateTransform();
            } else if (this.isDragging && this.dragTarget) {
                const dx = e.clientX - this.dragStartPos.x;
                const dy = e.clientY - this.dragStartPos.y;

                if (Math.abs(dx) > 5 || Math.abs(dy) > 5) {
                    this.hasDragged = true;
                }

                const rect = this.canvas.getBoundingClientRect();
                const x = (e.clientX - rect.left) / this.zoom - this.dragOffset.x;
                const y = (e.clientY - rect.top) / this.zoom - this.dragOffset.y;
                this.dragTarget.style.left = `${x}px`;
                this.dragTarget.style.top = `${y}px`;
            }
        });

        document.addEventListener('mouseup', () => {
            if (this.isPanning) {
                this.isPanning = false;
                if (this.wrapper) this.wrapper.style.cursor = 'grab';
            }
            if (this.isDragging) {
                this.isDragging = false;
                this.dragTarget?.classList.remove('dragging');
                if (this.hasDragged) {
                    this.savePositions();
                }
                this.dragTarget = null;
            }
        });

        // Preview modal close
        document.getElementById('preview-close')?.addEventListener('click', () => this.closePreview());
        this.previewModal?.addEventListener('click', (e) => {
            if (e.target === this.previewModal) this.closePreview();
        });

        // Preview navigation buttons
        document.getElementById('preview-prev')?.addEventListener('click', () => this.navigatePreview(-1));
        document.getElementById('preview-next')?.addEventListener('click', () => this.navigatePreview(1));

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Only handle if not typing in an input
            if (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA') {
                return;
            }

            if (e.key === 'Escape') {
                if (this.previewModal?.classList.contains('active')) {
                    this.closePreview();
                } else if (this.isFullscreen) {
                    this.toggleFullscreen();
                }
            }
            // Arrow key navigation when preview is open
            if (this.previewModal?.classList.contains('active')) {
                if (e.key === 'ArrowLeft') {
                    e.preventDefault();
                    this.navigatePreview(-1);
                }
                if (e.key === 'ArrowRight') {
                    e.preventDefault();
                    this.navigatePreview(1);
                }
            }
            if (e.key === 'f' && !e.ctrlKey && !e.metaKey && !this.previewModal?.classList.contains('active')) {
                e.preventDefault();
                this.toggleFullscreen();
            }
            if (e.key === '0' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                this.animateZoom(1);
            }
            // Tool shortcuts
            if (e.key === 'v' || e.key === 'V') {
                this.setActiveTool('select');
            }
            if (e.key === 'a' || e.key === 'A') {
                this.addEmptyScreen();
            }
            if (e.key === 'w' || e.key === 'W') {
                this.showLoadUrlModal();
            }
            if ((e.key === 'Delete' || e.key === 'Backspace') && this.selectedScreens.size > 0) {
                e.preventDefault();
                this.deleteSelectedScreens();
            }
            if (e.key === 'h' || e.key === 'H') {
                this.setActiveTool('hand');
            }
        });
    }

    bindToolsPanelEvents() {
        // Tool buttons
        document.getElementById('tool-select')?.addEventListener('click', () => this.setActiveTool('select'));
        document.getElementById('tool-add-screen')?.addEventListener('click', () => this.addEmptyScreen());
        document.getElementById('tool-delete')?.addEventListener('click', () => this.deleteSelectedScreens());
        document.getElementById('tool-annotate')?.addEventListener('click', () => this.setActiveTool('annotate'));
        document.getElementById('tool-text')?.addEventListener('click', () => this.setActiveTool('text'));
        document.getElementById('tool-arrow')?.addEventListener('click', () => this.setActiveTool('arrow'));
        document.getElementById('tool-hand')?.addEventListener('click', () => this.setActiveTool('hand'));

        // Set default tool
        this.setActiveTool('select');
        this.updateDeleteButtonState();
    }

    bindLoadUrlEvents() {
        // Tool button to open modal
        document.getElementById('tool-load-url')?.addEventListener('click', () => this.showLoadUrlModal());

        // Modal close buttons
        document.getElementById('load-url-modal-close')?.addEventListener('click', () => this.hideLoadUrlModal());
        document.getElementById('load-url-cancel')?.addEventListener('click', () => this.hideLoadUrlModal());

        // Submit button
        document.getElementById('load-url-submit')?.addEventListener('click', () => this.loadExternalUrl());

        // Enter key in input
        document.getElementById('load-url-input')?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.loadExternalUrl();
            }
        });

        // Close modal on background click
        document.getElementById('load-url-modal')?.addEventListener('click', (e) => {
            if (e.target.id === 'load-url-modal') {
                this.hideLoadUrlModal();
            }
        });
    }

    showLoadUrlModal() {
        const modal = document.getElementById('load-url-modal');
        const input = document.getElementById('load-url-input');
        console.log('showLoadUrlModal called, modal:', modal);
        if (modal) {
            modal.style.display = 'flex';
            if (input) {
                input.value = '';
                input.focus();
            }
        } else {
            console.error('Load URL modal not found in DOM');
            this.showToast('Modal not available. Please refresh the page.', 'error');
        }
    }

    hideLoadUrlModal() {
        const modal = document.getElementById('load-url-modal');
        if (modal) {
            modal.style.display = 'none';
        }
    }

    async loadExternalUrl() {
        const input = document.getElementById('load-url-input');
        const btn = document.getElementById('load-url-submit');
        const url = input?.value?.trim();

        if (!url) {
            this.showToast('Please enter a URL', 'error');
            return;
        }

        // Validate URL format
        try {
            new URL(url);
        } catch {
            this.showToast('Please enter a valid URL', 'error');
            return;
        }

        // Show loading state
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Loading...</span>';
        }

        try {
            const projectId = this.getProjectId();
            if (!projectId) {
                throw new Error('Project not found');
            }

            // Create a new design feature with the URL
            const response = await fetch(`/projects/${projectId}/api/load-external-url/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({ url, canvas_id: this.currentCanvasId })
            });

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.error || 'Failed to load URL');
            }

            const data = await response.json();
            this.showToast('Website loaded successfully');
            this.hideLoadUrlModal();

            // Refresh features to show the new screen
            await this.loadFeatures();

        } catch (error) {
            console.error('Error loading external URL:', error);
            this.showToast(error.message || 'Failed to load URL', 'error');
        } finally {
            // Reset button state
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-globe"></i><span>Load</span>';
            }
        }
    }

    setActiveTool(tool) {
        this.currentTool = tool;

        // Update UI
        document.querySelectorAll('.tool-btn[data-tool]').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tool === tool);
        });

        // Update cursor based on tool
        const wrapper = this.wrapper;
        if (wrapper) {
            switch (tool) {
                case 'hand':
                    wrapper.style.cursor = 'grab';
                    break;
                case 'select':
                    wrapper.style.cursor = 'default';
                    break;
                default:
                    wrapper.style.cursor = 'crosshair';
            }
        }
    }

    updateDeleteButtonState() {
        const deleteBtn = document.getElementById('tool-delete');
        if (deleteBtn) {
            deleteBtn.disabled = this.selectedScreens.size === 0;
        }
    }

    toggleScreenSelection(card, addToSelection = false) {
        const screenKey = `${card.dataset.featureId}_${card.dataset.pageId}`;

        if (!addToSelection) {
            // Clear other selections
            this.selectedScreens.forEach(key => {
                const otherCard = document.querySelector(`[data-feature-id="${key.split('_')[0]}"][data-page-id="${key.split('_').slice(1).join('_')}"]`);
                otherCard?.classList.remove('selected');
            });
            this.selectedScreens.clear();
        }

        if (this.selectedScreens.has(screenKey)) {
            this.selectedScreens.delete(screenKey);
            card.classList.remove('selected');
        } else {
            this.selectedScreens.add(screenKey);
            card.classList.add('selected');
        }

        this.updateDeleteButtonState();
    }

    clearSelection() {
        this.selectedScreens.forEach(key => {
            const [featureId, ...pageIdParts] = key.split('_');
            const pageId = pageIdParts.join('_');
            const card = document.querySelector(`[data-feature-id="${featureId}"][data-page-id="${pageId}"]`);
            card?.classList.remove('selected');
        });
        this.selectedScreens.clear();
        this.updateDeleteButtonState();
    }

    async deleteSelectedScreens() {
        if (this.selectedScreens.size === 0) {
            this.showToast('No screens selected. Click on a screen to select it first.', 'error');
            return;
        }

        const count = this.selectedScreens.size;
        const confirmMsg = count === 1
            ? 'Are you sure you want to delete this screen?'
            : `Are you sure you want to delete ${count} screens?`;

        if (!confirm(confirmMsg)) return;

        const projectId = this.getProjectId();
        if (!projectId) return;

        // Group deletions by feature
        const deletionsByFeature = new Map();
        this.selectedScreens.forEach(key => {
            const [featureId, ...pageIdParts] = key.split('_');
            const pageId = pageIdParts.join('_');
            if (!deletionsByFeature.has(featureId)) {
                deletionsByFeature.set(featureId, []);
            }
            deletionsByFeature.get(featureId).push(pageId);
        });

        try {
            // Delete screens via API
            for (const [featureId, pageIds] of deletionsByFeature) {
                const response = await fetch(`/projects/${projectId}/api/delete-screens/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCSRFToken()
                    },
                    body: JSON.stringify({
                        feature_id: featureId,
                        page_ids: pageIds
                    })
                });

                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.error || 'Failed to delete screens');
                }
            }

            // Also remove from canvas positions
            if (this.currentCanvas) {
                this.selectedScreens.forEach(key => {
                    delete this.currentCanvas.feature_positions[key];
                });
                await this.saveCanvasToServer();
            }

            this.showToast(`Deleted ${count} screen${count > 1 ? 's' : ''}`);
            this.clearSelection();
            await this.loadFeatures();

        } catch (error) {
            console.error('Error deleting screens:', error);
            this.showToast(error.message || 'Failed to delete screens', 'error');
        }
    }

<<<<<<< Updated upstream
    async deleteScreen(featureId, pageId, pageName) {
        if (!confirm(`Delete "${pageName}"?`)) return;
=======
    async deleteScreen(featureId, pageId) {
        if (!confirm('Are you sure you want to delete this screen?')) return;
>>>>>>> Stashed changes

        const projectId = this.getProjectId();
        if (!projectId) return;

        try {
            const response = await fetch(`/projects/${projectId}/api/delete-screens/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    feature_id: featureId,
                    page_ids: [pageId]
                })
            });

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.error || 'Failed to delete screen');
            }

<<<<<<< Updated upstream
            // Remove from canvas positions
            if (this.currentCanvas) {
                const key = `${featureId}_${pageId}`;
                delete this.currentCanvas.feature_positions[key];
=======
            // Also remove from canvas positions
            const screenKey = `${featureId}_${pageId}`;
            if (this.currentCanvas) {
                delete this.currentCanvas.feature_positions[screenKey];
>>>>>>> Stashed changes
                await this.saveCanvasToServer();
            }

            this.showToast('Screen deleted');
            await this.loadFeatures();

        } catch (error) {
            console.error('Error deleting screen:', error);
            this.showToast(error.message || 'Failed to delete screen', 'error');
        }
    }

    animateZoom(targetZoom) {
        targetZoom = Math.max(0.2, Math.min(1.5, targetZoom));
        this.targetZoom = targetZoom;

        if (this.zoomAnimationId) {
            cancelAnimationFrame(this.zoomAnimationId);
        }

        const startZoom = this.zoom;
        const startTime = performance.now();
        const duration = 300; // Longer duration for smoother feel

        const animate = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);

            // Ease out cubic for smooth deceleration
            const easeProgress = 1 - Math.pow(1 - progress, 3);

            this.zoom = startZoom + (targetZoom - startZoom) * easeProgress;
            this.updateTransform();
            document.getElementById('canvas-zoom-level').textContent = `${Math.round(this.zoom * 100)}%`;

            if (progress < 1) {
                this.zoomAnimationId = requestAnimationFrame(animate);
            } else {
                this.zoomAnimationId = null;
            }
        };

        this.zoomAnimationId = requestAnimationFrame(animate);
    }

    updateTransform() {
        this.canvas.style.transform = `translate(${this.panX}px, ${this.panY}px) scale(${this.zoom})`;
    }

    goBack() {
        // Switch to the Docs tab (filebrowser)
        const docsTab = document.querySelector('[data-tab="filebrowser"]');
        if (docsTab) {
            docsTab.click();
        }
    }

    toggleFullscreen() {
        this.isFullscreen = !this.isFullscreen;
        this.container.classList.toggle('fullscreen', this.isFullscreen);
        document.body.classList.toggle('design-fullscreen-active', this.isFullscreen);

        const btn = document.getElementById('canvas-fullscreen');
        if (btn) {
            btn.innerHTML = this.isFullscreen ?
                '<i class="fas fa-compress"></i>' :
                '<i class="fas fa-expand-arrows-alt"></i>';
            btn.title = this.isFullscreen ? 'Exit Fullscreen (F or Esc)' : 'Fullscreen (F)';
        }

        // Re-fit after toggling fullscreen
        setTimeout(() => this.fitToScreen(), 150);
    }

    fitToScreen() {
        const wrapperRect = this.wrapper.getBoundingClientRect();
        const bounds = this.getContentBounds();

        if (bounds.width === 0 || bounds.height === 0) {
            this.animateZoom(0.7);
            this.panX = 50;
            this.panY = 50;
            this.updateTransform();
            return;
        }

        const padding = 60;
        const scaleX = (wrapperRect.width - padding * 2) / bounds.width;
        const scaleY = (wrapperRect.height - padding * 2) / bounds.height;
        const scale = Math.min(scaleX, scaleY, 1.2);

        const targetPanX = padding - bounds.minX * scale + (wrapperRect.width - bounds.width * scale - padding * 2) / 2;
        const targetPanY = padding - bounds.minY * scale;

        // Animate pan
        const startPanX = this.panX;
        const startPanY = this.panY;
        const startTime = performance.now();
        const duration = 350;

        const animatePan = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const easeProgress = 1 - Math.pow(1 - progress, 3);

            this.panX = startPanX + (targetPanX - startPanX) * easeProgress;
            this.panY = startPanY + (targetPanY - startPanY) * easeProgress;
            this.updateTransform();

            if (progress < 1) {
                requestAnimationFrame(animatePan);
            }
        };

        this.animateZoom(scale);
        requestAnimationFrame(animatePan);
    }

    getContentBounds() {
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;

        const cards = this.featuresContainer.querySelectorAll('.screen-card');
        cards.forEach((card) => {
            const x = parseFloat(card.style.left) || 0;
            const y = parseFloat(card.style.top) || 0;
            const width = card.offsetWidth || this.cardWidth;
            const height = card.offsetHeight || this.cardHeight;

            minX = Math.min(minX, x);
            minY = Math.min(minY, y);
            maxX = Math.max(maxX, x + width);
            maxY = Math.max(maxY, y + height);
        });

        return {
            minX: minX === Infinity ? 0 : minX,
            minY: minY === Infinity ? 0 : minY,
            width: maxX === -Infinity ? 0 : maxX - minX,
            height: maxY === -Infinity ? 0 : maxY - minY
        };
    }

    async loadFeatures() {
        console.log('[DesignCanvas] loadFeatures called');
        this.showLoading(true);

        try {
            const projectId = this.getProjectId();
            console.log('[DesignCanvas] projectId:', projectId);
            if (!projectId) {
                console.log('[DesignCanvas] No projectId, showing empty');
                this.showEmpty(true);
                return;
            }

            const response = await fetch(`/projects/${projectId}/api/design-features/`);
            console.log('[DesignCanvas] API response status:', response.status);
            if (!response.ok) throw new Error('Failed to load features');

            const data = await response.json();
            console.log('[DesignCanvas] API response data:', data);
            console.log('[DesignCanvas] Features count:', data.features?.length || 0);
            this.features.clear();

            if (!data.features || data.features.length === 0) {
                console.log('[DesignCanvas] No features found, showing empty');
                this.showEmpty(true);
                return;
            }

            data.features.forEach((feature) => {
                console.log('[DesignCanvas] Adding feature:', feature.feature_id, feature.feature_name, 'pages:', feature.pages?.length || 0);
                this.features.set(feature.feature_id, feature);
            });

            console.log('[DesignCanvas] Total features in map:', this.features.size);
            console.log('[DesignCanvas] Current canvas:', this.currentCanvas);
            this.render();
            this.showEmpty(false);

        } catch (error) {
            console.error('[DesignCanvas] Error loading features:', error);
            this.showEmpty(true);
        } finally {
            this.showLoading(false);
        }
    }

    getProjectId() {
        return window.projectId ||
               document.querySelector('[data-project-id]')?.dataset.projectId ||
               new URLSearchParams(window.location.search).get('project_id');
    }

    render() {
        console.log('[DesignCanvas] render() called');
        this.featuresContainer.innerHTML = '';
        this.pageElements.clear();
        this.hideEmptyCanvasState();

        // Get saved positions from current canvas
        const savedPositions = this.currentCanvas?.feature_positions || {};
        const isDefaultCanvas = this.currentCanvas?.is_default === true;
        console.log('[DesignCanvas] render - currentCanvas:', this.currentCanvas);
        console.log('[DesignCanvas] render - savedPositions:', Object.keys(savedPositions).length, 'items');
        console.log('[DesignCanvas] render - isDefaultCanvas:', isDefaultCanvas);
        console.log('[DesignCanvas] render - features.size:', this.features.size);

        // For default canvas OR canvas with no positions yet: show all screens
        // For non-default canvas with positions: show only screens with saved positions
        const hasPositions = Object.keys(savedPositions).length > 0;
        console.log('[DesignCanvas] render - hasPositions:', hasPositions);

        // Check if we have any screens at all
        if (this.features.size === 0) {
            console.log('[DesignCanvas] render - No features, showing empty');
            this.showEmpty(true);
            return;
        }

        // Show all screens if: default canvas OR canvas has no positions yet (new canvas)
        // This way new canvases show all screens until user customizes them
        const showAllScreens = isDefaultCanvas || !hasPositions;
        console.log('[DesignCanvas] render - showAllScreens:', showAllScreens);

        let currentY = 50;
        let hasVisibleScreens = false;

        this.features.forEach((feature) => {
            const pages = feature.pages || [];

            // Filter pages based on canvas type
            // Show all pages if: default canvas OR new canvas with no positions
            const visiblePages = showAllScreens ? pages : pages.filter(page => {
                const positionKey = `${feature.feature_id}_${page.page_id}`;
                return savedPositions[positionKey];
            });

            if (visiblePages.length === 0) return;
            hasVisibleScreens = true;

            // Add feature section header
            const sectionHeader = document.createElement('div');
            sectionHeader.className = 'feature-section-header';
            sectionHeader.style.left = '50px';
            sectionHeader.style.top = `${currentY}px`;
            const platformBadge = feature.platform === 'mobile'
                ? '<span class="platform-badge mobile"><i class="fas fa-mobile-alt"></i> iOS</span>'
                : '<span class="platform-badge web"><i class="fas fa-desktop"></i> Web</span>';
            sectionHeader.innerHTML = `
                <span class="feature-section-title">${this.escapeHtml(feature.feature_name)}</span>
                ${platformBadge}
                <span class="feature-section-count">${visiblePages.length} screens</span>
            `;
            this.featuresContainer.appendChild(sectionHeader);

            currentY += 50;

            const columns = Math.min(4, Math.max(3, Math.ceil(Math.sqrt(visiblePages.length))));

            visiblePages.forEach((page, index) => {
                // Check for saved position in current canvas
                const positionKey = `${feature.feature_id}_${page.page_id}`;
                const savedPos = savedPositions[positionKey];

                let x, y;
                if (savedPos) {
                    // Use saved position
                    x = savedPos.x;
                    y = savedPos.y;
                } else {
                    // Calculate default grid position
                    const col = index % columns;
                    const row = Math.floor(index / columns);
                    x = 50 + col * (this.cardWidth + this.cardGap);
                    y = currentY + row * (this.cardHeight + this.cardGap);
                }

                const card = this.createScreenCard(feature, page, x, y);
                this.featuresContainer.appendChild(card);

                const pageKey = page.page_id;
                this.pageElements.set(pageKey, card);
            });

            // Move to next section (only for calculating header position)
            const rows = Math.ceil(visiblePages.length / columns);
            currentY += rows * (this.cardHeight + this.cardGap) + 80;
        });

        // Show empty state if no visible screens
        if (!hasVisibleScreens) {
            this.showEmptyCanvasState();
            return;
        }

        // Hide empty state if showing screens
        this.hideEmptyCanvasState();

        // Fit to screen after render
        requestAnimationFrame(() => {
            setTimeout(() => this.fitToScreen(), 50);
        });
    }

    showEmptyCanvasState() {
        // For empty canvas, just show the features container (which will be empty)
        // Users can click the + button in the toolbar to add screens
        if (this.featuresContainer) {
            this.featuresContainer.style.display = 'block';
        }

        // Remove any existing empty canvas state UI
        const existingEmptyState = document.getElementById('empty-canvas-state');
        if (existingEmptyState) {
            existingEmptyState.remove();
        }
    }

    hideEmptyCanvasState() {
        const emptyState = document.getElementById('empty-canvas-state');
        if (emptyState) {
            emptyState.style.display = 'none';
        }
        if (this.featuresContainer) {
            this.featuresContainer.style.display = 'block';
        }
    }

    showScreenPicker() {
        // Create screen picker modal
        let picker = document.getElementById('screen-picker-modal');
        if (picker) picker.remove();

        picker = document.createElement('div');
        picker.id = 'screen-picker-modal';
        picker.className = 'screen-picker-modal';

        // Get current visible screens
        const savedPositions = this.currentCanvas?.feature_positions || {};
        const currentlyVisible = new Set(Object.keys(savedPositions));

        let screensHtml = '';
        this.features.forEach((feature) => {
            const pages = feature.pages || [];
            if (pages.length === 0) return;

            screensHtml += `<div class="picker-feature-group">
                <div class="picker-feature-header">
                    <span class="picker-feature-name">${this.escapeHtml(feature.feature_name)}</span>
                    <button class="picker-add-all" data-feature-id="${feature.feature_id}">Add All</button>
                </div>
                <div class="picker-screens">`;

            pages.forEach(page => {
                const key = `${feature.feature_id}_${page.page_id}`;
                const isAdded = currentlyVisible.has(key);
                screensHtml += `
                    <div class="picker-screen ${isAdded ? 'added' : ''}"
                         data-key="${key}"
                         data-feature-id="${feature.feature_id}"
                         data-page-id="${page.page_id}">
                        <span class="picker-screen-name">${this.escapeHtml(page.page_name)}</span>
                        <button class="picker-toggle-btn">${isAdded ? '<i class="fas fa-check"></i>' : '<i class="fas fa-plus"></i>'}</button>
                    </div>`;
            });

            screensHtml += '</div></div>';
        });

        picker.innerHTML = `
            <div class="screen-picker-content">
                <div class="screen-picker-header">
                    <span>Add Screens to Canvas</span>
                    <button class="screen-picker-close" id="screen-picker-close"><i class="fas fa-times"></i></button>
                </div>
                <div class="screen-picker-body">
                    ${screensHtml || '<p class="no-screens">No screens available</p>'}
                </div>
                <div class="screen-picker-footer">
                    <button class="picker-done-btn" id="picker-done-btn">Done</button>
                </div>
            </div>
        `;

        document.body.appendChild(picker);

        // Bind events
        document.getElementById('screen-picker-close')?.addEventListener('click', () => picker.remove());
        document.getElementById('picker-done-btn')?.addEventListener('click', () => {
            picker.remove();
            this.render();
            setTimeout(() => this.fitToScreen(), 100);
        });

        // Toggle individual screens
        picker.querySelectorAll('.picker-screen').forEach(el => {
            el.addEventListener('click', () => this.toggleScreenInCanvas(el));
        });

        // Add all screens in a feature
        picker.querySelectorAll('.picker-add-all').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const featureId = btn.dataset.featureId;
                picker.querySelectorAll(`.picker-screen[data-feature-id="${featureId}"]`).forEach(el => {
                    if (!el.classList.contains('added')) {
                        this.toggleScreenInCanvas(el);
                    }
                });
            });
        });

        // Close on backdrop click
        picker.addEventListener('click', (e) => {
            if (e.target === picker) picker.remove();
        });
    }

    toggleScreenInCanvas(el) {
        const key = el.dataset.key;
        const featureId = el.dataset.featureId;
        const pageId = el.dataset.pageId;
        const isAdded = el.classList.contains('added');

        if (!this.currentCanvas) return;

        // Initialize if needed
        if (!this.currentCanvas.feature_positions) {
            this.currentCanvas.feature_positions = {};
        }

        if (isAdded) {
            // Remove from canvas
            delete this.currentCanvas.feature_positions[key];
            el.classList.remove('added');
            el.querySelector('.picker-toggle-btn').innerHTML = '<i class="fas fa-plus"></i>';
        } else {
            // Add to canvas with default position
            this.currentCanvas.feature_positions[key] = { x: 50, y: 50 };
            el.classList.add('added');
            el.querySelector('.picker-toggle-btn').innerHTML = '<i class="fas fa-check"></i>';
        }

        // Save to server
        this.saveCanvasToServer();
    }

    async saveCanvasToServer() {
        if (!this.currentCanvasId || !this.currentCanvas) return;

        const projectId = this.getProjectId();
        if (!projectId) return;

        try {
            await fetch(`/projects/${projectId}/api/canvases/${this.currentCanvasId}/positions/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({ positions: this.currentCanvas.feature_positions })
            });
        } catch (error) {
            console.error('Error saving canvas:', error);
        }
    }

    createScreenCard(feature, page, x, y) {
        const card = document.createElement('div');
        card.className = 'screen-card';
        card.id = `screen-${feature.feature_id}-${page.page_id}`;
        card.dataset.featureId = feature.feature_id;
        card.dataset.pageId = page.page_id;
        card.style.left = `${x}px`;
        card.style.top = `${y}px`;
        card.style.width = `${this.cardWidth}px`;

        const isEntry = page.is_entry || page.page_id === feature.entry_page_id;
        if (isEntry) card.classList.add('entry-point');

        // Create thumbnail preview
        const thumbnailHtml = this.createThumbnail(feature, page);

        card.innerHTML = `
            <div class="screen-thumbnail">
                ${thumbnailHtml}
            </div>
            <button class="screen-delete-btn" title="Delete Screen">
                <i class="fas fa-trash-alt"></i>
            </button>
            <div class="screen-info">
                <div class="screen-name-row">
                    <div class="screen-name">${this.escapeHtml(page.page_name)}</div>
                    <div class="screen-actions">
                        <button class="ai-edit-btn" title="Edit with AI">
                            <i class="fas fa-magic"></i>
                        </button>
                        <button class="screen-delete-btn" title="Delete Screen">
                            <i class="fas fa-trash-alt"></i>
                        </button>
                    </div>
                </div>
                <div class="screen-meta">
                    <span class="screen-type ${page.page_type || 'screen'}">${page.page_type || 'screen'}</span>
                    ${isEntry ? '<span class="entry-badge">Entry</span>' : ''}
                </div>
            </div>
        `;

        // AI edit button click
        const aiBtn = card.querySelector('.ai-edit-btn');
        aiBtn?.addEventListener('click', (e) => {
            e.stopPropagation();
            e.preventDefault();
            this.openAIChat(feature, page);
        });

        // Delete button click
        const deleteBtn = card.querySelector('.screen-delete-btn');
        deleteBtn?.addEventListener('click', (e) => {
            e.stopPropagation();
            e.preventDefault();
<<<<<<< Updated upstream
            this.deleteScreen(feature.feature_id, page.page_id, page.page_name);
=======
            this.deleteScreen(feature.feature_id, page.page_id);
>>>>>>> Stashed changes
        });

        // Drag to reposition
        card.addEventListener('mousedown', (e) => {
<<<<<<< Updated upstream
            // Don't start drag if clicking action buttons
=======
            // Don't start drag if clicking buttons
>>>>>>> Stashed changes
            if (e.target.closest('.ai-edit-btn') || e.target.closest('.screen-delete-btn')) return;

            e.stopPropagation();
            e.preventDefault();

            this.isDragging = true;
            this.hasDragged = false;
            this.dragTarget = card;
            this.dragStartPos = { x: e.clientX, y: e.clientY };
            card.classList.add('dragging');

            const rect = card.getBoundingClientRect();
            this.dragOffset = {
                x: (e.clientX - rect.left) / this.zoom,
                y: (e.clientY - rect.top) / this.zoom
            };
        });

        // Click handler - selection or preview depending on modifier keys
        card.addEventListener('click', (e) => {
            if (e.target.closest('.ai-edit-btn') || e.target.closest('.screen-delete-btn')) return;
            if (this.hasDragged) {
                this.hasDragged = false;
                return;
            }

            // Shift+click or Ctrl/Cmd+click for multi-select
            if (e.shiftKey || e.ctrlKey || e.metaKey) {
                this.toggleScreenSelection(card, true);
            } else if (this.selectedScreens.size > 0) {
                // If there are selected screens, toggle selection
                this.toggleScreenSelection(card, false);
            } else {
                // No selections - open preview
                this.openPreview(feature, page);
            }
        });

        // Double-click always opens preview
        card.addEventListener('dblclick', (e) => {
            if (e.target.closest('.ai-edit-btn') || e.target.closest('.screen-delete-btn')) return;
            this.openPreview(feature, page);
        });

        return card;
    }

    /**
     * Compose full page HTML by combining page content with applicable common elements
     */
    composePageHtml(feature, page) {
        const commonElements = feature.common_elements || [];
        const pageContent = page.html_content || '';
        const pageId = page.page_id;

        if (!commonElements.length) {
            return pageContent;
        }

        // Filter common elements that apply to this page
        const applicableElements = commonElements.filter(elem => {
            const appliesTo = elem.applies_to || [];
            const excludeFrom = elem.exclude_from || [];

            const applies = appliesTo.includes('all') || appliesTo.includes(pageId);
            const excluded = excludeFrom.includes(pageId);

            return applies && !excluded;
        });

        // Sort by position
        const positionOrder = { 'fixed-top': 0, 'top': 1, 'left': 2, 'right': 3, 'bottom': 4, 'fixed-bottom': 5 };
        applicableElements.sort((a, b) => (positionOrder[a.position] || 1) - (positionOrder[b.position] || 1));

        // Build composed HTML
        const topElements = [];
        const leftElements = [];
        const rightElements = [];
        const bottomElements = [];

        applicableElements.forEach(elem => {
            const pos = elem.position || 'top';
            const html = elem.html_content || '';
            if (pos === 'top' || pos === 'fixed-top') {
                topElements.push(html);
            } else if (pos === 'left') {
                leftElements.push(html);
            } else if (pos === 'right') {
                rightElements.push(html);
            } else if (pos === 'bottom' || pos === 'fixed-bottom') {
                bottomElements.push(html);
            }
        });

        // Compose the full page
        let composed = '';
        composed += topElements.join('\n');

        if (leftElements.length || rightElements.length) {
            composed += '<div class="layout-wrapper">';
            composed += leftElements.join('\n');
            composed += `<div class="main-content">${pageContent}</div>`;
            composed += rightElements.join('\n');
            composed += '</div>';
        } else {
            composed += pageContent;
        }

        composed += bottomElements.join('\n');

        return composed;
    }

    createThumbnail(feature, page) {
        const cssContent = feature.css_style || '';
        const htmlContent = page.html_content || '';

        if (!htmlContent) {
            return `<div class="empty-thumbnail"><i class="fas fa-desktop"></i></div>`;
        }

        // Compose full HTML with common elements (header, footer, sidebar)
        const composedHtml = this.composePageHtml(feature, page);

        const fullHtml = `
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    ${cssContent}
                    body { margin: 0; transform-origin: top left; overflow: hidden; }
                </style>
            </head>
            <body>${composedHtml}</body>
            </html>
        `.replace(/"/g, '&quot;');

        return `<iframe class="thumbnail-iframe" srcdoc="${fullHtml}" scrolling="no" sandbox="allow-same-origin"></iframe>`;
    }

    openAIChat(feature, page) {
        // Dispatch custom event to open AI chat panel
        const event = new CustomEvent('openDesignAIChat', {
            detail: {
                featureId: feature.feature_id,
                featureName: feature.feature_name,
                pageId: page.page_id,
                pageName: page.page_name,
                htmlContent: page.html_content,
                cssStyle: feature.css_style
            }
        });
        document.dispatchEvent(event);

        // Also try to show a built-in chat panel if available
        this.showAIChatPanel(feature, page);
    }

    showAIChatPanel(feature, page) {
        // Create or show the AI chat panel
        let panel = document.getElementById('design-ai-chat-panel');

        if (!panel) {
            panel = document.createElement('div');
            panel.id = 'design-ai-chat-panel';
            panel.className = 'design-ai-chat-panel';
            panel.innerHTML = `
                <div class="ai-chat-header">
                    <div class="ai-chat-title">
                        <i class="fas fa-magic"></i>
                        <span>Edit with AI</span>
                    </div>
                    <button class="ai-chat-close" id="ai-chat-close">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div class="ai-chat-screen-info" id="ai-chat-screen-info"></div>
                <div class="ai-chat-messages" id="ai-chat-messages">
                    <div class="ai-chat-welcome">
                        <i class="fas fa-sparkles"></i>
                        <p>Describe the changes you want to make to this screen</p>
                    </div>
                </div>
                <div class="ai-chat-input-container">
                    <textarea class="ai-chat-input" id="ai-chat-input" placeholder="Describe changes... (e.g., 'Make the button larger', 'Change the color scheme to blue')"></textarea>
                    <button class="ai-chat-send" id="ai-chat-send">
                        <i class="fas fa-paper-plane"></i>
                    </button>
                </div>
            `;
            // Append to body for fixed positioning
            document.body.appendChild(panel);

            // Bind close button
            document.getElementById('ai-chat-close')?.addEventListener('click', () => {
                panel.classList.remove('active');
            });

            // Bind send button
            document.getElementById('ai-chat-send')?.addEventListener('click', () => {
                this.sendAIChatMessage();
            });

            // Bind enter key
            document.getElementById('ai-chat-input')?.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendAIChatMessage();
                }
            });
        }

        // Update screen info
        const screenInfo = document.getElementById('ai-chat-screen-info');
        if (screenInfo) {
            screenInfo.innerHTML = `
                <span class="ai-screen-label">Editing:</span>
                <span class="ai-screen-name">${this.escapeHtml(page.page_name)}</span>
            `;
        }

        // Store current context
        panel.dataset.featureId = feature.feature_id;
        panel.dataset.pageId = page.page_id;
        panel.dataset.cssStyle = feature.css_style || '';
        panel.dataset.htmlContent = page.html_content || '';

        // Show panel
        panel.classList.add('active');

        // Focus input
        setTimeout(() => {
            document.getElementById('ai-chat-input')?.focus();
        }, 100);
    }

    async sendAIChatMessage() {
        const input = document.getElementById('ai-chat-input');
        const messagesContainer = document.getElementById('ai-chat-messages');
        const panel = document.getElementById('design-ai-chat-panel');
        const sendBtn = document.getElementById('ai-chat-send');
        const message = input?.value?.trim();

        if (!message) return;

        const featureId = panel?.dataset.featureId;
        const pageId = panel?.dataset.pageId;
        const projectId = this.getProjectId();

        if (!featureId || !pageId || !projectId) {
            console.error('Missing context for AI chat');
            return;
        }

        // Add user message
        const userMsg = document.createElement('div');
        userMsg.className = 'ai-chat-message user';
        userMsg.innerHTML = `<p>${this.escapeHtml(message)}</p>`;
        messagesContainer?.appendChild(userMsg);

        // Clear input and disable send button
        if (input) input.value = '';
        if (sendBtn) sendBtn.disabled = true;
        if (input) input.disabled = true;

        // Add loading message
        const loadingMsg = document.createElement('div');
        loadingMsg.className = 'ai-chat-message assistant loading';
        loadingMsg.innerHTML = `<p><i class="fas fa-circle-notch fa-spin"></i> Updating design...</p>`;
        messagesContainer?.appendChild(loadingMsg);

        // Scroll to bottom
        if (messagesContainer) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }

        try {
            const response = await fetch(`/projects/${projectId}/api/design-chat/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    feature_id: featureId,
                    page_id: pageId,
                    message: message
                })
            });

            const data = await response.json();

            // Remove loading message
            loadingMsg.remove();

            if (data.success) {
                // Show success message
                const assistantMsg = document.createElement('div');
                assistantMsg.className = 'ai-chat-message assistant success';
                assistantMsg.innerHTML = `
                    <p><i class="fas fa-check-circle"></i> ${this.escapeHtml(data.change_summary || 'Design updated successfully!')}</p>
                    ${data.assistant_message && data.assistant_message !== data.change_summary ? `<p class="ai-detail">${this.escapeHtml(data.assistant_message)}</p>` : ''}
                `;
                messagesContainer?.appendChild(assistantMsg);

                // Update the stored HTML content
                if (data.updated_html) {
                    panel.dataset.htmlContent = data.updated_html;
                }
                if (data.updated_css) {
                    panel.dataset.cssStyle = data.updated_css;
                }

                // Update the screen card thumbnail (pass edit_target and element_id)
                this.updateScreenCard(
                    featureId,
                    pageId,
                    data.updated_html,
                    data.updated_css,
                    data.edit_target || 'page_content',
                    data.element_id
                );

                // If preview modal is open, update it too with composed HTML
                if (this.previewModal?.classList.contains('active')) {
                    // Get the feature and page to compose HTML
                    const feature = this.features.get(featureId) || this.features.get(parseInt(featureId));
                    if (feature) {
                        const page = (feature.pages || []).find(p => p.page_id === pageId);
                        if (page) {
                            const composedHtml = this.composePageHtml(feature, page);
                            this.updatePreviewContent(composedHtml, data.updated_css || feature.css_style);
                        }
                    }
                }

            } else {
                // Show error message
                const assistantMsg = document.createElement('div');
                assistantMsg.className = 'ai-chat-message assistant error';
                assistantMsg.innerHTML = `
                    <p><i class="fas fa-exclamation-circle"></i> ${this.escapeHtml(data.error || 'Failed to update design')}</p>
                    ${data.assistant_message ? `<p class="ai-detail">${this.escapeHtml(data.assistant_message)}</p>` : ''}
                `;
                messagesContainer?.appendChild(assistantMsg);
            }

        } catch (error) {
            console.error('Error sending AI chat message:', error);
            loadingMsg.remove();

            const errorMsg = document.createElement('div');
            errorMsg.className = 'ai-chat-message assistant error';
            errorMsg.innerHTML = `<p><i class="fas fa-exclamation-circle"></i> Connection error. Please try again.</p>`;
            messagesContainer?.appendChild(errorMsg);
        } finally {
            // Re-enable input
            if (sendBtn) sendBtn.disabled = false;
            if (input) {
                input.disabled = false;
                input.focus();
            }

            // Scroll to bottom
            if (messagesContainer) {
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }
        }
    }

    updateScreenCard(featureId, pageId, newHtml, newCss, editTarget = 'page_content', elementId = null) {
        // Find the screen card
        const card = document.getElementById(`screen-${featureId}-${pageId}`);
        if (!card) return;

        // Get the feature for CSS (try both string and number keys)
        let feature = this.features.get(featureId) || this.features.get(parseInt(featureId));
        if (!feature) return;

        const cssContent = newCss || feature.css_style || '';

        // Update in-memory data based on edit target
        if (editTarget === 'common_element' && elementId) {
            // Update a common element
            const commonElements = feature.common_elements || [];
            const elemIndex = commonElements.findIndex(e => e.element_id === elementId);
            if (elemIndex >= 0) {
                commonElements[elemIndex].html_content = newHtml;
            }
        } else {
            // Update page content
            const pages = feature.pages || [];
            const page = pages.find(p => p.page_id === pageId);
            if (page) {
                page.html_content = newHtml;
            }
        }

        if (newCss) {
            feature.css_style = newCss;
        }

        // Get the current page for composing
        const pages = feature.pages || [];
        const page = pages.find(p => p.page_id === pageId);
        if (!page) return;

        // Compose full HTML with common elements
        const composedHtml = this.composePageHtml(feature, page);

        // Update the thumbnail iframe
        const thumbnailContainer = card.querySelector('.screen-thumbnail');
        if (thumbnailContainer) {
            const fullHtml = `
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <style>
                        ${cssContent}
                        body { margin: 0; transform-origin: top left; overflow: hidden; }
                    </style>
                </head>
                <body>${composedHtml}</body>
                </html>
            `.replace(/"/g, '&quot;');

            thumbnailContainer.innerHTML = `<iframe class="thumbnail-iframe" srcdoc="${fullHtml}" scrolling="no" sandbox="allow-same-origin"></iframe>`;
        }
    }

    updatePreviewContent(newHtml, cssContent) {
        const iframe = document.getElementById('preview-iframe');
        if (!iframe) return;

        const fullHtml = `
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>${cssContent}</style>
            </head>
            <body>${newHtml}</body>
            </html>
        `;

        iframe.srcdoc = fullHtml;
    }

    openPreview(feature, page) {
        const modal = this.previewModal;
        const iframe = document.getElementById('preview-iframe');
        const title = document.getElementById('preview-title');

        // Store current feature and page for navigation
        this.currentPreviewFeature = feature;
        this.currentPreviewPages = feature.pages || [];
        this.currentPreviewIndex = this.currentPreviewPages.findIndex(p => p.page_id === page.page_id);
        if (this.currentPreviewIndex < 0) this.currentPreviewIndex = 0;

        // Update title with feature -> screen format
        title.innerHTML = `
            <span class="preview-feature-name">${this.escapeHtml(feature.feature_name)}</span>
            <span class="preview-separator">→</span>
            <span class="preview-screen-name">${this.escapeHtml(page.page_name)}</span>
        `;

        // Update navigation state
        this.updatePreviewNavigation();

        const cssContent = feature.css_style || '';
        // Compose full HTML with common elements (header, footer, sidebar)
        const composedHtml = this.composePageHtml(feature, page);

        const fullHtml = `
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>${cssContent}</style>
            </head>
            <body>${composedHtml}</body>
            </html>
        `;

        iframe.srcdoc = fullHtml;
        modal.classList.add('active');
    }

    updatePreviewNavigation() {
        const prevBtn = document.getElementById('preview-prev');
        const nextBtn = document.getElementById('preview-next');
        const counter = document.getElementById('preview-counter');

        if (prevBtn) {
            prevBtn.disabled = this.currentPreviewIndex <= 0;
        }
        if (nextBtn) {
            nextBtn.disabled = this.currentPreviewIndex >= this.currentPreviewPages.length - 1;
        }
        if (counter) {
            counter.textContent = `${this.currentPreviewIndex + 1} / ${this.currentPreviewPages.length}`;
        }
    }

    navigatePreview(direction) {
        const newIndex = this.currentPreviewIndex + direction;
        if (newIndex < 0 || newIndex >= this.currentPreviewPages.length) return;

        this.currentPreviewIndex = newIndex;
        const page = this.currentPreviewPages[newIndex];

        // Update title
        const title = document.getElementById('preview-title');
        title.innerHTML = `
            <span class="preview-feature-name">${this.escapeHtml(this.currentPreviewFeature.feature_name)}</span>
            <span class="preview-separator">→</span>
            <span class="preview-screen-name">${this.escapeHtml(page.page_name)}</span>
        `;

        // Update navigation state
        this.updatePreviewNavigation();

        // Update iframe content
        const iframe = document.getElementById('preview-iframe');
        const cssContent = this.currentPreviewFeature.css_style || '';
        // Compose full HTML with common elements (header, footer, sidebar)
        const composedHtml = this.composePageHtml(this.currentPreviewFeature, page);

        const fullHtml = `
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>${cssContent}</style>
            </head>
            <body>${composedHtml}</body>
            </html>
        `;

        iframe.srcdoc = fullHtml;
    }

    closePreview() {
        this.previewModal?.classList.remove('active');
        this.currentPreviewFeature = null;
        this.currentPreviewPages = [];
        this.currentPreviewIndex = 0;
    }

    async savePositions() {
        const projectId = this.getProjectId();
        if (!projectId) return;

        // Collect positions with feature_id included for canvas storage
        const positions = {};
        this.pageElements.forEach((el, pageId) => {
            const featureId = el.dataset.featureId;
            const key = `${featureId}_${pageId}`;
            positions[key] = {
                x: parseFloat(el.style.left) || 0,
                y: parseFloat(el.style.top) || 0
            };
        });

        try {
            // If a canvas is selected, save to that canvas
            if (this.currentCanvasId) {
                await fetch(`/projects/${projectId}/api/canvases/${this.currentCanvasId}/positions/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCSRFToken()
                    },
                    body: JSON.stringify({ positions })
                });
                // Update local canvas data
                if (this.currentCanvas) {
                    this.currentCanvas.feature_positions = positions;
                }
            } else {
                // Fallback to legacy positions API
                const legacyPositions = {};
                this.pageElements.forEach((el, pageId) => {
                    legacyPositions[pageId] = {
                        x: parseFloat(el.style.left) || 0,
                        y: parseFloat(el.style.top) || 0
                    };
                });
                await fetch(`/projects/${projectId}/api/design-positions/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCSRFToken()
                    },
                    body: JSON.stringify({ positions: legacyPositions })
                });
            }
        } catch (error) {
            console.error('Error saving positions:', error);
        }
    }

    getCSRFToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
               document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1];
    }

    showLoading(show) {
        if (this.loadingState) {
            this.loadingState.style.display = show ? 'flex' : 'none';
        }
    }

    showEmpty(show) {
        if (this.emptyState) {
            this.emptyState.style.display = show ? 'flex' : 'none';
        }
        if (this.featuresContainer) {
            this.featuresContainer.style.display = show ? 'none' : 'block';
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }

    addEmptyScreen() {
        // Check if we have any features to add screens to
        if (this.features.size === 0) {
            this.showToast('No design features available. Generate a design preview first.', 'error');
            return;
        }

        // Get the first feature (or we could let user choose)
        const firstFeature = this.features.values().next().value;
        const featureId = firstFeature.feature_id;

        // Generate a unique placeholder ID
        const placeholderId = `placeholder-${Date.now()}`;

        // Calculate position for new screen - find the lowest point and add below
        const existingCards = this.featuresContainer?.querySelectorAll('.screen-card') || [];
        let maxY = 0;
        let maxRowX = 0;

        existingCards.forEach(card => {
            const cardY = parseInt(card.style.top) || 0;
            const cardX = parseInt(card.style.left) || 0;
            if (cardY > maxY) {
                maxY = cardY;
                maxRowX = cardX;
            } else if (cardY === maxY && cardX > maxRowX) {
                maxRowX = cardX;
            }
        });

        // Position: same row if space, otherwise new row below
        let x, y;
        const nextXInRow = maxRowX + this.cardWidth + this.cardGap;
        const maxCardsPerRow = 4;
        const rowWidth = maxCardsPerRow * (this.cardWidth + this.cardGap);

        if (existingCards.length === 0) {
            x = 50;
            y = 100;
        } else if (nextXInRow < rowWidth) {
            // Add to same row
            x = nextXInRow;
            y = maxY;
        } else {
            // Start new row below
            x = 50;
            y = maxY + this.cardHeight + this.cardGap;
        }

        // Create an empty placeholder card
        const card = this.createEmptyScreenCard(featureId, placeholderId, x, y);
        this.featuresContainer?.appendChild(card);

        // Add to canvas positions
        if (this.currentCanvas) {
            const key = `${featureId}_${placeholderId}`;
            if (!this.currentCanvas.feature_positions) {
                this.currentCanvas.feature_positions = {};
            }
            this.currentCanvas.feature_positions[key] = { x, y };
        }

        // Don't auto-open chat - user will click on the placeholder to open it
    }

    createEmptyScreenCard(featureId, placeholderId, x, y) {
        const card = document.createElement('div');
        card.className = 'screen-card empty-placeholder';
        card.id = `screen-${featureId}-${placeholderId}`;
        card.dataset.featureId = featureId;
        card.dataset.pageId = placeholderId;
        card.dataset.isPlaceholder = 'true';
        card.style.left = `${x}px`;
        card.style.top = `${y}px`;
        card.style.width = `${this.cardWidth}px`;

        card.innerHTML = `
            <div class="screen-thumbnail empty-thumbnail">
                <div class="empty-placeholder-content">
                    <i class="fas fa-plus-circle"></i>
                    <span>Click to describe</span>
                </div>
            </div>
            <div class="screen-info">
                <div class="screen-name-row">
                    <div class="screen-name">New Screen</div>
                    <button class="remove-placeholder-btn" title="Remove">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div class="screen-meta">
                    <span class="screen-type placeholder">placeholder</span>
                </div>
            </div>
        `;

        // Remove button
        const removeBtn = card.querySelector('.remove-placeholder-btn');
        removeBtn?.addEventListener('click', (e) => {
            e.stopPropagation();
            this.removePlaceholder(card, featureId, placeholderId);
        });

        // Click to open generation chat
        card.addEventListener('click', (e) => {
            if (e.target.closest('.remove-placeholder-btn')) return;
            this.openGenerationChat(featureId, placeholderId, card);
        });

        // Make it draggable
        card.addEventListener('mousedown', (e) => {
            if (e.target.closest('.remove-placeholder-btn')) return;

            e.stopPropagation();
            this.isDragging = true;
            this.hasDragged = false;
            this.dragTarget = card;
            this.dragStartPos = { x: e.clientX, y: e.clientY };
            card.classList.add('dragging');

            const rect = card.getBoundingClientRect();
            this.dragOffset = {
                x: (e.clientX - rect.left) / this.zoom,
                y: (e.clientY - rect.top) / this.zoom
            };
        });

        return card;
    }

    removePlaceholder(card, featureId, placeholderId) {
        card.remove();

        // Remove from canvas positions
        if (this.currentCanvas) {
            const key = `${featureId}_${placeholderId}`;
            delete this.currentCanvas.feature_positions[key];
            this.saveCanvasToServer();
        }

        // Close chat panel if open for this placeholder
        const panel = document.getElementById('design-ai-chat-panel');
        if (panel?.dataset.pageId === placeholderId) {
            panel.classList.remove('active');
        }
    }

    openGenerationChat(featureId, placeholderId, card) {
        // Get the feature for context
        const feature = this.features.get(featureId) || this.features.get(parseInt(featureId));

        // Create or show the AI chat panel
        let panel = document.getElementById('design-ai-chat-panel');

        if (!panel) {
            panel = document.createElement('div');
            panel.id = 'design-ai-chat-panel';
            panel.className = 'design-ai-chat-panel';
            panel.innerHTML = `
                <div class="ai-chat-header">
                    <div class="ai-chat-title">
                        <i class="fas fa-magic"></i>
                        <span>Create Screen</span>
                    </div>
                    <button class="ai-chat-close" id="ai-chat-close">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div class="ai-chat-screen-info" id="ai-chat-screen-info"></div>
                <div class="ai-chat-messages" id="ai-chat-messages">
                    <div class="ai-chat-welcome">
                        <i class="fas fa-sparkles"></i>
                        <p>Describe the screen you want to create</p>
                        <p class="ai-chat-hint">E.g., "A settings page with profile editing, password change, and notification preferences"</p>
                    </div>
                </div>
                <div class="ai-chat-input-container">
                    <textarea class="ai-chat-input" id="ai-chat-input" placeholder="Describe what you want on this screen..."></textarea>
                    <button class="ai-chat-send" id="ai-chat-send">
                        <i class="fas fa-paper-plane"></i>
                    </button>
                </div>
            `;
            document.body.appendChild(panel);

            // Bind close button
            document.getElementById('ai-chat-close')?.addEventListener('click', () => {
                panel.classList.remove('active');
            });

            // Bind send button
            document.getElementById('ai-chat-send')?.addEventListener('click', () => {
                this.generateScreenFromChat();
            });

            // Bind enter key
            document.getElementById('ai-chat-input')?.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.generateScreenFromChat();
                }
            });
        }

        // Update for generation mode vs edit mode
        const titleEl = panel.querySelector('.ai-chat-title span');
        if (titleEl) titleEl.textContent = 'Create Screen';

        // Update screen info
        const screenInfo = document.getElementById('ai-chat-screen-info');
        if (screenInfo) {
            screenInfo.innerHTML = `
                <span class="ai-screen-label">Feature:</span>
                <span class="ai-screen-name">${this.escapeHtml(feature?.feature_name || 'Unknown')}</span>
            `;
        }

        // Clear previous messages
        const messagesContainer = document.getElementById('ai-chat-messages');
        if (messagesContainer) {
            messagesContainer.innerHTML = `
                <div class="ai-chat-welcome">
                    <i class="fas fa-sparkles"></i>
                    <p>Describe the screen you want to create</p>
                    <p class="ai-chat-hint">E.g., "A settings page with profile editing, password change, and notification preferences"</p>
                </div>
            `;
        }

        // Store context
        panel.dataset.featureId = featureId;
        panel.dataset.pageId = placeholderId;
        panel.dataset.isGenerating = 'true';
        panel.dataset.cardElement = card.id;

        // Show panel
        panel.classList.add('active');

        // Focus input
        setTimeout(() => {
            document.getElementById('ai-chat-input')?.focus();
        }, 100);
    }

    async generateScreenFromChat() {
        const input = document.getElementById('ai-chat-input');
        const messagesContainer = document.getElementById('ai-chat-messages');
        const panel = document.getElementById('design-ai-chat-panel');
        const sendBtn = document.getElementById('ai-chat-send');
        const description = input?.value?.trim();

        if (!description) return;

        const featureId = panel?.dataset.featureId;
        const placeholderId = panel?.dataset.pageId;
        const isGenerating = panel?.dataset.isGenerating === 'true';
        const projectId = this.getProjectId();

        if (!featureId || !projectId) {
            this.showToast('Missing context for generation', 'error');
            return;
        }

        // If this is editing an existing screen, use the edit flow
        if (!isGenerating) {
            return this.sendAIChatMessage();
        }

        // Add user message
        const userMsg = document.createElement('div');
        userMsg.className = 'ai-chat-message user';
        userMsg.innerHTML = `<p>${this.escapeHtml(description)}</p>`;
        messagesContainer?.appendChild(userMsg);

        // Clear input and disable
        if (input) input.value = '';
        if (sendBtn) sendBtn.disabled = true;
        if (input) input.disabled = true;

        // Add loading message
        const loadingMsg = document.createElement('div');
        loadingMsg.className = 'ai-chat-message assistant loading';
        loadingMsg.innerHTML = `<p><i class="fas fa-circle-notch fa-spin"></i> Generating screen...</p>`;
        messagesContainer?.appendChild(loadingMsg);

        // Scroll to bottom
        if (messagesContainer) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }

        try {
            const response = await fetch(`/projects/${projectId}/api/generate-screen/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    feature_id: featureId,
                    description: description
                })
            });

            const data = await response.json();

            // Remove loading message
            loadingMsg.remove();

            if (data.success) {
                // Show success message
                const assistantMsg = document.createElement('div');
                assistantMsg.className = 'ai-chat-message assistant success';
                assistantMsg.innerHTML = `
                    <p><i class="fas fa-check-circle"></i> Created: ${this.escapeHtml(data.page?.page_name || 'New Screen')}</p>
                `;
                messagesContainer?.appendChild(assistantMsg);

                // Remove the placeholder card
                const placeholderCard = document.getElementById(`screen-${featureId}-${placeholderId}`);
                if (placeholderCard) {
                    placeholderCard.remove();
                }

                // Remove placeholder from canvas positions
                if (this.currentCanvas) {
                    const oldKey = `${featureId}_${placeholderId}`;
                    const oldPos = this.currentCanvas.feature_positions[oldKey];
                    delete this.currentCanvas.feature_positions[oldKey];

                    // Add the new screen with the same position
                    if (data.page) {
                        const newKey = `${featureId}_${data.page.page_id}`;
                        this.currentCanvas.feature_positions[newKey] = oldPos || { x: 50, y: 100 };
                    }
                    await this.saveCanvasToServer();
                }

                // Close panel after a moment
                setTimeout(() => {
                    panel.classList.remove('active');
                    this.loadFeatures();
                }, 1000);

            } else {
                const assistantMsg = document.createElement('div');
                assistantMsg.className = 'ai-chat-message assistant error';
                assistantMsg.innerHTML = `
                    <p><i class="fas fa-exclamation-circle"></i> ${this.escapeHtml(data.error || 'Failed to generate screen')}</p>
                `;
                messagesContainer?.appendChild(assistantMsg);

                // Re-enable input
                if (sendBtn) sendBtn.disabled = false;
                if (input) input.disabled = false;
            }

        } catch (error) {
            console.error('Error generating screen:', error);
            loadingMsg.remove();

            const errorMsg = document.createElement('div');
            errorMsg.className = 'ai-chat-message assistant error';
            errorMsg.innerHTML = `<p><i class="fas fa-exclamation-circle"></i> Connection error. Please try again.</p>`;
            messagesContainer?.appendChild(errorMsg);

            if (sendBtn) sendBtn.disabled = false;
            if (input) input.disabled = false;
        }

        // Scroll to bottom
        if (messagesContainer) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }

    refresh() {
        this.loadFeatures();
    }
}

// Initialize
let designCanvas = null;

function initDesignCanvas() {
    if (document.getElementById('design-canvas-container')) {
        designCanvas = new DesignCanvas('design-canvas-container');
    }
}

window.DesignCanvas = DesignCanvas;
window.initDesignCanvas = initDesignCanvas;
window.refreshDesignCanvas = () => designCanvas?.refresh();

// Add screen to current canvas (called when design agent generates a new screen)
window.addScreenToCurrentCanvas = (featureId, pageId) => {
    if (!designCanvas || !designCanvas.currentCanvas) return;

    const key = `${featureId}_${pageId}`;
    if (!designCanvas.currentCanvas.feature_positions) {
        designCanvas.currentCanvas.feature_positions = {};
    }

    // Add with default position
    designCanvas.currentCanvas.feature_positions[key] = { x: 50, y: 50 };

    // Save to server and refresh
    designCanvas.saveCanvasToServer();
    designCanvas.loadFeatures();
};

// Get current canvas ID
window.getCurrentDesignCanvasId = () => {
    return designCanvas?.currentCanvasId || window.currentDesignCanvasId || null;
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDesignCanvas);
} else {
    initDesignCanvas();
}
