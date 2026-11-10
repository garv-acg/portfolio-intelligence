"""
send_newsletter.py — runs from project root (avoids app/email/ shadowing stdlib)
Reads credentials from .env: GMAIL_USER, GMAIL_APP_PASSWORD, NEWSLETTER_TO
"""
from __future__ import annotations

import os
import smtplib
import sys
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# Load .env manually (avoid dotenv import touching sys.path)
env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

GMAIL_USER    = os.getenv("GMAIL_USER", "").strip()
GMAIL_PW      = os.getenv("GMAIL_APP_PASSWORD", "").strip()
RECIPIENT     = os.getenv("NEWSLETTER_TO", GMAIL_USER).strip()
HTML_PATH     = PROJECT_ROOT / "output" / "latest_newsletter.html"
TEXT_PATH     = PROJECT_ROOT / "output" / "latest_newsletter.txt"
_meta_path = PROJECT_ROOT / "output" / "meta.json"
_daily_pct = None
_weekly_pct = None
_is_weekly = False
if _meta_path.exists():
    try:
        import json as _json
        _meta = _json.loads(_meta_path.read_text())
        _daily_pct  = _meta.get("portfolio_daily_pct")
        _weekly_pct = _meta.get("portfolio_weekly_pct")
        _is_weekly  = bool(_meta.get("is_weekly"))
    except Exception:
        pass

_headline_pct = _weekly_pct if _is_weekly else _daily_pct
if _headline_pct is not None and _headline_pct > 0:
    _emoji = "📈"
elif _headline_pct is not None and _headline_pct < 0:
    _emoji = "📉"
else:
    _emoji = ""

if _is_weekly:
    SUBJECT = f"{_emoji} Weekly Portfolio Digest — Week of {date.today().strftime('%B %d, %Y')}".strip()
else:
    SUBJECT = f"{_emoji} Daily Portfolio Brief — {date.today().strftime('%B %d, %Y')}".strip()

if not GMAIL_USER or not GMAIL_PW:
    print("ERROR: GMAIL_USER / GMAIL_APP_PASSWORD not set in .env")
    sys.exit(1)
if not HTML_PATH.exists():
    print(f"ERROR: {HTML_PATH} not found. Run generate_hybrid_newsletter.py first.")
    sys.exit(1)

html = HTML_PATH.read_text(encoding="utf-8", errors="ignore")
text = TEXT_PATH.read_text(encoding="utf-8", errors="ignore") if TEXT_PATH.exists() else ""

# Inline CSS so Gmail/Outlook don't strip <style> blocks
try:
    import logging
    import premailer
    html = premailer.transform(
        html,
        base_url=None,
        remove_classes=False,
        strip_important=False,
        allow_insecure_ssl=True,
        cssutils_logging_level=logging.CRITICAL,  # suppress CSS 2.1 validation errors
    )
except Exception:
    pass  # send as-is if premailer unavailable

msg = MIMEMultipart("alternative")
msg["Subject"] = SUBJECT
msg["From"]    = GMAIL_USER
msg["To"]      = RECIPIENT
if text:
    msg.attach(MIMEText(text, "plain", "utf-8"))
msg.attach(MIMEText(html, "html", "utf-8"))

print(f"Sending to {RECIPIENT}...")
try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_PW)
        server.sendmail(GMAIL_USER, RECIPIENT, msg.as_string())
    print(f"Sent: {SUBJECT}")
except smtplib.SMTPAuthenticationError:
    print("ERROR: Gmail authentication failed. Check GMAIL_USER and GMAIL_APP_PASSWORD in .env")
    sys.exit(1)
except Exception as exc:
    print(f"ERROR: {exc}")
    sys.exit(1)
