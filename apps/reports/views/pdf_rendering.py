import datetime as dt
from typing import Any

from .shared import (
    MAX_PDF_EVENTS,
    RISK_STYLES,
    SEVERITY_DISPLAY_LEVELS,
    _pdf_font,
    draw_row,
)


def render_header(pdf: Any, now: dt.datetime, building_name: str, severity: str, variable: str, range_label: str, total: int) -> None:
    _pdf_font(pdf, "B", 18)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 12, "Historial de Eventos ", ln=1, align="L")
    _pdf_font(pdf, "B", 11)
    pdf.set_text_color(95, 95, 95)
    pdf.cell(0, 8, "SISTEMA DE TELEMETRIA Y CONTROL", ln=1, align="L")
    pdf.ln(5)

    _pdf_font(pdf, "", 9)
    pdf.set_text_color(26, 26, 26)
    pdf.cell(0, 6, f"Generado: {now.strftime('%d/%m/%Y %H:%M:%S')}", ln=1)
    pdf.cell(0, 6, f"Edificio: {building_name}", ln=1)
    pdf.cell(0, 6, f"Severidad: {severity if severity else 'Todas'}", ln=1)
    pdf.cell(0, 6, f"Variable: {variable if variable else 'Todas'}", ln=1)
    pdf.cell(0, 6, f"Rango: {range_label}", ln=1)
    pdf.cell(0, 6, f"Total de eventos: {total}", ln=1)
    pdf.ln(8)


def render_severity_legend(pdf: Any) -> None:
    _pdf_font(pdf, "B", 10)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 7, "LEYENDA DE SEVERIDADES", ln=1)
    pdf.ln(1)

    _pdf_font(pdf, "", 8)
    for lbl, fill, text_c, desc in SEVERITY_DISPLAY_LEVELS:
        pdf.set_fill_color(*fill)
        pdf.set_text_color(*text_c)
        pdf.set_draw_color(10, 10, 10)
        pdf.cell(28, 6, f"  {lbl}", 1, 0, "L", True)
        pdf.set_text_color(95, 95, 95)
        pdf.cell(162, 6, f" {desc}", 1, 1, "L")
    pdf.ln(8)


def get_column_config(show_all_buildings: bool) -> tuple[list[int], list[str], list[str]]:
    if show_all_buildings:
        return (
            [26, 26, 20, 30, 20, 68],
            ["Fecha / Hora", "Edificio", "Severidad", "Variable", "Valor", "Accion recomendada"],
            ["L", "L", "C", "L", "C", "L"],
        )
    return (
        [38, 26, 40, 24, 62],
        ["Fecha / Hora", "Severidad", "Variable", "Valor", "Accion recomendada"],
        ["L", "C", "L", "C", "L"],
    )


def render_table_header(pdf: Any, column_widths: list[int], column_aligns: list[str], column_headers: list[str]) -> None:
    _pdf_font(pdf, "B", 8)
    draw_row(
        pdf,
        column_widths,
        column_aligns,
        column_headers,
        fills=[(10, 10, 10)] * len(column_widths),
        colors=[(255, 255, 255)] * len(column_widths),
    )


def render_event_rows(pdf: Any, parsed_list: list[Any], column_widths: list[int], column_aligns: list[str], show_all_buildings: bool) -> None:
    _pdf_font(pdf, "", 7)
    pdf.set_draw_color(10, 10, 10)

    if len(parsed_list) > MAX_PDF_EVENTS:
        _pdf_font(pdf, "I", 8)
        pdf.set_text_color(194, 65, 12)
        pdf.cell(0, 6, f"Mostrando los primeros {MAX_PDF_EVENTS} de {len(parsed_list)} eventos totales.", ln=1)
        pdf.ln(2)

    for notif in parsed_list[:MAX_PDF_EVENTS]:
        risk = notif.parsed_data.get("risk", "")
        fill_c, text_c = RISK_STYLES.get(risk, ((255, 255, 255), (26, 26, 26)))

        date_str = notif.date.strftime("%d/%m/%Y %H:%M") if notif.date else ""
        variable_str = notif.parsed_data.get("variable", "")
        value_str = notif.parsed_data.get("value", "")
        if value_str and value_str.lower() not in ("true", "false", "none", ""):
            unit = notif.parsed_data.get("unit", "")
            value_str = f"{value_str} {unit}".strip()
        action_str = notif.parsed_data.get("action", "")

        if show_all_buildings:
            building_row = notif.monitoring_equipment.building.name if (
                notif.monitoring_equipment and notif.monitoring_equipment.building
            ) else "N/A"
            row_data = [date_str, building_row, risk, variable_str, value_str, action_str]
            cell_fills = [None, None, fill_c, None, None, None]
            cell_colors = [None, None, text_c, None, None, None]
        else:
            row_data = [date_str, risk, variable_str, value_str, action_str]
            cell_fills = [None, fill_c, None, None, None]
            cell_colors = [None, text_c, None, None, None]

        draw_row(pdf, column_widths, column_aligns, row_data, cell_fills, cell_colors)
