from __future__ import annotations

from fastapi import APIRouter, Query

from app.data.earnings import get_upcoming_earnings
from app.data.market_workbench import (
    catalyst_calendar,
    exposure_dashboard,
    macro_dashboard,
    portfolio_drift,
    sec_diff,
    watchlist_monitor,
)
from app.data.sec_filings import get_sec_filings
from server.shared import get_holdings, get_tickers

router = APIRouter()


@router.get("/overview")
def overview():
    holdings = get_holdings()
    tickers = [h.ticker for h in holdings]
    earnings = get_upcoming_earnings(tickers, days_ahead=30)
    sec = get_sec_filings(tickers, lookback_days=30, max_filings_per_ticker=3)
    return {
        "catalysts": catalyst_calendar(tickers, earnings=earnings, sec_filings=sec, days=14),
        "sec_diff": sec_diff(sec_filings=sec),
        "portfolio_drift": portfolio_drift(holdings),
        "macro": macro_dashboard(),
        "exposure": exposure_dashboard(holdings),
    }


@router.get("/watchlist")
def watchlist(tickers: str = Query(..., description="Comma-separated tickers")):
    watch = [t.strip() for t in tickers.split(",") if t.strip()]
    earnings = get_upcoming_earnings(watch, days_ahead=30)
    sec = get_sec_filings(watch, lookback_days=30, max_filings_per_ticker=3)
    return watchlist_monitor(watch, earnings=earnings, sec_filings=sec, benchmark="SPY")
