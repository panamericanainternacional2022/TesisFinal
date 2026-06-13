import datetime as dt
import logging
import os
from datetime import timedelta
from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.alerts.models import Notification
from apps.buildings.models import Building, MonitoringEquipment, UserBuilding

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
    ("Informativo", (249, 250, 251), (55, 65, 81), "Eventos informativos del sistema"),
    ("Bajo", (240, 253, 244), (22, 101, 52), "Valores normales de funcionamiento"),
    ("Medio", (255, 251, 235), (146, 64, 14), "Cerca del límite sugerido"),
    ("Alto", (255, 247, 237), (194, 65, 12), "Fuera de rango seguro"),
    ("Crítico", (254, 242, 242), (153, 27, 27), "Estado de peligro, acción inmediata"),
]

RISK_STYLES: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "Info": ((249, 250, 251), (55, 65, 81)),
    "Bajo": ((240, 253, 244), (22, 101, 52)),
    "Medio": ((255, 251, 235), (146, 64, 14)),
    "Alto": ((255, 247, 237), (194, 65, 12)),
    "Crítico": ((254, 242, 242), (153, 27, 27)),
}

_FONT_CACHE: dict[str, str] = {}


def _get_user_info(request: Any) -> tuple[int | None, str]:
    user_id: int | None = request.session.get("usuario_id")
    role: str = request.session.get("usuario_rol", "US")
    return user_id, role


def _parse_query_params(request: Any) -> dict[str, str]:
    building_id: str = request.GET.get("edificio", "").strip()
    if building_id.lower() in ("", "none", "null"):
        building_id = ""
    return {
        "building_id": building_id,
        "severity": request.GET.get("severidad", "").strip(),
        "variable": request.GET.get("variable", "").strip(),
        "period": request.GET.get("periodo", "24h").strip(),
        "date_from": request.GET.get("fecha_desde", "").strip(),
        "date_to": request.GET.get("fecha_hasta", "").strip(),
    }


def _filter_by_role_and_building(
    user_id: int | None,
    role: str,
    building_id: str,
) -> tuple[QuerySet, str]:
    from apps.core.auth_decorators import is_admin_role
    if is_admin_role(role):
        notifications = Notification.objects.all()
        building_name: str = "Todos los edificios"
        if building_id:
            notifications = notifications.filter(monitoring_equipment__building_id=building_id)
            try:
                building_name = Building.objects.get(id=building_id).name
            except Building.DoesNotExist:
                pass
    else:
        user_buildings = UserBuilding.objects.filter(
            user_id=user_id
        ).values_list("building_id", flat=True)
        building_name = "Todos los edificios"
        if building_id:
            if building_id.isdigit() and int(building_id) in list(user_buildings):
                notifications = Notification.objects.filter(
                    monitoring_equipment__building_id=building_id
                )
                try:
                    building_name = Building.objects.get(id=building_id).name
                except Building.DoesNotExist:
                    pass
            else:
                notifications = Notification.objects.none()
        else:
            equipment_ids = MonitoringEquipment.objects.filter(
                building_id__in=list(user_buildings)
            ).values_list("id", flat=True)
            notifications = Notification.objects.filter(
                user_id=user_id
            ) | Notification.objects.filter(monitoring_equipment_id__in=list(equipment_ids))
    return notifications, building_name


def _apply_severity_filter(
    notifications: QuerySet, severity: str
) -> QuerySet:
    if severity and severity in ALL_SEVERITY_LEVELS:
        notifications = notifications.filter(
            Q(mensaje__risk=severity)
            | Q(mensaje__contains=f'"risk": "{severity}"')
            | Q(mensaje__contains=f'"risk":"{severity}"')
        )
    return notifications


def _apply_period_filter(
    notifications: QuerySet,
    period: str,
    date_from_raw: str,
    date_to_raw: str,
) -> QuerySet:
    now = timezone.now()
    if period in PERIOD_DELTA_MAP:
        notifications = notifications.filter(date__gte=now - PERIOD_DELTA_MAP[period])
    elif period == "custom":
        if date_from_raw:
            try:
                naive = dt.datetime.strptime(date_from_raw, "%Y-%m-%d")
                notifications = notifications.filter(date__gte=timezone.make_aware(naive))
            except ValueError:
                pass
        if date_to_raw:
            try:
                naive = dt.datetime.strptime(date_to_raw, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59
                )
                notifications = notifications.filter(date__lte=timezone.make_aware(naive))
            except ValueError:
                pass
    return notifications


def _parse_and_filter_notifications(
    notifications: QuerySet, variable: str
) -> list[Any]:
    from apps.alerts.views.shared import parse_notification_for_display

    notifications = (
        notifications.select_related("monitoring_equipment__building")
        .distinct()
        .order_by("-date")
    )

    parsed: list[Any] = []
    for notif in notifications:
        notif = parse_notification_for_display(notif)
        parsed.append(notif)

    if variable:
        parsed = [
            n for n in parsed
            if n.parsed_data.get("parsed") and n.parsed_data.get("variable") == variable
        ]
    return parsed


def _get_period_label(period: str, date_from_raw: str, date_to_raw: str) -> str:
    if period in PERIOD_LABEL_MAP:
        label = PERIOD_LABEL_MAP[period]
        if period == "custom":
            label = f"Personalizado: {date_from_raw or '?'} al {date_to_raw or '?'}"
        return label
    return period


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
    line_height: float = 5.5
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
