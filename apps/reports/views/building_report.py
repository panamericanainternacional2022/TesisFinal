import datetime as dt
import logging
from typing import Any

from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from apps.buildings.models import Building, MonitoringEquipment
from apps.core.auth_decorators import login_required
from apps.sensors.sensor_config import (
    RISK_BAJO, RISK_MEDIO, RISK_ALTO, RISK_CRITICO,
    SEVERITY_LEVELS, SEVERITY_DISPLAY_LEVELS, RISK_STYLES,
    PUMP_VARS, ELEVATOR_VARS, RATIONING_THRESHOLD,
)
from apps.alerts.models import Notification

from .shared import _pdf_font, draw_row
from .pdf_rendering import _create_report_pdf, render_logo, render_severity_legend

logger = logging.getLogger(__name__)

_CRITICAL_LEVELS = {RISK_ALTO, RISK_CRITICO}


def generate_building_report_bytes(edificio_id: int) -> tuple[bytes, str]:
    from apps.core.services.risk_service import classify_risk
    from apps.alerts.services.threshold_service import get_thresholds
    from apps.sensors.sensor_config import (
        VAR_NAMES, UNITS, STATS_VARS, ACTIONS, VALUE_DISPLAY_ES,
    )
    from apps.sensors.simulation.globals import simulators

    building = get_object_or_404(Building, id=edificio_id)
    pdf = _create_report_pdf("Reporte de estado del edificio")
    now = dt.datetime.now()
    sim = simulators.get(edificio_id)
    thresholds = get_thresholds()

    equipment = list(MonitoringEquipment.objects.filter(building_id=edificio_id))
    pump_status = None
    elevator_status = None
    equip_types = set()
    for eq in equipment:
        equip_types.add(eq.equipment_type)
        if eq.equipment_type == "bomba":
            pump_status = eq.status
        elif eq.equipment_type == "elevador":
            elevator_status = eq.status

    sensor_data = sim.sensor_data if sim else {}
    history = sim.history if sim else []

    stats = _compute_stats(history, STATS_VARS)

    relevant_vars = set()
    if "bomba" in equip_types:
        relevant_vars.update(PUMP_VARS)
    if "elevador" in equip_types:
        relevant_vars.update(ELEVATOR_VARS)

    _render_header(pdf, now, building, sim)
    _render_executive_summary(pdf, sensor_data, thresholds, relevant_vars, pump_status, elevator_status, equip_types)

    render_severity_legend(pdf)

    critical_items = _get_critical_items(sensor_data, thresholds, relevant_vars)
    if critical_items:
        _render_critical_section(pdf, critical_items, VAR_NAMES, UNITS, ACTIONS, VALUE_DISPLAY_ES)

    _render_current_readings(pdf, sensor_data, thresholds, relevant_vars, equip_types, VAR_NAMES, UNITS, ACTIONS, VALUE_DISPLAY_ES)

    _render_rationing_section(pdf, sensor_data)

    if stats:
        _render_stats_table(pdf, stats, relevant_vars, VAR_NAMES, UNITS)

    _render_alerts_section(pdf, edificio_id, now)

    _render_recommendations_section(pdf, sensor_data)

    _render_thresholds(pdf, thresholds, relevant_vars, VAR_NAMES, UNITS)

    filename = f"reporte_{building.name}_{now.strftime('%Y%m%d_%H%M%S')}.pdf"
    filename = "".join(c for c in filename if c.isalnum() or c in "._- ")

    pdf_raw = pdf.output()
    pdf_bytes = (
        bytes(pdf_raw)
        if isinstance(pdf_raw, (bytearray, memoryview))
        else pdf_raw.encode("utf-8")
        if isinstance(pdf_raw, str)
        else bytes(pdf_raw)
    )
    return pdf_bytes, filename


@login_required
def building_report_pdf_view(request: Any, edificio_id: int) -> HttpResponse:
    try:
        pdf_bytes, filename = generate_building_report_bytes(edificio_id)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
    except ImportError:
        return HttpResponse(
            "Error: fpdf2 no está instalado. Ejecute: pip install fpdf2",
            content_type="text/plain", status=500,
        )
    except Exception as e:
        logger.warning("Building report PDF failed: %s", e)
        return HttpResponse(
            f"Error generando PDF: {e}",
            content_type="text/plain", status=500,
        )


def _compute_stats(history: list, STATS_VARS: list) -> dict:
    stats = {}
    for var in STATS_VARS:
        vals = [
            r["value"]
            for r in history
            if r["variable"] == var
            and isinstance(r["value"], (int, float))
            and not isinstance(r["value"], bool)
        ]
        vals = vals[-500:]
        if vals:
            stats[var] = {
                "avg": sum(vals) / len(vals),
                "min": min(vals),
                "max": max(vals),
            }
    return stats


def _get_critical_items(sensor_data: dict, thresholds: dict, relevant_vars: set) -> list[dict]:
    from apps.core.services.risk_service import classify_risk
    items = []
    for var in sorted(relevant_vars):
        if var not in sensor_data:
            continue
        risk, _ = classify_risk(var, sensor_data[var], thresholds)
        if risk in _CRITICAL_LEVELS:
            items.append({"var": var, "value": sensor_data[var], "risk": risk})
    return items


def _render_header(pdf: Any, now: dt.datetime, building: Building, sim: Any) -> None:
    render_logo(pdf)
    _pdf_font(pdf, "B", 18)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 12, "Reporte de estado del edificio", ln=1, align="L")
    _pdf_font(pdf, "", 11)
    pdf.set_text_color(26, 26, 26)
    pdf.cell(0, 7, f"Generado: {now.strftime('%d/%m/%Y %H:%M:%S')}", ln=1)
    pdf.cell(0, 7, f"Edificio: {building.name}", ln=1)
    pdf.cell(0, 7, f"RIF: {building.rif}", ln=1)
    address = building.address[:80] + ("..." if len(building.address) > 80 else "")
    pdf.cell(0, 7, f"Direcci\u00f3n: {address}", ln=1)
    if sim:
        if sim.sim_paused:
            pdf.cell(0, 7, "Simulaci\u00f3n: PAUSADA", ln=1)
        pdf.cell(0, 7, f"Velocidad de simulaci\u00f3n: {sim.sim_speed:.1f}x", ln=1)
    pdf.ln(6)


def _render_executive_summary(pdf: Any, sensor_data: dict, thresholds: dict,
                               relevant_vars: set, pump_status, elevator_status,
                               equip_types: set) -> None:
    from apps.core.services.risk_service import classify_risk
    _pdf_font(pdf, "B", 13)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 9, "Resumen ejecutivo", ln=1)
    pdf.ln(2)

    counts = {rl: 0 for rl in SEVERITY_LEVELS}
    for var in relevant_vars:
        if var in sensor_data:
            risk, _ = classify_risk(var, sensor_data[var], thresholds)
            if risk in counts:
                counts[risk] += 1

    col_w = 38
    _pdf_font(pdf, "", 9)
    for risk, fill, text_c, _desc in SEVERITY_DISPLAY_LEVELS:
        cnt = counts.get(risk, 0)
        pdf.set_fill_color(*fill)
        pdf.set_text_color(*text_c)
        pdf.set_draw_color(10, 10, 10)
        pdf.cell(col_w, 6, f"  {risk}: {cnt}", 1, 0, "L", True)
    pdf.ln(8)

    _pdf_font(pdf, "", 10)
    pdf.set_text_color(26, 26, 26)
    if "bomba" in equip_types:
        status_str = pump_status.capitalize() if pump_status else "Desconocido"
        pdf.cell(0, 6, f"Bomba: {status_str}", ln=1)
    if "elevador" in equip_types:
        status_str = elevator_status.capitalize() if elevator_status else "Desconocido"
        pdf.cell(0, 6, f"Elevador: {status_str}", ln=1)
    pdf.ln(4)


def _render_critical_section(pdf: Any, critical_items: list[dict],
                              VAR_NAMES: dict, UNITS: dict, ACTIONS: dict,
                              VALUE_DISPLAY_ES: dict = None) -> None:
    if pdf.get_y() > 240:
        pdf.add_page()

    _pdf_font(pdf, "B", 13)
    pdf.set_text_color(153, 27, 27)
    pdf.cell(0, 9, "Sensores en estado Cr\u00edtico / Alto", ln=1)
    pdf.ln(2)

    col_widths = [42, 24, 18, 96]
    col_headers = ["Variable", "Valor", "Riesgo", "Acci\u00f3n recomendada"]
    col_aligns = ["L", "C", "C", "L"]

    _pdf_font(pdf, "B", 10)
    draw_row(pdf, col_widths, col_aligns, col_headers,
             fills=[(10, 10, 10)] * len(col_widths),
             colors=[(255, 255, 255)] * len(col_widths))

    _pdf_font(pdf, "", 9)
    pdf.set_draw_color(10, 10, 10)
    for item in critical_items:
        var = item["var"]
        val = item["value"]
        risk = item["risk"]
        val_str = _format_value(var, val, UNITS, VALUE_DISPLAY_ES)
        var_name = VAR_NAMES.get(var, var)
        action = ACTIONS.get(var, {}).get(risk, "")
        fill_c, text_c = RISK_STYLES.get(risk, ((255, 255, 255), (26, 26, 26)))

        row_data = [var_name, val_str, risk, action[:60]]
        fills = [None, None, fill_c, None]
        colors = [None, None, text_c, None]
        draw_row(pdf, col_widths, col_aligns, row_data, fills, colors)

    pdf.ln(6)


def _render_current_readings(pdf: Any, sensor_data: dict, thresholds: dict,
                              relevant_vars: set, equip_types: set,
                              VAR_NAMES: dict, UNITS: dict, ACTIONS: dict,
                              VALUE_DISPLAY_ES: dict = None) -> None:
    from apps.core.services.risk_service import classify_risk
    if pdf.get_y() > 230:
        pdf.add_page()

    _pdf_font(pdf, "B", 13)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 9, "Lecturas actuales de sensores", ln=1)
    pdf.ln(2)

    col_widths = [42, 24, 16, 98]
    col_headers = ["Variable", "Valor", "Riesgo", "Acci\u00f3n recomendada"]
    col_aligns = ["L", "C", "C", "L"]

    sections = []
    if "bomba" in equip_types:
        sections.append(("Bomba y El\u00e9ctricos", [v for v in PUMP_VARS if v in relevant_vars]))
    if "elevador" in equip_types:
        sections.append(("Elevador y Motor", [v for v in ELEVATOR_VARS if v in relevant_vars]))

    for section_name, vars_list in sections:
        if pdf.get_y() > 240:
            pdf.add_page()

        _pdf_font(pdf, "B", 10)
        pdf.set_text_color(55, 65, 81)
        pdf.cell(0, 7, section_name, ln=1)
        pdf.ln(1)

        _pdf_font(pdf, "B", 10)
        draw_row(pdf, col_widths, col_aligns, col_headers,
                 fills=[(10, 10, 10)] * len(col_widths),
                 colors=[(255, 255, 255)] * len(col_widths))

        _pdf_font(pdf, "", 9)
        pdf.set_draw_color(10, 10, 10)
        for var in vars_list:
            if var not in sensor_data:
                continue
            val = sensor_data[var]
            risk, _ = classify_risk(var, val, thresholds)
            val_str = _format_value(var, val, UNITS, VALUE_DISPLAY_ES)
            var_name = VAR_NAMES.get(var, var)
            action = ACTIONS.get(var, {}).get(risk, "")[:55]
            fill_c, text_c = RISK_STYLES.get(risk, ((255, 255, 255), (26, 26, 26)))

            draw_row(pdf, col_widths, col_aligns,
                     [var_name, val_str, risk, action],
                     [None, None, fill_c, None],
                     [None, None, text_c, None])

        pdf.ln(4)


def _render_rationing_section(pdf: Any, sensor_data: dict) -> None:
    if pdf.get_y() > 250:
        pdf.add_page()

    _pdf_font(pdf, "B", 13)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 9, "Estado general de racionamiento", ln=1)
    pdf.ln(2)

    flow = sensor_data.get("flow_rate")
    if flow is None:
        _pdf_font(pdf, "", 10)
        pdf.set_text_color(95, 95, 95)
        pdf.cell(0, 7, "Sin datos de caudal disponibles.", ln=1)
        pdf.ln(4)
        return

    _pdf_font(pdf, "", 10)
    pdf.set_text_color(26, 26, 26)
    pdf.cell(0, 7, f"Caudal actual: {flow:.1f} L/s", ln=1)
    pdf.cell(0, 7, f"Umbral de racionamiento: {RATIONING_THRESHOLD} L/s", ln=1)
    pdf.ln(2)

    in_rationing = flow < RATIONING_THRESHOLD
    if in_rationing:
        pdf.set_fill_color(254, 242, 242)
        pdf.set_text_color(153, 27, 27)
        label = "ACTIVO \u2014 El caudal est\u00e1 por debajo del umbral de racionamiento."
    else:
        pdf.set_fill_color(240, 253, 244)
        pdf.set_text_color(22, 101, 52)
        label = "NORMAL \u2014 El caudal se encuentra dentro del rango aceptable."

    _pdf_font(pdf, "B", 10)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(0, 8, f"  {label}", 1, 1, "L", True)
    pdf.ln(4)


def _render_alerts_section(pdf: Any, edificio_id: int, now: dt.datetime) -> None:
    if pdf.get_y() > 230:
        pdf.add_page()

    _pdf_font(pdf, "B", 13)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 9, "Alertas detectadas en el per\u00edodo", ln=1)
    pdf.ln(2)

    since = now - dt.timedelta(hours=24)
    notifications = Notification.objects.filter(
        monitoring_equipment__building_id=edificio_id,
        date__gte=since,
    ).order_by("-date")

    total = notifications.count()
    _pdf_font(pdf, "", 10)
    pdf.set_text_color(26, 26, 26)
    pdf.cell(0, 7, f"\u00daltimas 24 horas: {total} alerta(s) registrada(s)", ln=1)
    pdf.ln(3)

    counts: dict[str, int] = {}
    for n in notifications:
        msg = n.message
        if isinstance(msg, dict):
            risk = msg.get("risk", "")
        else:
            risk = ""
        counts[risk] = counts.get(risk, 0) + 1

    if not counts:
        pdf.set_text_color(95, 95, 95)
        _pdf_font(pdf, "", 10)
        pdf.cell(0, 7, "No se registraron alertas en las \u00faltimas 24 horas.", ln=1)
        pdf.ln(4)
        return

    col_widths = [38, 38]
    col_headers = ["Severidad", "Cantidad"]
    col_aligns = ["L", "C"]

    _pdf_font(pdf, "B", 10)
    draw_row(pdf, col_widths, col_aligns, col_headers,
             fills=[(10, 10, 10)] * len(col_widths),
             colors=[(255, 255, 255)] * len(col_widths))

    _pdf_font(pdf, "", 9)
    pdf.set_draw_color(10, 10, 10)
    for risk_lvl, fill, text_c, _desc in SEVERITY_DISPLAY_LEVELS:
        cnt = counts.get(risk_lvl, 0)
        if cnt == 0:
            continue
        pdf.set_fill_color(*fill)
        pdf.set_text_color(*text_c)
        row_data = [risk_lvl, str(cnt)]
        row_fills = [fill, None]
        row_colors = [text_c, None]
        draw_row(pdf, col_widths, col_aligns, row_data, row_fills, row_colors)

    pdf.ln(6)


def _render_recommendations_section(pdf: Any, sensor_data: dict) -> None:
    from apps.alerts.services.recommendation_engine import generate_recommendations
    if pdf.get_y() > 240:
        pdf.add_page()

    _pdf_font(pdf, "B", 13)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 9, "Diagn\u00f3stico y recomendaciones", ln=1)
    pdf.ln(2)

    recs = generate_recommendations(sensor_data)

    _pdf_font(pdf, "", 10)
    pdf.set_draw_color(10, 10, 10)
    for i, rec in enumerate(recs, 1):
        if pdf.get_y() > 265:
            pdf.add_page()
        pdf.set_text_color(26, 26, 26)
        pdf.cell(6, 7, f"{i}.", 0, 0, "L")
        pdf.multi_cell(174, 7, rec)
        pdf.ln(1)

    pdf.ln(4)


def _render_stats_table(pdf: Any, stats: dict, relevant_vars: set,
                         VAR_NAMES: dict, UNITS: dict) -> None:
    if pdf.get_y() > 230:
        pdf.add_page()

    _pdf_font(pdf, "B", 13)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 9, "Estad\u00edsticas \u00faltima hora (promedio, m\u00ednimo, m\u00e1ximo)", ln=1)
    pdf.ln(2)

    col_widths = [42, 28, 28, 28]
    col_headers = ["Variable", "Promedio", "M\u00ednimo", "M\u00e1ximo"]
    col_aligns = ["L", "C", "C", "C"]

    _pdf_font(pdf, "B", 10)
    draw_row(pdf, col_widths, col_aligns, col_headers,
             fills=[(10, 10, 10)] * len(col_widths),
             colors=[(255, 255, 255)] * len(col_widths))

    _pdf_font(pdf, "", 9)
    pdf.set_draw_color(10, 10, 10)
    for var in sorted(relevant_vars):
        if var not in stats:
            continue
        s = stats[var]
        unit = UNITS.get(var, "")
        var_name = VAR_NAMES.get(var, var)
        draw_row(pdf, col_widths, col_aligns, [
            var_name,
            f"{s['avg']:.1f} {unit}".strip(),
            f"{s['min']:.1f} {unit}".strip(),
            f"{s['max']:.1f} {unit}".strip(),
        ])

    pdf.ln(6)


def _render_thresholds(pdf: Any, thresholds: dict, relevant_vars: set,
                        VAR_NAMES: dict, UNITS: dict) -> None:
    if pdf.get_y() > 230:
        pdf.add_page()

    _pdf_font(pdf, "B", 13)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 9, "Umbrales de riesgo configurados", ln=1)
    pdf.ln(2)

    col_widths = [42, 22, 22, 22, 22, 30]
    col_headers = ["Variable", "Direcci\u00f3n", "Bajo", "Medio", "Alto", "Unidad"]
    col_aligns = ["L", "C", "C", "C", "C", "C"]

    _pdf_font(pdf, "B", 10)
    draw_row(pdf, col_widths, col_aligns, col_headers,
             fills=[(10, 10, 10)] * len(col_widths),
             colors=[(255, 255, 255)] * len(col_widths))

    _pdf_font(pdf, "", 9)
    pdf.set_draw_color(10, 10, 10)
    dir_labels = {"higher": "> mayor", "lower": "< menor", "range": "rango"}
    for var in sorted(relevant_vars):
        if var not in thresholds:
            continue
        cfg = thresholds[var]
        unit = UNITS.get(var, "")
        var_name = VAR_NAMES.get(var, var)
        d = cfg.get("direction", "higher")
        if d == "range":
            draw_row(pdf, col_widths, col_aligns, [
                var_name, dir_labels.get(d, d),
                f"{cfg['low']}", "\u2014", f"{cfg['high']}", unit,
            ])
        else:
            low = cfg.get("low", 0)
            med = cfg.get("medium", 0)
            high = cfg.get("high", 0)
            draw_row(pdf, col_widths, col_aligns, [
                var_name, dir_labels.get(d, d),
                str(low), str(med), str(high), unit,
            ])

    pdf.ln(4)


def _format_value(var: str, value, units: dict, value_display_map: dict = None) -> str:
    if value_display_map and var in value_display_map:
        val_str = str(value).lower()
        return value_display_map[var].get(val_str, str(value))
    if isinstance(value, bool):
        return "S\u00ed" if value else "No"
    unit = units.get(var, "")
    display = f"{value:.1f}" if isinstance(value, float) else str(value)
    if unit:
        return f"{display} {unit}"
    return display
