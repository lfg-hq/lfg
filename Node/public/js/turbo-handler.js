class TurboHandler {
    constructor() {
        this.turboToggle = document.getElementById('turbo-mode-toggle');
        this.init();
    }

    init() {
        // First try to load from page data
        const turboModeFromPage = document.body.dataset.turboMode === 'true';
        if (this.turboToggle) {
            this.turboToggle.checked = turboModeFromPage;
            console.log('Initialized turbo mode from page data:', turboModeFromPage);
        }
        
        // Setup event listeners after initialization
        this.setupEventListeners();
    }

    setupEventListeners() {
        if (this.turboToggle) {
            this.turboToggle.addEventListener('change', (e) => {
                this.updateTurboMode(e.target.checked);
            });
        }
    }


    async updateTurboMode(turboMode) {
        try {
            const response = await fetch('/api/user/turbo-mode/', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    turbo_mode: turboMode
                })
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    console.log('Turbo mode updated successfully:', data.message);
                } else {
                    console.error('Failed to update turbo mode:', data.error);
                    this.showErrorMessage(data.error);
                    // Revert the toggle state on error
                    this.turboToggle.checked = !turboMode;
                }
            } else {
                const errorData = await response.json();
                console.error('Failed to update turbo mode:', errorData.error);
                this.showErrorMessage(errorData.error || 'Failed to update turbo mode');
                // Revert the toggle state on error
                this.turboToggle.checked = !turboMode;
            }
        } catch (error) {
            console.error('Error updating turbo mode:', error);
            this.showErrorMessage('Network error occurred while updating turbo mode');
            // Revert the toggle state on error
            this.turboToggle.checked = !turboMode;
        }
    }

    showErrorMessage(message) {
        // Create a temporary error notification
        const notification = document.createElement('div');
        notification.className = 'turbo-notification error';
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #f44336;
            color: white;
            padding: 12px 20px;
            border-radius: 4px;
            z-index: 1000;
            font-size: 14px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        `;

        document.body.appendChild(notification);

        // Remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 5000);
    }

    getCSRFToken() {
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
        return csrfToken ? csrfToken.value : '';
    }
}

// Initialize turbo handler when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    if (document.body.dataset.userAuthenticated === 'true') {
        new TurboHandler();
    }
});