/**
 * Guild Toggle Component
 * switches the active guild via POST /api/set-guild and reloads
 */

import { api } from '../modules/api.js';

export function initGuildToggle() {
    const primaryBtn = document.getElementById('guild-toggle-primary');
    const secondaryBtn = document.getElementById('guild-toggle-secondary');
    if (!primaryBtn || !secondaryBtn) {return;}

    async function switchGuild(btn) {
        if (btn.classList.contains('btn-primary')) {return;} // already active
        const targetId = btn.dataset.guildId;
        if (!targetId) {return;}
        try {
            await api.setGuild(targetId);
            window.location.reload();
        } catch (err) {
            console.error('Failed to switch guild:', err);
        }
    }

    primaryBtn.addEventListener('click', () => switchGuild(primaryBtn));
    secondaryBtn.addEventListener('click', () => switchGuild(secondaryBtn));
}
