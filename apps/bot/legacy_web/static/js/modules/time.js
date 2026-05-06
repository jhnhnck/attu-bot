/**
 * Time/Calendar Module
 * Handles time and calendar utilities
 */

import { api } from './api.js';

/**
 * Get current time status for a guild
 */
export async function getTimeStatus(guildId) {
    return api.getTime(guildId);
}

/**
 * Get year span for a specific year
 */
export async function getYearSpan(guildId, year) {
    return api.getYearSpan(guildId, year);
}

/**
 * Format a Unix timestamp to readable date/time
 * @param {number} timestamp - Unix timestamp (seconds)
 * @param {boolean} includeTime - Whether to include time in output
 * @param {boolean} includeSeconds - Whether to include seconds (only if includeTime is true)
 * @returns {string} Formatted date/time string
 */
export function formatTimestamp(timestamp, includeTime = true, includeSeconds = false) {
    const date = new Date(timestamp * 1000);

    const options = {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
    };

    if (includeTime) {
        options.hour = '2-digit';
        options.minute = '2-digit';
        if (includeSeconds) {
            options.second = '2-digit';
        }
    }

    return date.toLocaleString(undefined, options);
}

/**
 * Format timestamp as ISO date string (YYYY-MM-DD)
 * @param {number} timestamp - Unix timestamp (seconds)
 * @returns {string} ISO date string
 */
export function formatISODate(timestamp) {
    const date = new Date(timestamp * 1000);
    return date.toISOString().split('T')[0];
}

/**
 * Format timestamp as relative time (e.g., "2 hours ago", "in 3 days")
 * @param {number} timestamp - Unix timestamp (seconds)
 * @returns {string} Relative time string
 */
export function formatRelativeTime(timestamp) {
    const now = Date.now() / 1000;
    const diff = timestamp - now;
    const absDiff = Math.abs(diff);

    const units = [
        { name: 'year', seconds: 31536000 },
        { name: 'month', seconds: 2592000 },
        { name: 'week', seconds: 604800 },
        { name: 'day', seconds: 86400 },
        { name: 'hour', seconds: 3600 },
        { name: 'minute', seconds: 60 },
        { name: 'second', seconds: 1 },
    ];

    for (const unit of units) {
        const count = Math.floor(absDiff / unit.seconds);
        if (count >= 1) {
            const unitName = count === 1 ? unit.name : `${unit.name}s`;
            return diff < 0
                ? `${count} ${unitName} ago`
                : `in ${count} ${unitName}`;
        }
    }

    return 'just now';
}

/**
 * Format duration in days with more detail
 * @param {number} days - Number of days
 * @param {boolean} detailed - Whether to break down into years/months/days
 * @returns {string} Formatted duration string
 */
export function formatDuration(days, detailed = false) {
    if (days < 1) {
        return '< 1 day';
    }
    if (days === 1) {
        return '1 day';
    }

    if (!detailed) {
        return `${days} days`;
    }

    // Break down into years, months, days
    const years = Math.floor(days / 365);
    const remainingDays = days % 365;
    const months = Math.floor(remainingDays / 30);
    const finalDays = remainingDays % 30;

    const parts = [];
    if (years > 0) {
        parts.push(`${years} ${years === 1 ? 'year' : 'years'}`);
    }
    if (months > 0) {
        parts.push(`${months} ${months === 1 ? 'month' : 'months'}`);
    }
    if (finalDays > 0 || parts.length === 0) {
        parts.push(`${finalDays} ${finalDays === 1 ? 'day' : 'days'}`);
    }

    return parts.join(', ');
}

/**
 * Format seconds into human-readable duration
 * @param {number} seconds - Duration in seconds
 * @returns {string} Formatted duration
 */
export function formatSeconds(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
        return `${hours}h ${minutes}m ${secs}s`;
    } else if (minutes > 0) {
        return `${minutes}m ${secs}s`;
    } else {
        return `${secs}s`;
    }
}

/**
 * Parse HH:MM time string to minutes since midnight
 * @param {string} timeStr - Time string in HH:MM format
 * @returns {number} Minutes since midnight
 */
export function parseTimeToMinutes(timeStr) {
    const [hours, minutes] = timeStr.split(':').map(Number);
    return hours * 60 + minutes;
}

/**
 * Format minutes since midnight to HH:MM string
 * @param {number} minutes - Minutes since midnight
 * @returns {string} Time string in HH:MM format
 */
export function formatMinutesToTime(minutes) {
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}`;
}

/**
 * Get days until a future timestamp
 * @param {number} timestamp - Unix timestamp (seconds)
 * @returns {number} Days until timestamp (negative if in past)
 */
export function getDaysUntil(timestamp) {
    const now = Date.now() / 1000;
    const diff = timestamp - now;
    return Math.ceil(diff / 86400);
}

/**
 * Check if a timestamp is in the past
 * @param {number} timestamp - Unix timestamp (seconds)
 * @returns {boolean} True if timestamp is in the past
 */
export function isPast(timestamp) {
    return timestamp < (Date.now() / 1000);
}

/**
 * Check if a timestamp is in the future
 * @param {number} timestamp - Unix timestamp (seconds)
 * @returns {boolean} True if timestamp is in the future
 */
export function isFuture(timestamp) {
    return timestamp > (Date.now() / 1000);
}

/**
 * Get current Unix timestamp in seconds
 * @returns {number} Current Unix timestamp
 */
export function now() {
    return Math.floor(Date.now() / 1000);
}
