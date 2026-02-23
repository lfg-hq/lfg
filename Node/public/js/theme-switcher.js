/**
 * Theme Switcher
 * Handles switching between dark and light themes
 * Persists preference to localStorage
 */

(function() {
    'use strict';

    console.log('[ThemeSwitcher] Initializing...');

    const THEME_KEY = 'lfg-theme';
    const DARK_THEME = 'dark';
    const LIGHT_THEME = 'light';

    /**
     * Get the current theme from localStorage or system preference
     * @returns {string} 'dark' or 'light'
     */
    function getStoredTheme() {
        const stored = localStorage.getItem(THEME_KEY);
        console.log('[ThemeSwitcher] Stored theme:', stored);
        if (stored) {
            return stored;
        }
        // Default to dark theme (matches current app design)
        return DARK_THEME;
    }

    /**
     * Apply theme to document
     * @param {string} theme - 'dark' or 'light'
     */
    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        // document.body may not exist yet if called from <head>
        if (document.body) {
            document.body.setAttribute('data-theme', theme);
        }
        localStorage.setItem(THEME_KEY, theme);

        // Update theme toggle button if it exists
        updateToggleButton(theme);

        // Dispatch custom event for other scripts to react
        window.dispatchEvent(new CustomEvent('themechange', { detail: { theme } }));
    }

    /**
     * Toggle between dark and light themes
     * @returns {string} The new theme
     */
    function toggleTheme() {
        console.log('[ThemeSwitcher] toggleTheme() called');
        const current = document.documentElement.getAttribute('data-theme') || DARK_THEME;
        console.log('[ThemeSwitcher] Current theme:', current);
        const newTheme = current === DARK_THEME ? LIGHT_THEME : DARK_THEME;
        console.log('[ThemeSwitcher] Switching to:', newTheme);
        applyTheme(newTheme);
        return newTheme;
    }

    /**
     * Update toggle button appearance
     * @param {string} theme - Current theme
     */
    function updateToggleButton(theme) {
        // Update header toggle button
        const toggleBtn = document.getElementById('theme-toggle');
        if (toggleBtn) {
            const icon = toggleBtn.querySelector('i');
            if (icon) {
                if (theme === DARK_THEME) {
                    icon.className = 'fas fa-sun';
                    toggleBtn.setAttribute('title', 'Switch to light mode');
                } else {
                    icon.className = 'fas fa-moon';
                    toggleBtn.setAttribute('title', 'Switch to dark mode');
                }
            }
        }

        // Update sidebar toggle button text
        const sidebarToggle = document.getElementById('sidebar-theme-toggle');
        if (sidebarToggle) {
            const navText = sidebarToggle.querySelector('.nav-text');
            if (navText) {
                navText.textContent = theme === DARK_THEME ? 'Light Mode' : 'Dark Mode';
            }
            sidebarToggle.setAttribute('title', theme === DARK_THEME ? 'Switch to light mode' : 'Switch to dark mode');
        }
    }

    /**
     * Initialize theme on page load
     */
    function initTheme() {
        const theme = getStoredTheme();
        applyTheme(theme);
    }

    // Apply theme immediately to prevent flash
    initTheme();

    // Expose functions globally
    window.ThemeSwitcher = {
        toggle: toggleTheme,
        setTheme: applyTheme,
        getTheme: function() {
            return document.documentElement.getAttribute('data-theme') || DARK_THEME;
        },
        isDark: function() {
            return this.getTheme() === DARK_THEME;
        },
        isLight: function() {
            return this.getTheme() === LIGHT_THEME;
        }
    };

    // Auto-init toggle buttons when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        console.log('[ThemeSwitcher] DOMContentLoaded - binding event handlers');

        // Apply theme to body now that it exists
        const currentTheme = getStoredTheme();
        if (document.body) {
            document.body.setAttribute('data-theme', currentTheme);
        }

        // Bind click handlers to any theme toggle buttons with data-theme-toggle attribute
        const dataToggleBtns = document.querySelectorAll('[data-theme-toggle]');
        console.log('[ThemeSwitcher] Found data-theme-toggle buttons:', dataToggleBtns.length);
        dataToggleBtns.forEach(function(btn) {
            console.log('[ThemeSwitcher] Binding click to:', btn.id || btn.className);
            btn.addEventListener('click', function(e) {
                console.log('[ThemeSwitcher] data-theme-toggle button clicked');
                e.preventDefault();
                toggleTheme();
            });
        });

        // Also handle the #theme-toggle button specifically (header button)
        const mainToggle = document.getElementById('theme-toggle');
        if (mainToggle && !mainToggle.hasAttribute('data-theme-toggle')) {
            console.log('[ThemeSwitcher] Binding click to main theme-toggle');
            mainToggle.addEventListener('click', function(e) {
                console.log('[ThemeSwitcher] main theme-toggle clicked');
                e.preventDefault();
                toggleTheme();
            });
        }

        // Handle sidebar theme toggle specifically
        const sidebarToggle = document.getElementById('sidebar-theme-toggle');
        console.log('[ThemeSwitcher] Sidebar toggle element:', sidebarToggle);
        if (sidebarToggle && !sidebarToggle.hasAttribute('data-theme-toggle')) {
            console.log('[ThemeSwitcher] Binding click to sidebar-theme-toggle (no data attr)');
            sidebarToggle.addEventListener('click', function(e) {
                console.log('[ThemeSwitcher] sidebar-theme-toggle clicked');
                e.preventDefault();
                toggleTheme();
            });
        }

        // Update button state on load
        updateToggleButton(currentTheme);
        console.log('[ThemeSwitcher] Initialization complete');
    });

})();
