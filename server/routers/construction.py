from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.data.earnings import get_upcoming_earnings
from app.data.factor_engine import build_factor_signals, factor_signals_as_dicts
from app.data.market_data import get_equity_snapshot
from app.data.portfolio_construction import ConstructionConfig, build_portfolio_construction
from app.data.sec_filings import get_sec_filings
from server.shared import get_holdings

router = APIRouter()


class ConstructionParams(BaseModel):
    max_position_weight: float = 0.22
    max_sector_weight: float = 0.40
    min_position_weight: float = 0.02
    rebalance_threshold: float = 0.025


@router.post("")
def run_construction(params: ConstructionParams):
    holdings = get_holdings()
    if not holdings:
        raise HTTPException(404, "No holdings configured")
    tickers = [h.ticker for h in holdings]
    snapshot = get_equity_snapshot(holdings)
    earnings = get_upcoming_earnings(tickers, days_ahead=30)
    sec = get_sec_filings(tickers, lookback_days=30, max_filings_per_ticker=3)
    factors = factor_signals_as_dicts(build_factor_signals(tickers, earnings_calendar=earnings, sec_filings=sec))

    config = ConstructionConfig(
        max_position_weight=params.max_position_weight,
        max_sector_weight=params.max_sector_weight,
        min_position_weight=params.min_position_weight,
        rebalance_threshold=params.rebalance_threshold,
    )
    return build_portfolio_construction(snapshot, factors, config=config)


class SaveRecommendations(BaseModel):
    trades: list[dict]


@router.post("/save-recommendations")
def save_recommendations(body: SaveRecommendations):
    from server.db import DatabaseUnavailable, init_db, save_rebalance_recommendations

    try:
        init_db()
        saved = save_rebalance_recommendations(body.trades)
    except DatabaseUnavailable as exc:
        raise HTTPException(503, "DATABASE_URL is not configured on this deployment yet") from exc
    return {"saved": saved}
