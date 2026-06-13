# Constitución Arquitectónica: INES (Monitoreo INES)

### Estándar Unificado de Diseño Macro y Flujo de Dependencias — Versión 1.0 (Documento MACRO)

Este documento establece el marco normativo macro para la arquitectura de dependencias, límites de dominio y flujos de datos en el ecosistema de INES (Sistema de Monitoreo INES). Su único objetivo es prevenir acoplamientos circulares destructivos en la escritura de datos, garantizando la velocidad de desarrollo, la simplicidad del código y la coherencia del monolito pragmático. Su cumplimiento es obligatorio y complementario al estándar de diseño micro.

---

## 1. Regla de Oro: CQRS Pragmático y Escritura Colaborativa

Dividimos el comportamiento del sistema en dos flujos independientes para evitar acoplamientos destructivos y optimizar el rendimiento:

* **Flujo de Lectura (consultas / vistas): Totalmente libre.** Cualquier componente de lectura, selector, servicio de consulta o el propio *frontend* puede realizar combinaciones directas (`JOINs`) o consultar cualquier tabla o módulo directamente para renderizar la información como mejor convenga, sin pasar por orquestadores intermedios.
* **Flujo de Escritura (mutaciones / transacciones): Interconexión libre con importación perezosa (*lazy imports*).** Cualquier módulo o servicio del sistema tiene permitido invocar flujos de escritura, mutar estados o ejecutar servicios de cualquier otro módulo de forma bidireccional si la lógica de negocio lo requiere.

---

## 2. Prevención de Acoplamiento Cíclico y Línea Roja

Para permitir la escritura flexible entre dominios sin provocar bloqueos de inicialización o errores en tiempo de ejecución (`ImportError` circular en Django), se establecen las siguientes restricciones técnicas obligatorias:

* **Prohibición de Importaciones en el Alcance Global:** Queda estrictamente prohibido importar servicios de escritura de otros módulos en la cabecera (*top-level*) de los archivos.
* **Uso Obligatorio de Importación Perezosa (*lazy imports*):** Toda referencia a servicios de mutación de un módulo externo debe importarse de manera perezosa, declarando el `import` localmente y de forma exclusiva **dentro de la función o método específico** que ejecuta la transacción.
* **La Línea Roja (Prohibición de Cascada Circular en Caliente):** Aunque la importación perezosa permite que la función `A()` del módulo de sensores llame a la función `B()` del módulo de alertas, queda estrictamente prohibido que un flujo transaccional genere un bucle lógico cerrado en caliente. La función `B()` **jamás** debe volver a disparar un servicio sincrónico del módulo de sensores dentro del mismo hilo transaccional. Esto previene bucles infinitos y bloqueos (*deadlocks*) en la base de datos.

```python
# Ejemplo de uso correcto en cualquier servicio
def process_sensor_alert(building_id: int) -> None:
    # 1. Lógica propia del módulo actual
    ...
    # 2. LAZY IMPORT: Requerido para evitar la importación circular con el módulo externo
    from alerts.alerts import send_alert
    
    send_alert(building_id)
```

---

## 3. Diccionario de Dominios y Responsabilidades

El mapa de módulos del monolito define los límites conceptuales de cada contexto para mantener el código ordenado, aunque sus servicios transaccionales coexistan de forma flexible:

### Módulo Transversal: core

* **Responsabilidad:** Infraestructura base, decoradores de autenticación, middleware, tokens de diseño globales y servicios compartidos de clasificación de riesgo.

### Módulo: users

* **Responsabilidad:** Gestión de autenticación, perfiles de usuario (Persona/Usuario), roles (ADMIN/US), registro con activación por correo y preferencias de alerta.

### Módulo: buildings

* **Responsabilidad:** Gestión de edificios, registro de equipos de monitoreo (bombas y elevadores) y asignación de beneficiaros a inmuebles.

### Módulo: sensors

* **Responsabilidad:** Motor de simulación física (BuildingSimulator), generación de datos sensorizados cada 5s, modelo de fallos estocásticos con contagio, payload SSE y estados de protección de equipos.

### Módulo: alerts

* **Responsabilidad:** Detección de riesgos, umbrales configurables, modo de protección automática, envío de correos Gmail SMTP con cooldown de 5 min, notificaciones persistentes y racionamiento.

### Módulo: monitoring

* **Responsabilidad:** Paneles de monitoreo en tiempo real (SSE), historial de eventos con filtros y paginación, controles de simulación (inyección de fallos) y vista de selección de edificios.

### Módulo: reports

* **Responsabilidad:** Generación de reportes PDF (historial de eventos con leyenda de colores, medidas correctivas, listado de beneficiarios) con respaldo CSV.
