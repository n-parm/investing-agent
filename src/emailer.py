import smtplib
from email.message import EmailMessage
from typing import List
from .config import SMTP

def send_email(subject: str, body: str, to_addrs: List[str] | None = None):
    cfg = SMTP
    to_addrs = to_addrs or cfg.get("to_addrs", [])
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.get("from_addr")
    msg["To"] = ", ".join(to_addrs)
    msg.set_content(body)

    server = smtplib.SMTP(cfg.get("host"), cfg.get("port", 587), timeout=30)
    try:
        server.starttls()
        server.login(cfg.get("username"), cfg.get("password"))
        server.send_message(msg)
    finally:
        server.quit()
