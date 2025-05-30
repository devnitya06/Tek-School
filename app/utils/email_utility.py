import random
import secrets
import string
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from sqlalchemy.orm import Session
from app.models.users import Template
from jinja2 import Template as JinjaTemplate
from app.core.config import settings
from sqlalchemy.orm import Session


def generate_password():
    return ''.join(
        random.choices(
            string.ascii_letters + string.digits + string.punctuation, k=10
        )
    )

def generate_otp(length: int = 6) -> str:
    return ''.join(str(secrets.randbelow(10)) for _ in range(length))

def send_dynamic_email(
    context_key: str,
    recipient_email: str,
    context_data: dict,
    db: Session,
):
    template = db.query(Template).filter(Template.context == context_key).first()

    if not template:
        raise ValueError(f"No email template found with name '{context_key}'")
    subject_template = JinjaTemplate(template.subject)
    body_template = JinjaTemplate(template.body)

    subject = subject_template.render(**context_data)
    body_html = body_template.render(**context_data)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.MAIL_FROM_NAME} <{settings.MAIL_FROM}>"
    msg["To"] = recipient_email

    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP(settings.MAIL_SERVER, settings.MAIL_PORT) as server:
            server.starttls()
            server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
            server.sendmail(settings.MAIL_FROM, recipient_email, msg.as_string())
    except Exception as e:
        raise RuntimeError(f"Failed to send email: {e}")
