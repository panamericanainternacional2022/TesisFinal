// ─── VALIDACIÓN DE FORMULARIOS ───────────────────────────────────
// Texto: solo letras, espacios, ñ, acentos
// Números: solo dígitos (con excepciones para teléfono/RIF)
// Feedback visual en rojo debajo del input
// Botón submit deshabilitado mientras hayan errores

document.addEventListener('DOMContentLoaded', function () {

    // ─── UTILIDADES ─────────────────────────────────────────────

    function mostrarError(input, mensaje) {
        const grupo = input.closest('.form-group') || input.parentElement;
        let errEl = grupo.querySelector('.validation-error');
        if (!errEl) {
            errEl = document.createElement('div');
            errEl.className = 'validation-error';
            grupo.appendChild(errEl);
        }
        errEl.textContent = mensaje;
        input.classList.add('input-error');
        input.classList.remove('input-valid');
    }

    function limpiarError(input) {
        const grupo = input.closest('.form-group') || input.parentElement;
        const errEl = grupo.querySelector('.validation-error');
        if (errEl) errEl.textContent = '';
        input.classList.remove('input-error');
        input.classList.add('input-valid');
    }

    function tieneErrores(form) {
        if (form.querySelectorAll('.input-error').length > 0) return true;
        // Validar si hay campos obligatorios vacíos
        const requiredFields = form.querySelectorAll('input[required], select[required]');
        for (let i = 0; i < requiredFields.length; i++) {
            const el = requiredFields[i];
            if (!el.value || el.value.trim() === '') {
                return true;
            }
        }
        return false;
    }

    function toggleSubmit(form) {
        const btn = form.querySelector('button[type="submit"], .btn-primary');
        if (!btn) return;
        if (tieneErrores(form)) {
            btn.disabled = true;
            btn.style.opacity = '0.5';
            btn.style.cursor = 'not-allowed';
        } else {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.style.cursor = 'pointer';
        }
    }

    // ─── VALIDADORES POR TIPO ───────────────────────────────────

    // Solo letras (incluye ñ y acentos) y espacios
    function validarSoloLetras(input) {
        const valor = input.value;
        const maximo = input.maxLength && input.maxLength > 0 ? input.maxLength : 999;
        const soloLetras = /^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]*$/;

        let minimo = 2;
        if (input.id === 'nombreEdificio') {
            minimo = 3;
        }

        if (valor && !soloLetras.test(valor)) {
            input.value = valor.replace(/[^a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]/g, '');
            mostrarError(input, 'Este campo solo acepta letras y espacios.');
        } else if (valor.length > maximo) {
            input.value = valor.slice(0, maximo);
            mostrarError(input, `Máximo ${maximo} caracteres.`);
        } else if (valor.length > 0 && valor.length < minimo) {
            mostrarError(input, `El campo debe tener al menos ${minimo} caracteres.`);
        } else if (valor.length > 0 && valor.trim().length === 0) {
            mostrarError(input, 'Completa este campo correctamente.');
        } else {
            limpiarError(input);
        }
        toggleSubmit(input.form);
    }

    // Solo dígitos numéricos
    function validarSoloNumeros(input) {
        const valor = input.value;
        const maximo = input.maxLength && input.maxLength > 0 ? input.maxLength : 999;
        const soloDigitos = /^\d*$/;

        let minimo = 1;
        if (input.id === 'cedula') {
            minimo = 6;
        }

        if (valor && !soloDigitos.test(valor)) {
            input.value = valor.replace(/\D/g, '');
            mostrarError(input, 'Este campo solo acepta números.');
        } else if (valor.length > maximo) {
            input.value = valor.slice(0, maximo);
            mostrarError(input, `Máximo ${maximo} dígitos.`);
        } else if (valor.length > 0 && valor.length < minimo) {
            mostrarError(input, `La cédula debe tener al menos ${minimo} dígitos.`);
        } else {
            limpiarError(input);
        }
        toggleSubmit(input.form);
    }

    // RIF: letra J + 7-9 dígitos + dígito de control, guiones opcionales
    function validarRIF(input) {
        let valor = input.value.toUpperCase();
        const soloValido = /^[J\d\-]*$/;
        if (valor && !soloValido.test(valor)) {
            valor = valor.replace(/[^J\d\-]/g, '');
        }
        if (input.value !== valor) {
            input.value = valor;
        }
        const cleaned = valor.replace(/[\.\-\s]/g, '');
        const valido = /^J\d{7,9}\d$/;
        if (valor && !valido.test(cleaned)) {
            mostrarError(input, 'Formato: J + 7-9 dígitos + dígito control. Ej: J-12345678-0');
        } else if (valor) {
            limpiarError(input);
            const excludeId = input.getAttribute('data-exclude-id') || '';
            const url = `/buildings/api/check-rif/?rif=${encodeURIComponent(valor)}&exclude_id=${encodeURIComponent(excludeId)}`;
            fetch(url)
                .then(response => response.json())
                .then(data => {
                    if (data.exists) {
                        mostrarError(input, 'Este RIF ya está registrado en otro edificio.');
                    } else {
                        limpiarError(input);
                    }
                    toggleSubmit(input.form);
                })
                .catch(() => { });
        } else {
            limpiarError(input);
        }
        toggleSubmit(input.form);
    }

    // Cédula: V o E + 6-9 dígitos, guiones/puntos opcionales
    function validarCedula(input) {
        let valor = input.value.toUpperCase();
        const soloValido = /^[VE\d\.\-]*$/;
        if (valor && !soloValido.test(valor)) {
            valor = valor.replace(/[^VE\d\.\-]/g, '');
        }
        if (input.value !== valor) {
            input.value = valor;
        }
        const cleaned = valor.replace(/[\.\-\s]/g, '');
        const valido = /^[VE]\d{6,9}$/;
        if (valor && !valido.test(cleaned)) {
            mostrarError(input, 'Formato: V o E + 6-9 dígitos. Ej: V-12345678');
        } else if (valor) {
            limpiarError(input);
            const excludeId = input.getAttribute('data-exclude-id') || '';
            const url = `/users/api/check-cedula/?cedula=${encodeURIComponent(valor)}&exclude_id=${encodeURIComponent(excludeId)}`;
            fetch(url)
                .then(response => response.json())
                .then(data => {
                    if (data.exists) {
                        mostrarError(input, 'Esta cédula ya está registrada por otro usuario.');
                    } else {
                        limpiarError(input);
                    }
                    toggleSubmit(input.form);
                })
                .catch(() => { });
        } else {
            limpiarError(input);
        }
        toggleSubmit(input.form);
    }

    // Username: letras, números, sin espacios
    function validarUsername(input) {
        const valor = input.value;
        const valido = /^[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]+$/;
        if (valor && !valido.test(valor)) {
            input.value = valor.replace(/[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]/g, '');
            mostrarError(input, 'Solo se permiten letras y números, sin espacios.');
        } else if (valor && valor.length < 4) {
            mostrarError(input, 'El nombre de usuario debe tener al menos 4 caracteres.');
        } else {
            limpiarError(input);
        }
        toggleSubmit(input.form);
    }

    // Email: solo a-z, 0-9, punto (.) y @
    function validarEmail(input) {
        const valor = input.value;
        const emailRegex = /^[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)*@[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)+$/;
        if (valor && valor.includes('@')) {
            const local = valor.split('@')[0];
            if (local.length > 30) {
                mostrarError(input, 'Máximo 30 caracteres antes del @.');
                toggleSubmit(input.form);
                return;
            }
        }
        if (valor && valor.length < 6) {
            mostrarError(input, 'El correo debe tener al menos 6 caracteres.');
        } else if (valor && !emailRegex.test(valor)) {
            mostrarError(input, 'Ingresa un correo electrónico válido.');
        } else {
            limpiarError(input);
        }
        toggleSubmit(input.form);
    }

    // Contraseña: mínimo 6 caracteres
    function validarPassword(input) {
        const valor = input.value;
        if (valor && valor.length > 0 && valor.length < 6) {
            mostrarError(input, 'La contraseña debe tener al menos 6 caracteres.');
        } else if (valor && valor.length > 0 && !/(?=.*[a-zA-Z])(?=.*\d)/.test(valor)) {
            mostrarError(input, 'Debe contener letras y números.');
        } else {
            limpiarError(input);
        }
        toggleSubmit(input.form);
    }

    // Confirmar contraseña
    function validarConfirmPassword(input) {
        const form = input.form;
        const passField = form.querySelector('#password') || form.querySelector('#new_password') || form.querySelector('#current_password');
        const passValue = passField ? passField.value : '';
        if (input.value && input.value !== passValue) {
            mostrarError(input, 'Las contraseñas no coinciden.');
        } else {
            limpiarError(input);
        }
        toggleSubmit(input.form);
    }

    // ─── CONFIGURAR VALIDACIÓN POR DATA-ATRIBUTE ────────────────

    document.querySelectorAll('input[data-validate]').forEach(function (input) {
        const tipo = input.getAttribute('data-validate');

        input.addEventListener('input', function () {
            switch (tipo) {
                case 'solo-letras': validarSoloLetras(input); break;
                case 'solo-numeros': validarSoloNumeros(input); break;

                case 'rif': validarRIF(input); break;
                case 'cedula': validarCedula(input); break;
                case 'email': validarEmail(input); break;
                case 'password': 
                    validarPassword(input); 
                    // Re-validar confirmación de contraseña si ya tiene valor
                    const confirmField = input.form.querySelector('[data-validate="confirm-password"]');
                    if (confirmField && confirmField.value) {
                        validarConfirmPassword(confirmField);
                    }
                    break;
                case 'confirm-password': validarConfirmPassword(input); break;
                case 'username': validarUsername(input); break;
            }
        });

        // Bloquear teclas no permitidas según el tipo
        input.addEventListener('keypress', function (e) {
            switch (tipo) {
                case 'solo-letras':
                    if (!/^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]$/.test(e.key) && e.key !== 'Backspace' && e.key !== 'Tab') {
                        e.preventDefault();
                    }
                    break;
                case 'solo-numeros':
                    if (!/^\d$/.test(e.key) && e.key !== 'Backspace' && e.key !== 'Tab' && e.key !== 'Delete') {
                        e.preventDefault();
                    }
                    break;
                case 'username':
                    if (!/^[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]$/.test(e.key) && e.key !== 'Backspace' && e.key !== 'Tab') {
                        e.preventDefault();
                    }
                    break;
                case 'email':
                    if (!/^[a-zA-Z0-9.@]$/.test(e.key) && e.key !== 'Backspace' && e.key !== 'Tab') {
                        e.preventDefault();
                    }
                    break;
                case 'rif':
                    if (!/^[J\d\-]$/.test(e.key.toUpperCase()) && e.key !== 'Backspace' && e.key !== 'Tab') {
                        e.preventDefault();
                    }
                    break;
                case 'cedula':
                    if (!/^[VE\d\.\-]$/.test(e.key.toUpperCase()) && e.key !== 'Backspace' && e.key !== 'Tab') {
                        e.preventDefault();
                    }
                    break;
            }
        });

        // Validar al perder el foco también
        input.addEventListener('blur', function () {
            input.dispatchEvent(new Event('input'));
        });
    });

    // Validar select elements en cambios e inputs para limpiar errores
    document.querySelectorAll('select').forEach(function (select) {
        const handler = function () {
            if (select.value) {
                limpiarError(select);
            } else if (select.required) {
                mostrarError(select, 'Este campo es obligatorio.');
            }
            toggleSubmit(select.form);
        };
        select.addEventListener('change', handler);
        select.addEventListener('input', handler);
    });

    // ─── VALIDACIÓN INICIAL ─────────────────────────────────────

    document.querySelectorAll('form').forEach(function (form) {
        form.querySelectorAll('input[data-validate], select').forEach(function (input) {
            if (input.classList.contains('input-error')) {
                return;
            }
            if (input.value) {
                if (input.tagName === 'SELECT') {
                    input.dispatchEvent(new Event('change'));
                } else {
                    input.dispatchEvent(new Event('input'));
                }
            }
        });
        toggleSubmit(form);

        // Prevenir envío si hay errores o campos obligatorios vacíos
        form.addEventListener('submit', function (e) {
            let hasErrors = false;
            form.querySelectorAll('input[required], select[required]').forEach(function (input) {
                if (!input.value || input.value.trim() === '') {
                    mostrarError(input, 'Este campo es obligatorio.');
                    hasErrors = true;
                }
            });
            if (hasErrors || tieneErrores(form)) {
                e.preventDefault();
                toggleSubmit(form);
                
                // Hacer scroll al primer error
                const firstError = form.querySelector('.input-error');
                if (firstError) {
                    firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    firstError.focus();
                }
            }
        });
    });

});
