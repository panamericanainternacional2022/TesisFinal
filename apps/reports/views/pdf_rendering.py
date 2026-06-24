import datetime as dt
from typing import Any

from django.http import HttpResponse

from .shared import (
    MAX_PDF_EVENTS,
    RISK_STYLES,
    SEVERITY_DISPLAY_LEVELS,
    _pdf_font,
    draw_row,
    safe_text,
)

ACCENT_COLOR = (30, 58, 95)
ACCENT_LIGHT = (235, 241, 249)

DIVIDER_COLOR = (200, 205, 212)
HEADER_BG     = (10, 10, 10)
HEADER_TEXT   = (255, 255, 255)


def render_logo(pdf: Any) -> None:


    y0 = pdf.get_y()

    pdf.set_fill_color(*ACCENT_COLOR)
    pdf.rect(10, y0, 4, 22, "F")

    pdf.set_x(17)
    _pdf_font(pdf, "B", 28)
    pdf.set_text_color(*ACCENT_COLOR)
    pdf.cell(0, 14, "INES", ln=1, align="L")

    pdf.set_x(17)
    _pdf_font(pdf, "", 10)
    pdf.set_text_color(95, 95, 95)
    pdf.cell(0, 8, safe_text("Sistema inteligente de automatización"), ln=1, align="L")
    pdf.ln(2)

    pdf.set_draw_color(*DIVIDER_COLOR)
    pdf.set_line_width(0.5)
    y = pdf.get_y()
    pdf.line(10, y, 200, y)
    pdf.set_line_width(0.6)
    pdf.ln(6)


def render_pdf_header(
    pdf: Any,
    title: str,
    now: dt.datetime,
    meta_lines: list,
) -> None:


    render_logo(pdf)
    _pdf_font(pdf, "B", 18)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 12, safe_text(title), ln=1, align="L")
    _pdf_font(pdf, "", 11)
    pdf.set_text_color(26, 26, 26)
    for line in meta_lines:
        if line is not None:
            pdf.cell(0, 7, safe_text(line), ln=1)
    pdf.ln(6)


def render_section_divider(pdf: Any, title: str) -> None:


    if pdf.get_y() > 250:
        pdf.add_page()
    pdf.ln(2)
    _pdf_font(pdf, "B", 13)
    pdf.set_text_color(*ACCENT_COLOR)
    pdf.cell(0, 9, safe_text(title), ln=1)
    pdf.set_draw_color(*DIVIDER_COLOR)
    pdf.set_line_width(0.4)
    y = pdf.get_y()
    pdf.line(10, y, 200, y)
    pdf.set_line_width(0.6)
    pdf.ln(3)


def render_summary_box(pdf: Any, items: list) -> None:


    if not items:
        return

    n = len(items)
    cell_w = 190 // n
    start_x = pdf.get_x()
    start_y = pdf.get_y()
    box_h = 16

    if start_y + box_h > 270:
        pdf.add_page()
        start_y = pdf.get_y()

    pdf.set_draw_color(*HEADER_BG)

    for i, item in enumerate(items):
        fill = item.get("fill", (240, 244, 248))
        pdf.set_fill_color(*fill)
        x = start_x + i * cell_w
        pdf.rect(x, start_y, cell_w, box_h, "DF")

    _pdf_font(pdf, "", 8)
    for i, item in enumerate(items):
        text_c = item.get("text", (10, 10, 10))
        label = item.get("label", "")
        pdf.set_xy(start_x + i * cell_w + 3, start_y + 2)
        pdf.set_text_color(*text_c)
        pdf.cell(cell_w - 3, 5, safe_text(label), ln=0)

    _pdf_font(pdf, "B", 12)
    for i, item in enumerate(items):
        text_c = item.get("text", (10, 10, 10))
        value = str(item.get("value", ""))
        pdf.set_xy(start_x + i * cell_w + 3, start_y + 8)
        pdf.set_text_color(*text_c)
        pdf.cell(cell_w - 3, 7, safe_text(value), ln=0)

    pdf.set_xy(start_x, start_y + box_h + 4)


def render_text_progress_bar(
    pdf: Any,
    label: str,
    value: float,
    max_value: float,
    threshold: float | None = None,
    unit: str = "",
) -> None:


    if max_value <= 0:
        return

    ratio = min(1.0, max(0.0, value / max_value))
    pct = ratio * 100

    if threshold is not None and value < threshold:
        bar_fill = (254, 242, 242)
        bar_text = (153, 27, 27)
        estado = "⚠ Por debajo del umbral"
    else:
        bar_fill = (240, 253, 244)
        bar_text = (22, 101, 52)
        estado = "✓ Dentro del rango"

    if pdf.get_y() + 16 > 270:
        pdf.add_page()

    _pdf_font(pdf, "", 9)
    pdf.set_text_color(55, 65, 81)
    pdf.cell(0, 5, safe_text(label), ln=1)

    start_x = pdf.get_x()
    start_y = pdf.get_y()

    pdf.set_fill_color(*bar_fill)
    pdf.set_draw_color(*HEADER_BG)
    pdf.set_line_width(0.4)
    pdf.cell(0, 8, "", 1, 1, "L", True)

    bar_x = start_x + 4
    bar_y = start_y + 2
    bar_w = 80
    bar_h = 4

    pdf.set_fill_color(229, 231, 235)
    pdf.rect(bar_x, bar_y, bar_w, bar_h, "F")

    fill_color = (22, 101, 52) if (threshold is None or value >= threshold) else (153, 27, 27)
    pdf.set_fill_color(*fill_color)
    pdf.rect(bar_x, bar_y, bar_w * ratio, bar_h, "F")

    text_x = bar_x + bar_w + 4
    pdf.set_xy(text_x, start_y + 1)
    _pdf_font(pdf, "B", 9)
    pdf.set_text_color(*bar_text)
    
    safe_unit = safe_text(unit)
    info_text = f"{pct:.0f}%   ({value:.1f} / {max_value:.1f} {safe_unit})"
    pdf.cell(0, 6, info_text, 0, 0, "L")

    pdf.set_xy(start_x, start_y + 8)

    _pdf_font(pdf, "", 8)
    pdf.set_text_color(95, 95, 95)
    pdf.cell(0, 5, f"  {safe_text(estado)}", ln=1)
    pdf.ln(2)


def render_severity_legend(pdf: Any) -> None:

    render_section_divider(pdf, "Leyenda de severidades")
    _pdf_font(pdf, "", 10)
    for lbl, fill, text_c, desc in SEVERITY_DISPLAY_LEVELS:
        pdf.set_fill_color(*fill)
        pdf.set_text_color(*text_c)
        pdf.set_draw_color(10, 10, 10)
        pdf.cell(28, 6, f"  {safe_text(lbl)}", 1, 0, "L", True)
        pdf.set_text_color(95, 95, 95)
        pdf.cell(162, 6, f" {safe_text(desc)}", 1, 1, "L")
    pdf.ln(6)


def render_stats_summary(pdf: Any, parsed_list: list) -> None:

    from apps.sensors.sensor_config import SEVERITY_LEVELS
    stats: dict[str, int] = {k: 0 for k in SEVERITY_LEVELS}
    for n in parsed_list:
        risk = n.parsed_data.get("risk", "")
        if risk in stats:
            stats[risk] += 1

    render_section_divider(pdf, "Resumen por severidad")

    items = [
        {
            "label": lbl,
            "value": stats.get(lbl, 0),
            "fill": fill,
            "text": text_c,
        }
        for lbl, fill, text_c, _desc in SEVERITY_DISPLAY_LEVELS
    ]
    render_summary_box(pdf, items)


def get_column_config() -> tuple[list, list, list]:
    return (
        [28, 22, 18, 30, 18, 74],
        ["Fecha y hora", "Equipo", "Severidad", "Variable", "Valor", "Acción recomendada"],
        ["L", "L", "C", "L", "C", "L"],
    )


def render_table_header(
    pdf: Any,
    column_widths: list,
    column_aligns: list,
    column_headers: list,
) -> None:

    _pdf_font(pdf, "B", 10)
    draw_row(
        pdf,
        column_widths,
        column_aligns,
        column_headers,
        fills=[HEADER_BG] * len(column_widths),
        colors=[HEADER_TEXT] * len(column_widths),
    )


def _create_report_pdf(title: str) -> Any:


    from fpdf import FPDF

    class _ReportPDF(FPDF):
        _title = title

        def header(self) -> None:
            if self.page_no() == 1:
                self.set_fill_color(*ACCENT_COLOR)
                self.rect(10, 10, 190, 2, "F")
                self.ln(5)
            else:
                _pdf_font(self, "I", 9)
                self.set_text_color(95, 95, 95)
                title_text = safe_text(f"INES - {self._title}")
                page_text = safe_text(f"Pagina {self.page_no()} / {{nb}}")
                self.cell(0, 10, title_text, 0, 0, "L")
                self.cell(0, 10, page_text, 0, 1, "R")
                self.set_draw_color(*DIVIDER_COLOR)
                self.set_line_width(0.5)
                self.line(10, 18, 200, 18)
                self.ln(2)

        def footer(self) -> None:
            self.set_y(-15)
            _pdf_font(self, "I", 9)
            self.set_text_color(95, 95, 95)
            footer_text = safe_text(
                f"INES * Sistema inteligente de automatizacion"
                f"  *  Pagina {self.page_no()} / {{nb}}"
            )
            self.cell(0, 10, footer_text, 0, 0, "C")

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


def render_event_rows(
    pdf: Any,
    parsed_list: list,
    column_widths: list,
    column_aligns: list,
) -> None:

    _pdf_font(pdf, "", 9)
    pdf.set_draw_color(10, 10, 10)

    if len(parsed_list) > MAX_PDF_EVENTS:
        _pdf_font(pdf, "I", 9)
        pdf.set_text_color(194, 65, 12)
        pdf.cell(
            0, 6,
            safe_text(f"Mostrando los primeros {MAX_PDF_EVENTS} de {len(parsed_list)} eventos totales."),
            ln=1,
        )
        pdf.ln(2)

    for idx, notif in enumerate(parsed_list[:MAX_PDF_EVENTS]):
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

        draw_row(
            pdf, column_widths, column_aligns,
            row_data, cell_fills, cell_colors,
            row_index=idx,
        )
