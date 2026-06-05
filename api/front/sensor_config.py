"""
sensor_config.py — Configuración centralizada de sensores del sistema INES.

Para agregar una nueva variable al sistema en el futuro:
  1. Agrégala a VAR_NAMES con su nombre en español.
  2. Agrégala a UNITS con su unidad (o cadena vacía si no aplica).
  3. Si genera valores especiales (bool, enums), agrégala a VALUE_DISPLAY_ES.
  4. En app27.py, agrega sus acciones en get_professional_action() y en _VAR_ES.
  Eso es todo. No hay que tocar views.py ni el PDF.
"""

# ─── Nombres de variables (inglés → español) ─────────────────────────────────
VAR_NAMES = {
    # Bomba de agua
    "flow_rate":    "Caudal (flujo)",
    "pressure":     "Presión",
    "temperature":  "Temperatura",
    "vibration":    "Vibración",
    "tank_level":   "Nivel de tanque",
    "voltage":      "Voltaje",
    "current":      "Corriente",
    # Ascensor
    "speed":        "Velocidad",
    "load":         "Carga",
    "energy":       "Consumo eléctrico",
    "motor_stuck":  "Motor atascado",
    "trip_count":   "Conteo de viajes",
    "position":     "Posición",
    "door_status":  "Estado de puerta",
    # Eventos de sistema
    "Racionamiento":                        "Caudal (racionamiento)",
    "Protección automática":                "Protección automática",
    "Protección para la bomba de agua":     "Protección para la bomba de agua",
    "Protección para el elevador":          "Protección para el elevador",
}

# ─── Unidades de medida ───────────────────────────────────────────────────────
UNITS = {
    "flow_rate":    "L/s",
    "pressure":     "bar",
    "temperature":  "°C",
    "vibration":    "mm/s",
    "tank_level":   "%",
    "speed":        "m/s",
    "load":         "kg",
    "energy":       "kW",
    "voltage":      "V",
    "current":      "A",
    "trip_count":   "viajes",
    "position":     "piso",
    "door_status":  "",
    "motor_stuck":  "",
    "Racionamiento": "L/s",
}

# ─── Niveles de riesgo en español (forma adjetiva femenina) ───────────────────
RISK_NAMES_ES = {
    "Crítico": "crítica",
    "Alto":    "alta",
    "Medio":   "media",
    "Bajo":    "baja",
    "Normal":  "normal",
    "Info":    "informativa",
}

# ─── Nombres de dispositivos en español ──────────────────────────────────────
DEVICE_NAMES_ES = {
    "pump":       "bomba de agua",
    "elevator":   "ascensor",
    "motor":      "motor",
    "fan":        "ventilador",
    "compressor": "compresor",
    "generator":  "generador",
    "boiler":     "caldera",
    "chiller":    "enfriadora",
}

# ─── Traducción de valores especiales de sensores ─────────────────────────────
# Para variables cuyos valores son enums o booleanos, se traduce el valor crudo
# al español para mostrarlo en el frontend.
VALUE_DISPLAY_ES = {
    "door_status": {
        "open":   "Abierta",
        "closed": "Cerrada",
        "true":   "Bloqueada",
        "false":  "Normal",
    },
    "motor_stuck": {
        "true":  "Atascado",
        "false": "Normal",
        "1":     "Atascado",
        "0":     "Normal",
    },
}
