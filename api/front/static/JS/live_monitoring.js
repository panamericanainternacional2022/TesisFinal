const BACKEND_ORIGINS = ['http://localhost:5000', 'http://127.0.0.1:5000'];
let MONITOR_BACKEND_ORIGIN = BACKEND_ORIGINS[0];
let SSE_URL = `${MONITOR_BACKEND_ORIGIN}/stream/monitoreo`;

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

function formatNumeric(value) {
    if (typeof value === 'number') {
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
        motor_stuck: 'Motor pegado'
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
            `${formatNumeric(value)} ${getUnit(variable)}`);
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

function addLiveNotificationEvent(notification) {
    if (notification.risk === 'Info') return;
    unreadNotificationCount += 1;
    setNotificationBadge(unreadNotificationCount);
    const container = document.getElementById('live-notifications-list');
    if (!container) return;
    const placeholder = document.getElementById('live-no-notif');
    if (placeholder) {
        placeholder.remove();
    }
    
    const risk = safeText(notification.risk);
    const variable = getVariableName(notification.variable);
    const value = notification.value !== null && notification.value !== undefined ? notification.value : '';
    const unit = getUnit(notification.variable);
    
    let badgeClass = 'sensor-active';
    if (risk === 'Crítico') badgeClass = 'sensor-critical';
    else if (risk === 'Alto' || risk === 'Medio') badgeClass = 'sensor-warning';
    
    const isBoolean = value === true || value === false || String(value).toLowerCase() === 'true' || String(value).toLowerCase() === 'false';
    const displayVal = value !== '' && !isBoolean ? `${value}${unit ? ' ' + unit : ''}` : '';
    const valueBadge = displayVal !== '' ? `<span style="font-family: monospace; font-size: var(--text-xs); border: 2px solid var(--color-ink); background: var(--color-bg); padding: 2px 6px; font-weight: var(--weight-bold); color: var(--color-ink);">${displayVal}</span>` : '';

    const item = document.createElement('li');
    item.className = 'notif-item live-notif-item';
    item.innerHTML = `
        <div class="notif-icon"><i class="fa-solid fa-bell"></i></div>
        <div class="notif-body">
            <div style="display: flex; align-items: center; gap: var(--sp-1); flex-wrap: wrap; margin-bottom: 6px;">
                <span class="sensor-badge ${badgeClass}">${risk}</span>
                <span style="font-weight: var(--weight-bold); color: var(--color-ink); font-size: var(--text-base);">${variable}</span>
                ${valueBadge}
            </div>
            <p style="margin: 0; font-size: var(--text-sm); color: var(--color-text-secondary); line-height: var(--leading-normal);">${safeText(notification.message)}</p>
            <div class="notif-meta" style="margin-top: 8px;">
                <span><i class="fa-regular fa-clock"></i> ${new Date(notification.timestamp).toLocaleString()}</span>
                <span><i class="fa-solid fa-building"></i> Telemetría en vivo</span>
            </div>
        </div>
    `;
    
    let list = container.querySelector('.notif-list');
    if (!list) {
        list = document.createElement('ul');
        list.className = 'notif-list';
        container.appendChild(list);
    }
    list.prepend(item);
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
    const getLatest = (v) => {
        const r = history.filter(item => item.variable === v).pop();
        return r ? r.value : 0;
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
        chart1.update();
    }
    if (chart2) {
        chart2.data.datasets[0].data = [
            getLatest('speed'),
            getLatest('load'),
            getLatest('energy')
        ];
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

    document.getElementById('summaryLastUpdate').textContent = new Date().toLocaleTimeString();
    document.getElementById('summaryFlowRate').textContent = `${formatNumeric(current.flow_rate)} L/s`;
    document.getElementById('summaryPressure').textContent = `${formatNumeric(current.pressure)} bar`;
    document.getElementById('summaryTemperature').textContent = `${formatNumeric(current.temperature)} °C`;
    document.getElementById('summaryVoltage').textContent = `${formatNumeric(current.voltage)} V`;
    document.getElementById('summaryCurrent').textContent = `${formatNumeric(current.current)} A`;
    document.getElementById('summaryAlertCount').textContent = alertCount;
    document.getElementById('summaryRationing').textContent = rationingText;
    document.getElementById('summaryPumpStatus').textContent = data.pump_on ? 'ENCENDIDA' : 'APAGADA';
    document.getElementById('summaryElevatorStatus').textContent = data.elevator_on ? 'ENCENDIDO' : 'APAGADO';
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

    const totalAlerts = (data.alert_log || []).length;
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

    if (!alerts || alerts.length === 0) {
        unreadNotificationCount = 0;
        setNotificationBadge(0);
        container.innerHTML = `
            <div class="no-notif" id="live-no-notif">
                <i class="fa-regular fa-bell-slash"></i>
                <p>No hay notificaciones pendientes.</p>
            </div>
        `;
        return;
    }

    unreadNotificationCount = alerts.length;
    setNotificationBadge(unreadNotificationCount);
    const items = alerts.map(alert => `
        <div class="notif-item live-notif-item">
            <div class="notif-icon"><i class="fa-solid fa-bell"></i></div>
            <div class="notif-body">
                <p>${safeText(alert.message)}</p>
                <div class="notif-meta">
                    <span><i class="fa-regular fa-clock"></i> ${new Date(alert.timestamp).toLocaleString()}</span>
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
        renderConnectionStatus(true, 'Backend de monitoreo conectado');
        console.info('Conectado al backend de monitoreo SSE en', SSE_URL);
    };

    source.onerror = (err) => {
        renderConnectionStatus(false, 'El simulador de monitoreo está apagado. Comuníquese con el administrador para encenderlo.');
        console.error('Error de conexión SSE:', err);
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

function initLiveNotifications() {
    const notifContainer = document.getElementById('live-notifications-list');
    if (!notifContainer) return;
    // Disabled to avoid overwriting Django database notifications, pagination and filtering
    // fetchLiveNotifications();
    // setInterval(fetchLiveNotifications, 5000);

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
                        renderNotificationList([]);
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
            renderConnectionStatus(false, 'El simulador de monitoreo está apagado. Comuníquese con el administrador para encenderlo.');
            console.warn('No se pudo obtener el estado inicial desde el backend de monitoreo.', error);
        });
}

window.addEventListener('DOMContentLoaded', async () => {
    setNotificationBadge(0);
    initCharts();
    await resolveMonitorBackendOrigin();
    initLiveMonitoring();
    initLiveNotifications();
});
