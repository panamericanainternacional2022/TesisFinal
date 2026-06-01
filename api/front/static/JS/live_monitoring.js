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
    const name = label || getVariableName(variable);
    const badgeClass = getRiskBadge(risk);
    const displayValue = variable === 'motor_stuck' ? (value ? 'Sí' : 'No') : formatNumeric(value);
    return `
        <div class="monitor-card">
            <div class="monitor-card-title">${name}</div>
            <div class="monitor-card-value">${displayValue} ${getUnit(variable)}</div>
            <div class="monitor-card-meta"><span class="monitor-card-badge ${badgeClass}">${risk}</span></div>
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
    unreadNotificationCount += 1;
    setNotificationBadge(unreadNotificationCount);
    const container = document.getElementById('live-notifications-list');
    if (!container) return;
    const placeholder = document.getElementById('live-no-notif');
    if (placeholder) {
        placeholder.remove();
    }
    const item = document.createElement('div');
    item.className = 'notif-item live-notif-item';
    item.innerHTML = `
        <div class="notif-icon"><i class="fa-solid fa-bell"></i></div>
        <div class="notif-body">
            <p>${safeText(notification.message)}</p>
            <div class="notif-meta">
                <span><i class="fa-regular fa-clock"></i> ${new Date(notification.timestamp).toLocaleString()}</span>
                <span><strong>Variable:</strong> ${safeText(notification.variable)}</span>
                <span><strong>Riesgo:</strong> ${safeText(notification.risk)}</span>
            </div>
        </div>
    `;
    container.prepend(item);
}

function buildChartHistory(history, variables) {
    const timestamps = [...new Set(history.map(item => item.timestamp))].slice(-20);
    return {
        labels: timestamps,
        datasets: variables.map(variable => {
            return {
                label: getVariableName(variable),
                data: timestamps.map(ts => {
                    const entry = history.filter(item => item.timestamp === ts).find(item => item.variable === variable);
                    return entry ? entry.value : null;
                }),
                fill: false,
                tension: 0.25,
                borderWidth: 2,
                pointRadius: 3,
            };
        })
    };
}

function initCharts() {
    chart1 = createChart('chart1', {
        type: 'bar',
        data: { labels: [], datasets: [
            { label: 'Caudal', backgroundColor: '#2563eb', borderColor: '#1d4ed8', borderWidth: 1, borderRadius: 6 },
            { label: 'Presión', backgroundColor: '#ef4444', borderColor: '#dc2626', borderWidth: 1, borderRadius: 6 },
            { label: 'Temperatura', backgroundColor: '#f59e0b', borderColor: '#d97706', borderWidth: 1, borderRadius: 6 }
        ] },
        options: { responsive: true, plugins: { legend: { position: 'top' } }, scales: { x: { title: { display: true, text: 'Timestamp' } }, y: { beginAtZero: true } }, datasets: { bar: { barPercentage: 0.7, categoryPercentage: 0.8 } } }
    });
    chart2 = createChart('chart2', {
        type: 'bar',
        data: { labels: [], datasets: [
            { label: 'Vibración', backgroundColor: '#8b5cf6', borderColor: '#7c3aed', borderWidth: 1, borderRadius: 6 },
            { label: 'Nivel de tanque', backgroundColor: '#10b981', borderColor: '#059669', borderWidth: 1, borderRadius: 6 }
        ] },
        options: { responsive: true, plugins: { legend: { position: 'top' } }, scales: { x: { title: { display: true, text: 'Timestamp' } }, y: { beginAtZero: true } }, datasets: { bar: { barPercentage: 0.7, categoryPercentage: 0.8 } } }
    });
    chart3 = createChart('chart3', {
        type: 'bar',
        data: { labels: [], datasets: [
            { label: 'Velocidad', backgroundColor: '#0ea5e9', borderColor: '#0284c7', borderWidth: 1, borderRadius: 6 },
            { label: 'Carga', backgroundColor: '#e11d48', borderColor: '#be123c', borderWidth: 1, borderRadius: 6 },
            { label: 'Energía', backgroundColor: '#f97316', borderColor: '#ea580c', borderWidth: 1, borderRadius: 6 }
        ] },
        options: { responsive: true, plugins: { legend: { position: 'top' } }, scales: { x: { title: { display: true, text: 'Timestamp' } }, y: { beginAtZero: true } }, datasets: { bar: { barPercentage: 0.7, categoryPercentage: 0.8 } } }
    });
    chart4 = createChart('chart4', {
        type: 'bar',
        data: { labels: [], datasets: [
            { label: 'Voltaje', backgroundColor: '#0f766e', borderColor: '#0f766e', borderWidth: 1, borderRadius: 6 },
            { label: 'Corriente', backgroundColor: '#7c3aed', borderColor: '#6d28d9', borderWidth: 1, borderRadius: 6 }
        ] },
        options: { responsive: true, plugins: { legend: { position: 'top' } }, scales: { x: { title: { display: true, text: 'Timestamp' } }, y: { beginAtZero: true } }, datasets: { bar: { barPercentage: 0.7, categoryPercentage: 0.8 } } }
    });
}

function updateCharts(history) {
    if (!history || !history.length) return;
    const h = history.slice(-20);
    const chart1Data = buildChartHistory(h, ['flow_rate', 'pressure', 'temperature']);
    const chart2Data = buildChartHistory(h, ['vibration', 'tank_level']);
    const chart3Data = buildChartHistory(h, ['speed', 'load', 'energy']);
    const chart4Data = buildChartHistory(h, ['voltage', 'current']);

    if (chart1) { chart1.data.labels = chart1Data.labels; chart1.data.datasets.forEach((ds, idx) => ds.data = chart1Data.datasets[idx].data); chart1.update(); }
    if (chart2) { chart2.data.labels = chart2Data.labels; chart2.data.datasets.forEach((ds, idx) => ds.data = chart2Data.datasets[idx].data); chart2.update(); }
    if (chart3) { chart3.data.labels = chart3Data.labels; chart3.data.datasets.forEach((ds, idx) => ds.data = chart3Data.datasets[idx].data); chart3.update(); }
    if (chart4) { chart4.data.labels = chart4Data.labels; chart4.data.datasets.forEach((ds, idx) => ds.data = chart4Data.datasets[idx].data); chart4.update(); }
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
    document.getElementById('summaryPumpStatus').textContent = data.pump_on ? 'ON' : 'OFF';
    document.getElementById('summaryElevatorStatus').textContent = data.elevator_on ? 'ON' : 'OFF';
    const protectionStatusEl = document.getElementById('summaryProtectionStatus');
    if (protectionStatusEl) {
        protectionStatusEl.textContent = data.protection_active ? 'ON' : 'OFF';
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
                    <span><strong>Variable:</strong> ${safeText(alert.variable)}</span>
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
    if (!badge) return;
    badge.textContent = message || (isConnected ? 'Backend de monitoreo conectado' : 'No se pudo conectar al backend de monitoreo.');
    badge.className = isConnected ? 'sensor-active' : 'sensor-critical';
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
        renderConnectionStatus(false, `Error: no se encontró app27.py en ${MONITOR_BACKEND_ORIGIN}`);
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

function initLiveNotifications() {
    const notifContainer = document.getElementById('live-notifications-list');
    if (!notifContainer) return;
    fetchLiveNotifications();
    setInterval(fetchLiveNotifications, 5000);
}

function fetchInitialData() {
    fetch(`${MONITOR_BACKEND_ORIGIN}/api/status`)
        .then((r) => r.ok ? r.json() : Promise.reject(r.statusText))
        .then((data) => renderLiveMonitor(data))
        .catch((error) => {
            renderConnectionStatus(false, 'No se pudo obtener estado inicial de app27.py.');
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
