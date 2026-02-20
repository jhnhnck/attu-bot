/**
 * Markers Module
 * Handles year marker data
 */

import { api } from './api.js';

export class YearMarker {
    /**
     * Create a YearMarker instance
     * @param {Object} data - Marker data from API (BigInt already parsed by api.js)
     */
    constructor(data = {}) {
        // Handle BigInt for channel and message (Discord snowflakes)
        this.channel = data.channel ? BigInt(data.channel) : BigInt(0);
        this.message = data.message ? BigInt(data.message) : BigInt(0);
        this.year = data.year || 1;
        this.exact = data.exact || false;
        this.wiki_page = data.wiki_page || false;
    }

    /**
     * Convert to JSON for API submission
     * BigInt values will be stringified by api.js
     */
    toJSON() {
        return {
            channel: this.channel,
            message: this.message,
            year: this.year,
            exact: this.exact,
            wiki_page: this.wiki_page,
        };
    }

    /**
     * Get the Discord message URL
     * @param {string} guildId - The guild ID (needed for URL construction)
     * @returns {string} Discord message URL
     */
    getMessageUrl(guildId) {
        return `https://discord.com/channels/${guildId}/${this.channel}/${this.message}`;
    }

    /**
     * Extract timestamp from Discord snowflake message ID
     * @returns {Date} Date object from snowflake
     */
    getTimestamp() {
        // Discord snowflake format: timestamp << 22 + shard_id << 17 + worker_id << 12 + sequence
        const snowflake = this.message;
        const timestamp = (snowflake >> 22n) + 1420070400000n;
        return new Date(Number(timestamp));
    }

    /**
     * Check if marker has valid data
     */
    isValid() {
        return this.channel > 0 && this.message > 0 && this.year > 0;
    }
}

/**
 * Get all markers for a guild
 * @param {BigInt|number|string} guildId - Guild ID
 * @returns {Promise<YearMarker[]>} Array of YearMarker objects
 */
export async function getAllMarkers(guildId) {
    const result = await api.getMarkers(guildId);
    return result.markers.map((m) => new YearMarker(m));
}

/**
 * Get a specific marker for a year
 * @param {BigInt|number|string} guildId - Guild ID
 * @param {number} year - Year number
 * @returns {Promise<YearMarker>} YearMarker object
 */
export async function getMarker(guildId, year) {
    const result = await api.getMarker(guildId, year);
    return new YearMarker(result);
}

/**
 * Get marker timestamp for a year
 * @param {BigInt|number|string} guildId - Guild ID
 * @param {number} year - Year number
 * @returns {Promise<number>} Unix timestamp in seconds
 */
export async function getMarkerTimestamp(guildId, year) {
    const result = await api.getMarkerTimestamp(guildId, year);
    return result.timestamp;
}

/**
 * Create or update a marker (stub - returns 501)
 * @param {BigInt|number|string} guildId - Guild ID
 * @param {number} year - Year number
 * @param {Object} data - Marker data
 * @returns {Promise<Object>} API response
 */
export async function createMarker(guildId, year, data) {
    return api.createMarker(guildId, year, data);
}

/**
 * Delete a marker (stub - returns 501)
 * @param {BigInt|number|string} guildId - Guild ID
 * @param {number} year - Year number
 * @returns {Promise<Object>} API response
 */
export async function deleteMarker(guildId, year) {
    return api.deleteMarker(guildId, year);
}
