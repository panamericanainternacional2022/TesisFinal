# Reglas de Desarrollo — INES

## 1. Interfaz de Usuario y Alertas (Modales)
Queda estrictamente **prohibido** el uso de las alertas nativas del navegador (`alert()`, `confirm()`, `prompt()`) en cualquier vista, script o plantilla del proyecto. Todas las alertas y solicitudes de confirmación deben implementarse utilizando el sistema de **Modales Custom** coherente con el estilo tipográfico suizo de la aplicación.

### Reglas para Modales:
- **Esquinas Rectas:** No usar bordes redondeados (`border-radius: 0px`).
- **Bordes Fuertes:** Los contenedores deben usar un borde negro grueso de `2px solid var(--color-ink)`.
- **Sombra Sólida:** Usar una sombra sólida desplazada (`box-shadow: 8px 8px 0px rgba(10, 10, 10, 0.15)`).
- **Asincronía:** Los modales deben devolver una `Promise` (ej. `showCustomModal`, `showAlert`, `showConfirm`) para no bloquear el hilo de ejecución principal y permitir una experiencia de usuario fluida.

### Ejemplo de Uso en JS (Panel de Monitoreo / app27.py):
```javascript
// Mostrar una alerta informativa, de éxito o error
await window.showAlert('Mensaje de éxito', 'success');
await window.showAlert('Ocurrió un error', 'error');

// Confirmación de acción
if (await window.showConfirm('¿Estás seguro de realizar esta acción?')) {
    // Código si el usuario acepta
}
```

### Ejemplo de Uso en HTML (Vistas Django):
Para enlaces que requieran confirmación antes de navegar, utilizar la clase `.btn-confirm-delete` junto con el atributo `data-confirm`:
```html
<a href="{% url 'eliminar_elemento' item.id %}" class="btn-confirm-delete" data-confirm="¿Estás seguro de eliminar a {{ item.nombre }}?">
```
*(Asegurarse de tener importada la estructura y los scripts de `showCustomModal` en la plantilla).*
