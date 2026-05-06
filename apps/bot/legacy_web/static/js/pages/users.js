/**
 * Users Config Page Controller
 */

import { api } from '../modules/api.js';
import { loadGuildData, initListField, addListItem } from '../modules/guild-config-loader.js';
import { initSaveManager } from '../modules/save-manager.js';
import { showLoadingOverlayDelayed } from '../modules/ui.js';

export async function initUsersPage(guildId) {
    const form = document.getElementById('users-form');
    if (!form) {return;}

    const loader = showLoadingOverlayDelayed(form);

    try {
        const { config } = await loadGuildData(guildId);
        initListField('marker_users', config.users.markers, config.users.markers_names);
    } catch (err) {
        console.error('Failed to load users config:', err);
    } finally {
        loader.hide();
    }

    initSaveManager({
        formId: 'users-form',
        save: async (data) => {
            data.markers = data.markers || '';
            return api.patchUsers(guildId, data);
        },
    });

    document.getElementById('add-marker-user-btn')?.addEventListener('click', () => {
        addListItem('marker_users', 'marker_user_input');
    });
}
