document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar');
    const appContainer = document.querySelector('.app-container');
    const sidebarOverlay = document.getElementById('sidebar-overlay');
    const minimizeBtn = document.getElementById('minimize-btn');
    const expandBtn = document.getElementById('expand-btn');
    
    // Load saved state from localStorage
    const savedState = localStorage.getItem('sidebarCollapsed');
    const isInitiallyCollapsed = savedState === 'true' || window.innerWidth <= 768;
    
    // Initialize sidebar state
    if (isInitiallyCollapsed) {
        sidebar.classList.add('collapsed');
        appContainer.classList.add('sidebar-collapsed');
    }
    
    // Toggle sidebar visibility
    function toggleSidebar() {
        const isCollapsed = sidebar.classList.contains('collapsed');
        
        if (isCollapsed) {
            sidebar.classList.remove('collapsed');
            appContainer.classList.remove('sidebar-collapsed');
            if (window.innerWidth <= 768) {
                appContainer.classList.add('sidebar-expanded');
            }
            localStorage.setItem('sidebarCollapsed', 'false');
        } else {
            sidebar.classList.add('collapsed');
            appContainer.classList.add('sidebar-collapsed');
            appContainer.classList.remove('sidebar-expanded');
            localStorage.setItem('sidebarCollapsed', 'true');
        }
    }
    
    // Minimize button click handler
    if (minimizeBtn) {
        minimizeBtn.addEventListener('click', toggleSidebar);
    }
    
    // Expand button click handler
    if (expandBtn) {
        expandBtn.addEventListener('click', toggleSidebar);
    }
    
    // Handle overlay click on mobile
    if (sidebarOverlay) {
        sidebarOverlay.addEventListener('click', () => {
            if (window.innerWidth <= 768) {
                sidebar.classList.add('collapsed');
                appContainer.classList.add('sidebar-collapsed');
                appContainer.classList.remove('sidebar-expanded');
            }
        });
    }
    
    // Handle window resize
    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            if (window.innerWidth <= 768 && !sidebar.classList.contains('collapsed')) {
                sidebar.classList.add('collapsed');
                appContainer.classList.add('sidebar-collapsed');
                appContainer.classList.remove('sidebar-expanded');
            }
        }, 250);
    });
    
    // Keyboard shortcut (Ctrl/Cmd + B to toggle sidebar)
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
            e.preventDefault();
            toggleSidebar();
        }
    });
});