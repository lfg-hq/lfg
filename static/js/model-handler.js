class ModelHandler {
    constructor() {
        this.modelDropdown = document.getElementById('model-dropdown');
        this.modelSubmenu = document.getElementById('model-submenu');
        this.init();
    }

    init() {
        // First try to load from page data
        const modelKeyFromPage = document.body.dataset.modelKey;
        if (modelKeyFromPage) {
            this.setDropdownValue(modelKeyFromPage);
            console.log('Initialized model from page data:', modelKeyFromPage);
        }
        
        this.setupEventListeners();
    }

    setupEventListeners() {
        // Listen to left menu submenu options
        if (this.modelSubmenu) {
            const modelOptions = this.modelSubmenu.querySelectorAll('.submenu-option');
            modelOptions.forEach(option => {
                option.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const value = option.getAttribute('data-value');
                    this.updateModel(value);
                    
                    // Update UI to show selected state
                    modelOptions.forEach(opt => opt.classList.remove('selected'));
                    option.classList.add('selected');
                    
                    // Update the status display
                    const modelText = option.querySelector('span').textContent;
                    const currentModelLeft = document.getElementById('current-model-left');
                    if (currentModelLeft) {
                        currentModelLeft.textContent = modelText;
                    }
                });
            });
        }
        
        // Keep old dropdown listener if it exists
        if (this.modelDropdown) {
            // For custom dropdown
            if (this.modelDropdown.classList.contains('custom-dropdown-button')) {
                this.modelDropdown.addEventListener('dropdownChange', (e) => {
                    this.updateModel(e.detail.value);
                });
            } else if (this.modelDropdown.tagName === 'SELECT') {
                // Fallback for old select dropdown
                this.modelDropdown.addEventListener('change', (e) => {
                    this.updateModel(e.target.value);
                });
            }
        }
    }


    async updateModel(selectedModel) {
        try {
            const response = await fetch('/api/user/model-selection/', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    selected_model: selectedModel
                })
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    console.log('Model updated successfully:', data.message);
                    // this.showSuccessMessage(data.message);
                } else {
                    console.error('Failed to update model:', data.error);
                    this.showErrorMessage(data.error);
                }
            } else {
                const errorData = await response.json();
                console.error('Failed to update model:', errorData.error);
                this.showErrorMessage(errorData.error || 'Failed to update model');
            }
        } catch (error) {
            console.error('Error updating model:', error);
            this.showErrorMessage('Network error occurred while updating model');
        }
    }

    setDropdownValue(selectedModel) {
        // Update left menu submenu
        if (this.modelSubmenu) {
            const modelOptions = this.modelSubmenu.querySelectorAll('.submenu-option');
            modelOptions.forEach(option => {
                if (option.getAttribute('data-value') === selectedModel) {
                    option.classList.add('selected');
                    // Update the status display
                    const modelText = option.querySelector('span').textContent;
                    const currentModelLeft = document.getElementById('current-model-left');
                    if (currentModelLeft) {
                        currentModelLeft.textContent = modelText;
                    }
                } else {
                    option.classList.remove('selected');
                }
            });
        }
        
        // For custom dropdown (if it still exists)
        if (typeof setCustomDropdownValue === 'function' && this.modelDropdown) {
            setCustomDropdownValue('model-dropdown', selectedModel);
        } else if (this.modelDropdown && this.modelDropdown.tagName === 'SELECT') {
            // Fallback for old select dropdown
            // Check if the model exists in the dropdown options
            const optionExists = Array.from(this.modelDropdown.options).some(option => 
                option.value === selectedModel
            );
            
            if (optionExists) {
                this.modelDropdown.value = selectedModel;
            } else {
                console.warn('Model not found in dropdown options:', selectedModel);
                // Default to first option if selected model not found
                this.modelDropdown.value = this.modelDropdown.options[0].value;
            }
        }
    }

    showSuccessMessage(message) {
        // Create a temporary success notification
        const notification = document.createElement('div');
        notification.className = 'model-notification success';
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #4CAF50;
            color: white;
            padding: 12px 20px;
            border-radius: 4px;
            z-index: 1000;
            font-size: 14px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        `;

        document.body.appendChild(notification);

        // Remove after 3 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 3000);
    }

    showErrorMessage(message) {
        // Create a temporary error notification
        const notification = document.createElement('div');
        notification.className = 'model-notification error';
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

// Initialize model handler when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    if (document.body.dataset.userAuthenticated === 'true') {
        new ModelHandler();
    }
}); 