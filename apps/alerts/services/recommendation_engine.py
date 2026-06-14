from typing import Dict, Any, List

from apps.sensors.sensor_config import (
    VAR_NAMES, UNITS, RISK_BAJO, RISK_MEDIO, RISK_ALTO, RISK_CRITICO,
    RECOMMENDATION_THRESHOLDS,
)
from apps.sensors.simulation.constants import MAX_DOOR_CLOSE_ATTEMPTS


ACTIONS: Dict[str, Dict[str, str]] = {
    "flow_rate": {
        RISK_BAJO: "Flow rate within normal range. Routine monitoring active.",
        RISK_MEDIO: "Moderate flow rate. Check for minor leaks or line restrictions.",
        RISK_ALTO: "Elevated water flow. Monitor relief valves and possible leaks.",
        RISK_CRITICO: "Critical flow rate (total interruption or severe excess). Preventive pump shutdown activated. Inspect main pipeline.",
    },
    "pressure": {
        RISK_BAJO: "Pressure within operating range. No action required.",
        RISK_MEDIO: "Pressure in caution zone. Check pressure regulator preventively.",
        RISK_ALTO: "Pressure above recommended limit. Verify pressure regulator and gauges.",
        RISK_CRITICO: "Critical pressure. Imminent risk of pipe rupture. Turn off pump and release pressure.",
    },
    "temperature": {
        RISK_BAJO: "Normal temperature. Adequate ventilation.",
        RISK_MEDIO: "Moderately elevated temperature. Check machine room ventilation.",
        RISK_ALTO: "High pump motor temperature. Increase machine room ventilation.",
        RISK_CRITICO: "Critical motor temperature. Risk of overheating and melting. Emergency shutdown and cooling system check.",
    },
    "vibration": {
        RISK_BAJO: "Normal vibration. Correct mechanical alignment.",
        RISK_MEDIO: "Moderate vibration. Check mechanical fasteners and bearing condition.",
        RISK_ALTO: "Vibration above standard. Schedule mechanical maintenance.",
        RISK_CRITICO: "Severe mechanical vibration. Severe misalignment or bearing failure. Shut down equipment immediately.",
    },
    "tank_level": {
        RISK_BAJO: "Low tank level. Monitor resupply.",
        RISK_MEDIO: "Tank level in caution zone. Schedule refill soon.",
        RISK_ALTO: "High tank level. Monitor automatic filling.",
        RISK_CRITICO: "Critical tank level. Risk of pump cavitation. Stop suction and refill tank urgently.",
    },
    "speed": {
        RISK_BAJO: "Normal elevator speed.",
        RISK_MEDIO: "Moderately high speed. Monitor variable frequency drive.",
        RISK_ALTO: "Elevator speed above safe travel limit. Schedule VFD inspection.",
        RISK_CRITICO: "Critical overspeed. Emergency braking activated. Mandatory safety inspection.",
    },
    "load": {
        RISK_BAJO: "Normal cabin load.",
        RISK_MEDIO: "Moderate cabin load. Monitor motor behavior.",
        RISK_ALTO: "Cabin load near design limit. Monitor motor behavior.",
        RISK_CRITICO: "Elevator cabin overload. Remove excess weight to resume operation.",
    },
    "energy": {
        RISK_BAJO: "Normal energy consumption.",
        RISK_MEDIO: "Moderately high energy consumption. Check operational efficiency.",
        RISK_ALTO: "Unusually high energy consumption. Monitor efficiency.",
        RISK_CRITICO: "Critical energy spike. Possible short circuit or motor overexertion. Check electrical protections.",
    },
    "voltage": {
        RISK_BAJO: "Voltage within nominal range (200-240 V).",
        RISK_MEDIO: "Slight voltage deviation. Check electrical grid stability.",
        RISK_ALTO: "Voltage instability (outside 200 V - 240 V range). Risk to electronic components.",
        RISK_CRITICO: "Critical electrical voltage fluctuation. Disconnect equipment to prevent damage.",
    },
    "current": {
        RISK_BAJO: "Motor current within operating range.",
        RISK_MEDIO: "Moderately high motor current. Monitor winding temperature.",
        RISK_ALTO: "Motor current above recommended limit. Check load and winding condition.",
        RISK_CRITICO: "Critical amperage (electrical overload). Automatic protection shutdown active.",
    },
    "motor_stuck": {
        RISK_CRITICO: "Elevator motor shaft stuck/blocked. Stop cabin and perform emergency passenger release.",
    },
    "trip_count": {
        RISK_BAJO: "Trip count within normal range.",
        RISK_MEDIO: "High trip count. Schedule traction system inspection soon.",
        RISK_ALTO: "High trip count. Check wear on elevator mechanical components.",
        RISK_CRITICO: "Critical trip count. Mandatory technical inspection before continuing operation.",
    },
    "position": {
        RISK_BAJO: "Elevator position within normal operating range.",
        RISK_MEDIO: "Elevator position in caution zone. Monitor displacement.",
        RISK_ALTO: "Elevator position outside safe range. Check limit system.",
        RISK_CRITICO: "Critical position detected. Stop elevator and check guide system.",
    },
    "door_status": {
        RISK_BAJO: "Normal door status.",
        RISK_MEDIO: "Irregular door behavior. Monitor opening and closing cycles.",
        RISK_ALTO: "Door closing failure. Check interlocking mechanism.",
        RISK_CRITICO: "Door unresponsive. Stop operation and inspect door system.",
    },
    "rationing": {
        RISK_CRITICO: "Flow rate below minimum admissible (rationing active). Restrict general consumption.",
    },
}

# ─── Mensajes de alerta temprana (usados por generate_recommendations) ──
_WARN_MSGS: Dict[str, str] = {
    "temperature": "Elevated temperature. Monitor.",
    "flow_rate": "Low optimal flow rate. Check filters.",
    "pressure": "Excessive pressure (>8 bar). Leak risk.",
    "vibration": "Abnormal vibration (>7 mm/s). Verify alignment.",
    "tank_level": "Low tank level.",
    "load": "Elevator overload (>800 kg). Reduce load.",
    "current": "Electrical overload (current >45A).",
}

_CRIT_MSGS: Dict[str, str] = {
    "temperature": "Very high motor temperature (>85°C). Check cooling system.",
    "flow_rate": "Low flow rate (<10 L/s). Check pump.",
    "tank_level": "Critical tank level (<20%). Urgent refill.",
}

_RANGE_MSG: str = "Electrical instability. Check power supply."


def generate_recommendations(
    data: Dict[str, Any],
    stats: Any = None,
    door_close_attempts: int = 0,
) -> List[str]:
    recs: List[str] = []

    for var, cfg in RECOMMENDATION_THRESHOLDS.items():
        value = data.get(var)
        if value is None:
            continue

        if "max_crit" in cfg and value > cfg["max_crit"]:
            recs.append(_CRIT_MSGS.get(var, ""))
        elif "max_warn" in cfg and value > cfg["max_warn"]:
            recs.append(_WARN_MSGS.get(var, ""))
        elif "min_crit" in cfg and value < cfg["min_crit"]:
            recs.append(_CRIT_MSGS.get(var, ""))
        elif "min_warn" in cfg and value < cfg["min_warn"]:
            recs.append(_WARN_MSGS.get(var, ""))
        elif "range_warn" in cfg:
            lo, hi = cfg["range_warn"]
            if value < lo or value > hi:
                recs.append(_RANGE_MSG)

    if data.get("motor_stuck", False):
        recs.append("MOTOR STUCK. Urgent maintenance required.")
    if door_close_attempts >= MAX_DOOR_CLOSE_ATTEMPTS:
        recs.append(f"Check doors: {door_close_attempts} failed closing attempts.")
    if not recs:
        recs.append("All parameters normal. Stable operation.")
    return recs[:5]


def get_professional_action(variable: str, risk_level: str, value: Any) -> str:
    var_actions = ACTIONS.get(variable, {})
    var_display = VAR_NAMES.get(variable, variable.replace("_", " "))
    return var_actions.get(risk_level, f"Check the {var_display.lower()} sensor. Schedule preventive inspection.")
