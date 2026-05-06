/**
 * Epoch Config Page Controller
 */

import { api } from '../modules/api.js';
import { loadGuildData, populateField } from '../modules/guild-config-loader.js';
import { initSaveManager } from '../modules/save-manager.js';
import { showLoadingOverlayDelayed } from '../modules/ui.js';

export async function initEpochPage(guildId) {
    const form = document.getElementById('epoch-form');
    if (!form) {return;}

    const loader = showLoadingOverlayDelayed(form);

    try {
        const { config } = await loadGuildData(guildId);

        populateField('time', config.epoch.time);
        populateField('year', config.epoch.year);
        populateField('length', config.epoch.length);
        populateField('paused', config.epoch.paused);
        populateField('rollover_time', config.epoch.rollover_time);
    } catch (err) {
        console.error('Failed to load epoch config:', err);
    } finally {
        loader.hide();
    }

    initSaveManager({
        formId: 'epoch-form',
        save: async (data) => {
            // convert rollover_time HH:MM to rollover_minutes for the backend
            if (data.rollover_time && data.rollover_time.includes(':')) {
                const [h, m] = data.rollover_time.split(':');
                data.rollover_minutes = parseInt(h, 10) * 60 + parseInt(m, 10);
                delete data.rollover_time;
            }
            // ensure numeric fields are numbers
            data.time = parseInt(data.time, 10) || 0;
            data.year = parseInt(data.year, 10) || 1;
            data.length = parseInt(data.length, 10) || 14;
            return api.patchEpoch(guildId, data);
        },
    });
}
