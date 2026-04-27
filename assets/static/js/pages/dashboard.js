/**
 * Dashboard Page Controller
 * Handles the combined overview dashboard
 */

import { api } from '../modules/api.js';

/**
 * Initialize dashboard page
 */
export function initDashboard() {
    const dashboardEl = document.getElementById('dashboard');
    if (!dashboardEl) {return;}

    // load all dashboard data in parallel
    Promise.all([
        loadStats(),
        loadTimeStatus(),
        loadRecentAudit(),
    ]);
}

/**
 * Load system statistics
 */
async function loadStats() {
    try {
        const stats = await api.getStats();

        // system status
        const dbEl = document.getElementById('stat-db');
        if (dbEl && stats.system) {
            dbEl.textContent = stats.system.db_connected ? 'Connected' : 'Offline';
            dbEl.className = `badge ${stats.system.db_connected ? 'bg-success' : 'bg-danger'}`;
        }

        const configEl = document.getElementById('stat-config');
        if (configEl && stats.system) {
            configEl.textContent = stats.system.config_loaded ? 'Loaded' : 'Not Loaded';
            configEl.className = `badge ${stats.system.config_loaded ? 'bg-success' : 'bg-warning'}`;
        }

        const uptimeEl = document.getElementById('stat-uptime');
        if (uptimeEl && stats.system) {
            uptimeEl.textContent = formatUptime(stats.system.uptime_seconds || 0);
        }

        const guildsEl = document.getElementById('stat-guilds');
        if (guildsEl && stats.guilds) {
            guildsEl.textContent = `${stats.guilds.configured}/${stats.guilds.total}`;
        }

        const versionEl = document.getElementById('stat-version');
        if (versionEl && stats.system) {
            versionEl.textContent = stats.system.config_version || '-';
        }

        // data summary
        if (stats.data) {
            setText('stat-years', stats.data.total_years || 0);
            setText('stat-markers', stats.data.total_markers || 0);
            setText('stat-stars', (stats.data.total_stars || 0).toLocaleString());
            setText('stat-eggs', stats.data.total_eggs_hatched || 0);
        }
    } catch (err) {
        console.error('Failed to load stats:', err);
    }
}

/**
 * Load time status for active guild
 */
async function loadTimeStatus() {
    try {
        // use the active guild (from the guild context injected server-side)
        // the /api/guilds/<id>/time endpoint needs the guild id; we'll get it from admin stats
        const stats = await api.getStats();
        if (!stats.guilds?.authorized?.length) {return;}

        // use the first authorized guild as a proxy for active guild
        const guildId = stats.guilds.authorized[0];
        const time = await api.getTime(guildId);

        setText('dash-year', `Year ${time.current_year}`);
        setText('dash-day', `${time.current_day} / ${time.year_length}`);

        const pct = time.year_length > 0 ? Math.round((time.current_day / time.year_length) * 100) : 0;
        const bar = document.getElementById('dash-progress');
        if (bar) {
            bar.style.width = `${pct}%`;
            bar.setAttribute('aria-valuenow', pct);
        }

        const pausedEl = document.getElementById('dash-paused');
        if (pausedEl) {
            pausedEl.innerHTML = time.paused
                ? '<span class="badge bg-warning">Paused</span>'
                : '<span class="badge bg-success">Running</span>';
        }
    } catch (err) {
        console.error('Failed to load time status:', err);
        setText('dash-year', '-');
        setText('dash-day', '-');
    }
}

/**
 * Load recent audit log entries
 */
async function loadRecentAudit() {
    const container = document.getElementById('dash-audit');
    if (!container) {return;}

    try {
        const data = await api.getAuditLogs({ limit: 5 });
        const logs = data.logs || [];

        if (logs.length === 0) {
            container.innerHTML = '<div class="list-group-item text-center text-muted py-3">No recent changes</div>';
            return;
        }

        container.innerHTML = logs.map(log => {
            const badge = log.success
                ? `<span class="badge bg-${typeBadge(log.config_type)} me-1">${escapeHtml(log.config_type)}</span>`
                : '<span class="badge bg-danger me-1">failed</span>';
            return `
                <div class="list-group-item d-flex justify-content-between align-items-center py-2">
                    <div>
                        ${badge}
                        <span class="small">${escapeHtml(log.action)}</span>
                    </div>
                    <small class="text-muted">${escapeHtml(log.timestamp_formatted)}</small>
                </div>
            `;
        }).join('');
    } catch (err) {
        console.error('Failed to load audit logs:', err);
        container.innerHTML = '<div class="list-group-item text-center text-muted py-3">Failed to load</div>';
    }
}

function typeBadge(type) {
    switch (type) {
        case 'guild': return 'success';
        case 'theme': return 'warning';
        case 'system': return 'danger';
        case 'chat': return 'info';
        default: return 'secondary';
    }
}

function setText(id, text) {
    const el = document.getElementById(id);
    if (el) {el.textContent = text;}
}

function formatUptime(seconds) {
    if (seconds < 60) {return `${seconds}s`;}
    if (seconds < 3600) {return `${Math.floor(seconds / 60)}m`;}
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h < 24) {return `${h}h ${m}m`;}
    const d = Math.floor(h / 24);
    return `${d}d ${h % 24}h`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// re-export for backwards compatibility
export function formatGuildId(id) {
    return typeof id === 'bigint' ? id.toString() : String(id);
}
