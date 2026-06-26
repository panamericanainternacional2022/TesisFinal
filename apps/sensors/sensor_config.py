VAR_NAMES = {
    "flow_rate":    "Caudal (flujo)",
    "pressure":     "Presión",
    "temperature":  "Temperatura",
    "vibration":    "Vibración",
    "tank_level":   "Nivel de tanque",
    "voltage":      "Voltaje",
    "current":      "Corriente",
    "speed":        "Velocidad",
    "load":         "Carga",
    "energy":       "Consumo eléctrico",
    "motor_stuck":  "Motor atascado",
    "trip_count":   "Conteo de viajes",
    "position":     "Posición",
    "door_status":  "Estado de puerta",
    "rationing":                "Caudal (racionamiento)",
    "auto_protection":          "Protección automática",
    "protection_pump":          "Protección para la bomba de agua",
    "protection_elevator":      "Protección para el elevador",
    "fault_resolved_pump":      "Falla de bomba resuelta",
    "fault_resolved_elevator":  "Falla de elevador resuelta",
}

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

RISK_INFO    = "Info"
RISK_BAJO    = "Bajo"
RISK_MEDIO   = "Medio"
RISK_ALTO    = "Alto"
RISK_CRITICO = "Crítico"
RISK_NORMAL  = "Normal"

SEVERITY_LEVELS = [RISK_INFO, RISK_BAJO, RISK_MEDIO, RISK_ALTO, RISK_CRITICO]

RISK_COLORS = {
    RISK_INFO: {
        "pdf":     {"bg": (249, 250, 251), "text": (55, 65, 81)},
        "email":   {"bg": "#f9fafb", "border": "#e5e7eb", "text": "#374151"},
        "desc":    "Eventos informativos del sistema",
    },
    RISK_BAJO: {
        "pdf":     {"bg": (240, 253, 244), "text": (22, 101, 52)},
        "email":   {"bg": "#f0fdf4", "border": "#bbf7d0", "text": "#16a34a"},
        "desc":    "Valores normales de funcionamiento",
    },
    RISK_MEDIO: {
        "pdf":     {"bg": (255, 251, 235), "text": (146, 64, 14)},
        "email":   {"bg": "#fffbeb", "border": "#fde68a", "text": "#b45309"},
        "desc":    "Cerca del límite sugerido",
    },
    RISK_ALTO: {
        "pdf":     {"bg": (255, 247, 237), "text": (194, 65, 12)},
        "email":   {"bg": "#fef2f2", "border": "#fecaca", "text": "#dc2626"},
        "desc":    "Fuera de rango seguro",
    },
    RISK_CRITICO: {
        "pdf":     {"bg": (254, 242, 242), "text": (153, 27, 27)},
        "email":   {"bg": "#fef2f2", "border": "#fecaca", "text": "#dc2626"},
        "desc":    "Estado de peligro, acción inmediata",
    },
}

SEVERITY_DISPLAY_LEVELS = [
    (risk, v["pdf"]["bg"], v["pdf"]["text"], v["desc"])
    for risk, v in RISK_COLORS.items()
]

RISK_STYLES: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    risk: (v["pdf"]["bg"], v["pdf"]["text"])
    for risk, v in RISK_COLORS.items()
}

EMAIL_COLOR_PALETTE: dict[str, dict[str, str]] = {
    risk: v["email"]
    for risk, v in RISK_COLORS.items()
    if risk != RISK_INFO
}
EMAIL_FALLBACK_COLORS: dict[str, str] = {
    "bg": "#f5f5f5", "border": "#e0e0e0", "text": "#6b6b6b",
}

RISK_NAMES_ES = {
    RISK_CRITICO: "crítica",
    RISK_ALTO:    "alta",
    RISK_MEDIO:   "media",
    RISK_BAJO:    "baja",
    RISK_NORMAL:  "normal",
    RISK_INFO:    "informativa",
}

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

NO_RISK_VARS = ["position"]

ZERO_IS_CRITICAL_VARS = {"flow_rate", "pressure"}

BOOLEAN_VARS = {"motor_stuck"}

ENUM_VARS = {"door_status"}

ENUM_RISK_VALUES = {
    "door_status": {"open"},
}

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

_ELEVATOR_NUMERIC = [v for v in ELEVATOR_VARS if v not in NO_RISK_VARS and v not in BOOLEAN_VARS and v not in ENUM_VARS]

STATS_VARS = PUMP_VARS + _ELEVATOR_NUMERIC

PDF_STATS_VARS = PUMP_VARS + _ELEVATOR_NUMERIC

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
        "true":  "Sí",
        "false": "No",
        "1":     "Sí",
        "0":     "No",
    },
}

DEFAULT_THRESHOLDS = {
    "flow_rate":   {"direction": "lower",  "low": 8.0,  "medium": 5.0, "high": 2.0},
    "pressure":    {"direction": "range",  "low": 2.0,  "high": 8.0},
    "temperature": {"direction": "higher", "low": 70,   "medium": 85,  "high": 100},
    "vibration":   {"direction": "higher", "low": 4,    "medium": 7,   "high": 10},
    "tank_level":  {"direction": "lower",  "low": 30,   "medium": 15,  "high": 5},
    "speed":       {"direction": "higher", "low": 2.5,  "medium": 3.0, "high": 4.0},
    "load":        {"direction": "higher", "low": 600,  "medium": 800, "high": 900},
    "trip_count":  {"direction": "higher", "low": 10000,"medium": 20000,"high": 30000},
    "energy":      {"direction": "higher", "low": 8,    "medium": 12,  "high": 15},
    "voltage":     {"direction": "range",  "low": 200,  "high": 240},
    "current":     {"direction": "higher", "low": 30,   "medium": 40,  "high": 50},
}

RECOMMENDATION_THRESHOLDS = {
    "temperature": {"max_warn": 70,  "max_crit": 85},
    "flow_rate":   {"min_warn": 8.0, "min_crit": 5.0},
    "pressure":    {"min_warn": 2.0, "max_warn": 8.0},
    "vibration":   {"max_warn": 7},
    "tank_level":  {"min_warn": 30,  "min_crit": 20},
    "load":        {"max_warn": 800},
    "voltage":     {"range_warn": (200, 240)},
    "current":     {"max_warn": 45},
}

RECOMMENDATION_WARN_MSGS: dict[str, str] = {
    "temperature": "Temperatura elevada. Monitorear.",
    "flow_rate": "Caudal óptimo bajo. Verificar filtros.",
    "pressure": "Presión fuera de rango. Riesgo de fuga o bloqueo.",
    "vibration": "Vibración anormal. Verificar alineación.",
    "tank_level": "Nivel de tanque bajo.",
    "load": "Sobrecarga de elevador. Reducir carga.",
    "current": "Sobrecarga eléctrica.",
}

RECOMMENDATION_CRIT_MSGS: dict[str, str] = {
    "temperature": "Temperatura del motor muy alta. Verificar sistema de enfriamiento.",
    "flow_rate": "Caudal bajo. Verificar bomba.",
    "tank_level": "Nivel de tanque crítico. Relleno urgente.",
}

RECOMMENDATION_RANGE_MSG: str = "Inestabilidad eléctrica. Verificar suministro eléctrico."

RECOMMENDATION_MOTOR_STUCK_MSG: str = "Motor atascado. Mantenimiento urgente requerido."
RECOMMENDATION_DOOR_MSG_TEMPLATE: str = "Verificar puertas: {} intentos de cierre fallidos."
RECOMMENDATION_OK_MSG: str = "Todos los parámetros normales. Operación estable."
RECOMMENDATION_FALLBACK_ACTION_TEMPLATE: str = "Verificar el sensor {}. Programar inspección preventiva."

ACTIONS: dict[str, dict[str, str]] = {
    "flow_rate": {
        RISK_BAJO: "Caudal dentro del rango normal. Monitoreo rutinario activo.",
        RISK_MEDIO: "Caudal ligeramente bajo. Verifique posibles obstrucciones o filtros sucios.",
        RISK_ALTO: "Caudal significativamente bajo. Verifique posibles fugas o fallas parciales en la bomba.",
        RISK_CRITICO: "Caudal crítico bajo (flujo casi nulo). Parada preventiva de bomba activada. Inspeccione la tubería de succión y la bomba.",
    },
    "pressure": {
        RISK_BAJO: "Presión dentro del rango normal. Monitoreo rutinario activo.",
        RISK_ALTO: "Presión fuera del rango operativo seguro (2.0 - 8.0 bar). Verifique posibles fugas (presión baja) o bloqueos (presión alta).",
        RISK_CRITICO: "Presión en nivel crítico (flujo nulo o sobrepresión extrema). Detenga la bomba de inmediato y verifique la tubería.",
    },
    "temperature": {
        RISK_BAJO: "Temperatura normal. Ventilación adecuada.",
        RISK_MEDIO: "Temperatura moderadamente elevada. Verifique la ventilación de la sala de máquinas.",
        RISK_ALTO: "Temperatura alta del motor de bomba. Aumente la ventilación de la sala de máquinas.",
        RISK_CRITICO: "Temperatura crítica del motor. Riesgo de sobrecalentamiento y fusión. Apagado de emergencia y verificación del sistema de enfriamiento.",
    },
    "vibration": {
        RISK_BAJO: "Vibración normal. Alineación mecánica correcta.",
        RISK_MEDIO: "Vibración moderada. Verifique sujetadores mecánicos y estado de rodamientos.",
        RISK_ALTO: "Vibración por encima del estándar. Programe mantenimiento mecánico.",
        RISK_CRITICO: "Vibración mecánica severa. Desalineación grave o falla de rodamiento. Detenga el equipo inmediatamente.",
    },
    "tank_level": {
        RISK_BAJO: "Nivel de tanque bajo. Monitoree el reabastecimiento.",
        RISK_MEDIO: "Nivel de tanque en zona de precaución. Programe relleno próximamente.",
        RISK_ALTO: "Nivel de tanque alto. Monitoree el llenado automático.",
        RISK_CRITICO: "Nivel de tanque crítico. Riesgo de cavitación de bomba. Detenga succión y rellene el tanque urgentemente.",
    },
    "speed": {
        RISK_BAJO: "Velocidad de elevador normal.",
        RISK_MEDIO: "Velocidad moderadamente alta. Monitoree el variador de frecuencia.",
        RISK_ALTO: "Velocidad de elevador por encima del límite seguro. Programe inspección del VFD.",
        RISK_CRITICO: "Sobrepaso de velocidad crítico. Frenado de emergencia activado. Inspección de seguridad obligatoria.",
    },
    "load": {
        RISK_BAJO: "Carga de cabina normal.",
        RISK_MEDIO: "Carga de cabina moderada. Monitoree el comportamiento del motor.",
        RISK_ALTO: "Carga de cabina cerca del límite de diseño. Monitoree el comportamiento del motor.",
        RISK_CRITICO: "Sobrecarga de cabina de elevador. Retire el exceso de peso para reanudar operación.",
    },
    "energy": {
        RISK_BAJO: "Consumo de energía normal.",
        RISK_MEDIO: "Consumo de energía moderadamente alto. Verifique la eficiencia operativa.",
        RISK_ALTO: "Consumo de energía inusualmente alto. Monitoree la eficiencia.",
        RISK_CRITICO: "Pico de energía crítico. Posible cortocircuito o sobreesfuerzo del motor. Verifique protecciones eléctricas.",
    },
    "voltage": {
        RISK_BAJO: "Voltaje dentro del rango nominal (200-240 V).",
        RISK_MEDIO: "Desviación leve de voltaje. Verifique la estabilidad de la red eléctrica.",
        RISK_ALTO: "Inestabilidad de voltaje (fuera del rango 200 V - 240 V). Riesgo para componentes electrónicos.",
        RISK_CRITICO: "Fluctuación crítica de voltaje. Desconecte el equipo para evitar daños.",
    },
    "current": {
        RISK_BAJO: "Corriente del motor dentro del rango operativo.",
        RISK_MEDIO: "Corriente del motor moderadamente alta. Monitoree la temperatura del bobinado.",
        RISK_ALTO: "Corriente del motor por encima del límite recomendado. Verifique carga y estado del bobinado.",
        RISK_CRITICO: "Amperaje crítico (sobrecarga eléctrica). Apagado automático por protección activo.",
    },
    "motor_stuck": {
        RISK_CRITICO: "Eje del motor del elevador atascado/bloqueado. Detenga la cabina y realice liberación de emergencia de pasajeros.",
    },
    "trip_count": {
        RISK_BAJO: "Conteo de viajes dentro del rango normal.",
        RISK_MEDIO: "Conteo de viajes alto. Programe inspección del sistema de tracción próximamente.",
        RISK_ALTO: "Conteo de viajes alto. Verifique desgaste en componentes mecánicos del elevador.",
        RISK_CRITICO: "Conteo de viajes crítico. Inspección técnica obligatoria antes de continuar operación.",
    },
    "position": {
        RISK_BAJO: "Posición del elevador dentro del rango operativo normal.",
        RISK_MEDIO: "Posición del elevador en zona de precaución. Monitoree el desplazamiento.",
        RISK_ALTO: "Posición del elevador fuera del rango seguro. Verifique el sistema de límites.",
        RISK_CRITICO: "Posición crítica detectada. Detenga el elevador y verifique el sistema de guía.",
    },
    "door_status": {
        RISK_BAJO: "Estado de puerta normal.",
        RISK_MEDIO: "Comportamiento irregular de puerta. Monitoree ciclos de apertura y cierre.",
        RISK_ALTO: "Fallo de cierre de puerta. Verifique mecanismo de enclavamiento.",
        RISK_CRITICO: "Puerta sin respuesta. Detenga operación e inspeccione el sistema de puerta.",
    },
    "rationing": {
        RISK_CRITICO: "Caudal por debajo del mínimo admisible (racionamiento activo). Restrinja el consumo general.",
    },
    "auto_protection": {
        RISK_CRITICO: "Protección automática activada. Operación forzada / Estado seguro activado.",
    },
    "protection_pump": {
        RISK_INFO: "Protección para la bomba de agua finalizada. Operación normal restaurada.",
        RISK_BAJO: "Protección para la bomba de agua finalizada. Operación normal restaurada.",
    },
    "protection_elevator": {
        RISK_INFO: "Protección para el elevador finalizada. Operación normal restaurada.",
        RISK_BAJO: "Protección para el elevador finalizada. Operación normal restaurada.",
    },
    "fault_resolved_pump": {
        RISK_BAJO: "Falla en la bomba de agua resuelta. Operación normal restaurada.",
    },
    "fault_resolved_elevator": {
        RISK_BAJO: "Falla en el elevador resuelta. Operación normal restaurada.",
    },
}

SYSTEM_VARS = ["rationing", "auto_protection", "protection_pump", "protection_elevator", "fault_resolved_pump", "fault_resolved_elevator"]

ALERT_VARS = list(set(PUMP_VARS + ELEVATOR_VARS + SYSTEM_VARS))

PROTECTION_VARS = {
    "pump":     [v for v in PUMP_VARS if v != "tank_level"],
    "elevator": [v for v in ELEVATOR_VARS if v not in ("position", "trip_count", "door_status")],
}

SIM_TICK_INTERVAL = 1
MAX_CONSECUTIVE_FAILURES = 5

COOLDOWN_SECONDS: int = 300
MAX_PDF_EVENTS: int = 200
PAGE_SIZE: int = 15
SMTP_TIMEOUT: int = 15
API_NOTIFICATION_LIMIT: int = 50
PAYLOAD_HISTORY_SLICE: int = 200

RATIONING_THRESHOLD = 8.0

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

RISK_UNKNOWN = "Desconocido"

FAULT_NAMES_ES = {
    "dry_run":            "Sequía",
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

PUMP_FAULT_KEYS = ("dry_run", "blocked_discharge", "pipe_burst", "cavitation", "overheat", "power_surge", "power_outage")
ELEVATOR_FAULT_KEYS = ("motor_stuck", "door_blocked", "overspeed")

UNKNOWN_PERSON_NAME: str = "Sin nombre"
UNKNOWN_EMAIL_LABEL: str = "Sin correo"
