/**
 * Years Page Controller
 * Handles the years viewer page
 */

import { confirmAction, showError, showLoadingOverlay, showSuccess } from "../modules/ui.js";
import { createYear, deleteYear, getAllYears } from "../modules/years.js";

let guildId = null;
let yearModal = null;

/**
 * Initialize years page
 * @param {BigInt|number|string} guildIdParam - The guild ID
 */
export function initYears(guildIdParam) {
    guildId = guildIdParam;
    const yearsContainer = document.getElementById("years-container");
    if (!yearsContainer) return;

    // Initialize modal
    const modalElement = document.getElementById("yearModal");
    if (modalElement && typeof bootstrap !== "undefined") {
        yearModal = new bootstrap.Modal(modalElement);
    }

    // Set up event listeners
    setupEventListeners();

    // Load years data
    loadYears();

    console.log("Years page initialized for guild:", guildId);
}

/**
 * Set up event listeners
 */
function setupEventListeners() {
    // Create button
    const createBtn = document.getElementById("create-year-btn");
    if (createBtn) {
        createBtn.addEventListener("click", () => openYearModal());
    }

    // Save button
    const saveBtn = document.getElementById("save-year-btn");
    if (saveBtn) {
        saveBtn.addEventListener("click", saveYear);
    }
}

/**
 * Load years from API
 */
async function loadYears() {
    const container = document.getElementById("years-container");
    const tableBody = document.getElementById("years-table-body");

    if (!container || !tableBody) return;

    try {
        showLoadingOverlay(container, true);

        const years = await getAllYears(guildId);

        // Sort years by year number (descending - newest first)
        years.sort((a, b) => b.year - a.year);

        renderYearsTable(years);
    } catch (error) {
        console.error("Failed to load years:", error);
        showError(error, "Failed to Load Years");
        tableBody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center text-danger">
                    <i data-feather="alert-circle" class="me-2"></i>
                    Failed to load years data
                </td>
            </tr>
        `;
    } finally {
        showLoadingOverlay(container, false);
    }
}

/**
 * Render years in table
 * @param {Year[]} years - Array of Year objects
 */
function renderYearsTable(years) {
    const tableBody = document.getElementById("years-table-body");

    if (!tableBody) return;

    if (years.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="7" class="text-center text-muted">
                    <i data-feather="calendar" class="me-2"></i>
                    No years recorded yet
                </td>
            </tr>
        `;
        // Initialize Feather icons
        if (typeof feather !== "undefined") {
            feather.replace();
        }
        return;
    }

    tableBody.innerHTML = years.map((year) => {
        const startDate = year.start_time > 0 ? formatDate(year.start_time) : "N/A";
        const endDate = year.end_time > 0 ? formatDate(year.end_time) : "Ongoing";
        const duration = year.getDurationDays();
        const durationDisplay = duration !== null ? `${duration} days` : "Ongoing";
        const statusBadge = year.isComplete()
            ? '<span class="badge bg-success">Complete</span>'
            : '<span class="badge bg-warning">Ongoing</span>';

        return `
            <tr>
                <td>${year.year}</td>
                <td>${escapeHtml(year.getDisplayName())}</td>
                <td>${startDate}</td>
                <td>${endDate}</td>
                <td>${durationDisplay}</td>
                <td>${statusBadge}</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary me-1" onclick="window.editYear(${year.year})" title="Edit">
                        <i data-feather="edit-2"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="window.deleteYearConfirm(${year.year})" title="Delete">
                        <i data-feather="trash-2"></i>
                    </button>
                </td>
            </tr>
        `;
    }).join("");

    // Initialize Feather icons
    if (typeof feather !== "undefined") {
        feather.replace();
    }
}

/**
 * Open year modal for create or edit
 * @param {number} yearNumber - Year number to edit (null for create)
 */
async function openYearModal(yearNumber = null) {
    const modalTitle = document.getElementById("yearModalLabel");
    const form = document.getElementById("year-form");

    if (yearNumber) {
        // Edit mode
        modalTitle.textContent = `Edit Year ${yearNumber}`;
        try {
            const { getYear } = await import("../modules/years.js");
            const year = await getYear(guildId, yearNumber);

            document.getElementById("year-id").value = year.year;
            document.getElementById("year-number").value = year.year;
            document.getElementById("year-number").disabled = true; // Can't change year number
            document.getElementById("year-start-time").value = year.start_time;
            document.getElementById("year-end-time").value = year.end_time;
            document.getElementById("year-duration").value = year.duration;
            document.getElementById("year-formatted").value = year.formatted;
            document.getElementById("year-notes").value = year.notes;
        } catch (error) {
            showError(error, "Failed to Load Year");
            return;
        }
    } else {
        // Create mode
        modalTitle.textContent = "Create Year";
        form.reset();
        document.getElementById("year-id").value = "";
        document.getElementById("year-number").disabled = false;
        document.getElementById("year-end-time").value = "0";
        document.getElementById("year-duration").value = "0";
    }

    if (yearModal) {
        yearModal.show();
    }
}

/**
 * Save year (create or update)
 */
async function saveYear() {
    const saveBtn = document.getElementById("save-year-btn");
    const yearNumber = parseInt(document.getElementById("year-number").value);
    const startTime = parseInt(document.getElementById("year-start-time").value);
    const endTime = parseInt(document.getElementById("year-end-time").value) || 0;
    const duration = parseInt(document.getElementById("year-duration").value) || 0;
    const formatted = document.getElementById("year-formatted").value.trim();
    const notes = document.getElementById("year-notes").value.trim();

    if (!yearNumber || !startTime) {
        showError(new Error("Year number and start time are required"), "Validation Error");
        return;
    }

    const originalText = saveBtn.textContent;
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Saving...';

    try {
        await createYear(guildId, yearNumber, {
            start_time: startTime,
            end_time: endTime,
            duration: duration,
            formatted: formatted || `Year ${yearNumber} PC`,
            notes: notes,
        });

        showSuccess(`Year ${yearNumber} saved successfully`);

        if (yearModal) {
            yearModal.hide();
        }

        // Reload years
        await loadYears();
    } catch (error) {
        showError(error, "Failed to Save Year");
    } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = originalText;
    }
}

/**
 * Delete year with confirmation
 * @param {number} yearNumber - Year number to delete
 */
async function deleteYearConfirm(yearNumber) {
    const confirmed = await confirmAction(
        `Are you sure you want to delete Year ${yearNumber}? This action cannot be undone.`,
        "Delete Year",
        { danger: true, confirmText: "Delete" }
    );

    if (!confirmed) return;

    try {
        await deleteYear(guildId, yearNumber);
        showSuccess(`Year ${yearNumber} deleted successfully`);

        // Reload years
        await loadYears();
    } catch (error) {
        showError(error, "Failed to Delete Year");
    }
}

// Make functions globally accessible for onclick handlers
window.editYear = openYearModal;
window.deleteYearConfirm = deleteYearConfirm;

/**
 * Format Unix timestamp to date string
 * @param {number} timestamp - Unix timestamp in seconds
 * @returns {string} Formatted date string
 */
function formatDate(timestamp) {
    // timestamp is in seconds, convert to milliseconds
    const date = new Date(timestamp * 1000);
    return date.toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
    });
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

