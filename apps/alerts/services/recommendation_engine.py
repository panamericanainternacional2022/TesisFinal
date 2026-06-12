from typing import Dict, Any, List

from apps.sensors.sensor_config import VAR_NAMES


ACTIONS: Dict[str, Dict[str, str]] = {
    "flow_rate": {
        "Bajo": "Flow rate within normal range. Routine monitoring active.",
        "Medio": "Moderate flow rate. Check for minor leaks or line restrictions.",
        "Alto": "Elevated water flow. Monitor relief valves and possible leaks.",
        "Crítico": "Critical flow rate (total interruption or severe excess). Preventive pump shutdown activated. Inspect main pipeline.",
    },
    "pressure": {
        "Bajo": "Pressure within operating range. No action required.",
        "Medio": "Pressure in caution zone. Check pressure regulator preventively.",
        "Alto": "Pressure above recommended limit. Verify pressure regulator and gauges.",
        "Crítico": "Critical pressure. Imminent risk of pipe rupture. Turn off pump and release pressure.",
    },
    "temperature": {
        "Bajo": "Normal temperature. Adequate ventilation.",
        "Medio": "Moderately elevated temperature. Check machine room ventilation.",
        "Alto": "High pump motor temperature. Increase machine room ventilation.",
        "Crítico": "Critical motor temperature. Risk of overheating and melting. Emergency shutdown and cooling system check.",
    },
    "vibration": {
        "Bajo": "Normal vibration. Correct mechanical alignment.",
        "Medio": "Moderate vibration. Check mechanical fasteners and bearing condition.",
        "Alto": "Vibration above standard. Schedule mechanical maintenance.",
        "Crítico": "Severe mechanical vibration. Severe misalignment or bearing failure. Shut down equipment immediately.",
    },
    "tank_level": {
        "Bajo": "Low tank level. Monitor resupply.",
        "Medio": "Tank level in caution zone. Schedule refill soon.",
        "Alto": "High tank level. Monitor automatic filling.",
        "Crítico": "Critical tank level. Risk of pump cavitation. Stop suction and refill tank urgently.",
    },
    "speed": {
        "Bajo": "Normal elevator speed.",
        "Medio": "Moderately high speed. Monitor variable frequency drive.",
        "Alto": "Elevator speed above safe travel limit. Schedule VFD inspection.",
        "Crítico": "Critical overspeed. Emergency braking activated. Mandatory safety inspection.",
    },
    "load": {
        "Bajo": "Normal cabin load.",
        "Medio": "Moderate cabin load. Monitor motor behavior.",
        "Alto": "Cabin load near design limit. Monitor motor behavior.",
        "Crítico": "Elevator cabin overload. Remove excess weight to resume operation.",
    },
    "energy": {
        "Bajo": "Normal energy consumption.",
        "Medio": "Moderately high energy consumption. Check operational efficiency.",
        "Alto": "Unusually high energy consumption. Monitor efficiency.",
        "Crítico": "Critical energy spike. Possible short circuit or motor overexertion. Check electrical protections.",
    },
    "voltage": {
        "Bajo": "Voltage within nominal range (200-240 V).",
        "Medio": "Slight voltage deviation. Check electrical grid stability.",
        "Alto": "Voltage instability (outside 200 V - 240 V range). Risk to electronic components.",
        "Crítico": "Critical electrical voltage fluctuation. Disconnect equipment to prevent damage.",
    },
    "current": {
        "Bajo": "Motor current within operating range.",
        "Medio": "Moderately high motor current. Monitor winding temperature.",
        "Alto": "Motor current above recommended limit. Check load and winding condition.",
        "Crítico": "Critical amperage (electrical overload). Automatic protection shutdown active.",
    },
    "motor_stuck": {
        "Crítico": "Elevator motor shaft stuck/blocked. Stop cabin and perform emergency passenger release.",
    },
    "trip_count": {
        "Bajo": "Trip count within normal range.",
        "Medio": "High trip count. Schedule traction system inspection soon.",
        "Alto": "High trip count. Check wear on elevator mechanical components.",
        "Crítico": "Critical trip count. Mandatory technical inspection before continuing operation.",
    },
    "position": {
        "Bajo": "Elevator position within normal operating range.",
        "Medio": "Elevator position in caution zone. Monitor displacement.",
        "Alto": "Elevator position outside safe range. Check limit system.",
        "Crítico": "Critical position detected. Stop elevator and check guide system.",
    },
    "door_status": {
        "Bajo": "Normal door status.",
        "Medio": "Irregular door behavior. Monitor opening and closing cycles.",
        "Alto": "Door closing failure. Check interlocking mechanism.",
        "Crítico": "Door unresponsive. Stop operation and inspect door system.",
    },
    "rationing": {
        "Crítico": "Flow rate below minimum admissible (rationing active). Restrict general consumption.",
    },
}


def generate_recommendations(
    data: Dict[str, Any],
    stats: Any = None,
    door_close_attempts: int = 0,
) -> List[str]:
    recs: List[str] = []
    if data.get("temperature", 0) > 85:
        recs.append("Very high motor temperature (>85°C). Check cooling system.")
    elif data.get("temperature", 0) > 70:
        recs.append("Elevated temperature. Monitor.")
    if data.get("flow_rate", 0) < 10:
        recs.append("Low flow rate (<10 L/s). Check pump.")
    elif data.get("flow_rate", 0) < 20:
        recs.append("Low optimal flow rate. Check filters.")
    if data.get("pressure", 0) > 8:
        recs.append("Excessive pressure (>8 bar). Leak risk.")
    if data.get("vibration", 0) > 7:
        recs.append("Abnormal vibration (>7 mm/s). Verify alignment.")
    if data.get("tank_level", 100) < 20:
        recs.append("Critical tank level (<20%). Urgent refill.")
    elif data.get("tank_level", 100) < 30:
        recs.append("Low tank level.")
    if data.get("load", 0) > 800:
        recs.append("Elevator overload (>800 kg). Reduce load.")
    voltage = data.get("voltage", 220)
    if voltage < 200 or voltage > 240:
        recs.append("Electrical instability. Check power supply.")
    if data.get("current", 0) > 45:
        recs.append("Electrical overload (current >45A).")
    if data.get("motor_stuck", False):
        recs.append("MOTOR STUCK. Urgent maintenance required.")
    if door_close_attempts >= 3:
        recs.append(f"Check doors: {door_close_attempts} failed closing attempts.")
    if not recs:
        recs.append("All parameters normal. Stable operation.")
    return recs[:5]


def get_professional_action(variable: str, risk_level: str, value: Any) -> str:
    var_actions = ACTIONS.get(variable, {})
    var_display = VAR_NAMES.get(variable, variable.replace("_", " "))
    return var_actions.get(risk_level, f"Check the {var_display.lower()} sensor. Schedule preventive inspection.")
