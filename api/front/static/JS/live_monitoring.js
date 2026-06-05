const BACKEND_ORIGINS = ['http://localhost:5000', 'http://127.0.0.1:5000'];
let MONITOR_BACKEND_ORIGIN = BACKEND_ORIGINS[0];
let SSE_URL = `${MONITOR_BACKEND_ORIGIN}/stream/monitoreo`;
let monitorConnectionTimeout = null;

async function resolveMonitorBackendOrigin() {
    for (const origin of BACKEND_ORIGINS) {
        try {
            const response = await fetch(`${origin}/api/status`, { method: 'GET', mode: 'cors' });
            if (response.ok) {
                MONITOR_BACKEND_ORIGIN = origin;
                SSE_URL = `${MONITOR_BACKEND_ORIGIN}/stream/monitoreo`;
                console.info('Usando backend de monitoreo en', origin);
                return origin;
            }
        } catch (error) {
            console.warn('No se puede conectar a', origin, error);
        }
    }
    console.warn('No se pudo detectar backend de monitoreo; usando', MONITOR_BACKEND_ORIGIN);
    return MONITOR_BACKEND_ORIGIN;
}

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
    if (risk === 'Crítico') return 'badge-red';
    if (risk === 'Alto') return 'badge-orange';
    if (risk === 'Medio') return 'badge-yellow';
    return 'badge-green';
}

function getVariableName(variable) {
    const names = {
        flow_rate: 'Caudal',
        pressure: 'Presión',
        temperature: 'Temperatura',
        vibration: 'Vibración',
        tank_level: 'Nivel de tanque',
        voltage: 'Voltaje',
        current: 'Corriente',
        position: 'Posición',
        speed: 'Velocidad',
        load: 'Carga',
        trip_count: 'Viajes',
        door_status: 'Puerta',
        energy: 'Energía',
        motor_stuck: 'Motor atascado'
    };
    return names[variable] || variable.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function getUnit(variable) {
    const units = {
        flow_rate: 'L/s',
        pressure: 'bar',
        temperature: '°C',
        vibration: 'mm/s',
        tank_level: '%',
        speed: 'm/s',
        load: 'kg',
        trip_count: 'viajes',
        energy: 'kW',
        voltage: 'V',
        current: 'A',
    };
    return units[variable] || '';
}

function renderCard(variable, value, risk, label) {
    const name = getVariableName(variable).toUpperCase();
    const badgeClass = getRiskBadge(risk);
    const displayValue = variable === 'motor_stuck' ? (value ? 'Sí' : 'No') :
        (variable === 'door_status' ? (value === 'open' ? 'Abierta' : (value === 'closed' ? 'Cerrada' : safeText(value))) :
            `${formatNumeric(value, variable)} ${getUnit(variable)}`);
    let riskCls = 'risk-low';
    if (risk === 'Medio') riskCls = 'risk-med';
    else if (risk === 'Alto') riskCls = 'risk-high';
    else if (risk === 'Crítico') riskCls = 'risk-crit';

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

    chart1 = createChart('chart1', {
        type: 'bar',
        data: {
            labels: ['Caudal (L/s)', 'Presión (bar)', 'Temp (°C)', 'Vibración (mm/s)', 'Tanque (%)', 'Voltaje (V)', 'Corriente (A)'],
            datasets: [{
                backgroundColor: '#0a0a0a',
                borderColor: '#0a0a0a',
                borderWidth: 1,
                data: [0, 0, 0, 0, 0, 0, 0]
            }]
        },
        options: chartDefaults
    });

    chart2 = createChart('chart2', {
        type: 'bar',
        data: {
            labels: ['Velocidad (m/s)', 'Carga (kg)', 'Energía (kW)'],
            datasets: [{
                backgroundColor: '#0a0a0a',
                borderColor: '#0a0a0a',
                borderWidth: 1,
                data: [0, 0, 0]
            }]
        },
        options: chartDefaults
    });
}

function updateCharts(history) {
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
        if (r.risk === 'Crítico') return '#991b1b'; // Red
        if (r.risk === 'Alto') return '#c2410c'; // Orange
        if (r.risk === 'Medio') return '#b45309'; // Amber/Yellow
        return '#166534'; // Green / Low
    };

    if (chart1) {
        chart1.data.datasets[0].data = [
            getLatest('flow_rate'),
            getLatest('pressure'),
            getLatest('temperature'),
            getLatest('vibration'),
            getLatest('tank_level'),
            getLatest('voltage'),
            getLatest('current')
        ];
        chart1.data.datasets[0].backgroundColor = [
            getSensorColor('flow_rate'),
            getSensorColor('pressure'),
            getSensorColor('temperature'),
            getSensorColor('vibration'),
            getSensorColor('tank_level'),
            getSensorColor('voltage'),
            getSensorColor('current')
        ];
        chart1.data.datasets[0].borderColor = chart1.data.datasets[0].backgroundColor;
        chart1.update();
    }
    if (chart2) {
        chart2.data.datasets[0].data = [
            getLatest('speed'),
            getLatest('load'),
            getLatest('energy')
        ];
        chart2.data.datasets[0].backgroundColor = [
            getSensorColor('speed'),
            getSensorColor('load'),
            getSensorColor('energy')
        ];
        chart2.data.datasets[0].borderColor = chart2.data.datasets[0].backgroundColor;
        chart2.update();
    }
}

function isBombaVariable(variable) {
    return ['flow_rate', 'pressure', 'temperature', 'vibration', 'tank_level', 'voltage', 'current'].includes(variable);
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
    setElementText('summaryFlowRate', `${formatNumeric(current.flow_rate)} L/s`);
    setElementText('summaryPressure', `${formatNumeric(current.pressure)} bar`);
    setElementText('summaryTemperature', `${formatNumeric(current.temperature)} °C`);
    setElementText('summaryVoltage', `${formatNumeric(current.voltage)} V`);
    setElementText('summaryCurrent', `${formatNumeric(current.current)} A`);
    setElementText('summaryAlertCount', alertCount);
    setElementText('summaryRationing', rationingText);
    setElementText('summaryPumpStatus', data.pump_on ? 'ENCENDIDA' : 'APAGADA');
    setElementText('summaryElevatorStatus', data.elevator_on ? 'ENCENDIDO' : 'APAGADO');
    const protectionStatusEl = document.getElementById('summaryProtectionStatus');
    if (protectionStatusEl) {
        protectionStatusEl.textContent = data.protection_active ? 'ACTIVA' : 'INACTIVA';
    }

    const bombaCards = sensors.filter(s => isBombaVariable(s.id)).map(sensor => {
        const value = sensor.valor !== undefined ? sensor.valor : current[sensor.id];
        return renderCard(sensor.id, value, sensor.riesgo || 'Desconocido', sensor.nombre);
    }).join('');
    const ascensorCards = sensors.filter(s => !isBombaVariable(s.id)).map(sensor => {
        const value = sensor.valor !== undefined ? sensor.valor : current[sensor.id];
        const risk = sensor.id === 'motor_stuck'
            ? (sensor.valor ? 'Crítico' : 'Bajo')
            : (sensor.riesgo || 'Desconocido');
        return renderCard(sensor.id, value, risk, sensor.nombre);
    }).join('');

    document.getElementById('bombaCards').innerHTML = bombaCards;
    document.getElementById('ascensorCards').innerHTML = ascensorCards;

    updateCharts(data.history || []);

    const totalAlerts = (data.alert_log || []).filter(a => a.risk !== 'Info').length;
    unreadNotificationCount = totalAlerts;
    setNotificationBadge(totalAlerts);

    // Toggle button state is driven by Django session; simulator state is not authoritative.
}

function renderNotificationList(alerts) {
    const container = document.getElementById('live-notifications-list');
    if (!container) return;
    const placeholder = document.getElementById('live-no-notif');
    if (placeholder) {
        placeholder.remove();
    }

    // Filtrar alertas de nivel Info — solo mostrar Crítico, Alto, Medio, Bajo
    const filtered = (alerts || []).filter(a => a.risk !== 'Info');

    if (filtered.length === 0) {
        unreadNotificationCount = 0;
        setNotificationBadge(0);
        container.innerHTML = `
            <div class="no-notif" id="live-no-notif">
                <i class="fa-solid fa-bell-slash"></i>
                <p>No hay notificaciones pendientes.</p>
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

function fetchLiveNotifications() {
    fetch(`${MONITOR_BACKEND_ORIGIN}/get_alert_log`)
        .then((r) => r.ok ? r.json() : Promise.reject(r.statusText))
        .then((alerts) => {
            renderNotificationList(alerts);
            renderConnectionStatus(true, 'Backend de monitoreo conectado');
        })
        .catch((error) => {
            renderConnectionStatus(false, `No se puede conectar al backend de monitoreo (${MONITOR_BACKEND_ORIGIN}).`);
            console.warn('Error cargando alertas desde app27.py:', error);
        });
}

function renderConnectionStatus(isConnected, message) {
    const badge = document.getElementById('monitor-backend-status');
    if (badge) {
        badge.textContent = message || (isConnected ? 'Backend de monitoreo conectado' : 'No se pudo conectar al backend de monitoreo.');
        badge.className = isConnected ? 'sensor-active' : 'sensor-critical';
    }

    if (isConnected && monitorConnectionTimeout) {
        clearTimeout(monitorConnectionTimeout);
        monitorConnectionTimeout = null;
    }

    // Toggle button state is driven by Django session, not simulator connectivity.
    // No changes to toggleBtn here.

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
    if (typeof EventSource === 'undefined') {
        console.warn('EventSource no está disponible en este navegador.');
        fetchInitialData();
        return;
    }

    const source = new EventSource(SSE_URL);

    source.onopen = () => {
        if (monitorConnectionTimeout) {
            clearTimeout(monitorConnectionTimeout);
            monitorConnectionTimeout = null;
        }
        renderConnectionStatus(true, 'Backend de monitoreo conectado');
        console.info('Conectado al backend de monitoreo SSE en', SSE_URL);

        // Push the session-stored alert state to the simulator now that it's online.
        const toggleBtn = document.getElementById('toggleAlertsBtn');
        if (toggleBtn) {
            const sessionEnabled = toggleBtn.dataset.enabled === 'true';
            fetch(`${MONITOR_BACKEND_ORIGIN}/toggle_alerts`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: sessionEnabled })
            }).catch(() => { });
        }
    };

    source.onerror = (err) => {
        console.error('Error de conexión SSE:', err);
        if (!monitorConnectionTimeout) {
            monitorConnectionTimeout = setTimeout(() => {
                renderConnectionStatus(false, 'El simulador de monitoreo está apagado. Comuníquese con el administrador para encenderlo.');
                monitorConnectionTimeout = null;
            }, 3500);
        }
    };

    source.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            renderLiveMonitor(data);
        } catch (error) {
            console.error('Error parseando evento SSE:', error);
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

        // Hover effect on duration buttons
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

async function reEnableAlerts() {
    const btn = document.getElementById('toggleAlertsBtn');
    if (!btn) return;
    btn.dataset.enabled = 'true';
    btn.dataset.disabledUntilMs = '';
    btn.className = 'btn-alerts-toggle enabled';
    btn.innerHTML = '<i class="fa-solid fa-bell"></i> Desactivar alertas';

    const csrfToken = getCookie('csrftoken');
    const headers = { 'Content-Type': 'application/json' };
    if (csrfToken) headers['X-CSRFToken'] = csrfToken;
    fetch('/notificaciones/toggle_alerts/', { method: 'POST', headers, body: JSON.stringify({ enabled: true }) }).catch(() => { });
    fetch(`${MONITOR_BACKEND_ORIGIN}/toggle_alerts`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: true }) }).catch(() => { });
    await window.showAlert('El tiempo de pausa ha expirado. Alertas reactivadas.', 'success');
    window.location.reload();
}

function initLiveNotifications() {
    const notifContainer = document.getElementById('live-notifications-list');
    if (!notifContainer) return;
    // Disabled to avoid overwriting Django database notifications, pagination and filtering
    // fetchLiveNotifications();
    // setInterval(fetchLiveNotifications, 5000);

    const toggleBtn = document.getElementById('toggleAlertsBtn');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', async () => {
            const isCurrentlyEnabled = toggleBtn.dataset.enabled === 'true';

            if (!isCurrentlyEnabled) {
                // ── Re-enable ─────────────────────────────────────────
                if (alertCountdownInterval) { clearInterval(alertCountdownInterval); alertCountdownInterval = null; }
                toggleBtn.dataset.enabled = 'true';
                toggleBtn.dataset.disabledUntilMs = '';
                toggleBtn.className = 'btn-alerts-toggle enabled';
                toggleBtn.innerHTML = '<i class="fa-solid fa-bell"></i> Desactivar alertas';

                const csrfToken = getCookie('csrftoken');
                const h = { 'Content-Type': 'application/json' };
                if (csrfToken) h['X-CSRFToken'] = csrfToken;
                try { await fetch('/notificaciones/toggle_alerts/', { method: 'POST', headers: h, body: JSON.stringify({ enabled: true }) }); }
                catch (err) { console.error('Error al guardar estado en sesión Django:', err); }
                fetch(`${MONITOR_BACKEND_ORIGIN}/toggle_alerts`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: true }) }).catch(() => { });
                await window.showAlert('Alertas activadas con éxito.', 'success');
                window.location.reload();

            } else {
                // ── Disable: ask for duration ──────────────────────────
                const minutes = await showDurationPicker();
                if (minutes === undefined) return; // cancelled

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

                const csrfToken = getCookie('csrftoken');
                const h = { 'Content-Type': 'application/json' };
                if (csrfToken) h['X-CSRFToken'] = csrfToken;
                try { await fetch('/notificaciones/toggle_alerts/', { method: 'POST', headers: h, body: JSON.stringify({ enabled: false, duration_minutes: minutes }) }); }
                catch (err) { console.error('Error al guardar estado en sesión Django:', err); }
                fetch(`${MONITOR_BACKEND_ORIGIN}/toggle_alerts`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: false }) }).catch(() => { });

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
            const shouldClear = await window.showConfirm('¿Estás seguro de que deseas limpiar todas las notificaciones?');

            if (shouldClear) {
                try {
                    const csrfToken = getCookie('csrftoken');
                    const headers = { 'Content-Type': 'application/json' };
                    if (csrfToken) {
                        headers['X-CSRFToken'] = csrfToken;
                    }

                    const respDjango = await fetch('/notificaciones/limpiar/', {
                        method: 'POST',
                        headers: headers
                    });

                    await fetch(`${MONITOR_BACKEND_ORIGIN}/clear_alerts`, { method: 'POST' }).catch(() => { });

                    if (respDjango.ok) {
                        await window.showAlert('Notificaciones limpiadas con éxito.', 'success');
                        window.location.href = window.location.pathname;
                    } else {
                        throw new Error('Error al limpiar');
                    }
                } catch (error) {
                    console.error('Error:', error);
                    await window.showAlert('No se pudieron limpiar las notificaciones.', 'error');
                }
            }
        });
    }
}

function fetchInitialData() {
    fetch(`${MONITOR_BACKEND_ORIGIN}/api/status`)
        .then((r) => r.ok ? r.json() : Promise.reject(r.statusText))
        .then((data) => renderLiveMonitor(data))
        .catch((error) => {
            console.warn('No se pudo obtener el estado inicial desde el backend de monitoreo.', error);
        });
}

window.addEventListener('DOMContentLoaded', async () => {
    setNotificationBadge(0);
    initCharts();

    // Render toggle button from Django session state immediately (always enabled, no spinner)
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

    // Start 3.5-second connection fallback timer
    monitorConnectionTimeout = setTimeout(() => {
        renderConnectionStatus(false, 'El simulador de monitoreo está apagado. Comuníquese con el administrador para encenderlo.');
        monitorConnectionTimeout = null;
    }, 3500);

    await resolveMonitorBackendOrigin();

    initLiveMonitoring();
    initLiveNotifications();
});
