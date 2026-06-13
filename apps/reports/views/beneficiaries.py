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
        from fpdf import FPDF

        usuarios = (
            Usuario.objects.select_related("id_persona")
            .prefetch_related("building_assignments__building")
            .exclude(rol__in=ADMIN_ROLES)
        )
        from apps.users.services import build_beneficiary_data

        beneficiaries = [build_beneficiary_data(u) for u in usuarios]

        class BeneficiaryPDF(FPDF):
            def header(self) -> None:
                _pdf_font(self, "B", 14)
                self.cell(0, 10, "INES - Reporte General de Beneficiarios", 0, 1, "C")
                self.set_draw_color(37, 99, 235)
                self.set_line_width(0.5)
                self.line(10, 22, 200, 22)
                self.ln(10)

            def footer(self) -> None:
                self.set_y(-15)
                _pdf_font(self, "I", 8)
                self.cell(0, 10, f"Página {self.page_no()}", 0, 0, "C")

        pdf = BeneficiaryPDF()
        pdf.add_page()
        _pdf_font(pdf, "B", 10)
        pdf.set_fill_color(240, 244, 248)

        pdf.cell(25, 8, "Cedula", 1, 0, "C", True)
        pdf.cell(45, 8, "Nombre", 1, 0, "C", True)
        pdf.cell(45, 8, "Apellido", 1, 0, "C", True)
        pdf.cell(45, 8, "Email", 1, 0, "C", True)
        pdf.cell(30, 8, "Edificio", 1, 1, "C", True)

        _pdf_font(pdf, "", 9)
        for b in beneficiaries:
            pdf.cell(25, 8, str(b["cedula"]), 1, 0, "C")
            pdf.cell(45, 8, b["nombre"][:24], 1)
            pdf.cell(45, 8, b["last_name"][:24], 1)
            pdf.cell(45, 8, b["email"][:24], 1)
            pdf.cell(30, 8, b["edificio_nombre"][:18], 1, 1)

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

