/**
 * Time Status Page Controller
 * Handles the time status dashboard page
 */

import { formatTimestamp, getTimeStatus } from "../modules/time.js";
import { showError, showLoadingOverlay } from "../modules/ui.js";

let guildId = null;
let refreshInterval = null;

/**
 * Initialize time status page
 * @param {BigInt|number|string} guildIdParam - The guild ID
 */
export function initTimeStatus(guildIdParam) {
    guildId = guildIdParam;
    const timeContainer = document.getElementById("time-container");
    if (!timeContainer) return;

    // Load time status
    loadTimeStatus();

    // Auto-refresh every 30 seconds
    refreshInterval = setInterval(loadTimeStatus, 30000);

    console.log("Time status page initialized for guild:", guildId);
}

/**
 * Clean up on page unload
 */
export function cleanup() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

/**
 * Load time status from API
 */
async function loadTimeStatus() {
    const container = document.getElementById("time-container");
    if (!container) return;

    try {
        showLoadingOverlay(container, true);

        const timeData = await getTimeStatus(guildId);

        renderTimeStatus(timeData);
    } catch (error) {
        console.error("Failed to load time status:", error);
        showError(error, "Failed to Load Time Status");
    } finally {
        showLoadingOverlay(container, false);
    }
}

/**
 * Render time status data
 * @param {Object} timeData - Time status from API
 */
function renderTimeStatus(timeData) {
    // Update current year
    const yearEl = document.getElementById("current-year");
    if (yearEl) {
        yearEl.textContent = timeData.current_year;
    }

    // Update current day
    const dayEl = document.getElementById("current-day");
    if (dayEl) {
        dayEl.textContent = timeData.current_day;
    }

    // Update elapsed days
    const elapsedEl = document.getElementById("elapsed-days");
    if (elapsedEl) {
        elapsedEl.textContent = timeData.elapsed_days;
    }

    // Update year length
    const yearLengthEl = document.getElementById("year-length");
    if (yearLengthEl) {
        yearLengthEl.textContent = `${timeData.year_length} days`;
    }

    // Update paused status
    const pausedEl = document.getElementById("paused-status");
    if (pausedEl) {
        if (timeData.paused) {
            pausedEl.innerHTML = '<span class="badge bg-warning">Paused</span>';
        } else {
            pausedEl.innerHTML = '<span class="badge bg-success">Active</span>';
        }
    }

    // Update next rollover
    const rolloverEl = document.getElementById("next-rollover");
    if (rolloverEl) {
        rolloverEl.textContent = formatTimestamp(timeData.next_rollover, true);
    }

    // Update rollover time (daily time)
    const rolloverTimeEl = document.getElementById("rollover-time");
    if (rolloverTimeEl) {
        rolloverTimeEl.textContent = timeData.rollover_time;
    }

    // Update epoch info
    const epochTimeEl = document.getElementById("epoch-time");
    if (epochTimeEl) {
        epochTimeEl.textContent = formatTimestamp(timeData.epoch_time, true);
    }

    const epochYearEl = document.getElementById("epoch-year");
    if (epochYearEl) {
        epochYearEl.textContent = timeData.epoch_year;
    }

    // Update progress bar if not paused
    const progressBar = document.getElementById("year-progress");
    const progressText = document.getElementById("year-progress-text");
    if (progressBar && progressText && !timeData.paused) {
        const progress = (timeData.current_day / timeData.year_length) * 100;
        progressBar.style.width = `${progress}%`;
        progressBar.setAttribute("aria-valuenow", progress);
        progressText.textContent = `${Math.round(progress)}% through year`;
    } else if (progressBar && progressText) {
        progressBar.style.width = "0%";
        progressText.textContent = "Paused";
    }

    // Initialize Feather icons
    if (typeof feather !== "undefined") {
        feather.replace();
    }
}

// Auto-initialize if DOM is ready and guildId is set globally
document.addEventListener("DOMContentLoaded", () => {
    const timeContainer = document.getElementById("time-container");
    if (timeContainer && typeof window.currentGuildId !== "undefined") {
        initTimeStatus(window.currentGuildId);
    }

    // Clean up on page unload
    window.addEventListener("beforeunload", cleanup);
});
