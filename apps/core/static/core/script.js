// =============================================================================
// 1. COMPONENTE: CustomSelect
// =============================================================================

class CustomSelect {
    constructor(el, options = {}) {
        if (!el || el.tagName !== 'SELECT') return;
        this.select = el;
        this.options = options;
        this._build();
        this._bind();
    }

    get value() { return this._hiddenInput.value; }
    set value(val) { this._setValue(val); }

    _build() {
        this.select.style.display = 'none';

        this.wrapper = document.createElement('div');
        this.wrapper.className = 'custom-select';

        this.trigger = document.createElement('button');
        this.trigger.type = 'button';
        this.trigger.className = 'custom-select-trigger';
        this.trigger.setAttribute('aria-haspopup', 'listbox');
        this.trigger.setAttribute('aria-expanded', 'false');
        if (this.select.disabled) this.trigger.disabled = true;

        this.valueEl = document.createElement('span');
        this.valueEl.className = 'custom-select-value';

        this.arrowEl = document.createElement('i');
        this.arrowEl.className = 'fa-solid fa-chevron-down custom-select-arrow';

        this.trigger.appendChild(this.valueEl);
        this.trigger.appendChild(this.arrowEl);

        this.menu = document.createElement('div');
        this.menu.className = 'custom-select-menu';
        this.menu.setAttribute('role', 'listbox');

        this._hiddenInput = document.createElement('input');
        this._hiddenInput.type = 'hidden';
        this._hiddenInput.name = this.select.name || '';
        this.select.removeAttribute('name');

        this._items = [];
        this._populateItems();

        const parent = this.select.parentNode;
        parent.insertBefore(this.wrapper, this.select);
        this.wrapper.appendChild(this.trigger);
        this.wrapper.appendChild(this.menu);
        this.wrapper.appendChild(this._hiddenInput);
    }

    _populateItems() {
        this.menu.innerHTML = '';
        this._items = [];
        Array.from(this.select.options).forEach((opt, i) => {
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'custom-select-item';
            item.textContent = opt.text;
            item.dataset.value = opt.value;
            item.dataset.index = i;
            item.setAttribute('role', 'option');
            if (opt.selected) {
                item.classList.add('selected');
                this.valueEl.textContent = opt.text;
                this._hiddenInput.value = opt.value;
            }
            if (opt.disabled) item.disabled = true;
            this.menu.appendChild(item);
            this._items.push(item);
        });
    }

    _bind() {
        this.trigger.addEventListener('click', (e) => {
            if (this.select.disabled) return;
            e.stopPropagation();
            this.toggle();
        });

        // Event delegation on menu — covers dynamically repopulated items too
        this.menu.addEventListener('click', (e) => {
            const item = e.target.closest('.custom-select-item');
            if (!item || item.disabled) return;
            e.stopPropagation();
            this._selectItem(item);
            this.select.dispatchEvent(new Event('change', { bubbles: true }));
            this.close();
        });

        document.addEventListener('click', () => this.close());

        document.addEventListener('keydown', (e) => {
            if (!this.menu.classList.contains('open')) return;

            const currentIndex = this._items.findIndex(el => el.classList.contains('selected'));
            let newIndex = currentIndex;

            switch (e.key) {
                case 'ArrowDown':
                    e.preventDefault();
                    newIndex = Math.min(currentIndex + 1, this._items.length - 1);
                    while (newIndex < this._items.length - 1 && this._items[newIndex].disabled) newIndex++;
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    newIndex = Math.max(currentIndex - 1, 0);
                    while (newIndex > 0 && this._items[newIndex].disabled) newIndex--;
                    break;
                case 'Enter':
                    e.preventDefault();
                    if (currentIndex >= 0 && !this._items[currentIndex].disabled) {
                        this._selectItem(this._items[currentIndex]);
                        this.select.dispatchEvent(new Event('change', { bubbles: true }));
                        this.close();
                    }
                    return;
                case 'Escape':
                    e.preventDefault();
                    this.close();
                    return;
                default:
                    return;
            }

            if (newIndex !== currentIndex && this._items[newIndex]) {
                this._items[newIndex].focus();
                this._items.forEach(el => el.classList.remove('selected'));
                this._items[newIndex].classList.add('selected');
                this.valueEl.textContent = this._items[newIndex].textContent;
                this._hiddenInput.value = this._items[newIndex].dataset.value;
                this._items[newIndex].scrollIntoView({ block: 'nearest' });
            }
        });
    }

    _selectItem(item) {
        this._items.forEach(el => el.classList.remove('selected'));
        item.classList.add('selected');
        this.valueEl.textContent = item.textContent;
        this._hiddenInput.value = item.dataset.value;
        this.select.value = item.dataset.value;
        if (this.options.onChange) this.options.onChange(item.dataset.value, item.textContent);
    }

    _setValue(val) {
        const item = this._items.find(el => el.dataset.value === String(val));
        if (item) this._selectItem(item);
    }

    open() {
        if (this.menu.classList.contains('open')) return;
        this.menu.classList.add('open');
        this.trigger.classList.add('open');
        this.trigger.setAttribute('aria-expanded', 'true');
        const selected = this._items.find(el => el.classList.contains('selected'));
        if (selected) { selected.scrollIntoView({ block: 'nearest' }); selected.focus(); }
    }

    close() {
        this.menu.classList.remove('open');
        this.trigger.classList.remove('open');
        this.trigger.setAttribute('aria-expanded', 'false');
    }

    toggle() {
        this.menu.classList.contains('open') ? this.close() : this.open();
    }

    updateOptions(options) {
        this.select.innerHTML = '';
        options.forEach(opt => {
            const o = document.createElement('option');
            o.value = opt.value;
            o.text = opt.text;
            if (opt.selected) o.selected = true;
            this.select.appendChild(o);
        });
        // Event delegation on menu handles new items automatically — no _rebindItems needed
        this._populateItems();
    }

    static init(selector = '.custom-select-init') {
        document.querySelectorAll(selector).forEach(el => {
            if (!el._customSelect) el._customSelect = new CustomSelect(el);
        });
    }
}

document.addEventListener('DOMContentLoaded', () => CustomSelect.init());


// =============================================================================
// 2. UTILIDADES GLOBALES: initFormState
// =============================================================================

window.initFormState = function initFormState(form, isEditing) {
    if (!form) return;
    const submitBtn = form.querySelector('.btn-primary');
    if (!submitBtn) return;

    const initialValues = {};
    form.querySelectorAll('input[name], select[name]').forEach(el => {
        initialValues[el.name] = el.value;
    });

    const setBtn = (disabled) => { submitBtn.disabled = disabled; };

    const checkState = () => {
        const hasErrors = form.querySelectorAll('.input-error').length > 0;
        let shouldEnable;
        if (isEditing) {
            const hasChanges = Array.from(form.querySelectorAll('input[name], select[name]'))
                .some(el => el.value !== (initialValues[el.name] || ''));
            shouldEnable = hasChanges && !hasErrors;
        } else {
            const allFilled = Array.from(form.querySelectorAll('input[required], select[required]'))
                .every(el => el.value.trim() !== '');
            shouldEnable = allFilled && !hasErrors;
        }
        setBtn(!shouldEnable);
    };

    setTimeout(checkState, 0);

    form.querySelectorAll('input, select').forEach(el => {
        ['input', 'change', 'blur'].forEach(evt =>
            el.addEventListener(evt, () => setTimeout(checkState, 0))
        );
    });

    return checkState;
};


// =============================================================================
// 3. UTILIDADES GLOBALES: Modal, Toast, csrfFetch, Dropdowns
// =============================================================================

(function (window) {

    // --- Modal customizado ---

    function showCustomModal({ title, message, type = 'info', showCancel = false }) {
        return new Promise((resolve) => {
            const ICON_MAP = {
                success: '<i class="fa-solid fa-circle-check custom-modal-icon custom-modal-icon-success"></i>',
                error: '<i class="fa-solid fa-circle-xmark custom-modal-icon custom-modal-icon-error"></i>',
            };
            const iconHtml = ICON_MAP[type] || '<i class="fa-solid fa-triangle-exclamation custom-modal-icon custom-modal-icon-warn"></i>';

            const backdrop = document.createElement('div');
            backdrop.className = 'custom-modal-backdrop';

            const container = document.createElement('div');
            container.className = 'custom-modal-container';
            container.innerHTML = `
                <div class="custom-modal-header">
                    ${iconHtml}
                    <span class="custom-modal-title">${title}</span>
                </div>
                <div class="custom-modal-body">${message}</div>
                <div class="custom-modal-actions">
                    ${showCancel ? '<button id="customModalCancelBtn" class="btn btn-secondary">Cancelar</button>' : ''}
                    <button id="customModalConfirmBtn" class="btn btn-primary">Aceptar</button>
                </div>
            `;

            backdrop.appendChild(container);
            document.body.appendChild(backdrop);
            setTimeout(() => backdrop.classList.add('active'), 10);

            const cleanUp = (value) => {
                backdrop.classList.remove('active');
                setTimeout(() => { backdrop.remove(); resolve(value); }, 150);
            };

            container.querySelector('#customModalConfirmBtn').addEventListener('click', () => cleanUp(true));
            if (showCancel) {
                container.querySelector('#customModalCancelBtn').addEventListener('click', () => cleanUp(false));
            }
        });
    }

    window.showCustomModal = showCustomModal;

    window.showAlert = (message, type = 'info') => {
        const TITLE_MAP = { error: 'Error', success: 'Éxito', warn: 'Advertencia', warning: 'Advertencia' };
        return showCustomModal({ title: TITLE_MAP[type] || 'Notificación', message, type, showCancel: false });
    };

    window.showConfirm = (message) =>
        showCustomModal({ title: 'Confirmar', message, type: 'confirm', showCancel: true });

    // --- Toast: un único listener delegado para todos los botones de cierre ---
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.toast-item .btn-icon');
        if (!btn) return;
        const toast = btn.closest('.toast-item');
        toast.style.transform = 'translateX(120%)';
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 350);
    });

    window.showToast = (message, type = 'info') => {
        let container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        const hasClose = type !== 'success';
        const toast = document.createElement('div');
        toast.className = `toast-item toast-${type}`;
        toast.innerHTML = `
            ${hasClose ? '<button type="button" class="btn btn-icon toast-close"><i class="fa-solid fa-xmark"></i></button>' : ''}
            <div class="toast-body-content" style="${hasClose ? 'padding-right:15px;' : 'padding-right:0;'}">${message}</div>
        `;
        container.appendChild(toast);
        requestAnimationFrame(() => { toast.style.transform = 'translateX(0)'; toast.style.opacity = '1'; });
        setTimeout(() => {
            toast.style.transform = 'translateX(120%)';
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 350);
        }, 5000);
    };

})(window);


// --- CSRF Fetch (versión única, robusta — sustituye a window.csrfFetch y la local) ---

function getCookie(name) {
    const found = document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith(`${name}=`));
    return found ? decodeURIComponent(found.slice(name.length + 1)) : null;
}

function csrfFetch(url, opts = {}) {
    let token = getCookie('csrftoken');
    if (!token && window.CSRF_TOKEN) token = window.CSRF_TOKEN;
    const headers = { 'X-CSRFToken': token, ...opts.headers };
    if (opts.body && !headers['Content-Type'] && !headers['content-type']) {
        headers['Content-Type'] = 'application/json';
    }
    opts.headers = headers;
    opts.credentials = 'same-origin';
    return fetch(url, opts);
}

// Exponer como global para templates que llamen window.csrfFetch directamente
window.csrfFetch = csrfFetch;


// --- Dropdowns: delegación de eventos, evita múltiples listeners ---

window.closeAllDropdowns = () => {
    document.querySelectorAll('.dropdown-menu.open').forEach(menu => {
        menu.classList.remove('open');
        const trigger = menu.previousElementSibling;
        if (trigger?.classList.contains('btn-icon')) trigger.classList.remove('open');
    });
};

window.initDropdowns = () => {
    document.addEventListener('click', (e) => {
        const trigger = e.target.closest('.actions-dropdown .btn-icon');
        if (trigger) {
            e.stopPropagation();
            const menu = trigger.nextElementSibling;
            const isOpen = menu.classList.contains('open');
            closeAllDropdowns();
            if (!isOpen) { menu.classList.add('open'); trigger.classList.add('open'); }
        } else {
            closeAllDropdowns();
        }
    });
};

// Delegación de eventos — no hay listeners individuales por enlace
window.initConfirmDelete = () => {
    document.addEventListener('click', (e) => {
        const link = e.target.closest('.js-btn-confirm-delete');
        if (!link) return;
        e.preventDefault();
        showCustomModal({
            title: 'Confirmar',
            message: link.getAttribute('data-confirm'),
            type: 'confirm',
            showCancel: true,
        }).then(confirmed => { if (confirmed) window.location.href = link.getAttribute('href'); });
    });
};

function initAutoSubmit() {
    document.querySelectorAll('.js-auto-submit').forEach(el => {
        el.addEventListener('change', function () { this.form.submit(); });
    });
}

document.addEventListener('DOMContentLoaded', () => {
    initDropdowns();
    initConfirmDelete();
    initAutoSubmit();
});


// =============================================================================
// 4. CONFIGURACIÓN DEL MÓDULO DE MONITOREO
// =============================================================================

// --- Endpoints de API centralizados (elimina URLs hardcodeadas en funciones) ---
const API = {
    thresholdsUpdate: '/api/thresholds/update/',
    limitsUpdate: '/api/sensor-limits/update/',
    manualUpdate: '/api/manual-update/',
    toggleAlerts: '/notifications/toggle-alerts/',
    toggleEmailAlerts: '/notifications/toggle-email-alerts/',
    clearNotifications: '/notifications/clear/',
    simStatus: (id) => `/api/sim/${id}/status/`,
    simPause: (id) => `/api/sim/${id}/pause/`,
    simReset: (id) => `/api/sim/${id}/reset/`,
    simInjectFault: (id) => `/api/sim/${id}/inject-fault/`,
    simClearFault: (id) => `/api/sim/${id}/clear-fault/`,
    simSetSpeed: (id) => `/api/sim/${id}/set-speed/`,
    status: (id) => id ? `/api/status/?edificio_id=${id}` : '/api/status/',
    thresholds: (id) => `/api/thresholds/?edificio_id=${id}`,
    sensorLimits: (id) => `/api/sensor-limits/?edificio_id=${id}`,
};

// --- Carga de configuración desde el DOM ---
const _CONFIG = (() => {
    const el = document.getElementById('appConfig');
    return el ? JSON.parse(el.textContent) : {};
})();

const IS_ADMIN = window.IS_ADMIN === true;
const _VAR_NAMES = _CONFIG.var_names || {};
const _UNITS = _CONFIG.units || {};
const _BOMBA_VARS = _CONFIG.pump_vars || [];
const _ELEVADOR_VARS = _CONFIG.elevator_vars || [];
const _RISK = _CONFIG.risk_labels || {};
const _NO_RISK_VARS = _CONFIG.no_risk_vars || [];
const _LIMITS_EXCLUDE_VARS = _CONFIG.limits_exclude_vars || [];
const _BOOLEAN_VARS = _CONFIG.boolean_vars || [];
const _ENUM_VARS = _CONFIG.enum_vars || [];
const _ENUM_RISK_VALUES = _CONFIG.enum_risk_values || {};
const _VALUE_DISPLAY = _CONFIG.value_display_es || {};
let _SENSOR_RANGES = _CONFIG.sensor_ranges || {};

// Pre-calculadas una sola vez — evita recalcular en cada actualización de gráfico
const CHART_PUMP_VARS = _BOMBA_VARS.filter(v => v !== 'tank_level');
const CHART_ELEV_VARS = _ELEVADOR_VARS.filter(
    v => v !== 'position' && v !== 'door_status' && v !== 'motor_stuck'
);

const CSS_CLASSES = {
    riskCard: { low: 'risk-low', med: 'risk-med', high: 'risk-high', crit: 'risk-crit' },
    statusBadge: { falla: 'badge badge-crit', mantenimiento: 'badge badge-med' },
};

let EDIFICIO_ID = _CONFIG.edificio_id || window.SELECTED_EDIFICIO_ID || 0;
let SSE_URL = EDIFICIO_ID ? `/sse/${EDIFICIO_ID}/` : null;

// --- Estado mutable del módulo ---
let sseSource = null;
let monitorConnectionTimeout = null;
let currentThresholds = {};
let _originalThresholds = {};
let _dirtySensorKeys = new Set();
let _limitsDirtyKeys = new Set();
let _unsavedGuardDisabled = false;
function _hasUnsavedChanges() {
    return _dirtySensorKeys.size > 0 || _limitsDirtyKeys.size > 0;
}
let currentReadings = {};
let chart1, chart2;
let unreadNotificationCount = 0;
let alertCountdownInterval = null;


// =============================================================================
// 5. FUNCIONES UTILITARIAS / LÓGICA DE NEGOCIO
// =============================================================================

const safeText = (value) => (value === null || value === undefined) ? '-' : String(value);

function formatNumeric(value, variable) {
    if (typeof value !== 'number') return safeText(value);
    if (variable === 'trip_count' || variable === 'load') return Math.round(value).toString();
    return value.toFixed(2);
}

const getVariableName = (variable) =>
    _VAR_NAMES[variable] || variable.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

const getUnit = (variable) => _UNITS[variable] || '';

function translateSensorValue(variable, value) {
    if (_VALUE_DISPLAY[variable]) {
        const tr = _VALUE_DISPLAY[variable][String(value)];
        if (tr !== undefined) return tr;
    }
    if (typeof value === 'boolean') return value ? 'Sí' : 'No';
    return null;
}

function getRiskBadge(risk) {
    if (risk === _RISK.critico) return 'badge-crit';
    if (risk === _RISK.alto) return 'badge-high';
    if (risk === _RISK.medio) return 'badge-med';
    if (risk === _RISK.bajo) return 'badge-low';
    return 'badge-info';
}

function getRiskClass(varName, value) {
    if (_BOOLEAN_VARS.includes(varName)) {
        const crit = !!value;
        return {
            card: crit ? CSS_CLASSES.riskCard.crit : CSS_CLASSES.riskCard.low,
            badge: `badge-${crit ? 'crit' : 'low'}`,
            label: crit ? _RISK.critico : _RISK.bajo,
        };
    }
    if (_ENUM_VARS.includes(varName)) {
        const risky = _ENUM_RISK_VALUES[varName] || [];
        const crit = risky.includes(String(value).toLowerCase());
        return {
            card: crit ? CSS_CLASSES.riskCard.crit : CSS_CLASSES.riskCard.low,
            badge: `badge-${crit ? 'crit' : 'low'}`,
            label: crit ? _RISK.critico : _RISK.bajo,
        };
    }
    if (_NO_RISK_VARS.includes(varName)) {
        return { card: CSS_CLASSES.riskCard.low, badge: 'badge-low', label: _RISK.bajo };
    }

    const cfg = currentThresholds[varName];
    if (!cfg) return { card: '', badge: 'badge-info', label: _RISK.unknown };

    let risk = _RISK.bajo, cls = 'low';
    if (cfg.direction === 'range') {
        if (!(value >= cfg.low && value <= cfg.high)) { risk = _RISK.alto; cls = 'high'; }
    } else {
        const { direction: d, low, medium: med, high } = cfg;
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
    return { card: CSS_CLASSES.riskCard[cls] || '', badge: `badge-${cls}`, label: risk };
}

const getCSSVar = (name) =>
    getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '';


// =============================================================================
// 6. RENDERIZADO DE UI: Tarjetas, Gráficos, Estados
// =============================================================================

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
            <div class="sensor-card-footer">${badgeHtml}</div>
        </div>
    `;
}

function updateCards(data) {
    const bombaContainer = document.getElementById('bombaCards');
    const elevadorContainer = document.getElementById('elevadorCards');
    if (!bombaContainer || !elevadorContainer) return;

    for (const [k, v] of Object.entries(data)) {
        const ri = getRiskClass(k, v);
        const displayValue = translateSensorValue(k, v) ?? `${formatNumeric(v, k)} ${getUnit(k)}`;
        const isNoRisk = _NO_RISK_VARS.includes(k);
        const finalClass = isNoRisk ? '' : ri.card;

        let card = document.getElementById(`sensor-card-${k}`);
        if (!card) {
            card = document.createElement('div');
            card.id = `sensor-card-${k}`;
            card.className = `sensor-card ${finalClass}`;
            const badgeHtml = isNoRisk ? '' : `<span class="badge ${ri.badge}">${ri.label}</span>`;
            card.innerHTML = `
                <div class="sensor-card-name">${getVariableName(k)}</div>
                <div class="sensor-card-value">${displayValue}</div>
                <div class="sensor-card-footer">${badgeHtml}</div>
            `;
            if (_BOMBA_VARS.includes(k)) bombaContainer.appendChild(card);
            else if (_ELEVADOR_VARS.includes(k)) elevadorContainer.appendChild(card);
        } else {
            card.className = `sensor-card ${finalClass}`;
            const valEl = card.querySelector('.sensor-card-value');
            if (valEl && valEl.textContent !== displayValue) valEl.textContent = displayValue;
            const footerEl = card.querySelector('.sensor-card-footer');
            if (footerEl) {
                const badgeEl = footerEl.querySelector('.badge');
                if (!isNoRisk) {
                    if (badgeEl) { badgeEl.className = `badge ${ri.badge}`; badgeEl.textContent = ri.label; }
                    else footerEl.innerHTML = `<span class="badge ${ri.badge}">${ri.label}</span>`;
                } else if (badgeEl) {
                    badgeEl.remove();
                }
            }
        }
    }
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
                    label: (ctx) => {
                        const dataset = ctx.chart.data.datasets[ctx.datasetIndex];
                        const variable = dataset.variables ? dataset.variables[ctx.dataIndex] : null;
                        const formatted = variable
                            ? formatNumeric(ctx.raw, variable)
                            : (typeof ctx.raw === 'number' ? ctx.raw.toFixed(2) : ctx.raw);
                        return `${ctx.label}: ${formatted}`;
                    },
                },
            },
        },
        scales: {
            x: { ticks: { font: { family: "'DM Sans', system-ui", size: 10 } } },
            y: { beginAtZero: true, ticks: { font: { family: "'DM Sans', system-ui", size: 10 } } },
        },
    };

    const inkColor = getCSSVar('--color-ink') || '#0a0a0a';

    chart1 = new Chart(canvas1.getContext('2d'), {
        type: 'bar',
        data: {
            labels: CHART_PUMP_VARS.map(v => `${getVariableName(v)} (${getUnit(v)})`),
            datasets: [{
                variables: CHART_PUMP_VARS,
                backgroundColor: inkColor,
                borderColor: inkColor,
                borderWidth: 1,
                data: new Array(CHART_PUMP_VARS.length).fill(0),
            }],
        },
        options: chartDefaults,
    });

    chart2 = new Chart(canvas2.getContext('2d'), {
        type: 'bar',
        data: {
            labels: CHART_ELEV_VARS.map(v => `${getVariableName(v)} (${getUnit(v)})`),
            datasets: [{
                variables: CHART_ELEV_VARS,
                backgroundColor: inkColor,
                borderColor: inkColor,
                borderWidth: 1,
                data: new Array(CHART_ELEV_VARS.length).fill(0),
            }],
        },
        options: chartDefaults,
    });
}

function updateCharts(history) {
    if (typeof Chart === 'undefined' || !chart1 || !history?.length) return;

    const getLatestReading = (v) => history.filter(item => item.variable === v).pop();
    const getLatest = (v) => { const r = getLatestReading(v); return r ? r.value : 0; };
    const getSensorColor = (v) => {
        const r = getLatestReading(v);
        if (!r) return getCSSVar('--color-ink') || '#0a0a0a';
        if (r.risk === _RISK.critico) return getCSSVar('--state-critical') || '#dc2626';
        if (r.risk === _RISK.alto) return getCSSVar('--state-high') || '#c2410c';
        if (r.risk === _RISK.medio) return getCSSVar('--state-warn') || '#b45309';
        return getCSSVar('--state-ok') || '#16a34a';
    };

    const applyToChart = (chartInst, vars) => {
        chartInst.data.datasets[0].data = vars.map(getLatest);
        chartInst.data.datasets[0].backgroundColor = vars.map(getSensorColor);
        chartInst.data.datasets[0].borderColor = chartInst.data.datasets[0].backgroundColor;
        chartInst.update();
    };

    if (chart1) applyToChart(chart1, CHART_PUMP_VARS);
    if (chart2) applyToChart(chart2, CHART_ELEV_VARS);
}

// --- Estados de pantalla ---

const STATE_IDS = ['stateLoading', 'stateOffline', 'stateNoEquipment', 'stateNoBuildings'];

function showState(stateId) {
    STATE_IDS.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = id === stateId ? '' : 'none';
    });
    const card = document.getElementById('stateCard');
    if (card) card.style.display = 'block';
    const active = document.getElementById('activeMonitoring');
    if (active) active.style.display = 'none';
}

function hideAllStates() {
    STATE_IDS.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
    const card = document.getElementById('stateCard');
    if (card) card.style.display = 'none';
    const active = document.getElementById('activeMonitoring');
    if (active) active.style.display = 'block';
}

function renderConnectionStatus(isConnected) {
    if (monitorConnectionTimeout) { clearTimeout(monitorConnectionTimeout); monitorConnectionTimeout = null; }
    if (isConnected) hideAllStates();
    else showState('stateOffline');
}

function updateStatusBadge(badgeId, emptyId, statusVal) {
    const badgeEl = document.getElementById(badgeId);
    const emptyEl = document.getElementById(emptyId);
    if (!badgeEl || !emptyEl) return;
    if (statusVal) {
        badgeEl.style.display = 'inline-block';
        badgeEl.textContent = statusVal.charAt(0).toUpperCase() + statusVal.slice(1);
        emptyEl.style.display = 'none';
        badgeEl.className = CSS_CLASSES.statusBadge[statusVal] || 'badge badge-low';
    } else {
        badgeEl.style.display = 'none';
        emptyEl.style.display = 'inline';
    }
}

function updateEquipmentVisibility(equipTypes) {
    const et = equipTypes || [];
    const hasPump = et.includes('bomba');
    const hasElev = et.includes('elevador');

    if (!hasPump && !hasElev && EDIFICIO_ID) { showState('stateNoEquipment'); return false; }

    const toggle = (ids, show) =>
        ids.forEach(id => { const el = document.getElementById(id); if (el) el.style.display = show ? '' : 'none'; });

    toggle(['bombaSection', 'chartPumpPanel', 'statsBombaPanel'], hasPump);
    toggle(['elevadorSection', 'chartElevatorPanel', 'statsElevadorPanel'], hasElev);

    const pumpNI = document.getElementById('pumpNotInstalled');
    const pumpBadge = document.getElementById('pumpStatusBadge');
    const pumpEmpty = document.getElementById('pumpStatusEmpty');
    if (pumpNI && pumpBadge && pumpEmpty) {
        if (!hasPump) { pumpBadge.style.display = 'none'; pumpEmpty.style.display = 'none'; pumpNI.style.display = 'inline'; }
        else pumpNI.style.display = 'none';
    }

    const elevNI = document.getElementById('elevatorNotInstalled');
    const elevBadge = document.getElementById('elevatorStatusBadge');
    const elevEmpty = document.getElementById('elevatorStatusEmpty');
    if (elevNI && elevBadge && elevEmpty) {
        if (!hasElev) { elevBadge.style.display = 'none'; elevEmpty.style.display = 'none'; elevNI.style.display = 'inline'; }
        else elevNI.style.display = 'none';
    }
    return true;
}

// --- Helpers para CustomSelect en controles admin ---
const _csSelect = (el) => el?._customSelect ?? null;
const _csSetValue = (el, val) => { const cs = _csSelect(el); if (cs) cs.value = String(val); else if (el) el.value = val; };
const _csSetDisabled = (el, disabled) => { const cs = _csSelect(el); if (cs?.trigger) cs.trigger.disabled = disabled; if (el) el.disabled = disabled; };
const _csSetDisplay = (el, display) => { const cs = _csSelect(el); if (el) el.style.display = display; if (cs?.wrapper) cs.wrapper.style.display = display; };
const _csSyncOptions = (el) => { const cs = _csSelect(el); if (cs) cs.updateOptions(Array.from(el.options).map(o => ({ value: o.value, text: o.text }))); };

function updateAdminControlsByEquipment(equipTypes) {
    if (!IS_ADMIN) return;
    const et = equipTypes || [];
    const hasPump = et.includes('bomba');
    const hasElev = et.includes('elevador');

    _csSetDisabled(document.getElementById('simFaultPump'), !hasPump);
    _csSetDisabled(document.getElementById('simFaultElevator'), !hasElev);

    const eqSel = document.getElementById('manualEquipmentSelect');
    const eqStatic = document.getElementById('manualEquipmentStatic');
    if (!eqSel || !eqStatic) return;

    const eqGroup = eqSel.closest('.form-group');

    if (hasPump && hasElev) {
        const cs = _csSelect(eqSel);
        if (cs?.wrapper) cs.wrapper.style.display = '';
        eqStatic.classList.add('d-none');
        if (eqGroup) eqGroup.style.display = '';
    } else if (hasPump) {
        if (eqGroup) eqGroup.style.display = 'none';
        _csSetValue(eqSel, 'pump');
        populateManualSensorSelect();
    } else if (hasElev) {
        if (eqGroup) eqGroup.style.display = 'none';
        _csSetValue(eqSel, 'elevator');
        populateManualSensorSelect();
    } else {
        if (eqGroup) eqGroup.style.display = 'none';
    }
}

function setNotificationBadge(count) {
    const pageBadge = document.getElementById('notificationBadgeCount');
    if (!pageBadge) return;
    if (count > 0) { pageBadge.textContent = count; pageBadge.style.display = 'inline-flex'; pageBadge.hidden = false; }
    else { pageBadge.textContent = ''; pageBadge.style.display = 'none'; pageBadge.hidden = true; }
}


// =============================================================================
// 7. CONEXIÓN SSE Y PROCESAMIENTO DE DATOS
// =============================================================================

function connectSSE() {
    if (sseSource) sseSource.close();
    const isMonitoring = document.getElementById('activeMonitoring') !== null;

    if (!SSE_URL || typeof EventSource === 'undefined') {
        if (isMonitoring) fetchInitialData();
        return;
    }

    sseSource = new EventSource(SSE_URL);

    sseSource.onopen = () => { if (isMonitoring) renderConnectionStatus(true); };

    sseSource.onerror = () => {
        if (isMonitoring && !monitorConnectionTimeout) {
            monitorConnectionTimeout = setTimeout(() => {
                showState('stateOffline');
                monitorConnectionTimeout = null;
            }, 15000);
        }
    };

    sseSource.onmessage = (event) => {
        try { applyPayload(JSON.parse(event.data)); } catch (_) { /* ignorar datos malformados */ }
    };

    sseSource.addEventListener('notification', (event) => {
        try { addLiveNotificationEvent(JSON.parse(event.data)); } catch (_) { /* ignorar */ }
    });

    if (isMonitoring) fetchInitialData();
}

// Extraída de applyPayload para responsabilidad única
function _countUnreadAlerts(alertLog) {
    const EXCLUDED = [_RISK.info, _RISK.bajo, _RISK.medio];
    const clearedAtMs = window.ALERTS_CLEARED_AT ? window.ALERTS_CLEARED_AT * 1000 : null;
    return (alertLog || []).filter(a => {
        if (EXCLUDED.includes(a.risk)) return false;
        if (clearedAtMs) {
            const alertMs = a.timestamp ? new Date(a.timestamp.replace(' ', 'T') + 'Z').getTime() : 0;
            if (alertMs <= clearedAtMs) return false;
        }
        return true;
    }).length;
}

function applyPayload(data) {
    if (data.thresholds) currentThresholds = data.thresholds;
    hideAllStates();

    if (data.current) { currentReadings = data.current; updateCards(data.current); }
    if (data.history) updateCharts(data.history);

    updateStatusBadge('pumpStatusBadge', 'pumpStatusEmpty', data.pump_status);
    updateStatusBadge('elevatorStatusBadge', 'elevatorStatusEmpty', data.elevator_status);

    const lastUpd = document.getElementById('lastUpdate');
    if (lastUpd) lastUpd.innerText = new Date().toLocaleTimeString();

    const hasEquipment = updateEquipmentVisibility(data.equipment_types);
    if (IS_ADMIN) updateAdminControlsByEquipment(data.equipment_types);
    if (data.current && hasEquipment) updateSummaryValues(data);
    if (data.stats || data.recommendations) {
        updateStatsAndRecs(data.stats, data.recommendations, data.door_close_attempts);
    }

    if (IS_ADMIN) {
        if (data.sim_paused !== undefined) updatePauseBtn(data.sim_paused);

        if (data.sim_speed !== undefined) {
            document.querySelectorAll('[data-speed]').forEach(btn => {
                const isActive = parseFloat(btn.dataset.speed) === data.sim_speed;
                btn.classList.toggle('btn-primary', isActive);
                btn.classList.toggle('btn-secondary', !isActive);
            });
        }

        const simSpd = document.getElementById('simSpeedDisplay');
        if (simSpd) {
            const isPaused = data.sim_paused !== undefined
                ? data.sim_paused
                : document.getElementById('simPauseBtn')?.querySelector('i.fa-play') !== null;
            const speed = data.sim_speed !== undefined
                ? data.sim_speed
                : parseFloat(document.querySelector('[data-speed].btn-primary')?.dataset.speed || 1.0);
            simSpd.textContent = isPaused ? 'Pausada' : `${speed.toFixed(1)}x`;
            simSpd.className = isPaused ? 'badge badge-med' : 'badge badge-info';
        }
    }

    const totalAlerts = _countUnreadAlerts(data.alert_log);
    unreadNotificationCount = totalAlerts;
    setNotificationBadge(totalAlerts);
}

function updateSummaryValues(data) {
    const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    setVal('summaryPumpStatus', data.pump_on ? 'Encendida' : 'Apagada');
    setVal('summaryElevatorStatus', data.elevator_on ? 'Encendido' : 'Apagado');
}


// =============================================================================
// 8. ESTADÍSTICAS Y RECOMENDACIONES
// =============================================================================

function renderStatsTable(entries, containerId, firstColLabel) {
    const div = document.getElementById(containerId);
    if (!div) return;
    if (!entries.length) { div.innerHTML = ''; return; }
    const rows = entries.map(([k, v]) =>
        `<tr><td>${getVariableName(k)}</td><td>${formatNumeric(v.avg, k)}</td><td>${formatNumeric(v.min, k)}</td><td>${formatNumeric(v.max, k)}</td></tr>`
    ).join('');
    div.innerHTML = `
        <div class="table-wrapper"><div class="table-responsive">
            <table class="report-table stats-table">
                <thead><tr>
                    <th><i class="fa-solid fa-square-poll-vertical"></i> ${firstColLabel}</th>
                    <th>Prom.</th><th>Mín.</th><th>Máx.</th>
                </tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div></div>`;
}

function updateStatsAndRecs(stats, recs, attempts) {
    const entries = stats && Object.keys(stats).length ? Object.entries(stats) : [];
    renderStatsTable(entries.filter(([k]) => _BOMBA_VARS.includes(k)), 'statsBombaPanel', 'Estadísticas de la bomba');
    renderStatsTable(entries.filter(([k]) => _ELEVADOR_VARS.includes(k)), 'statsElevadorPanel', 'Estadísticas del elevador');

    const recsContent = document.getElementById('recommendationsContent');
    if (!recsContent || !recs?.length) return;

    recsContent.innerHTML = '';
    const isOk = recs.length === 1 && recs[0].includes('normales');

    recs.forEach(rec => {
        let cardHtml;
        if (isOk) {
            cardHtml = `<div class="status-banner"><i class="fa-solid fa-circle-check"></i><span>${rec}</span></div>`;
        } else {
            const isCrit = rec.toLowerCase().includes('crític') || rec.toLowerCase().includes('urgente') || rec.toLowerCase().includes('atascado');
            const bgColor = isCrit ? 'var(--state-critical-bg)' : 'var(--state-warn-bg)';
            const borderColor = isCrit ? 'var(--state-critical)' : 'var(--state-warn)';
            const icon = isCrit ? 'fa-solid fa-circle-exclamation' : 'fa-solid fa-triangle-exclamation';
            const doorNote = (rec.includes('puertas') && typeof attempts === 'number' && attempts > 0)
                ? ` (Intentos fallidos: ${attempts})` : '';
            cardHtml = `<div class="status-banner" style="background:${bgColor};color:${borderColor};"><i class="${icon}"></i><span>${rec}${doorNote}</span></div>`;
        }
        const div = document.createElement('div');
        div.innerHTML = cardHtml.trim();
        recsContent.appendChild(div.firstElementChild);
    });
}


// =============================================================================
// 9. UMBRALES Y LÍMITES DE SENSORES
// =============================================================================

// Valida el orden lógico de los niveles de umbral
function _validateThresholdRange(dir, low, med, high) {
    if (isNaN(low) || isNaN(high) || (dir !== 'range' && isNaN(med))) {
        return { valid: false, errorText: 'Introduzca valores numéricos válidos.', errorInputs: [] };
    }
    if (dir === 'range') {
        if (!(low < high)) return { valid: false, errorText: 'El mínimo aceptable debe ser menor al máximo aceptable.', errorInputs: ['low', 'high'] };
    } else if (dir === 'higher') {
        const errs = [];
        if (low >= med) errs.push('low', 'med');
        if (med >= high) errs.push('med', 'high');
        if (errs.length) return { valid: false, errorText: 'Los valores deben estar ordenados: Medio < Alto < Crítico.', errorInputs: [...new Set(errs)] };
    } else if (dir === 'lower') {
        const errs = [];
        if (low <= med) errs.push('low', 'med');
        if (med <= high) errs.push('med', 'high');
        if (errs.length) return { valid: false, errorText: 'Los valores deben estar ordenados: Medio > Alto > Crítico.', errorInputs: [...new Set(errs)] };
    }
    return { valid: true, errorText: '', errorInputs: [] };
}

// Valida que los umbrales respeten los límites físicos del sensor
function _validateThresholdBounds(dir, low, high, bounds, unit) {
    const [minBound, maxBound] = bounds;
    const unitStr = unit ? ` ${unit}` : '';
    const outOfRange = (dir === 'lower')
        ? (low > maxBound && high < minBound)
        : (low < minBound && high > maxBound);

    if (outOfRange) return { valid: false, errorText: `Los umbrales deben estar dentro de los límites del sensor (${minBound} - ${maxBound}${unitStr}).`, errorInputs: ['low', 'high'] };

    if (dir === 'lower') {
        if (low > maxBound) return { valid: false, errorText: `El umbral medio no puede ser mayor al límite físico (${maxBound}${unitStr}).`, errorInputs: ['low'] };
        if (high < minBound) return { valid: false, errorText: `El umbral crítico no puede ser menor al límite físico (${minBound}${unitStr}).`, errorInputs: ['high'] };
    } else if (dir === 'higher') {
        if (low < minBound) return { valid: false, errorText: `El umbral medio no puede ser menor al límite físico (${minBound}${unitStr}).`, errorInputs: ['low'] };
        if (high > maxBound) return { valid: false, errorText: `El umbral crítico no puede ser mayor al límite físico (${maxBound}${unitStr}).`, errorInputs: ['high'] };
    } else { // range
        if (low < minBound) return { valid: false, errorText: `El mínimo aceptable no puede ser menor al límite físico (${minBound}${unitStr}).`, errorInputs: ['low'] };
        if (high > maxBound) return { valid: false, errorText: `El máximo aceptable no puede ser mayor al límite físico (${maxBound}${unitStr}).`, errorInputs: ['high'] };
    }
    return { valid: true, errorText: '', errorInputs: [] };
}

function renderThresholdsPanel(th) {
    const bombaVars = _BOMBA_VARS.filter(k => th[k] && !_NO_RISK_VARS.includes(k));
    const elevadorVars = _ELEVADOR_VARS.filter(k => th[k] && !_NO_RISK_VARS.includes(k));
    const otherVars = Object.keys(th).filter(k =>
        !_NO_RISK_VARS.includes(k) && !_BOMBA_VARS.includes(k) && !_ELEVADOR_VARS.includes(k)
    );

    function buildCard(k, cfg) {
        const div = document.createElement('div');
        div.className = 'thresh-card';
        const name = getVariableName(k);
        const unit = getUnit(k);
        const bounds = _SENSOR_RANGES[k];
        const boundsText = bounds ? `Límite: ${bounds[0]} – ${bounds[1]}${unit ? ' ' + unit : ''}` : '';
        const DIR_BADGE = {
            higher: '<span class="thresh-dir-badge" style="color:var(--state-critical);" title="Mayor es peor">\u2191 Mayor es peor</span>',
            lower: '<span class="thresh-dir-badge" style="color:var(--state-high);" title="Menor es peor">\u2193 Menor es peor</span>',
        };
        const dirBadge = DIR_BADGE[cfg.direction] || '<span class="thresh-dir-badge" style="color:var(--state-inactive);" title="Rango válido">\u27FA Rango válido</span>';
        const headerHtml = `<div class="thresh-card-header">
            <span class="thresh-label">${name}${unit && k !== 'trip_count' ? ` (${unit})` : ''}</span>
            ${dirBadge}
        </div>`;

        if (cfg.direction === 'range') {
            div.innerHTML = headerHtml + `
                <div class="thresh-grid-2">
                    <div class="form-group"><label class="form-label">Mínimo aceptable</label><input type="number" step="any" data-var="${k}" data-level="low" value="${cfg.low}" class="form-input"></div>
                    <div class="form-group"><label class="form-label">Máximo aceptable</label><input type="number" step="any" data-var="${k}" data-level="high" value="${cfg.high}" class="form-input"></div>
                </div>
                <div class="thresh-error-msg"></div>
                <input type="hidden" data-var="${k}" data-level="direction" value="range">
                <div class="thresh-card-footer"><span>${boundsText}</span></div>`;
        } else {
            div.innerHTML = headerHtml + `
                <div class="thresh-grid-3">
                    <div class="form-group"><label class="form-label">\u2192 Medio</label><input type="number" step="any" data-var="${k}" data-level="low" value="${cfg.low}" class="form-input"></div>
                    <div class="form-group"><label class="form-label">\u2192 Alto</label><input type="number" step="any" data-var="${k}" data-level="medium" value="${cfg.medium}" class="form-input"></div>
                    <div class="form-group"><label class="form-label">\u2192 Crítico</label><input type="number" step="any" data-var="${k}" data-level="high" value="${cfg.high}" class="form-input"></div>
                </div>
                <div class="thresh-error-msg"></div>
                <input type="hidden" data-var="${k}" data-level="direction" value="${cfg.direction}">
                <div class="thresh-card-footer"><span>${boundsText}</span></div>`;
        }
        return div;
    }

    function buildSection(containerId, vars) {
        const panel = document.getElementById(containerId);
        if (!panel) return;
        panel.innerHTML = '';
        vars.forEach(k => { const cfg = th[k]; if (cfg) panel.appendChild(buildCard(k, cfg)); });
    }

    buildSection('thresholdsBombaPanel', bombaVars);
    buildSection('thresholdsElevadorPanel', elevadorVars);
    if (otherVars.length) {
        const panel = document.getElementById('thresholdsBombaPanel');
        if (panel) otherVars.forEach(k => panel.appendChild(buildCard(k, th[k])));
    }

    _originalThresholds = JSON.parse(JSON.stringify(th));
    _dirtySensorKeys.clear();
    updateGlobalDirtyBadge();
    validateThresholdInputs('bomba');
    validateThresholdInputs('elevador');
    updateManualInputType();
}

function updateDirtyState(scope) {
    const bomba = scope === 'bomba';
    const panelId = bomba ? 'thresholdsBombaPanel' : 'thresholdsElevadorPanel';
    const panelVars = bomba ? _BOMBA_VARS : _ELEVADOR_VARS;
    const panel = document.getElementById(panelId);
    if (!panel) return;
    const panelKeys = new Set();
    panel.querySelectorAll('input[type="number"]').forEach(inp => {
        const varKey = inp.dataset.var;
        const lvl = inp.dataset.level;
        if (!varKey || !lvl || lvl === 'direction') return;
        const orig = _originalThresholds[varKey]?.[lvl];
        if (orig !== undefined && parseFloat(inp.value) !== orig) {
            inp.classList.add('is-dirty');
            inp.title = `Valor original: ${orig}${getUnit(varKey) ? ' ' + getUnit(varKey) : ''}`;
            panelKeys.add(varKey);
        } else {
            inp.classList.remove('is-dirty');
            inp.title = '';
        }
    });
    for (const k of panelVars) {
        if (panelKeys.has(k)) _dirtySensorKeys.add(k);
        else _dirtySensorKeys.delete(k);
    }
    updateGlobalDirtyBadge();
}

function updateGlobalDirtyBadge() {
    const badge = document.getElementById('globalDirtyBadge');
    const resetBtn = document.getElementById('resetAllThresholdsBtn');
    const saveAllBtn = document.getElementById('saveAllThresholdsBtn');
    const totalDirty = _dirtySensorKeys.size;
    if (badge) {
        if (!totalDirty) {
            badge.classList.add('d-none');
        } else {
            badge.classList.remove('d-none');
            badge.textContent = `${totalDirty} sensor(es) modificado(s)`;
        }
    }
    if (resetBtn) resetBtn.disabled = !totalDirty;
    if (saveAllBtn) saveAllBtn.disabled = totalDirty === 0;
}

function validateThresholdInputs(scope) {
    const bomba = scope === 'bomba';
    const PANEL_IDS = bomba ? ['thresholdsBombaPanel'] : ['thresholdsElevadorPanel'];
    const btn = document.getElementById(bomba ? 'saveThresholdsBombaBtn' : 'saveThresholdsElevadorBtn');
    let hasError = false, hasChanges = false;
    const processed = {};

    const findInp = (v, level) => {
        for (const pid of PANEL_IDS) {
            const el = document.getElementById(pid)?.querySelector(`input[data-var="${v}"][data-level="${level}"]`);
            if (el) return el;
        }
        return null;
    };

    const findErrorMsgEl = (v) => {
        for (const pid of PANEL_IDS) {
            const el = document.getElementById(pid)?.querySelector(`input[data-var="${v}"]`);
            if (el) return el.closest('.thresh-card')?.querySelector('.thresh-error-msg') ?? null;
        }
        return null;
    };

    const setInputColors = (inpKeys, inputMap, hasError) =>
        inpKeys.forEach(k => {
            if (inputMap[k]) {
                inputMap[k].classList.toggle('input-thresh-error', hasError);
            }
        });

    PANEL_IDS.forEach(panelId => {
        const panel = document.getElementById(panelId);
        if (!panel) return;
        panel.querySelectorAll('input[type="number"]').forEach(inp => {
            const v = inp.dataset.var;
            if (!v || processed[v]) return;
            processed[v] = true;

            const dirInp = findInp(v, 'direction');
            const lowInp = findInp(v, 'low');
            const medInp = findInp(v, 'medium');
            const highInp = findInp(v, 'high');
            const inputMap = { low: lowInp, med: medInp, high: highInp };

            setInputColors(['low', 'med', 'high'], inputMap, false);

            const errorMsgEl = findErrorMsgEl(v);
            if (errorMsgEl) { errorMsgEl.textContent = ''; errorMsgEl.style.display = 'none'; }

            const dir = dirInp?.value;
            const low = parseFloat(lowInp?.value);
            const med = parseFloat(medInp?.value);
            const high = parseFloat(highInp?.value);

            let result = _validateThresholdRange(dir, low, med, high);
            if (result.valid && _SENSOR_RANGES[v]) {
                result = _validateThresholdBounds(dir, low, high, _SENSOR_RANGES[v], getUnit(v));
            }

            if (!result.valid) {
                hasError = true;
                setInputColors(result.errorInputs, inputMap, true);
                if (errorMsgEl && result.errorText) { errorMsgEl.textContent = result.errorText; errorMsgEl.style.display = 'block'; }
            }
        });
    });

    PANEL_IDS.forEach(panelId => {
        const panel = document.getElementById(panelId);
        if (!panel) return;
        panel.querySelectorAll('input[type="number"]').forEach(inp => {
            const varKey = inp.dataset.var;
            const lvl = inp.dataset.level;
            if (!varKey || !lvl || lvl === 'direction') return;
            if (_originalThresholds[varKey]?.[lvl] !== undefined) {
                if (parseFloat(inp.value) !== _originalThresholds[varKey][lvl]) hasChanges = true;
            }
        });
    });

    if (btn) btn.disabled = hasError || !hasChanges;
    updateDirtyState(scope);
}

async function saveThresholds(scope) {
    const bomba = scope === 'bomba';
    const PANEL_IDS = bomba ? ['thresholdsBombaPanel'] : ['thresholdsElevadorPanel'];
    const newTh = { edificio_id: EDIFICIO_ID };
    PANEL_IDS.forEach(panelId => {
        const panel = document.getElementById(panelId);
        if (!panel) return;
        panel.querySelectorAll('input[type="number"]').forEach(inp => {
            const v = inp.dataset.var, l = inp.dataset.level;
            if (!v || !l) return;
            if (!newTh[v]) newTh[v] = { direction: panel.querySelector(`input[data-var="${v}"][data-level="direction"]`)?.value || 'higher' };
            newTh[v][l] = parseFloat(inp.value);
        });
    });
    try {
        const resp = await csrfFetch(API.thresholdsUpdate, { method: 'POST', body: JSON.stringify(newTh) });
        const res = await resp.json();
        if (res.status === 'ok') {
            window.showToast(bomba ? 'Umbrales de bomba guardados correctamente.' : 'Umbrales de elevador guardados correctamente.', 'success');
            currentThresholds = res.thresholds;
            renderThresholdsPanel(res.thresholds);
            updateManualInputType();
        } else {
            window.showToast(`Error al guardar: ${res.message || 'Inténtelo de nuevo.'}`, 'error');
        }
    } catch (_) {
        window.showToast('Error de conexión. Inténtelo de nuevo.', 'error');
    }
}

function resetPanelThresholds(scope) {
    const bomba = scope === 'bomba';
    const PANEL_IDS = bomba ? ['thresholdsBombaPanel'] : ['thresholdsElevadorPanel'];
    PANEL_IDS.forEach(panelId => {
        const panel = document.getElementById(panelId);
        if (!panel) return;
        panel.querySelectorAll('input[type="number"]').forEach(inp => {
            const varKey = inp.dataset.var;
            const lvl = inp.dataset.level;
            if (!varKey || !lvl || lvl === 'direction') return;
            const orig = _originalThresholds[varKey]?.[lvl];
            if (orig !== undefined) inp.value = orig;
        });
    });
    validateThresholdInputs(scope);
}

async function resetAllThresholds() {
    if (!await window.showConfirm('¿Restablecer todos los umbrales a sus valores originales (último guardado)?')) return;
    resetPanelThresholds('bomba');
    resetPanelThresholds('elevador');
    window.showToast('Umbrales restablecidos a los valores guardados.', 'success');
}

let _originalLimits = {};

function renderLimitsPanel(ranges) {
    const bombaVars = _BOMBA_VARS.filter(k => ranges[k] && !_NO_RISK_VARS.includes(k) && !_LIMITS_EXCLUDE_VARS.includes(k));
    const elevadorVars = _ELEVADOR_VARS.filter(k => ranges[k] && !_NO_RISK_VARS.includes(k) && !_LIMITS_EXCLUDE_VARS.includes(k));

    function buildLimitCard(k, r) {
        const div = document.createElement('div');
        div.className = 'thresh-card';
        const name = getVariableName(k);
        const unit = getUnit(k);
        const maxVal = r[1];
        const thresh = currentThresholds[k];
        let refText = '';
        if (thresh?.high !== undefined) {
            const label = thresh.direction === 'range' ? 'Máximo aceptable' : 'Crítico';
            refText = `${label}: ${thresh.high}${unit ? ' ' + unit : ''}`;
        }
        const headerHtml = `<div class="thresh-card-header">
            <span class="thresh-label">${name}${unit ? ` (${unit})` : ''}</span>
            ${refText ? `<span class="thresh-hint">${refText}</span>` : ''}
        </div>`;
        div.innerHTML = headerHtml + `
            <div class="form-group">
                <input type="number" step="any" data-var="${k}" data-level="max" value="${maxVal}" class="form-input">
                <div class="limit-error-msg"></div>
            </div>`;
        return div;
    }

    function buildLimitSection(containerId, vars) {
        const panel = document.getElementById(containerId);
        if (!panel) return;
        panel.innerHTML = '';
        vars.forEach(k => panel.appendChild(buildLimitCard(k, ranges[k])));
    }

    buildLimitSection('limitsBombaPanel', bombaVars);
    buildLimitSection('limitsElevadorPanel', elevadorVars);
    _originalLimits = JSON.parse(JSON.stringify(ranges));
    _limitsDirtyKeys.clear();
    updateLimitsDirtyBadge();
    validateLimitInputs('bomba');
    validateLimitInputs('elevador');
}

function validateLimitInputs(scope) {
    const bomba = scope === 'bomba';
    const PANEL_IDS = bomba ? ['limitsBombaPanel'] : ['limitsElevadorPanel'];
    const btn = document.getElementById(bomba ? 'saveLimitsBombaBtn' : 'saveLimitsElevadorBtn');
    let hasError = false, hasChanges = false;

    PANEL_IDS.forEach(panelId => {
        const panel = document.getElementById(panelId);
        if (!panel) return;
        panel.querySelectorAll('input[type="number"]').forEach(inp => {
            const v = inp.dataset.var;
            const val = parseFloat(inp.value);
            inp.classList.remove('input-thresh-error');
            const errorMsgEl = inp.closest('.form-group')?.querySelector('.limit-error-msg');
            if (errorMsgEl) { errorMsgEl.textContent = ''; errorMsgEl.style.display = 'none'; }

            const showError = (text) => {
                hasError = true;
                inp.classList.add('input-thresh-error');
                if (errorMsgEl) { errorMsgEl.textContent = text; errorMsgEl.style.display = 'block'; }
            };

            if (isNaN(val)) return showError('Introduzca un número válido.');
            const defaultMin = _originalLimits[v]?.[0] ?? 0;
            if (val <= defaultMin) return showError(`Debe ser mayor que el mínimo (${defaultMin}).`);
            const thresh = currentThresholds[v];
            if (thresh?.high !== undefined && val < thresh.high) {
                const label = thresh.direction === 'range' ? 'máximo aceptable' : 'crítico';
                const unitStr = getUnit(v) ? ` ${getUnit(v)}` : '';
                return showError(`No puede ser menor al umbral ${label} (${thresh.high}${unitStr}).`);
            }
            if (_originalLimits[v] && val !== _originalLimits[v][1]) hasChanges = true;
        });
    });

    if (btn) btn.disabled = hasError || !hasChanges;
    updateLimitsDirtyState(scope);
}

async function saveLimits(scope) {
    const bomba = scope === 'bomba';
    const PANEL_IDS = bomba ? ['limitsBombaPanel'] : ['limitsElevadorPanel'];
    const newLimits = { edificio_id: EDIFICIO_ID };
    PANEL_IDS.forEach(panelId => {
        const panel = document.getElementById(panelId);
        if (!panel) return;
        panel.querySelectorAll('input[type="number"]').forEach(inp => {
            newLimits[inp.dataset.var] = parseFloat(inp.value);
        });
    });
    try {
        const resp = await csrfFetch(API.limitsUpdate, { method: 'POST', body: JSON.stringify(newLimits) });
        const res = await resp.json();
        if (res.status === 'ok') {
            window.showToast(bomba ? 'Límites de bomba guardados correctamente.' : 'Límites de elevador guardados correctamente.', 'success');
            _CONFIG.sensor_ranges = res.sensor_ranges;
            _SENSOR_RANGES = res.sensor_ranges;
            currentThresholds = res.thresholds || currentThresholds;
            renderLimitsPanel(res.sensor_ranges);
            updateManualInputType();
        } else {
            window.showToast(`Error al guardar: ${res.message || 'Inténtelo de nuevo.'}`, 'error');
        }
    } catch (_) {
        window.showToast('Error de conexión. Inténtelo de nuevo.', 'error');
    }
}

function updateLimitsDirtyState(scope) {
    const bomba = scope === 'bomba';
    const PANEL_IDS = bomba ? ['limitsBombaPanel'] : ['limitsElevadorPanel'];
    const panelVars = bomba ? _BOMBA_VARS : _ELEVADOR_VARS;
    const panelKeys = new Set();
    PANEL_IDS.forEach(panelId => {
        const panel = document.getElementById(panelId);
        if (!panel) return;
        panel.querySelectorAll('input[type="number"]').forEach(inp => {
            const varKey = inp.dataset.var;
            if (!varKey) return;
            const orig = _originalLimits[varKey]?.[1];
            const val = parseFloat(inp.value);
            if (orig !== undefined && val !== orig) {
                inp.classList.add('is-dirty');
                inp.title = `Valor original: ${orig}${getUnit(varKey) ? ' ' + getUnit(varKey) : ''}`;
                panelKeys.add(varKey);
            } else {
                inp.classList.remove('is-dirty');
                inp.title = '';
            }
        });
    });
    for (const k of panelVars) {
        if (!_LIMITS_EXCLUDE_VARS.includes(k)) {
            if (panelKeys.has(k)) _limitsDirtyKeys.add(k);
            else _limitsDirtyKeys.delete(k);
        }
    }
    updateLimitsDirtyBadge();
}

function updateLimitsDirtyBadge() {
    const badge = document.getElementById('globalLimitsDirtyBadge');
    const resetBtn = document.getElementById('resetAllLimitsBtn');
    const totalDirty = _limitsDirtyKeys.size;
    if (badge) {
        if (!totalDirty) {
            badge.classList.add('d-none');
        } else {
            badge.classList.remove('d-none');
            badge.textContent = `${totalDirty} sensor(es) modificado(s)`;
        }
    }
    if (resetBtn) resetBtn.disabled = !totalDirty;
}

function resetPanelLimits(scope) {
    const bomba = scope === 'bomba';
    const PANEL_IDS = bomba ? ['limitsBombaPanel'] : ['limitsElevadorPanel'];
    PANEL_IDS.forEach(panelId => {
        const panel = document.getElementById(panelId);
        if (!panel) return;
        panel.querySelectorAll('input[type="number"]').forEach(inp => {
            const varKey = inp.dataset.var;
            if (!varKey) return;
            const orig = _originalLimits[varKey]?.[1];
            if (orig !== undefined) inp.value = orig;
        });
    });
    validateLimitInputs(scope);
}

async function resetAllLimits() {
    if (!await window.showConfirm('¿Restablecer todos los límites a sus valores originales (último guardado)?')) return;
    resetPanelLimits('bomba');
    resetPanelLimits('elevador');
    window.showToast('Límites restablecidos a los valores guardados.', 'success');
}


// =============================================================================
// 10. CONTROLES MANUALES DE ADMIN
// =============================================================================

function buildThresholdHint(varName) {
    const cfg = currentThresholds[varName];
    if (!cfg) return '';
    const u = getUnit(varName) ? ` ${getUnit(varName)}` : '';
    if (cfg.direction === 'range') return `Rango válido: ${cfg.low}${u} \u2013 ${cfg.high}${u}`;
    const { low, medium: med, high } = cfg;
    if (cfg.direction === 'higher') return `Medio > ${low}${u} \u00b7 Alto > ${med}${u} \u00b7 Cr\u00edtico > ${high}${u}`;
    return `Medio < ${low}${u} \u00b7 Alto < ${med}${u} \u00b7 Cr\u00edtico < ${high}${u}`;
}

function updateManualInputType() {
    const v = document.getElementById('manualSensorSelect')?.value;
    const inp = document.getElementById('manualValueInput');
    const sel = document.getElementById('manualValueSelect');
    if (!v || !inp || !sel) return;

    const csWrapper = _csSelect(sel)?.wrapper;
    const isEnum = v === 'door_status' || v === 'motor_stuck';

    inp.style.display = isEnum ? 'none' : 'block';
    if (csWrapper) csWrapper.style.display = isEnum ? 'block' : 'none';

    if (v === 'door_status') {
        sel.innerHTML = '';
        Object.entries(_VALUE_DISPLAY['door_status'] || {})
            .filter(([val]) => val === 'open' || val === 'closed')
            .forEach(([val, label]) => {
                const opt = document.createElement('option');
                opt.value = val; opt.textContent = label;
                sel.appendChild(opt);
            });
        inp.value = '';
        _csSyncOptions(sel);
    } else if (v === 'motor_stuck') {
        sel.innerHTML = '<option value="true">Sí</option><option value="false">No</option>';
        inp.value = '';
        _csSyncOptions(sel);
    } else {
        const range = _SENSOR_RANGES[v];
        if (range) {
            inp.min = range[0]; inp.max = range[1];
            inp.placeholder = `Ej: ${range[0]} - ${range[1]}${getUnit(v) ? ` ${getUnit(v)}` : ''}`;
            inp.step = v === 'position' ? '1' : 'any';
        } else {
            inp.removeAttribute('min'); inp.removeAttribute('max');
            inp.placeholder = `Ingrese valor numérico${getUnit(v) ? ` (${getUnit(v)})` : ''}`;
            inp.step = 'any';
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
    const container = sel.closest('.form-group');

    if (vars.length <= 1) {
        if (container) container.style.display = 'none';
        if (vars.length === 1) {
            const unit = getUnit(vars[0]);
            const opt = document.createElement('option');
            opt.value = vars[0];
            opt.textContent = getVariableName(vars[0]) + (unit && vars[0] !== 'trip_count' ? ` (${unit})` : '');
            sel.appendChild(opt);
            _csSyncOptions(sel);
            _csSetValue(sel, vars[0]);
        }
        return;
    }
    if (container) container.style.display = '';
    vars.forEach(v => {
        const unit = getUnit(v);
        const opt = document.createElement('option');
        opt.value = v;
        opt.textContent = getVariableName(v) + (unit && v !== 'trip_count' ? ` (${unit})` : '');
        sel.appendChild(opt);
    });
    _csSyncOptions(sel);
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

    const status = validateManualInput();
    if (status.hasError) {
        span.innerHTML = `<span style="color:var(--state-critical);font-weight:bold;font-size:var(--text-s);"><i class="fa-solid fa-circle-exclamation"></i> ${status.errorText}</span>`;
        return;
    }
    if (status.empty) {
        const hint = buildThresholdHint(v);
        span.innerHTML = hint ? `<span class="thresh-hint">${hint}</span>` : '';
        return;
    }

    const isEnum = v === 'door_status' || v === 'motor_stuck';
    const raw = isEnum ? sel.value : inp.value;
    let val = raw;
    if (v === 'motor_stuck') val = (raw === 'true' || raw === '1');
    else if (!isEnum) { const n = parseFloat(raw); if (isNaN(n)) return; val = n; }

    span.innerHTML = _NO_RISK_VARS.includes(v)
        ? ''
        : (() => { const ri = getRiskClass(v, val); return `Riesgo estimado: <span class="badge ${ri.badge}">${ri.label}</span>`; })();
}

function validateManualInput() {
    const v = document.getElementById('manualSensorSelect')?.value;
    const inp = document.getElementById('manualValueInput');
    const sendBtn = document.getElementById('sendManualBtn');
    if (!v) return { hasError: false, empty: true };

    const isEnum = v === 'door_status' || v === 'motor_stuck';
    let hasError = false, errorText = '', empty = false;

    if (!isEnum && inp) {
        const raw = inp.value.trim();
        empty = !raw;
        if (!empty) {
            const val = parseFloat(raw);
            if (isNaN(val)) { hasError = true; errorText = 'Introduzca un número válido.'; }
            else if (_SENSOR_RANGES[v]) {
                const [min, max] = _SENSOR_RANGES[v];
                if (val < min || val > max) {
                    hasError = true;
                    errorText = `El valor debe estar entre ${min} y ${max}${getUnit(v) ? ' ' + getUnit(v) : ''}.`;
                }
            }
        }
    }
    if (inp) {
        inp.classList.toggle('input-thresh-error', hasError);
    }
    if (sendBtn) sendBtn.disabled = empty || hasError;
    return { hasError, errorText, empty };
}

async function sendManualValue() {
    const v = document.getElementById('manualSensorSelect')?.value;
    const inp = document.getElementById('manualValueInput');
    const sel = document.getElementById('manualValueSelect');
    if (!v) return;

    const isEnum = v === 'door_status' || v === 'motor_stuck';
    const raw = isEnum ? sel.value : inp.value;
    if (raw === undefined || raw === '') { window.showToast('Complete todos los campos.', 'error'); return; }

    let val = raw;
    if (v === 'door_status') {
        val = raw.toLowerCase();
        if (!['open', 'closed'].includes(val)) { window.showToast(`Valores aceptados: open, closed.`, 'error'); return; }
    } else if (v === 'motor_stuck') {
        val = raw === 'true' || raw === '1';
    } else {
        const n = parseFloat(raw);
        if (isNaN(n)) { window.showToast('Introduzca un valor numérico válido.', 'error'); return; }
        if (_SENSOR_RANGES[v] && (n < _SENSOR_RANGES[v][0] || n > _SENSOR_RANGES[v][1])) return;
        val = n;
    }
    try {
        const resp = await csrfFetch(API.manualUpdate, { method: 'POST', body: JSON.stringify({ variable: v, value: val, edificio_id: EDIFICIO_ID }) });
        const res = await resp.json();
        if (res.status === 'ok') window.showToast('Valor enviado correctamente.', 'success');
        else window.showToast(res.message || 'No se pudo aplicar el valor.', 'error');
    } catch (_) { window.showToast('Error de conexión. Inténtelo de nuevo.', 'error'); }
}

// --- Controles de simulación ---

async function fetchSimStatus() {
    if (!EDIFICIO_ID) return null;
    try { const resp = await fetch(API.simStatus(EDIFICIO_ID)); return await resp.json(); }
    catch (_) { return null; }
}

async function togglePause() {
    if (!EDIFICIO_ID) return;
    try {
        const resp = await csrfFetch(API.simPause(EDIFICIO_ID), { method: 'POST', body: '{}' });
        const data = await resp.json();
        if (data.status === 'ok') updatePauseBtn(data.paused);
    } catch (_) { setSimMessage('Error al pausar o reanudar la simulación.', 'error'); }
}

function updatePauseBtn(paused) {
    const btn = document.getElementById('simPauseBtn');
    if (!btn) return;
    btn.innerHTML = paused ? '<i class="fas fa-play"></i> <span>Reanudar</span>' : '<i class="fas fa-pause"></i> <span>Pausar</span>';
    btn.className = paused ? 'btn btn-primary' : 'btn btn-secondary';
}

async function resetSim() {
    const confirmed = await window.showConfirm('¿Reiniciar el simulador al estado normal?');
    if (!confirmed || !EDIFICIO_ID) return;
    try {
        const resp = await csrfFetch(API.simReset(EDIFICIO_ID), { method: 'POST', body: '{}' });
        const data = await resp.json();
        if (data.status === 'ok') {
            setSimMessage(data.message, 'success');
            updatePauseBtn(false);
            _csSetValue(document.getElementById('simFaultPump'), '');
            _csSetValue(document.getElementById('simFaultElevator'), '');
        } else { setSimMessage(data.message, 'error'); }
    } catch (_) { setSimMessage('Error al reiniciar la simulación.', 'error'); }
}

async function injectFault(device) {
    if (!EDIFICIO_ID) return;
    const faultType = document.getElementById(device === 'pump' ? 'simFaultPump' : 'simFaultElevator')?.value;
    const url = faultType ? API.simInjectFault(EDIFICIO_ID) : API.simClearFault(EDIFICIO_ID);
    const body = faultType
        ? JSON.stringify({ device, fault_type: faultType })
        : JSON.stringify({ device });
    try {
        const resp = await csrfFetch(url, { method: 'POST', body });
        const data = await resp.json();
        setSimMessage(data.message, data.status === 'ok' ? 'success' : 'error');
    } catch (_) { setSimMessage('Error al gestionar la falla.', 'error'); }
}

async function setSpeed(speed) {
    if (!EDIFICIO_ID) return;
    document.querySelectorAll('[data-speed]').forEach(btn => {
        const isActive = parseFloat(btn.dataset.speed) === speed;
        btn.classList.toggle('btn-primary', isActive);
        btn.classList.toggle('btn-secondary', !isActive);
    });
    try { await csrfFetch(API.simSetSpeed(EDIFICIO_ID), { method: 'POST', body: JSON.stringify({ speed }) }); }
    catch (_) { /* silent */ }
}

const setSimMessage = (msg, type) =>
    window.showToast(msg, type === 'error' ? 'error' : type === 'success' ? 'success' : 'info');


// =============================================================================
// 11. NOTIFICACIONES EN VIVO
// =============================================================================

function renderNotificationList(alerts) {
    const container = document.getElementById('live-notifications-list');
    if (!container) return;
    document.getElementById('live-no-notif')?.remove();

    const filtered = (alerts || []).filter(a => a.risk !== _RISK.info);
    if (!filtered.length) {
        unreadNotificationCount = 0;
        setNotificationBadge(0);
        container.innerHTML = `<div class="no-notif" id="live-no-notif"><i class="fa-solid fa-bell-slash"></i><p>No hay alertas pendientes.</p></div>`;
        return;
    }
    unreadNotificationCount = filtered.length;
    setNotificationBadge(unreadNotificationCount);
    container.innerHTML = filtered.map(alert => `
        <div class="notif-item">
            <div class="notif-icon"><i class="fa-solid fa-bell"></i></div>
            <div class="notif-body">
                <p>${safeText(alert.message)}</p>
                <div class="notif-meta">
                    <span><i class="fa-solid fa-clock"></i> ${new Date(alert.timestamp).toLocaleString()}</span>
                    <span><strong>Variable:</strong> ${safeText(getVariableName(alert.variable))}</span>
                    <span><strong>Riesgo:</strong> ${safeText(alert.risk)}</span>
                </div>
            </div>
        </div>`).join('');
}

// Parseo de timestamp con early return — evita try/catch anidado innecesario
function _parseTimestamp(ts) {
    if (!ts) return '';
    const d = new Date(ts.replace(' ', 'T') + 'Z');
    return isNaN(d.getTime()) ? ts : d.toLocaleString();
}

function addLiveNotificationEvent(data) {
    const container = document.getElementById('live-notifications-list');
    if (!container) return;
    document.getElementById('live-no-notif')?.remove();

    let ul = container.querySelector('.notif-list');
    if (!ul) { ul = document.createElement('ul'); ul.className = 'notif-list'; container.appendChild(ul); }

    const riskLower = String(data.risk || 'info').toLowerCase();
    const li = document.createElement('li');
    li.className = 'notif-item';

    const BADGE_MAP = { 'CRÍTICO': 'sensor-critical', 'ALTO': 'sensor-high', 'MEDIO': 'sensor-warning', 'BAJO': 'sensor-active' };
    const badgeClass = BADGE_MAP[data.risk] || 'sensor-info';
    const valueStr = String(data.value);
    const unit = getUnit(data.variable);
    const SKIP_VALUES = new Set(['true', 'True', 'false', 'False', 'undefined', 'null']);
    const showValueBox = !SKIP_VALUES.has(valueStr) && valueStr.trim() !== '';
    const valueHtml = showValueBox
        ? `<span class="code-badge">${formatNumeric(data.value, data.variable)}${unit ? ' ' + unit : ''}</span>`
        : '';

    li.innerHTML = `
        <div class="notif-body">
            <div class="flex-wrap mb-1">
                <span class="sensor-badge ${badgeClass}">${safeText(data.risk)}</span>
                ${valueHtml}
                <span class="value-bold">${safeText(getVariableName(data.variable))}</span>
            </div>
            <p class="notif-meta-text">${safeText(data.message)}</p>
            <div class="notif-meta" style="margin-top:8px;">
                <span><i class="fa-solid fa-clock"></i> ${_parseTimestamp(data.timestamp)}</span>
            </div>
        </div>`;

    ul.prepend(li);
    unreadNotificationCount++;
    setNotificationBadge(unreadNotificationCount);
}

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
            <div class="custom-modal-header">
                <i class="fa-solid fa-clock custom-modal-icon custom-modal-icon-warn"></i>
                <span class="custom-modal-title">Desactivar alertas</span>
            </div>
            <div class="custom-modal-body">¿Por cuánto tiempo deseas desactivar las alertas?</div>
            <div id="durationGrid" class="duration-grid">
                ${durations.map(d => `<button class="btn btn-secondary" data-minutes="${d.value === null ? 'null' : d.value}">${d.label}</button>`).join('')}
            </div>
            <div class="custom-modal-actions">
                <button id="durationCancelBtn" class="btn btn-secondary">Cancelar</button>
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
    const tick = () => {
        const remaining = disabledUntilMs - Date.now();
        if (remaining <= 0) { clearInterval(alertCountdownInterval); alertCountdownInterval = null; reEnableAlerts(); return; }
        btn.innerHTML = `<i class="fa-solid fa-bell-slash"></i> Activar alertas <span style="font-size:var(--text-s);opacity:0.7;font-weight:normal;">(${formatCountdown(remaining)})</span>`;
    };
    tick();
    alertCountdownInterval = setInterval(tick, 1000);
}

async function reEnableAlerts() {
    const btn = document.getElementById('toggleAlertsBtn');
    if (!btn) return;
    btn.dataset.enabled = 'true'; btn.dataset.disabledUntilMs = '';
    btn.className = 'btn btn-primary';
    btn.innerHTML = '<i class="fa-solid fa-bell"></i> Desactivar alertas';
    await csrfFetch(API.toggleAlerts, { method: 'POST', body: JSON.stringify({ enabled: true }) });
    await window.showAlert('Alertas reactivadas.', 'success');
    window.location.reload();
}


// =============================================================================
// 12. MANEJADORES DE EVENTOS
// =============================================================================

function initLiveNotifications() {
    const toggleBtn = document.getElementById('toggleAlertsBtn');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', async () => {
            const isEnabled = toggleBtn.dataset.enabled === 'true';
            if (!isEnabled) {
                if (alertCountdownInterval) { clearInterval(alertCountdownInterval); alertCountdownInterval = null; }
                toggleBtn.dataset.enabled = 'true'; toggleBtn.dataset.disabledUntilMs = '';
                toggleBtn.className = 'btn btn-primary';
                toggleBtn.innerHTML = '<i class="fa-solid fa-bell"></i> Desactivar alertas';
                await csrfFetch(API.toggleAlerts, { method: 'POST', body: JSON.stringify({ enabled: true }) });
                await window.showAlert('Alertas activadas con éxito.', 'success');
                window.location.reload();
            } else {
                const minutes = await showDurationPicker();
                if (minutes === undefined) return;
                toggleBtn.dataset.enabled = 'false'; toggleBtn.className = 'btn btn-secondary';
                if (minutes !== null) {
                    const untilMs = Date.now() + minutes * 60 * 1000;
                    toggleBtn.dataset.disabledUntilMs = untilMs;
                    startAlertCountdown(untilMs);
                } else {
                    toggleBtn.dataset.disabledUntilMs = '';
                    toggleBtn.innerHTML = '<i class="fa-solid fa-bell-slash"></i> Activar alertas';
                }
                await csrfFetch(API.toggleAlerts, { method: 'POST', body: JSON.stringify({ enabled: false, duration_minutes: minutes }) });
                const label = minutes === null ? 'indefinidamente' : minutes < 60 ? `por ${minutes} min` : minutes === 60 ? 'por 1 hora' : `por ${minutes / 60} horas`;
                await window.showAlert(`Alertas pausadas ${label}.`, 'success');
                window.location.reload();
            }
        });
    }

    const emailToggleBtn = document.getElementById('toggleEmailAlertsBtn');
    if (emailToggleBtn) {
        emailToggleBtn.addEventListener('click', async () => {
            const newEnabled = emailToggleBtn.dataset.enabled !== 'true';
            emailToggleBtn.dataset.enabled = newEnabled ? 'true' : 'false';
            emailToggleBtn.className = newEnabled ? 'btn btn-primary' : 'btn btn-secondary';
            emailToggleBtn.innerHTML = newEnabled
                ? '<i class="fa-solid fa-envelope"></i> Desactivar correos'
                : '<i class="fa-solid fa-envelope"></i> Activar correos';
            await csrfFetch(API.toggleEmailAlerts, { method: 'POST', body: JSON.stringify({ enabled: newEnabled }) });
            await window.showAlert(newEnabled ? 'Correos activados con éxito.' : 'Correos desactivados con éxito.', 'success');
        });
    }

    const clearBtn = document.getElementById('clearDbNotificationsBtn');
    if (clearBtn) {
        clearBtn.addEventListener('click', async () => {
            if (!await window.showConfirm('¿Estás seguro de que deseas limpiar todas las alertas?')) return;
            try {
                const resp = await csrfFetch(API.clearNotifications, { method: 'POST' });
                if (resp.ok) { await window.showAlert('Alertas limpiadas con éxito.', 'success'); window.location.href = window.location.pathname; }
                else throw new Error('Error al limpiar');
            } catch (_) { await window.showAlert('No se pudieron limpiar las alertas.', 'error'); }
        });
    }
}

async function fetchInitialData() {
    // --- Página de límites de sensores ---
    if (window.IS_LIMITS_PAGE) {
        try {
            const resp = await fetch(API.sensorLimits(EDIFICIO_ID));
            if (!resp.ok) throw new Error(resp.statusText);
            const data = await resp.json();
            hideAllStates();
            currentThresholds = data.thresholds || {};
            renderLimitsPanel(data.limits || {});
        } catch (_) { showState('stateOffline'); }
        return;
    }

    // --- Página de umbrales ---
    if (window.IS_THRESHOLDS_PAGE) {
        try {
            const resp = await fetch(API.thresholds(EDIFICIO_ID));
            if (!resp.ok) throw new Error(resp.statusText);
            currentThresholds = await resp.json();
            hideAllStates();
            renderThresholdsPanel(currentThresholds);

        } catch (_) { showState('stateOffline'); }
        return;
    }

    // --- Dashboard principal ---
    try {
        const resp = await fetch(API.status(EDIFICIO_ID));
        if (!resp.ok) throw new Error(resp.statusText);
        const data = await resp.json();
        applyPayload(data);
        if (IS_ADMIN && data.thresholds) renderThresholdsPanel(data.thresholds);
    } catch (_) {
        if (IS_ADMIN) {
            ['statsBombaPanel', 'statsElevadorPanel'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.innerHTML = '<span class="text-secondary text-sm">Sin datos de telemetría para este edificio.</span>';
            });
        }
    }
}

// Handler unificado — corrige bug de doble listener en setupAdminEvents
function _onManualChange() {
    validateManualInput();
    updateManualRiskPreview();
}

function setupAdminEvents() {
    // --- Simulación ---
    const pauseBtn = document.getElementById('simPauseBtn');
    const resetBtn = document.getElementById('simResetBtn');
    const faultPump = document.getElementById('simFaultPump');
    const faultElev = document.getElementById('simFaultElevator');

    if (pauseBtn) pauseBtn.addEventListener('click', togglePause);
    if (resetBtn) resetBtn.addEventListener('click', resetSim);
    if (faultPump) faultPump.addEventListener('change', () => injectFault('pump'));
    if (faultElev) faultElev.addEventListener('change', () => injectFault('elevator'));

    // Delegación de eventos para botones de velocidad (evita N listeners)
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-speed]');
        if (btn) setSpeed(parseFloat(btn.dataset.speed));
    });

    // --- Panel de umbrales ---
    const saveThreshBombaBtn = document.getElementById('saveThresholdsBombaBtn');
    const threshBombaPanel = document.getElementById('thresholdsBombaPanel');
    const saveThreshElevadorBtn = document.getElementById('saveThresholdsElevadorBtn');
    const threshElevadorPanel = document.getElementById('thresholdsElevadorPanel');
    const resetAllBtn = document.getElementById('resetAllThresholdsBtn');
    if (saveThreshBombaBtn) saveThreshBombaBtn.addEventListener('click', () => saveThresholds('bomba'));
    if (threshBombaPanel) threshBombaPanel.addEventListener('input', () => validateThresholdInputs('bomba'));
    if (saveThreshElevadorBtn) saveThreshElevadorBtn.addEventListener('click', () => saveThresholds('elevador'));
    if (threshElevadorPanel) threshElevadorPanel.addEventListener('input', () => validateThresholdInputs('elevador'));
    if (resetAllBtn) resetAllBtn.addEventListener('click', resetAllThresholds);

    // --- Panel de límites ---
    const saveLimitsBombaBtn = document.getElementById('saveLimitsBombaBtn');
    const limitsBombaPanel = document.getElementById('limitsBombaPanel');
    const saveLimitsElevadorBtn = document.getElementById('saveLimitsElevadorBtn');
    const limitsElevadorPanel = document.getElementById('limitsElevadorPanel');
    if (saveLimitsBombaBtn) saveLimitsBombaBtn.addEventListener('click', () => saveLimits('bomba'));
    if (limitsBombaPanel) limitsBombaPanel.addEventListener('input', () => validateLimitInputs('bomba'));
    if (saveLimitsElevadorBtn) saveLimitsElevadorBtn.addEventListener('click', () => saveLimits('elevador'));
    if (limitsElevadorPanel) limitsElevadorPanel.addEventListener('input', () => validateLimitInputs('elevador'));

    const resetAllLimitsBtn = document.getElementById('resetAllLimitsBtn');
    if (resetAllLimitsBtn) resetAllLimitsBtn.addEventListener('click', resetAllLimits);

    // --- Controles de valor manual (BUG FIX: un solo listener por elemento) ---
    const manualValInput = document.getElementById('manualValueInput');
    const manualValSelect = document.getElementById('manualValueSelect');
    const manualSensorSel = document.getElementById('manualSensorSelect');
    const manualEquipSel = document.getElementById('manualEquipmentSelect');
    const sendManualBtn = document.getElementById('sendManualBtn');

    if (manualValInput) manualValInput.addEventListener('input', _onManualChange);
    if (manualValSelect) manualValSelect.addEventListener('change', _onManualChange);
    if (manualSensorSel) {
        manualSensorSel.addEventListener('change', () => {
            updateManualInputType();
            updateSensorTypeIndicator();
            _onManualChange();
        });
    }
    if (manualEquipSel) {
        manualEquipSel.addEventListener('change', () => {
            populateManualSensorSelect();
            updateSensorTypeIndicator();
            _onManualChange();
        });
    }
    if (sendManualBtn) sendManualBtn.addEventListener('click', sendManualValue);

    // --- Estado inicial del simulador ---
    fetchSimStatus().then(data => {
        if (!data) return;
        updatePauseBtn(data.paused);
        document.querySelectorAll('[data-speed]').forEach(btn => {
            const isActive = parseFloat(btn.dataset.speed) === data.speed;
            btn.classList.toggle('btn-primary', isActive);
            btn.classList.toggle('btn-secondary', !isActive);
        });
        _csSetValue(document.getElementById('simFaultPump'), data.faults?.pump || '');
        _csSetValue(document.getElementById('simFaultElevator'), data.faults?.elevator || '');
    });

    populateManualSensorSelect();
    updateSensorTypeIndicator();
    validateManualInput();
}

function setupBuildingSelector() {
    const sel = document.getElementById('buildingSelect');
    if (!sel) return;
    sel.addEventListener('change', async function () {
        const newId = parseInt(this.value);
        if (!newId || newId === EDIFICIO_ID) return;
        if (_hasUnsavedChanges()) {
            const confirmed = await window.showConfirm('Tienes cambios sin guardar. ¿Cambiar de edificio?');
            if (!confirmed) {
                this.value = EDIFICIO_ID;
                return;
            }
        }
        _unsavedGuardDisabled = true;
        window.location.href = `?edificio_id=${newId}`;
    });
}

function setupUnsavedChangesGuard() {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) {
        sidebar.addEventListener('click', (e) => {
            const link = e.target.closest('a.sidebar-link');
            if (!link || !_hasUnsavedChanges()) return;
            const href = link.getAttribute('href');
            if (!href || href === '#') return;
            e.preventDefault();
            window.showConfirm('Tienes cambios sin guardar. ¿Salir de la página?')
                .then(confirmed => {
                    if (confirmed) {
                        _unsavedGuardDisabled = true;
                        window.location.href = href;
                    }
                });
        });
    }
    window.addEventListener('beforeunload', (e) => {
        if (_unsavedGuardDisabled) return;
        if (_hasUnsavedChanges()) {
            e.preventDefault();
            e.returnValue = '';
        }
    });
}


// =============================================================================
// 13. INICIALIZACIÓN PRINCIPAL
// =============================================================================

window.addEventListener('DOMContentLoaded', () => {
    // --- Página de límites ---
    if (window.IS_LIMITS_PAGE) {
        showState('stateLoading');
        fetchInitialData();
        if (IS_ADMIN) setupAdminEvents();
        setupBuildingSelector();
        setupUnsavedChangesGuard();
        return;
    }

    // --- Página de umbrales ---
    if (window.IS_THRESHOLDS_PAGE) {
        showState('stateLoading');
        fetchInitialData();
        if (IS_ADMIN) setupAdminEvents();
        setupBuildingSelector();
        setupUnsavedChangesGuard();
        return;
    }

    const isMonitoringPage = document.getElementById('activeMonitoring') !== null;

    // --- Página de notificaciones / alertas ---
    if (!isMonitoringPage) {
        if (document.getElementById('live-notifications-list')) {
            const badgeCountEl = document.getElementById('notificationBadgeCount');
            if (badgeCountEl) unreadNotificationCount = parseInt(badgeCountEl.textContent, 10) || 0;
            initLiveNotifications();
            if (EDIFICIO_ID) connectSSE();
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
            emailToggleBtn.className = emailEnabled ? 'btn btn-primary' : 'btn btn-secondary';
            emailToggleBtn.innerHTML = emailEnabled
                ? '<i class="fa-solid fa-envelope"></i> Desactivar correos'
                : '<i class="fa-solid fa-envelope-slash"></i> Activar correos';
        }
        return;
    }

    // --- Página de monitoreo principal ---
    setNotificationBadge(0);
    showState('stateLoading');
    initCharts();

    monitorConnectionTimeout = setTimeout(() => {
        showState('stateOffline');
        monitorConnectionTimeout = null;
    }, 15000);

    connectSSE();
    if (IS_ADMIN) setupAdminEvents();
    setupBuildingSelector();
});


// =============================================================================
// 14. VALIDACIÓN DE FORMULARIOS
// =============================================================================

function initFormValidation() {

    // Expresiones regulares centralizadas
    const REGEX = {
        soloLetras: /^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]*$/,
        soloDigitos: /^\d*$/,
        rif: /^J\d{7,9}\d$/,
        cedula: /^[VE]\d{6,9}$/,
        email: /^[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)*@[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)+$/,
        password: /(?=.*[a-zA-Z])(?=.*\d)/,
    };

    // Configuración de teclas permitidas por tipo de validación
    const KEYPRESS_CONFIG = {
        'solo-letras': { regex: /^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]$/, useUpper: false, allowDelete: false },
        'solo-numeros': { regex: /^\d$/, useUpper: false, allowDelete: true },
        'username': { regex: /^[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]$/, useUpper: false, allowDelete: false },
        'email': { regex: /^[a-zA-Z0-9.@]$/, useUpper: false, allowDelete: false },
        'rif': { regex: /^[J\d\-]$/, useUpper: true, allowDelete: false },
        'cedula': { regex: /^[VE\d.\-]$/, useUpper: true, allowDelete: false },
    };

    // --- Utilidades de error ---
    const mostrarError = (input, mensaje) => {
        const grupo = input.closest('.form-group') || input.parentElement;
        let errEl = grupo.querySelector('.validation-error');
        if (!errEl) { errEl = document.createElement('div'); errEl.className = 'validation-error'; grupo.appendChild(errEl); }
        errEl.textContent = mensaje;
        input.classList.add('input-error');
    };

    const limpiarError = (input) => {
        const grupo = input.closest('.form-group') || input.parentElement;
        const errEl = grupo.querySelector('.validation-error');
        if (errEl) errEl.textContent = '';
        input.classList.remove('input-error');
    };

    const tieneErrores = (form) => {
        if (form.querySelectorAll('.input-error').length > 0) return true;
        return Array.from(form.querySelectorAll('input[required], select[required]'))
            .some(el => !el.value || el.value.trim() === '');
    };

    const toggleSubmit = (form) => {
        const btn = form.querySelector('button[type="submit"], .btn-primary');
        if (btn) btn.disabled = tieneErrores(form);
    };

    // --- Validadores individuales ---
    const validarSoloLetras = (input) => {
        const valor = input.value;
        const maximo = input.maxLength > 0 ? input.maxLength : 999;
        const minimo = input.id === 'nombreEdificio' ? 3 : 2;
        if (valor && !REGEX.soloLetras.test(valor)) {
            input.value = valor.replace(/[^a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]/g, '');
            mostrarError(input, 'Este campo solo acepta letras y espacios.');
        } else if (valor.length > maximo) {
            input.value = valor.slice(0, maximo); mostrarError(input, `Máximo ${maximo} caracteres.`);
        } else if (valor.length > 0 && valor.length < minimo) {
            mostrarError(input, `El campo debe tener al menos ${minimo} caracteres.`);
        } else if (valor.length > 0 && valor.trim().length === 0) {
            mostrarError(input, 'Completa este campo correctamente.');
        } else { limpiarError(input); }
        toggleSubmit(input.form);
    };

    const validarSoloNumeros = (input) => {
        const valor = input.value;
        const maximo = input.maxLength > 0 ? input.maxLength : 999;
        const minimo = input.id === 'cedula' ? 6 : 1;
        if (valor && !REGEX.soloDigitos.test(valor)) {
            input.value = valor.replace(/\D/g, ''); mostrarError(input, 'Este campo solo acepta números.');
        } else if (valor.length > maximo) {
            input.value = valor.slice(0, maximo); mostrarError(input, `Máximo ${maximo} dígitos.`);
        } else if (valor.length > 0 && valor.length < minimo) {
            mostrarError(input, `La cédula debe tener al menos ${minimo} dígitos.`);
        } else { limpiarError(input); }
        toggleSubmit(input.form);
    };

    const validarRIF = (input) => {
        let valor = input.value.toUpperCase().replace(/[^J\d\-]/g, '');
        if (input.value !== valor) input.value = valor;
        const cleaned = valor.replace(/[.\-\s]/g, '');
        if (valor && !REGEX.rif.test(cleaned)) {
            mostrarError(input, 'Formato: J + 7-9 dígitos + dígito control. Ej: J-12345678-0');
        } else if (valor) {
            limpiarError(input);
            const excludeId = input.getAttribute('data-exclude-id') || '';
            fetch(`/buildings/api/check-rif/?rif=${encodeURIComponent(valor)}&exclude_id=${encodeURIComponent(excludeId)}`)
                .then(r => r.json())
                .then(data => {
                    if (data.exists) mostrarError(input, 'Este RIF ya está registrado en otro edificio.');
                    else limpiarError(input);
                    toggleSubmit(input.form);
                }).catch(() => { });
        } else { limpiarError(input); }
        toggleSubmit(input.form);
    };

    const validarCedula = (input) => {
        let valor = input.value.toUpperCase().replace(/[^VE\d.\-]/g, '');
        if (input.value !== valor) input.value = valor;
        const cleaned = valor.replace(/[.\-\s]/g, '');
        if (valor && !REGEX.cedula.test(cleaned)) {
            mostrarError(input, 'Formato: V o E + 6-9 dígitos. Ej: V-12345678');
        } else if (valor) {
            limpiarError(input);
            const excludeId = input.getAttribute('data-exclude-id') || '';
            fetch(`/users/api/check-cedula/?cedula=${encodeURIComponent(valor)}&exclude_id=${encodeURIComponent(excludeId)}`)
                .then(r => r.json())
                .then(data => {
                    if (data.exists) mostrarError(input, 'Esta cédula ya está registrada por otro usuario.');
                    else limpiarError(input);
                    toggleSubmit(input.form);
                }).catch(() => { });
        } else { limpiarError(input); }
        toggleSubmit(input.form);
    };

    const validarUsername = (input) => {
        const valor = input.value;
        const valido = /^[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]+$/;
        if (valor && !valido.test(valor)) { input.value = valor.replace(/[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]/g, ''); mostrarError(input, 'Solo se permiten letras y números, sin espacios.'); }
        else if (valor && valor.length < 4) mostrarError(input, 'El nombre de usuario debe tener al menos 4 caracteres.');
        else limpiarError(input);
        toggleSubmit(input.form);
    };

    const validarEmail = (input) => {
        const valor = input.value;
        if (valor && valor.includes('@') && valor.split('@')[0].length > 30) {
            mostrarError(input, 'Máximo 30 caracteres antes del @.'); toggleSubmit(input.form); return;
        }
        if (valor && valor.length < 6) mostrarError(input, 'El correo debe tener al menos 6 caracteres.');
        else if (valor && !REGEX.email.test(valor)) mostrarError(input, 'Ingresa un correo electrónico válido.');
        else limpiarError(input);
        toggleSubmit(input.form);
    };

    const validarPassword = (input) => {
        const valor = input.value;
        if (valor && valor.length < 6) mostrarError(input, 'La contraseña debe tener al menos 6 caracteres.');
        else if (valor && !REGEX.password.test(valor)) mostrarError(input, 'Debe contener letras y números.');
        else limpiarError(input);
        toggleSubmit(input.form);
    };

    const validarConfirmPassword = (input) => {
        const passField = input.form.querySelector('#password') || input.form.querySelector('#new_password') || input.form.querySelector('#current_password');
        if (input.value && input.value !== passField?.value) mostrarError(input, 'Las contraseñas no coinciden.');
        else limpiarError(input);
        toggleSubmit(input.form);
    };

    const VALIDATORS = {
        'solo-letras': validarSoloLetras,
        'solo-numeros': validarSoloNumeros,
        'rif': validarRIF,
        'cedula': validarCedula,
        'email': validarEmail,
        'password': validarPassword,
        'confirm-password': validarConfirmPassword,
        'username': validarUsername,
    };

    // --- Registro de listeners ---
    document.querySelectorAll('input[data-validate]').forEach((input) => {
        const tipo = input.getAttribute('data-validate');

        input.addEventListener('input', () => {
            const validator = VALIDATORS[tipo];
            if (!validator) return;
            validator(input);
            // Sincronizar confirm-password cuando cambia la contraseña
            if (tipo === 'password') {
                const confirmField = input.form?.querySelector('[data-validate="confirm-password"]');
                if (confirmField?.value) validarConfirmPassword(confirmField);
            }
        });

        input.addEventListener('keypress', (e) => {
            const cfg = KEYPRESS_CONFIG[tipo];
            if (!cfg) return;
            const key = cfg.useUpper ? e.key.toUpperCase() : e.key;
            const allowed = cfg.regex.test(key) || e.key === 'Backspace' || e.key === 'Tab' || (cfg.allowDelete && e.key === 'Delete');
            if (!allowed) e.preventDefault();
        });

        input.addEventListener('blur', () => input.dispatchEvent(new Event('input')));
    });

    // --- Selects ---
    document.querySelectorAll('select').forEach((select) => {
        const handler = () => {
            if (select.value) limpiarError(select);
            else if (select.required) mostrarError(select, 'Este campo es obligatorio.');
            if (select.form) toggleSubmit(select.form);
        };
        select.addEventListener('change', handler);
        select.addEventListener('input', handler);
    });

    // --- Formularios: inicialización y submit ---
    document.querySelectorAll('form').forEach((form) => {
        form.querySelectorAll('input[data-validate], select[data-validate]').forEach((input) => {
            if (input.classList.contains('input-error') || !input.value) return;
            input.dispatchEvent(new Event(input.tagName === 'SELECT' ? 'change' : 'input'));
        });
        toggleSubmit(form);

        form.addEventListener('submit', (e) => {
            let hasErrors = false;
            form.querySelectorAll('input[required], select[required]').forEach((input) => {
                if (!input.value || input.value.trim() === '') {
                    mostrarError(input, 'Este campo es obligatorio.'); hasErrors = true;
                }
            });
            if (hasErrors || tieneErrores(form)) {
                e.preventDefault();
                toggleSubmit(form);
                const firstError = form.querySelector('.input-error');
                if (firstError) { firstError.scrollIntoView({ behavior: 'smooth', block: 'center' }); firstError.focus(); }
            }
        });
    });
}

document.addEventListener('DOMContentLoaded', initFormValidation);
