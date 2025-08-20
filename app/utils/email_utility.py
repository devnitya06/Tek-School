import random
import secrets
import string
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from sqlalchemy.orm import Session
from jinja2 import Environment, FileSystemLoader
from jinja2 import Template as JinjaTemplate
from app.core.config import settings

# Load templates from templates folder
templates_env = Environment(loader=FileSystemLoader('app/templates'))

def generate_password():
    return ''.join(
        random.choices(string.ascii_letters + string.digits + string.punctuation, k=10)
    )

def generate_otp(length: int = 6) -> str:
    return ''.join(str(secrets.randbelow(10)) for _ in range(length))

def send_dynamic_email(
    context_key: str,
    subject: str,
    recipient_email: str,         
    context_data: dict,           
    db: Session,                  
):
    try:
        # Load HTML template from file
        template = templates_env.get_template(context_key)
        body_html = template.render(**context_data)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.MAIL_FROM_NAME} <{settings.MAIL_FROM}>"
        msg["To"] = recipient_email

        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP(settings.MAIL_SERVER, settings.MAIL_PORT) as server:
            server.starttls()
            server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
            server.sendmail(settings.MAIL_FROM, recipient_email, msg.as_string())

    except Exception as e:
        raise RuntimeError(f"Failed to send email: {e}")

