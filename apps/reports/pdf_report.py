"""
Módulo de generación de reportes PDF del sistema PCLogo.
Contiene la clase PDFReport y la función generate_pdf_report.
"""

import unicodedata
import logging
from datetime import datetime, timedelta
from io import BytesIO

from apps.sensors.sensor_config import PDF_BAR_VARS, PDF_STATS_VARS, PDF_BAR_LABELS, VAR_NAMES
from apps.reports.services.risk_service import classify_risk
from apps.alerts.services.alert_service import get_unit

try:
    from fpdf import FPDF

    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print(
        "fpdf2 no instalado. Reportes PDF no disponibles. Instale: pip install fpdf2"
    )

logger = logging.getLogger(__name__)


_FPDF_BASE = FPDF if PDF_AVAILABLE else object


class PDFReport(_FPDF_BASE):
    def header(self):
        if self.page_no() == 1:
            self.set_fill_color(10, 10, 10)
            self.rect(10, 10, 190, 2, "F")
            self.ln(5)
        else:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(95, 95, 95)
            self.cell(0, 10, "SISTEMA PCLogo - Reporte de Monitoreo", 0, 0, "L")
            self.cell(0, 10, f"Página {self.page_no()}", 0, 1, "R")
            self.set_draw_color(10, 10, 10)
            self.set_line_width(0.6)
            self.line(10, 18, 200, 18)
            self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(95, 95, 95)
        self.cell(0, 10, f"Generado por INES - Página {self.page_no()}", 0, 0, "C")


def _pdf_safe(text):
    return unicodedata.normalize('NFKD', str(text)).encode('latin-1', 'ignore').decode('latin-1')


def _es_var(v):
    return VAR_NAMES.get(v, v.replace("_", " ").title())


def generate_pdf_report(period, edificio_id=None):
    from apps.sensors.simulation import simulators
    from apps.alerts.services.alert_service import get_alert_log

    if not PDF_AVAILABLE:
        raise ImportError("fpdf2 no instalado")

    sim = None
    if edificio_id and edificio_id in simulators:
        sim = simulators[edificio_id]
    elif simulators:
        sim = next(iter(simulators.values()))

    sensor_data = sim.sensor_data if sim else {}
    history = sim.history if sim else []
    rationing_threshold = sim.config.get("rationing_threshold", 10.0) if sim else 10.0

    now = datetime.now()
    if period == "minute":
        start_time = now - timedelta(minutes=1)
        period_name = "Último minuto"
    elif period == "ten_minutes":
        start_time = now - timedelta(minutes=10)
        period_name = "Últimos 10 minutos"
    elif period == "hour":
        start_time = now - timedelta(hours=1)
        period_name = "Última hora"
    elif period == "day":
        start_time = now - timedelta(days=1)
        period_name = "Último día"
    elif period == "week":
        start_time = now - timedelta(days=7)
        period_name = "Última semana"
    else:
        start_time = now - timedelta(days=30)
        period_name = "Último mes"
    filtered_readings = [
        r
        for r in history
        if datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S") >= start_time
    ]
    stats = {}
    for var in PDF_STATS_VARS:
        vals = [
            r["value"]
            for r in filtered_readings
            if r["variable"] == var and isinstance(r["value"], (int, float))
        ]
        if vals:
            stats[var] = {
                "min": min(vals),
                "max": max(vals),
                "avg": sum(vals) / len(vals),
                "count": len(vals),
            }
        else:
            stats[var] = {"min": "N/A", "max": "N/A", "avg": "N/A", "count": 0}
    alerts_in_period = [
        a
        for a in get_alert_log(edificio_id, 500)
        if datetime.strptime(a["timestamp"], "%Y-%m-%d %H:%M:%S") >= start_time
    ]
    pdf = PDFReport()
    pdf.set_line_width(0.6)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 12, "Reporte de Monitoreo Automatizado", ln=1, align="L")
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(95, 95, 95)
    pdf.cell(0, 8, "SISTEMA DE TELEMETRIA Y CONTROL", ln=1, align="L")
    pdf.ln(5)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(26, 26, 26)
    pdf.cell(0, 6, f"Generado: {now.strftime('%d/%m/%Y %H:%M:%S')}", ln=1, align="L")
    pdf.cell(
        0,
        6,
        f"Periodo de Análisis: {period_name} (desde {start_time.strftime('%d/%m/%Y %H:%M:%S')})",
        ln=1,
        align="L",
    )
    pdf.ln(8)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 8, "LEYENDA DE RIESGOS", ln=1)
    pdf.ln(2)

    pdf.set_fill_color(240, 253, 244)
    pdf.set_text_color(22, 101, 52)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(30, 8, "  Bajo", 1, 0, "L", True)
    pdf.set_text_color(95, 95, 95)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(160, 8, " Valores normales de funcionamiento", 1, 1, "L")

    pdf.set_fill_color(255, 251, 235)
    pdf.set_text_color(146, 64, 14)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(30, 8, "  Medio", 1, 0, "L", True)
    pdf.set_text_color(95, 95, 95)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(160, 8, " Cerca del limite sugerido, requiere observacion", 1, 1, "L")

    pdf.set_fill_color(255, 247, 237)
    pdf.set_text_color(194, 65, 12)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(30, 8, "  Alto", 1, 0, "L", True)
    pdf.set_text_color(95, 95, 95)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(160, 8, " Fuera de rango seguro, requiere revision preventiva", 1, 1, "L")

    pdf.set_fill_color(254, 242, 242)
    pdf.set_text_color(153, 27, 27)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(30, 8, "  Critico", 1, 0, "L", True)
    pdf.set_text_color(95, 95, 95)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(160, 8, " Estado de peligro, requiere accion correctiva inmediata", 1, 1, "L")
    pdf.ln(10)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 8, "VALORES PROMEDIO DEL PERIODO", ln=1)
    pdf.ln(2)
    present_vars = []
    labels = []
    avgs = []
    for v in PDF_BAR_VARS:
        if v in stats and isinstance(stats[v]["avg"], float):
            present_vars.append(v)
            labels.append(PDF_BAR_LABELS.get(v, v))
            avgs.append(stats[v]["avg"])
    if avgs:
        max_avg = max(avgs)
        x0 = 15
        y0 = pdf.get_y()
        bar_width = 16
        spacing = 4
        max_bar_height = 50
        pdf.set_font("Helvetica", "", 7)
        for i, (var_name, lab, val) in enumerate(zip(present_vars, labels, avgs)):
            x = x0 + i * (bar_width + spacing)
            if x + bar_width > 200:
                break
            height = (val / max_avg) * max_bar_height if max_avg > 0 else 10

            risk, color_name = classify_risk(var_name, val)
            if color_name == "green":
                fill_color = (22, 101, 52)
            elif color_name == "yellow":
                fill_color = (146, 64, 14)
            elif color_name == "orange":
                fill_color = (194, 65, 12)
            elif color_name == "red":
                fill_color = (153, 27, 27)
            else:
                fill_color = (30, 41, 59)

            pdf.set_fill_color(*fill_color)
            pdf.set_draw_color(10, 10, 10)
            pdf.rect(x, y0 + max_bar_height - height, bar_width, height, "FD")

            pdf.set_text_color(*fill_color)
            pdf.set_xy(x, y0 + max_bar_height - height - 4)
            pdf.cell(bar_width, 4, f"{val:.1f}", 0, 0, "C")

            pdf.set_text_color(95, 95, 95)
            pdf.set_xy(x, y0 + max_bar_height + 2)
            pdf.cell(bar_width, 4, lab, 0, 0, "C")
        pdf.set_y(y0 + max_bar_height + 12)
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 8, "VALORES ACTUALES DE SENSORES", ln=1)
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(10, 10, 10)
    pdf.set_text_color(255, 255, 255)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(80, 8, "  Variable", 1, 0, "L", True)
    pdf.cell(50, 8, "  Valor Actual", 1, 0, "L", True)
    pdf.cell(60, 8, "Riesgo / Estado", 1, 1, "C", True)

    pdf.set_font("Helvetica", "", 9)
    pdf.set_draw_color(10, 10, 10)
    for var, val in sensor_data.items():
        risk, color = classify_risk(var, val)
        if color == "green":
            fill = (240, 253, 244)
            text_c = (22, 101, 52)
        elif color == "yellow":
            fill = (255, 251, 235)
            text_c = (146, 64, 14)
        elif color == "orange":
            fill = (255, 247, 237)
            text_c = (194, 65, 12)
        elif color == "red":
            fill = (254, 242, 242)
            text_c = (153, 27, 27)
        else:
            fill = (249, 250, 251)
            text_c = (55, 65, 81)

        if isinstance(val, bool):
            val_str = "Sí" if val else "No"
        else:
            val_str = f"{val} {get_unit(var)}"

        pdf.set_text_color(26, 26, 26)
        pdf.set_draw_color(10, 10, 10)
        pdf.cell(80, 8, _pdf_safe(f"  {_es_var(var)}"), 1, 0, "L")
        pdf.cell(50, 8, _pdf_safe(f"  {val_str}"), 1, 0, "L")

        pdf.set_fill_color(*fill)
        pdf.set_text_color(*text_c)
        pdf.set_draw_color(10, 10, 10)
        pdf.cell(60, 8, _pdf_safe(risk), 1, 1, "C", True)
    pdf.ln(8)

    if pdf.get_y() > 220:
        pdf.add_page()

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 8, _pdf_safe(f"ESTADISTICAS DE VARIABLES ({period_name.upper()})"), ln=1)
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(10, 10, 10)
    pdf.set_text_color(255, 255, 255)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(55, 7, "  Variable", 1, 0, "L", True)
    pdf.cell(32, 7, "Minimo", 1, 0, "C", True)
    pdf.cell(32, 7, "Maximo", 1, 0, "C", True)
    pdf.cell(36, 7, "Promedio", 1, 0, "C", True)
    pdf.cell(35, 7, "Lecturas", 1, 1, "C", True)

    pdf.set_font("Helvetica", "", 8)
    pdf.set_draw_color(10, 10, 10)
    pdf.set_text_color(26, 26, 26)
    for var in PDF_STATS_VARS:
        s = stats[var]
        pdf.cell(55, 6, _pdf_safe(f"  {_es_var(var)}"), 1)
        pdf.cell(32, 6, str(s["min"]), 1, 0, "C")
        pdf.cell(32, 6, str(s["max"]), 1, 0, "C")
        avg_val = f"{s['avg']:.2f}" if isinstance(s["avg"], float) else "N/A"
        pdf.cell(36, 6, avg_val, 1, 0, "C")
        pdf.cell(35, 6, str(s["count"]), 1, 1, "C")
    pdf.ln(8)

    if pdf.get_y() > 210:
        pdf.add_page()

    recs = []
    if "temperature" in stats and isinstance(stats["temperature"]["avg"], float):
        if stats["temperature"]["avg"] > 85:
            recs.append("Temperatura promedio elevada. Mejorar ventilación de sala.")
    if "flow_rate" in stats and isinstance(stats["flow_rate"]["avg"], float):
        if stats["flow_rate"]["avg"] < 10:
            recs.append("Caudal promedio bajo. Revisar bomba hidráulica y filtros.")
    if "pressure" in stats and isinstance(stats["pressure"]["avg"], float):
        if stats["pressure"]["avg"] > 7:
            recs.append("Presion media alta. Verificar reguladores de presion.")
    if "tank_level" in stats and isinstance(stats["tank_level"]["avg"], float):
        if stats["tank_level"]["avg"] < 25:
            recs.append("Nivel de tanque bajo. Aumentar frecuencia de recarga.")
    if not recs:
        recs.append("Todos los parámetros promedio se encuentran estables.")

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 8, "DIAGNOSTICO Y RECOMENDACIONES", ln=1)
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(55, 65, 81)
    for rec in recs[:5]:
        pdf.cell(0, 6, f"- {rec}", ln=1)
    pdf.ln(8)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 8, f"ALERTAS DETECTADAS EN EL PERIODO: {len(alerts_in_period)}", ln=1)
    pdf.ln(2)
    if alerts_in_period:
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(254, 242, 242)
        pdf.set_text_color(153, 27, 27)
        pdf.set_draw_color(10, 10, 10)
        pdf.cell(50, 7, "  Fecha/Hora", 1, 0, "L", True)
        pdf.cell(50, 7, "  Variable", 1, 0, "L", True)
        pdf.cell(40, 7, "Valor", 1, 0, "C", True)
        pdf.cell(50, 7, "Riesgo", 1, 1, "C", True)

        pdf.set_font("Helvetica", "", 8)
        pdf.set_draw_color(10, 10, 10)
        pdf.set_text_color(26, 26, 26)
        for a in alerts_in_period[:15]:
            val_raw = a.get("value")
            if val_raw is None:
                val_str_pdf = "-"
            elif isinstance(val_raw, bool):
                val_str_pdf = "Si" if val_raw else "No"
            else:
                unit = get_unit(a.get("variable", ""))
                val_str_pdf = f"{val_raw} {unit}".strip() if unit else str(val_raw)
            pdf.cell(50, 6, f"  {a['timestamp']}", 1)
            pdf.cell(50, 6, _pdf_safe(f"  {_es_var(a['variable'])}"), 1)
            pdf.cell(40, 6, _pdf_safe(val_str_pdf), 1, 0, "C")
            pdf.cell(50, 6, _pdf_safe(a["risk"]), 1, 1, "C")
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(95, 95, 95)
        pdf.cell(0, 8, "No se registraron alertas críticas durante este período.", ln=1)
    pdf.ln(8)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 8, "ESTADO GENERAL DE RACIONAMIENTO", ln=1)
    pdf.ln(2)

    if sensor_data.get("flow_rate", 0) < rationing_threshold:
        pdf.set_fill_color(254, 242, 242)
        pdf.set_text_color(153, 27, 27)
        pdf.set_draw_color(10, 10, 10)
        pdf.cell(0, 10, "  RACIONAMIENTO ACTIVO - Caudal por debajo del minimo admisible", 1, 1, "L", True)
    else:
        pdf.set_fill_color(240, 253, 244)
        pdf.set_text_color(22, 101, 52)
        pdf.set_draw_color(10, 10, 10)
        pdf.cell(0, 10, "  Racionamiento inactivo. Flujo hidraulico normal.", 1, 1, "L", True)

    pdf_output = pdf.output(dest="S")
    if isinstance(pdf_output, str):
        pdf_output = pdf_output.encode("latin-1")
    return BytesIO(pdf_output)
