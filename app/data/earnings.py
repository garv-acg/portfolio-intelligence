from __future__ import annotations

import csv
import io
import os
from datetime import date, timedelta

import yfinance as yf


def _fetch_av_earnings(tickers: list[str], days_ahead: int) -> list[dict]:
    """Fetch upcoming earnings from Alpha Vantage earnings calendar CSV."""
    try:
        import requests
        key = os.getenv("ALPHAVANTAGE_API_KEY", "").strip()
        if not key:
            return []
        url = f"https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&horizon=3month&apikey={key}"
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return []
        ticker_set = {t.upper() for t in tickers}
        today = date.today()
        end = today + timedelta(days=days_ahead)
        events = []
        reader = csv.DictReader(io.StringIO(r.text))
        for row in reader:
            sym = str(row.get("symbol", "")).upper()
            if sym not in ticker_set:
                continue
            d_str = str(row.get("reportDate", ""))[:10]
            try:
                d = date.fromisoformat(d_str)
                if today <= d <= end:
                    events.append({"ticker": sym, "date": d_str, "source": "Alpha Vantage"})
            except Exception:
                continue
        return events
    except Exception:
        return []


def get_upcoming_earnings(tickers: list[str], days_ahead: int = 14) -> list[dict]:
    """Best-effort earnings lookup. Tries Yahoo Finance first, then Alpha Vantage."""
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

    # If Yahoo returned nothing for any ticker, fill gaps with Alpha Vantage
    found_tickers = {e["ticker"].upper() for e in events}
    missing = [t for t in tickers if t.upper() not in found_tickers]
    if missing:
        av_events = _fetch_av_earnings(missing, days_ahead)
        events.extend(av_events)

    return events


def get_earnings_preview(ticker: str) -> dict:
    """
    Best-effort earnings preview for a single ticker: consensus EPS estimate
    for the next report and the most recent quarter's actual vs estimate
    (beat/miss). Returns a dict with None values when data is unavailable —
    callers should render '—' rather than fail.
    """
    out = {
        "eps_estimate": None,
        "last_eps_actual": None,
        "last_eps_estimate": None,
        "last_surprise_pct": None,
        "revenue_estimate": None,
    }
    try:
        t = yf.Ticker(ticker)
        ed = t.earnings_dates
        if ed is None or ed.empty:
            return out

        today_ts = ed.index.tz_localize(None) if ed.index.tz is not None else ed.index
        import pandas as pd
        now = pd.Timestamp.now()

        future_rows = ed[ed.index.tz_localize(None) >= now] if ed.index.tz is not None else ed[ed.index >= now]
        past_rows   = ed[ed.index.tz_localize(None) <  now] if ed.index.tz is not None else ed[ed.index <  now]

        if not future_rows.empty:
            row = future_rows.iloc[-1]  # nearest upcoming (rows are descending)
            est_col = next((c for c in ["EPS Estimate"] if c in row.index), None)
            if est_col and pd.notna(row[est_col]):
                out["eps_estimate"] = float(row[est_col])

        if not past_rows.empty:
            row = past_rows.iloc[0]  # most recent past report
            if "Reported EPS" in row.index and pd.notna(row["Reported EPS"]):
                out["last_eps_actual"] = float(row["Reported EPS"])
            if "EPS Estimate" in row.index and pd.notna(row["EPS Estimate"]):
                out["last_eps_estimate"] = float(row["EPS Estimate"])
            if "Surprise(%)" in row.index and pd.notna(row["Surprise(%)"]):
                out["last_surprise_pct"] = float(row["Surprise(%)"]) * 100 if abs(float(row["Surprise(%)"])) < 1 else float(row["Surprise(%)"])
    except Exception:
        pass
    return out
