/**
 * Dashboard Page Controller
 * Handles the main dashboard/index page
 */

import { api } from "../modules/api.js";
import { showError, showLoadingOverlay } from "../modules/ui.js";

/**
 * Initialize dashboard page
 */
export function initDashboard() {
    const dashboardEl = document.getElementById("dashboard");
    if (!dashboardEl) return;

    // Load guild data via API (for dynamic updates)
    loadGuildStats();

    // Initialize any dashboard-specific functionality
    console.log("Dashboard initialized");
}

/**
 * Load guild statistics for dashboard cards
 */
async function loadGuildStats() {
    const statsContainer = document.getElementById("guild-stats");
    if (!statsContainer) return;

    try {
        // Show loading state
        showLoadingOverlay(statsContainer, true);

        // Fetch admin stats
        const stats = await api.getStats();

        // Update stats display
        updateStatsDisplay(stats);
    } catch (error) {
        console.error("Failed to load guild stats:", error);
        showError(error, "Failed to Load Stats");
    } finally {
        showLoadingOverlay(statsContainer, false);
    }
}

/**
 * Update the stats display
 */
function updateStatsDisplay(stats) {
    // Update guild count
    const guildCountEl = document.getElementById("stat-guilds");
    if (guildCountEl && stats.guilds) {
        guildCountEl.textContent = `${stats.guilds.configured}/${stats.guilds.total}`;
    }

    // Update years count
    const yearsCountEl = document.getElementById("stat-years");
    if (yearsCountEl && stats.data) {
        yearsCountEl.textContent = stats.data.total_years || 0;
    }

    // Update markers count
    const markersCountEl = document.getElementById("stat-markers");
    if (markersCountEl && stats.data) {
        markersCountEl.textContent = stats.data.total_markers || 0;
    }

    // Update system status
    const statusEl = document.getElementById("stat-status");
    if (statusEl && stats.system) {
        const isConnected = stats.system.db_connected && stats.system.config_loaded;
        statusEl.textContent = isConnected ? "Online" : "Offline";
        statusEl.className = isConnected ? "badge bg-success" : "badge bg-danger";
    }
}

/**
 * Format guild ID for display
 */
export function formatGuildId(id) {
    if (typeof id === "bigint") {
        return id.toString();
    }
    return String(id);
}

/**
 * Get guild card template
 */
export function getGuildCardTemplate(guild) {
    const configured = guild.configured;
    const statusClass = configured ? "bg-success" : "bg-warning";
    const statusText = configured ? "Configured" : "Not Configured";

    return `
        <div class="col-md-6 col-lg-4 mb-4">
            <div class="card h-100 shadow-sm">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h5 class="card-title mb-0">
                        <i data-feather="users" class="me-2"></i>
                        ${escapeHtml(guild.name)}
                    </h5>
                    <span class="badge ${statusClass}">${statusText}</span>
                </div>
                <div class="card-body">
                    <p class="card-text">
                        <small class="text-muted">
                            <i data-feather="hash"></i>
                            Guild ID: <code>${formatGuildId(guild.id)}</code>
                        </small>
                    </p>
                </div>
                <div class="card-footer bg-transparent">
                    <a href="/guild/${formatGuildId(guild.id)}" class="btn btn-primary btn-sm">
                        <i data-feather="settings" class="me-1"></i>
                        Configure
                    </a>
                </div>
            </div>
        </div>
    `;
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

