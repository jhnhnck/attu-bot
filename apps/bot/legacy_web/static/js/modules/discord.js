/**
 * Discord Integration Module
 * Parallels discord_integration.py
 */

import { api } from './api.js';

/**
 * Cache for Discord data
 */
const cache = new Map();
const CACHE_TTL = 300000; // 5 minutes

/**
 * Get Discord channels for a guild with caching
 */
export async function getGuildChannels(guildId) {
    const cacheKey = `channels:${guildId}`;
    const cached = cache.get(cacheKey);

    if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
        return cached.data;
    }

    const result = await api.getChannels(guildId);
    cache.set(cacheKey, {
        data: result.channels,
        timestamp: Date.now(),
    });

    return result.channels;
}

/**
 * Get Discord roles for a guild with caching
 */
export async function getGuildRoles(guildId) {
    const cacheKey = `roles:${guildId}`;
    const cached = cache.get(cacheKey);

    if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
        return cached.data;
    }

    const result = await api.getRoles(guildId);
    cache.set(cacheKey, {
        data: result.roles,
        timestamp: Date.now(),
    });

    return result.roles;
}

/**
 * Invalidate cache for a guild
 */
export function invalidateGuildCache(guildId) {
    cache.delete(`channels:${guildId}`);
    cache.delete(`roles:${guildId}`);
}
