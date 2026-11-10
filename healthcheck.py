"""
healthcheck.py
──────────────
Independently-scheduled watchdog for the newsletter automation.

overnight_runner.py already alerts on its own failures (via Resend), but if
the job never runs at all — machine asleep through the scheduled time,
launchd misconfigured, the process killed before it could log or alert —
there's no signal from that path. This script is a second launchd job on
its own schedule that checks whether today's run actually completed
successfully, and alerts if not.

Run directly:
    python healthcheck.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import os

env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from app.email.send_email import send_with_resend  # noqa: E402

LOG_DIR      = PROJECT_ROOT / "logs"
STATUS_FILE  = LOG_DIR / "send_status.jsonl"
HEALTH_LOG   = LOG_DIR / "healthcheck.log"


def write_log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now(timezone.utc).isoformat()}] {message}"
    print(line)
    with HEALTH_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def last_status() -> dict | None:
    if not STATUS_FILE.exists():
        return None
    lines = [l for l in STATUS_FILE.read_text().splitlines() if l.strip()]
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return None


def alert(reason: str) -> None:
    today = date.today().strftime("%B %d, %Y")
    subject = f"Newsletter Healthcheck Failed — {today}"
    body = f"No successful newsletter send recorded for {today}.\n\nReason: {reason}\n"

    resend_key = os.getenv("RESEND_API_KEY", "").strip()
    email_from = os.getenv("EMAIL_FROM", "").strip()
    email_to   = os.getenv("EMAIL_TO", "").strip()
    try:
        if send_with_resend(resend_key, email_from, email_to, subject, f"<pre>{body}</pre>"):
            write_log(f"ALERT | Healthcheck failure sent via Resend: {reason}")
            return
    except Exception as exc:
        write_log(f"ALERT | Resend healthcheck alert failed: {exc}")

    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{reason}" with title "{subject}"'],
            check=False,
            timeout=10,
        )
        write_log(f"ALERT | Sent local macOS notification (Resend unavailable): {reason}")
    except Exception as exc:
        write_log(f"ALERT | Could not show local notification either: {exc}")


def main() -> None:
    today = date.today().isoformat()
    status = last_status()

    if status is None:
        write_log("FAIL | No send_status.jsonl entries found — overnight job may not have run")
        alert("No status log entries found at all — the overnight job may not have run.")
        return

    if status.get("date") != today:
        write_log(f"FAIL | Most recent status entry is for {status.get('date')}, not today ({today})")
        alert(f"Most recent status entry is for {status.get('date')}, not today — the job likely didn't run today.")
        return

    if not status.get("send_ok"):
        write_log(f"FAIL | Today's entry shows send_ok={status.get('send_ok')} | error={status.get('error')}")
        # overnight_runner.py should have already alerted on this, but confirm it landed.
        if not status.get("alert_ok"):
            alert(f"Today's send failed AND its own alert may not have gone out. error={status.get('error')}")
        return

    write_log("OK | Today's newsletter send completed successfully")


if __name__ == "__main__":
    main()
