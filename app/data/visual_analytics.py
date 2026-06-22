from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests


@dataclass(frozen=True)
class VisualAnalytics:
    allocation: list[dict[str, Any]]
    sector_exposure: list[dict[str, Any]]
    top_contributors: list[dict[str, Any]]
    daily_attribution: list[dict[str, Any]]
    rolling_returns: list[dict[str, Any]]
    volatility_monitor: dict[str, Any]
    drawdown: list[dict[str, Any]]
    source_note: str


SECTOR_MAP: dict[str, str] = {
    "AAPL": "Information Technology",
    "AMZN": "Consumer Discretionary",
    "AVGO": "Information Technology",
    "GE": "Industrials",
    "NVDA": "Information Technology",
    "SPOT": "Communication Services",
    "MSFT": "Information Technology",
    "GOOGL": "Communication Services",
    "GOOG": "Communication Services",
    "META": "Communication Services",
    "TSLA": "Consumer Discretionary",
}


def _get(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _download_yahoo_prices(ticker: str, lookback_days: int = 120) -> pd.Series:
    end = int(datetime.now(timezone.utc).timestamp())
    start = int((datetime.now(timezone.utc) - timedelta(days=lookback_days)).timestamp())

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

    try:
        response = requests.get(
            url,
            params={
                "period1": start,
                "period2": end,
                "interval": "1d",
                "events": "history",
            },
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        data = response.json()

        result = data.get("chart", {}).get("result", [])
        if not result:
            return pd.Series(dtype=float)

        payload = result[0]
        timestamps = payload.get("timestamp", [])
        closes = payload.get("indicators", {}).get("quote", [{}])[0].get("close", [])

        if not timestamps or not closes:
            return pd.Series(dtype=float)

        dates = pd.to_datetime(timestamps, unit="s", utc=True).date
        series = pd.Series(closes, index=pd.to_datetime(dates), dtype="float64").dropna()
        series.name = ticker
        return series

    except Exception:
        return pd.Series(dtype=float)


def _portfolio_values_from_prices(holdings: list[Any], lookback_days: int = 120) -> pd.DataFrame:
    frames: list[pd.Series] = []

    for holding in holdings:
        ticker = str(_get(holding, "ticker", "")).upper().strip()
        shares = _to_float(_get(holding, "shares", 0.0))

        if not ticker or shares <= 0:
            continue

        prices = _download_yahoo_prices(ticker, lookback_days=lookback_days)

        if prices.empty:
            continue

        frames.append(prices * shares)

    if not frames:
        return pd.DataFrame()

    values = pd.concat(frames, axis=1).sort_index()
    values = values.ffill().dropna(how="all")
    return values


def _allocation_from_snapshot(portfolio_snapshot: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    total_value = sum(_to_float(_get(row, "market_value", _get(row, "value", 0.0))) for row in portfolio_snapshot)

    if total_value <= 0:
        return []

    for row in portfolio_snapshot:
        ticker = str(_get(row, "ticker", "")).upper()
        value = _to_float(_get(row, "market_value", _get(row, "value", 0.0)))
        weight = value / total_value if total_value else 0.0
        sector = SECTOR_MAP.get(ticker, "Unclassified")

        rows.append(
            {
                "ticker": ticker,
                "company": _get(row, "name", _get(row, "company", "")),
                "value": value,
                "weight": weight,
                "weight_pct": weight * 100.0,
                "sector": sector,
            }
        )

    return sorted(rows, key=lambda item: item["weight"], reverse=True)


def _sector_exposure(allocation: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sector_totals: dict[str, float] = {}

    for row in allocation:
        sector = row.get("sector") or "Unclassified"
        sector_totals[sector] = sector_totals.get(sector, 0.0) + float(row.get("value", 0.0))

    total = sum(sector_totals.values())

    if total <= 0:
        return []

    return sorted(
        [
            {
                "sector": sector,
                "value": value,
                "weight_pct": (value / total) * 100.0,
            }
            for sector, value in sector_totals.items()
        ],
        key=lambda item: item["weight_pct"],
        reverse=True,
    )


def _daily_attribution_from_snapshot(portfolio_snapshot: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    total_value = sum(_to_float(_get(row, "market_value", _get(row, "value", 0.0))) for row in portfolio_snapshot)

    for row in portfolio_snapshot:
        ticker = str(_get(row, "ticker", "")).upper()
        value = _to_float(_get(row, "market_value", _get(row, "value", 0.0)))
        daily_pl = _to_float(_get(row, "daily_pl", _get(row, "day_pl", 0.0)))
        move_pct = _to_float(_get(row, "day_change_pct", _get(row, "move_pct", 0.0)))
        weight = value / total_value if total_value else 0.0

        rows.append(
            {
                "ticker": ticker,
                "value": value,
                "daily_pl": daily_pl,
                "move_pct": move_pct,
                "weight_pct": weight * 100.0,
                "contribution_pct": (daily_pl / total_value) * 100.0 if total_value else 0.0,
                "sector": SECTOR_MAP.get(ticker, "Unclassified"),
            }
        )

    return sorted(rows, key=lambda item: abs(item["daily_pl"]), reverse=True)


def _rolling_returns(values: pd.DataFrame) -> list[dict[str, Any]]:
    if values.empty:
        return []

    portfolio_value = values.sum(axis=1).dropna()

    if len(portfolio_value) < 3:
        return []

    returns = portfolio_value.pct_change().dropna()
    cumulative = (1 + returns).cumprod() - 1
    rolling_5d = portfolio_value.pct_change(5)
    rolling_21d = portfolio_value.pct_change(21)

    out = []

    for date, value in portfolio_value.tail(45).items():
        out.append(
            {
                "date": date.date().isoformat(),
                "portfolio_value": float(value),
                "cumulative_return_pct": float(cumulative.get(date, 0.0) * 100.0) if date in cumulative.index else None,
                "rolling_5d_return_pct": float(rolling_5d.get(date) * 100.0) if pd.notna(rolling_5d.get(date)) else None,
                "rolling_21d_return_pct": float(rolling_21d.get(date) * 100.0) if pd.notna(rolling_21d.get(date)) else None,
            }
        )

    return out


def _volatility_monitor(values: pd.DataFrame) -> dict[str, Any]:
    if values.empty:
        return {
            "daily_volatility_pct": None,
            "annualized_volatility_pct": None,
            "realized_21d_volatility_pct": None,
            "latest_daily_return_pct": None,
            "status": "Insufficient price history",
        }

    portfolio_value = values.sum(axis=1).dropna()
    returns = portfolio_value.pct_change().dropna()

    if returns.empty:
        return {
            "daily_volatility_pct": None,
            "annualized_volatility_pct": None,
            "realized_21d_volatility_pct": None,
            "latest_daily_return_pct": None,
            "status": "Insufficient return history",
        }

    daily_vol = returns.std() * 100.0
    annualized_vol = returns.std() * (252 ** 0.5) * 100.0
    realized_21d = returns.tail(21).std() * (252 ** 0.5) * 100.0 if len(returns) >= 5 else None
    latest_return = returns.iloc[-1] * 100.0

    if annualized_vol >= 35:
        status = "Elevated"
    elif annualized_vol >= 20:
        status = "Moderate"
    else:
        status = "Contained"

    return {
        "daily_volatility_pct": float(daily_vol),
        "annualized_volatility_pct": float(annualized_vol),
        "realized_21d_volatility_pct": float(realized_21d) if realized_21d is not None else None,
        "latest_daily_return_pct": float(latest_return),
        "status": status,
    }


def _drawdown(values: pd.DataFrame) -> list[dict[str, Any]]:
    if values.empty:
        return []

    portfolio_value = values.sum(axis=1).dropna()

    if portfolio_value.empty:
        return []

    running_max = portfolio_value.cummax()
    drawdown = (portfolio_value / running_max - 1.0) * 100.0

    return [
        {
            "date": date.date().isoformat(),
            "portfolio_value": float(portfolio_value.loc[date]),
            "drawdown_pct": float(value),
        }
        for date, value in drawdown.tail(45).items()
    ]


def build_visual_analytics(
    holdings: list[Any],
    portfolio_snapshot: list[Any],
    lookback_days: int = 120,
) -> VisualAnalytics:
    allocation = _allocation_from_snapshot(portfolio_snapshot)
    sector_exposure = _sector_exposure(allocation)
    daily_attribution = _daily_attribution_from_snapshot(portfolio_snapshot)
    top_contributors = sorted(daily_attribution, key=lambda item: item["daily_pl"], reverse=True)

    values = _portfolio_values_from_prices(
        holdings=holdings,
        lookback_days=lookback_days,
    )

    rolling_returns = _rolling_returns(values)
    volatility_monitor = _volatility_monitor(values)
    drawdown = _drawdown(values)

    return VisualAnalytics(
        allocation=allocation,
        sector_exposure=sector_exposure,
        top_contributors=top_contributors,
        daily_attribution=daily_attribution,
        rolling_returns=rolling_returns,
        volatility_monitor=volatility_monitor,
        drawdown=drawdown,
        source_note="Visual analytics calculated from Yahoo Finance historical prices and current portfolio holdings.",
    )


def visual_analytics_as_dict(analytics: VisualAnalytics) -> dict[str, Any]:
    return analytics.__dict__
