/**
 * Roles Config Page Controller
 */

import { api } from '../modules/api.js';
import { loadGuildData, populateField, populateRoleSelects } from '../modules/guild-config-loader.js';
import { initSaveManager } from '../modules/save-manager.js';
import { showLoadingOverlayDelayed } from '../modules/ui.js';

export async function initRolesPage(guildId) {
    const form = document.getElementById('roles-form');
    if (!form) {return;}

    const loader = showLoadingOverlayDelayed(form);

    try {
        const { config, roles } = await loadGuildData(guildId);

        populateRoleSelects(roles);
        populateField('announcements', config.roles.announcements);
        populateField('bot_color', config.roles.bot_color);
        populateField('trees_admin_role', config.roles.trees_admin_role);
        populateField('trees_user_role', config.roles.trees_user_role);
    } catch (err) {
        console.error('Failed to load roles config:', err);
    } finally {
        loader.hide();
    }

    initSaveManager({
        formId: 'roles-form',
        // role IDs are 19-digit Discord snowflakes; parseInt would round them
        // past Number.MAX_SAFE_INTEGER. send strings - pydantic int accepts them.
        save: async (data) => api.patchRoles(guildId, data),
    });
}
