"""
send_newsletter.py
──────────────────
Sends the latest newsletter HTML as an email via Gmail SMTP.

Requirements in .env:
    GMAIL_USER=your@gmail.com
    GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
    NEWSLETTER_TO=recipient@gmail.com   (defaults to GMAIL_USER if not set)

Run manually:
    python send_newsletter.py

Or called automatically by launchd after main.py generates the newsletter.
"""
from __future__ import annotations

import os
import smtplib
import sys
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────────
GMAIL_USER       = os.getenv("GMAIL_USER", "").strip()
GMAIL_PASSWORD   = os.getenv("GMAIL_APP_PASSWORD", "").strip()
NEWSLETTER_TO    = os.getenv("NEWSLETTER_TO", GMAIL_USER).strip()
HTML_PATH        = Path("output/latest_newsletter.html")
TEXT_PATH        = Path("output/latest_newsletter.txt")

SUBJECT = f"Daily Portfolio Brief — {date.today().strftime('%B %d, %Y')}"


def send() -> None:
    # ── Validate config ────────────────────────────────────────────────────────
    if not GMAIL_USER:
        print("ERROR: GMAIL_USER not set in .env")
        sys.exit(1)
    if not GMAIL_PASSWORD:
        print("ERROR: GMAIL_APP_PASSWORD not set in .env")
        sys.exit(1)
    if not HTML_PATH.exists():
        print(f"ERROR: Newsletter not found at {HTML_PATH}. Run main.py first.")
        sys.exit(1)

    # ── Build message ──────────────────────────────────────────────────────────
    html_content = HTML_PATH.read_text(encoding="utf-8", errors="ignore")
    text_content = (
        TEXT_PATH.read_text(encoding="utf-8", errors="ignore")
        if TEXT_PATH.exists()
        else "Please view this email in an HTML-capable client."
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = SUBJECT
    msg["From"]    = GMAIL_USER
    msg["To"]      = NEWSLETTER_TO

    msg.attach(MIMEText(text_content, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html",  "utf-8"))

    # ── Send via Gmail SMTP ────────────────────────────────────────────────────
    print(f"Sending newsletter to {NEWSLETTER_TO}...")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_USER, NEWSLETTER_TO, msg.as_string())
        print(f"Sent: {SUBJECT}")
    except smtplib.SMTPAuthenticationError:
        print("ERROR: Gmail authentication failed.")
        print("  - Check GMAIL_USER and GMAIL_APP_PASSWORD in your .env")
        print("  - Make sure you're using an App Password, not your regular password")
        print("  - App passwords: myaccount.google.com/apppasswords")
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: Failed to send email: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    send()