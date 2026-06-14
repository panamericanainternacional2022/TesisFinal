const EDIFICIO_ID = window.EDIFICIO_ID || 0;
const SSE_URL = EDIFICIO_ID ? `/sse/${EDIFICIO_ID}/` : null;
let monitorConnectionTimeout = null;

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

function getRiskBadge(risk) {
    if (risk === _RISK.critico) return 'badge-red';
    if (risk === _RISK.alto) return 'badge-orange';
    if (risk === _RISK.medio) return 'badge-yellow';
    return 'badge-green';
}

function _loadConfig() {
    const el = document.getElementById('dashConfig');
    return el ? JSON.parse(el.textContent) : null;
}

const _CONFIG = _loadConfig();
const _VAR_NAMES = (_CONFIG && _CONFIG.var_names) || {
    flow_rate: 'Caudal', pressure: 'Presión', temperature: 'Temperatura',
    vibration: 'Vibración', tank_level: 'Nivel de tanque', voltage: 'Voltaje',
    current: 'Corriente', position: 'Posición', speed: 'Velocidad', load: 'Carga',
    trip_count: 'Viajes', door_status: 'Puerta', energy: 'Energía', motor_stuck: 'Motor atascado'
};
const _UNITS = (_CONFIG && _CONFIG.units) || {
    flow_rate: 'L/s', pressure: 'bar', temperature: '°C', vibration: 'mm/s',
    tank_level: '%', speed: 'm/s', load: 'kg', trip_count: 'viajes',
    energy: 'kW', voltage: 'V', current: 'A'
};
const _BOMBA_VARS = (_CONFIG && _CONFIG.pump_vars) || [
    'flow_rate', 'pressure', 'temperature', 'vibration', 'tank_level', 'voltage', 'current'
];
const _ELEVADOR_VARS = (_CONFIG && _CONFIG.elevator_vars) || [
    'position', 'speed', 'load', 'trip_count', 'door_status', 'energy', 'motor_stuck'
];
const _RISK = (_CONFIG && _CONFIG.risk_labels) || {
    info: 'Info', bajo: 'Bajo', medio: 'Medio', alto: 'Alto', critico: 'Crítico', unknown: 'Desconocido'
};

function getVariableName(variable) {
    return _VAR_NAMES[variable] || variable.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function getUnit(variable) {
    return _UNITS[variable] || '';
}

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

let chart1, chart2, chart3, chart4;
let unreadNotificationCount = 0;
let alertCountdownInterval = null;

function createChart(canvasId, config) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;
    return new Chart(ctx, config);
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
            badge.setAttribute('aria-hidden', 'false');
        } else {
            badge.textContent = '';
            badge.style.display = 'none';
            badge.hidden = true;
            badge.setAttribute('aria-hidden', 'true');
        }
    });
}

function initCharts() {
    if (typeof Chart === 'undefined') {
        console.warn('Chart.js no se ha cargado. Los gráficos estarán desactivados.');
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

    chart1 = createChart('chart1', {
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

    chart2 = createChart('chart2', {
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

    const getLatestReading = (v) => {
        return history.filter(item => item.variable === v).pop();
    };

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

function isBombaVariable(variable) {
    return _BOMBA_VARS.includes(variable);
}

function renderLiveMonitor(data) {
    const current = data.current || {};
    const alertCount = (data.alert_log || []).length;
    const rationingText = data.rationing ? 'Racionamiento activo' : 'Operación normal';
    const sensors = data.sensors || [];

    const setElementText = (id, text) => {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    };

    setElementText('summaryLastUpdate', new Date().toLocaleTimeString());
    setElementText('summaryFlowRate', `${formatNumeric(current.flow_rate)} ${getUnit('flow_rate')}`);
    setElementText('summaryPressure', `${formatNumeric(current.pressure)} ${getUnit('pressure')}`);
    setElementText('summaryTemperature', `${formatNumeric(current.temperature)} ${getUnit('temperature')}`);
    setElementText('summaryVoltage', `${formatNumeric(current.voltage)} ${getUnit('voltage')}`);
    setElementText('summaryCurrent', `${formatNumeric(current.current)} ${getUnit('current')}`);
    setElementText('summaryAlertCount', alertCount);
    setElementText('summaryRationing', rationingText);
    setElementText('summaryPumpStatus', data.pump_on ? 'ENCENDIDA' : 'APAGADA');
    setElementText('summaryElevatorStatus', data.elevator_on ? 'ENCENDIDO' : 'APAGADO');
    const protectionStatusEl = document.getElementById('summaryProtectionStatus');
    if (protectionStatusEl) {
        protectionStatusEl.textContent = data.protection_active ? 'ACTIVA' : 'INACTIVA';
    }

    const updateBadge = (badgeId, statusVal) => {
        const badgeEl = document.getElementById(badgeId);
        if (badgeEl) {
            if (statusVal) {
                badgeEl.style.display = 'inline-flex';
                badgeEl.textContent = statusVal.toUpperCase();
                if (statusVal === 'falla') {
                    badgeEl.className = 'monitor-card-badge badge-red';
                } else if (statusVal === 'mantenimiento') {
                    badgeEl.className = 'monitor-card-badge badge-yellow';
                } else {
                    badgeEl.className = 'monitor-card-badge badge-green';
                }
            } else {
                badgeEl.style.display = 'none';
            }
        }
    };
    updateBadge('pumpStatusBadge', data.pump_status);
    updateBadge('elevatorStatusBadge', data.elevator_status);

    const equipTypes = data.equipment_types || ['bomba', 'elevador'];
    const hasPump = equipTypes.includes('bomba');
    const hasElevator = equipTypes.includes('elevador');
    const hasAnyEquipment = hasPump || hasElevator;

    const noEquipEl = document.getElementById('noEquipmentMessage');
    const activeContentEl = document.getElementById('monitoringActiveContent');
    if (noEquipEl) noEquipEl.style.display = hasAnyEquipment ? 'none' : 'block';
    if (activeContentEl) activeContentEl.style.display = hasAnyEquipment ? 'block' : 'none';

    if (!hasAnyEquipment) return;

    const bombaCards = sensors.filter(s => isBombaVariable(s.id)).map(sensor => {
        const value = sensor.valor !== undefined ? sensor.valor : current[sensor.id];
        return renderCard(sensor.id, value, sensor.riesgo || _RISK.unknown, sensor.nombre);
    }).join('');
    const elevadorCards = sensors.filter(s => !isBombaVariable(s.id)).map(sensor => {
        const value = sensor.valor !== undefined ? sensor.valor : current[sensor.id];
        const risk = sensor.id === 'motor_stuck'
            ? (sensor.valor ? _RISK.critico : _RISK.bajo)
            : (sensor.riesgo || _RISK.unknown);
        return renderCard(sensor.id, value, risk, sensor.nombre);
    }).join('');

    const bombaCardsEl = document.getElementById('bombaCards');
    if (bombaCardsEl) bombaCardsEl.innerHTML = bombaCards;
    const elevadorCardsEl = document.getElementById('elevadorCards');
    if (elevadorCardsEl) elevadorCardsEl.innerHTML = elevadorCards;

    const toggleDisplay = (id, show) => {
        const el = document.getElementById(id);
        if (el) el.style.display = show ? '' : 'none';
    };
    toggleDisplay('bombaSection', hasPump);
    toggleDisplay('elevadorSection', hasElevator);
    toggleDisplay('summaryPumpRow', hasPump);
    toggleDisplay('summaryElevatorRow', hasElevator);
    toggleDisplay('chartPumpPanel', hasPump);
    toggleDisplay('chartElevatorPanel', hasElevator);

    updateCharts(data.history || []);

    const _INFO_LABEL = 'Info';
    const totalAlerts = (data.alert_log || []).filter(a => a.risk !== _INFO_LABEL).length;
    unreadNotificationCount = totalAlerts;
    setNotificationBadge(totalAlerts);
}

function renderNotificationList(alerts) {
    const container = document.getElementById('live-notifications-list');
    if (!container) return;
    const placeholder = document.getElementById('live-no-notif');
    if (placeholder) {
        placeholder.remove();
    }

    const filtered = (alerts || []).filter(a => a.risk !== _INFO_LABEL);

    if (filtered.length === 0) {
        unreadNotificationCount = 0;
        setNotificationBadge(0);
        container.innerHTML = `
            <div class="no-notif" id="live-no-notif">
                <i class="fa-solid fa-bell-slash"></i>
                <p>No hay alertas pendientes.</p>
            </div>
        `;
        return;
    }

    unreadNotificationCount = filtered.length;
    setNotificationBadge(unreadNotificationCount);
    const items = filtered.map(alert => `
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

    container.innerHTML = items;
}

function renderConnectionStatus(isConnected, message) {
    const badge = document.getElementById('monitor-backend-status');
    if (badge) {
        badge.textContent = message || (isConnected ? 'Sistema de monitoreo conectado' : 'No se pudo conectar al sistema de monitoreo.');
        badge.className = isConnected ? 'sensor-active' : 'sensor-critical';
    }

    if (isConnected && monitorConnectionTimeout) {
        clearTimeout(monitorConnectionTimeout);
        monitorConnectionTimeout = null;
    }

    const activeContent = document.getElementById('monitoringActiveContent');
    const fallback = document.getElementById('userOfflineFallback');
    const loading = document.getElementById('userLoadingFallback');

    if (loading) {
        loading.style.display = 'none';
    }

    if (activeContent && fallback) {
        if (isConnected) {
            activeContent.style.display = 'block';
            fallback.style.display = 'none';
        } else {
            activeContent.style.display = 'none';
            fallback.style.display = 'flex';
        }
    }
}

function initLiveMonitoring() {
    if (!SSE_URL) {
        console.warn('Sin edificio_id definido; SSE no iniciado.');
        fetchInitialData();
        return;
    }
    if (typeof EventSource === 'undefined') {
        console.warn('EventSource no está disponible.');
        fetchInitialData();
        return;
    }

    const source = new EventSource(SSE_URL);

    source.onopen = () => {
        if (monitorConnectionTimeout) {
            clearTimeout(monitorConnectionTimeout);
            monitorConnectionTimeout = null;
        }
        renderConnectionStatus(true, 'Sistema de monitoreo conectado');
        console.info('Conectado SSE en', SSE_URL);
    };

    source.onerror = (err) => {
        console.error('Error SSE:', err);
        if (!monitorConnectionTimeout) {
            monitorConnectionTimeout = setTimeout(() => {
                renderConnectionStatus(false, 'El simulador de monitoreo está apagado.');
                monitorConnectionTimeout = null;
            }, 3500);
        }
    };

    source.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            renderLiveMonitor(data);
        } catch (error) {
            console.error('Error parseando SSE:', error);
        }
    };

    source.addEventListener('notification', (event) => {
        try {
            const data = JSON.parse(event.data);
            addLiveNotificationEvent(data);
        } catch (error) {
            console.error('Error parseando notificación SSE:', error);
        }
    });

    fetchInitialData();
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
            <p style="font-size:var(--text-sm);color:var(--color-text-secondary);margin-bottom:var(--sp-3);line-height:var(--leading-normal);">¿Por cuánto tiempo deseas desactivar las alertas?</p>
            <div id="durationGrid" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:var(--sp-3);">
                ${durations.map(d => `
                    <button data-minutes="${d.value === null ? 'null' : d.value}" style="
                        background:var(--color-surface);
                        border:2px solid var(--color-ink);
                        color:var(--color-ink);
                        padding:12px 8px;
                        font-family:var(--font);
                        font-size:var(--text-sm);
                        font-weight:var(--weight-bold);
                        cursor:pointer;
                        box-shadow:3px 3px 0px var(--color-ink);
                        transition:all 120ms ease;
                        border-radius:0 !important;
                    ">${d.label}</button>
                `).join('')}
            </div>
            <div style="display:flex;justify-content:flex-end;">
                <button id="durationCancelBtn" style="background:none;border:1px solid var(--color-ink);padding:8px var(--sp-2);cursor:pointer;font-family:var(--font);font-size:var(--text-sm);font-weight:var(--weight-medium);border-radius:0px !important;">Cancelar</button>
            </div>
        `;

        container.querySelectorAll('#durationGrid button').forEach(btn => {
            btn.addEventListener('mouseenter', () => {
                btn.style.background = 'var(--color-ink)';
                btn.style.color = 'var(--color-surface)';
                btn.style.transform = 'translate(-1px,-1px)';
                btn.style.boxShadow = '4px 4px 0px rgba(10,10,10,0.2)';
            });
            btn.addEventListener('mouseleave', () => {
                btn.style.background = 'var(--color-surface)';
                btn.style.color = 'var(--color-ink)';
                btn.style.transform = '';
                btn.style.boxShadow = '3px 3px 0px var(--color-ink)';
            });
        });

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
            const raw = btn.dataset.minutes;
            cleanUp(raw === 'null' ? null : parseInt(raw, 10));
        });
    });
}

// ── Countdown helpers ───────────────────────────────────────────────
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

function csrfFetch(url, options) {
    let csrfToken = getCookie('csrftoken');
    if (!csrfToken && window.CSRF_TOKEN) {
        csrfToken = window.CSRF_TOKEN;
    }
    const headers = options.headers || {};
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
    if (csrfToken) headers['X-CSRFToken'] = csrfToken;
    return fetch(url, { ...options, headers, credentials: 'same-origin' });
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
    const notifContainer = document.getElementById('live-notifications-list');
    if (!notifContainer) return;

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
                    } else {
                        throw new Error('Error al limpiar');
                    }
                } catch (error) {
                    console.error('Error:', error);
                    await window.showAlert('No se pudieron limpiar las alertas.', 'error');
                }
            }
        });
    }
}

function fetchInitialData() {
    const url = EDIFICIO_ID ? `/api/status/?edificio_id=${EDIFICIO_ID}` : '/api/status/';
    fetch(url)
        .then((r) => r.ok ? r.json() : Promise.reject(r.statusText))
        .then((data) => renderLiveMonitor(data))
        .catch((error) => {
            console.warn('No se pudo obtener estado inicial.', error);
        });
}

window.addEventListener('DOMContentLoaded', async () => {
    const isMonitoringPage = document.getElementById('live-monitoring-content') !== null;
    const isNotificationsPage = document.getElementById('live-notifications-list') !== null;

    if (isMonitoringPage) {
        setNotificationBadge(0);
        initCharts();

        monitorConnectionTimeout = setTimeout(() => {
            renderConnectionStatus(false, 'El simulador de monitoreo está apagado.');
            monitorConnectionTimeout = null;
        }, 3500);

        initLiveMonitoring();
    }

    if (isNotificationsPage) {
        const badgeCountEl = document.getElementById('notificationBadgeCount');
        if (badgeCountEl) {
            unreadNotificationCount = parseInt(badgeCountEl.textContent, 10) || 0;
        }
        initLiveNotifications();
    }

    const toggleBtn = document.getElementById('toggleAlertsBtn');
    if (toggleBtn) {
        toggleBtn.disabled = false;
        toggleBtn.style.opacity = '1';
        toggleBtn.style.cursor = 'pointer';
        toggleBtn.style.display = 'inline-flex';
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
});
