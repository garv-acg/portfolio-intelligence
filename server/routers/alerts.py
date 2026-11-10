from __future__ import annotations

from fastapi import APIRouter

from app.data.alert_engine import build_alerts
from app.data.earnings import get_upcoming_earnings
from app.data.holdings_monitor import build_holdings_change_monitor
from app.data.market_data import get_equity_snapshot
from app.data.sec_filings import get_sec_filings
from app.data.visual_analytics import build_visual_analytics, visual_analytics_as_dict
from server.shared import get_holdings

router = APIRouter()


@router.get("")
def alerts():
    """Recomputed live on every request — no persistence. Unlike the local
    Streamlit app (which reads a daily sqlite alert log written by the email
    pipeline), this endpoint has no access to that local file once deployed
    on Render, so it re-derives the same categories of alert directly from
    live data. One gap: regime-shift detection needs yesterday's regime
    value, which lives in a local-only history store — this endpoint always
    passes an empty regime, so "Regime Shift" alerts never fire here (they
    still fire in the daily email, which has that history)."""
    holdings = get_holdings()
    tickers = [h.ticker for h in holdings]
    earnings = get_upcoming_earnings(tickers, days_ahead=30)
    sec = get_sec_filings(tickers, lookback_days=30, max_filings_per_ticker=5)
    monitor = build_holdings_change_monitor(holdings, earnings_calendar=earnings, sec_filings=sec, benchmark="SPY")
    holdings_rows = monitor.get("holdings", [])

    snapshot = get_equity_snapshot(holdings)
    analytics = visual_analytics_as_dict(build_visual_analytics(holdings, snapshot, lookback_days=60))

    payload = {
        "portfolio_snapshot": [
            {"ticker": r.get("ticker", ""), "day_change_pct": r.get("daily_move_pct")} for r in holdings_rows
        ],
        "visual_analytics": analytics,
        "earnings_calendar": earnings,
        "sec_filings": sec,
        "cross_asset_regime": {},
    }
    alert_list = build_alerts(payload)
    rows = [
        {"alert_type": a.alert_type, "severity": a.severity, "ticker": a.ticker, "title": a.title, "message": a.message, "source": a.source}
        for a in alert_list
    ]
    return {
        "alerts": rows,
        "summary": {
            "total_alerts": len(rows),
            "high_severity_alerts": sum(1 for r in rows if r["severity"] == "High"),
        },
    }
