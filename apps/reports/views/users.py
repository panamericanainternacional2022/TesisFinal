import logging
from typing import Any

from django.http import HttpResponse

from apps.core.auth_decorators import ADMIN_ROLES, login_required
from apps.users.models import Usuario

from .shared import _pdf_font, draw_row
from .pdf_rendering import _create_report_pdf, make_pdf_response, render_logo

logger = logging.getLogger(__name__)


@login_required
def user_pdf_view(request: Any) -> HttpResponse:
    try:
        import datetime as dt
        from django.db.models import Q

        query = request.GET.get("q", "").strip()
        building_id = request.GET.get("edificio", "").strip()
        estado = request.GET.get("estado", "").strip()

        usuarios = (
            Usuario.objects.select_related("id_persona")
            .prefetch_related("building_assignments__building")
            .exclude(rol__in=ADMIN_ROLES)
        )

        if building_id:
            usuarios = usuarios.filter(building_assignments__building_id=building_id)

        if estado == "registrado":
            usuarios = usuarios.filter(registered=True)
        elif estado == "por_registrar":
            usuarios = usuarios.filter(registered=False)

        if query:
            usuarios = usuarios.filter(
                Q(id_persona__ci__icontains=query)
                | Q(id_persona__first_name__icontains=query)
                | Q(id_persona__middle_name__icontains=query)
                | Q(id_persona__first_last_name__icontains=query)
                | Q(id_persona__second_last_name__icontains=query)
                | Q(id_persona__email__icontains=query)
                | Q(username__icontains=query)
                | Q(building_assignments__building__name__icontains=query)
            ).distinct()

        from apps.users.services import build_user_data

        users = [build_user_data(u) for u in usuarios]

        # Group by building
        from collections import OrderedDict
        groups: OrderedDict[str, list[Any]] = OrderedDict()
        for b in users:
            key = b["edificio_nombre"] or "Sin edificio"
            if key not in groups:
                groups[key] = []
            groups[key].append(b)

        pdf = _create_report_pdf("Informe de usuarios")

        now = dt.datetime.now()
        render_logo(pdf)
        _pdf_font(pdf, "B", 18)
        pdf.set_text_color(10, 10, 10)
        pdf.cell(0, 12, "Informe de usuarios", ln=1, align="L")
        _pdf_font(pdf, "", 11)
        pdf.set_text_color(26, 26, 26)
        pdf.cell(0, 7, f"Generado: {now.strftime('%d/%m/%Y %H:%M:%S')}", ln=1)
        pdf.cell(0, 7, f"Total de usuarios: {len(users)}", ln=1)
        pdf.cell(0, 7, f"Edificios: {len(groups)}", ln=1)
        pdf.ln(8)

        col_widths = [20, 35, 35, 48, 28, 24]
        col_headers = ["Cédula", "Nombre", "Apellido", "Correo electrónico", "Usuario", "Estado"]
        col_aligns = ["C", "L", "L", "L", "L", "C"]

        for group_idx, (building_name, members) in enumerate(groups.items()):
            if pdf.get_y() > 240:
                pdf.add_page()

            _pdf_font(pdf, "B", 11)
            pdf.set_text_color(10, 10, 10)
            pdf.cell(0, 8, f"{building_name} ({len(members)})", ln=1)
            pdf.ln(2)

            _pdf_font(pdf, "B", 10)
            draw_row(
                pdf,
                col_widths,
                col_aligns,
                col_headers,
                fills=[(10, 10, 10)] * len(col_widths),
                colors=[(255, 255, 255)] * len(col_widths),
            )

            _pdf_font(pdf, "", 9)
            pdf.set_draw_color(10, 10, 10)
            for b in members:
                estado_str = "Registrado" if b["registered"] else "Pendiente"
                row_data = [
                    str(b["cedula"]),
                    b["nombre"][:24],
                    b["last_name"][:24],
                    b["email"][:30],
                    b.get("username", "")[:16],
                    estado_str,
                ]
                draw_row(pdf, col_widths, col_aligns, row_data)

            pdf.ln(4)

        return make_pdf_response(pdf, "reporte_usuarios.pdf")

    except ImportError:
        return HttpResponse(
            "Error: fpdf2 no está instalado. Ejecute: pip install fpdf2",
            content_type="text/plain",
            status=500,
        )
    except Exception as e:
        logger.warning("User PDF generation failed: %s", e)
        return HttpResponse(
            f"Error generando PDF: {e}",
            content_type="text/plain",
            status=500,
        )
