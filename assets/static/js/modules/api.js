/**
 * API Client Module
 * Parallels routes.py - handles all API communication
 */

export class ApiClient {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl;
    }

    /**
     * Convert string IDs to BigInt for Discord snowflakes
     * Recursively processes objects and arrays
     */
    parseBigInts(obj) {
        if (obj === null || obj === undefined) {return obj;}

        if (Array.isArray(obj)) {
            return obj.map(item => this.parseBigInts(item));
        }

        if (typeof obj === 'object') {
            const result = {};
            for (const [key, value] of Object.entries(obj)) {
                // convert string IDs to BigInt (specific field names that are IDs)
                // use exact matches or suffix matches to avoid false positives like "admin" matching "role"
                const isIdField =
                    key === 'id' ||
                    key === 'guild_id' ||
                    key === 'channel' ||
                    key === 'message' ||
                    key.endsWith('_id') ||
                    key.endsWith('_channel') ||
                    key.endsWith('_role') ||
                    key.endsWith('_user') ||
                    key === 'valid_bots';

                if (typeof value === 'string' && isIdField && /^\d+$/.test(value)) {
                    result[key] = BigInt(value);
                } else if (Array.isArray(value) && isIdField) {
                    // convert arrays of ID strings (e.g. valid_bots) element-wise
                    result[key] = value.map(item =>
                        typeof item === 'string' && /^\d+$/.test(item) ? BigInt(item) : item
                    );
                } else if (typeof value === 'object' || Array.isArray(value)) {
                    result[key] = this.parseBigInts(value);
                } else {
                    result[key] = value;
                }
            }
            return result;
        }

        return obj;
    }

    /**
     * Convert BigInt values to strings for JSON serialization
     */
    stringifyBigInts(obj) {
        if (obj === null || obj === undefined) {return obj;}

        if (typeof obj === 'bigint') {
            return obj.toString();
        }

        if (Array.isArray(obj)) {
            return obj.map(item => this.stringifyBigInts(item));
        }

        if (typeof obj === 'object') {
            const result = {};
            for (const [key, value] of Object.entries(obj)) {
                result[key] = this.stringifyBigInts(value);
            }
            return result;
        }

        return obj;
    }

    /**
     * Ensure a value is a string (handles BigInt URL params)
     */
    toParam(value) {
        return typeof value === 'bigint' ? value.toString() : value;
    }

    /**
     * Generic fetch wrapper with error handling and BigInt support
     */
    async fetch(url, options = {}) {
        try {
            // Convert BigInts to strings in request body
            if (options.body) {
                const bodyData = JSON.parse(options.body);
                options.body = JSON.stringify(this.stringifyBigInts(bodyData));
            }

            const response = await fetch(`${this.baseUrl}${url}`, {
                ...options,
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]')?.content ?? '',
                    ...options.headers,
                },
            });

            const data = await response.json();

            if (!response.ok) {
                const error = new Error(data.error || `HTTP error! status: ${response.status}`);
                error.status = response.status;
                error.details = data.details || null;
                throw error;
            }

            // Parse string IDs back to BigInt
            return this.parseBigInts(data);
        } catch (error) {
            console.error('API fetch error:', error);
            throw error;
        }
    }

    // Guild endpoints
    async getGuilds() {
        return this.fetch('/api/guilds');
    }

    async getGuild(guildId) {
        return this.fetch(`/api/guilds/${this.toParam(guildId)}`);
    }

    async saveGuild(guildId, data) {
        return this.fetch(`/api/guilds/${this.toParam(guildId)}`, {
            method: 'POST',
            body: JSON.stringify(this.stringifyBigInts(data)),
        });
    }

    // Years endpoints
    async getYears(guildId) {
        return this.fetch(`/api/guilds/${this.toParam(guildId)}/years`);
    }

    async getYear(guildId, year) {
        return this.fetch(`/api/guilds/${this.toParam(guildId)}/years/${year}`);
    }

    async getLatestYear(guildId) {
        return this.fetch(`/api/guilds/${this.toParam(guildId)}/years/latest`);
    }

    async createYear(guildId, year, data) {
        return this.fetch(`/api/guilds/${this.toParam(guildId)}/years/${year}`, {
            method: 'POST',
            body: JSON.stringify(this.stringifyBigInts(data)),
        });
    }

    async deleteYear(guildId, year) {
        return this.fetch(`/api/guilds/${this.toParam(guildId)}/years/${year}`, {
            method: 'DELETE',
        });
    }

    // Markers endpoints
    async getMarkers(guildId) {
        return this.fetch(`/api/guilds/${this.toParam(guildId)}/markers`);
    }

    async getMarker(guildId, year) {
        return this.fetch(`/api/guilds/${this.toParam(guildId)}/markers/${year}`);
    }

    async getMarkerTimestamp(guildId, year) {
        return this.fetch(`/api/guilds/${this.toParam(guildId)}/markers/${year}/timestamp`);
    }

    async createMarker(guildId, year, data) {
        return this.fetch(`/api/guilds/${this.toParam(guildId)}/markers/${year}`, {
            method: 'POST',
            body: JSON.stringify(this.stringifyBigInts(data)),
        });
    }

    async deleteMarker(guildId, year) {
        return this.fetch(`/api/guilds/${this.toParam(guildId)}/markers/${year}`, {
            method: 'DELETE',
        });
    }

    // Time/Calendar endpoints
    async getTime(guildId) {
        return this.fetch(`/api/guilds/${this.toParam(guildId)}/time`);
    }

    async getYearSpan(guildId, year) {
        return this.fetch(`/api/guilds/${this.toParam(guildId)}/time/year-span/${year}`);
    }

    // Theme endpoints
    async getTheme() {
        return this.fetch('/api/theme');
    }

    async saveTheme(data) {
        return this.fetch('/api/theme', {
            method: 'POST',
            body: JSON.stringify(this.stringifyBigInts(data)),
        });
    }

    // System endpoints
    async getSystem() {
        return this.fetch('/api/system');
    }

    async saveSystem(data) {
        return this.fetch('/api/system', {
            method: 'POST',
            body: JSON.stringify(this.stringifyBigInts(data)),
        });
    }

    // Chat config endpoints
    async getChat() {
        return this.fetch('/api/chat');
    }

    async saveChat(data) {
        return this.fetch('/api/chat', {
            method: 'POST',
            body: JSON.stringify(this.stringifyBigInts(data)),
        });
    }

    // Admin/Stats endpoints
    async getStats() {
        return this.fetch('/api/admin/stats');
    }

    // Discord endpoints
    async getChannels(guildId) {
        return this.fetch(`/api/guilds/${this.toParam(guildId)}/channels`);
    }

    async getRoles(guildId) {
        return this.fetch(`/api/guilds/${this.toParam(guildId)}/roles`);
    }

    async getGuildInfo(guildId) {
        return this.fetch(`/api/guilds/${this.toParam(guildId)}/info`);
    }

    // Audit log endpoints
    async getAuditLogs(params = {}) {
        const queryString = new URLSearchParams(params).toString();
        return this.fetch(`/api/audit?${queryString}`);
    }
}

// Export singleton instance
export const api = new ApiClient();
