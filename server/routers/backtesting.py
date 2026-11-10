from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.data.backtesting_engine import BacktestConfig, run_backtest
from server.shared import get_tickers

router = APIRouter()


class BacktestParams(BaseModel):
    benchmark: str = "SPY"
    lookback_days: int = 180
    rebalance_frequency_days: int = 21
    transaction_cost_bps: float = 10.0
    initial_capital: float = 10000.0


@router.post("")
def backtest(params: BacktestParams):
    tickers = get_tickers()
    if not tickers:
        raise HTTPException(404, "No holdings configured")
    config = BacktestConfig(
        benchmark=params.benchmark.upper().strip(),
        lookback_days=params.lookback_days,
        rebalance_frequency_days=params.rebalance_frequency_days,
        transaction_cost_bps=params.transaction_cost_bps,
        initial_capital=params.initial_capital,
    )
    return run_backtest(tickers, config=config)
