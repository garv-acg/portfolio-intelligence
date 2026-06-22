from __future__ import annotations

import argparse
import os
import smtplib
import subprocess
import sys
from datetime import date, datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

LOG_DIR  = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "overnight_runs.log"


def write_log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    line = f"[{timestamp}] {message}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_step(name: str, command: list[str]) -> tuple[bool, str]:
    write_log(f"START | {name}")
    result = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    if result.returncode == 0:
        write_log(f"SUCCESS | {name}")
    else:
        write_log(f"FAIL | {name} | exit={result.returncode}")
    if output.strip():
        write_log(f"OUTPUT | {name}\n{output.strip()}")
    return result.returncode == 0, output.strip()


def send_failure_alert(failed_step: str, output: str) -> None:
    gmail_user = os.getenv("GMAIL_USER", "").strip()
    gmail_pw   = os.getenv("GMAIL_APP_PASSWORD", "").strip()
    notify_to  = os.getenv("NEWSLETTER_TO", gmail_user).strip()

    if not gmail_user or not gmail_pw:
        write_log("ALERT | Cannot send failure email — GMAIL_USER/GMAIL_APP_PASSWORD not set")
        return

    today = date.today().strftime("%B %d, %Y")
    body = (
        f"Newsletter automation failed on {today}.\n\n"
        f"Failed step: {failed_step}\n\n"
        f"Output:\n{output[:2000] if output else '(no output)'}\n\n"
        f"Check logs at: {LOG_FILE}\n"
    )
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"⚠ Newsletter Failed — {today}"
    msg["From"]    = gmail_user
    msg["To"]      = notify_to

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
            server.login(gmail_user, gmail_pw)
            server.sendmail(gmail_user, notify_to, msg.as_string())
        write_log(f"ALERT | Failure notification sent to {notify_to}")
    except Exception as exc:
        write_log(f"ALERT | Could not send failure notification: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Overnight newsletter runner.")
    parser.add_argument("--skip-email", action="store_true", help="Generate but do not send.")
    parser.add_argument("--dry-run",    action="store_true", help="Show steps without running.")
    args = parser.parse_args()

    python = sys.executable

    steps = [
        ("Generate newsletter", [python, str(PROJECT_ROOT / "generate_hybrid_newsletter.py")]),
    ]
    if not args.skip_email:
        # Use app/send_newsletter.py — reads creds from .env, proper error handling
        steps.append(("Send newsletter email", [python, str(PROJECT_ROOT / "send_newsletter.py")]))

    write_log("OVERNIGHT WORKFLOW STARTED")

    if args.dry_run:
        for name, command in steps:
            write_log(f"DRY RUN | {name} | {' '.join(command)}")
        write_log("OVERNIGHT WORKFLOW DRY RUN COMPLETE")
        return

    for name, command in steps:
        ok, output = run_step(name, command)
        if not ok:
            write_log("OVERNIGHT WORKFLOW FAILED")
            if not args.skip_email:
                send_failure_alert(name, output)
            raise SystemExit(1)

    write_log("OVERNIGHT WORKFLOW COMPLETE")


if __name__ == "__main__":
    main()
