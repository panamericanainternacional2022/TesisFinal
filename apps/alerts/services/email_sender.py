import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Any, Dict, List, Optional



logger = logging.getLogger(__name__)


def get_unit(variable: str) -> str:
    from apps.sensors.sensor_config import UNITS
    return UNITS.get(variable, "")


def get_building_emails(edificio_id: Optional[int] = None) -> List[str]:
    try:
        from apps.buildings.models import Building, MonitoringEquipment, UserBuilding
    except Exception:
        return []
    try:
        if not edificio_id:
            equipo = MonitoringEquipment.objects.first()
            if equipo and equipo.building:
                edificio_id = equipo.building.id
            else:
                first_edf = Building.objects.first()
                if first_edf:
                    edificio_id = first_edf.id
                else:
                    return []

        users = UserBuilding.objects.filter(
            building_id=edificio_id,
            user__registered=True,
            user__alerts_disabled=False,
        ).select_related("user__id_persona")
        emails: List[str] = []
        for u in users:
            if u.user and u.user.id_persona and u.user.id_persona.email:
                email = u.user.id_persona.email.strip()
                if email and email not in emails:
                    emails.append(email)
        return emails
    except Exception as e:
        logger.error("Error retrieving emails for building %s: %s", edificio_id, e)
        return []


class EmailAttachment:
    def __init__(self, pdf_data: Any, filename: str = "report.pdf") -> None:
        self.pdf_data = pdf_data
        self.filename = filename


class EmailConfig:
    def __init__(
        self,
        risk_level: str,
        subject: str,
        body: str,
        attachment: Optional[EmailAttachment] = None,
        recipients: Optional[List[str]] = None,
        smtp_server: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
    ) -> None:
        self.risk_level = risk_level
        self.subject = subject
        self.body = body
        self.attachment = attachment
        self.recipients = recipients
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password


def _get_email_colors(risk_level: str) -> Dict[str, str]:
    from apps.sensors.sensor_config import RISK_BAJO, RISK_MEDIO, RISK_ALTO, RISK_CRITICO
    palette = {
        RISK_BAJO: {"bg": "#f0fdf4", "border": "#bbf7d0", "text": "#16a34a"},
        RISK_MEDIO: {"bg": "#fffbeb", "border": "#fde68a", "text": "#b45309"},
        RISK_ALTO: {"bg": "#fef2f2", "border": "#fecaca", "text": "#dc2626"},
        RISK_CRITICO: {"bg": "#fef2f2", "border": "#fecaca", "text": "#dc2626"},
    }
    return palette.get(risk_level, {"bg": "#f5f5f5", "border": "#e0e0e0", "text": "#6b6b6b"})


def _build_html_content(body: str, risk_level: str) -> str:
    colors = _get_email_colors(risk_level)
    lines = body.strip().split("\n")
    html_paragraphs: List[str] = []
    in_details = False
    in_actions = False
    details_rows: List[str] = []
    action_text = ""

    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            continue
        if "EVENT DETAILS:" in line_strip:
            in_details = True
            in_actions = False
            continue
        elif "SUGGESTED CORRECTIVE MEASURES:" in line_strip:
            in_details = False
            in_actions = True
            continue
        elif line_strip.startswith("---") or line_strip.startswith("==="):
            continue

        if in_details:
            if ":" in line_strip:
                parts = line_strip.split(":", 1)
                key = parts[0].strip()
                val = parts[1].strip()
                details_rows.append(f"""
                  <tr>
                    <td style="padding: 10px 0; border-bottom: 1px solid #e0e0e0; font-weight: 700; width: 35%; color: #0a0a0a;">{key}</td>
                    <td style="padding: 10px 0; border-bottom: 1px solid #e0e0e0; color: #2e2e2e;">{val}</td>
                  </tr>
                """)
            else:
                if details_rows:
                    html_paragraphs.append(f"<p style='margin: 0 0 12px 0;'>{line_strip}</p>")
        elif in_actions:
            if line_strip.startswith("Action:"):
                action_text = line_strip.split(":", 1)[1].strip()
            else:
                action_text += " " + line_strip
        else:
            if "SYSTEM" in line_strip and "REPORT" in line_strip:
                html_paragraphs.append(
                    f"<h2 style='margin: 0 0 16px 0; font-size: 16px; font-weight: 700; "
                    f"text-transform: uppercase; letter-spacing: 0.06em; border-bottom: 2px solid #0a0a0a; "
                    f"padding-bottom: 8px;'>{line_strip}</h2>"
                )
            else:
                html_paragraphs.append(f"<p style='margin: 0 0 12px 0;'>{line_strip}</p>")

    formatted_content = "".join(html_paragraphs)
    if details_rows:
        formatted_content += f"""
        <h3 style="margin: 20px 0 10px 0; font-size: 13px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: #0a0a0a;">Event Details</h3>
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: collapse; margin-bottom: 24px; font-size: 13px;">
          {"".join(details_rows)}
        </table>
        """
    if action_text:
        formatted_content += f"""
        <div style="margin: 24px 0; padding: 16px; background-color: {colors['bg']}; border: 1px solid {colors['border']}; border-left: 4px solid {colors['text']};">
          <span style="font-size: 11px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: {colors['text']}; display: block; margin-bottom: 6px;">Recommended Corrective Measure</span>
          <p style="margin: 0; font-size: 13px; font-weight: 500; color: #0a0a0a; line-height: 1.4;">{action_text}</p>
        </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{subject}}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f5f5f5; font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; color: #0a0a0a;">
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f5f5f5; padding: 24px 0;">
    <tr>
      <td align="center">
        <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #ffffff; border: 1px solid #0a0a0a; border-collapse: collapse;">
          <tr>
            <td style="padding: 24px; border-bottom: 1px solid #0a0a0a; background-color: #ffffff;">
              <span style="font-size: 14px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #0a0a0a;">Telemetry System </span>
            </td>
          </tr>
          <tr>
            <td style="padding: 24px; border-bottom: 1px solid #0a0a0a; background-color: {colors['bg']}; border-left: 6px solid {colors['text']};">
              <span style="font-size: 11px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: {colors['text']}; display: block; margin-bottom: 4px;">RISK LEVEL: {risk_level.upper()}</span>
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; line-height: 1.2; letter-spacing: -0.02em; color: #0a0a0a;">Alert and Monitoring Notification </h1>
            </td>
          </tr>
          <tr>
            <td style="padding: 24px; font-size: 14px; line-height: 1.55; color: #2e2e2e;">
              {formatted_content}
            </td>
          </tr>
          <tr>
            <td style="padding: 16px 24px; border-top: 1px solid #e0e0e0; background-color: #f5f5f5; font-size: 11px; color: #6b6b6b; text-align: center;">
              This message is automatically generated by the Control Panel.<br>
              Please do not reply to this email.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _send_email_smtp(config: EmailConfig) -> None:
    smtp_server = config.smtp_server or os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = config.smtp_port or int(os.environ.get("SMTP_PORT", 587))
    smtp_user = config.smtp_user or os.environ.get("SMTP_USER", "")
    smtp_password = config.smtp_password or os.environ.get("SMTP_PASSWORD", "")

    if not smtp_user or not smtp_password:
        logger.warning("SMTP credentials not configured. No real email will be sent to %s.", config.recipients)
        return

    html_content = _build_html_content(config.body, config.risk_level)

    msg = MIMEMultipart("mixed")
    msg["From"] = smtp_user
    msg["Subject"] = config.subject

    alt_part = MIMEMultipart("alternative")
    alt_part.attach(MIMEText(config.body, "plain", "utf-8"))
    alt_part.attach(MIMEText(html_content, "html", "utf-8"))
    msg.attach(alt_part)

    if config.attachment:
        config.attachment.pdf_data.seek(0)
        part = MIMEApplication(config.attachment.pdf_data.read(), _subtype="pdf")
        part.add_header("Content-Disposition", "attachment", filename=config.attachment.filename)
        msg.attach(part)

    from apps.sensors.sensor_config import SMTP_TIMEOUT
    server = smtplib.SMTP(smtp_server, smtp_port, timeout=SMTP_TIMEOUT)
    server.starttls()
    server.login(smtp_user, smtp_password)
    for rec in config.recipients or []:
        if "To" in msg:
            del msg["To"]
        msg["To"] = rec
        server.send_message(msg)
        logger.info("Real email sent to %s (risk %s)", rec, config.risk_level)
    server.quit()


def send_email_alert(
    risk_level: str,
    subject: str,
    body: str,
    attachment_pdf: Any = None,
    attachment_name: str = "report.pdf",
    recipients: Optional[List[str]] = None,
    smtp_server: Optional[str] = None,
    smtp_port: Optional[int] = None,
    smtp_user: Optional[str] = None,
    smtp_password: Optional[str] = None,
) -> None:
    if recipients is None:
        recipients = get_building_emails()
    if not recipients:
        logger.info("No subscribers for level %s in email", risk_level)
        return

    attachment = EmailAttachment(attachment_pdf, attachment_name) if attachment_pdf else None
    config = EmailConfig(
        risk_level=risk_level,
        subject=subject,
        body=body,
        attachment=attachment,
        recipients=recipients,
        smtp_server=smtp_server,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_password=smtp_password,
    )

    try:
        _send_email_smtp(config)
    except Exception as e:
        logger.error("Error sending email: %s", e)
