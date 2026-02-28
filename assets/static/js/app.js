/* AttuBot Web Interface - JavaScript (Bootstrap 5) */

// ========== Utility Functions ==========

// Show notification using Bootstrap toasts
function showNotification(message, status = 'primary') {
    // Create toast container if it doesn't exist
    let toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
        toastContainer.style.zIndex = '9999';
        document.body.appendChild(toastContainer);
    }

    const colorMap = {
        success: 'success',
        danger: 'danger',
        warning: 'warning',
        info: 'info',
        primary: 'primary',
    };

    const bgColor = colorMap[status] || 'primary';
    const toastId = `toast-${Date.now()}`;
    const toastHTML = `
        <div id="${toastId}" class="toast align-items-center text-bg-${bgColor} border-0" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">${escapeHtml(message)}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;

    toastContainer.insertAdjacentHTML('beforeend', toastHTML);
    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, { autohide: true, delay: 3000 });
    toast.show();

    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
}

// Show loading state on element
function setLoading(element, isLoading) {
    if (isLoading) {
        element.classList.add('loading');
        element.disabled = true;
        if (element.tagName === 'BUTTON') {
            const originalText = element.textContent;
            element.dataset.originalHtml = element.innerHTML;
            element.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status"></span> ${originalText}`;
        }
    } else {
        element.classList.remove('loading');
        element.disabled = false;
        if (element.tagName === 'BUTTON' && element.dataset.originalHtml) {
            element.innerHTML = element.dataset.originalHtml;
            delete element.dataset.originalHtml;
        }
    }
}

// Show loading overlay on a container element
function showLoadingOverlay(element, show = true) {
    if (show) {
        let overlay = element.querySelector('.loading-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.className = 'loading-overlay position-absolute top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center bg-body bg-opacity-75';
            overlay.style.zIndex = '1000';
            overlay.innerHTML = '<div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div>';

            const {position} = window.getComputedStyle(element);
            if (position === 'static') {
                element.style.position = 'relative';
            }

            element.appendChild(overlay);
        }
        overlay.style.display = 'flex';
    } else {
        const overlay = element.querySelector('.loading-overlay');
        if (overlay) {
            overlay.remove();
        }
    }
}

// Fetch JSON from API
async function fetchJSON(url, options = {}) {
    try {
        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]')?.content ?? '',
                ...options.headers
            }
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || `HTTP error! status: ${response.status}`);
        }

        return data;
    } catch (error) {
        console.error('Fetch error:', error);
        showNotification(error.message || 'Network error occurred', 'danger');
        throw error;
    }
}

// Serialize form to JSON with nested structure
function serializeForm(form) {
    const formData = new FormData(form);
    const data = {};

    for (const [key, value] of formData.entries()) {
        if (key.includes('.')) {
            const parts = key.split('.');
            let current = data;
            for (let i = 0; i < parts.length - 1; i++) {
                if (!current[parts[i]]) {
                    current[parts[i]] = {};
                }
                current = current[parts[i]];
            }
            const lastKey = parts[parts.length - 1];
            current[lastKey] = parseValue(value);
        } else {
            data[key] = parseValue(value);
        }
    }

    // Handle checkboxes that aren't checked
    form.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
        if (!checkbox.checked) {
            const key = checkbox.name;
            if (key.includes('.')) {
                const parts = key.split('.');
                let current = data;
                for (let i = 0; i < parts.length - 1; i++) {
                    if (!current[parts[i]]) {
                        current[parts[i]] = {};
                    }
                    current = current[parts[i]];
                }
                current[parts[parts.length - 1]] = false;
            } else {
                data[key] = false;
            }
        }
    });

    return data;
}

function parseValue(value) {
    if (!isNaN(value) && value !== '') {
        const num = Number(value);
        if (Number.isSafeInteger(num)) {
            return num;
        }
        if (value.match(/^-?\d+$/)) {
            return value;
        }
        return num;
    }
    if (value === 'true') {return true;}
    if (value === 'false') {return false;}
    if (typeof value === 'string' && value.includes(',')) {
        return value.split(',').map(v => v.trim()).filter(v => v).map(v => {
            if (!isNaN(v) && v !== '') {
                const num = Number(v);
                if (Number.isSafeInteger(num)) {return num;}
                if (v.match(/^-?\d+$/)) {return v;}
                return num;
            }
            return v;
        });
    }
    return value;
}

// ========== Guild Configuration ==========

async function loadDiscordData(guildId) {
    try {
        const [channelsData, rolesData] = await Promise.all([
            fetchJSON(`/api/guilds/${guildId}/channels`),
            fetchJSON(`/api/guilds/${guildId}/roles`)
        ]);

        const channelSelects = document.querySelectorAll('.discord-channel-select');
        channelSelects.forEach(select => {
            const currentValue = select.value;
            select.innerHTML = '<option value="0">Not Set</option>';

            // Separate threads from regular channels
            const threads = channelsData.channels.filter(c => c.is_thread);
            const regularChannels = channelsData.channels.filter(c => !c.is_thread);

            // Add regular channels (grouped by category)
            const categories = regularChannels.filter(c => c.type === 'category');
            categories.forEach(cat => {
                const group = document.createElement('optgroup');
                group.label = cat.name;
                const children = regularChannels.filter(c => c.category_id === cat.id);
                children.forEach(c => {
                    const opt = document.createElement('option');
                    opt.value = c.id;
                    opt.textContent = c.name;
                    group.appendChild(opt);
                });
                if (group.children.length > 0) {
                    select.appendChild(group);
                }
            });

            const uncategorized = regularChannels.filter(c => !c.category_id && c.type !== 'category');
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

            // Add threads in their own section at the end
            if (threads.length > 0) {
                const threadGroup = document.createElement('optgroup');
                threadGroup.label = 'Threads';
                threads.forEach(thread => {
                    const opt = document.createElement('option');
                    opt.value = thread.id;
                    opt.textContent = `💬 ${thread.name}`;
                    opt.title = `Parent: ${thread.parent_name || 'Unknown'}`;
                    threadGroup.appendChild(opt);
                });
                select.appendChild(threadGroup);
            }

            select.value = currentValue;
        });

        const roleSelects = document.querySelectorAll('.discord-role-select');
        roleSelects.forEach(select => {
            const currentValue = select.value;
            select.innerHTML = '<option value="0">Not Set</option>';
            rolesData.roles.forEach(role => {
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

    } catch (error) {
        console.error('Error loading Discord data:', error);
    }
}

async function loadGuildConfig(guildId) {
    const container = document.getElementById('guild-config-form');
    if (container) {showLoadingOverlay(container, true);}

    try {
        await loadDiscordData(guildId);
        const data = await fetchJSON(`/api/guilds/${guildId}`);

        populateField('channels.activity', data.channels.activity);
        populateField('channels.announcements', data.channels.announcements);
        populateField('channels.year_vc', data.channels.year_vc);
        populateField('channels.year_links', data.channels.year_links);
        populateField('channels.meta_chat', data.channels.meta_chat);
        populateField('channels.general', data.channels.general);
        populateField('channels.logs', data.channels.logs);

        // Use resolved channel names for display
        initListField('lore_channels', data.channels.lore_channels, data.channels.lore_channels_names);
        initListField('canon_channels', data.channels.canon_channels, data.channels.canon_channels_names);

        populateField('epoch.time', data.epoch.time);
        populateField('epoch.year', data.epoch.year);
        populateField('epoch.length', data.epoch.length);
        populateField('epoch.paused', data.epoch.paused);
        populateField('epoch.rollover_time', data.epoch.rollover_time);

        populateField('roles.announcements', data.roles.announcements);

        // Use resolved user names for display
        initListField('marker_users', data.users.markers, data.users.markers_names);

        // starboard
        if (data.starboard) {
            populateField('starboard.channel_id', data.starboard.channel_id);
            if (data.starboard.emojis) {
                emojiMap = Object.assign({}, data.starboard.emojis);
                renderEmojiTable();
            }
            initListField('starboard_valid_bots', data.starboard.valid_bots);
        }

        showNotification('Configuration loaded', 'success');
    } catch {
        showNotification('Failed to load configuration', 'danger');
    } finally {
        if (container) {showLoadingOverlay(container, false);}
    }
}

function populateField(name, value) {
    const field = document.querySelector(`[name="${name}"]`);
    if (!field) {
        console.warn(`Field not found: ${name}`);
        return;
    }

    if (field.type === 'checkbox') {
        field.checked = value;
    } else {
        field.value = value;
    }
}

async function saveGuildConfig(guildId, formElement) {
    const saveButton = document.getElementById('save-guild-btn');
    setLoading(saveButton, true);

    try {
        const data = serializeForm(formElement);
        const result = await fetchJSON(`/api/guilds/${guildId}`, {
            method: 'POST',
            body: JSON.stringify(data)
        });

        showNotification(result.message || 'Configuration saved successfully', 'success');
    } catch {
        // Error already shown
    } finally {
        setLoading(saveButton, false);
    }
}

async function validateGuildConfig(guildId, formElement) {
    const validateButton = document.getElementById('validate-guild-btn');
    setLoading(validateButton, true);

    try {
        const data = serializeForm(formElement);
        const result = await fetchJSON(`/api/guilds/${guildId}/validate`, {
            method: 'POST',
            body: JSON.stringify(data)
        });

        if (result.valid) {
            showNotification(result.message || 'Configuration is valid', 'success');
        }
    } catch {
        // Error already shown
    } finally {
        setLoading(validateButton, false);
    }
}

async function resetGuildConfig(guildId) {
    const resetButton = document.getElementById('reset-guild-btn');
    setLoading(resetButton, true);

    try {
        await fetchJSON(`/api/guilds/${guildId}/reset`, { method: 'POST' });
        await loadGuildConfig(guildId);
        showNotification('Configuration reset to database values', 'success');
    } catch {
        // Error already shown
    } finally {
        setLoading(resetButton, false);
    }
}

async function refreshDiscordData(guildId) {
    const refreshButton = document.getElementById('refresh-discord-btn');
    setLoading(refreshButton, true);

    try {
        await fetchJSON(`/api/guilds/${guildId}/refresh`, { method: 'POST' });
        await loadDiscordData(guildId);
        showNotification('Discord data refreshed', 'success');
    } catch {
        // Error already shown
    } finally {
        setLoading(refreshButton, false);
    }
}

function exportGuildConfig(guildId, formElement) {
    const data = serializeForm(formElement);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `guild-config-${guildId}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showNotification('Configuration exported', 'success');
}

function importGuildConfig() {
    const fileInput = document.getElementById('import-guild-file');
    fileInput.click();

    fileInput.onchange = (e) => {
        const file = e.target.files[0];
        if (!file) {return;}

        const reader = new FileReader();
        reader.onload = (event) => {
            try {
                const data = JSON.parse(event.target.result);

                if (data.channels) {
                    Object.keys(data.channels).forEach(key => {
                        const val = data.channels[key];
                        if (['lore_channels', 'canon_channels'].includes(key)) {
                            initListField(key, val);
                        } else {
                            populateField(`channels.${key}`, val);
                        }
                    });
                }
                if (data.epoch) {
                    Object.keys(data.epoch).forEach(key => {
                        populateField(`epoch.${key}`, data.epoch[key]);
                    });
                }
                if (data.roles) {
                    Object.keys(data.roles).forEach(key => {
                        populateField(`roles.${key}`, data.roles[key]);
                    });
                }
                if (data.users) {
                    Object.keys(data.users).forEach(key => {
                        const val = data.users[key];
                        if (key === 'markers') {
                            initListField('marker_users', val);
                        } else {
                            populateField(`users.${key}`, val);
                        }
                    });
                }

                showNotification("Configuration imported. Don't forget to save!", 'warning');
            } catch (err) {
                console.error('Import error:', err);
                showNotification('Failed to parse JSON file', 'danger');
            }
        };
        reader.readAsText(file);
    };
}

// ========== List Field Management ==========

function initListField(fieldName, items, names) {
    const hiddenInput = document.getElementById(fieldName);
    const listContainer = document.getElementById(`list-${fieldName}`);

    if (!hiddenInput || !listContainer) {return;}

    listContainer.innerHTML = '';
    const itemList = (items || []).map(String);
    hiddenInput.value = itemList.join(',');

    // Use names array if provided and has valid entries, otherwise fall back to item values
    let displayNames = itemList;
    if (names && Array.isArray(names) && names.length > 0) {
        // Check if names array has any non-null/non-empty values
        const hasValidNames = names.some(n => n != null && n !== '');
        if (hasValidNames) {
            displayNames = names;
        }
    }

    itemList.forEach((item, index) => {
        if (!item) {return;}
        const displayName = displayNames[index] || item;
        renderListItem(listContainer, fieldName, item, displayName);
    });
}

function addListItem(fieldName, inputId) {
    const input = document.getElementById(inputId);
    const hiddenInput = document.getElementById(fieldName);
    const listContainer = document.getElementById(`list-${fieldName}`);

    if (!input || !hiddenInput || !listContainer) {return;}

    const value = input.value.trim();
    if (!value) {return;}

    const currentItems = hiddenInput.value ? hiddenInput.value.split(',') : [];
    if (currentItems.includes(value)) {
        showNotification('Item already exists in list', 'warning');
        return;
    }

    currentItems.push(value);
    hiddenInput.value = currentItems.join(',');
    renderListItem(listContainer, fieldName, value);
    input.value = '';
}

function removeListItem(fieldName, value) {
    const hiddenInput = document.getElementById(fieldName);
    const listContainer = document.getElementById(`list-${fieldName}`);

    if (!hiddenInput || !listContainer) {return;}

    const currentItems = hiddenInput.value ? hiddenInput.value.split(',') : [];
    const newItems = currentItems.filter(item => item !== String(value));
    hiddenInput.value = newItems.join(',');
    initListField(fieldName, newItems);
}

function renderListItem(container, fieldName, value, displayName) {
    const li = document.createElement('li');
    li.className = 'list-group-item d-flex justify-content-between align-items-center';
    // Show displayName if provided, otherwise fall back to value
    const display = displayName && displayName !== value ? `${displayName} (${value})` : value;
    li.innerHTML = `
        <span>${escapeHtml(display)}</span>
        <button type="button" class="btn btn-sm btn-outline-danger" onclick="removeListItem('${fieldName}', '${value}')">
            <i data-feather="x"></i>
        </button>
    `;
    container.appendChild(li);
    // Re-initialize feather icons
    if (typeof feather !== 'undefined') {
        feather.replace();
    }
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Make globally accessible
window.addListItem = addListItem;
window.removeListItem = removeListItem;
window.initListField = initListField;

// ========== Emoji Map (Starboard) ==========

let emojiMap = {};

function renderEmojiTable() {
    const tbody = document.getElementById('emoji-table-body');
    if (!tbody) { return; }
    tbody.innerHTML = '';
    for (const [emoji, color] of Object.entries(emojiMap)) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(emoji)}</td>
            <td><span style="display:inline-block;width:20px;height:20px;background:${color};border:1px solid #ccc;border-radius:3px;vertical-align:middle;"></span> ${escapeHtml(color)}</td>
            <td><button type="button" class="btn btn-sm btn-outline-danger" onclick="removeEmoji('${escapeHtml(emoji)}')">Remove</button></td>
        `;
        tbody.appendChild(tr);
    }
    const hidden = document.getElementById('starboard_emojis');
    if (hidden) { hidden.value = JSON.stringify(emojiMap); }
}

function addEmojiEntry() {
    const emojiInput = document.getElementById('emoji_input');
    const colorInput = document.getElementById('emoji_color_input');
    if (!emojiInput || !colorInput) { return; }
    const emoji = emojiInput.value.trim();
    const color = colorInput.value.trim();
    if (!emoji) { return; }
    emojiMap[emoji] = color;
    emojiInput.value = '';
    renderEmojiTable();
}

function removeEmoji(emoji) {
    delete emojiMap[emoji];
    renderEmojiTable();
}

window.addEmojiEntry = addEmojiEntry;
window.removeEmoji = removeEmoji;

// ========== Theme Configuration ==========

async function loadThemeConfig() {
    const container = document.getElementById('theme-config-form');
    if (container) {showLoadingOverlay(container, true);}

    try {
        const data = await fetchJSON('/api/theme');

        populateField('rotation', data.rotation);
        populateField('max_rate', data.max_rate);
        populateField('bot_color', data.bot_color);
        populateField('guild_color', data.guild_color);

        syncColorInputs();
        showNotification('Theme loaded', 'success');
    } catch {
        showNotification('Failed to load theme', 'danger');
    } finally {
        if (container) {showLoadingOverlay(container, false);}
    }
}

async function saveThemeConfig(formElement) {
    const saveButton = document.getElementById('save-theme-btn');
    setLoading(saveButton, true);

    try {
        const data = serializeForm(formElement);
        const result = await fetchJSON('/api/theme', {
            method: 'POST',
            body: JSON.stringify(data)
        });

        showNotification(result.message || 'Theme saved successfully', 'success');
    } catch {
        // Error already shown
    } finally {
        setLoading(saveButton, false);
    }
}

async function resetThemeConfig() {
    const resetButton = document.getElementById('reset-theme-btn');
    setLoading(resetButton, true);

    try {
        await loadThemeConfig();
        showNotification('Theme reset to saved values', 'success');
    } catch {
        // Error already shown
    } finally {
        setLoading(resetButton, false);
    }
}

// ========== Color Picker Sync ==========

function syncColorInputs() {
    const colorPairs = [
        { picker: 'bot_color_picker', text: 'bot_color' },
        { picker: 'guild_color_picker', text: 'guild_color' }
    ];

    colorPairs.forEach(pair => {
        const pickerInput = document.getElementById(pair.picker);
        const textInput = document.getElementById(pair.text);

        if (pickerInput && textInput) {
            if (/^#[0-9A-F]{6}$/i.test(textInput.value)) {
                pickerInput.value = textInput.value;
            }

            pickerInput.addEventListener('input', function() {
                textInput.value = this.value;
            });

            textInput.addEventListener('input', function() {
                if (/^#[0-9A-F]{6}$/i.test(this.value)) {
                    pickerInput.value = this.value;
                }
            });
        }
    });
}

// ========== System Configuration ==========

async function loadSystemConfig() {
    const container = document.getElementById('system-config-form');
    if (container) {showLoadingOverlay(container, true);}

    try {
        const data = await fetchJSON('/api/system');

        populateField('primary_guild', data.primary_guild);
        populateField('error_log_guild', data.error_log_guild);
        populateField('error_log_channel', data.error_log_channel);
        populateField('error_hook', data.error_hook);

        const versionEl = document.getElementById('schema-version');
        if (versionEl) {
            versionEl.value = data.version;
        }

        showNotification('System configuration loaded', 'success');
    } catch {
        showNotification('Failed to load system configuration', 'danger');
    } finally {
        if (container) {showLoadingOverlay(container, false);}
    }
}

async function saveSystemConfig(formElement) {
    const saveButton = document.getElementById('save-system-btn');
    setLoading(saveButton, true);

    try {
        const data = serializeForm(formElement);
        const result = await fetchJSON('/api/system', {
            method: 'POST',
            body: JSON.stringify(data)
        });

        showNotification(result.message || 'System configuration saved successfully', 'success');
    } catch {
        // Error already shown
    } finally {
        setLoading(saveButton, false);
    }
}

async function resetSystemConfig() {
    const resetButton = document.getElementById('reset-system-btn');
    setLoading(resetButton, true);

    try {
        await loadSystemConfig();
        showNotification('System configuration reset to saved values', 'success');
    } catch {
        // Error already shown
    } finally {
        setLoading(resetButton, false);
    }
}

// ========== Audit Log ==========

const _auditLogMap = new Map();

async function loadAuditLogs() {
    const tableBody = document.getElementById('audit-log-body');
    if (!tableBody) {return;}

    const container = tableBody.closest('.card') || tableBody.parentElement;
    if (container) {showLoadingOverlay(container, true);}

    const configType = document.getElementById('filterConfigType')?.value;
    const guildId = document.getElementById('filterGuildId')?.value;

    let url = '/api/audit?limit=100';
    if (configType) {url += `&config_type=${configType}`;}
    if (guildId) {url += `&guild_id=${guildId}`;}

    try {
        const data = await fetchJSON(url);
        renderAuditLogs(data.logs);
    } catch {
        // Error shown by fetchJSON
    } finally {
        if (container) {showLoadingOverlay(container, false);}
    }
}

function renderAuditLogs(logs) {
    const tableBody = document.getElementById('audit-log-body');
    if (!tableBody) {return;}

    if (!logs || logs.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="6" class="text-center">No logs found</td></tr>';
        return;
    }

    _auditLogMap.clear();

    tableBody.innerHTML = logs.map((log, index) => {
        _auditLogMap.set(index, log);
        return `
        <tr>
            <td>${escapeHtml(log.timestamp_formatted)}</td>
            <td><span class="badge ${getLogBadgeClass(log.config_type)}">${escapeHtml(log.config_type)}</span></td>
            <td>${escapeHtml(log.action)}</td>
            <td>${escapeHtml(log.guild_id || '-')}</td>
            <td>
                ${log.success
        ? '<span class="text-success"><i data-feather="check"></i></span>'
        : `<span class="text-danger" title="${escapeHtml(log.error_message || 'Unknown error')}"><i data-feather="x"></i></span>`
}
            </td>
            <td>
                <button class="btn btn-sm btn-outline-secondary" type="button" data-log-id="${index}">Details</button>
            </td>
        </tr>
    `;
    }).join('');

    // Attach event listeners — avoids inline JSON serialisation in onclick (M3)
    tableBody.querySelectorAll('[data-log-id]').forEach(btn => {
        btn.addEventListener('click', () => {
            const log = _auditLogMap.get(parseInt(btn.dataset.logId, 10));
            if (log) { showLogDetails(log); }
        });
    });

    if (typeof feather !== 'undefined') {
        feather.replace();
    }
}

function getLogBadgeClass(type) {
    switch (type) {
        case 'guild': return 'bg-success';
        case 'theme': return 'bg-warning';
        case 'system': return 'bg-danger';
        default: return 'bg-secondary';
    }
}

function showLogDetails(log) {
    const modal = new bootstrap.Modal(document.getElementById('logDetailsModal'));
    const content = document.getElementById('logDetailsContent');

    let changesHtml;
    if (log.changes && log.changes.length > 0) {
        changesHtml = `
            <table class="table table-sm table-bordered">
                <thead><tr><th>Field</th><th>Old Value</th><th>New Value</th></tr></thead>
                <tbody>
                    ${log.changes.map(c => `
                        <tr>
                            <td><code>${escapeHtml(c.field)}</code></td>
                            <td class="text-danger">${c.old_value !== null ? escapeHtml(JSON.stringify(c.old_value)) : '<i>null</i>'}</td>
                            <td class="text-success">${c.new_value !== null ? escapeHtml(JSON.stringify(c.new_value)) : '<i>null</i>'}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } else if (!log.success) {
        changesHtml = `<div class="alert alert-danger">Error: ${escapeHtml(log.error_message)}</div>`;
    } else {
        changesHtml = '<p>No specific field changes recorded.</p>';
    }

    content.innerHTML = `
        <dl class="row">
            <dt class="col-sm-3">Timestamp</dt><dd class="col-sm-9">${escapeHtml(log.timestamp_formatted)}</dd>
            <dt class="col-sm-3">IP Address</dt><dd class="col-sm-9">${escapeHtml(log.ip_address)}</dd>
            <dt class="col-sm-3">Action</dt><dd class="col-sm-9">${escapeHtml(log.action)} ${escapeHtml(log.config_type)}</dd>
        </dl>
        <h5>Changes</h5>
        ${changesHtml}
    `;

    modal.show();
}

window.showLogDetails = showLogDetails;

// ========== Initialize ==========

document.addEventListener('DOMContentLoaded', () => {
    // Initialize Feather icons
    if (typeof feather !== 'undefined') {
        feather.replace();
    }

    // Sync color pickers with text inputs
    syncColorInputs();

    // Guild config page
    const guildForm = document.getElementById('guild-config-form');
    if (guildForm) {
        const {guildId} = guildForm.dataset;

        loadGuildConfig(guildId);

        const saveBtn = document.getElementById('save-guild-btn');
        if (saveBtn) {saveBtn.addEventListener('click', () => saveGuildConfig(guildId, guildForm));}

        const validateBtn = document.getElementById('validate-guild-btn');
        if (validateBtn) {validateBtn.addEventListener('click', () => validateGuildConfig(guildId, guildForm));}

        const resetBtn = document.getElementById('reset-guild-btn');
        if (resetBtn) {resetBtn.addEventListener('click', () => resetGuildConfig(guildId));}

        const refreshBtn = document.getElementById('refresh-discord-btn');
        if (refreshBtn) {refreshBtn.addEventListener('click', () => refreshDiscordData(guildId));}

        const exportBtn = document.getElementById('export-guild-btn');
        if (exportBtn) {exportBtn.addEventListener('click', () => exportGuildConfig(guildId, guildForm));}

        const importBtn = document.getElementById('import-guild-btn');
        if (importBtn) {importBtn.addEventListener('click', () => importGuildConfig(guildForm));}

        // live hex color preview for emoji swatch
        const emojiColorInput = document.getElementById('emoji_color_input');
        if (emojiColorInput) {
            emojiColorInput.addEventListener('input', function() {
                const val = this.value.trim();
                const preview = document.getElementById('emoji_color_preview');
                if (/^#[0-9a-fA-F]{6}$/.test(val)) {
                    if (preview) { preview.style.background = val; }
                    this.classList.remove('is-invalid');
                } else {
                    this.classList.add('is-invalid');
                }
            });
        }
    }

    // Theme config page
    const themeForm = document.getElementById('theme-config-form');
    if (themeForm) {
        loadThemeConfig();

        const saveBtn = document.getElementById('save-theme-btn');
        if (saveBtn) {saveBtn.addEventListener('click', () => saveThemeConfig(themeForm));}

        const resetBtn = document.getElementById('reset-theme-btn');
        if (resetBtn) {resetBtn.addEventListener('click', () => resetThemeConfig());}
    }

    // System config page
    const systemForm = document.getElementById('system-config-form');
    if (systemForm) {
        loadSystemConfig();

        const saveBtn = document.getElementById('save-system-btn');
        if (saveBtn) {saveBtn.addEventListener('click', () => saveSystemConfig(systemForm));}

        const resetBtn = document.getElementById('reset-system-btn');
        if (resetBtn) {resetBtn.addEventListener('click', () => resetSystemConfig());}
    }

    // Audit log page
    const auditLogTable = document.getElementById('audit-log-body');
    if (auditLogTable) {
        loadAuditLogs();

        const filterConfigType = document.getElementById('filterConfigType');
        if (filterConfigType) {filterConfigType.addEventListener('change', loadAuditLogs);}

        const filterGuildId = document.getElementById('filterGuildId');
        if (filterGuildId) {filterGuildId.addEventListener('change', loadAuditLogs);}

        const refreshBtn = document.getElementById('refresh-audit-btn');
        if (refreshBtn) {refreshBtn.addEventListener('click', loadAuditLogs);}
    }
});

// Global error handler
window.addEventListener('error', (e) => {
    console.error('Global error:', e.error);
});

window.addEventListener('unhandledrejection', (e) => {
    console.error('Unhandled promise rejection:', e.reason);
});
