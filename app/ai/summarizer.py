from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.ai.prompts import NEWSLETTER_USER_PROMPT, SYSTEM_PROMPT


def generate_ai_newsletter(briefing_data: dict[str, Any], api_key: str | None, model: str) -> str | None:
    if not api_key:
        return None

    client = OpenAI(api_key=api_key)
    prompt = NEWSLETTER_USER_PROMPT.format(briefing_data=json.dumps(briefing_data, indent=2, default=str))

    response = client.chat.completions.create(
        model=model,
        temperature=0.1,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    return response.choices[0].message.content
