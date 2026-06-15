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

# ─── Paleta de acento ────────────────────────────────────────────────────────
ACCENT_COLOR = (30, 58, 95)        # Navy blue — identidad de marca INES
ACCENT_LIGHT = (235, 241, 249)     # Azul muy suave — zebra alternado

# ─── Colores neutros ─────────────────────────────────────────────────────────
DIVIDER_COLOR = (200, 205, 212)    # Gris suave para líneas divisoras
HEADER_BG     = (10, 10, 10)       # Negro para encabezados de tabla
HEADER_TEXT   = (255, 255, 255)    # Blanco para texto de encabezados


# ─── Logo ────────────────────────────────────────────────────────────────────

def render_logo(pdf: Any) -> None:
    """
    Logo de INES con barra de acento navy a la izquierda.
    Patrón idéntico usado por los 3 PDFs vía render_pdf_header.
    """
    y0 = pdf.get_y()

    # Barra de acento vertical izquierda
    pdf.set_fill_color(*ACCENT_COLOR)
    pdf.rect(10, y0, 4, 22, "F")

    # Wordmark "INES"
    pdf.set_x(17)
    _pdf_font(pdf, "B", 28)
    pdf.set_text_color(*ACCENT_COLOR)
    pdf.cell(0, 14, "INES", ln=1, align="L")

    # Bajada de marca
    pdf.set_x(17)
    _pdf_font(pdf, "", 10)
    pdf.set_text_color(95, 95, 95)
    pdf.cell(0, 8, "Sistema inteligente de automatización", ln=1, align="L")
    pdf.ln(2)

    # Línea separadora suave
    pdf.set_draw_color(*DIVIDER_COLOR)
    pdf.set_line_width(0.5)
    y = pdf.get_y()
    pdf.line(10, y, 200, y)
    pdf.set_line_width(0.6)
    pdf.ln(6)


# ─── Encabezado unificado ─────────────────────────────────────────────────────

def render_pdf_header(
    pdf: Any,
    title: str,
    now: dt.datetime,
    meta_lines: list,
) -> None:
    """
    Encabezado unificado para los 3 PDFs.
    Llama a render_logo, luego muestra el título y las líneas de metadatos.
    meta_lines: lista de strings o None (los None se omiten).
    """
    render_logo(pdf)
    _pdf_font(pdf, "B", 18)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 12, title, ln=1, align="L")
    _pdf_font(pdf, "", 11)
    pdf.set_text_color(26, 26, 26)
    for line in meta_lines:
        if line is not None:
            pdf.cell(0, 7, line, ln=1)
    pdf.ln(6)


# ─── Divisor de sección ───────────────────────────────────────────────────────

def render_section_divider(pdf: Any, title: str) -> None:
    """
    Divisor de sección: título con acento navy + línea gris suave.
    Patrón único que reemplaza el bloque _pdf_font(B,13) + set_text_color + cell
    en todas las secciones de los 3 PDFs.
    """
    if pdf.get_y() > 250:
        pdf.add_page()
    pdf.ln(2)
    _pdf_font(pdf, "B", 13)
    pdf.set_text_color(*ACCENT_COLOR)
    pdf.cell(0, 9, title, ln=1)
    pdf.set_draw_color(*DIVIDER_COLOR)
    pdf.set_line_width(0.4)
    y = pdf.get_y()
    pdf.line(10, y, 200, y)
    pdf.set_line_width(0.6)
    pdf.ln(3)


# ─── Caja de resumen ejecutivo ────────────────────────────────────────────────

def render_summary_box(pdf: Any, items: list) -> None:
    """
    Fila de celdas coloreadas para resúmenes ejecutivos.
    Patrón idéntico usado por los 3 PDFs.
    Cada item: {"label": str, "value": str|int, "fill": (r,g,b), "text": (r,g,b)}
    """
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

    # Fondos
    for i, item in enumerate(items):
        fill = item.get("fill", (240, 244, 248))
        pdf.set_fill_color(*fill)
        x = start_x + i * cell_w
        pdf.rect(x, start_y, cell_w, box_h, "DF")

    # Etiquetas (fila superior)
    _pdf_font(pdf, "", 8)
    for i, item in enumerate(items):
        text_c = item.get("text", (10, 10, 10))
        label = item.get("label", "")
        pdf.set_xy(start_x + i * cell_w + 3, start_y + 2)
        pdf.set_text_color(*text_c)
        pdf.cell(cell_w - 3, 5, label, ln=0)

    # Valores (fila inferior, más grandes)
    _pdf_font(pdf, "B", 12)
    for i, item in enumerate(items):
        text_c = item.get("text", (10, 10, 10))
        value = str(item.get("value", ""))
        pdf.set_xy(start_x + i * cell_w + 3, start_y + 8)
        pdf.set_text_color(*text_c)
        pdf.cell(cell_w - 3, 7, value, ln=0)

    pdf.set_xy(start_x, start_y + box_h + 4)


# ─── Barra de progreso textual ────────────────────────────────────────────────

def render_text_progress_bar(
    pdf: Any,
    label: str,
    value: float,
    max_value: float,
    threshold: float | None = None,
    unit: str = "",
) -> None:
    """
    Barra de progreso en texto (bloques Unicode █░) para mostrar
    una lectura respecto a su rango máximo y umbral crítico.
    Patrón compartido disponible para los 3 PDFs.
    """
    if max_value <= 0:
        return

    bar_width = 24
    ratio = min(1.0, max(0.0, value / max_value))
    filled = round(ratio * bar_width)
    bar = "█" * filled + "░" * (bar_width - filled)
    pct = ratio * 100

    # Determinar color de la barra
    if threshold is not None and value < threshold:
        bar_fill = (254, 242, 242)
        bar_text = (153, 27, 27)
        estado = "⚠ Por debajo del umbral"
    else:
        bar_fill = (240, 253, 244)
        bar_text = (22, 101, 52)
        estado = "✓ Dentro del rango"

    if pdf.get_y() + 14 > 270:
        pdf.add_page()

    _pdf_font(pdf, "", 9)
    pdf.set_text_color(55, 65, 81)
    pdf.cell(0, 5, label, ln=1)

    _pdf_font(pdf, "B", 9)
    pdf.set_text_color(*bar_text)
    bar_line = f"{bar}  {pct:.0f}%   {value:.1f} / {max_value:.1f} {unit}".strip()
    pdf.set_fill_color(*bar_fill)
    pdf.set_draw_color(*HEADER_BG)
    pdf.cell(0, 7, f"  {bar_line}", 1, 1, "L", True)

    _pdf_font(pdf, "", 8)
    pdf.set_text_color(95, 95, 95)
    pdf.cell(0, 5, f"  {estado}", ln=1)
    pdf.ln(2)


# ─── Leyenda de severidades ───────────────────────────────────────────────────

def render_severity_legend(pdf: Any) -> None:
    """Leyenda de severidades — patrón compartido para building_report e history."""
    render_section_divider(pdf, "Leyenda de severidades")
    _pdf_font(pdf, "", 10)
    for lbl, fill, text_c, desc in SEVERITY_DISPLAY_LEVELS:
        pdf.set_fill_color(*fill)
        pdf.set_text_color(*text_c)
        pdf.set_draw_color(10, 10, 10)
        pdf.cell(28, 6, f"  {lbl}", 1, 0, "L", True)
        pdf.set_text_color(95, 95, 95)
        pdf.cell(162, 6, f" {desc}", 1, 1, "L")
    pdf.ln(6)


# ─── Resumen por severidad ────────────────────────────────────────────────────

def render_stats_summary(pdf: Any, parsed_list: list) -> None:
    """Resumen de conteos por severidad — usado en history."""
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


# ─── Configuración de columnas de historial ───────────────────────────────────

def get_column_config() -> tuple[list, list, list]:
    return (
        [28, 22, 18, 30, 18, 74],
        ["Fecha y hora", "Equipo", "Severidad", "Variable", "Valor", "Acción recomendada"],
        ["L", "L", "C", "L", "C", "L"],
    )


# ─── Encabezado de tabla ──────────────────────────────────────────────────────

def render_table_header(
    pdf: Any,
    column_widths: list,
    column_aligns: list,
    column_headers: list,
) -> None:
    """Encabezado de tabla (fondo negro, texto blanco) — patrón compartido."""
    _pdf_font(pdf, "B", 10)
    draw_row(
        pdf,
        column_widths,
        column_aligns,
        column_headers,
        fills=[HEADER_BG] * len(column_widths),
        colors=[HEADER_TEXT] * len(column_widths),
    )


# ─── PDF base ─────────────────────────────────────────────────────────────────

def _create_report_pdf(title: str) -> Any:
    """
    Clase PDF base con header/footer unificados.
    Página 1: franja navy en la parte superior.
    Páginas 2+: header con nombre del reporte y número de página.
    """
    from fpdf import FPDF

    class _ReportPDF(FPDF):
        _title = title

        def header(self) -> None:
            if self.page_no() == 1:
                # Franja de acento navy en la parte superior
                self.set_fill_color(*ACCENT_COLOR)
                self.rect(10, 10, 190, 2, "F")
                self.ln(5)
            else:
                _pdf_font(self, "I", 9)
                self.set_text_color(95, 95, 95)
                self.cell(0, 10, f"INES \u2014 {self._title}", 0, 0, "L")
                self.cell(0, 10, f"P\u00e1gina {self.page_no()} / {{nb}}", 0, 1, "R")
                self.set_draw_color(*DIVIDER_COLOR)
                self.set_line_width(0.5)
                self.line(10, 18, 200, 18)
                self.ln(2)

        def footer(self) -> None:
            self.set_y(-15)
            _pdf_font(self, "I", 9)
            self.set_text_color(95, 95, 95)
            self.cell(
                0, 10,
                f"INES \u00b7 Sistema inteligente de automatizaci\u00f3n"
                f"  \u00b7  P\u00e1gina {self.page_no()} / {{nb}}",
                0, 0, "C",
            )

    pdf = _ReportPDF()
    pdf.alias_nb_pages()
    pdf.set_line_width(0.6)
    pdf.add_page()
    return pdf


# ─── Respuesta HTTP ───────────────────────────────────────────────────────────

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


# ─── Helpers de historial ─────────────────────────────────────────────────────

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
    """Filas de eventos con zebra striping — patrón compartido."""
    _pdf_font(pdf, "", 9)
    pdf.set_draw_color(10, 10, 10)

    if len(parsed_list) > MAX_PDF_EVENTS:
        _pdf_font(pdf, "I", 9)
        pdf.set_text_color(194, 65, 12)
        pdf.cell(
            0, 6,
            f"Mostrando los primeros {MAX_PDF_EVENTS} de {len(parsed_list)} eventos totales.",
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
