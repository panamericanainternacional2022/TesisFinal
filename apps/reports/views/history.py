import datetime as dt
from typing import Any

from django.http import HttpResponse

from apps.core.auth_decorators import login_required

from .pdf_rendering import (
    _create_report_pdf,
    get_column_config,
    make_pdf_response,
    render_event_rows,
    render_pdf_header,
    render_section_divider,
    render_severity_legend,
    render_stats_summary,
    render_table_header,
)
from .shared import (
    _apply_period_filter,
    _apply_severity_filter,
    _filter_by_role_and_building,
    _get_period_label,
    _get_user_info,
    _parse_and_filter_notifications,
    _parse_query_params,
    _pdf_font,
    draw_row,
)


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
        pdf = _create_report_pdf("Historial de eventos")
        now = dt.datetime.now()

        # ── Patrón unificado: header → leyenda → secciones ───────────────────
        render_pdf_header(
            pdf,
            title="Historial de eventos",
            now=now,
            meta_lines=[
                f"Generado: {now.strftime('%d/%m/%Y %H:%M:%S')}",
                f"Edificio: {building_name}",
                f"Severidad: {params['severity'] if params['severity'] else 'Todas'}",
                f"Variable: {params['variable'] if params['variable'] else 'Todas'}",
                f"Período: {range_label}",
                (
                    f"Rango personalizado: {params['date_from']} al {params['date_to']}"
                    if params["date_from"] and params["date_to"]
                    else None
                ),
                f"Total de eventos: {len(parsed_list)}",
            ],
        )

        # Patrón unificado: Resumen → Leyenda (igual que building_report)
        if parsed_list:
            render_stats_summary(pdf, parsed_list)

        render_severity_legend(pdf)

        # Agrupar por edificio
        from collections import OrderedDict
        groups: OrderedDict[str, list[Any]] = OrderedDict()
        for n in parsed_list:
            bld = (
                n.monitoring_equipment.building.name
                if (n.monitoring_equipment and n.monitoring_equipment.building)
                else "Sin edificio"
            )
            groups.setdefault(bld, []).append(n)

        # Resumen de eventos por edificio (sólo si hay más de un edificio)
        if len(groups) > 1:
            _render_building_summary(pdf, groups)

        column_widths, column_headers, column_aligns = get_column_config()

        if parsed_list:
            for group_name, group_events in groups.items():
                if pdf.get_y() > 240:
                    pdf.add_page()

                render_section_divider(pdf, f"{group_name} ({len(group_events)} evento(s))")
                render_table_header(pdf, column_widths, column_aligns, column_headers)
                render_event_rows(pdf, group_events, column_widths, column_aligns)
                pdf.ln(4)
        else:
            _pdf_font(pdf, "I", 10)
            pdf.set_text_color(95, 95, 95)
            pdf.cell(0, 9, "No se encontraron eventos con los filtros aplicados.", ln=1)

        filename = f"historial_{now.strftime('%Y%m%d_%H%M%S')}.pdf"
        return make_pdf_response(pdf, filename)

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


# ─── Sección: resumen por edificio ───────────────────────────────────────────

def _render_building_summary(pdf: Any, groups: dict) -> None:
    """
    Tabla de resumen de eventos agrupados por edificio.
    Se muestra sólo cuando hay más de un edificio en el resultado.
    """
    render_section_divider(pdf, "Distribución de eventos por edificio")

    col_widths = [120, 30, 40]
    col_headers = ["Edificio", "Eventos", "% del total"]
    col_aligns = ["L", "C", "C"]

    render_table_header(pdf, col_widths, col_aligns, col_headers)

    _pdf_font(pdf, "", 9)
    pdf.set_draw_color(10, 10, 10)
    total_events = sum(len(v) for v in groups.values())

    for idx, (bld_name, events) in enumerate(groups.items()):
        count = len(events)
        pct = (count / total_events * 100) if total_events else 0
        draw_row(
            pdf,
            col_widths,
            col_aligns,
            [bld_name, str(count), f"{pct:.1f}%"],
            row_index=idx,
        )

    pdf.ln(6)
