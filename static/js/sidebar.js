document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar');
    const appContainer = document.querySelector('.app-container');
    const minimizeBtn = document.getElementById('minimize-btn');
    const userInfo = document.getElementById('user-info');
    const userInfoButton = document.getElementById('user-info-button');
    const userDropdown = document.getElementById('user-dropdown');
    
    // Load saved state from localStorage
    const savedState = localStorage.getItem('sidebarMinimized');
    const isInitiallyMinimized = savedState === 'true';
    
    // Initialize sidebar state
    if (isInitiallyMinimized) {
        sidebar.classList.add('minimized');
        appContainer.classList.add('sidebar-minimized');
    }
    
    // Toggle sidebar minimized state
    function toggleMinimized() {
        const isMinimized = sidebar.classList.contains('minimized');
        
        if (isMinimized) {
            sidebar.classList.remove('minimized');
            appContainer.classList.remove('sidebar-minimized');
            localStorage.setItem('sidebarMinimized', 'false');
        } else {
            sidebar.classList.add('minimized');
            appContainer.classList.add('sidebar-minimized');
            localStorage.setItem('sidebarMinimized', 'true');
            // Close dropdown when minimizing
            userInfo.classList.remove('open');
        }
    }
    
    // Minimize button click handler
    if (minimizeBtn) {
        minimizeBtn.addEventListener('click', toggleMinimized);
    }
    
    // Logo click handler in minimized state
    const logoSection = document.querySelector('.logo-section');
    if (logoSection) {
        logoSection.addEventListener('click', () => {
            if (sidebar.classList.contains('minimized')) {
                toggleMinimized();
            }
        });
    }
    
    // User dropdown toggle
    if (userInfoButton) {
        userInfoButton.addEventListener('click', (e) => {
            e.stopPropagation();
            userInfo.classList.toggle('open');
        });
    }
    
    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
        if (!userInfo.contains(e.target)) {
            userInfo.classList.remove('open');
        }
    });
    
    // Prevent dropdown from closing when clicking inside it
    if (userDropdown) {
        userDropdown.addEventListener('click', (e) => {
            e.stopPropagation();
        });
    }
    
    // Handle window resize
    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            if (window.innerWidth <= 768) {
                sidebar.classList.add('minimized');
                appContainer.classList.add('sidebar-minimized');
            }
        }, 250);
    });
    
    // Keyboard shortcut (Ctrl/Cmd + B to toggle minimized)
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
            e.preventDefault();
            toggleMinimized();
        }
    });
    
    // Handle integrations button
    const integrationsBtn = document.getElementById('integrations-btn');
    if (integrationsBtn) {
        integrationsBtn.addEventListener('click', (e) => {
            e.preventDefault();
            // You can add integration modal or redirect here
            alert('Integrations page coming soon!');
        });
    }
});