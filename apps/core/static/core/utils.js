

window.csrfFetch = function csrfFetch(url, opts = {}) {
    const csrfCookie = document.cookie.split('; ').find(r => r.startsWith('csrftoken='));
    const token = csrfCookie ? csrfCookie.split('=')[1] : '';
    opts.headers = { ...opts.headers, 'X-CSRFToken': token };
    opts.credentials = 'same-origin';
    return fetch(url, opts);
};

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

document.addEventListener('DOMContentLoaded', () => {
    initDropdowns();
    initConfirmDelete();
});
