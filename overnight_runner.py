from __future__ import annotations

import argparse
import json
import os
import smtplib
import socket
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")
sys.path.insert(0, str(PROJECT_ROOT))

from app.email.send_email import send_with_resend  # noqa: E402

LOG_DIR      = PROJECT_ROOT / "logs"
LOG_FILE     = LOG_DIR / "overnight_runs.log"
STATUS_FILE  = LOG_DIR / "send_status.jsonl"
HTML_OUT     = PROJECT_ROOT / "output" / "latest_newsletter.html"

# How long to wait for network before giving up (seconds)
NETWORK_WAIT_SECS = 120
NETWORK_RETRY_INTERVAL = 5


def write_log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    line = f"[{timestamp}] {message}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def wait_for_network(timeout: int = NETWORK_WAIT_SECS) -> bool:
    """Block until DNS resolves or timeout. Returns True if network is up."""
    deadline = time.monotonic() + timeout
    attempt = 0
    while time.monotonic() < deadline:
        try:
            socket.getaddrinfo("smtp.gmail.com", 465, proto=socket.IPPROTO_TCP)
            if attempt > 0:
                write_log(f"NETWORK | Ready after {attempt * NETWORK_RETRY_INTERVAL}s wait")
            return True
        except OSError:
            if attempt == 0:
                write_log(f"NETWORK | Not ready yet — will retry every {NETWORK_RETRY_INTERVAL}s for up to {timeout}s")
            attempt += 1
            time.sleep(NETWORK_RETRY_INTERVAL)
    write_log(f"NETWORK | Timed out after {timeout}s — no network connectivity")
    return False


def run_step(name: str, command: list[str], timeout_secs: int = 600) -> tuple[bool, str]:
    write_log(f"START | {name}")
    result = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_secs,
    )
    output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    if result.returncode == 0:
        write_log(f"SUCCESS | {name}")
    else:
        write_log(f"FAIL | {name} | exit={result.returncode}")
    if output.strip():
        write_log(f"OUTPUT | {name}\n{output.strip()}")
    return result.returncode == 0, output.strip()


def newsletter_was_generated_today() -> bool:
    """Return True if output/latest_newsletter.html was written today (UTC)."""
    if not HTML_OUT.exists():
        return False
    mtime = datetime.fromtimestamp(HTML_OUT.stat().st_mtime, tz=timezone.utc)
    return mtime.date() == datetime.now(timezone.utc).date()


def write_status(generate_ok: bool, send_ok: bool | None, alert_ok: bool | None, error: str | None) -> None:
    """Append one line to logs/send_status.jsonl summarizing today's run."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "date": date.today().isoformat(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "generate_ok": generate_ok,
        "send_ok": send_ok,
        "alert_ok": alert_ok,
        "error": error,
    }
    with STATUS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def send_failure_alert(failed_step: str, output: str) -> bool:
    """Alert on a different transport than Gmail, so a Gmail-side problem
    (the thing most likely to be failing) can't also take out the alert."""
    today = date.today().strftime("%B %d, %Y")
    subject = f"Newsletter Failed — {today}"
    body_text = (
        f"Newsletter automation failed on {today}.\n\n"
        f"Failed step: {failed_step}\n\n"
        f"Output:\n{output[:2000] if output else '(no output)'}\n\n"
        f"Check logs at: {LOG_FILE}\n"
    )

    resend_key = os.getenv("RESEND_API_KEY", "").strip()
    email_from = os.getenv("EMAIL_FROM", "").strip()
    email_to   = os.getenv("EMAIL_TO", "").strip()
    try:
        if send_with_resend(resend_key, email_from, email_to, subject, f"<pre>{body_text}</pre>"):
            write_log(f"ALERT | Failure notification sent via Resend to {email_to}")
            return True
    except Exception as exc:
        write_log(f"ALERT | Resend failure notification failed: {exc}")

    # Last resort: a local macOS notification needs no network at all.
    try:
        safe_body = body_text.replace('"', "'").splitlines()[0][:200]
        subprocess.run(
            ["osascript", "-e", f'display notification "{safe_body}" with title "{subject}"'],
            check=False,
            timeout=10,
        )
        write_log("ALERT | Sent local macOS notification (Resend unavailable)")
        return True
    except Exception as exc:
        write_log(f"ALERT | Could not show local notification either: {exc}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Overnight newsletter runner.")
    parser.add_argument("--skip-email", action="store_true", help="Generate but do not send.")
    parser.add_argument("--dry-run",    action="store_true", help="Show steps without running.")
    args = parser.parse_args()

    python = sys.executable

    # main.py is the single entry point — generate_hybrid_newsletter.py has no __main__
    # and does nothing when called directly.
    steps = [
        ("Generate newsletter", [python, str(PROJECT_ROOT / "main.py")]),
    ]
    if not args.skip_email:
        steps.append(("Send newsletter email", [python, str(PROJECT_ROOT / "send_newsletter.py")]))

    write_log("OVERNIGHT WORKFLOW STARTED")

    if args.dry_run:
        for name, command in steps:
            write_log(f"DRY RUN | {name} | {' '.join(command)}")
        write_log("OVERNIGHT WORKFLOW DRY RUN COMPLETE")
        return

    # Wait for network before doing anything that touches the internet
    if not wait_for_network():
        write_log("OVERNIGHT WORKFLOW ABORTED — no network")
        write_status(generate_ok=False, send_ok=None, alert_ok=None, error="no network")
        raise SystemExit(1)

    generate_ok = False
    send_ok: bool | None = None

    for name, command in steps:
        ok, output = run_step(name, command)

        # After generation, verify the output file was actually updated today.
        # If main.py exited 0 but didn't write a fresh file, treat it as failure.
        if ok and name == "Generate newsletter":
            if not newsletter_was_generated_today():
                write_log(
                    "FAIL | Generate newsletter | exit=0 but latest_newsletter.html "
                    "was NOT updated today — pipeline may have silently failed"
                )
                ok = False
                output += "\n[overnight_runner] File freshness check failed."

        if name == "Generate newsletter":
            generate_ok = ok
        elif name == "Send newsletter email":
            send_ok = ok

        if not ok:
            write_log("OVERNIGHT WORKFLOW FAILED")
            alert_ok = send_failure_alert(name, output) if not args.skip_email else None
            write_status(generate_ok=generate_ok, send_ok=send_ok, alert_ok=alert_ok, error=f"{name}: {output[:500]}")
            raise SystemExit(1)

    write_log("OVERNIGHT WORKFLOW COMPLETE")
    write_status(generate_ok=generate_ok, send_ok=send_ok, alert_ok=None, error=None)


if __name__ == "__main__":
    main()
