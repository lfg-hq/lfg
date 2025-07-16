document.addEventListener('DOMContentLoaded', function() {
    // Initialize custom dropdowns
    initializeCustomDropdowns();
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