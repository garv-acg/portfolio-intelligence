"""
main.py
───────
Single entry point for newsletter generation.

Run directly:
    python main.py

Or called via the Streamlit control centre's "Generate Newsletter" button.

All logic lives in generate_hybrid_newsletter.py.  This file is intentionally
thin so there is exactly ONE newsletter pipeline and ONE set of output files.
"""
from __future__ import annotations

from generate_hybrid_newsletter import build_and_save_newsletter


def main(send_email: bool = False) -> None:
    build_and_save_newsletter()

    if send_email:
        # Email delivery wired separately via send_newsletter.py
        print("Email delivery not configured — run send_newsletter.py directly.")


if __name__ == "__main__":
    main(send_email=False)