import logging
from typing import Any

from django.http import HttpResponse

from apps.core.auth_decorators import ADMIN_ROLES, login_required
from apps.users.models import Usuario

from .shared import _pdf_font, draw_row
from .pdf_rendering import (
    _create_report_pdf,
    make_pdf_response,
    render_pdf_header,
    render_section_divider,
    render_summary_box,
    render_table_header,
)

logger = logging.getLogger(__name__)



@login_required
def user_pdf_view(request: Any) -> HttpResponse:
    try:
        import datetime as dt
        from django.db.models import Q

        query     = request.GET.get("q", "").strip()
        building_id = request.GET.get("edificio", "").strip()
        estado    = request.GET.get("estado", "").strip()

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

        # Incluir el rol junto a los datos del usuario
        users = [{"rol": u.rol, **build_user_data(u)} for u in usuarios]

        # Agrupar por edificio
        from collections import OrderedDict
        groups: OrderedDict[str, list[Any]] = OrderedDict()
        for b in users:
            key = b["edificio_nombre"] or "Sin edificio"
            groups.setdefault(key, []).append(b)

        now = dt.datetime.now()
        pdf = _create_report_pdf("Informe de usuarios")

        # Construir líneas de filtros aplicados
        filtros: list[str] = []
        if query:
            filtros.append(f"Búsqueda: «{query}»")
        if estado:
            estado_labels = {
                "registrado":   "Registrados",
                "por_registrar": "Pendientes de registro",
            }
            filtros.append(f"Estado: {estado_labels.get(estado, estado)}")

        total_registrados = sum(1 for u in users if u["registered"])
        total_pendientes  = len(users) - total_registrados

        # ── Patrón unificado: header → resumen → secciones ───────────────────
        render_pdf_header(
            pdf,
            title="Informe de usuarios",
            now=now,
            meta_lines=[
                f"Generado: {now.strftime('%d/%m/%Y %H:%M:%S')}",
                f"Total de usuarios: {len(users)}",
                f"Edificios: {len(groups)}",
                *filtros,           # filtros aplicados (puede ser vacío)
            ],
        )

        # Resumen ejecutivo via render_summary_box — mismo patrón
        render_section_divider(pdf, "Resumen de usuarios")
        render_summary_box(
            pdf,
            items=[
                {
                    "label": "Total de usuarios",
                    "value": len(users),
                    "fill":  (235, 241, 249),
                    "text":  (30, 58, 95),
                },
                {
                    "label": "Registrados",
                    "value": total_registrados,
                    "fill":  (240, 253, 244),
                    "text":  (22, 101, 52),
                },
                {
                    "label": "Pendientes",
                    "value": total_pendientes,
                    "fill":  (255, 251, 235),
                    "text":  (146, 64, 14),
                },
                {
                    "label": "Edificios",
                    "value": len(groups),
                    "fill":  (249, 250, 251),
                    "text":  (55, 65, 81),
                },
            ],
        )

        # Tabla de usuarios por edificio — sin columna Rol (todos son usuarios)
        col_widths  = [20, 32, 32, 64, 24, 18]
        col_headers = ["Cédula", "Nombre", "Apellido", "Correo electrónico", "Usuario", "Estado"]
        col_aligns  = ["C", "L", "L", "L", "L", "C"]

        for group_idx, (building_name, members) in enumerate(groups.items()):
            if pdf.get_y() > 240:
                pdf.add_page()

            render_section_divider(pdf, f"{building_name} ({len(members)} usuario(s))")
            render_table_header(pdf, col_widths, col_aligns, col_headers)

            _pdf_font(pdf, "", 9)
            pdf.set_draw_color(10, 10, 10)
            for idx, b in enumerate(members):
                estado_str = "Registrado" if b["registered"] else "Pendiente"

                # El username auto-generado no tiene significado antes del registro
                username_display = b.get("username", "")[:14] if b["registered"] else "-"

                # Colorear el estado
                if b["registered"]:
                    est_fill = (240, 253, 244)
                    est_text = (22, 101, 52)
                else:
                    est_fill = (255, 251, 235)
                    est_text = (146, 64, 14)

                draw_row(
                    pdf,
                    col_widths,
                    col_aligns,
                    [
                        str(b["cedula"]),
                        b["nombre"][:22],
                        b["last_name"][:22],
                        b["email"][:40],
                        username_display,
                        estado_str,
                    ],
                    [None, None, None, None, None, est_fill],
                    [None, None, None, None, None, est_text],
                    row_index=idx,
                )

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
