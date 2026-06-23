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
const _BOOLEAN_VARS = _CONFIG.boolean_vars || [];
const _ENUM_VARS = _CONFIG.enum_vars || [];
const _ENUM_RISK_VALUES = _CONFIG.enum_risk_values || {};
const _VALUE_DISPLAY = _CONFIG.value_display_es || {};
let _SENSOR_RANGES = _CONFIG.sensor_ranges || {};

let EDIFICIO_ID = _CONFIG.edificio_id || window.SELECTED_BUILDING_ID || 0;
let SSE_URL = EDIFICIO_ID ? `/sse/${EDIFICIO_ID}/` : null;

let sseSource = null;
let monitorConnectionTimeout = null;
let currentThresholds = {};
let _originalThresholds = {};
let currentReadings = {};
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
        return value.toFixed(2);
    }
    return safeText(value);
}

function getVariableName(variable) {
    return _VAR_NAMES[variable] || variable.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function getUnit(variable) {
    return _UNITS[variable] || '';
}

function translateSensorValue(variable, value) {
    // Usa VALUE_DISPLAY_ES de sensor_config como fuente única de verdad
    if (_VALUE_DISPLAY[variable]) {
        const tr = _VALUE_DISPLAY[variable][String(value)];
        if (tr !== undefined) return tr;
    }
    // Fallback para booleanos no mapeados
    if (typeof value === 'boolean') return value ? 'Sí' : 'No';
    return null; // null = el caller formatea numéricamente
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

function csrfFetch(url, opts = {}) {
    let token = getCookie('csrftoken');
    if (!token && window.CSRF_TOKEN) token = window.CSRF_TOKEN;
    const headers = {
        'X-CSRFToken': token,
        ...opts.headers
    };
    if (opts.body && !headers['Content-Type'] && !headers['content-type']) {
        headers['Content-Type'] = 'application/json';
    }
    opts.headers = headers;
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
    if (_BOOLEAN_VARS.includes(varName)) {
        let crit = !!value;
        return { card: 'risk-' + (crit ? 'crit' : 'low'), badge: 'badge-' + (crit ? 'crit' : 'low'), label: crit ? _RISK.critico : _RISK.bajo };
    }
    if (_ENUM_VARS.includes(varName)) {
        let risky = _ENUM_RISK_VALUES[varName] || [];
        let crit = risky.includes(String(value).toLowerCase());
        return { card: 'risk-' + (crit ? 'crit' : 'low'), badge: 'badge-' + (crit ? 'crit' : 'low'), label: crit ? _RISK.critico : _RISK.bajo };
    }
    if (_NO_RISK_VARS.includes(varName)) {
        return { card: 'risk-low', badge: 'badge-low', label: _RISK.bajo };
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

function renderCard(variable, value, risk, badgeClass, cardClass) {
    const name = getVariableName(variable);
    const displayValue = translateSensorValue(variable, value)
        ?? `${formatNumeric(value, variable)} ${getUnit(variable)}`;

    const isNoRisk = _NO_RISK_VARS.includes(variable);
    const finalCardClass = isNoRisk ? '' : cardClass;
    const badgeHtml = isNoRisk ? '' : `<span class="badge ${badgeClass}">${risk}</span>`;

    return `
        <div class="sensor-card ${finalCardClass}">
            <div class="sensor-card-name">${name}</div>
            <div class="sensor-card-value">${displayValue}</div>
            <div class="sensor-card-footer">
                ${badgeHtml}
            </div>
        </div>
    `;
}

function updateCards(data) {
    const b = document.getElementById('bombaCards');
    const a = document.getElementById('elevadorCards');
    if (!b || !a) return;
    for (let [k, v] of Object.entries(data)) {
        let ri = getRiskClass(k, v);
        let card = document.getElementById(`sensor-card-${k}`);
        const displayValue = translateSensorValue(k, v)
            ?? `${formatNumeric(v, k)} ${getUnit(k)}`;
        const isNoRisk = _NO_RISK_VARS.includes(k);
        const finalCardClass = isNoRisk ? '' : ri.card;
        
        if (!card) {
            card = document.createElement('div');
            card.id = `sensor-card-${k}`;
            card.className = `sensor-card ${finalCardClass}`;
            
            const badgeHtml = isNoRisk ? '' : `<span class="badge ${ri.badge}">${ri.label}</span>`;
            card.innerHTML = `
                <div class="sensor-card-name">${getVariableName(k)}</div>
                <div class="sensor-card-value">${displayValue}</div>
                <div class="sensor-card-footer">${badgeHtml}</div>
            `;
            if (_BOMBA_VARS.includes(k)) b.appendChild(card);
            else if (_ELEVADOR_VARS.includes(k)) a.appendChild(card);
        } else {
            card.className = `sensor-card ${finalCardClass}`;
            const valEl = card.querySelector('.sensor-card-value');
            if (valEl && valEl.textContent !== displayValue) {
                valEl.textContent = displayValue;
            }
            const footerEl = card.querySelector('.sensor-card-footer');
            if (footerEl) {
                const badgeEl = footerEl.querySelector('.badge');
                if (!isNoRisk) {
                    if (badgeEl) {
                        badgeEl.className = `badge ${ri.badge}`;
                        badgeEl.textContent = ri.label;
                    } else {
                        footerEl.innerHTML = `<span class="badge ${ri.badge}">${ri.label}</span>`;
                    }
                } else if (badgeEl) {
                    badgeEl.remove();
                }
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════════
// 6.  Charts
// ═══════════════════════════════════════════════════════════════════

function getCSSVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '';
}

function initCharts() {
    if (typeof Chart === 'undefined') {
        console.warn('Chart.js no disponible. Gráficos desactivados.');
        return;
    }
    const canvas1 = document.getElementById('chart1');
    const canvas2 = document.getElementById('chart2');
    if (!canvas1 || !canvas2) {
        console.warn('Canvas para gráficos no encontrados. Omisión de inicialización.');
        return;
    }

    const chartDefaults = {
        responsive: true,
        plugins: {
            legend: { display: false },
            tooltip: {
                callbacks: {
                    label: ctx => {
                        const dataset = ctx.chart.data.datasets[ctx.datasetIndex];
                        const variable = dataset.variables ? dataset.variables[ctx.dataIndex] : null;
                        const formattedVal = variable ? formatNumeric(ctx.raw, variable) : (typeof ctx.raw === 'number' ? ctx.raw.toFixed(2) : ctx.raw);
                        return `${ctx.label}: ${formattedVal}`;
                    }
                }
            }
        },
        scales: {
            x: { ticks: { font: { family: "'DM Sans', system-ui", size: 10 } } },
            y: { beginAtZero: true, ticks: { font: { family: "'DM Sans', system-ui", size: 10 } } }
        }
    };

    const pumpNumVars = _BOMBA_VARS.filter(v => v !== 'tank_level');
    const pumpLabels = pumpNumVars.map(v => `${getVariableName(v)} (${getUnit(v)})`);
    const elevChartVars = _ELEVADOR_VARS.filter(v => v !== 'position' && v !== 'door_status' && v !== 'motor_stuck');
    const elevLabels = elevChartVars.map(v => `${getVariableName(v)} (${getUnit(v)})`);

    chart1 = new Chart(canvas1.getContext('2d'), {
        type: 'bar',
        data: {
            labels: pumpLabels,
            datasets: [{
                variables: pumpNumVars,
                backgroundColor: getCSSVar('--color-ink') || '#0a0a0a',
                borderColor: getCSSVar('--color-ink') || '#0a0a0a',
                borderWidth: 1,
                data: new Array(pumpLabels.length).fill(0)
            }]
        },
        options: chartDefaults
    });

    chart2 = new Chart(canvas2.getContext('2d'), {
        type: 'bar',
        data: {
            labels: elevLabels,
            datasets: [{
                variables: elevChartVars,
                backgroundColor: getCSSVar('--color-ink') || '#0a0a0a',
                borderColor: getCSSVar('--color-ink') || '#0a0a0a',
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
        if (!r) return getCSSVar('--color-ink') || '#0a0a0a';
        if (r.risk === _RISK.critico) return getCSSVar('--state-critical') || '#dc2626';
        if (r.risk === _RISK.alto) return '#c2410c';
        if (r.risk === _RISK.medio) return getCSSVar('--state-warn') || '#b45309';
        return getCSSVar('--state-ok') || '#16a34a';
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
        badgeEl.textContent = statusVal.charAt(0).toUpperCase() + statusVal.slice(1);
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

function updateAdminControlsByEquipment(equipTypes) {
    if (!IS_ADMIN) return;
    const et = equipTypes || [];
    const hasPump = et.includes('bomba');
    const hasElev = et.includes('elevador');

    const fp = document.getElementById('simFaultPump');
    const fe = document.getElementById('simFaultElevator');
    if (fp) fp.disabled = !hasPump;
    if (fe) fe.disabled = !hasElev;

    const eqSel = document.getElementById('manualEquipmentSelect');
    const eqStatic = document.getElementById('manualEquipmentStatic');
    if (!eqSel || !eqStatic) return;

    if (hasPump && hasElev) {
        eqSel.style.display = '';
        eqStatic.style.display = 'none';
    } else if (hasPump) {
        eqSel.style.display = 'none';
        eqStatic.style.display = 'block';
        eqStatic.textContent = 'Bomba de agua';
        eqSel.value = 'pump';
        populateManualSensorSelect();
    } else if (hasElev) {
        eqSel.style.display = 'none';
        eqStatic.style.display = 'block';
        eqStatic.textContent = 'Elevador';
        eqSel.value = 'elevator';
        populateManualSensorSelect();
    } else {
        eqSel.style.display = 'none';
        eqStatic.style.display = 'block';
        eqStatic.textContent = '—';
    }
}

function setNotificationBadge(count) {
    // Solo actualiza el badge de la página de notificaciones (notificationBadgeCount).
    // El badge del sidebar (notificationBadgeSidebar) lo gestiona el context processor
    // del servidor para reflejar la suma de TODOS los edificios del usuario, no solo
    // el edificio activo seleccionado en el dashboard.
    const pageBadge = document.getElementById('notificationBadgeCount');
    if (pageBadge) {
        if (count > 0) {
            pageBadge.textContent = count;
            pageBadge.style.display = 'inline-flex';
            pageBadge.hidden = false;
        } else {
            pageBadge.textContent = '';
            pageBadge.style.display = 'none';
            pageBadge.hidden = true;
        }
    }
}

// ═══════════════════════════════════════════════════════════════════
// 10.  SSE ― main data pipeline
// ═══════════════════════════════════════════════════════════════════

function connectSSE() {
    if (sseSource) sseSource.close();
    const isMonitoring = document.getElementById('activeMonitoring') !== null;
    if (!SSE_URL) {
        if (isMonitoring) fetchInitialData();
        return;
    }
    if (typeof EventSource === 'undefined') {
        if (isMonitoring) fetchInitialData();
        return;
    }

    sseSource = new EventSource(SSE_URL);

    sseSource.onopen = () => {
        if (isMonitoring) {
            renderConnectionStatus(true, 'Sistema de monitoreo conectado');
        }
    };

    sseSource.onerror = () => {
        if (isMonitoring && !monitorConnectionTimeout) {
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

    sseSource.addEventListener("notification", (event) => {
        try {
            addLiveNotificationEvent(JSON.parse(event.data));
        } catch (e) { /* ignore parse errors */ }
    });

    if (isMonitoring) {
        fetchInitialData();
    }
}

function applyPayload(data) {
    if (data.thresholds) currentThresholds = data.thresholds;

    hideAllStates();

    if (data.current) {
        currentReadings = data.current;
        updateCards(data.current);
    }
    if (data.history) updateCharts(data.history);

    updateStatusBadge('pumpStatusBadge', 'pumpStatusEmpty', data.pump_status);
    updateStatusBadge('elevatorStatusBadge', 'elevatorStatusEmpty', data.elevator_status);

    const lastUpd = document.getElementById('lastUpdate');
    if (lastUpd) lastUpd.innerText = new Date().toLocaleTimeString();

    const hasEquipment = updateEquipmentVisibility(data.equipment_types);

    if (IS_ADMIN) updateAdminControlsByEquipment(data.equipment_types);

    if (data.current && hasEquipment) {
        updateSummaryValues(data);
    }

    if (data.stats || data.recommendations) {
        updateStatsAndRecs(data.stats, data.recommendations, data.door_close_attempts);
    }

    if (IS_ADMIN) {
        if (data.sim_paused !== undefined) updatePauseBtn(data.sim_paused);
        if (data.sim_speed !== undefined) {
            document.querySelectorAll('.speed-btn').forEach(btn => {
                if (parseFloat(btn.dataset.speed) === data.sim_speed) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            });
        }

        const simSpd = document.getElementById('simSpeedDisplay');
        if (simSpd) {
            const isPaused = data.sim_paused !== undefined ? data.sim_paused : document.getElementById('simPauseBtn')?.querySelector('i.fa-play') !== null;
            const speed = data.sim_speed !== undefined ? data.sim_speed : parseFloat(document.querySelector('.speed-btn.active')?.dataset.speed || 1.0);

            if (isPaused) {
                simSpd.textContent = 'Pausada';
                simSpd.className = 'badge badge-med';
            } else {
                simSpd.textContent = speed.toFixed(1) + 'x';
                simSpd.className = 'badge badge-info';
            }
        }
    }

    // Filtra alert_log igual que el context processor y notifications_view:
    // 1) Solo alertas posteriores a alerts_cleared_at (timestamp de "limpiar alertas")
    // 2) Excluye severidades bajas: info, bajo, medio
    const _EXCLUDED_RISKS = [_RISK.info, _RISK.bajo, _RISK.medio];
    const _clearedAtMs = window.ALERTS_CLEARED_AT ? window.ALERTS_CLEARED_AT * 1000 : null;
    const totalAlerts = (data.alert_log || []).filter(a => {
        if (_EXCLUDED_RISKS.includes(a.risk)) return false;
        if (_clearedAtMs) {
            const alertMs = a.timestamp ? new Date(a.timestamp.replace(' ', 'T') + 'Z').getTime() : 0;
            if (alertMs <= _clearedAtMs) return false;
        }
        return true;
    }).length;
    unreadNotificationCount = totalAlerts;
    setNotificationBadge(totalAlerts);
}

function updateSummaryValues(data) {
    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    };
    setVal('summaryPumpStatus', data.pump_on ? 'Encendida' : 'Apagada');
    setVal('summaryElevatorStatus', data.elevator_on ? 'Encendido' : 'Apagado');
}

// ═══════════════════════════════════════════════════════════════════
// 11.  Admin: Stats & recommendations
// ═══════════════════════════════════════════════════════════════════

function renderStatsTable(entries, containerId, firstColLabel, accentColor) {
    const div = document.getElementById(containerId);
    if (!div) return;
    if (entries.length) {
        const rows = entries.map(([k, v]) =>
            `<tr>` +
            `<td style="padding:8px var(--sp-3); font-weight:var(--weight-bold); font-size:var(--text-xs); border-top:1px solid var(--color-ink); color:var(--color-ink);">${getVariableName(k)}</td>` +
            `<td style="padding:8px var(--sp-3); font-weight:var(--weight-bold); text-align:right; font-size:var(--text-xs); border-top:1px solid var(--color-ink); color:var(--color-ink);">${formatNumeric(v.avg, k)}</td>` +
            `<td style="padding:8px var(--sp-3); text-align:right; font-size:var(--text-xs); border-top:1px solid var(--color-ink); color:var(--color-text-secondary);">${formatNumeric(v.min, k)}</td>` +
            `<td style="padding:8px var(--sp-3); text-align:right; font-size:var(--text-xs); border-top:1px solid var(--color-ink); color:var(--color-text-secondary);">${formatNumeric(v.max, k)}</td>` +
            `</tr>`
        ).join('');
        div.innerHTML = `
        <div class="table-wrapper" style="border-top: 6px solid ${accentColor} !important; margin-bottom: var(--sp-3);">
            <div class="table-responsive" style="overflow-x:auto;">
                <table class="report-table">
                    <thead>
                        <tr>
                            <th style="padding:10px var(--sp-3); border-bottom:2px solid var(--color-ink); background:var(--color-ink) !important; font-size:var(--text-xs); font-weight:var(--weight-bold); letter-spacing:var(--tracking-wide); color:#ffffff !important;"><i class="fa-solid fa-square-poll-vertical"></i> ${firstColLabel}</th>
                            <th style="text-align:right; padding:10px var(--sp-3); border-bottom:2px solid var(--color-ink); background:var(--color-ink) !important; font-size:var(--text-xs); font-weight:var(--weight-bold); letter-spacing:var(--tracking-wide); color:#ffffff !important;">Prom.</th>
                            <th style="text-align:right; padding:10px var(--sp-3); border-bottom:2px solid var(--color-ink); background:var(--color-ink) !important; font-size:var(--text-xs); font-weight:var(--weight-bold); letter-spacing:var(--tracking-wide); color:#ffffff !important;">Mín.</th>
                            <th style="text-align:right; padding:10px var(--sp-3); border-bottom:2px solid var(--color-ink); background:var(--color-ink) !important; font-size:var(--text-xs); font-weight:var(--weight-bold); letter-spacing:var(--tracking-wide); color:#ffffff !important;">Máx.</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows}
                    </tbody>
                </table>
            </div>
        </div>`;
    } else {
        div.innerHTML = '';
    }
}

function updateStatsAndRecs(stats, recs, attempts) {
    const entries = stats && Object.keys(stats).length ? Object.entries(stats) : [];
    renderStatsTable(entries.filter(([k]) => _BOMBA_VARS.includes(k)), 'statsBombaPanel', 'Estadísticas de la bomba', '#2563eb');
    renderStatsTable(entries.filter(([k]) => _ELEVADOR_VARS.includes(k)), 'statsElevadorPanel', 'Estadísticas del elevador', '#7c3aed');
    
    const recsContent = document.getElementById('recommendationsContent');
    if (recsContent) {
        if (recs && recs.length) {
            recsContent.innerHTML = '';
            const isOk = recs.length === 1 && recs[0].includes("normales");
            recs.forEach(rec => {
                let cardHtml = '';
                if (isOk) {
                    cardHtml = `
                        <div style="background: var(--state-ok-bg); color: var(--state-ok); border: 2px solid var(--color-ink); border-left: 6px solid var(--state-ok); padding: var(--sp-2) var(--sp-3); box-shadow: 4px 4px 0px var(--color-ink); font-weight: var(--weight-bold); display: flex; align-items: center; gap: 10px;">
                            <i class="fa-solid fa-circle-check" style="font-size: var(--text-md);"></i>
                            <span>${rec}</span>
                        </div>
                    `;
                } else {
                    const isCrit = rec.toLowerCase().includes("crític") || rec.toLowerCase().includes("urgente") || rec.toLowerCase().includes("atascado");
                    const bgColor = isCrit ? 'var(--state-critical-bg)' : 'var(--state-warn-bg)';
                    const borderColor = isCrit ? 'var(--state-critical)' : 'var(--state-warn)';
                    const icon = isCrit ? 'fa-solid fa-circle-exclamation' : 'fa-solid fa-triangle-exclamation';
                    
                    let doorNote = '';
                    if (rec.includes("puertas") && typeof attempts === 'number' && attempts > 0) {
                        doorNote = ` (Intentos fallidos: ${attempts})`;
                    }
                    
                    cardHtml = `
                        <div style="background: ${bgColor}; color: ${borderColor}; border: 2px solid var(--color-ink); border-left: 6px solid ${borderColor}; padding: var(--sp-2) var(--sp-3); box-shadow: 4px 4px 0px var(--color-ink); font-weight: var(--weight-bold); display: flex; align-items: center; gap: 10px;">
                            <i class="${icon}" style="font-size: var(--text-md);"></i>
                            <span>${rec}${doorNote}</span>
                        </div>
                    `;
                }
                const div = document.createElement('div');
                div.innerHTML = cardHtml.trim();
                recsContent.appendChild(div.firstElementChild);
            });
        }
    }
}

// ═══════════════════════════════════════════════════════════════════
// 12.  Admin: Thresholds
// ═══════════════════════════════════════════════════════════════════

function renderThresholdsPanel(th) {
    // Split variables into pump and elevator groups
    const bombaVars = _BOMBA_VARS.filter(k => th[k] && !_NO_RISK_VARS.includes(k));
    const elevadorVars = _ELEVADOR_VARS.filter(k => th[k] && !_NO_RISK_VARS.includes(k));
    // Also include any variable not in either list (fallback)
    const otherVars = Object.keys(th).filter(k =>
        !_NO_RISK_VARS.includes(k) &&
        !_BOMBA_VARS.includes(k) &&
        !_ELEVADOR_VARS.includes(k)
    );

    function buildCard(k, cfg) {
        let div = document.createElement('div');
        div.style.cssText = 'border:1px solid var(--color-border);padding:var(--sp-1);';

        const name = getVariableName(k);
        const unit = getUnit(k);
        const curVal = currentReadings[k];

        // Cargar límites físicos dinámicos
        const bounds = _SENSOR_RANGES[k];
        let boundsStr = '';
        if (bounds) {
            boundsStr = `Límite: ${bounds[0]} - ${bounds[1]}${unit ? ' ' + unit : ''}`;
        }

        let rightText = '';
        if (curVal !== undefined && curVal !== null) {
            rightText = `Actual: ${formatNumeric(curVal, k)}${unit ? ' ' + unit : ''}`;
            if (boundsStr) {
                rightText += ` · ${boundsStr}`;
            }
        } else if (boundsStr) {
            rightText = boundsStr;
        }

        let dirBadge;
        if (cfg.direction === 'higher') {
            dirBadge = '<span style="color:var(--state-critical);font-size:0.75rem;" title="Mayor es peor">\u2191</span>';
        } else if (cfg.direction === 'lower') {
            dirBadge = '<span style="color:#c2410c;font-size:0.75rem;" title="Menor es peor">\u2193</span>';
        } else {
            dirBadge = '<span style="color:var(--state-inactive);font-size:0.75rem;" title="Rango válido">\u27FA</span>';
        }

        let headerHtml = `<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
            <span style="font-size:var(--text-xs);font-weight:var(--weight-medium);letter-spacing:var(--tracking-wide);color:var(--color-text-secondary);">
                ${name}${unit && k !== 'trip_count' ? ' (' + unit + ')' : ''} ${dirBadge}
            </span>
            ${rightText ? '<span style="font-size:0.6rem;color:var(--color-text-secondary);">' + rightText + '</span>' : ''}
        </div>`;

        if (cfg.direction === 'range') {
            div.innerHTML = headerHtml + `
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--sp-1);">
                    <div class="form-group"><label class="form-label" style="color:#166534;">Mín aceptable</label><input type="number" step="any" data-var="${k}" data-level="low" value="${cfg.low}" style="border-left:4px solid #166534;"></div>
                    <div class="form-group"><label class="form-label" style="color:#991b1b;">Máx aceptable</label><input type="number" step="any" data-var="${k}" data-level="high" value="${cfg.high}" style="border-left:4px solid #991b1b;"></div>
                </div>
                <div style="margin-top:2px;font-size:0.6rem;color:var(--color-text-secondary);">Fuera de este rango = riesgo <strong style="color:#c2410c;">Alto</strong></div>
                <div class="thresh-error-msg" style="color:var(--state-critical);font-size:0.65rem;margin-top:4px;display:none;"></div>
                <input type="hidden" data-var="${k}" data-level="direction" value="range">`;
        } else {
            div.innerHTML = headerHtml + `
                <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:var(--sp-1);">
                    <div class="form-group"><label class="form-label" style="color:#166534;">\u2192 Medio</label><input type="number" step="any" data-var="${k}" data-level="low" value="${cfg.low}" style="border-left:4px solid #166534;"></div>
                    <div class="form-group"><label class="form-label" style="color:#b45309;">\u2192 Alto</label><input type="number" step="any" data-var="${k}" data-level="medium" value="${cfg.medium}" style="border-left:4px solid #b45309;"></div>
                    <div class="form-group"><label class="form-label" style="color:#991b1b;">\u2192 Cr\u00EDtico</label><input type="number" step="any" data-var="${k}" data-level="high" value="${cfg.high}" style="border-left:4px solid #991b1b;"></div>
                </div>
                <div class="thresh-error-msg" style="color:var(--state-critical);font-size:0.65rem;margin-top:4px;display:none;"></div>
                <input type="hidden" data-var="${k}" data-level="direction" value="${cfg.direction}">`;
        }
        return div;
    }

    function buildSection(containerId, vars) {
        const panel = document.getElementById(containerId);
        if (!panel) return;
        panel.innerHTML = '';
        vars.forEach(k => {
            const cfg = th[k];
            if (!cfg) return;
            panel.appendChild(buildCard(k, cfg));
        });
    }

    buildSection('thresholdsBombaPanel', bombaVars);
    buildSection('thresholdsElevadorPanel', elevadorVars);
    // fallback: any extra vars go to bomba panel
    if (otherVars.length) {
        const panel = document.getElementById('thresholdsBombaPanel');
        if (panel) otherVars.forEach(k => panel.appendChild(buildCard(k, th[k])));
    }

    // Guardar snapshot de valores originales para detectar cambios
    _originalThresholds = JSON.parse(JSON.stringify(th));
    validateThresholdInputs();
    // Update manual override hint with the new thresholds
    updateManualInputType();
}

function validateThresholdInputs() {
    const PANEL_IDS = ['thresholdsBombaPanel', 'thresholdsElevadorPanel', 'thresholdsPanel'];
    let hasError = false;
    let btn = document.getElementById('saveThresholdsBtn');
    let processed = {};

    // Helper: find an input across all panels
    function findInp(v, level) {
        for (const pid of PANEL_IDS) {
            const p = document.getElementById(pid);
            if (!p) continue;
            const el = p.querySelector(`input[data-var="${v}"][data-level="${level}"]`);
            if (el) return el;
        }
        return null;
    }

    // Helper: find a threshold card container
    function findCard(v) {
        for (const pid of PANEL_IDS) {
            const p = document.getElementById(pid);
            if (!p) continue;
            const el = p.querySelector(`input[data-var="${v}"]`);
            if (el) return el.closest('div[style*="border"]');
        }
        return null;
    }

    PANEL_IDS.forEach(panelId => {
        const panel = document.getElementById(panelId);
        if (!panel) return;
        panel.querySelectorAll('input[type="number"]').forEach(inp => {
            let v = inp.dataset.var;
            if (!v || processed[v]) return;
            processed[v] = true;
            let dirInp = findInp(v, 'direction');
            let dir = dirInp?.value;
            let lowInp = findInp(v, 'low');
            let medInp = findInp(v, 'medium');
            let highInp = findInp(v, 'high');
            let low = parseFloat(lowInp?.value);
            let med = parseFloat(medInp?.value);
            let high = parseFloat(highInp?.value);
            [lowInp, medInp, highInp].forEach(el => { if (el) el.style.borderColor = ''; });

            const card = findCard(v);
            const errorMsgEl = card ? card.querySelector('.thresh-error-msg') : null;
            if (errorMsgEl) {
                errorMsgEl.textContent = '';
                errorMsgEl.style.display = 'none';
            }

            let valid = false;
            let errorText = '';

            if (isNaN(low) || isNaN(high) || (dir !== 'range' && isNaN(med))) {
                errorText = 'Introduzca valores numéricos válidos.';
            } else {
                if (dir === 'range') {
                    valid = low < high;
                    if (!valid) {
                        errorText = 'El mínimo aceptable debe ser menor al máximo aceptable.';
                        if (lowInp) lowInp.style.borderColor = 'var(--state-critical)';
                        if (highInp) highInp.style.borderColor = 'var(--state-critical)';
                    }
                } else if (dir === 'higher') {
                    valid = low < med && med < high;
                    if (!valid) {
                        errorText = 'Los valores deben estar ordenados: Medio < Alto < Crítico.';
                        if (lowInp) lowInp.style.borderColor = 'var(--state-critical)';
                        if (medInp) medInp.style.borderColor = 'var(--state-critical)';
                        if (highInp) highInp.style.borderColor = 'var(--state-critical)';
                    }
                } else if (dir === 'lower') {
                    valid = low > med && med > high;
                    if (!valid) {
                        errorText = 'Los valores deben estar ordenados: Medio > Alto > Crítico.';
                        if (lowInp) lowInp.style.borderColor = 'var(--state-critical)';
                        if (medInp) medInp.style.borderColor = 'var(--state-critical)';
                        if (highInp) highInp.style.borderColor = 'var(--state-critical)';
                    }
                }

                // Validación cruzada contra los límites máximos del sensor
                const bounds = _SENSOR_RANGES[v];
                if (bounds && valid) {
                    const minBound = bounds[0];
                    const maxBound = bounds[1];
                    const unit = getUnit(v);
                    const unitStr = unit ? ' ' + unit : '';
                    if (dir === 'range') {
                        if (low < minBound && high > maxBound) {
                            valid = false;
                            errorText = `Los umbrales deben estar dentro de los límites del sensor (${minBound} - ${maxBound}${unitStr}).`;
                            if (lowInp) lowInp.style.borderColor = 'var(--state-critical)';
                            if (highInp) highInp.style.borderColor = 'var(--state-critical)';
                        } else if (low < minBound) {
                            valid = false;
                            errorText = `El mínimo aceptable no puede ser menor al límite físico (${minBound}${unitStr}).`;
                            if (lowInp) lowInp.style.borderColor = 'var(--state-critical)';
                        } else if (high > maxBound) {
                            valid = false;
                            errorText = `El máximo aceptable no puede ser mayor al límite físico (${maxBound}${unitStr}).`;
                            if (highInp) highInp.style.borderColor = 'var(--state-critical)';
                        }
                    } else if (dir === 'higher') {
                        if (low < minBound && high > maxBound) {
                            valid = false;
                            errorText = `Los umbrales deben estar dentro de los límites del sensor (${minBound} - ${maxBound}${unitStr}).`;
                            if (lowInp) lowInp.style.borderColor = 'var(--state-critical)';
                            if (highInp) highInp.style.borderColor = 'var(--state-critical)';
                        } else if (low < minBound) {
                            valid = false;
                            errorText = `El umbral medio no puede ser menor al límite físico (${minBound}${unitStr}).`;
                            if (lowInp) lowInp.style.borderColor = 'var(--state-critical)';
                        } else if (high > maxBound) {
                            valid = false;
                            errorText = `El umbral crítico no puede ser mayor al límite físico (${maxBound}${unitStr}).`;
                            if (highInp) highInp.style.borderColor = 'var(--state-critical)';
                        }
                    } else if (dir === 'lower') {
                        if (low > maxBound && high < minBound) {
                            valid = false;
                            errorText = `Los umbrales deben estar dentro de los límites del sensor (${minBound} - ${maxBound}${unitStr}).`;
                            if (lowInp) lowInp.style.borderColor = 'var(--state-critical)';
                            if (highInp) highInp.style.borderColor = 'var(--state-critical)';
                        } else if (low > maxBound) {
                            valid = false;
                            errorText = `El umbral medio no puede ser mayor al límite físico (${maxBound}${unitStr}).`;
                            if (lowInp) lowInp.style.borderColor = 'var(--state-critical)';
                        } else if (high < minBound) {
                            valid = false;
                            errorText = `El umbral crítico no puede ser menor al límite físico (${minBound}${unitStr}).`;
                            if (highInp) highInp.style.borderColor = 'var(--state-critical)';
                        }
                    }
                }
            }

            if (!valid) {
                hasError = true;
                if (errorMsgEl && errorText) {
                    errorMsgEl.textContent = errorText;
                    errorMsgEl.style.display = 'block';
                }
            }
        });
    });

    // Detectar cambios respecto al snapshot original
    let hasChanges = false;
    PANEL_IDS.forEach(panelId => {
        const panel = document.getElementById(panelId);
        if (!panel) return;
        panel.querySelectorAll('input[type="number"]').forEach(inp => {
            const varKey = inp.dataset.var;
            const lvl = inp.dataset.level;
            if (!varKey || !lvl || lvl === 'direction') return;
            if (_originalThresholds[varKey] !== undefined && _originalThresholds[varKey][lvl] !== undefined) {
                if (parseFloat(inp.value) !== _originalThresholds[varKey][lvl]) hasChanges = true;
            }
        });
    });

    const shouldDisable = hasError || !hasChanges;
    if (btn) {
        btn.disabled = shouldDisable;
        btn.style.opacity = shouldDisable ? '0.5' : '1';
        btn.style.cursor = shouldDisable ? 'not-allowed' : 'pointer';
    }
}


async function saveThresholds() {
    let newTh = { edificio_id: EDIFICIO_ID };
    // Collect from both panels
    ['thresholdsBombaPanel', 'thresholdsElevadorPanel', 'thresholdsPanel'].forEach(panelId => {
        const panel = document.getElementById(panelId);
        if (!panel) return;
        panel.querySelectorAll('input[type="number"]').forEach(inp => {
            let v = inp.dataset.var, l = inp.dataset.level;
            if (!v || !l) return;
            if (!newTh[v]) newTh[v] = { direction: panel.querySelector(`input[data-var="${v}"][data-level="direction"]`)?.value || 'higher' };
            newTh[v][l] = parseFloat(inp.value);
        });
    });
    let resp = await csrfFetch('/api/thresholds/update/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(newTh) });
    let res = await resp.json();
    if (res.status === 'ok') {
        window.showToast('Umbrales guardados correctamente.', 'success');
        currentThresholds = res.thresholds;
        renderThresholdsPanel(res.thresholds);
        // Update the manual override hint immediately
        updateManualInputType();
    } else {
        window.showToast(`Error al guardar: ${res.message || 'Inténtelo de nuevo.'}`, 'error');
    }
}

// ═══════════════════════════════════════════════════════════════════
// 12.5. Admin: Sensor limits configuration
// ═══════════════════════════════════════════════════════════════════

let _originalLimits = {};

function renderLimitsPanel(ranges) {
    const bombaVars = _BOMBA_VARS.filter(k => ranges[k] && !_NO_RISK_VARS.includes(k));
    const elevadorVars = _ELEVADOR_VARS.filter(k => ranges[k] && !_NO_RISK_VARS.includes(k));

    function buildLimitCard(k, r) {
        let div = document.createElement('div');
        div.style.cssText = 'border:1px solid var(--color-border);padding:var(--sp-1);';

        const name = getVariableName(k);
        const unit = getUnit(k);
        const minVal = r[0];
        const maxVal = r[1];

        // Obtener el umbral crítico actual
        const thresh = currentThresholds[k];
        let threshStr = '';
        if (thresh && thresh.high !== undefined) {
            const label = (thresh.direction === 'range') ? 'Máx aceptable' : 'Crítico';
            threshStr = `${label}: ${thresh.high}${unit ? ' ' + unit : ''}`;
        }

        div.innerHTML = `
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
                <span style="font-size:var(--text-xs);font-weight:var(--weight-medium);letter-spacing:var(--tracking-wide);color:var(--color-text-secondary);">
                    ${name}${unit && k !== 'trip_count' ? ' (' + unit + ')' : ''}
                </span>
                ${threshStr ? `<span style="font-size:0.6rem;color:var(--color-text-secondary);" class="crit-threshold-hint" data-var="${k}">${threshStr}</span>` : ''}
            </div>
            <div class="form-group">
                <label class="form-label" style="color:var(--color-ink);">Límite máximo (Mínimo: ${minVal}${unit ? ' ' + unit : ''})</label>
                <input type="number" step="any" data-var="${k}" data-level="max" value="${maxVal}" style="border-left:4px solid var(--color-ink);">
                <div class="limit-error-msg" style="color:var(--state-critical);font-size:0.65rem;margin-top:2px;display:none;"></div>
            </div>
        `;
        return div;
    }

    function buildLimitSection(containerId, vars) {
        const panel = document.getElementById(containerId);
        if (!panel) return;
        panel.innerHTML = '';
        vars.forEach(k => {
            panel.appendChild(buildLimitCard(k, ranges[k]));
        });
    }

    buildLimitSection('limitsBombaPanel', bombaVars);
    buildLimitSection('limitsElevadorPanel', elevadorVars);

    _originalLimits = JSON.parse(JSON.stringify(ranges));
    validateLimitInputs();
}

function validateLimitInputs() {
    let hasError = false;
    let hasChanges = false;
    let btn = document.getElementById('saveLimitsBtn');

    ['limitsBombaPanel', 'limitsElevadorPanel'].forEach(panelId => {
        const panel = document.getElementById(panelId);
        if (!panel) return;
        panel.querySelectorAll('input[type="number"]').forEach(inp => {
            const v = inp.dataset.var;
            const val = parseFloat(inp.value);

            inp.style.borderColor = '';

            const card = inp.closest('.form-group') || inp.parentNode;
            const errorMsgEl = card ? card.querySelector('.limit-error-msg') : null;
            if (errorMsgEl) {
                errorMsgEl.textContent = '';
                errorMsgEl.style.display = 'none';
            }

            if (isNaN(val)) {
                hasError = true;
                inp.style.borderColor = 'var(--state-critical)';
                if (errorMsgEl) {
                    errorMsgEl.textContent = 'Introduzca un número válido.';
                    errorMsgEl.style.display = 'block';
                }
                return;
            }

            const defaultMin = (_originalLimits && _originalLimits[v]) ? _originalLimits[v][0] : 0;
            if (val <= defaultMin) {
                hasError = true;
                inp.style.borderColor = 'var(--state-critical)';
                if (errorMsgEl) {
                    errorMsgEl.textContent = `Debe ser mayor que el mínimo (${defaultMin}).`;
                    errorMsgEl.style.display = 'block';
                }
            }

            // Validar contra el umbral crítico
            const thresh = (window.currentThresholds || currentThresholds || {})[v];
            if (thresh && thresh.high !== undefined) {
                if (val < thresh.high) {
                    hasError = true;
                    inp.style.borderColor = 'var(--state-critical)';
                    if (errorMsgEl) {
                        const label = (thresh.direction === 'range') ? 'máximo aceptable' : 'crítico';
                        const unit = getUnit(v);
                        errorMsgEl.textContent = `No puede ser menor al umbral ${label} (${thresh.high}${unit ? ' ' + unit : ''}).`;
                        errorMsgEl.style.display = 'block';
                    }
                }
            }

            if (_originalLimits[v] && val !== _originalLimits[v][1]) {
                hasChanges = true;
            }
        });
    });

    const shouldDisable = hasError || !hasChanges;
    if (btn) {
        btn.disabled = shouldDisable;
        btn.style.opacity = shouldDisable ? '0.5' : '1';
        btn.style.cursor = shouldDisable ? 'not-allowed' : 'pointer';
    }
}

async function saveLimits() {
    let newLimits = { edificio_id: EDIFICIO_ID };
    ['limitsBombaPanel', 'limitsElevadorPanel'].forEach(panelId => {
        const panel = document.getElementById(panelId);
        if (!panel) return;
        panel.querySelectorAll('input[type="number"]').forEach(inp => {
            const v = inp.dataset.var;
            newLimits[v] = parseFloat(inp.value);
        });
    });

    let resp = await csrfFetch('/api/sensor-limits/update/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newLimits)
    });
    let res = await resp.json();
    if (res.status === 'ok') {
        window.showToast('Límites de sensores guardados correctamente.', 'success');
        _CONFIG.sensor_ranges = res.sensor_ranges;
        _SENSOR_RANGES = res.sensor_ranges;
        currentThresholds = res.thresholds || currentThresholds;
        renderLimitsPanel(res.sensor_ranges);
        updateManualInputType();
    } else {
        window.showToast(`Error al guardar: ${res.message || 'Inténtelo de nuevo.'}`, 'error');
    }
}

// ═══════════════════════════════════════════════════════════════════
// 13.  Admin: Manual sensor control
// ═══════════════════════════════════════════════════════════════════

/**
 * Returns a human-readable hint string showing the current threshold
 * levels for the given variable, e.g.
 *   "Medio > 30 | Alto > 50 | Crítico > 80 L/s"
 * Returns '' if the variable has no threshold config.
 */
function buildThresholdHint(varName) {
    const cfg = currentThresholds[varName];
    if (!cfg) return '';
    const unit = getUnit(varName);
    const u = unit ? ` ${unit}` : '';
    if (cfg.direction === 'range') {
        return `Rango válido: ${cfg.low}${u} – ${cfg.high}${u}`;
    }
    const low = cfg.low, med = cfg.medium, high = cfg.high;
    if (cfg.direction === 'higher') {
        return `Medio \u003e ${low}${u} \u00b7 Alto \u003e ${med}${u} \u00b7 Cr\u00edtico \u003e ${high}${u}`;
    }
    // lower
    return `Medio \u003c ${low}${u} \u00b7 Alto \u003c ${med}${u} \u00b7 Cr\u00edtico \u003c ${high}${u}`;
}

function updateManualInputType() {
    const v = document.getElementById('manualSensorSelect')?.value;
    const inp = document.getElementById('manualValueInput');
    const sel = document.getElementById('manualValueSelect');
    if (!v || !inp || !sel) return;

    if (v === 'door_status') {
        inp.style.display = 'none';
        sel.style.display = 'block';
        sel.innerHTML = '';
        const opts = Object.entries(_VALUE_DISPLAY['door_status'] || {});
        opts.forEach(([val, label]) => {
            if (val === 'open' || val === 'closed') {
                let opt = document.createElement('option');
                opt.value = val;
                opt.textContent = label;
                sel.appendChild(opt);
            }
        });
        inp.value = '';
    } else if (v === 'motor_stuck') {
        inp.style.display = 'none';
        sel.style.display = 'block';
        sel.innerHTML = '<option value="true">Sí</option><option value="false">No</option>';
        inp.value = '';
    } else {
        inp.style.display = 'block';
        sel.style.display = 'none';
        if (_SENSOR_RANGES[v]) {
            inp.min = _SENSOR_RANGES[v][0];
            inp.max = _SENSOR_RANGES[v][1];
            let unit = getUnit(v);
            let unitStr = unit ? ` ${unit}` : '';
            inp.placeholder = `Ej: ${_SENSOR_RANGES[v][0]} - ${_SENSOR_RANGES[v][1]}${unitStr}`;
        } else {
            inp.removeAttribute('min');
            inp.removeAttribute('max');
            let unit = getUnit(v);
            inp.placeholder = `Ingrese valor numérico${unit ? ' (' + unit + ')' : ''}`;
        }
    }
    updateManualRiskPreview();
    validateManualInput();
}

function populateManualSensorSelect() {
    const sel = document.getElementById('manualSensorSelect');
    const eqSel = document.getElementById('manualEquipmentSelect');
    if (!sel || !eqSel) return;
    sel.innerHTML = '';
    const eq = eqSel.value || 'pump';
    const vars = eq === 'pump' ? _BOMBA_VARS : _ELEVADOR_VARS;
    vars.forEach(v => {
        let opt = document.createElement('option');
        opt.value = v;
        let unit = getUnit(v);
        opt.textContent = getVariableName(v) + (unit && v !== 'trip_count' ? ` (${unit})` : '');
        sel.appendChild(opt);
    });
    updateManualInputType();
}

function updateSensorTypeIndicator() {
    const v = document.getElementById('manualSensorSelect')?.value;
    const el = document.getElementById('sensorTypeIndicator');
    if (el && v) el.textContent = _BOMBA_VARS.includes(v) ? 'Bomba / Eléctrico' : 'Elevador / Motor';
}

function updateManualRiskPreview() {
    const v = document.getElementById('manualSensorSelect')?.value;
    const inp = document.getElementById('manualValueInput');
    const sel = document.getElementById('manualValueSelect');
    const span = document.getElementById('manualRiskPreview');
    if (!span || !v) return;

    // Run validation first
    const status = validateManualInput();

    if (status.hasError) {
        // Show validation error in risk preview line
        span.innerHTML = `<span style="color:var(--state-critical);font-weight:bold;font-size:0.65rem;"><i class="fa-solid fa-circle-exclamation"></i> ${status.errorText}</span>`;
        return;
    }

    if (status.empty) {
        // Show threshold hint instead of blank
        const hint = buildThresholdHint(v);
        if (hint) {
            span.innerHTML = `<span style="color:var(--color-text-secondary);font-size:0.6rem;">${hint}</span>`;
        } else {
            span.innerHTML = '';
        }
        return;
    }

    let raw = '';
    if (v === 'door_status' || v === 'motor_stuck') {
        raw = sel.value;
    } else {
        raw = inp.value;
    }

    let val = raw;
    if (v === 'door_status') { /* string */ }
    else if (v === 'motor_stuck') val = (raw === 'true' || raw === '1');
    else {
        let n = parseFloat(raw);
        if (isNaN(n)) return;
        val = n;
    }

    if (_NO_RISK_VARS.includes(v)) {
        span.innerHTML = '';
    } else {
        let ri = getRiskClass(v, val);
        span.innerHTML = `Riesgo estimado: <span class="badge ${ri.badge}">${ri.label}</span>`;
    }
}

function validateManualInput() {
    const v = document.getElementById('manualSensorSelect')?.value;
    const inp = document.getElementById('manualValueInput');
    const sendBtn = document.getElementById('sendManualBtn');

    if (!v) return { hasError: false, empty: true };

    let hasError = false;
    let errorText = '';
    let empty = false;

    if (v === 'door_status' || v === 'motor_stuck') {
        empty = false;
    } else if (inp) {
        const raw = inp.value.trim();
        empty = !raw;
        if (!empty) {
            const val = parseFloat(raw);
            if (isNaN(val)) {
                hasError = true;
                errorText = 'Introduzca un número válido.';
            } else if (_SENSOR_RANGES[v]) {
                const min = _SENSOR_RANGES[v][0];
                const max = _SENSOR_RANGES[v][1];
                if (val < min || val > max) {
                    hasError = true;
                    const unit = getUnit(v);
                    const unitStr = unit ? ' ' + unit : '';
                    errorText = `El valor debe estar entre ${min} y ${max}${unitStr}.`;
                }
            }
        }
    }

    if (inp) {
        inp.style.borderColor = hasError ? 'var(--state-critical)' : '';
    }

    if (sendBtn) {
        const disabled = empty || hasError;
        sendBtn.disabled = disabled;
        sendBtn.style.opacity = disabled ? '0.5' : '1';
        sendBtn.style.cursor = disabled ? 'not-allowed' : 'pointer';
    }

    return { hasError, errorText, empty };
}

async function sendManualValue() {
    const v = document.getElementById('manualSensorSelect')?.value;
    const inp = document.getElementById('manualValueInput');
    const sel = document.getElementById('manualValueSelect');

    if (!v) return;
    let raw = '';
    if (v === 'door_status' || v === 'motor_stuck') {
        raw = sel.value;
    } else {
        raw = inp.value;
    }

    if (raw === undefined || raw === '') { window.showToast('Complete todos los campos.', 'error'); return; }
    let val = raw;
    if (v === 'door_status') {
        val = raw.toLowerCase();
        const aceptados = ['open', 'closed'];
        if (!aceptados.includes(val)) {
            window.showToast(`Valores aceptados: ${aceptados.join(', ')}.`, 'error');
            return;
        }
    } else if (v === 'motor_stuck') {
        val = (raw === 'true' || raw === '1');
    } else {
        let n = parseFloat(raw);
        if (isNaN(n)) { window.showToast('Introduzca un valor numérico válido.', 'error'); return; }
        if (_SENSOR_RANGES[v] && (n < _SENSOR_RANGES[v][0] || n > _SENSOR_RANGES[v][1])) {
            return;
        }
        val = n;
    }
    try {
        let resp = await csrfFetch('/api/manual-update/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ variable: v, value: val, edificio_id: EDIFICIO_ID }) });
        let res = await resp.json();
        if (res.status === 'ok') {
            window.showToast('Valor enviado correctamente.', 'success');
        } else {
            window.showToast(res.message || 'No se pudo aplicar el valor.', 'error');
        }
    } catch (e) {
        window.showToast('Error de conexión. Inténtelo de nuevo.', 'error');
    }
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
        }
    } catch (e) { setSimMessage('Error al pausar o reanudar la simulación.', 'error'); }
}

function updatePauseBtn(paused) {
    const btn = document.getElementById('simPauseBtn');
    if (!btn) return;
    if (paused) {
        btn.innerHTML = '<i class="fas fa-play"></i> <span>Reanudar</span>';
        btn.className = 'btn btn-secondary';
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
            setSimMessage(data.message, 'success');
            updatePauseBtn(false);
            const fp = document.getElementById('simFaultPump');
            const fe = document.getElementById('simFaultElevator');
            if (fp) fp.value = '';
            if (fe) fe.value = '';
        } else { setSimMessage(data.message, 'error'); }
    } catch (e) { setSimMessage('Error al reiniciar la simulación.', 'error'); }
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
        if (data.status === 'ok') { setSimMessage(data.message, 'success'); }
        else { setSimMessage(data.message, 'error'); }
    } catch (e) { setSimMessage('Error al gestionar la falla.', 'error'); }
}

async function setSpeed(speed) {
    if (!EDIFICIO_ID) return;

    document.querySelectorAll('.speed-btn').forEach(btn => {
        if (parseFloat(btn.dataset.speed) === speed) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    try {
        let resp = await csrfFetch(`/api/sim/${EDIFICIO_ID}/set-speed/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ speed: speed }) });
        let data = await resp.json();
    } catch (e) { /* silent */ }
}

function setSimMessage(msg, type) {
    window.showToast(msg, type === 'error' ? 'error' : type === 'success' ? 'success' : 'info');
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
    
    let ul = container.querySelector('.notif-list');
    if (!ul) {
        ul = document.createElement('ul');
        ul.className = 'notif-list';
        container.appendChild(ul);
    }

    const riskLower = String(data.risk || 'info').toLowerCase();
    const li = document.createElement('li');
    li.className = `notif-item hist-item-${riskLower} live-notif-item`;

    let badgeClass = 'sensor-info';
    if (data.risk === 'CRÍTICO') badgeClass = 'sensor-critical';
    else if (data.risk === 'ALTO') badgeClass = 'sensor-high';
    else if (data.risk === 'MEDIO') badgeClass = 'sensor-warning';
    else if (data.risk === 'BAJO') badgeClass = 'sensor-active';

    const valueStr = String(data.value);
    const unit = getUnit(data.variable);
    const showValueBox = valueStr !== 'true' && valueStr !== 'True' && valueStr !== 'false' && valueStr !== 'False' && valueStr !== 'undefined' && valueStr !== 'null' && valueStr.trim() !== '';
    const valueHtml = showValueBox 
        ? `<span style="font-family: monospace; font-size: var(--text-xs); border: 2px solid var(--color-ink); background: var(--color-bg); padding: 2px 6px; font-weight: var(--weight-bold); color: var(--color-ink);">${formatNumeric(data.value, data.variable)}${unit ? ' ' + unit : ''}</span>`
        : '';

    let dateStr = '';
    if (data.timestamp) {
        try {
            const parsedDate = new Date(data.timestamp.replace(' ', 'T') + 'Z');
            if (!isNaN(parsedDate.getTime())) {
                dateStr = parsedDate.toLocaleString();
            } else {
                dateStr = data.timestamp;
            }
        } catch (e) {
            dateStr = data.timestamp;
        }
    }

    li.innerHTML = `
        <div class="notif-body">
            <div style="display: flex; align-items: center; gap: var(--sp-1); flex-wrap: wrap; margin-bottom: 6px;">
                <span class="sensor-badge ${badgeClass}">${safeText(data.risk)}</span>
                ${valueHtml}
                <span style="font-weight: var(--weight-bold); color: var(--color-ink); font-size: var(--text-base);">${safeText(getVariableName(data.variable))}</span>
            </div>
            <p style="margin: 0; font-size: var(--text-sm); color: var(--color-text-secondary); line-height: var(--leading-normal);">${safeText(data.message)}</p>
            <div class="notif-meta" style="margin-top: 8px;">
                <span><i class="fa-solid fa-clock"></i> ${dateStr}</span>
            </div>
        </div>
    `;
    ul.prepend(li);
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
                <span style="font-size:var(--text-lg);font-weight:var(--weight-bold);color:var(--color-ink);letter-spacing:var(--tracking-wide);">Desactivar alertas</span>
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
    btn.className = 'btn btn-primary';
    btn.innerHTML = '<i class="fa-solid fa-bell"></i> Desactivar alertas';
    await csrfFetch('/notifications/toggle-alerts/', { method: 'POST', body: JSON.stringify({ enabled: true }) });
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
                toggleBtn.className = 'btn btn-primary';
                toggleBtn.innerHTML = '<i class="fa-solid fa-bell"></i> Desactivar alertas';
                await csrfFetch('/notifications/toggle-alerts/', { method: 'POST', body: JSON.stringify({ enabled: true }) });
                await window.showAlert('Alertas activadas con éxito.', 'success');
                window.location.reload();
            } else {
                const minutes = await showDurationPicker();
                if (minutes === undefined) return;
                toggleBtn.dataset.enabled = 'false';
                toggleBtn.className = 'btn btn-secondary';
                if (minutes !== null) {
                    const untilMs = Date.now() + minutes * 60 * 1000;
                    toggleBtn.dataset.disabledUntilMs = untilMs;
                    startAlertCountdown(untilMs);
                } else {
                    toggleBtn.dataset.disabledUntilMs = '';
                    toggleBtn.innerHTML = '<i class="fa-solid fa-bell-slash"></i> Activar alertas';
                }
                await csrfFetch('/notifications/toggle-alerts/', { method: 'POST', body: JSON.stringify({ enabled: false, duration_minutes: minutes }) });
                const label = minutes === null ? 'indefinidamente'
                    : minutes < 60 ? `por ${minutes} min`
                        : minutes === 60 ? 'por 1 hora'
                            : `por ${minutes / 60} horas`;
                await window.showAlert(`Alertas pausadas ${label}.`, 'success');
                window.location.reload();
            }
        });
    }

    const emailToggleBtn = document.getElementById('toggleEmailAlertsBtn');
    if (emailToggleBtn) {
        emailToggleBtn.addEventListener('click', async () => {
            const isCurrentlyEnabled = emailToggleBtn.dataset.enabled === 'true';
            const newEnabled = !isCurrentlyEnabled;
            emailToggleBtn.dataset.enabled = newEnabled ? 'true' : 'false';
            emailToggleBtn.className = newEnabled ? 'btn btn-primary' : 'btn btn-secondary';
            emailToggleBtn.innerHTML = newEnabled
                ? '<i class="fa-solid fa-envelope"></i> Desactivar correos'
                : '<i class="fa-solid fa-envelope"></i> Activar correos';
            await csrfFetch('/notifications/toggle-email-alerts/', {
                method: 'POST',
                body: JSON.stringify({ enabled: newEnabled }),
            });
            const msg = newEnabled ? 'Correos activados con éxito.' : 'Correos desactivados con éxito.';
            await window.showAlert(msg, 'success');
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
    if (window.IS_LIMITS_PAGE) {
        const url = `/api/sensor-limits/?edificio_id=${EDIFICIO_ID}`;
        fetch(url)
            .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
            .then(data => {
                hideAllStates();
                currentThresholds = data.thresholds || {};
                renderLimitsPanel(data.limits || {});
            })
            .catch(() => {
                showState('stateOffline');
            });
        return;
    }

    const isThresholdsPage = document.getElementById('saveThresholdsBtn') !== null;
    if (isThresholdsPage) {
        // Fetch thresholds directly so the page works even without a running simulator
        const url = `/api/thresholds/?edificio_id=${EDIFICIO_ID}`;
        fetch(url)
            .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
            .then(data => {
                hideAllStates();
                currentThresholds = data || {};
                renderThresholdsPanel(currentThresholds);

                // Then try to fetch status to populate current values, but ignore failure
                fetch(`/api/status/?edificio_id=${EDIFICIO_ID}`)
                    .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
                    .then(statusData => {
                        if (statusData.current) {
                            currentReadings = statusData.current;
                            renderThresholdsPanel(currentThresholds);
                        }
                    }).catch(() => { });
            })
            .catch(() => {
                showState('stateOffline');
            });
        return;
    }

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
    const saveThreshBtn = document.getElementById('saveThresholdsBtn');
    const threshPanel = document.getElementById('thresholdsPanel');
    const manualValInput = document.getElementById('manualValueInput');
    const manualValSelect = document.getElementById('manualValueSelect');
    const manualSensorSel = document.getElementById('manualSensorSelect');
    const manualEquipSel = document.getElementById('manualEquipmentSelect');
    const sendManualBtn = document.getElementById('sendManualBtn');

    if (pauseBtn) pauseBtn.addEventListener('click', togglePause);
    if (resetBtn) resetBtn.addEventListener('click', resetSim);
    if (faultPump) faultPump.addEventListener('change', () => injectFault('pump'));
    if (faultElev) faultElev.addEventListener('change', () => injectFault('elevator'));

    document.querySelectorAll('.speed-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const speed = parseFloat(e.target.dataset.speed);
            setSpeed(speed);
        });
    });

    if (saveThreshBtn) saveThreshBtn.addEventListener('click', saveThresholds);
    const saveLimitsBtn = document.getElementById('saveLimitsBtn');
    const limitsBombaPanel = document.getElementById('limitsBombaPanel');
    const limitsElevadorPanel = document.getElementById('limitsElevadorPanel');
    if (saveLimitsBtn) saveLimitsBtn.addEventListener('click', saveLimits);
    if (limitsBombaPanel) limitsBombaPanel.addEventListener('input', validateLimitInputs);
    if (limitsElevadorPanel) limitsElevadorPanel.addEventListener('input', validateLimitInputs);

    const threshBombaPanel = document.getElementById('thresholdsBombaPanel');
    const threshElevadorPanel = document.getElementById('thresholdsElevadorPanel');
    if (threshPanel) threshPanel.addEventListener('input', validateThresholdInputs);
    if (threshBombaPanel) threshBombaPanel.addEventListener('input', validateThresholdInputs);
    if (threshElevadorPanel) threshElevadorPanel.addEventListener('input', validateThresholdInputs);
    if (manualValInput) manualValInput.addEventListener('input', updateManualRiskPreview);
    if (manualValSelect) manualValSelect.addEventListener('change', updateManualRiskPreview);
    if (manualEquipSel) {
        manualEquipSel.addEventListener('change', () => {
            populateManualSensorSelect();
            updateSensorTypeIndicator();
        });
    }
    if (manualSensorSel) {
        manualSensorSel.addEventListener('change', () => {
            updateManualInputType();
            updateSensorTypeIndicator();
        });
    }
    if (sendManualBtn) sendManualBtn.addEventListener('click', sendManualValue);

    // Deshabilitar botón "Enviar" cuando el campo está vacío
    validateManualInput();
    if (manualValInput) {
        manualValInput.addEventListener('input', () => {
            validateManualInput();
            updateManualRiskPreview();
        });
    }
    if (manualValSelect) {
        manualValSelect.addEventListener('change', () => {
            validateManualInput();
            updateManualRiskPreview();
        });
    }
    if (manualSensorSel) {
        manualSensorSel.addEventListener('change', () => {
            validateManualInput();
            updateManualRiskPreview();
        });
    }
    if (manualEquipSel) {
        manualEquipSel.addEventListener('change', () => {
            validateManualInput();
            updateManualRiskPreview();
        });
    }

    fetchSimStatus().then(data => {
        if (data) {
            updatePauseBtn(data.paused);
            document.querySelectorAll('.speed-btn').forEach(btn => {
                if (parseFloat(btn.dataset.speed) === data.speed) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            });
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
    if (window.IS_LIMITS_PAGE) {
        showState('stateLoading');
        fetchInitialData();
        if (IS_ADMIN) {
            setupAdminEvents();
        }
        setupBuildingSelector();
        return;
    }

    const isMonitoringPage = document.getElementById('activeMonitoring') !== null;
    if (!isMonitoringPage) {
        if (document.getElementById('live-notifications-list')) {
            const badgeCountEl = document.getElementById('notificationBadgeCount');
            if (badgeCountEl) unreadNotificationCount = parseInt(badgeCountEl.textContent, 10) || 0;
            initLiveNotifications();
            if (EDIFICIO_ID) {
                connectSSE();
            }
        }
        const toggleBtn = document.getElementById('toggleAlertsBtn');
        if (toggleBtn) {
            toggleBtn.disabled = false;
            toggleBtn.classList.remove('is-hidden');
            const sessionEnabled = toggleBtn.dataset.enabled === 'true';
            const disabledUntilMs = parseInt(toggleBtn.dataset.disabledUntilMs || '0', 10);
            if (sessionEnabled) {
                toggleBtn.className = 'btn btn-primary';
                toggleBtn.innerHTML = '<i class="fa-solid fa-bell"></i> Desactivar alertas';
            } else if (disabledUntilMs && disabledUntilMs > Date.now()) {
                toggleBtn.className = 'btn btn-secondary';
                startAlertCountdown(disabledUntilMs);
            } else {
                toggleBtn.className = 'btn btn-secondary';
                toggleBtn.innerHTML = '<i class="fa-solid fa-bell-slash"></i> Activar alertas';
            }
        }

        const emailToggleBtn = document.getElementById('toggleEmailAlertsBtn');
        if (emailToggleBtn) {
            emailToggleBtn.disabled = false;
            emailToggleBtn.classList.remove('is-hidden');
            const emailEnabled = emailToggleBtn.dataset.enabled === 'true';
            if (emailEnabled) {
                emailToggleBtn.className = 'btn btn-primary';
                emailToggleBtn.innerHTML = '<i class="fa-solid fa-envelope"></i> Desactivar correos';
            } else {
                emailToggleBtn.className = 'btn btn-secondary';
                emailToggleBtn.innerHTML = '<i class="fa-solid fa-envelope-slash"></i> Activar correos';
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
