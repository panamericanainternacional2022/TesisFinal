"""
sensor_config.py — Configuración centralizada de sensores del sistema INES.

Para agregar una nueva variable al sistema en el futuro:
  1. Agrégala a VAR_NAMES con su nombre en español.
  2. Agrégala a UNITS con su unidad (o cadena vacía si no aplica).
  3. Si genera valores especiales (bool, enums), agrégala a VALUE_DISPLAY_ES.
  4. Si pertenece a un dispositivo, agrégala a PUMP_VARS o ELEVATOR_VARS.
  5. En app27.py, agrega sus acciones en get_professional_action().
   Eso es todo. Las listas de estadísticas se derivan automáticamente.
"""

# ─── Nombres de variables (inglés → español) ──────────────────────────────
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
    "rationing":            "Caudal (racionamiento)",
    "auto_protection":      "Protección automática",
    "protection_pump":      "Protección para la bomba de agua",
    "protection_elevator":  "Protección para el elevador",
}

# ─── Unidades de medida ───────────────────────────────────────────────────
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
    "rationing":    "L/s",
}

# ─── Niveles de riesgo en español (forma adjetiva femenina) ───────────────
RISK_NAMES_ES = {
    "Crítico": "crítica",
    "Alto":    "alta",
    "Medio":   "media",
    "Bajo":    "baja",
    "Normal":  "normal",
    "Info":    "informativa",
}

# ─── Nombres de dispositivos en español ───────────────────────────────────
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

# ─── Variables excluidas de clasificación de riesgo ───────────────────────
NO_RISK_VARS = ["position", "door_status", "motor_stuck"]

# ─── Variables de sensores agrupadas por dispositivo ──────────────────────
PUMP_VARS = [
    "flow_rate",
    "pressure",
    "temperature",
    "vibration",
    "tank_level",
    "voltage",
    "current",
]

ELEVATOR_VARS = [
    "position",
    "speed",
    "load",
    "trip_count",
    "door_status",
    "energy",
    "motor_stuck",
]

# ─── Listas derivadas (sin redundancia de nombres) ────────────────────────
# Variables numéricas de ascensor útiles para estadísticas
_ELEVATOR_NUMERIC = [v for v in ELEVATOR_VARS if v not in NO_RISK_VARS]

# Estadísticas de la UI en vivo: variables de bomba + carga
STATS_VARS = PUMP_VARS + ["load"]

# Tabla de estadísticas del PDF: todas las variables numéricas de ambos dispositivos
PDF_STATS_VARS = PUMP_VARS + _ELEVATOR_NUMERIC

# Gráfico de barras del PDF: todas las numéricas excepto velocidad y viajes
PDF_BAR_VARS = [v for v in PDF_STATS_VARS if v not in ("speed", "trip_count")]

PDF_BAR_LABELS = {
    "temperature": "Temp. (°C)",
    "pressure":    "Presión (bar)",
    "flow_rate":   "Caudal (L/s)",
    "vibration":   "Vibración (mm/s)",
    "tank_level":  "Tanque (%)",
    "load":        "Carga (kg)",
    "energy":      "Energía (kW)",
    "voltage":     "Voltaje (V)",
    "current":     "Corriente (A)",
}

# ─── Traducción de valores especiales de sensores ─────────────────────────
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
