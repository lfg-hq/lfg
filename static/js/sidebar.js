document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar');
    const appContainer = document.querySelector('.app-container');
    const minimizeBtn = document.getElementById('minimize-btn');
    const userInfo = document.getElementById('user-info');
    const userInfoButton = document.getElementById('user-info-button');
    const userDropdown = document.getElementById('user-dropdown');
    
    // The sidebar state is already set by the server, just sync localStorage
    const isMinimized = sidebar && sidebar.classList.contains('minimized');
    const isSidebarMinimized = appContainer && appContainer.classList.contains('sidebar-minimized');
    
    // Sync localStorage with server state
    localStorage.setItem('sidebarMinimized', isMinimized ? 'true' : 'false');
    
    // Toggle sidebar minimized state
    async function toggleMinimized() {
        const isMinimized = sidebar.classList.contains('minimized');
        const newState = !isMinimized;
        
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
        
        // Sync with server
        try {
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
            await fetch('/api/toggle-sidebar/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ minimized: newState })
            });
        } catch (error) {
            console.error('Failed to sync sidebar state:', error);
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
    
    // Handle integrations button - remove click handler since it's now a regular link
    // The integrations button now properly navigates to the integrations page
    
    // Handle chat link click
    const chatLink = document.querySelector('.chat-link');
    if (chatLink) {
        chatLink.addEventListener('click', async (e) => {
            e.preventDefault();
            
            try {
                // Fetch the latest conversation info
                const response = await fetch('/api/latest-conversation/');
                const data = await response.json();
                
                if (data.success) {
                    // Construct the URL
                    let url = `/chat/project/${data.project_id}/`;
                    if (data.conversation_id) {
                        url += `?conversation_id=${data.conversation_id}`;
                    }
                    // Navigate to the URL
                    window.location.href = url;
                }
            } catch (error) {
                console.error('Error fetching latest conversation:', error);
                // Fallback to chat index
                window.location.href = '/chat/';
            }
        });
    }
    
    // Format number to K, M notation
    function formatTokenCount(num) {
        if (num >= 1000000) {
            return (num / 1000000).toFixed(num >= 10000000 ? 0 : 1) + 'M';
        } else if (num >= 1000) {
            return (num / 1000).toFixed(num >= 10000 ? 0 : 1) + 'K';
        }
        return num.toString();
    }

    // Fetch and update daily token usage
    async function updateDailyTokens() {
        try {
            const response = await fetch('/api/daily-token-usage/');
            const data = await response.json();
            
            if (data.success) {
                const tokenElement = document.getElementById('daily-tokens');
                const minimizedTokenElement = document.getElementById('minimized-tokens');
                
                if (tokenElement || minimizedTokenElement) {
                    const formattedTokens = formatTokenCount(data.tokens);
                    
                    if (tokenElement) {
                        tokenElement.textContent = formattedTokens;
                    }
                    if (minimizedTokenElement) {
                        minimizedTokenElement.textContent = formattedTokens;
                    }
                }
            }
        } catch (error) {
            console.error('Error fetching daily token usage:', error);
        }
    }
    
    // Update tokens on page load
    updateDailyTokens();
    
    // Export the function so it can be called from other scripts
    window.updateDailyTokens = updateDailyTokens;
});