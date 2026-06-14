from typing import Any

from django.http import HttpResponse

from apps.core.auth_decorators import login_required

from .pdf_rendering import (
    _create_report_pdf,
    get_column_config,
    make_pdf_response,
    render_event_rows,
    render_header,
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

        import datetime as dt
        now = dt.datetime.now()
        render_header(
            pdf, now, building_name,
            params["severity"], params["variable"],
            range_label, len(parsed_list),
            date_from=params["date_from"], date_to=params["date_to"],
        )
        render_severity_legend(pdf)

        if parsed_list:
            render_stats_summary(pdf, parsed_list)

        from collections import OrderedDict
        groups: OrderedDict[str, list[Any]] = OrderedDict()
        for n in parsed_list:
            bld = (
                n.monitoring_equipment.building.name
                if (n.monitoring_equipment and n.monitoring_equipment.building)
                else "Sin edificio"
            )
            groups.setdefault(bld, []).append(n)

        column_widths, column_headers, column_aligns = get_column_config()

        if parsed_list:
            for group_name, group_events in groups.items():
                if pdf.get_y() > 240:
                    pdf.add_page()

                _pdf_font(pdf, "B", 11)
                pdf.set_text_color(10, 10, 10)
                pdf.cell(0, 8, f"{group_name} ({len(group_events)})", ln=1)
                pdf.ln(2)

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
