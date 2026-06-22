from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from app.data.history_db import connect, init_history_db


@dataclass(frozen=True)
class FactorSignal:
    ticker: str
    momentum_5d_pct: float | None
    momentum_21d_pct: float | None
    momentum_63d_pct: float | None
    volatility_21d_pct: float | None
    relative_strength_21d_pct: float | None
    drawdown_pct: float | None
    earnings_flag: str
    sec_flag: str
    composite_score: float
    signal_label: str


def _get(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _download_prices(ticker: str, lookback_days: int = 140) -> pd.Series:
    end = int(datetime.now(timezone.utc).timestamp())
    start = int((datetime.now(timezone.utc) - timedelta(days=lookback_days)).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

    try:
        r = requests.get(
            url,
            params={"period1": start, "period2": end, "interval": "1d", "events": "history"},
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        r.raise_for_status()
        data = r.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return pd.Series(dtype=float)

        payload = result[0]
        timestamps = payload.get("timestamp", [])
        closes = payload.get("indicators", {}).get("quote", [{}])[0].get("close", [])

        if not timestamps or not closes:
            return pd.Series(dtype=float)

        idx = pd.to_datetime(timestamps, unit="s", utc=True).date
        return pd.Series(closes, index=pd.to_datetime(idx), dtype="float64").dropna()

    except Exception:
        return pd.Series(dtype=float)


def _pct_change(series: pd.Series, periods: int) -> float | None:
    if len(series) <= periods:
        return None
    try:
        return float((series.iloc[-1] / series.iloc[-periods - 1] - 1.0) * 100.0)
    except Exception:
        return None


def _volatility(series: pd.Series, window: int = 21) -> float | None:
    returns = series.pct_change().dropna()
    if len(returns) < 5:
        return None
    return float(returns.tail(window).std() * (252 ** 0.5) * 100.0)


def _drawdown(series: pd.Series, window: int = 63) -> float | None:
    if series.empty:
        return None
    recent = series.tail(window)
    high = recent.max()
    if high <= 0:
        return None
    return float((series.iloc[-1] / high - 1.0) * 100.0)


def _score_factor(value: float | None, low: float, high: float, invert: bool = False) -> float:
    if value is None:
        return 50.0
    score = (value - low) / (high - low) * 100.0
    score = max(0.0, min(100.0, score))
    return 100.0 - score if invert else score


def _event_score(earnings_flag: str, sec_flag: str) -> float:
    score = 50.0
    if earnings_flag != "None":
        score += 10.0
    if "Item 5.02" in sec_flag:
        score += 10.0
    elif sec_flag != "None":
        score += 6.0
    return max(0.0, min(100.0, score))


def _label(score: float) -> str:
    if score >= 75:
        return "Strong"
    if score >= 60:
        return "Constructive"
    if score >= 45:
        return "Neutral"
    if score >= 30:
        return "Weakening"
    return "Weak"


def _upcoming_earnings_flags(tickers: list[str], earnings_calendar: list[Any]) -> dict[str, str]:
    out = {ticker: "None" for ticker in tickers}
    today = datetime.now().date()

    for item in earnings_calendar or []:
        ticker = str(_get(item, "ticker", "")).upper()
        date_raw = _get(item, "date")
        if not ticker or not date_raw:
            continue
        try:
            event_date = datetime.fromisoformat(str(date_raw)[:10]).date()
            days = (event_date - today).days
            if 0 <= days <= 7:
                out[ticker] = f"Earnings within {days}d"
            elif 0 <= days <= 30:
                out[ticker] = f"Earnings within {days}d"
        except Exception:
            continue

    return out


def _sec_flags(tickers: list[str], sec_filings: list[Any]) -> dict[str, str]:
    out = {ticker: "None" for ticker in tickers}

    for item in sec_filings or []:
        ticker = str(_get(item, "ticker", "")).upper()
        if ticker not in out:
            continue
        items = _get(item, "items_detected", []) or []
        form = _get(item, "form_type", "")
        signal_type = _get(item, "signal_type", "")
        if items:
            out[ticker] = f"{form} {', '.join(items)}"
        elif form:
            out[ticker] = f"{form} {signal_type}".strip()

    return out


def build_factor_signals(
    tickers: list[str],
    earnings_calendar: list[Any] | None = None,
    sec_filings: list[Any] | None = None,
    benchmark: str = "^GSPC",
) -> list[FactorSignal]:
    tickers = [ticker.upper().strip() for ticker in tickers if ticker]
    benchmark_prices = _download_prices(benchmark)
    benchmark_21d = _pct_change(benchmark_prices, 21)

    earnings_flags = _upcoming_earnings_flags(tickers, earnings_calendar or [])
    sec_flags = _sec_flags(tickers, sec_filings or [])

    results: list[FactorSignal] = []

    for ticker in tickers:
        prices = _download_prices(ticker)
        mom_5d = _pct_change(prices, 5)
        mom_21d = _pct_change(prices, 21)
        mom_63d = _pct_change(prices, 63)
        vol_21d = _volatility(prices, 21)
        dd = _drawdown(prices, 63)

        relative_strength = None
        if mom_21d is not None and benchmark_21d is not None:
            relative_strength = mom_21d - benchmark_21d

        momentum_score = (
            _score_factor(mom_5d, -8, 8) * 0.25
            + _score_factor(mom_21d, -15, 15) * 0.45
            + _score_factor(mom_63d, -25, 25) * 0.30
        )
        volatility_score = _score_factor(vol_21d, 15, 60, invert=True)
        relative_score = _score_factor(relative_strength, -10, 10)
        drawdown_score = _score_factor(dd, -20, 0)
        event_factor_score = _event_score(earnings_flags.get(ticker, "None"), sec_flags.get(ticker, "None"))

        composite = (
            momentum_score * 0.35
            + volatility_score * 0.20
            + relative_score * 0.25
            + drawdown_score * 0.15
            + event_factor_score * 0.05
        )

        results.append(
            FactorSignal(
                ticker=ticker,
                momentum_5d_pct=mom_5d,
                momentum_21d_pct=mom_21d,
                momentum_63d_pct=mom_63d,
                volatility_21d_pct=vol_21d,
                relative_strength_21d_pct=relative_strength,
                drawdown_pct=dd,
                earnings_flag=earnings_flags.get(ticker, "None"),
                sec_flag=sec_flags.get(ticker, "None"),
                composite_score=float(composite),
                signal_label=_label(float(composite)),
            )
        )

    return sorted(results, key=lambda row: row.composite_score, reverse=True)


def save_factor_signals(run_id: str, signals: list[FactorSignal], db_path: Path = Path("data/history.db")) -> None:
    init_history_db(db_path)
    with connect(db_path) as conn:
        for signal in signals:
            data = signal.__dict__
            for name in [
                "momentum_5d_pct",
                "momentum_21d_pct",
                "momentum_63d_pct",
                "volatility_21d_pct",
                "relative_strength_21d_pct",
                "drawdown_pct",
            ]:
                conn.execute(
                    """
                    INSERT INTO factor_signals (
                        run_id, ticker, signal_name, signal_value,
                        signal_score, signal_direction, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        signal.ticker,
                        name,
                        data.get(name),
                        signal.composite_score,
                        signal.signal_label,
                        str(data),
                    ),
                )


def cumulative_attribution(days: int | None = None, db_path: Path = Path("data/history.db")) -> pd.DataFrame:
    init_history_db(db_path)
    query = """
        SELECT
            ticker,
            COUNT(*) AS observations,
            SUM(daily_pl) AS cumulative_daily_pl,
            AVG(contribution_pct) AS avg_contribution_pct,
            SUM(contribution_pct) AS cumulative_contribution_pct,
            AVG(move_pct) AS avg_move_pct,
            AVG(weight_pct) AS avg_weight_pct,
            MAX(daily_pl) AS best_daily_pl,
            MIN(daily_pl) AS worst_daily_pl
        FROM attribution
    """
    params: list[Any] = []
    if days is not None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        query += """
            WHERE run_id IN (
                SELECT run_id FROM runs WHERE created_at >= ?
            )
        """
        params.append(cutoff)

    query += """
        GROUP BY ticker
        ORDER BY cumulative_daily_pl DESC
    """

    with connect(db_path) as conn:
        return pd.read_sql_query(query, conn, params=params)


def factor_signals_as_dicts(signals: list[FactorSignal]) -> list[dict[str, Any]]:
    return [signal.__dict__ for signal in signals]
