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

async function refreshAI() {
    try {
        const s = await api('api/admin/ai');
        const el = document.getElementById('ai-status');
        el.textContent = `${s.is_configured ? 'Relay configured' : 'Not configured (scripted NPC lines)'}`
            + ` | queue ${s.queue_depth} | ok ${s.stats.completed} | fallback ${s.stats.fallback}`
            + ` | timeouts ${s.stats.timeouts}`;
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
api('api/auth/me').then(me => { document.getElementById('admin-name').textContent = me.name; }).catch(() => {});
refreshAll();
setInterval(refreshAll, 30000);
