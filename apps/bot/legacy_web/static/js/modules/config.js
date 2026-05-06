/**
 * Config Models Module
 * Parallels config.py - runtime config models
 */

import { api } from './api.js';

export class GuildConfig {
    /**
     * Create a GuildConfig instance
     * @param {Object} data - Guild config data (BigInt already parsed by api.js)
     */
    constructor(data = {}) {
        // Handle BigInt for guild ID
        this.id = data.id ? BigInt(data.id) : (data.guild_id ? BigInt(data.guild_id) : BigInt(0));
        this.name = data.name || '';
        this.channels = data.channels || {};
        this.epoch = data.epoch || {};
        this.roles = data.roles || {};
        this.users = data.users || {};
        this.starboard = data.starboard || {};
    }

    toJSON() {
        return {
            channels: this.channels,
            epoch: this.epoch,
            roles: this.roles,
            users: this.users,
            starboard: this.starboard,
        };
    }

    /**
     * Get channel ID by type
     * @param {string} type - Channel type (activity, announcements, etc.)
     * @returns {BigInt} Channel ID
     */
    getChannel(type) {
        const channelId = this.channels[type];
        return channelId ? BigInt(channelId) : BigInt(0);
    }

    /**
     * Get epoch year
     * @returns {number} Epoch year
     */
    getEpochYear() {
        return this.epoch.year || 1;
    }

    /**
     * Get year length in days
     * @returns {number} Year length
     */
    getYearLength() {
        return this.epoch.length || 365;
    }

    /**
     * Check if epoch is paused
     * @returns {boolean} Paused state
     */
    isPaused() {
        return this.epoch.paused || false;
    }
}

export class ThemeConfig {
    /**
     * Create a ThemeConfig instance
     * @param {Object} data - Theme config data
     */
    constructor(data = {}) {
        this.rotation = data.rotation || 0.0;
        this.max_rate = data.max_rate || 0.5;
        this.bot_color = data.bot_color || '#ff0000';
        this.guild_color = data.guild_color || '#ffffff';
    }

    toJSON() {
        return {
            rotation: this.rotation,
            max_rate: this.max_rate,
            bot_color: this.bot_color,
            guild_color: this.guild_color,
        };
    }

    /**
     * Get rotation as degrees
     * @returns {number} Rotation in degrees
     */
    getRotationDegrees() {
        return this.rotation * 360;
    }
}

export class SystemConfig {
    /**
     * Create a SystemConfig instance
     * @param {Object} data - System config data (BigInt already parsed by api.js)
     */
    constructor(data = {}) {
        this.version = data.version || '';
        // Handle BigInt for guild IDs
        this.primary_guild = data.primary_guild ? BigInt(data.primary_guild) : BigInt(0);
        this.error_log_guild = data.error_log_guild ? BigInt(data.error_log_guild) : BigInt(0);
        this.error_log_channel = data.error_log_channel ? BigInt(data.error_log_channel) : BigInt(0);
        this.error_hook = data.error_hook || '';
    }

    toJSON() {
        return {
            primary_guild: this.primary_guild,
            error_log_guild: this.error_log_guild,
            error_log_channel: this.error_log_channel,
            error_hook: this.error_hook,
        };
    }

    /**
     * Check if error logging is configured
     * @returns {boolean} True if error logging is set up
     */
    isErrorLoggingConfigured() {
        return this.error_log_guild > 0 && this.error_log_channel > 0;
    }
}

export class ChatConfig {
    /**
     * Create a ChatConfig instance
     * @param {Object} data - Chat runtime config data
     */
    constructor(data = {}) {
        this.discord_lookback_hours = data.discord_lookback_hours ?? 6;
        this.discord_window_minutes = data.discord_window_minutes ?? 30;
        this.noise_filter_min_tokens = data.noise_filter_min_tokens ?? 20;
        this.ignored_user_ids = data.ignored_user_ids ?? [];
        this.ingest_discord = data.ingest_discord ?? true;
        this.ingest_wiki = data.ingest_wiki ?? true;
        this.ingest_documents = data.ingest_documents ?? true;
        this.wiki_namespaces = data.wiki_namespaces ?? ['0'];
        this.character_log_channel_id = data.character_log_channel_id ?? null;
        this.chat_channels = data.chat_channels ?? {};
        this.user_nations = data.user_nations ?? {};
        this.retrieval_top_k_wiki = data.retrieval_top_k_wiki ?? 5;
        this.retrieval_top_k_discord = data.retrieval_top_k_discord ?? 5;
        this.retrieval_top_k_documents = data.retrieval_top_k_documents ?? 3;
        this.retrieval_top_k_images = data.retrieval_top_k_images ?? 2;
    }

    toJSON() {
        return {
            discord_lookback_hours: this.discord_lookback_hours,
            discord_window_minutes: this.discord_window_minutes,
            noise_filter_min_tokens: this.noise_filter_min_tokens,
            ignored_user_ids: this.ignored_user_ids,
            ingest_discord: this.ingest_discord,
            ingest_wiki: this.ingest_wiki,
            ingest_documents: this.ingest_documents,
            wiki_namespaces: this.wiki_namespaces,
            character_log_channel_id: this.character_log_channel_id,
            chat_channels: this.chat_channels,
            user_nations: this.user_nations,
            retrieval_top_k_wiki: this.retrieval_top_k_wiki,
            retrieval_top_k_discord: this.retrieval_top_k_discord,
            retrieval_top_k_documents: this.retrieval_top_k_documents,
            retrieval_top_k_images: this.retrieval_top_k_images,
        };
    }
}

// ========== API Functions ==========

/**
 * Fetch and create GuildConfig
 * @param {BigInt|number|string} guildId - Guild ID
 * @returns {Promise<GuildConfig>} GuildConfig instance
 */
export async function getGuildConfig(guildId) {
    const data = await api.getGuild(guildId);
    return new GuildConfig(data);
}

/**
 * Save GuildConfig
 * @param {BigInt|number|string} guildId - Guild ID
 * @param {Object} data - Guild config data
 * @returns {Promise<Object>} API response
 */
export async function saveGuildConfig(guildId, data) {
    return api.saveGuild(guildId, data);
}

/**
 * Fetch and create ThemeConfig
 * @returns {Promise<ThemeConfig>} ThemeConfig instance
 */
export async function getThemeConfig() {
    const data = await api.getTheme();
    return new ThemeConfig(data);
}

/**
 * Save ThemeConfig
 * @param {Object} data - Theme config data
 * @returns {Promise<Object>} API response
 */
export async function saveThemeConfig(data) {
    return api.saveTheme(data);
}

/**
 * Fetch and create SystemConfig
 * @returns {Promise<SystemConfig>} SystemConfig instance
 */
export async function getSystemConfig() {
    const data = await api.getSystem();
    return new SystemConfig(data);
}

/**
 * Save SystemConfig
 * @param {Object} data - System config data
 * @returns {Promise<Object>} API response
 */
export async function saveSystemConfig(data) {
    return api.saveSystem(data);
}

/**
 * Fetch and create ChatConfig
 * @returns {Promise<ChatConfig>} ChatConfig instance
 */
export async function getChatConfig() {
    const data = await api.getChat();
    return new ChatConfig(data);
}

/**
 * Save ChatConfig
 * @param {Object} data - Chat config data
 * @returns {Promise<Object>} API response
 */
export async function saveChatConfig(data) {
    return api.saveChat(data);
}
