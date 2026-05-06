/**
 * Years Module
 * Handles year record data
 */

import { api } from './api.js';

export class Year {
    /**
     * Create a Year instance
     * @param {Object} data - Year data from API (BigInt already parsed by api.js)
     */
    constructor(data = {}) {
        // Handle BigInt for guild (already parsed by api.js)
        this.guild = data.guild ? BigInt(data.guild) : BigInt(0);
        this.year = data.year || 1;
        this.start_time = data.start_time || 0;
        this.end_time = data.end_time || 0;
        this.duration = data.duration || 0;
        this.formatted = data.formatted || '';
        this.notes = data.notes || '';
    }

    /**
     * Convert to JSON for API submission
     * BigInt values will be stringified by api.js
     */
    toJSON() {
        return {
            guild: this.guild,
            year: this.year,
            start_time: this.start_time,
            end_time: this.end_time,
            duration: this.duration,
            formatted: this.formatted,
            notes: this.notes,
        };
    }

    /**
     * Check if year is complete (has end_time)
     */
    isComplete() {
        return this.end_time > 0;
    }

    /**
     * Get formatted display string
     */
    getDisplayName() {
        return this.formatted || `Year ${this.year} PC`;
    }

    /**
     * Get duration in days (computed or stored)
     */
    getDurationDays() {
        if (this.duration > 0) {
            return this.duration;
        }
        if (this.end_time > 0 && this.start_time > 0) {
            return Math.round((this.end_time - this.start_time) / 86400);
        }
        return null;
    }
}

/**
 * Get all years for a guild
 * @param {BigInt|number|string} guildId - Guild ID
 * @returns {Promise<Year[]>} Array of Year objects
 */
export async function getAllYears(guildId) {
    const result = await api.getYears(guildId);
    return result.years.map((y) => new Year(y));
}

/**
 * Get a specific year
 * @param {BigInt|number|string} guildId - Guild ID
 * @param {number} year - Year number
 * @returns {Promise<Year>} Year object
 */
export async function getYear(guildId, year) {
    const result = await api.getYear(guildId, year);
    return new Year(result);
}

/**
 * Get the latest (most recent) year
 * @param {BigInt|number|string} guildId - Guild ID
 * @returns {Promise<Year>} Latest Year object
 */
export async function getLatestYear(guildId) {
    const result = await api.getLatestYear(guildId);
    return new Year(result);
}

/**
 * Create or update a year (stub - returns 501)
 * @param {BigInt|number|string} guildId - Guild ID
 * @param {number} year - Year number
 * @param {Object} data - Year data
 * @returns {Promise<Object>} API response
 */
export async function createYear(guildId, year, data) {
    return api.createYear(guildId, year, data);
}

/**
 * Delete a year (stub - returns 501)
 * @param {BigInt|number|string} guildId - Guild ID
 * @param {number} year - Year number
 * @returns {Promise<Object>} API response
 */
export async function deleteYear(guildId, year) {
    return api.deleteYear(guildId, year);
}
