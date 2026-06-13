import logging
from typing import Any

from django.http import HttpResponse

from apps.core.auth_decorators import ADMIN_ROLES, login_required
from apps.users.models import Usuario

from .shared import _pdf_font

logger = logging.getLogger(__name__)


@login_required
def beneficiary_pdf_view(request: Any) -> HttpResponse:
    try:
        import datetime as dt
        from fpdf import FPDF
        from django.db.models import Q

        from .shared import draw_row

        query = request.GET.get("q", "").strip()
        building_id = request.GET.get("edificio", "").strip()
        estado = request.GET.get("estado", "").strip()

        usuarios = (
            Usuario.objects.select_related("id_persona")
            .prefetch_related("building_assignments__building")
            .exclude(rol__in=ADMIN_ROLES)
        )

        building_name = None
        if building_id:
            usuarios = usuarios.filter(building_assignments__building_id=building_id)
            try:
                from apps.buildings.models import Building
                building_name = Building.objects.get(id=building_id).name
            except Building.DoesNotExist:
                pass

        if estado == "registrado":
            usuarios = usuarios.filter(registered=True)
        elif estado == "por_registrar":
            usuarios = usuarios.filter(registered=False)

        if query:
            usuarios = usuarios.filter(
                Q(id_persona__ci__icontains=query)
                | Q(id_persona__name__icontains=query)
                | Q(id_persona__last_name__icontains=query)
                | Q(id_persona__email__icontains=query)
                | Q(username__icontains=query)
                | Q(building_assignments__building__name__icontains=query)
            ).distinct()

        from apps.users.services import build_beneficiary_data

        beneficiaries = [build_beneficiary_data(u) for u in usuarios]

        class BeneficiaryPDF(FPDF):
            def header(self) -> None:
                if self.page_no() == 1:
                    self.set_fill_color(10, 10, 10)
                    self.rect(10, 10, 190, 2, "F")
                    self.ln(5)
                else:
                    _pdf_font(self, "I", 8)
                    self.set_text_color(95, 95, 95)
                    self.cell(0, 10, "INES - Reporte de Beneficiarios", 0, 0, "L")
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

        pdf = BeneficiaryPDF()
        pdf.set_line_width(0.6)
        pdf.add_page()

        now = dt.datetime.now()
        _pdf_font(pdf, "B", 18)
        pdf.set_text_color(10, 10, 10)
        pdf.cell(0, 12, "Reporte de Beneficiarios", ln=1, align="L")
        _pdf_font(pdf, "B", 11)
        pdf.set_text_color(95, 95, 95)
        pdf.cell(0, 8, "SISTEMA DE TELEMETRIA Y CONTROL", ln=1, align="L")
        pdf.ln(5)
        _pdf_font(pdf, "", 9)
        pdf.set_text_color(26, 26, 26)
        pdf.cell(0, 6, f"Generado: {now.strftime('%d/%m/%Y %H:%M:%S')}", ln=1)
        if building_name:
            pdf.cell(0, 6, f"Edificio: {building_name}", ln=1)
        if estado:
            estado_label = "Registrados" if estado == "registrado" else "Por registrar"
            pdf.cell(0, 6, f"Estado: {estado_label}", ln=1)
        if query:
            pdf.cell(0, 6, f"Busqueda: {query}", ln=1)
        pdf.cell(0, 6, f"Total de beneficiarios: {len(beneficiaries)}", ln=1)
        pdf.ln(8)

        _pdf_font(pdf, "B", 10)
        pdf.set_text_color(10, 10, 10)
        pdf.cell(0, 7, f"BENEFICIARIOS REGISTRADOS ({len(beneficiaries)})", ln=1)
        pdf.ln(2)

        col_widths = [25, 45, 45, 45, 30]
        col_headers = ["Cedula", "Nombre", "Apellido", "Email", "Edificio"]
        col_aligns = ["C", "L", "L", "L", "C"]

        if beneficiaries:
            _pdf_font(pdf, "B", 8)
            draw_row(
                pdf,
                col_widths,
                col_aligns,
                col_headers,
                fills=[(10, 10, 10)] * len(col_widths),
                colors=[(255, 255, 255)] * len(col_widths),
            )
            _pdf_font(pdf, "", 7)
            pdf.set_draw_color(10, 10, 10)
            for b in beneficiaries:
                row_data = [
                    str(b["cedula"]),
                    b["nombre"][:24],
                    b["last_name"][:24],
                    b["email"][:24],
                    b["edificio_nombre"][:18],
                ]
                draw_row(pdf, col_widths, col_aligns, row_data)
        else:
            _pdf_font(pdf, "I", 9)
            pdf.set_text_color(95, 95, 95)
            pdf.cell(0, 8, "No se encontraron beneficiarios con los filtros aplicados.", ln=1)

        pdf_raw = pdf.output()
        pdf_bytes = (
            bytes(pdf_raw)
            if isinstance(pdf_raw, (bytearray, memoryview))
            else pdf_raw.encode("utf-8")
            if isinstance(pdf_raw, str)
            else bytes(pdf_raw)
        )

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="reporte_beneficiarios.pdf"'
        return response

    except ImportError:
        return HttpResponse(
            "Error: fpdf2 no está instalado. Ejecute: pip install fpdf2",
            content_type="text/plain",
            status=500,
        )
    except Exception as e:
        logger.warning("Beneficiary PDF generation failed: %s", e)
        return HttpResponse(
            f"Error generando PDF: {e}",
            content_type="text/plain",
            status=500,
        )

