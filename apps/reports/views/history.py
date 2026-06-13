from typing import Any

from django.http import HttpResponse

from apps.core.auth_decorators import login_required

from .pdf_rendering import (
    get_column_config,
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
        from fpdf import FPDF

        class HistoryPDF(FPDF):
            def header(self) -> None:
                if self.page_no() == 1:
                    self.set_fill_color(10, 10, 10)
                    self.rect(10, 10, 190, 2, "F")
                    self.ln(5)
                else:
                    _pdf_font(self, "I", 9)
                    self.set_text_color(95, 95, 95)
                    self.cell(0, 10, "INES - Historial de eventos", 0, 0, "L")
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

        pdf = HistoryPDF()
        pdf.alias_nb_pages()
        pdf.set_line_width(0.6)
        pdf.add_page()

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

        pdf_raw = pdf.output()
        pdf_bytes = (
            bytes(pdf_raw)
            if isinstance(pdf_raw, (bytearray, memoryview))
            else pdf_raw.encode("utf-8")
            if isinstance(pdf_raw, str)
            else bytes(pdf_raw)
        )

        now_dt = now
        filename = f"historial_{now_dt.strftime('%Y%m%d_%H%M%S')}.pdf"
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
