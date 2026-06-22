from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    project_root: Path = PROJECT_ROOT

    portfolio_file: Path = PROJECT_ROOT / "portfolio.yml"

    output_dir: Path = PROJECT_ROOT / "output"
    template_dir: Path = PROJECT_ROOT / "templates"
    logs_dir: Path = PROJECT_ROOT / "logs"

    # OpenAI
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY") or None
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # News / Market APIs
    newsapi_key: str | None = os.getenv("NEWSAPI_KEY") or None
    alphavantage_api_key: str | None = os.getenv("ALPHAVANTAGE_API_KEY") or None
    fred_api_key: str | None = os.getenv("FRED_API_KEY") or None
    fmp_api_key: str | None = os.getenv("FMP_API_KEY") or None

    # Email
    resend_api_key: str | None = os.getenv("RESEND_API_KEY") or None
    email_from: str = os.getenv(
        "EMAIL_FROM",
        "Market Brief <onboarding@resend.dev>",
    )
    email_to: str | None = os.getenv("EMAIL_TO") or None

    # Newsletter Controls
    max_articles_per_ticker: int = int(
        os.getenv("NEWSLETTER_MAX_ARTICLES_PER_TICKER", "3")
    )

    lookback_hours: int = int(
        os.getenv("NEWSLETTER_LOOKBACK_HOURS", "24")
    )


settings = Settings()

settings.output_dir.mkdir(parents=True, exist_ok=True)
settings.logs_dir.mkdir(parents=True, exist_ok=True)
