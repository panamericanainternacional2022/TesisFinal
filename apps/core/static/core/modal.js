
(function(window) {
    function showCustomModal({ title, message, type = 'info', showCancel = false }) {
        return new Promise((resolve) => {
            const backdrop = document.createElement('div');
            backdrop.className = 'custom-modal-backdrop';

            const container = document.createElement('div');
            container.className = 'custom-modal-container';

            let iconHtml = '<i class="fa-solid fa-triangle-exclamation" style="color: var(--state-warn); font-size: var(--text-xl);"></i>';
            if (type === 'success') {
                iconHtml = '<i class="fa-solid fa-circle-check" style="color: var(--state-ok); font-size: var(--text-xl);"></i>';
            } else if (type === 'error') {
                iconHtml = '<i class="fa-solid fa-circle-xmark" style="color: var(--state-critical); font-size: var(--text-xl);"></i>';
            }

            container.innerHTML = `
                <div style="display: flex; align-items: center; gap: 12px; margin-bottom: var(--sp-2, 16px);">
                    ${iconHtml}
                    <span style="font-size: var(--text-lg, 1.125rem); font-weight: var(--weight-bold, 700); color: var(--color-ink, #0a0a0a); letter-spacing: var(--tracking-wide, 0.06em);">${title}</span>
                </div>
                <div style="font-size: var(--text-sm, 0.875rem); color: var(--color-text-secondary, #5f5f5f); line-height: var(--leading-normal, 1.5); margin-bottom: var(--sp-3, 24px); word-break: break-word;">
                    ${message}
                </div>
                <div style="display: flex; justify-content: flex-end; gap: var(--sp-2, 16px);">
                    ${showCancel ? `<button id="customModalCancelBtn" class="btn btn-secondary">Cancelar</button>` : ''}
                    <button id="customModalConfirmBtn" class="btn btn-primary">Aceptar</button>
                </div>
            `;

            backdrop.appendChild(container);
            document.body.appendChild(backdrop);

            setTimeout(() => {
                backdrop.classList.add('active');
            }, 10);

            const cleanUp = (value) => {
                backdrop.classList.remove('active');
                setTimeout(() => {
                    backdrop.remove();
                    resolve(value);
                }, 150);
            };

            container.querySelector('#customModalConfirmBtn').addEventListener('click', () => cleanUp(true));
            if (showCancel) {
                container.querySelector('#customModalCancelBtn').addEventListener('click', () => cleanUp(false));
            }
        });
    }

    window.showCustomModal = showCustomModal;

    window.showAlert = function(message, type = 'info') {
        let title = 'Notificación';
        if (type === 'error') title = 'Error';
        else if (type === 'success') title = 'Éxito';
        else if (type === 'warn' || type === 'warning') title = 'Advertencia';
        return showCustomModal({ title, message, type, showCancel: false });
    };

    window.showConfirm = function(message) {
        return showCustomModal({ title: 'Confirmar', message, type: 'confirm', showCancel: true });
    };

    document.addEventListener('click', function(e) {
        const btn = e.target.closest('.toast-item .btn-icon');
        if (btn) {
            const t = btn.closest('.toast-item');
            t.style.transform = 'translateX(120%)';
            t.style.opacity = '0';
            setTimeout(function() { t.remove(); }, 350);
        }
    });

    window.showToast = function(message, type) {
        type = type || 'info';
        let container = document.querySelector('.js-messages-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'js-messages-container';
            container.style.cssText = 'position:fixed;top:24px;right:24px;z-index:10000;display:flex;flex-direction:column;gap:12px;pointer-events:none;max-width:380px;width:calc(100% - 48px);';
            document.body.appendChild(container);
        }
        const styles = {
            success: 'background-color:var(--state-ok-bg);color:var(--state-ok);border-left:6px solid var(--state-ok);',
            error:   'background-color:var(--state-critical-bg);color:var(--state-critical);border-left:6px solid var(--state-critical);',
            warning: 'background-color:var(--state-warn-bg);color:var(--state-warn);border-left:6px solid var(--state-warn);',
            info:    'background-color:var(--state-inactive-bg);color:var(--state-inactive);border-left:6px solid var(--state-inactive);'
        };
        const itemStyle = styles[type] || styles.info;
        const toast = document.createElement('div');
        toast.className = 'toast-item';
        toast.style.cssText = 'pointer-events:auto;padding:15px;position:relative;border-radius:0;box-sizing:border-box;border:2px solid var(--color-ink);box-shadow:4px 4px 0px var(--color-ink-shadow);transform:translateX(120%);opacity:0;transition:transform 350ms cubic-bezier(0.4,0,0.2,1),opacity 350ms ease;' + itemStyle;
        const hasClose = type !== 'success';
        toast.innerHTML = (hasClose ? '<button type="button" class="btn btn-icon toast-close"><i class="fa-solid fa-xmark"></i></button>' : '')
            + '<div class="toast-body-content" style="' + (hasClose ? 'padding-right:15px;' : 'padding-right:0;') + '">' + message + '</div>';
        container.appendChild(toast);
        requestAnimationFrame(function() { toast.style.transform = 'translateX(0)'; toast.style.opacity = '1'; });
        setTimeout(function() {
            toast.style.transform = 'translateX(120%)';
            toast.style.opacity = '0';
            setTimeout(function() { toast.remove(); }, 350);
        }, 5000);
    };
})(window);
