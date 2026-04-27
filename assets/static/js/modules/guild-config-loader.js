/**
 * Guild Config Loader
 * Shared logic for loading guild config, discord channels, and discord roles
 * used by per-section config pages.
 */

import { api } from './api.js';

/**
 * Try to read SSR data from a JSON script block injected by the server.
 * Returns null if no SSR data is present or parsing fails.
 * @returns {object|null}
 */
export function getSSRData() {
    const el = document.getElementById('ssr-data');
    if (!el) {return null;}
    try {
        return JSON.parse(el.textContent);
    } catch {
        return null;
    }
}

/**
 * Load full guild config and discord data.
 * Prefers SSR data if available, falls back to API fetch.
 * @param {string|number} guildId
 * @returns {Promise<{config: object, channels: Array, roles: Array}>}
 */
export async function loadGuildData(guildId) {
    const ssr = getSSRData();
    if (ssr && ssr.config) {
        return {
            config: ssr.config,
            channels: ssr.channels || [],
            roles: ssr.roles || [],
        };
    }

    const [configData, channelsData, rolesData] = await Promise.all([
        api.getGuild(guildId),
        api.getChannels(guildId).catch(() => ({ channels: [] })),
        api.getRoles(guildId).catch(() => ({ roles: [] })),
    ]);

    return {
        config: configData,
        channels: channelsData.channels || [],
        roles: rolesData.roles || [],
    };
}

/**
 * Populate all <select> elements with CSS class discord-channel-select.
 * Groups channels by category with a separate "Threads" group at the end.
 */
export function populateChannelSelects(channels) {
    const selects = document.querySelectorAll('.discord-channel-select');
    selects.forEach(select => {
        const currentValue = select.value;
        select.innerHTML = '<option value="0">Not Set</option>';

        const threads = channels.filter(c => c.is_thread);
        const regular = channels.filter(c => !c.is_thread);
        const categories = regular.filter(c => c.type === 'category');

        categories.forEach(cat => {
            const group = document.createElement('optgroup');
            group.label = cat.name;
            regular.filter(c => c.category_id === cat.id).forEach(c => {
                const opt = document.createElement('option');
                opt.value = c.id;
                opt.textContent = c.name;
                group.appendChild(opt);
            });
            if (group.children.length > 0) {select.appendChild(group);}
        });

        const uncategorized = regular.filter(c => !c.category_id && c.type !== 'category');
        if (uncategorized.length > 0) {
            const group = document.createElement('optgroup');
            group.label = 'Other';
            uncategorized.forEach(c => {
                const opt = document.createElement('option');
                opt.value = c.id;
                opt.textContent = c.name;
                group.appendChild(opt);
            });
            select.appendChild(group);
        }

        if (threads.length > 0) {
            const group = document.createElement('optgroup');
            group.label = 'Threads';
            threads.forEach(t => {
                const opt = document.createElement('option');
                opt.value = t.id;
                opt.textContent = `\u{1F4AC} ${t.name}`;
                opt.title = `Parent: ${t.parent_name || 'Unknown'}`;
                group.appendChild(opt);
            });
            select.appendChild(group);
        }

        select.value = currentValue;
    });
}

/**
 * Populate all <select> elements with CSS class discord-role-select.
 */
export function populateRoleSelects(roles) {
    const selects = document.querySelectorAll('.discord-role-select');
    selects.forEach(select => {
        const currentValue = select.value;
        select.innerHTML = '<option value="0">Not Set</option>';
        roles.forEach(role => {
            const opt = document.createElement('option');
            opt.value = role.id;
            opt.textContent = role.name;
            if (role.color && role.color !== '0x0') {
                opt.style.color = role.color.replace('0x', '#');
            }
            select.appendChild(opt);
        });
        select.value = currentValue;
    });
}

/**
 * Set a form field value by name attribute.
 */
export function populateField(name, value) {
    const field = document.querySelector(`[name="${name}"]`);
    if (!field) {return;}
    if (field.type === 'checkbox') {
        field.checked = value;
    } else {
        field.value = value;
    }
}

/**
 * Escape HTML to prevent XSS.
 */
export function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Initialize a list field (lore_channels, canon_channels, marker_users, valid_bots).
 * Stores comma-separated values in a hidden input and renders an <ul> of items.
 */
export function initListField(fieldName, items, names) {
    const hiddenInput = document.getElementById(fieldName);
    const listContainer = document.getElementById(`list-${fieldName}`);
    if (!hiddenInput || !listContainer) {return;}

    listContainer.innerHTML = '';
    const itemList = (items || []).map(String);
    hiddenInput.value = itemList.join(',');

    let displayNames = itemList;
    if (names && Array.isArray(names) && names.some(n => n != null && n !== '')) {
        displayNames = names;
    }

    itemList.forEach((item, index) => {
        if (!item) {return;}
        const displayName = displayNames[index] || item;
        _renderListItem(listContainer, fieldName, item, displayName);
    });
}

function _renderListItem(container, fieldName, value, displayName) {
    const li = document.createElement('li');
    li.className = 'list-group-item d-flex justify-content-between align-items-center';
    const display = displayName && displayName !== value ? `${displayName} (${value})` : value;
    li.innerHTML = `
        <span>${escapeHtml(display)}</span>
        <button type="button" class="btn btn-sm btn-outline-danger list-remove-btn" data-field="${fieldName}" data-value="${value}">
            <i data-feather="x"></i>
        </button>
    `;
    li.querySelector('.list-remove-btn').addEventListener('click', () => {
        _removeListItem(fieldName, value);
    });
    container.appendChild(li);
    if (typeof feather !== 'undefined') {feather.replace();}
}

function _removeListItem(fieldName, value) {
    const hiddenInput = document.getElementById(fieldName);
    if (!hiddenInput) {return;}
    const items = hiddenInput.value ? hiddenInput.value.split(',') : [];
    const newItems = items.filter(item => item !== String(value));
    initListField(fieldName, newItems);
    // trigger change event so save-manager picks it up
    hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
}

/**
 * Add an item to a list field from an input element.
 */
export function addListItem(fieldName, inputId) {
    const input = document.getElementById(inputId);
    const hiddenInput = document.getElementById(fieldName);
    if (!input || !hiddenInput) {return;}

    const value = input.value.trim();
    if (!value) {return;}

    const currentItems = hiddenInput.value ? hiddenInput.value.split(',') : [];
    if (currentItems.includes(value)) {return;}

    currentItems.push(value);
    hiddenInput.value = currentItems.join(',');

    const listContainer = document.getElementById(`list-${fieldName}`);
    if (listContainer) {_renderListItem(listContainer, fieldName, value, value);}

    input.value = '';
    hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
}
