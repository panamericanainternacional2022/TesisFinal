/* ==========================================================================
   utils.js — INES · Swiss Typographic Grid
   Utilidades JavaScript globales compartidas entre todos los templates.

   Cargado por base_sidebar.html (disponible en todas las páginas con sidebar).
   ========================================================================== */

/* ── CSRF Fetch ─────────────────────────────────────────────────────────────
   Wrapper sobre fetch() que inyecta automáticamente el token CSRF de Django.
   Uso: csrfFetch('/api/endpoint/', { method: 'POST', body: JSON.stringify(data) })
   ── */
window.csrfFetch = function csrfFetch(url, opts = {}) {
    const csrfCookie = document.cookie.split('; ').find(r => r.startsWith('csrftoken='));
    const token = csrfCookie ? csrfCookie.split('=')[1] : '';
    opts.headers = { ...opts.headers, 'X-CSRFToken': token };
    opts.credentials = 'same-origin';
    return fetch(url, opts);
};

/* ── Dropdown Actions — toggle y cierre global ──────────────────────────────
   Gestiona los menús .actions-dropdown presentes en listas de datos.
   Inicializar con: initDropdowns() una vez que el DOM esté listo.
   ── */
window.closeAllDropdowns = function closeAllDropdowns() {
    document.querySelectorAll('.dropdown-menu.open').forEach(menu => {
        menu.classList.remove('open');
        const trigger = menu.previousElementSibling;
        if (trigger?.classList.contains('btn-icon')) {
            trigger.classList.remove('open');
        }
    });
};

window.initDropdowns = function initDropdowns() {
    document.addEventListener('click', function (e) {
        const trigger = e.target.closest('.actions-dropdown .btn-icon');
        if (trigger) {
            e.stopPropagation();
            const menu = trigger.nextElementSibling;
            const isOpen = menu.classList.contains('open');
            closeAllDropdowns();
            if (!isOpen) {
                menu.classList.add('open');
                trigger.classList.add('open');
            }
        } else {
            closeAllDropdowns();
        }
    });
};

/* ── Confirm-delete con modal ───────────────────────────────────────────────
   Adjunta el comportamiento de confirmación a todos los .btn-confirm-delete.
   Depende de showCustomModal() de modal.js (cargado globalmente).
   ── */
window.initConfirmDelete = function initConfirmDelete() {
    document.querySelectorAll('.btn-confirm-delete').forEach(link => {
        link.addEventListener('click', function (e) {
            e.preventDefault();
            const url     = this.getAttribute('href');
            const message = this.getAttribute('data-confirm');
            showCustomModal({
                title:      'Confirmar',
                message:    message,
                type:       'confirm',
                showCancel: true
            }).then(confirmed => {
                if (confirmed) window.location.href = url;
            });
        });
    });
};

/* ── Auto-init al cargar DOM ────────────────────────────────────────────────
   Inicializa dropdowns y confirm-delete en todas las páginas automáticamente.
   Los templates individuales pueden llamar a estas funciones de nuevo si
   agregan elementos dinámicamente al DOM.
   ── */
document.addEventListener('DOMContentLoaded', () => {
    initDropdowns();
    initConfirmDelete();
});
