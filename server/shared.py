"""Small shared helpers used across server/routers/*.py."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import portfolio_store  # noqa: E402


@dataclass
class Holding:
    ticker: str
    shares: float
    cost_basis: float = 0.0
    name: str = ""

    def __post_init__(self):
        if not self.name:
            self.name = self.ticker


def get_holdings() -> list[Holding]:
    rows = portfolio_store.load_holdings()
    return [Holding(ticker=r["ticker"], shares=r["shares"], cost_basis=r.get("cost_basis", 0.0)) for r in rows]


def get_tickers() -> list[str]:
    return [h.ticker for h in get_holdings()]


SECTOR_FALLBACK = {
    "AAPL": "Information Technology", "MSFT": "Information Technology", "NVDA": "Information Technology",
    "AVGO": "Information Technology", "GOOGL": "Communication Services", "GOOG": "Communication Services",
    "META": "Communication Services", "SPOT": "Communication Services", "AMZN": "Consumer Discretionary",
    "TSLA": "Consumer Discretionary", "GE": "Industrials", "JPM": "Financials", "V": "Financials",
    "UNH": "Health Care", "XOM": "Energy",
}
