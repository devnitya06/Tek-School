"""
Quick test — sends a CPU alert email immediately to garnaik53@gmail.com
Run: python test_cpu_alert.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.cpu_monitor import _send_cpu_alert_email

print("Sending test CPU alert email to garnaik53@gmail.com ...")

_send_cpu_alert_email(
    alert_message="[CPU_ALERT] System CPU 91.5% is above 85.0% threshold. "
                  "Top process: python (pid=1234) with CPU 88.0%, "
                  "memory 12.3%, state=running, threads=4. "
                  "Command: uvicorn app.main:app. "
                  "Reason: FastAPI application is handling requests or startup work.",
    system_cpu=91.5,
    threshold=85.0,
)

print("Done! Check garnaik53@gmail.com inbox (also check spam folder).")
