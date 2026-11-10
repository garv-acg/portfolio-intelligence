from __future__ import annotations

from fastapi import APIRouter

from app.data.earnings import get_upcoming_earnings
from app.data.factor_engine import build_factor_signals, factor_signals_as_dicts
from app.data.sec_filings import get_sec_filings
from server.shared import get_tickers

router = APIRouter()


@router.get("")
def factors():
    tickers = get_tickers()
    earnings = get_upcoming_earnings(tickers, days_ahead=30)
    sec = get_sec_filings(tickers, lookback_days=30, max_filings_per_ticker=3)
    signals = build_factor_signals(tickers, earnings_calendar=earnings, sec_filings=sec)
    return {"signals": factor_signals_as_dicts(signals)}


@router.get("/attribution")
def attribution(days: int | None = None):
    from app.data.factor_engine import cumulative_attribution

    df = cumulative_attribution(days=days)
    if df is None or df.empty:
        return {"rows": [], "note": "No attribution history yet — this table isn't populated by the live daily pipeline."}
    return {"rows": df.to_dict(orient="records")}
