// Mobile menu handler for chat input actions
document.addEventListener('DOMContentLoaded', function() {
    const mobileMenuBtn = document.getElementById('mobile-menu-btn');
    const mobileMenuDropdown = document.getElementById('mobile-menu-dropdown');
    const mobileRoleSelect = document.getElementById('mobile-role-select');
    const mobileModelSelect = document.getElementById('mobile-model-select');
    const mobileTurboToggle = document.getElementById('mobile-turbo-toggle');
    
    // Desktop elements
    const turboToggle = document.getElementById('turbo-mode-toggle');
    const roleDropdownText = document.getElementById('role-dropdown-text');
    const modelDropdownText = document.getElementById('model-dropdown-text');
    
    // Toggle mobile menu
    if (mobileMenuBtn) {
        mobileMenuBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            mobileMenuDropdown.classList.toggle('show');
        });
    }
    
    // Close menu when clicking outside
    document.addEventListener('click', function(e) {
        if (!e.target.closest('#mobile-menu-btn') && !e.target.closest('#mobile-menu-dropdown')) {
            mobileMenuDropdown.classList.remove('show');
        }
    });
    
    // Sync turbo mode between desktop and mobile
    if (mobileTurboToggle && turboToggle) {
        mobileTurboToggle.addEventListener('change', function() {
            turboToggle.checked = mobileTurboToggle.checked;
            // Trigger change event on desktop toggle
            turboToggle.dispatchEvent(new Event('change'));
        });
        
        // Sync from desktop to mobile
        turboToggle.addEventListener('change', function() {
            mobileTurboToggle.checked = turboToggle.checked;
        });
        
        // Set initial state
        mobileTurboToggle.checked = turboToggle.checked;
    }
    
    // Sync role selection
    if (mobileRoleSelect) {
        mobileRoleSelect.addEventListener('change', function() {
            // Update desktop dropdown text
            if (roleDropdownText) {
                roleDropdownText.textContent = mobileRoleSelect.options[mobileRoleSelect.selectedIndex].text;
            }
            
            // Trigger role change event
            window.dispatchEvent(new CustomEvent('roleChanged', { 
                detail: { 
                    value: mobileRoleSelect.value,
                    text: mobileRoleSelect.options[mobileRoleSelect.selectedIndex].text
                } 
            }));
        });
        
        // Listen for desktop role changes
        window.addEventListener('roleChanged', function(e) {
            if (e.detail && e.detail.value) {
                mobileRoleSelect.value = e.detail.value;
            }
        });
    }
    
    // Sync model selection
    if (mobileModelSelect) {
        mobileModelSelect.addEventListener('change', function() {
            // Update desktop dropdown text
            if (modelDropdownText) {
                modelDropdownText.textContent = mobileModelSelect.options[mobileModelSelect.selectedIndex].text;
            }
            
            // Trigger model change event
            window.dispatchEvent(new CustomEvent('modelChanged', { 
                detail: { 
                    value: mobileModelSelect.value,
                    text: mobileModelSelect.options[mobileModelSelect.selectedIndex].text
                } 
            }));
        });
        
        // Listen for desktop model changes
        window.addEventListener('modelChanged', function(e) {
            if (e.detail && e.detail.value) {
                mobileModelSelect.value = e.detail.value;
            }
        });
    }
    
    // Set initial values
    if (roleDropdownText && mobileRoleSelect) {
        // Find the option that matches the current text
        for (let option of mobileRoleSelect.options) {
            if (option.text === roleDropdownText.textContent) {
                mobileRoleSelect.value = option.value;
                break;
            }
        }
    }
    
    if (modelDropdownText && mobileModelSelect) {
        // Find the option that matches the current text
        for (let option of mobileModelSelect.options) {
            if (option.text === modelDropdownText.textContent) {
                mobileModelSelect.value = option.value;
                break;
            }
        }
    }
});