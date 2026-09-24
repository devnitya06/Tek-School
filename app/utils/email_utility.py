import random
import secrets
import string
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from sqlalchemy.orm import Session
from jinja2 import Environment, FileSystemLoader
from jinja2 import Template as JinjaTemplate
from app.core.config import settings

# Load templates from templates folder
templates_env = Environment(loader=FileSystemLoader('app/templates'))

def generate_password(prefix: str = None) -> str:
    symbol = random.choice("@#$")
    digits = ''.join(str(secrets.randbelow(10)) for _ in range(4))
    if prefix:
        clean_prefix = ''.join(ch for ch in prefix if ch.isalnum()).lower()[:4]
        if clean_prefix:
            prefix = clean_prefix.capitalize()
        else:
            prefix = ''.join(random.choices(string.ascii_lowercase, k=4)).capitalize()
    else:
        prefix = ''.join(random.choices(string.ascii_lowercase, k=4)).capitalize()
    return f"{prefix}{symbol}{digits}"


def generate_otp(length: int = 6) -> str:
    return ''.join(str(secrets.randbelow(10)) for _ in range(length))


def generate_calendar_invite_ics(
    summary: str,
    start_dt: datetime,
    end_dt: datetime,
    description: str,
    location: str,
    uid: str,
) -> str:
    """Build an iCalendar payload that can be saved as a calendar invite."""
    def format_ical(value: datetime) -> str:
        return value.strftime("%Y%m%dT%H%M%S")

    dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    ics = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//BeingIdeal//Demo Booking//EN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{format_ical(start_dt)}",
        f"DTEND:{format_ical(end_dt)}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        f"LOCATION:{location}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(ics) + "\r\n"


def send_raw_email(
    recipient_email: str,
    subject: str,
    body: str,
):
    """Send an email with a pre-rendered HTML body string (no template file needed)."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.MAIL_FROM_NAME} <{settings.MAIL_FROM}>"
        msg["To"] = recipient_email

        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(settings.MAIL_SERVER, settings.MAIL_PORT) as server:
            server.starttls()
            server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
            server.sendmail(settings.MAIL_FROM, recipient_email, msg.as_string())

    except Exception as e:
        raise RuntimeError(f"Failed to send email: {e}")


def send_dynamic_email(
    context_key: str,
    subject: str,
    recipient_email: str,
    context_data: dict,
    db: Session,
    attachments: list[tuple[str, str]] | None = None,
):
    try:
        # Load HTML template from file
        template = templates_env.get_template(context_key)
        body_html = template.render(**context_data)
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = f"{settings.MAIL_FROM_NAME} <{settings.MAIL_FROM}>"
        msg["To"] = recipient_email

        msg.attach(MIMEText(body_html, "html"))

        if attachments:
            for filename, content in attachments:
                calendar_part = MIMEText(content, _subtype="calendar", _charset="utf-8")
                calendar_part["Content-Type"] = "text/calendar; charset=UTF-8; method=REQUEST"
                calendar_part["Content-Transfer-Encoding"] = "7bit"
                calendar_part.add_header("Content-Disposition", "attachment", filename=filename)
                msg.attach(calendar_part)

        with smtplib.SMTP(settings.MAIL_SERVER, settings.MAIL_PORT) as server:
            server.starttls()
            server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
            server.sendmail(settings.MAIL_FROM, recipient_email, msg.as_string())

    except Exception as e:
        raise RuntimeError(f"Failed to send email: {e}")

