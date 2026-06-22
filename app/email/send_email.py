from __future__ import annotations

import requests


def send_with_resend(api_key: str | None, email_from: str, email_to: str | None, subject: str, html: str) -> bool:
    if not api_key or not email_to:
        return False

    response = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"from": email_from, "to": [email_to], "subject": subject, "html": html},
        timeout=20,
    )
    response.raise_for_status()
    return True
