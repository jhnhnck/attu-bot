/**
 * Channels Config Page Controller
 */

import { api } from '../modules/api.js';
import { loadGuildData, populateChannelSelects, populateField, initListField, addListItem } from '../modules/guild-config-loader.js';
import { initSaveManager } from '../modules/save-manager.js';
import { showLoadingOverlayDelayed } from '../modules/ui.js';

export async function initChannelsPage(guildId) {
    const form = document.getElementById('channels-form');
    if (!form) {return;}

    const loader = showLoadingOverlayDelayed(form);

    try {
        const { config, channels } = await loadGuildData(guildId);

        populateChannelSelects(channels);

        populateField('activity', config.channels.activity);
        populateField('announcements', config.channels.announcements);
        populateField('year_vc', config.channels.year_vc);
        populateField('year_links', config.channels.year_links);
        populateField('meta_chat', config.channels.meta_chat);
        populateField('general', config.channels.general);
        populateField('logs', config.channels.logs);
        populateField('eggs', config.channels.eggs);

        initListField('lore_channels', config.channels.lore_channels, config.channels.lore_channels_names);
        initListField('canon_channels', config.channels.canon_channels, config.channels.canon_channels_names);
    } catch (err) {
        console.error('Failed to load channels config:', err);
    } finally {
        loader.hide();
    }

    // save manager
    const _manager = initSaveManager({
        formId: 'channels-form',
        save: async (data) => {
            // parse list fields back from comma-separated
            data.lore_channels = data.lore_channels || '';
            data.canon_channels = data.canon_channels || '';
            const resp = await api.patchChannels(guildId, data);
            return resp;
        },
    });

    // list field add buttons
    document.getElementById('add-lore-btn')?.addEventListener('click', () => {
        addListItem('lore_channels', 'lore_channel_input');
    });
    document.getElementById('add-canon-btn')?.addEventListener('click', () => {
        addListItem('canon_channels', 'canon_channel_input');
    });

    // refresh discord data
    document.getElementById('refresh-discord-btn')?.addEventListener('click', async () => {
        const btn = document.getElementById('refresh-discord-btn');
        btn.disabled = true;
        try {
            await api.fetch(`/api/guilds/${guildId}/refresh`, { method: 'POST' });
            const { channels } = await loadGuildData(guildId);
            populateChannelSelects(channels);
        } finally {
            btn.disabled = false;
        }
    });
}
