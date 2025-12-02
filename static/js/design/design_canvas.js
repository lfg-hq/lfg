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

        this.init();
    }

    init() {
        this.bindEvents();
        this.loadFeatures();
    }

    bindEvents() {
        // Back button - switch to Docs tab
        document.getElementById('canvas-back')?.addEventListener('click', () => this.goBack());

        // Zoom controls - smaller increments
        document.getElementById('canvas-zoom-in')?.addEventListener('click', () => this.animateZoom(this.zoom + 0.1));
        document.getElementById('canvas-zoom-out')?.addEventListener('click', () => this.animateZoom(this.zoom - 0.1));
        document.getElementById('canvas-fit')?.addEventListener('click', () => this.fitToScreen());
        document.getElementById('canvas-refresh')?.addEventListener('click', () => this.loadFeatures());

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
        });
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
        this.showLoading(true);

        try {
            const projectId = this.getProjectId();
            if (!projectId) {
                this.showEmpty(true);
                return;
            }

            const response = await fetch(`/projects/${projectId}/api/design-features/`);
            if (!response.ok) throw new Error('Failed to load features');

            const data = await response.json();
            this.features.clear();

            if (!data.features || data.features.length === 0) {
                this.showEmpty(true);
                return;
            }

            data.features.forEach((feature) => {
                this.features.set(feature.feature_id, feature);
            });

            this.render();
            this.showEmpty(false);

        } catch (error) {
            console.error('Error loading features:', error);
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
        this.featuresContainer.innerHTML = '';
        this.pageElements.clear();

        let currentY = 50;

        this.features.forEach((feature) => {
            // Add feature section header
            const sectionHeader = document.createElement('div');
            sectionHeader.className = 'feature-section-header';
            sectionHeader.style.left = '50px';
            sectionHeader.style.top = `${currentY}px`;
            sectionHeader.innerHTML = `
                <span class="feature-section-title">${this.escapeHtml(feature.feature_name)}</span>
                <span class="feature-section-count">${feature.pages?.length || 0} screens</span>
            `;
            this.featuresContainer.appendChild(sectionHeader);

            currentY += 50;

            // Render all screens as individual cards in a grid
            const pages = feature.pages || [];
            const columns = Math.min(4, Math.max(3, Math.ceil(Math.sqrt(pages.length))));

            pages.forEach((page, index) => {
                const col = index % columns;
                const row = Math.floor(index / columns);
                const x = 50 + col * (this.cardWidth + this.cardGap);
                const y = currentY + row * (this.cardHeight + this.cardGap);

                const card = this.createScreenCard(feature, page, x, y);
                this.featuresContainer.appendChild(card);

                const pageKey = page.page_id;
                this.pageElements.set(pageKey, card);
            });

            // Move to next section
            const rows = Math.ceil(pages.length / columns);
            currentY += rows * (this.cardHeight + this.cardGap) + 80;
        });

        // Fit to screen after render
        requestAnimationFrame(() => {
            setTimeout(() => this.fitToScreen(), 50);
        });
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
            <div class="screen-info">
                <div class="screen-name-row">
                    <div class="screen-name">${this.escapeHtml(page.page_name)}</div>
                    <button class="ai-edit-btn" title="Edit with AI">
                        <i class="fas fa-magic"></i>
                    </button>
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

        // Drag to reposition
        card.addEventListener('mousedown', (e) => {
            // Don't start drag if clicking AI button
            if (e.target.closest('.ai-edit-btn')) return;

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

        // Click to preview - only if not dragged
        card.addEventListener('click', (e) => {
            if (e.target.closest('.ai-edit-btn')) return;
            if (!this.hasDragged) {
                this.openPreview(feature, page);
            }
            this.hasDragged = false;
        });

        return card;
    }

    createThumbnail(feature, page) {
        const cssContent = feature.css_style || '';
        const htmlContent = page.html_content || '';

        if (!htmlContent) {
            return `<div class="empty-thumbnail"><i class="fas fa-desktop"></i></div>`;
        }

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
            <body>${htmlContent}</body>
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

        // Show panel
        panel.classList.add('active');

        // Focus input
        setTimeout(() => {
            document.getElementById('ai-chat-input')?.focus();
        }, 100);
    }

    sendAIChatMessage() {
        const input = document.getElementById('ai-chat-input');
        const messagesContainer = document.getElementById('ai-chat-messages');
        const message = input?.value?.trim();

        if (!message) return;

        // Add user message
        const userMsg = document.createElement('div');
        userMsg.className = 'ai-chat-message user';
        userMsg.innerHTML = `<p>${this.escapeHtml(message)}</p>`;
        messagesContainer?.appendChild(userMsg);

        // Clear input
        if (input) input.value = '';

        // Add loading message
        const loadingMsg = document.createElement('div');
        loadingMsg.className = 'ai-chat-message assistant loading';
        loadingMsg.innerHTML = `<p><i class="fas fa-circle-notch fa-spin"></i> Thinking...</p>`;
        messagesContainer?.appendChild(loadingMsg);

        // Scroll to bottom
        if (messagesContainer) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }

        // TODO: Send to AI backend
        // For now, show a placeholder response
        setTimeout(() => {
            loadingMsg.remove();
            const assistantMsg = document.createElement('div');
            assistantMsg.className = 'ai-chat-message assistant';
            assistantMsg.innerHTML = `<p>This feature is coming soon! You'll be able to edit screens with natural language commands.</p>`;
            messagesContainer?.appendChild(assistantMsg);
            if (messagesContainer) {
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }
        }, 1500);
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
        const htmlContent = page.html_content || '';

        const fullHtml = `
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>${cssContent}</style>
            </head>
            <body>${htmlContent}</body>
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
        const htmlContent = page.html_content || '';

        const fullHtml = `
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>${cssContent}</style>
            </head>
            <body>${htmlContent}</body>
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
        const positions = {};

        this.pageElements.forEach((el, pageId) => {
            positions[pageId] = {
                x: parseFloat(el.style.left) || 0,
                y: parseFloat(el.style.top) || 0
            };
        });

        try {
            const projectId = this.getProjectId();
            if (!projectId) return;

            await fetch(`/projects/${projectId}/api/design-positions/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({ positions })
            });
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

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDesignCanvas);
} else {
    initDesignCanvas();
}
