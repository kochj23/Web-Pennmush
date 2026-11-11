/**
 * Web-Pennmush Admin Dashboard
 * Author: Jordan Koch (GitHub: kochj23)
 * Uses the admin-only REST API with the HttpOnly session cookie.
 * Everything user-controlled is rendered with textContent.
 */
'use strict';

async function api(path, options = {}) {
    const response = await fetch(path, Object.assign({ credentials: 'same-origin' }, options));
    if (response.status === 401 || response.status === 403) {
        window.location.href = './';
        throw new Error('not authorised');
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
}

function cell(text) {
    const td = document.createElement('td');
    td.textContent = text;
    return td;
}

async function refreshStats() {
    try {
        const stats = await api('api/stats');
        document.getElementById('stat-players').textContent = stats.players || 0;
        document.getElementById('stat-connected').textContent = stats.connected_players || 0;
        document.getElementById('stat-rooms').textContent = stats.rooms || 0;
        document.getElementById('stat-objects').textContent = (stats.things || 0) + (stats.exits || 0);
    } catch (e) { console.error(e); }
}

const AI_STATE_TEXT = {
    healthy: 'Healthy: relay polling',
    unreachable: 'Unreachable: relay not polling (scripted lines)',
    disabled: 'Switched off by staff (scripted lines)',
    not_configured: 'Not configured (scripted lines)',
};

function renderAI(s) {
    const el = document.getElementById('ai-status');
    const age = s.last_poll_age_s === null ? 'never' : `${s.last_poll_age_s}s ago`;
    el.textContent = `${AI_STATE_TEXT[s.state] || s.state} | last poll ${age}`
        + ` | queue ${s.queue_depth} | ai ${s.replies.ai} | relay fallback ${s.replies.relay_fallback}`
        + ` | scripted ${s.replies.scripted} | timeouts ${s.stats.timeouts}`;
    const btn = document.getElementById('ai-toggle');
    btn.textContent = s.enabled ? 'Switch AI off' : 'Switch AI on';
    btn.dataset.enabled = s.enabled ? '1' : '0';
    btn.disabled = !s.relay_configured;
}

async function refreshAI() {
    try { renderAI(await api('api/admin/ai')); } catch (e) { console.error(e); }
}

async function toggleAI() {
    const btn = document.getElementById('ai-toggle');
    const enabled = btn.dataset.enabled !== '1';
    try {
        renderAI(await api('api/admin/ai', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled }),
        }));
    } catch (e) { console.error(e); }
}

async function approve(id) {
    await api(`api/admin/players/${encodeURIComponent(id)}/approve`, { method: 'POST' });
    await refreshAccounts();
}

async function refreshAccounts() {
    const tbody = document.getElementById('accounts-table');
    try {
        const players = await api('api/admin/players');
        tbody.replaceChildren();
        players.forEach(p => {
            const tr = document.createElement('tr');
            tr.appendChild(cell(String(p.id)));
            tr.appendChild(cell(p.name));
            tr.appendChild(cell(p.pending ? 'pending approval' : (p.is_connected ? 'online' : 'offline')));
            tr.appendChild(cell(p.site_account_id || ''));
            const td = document.createElement('td');
            if (p.pending) {
                const btn = document.createElement('button');
                btn.className = 'action-button';
                btn.textContent = 'Approve';
                btn.addEventListener('click', () => approve(p.id));
                td.appendChild(btn);
            }
            tr.appendChild(td);
            tbody.appendChild(tr);
        });
    } catch (e) { console.error(e); }
}

async function refreshAll() {
    await Promise.all([refreshStats(), refreshAI(), refreshAccounts()]);
}

document.getElementById('refresh-stats').addEventListener('click', refreshStats);
document.getElementById('refresh-accounts').addEventListener('click', refreshAccounts);
document.getElementById('ai-toggle').addEventListener('click', toggleAI);
api('api/auth/me').then(me => { document.getElementById('admin-name').textContent = me.name; }).catch(() => {});
refreshAll();
setInterval(refreshAll, 30000);
