import datetime as dt
from typing import Any

from django.http import HttpResponse

from .shared import (
    MAX_PDF_EVENTS,
    RISK_STYLES,
    SEVERITY_DISPLAY_LEVELS,
    _pdf_font,
    draw_row,
)
from apps.sensors.sensor_config import RISK_INFO


def render_logo(pdf: Any) -> None:
    _pdf_font(pdf, "B", 28)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 16, "INES", ln=1, align="L")
    _pdf_font(pdf, "", 10)
    pdf.set_text_color(95, 95, 95)
    pdf.cell(0, 6, "Sistema inteligente de automatización", ln=1, align="L")
    pdf.ln(2)
    pdf.set_draw_color(10, 10, 10)
    pdf.set_line_width(0.8)
    y = pdf.get_y()
    pdf.line(10, y, 200, y)
    pdf.ln(6)


def render_header(pdf: Any, now: dt.datetime, building_name: str, severity: str, variable: str, range_label: str, total: int, date_from: str = "", date_to: str = "") -> None:
    render_logo(pdf)
    _pdf_font(pdf, "B", 18)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 12, "Historial de eventos", ln=1, align="L")
    _pdf_font(pdf, "", 11)
    pdf.set_text_color(26, 26, 26)
    pdf.cell(0, 7, f"Generado: {now.strftime('%d/%m/%Y %H:%M:%S')}", ln=1)
    pdf.cell(0, 7, f"Edificio: {building_name}", ln=1)
    pdf.cell(0, 7, f"Severidad: {severity if severity else 'Todas'}", ln=1)
    pdf.cell(0, 7, f"Variable: {variable if variable else 'Todas'}", ln=1)
    pdf.cell(0, 7, f"Rango: {range_label}", ln=1)
    if date_from and date_to:
        pdf.cell(0, 7, f"Desde: {date_from}  Hasta: {date_to}", ln=1)
    pdf.cell(0, 7, f"Total de eventos: {total}", ln=1)
    pdf.ln(8)


def render_stats_summary(pdf: Any, parsed_list: list[Any]) -> None:
    from apps.sensors.sensor_config import SEVERITY_LEVELS
    stats: dict[str, int] = {k: 0 for k in SEVERITY_LEVELS}
    for n in parsed_list:
        risk = n.parsed_data.get("risk", "")
        if risk in stats:
            stats[risk] += 1

    _pdf_font(pdf, "B", 11)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 8, "Resumen por severidad", ln=1)
    pdf.ln(1)

    col_w = 38
    _pdf_font(pdf, "", 9)
    for lbl, fill, text_c, _desc in SEVERITY_DISPLAY_LEVELS:
        key = RISK_INFO if lbl == "Informativo" else lbl
        count = stats.get(key, 0)
        pdf.set_fill_color(*fill)
        pdf.set_text_color(*text_c)
        pdf.set_draw_color(10, 10, 10)
        pdf.cell(col_w, 6, f"  {lbl}: {count}", 1, 0, "L", True)
    pdf.ln(8)


def render_severity_legend(pdf: Any) -> None:
    _pdf_font(pdf, "B", 11)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 8, "Leyenda de severidades", ln=1)
    pdf.ln(1)

    _pdf_font(pdf, "", 10)
    for lbl, fill, text_c, desc in SEVERITY_DISPLAY_LEVELS:
        pdf.set_fill_color(*fill)
        pdf.set_text_color(*text_c)
        pdf.set_draw_color(10, 10, 10)
        pdf.cell(28, 6, f"  {lbl}", 1, 0, "L", True)
        pdf.set_text_color(95, 95, 95)
        pdf.cell(162, 6, f" {desc}", 1, 1, "L")
    pdf.ln(8)


def get_column_config() -> tuple[list[int], list[str], list[str]]:
    return (
        [28, 22, 18, 30, 18, 74],
        ["Fecha y hora", "Equipo", "Severidad", "Variable", "Valor", "Acción recomendada"],
        ["L", "L", "C", "L", "C", "L"],
    )


def render_table_header(pdf: Any, column_widths: list[int], column_aligns: list[str], column_headers: list[str]) -> None:
    _pdf_font(pdf, "B", 10)
    draw_row(
        pdf,
        column_widths,
        column_aligns,
        column_headers,
        fills=[(10, 10, 10)] * len(column_widths),
        colors=[(255, 255, 255)] * len(column_widths),
    )


def _create_report_pdf(title: str) -> Any:
    from fpdf import FPDF

    class _ReportPDF(FPDF):
        _title = title

        def header(self) -> None:
            if self.page_no() == 1:
                self.set_fill_color(10, 10, 10)
                self.rect(10, 10, 190, 2, "F")
                self.ln(5)
            else:
                _pdf_font(self, "I", 9)
                self.set_text_color(95, 95, 95)
                self.cell(0, 10, f"INES - {self._title}", 0, 0, "L")
                self.cell(0, 10, f"Página {self.page_no()} / {{nb}}", 0, 1, "R")
                self.set_draw_color(10, 10, 10)
                self.set_line_width(0.6)
                self.line(10, 18, 200, 18)
                self.ln(2)

        def footer(self) -> None:
            self.set_y(-15)
            _pdf_font(self, "I", 9)
            self.set_text_color(95, 95, 95)
            self.cell(0, 10, f"Generado por INES - Página {self.page_no()} / {{nb}}", 0, 0, "C")

    pdf = _ReportPDF()
    pdf.alias_nb_pages()
    pdf.set_line_width(0.6)
    pdf.add_page()
    return pdf


def make_pdf_response(pdf: Any, filename: str) -> HttpResponse:
    pdf_raw = pdf.output()
    pdf_bytes = (
        bytes(pdf_raw)
        if isinstance(pdf_raw, (bytearray, memoryview))
        else pdf_raw.encode("utf-8")
        if isinstance(pdf_raw, str)
        else bytes(pdf_raw)
    )
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _get_equipment_name(notif: Any) -> str:
    if notif.monitoring_equipment:
        return notif.monitoring_equipment.name
    return "N/A"


def render_event_rows(pdf: Any, parsed_list: list[Any], column_widths: list[int], column_aligns: list[str]) -> None:
    _pdf_font(pdf, "", 9)
    pdf.set_draw_color(10, 10, 10)

    if len(parsed_list) > MAX_PDF_EVENTS:
        _pdf_font(pdf, "I", 9)
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
        equip_str = _get_equipment_name(notif)

        row_data = [date_str, equip_str, risk, variable_str, value_str, action_str]
        cell_fills = [None, None, fill_c, None, None, None]
        cell_colors = [None, None, text_c, None, None, None]

        draw_row(pdf, column_widths, column_aligns, row_data, cell_fills, cell_colors)
