/**
 * Markers Page Controller
 * Handles the markers viewer page
 */

import { createMarker, deleteMarker, getAllMarkers } from '../modules/markers.js';
import { confirmAction, showError, showLoadingOverlay, showSuccess } from '../modules/ui.js';

let guildId = null;
let markerModal = null;

/**
 * Initialize markers page
 * @param {BigInt|number|string} guildIdParam - The guild ID
 */
export function initMarkers(guildIdParam) {
    guildId = guildIdParam;
    const markersContainer = document.getElementById('markers-container');
    if (!markersContainer) {return;}

    // Initialize modal
    const modalElement = document.getElementById('markerModal');
    if (modalElement && typeof bootstrap !== 'undefined') {
        markerModal = new bootstrap.Modal(modalElement);
    }

    // Set up event listeners
    setupEventListeners();

    // Load markers data
    loadMarkers();

    console.log('Markers page initialized for guild:', guildId);
}

/**
 * Set up event listeners
 */
function setupEventListeners() {
    // Create button
    const createBtn = document.getElementById('create-marker-btn');
    if (createBtn) {
        createBtn.addEventListener('click', () => openMarkerModal());
    }

    // Save button
    const saveBtn = document.getElementById('save-marker-btn');
    if (saveBtn) {
        saveBtn.addEventListener('click', saveMarker);
    }
}

/**
 * Load markers from API
 */
async function loadMarkers() {
    const container = document.getElementById('markers-container');
    const tableBody = document.getElementById('markers-table-body');

    if (!container || !tableBody) {return;}

    try {
        showLoadingOverlay(container, true);

        const markers = await getAllMarkers(guildId);

        // Sort markers by year (descending - newest first)
        markers.sort((a, b) => b.year - a.year);

        renderMarkersTable(markers);
    } catch (error) {
        console.error('Failed to load markers:', error);
        showError(error, 'Failed to Load Markers');
        tableBody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center text-danger">
                    <i data-feather="alert-circle" class="me-2"></i>
                    Failed to load markers data
                </td>
            </tr>
        `;
    } finally {
        showLoadingOverlay(container, false);
    }
}

/**
 * Render markers in table
 * @param {YearMarker[]} markers - Array of YearMarker objects
 */
function renderMarkersTable(markers) {
    const tableBody = document.getElementById('markers-table-body');

    if (!tableBody) {return;}

    if (markers.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="7" class="text-center text-muted">
                    <i data-feather="map-pin" class="me-2"></i>
                    No markers recorded yet
                </td>
            </tr>
        `;
        // Initialize Feather icons
        if (typeof feather !== 'undefined') {
            feather.replace();
        }
        return;
    }

    tableBody.innerHTML = markers.map((marker) => {
        const timestamp = marker.getTimestamp();
        const timestampDisplay = timestamp.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
        const exactBadge = marker.exact
            ? '<span class="badge bg-success">Exact</span>'
            : '<span class="badge bg-secondary">Approximate</span>';
        const wikiBadge = marker.wiki_page
            ? '<span class="badge bg-info">Wiki Page</span>'
            : '';
        const discordLink = marker.isValid()
            ? `<a href="${escapeHtml(marker.getMessageUrl(guildId.toString()))}" target="_blank" class="btn btn-sm btn-outline-primary">
                <i data-feather="external-link" class="me-1"></i>
                View
               </a>`
            : '<span class="text-muted">N/A</span>';

        return `
            <tr>
                <td>${marker.year}</td>
                <td>${formatSnowflake(marker.channel)}</td>
                <td>${formatSnowflake(marker.message)}</td>
                <td>${timestampDisplay}</td>
                <td>${exactBadge} ${wikiBadge}</td>
                <td>${discordLink}</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary me-1" onclick="window.editMarker(${marker.year})" title="Edit">
                        <i data-feather="edit-2"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="window.deleteMarkerConfirm(${marker.year})" title="Delete">
                        <i data-feather="trash-2"></i>
                    </button>
                </td>
            </tr>
        `;
    }).join('');

    // Initialize Feather icons
    if (typeof feather !== 'undefined') {
        feather.replace();
    }
}

/**
 * Open marker modal for create or edit
 * @param {number} year - Year to edit (null for create)
 */
async function openMarkerModal(year = null) {
    const modalTitle = document.getElementById('markerModalLabel');
    const form = document.getElementById('marker-form');

    if (year) {
        // Edit mode
        modalTitle.textContent = `Edit Marker for Year ${year}`;
        try {
            const { getMarker } = await import('../modules/markers.js');
            const marker = await getMarker(guildId, year);

            document.getElementById('marker-id').value = marker.year;
            document.getElementById('marker-year').value = marker.year;
            document.getElementById('marker-year').disabled = true; // Can't change year
            document.getElementById('marker-channel').value = marker.channel.toString();
            document.getElementById('marker-message').value = marker.message.toString();
            document.getElementById('marker-exact').checked = marker.exact;
            document.getElementById('marker-wiki-page').checked = marker.wiki_page;
        } catch (error) {
            showError(error, 'Failed to Load Marker');
            return;
        }
    } else {
        // Create mode
        modalTitle.textContent = 'Create Marker';
        form.reset();
        document.getElementById('marker-id').value = '';
        document.getElementById('marker-year').disabled = false;
    }

    if (markerModal) {
        markerModal.show();
    }
}

/**
 * Save marker (create or update)
 */
async function saveMarker() {
    const saveBtn = document.getElementById('save-marker-btn');
    const year = parseInt(document.getElementById('marker-year').value);
    const channel = document.getElementById('marker-channel').value.trim();
    const message = document.getElementById('marker-message').value.trim();
    const exact = document.getElementById('marker-exact').checked;
    const wikiPage = document.getElementById('marker-wiki-page').checked;

    if (!year || !message) {
        showError(new Error('Year and message ID are required'), 'Validation Error');
        return;
    }

    const originalText = saveBtn.textContent;
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Saving...';

    try {
        const data = {
            message,
            exact,
            wiki_page: wikiPage,
        };

        // Only include channel if provided
        if (channel) {
            data.channel = channel;
        }

        await createMarker(guildId, year, data);

        showSuccess(`Marker for year ${year} saved successfully`);

        if (markerModal) {
            markerModal.hide();
        }

        // Reload markers
        await loadMarkers();
    } catch (error) {
        showError(error, 'Failed to Save Marker');
    } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = originalText;
    }
}

/**
 * Delete marker with confirmation
 * @param {number} year - Year to delete marker for
 */
async function deleteMarkerConfirm(year) {
    const confirmed = await confirmAction(
        `Are you sure you want to delete the marker for Year ${year}? This action cannot be undone.`,
        'Delete Marker',
        { danger: true, confirmText: 'Delete' }
    );

    if (!confirmed) {return;}

    try {
        await deleteMarker(guildId, year);
        showSuccess(`Marker for year ${year} deleted successfully`);

        // Reload markers
        await loadMarkers();
    } catch (error) {
        showError(error, 'Failed to Delete Marker');
    }
}

// Make functions globally accessible for onclick handlers
window.editMarker = openMarkerModal;
window.deleteMarkerConfirm = deleteMarkerConfirm;

/**
 * Format Discord snowflake ID for display
 * @param {BigInt} snowflake - Discord snowflake ID
 * @returns {string} Formatted snowflake string
 */
function formatSnowflake(snowflake) {
    if (!snowflake || snowflake === BigInt(0)) {return 'N/A';}
    return snowflake.toString();
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

