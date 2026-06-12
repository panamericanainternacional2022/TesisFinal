import datetime as dt
from typing import Any

from django.db.models import Q, QuerySet
from django.http import HttpResponse
from django.utils import timezone

from apps.alerts.models import Notification
from apps.alerts.views.shared import parse_notification_for_display
from apps.buildings.models import Building, MonitoringEquipment, UserBuilding
from apps.core.auth_decorators import is_admin_role, login_required

from .shared import (
    ALL_SEVERITY_LEVELS,
    MAX_PDF_EVENTS,
    PERIOD_DELTA_MAP,
    PERIOD_LABEL_MAP,
    RISK_STYLES,
    SEVERITY_DISPLAY_LEVELS,
    _pdf_font,
    draw_row,
    logger,
)


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


def _build_pdf_header(pdf: Any, now: dt.datetime, building_name: str, severity: str, variable: str, range_label: str, total: int) -> None:
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


def _render_severity_legend(pdf: Any) -> None:
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


def _get_column_config(show_all_buildings: bool) -> tuple[list[int], list[str], list[str]]:
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


def _render_table_header(pdf: Any, column_widths: list[int], column_aligns: list[str], column_headers: list[str]) -> None:
    _pdf_font(pdf, "B", 8)
    draw_row(
        pdf,
        column_widths,
        column_aligns,
        column_headers,
        fills=[(10, 10, 10)] * len(column_widths),
        colors=[(255, 255, 255)] * len(column_widths),
    )


def _render_event_rows(pdf: Any, parsed_list: list[Any], column_widths: list[int], column_aligns: list[str], show_all_buildings: bool) -> None:
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


@login_required
def history_pdf_view(request: Any) -> HttpResponse:
    user_id, role = _get_user_info(request)
    if not user_id:
        return HttpResponse("No autorizado", status=401)

    params = _parse_query_params(request)

    notifications, building_name = _filter_by_role_and_building(
        user_id, role, params["building_id"]
    )

    notifications = _apply_severity_filter(notifications, params["severity"])
    notifications = _apply_period_filter(
        notifications, params["period"], params["date_from"], params["date_to"]
    )

    parsed_list = _parse_and_filter_notifications(notifications, params["variable"])

    range_label = _get_period_label(params["period"], params["date_from"], params["date_to"])

    try:
        from fpdf import FPDF

        class HistoryPDF(FPDF):
            def header(self) -> None:
                if self.page_no() == 1:
                    self.set_fill_color(10, 10, 10)
                    self.rect(10, 10, 190, 2, "F")
                    self.ln(5)
                else:
                    _pdf_font(self, "I", 8)
                    self.set_text_color(95, 95, 95)
                    self.cell(0, 10, "INES - Historial de Eventos", 0, 0, "L")
                    self.cell(0, 10, f"Pagina {self.page_no()}", 0, 1, "R")
                    self.set_draw_color(10, 10, 10)
                    self.set_line_width(0.6)
                    self.line(10, 18, 200, 18)
                    self.ln(2)

            def footer(self) -> None:
                self.set_y(-15)
                _pdf_font(self, "I", 8)
                self.set_text_color(95, 95, 95)
                self.cell(0, 10, f"Generado por INES - Pagina {self.page_no()}", 0, 0, "C")

        pdf = HistoryPDF()
        pdf.set_line_width(0.6)
        pdf.add_page()

        now = dt.datetime.now()
        _build_pdf_header(pdf, now, building_name, params["severity"], params["variable"], range_label, len(parsed_list))
        _render_severity_legend(pdf)

        show_all_buildings = building_name == "Todos los edificios"
        column_widths, column_headers, column_aligns = _get_column_config(show_all_buildings)

        _pdf_font(pdf, "B", 10)
        pdf.set_text_color(10, 10, 10)
        pdf.cell(0, 7, f"EVENTOS REGISTRADOS ({len(parsed_list)})", ln=1)
        pdf.ln(2)

        if parsed_list:
            _render_table_header(pdf, column_widths, column_aligns, column_headers)
            _render_event_rows(pdf, parsed_list, column_widths, column_aligns, show_all_buildings)
        else:
            _pdf_font(pdf, "I", 9)
            pdf.set_text_color(95, 95, 95)
            pdf.cell(0, 8, "No se encontraron eventos con los filtros aplicados.", ln=1)

        pdf_raw = pdf.output()
        pdf_bytes = (
            bytes(pdf_raw)
            if isinstance(pdf_raw, (bytearray, memoryview))
            else pdf_raw.encode("utf-8")
            if isinstance(pdf_raw, str)
            else bytes(pdf_raw)
        )

        filename = f"historial_{now.strftime('%Y%m%d_%H%M%S')}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    except ImportError:
        return HttpResponse(
            "Error: fpdf2 no está instalado. Ejecute: pip install fpdf2",
            content_type="text/plain",
            status=500,
        )
    except Exception as e:
        return HttpResponse(
            f"Error generando PDF: {e}",
            content_type="text/plain",
            status=500,
        )
