from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Holding:
    ticker: str
    name: str | None = None
    shares: float | None = None
    cost_basis: float | None = None


def load_portfolio(path: Path) -> list[Holding]:
    if not path.exists():
        raise FileNotFoundError(f"Portfolio file not found: {path}")

    data: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    holdings_raw = data.get("holdings", [])

    holdings: list[Holding] = []
    for item in holdings_raw:
        ticker = str(item.get("ticker", "")).strip().upper()
        if not ticker:
            continue
        holdings.append(
            Holding(
                ticker=ticker,
                name=item.get("name"),
                shares=item.get("shares"),
                cost_basis=item.get("cost_basis"),
            )
        )
    return holdings
