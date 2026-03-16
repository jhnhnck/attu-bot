/**
 * Chat Config Page Controller
 * Handles the /chat runtime configuration editor
 */

import { getChatConfig, saveChatConfig } from '../modules/config.js';
import { showSuccess, showErrorNotification, setLoading } from '../modules/ui.js';

const CHANNEL_TYPES = ['discussion', 'roleplay', 'shitpost', 'forum'];

/** @type {Object|null} last-loaded config, used for reset */
let _loadedConfig = null;

export function initChatConfig() {
    document.getElementById('save-chat-btn')?.addEventListener('click', onSave);
    document.getElementById('reset-chat-btn')?.addEventListener('click', onReset);
    document.getElementById('add-channel-btn')?.addEventListener('click', () => addChannelRow('', '', '', 'discussion', true));
    document.getElementById('add-nation-btn')?.addEventListener('click', () => addNationRow('', ''));

    loadConfig();
}

async function loadConfig() {
    try {
        const cfg = await getChatConfig();
        _loadedConfig = cfg;
        populateForm(cfg);
    } catch (err) {
        console.error('Failed to load chat config:', err);
        showErrorNotification('Failed to load chat configuration');
    }
}

function populateForm(cfg) {
    // toggles
    setChecked('ingest_wiki', cfg.ingest_wiki);
    setChecked('ingest_discord', cfg.ingest_discord);
    setChecked('ingest_documents', cfg.ingest_documents);

    // discord ingestion settings
    setValue('discord_lookback_hours', cfg.discord_lookback_hours);
    setValue('discord_window_minutes', cfg.discord_window_minutes);
    setValue('noise_filter_min_tokens', cfg.noise_filter_min_tokens);
    setValue('character_log_channel_id', cfg.character_log_channel_id ?? '');
    setValue('ignored_user_ids', cfg.ignored_user_ids.join(', '));

    // wiki
    setValue('wiki_namespaces', cfg.wiki_namespaces.join(', '));

    // retrieval
    setValue('retrieval_top_k_wiki', cfg.retrieval_top_k_wiki);
    setValue('retrieval_top_k_discord', cfg.retrieval_top_k_discord);
    setValue('retrieval_top_k_documents', cfg.retrieval_top_k_documents);
    setValue('retrieval_top_k_images', cfg.retrieval_top_k_images);

    // dynamic tables
    clearTable('channels-tbody');
    for (const [cid, ch] of Object.entries(cfg.chat_channels)) {
        addChannelRow(cid, ch.name, ch.description, ch.channel_type, ch.ingest);
    }

    clearTable('nations-tbody');
    for (const [uid, nation] of Object.entries(cfg.user_nations)) {
        addNationRow(uid, nation);
    }

    if (typeof feather !== 'undefined') feather.replace();
}

function collectForm() {
    const chat_channels = {};
    for (const row of document.querySelectorAll('#channels-tbody tr')) {
        const cid = row.querySelector('.ch-id')?.value.trim();
        if (!cid) continue;
        chat_channels[cid] = {
            name: row.querySelector('.ch-name')?.value ?? '',
            description: row.querySelector('.ch-desc')?.value ?? '',
            channel_type: row.querySelector('.ch-type')?.value ?? 'discussion',
            ingest: row.querySelector('.ch-ingest')?.checked ?? true,
        };
    }

    const user_nations = {};
    for (const row of document.querySelectorAll('#nations-tbody tr')) {
        const uid = row.querySelector('.nat-uid')?.value.trim();
        const nation = row.querySelector('.nat-name')?.value.trim();
        if (uid && nation) user_nations[uid] = nation;
    }

    const ignoredRaw = document.getElementById('ignored_user_ids')?.value ?? '';
    const ignored_user_ids = ignoredRaw.split(',').map(s => s.trim()).filter(Boolean).map(Number);

    const namespacesRaw = document.getElementById('wiki_namespaces')?.value ?? '0';
    const wiki_namespaces = namespacesRaw.split(',').map(s => s.trim()).filter(Boolean);

    const charLogRaw = parseInt(document.getElementById('character_log_channel_id')?.value ?? '0');

    return {
        ingest_wiki: document.getElementById('ingest_wiki')?.checked ?? true,
        ingest_discord: document.getElementById('ingest_discord')?.checked ?? true,
        ingest_documents: document.getElementById('ingest_documents')?.checked ?? true,
        discord_lookback_hours: parseInt(document.getElementById('discord_lookback_hours')?.value ?? 6),
        discord_window_minutes: parseInt(document.getElementById('discord_window_minutes')?.value ?? 30),
        noise_filter_min_tokens: parseInt(document.getElementById('noise_filter_min_tokens')?.value ?? 20),
        character_log_channel_id: charLogRaw || null,
        ignored_user_ids,
        wiki_namespaces,
        retrieval_top_k_wiki: parseInt(document.getElementById('retrieval_top_k_wiki')?.value ?? 5),
        retrieval_top_k_discord: parseInt(document.getElementById('retrieval_top_k_discord')?.value ?? 5),
        retrieval_top_k_documents: parseInt(document.getElementById('retrieval_top_k_documents')?.value ?? 3),
        retrieval_top_k_images: parseInt(document.getElementById('retrieval_top_k_images')?.value ?? 2),
        chat_channels,
        user_nations,
    };
}

async function onSave() {
    const btn = document.getElementById('save-chat-btn');
    setLoading(btn, true);
    try {
        const data = collectForm();
        await saveChatConfig(data);
        showSuccess('Chat configuration saved');
    } catch (err) {
        console.error('Failed to save chat config:', err);
        showErrorNotification(err.message ?? 'Failed to save chat configuration');
    } finally {
        setLoading(btn, false);
    }
}

function onReset() {
    if (_loadedConfig) {
        populateForm(_loadedConfig);
    } else {
        loadConfig();
    }
}

// ========== Dynamic table helpers ==========

function addChannelRow(cid, name, description, channelType, ingest) {
    const tbody = document.getElementById('channels-tbody');
    if (!tbody) return;

    const typeOptions = CHANNEL_TYPES.map(t =>
        `<option value="${t}"${t === channelType ? ' selected' : ''}>${t}</option>`
    ).join('');

    const tr = document.createElement('tr');
    tr.innerHTML = `
        <td><input type="text" class="form-control form-control-sm ch-id" value="${escHtml(cid)}" placeholder="channel ID" /></td>
        <td><input type="text" class="form-control form-control-sm ch-name" value="${escHtml(name)}" placeholder="display name" /></td>
        <td><input type="text" class="form-control form-control-sm ch-desc" value="${escHtml(description)}" placeholder="short description" /></td>
        <td><select class="form-select form-select-sm ch-type">${typeOptions}</select></td>
        <td class="text-center"><input type="checkbox" class="form-check-input ch-ingest"${ingest ? ' checked' : ''} /></td>
        <td><button type="button" class="btn btn-outline-danger btn-sm remove-row-btn" aria-label="remove"><i data-feather="x"></i></button></td>
    `;
    tr.querySelector('.remove-row-btn').addEventListener('click', () => tr.remove());
    tbody.appendChild(tr);
    if (typeof feather !== 'undefined') feather.replace();
}

function addNationRow(uid, nation) {
    const tbody = document.getElementById('nations-tbody');
    if (!tbody) return;

    const tr = document.createElement('tr');
    tr.innerHTML = `
        <td><input type="text" class="form-control form-control-sm nat-uid" value="${escHtml(uid)}" placeholder="user ID" /></td>
        <td><input type="text" class="form-control form-control-sm nat-name" value="${escHtml(nation)}" placeholder="nation name" /></td>
        <td><button type="button" class="btn btn-outline-danger btn-sm remove-row-btn" aria-label="remove"><i data-feather="x"></i></button></td>
    `;
    tr.querySelector('.remove-row-btn').addEventListener('click', () => tr.remove());
    tbody.appendChild(tr);
    if (typeof feather !== 'undefined') feather.replace();
}

function clearTable(tbodyId) {
    const tbody = document.getElementById(tbodyId);
    if (tbody) tbody.innerHTML = '';
}

// ========== Utilities ==========

function setValue(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value ?? '';
}

function setChecked(id, value) {
    const el = document.getElementById(id);
    if (el) el.checked = !!value;
}

function escHtml(str) {
    return String(str ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
