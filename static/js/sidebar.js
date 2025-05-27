document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar');
    const appContainer = document.querySelector('.app-container');
    const sidebarOverlay = document.getElementById('sidebar-overlay');
    
    // Function to determine if mouse is in the left zone for appearance
    function isInAppearZone(e) {
        const screenWidth = window.innerWidth;
        const appearZoneWidth = screenWidth * 0.05; // 10% of screen width
        return e.clientX <= appearZoneWidth;
    }
    
    // Function to determine if mouse is far enough to hide sidebar
    function isInHideZone(e) {
        const screenWidth = window.innerWidth;
        const hideZoneWidth = screenWidth * 0.2; // 20% of screen width
        return e.clientX > hideZoneWidth;
    }
    
    // Track sidebar state for better control
    let isSidebarExpanded = false;
    
    // Only add mousemove listener for desktop (not mobile)
    if (window.innerWidth > 768) {
        // Expand sidebar when mouse enters the left zone, hide only when moving past 20%
        document.addEventListener('mousemove', (e) => {
            if (isInAppearZone(e) && !isSidebarExpanded) {
                sidebar.classList.add('expanded');
                appContainer.classList.add('sidebar-expanded');
                isSidebarExpanded = true;
            } else if (isInHideZone(e) && isSidebarExpanded) {
                sidebar.classList.remove('expanded');
                appContainer.classList.remove('sidebar-expanded');
                isSidebarExpanded = false;
            }
        });
    }
    
    // Handle touch devices - toggle on sidebar touch
    sidebar.addEventListener('touchstart', (e) => {
        if (!isSidebarExpanded) {
            e.preventDefault();
            sidebar.classList.add('expanded');
            appContainer.classList.add('sidebar-expanded');
            isSidebarExpanded = true;
        }
    });
    
    // Close on touch outside sidebar
    document.addEventListener('touchstart', (e) => {
        if (isSidebarExpanded && !sidebar.contains(e.target)) {
            sidebar.classList.remove('expanded');
            appContainer.classList.remove('sidebar-expanded');
            isSidebarExpanded = false;
        }
    });
    
    // Close sidebar when clicking on overlay
    sidebarOverlay.addEventListener('click', () => {
        sidebar.classList.remove('expanded');
        appContainer.classList.remove('sidebar-expanded');
        isSidebarExpanded = false;
    });
    
    // Handle mobile menu button if it exists
    const mobileToggle = document.querySelector('.mobile-sidebar-toggle');
    if (mobileToggle) {
        mobileToggle.addEventListener('click', () => {
            if (isSidebarExpanded) {
                sidebar.classList.remove('expanded');
                appContainer.classList.remove('sidebar-expanded');
                isSidebarExpanded = false;
            } else {
                sidebar.classList.add('expanded');
                appContainer.classList.add('sidebar-expanded');
                isSidebarExpanded = true;
            }
        });
    }
}); 