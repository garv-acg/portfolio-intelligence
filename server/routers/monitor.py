from __future__ import annotations

from fastapi import APIRouter

from app.data.earnings import get_upcoming_earnings
from app.data.holdings_monitor import build_holdings_change_monitor
from app.data.sec_filings import get_sec_filings
from server.shared import get_holdings, get_tickers

router = APIRouter()


@router.get("")
def monitor():
    holdings = get_holdings()
    tickers = [h.ticker for h in holdings]
    earnings = get_upcoming_earnings(tickers, days_ahead=30)
    sec = get_sec_filings(tickers, lookback_days=30, max_filings_per_ticker=3)
    return build_holdings_change_monitor(holdings, earnings_calendar=earnings, sec_filings=sec, benchmark="SPY")
