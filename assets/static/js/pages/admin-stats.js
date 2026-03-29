/**
 * Admin Stats Page Controller
 * Handles the system statistics page
 */

import { api } from '../modules/api.js';
import { showError, showLoadingOverlay } from '../modules/ui.js';

/**
 * Initialize admin stats page
 */
export function initAdminStats() {
    const statsContainer = document.getElementById('admin-stats-container');
    if (!statsContainer) {return;}

    // Load stats
    loadStats();

    console.log('Admin stats page initialized');
}

/**
 * Load stats from API
 */
async function loadStats() {
    const container = document.getElementById('admin-stats-container');
    if (!container) {return;}

    try {
        showLoadingOverlay(container, true);

        const stats = await api.getStats();

        renderStats(stats);
    } catch (error) {
        console.error('Failed to load admin stats:', error);
        showError(error, 'Failed to Load Statistics');
    } finally {
        showLoadingOverlay(container, false);
    }
}

/**
 * Render stats data
 * @param {Object} stats - Statistics from API
 */
function renderStats(stats) {
    // Guild stats
    const guildsTotalEl = document.getElementById('stats-guilds-total');
    if (guildsTotalEl && stats.guilds) {
        guildsTotalEl.textContent = stats.guilds.total;
    }

    const guildsConfiguredEl = document.getElementById('stats-guilds-configured');
    if (guildsConfiguredEl && stats.guilds) {
        guildsConfiguredEl.textContent = stats.guilds.configured;
    }

    // Data stats
    const yearsTotalEl = document.getElementById('stats-years-total');
    if (yearsTotalEl && stats.data) {
        yearsTotalEl.textContent = stats.data.total_years;
    }

    const markersTotalEl = document.getElementById('stats-markers-total');
    if (markersTotalEl && stats.data) {
        markersTotalEl.textContent = stats.data.total_markers;
    }

    const starredEl = document.getElementById('stats-starred-total');
    if (starredEl && stats.data) {
        starredEl.textContent = stats.data.total_starred_messages ?? '-';
    }

    const starsEl = document.getElementById('stats-stars-total');
    if (starsEl && stats.data) {
        starsEl.textContent = stats.data.total_stars ?? '-';
    }

    const eggsEl = document.getElementById('stats-eggs-total');
    if (eggsEl && stats.data) {
        eggsEl.textContent = stats.data.total_eggs_hatched ?? '-';
    }

    // System stats
    const dbStatusEl = document.getElementById('stats-db-status');
    if (dbStatusEl && stats.system) {
        if (stats.system.db_connected) {
            dbStatusEl.innerHTML = '<span class="badge bg-success">Connected</span>';
        } else {
            dbStatusEl.innerHTML = '<span class="badge bg-danger">Disconnected</span>';
        }
    }

    const configStatusEl = document.getElementById('stats-config-status');
    if (configStatusEl && stats.system) {
        if (stats.system.config_loaded) {
            configStatusEl.innerHTML = '<span class="badge bg-success">Loaded</span>';
        } else {
            configStatusEl.innerHTML = '<span class="badge bg-warning">Not Loaded</span>';
        }
    }

    const uptimeEl = document.getElementById('stats-uptime');
    if (uptimeEl && stats.system) {
        uptimeEl.textContent = formatUptime(stats.system.uptime_seconds);
    }

    const primaryGuildEl = document.getElementById('stats-primary-guild');
    if (primaryGuildEl && stats.system) {
        primaryGuildEl.textContent = stats.system.primary_guild || 'Not set';
    }

    const configVersionEl = document.getElementById('stats-config-version');
    if (configVersionEl && stats.system) {
        configVersionEl.textContent = stats.system.config_version || 'N/A';
    }

    // Initialize Feather icons
    if (typeof feather !== 'undefined') {
        feather.replace();
    }
}

/**
 * Format uptime in human-readable format
 * @param {number} seconds - Uptime in seconds
 * @returns {string} Formatted uptime
 */
function formatUptime(seconds) {
    if (!seconds || seconds < 0) {return 'Unknown';}

    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);

    const parts = [];
    if (days > 0) {
        parts.push(`${days} ${days === 1 ? 'day' : 'days'}`);
    }
    if (hours > 0) {
        parts.push(`${hours} ${hours === 1 ? 'hour' : 'hours'}`);
    }
    if (minutes > 0 || parts.length === 0) {
        parts.push(`${minutes} ${minutes === 1 ? 'minute' : 'minutes'}`);
    }

    return parts.join(', ');
}

// Auto-initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    const statsContainer = document.getElementById('admin-stats-container');
    if (statsContainer) {
        initAdminStats();
    }
});
