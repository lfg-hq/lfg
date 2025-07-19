document.addEventListener('DOMContentLoaded', function() {
    // Initialize custom dropdowns
    initializeCustomDropdowns();
    // Initialize settings button
    initializeSettingsButton();
});

function initializeCustomDropdowns() {
    const dropdowns = document.querySelectorAll('.custom-dropdown');
    
    dropdowns.forEach(dropdown => {
        const button = dropdown.querySelector('.custom-dropdown-button');
        const menu = dropdown.querySelector('.custom-dropdown-menu');
        const items = menu.querySelectorAll('.custom-dropdown-item');
        const textSpan = button.querySelector('span');
        
        // Toggle dropdown on button click
        button.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = dropdown.classList.contains('open');
            
            // Close all other dropdowns
            document.querySelectorAll('.custom-dropdown.open').forEach(d => {
                if (d !== dropdown) {
                    d.classList.remove('open');
                    d.querySelector('.custom-dropdown-button').classList.remove('active');
                }
            });
            
            // Toggle current dropdown
            dropdown.classList.toggle('open');
            button.classList.toggle('active');
        });
        
        // Handle item selection
        items.forEach(item => {
            // Skip group labels
            if (item.classList.contains('dropdown-group-label')) {
                return;
            }
            
            item.addEventListener('click', (e) => {
                e.stopPropagation();
                
                // Remove selected class from all items
                items.forEach(i => i.classList.remove('selected'));
                
                // Add selected class to clicked item
                item.classList.add('selected');
                
                // Update button text
                textSpan.textContent = item.textContent;
                
                // Close dropdown
                dropdown.classList.remove('open');
                button.classList.remove('active');
                
                // Trigger change event for compatibility with existing code
                const dropdownId = button.id;
                const value = item.getAttribute('data-value');
                
                // Create and dispatch custom event
                const event = new CustomEvent('dropdownChange', {
                    detail: { value: value, text: item.textContent }
                });
                button.dispatchEvent(event);
                
                // For role dropdown
                if (dropdownId === 'role-dropdown') {
                    // Update the global variable if it exists
                    if (typeof window.currentRole !== 'undefined') {
                        window.currentRole = value;
                    }
                    // Update status display
                    const currentRoleSpan = document.getElementById('current-role');
                    if (currentRoleSpan) {
                        currentRoleSpan.textContent = item.textContent;
                    }
                    // Trigger role change event
                    if (typeof handleRoleChange === 'function') {
                        handleRoleChange(value);
                    }
                }
                
                // For model dropdown
                if (dropdownId === 'model-dropdown') {
                    // Update the global variable if it exists
                    if (typeof window.currentModel !== 'undefined') {
                        window.currentModel = value;
                    }
                    // Update status display
                    const currentModelSpan = document.getElementById('current-model');
                    if (currentModelSpan) {
                        currentModelSpan.textContent = item.textContent;
                    }
                    // Trigger model change event
                    if (typeof handleModelChange === 'function') {
                        handleModelChange(value);
                    }
                }
            });
        });
    });
    
    // Close dropdowns when clicking outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.custom-dropdown')) {
            document.querySelectorAll('.custom-dropdown.open').forEach(dropdown => {
                dropdown.classList.remove('open');
                dropdown.querySelector('.custom-dropdown-button').classList.remove('active');
            });
        }
    });
}

// Helper function to get selected value
function getCustomDropdownValue(dropdownId) {
    const dropdown = document.getElementById(dropdownId + '-wrapper');
    if (dropdown) {
        const selectedItem = dropdown.querySelector('.custom-dropdown-item.selected');
        return selectedItem ? selectedItem.getAttribute('data-value') : null;
    }
    return null;
}

// Helper function to set dropdown value
function setCustomDropdownValue(dropdownId, value) {
    const dropdown = document.getElementById(dropdownId + '-wrapper');
    if (dropdown) {
        const items = dropdown.querySelectorAll('.custom-dropdown-item');
        const button = dropdown.querySelector('.custom-dropdown-button');
        const textSpan = button.querySelector('span');
        
        items.forEach(item => {
            if (item.getAttribute('data-value') === value) {
                // Remove selected class from all items
                items.forEach(i => i.classList.remove('selected'));
                
                // Add selected class to matching item
                item.classList.add('selected');
                
                // Update button text
                textSpan.textContent = item.textContent;
                
                // Trigger change event
                const event = new CustomEvent('dropdownChange', {
                    detail: { value: value, text: item.textContent }
                });
                button.dispatchEvent(event);
            }
        });
    }
}

// Export functions for global use
window.getCustomDropdownValue = getCustomDropdownValue;
window.setCustomDropdownValue = setCustomDropdownValue;

// Global functions to handle dropdown changes
window.handleRoleChange = function(value) {
    console.log('Role changed to:', value);
    // Additional role change logic can be added here
};

window.handleModelChange = function(value) {
    console.log('Model changed to:', value);
    // Additional model change logic can be added here
};

// Initialize settings button functionality
function initializeSettingsButton() {
    const settingsBtn = document.getElementById('settings-btn');
    const settingsDropdown = document.getElementById('settings-dropdown');
    
    // Submenus
    const roleSubmenu = document.getElementById('role-submenu');
    const modelSubmenu = document.getElementById('model-submenu');
    
    // Status display
    const currentRoleSpan = document.getElementById('current-role');
    const currentModelSpan = document.getElementById('current-model');
    const currentRoleLeftSpan = document.getElementById('current-role-left');
    const currentModelLeftSpan = document.getElementById('current-model-left');
    
    // Status click buttons
    const roleStatusBtn = document.getElementById('role-status-btn');
    const modelStatusBtn = document.getElementById('model-status-btn');
    
    if (!settingsBtn || !settingsDropdown) return;
    
    let closeTimeout;
    let clickedOpen = false;
    
    // Show dropdown on hover for settings button only
    settingsBtn.addEventListener('mouseenter', () => {
        if (!clickedOpen) {
            clearTimeout(closeTimeout);
            settingsDropdown.classList.add('open');
        }
    });
    
    // Keep dropdown open when hovering over it
    settingsDropdown.addEventListener('mouseenter', () => {
        clearTimeout(closeTimeout);
    });
    
    // Hide dropdown when mouse leaves both button and dropdown
    settingsBtn.addEventListener('mouseleave', () => {
        if (!clickedOpen) {
            closeTimeout = setTimeout(() => {
                if (!settingsDropdown.matches(':hover')) {
                    settingsDropdown.classList.remove('open');
                }
            }, 200);
        }
    });
    
    settingsDropdown.addEventListener('mouseleave', () => {
        if (!clickedOpen) {
            closeTimeout = setTimeout(() => {
                settingsDropdown.classList.remove('open');
            }, 200);
        }
    });
    
    // Handle clicking on role status
    if (roleStatusBtn) {
        roleStatusBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            e.preventDefault();
            clickedOpen = true;
            settingsDropdown.classList.add('open');
            // Show role submenu directly
            setTimeout(() => {
                const roleMenuItem = document.querySelector('[data-submenu="role"]');
                if (roleMenuItem) {
                    roleMenuItem.dispatchEvent(new MouseEvent('mouseenter'));
                }
            }, 50);
        });
    }
    
    // Handle clicking on model status
    if (modelStatusBtn) {
        modelStatusBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            e.preventDefault();
            clickedOpen = true;
            settingsDropdown.classList.add('open');
            // Show model submenu directly
            setTimeout(() => {
                const modelMenuItem = document.querySelector('[data-submenu="model"]');
                if (modelMenuItem) {
                    modelMenuItem.dispatchEvent(new MouseEvent('mouseenter'));
                }
            }, 50);
        });
    }
    
    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('#settings-dropdown') && !e.target.closest('#settings-btn') && 
            !e.target.closest('#role-status-btn') && !e.target.closest('#model-status-btn')) {
            settingsDropdown.classList.remove('open');
            clickedOpen = false;
        }
    });
    
    // Handle role option selection
    roleSubmenu.querySelectorAll('.submenu-option').forEach(option => {
        option.addEventListener('click', (e) => {
            e.stopPropagation();
            
            // Update selection
            roleSubmenu.querySelectorAll('.submenu-option').forEach(opt => opt.classList.remove('selected'));
            option.classList.add('selected');
            
            // Update display
            const value = option.getAttribute('data-value');
            const text = option.querySelector('span').textContent;
            
            // Update status display
            if (currentRoleSpan) {
                currentRoleSpan.textContent = text;
            }
            if (currentRoleLeftSpan) {
                currentRoleLeftSpan.textContent = text;
            }
            
            // Update global variable
            if (typeof window.currentRole !== 'undefined') {
                window.currentRole = value;
            }
            
            // Trigger role change event
            if (typeof handleRoleChange === 'function') {
                handleRoleChange(value);
            }
            
            // Close dropdown
            settingsDropdown.classList.remove('open');
            clickedOpen = false;
        });
    });
    
    // Handle model option selection
    modelSubmenu.querySelectorAll('.submenu-option').forEach(option => {
        option.addEventListener('click', (e) => {
            e.stopPropagation();
            
            // Update selection
            modelSubmenu.querySelectorAll('.submenu-option').forEach(opt => opt.classList.remove('selected'));
            option.classList.add('selected');
            
            // Update display
            const value = option.getAttribute('data-value');
            const text = option.querySelector('span').textContent;
            
            // Update status display
            if (currentModelSpan) {
                currentModelSpan.textContent = text;
            }
            if (currentModelLeftSpan) {
                currentModelLeftSpan.textContent = text;
            }
            
            // Update global variable
            if (typeof window.currentModel !== 'undefined') {
                window.currentModel = value;
            }
            
            // Trigger model change event
            if (typeof handleModelChange === 'function') {
                handleModelChange(value);
            }
            
            // Close dropdown
            settingsDropdown.classList.remove('open');
            clickedOpen = false;
        });
    });
}

