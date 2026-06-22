"""
run_newsletter.py
Called by launchd at 7 AM daily.
Generates the newsletter then sends it via Gmail.
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).parent
LOG_DIR = PROJECT / "logs"
LOG_DIR.mkdir(exist_ok=True)

def run(script):
    print(f"\n{'='*50}")
    print(f"Running: {script}  [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    print("="*50)
    result = subprocess.run(
        [sys.executable, str(PROJECT / script)],
        cwd=str(PROJECT),
    )
    if result.returncode != 0:
        print(f"ERROR: {script} failed with code {result.returncode}")
        return False
    return True

if __name__ == "__main__":
    print(f"Newsletter Agent — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if not run("main.py"):
        print("Generation failed. Email not sent.")
        sys.exit(1)
    if not run("send_newsletter.py"):
        print("Generated but email failed.")
        sys.exit(1)
    print("\nDone. Newsletter generated and sent.")
