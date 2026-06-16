/* ── live_monitoring.js — Unified monitoring (user + admin) ── */

// ═══════════════════════════════════════════════════════════════════
// 1.  Global flags
// ═══════════════════════════════════════════════════════════════════

const IS_ADMIN = window.IS_ADMIN === true;

// ═══════════════════════════════════════════════════════════════════
// 2.  Config from  dashConfig
// ═══════════════════════════════════════════════════════════════════

function _loadConfig() {
    const el = document.getElementById('dashConfig');
    return el ? JSON.parse(el.textContent) : null;
}

const _CONFIG = _loadConfig() || {};
const _VAR_NAMES = _CONFIG.var_names || {};
const _UNITS = _CONFIG.units || {};
const _BOMBA_VARS = _CONFIG.pump_vars || [];
const _ELEVADOR_VARS = _CONFIG.elevator_vars || [];
const _RISK = _CONFIG.risk_labels || {};
const _NO_RISK_VARS = _CONFIG.no_risk_vars || [];

const EDIFICIO_ID = _CONFIG.edificio_id || 0;
const SSE_URL = EDIFICIO_ID ? `/sse/${EDIFICIO_ID}/` : null;

let sseSource = null;
let monitorConnectionTimeout = null;
let currentThresholds = {};
let chart1, chart2;
let unreadNotificationCount = 0;
let alertCountdownInterval = null;

// ═══════════════════════════════════════════════════════════════════
// 3.  Utility functions
// ═══════════════════════════════════════════════════════════════════

function safeText(value) {
    return value === null || value === undefined ? '-' : String(value);
}

function formatNumeric(value, variable) {
    if (typeof value === 'number') {
        if (variable === 'trip_count' || variable === 'load') {
            return Math.round(value).toString();
        }
        return value.toFixed(1);
    }
    return safeText(value);
}

function getVariableName(variable) {
    return _VAR_NAMES[variable] || variable.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function getUnit(variable) {
    return _UNITS[variable] || '';
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function csrfFetch(url, opts) {
    let token = getCookie('csrftoken');
    if (!token && window.CSRF_TOKEN) token = window.CSRF_TOKEN;
    opts.headers = { ...opts.headers, 'X-CSRFToken': token };
    opts.credentials = 'same-origin';
    return fetch(url, opts);
}

// ═══════════════════════════════════════════════════════════════════
// 4.  Risk helpers
// ═══════════════════════════════════════════════════════════════════

function getRiskBadge(risk) {
    if (risk === _RISK.critico) return 'badge-crit';
    if (risk === _RISK.alto) return 'badge-high';
    if (risk === _RISK.medio) return 'badge-med';
    if (risk === _RISK.bajo) return 'badge-low';
    return 'badge-info';
}

function getRiskClass(varName, value) {
    if (_NO_RISK_VARS.includes(varName)) {
        let crit = (varName === 'motor_stuck' && value);
        return { card: 'risk-' + (crit ? 'crit' : 'low'), badge: 'badge-' + (crit ? 'crit' : 'low'), label: crit ? _RISK.critico : _RISK.bajo };
    }
    let cfg = currentThresholds[varName];
    if (!cfg) return { card: '', badge: 'badge-info', label: _RISK.unknown };
    let risk = _RISK.bajo, cls = 'low';
    if (cfg.direction === 'range') {
        if (!(value >= cfg.low && value <= cfg.high)) { risk = _RISK.alto; cls = 'high'; }
    } else {
        let d = cfg.direction, low = cfg.low, med = cfg.medium, high = cfg.high;
        if (d === 'higher') {
            if (value > high) { risk = _RISK.critico; cls = 'crit'; }
            else if (value > med) { risk = _RISK.alto; cls = 'high'; }
            else if (value > low) { risk = _RISK.medio; cls = 'med'; }
        } else {
            if (value < high) { risk = _RISK.critico; cls = 'crit'; }
            else if (value < med) { risk = _RISK.alto; cls = 'high'; }
            else if (value < low) { risk = _RISK.medio; cls = 'med'; }
        }
    }
    return { card: 'risk-' + cls, badge: 'badge-' + cls, label: risk };
}

function isBombaVariable(variable) {
    return _BOMBA_VARS.includes(variable);
}

// ═══════════════════════════════════════════════════════════════════
// 5.  Card rendering
// ═══════════════════════════════════════════════════════════════════

function renderCard(variable, value, risk, label) {
    const name = getVariableName(variable).toUpperCase();
    const badgeClass = getRiskBadge(risk);
    const displayValue = variable === 'motor_stuck' ? (value ? 'Sí' : 'No') :
        (variable === 'door_status' ? (value === 'open' ? 'Abierta' : (value === 'closed' ? 'Cerrada' : safeText(value))) :
            `${formatNumeric(value, variable)} ${getUnit(variable)}`);
    let riskCls = 'risk-low';
    if (risk === _RISK.medio) riskCls = 'risk-med';
    else if (risk === _RISK.alto) riskCls = 'risk-high';
    else if (risk === _RISK.critico) riskCls = 'risk-crit';

    return `
        <div class="sensor-card ${riskCls}">
            <div class="sensor-card-name">${name}</div>
            <div class="sensor-card-value">${displayValue}</div>
            <div class="sensor-card-footer">
                <span class="badge ${badgeClass}">${risk}</span>
            </div>
        </div>
    `;
}

function updateCards(data) {
    const b = document.getElementById('bombaCards');
    const a = document.getElementById('elevadorCards');
    if (!b || !a) return;
    b.innerHTML = '';
    a.innerHTML = '';
    for (let [k, v] of Object.entries(data)) {
        let ri = getRiskClass(k, v);
        let dn = getVariableName(k).toUpperCase();
        let valStr = typeof v === 'boolean' ? (v ? 'Sí' : 'No') :
            (k === 'door_status' ? (v === 'open' ? 'Abierta' : (v === 'closed' ? 'Cerrada' : v)) :
                `${v} ${getUnit(k)}`);
        let card = document.createElement('div');
        card.className = `sensor-card ${ri.card}`;
        card.innerHTML = `
            <div class="sensor-card-name">${dn}</div>
            <div class="sensor-card-value">${valStr}</div>
            <div class="sensor-card-footer">
                <span class="badge ${ri.badge}">${ri.label}</span>
            </div>`;
        if (_BOMBA_VARS.includes(k)) b.appendChild(card);
        else if (_ELEVADOR_VARS.includes(k)) a.appendChild(card);
    }
}

// ═══════════════════════════════════════════════════════════════════
// 6.  Charts
// ═══════════════════════════════════════════════════════════════════

function initCharts() {
    if (typeof Chart === 'undefined') {
        console.warn('Chart.js no disponible. Gráficos desactivados.');
        return;
    }
    const chartDefaults = {
        responsive: true,
        plugins: {
            legend: { display: false },
            tooltip: { callbacks: { label: ctx => `${ctx.label}: ${ctx.raw}` } }
        },
        scales: {
            x: { ticks: { font: { family: "'DM Sans', system-ui", size: 10 } } },
            y: { beginAtZero: true, ticks: { font: { family: "'DM Sans', system-ui", size: 10 } } }
        }
    };

    const pumpLabels = _BOMBA_VARS.map(v => `${getVariableName(v)} (${getUnit(v)})`);
    const elevLabels = _ELEVADOR_VARS.filter(v => v !== 'position' && v !== 'door_status' && v !== 'motor_stuck')
        .map(v => `${getVariableName(v)} (${getUnit(v)})`);

    chart1 = new Chart(document.getElementById('chart1')?.getContext('2d'), {
        type: 'bar',
        data: {
            labels: pumpLabels,
            datasets: [{
                backgroundColor: '#0a0a0a',
                borderColor: '#0a0a0a',
                borderWidth: 1,
                data: new Array(pumpLabels.length).fill(0)
            }]
        },
        options: chartDefaults
    });

    chart2 = new Chart(document.getElementById('chart2')?.getContext('2d'), {
        type: 'bar',
        data: {
            labels: elevLabels,
            datasets: [{
                backgroundColor: '#0a0a0a',
                borderColor: '#0a0a0a',
                borderWidth: 1,
                data: new Array(elevLabels.length).fill(0)
            }]
        },
        options: chartDefaults
    });
}

function updateCharts(history) {
    if (typeof Chart === 'undefined' || !chart1) return;
    if (!history || !history.length) return;

    const getLatestReading = (v) => history.filter(item => item.variable === v).pop();

    const getLatest = (v) => {
        const r = getLatestReading(v);
        return r ? r.value : 0;
    };

    const getSensorColor = (v) => {
        const r = getLatestReading(v);
        if (!r) return '#0a0a0a';
        if (r.risk === _RISK.critico) return '#991b1b';
        if (r.risk === _RISK.alto) return '#c2410c';
        if (r.risk === _RISK.medio) return '#b45309';
        return '#166534';
    };

    if (chart1) {
        const pumpNumVars = _BOMBA_VARS.filter(v => v !== 'tank_level');
        chart1.data.datasets[0].data = pumpNumVars.map(v => getLatest(v));
        chart1.data.datasets[0].backgroundColor = pumpNumVars.map(v => getSensorColor(v));
        chart1.data.datasets[0].borderColor = chart1.data.datasets[0].backgroundColor;
        chart1.update();
    }
    if (chart2) {
        const elevChartVars = _ELEVADOR_VARS.filter(v => v !== 'position' && v !== 'door_status' && v !== 'motor_stuck');
        chart2.data.datasets[0].data = elevChartVars.map(v => getLatest(v));
        chart2.data.datasets[0].backgroundColor = elevChartVars.map(v => getSensorColor(v));
        chart2.data.datasets[0].borderColor = chart2.data.datasets[0].backgroundColor;
        chart2.update();
    }
}

// ═══════════════════════════════════════════════════════════════════
// 7.  Connection state management
// ═══════════════════════════════════════════════════════════════════

function showState(stateId) {
    const states = ['stateLoading', 'stateOffline', 'stateNoEquipment', 'stateNoBuildings'];
    states.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = id === stateId ? 'flex' : 'none';
    });
    const card = document.getElementById('stateNotifCard');
    if (card) card.style.display = 'block';
    const active = document.getElementById('activeMonitoring');
    if (active) active.style.display = 'none';
}

function hideAllStates() {
    ['stateLoading', 'stateOffline', 'stateNoEquipment', 'stateNoBuildings'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
    const card = document.getElementById('stateNotifCard');
    if (card) card.style.display = 'none';
    const active = document.getElementById('activeMonitoring');
    if (active) active.style.display = 'block';
}

function renderConnectionStatus(isConnected, message) {
    if (monitorConnectionTimeout) {
        clearTimeout(monitorConnectionTimeout);
        monitorConnectionTimeout = null;
    }
    if (isConnected) {
        hideAllStates();
    } else {
        showState('stateOffline');
    }
}

// ═══════════════════════════════════════════════════════════════════
// 8.  Badge helpers
// ═══════════════════════════════════════════════════════════════════

function updateStatusBadge(badgeId, emptyId, statusVal) {
    const badgeEl = document.getElementById(badgeId);
    const emptyEl = document.getElementById(emptyId);
    if (!badgeEl || !emptyEl) return;
    if (statusVal) {
        badgeEl.style.display = 'inline-block';
        badgeEl.textContent = statusVal.toUpperCase();
        emptyEl.style.display = 'none';
        if (statusVal === 'falla') badgeEl.className = 'badge badge-crit';
        else if (statusVal === 'mantenimiento') badgeEl.className = 'badge badge-med';
        else badgeEl.className = 'badge badge-low';
    } else {
        badgeEl.style.display = 'none';
        emptyEl.style.display = 'inline';
    }
}

// ═══════════════════════════════════════════════════════════════════
// 9.  Equipment visibility
// ═══════════════════════════════════════════════════════════════════

function updateEquipmentVisibility(equipTypes) {
    const et = equipTypes || [];
    const hasPump = et.includes('bomba');
    const hasElev = et.includes('elevador');
    const hasAny = hasPump || hasElev;

    if (!hasAny && EDIFICIO_ID) {
        showState('stateNoEquipment');
        return false;
    }

    const toggle = (ids, show) => {
        ids.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.display = show ? '' : 'none';
        });
    };

    toggle(['bombaSection', 'chartPumpPanel', 'statsBombaPanel'], hasPump);
    toggle(['elevadorSection', 'chartElevatorPanel', 'statsElevadorPanel'], hasElev);

    const pumpNI = document.getElementById('pumpNotInstalled');
    const pumpBadge = document.getElementById('pumpStatusBadge');
    const pumpEmpty = document.getElementById('pumpStatusEmpty');
    if (pumpNI && pumpBadge && pumpEmpty) {
        if (!hasPump) {
            pumpBadge.style.display = 'none';
            pumpEmpty.style.display = 'none';
            pumpNI.style.display = 'inline';
        } else {
            pumpNI.style.display = 'none';
        }
    }

    const elevNI = document.getElementById('elevatorNotInstalled');
    const elevBadge = document.getElementById('elevatorStatusBadge');
    const elevEmpty = document.getElementById('elevatorStatusEmpty');
    if (elevNI && elevBadge && elevEmpty) {
        if (!hasElev) {
            elevBadge.style.display = 'none';
            elevEmpty.style.display = 'none';
            elevNI.style.display = 'inline';
        } else {
            elevNI.style.display = 'none';
        }
    }

    return true;
}

function setNotificationBadge(count) {
    const badges = [
        document.getElementById('notificationBadgeCount'),
        document.getElementById('notificationBadgeSidebar')
    ].filter(Boolean);
    badges.forEach((badge) => {
        if (count > 0) {
            badge.textContent = count;
            badge.style.display = 'inline-flex';
            badge.hidden = false;
        } else {
            badge.textContent = '';
            badge.style.display = 'none';
            badge.hidden = true;
        }
    });
}

// ═══════════════════════════════════════════════════════════════════
// 10.  SSE ― main data pipeline
// ═══════════════════════════════════════════════════════════════════

function connectSSE() {
    if (sseSource) sseSource.close();
    if (!SSE_URL) {
        fetchInitialData();
        return;
    }
    if (typeof EventSource === 'undefined') {
        fetchInitialData();
        return;
    }

    sseSource = new EventSource(SSE_URL);

    sseSource.onopen = () => {
        renderConnectionStatus(true, 'Sistema de monitoreo conectado');
    };

    sseSource.onerror = () => {
        if (!monitorConnectionTimeout) {
            monitorConnectionTimeout = setTimeout(() => {
                showState('stateOffline');
                monitorConnectionTimeout = null;
            }, 15000);
        }
    };

    sseSource.onmessage = (event) => {
        try {
            applyPayload(JSON.parse(event.data));
        } catch (e) { /* ignore parse errors */ }
    };

    fetchInitialData();
}

function applyPayload(data) {
    if (data.thresholds) currentThresholds = data.thresholds;

    hideAllStates();

    if (data.current) updateCards(data.current);
    if (data.history) updateCharts(data.history);

    updateStatusBadge('pumpStatusBadge', 'pumpStatusEmpty', data.pump_status);
    updateStatusBadge('elevatorStatusBadge', 'elevatorStatusEmpty', data.elevator_status);

    const lastUpd = document.getElementById('lastUpdate');
    if (lastUpd) lastUpd.innerText = new Date().toLocaleTimeString();

    const hasEquipment = updateEquipmentVisibility(data.equipment_types);

    if (data.current && hasEquipment) {
        updateSummaryValues(data);
    }

    if (IS_ADMIN) {
        if (data.stats || data.recommendations) {
            updateStatsAndRecs(data.stats, data.recommendations, data.door_close_attempts);
        }
        if (data.sim_paused !== undefined) updatePauseBtn(data.sim_paused);
        if (data.sim_speed !== undefined) {
            const simSpd = document.getElementById('simSpeedDisplay');
            if (simSpd) simSpd.textContent = data.sim_speed.toFixed(1) + 'x';
        }
    }

    const totalAlerts = (data.alert_log || []).filter(a => a.risk !== _RISK.info).length;
    unreadNotificationCount = totalAlerts;
    setNotificationBadge(totalAlerts);
}

function updateSummaryValues(data) {
    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    };
    setVal('summaryPumpStatus', data.pump_on ? 'ENCENDIDA' : 'APAGADA');
    setVal('summaryElevatorStatus', data.elevator_on ? 'ENCENDIDO' : 'APAGADO');
}

// ═══════════════════════════════════════════════════════════════════
// 11.  Admin: Stats & recommendations
// ═══════════════════════════════════════════════════════════════════

function renderStatsTable(entries, containerId, firstColLabel, accentColor) {
    const div = document.getElementById(containerId);
    if (!div) return;
    if (entries.length) {
        const rows = entries.map(([k, v]) =>
            `<tr><td style="padding:8px 10px;font-weight:var(--weight-bold);text-transform:uppercase;letter-spacing:var(--tracking-wide);font-size:var(--text-xs);border-bottom:1px solid var(--color-border);color:var(--color-ink);">${getVariableName(k).toUpperCase()}</td>` +
            `<td style="padding:8px 10px;font-weight:var(--weight-bold);text-align:right;border-bottom:1px solid var(--color-border);color:var(--color-ink);">${v.avg.toFixed(1)}</td>` +
            `<td style="padding:8px 10px;text-align:right;border-bottom:1px solid var(--color-border);color:var(--color-text-secondary);">${v.min}</td>` +
            `<td style="padding:8px 10px;text-align:right;border-bottom:1px solid var(--color-border);color:var(--color-text-secondary);">${v.max}</td></tr>`
        ).join('');
        div.innerHTML = `<div style="border:2px solid var(--color-ink);box-shadow:4px 4px 0px rgba(10,10,10,0.15);border-left:6px solid ${accentColor};">
        <table style="width:100%;border-collapse:collapse;font-size:var(--text-xs);">
            <thead><tr>
                <th style="text-align:left;padding:10px;border-bottom:2px solid var(--color-ink);background:var(--color-ink);font-size:var(--text-xs);font-weight:var(--weight-bold);text-transform:uppercase;letter-spacing:var(--tracking-wide);color:#fff;">${firstColLabel}</th>
                <th style="text-align:right;padding:10px;border-bottom:2px solid var(--color-ink);background:var(--color-ink);font-size:var(--text-xs);font-weight:var(--weight-bold);text-transform:uppercase;letter-spacing:var(--tracking-wide);color:#fff;">Prom.</th>
                <th style="text-align:right;padding:10px;border-bottom:2px solid var(--color-ink);background:var(--color-ink);font-size:var(--text-xs);font-weight:var(--weight-bold);text-transform:uppercase;letter-spacing:var(--tracking-wide);color:#fff;">Mín.</th>
                <th style="text-align:right;padding:10px;border-bottom:2px solid var(--color-ink);background:var(--color-ink);font-size:var(--text-xs);font-weight:var(--weight-bold);text-transform:uppercase;letter-spacing:var(--tracking-wide);color:#fff;">Máx.</th>
            </tr></thead><tbody>${rows}</tbody></table></div>`;
    } else {
        div.innerHTML = '<p style="color:var(--color-text-secondary);font-size:var(--text-sm);">No hay datos.</p>';
    }
}

function updateStatsAndRecs(stats, recs, attempts) {
    const entries = stats && Object.keys(stats).length ? Object.entries(stats) : [];
    renderStatsTable(entries.filter(([k]) => _BOMBA_VARS.includes(k)), 'statsBombaPanel', 'Estadísticas de la bomba', '#2563eb');
    renderStatsTable(entries.filter(([k]) => _ELEVADOR_VARS.includes(k)), 'statsElevadorPanel', 'Estadísticas del elevador', '#7c3aed');
    const inlineEl = document.getElementById('inlineRec');
    if (inlineEl) {
        if (recs && recs.length) {
            let doorNote = (typeof attempts === 'number' && attempts > 0) ? ` | 🚪 ${attempts} intentos` : '';
            inlineEl.innerHTML = '⚠️ ' + recs[0] + doorNote;
            inlineEl.style.color = 'var(--state-warn)';
        } else {
            inlineEl.innerHTML = '✅ Todo normal';
            inlineEl.style.color = 'var(--color-text-secondary)';
        }
    }
}

// ═══════════════════════════════════════════════════════════════════
// 12.  Admin: Thresholds
// ═══════════════════════════════════════════════════════════════════

function renderThresholdsPanel(th) {
    const panel = document.getElementById('thresholdsPanel');
    if (!panel) return;
    panel.innerHTML = '';
    for (let [k, cfg] of Object.entries(th)) {
        if (_NO_RISK_VARS.includes(k)) continue;
        let div = document.createElement('div');
        div.style.cssText = 'border:1px solid var(--color-border);padding:var(--sp-1);';
        if (cfg.direction === 'range') {
            div.innerHTML = `<div style="font-size:var(--text-xs);font-weight:var(--weight-medium);text-transform:uppercase;letter-spacing:var(--tracking-wide);color:var(--color-text-secondary);margin-bottom:6px;">${getVariableName(k)} (rango)</div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--sp-1);">
                    <div class="form-group"><label class="form-label">Mín</label><input type="number" step="any" data-var="${k}" data-level="low" value="${cfg.low}"></div>
                    <div class="form-group"><label class="form-label">Máx</label><input type="number" step="any" data-var="${k}" data-level="high" value="${cfg.high}"></div>
                </div><input type="hidden" data-var="${k}" data-level="direction" value="range">`;
        } else {
            div.innerHTML = `<div style="font-size:var(--text-xs);font-weight:var(--weight-medium);text-transform:uppercase;letter-spacing:var(--tracking-wide);color:var(--color-text-secondary);margin-bottom:6px;">${getVariableName(k)}</div>
                <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:var(--sp-1);">
                    <div class="form-group"><label class="form-label">Bajo</label><input type="number" step="any" data-var="${k}" data-level="low" value="${cfg.low}"></div>
                    <div class="form-group"><label class="form-label">Medio</label><input type="number" step="any" data-var="${k}" data-level="medium" value="${cfg.medium}"></div>
                    <div class="form-group"><label class="form-label">Alto</label><input type="number" step="any" data-var="${k}" data-level="high" value="${cfg.high}"></div>
                </div><input type="hidden" data-var="${k}" data-level="direction" value="${cfg.direction}">`;
        }
        panel.appendChild(div);
    }
    validateThresholdInputs();
}

function validateThresholdInputs() {
    let hasError = false;
    let btn = document.getElementById('saveThresholdsBtn');
    let processed = {};
    document.querySelectorAll('#thresholdsPanel input[type="number"]').forEach(inp => {
        let v = inp.dataset.var;
        if (!v || processed[v]) return;
        processed[v] = true;
        let dir = document.querySelector(`#thresholdsPanel input[data-var="${v}"][data-level="direction"]`)?.value;
        let low = parseFloat(document.querySelector(`#thresholdsPanel input[data-var="${v}"][data-level="low"]`)?.value);
        let high = parseFloat(document.querySelector(`#thresholdsPanel input[data-var="${v}"][data-level="high"]`)?.value);
        let lowInp = document.querySelector(`#thresholdsPanel input[data-var="${v}"][data-level="low"]`);
        let highInp = document.querySelector(`#thresholdsPanel input[data-var="${v}"][data-level="high"]`);
        let medInp = document.querySelector(`#thresholdsPanel input[data-var="${v}"][data-level="medium"]`);
        [lowInp, medInp, highInp].forEach(el => { if (el) el.style.borderColor = ''; });

        let valid = false;
        if (dir === 'range') {
            valid = !isNaN(low) && !isNaN(high) && low < high;
            if (!valid) { if (lowInp) lowInp.style.borderColor = 'var(--state-critical)'; if (highInp) highInp.style.borderColor = 'var(--state-critical)'; }
        } else if (dir === 'higher') {
            let medium = parseFloat(medInp?.value);
            valid = !isNaN(low) && !isNaN(medium) && !isNaN(high) && low < medium && medium < high;
            if (!valid) { if (lowInp) lowInp.style.borderColor = 'var(--state-critical)'; if (medInp) medInp.style.borderColor = 'var(--state-critical)'; if (highInp) highInp.style.borderColor = 'var(--state-critical)'; }
        } else if (dir === 'lower') {
            let medium = parseFloat(medInp?.value);
            valid = !isNaN(low) && !isNaN(medium) && !isNaN(high) && low > medium && medium > high;
            if (!valid) { if (lowInp) lowInp.style.borderColor = 'var(--state-critical)'; if (medInp) medInp.style.borderColor = 'var(--state-critical)'; if (highInp) highInp.style.borderColor = 'var(--state-critical)'; }
        }
        if (!valid) hasError = true;
    });
    if (btn) btn.disabled = hasError;
}

async function saveThresholds() {
    let newTh = {};
    document.querySelectorAll('#thresholdsPanel input[type="number"]').forEach(inp => {
        let v = inp.dataset.var, l = inp.dataset.level;
        if (!newTh[v]) newTh[v] = { direction: document.querySelector(`#thresholdsPanel input[data-var="${v}"][data-level="direction"]`).value };
        newTh[v][l] = parseFloat(inp.value);
    });
    let resp = await csrfFetch('/api/thresholds/update/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(newTh) });
    let res = await resp.json();
    let msgEl = document.getElementById('saveMessage');
    if (res.status === 'ok') {
        msgEl.innerHTML = '<span style="color:var(--state-ok);font-weight:var(--weight-bold);">✓ Guardados</span>';
        setTimeout(() => msgEl.innerHTML = '', 2000);
        currentThresholds = res.thresholds;
        renderThresholdsPanel(res.thresholds);
        validateThresholdInputs();
    } else {
        msgEl.innerHTML = `<span style="color:var(--state-critical);font-weight:var(--weight-bold);">✗ Error: ${res.message}</span>`;
    }
}

// ═══════════════════════════════════════════════════════════════════
// 13.  Admin: Manual sensor control
// ═══════════════════════════════════════════════════════════════════

function populateManualSensorSelect() {
    const sel = document.getElementById('manualSensorSelect');
    if (!sel) return;
    sel.innerHTML = '';
    [..._BOMBA_VARS, ..._ELEVADOR_VARS].forEach(v => {
        let opt = document.createElement('option');
        opt.value = v;
        opt.textContent = (_BOMBA_VARS.includes(v) ? 'Bomba: ' : 'Elevador: ') + getVariableName(v).toUpperCase();
        sel.appendChild(opt);
    });
}

function updateSensorTypeIndicator() {
    const v = document.getElementById('manualSensorSelect')?.value;
    const el = document.getElementById('sensorTypeIndicator');
    if (el && v) el.textContent = _BOMBA_VARS.includes(v) ? 'Bomba / Eléctrico' : 'Elevador / Motor';
}

function updateManualRiskPreview() {
    const v = document.getElementById('manualSensorSelect')?.value;
    const raw = document.getElementById('manualValueInput')?.value;
    const span = document.getElementById('manualRiskPreview');
    if (!span || !raw) { if (span) span.innerHTML = ''; return; }
    let val = raw;
    if (v === 'door_status') { /* string */ }
    else if (v === 'motor_stuck') val = (raw === 'true' || raw === '1');
    else { let n = parseFloat(raw); if (isNaN(n)) { span.innerHTML = '<span style="color:var(--state-critical)">Valor inválido</span>'; return; } val = n; }
    let ri = getRiskClass(v, val);
    span.innerHTML = `Riesgo estimado: <span class="badge ${ri.badge}">${ri.label}</span>`;
}

async function sendManualValue() {
    const v = document.getElementById('manualSensorSelect')?.value;
    const raw = document.getElementById('manualValueInput')?.value;
    const msgEl = document.getElementById('manualMessage');
    if (!v || !raw) { msgEl.innerHTML = '<span style="color:var(--state-critical)">Complete los campos</span>'; return; }
    let val = raw;
    if (v === 'door_status') { val = raw.toLowerCase(); if (!['open', 'closed'].includes(val)) { msgEl.innerHTML = '<span style="color:var(--state-critical)">Debe ser "open" o "closed"</span>'; return; } }
    else if (v === 'motor_stuck') val = (raw === 'true' || raw === '1');
    else { let n = parseFloat(raw); if (isNaN(n)) { msgEl.innerHTML = '<span style="color:var(--state-critical)">Valor numérico inválido</span>'; return; } val = n; }
    try {
        let resp = await csrfFetch('/api/manual-update/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ variable: v, value: val, edificio_id: EDIFICIO_ID }) });
        let res = await resp.json();
        if (res.status === 'ok') { msgEl.innerHTML = `<span style="color:var(--state-ok)">✓ ${v} = ${res.value} (${res.risk})</span>`; setTimeout(() => msgEl.innerHTML = '', 3000); }
        else { msgEl.innerHTML = `<span style="color:var(--state-critical)">Error: ${res.message}</span>`; }
    } catch (e) { msgEl.innerHTML = '<span style="color:var(--state-critical)">Error de conexión</span>'; }
}

// ═══════════════════════════════════════════════════════════════════
// 14.  Admin: Simulation control
// ═══════════════════════════════════════════════════════════════════

async function fetchSimStatus() {
    if (!EDIFICIO_ID) return null;
    try {
        let resp = await fetch(`/api/sim/${EDIFICIO_ID}/status/`);
        return await resp.json();
    } catch (e) { return null; }
}

async function togglePause() {
    if (!EDIFICIO_ID) return;
    try {
        let resp = await csrfFetch(`/api/sim/${EDIFICIO_ID}/pause/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        let data = await resp.json();
        if (data.status === 'ok') {
            updatePauseBtn(data.paused);
            setSimMessage(data.paused ? '⏸ Simulación pausada' : '▶ Simulación reanudada', 'info');
        }
    } catch (e) { setSimMessage('Error al pausar/reanudar', 'error'); }
}

function updatePauseBtn(paused) {
    const btn = document.getElementById('simPauseBtn');
    if (!btn) return;
    if (paused) {
        btn.innerHTML = '<i class="fas fa-play"></i> <span>Reanudar</span>';
        btn.className = 'btn btn-ok';
    } else {
        btn.innerHTML = '<i class="fas fa-pause"></i> <span>Pausar</span>';
        btn.className = 'btn btn-ghost';
    }
}

async function resetSim() {
    let confirmed = await window.showConfirm('¿Reiniciar el simulador al estado normal?');
    if (!confirmed || !EDIFICIO_ID) return;
    try {
        let resp = await csrfFetch(`/api/sim/${EDIFICIO_ID}/reset/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        let data = await resp.json();
        if (data.status === 'ok') {
            setSimMessage('✅ ' + data.message, 'success');
            updatePauseBtn(false);
            const fp = document.getElementById('simFaultPump');
            const fe = document.getElementById('simFaultElevator');
            if (fp) fp.value = '';
            if (fe) fe.value = '';
        } else { setSimMessage('❌ ' + data.message, 'error'); }
    } catch (e) { setSimMessage('Error al reiniciar', 'error'); }
}

async function injectFault(device) {
    if (!EDIFICIO_ID) return;
    let sel = document.getElementById(device === 'pump' ? 'simFaultPump' : 'simFaultElevator');
    let faultType = sel?.value;
    try {
        let url, body;
        if (!faultType) {
            url = `/api/sim/${EDIFICIO_ID}/clear-fault/`;
            body = JSON.stringify({ device: device });
        } else {
            url = `/api/sim/${EDIFICIO_ID}/inject-fault/`;
            body = JSON.stringify({ device: device, fault_type: faultType });
        }
        let resp = await csrfFetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body });
        let data = await resp.json();
        if (data.status === 'ok') { setSimMessage('✅ ' + data.message, 'success'); }
        else { setSimMessage('❌ ' + data.message, 'error'); }
    } catch (e) { setSimMessage('Error al gestionar falla', 'error'); }
}

async function setSpeed() {
    if (!EDIFICIO_ID) return;
    const slider = document.getElementById('simSpeedSlider');
    const label = document.getElementById('simSpeedLabel');
    if (!slider) return;
    const speed = parseFloat(slider.value);
    if (label) label.textContent = speed.toFixed(1) + 'x';
    try {
        let resp = await csrfFetch(`/api/sim/${EDIFICIO_ID}/set-speed/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ speed: speed }) });
        let data = await resp.json();
        if (data.status === 'ok') setSimMessage('⚡ Velocidad: ' + data.speed.toFixed(1) + 'x', 'info');
    } catch (e) { /* silent */ }
}

function setSimMessage(msg, type) {
    const el = document.getElementById('simStatusMessage');
    if (!el) return;
    const color = type === 'error' ? 'var(--state-critical)' : type === 'success' ? 'var(--state-ok)' : 'var(--color-text-secondary)';
    el.innerHTML = '<span style="color:' + color + ';">' + msg + '</span>';
    setTimeout(() => { if (el.innerHTML === '<span style="color:' + color + ';">' + msg + '</span>') el.innerHTML = ''; }, 4000);
}

// ═══════════════════════════════════════════════════════════════════
// 15.  Notifications (from user template)
// ═══════════════════════════════════════════════════════════════════

function renderNotificationList(alerts) {
    const container = document.getElementById('live-notifications-list');
    if (!container) return;
    const placeholder = document.getElementById('live-no-notif');
    if (placeholder) placeholder.remove();

    const filtered = (alerts || []).filter(a => a.risk !== _RISK.info);
    if (filtered.length === 0) {
        unreadNotificationCount = 0;
        setNotificationBadge(0);
        container.innerHTML = `<div class="no-notif" id="live-no-notif">
            <i class="fa-solid fa-bell-slash"></i>
            <p>No hay alertas pendientes.</p>
        </div>`;
        return;
    }
    unreadNotificationCount = filtered.length;
    setNotificationBadge(unreadNotificationCount);
    container.innerHTML = filtered.map(alert => `
        <div class="notif-item live-notif-item">
            <div class="notif-icon"><i class="fa-solid fa-bell"></i></div>
            <div class="notif-body">
                <p>${safeText(alert.message)}</p>
                <div class="notif-meta">
                    <span><i class="fa-solid fa-clock"></i> ${new Date(alert.timestamp).toLocaleString()}</span>
                    <span><strong>Variable:</strong> ${safeText(getVariableName(alert.variable))}</span>
                    <span><strong>Riesgo:</strong> ${safeText(alert.risk)}</span>
                </div>
            </div>
        </div>
    `).join('');
}

function addLiveNotificationEvent(data) {
    const container = document.getElementById('live-notifications-list');
    if (!container) return;
    const placeholder = document.getElementById('live-no-notif');
    if (placeholder) placeholder.remove();
    const item = document.createElement('div');
    item.className = 'notif-item live-notif-item';
    item.innerHTML = `
        <div class="notif-icon"><i class="fa-solid fa-bell"></i></div>
        <div class="notif-body">
            <p>${safeText(data.message || '')}</p>
            <div class="notif-meta">
                <span><i class="fa-solid fa-clock"></i> ${data.timestamp ? new Date(data.timestamp).toLocaleString() : ''}</span>
                <span><strong>Variable:</strong> ${safeText(getVariableName(data.variable) || data.variable)}</span>
                <span><strong>Riesgo:</strong> ${safeText(data.risk)}</span>
            </div>
        </div>
    `;
    container.prepend(item);
    unreadNotificationCount++;
    setNotificationBadge(unreadNotificationCount);
}

// ── Duration picker modal ──────────────────────────────────────────

function showDurationPicker() {
    return new Promise((resolve) => {
        const durations = [
            { label: '5 min', value: 5 },
            { label: '10 min', value: 10 },
            { label: '30 min', value: 30 },
            { label: '1 hora', value: 60 },
            { label: '3 horas', value: 180 },
            { label: 'Siempre', value: null },
        ];
        const backdrop = document.createElement('div');
        backdrop.className = 'custom-modal-backdrop';
        const container = document.createElement('div');
        container.className = 'custom-modal-container';
        container.innerHTML = `
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:var(--sp-2);">
                <i class="fa-solid fa-clock" style="color:var(--state-warn);font-size:var(--text-xl);"></i>
                <span style="font-size:var(--text-lg);font-weight:var(--weight-bold);color:var(--color-ink);text-transform:uppercase;letter-spacing:var(--tracking-wide);">Desactivar alertas</span>
            </div>
            <p style="font-size:var(--text-sm);color:var(--color-text-secondary);margin-bottom:var(--sp-3);">¿Por cuánto tiempo deseas desactivar las alertas?</p>
            <div id="durationGrid" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:var(--sp-3);">
                ${durations.map(d => `<button data-minutes="${d.value === null ? 'null' : d.value}" style="background:var(--color-surface);border:2px solid var(--color-ink);color:var(--color-ink);padding:12px 8px;font-family:var(--font);font-size:var(--text-sm);font-weight:var(--weight-bold);cursor:pointer;box-shadow:3px 3px 0px var(--color-ink);transition:all 120ms ease;border-radius:0 !important;">${d.label}</button>`).join('')}
            </div>
            <div style="display:flex;justify-content:flex-end;">
                <button id="durationCancelBtn" style="background:none;border:1px solid var(--color-ink);padding:8px var(--sp-2);cursor:pointer;font-family:var(--font);font-size:var(--text-sm);font-weight:var(--weight-medium);border-radius:0px !important;">Cancelar</button>
            </div>`;
        backdrop.appendChild(container);
        document.body.appendChild(backdrop);
        setTimeout(() => backdrop.classList.add('active'), 10);
        const cleanUp = (value) => {
            backdrop.classList.remove('active');
            setTimeout(() => { backdrop.remove(); resolve(value); }, 150);
        };
        container.querySelector('#durationCancelBtn').addEventListener('click', () => cleanUp(undefined));
        container.querySelector('#durationGrid').addEventListener('click', (e) => {
            const btn = e.target.closest('button[data-minutes]');
            if (!btn) return;
            cleanUp(btn.dataset.minutes === 'null' ? null : parseInt(btn.dataset.minutes, 10));
        });
    });
}

function formatCountdown(remainingMs) {
    const totalSecs = Math.ceil(remainingMs / 1000);
    const h = Math.floor(totalSecs / 3600);
    const m = Math.floor((totalSecs % 3600) / 60);
    const s = totalSecs % 60;
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function startAlertCountdown(disabledUntilMs) {
    if (alertCountdownInterval) { clearInterval(alertCountdownInterval); alertCountdownInterval = null; }
    const btn = document.getElementById('toggleAlertsBtn');
    if (!btn) return;
    function tick() {
        const remaining = disabledUntilMs - Date.now();
        if (remaining <= 0) {
            clearInterval(alertCountdownInterval);
            alertCountdownInterval = null;
            reEnableAlerts();
            return;
        }
        btn.innerHTML = `<i class="fa-solid fa-bell-slash"></i> Activar alertas <span style="font-size:0.8em;opacity:0.7;font-weight:normal;">(${formatCountdown(remaining)})</span>`;
    }
    tick();
    alertCountdownInterval = setInterval(tick, 1000);
}

async function reEnableAlerts() {
    const btn = document.getElementById('toggleAlertsBtn');
    if (!btn) return;
    btn.dataset.enabled = 'true';
    btn.dataset.disabledUntilMs = '';
    btn.className = 'btn-alerts-toggle enabled';
    btn.innerHTML = '<i class="fa-solid fa-bell"></i> Desactivar alertas';
    await Promise.allSettled([
        csrfFetch('/notifications/toggle-alerts/', { method: 'POST', body: JSON.stringify({ enabled: true }) }),
        csrfFetch('/api/toggle-alerts/', { method: 'POST', body: JSON.stringify({ enabled: true, edificio_id: EDIFICIO_ID }) }),
    ]);
    await window.showAlert('Alertas reactivadas.', 'success');
    window.location.reload();
}

function initLiveNotifications() {
    const toggleBtn = document.getElementById('toggleAlertsBtn');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', async () => {
            const isCurrentlyEnabled = toggleBtn.dataset.enabled === 'true';
            if (!isCurrentlyEnabled) {
                if (alertCountdownInterval) { clearInterval(alertCountdownInterval); alertCountdownInterval = null; }
                toggleBtn.dataset.enabled = 'true';
                toggleBtn.dataset.disabledUntilMs = '';
                toggleBtn.className = 'btn-alerts-toggle enabled';
                toggleBtn.innerHTML = '<i class="fa-solid fa-bell"></i> Desactivar alertas';
                await Promise.allSettled([
                    csrfFetch('/notifications/toggle-alerts/', { method: 'POST', body: JSON.stringify({ enabled: true }) }),
                    csrfFetch('/api/toggle-alerts/', { method: 'POST', body: JSON.stringify({ enabled: true, edificio_id: EDIFICIO_ID }) }),
                ]);
                await window.showAlert('Alertas activadas con éxito.', 'success');
                window.location.reload();
            } else {
                const minutes = await showDurationPicker();
                if (minutes === undefined) return;
                toggleBtn.dataset.enabled = 'false';
                toggleBtn.className = 'btn-alerts-toggle disabled';
                if (minutes !== null) {
                    const untilMs = Date.now() + minutes * 60 * 1000;
                    toggleBtn.dataset.disabledUntilMs = untilMs;
                    startAlertCountdown(untilMs);
                } else {
                    toggleBtn.dataset.disabledUntilMs = '';
                    toggleBtn.innerHTML = '<i class="fa-solid fa-bell-slash"></i> Activar alertas';
                }
                await Promise.allSettled([
                    csrfFetch('/notifications/toggle-alerts/', { method: 'POST', body: JSON.stringify({ enabled: false, duration_minutes: minutes }) }),
                    csrfFetch('/api/toggle-alerts/', { method: 'POST', body: JSON.stringify({ enabled: false, edificio_id: EDIFICIO_ID }) }),
                ]);
                const label = minutes === null ? 'indefinidamente'
                    : minutes < 60 ? `por ${minutes} min`
                        : minutes === 60 ? 'por 1 hora'
                            : `por ${minutes / 60} horas`;
                await window.showAlert(`Alertas pausadas ${label}.`, 'success');
                window.location.reload();
            }
        });
    }
    const clearBtn = document.getElementById('clearDbNotificationsBtn');
    if (clearBtn) {
        clearBtn.addEventListener('click', async () => {
            const shouldClear = await window.showConfirm('¿Estás seguro de que deseas limpiar todas las alertas?');
            if (shouldClear) {
                try {
                    const resp = await csrfFetch('/notifications/clear/', { method: 'POST' });
                    if (resp.ok) {
                        await window.showAlert('Alertas limpiadas con éxito.', 'success');
                        window.location.href = window.location.pathname;
                    } else { throw new Error('Error al limpiar'); }
                } catch (error) {
                    await window.showAlert('No se pudieron limpiar las alertas.', 'error');
                }
            }
        });
    }
}

// ═══════════════════════════════════════════════════════════════════
// 16.  Initial fetch
// ═══════════════════════════════════════════════════════════════════

function fetchInitialData() {
    const url = EDIFICIO_ID ? `/api/status/?edificio_id=${EDIFICIO_ID}` : '/api/status/';
    fetch(url)
        .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
        .then(data => {
            applyPayload(data);
            if (IS_ADMIN && data.thresholds) renderThresholdsPanel(data.thresholds);
        })
        .catch(() => {
            if (IS_ADMIN) {
                ['statsBombaPanel', 'statsElevadorPanel'].forEach(id => {
                    const el = document.getElementById(id);
                    if (el) el.innerHTML = '<span style="color:var(--color-text-secondary);font-size:var(--text-sm);">Sin datos de telemetría para este edificio.</span>';
                });
            }
        });
}

// ═══════════════════════════════════════════════════════════════════
// 17.  Bootstrap
// ═══════════════════════════════════════════════════════════════════

function setupAdminEvents() {
    const pauseBtn = document.getElementById('simPauseBtn');
    const resetBtn = document.getElementById('simResetBtn');
    const faultPump = document.getElementById('simFaultPump');
    const faultElev = document.getElementById('simFaultElevator');
    const speedSlider = document.getElementById('simSpeedSlider');
    const saveThreshBtn = document.getElementById('saveThresholdsBtn');
    const threshPanel = document.getElementById('thresholdsPanel');
    const manualValInput = document.getElementById('manualValueInput');
    const manualSensorSel = document.getElementById('manualSensorSelect');
    const sendManualBtn = document.getElementById('sendManualBtn');

    if (pauseBtn) pauseBtn.addEventListener('click', togglePause);
    if (resetBtn) resetBtn.addEventListener('click', resetSim);
    if (faultPump) faultPump.addEventListener('change', () => injectFault('pump'));
    if (faultElev) faultElev.addEventListener('change', () => injectFault('elevator'));
    if (speedSlider) speedSlider.addEventListener('input', setSpeed);
    if (saveThreshBtn) saveThreshBtn.addEventListener('click', saveThresholds);
    if (threshPanel) threshPanel.addEventListener('input', validateThresholdInputs);
    if (manualValInput) manualValInput.addEventListener('input', updateManualRiskPreview);
    if (manualSensorSel) {
        manualSensorSel.addEventListener('change', () => { updateManualRiskPreview(); updateSensorTypeIndicator(); });
    }
    if (sendManualBtn) sendManualBtn.addEventListener('click', sendManualValue);

    fetchSimStatus().then(data => {
        if (data) {
            updatePauseBtn(data.paused);
            const slider = document.getElementById('simSpeedSlider');
            const label = document.getElementById('simSpeedLabel');
            if (slider) slider.value = data.speed;
            if (label) label.textContent = data.speed.toFixed(1) + 'x';
            const fp = document.getElementById('simFaultPump');
            const fe = document.getElementById('simFaultElevator');
            if (fp) fp.value = data.faults && data.faults.pump ? data.faults.pump : '';
            if (fe) fe.value = data.faults && data.faults.elevator ? data.faults.elevator : '';
        }
    });

    populateManualSensorSelect();
    updateSensorTypeIndicator();
}

function setupBuildingSelector() {
    const sel = document.getElementById('buildingSelect');
    if (!sel) return;
    sel.addEventListener('change', function () {
        const newId = parseInt(this.value);
        if (newId && newId !== EDIFICIO_ID) {
            window.location.href = `?edificio_id=${newId}`;
        }
    });
}

window.addEventListener('DOMContentLoaded', () => {
    const isMonitoringPage = document.getElementById('activeMonitoring') !== null;
    if (!isMonitoringPage) {
        if (document.getElementById('live-notifications-list')) {
            const badgeCountEl = document.getElementById('notificationBadgeCount');
            if (badgeCountEl) unreadNotificationCount = parseInt(badgeCountEl.textContent, 10) || 0;
            initLiveNotifications();
        }
        const toggleBtn = document.getElementById('toggleAlertsBtn');
        if (toggleBtn) {
            toggleBtn.disabled = false;
            toggleBtn.style.opacity = '1';
            toggleBtn.style.display = '';
            const sessionEnabled = toggleBtn.dataset.enabled === 'true';
            const disabledUntilMs = parseInt(toggleBtn.dataset.disabledUntilMs || '0', 10);
            if (sessionEnabled) {
                toggleBtn.className = 'btn-alerts-toggle enabled';
                toggleBtn.innerHTML = '<i class="fa-solid fa-bell"></i> Desactivar alertas';
            } else if (disabledUntilMs && disabledUntilMs > Date.now()) {
                toggleBtn.className = 'btn-alerts-toggle disabled';
                startAlertCountdown(disabledUntilMs);
            } else {
                toggleBtn.className = 'btn-alerts-toggle disabled';
                toggleBtn.innerHTML = '<i class="fa-solid fa-bell-slash"></i> Activar alertas';
            }
        }
        return;
    }

    setNotificationBadge(0);
    showState('stateLoading');

    initCharts();

    monitorConnectionTimeout = setTimeout(() => {
        showState('stateOffline');
        monitorConnectionTimeout = null;
    }, 15000);

    connectSSE();

    if (IS_ADMIN) {
        setupAdminEvents();
    }

    setupBuildingSelector();
});
