// This script handles fetching the user_role from the database 
// and updates the dropdown accordingly
(function() {
    // Function to extract user_role from conversation data and set the dropdown
    function updateRoleDropdownFromDatabase(conversationData) {
        if (!conversationData || !conversationData.messages || !conversationData.messages.length) {
            console.log('No messages found in conversation data');
            return;
        }
        
        // Find the most recent user role from messages (search in reverse)
        let lastUserRole = null;
        for (let i = conversationData.messages.length - 1; i >= 0; i--) {
            const message = conversationData.messages[i];
            if (message.role === 'user' && message.user_role && message.user_role !== 'default') {
                lastUserRole = message.user_role;
                console.log('Found last user role in conversation:', lastUserRole);
                break;
            }
        }
        
        // Set the dropdown value based on the last user role
        if (lastUserRole) {
            // Use custom dropdown helper function
            if (typeof setCustomDropdownValue === 'function') {
                setCustomDropdownValue('role-dropdown', lastUserRole);
                console.log('Set role dropdown to last used role from DB:', lastUserRole);
            } else {
                // Fallback for old dropdown
                const roleDropdown = document.getElementById('role-dropdown');
                if (roleDropdown && roleDropdown.tagName === 'SELECT') {
                    // Check if this option exists in the dropdown
                    const optionExists = Array.from(roleDropdown.options).some(option => 
                        option.value === lastUserRole
                    );
                    
                    if (optionExists) {
                        roleDropdown.value = lastUserRole;
                        console.log('Set role dropdown to last used role from DB:', lastUserRole);
                    } else {
                        console.log('Role not available in dropdown:', lastUserRole);
                    }
                }
            }
        }
    }
    
    // Override the original loadConversation function to set user role
    document.addEventListener('DOMContentLoaded', function() {
        // Wait until the chat.js script has loaded and defined the function
        setTimeout(() => {
            if (typeof loadConversation === 'function') {
                const originalLoadConversation = loadConversation;
                
                // Override the loadConversation function
                window.loadConversation = function(conversationId) {
                    // Call the original function first
                    const result = originalLoadConversation.apply(this, arguments);
                    
                    // Then fetch the conversation data again to get the user_role
                    fetch(`/api/conversations/${conversationId}/`)
                        .then(response => response.json())
                        .then(data => {
                            updateRoleDropdownFromDatabase(data);
                        })
                        .catch(error => {
                            console.error('Error fetching conversation for role update:', error);
                        });
                    
                    return result;
                };
                
                console.log('Successfully overrode loadConversation function');
            } else {
                console.warn('loadConversation function not found, cannot override');
            }
        }, 500);
        
        // Also use localStorage for backup persistence between refreshes
        const roleDropdown = document.getElementById('role-dropdown');
        if (roleDropdown) {
            // For custom dropdown
            if (roleDropdown.classList.contains('custom-dropdown-button')) {
                // Listen for custom dropdown change event
                roleDropdown.addEventListener('dropdownChange', function(e) {
                    localStorage.setItem('user_role', e.detail.value);
                    console.log('Saved role to localStorage:', e.detail.value);
                });
                
                // Load from localStorage as a fallback
                const savedRole = localStorage.getItem('user_role');
                if (savedRole && typeof setCustomDropdownValue === 'function') {
                    setCustomDropdownValue('role-dropdown', savedRole);
                    console.log('Loaded saved role from localStorage:', savedRole);
                }
            } else if (roleDropdown.tagName === 'SELECT') {
                // Fallback for old select dropdown
                roleDropdown.addEventListener('change', function() {
                    localStorage.setItem('user_role', this.value);
                    console.log('Saved role to localStorage:', this.value);
                });
                
                const savedRole = localStorage.getItem('user_role');
                if (savedRole) {
                    const optionExists = Array.from(roleDropdown.options).some(option => 
                        option.value === savedRole
                    );
                    
                    if (optionExists) {
                        roleDropdown.value = savedRole;
                        console.log('Loaded saved role from localStorage:', savedRole);
                    }
                }
            }
        }
    });
})();

class RoleHandler {
    constructor() {
        this.roleDropdown = document.getElementById('role-dropdown');
        this.init();
    }

    init() {
        this.loadCurrentRole();
        this.setupEventListeners();
    }

    setupEventListeners() {
        if (this.roleDropdown) {
            // For custom dropdown
            if (this.roleDropdown.classList.contains('custom-dropdown-button')) {
                this.roleDropdown.addEventListener('dropdownChange', (e) => {
                    this.updateRole(e.detail.value);
                });
            } else if (this.roleDropdown.tagName === 'SELECT') {
                // Fallback for old select dropdown
                this.roleDropdown.addEventListener('change', (e) => {
                    this.updateRole(e.target.value);
                });
            }
        }
    }

    async loadCurrentRole() {
        try {
            const response = await fetch('/api/user/agent-role/', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                }
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success && data.agent_role) {
                    this.setDropdownValue(data.agent_role.name);
                    console.log('Loaded current role:', data.agent_role.display_name);
                }
            } else {
                console.error('Failed to load current role');
            }
        } catch (error) {
            console.error('Error loading current role:', error);
        }
    }

    async updateRole(roleName) {
        try {
            const response = await fetch('/api/user/agent-role/', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    name: roleName
                })
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    console.log('Role updated successfully:', data.message);
                    // this.showSuccessMessage(data.message);
                } else {
                    console.error('Failed to update role:', data.error);
                    this.showErrorMessage(data.error);
                }
            } else {
                const errorData = await response.json();
                console.error('Failed to update role:', errorData.error);
                this.showErrorMessage(errorData.error || 'Failed to update role');
            }
        } catch (error) {
            console.error('Error updating role:', error);
            this.showErrorMessage('Network error occurred while updating role');
        }
    }

    setDropdownValue(roleName) {
        // Map backend role names to dropdown values
        const roleMapping = {
            'developer': 'developer',
            'product_analyst': 'product_analyst',
            'designer': 'designer',
            'default': 'product_analyst' // Changed default to product_analyst
        };

        const dropdownValue = roleMapping[roleName] || 'product_analyst';
        
        // For custom dropdown
        if (typeof setCustomDropdownValue === 'function') {
            setCustomDropdownValue('role-dropdown', dropdownValue);
        } else if (this.roleDropdown && this.roleDropdown.tagName === 'SELECT') {
            // Fallback for old select dropdown
            this.roleDropdown.value = dropdownValue;
        }
    }

    showSuccessMessage(message) {
        // Create a temporary success notification
        const notification = document.createElement('div');
        notification.className = 'role-notification success';
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
        notification.className = 'role-notification error';
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

// Initialize role handler when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    if (document.body.dataset.userAuthenticated === 'true') {
        new RoleHandler();
    }
}); 