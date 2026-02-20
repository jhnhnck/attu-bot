/**
 * Main Entry Point
 * Initializes the application and modules
 */

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

    console.log('Doom Bot Configurator initialized');
});

// Export for use in other modules if needed
export { initUI };
