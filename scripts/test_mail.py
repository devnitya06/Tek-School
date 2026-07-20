import os
import sys
import smtplib, ssl
from email.message import EmailMessage
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# Fetch credentials from the environment
port = int(os.getenv("MAIL_PORT", 587))
smtp_server = os.getenv("MAIL_SERVER")
username = os.getenv("MAIL_USERNAME")
password = os.getenv("MAIL_PASSWORD")
sender_email = os.getenv("MAIL_FROM")

# Accept recipient from command line arg, fallback to default
recipient_email = sys.argv[1] if len(sys.argv) > 1 else "santanugarnaik.dev@gmail.com"

print(f"Sending from : {sender_email}")
print(f"Sending to   : {recipient_email}")
print(f"SMTP server  : {smtp_server}:{port}")
print(f"Username     : {username}")
print()

msg = EmailMessage()
msg['Subject'] = "Test Email from Tek-School"
msg['From'] = sender_email
msg['To'] = recipient_email
msg.set_content("This is a test email sent from the Tek-School backend. If you received this, email is working correctly.")

try:
    if port == 465:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
            server.login(username, password)
            server.send_message(msg)
    elif port == 587:
        with smtplib.SMTP(smtp_server, port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(username, password)
            server.send_message(msg)
    else:
        print("use 465 / 587 as port value")
        exit()
    print(f"[OK] Successfully sent to {recipient_email}")
except Exception as e:
    print(f"[FAIL] {e}")