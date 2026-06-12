import datetime as dt
import os

from django.shortcuts import render
from django.http import HttpResponse
from django.utils import timezone as tz

from apps.core.auth_decorators import _login_required, _is_admin_role
from apps.users.models import Usuario
from apps.users.services import _build_beneficiario_data
from apps.buildings.models import Edificio, UsuarioEdificio, EquipoMonitoreo
from apps.alerts.models import Notificacion
from apps.alerts.views import _parse_notif_for_historial
from django.db.models import Q


@_login_required
def historial_pdf_view(request):
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return HttpResponse("No autorizado", status=401)
    rol = request.session.get("usuario_rol", "US")

    edificio_id = request.GET.get("edificio", "").strip()
    if edificio_id.lower() in ("", "none", "null"):
        edificio_id = ""
    severidad = request.GET.get("severidad", "").strip()
    variable_filter = request.GET.get("variable", "").strip()
    periodo_seleccionado = request.GET.get("periodo", "24h").strip()
    fecha_desde_raw = request.GET.get("fecha_desde", "").strip()
    fecha_hasta_raw = request.GET.get("fecha_hasta", "").strip()

    if _is_admin_role(rol):
        notificaciones = Notificacion.objects.all()
        edificio_nombre = "Todos los edificios"
        if edificio_id:
            notificaciones = notificaciones.filter(id_equipo_monitoreo__id_edificio_id=edificio_id)
            try:
                edificio_nombre = Edificio.objects.get(id_edificio=edificio_id).nb_edificio
            except Edificio.DoesNotExist:
                pass
    else:
        usuario_edificios = UsuarioEdificio.objects.filter(
            id_usuario_id=usuario_id
        ).values_list("id_edificio", flat=True)
        edificio_nombre = "Todos los edificios"
        if edificio_id:
            if edificio_id.isdigit() and int(edificio_id) in list(usuario_edificios):
                notificaciones = Notificacion.objects.filter(
                    id_equipo_monitoreo__id_edificio_id=edificio_id
                )
                try:
                    edificio_nombre = Edificio.objects.get(id_edificio=edificio_id).nb_edificio
                except Edificio.DoesNotExist:
                    pass
            else:
                notificaciones = Notificacion.objects.none()
        else:
            equipos = EquipoMonitoreo.objects.filter(
                id_edificio_id__in=list(usuario_edificios)
            ).values_list("id_equipo_monitoreo", flat=True)
            notificaciones = Notificacion.objects.filter(
                id_usuario_id=usuario_id
            ) | Notificacion.objects.filter(id_equipo_monitoreo_id__in=list(equipos))

    ALL_SEVERITIES = ["Info", "Bajo", "Medio", "Alto", "Crítico"]
    if severidad and severidad in ALL_SEVERITIES:
        notificaciones = notificaciones.filter(
            Q(mensaje__risk=severidad)
            | Q(mensaje__contains=f'"risk": "{severidad}"')
            | Q(mensaje__contains=f'"risk":"{severidad}"')
        )

    now = tz.now()
    DELTA_MAP = {
        "1h":  dt.timedelta(hours=1),
        "12h": dt.timedelta(hours=12),
        "24h": dt.timedelta(hours=24),
        "3d":  dt.timedelta(days=3),
        "7d":  dt.timedelta(days=7),
    }

    if periodo_seleccionado in DELTA_MAP:
        notificaciones = notificaciones.filter(fecha__gte=now - DELTA_MAP[periodo_seleccionado])
    elif periodo_seleccionado == "custom":
        if fecha_desde_raw:
            try:
                naive = dt.datetime.strptime(fecha_desde_raw, "%Y-%m-%d")
                notificaciones = notificaciones.filter(fecha__gte=tz.make_aware(naive))
            except ValueError:
                pass
        if fecha_hasta_raw:
            try:
                naive = dt.datetime.strptime(fecha_hasta_raw, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59
                )
                notificaciones = notificaciones.filter(fecha__lte=tz.make_aware(naive))
            except ValueError:
                pass

    periodo_label_map = {
        "1h":  "Última hora",
        "12h": "Últimas 12 horas",
        "24h": "Últimas 24 horas",
        "3d":  "Últimos 3 días",
        "7d":  "Últimos 7 días",
        "custom": f"Personalizado: {fecha_desde_raw or '?'} al {fecha_hasta_raw or '?'}",
    }
    rango = periodo_label_map.get(periodo_seleccionado, periodo_seleccionado)

    notificaciones = (
        notificaciones.select_related("id_equipo_monitoreo__id_edificio")
        .distinct()
        .order_by("-fecha")
    )

    parsed_list = []
    for notif in notificaciones:
        notif = _parse_notif_for_historial(notif)
        parsed_list.append(notif)

    if variable_filter:
        parsed_list = [
            n for n in parsed_list
            if n.parsed_data.get("parsed") and n.parsed_data.get("variable") == variable_filter
        ]

    try:
        from fpdf import FPDF
        from io import BytesIO

        now = dt.datetime.now()

        _UNICODE_FONTS = {}
        _FONT_SEARCH_PATHS = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/DejaVuSans.ttf",
            "C:/Windows/Fonts/DejaVuSans.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/ARIAL.TTF",
        ]
        for _p in _FONT_SEARCH_PATHS:
            if os.path.exists(_p):
                _p_dir = os.path.dirname(_p)
                _p_name = os.path.splitext(os.path.basename(_p))[0]
                _UNICODE_FONTS["family"] = "DejaVu" if "DejaVu" in _p_name else "Arial"
                _UNICODE_FONTS["path"] = _p
                _UNICODE_FONTS["path_bold"] = os.path.join(_p_dir, _p_name.replace("Sans", "Sans-Bold") + ".ttf")
                if not os.path.exists(_UNICODE_FONTS.get("path_bold", "")):
                    _UNICODE_FONTS["path_bold"] = _p
                break

        def _pdf_font(pdf_obj, style="", size=10):
            if _UNICODE_FONTS:
                family = _UNICODE_FONTS["family"]
                pdf_obj.add_font(family, style, _UNICODE_FONTS["path_bold"] if style == "B" else _UNICODE_FONTS["path"], uni=True)
                pdf_obj.set_font(family, style, size)
            else:
                pdf_obj.set_font("Helvetica", style, size)

        class HistorialPDF(FPDF):
            def header(self):
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

            def footer(self):
                self.set_y(-15)
                _pdf_font(self, "I", 8)
                self.set_text_color(95, 95, 95)
                self.cell(0, 10, f"Generado por INES - Pagina {self.page_no()}", 0, 0, "C")

        pdf = HistorialPDF()
        pdf.set_line_width(0.6)
        pdf.add_page()

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
        pdf.cell(0, 6, f"Edificio: {edificio_nombre}", ln=1)
        pdf.cell(0, 6, f"Severidad: {severidad if severidad else 'Todas'}", ln=1)
        pdf.cell(0, 6, f"Variable: {variable_filter if variable_filter else 'Todas'}", ln=1)
        pdf.cell(0, 6, f"Rango: {rango}", ln=1)
        pdf.cell(0, 6, f"Total de eventos: {len(parsed_list)}", ln=1)
        pdf.ln(8)

        _pdf_font(pdf, "B", 10)
        pdf.set_text_color(10, 10, 10)
        pdf.cell(0, 7, "LEYENDA DE SEVERIDADES", ln=1)
        pdf.ln(1)
        levels = [
            ("Info", (249, 250, 251), (55, 65, 81), "Eventos informativos del sistema"),
            ("Bajo", (240, 253, 244), (22, 101, 52), "Valores normales de funcionamiento"),
            ("Medio", (255, 251, 235), (146, 64, 14), "Cerca del limite sugerido"),
            ("Alto", (255, 247, 237), (194, 65, 12), "Fuera de rango seguro"),
            ("Critico", (254, 242, 242), (153, 27, 27), "Estado de peligro, accion inmediata"),
        ]
        _pdf_font(pdf, "", 8)
        for lbl, fill, text_c, desc in levels:
            pdf.set_fill_color(*fill)
            pdf.set_text_color(*text_c)
            pdf.set_draw_color(10, 10, 10)
            pdf.cell(28, 6, f"  {lbl}", 1, 0, "L", True)
            pdf.set_text_color(95, 95, 95)
            pdf.cell(162, 6, f" {desc}", 1, 1, "L")
        pdf.ln(8)

        _pdf_font(pdf, "B", 10)
        pdf.set_text_color(10, 10, 10)
        pdf.cell(0, 7, f"EVENTOS REGISTRADOS ({len(parsed_list)})", ln=1)
        pdf.ln(2)

        mostrar_todos_edificios = (edificio_nombre == "Todos los edificios")
        if mostrar_todos_edificios:
            col_widths = [26, 26, 20, 30, 20, 68]
            col_headers = ["Fecha / Hora", "Edificio", "Severidad", "Variable", "Valor", "Accion recomendada"]
            col_aligns = ["L", "L", "C", "L", "C", "L"]
        else:
            col_widths = [38, 26, 40, 24, 62]
            col_headers = ["Fecha / Hora", "Severidad", "Variable", "Valor", "Accion recomendada"]
            col_aligns = ["L", "C", "L", "C", "L"]

        def draw_row(pdf_obj, widths, aligns, row_data, cell_fills=None, cell_texts=None):
            lines_per_col = []
            for w, text in zip(widths, row_data):
                t_str = str(text) if text is not None else ""
                if not _UNICODE_FONTS:
                    t_str = t_str.encode("latin-1", errors="replace").decode("latin-1")
                lines = pdf_obj.multi_cell(w, 4, t_str, split_only=True)
                lines_per_col.append(lines)

            max_lines = max(len(lines) for lines in lines_per_col) if lines_per_col else 1
            line_height = 4.5
            row_height = max_lines * line_height

            if pdf_obj.get_y() + row_height > 270:
                pdf_obj.add_page()

            start_x = pdf_obj.get_x()
            start_y = pdf_obj.get_y()

            for i in range(max_lines):
                pdf_obj.set_xy(start_x, start_y + (i * line_height))
                for j, lines in enumerate(lines_per_col):
                    w = widths[j]
                    fill_c = cell_fills[j] if (cell_fills and cell_fills[j]) else None
                    if fill_c:
                        pdf_obj.set_fill_color(*fill_c)
                        pdf_obj.cell(w, line_height, "", border=0, fill=True)
                    else:
                        pdf_obj.cell(w, line_height, "", border=0, fill=False)

            for i in range(max_lines):
                pdf_obj.set_xy(start_x, start_y + (i * line_height))
                for j, lines in enumerate(lines_per_col):
                    w = widths[j]
                    align = aligns[j]
                    txt = lines[i] if i < len(lines) else ""
                    if align == "L" and txt:
                        txt = f" {txt}"

                    text_c = cell_texts[j] if (cell_texts and cell_texts[j]) else (26, 26, 26)
                    pdf_obj.set_text_color(*text_c)
                    pdf_obj.cell(w, line_height, txt, border=0, align=align, fill=False)

            curr_x = start_x
            pdf_obj.set_draw_color(10, 10, 10)
            for w in widths:
                pdf_obj.rect(curr_x, start_y, w, row_height)
                curr_x += w

            pdf_obj.set_xy(start_x, start_y + row_height)

        if parsed_list:
            _pdf_font(pdf, "B", 8)
            draw_row(
                pdf,
                col_widths,
                col_aligns,
                col_headers,
                cell_fills=[(10, 10, 10)] * len(col_widths),
                cell_texts=[(255, 255, 255)] * len(col_widths)
            )

            _pdf_font(pdf, "", 7)
            pdf.set_draw_color(10, 10, 10)

            MAX_PDF_EVENTS = 200
            if len(parsed_list) > MAX_PDF_EVENTS:
                _pdf_font(pdf, "I", 8)
                pdf.set_text_color(194, 65, 12)
                pdf.cell(0, 6, f"Mostrando los primeros {MAX_PDF_EVENTS} de {len(parsed_list)} eventos totales.", ln=1)
                pdf.ln(2)

            risk_styles = {
                "Info":    ((249, 250, 251), (55, 65, 81)),
                "Bajo":    ((240, 253, 244), (22, 101, 52)),
                "Medio":   ((255, 251, 235), (146, 64, 14)),
                "Alto":    ((255, 247, 237), (194, 65, 12)),
                "Crítico": ((254, 242, 242), (153, 27, 27)),
            }

            for notif in parsed_list[:MAX_PDF_EVENTS]:
                risk = notif.parsed_data.get("risk", "")
                fill_c, text_c = risk_styles.get(risk, ((255, 255, 255), (26, 26, 26)))

                fecha_str = notif.fecha.strftime("%d/%m/%Y %H:%M") if notif.fecha else ""
                variable_str = notif.parsed_data.get("variable", "")
                valor_str = notif.parsed_data.get("value", "")
                if valor_str and valor_str.lower() not in ("true", "false", "none", ""):
                    unidad = notif.parsed_data.get("unit", "")
                    valor_str = f"{valor_str} {unidad}".strip()
                accion_str = notif.parsed_data.get("action", "")

                if mostrar_todos_edificios:
                    edificio_fila = notif.id_equipo_monitoreo.id_edificio.nb_edificio if (notif.id_equipo_monitoreo and notif.id_equipo_monitoreo.id_edificio) else "N/A"
                    row_data = [fecha_str, edificio_fila, risk, variable_str, valor_str, accion_str]
                    cell_fills = [None, None, fill_c, None, None, None]
                    cell_texts = [None, None, text_c, None, None, None]
                else:
                    row_data = [fecha_str, risk, variable_str, valor_str, accion_str]
                    cell_fills = [None, fill_c, None, None, None]
                    cell_texts = [None, text_c, None, None, None]

                draw_row(pdf, col_widths, col_aligns, row_data, cell_fills, cell_texts)
        else:
            _pdf_font(pdf, "I", 9)
            pdf.set_text_color(95, 95, 95)
            pdf.cell(0, 8, "No se encontraron eventos con los filtros aplicados.", ln=1)

        pdf_raw = pdf.output()
        pdf_bytes = bytes(pdf_raw) if isinstance(pdf_raw, (bytearray, memoryview)) else pdf_raw.encode("utf-8") if isinstance(pdf_raw, str) else bytes(pdf_raw)

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


@_login_required
def descargar_pdf_view(request):
    try:
        from fpdf import FPDF

        from apps.core.auth_decorators import ADMIN_ROLES
        usuarios = (
            Usuario.objects.select_related("id_persona")
            .prefetch_related("usuarioedificio_set__id_edificio")
            .exclude(rol__in=ADMIN_ROLES)
        )
        beneficiarios = [_build_beneficiario_data(u) for u in usuarios]

        class PDF(FPDF):
            def header(self):
                _pdf_font(self, "B", 14)
                self.cell(0, 10, "INES - Reporte General de Beneficiarios", 0, 1, "C")
                self.set_draw_color(37, 99, 235)
                self.set_line_width(0.5)
                self.line(10, 22, 200, 22)
                self.ln(10)

            def footer(self):
                self.set_y(-15)
                _pdf_font(self, "I", 8)
                self.cell(0, 10, f"Página {self.page_no()}", 0, 0, "C")

        pdf = PDF()
        pdf.add_page()
        _pdf_font(pdf, "B", 10)
        pdf.set_fill_color(240, 244, 248)

        pdf.cell(25, 8, "Cedula", 1, 0, "C", True)
        pdf.cell(45, 8, "Nombre", 1, 0, "C", True)
        pdf.cell(45, 8, "Apellido", 1, 0, "C", True)
        pdf.cell(45, 8, "Email", 1, 0, "C", True)
        pdf.cell(30, 8, "Edificio", 1, 1, "C", True)

        _pdf_font(pdf, "", 9)
        for b in beneficiarios:
            pdf.cell(25, 8, str(b["cedula"]), 1, 0, "C")
            pdf.cell(45, 8, b["nombre"][:24], 1)
            pdf.cell(45, 8, b["apellido"][:24], 1)
            pdf.cell(45, 8, b["email"][:24], 1)
            pdf.cell(30, 8, b["edificio_nombre"][:18], 1, 1)

        pdf_raw = pdf.output()
        pdf_bytes = bytes(pdf_raw) if isinstance(pdf_raw, (bytearray, memoryview)) else pdf_raw.encode("utf-8") if isinstance(pdf_raw, str) else bytes(pdf_raw)

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="reporte_beneficiarios.pdf"'
        return response

    except Exception as e:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("Error generando PDF de beneficiarios, fallback a CSV: %s", e)

        import csv

        from apps.core.auth_decorators import ADMIN_ROLES

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            'attachment; filename="reporte_beneficiarios.csv"'
        )
        response.write("\ufeff".encode("utf8"))
        writer = csv.writer(response)
        writer.writerow(
            ["Cedula", "Nombre", "Apellido", "Email", "Telefono", "Edificio"]
        )
        usuarios = (
            Usuario.objects.select_related("id_persona")
            .prefetch_related("usuarioedificio_set__id_edificio")
            .exclude(rol__in=ADMIN_ROLES)
        )
        for u in usuarios:
            b = _build_beneficiario_data(u)
            writer.writerow(
                [
                    b["cedula"],
                    b["nombre"],
                    b["apellido"],
                    b["email"],
                    b["telefono"],
                    b["edificio_nombre"],
                ]
            )
        return response
