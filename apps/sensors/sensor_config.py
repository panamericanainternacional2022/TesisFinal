"""
sensor_config.py — Configuración centralizada de sensores del sistema INES.
Única fuente de verdad para nombres, unidades, umbrales, rangos, etc.

Para agregar una nueva variable al sistema en el futuro:
  1. Agrégala a VAR_NAMES con su nombre en español.
  2. Agrégala a UNITS con su unidad (o cadena vacía si no aplica).
  3. Si genera valores especiales (bool, enums), agrégala a VALUE_DISPLAY_ES.
  4. Si pertenece a un dispositivo, agrégala a PUMP_VARS o ELEVATOR_VARS.
  5. Si tiene umbrales de riesgo, agrégala a DEFAULT_THRESHOLDS.
  6. Si tiene rango físico, agrégala a SENSOR_RANGES.
   Eso es todo. Las listas derivadas se generan automáticamente.
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
    # Elevador
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

# ─── Niveles de riesgo (constantes) ───────────────────────────────────────
RISK_INFO    = "Info"
RISK_BAJO    = "Bajo"
RISK_MEDIO   = "Medio"
RISK_ALTO    = "Alto"
RISK_CRITICO = "Crítico"
RISK_NORMAL  = "Normal"

SEVERITY_LEVELS = [RISK_INFO, RISK_BAJO, RISK_MEDIO, RISK_ALTO, RISK_CRITICO]

# ─── Niveles de riesgo en español (forma adjetiva femenina) ───────────────
RISK_NAMES_ES = {
    RISK_CRITICO: "crítica",
    RISK_ALTO:    "alta",
    RISK_MEDIO:   "media",
    RISK_BAJO:    "baja",
    RISK_NORMAL:  "normal",
    RISK_INFO:    "informativa",
}

# ─── Nombres de dispositivos en español ───────────────────────────────────
DEVICE_NAMES_ES = {
    "pump":       "bomba de agua",
    "elevator":   "elevador",
    "motor":      "motor",
    "fan":        "ventilador",
    "compressor": "compresor",
    "generator":  "generador",
    "boiler":     "caldera",
    "chiller":    "enfriadora",
}

# ─── Variables excluidas de clasificación de riesgo ───────────────────────
NO_RISK_VARS = ["position", "door_status"]

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
# Variables numéricas de elevador útiles para estadísticas
_ELEVATOR_NUMERIC = [v for v in ELEVATOR_VARS if v not in NO_RISK_VARS]

# Estadísticas de la UI en vivo: todas las variables numéricas de ambos dispositivos
STATS_VARS = PUMP_VARS + _ELEVATOR_NUMERIC

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
        "open":     "Abierta",
        "closed":   "Cerrada",
        "opening":  "Abriendo",
        "closing":  "Cerrando",
        "true":     "Bloqueada",
        "false":    "Normal",
    },
    "motor_stuck": {
        "true":  "Atascado",
        "false": "Normal",
        "1":     "Atascado",
        "0":     "Normal",
    },
}

# ─── Umbrales de riesgo por defecto ────────────────────────────────────
# Cada entrada: {"direction": "higher"|"lower"|"range", "low": ..., "medium": ..., "high": ...}
DEFAULT_THRESHOLDS = {
    "flow_rate":   {"direction": "higher", "low": 20,   "medium": 35,  "high": 45},
    "pressure":    {"direction": "higher", "low": 5,    "medium": 7,   "high": 9},
    "temperature": {"direction": "higher", "low": 70,   "medium": 85,  "high": 100},
    "vibration":   {"direction": "higher", "low": 4,    "medium": 7,   "high": 10},
    "tank_level":  {"direction": "lower",  "low": 30,   "medium": 15,  "high": 5},
    "speed":       {"direction": "higher", "low": 1.5,  "medium": 2.5, "high": 3.5},
    "load":        {"direction": "higher", "low": 400,  "medium": 700, "high": 900},
    "trip_count":  {"direction": "higher", "low": 10000,"medium": 20000,"high": 30000},
    "energy":      {"direction": "higher", "low": 8,    "medium": 12,  "high": 15},
    "voltage":     {"direction": "range",  "low": 200,  "high": 240},
    "current":     {"direction": "higher", "low": 30,   "medium": 40,  "high": 50},
}

# ─── Umbrales de recomendación (alertas tempranas) ─────────────────────
# Son más conservadores que DEFAULT_THRESHOLDS; se usan en el motor de
# recomendaciones para generar mensajes proactivos antes de que el riesgo
# se vuelva crítico.
RECOMMENDATION_THRESHOLDS = {
    "temperature": {"max_warn": 70,  "max_crit": 85},
    "flow_rate":   {"min_warn": 20,  "min_crit": 10},
    "pressure":    {"max_warn": 8},
    "vibration":   {"max_warn": 7},
    "tank_level":  {"min_warn": 30,  "min_crit": 20},
    "load":        {"max_warn": 800},
    "voltage":     {"range_warn": (200, 240)},
    "current":     {"max_warn": 45},
}

# ─── Variables de sistema (eventos, no sensores físicos) ───────────────
SYSTEM_VARS = ["rationing", "auto_protection", "protection_pump", "protection_elevator"]

# ─── Todas las variables que generan alertas ───────────────────────────
ALERT_VARS = list(set(PUMP_VARS + ELEVATOR_VARS + SYSTEM_VARS))

# ─── Variables que activan protección automática ───────────────────────
PROTECTION_VARS = {
    "pump":     [v for v in PUMP_VARS if v != "tank_level"],
    "elevator": [v for v in ELEVATOR_VARS if v not in ("position", "trip_count", "door_status")],
}

# ─── Constantes del engine de simulación ───────────────────────────────
SIM_TICK_INTERVAL = 5
MAX_CONSECUTIVE_FAILURES = 5

# ─── Umbral de racionamiento (L/s) ─────────────────────────────────────
RATIONING_THRESHOLD = 8.0

# ─── Rango físico (clamp bounds) por variable ──────────────────────────
SENSOR_RANGES = {
    "flow_rate":   (0, 60),
    "pressure":    (0, 12),
    "temperature": (22.0, 130),
    "vibration":   (0, 15),
    "tank_level":  (0, 100),
    "voltage":     (180, 260),
    "current":     (0, 70),
    "speed":       (0, 6),
    "load":        (0, 1200),
    "energy":      (0, 20),
    "trip_count":  (0, 100000),
}

# ─── Nivel de riesgo por defecto cuando no hay umbrales ────────────────
RISK_UNKNOWN = "Desconocido"

# ─── Nombres de fallas de simulación en español ────────────────────────
FAULT_NAMES_ES = {
    "dry_run":            "Sequía (dry run)",
    "blocked_discharge":  "Descarga bloqueada",
    "pipe_burst":         "Ruptura de tubería",
    "cavitation":         "Cavitación",
    "overheat":           "Sobrecalentamiento",
    "power_surge":        "Sobrecarga eléctrica",
    "power_outage":       "Corte eléctrico",
    "motor_stuck":        "Motor atascado",
    "door_blocked":       "Puerta bloqueada",
    "overspeed":          "Exceso de velocidad",
}
