/**
 * Starboard Config Page Controller
 */

import { api } from '../modules/api.js';
import { loadGuildData, populateChannelSelects, populateField, initListField, addListItem, escapeHtml } from '../modules/guild-config-loader.js';
import { initSaveManager } from '../modules/save-manager.js';
import { showLoadingOverlayDelayed } from '../modules/ui.js';

let emojiMap = {};

function renderEmojiTable() {
    const tbody = document.getElementById('emoji-table-body');
    if (!tbody) {return;}
    tbody.innerHTML = '';
    for (const [emoji, color] of Object.entries(emojiMap)) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(emoji)}</td>
            <td><span style="display:inline-block;width:20px;height:20px;background:${color};border:1px solid #ccc;border-radius:3px;vertical-align:middle;"></span> ${escapeHtml(color)}</td>
            <td><button type="button" class="btn btn-sm btn-outline-danger emoji-remove-btn" data-emoji="${escapeHtml(emoji)}">Remove</button></td>
        `;
        tr.querySelector('.emoji-remove-btn').addEventListener('click', () => {
            delete emojiMap[emoji];
            renderEmojiTable();
        });
        tbody.appendChild(tr);
    }
    const hidden = document.getElementById('starboard_emojis');
    if (hidden) {
        hidden.value = JSON.stringify(emojiMap);
        hidden.dispatchEvent(new Event('change', { bubbles: true }));
    }
}

export async function initStarboardPage(guildId) {
    const form = document.getElementById('starboard-form');
    if (!form) {return;}

    const loader = showLoadingOverlayDelayed(form);

    try {
        const { config, channels } = await loadGuildData(guildId);

        populateChannelSelects(channels);
        populateField('channel_id', config.starboard?.channel_id);

        if (config.starboard?.emojis) {
            emojiMap = { ...config.starboard.emojis };
            renderEmojiTable();
        }
        initListField('starboard_valid_bots', config.starboard?.valid_bots, config.starboard?.valid_bots_names);
    } catch (err) {
        console.error('Failed to load starboard config:', err);
    } finally {
        loader.hide();
    }

    initSaveManager({
        formId: 'starboard-form',
        save: async (data) => {
            // inject emoji map directly
            data.emojis = { ...emojiMap };
            data.channel_id = parseInt(data.channel_id, 10) || 0;
            data.valid_bots = data.valid_bots || '';
            return api.patchStarboard(guildId, data);
        },
    });

    // add emoji
    document.getElementById('add-emoji-btn')?.addEventListener('click', () => {
        const emojiInput = document.getElementById('emoji_input');
        const colorInput = document.getElementById('emoji_color_input');
        if (!emojiInput || !colorInput) {return;}
        const emoji = emojiInput.value.trim();
        const color = colorInput.value.trim();
        if (!emoji) {return;}
        emojiMap[emoji] = color;
        emojiInput.value = '';
        renderEmojiTable();
    });

    // color preview sync
    const emojiColorInput = document.getElementById('emoji_color_input');
    if (emojiColorInput) {
        emojiColorInput.addEventListener('input', function() {
            const val = this.value.trim();
            const preview = document.getElementById('emoji_color_preview');
            if (/^#[0-9a-fA-F]{6}$/.test(val)) {
                if (preview) {preview.style.background = val;}
                this.classList.remove('is-invalid');
            } else {
                this.classList.add('is-invalid');
            }
        });
    }

    // add valid bot
    document.getElementById('add-valid-bot-btn')?.addEventListener('click', () => {
        addListItem('starboard_valid_bots', 'valid_bot_input');
    });
}
