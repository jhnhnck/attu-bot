/**
 * UI Utilities Module
 * Handles notifications, loading states, modals, etc.
 */

let toastContainer = null;
let confirmModal = null;
let errorModal = null;

/**
 * Initialize UI components (call on page load)
 */
export function initUI() {
    // Create toast container
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
        toastContainer.style.zIndex = '9999';
        document.body.appendChild(toastContainer);
    }

    // Create confirm modal
    if (!confirmModal) {
        const modalHTML = `
            <div class="modal fade" id="confirmModal" tabindex="-1" aria-labelledby="confirmModalLabel" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="confirmModalLabel">Confirm Action</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body" id="confirmModalBody">
                            Are you sure?
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                            <button type="button" class="btn btn-primary" id="confirmModalConfirm">Confirm</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        confirmModal = new bootstrap.Modal(document.getElementById('confirmModal'));
    }

    // Create error modal
    if (!errorModal) {
        const modalHTML = `
            <div class="modal fade" id="errorModal" tabindex="-1" aria-labelledby="errorModalLabel" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header bg-danger text-white">
                            <h5 class="modal-title" id="errorModalLabel">Error</h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body" id="errorModalBody">
                            An error occurred.
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        errorModal = new bootstrap.Modal(document.getElementById('errorModal'));
    }
}

/**
 * Show a Bootstrap toast notification
 * @param {string} message - The message to display
 * @param {string} type - Toast type: 'success', 'error', 'warning', 'info'
 * @param {number} duration - Auto-hide delay in milliseconds (0 = no auto-hide)
 */
export function showNotification(message, type = "info", duration = 5000) {
    if (!toastContainer) {
        initUI();
    }

    // Map types to Bootstrap colors
    const colorMap = {
        success: 'success',
        error: 'danger',
        warning: 'warning',
        info: 'info',
    };

    const iconMap = {
        success: 'check-circle',
        error: 'x-circle',
        warning: 'alert-triangle',
        info: 'info',
    };

    const bgColor = colorMap[type] || 'info';
    const icon = iconMap[type] || 'info';

    const toastId = `toast-${Date.now()}`;
    const toastHTML = `
        <div id="${toastId}" class="toast align-items-center text-bg-${bgColor} border-0" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">
                    <i data-feather="${icon}" class="me-2" style="width: 16px; height: 16px;"></i>
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;

    toastContainer.insertAdjacentHTML('beforeend', toastHTML);
    const toastElement = document.getElementById(toastId);

    // Initialize Feather icons in toast
    if (typeof feather !== 'undefined') {
        feather.replace();
    }

    const toast = new bootstrap.Toast(toastElement, {
        autohide: duration > 0,
        delay: duration,
    });

    toast.show();

    // Remove from DOM after hidden
    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
}

/**
 * Show success notification (convenience method)
 */
export function showSuccess(message, duration = 5000) {
    showNotification(message, 'success', duration);
}

/**
 * Show error notification (convenience method)
 */
export function showErrorNotification(message, duration = 8000) {
    showNotification(message, 'error', duration);
}

/**
 * Show warning notification (convenience method)
 */
export function showWarning(message, duration = 6000) {
    showNotification(message, 'warning', duration);
}

/**
 * Show info notification (convenience method)
 */
export function showInfo(message, duration = 5000) {
    showNotification(message, 'info', duration);
}

/**
 * Set loading state on an element (typically a button)
 * @param {HTMLElement} element - The element to set loading state on
 * @param {boolean} isLoading - Whether to show loading state
 */
export function setLoading(element, isLoading) {
    if (isLoading) {
        element.disabled = true;
        element.dataset.originalContent = element.innerHTML;

        // Add spinner
        const spinner = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>`;
        element.innerHTML = spinner + (element.dataset.loadingText || 'Loading...');
    } else {
        element.disabled = false;
        if (element.dataset.originalContent) {
            element.innerHTML = element.dataset.originalContent;
            delete element.dataset.originalContent;
        }
    }
}

/**
 * Show a loading overlay on an element
 * @param {HTMLElement} element - The element to show loading overlay on
 * @param {boolean} show - Whether to show or hide the overlay
 */
export function showLoadingOverlay(element, show = true) {
    if (show) {
        // Create overlay if it doesn't exist
        let overlay = element.querySelector('.loading-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.className = 'loading-overlay position-absolute top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center bg-body bg-opacity-75';
            overlay.style.zIndex = '1000';
            overlay.innerHTML = '<div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div>';

            // Ensure parent has position relative
            const position = window.getComputedStyle(element).position;
            if (position === 'static') {
                element.style.position = 'relative';
            }

            element.appendChild(overlay);
        }
        overlay.style.display = 'flex';
    } else {
        const overlay = element.querySelector('.loading-overlay');
        if (overlay) {
            overlay.remove();
        }
    }
}

/**
 * Show a confirmation modal
 * @param {string} message - The confirmation message
 * @param {string} title - The modal title
 * @param {object} options - Additional options (confirmText, cancelText, danger)
 * @returns {Promise<boolean>} - Resolves to true if confirmed, false if cancelled
 */
export async function confirmAction(message, title = "Confirm Action", options = {}) {
    if (!confirmModal) {
        initUI();
    }

    return new Promise((resolve) => {
        const modalElement = document.getElementById('confirmModal');
        const titleElement = document.getElementById('confirmModalLabel');
        const bodyElement = document.getElementById('confirmModalBody');
        const confirmBtn = document.getElementById('confirmModalConfirm');

        // Set content
        titleElement.textContent = title;
        bodyElement.textContent = message;

        // Set button text
        confirmBtn.textContent = options.confirmText || 'Confirm';

        // Set button style (danger for destructive actions)
        confirmBtn.className = `btn ${options.danger ? 'btn-danger' : 'btn-primary'}`;

        // Handle confirm
        const handleConfirm = () => {
            confirmModal.hide();
            cleanup();
            resolve(true);
        };

        // Handle cancel
        const handleCancel = () => {
            cleanup();
            resolve(false);
        };

        // Cleanup listeners
        const cleanup = () => {
            confirmBtn.removeEventListener('click', handleConfirm);
            modalElement.removeEventListener('hidden.bs.modal', handleCancel);
        };

        // Add listeners
        confirmBtn.addEventListener('click', handleConfirm);
        modalElement.addEventListener('hidden.bs.modal', handleCancel, { once: true });

        // Show modal
        confirmModal.show();
    });
}

/**
 * Show an error modal
 * @param {Error|string} error - The error object or message
 * @param {string} title - The modal title
 */
export function showError(error, title = "Error") {
    if (!errorModal) {
        initUI();
    }

    const titleElement = document.getElementById('errorModalLabel');
    const bodyElement = document.getElementById('errorModalBody');

    titleElement.textContent = title;

    // Format error message
    let errorMessage = '';
    if (error instanceof Error) {
        errorMessage = error.message;
        if (error.details) {
            errorMessage += '\n\nDetails:\n' + JSON.stringify(error.details, null, 2);
        }
    } else {
        errorMessage = String(error);
    }

    bodyElement.textContent = errorMessage;

    errorModal.show();
}

/**
 * Show a simple alert modal
 * @param {string} message - The message to display
 * @param {string} title - The modal title
 * @param {string} type - Alert type: 'info', 'success', 'warning', 'danger'
 */
export function showAlert(message, title = "Alert", type = "info") {
    // Reuse error modal but with different styling
    if (!errorModal) {
        initUI();
    }

    const modalElement = document.getElementById('errorModal');
    const headerElement = modalElement.querySelector('.modal-header');
    const titleElement = document.getElementById('errorModalLabel');
    const bodyElement = document.getElementById('errorModalBody');

    // Set header color
    const colorMap = {
        info: 'bg-info',
        success: 'bg-success',
        warning: 'bg-warning',
        danger: 'bg-danger',
    };

    headerElement.className = `modal-header ${colorMap[type] || 'bg-info'} text-white`;
    titleElement.textContent = title;
    bodyElement.textContent = message;

    errorModal.show();

    // Reset header color when hidden
    modalElement.addEventListener('hidden.bs.modal', () => {
        headerElement.className = 'modal-header bg-danger text-white';
    }, { once: true });
}

/**
 * Debounce a function call
 * @param {Function} func - The function to debounce
 * @param {number} wait - The delay in milliseconds
 * @returns {Function} - The debounced function
 */
export function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}
