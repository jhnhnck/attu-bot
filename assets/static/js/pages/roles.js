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
        save: async (data) => {
            data.announcements = parseInt(data.announcements, 10) || 0;
            data.bot_color = parseInt(data.bot_color, 10) || 0;
            data.trees_admin_role = parseInt(data.trees_admin_role, 10) || 0;
            data.trees_user_role = parseInt(data.trees_user_role, 10) || 0;
            return api.patchRoles(guildId, data);
        },
    });
}
