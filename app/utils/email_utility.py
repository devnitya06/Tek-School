import random
import re
import secrets
import string
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from app.models.users import Template
from app.core.config import settings
from sqlalchemy.orm import Session
from typing import Dict
import json


def generate_password():
    password = ''.join(random.choices(string.ascii_letters + string.digits + string.punctuation, k=10))
    return password

def generate_otp(length: int = 6) -> str:
    return ''.join(str(secrets.randbelow(10)) for _ in range(length))

conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_FROM_NAME=settings.MAIL_FROM_NAME,
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)



async def send_dynamic_email(
    db: Session,
    template_name: str,
    to_email: str,
    context: Dict[str, str]
):
    # Fetch the template by name
    template = db.query(Template).filter(Template.name == template_name).first()
    if not template:
        raise ValueError("Email template not found")

    # Replace context variables in subject and body
    subject = template.subject
    body = template.body

    try:
        context_data = json.loads(template.context)
        for key in context_data.keys():
            subject = subject.replace(f"{{{{{key}}}}}", context.get(key, ""))
            body = body.replace(f"{{{{{key}}}}}", context.get(key, ""))
    except json.JSONDecodeError:
        raise ValueError("Invalid context format in template")

    message = MessageSchema(
        subject=subject,
        recipients=[to_email],
        body=body,
        subtype="html"
    )

    fm = FastMail(conf)
    await fm.send_message(message)
