# Requisitos: Ejemplos de funcionamiento de la app

> Documento para analizar el código contra ejemplos concretos.
> Archivos clave: `app27.py`, `simulation.py`, `alerts.py`, `front/models.py`, `front/sensor_config.py`, `front/views.py`, `front/static/JS/live_monitoring.js`, `templates/monitoreo_dashboard.html`

---

## Variante 1: Edificio solo con bomba de agua

### Setup en DB
- `Edificio` (id=1, nombre="Torre Norte")
- `EquipoMonitoreo` (id=1, id_edificio=1, tipo="bomba", status="operativo")

### Comportamiento esperado del simulador
- `BuildingSimulator.equipment_types == {"bomba"}`
- `pump_on == True`, `elevator_on == False`
- `update_sensor_data()` itera:
  - `flow_rate`, `pressure`, `temperature`, `vibration`, `tank_level`, `voltage`, `current` → se simulan activamente (variación gaussiana, susceptibles a fallas)
  - `position`, `speed`, `load`, `trip_count`, `door_status`, `energy`, `motor_stuck` → valores fijos por defecto (speed=0, load=0, door_status="closed", motor_stuck=False, etc.)

### Payload SocketIO (build_live_payload)
```json
{
  "current": {
    "flow_rate": 14.2,
    "pressure": 3.1,
    "temperature": 42.5,
    "vibration": 0.8,
    "tank_level": 75.0,
    "voltage": 220.0,
    "current": 5.0
  },
  "sensors": {
    "flow_rate": { "value": 14.2, "risk": "Bajo", "color": "green", "unit": "L/min", "name": "Caudal", "min": 0, "max": 50 },
    "pressure": { "value": 3.1, ... },
    "temperature": { "value": 42.5, ... },
    "vibration": { "value": 0.8, ... },
    "tank_level": { "value": 75.0, ... },
    "voltage": { "value": 220.0, ... },
    "current": { "value": 5.0, ... }
  },
  "history": [ /* solo entradas con variable en PUMP_VARS */ ],
  "equipment_types": ["bomba"],
  "protection_pump": null,
  "protection_elevator": null
}
```

### Prohibiciones
- El payload NO debe contener `position`, `speed`, `load`, `trip_count`, `door_status`, `energy`, `motor_stuck` en `current` ni en `sensors`
- El history NO debe contener entradas con variable de ascensor
- `equipment_types` debe ser `["bomba"]` (no `["bomba", "elevador"]`)

### Dashboard visible
- Sección bomba ✅ (tarjetas, status row, chart panel)
- Sección ascensor ❌ (oculta via JS: `display = "none"`)
- Fila resumen bomba ✅
- Fila resumen ascensor ❌

### Alertas
- `flow_rate` cae a 3.2 L/min → `classify_risk` → "Alto" → `send_alert("flow_rate", 3.2, "Alto", ...)` → **se dispara**
- `speed` sube a 3.0 → `classify_risk` → "Crítico" → `send_alert("speed", 3.0, "Crítico", ...)` → **NO se dispara** (speed no está en `_alert_vars`)
- `motor_stuck` cambia a True → **NO se dispara** (motor_stuck no está en `_alert_vars` para edificio sin ascensor)
- `check_rationing(sensor_data["flow_rate"])` se ejecuta solo si `flow_rate` existe (existe por el DEFAULT_SENSOR_DATA)

### Notificaciones en DB
- Alerta de `flow_rate` → `persist_notification_in_django`:
  - `variable = "flow_rate"` → está en `PUMP_VARS` → `_tipo = "bomba"`
  - Busca `EquipoMonitoreo.objects.filter(id_edificio_id=X, tipo="bomba")` → encuentra EQ-001
  - Crea `Notificacion` con `id_equipo_monitoreo=EQ-001` ✅
- Alerta de `speed` no se dispara, no hay notificación ❌ (correcto, no debe haber)

### Protección automática
- `flow_rate` en "Crítico" → `enter_protection_mode(...)` → `protection_targets={"pump"}`
- Dashboard muestra `protection_pump: {"message": "protección activa por alerta...", "remaining": 30}`
- `pump_on` se fuerza a `True` (marcha forzada)
- `protection_elevator` se mantiene en `null`

---

## Variante 2: Edificio solo con elevador

### Setup en DB
- `Edificio` (id=2, nombre="Edificio Central")
- `EquipoMonitoreo` (id=2, id_edificio=2, tipo="elevador", status="operativo")

### Comportamiento esperado del simulador
- `BuildingSimulator.equipment_types == {"elevador"}`
- `pump_on == False`, `elevator_on == True`
- `update_sensor_data()` itera:
  - `position`, `speed`, `load`, `trip_count`, `door_status`, `energy`, `motor_stuck` → se simulan activamente
  - `flow_rate`, `pressure`, `temperature`, `vibration`, `tank_level`, `voltage`, `current` → valores fijos por defecto

### Payload SocketIO
```json
{
  "current": {
    "position": 3.0,
    "speed": 1.2,
    "load": 450.0,
    "trip_count": 128,
    "door_status": "open",
    "energy": 2.5,
    "motor_stuck": false
  },
  "sensors": {
    "position": { "value": 3.0, ... },
    "speed": { "value": 1.2, ... },
    "load": { "value": 450.0, ... },
    "trip_count": { "value": 128, ... },
    "door_status": { "value": "open", ... },
    "energy": { "value": 2.5, ... },
    "motor_stuck": { "value": false, ... }
  },
  "history": [ /* solo entradas con variable en ELEVATOR_VARS */ ],
  "equipment_types": ["elevador"],
  "protection_pump": null,
  "protection_elevator": null
}
```

### Prohibiciones
- El payload NO debe contener `flow_rate`, `pressure`, `temperature`, `vibration`, `tank_level`, `voltage`, `current`
- `equipment_types` debe ser `["elevador"]` únicamente

### Dashboard visible
- Sección bomba ❌
- Sección ascensor ✅

### Alertas
- `speed` sube a 3.5 → "Crítico" → `send_alert("speed", 3.5, "Crítico", ...)` → **se dispara**, activa protección en elevator
- `flow_rate` cae a 2.0 → NO se evalúa (no en `_alert_vars`)
- `motor_stuck` cambia a True → **se dispara** (se agrega explícitamente en `_alert_vars`)

### Protección
- `speed` en "Crítico" → `enter_protection_mode(targets={"elevator"})`
- Dashboard muestra `protection_elevator: {...}`, `protection_pump: null`
- `elevator_on` se fuerza a True, puerta forzada a "closed"

---

## Variante 3: Edificio con bomba + elevador

### Setup en DB
- `Edificio` (id=3, nombre="Complejo Industrial")
- `EquipoMonitoreo` (id=3, id_edificio=3, tipo="bomba")
- `EquipoMonitoreo` (id=4, id_edificio=3, tipo="elevador")

### Comportamiento esperado del simulador
- `BuildingSimulator.equipment_types == {"bomba", "elevador"}`
- `pump_on == True`, `elevator_on == True`
- `update_sensor_data()` itera TODAS las variables (14 en total)

### Payload SocketIO
```json
{
  "current": {
    "flow_rate": 14.2, "pressure": 3.1, "temperature": 42.5, "vibration": 0.8,
    "tank_level": 75.0, "voltage": 220.0, "current": 5.0,
    "position": 3.0, "speed": 1.2, "load": 450.0, "trip_count": 128,
    "door_status": "open", "energy": 2.5, "motor_stuck": false
  },
  "sensors": { /* las 14 variables */ },
  "history": [ /* entradas de TODAS las variables */ ],
  "equipment_types": ["bomba", "elevador"]
}
```

### Dashboard visible
- Sección bomba ✅
- Sección ascensor ✅
- Fila resumen bomba ✅
- Fila resumen ascensor ✅

### Alertas
Se evalúan TODAS las variables de PUMP_VARS + ELEVATOR_VARS + motor_stuck (15 variables en total).
`_alert_vars` = PUMP_VARS ∪ ELEVATOR_VARS ∪ {"motor_stuck"}

### Notificaciones
- Variable de bomba → equipo tipo "bomba"
- Variable de ascensor → equipo tipo "elevador"
- Cada notificación se vincula al `EquipoMonitoreo` correcto

---

## Variante 4: Edificio sin equipos (caso borde)

### Setup en DB
- `Edificio` (id=4, nombre="Edificio Vacío")
- Sin `EquipoMonitoreo` asociado

### Comportamiento esperado
- En startup: no se crea `BuildingSimulator` (no hay equipos que simular)
- `simulators.get(4)` → `None`
- Si es el dummy de respaldo: `equipment_types = {"bomba", "elevador"}` (simula todo)

---

## Variante 5: Cambio de estado del equipo

### Setup
- `EquipoMonitoreo` tipo="bomba", status cambia de "operativo" a "falla"

### Comportamiento esperado
- Dashboard muestra `status: "falla"` en payload (viene de `eq.status`)
- JS actualiza badge `#pumpStatusBadge` con color rojo y texto "Falla"
- El simulador continúa funcionando (status es solo informativo, no afecta pump_on/elevator_on)
- La protección automática puede sobreescribir temporalmente pump_on/elevator_on

---

## Variante 6: Protección automática por alerta crítica

### Setup
- Edificio con bomba, `flow_rate` cae a 0 L/min (fuera de rango)

### Flujo
1. `classify_risk("flow_rate", 0.0)` → `("Crítico", "red")`
2. `send_alert("flow_rate", 0.0, "Crítico", "Verificar inmediatamente...")`
3. Como risk_level es "Crítico" y variable mapea a "pump":
   - `enter_protection_mode(...)` con `targets={"pump"}`
   - En la response: `protection_pump = {"message": "protección activa por alerta...", "remaining": 30}`
   - `pump_on = True` forzado
4. Dashboard muestra tarjeta de protección: "Protección activa - 30s restantes"
5. Tras 30s sin nuevas alertas críticas: protección expira, `pump_on` vuelve a su valor normal

---

## Variante 7: Eliminación en cascada

### Setup
- Edificio con bomba y elevador (2 equipos)
- Se elimina el edificio

### Flujo esperado
```python
edificio.delete()
```
- Django cascade elimina los 2 `EquipoMonitoreo`
- Django cascade elimina las `Notificacion` asociadas
- `UsuarioEdificio` se elimina en cascada
- `views.py` ya no tiene código manual de limpieza (`equipos.delete()`, `StatusEquipoMonitoreo.delete()`, etc.)
- **No debe haber errores de FK ni modelos huérfanos**

---

## Resumen de invariantes

| # | Invariante | Archivo donde se asegura |
|---|-----------|-------------------------|
| 1 | `sensor_data` siempre contiene TODAS las variables (DEFAULT_SENSOR_DATA = 14 vars) | `simulation.py` global y `BuildingSimulator.__init__` |
| 2 | Solo se simulan activamente variables del equipo presente | `simulation.py:update_sensor_data()` (if pump_on / if elevator_on) |
| 3 | Solo variables relevantes llegan al payload | `app27.py:build_live_payload()` (filtro por `_relevant_vars` con PUMP_VARS/ELEVATOR_VARS) |
| 4 | Solo variables relevantes se evalúan para alertas | `app27.py:_run_sim_tick()` (filtro `_alert_vars`) |
| 5 | Solo variables relevantes van al history del payload y del simulador | `app27.py:build_live_payload()` + `_run_sim_tick()` |
| 6 | `equipment_types` se pasa al frontend | `app27.py:build_live_payload()` |
| 7 | Frontend oculta/muestra secciones según equipment_types | `live_monitoring.js`, `monitoreo_dashboard.html` |
| 8 | Notificaciones se vinculan al equipo correcto por tipo de variable | `alerts.py:persist_notification_in_django()` |
| 9 | Eliminación de edificio no requiere código manual de limpieza | `front/views.py` usa solo `edificio.delete()` |
| 10 | `check_rationing` solo se ejecuta si existe `flow_rate` en sensor_data | `app27.py:_run_sim_tick()` (siempre existe por DEFAULT_SENSOR_DATA) |
| 11 | `persona` y `usuario` siguen separados (no mergeados aún) | `front/models.py` |
