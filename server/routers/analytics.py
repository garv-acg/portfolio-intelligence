from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.data.market_data import get_equity_snapshot
from app.data.visual_analytics import build_visual_analytics, visual_analytics_as_dict
from server.shared import get_holdings

router = APIRouter()


@router.get("")
def analytics():
    holdings = get_holdings()
    if not holdings:
        raise HTTPException(404, "No holdings configured")
    snapshot = get_equity_snapshot(holdings)
    result = build_visual_analytics(holdings, snapshot, lookback_days=120)
    return visual_analytics_as_dict(result)
