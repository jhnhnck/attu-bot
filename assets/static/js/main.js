/**
 * Main Entry Point
 * Initializes the application and modules
 */

import { initGuildToggle } from './components/guild-toggle.js';
import { initThemeToggle } from './components/theme-toggle.js';
import { initUI } from './modules/ui.js';

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    // Initialize Feather icons
    if (typeof feather !== 'undefined') {
        feather.replace();
    }

    // Initialize UI components (modals, toasts, etc.)
    initUI();

    // Initialize theme toggle
    initThemeToggle();

    // Initialize guild toggle
    initGuildToggle();

    // Auto-close offcanvas sidebar on nav click (mobile)
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
        sidebar.querySelectorAll('.sidebar-link').forEach(link => {
            link.addEventListener('click', () => {
                const offcanvas = bootstrap.Offcanvas.getInstance(sidebar);
                if (offcanvas) {offcanvas.hide();}
            });
        });
    }

    console.log('Doom Bot Configurator initialized');
});

// Export for use in other modules if needed
export { initUI };
