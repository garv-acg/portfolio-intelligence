import json
import subprocess
import sys
from pathlib import Path

PREFS = Path("data/users/demo/newsletter_preferences.json")
HTML = Path("output/hybrid_newsletter.html")

SECTION_TESTS = {
    "portfolio_snapshot": "Portfolio Snapshot",
    "visual_intelligence": "Visual Intelligence",
    "top_movers": "Top Movers",
    "portfolio_news": "Portfolio News",
    "market_update": "Market Update",
    "macro_snapshot": "Macro Snapshot",
    "economic_calendar": "Economic Calendar",
    "earnings_calendar": "Earnings Calendar",
    "sec_monitoring": "SEC Monitoring",
    "alerts": "Alerts",
    "global_developments": "Global Developments",
}

original = json.loads(PREFS.read_text())

import generate_hybrid_newsletter
generate_hybrid_newsletter.FAST_TEST_MODE = True

def run_generation():
    result = subprocess.run(
        [sys.executable, "generate_hybrid_newsletter.py"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit("Generation failed")

def html_contains(text):
    return text in HTML.read_text(encoding="utf-8")

try:
    print("NEWSLETTER PREFERENCES TEST\n")

    for key, heading in SECTION_TESTS.items():
        prefs = original.copy()
        prefs[key] = False
        PREFS.write_text(json.dumps(prefs, indent=2))

        run_generation()
        passed = not html_contains(f"<h2>{heading}</h2>")

        print(("PASS" if passed else "FAIL") + f" | {key} off hides {heading}")

    PREFS.write_text(json.dumps(original, indent=2))
    run_generation()

    print("\nRESTORED ORIGINAL PREFERENCES")
    print("Done.")

finally:
    PREFS.write_text(json.dumps(original, indent=2))
