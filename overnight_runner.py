from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "overnight_runs.log"


def write_log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    line = f"[{timestamp}] {message}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_step(name: str, command: list[str]) -> tuple[bool, str]:
    write_log(f"START | {name} | {' '.join(command)}")

    result = subprocess.run(
        command,
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    output = ""
    if result.stdout:
        output += result.stdout
    if result.stderr:
        output += "\n" + result.stderr

    if result.returncode == 0:
        write_log(f"SUCCESS | {name}")
    else:
        write_log(f"FAIL | {name} | return_code={result.returncode}")

    if output.strip():
        write_log(f"OUTPUT | {name}\n{output.strip()}")

    return result.returncode == 0, output


def main() -> None:
    parser = argparse.ArgumentParser(description="Overnight automation runner for the newsletter platform.")
    parser.add_argument("--skip-email", action="store_true", help="Generate newsletter but do not send email.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without executing.")
    args = parser.parse_args()

    write_log("OVERNIGHT WORKFLOW STARTED")

    steps = [
        ("Generate newsletter, history, factors, and alerts", [sys.executable, "generate_hybrid_newsletter.py"]),
    ]

    if not args.skip_email:
        steps.append(("Send newsletter email", [sys.executable, "send_newsletter.py"]))

    if args.dry_run:
        for name, command in steps:
            write_log(f"DRY RUN | {name} | {' '.join(command)}")
        write_log("OVERNIGHT WORKFLOW DRY RUN COMPLETE")
        return

    all_good = True

    for name, command in steps:
        ok, _ = run_step(name, command)
        if not ok:
            all_good = False
            break

    if all_good:
        write_log("OVERNIGHT WORKFLOW COMPLETE")
    else:
        write_log("OVERNIGHT WORKFLOW FAILED")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
