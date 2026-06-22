from __future__ import annotations

from datetime import date, timedelta

import yfinance as yf


def get_upcoming_earnings(tickers: list[str], days_ahead: int = 14) -> list[dict]:
    """Best-effort earnings lookup. Yahoo can be incomplete; omit missing data."""
    today = date.today()
    end = today + timedelta(days=days_ahead)
    events: list[dict] = []

    for ticker in tickers:
        try:
            cal = yf.Ticker(ticker).calendar
            earnings_date = None

            if isinstance(cal, dict):
                earnings_date = cal.get("Earnings Date")
                if isinstance(earnings_date, list) and earnings_date:
                    earnings_date = earnings_date[0]

            if earnings_date is None:
                continue

            if hasattr(earnings_date, "date"):
                earnings_day = earnings_date.date()
            else:
                earnings_day = earnings_date

            if today <= earnings_day <= end:
                events.append({"ticker": ticker, "date": str(earnings_day), "source": "Yahoo Finance"})
        except Exception:
            continue

    return events
