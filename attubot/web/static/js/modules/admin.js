/**
 * Admin Module
 * Handles admin-only features and statistics
 */

import { api } from "./api.js";

/**
 * Get system statistics
 */
export async function getSystemStats() {
    return api.getStats();
}

/**
 * Get audit logs with optional filtering
 */
export async function getAuditLogs(filters = {}) {
    return api.getAuditLogs(filters);
}
