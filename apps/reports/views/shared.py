import logging
import os
from datetime import timedelta
from typing import Any

logger = logging.getLogger(__name__)

ALL_SEVERITY_LEVELS: list[str] = ["Info", "Bajo", "Medio", "Alto", "Crítico"]

PERIOD_DELTA_MAP: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "12h": timedelta(hours=12),
    "24h": timedelta(hours=24),
    "3d": timedelta(days=3),
    "7d": timedelta(days=7),
}

PERIOD_LABEL_MAP: dict[str, str] = {
    "1h": "Última hora",
    "12h": "Últimas 12 horas",
    "24h": "Últimas 24 horas",
    "3d": "Últimos 3 días",
    "7d": "Últimos 7 días",
}

FONT_SEARCH_PATHS: list[str] = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/DejaVuSans.ttf",
    "C:/Windows/Fonts/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/ARIAL.TTF",
]

MAX_PDF_EVENTS: int = 200

SEVERITY_DISPLAY_LEVELS: list[tuple[str, tuple[int, int, int], tuple[int, int, int], str]] = [
    ("Info", (249, 250, 251), (55, 65, 81), "Eventos informativos del sistema"),
    ("Bajo", (240, 253, 244), (22, 101, 52), "Valores normales de funcionamiento"),
    ("Medio", (255, 251, 235), (146, 64, 14), "Cerca del limite sugerido"),
    ("Alto", (255, 247, 237), (194, 65, 12), "Fuera de rango seguro"),
    ("Crítico", (254, 242, 242), (153, 27, 27), "Estado de peligro, accion inmediata"),
]

RISK_STYLES: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "Info": ((249, 250, 251), (55, 65, 81)),
    "Bajo": ((240, 253, 244), (22, 101, 52)),
    "Medio": ((255, 251, 235), (146, 64, 14)),
    "Alto": ((255, 247, 237), (194, 65, 12)),
    "Crítico": ((254, 242, 242), (153, 27, 27)),
}

_FONT_CACHE: dict[str, str] = {}


def _resolve_font() -> dict[str, str]:
    if _FONT_CACHE:
        return _FONT_CACHE
    for path in FONT_SEARCH_PATHS:
        if os.path.exists(path):
            dir_path = os.path.dirname(path)
            base = os.path.splitext(os.path.basename(path))[0]
            family = "DejaVu" if "DejaVu" in base else "Arial"
            bold_path = os.path.join(dir_path, base.replace("Sans", "Sans-Bold") + ".ttf")
            if not os.path.exists(bold_path):
                bold_path = path
            _FONT_CACHE.update({"family": family, "path": path, "bold_path": bold_path})
            break
    return _FONT_CACHE


def _pdf_font(pdf: Any, style: str = "", size: int = 10) -> None:
    config = _resolve_font()
    if config:
        family: str = config["family"]
        font_path: str = config["bold_path"] if style == "B" else config["path"]
        pdf.add_font(family, style, font_path, uni=True)
        pdf.set_font(family, style, size)
    else:
        pdf.set_font("Helvetica", style, size)


def draw_row(
    pdf: Any,
    widths: list[int],
    aligns: list[str],
    data: list[str],
    fills: list[tuple[int, int, int] | None] | None = None,
    colors: list[tuple[int, int, int] | None] | None = None,
) -> None:
    lines_per_col: list[list[str]] = []
    for w, text in zip(widths, data):
        t_str = str(text) if text is not None else ""
        if not _resolve_font():
            t_str = t_str.encode("latin-1", errors="replace").decode("latin-1")
        lines = pdf.multi_cell(w, 4, t_str, split_only=True)
        lines_per_col.append(lines)

    max_lines = max(len(lines) for lines in lines_per_col) if lines_per_col else 1
    line_height: float = 4.5
    row_height: float = max_lines * line_height

    if pdf.get_y() + row_height > 270:
        pdf.add_page()

    start_x: float = pdf.get_x()
    start_y: float = pdf.get_y()

    for i in range(max_lines):
        pdf.set_xy(start_x, start_y + (i * line_height))
        for j, lines in enumerate(lines_per_col):
            w = widths[j]
            fill_c = fills[j] if (fills and fills[j]) else None
            if fill_c:
                pdf.set_fill_color(*fill_c)
                pdf.cell(w, line_height, "", border=0, fill=True)
            else:
                pdf.cell(w, line_height, "", border=0, fill=False)

    for i in range(max_lines):
        pdf.set_xy(start_x, start_y + (i * line_height))
        for j, lines in enumerate(lines_per_col):
            w = widths[j]
            align = aligns[j]
            txt = lines[i] if i < len(lines) else ""
            if align == "L" and txt:
                txt = f" {txt}"

            text_c = colors[j] if (colors and colors[j]) else (26, 26, 26)
            pdf.set_text_color(*text_c)
            pdf.cell(w, line_height, txt, border=0, align=align, fill=False)

    curr_x = start_x
    pdf.set_draw_color(10, 10, 10)
    for w in widths:
        pdf.rect(curr_x, start_y, w, row_height)
        curr_x += w

    pdf.set_xy(start_x, start_y + row_height)
