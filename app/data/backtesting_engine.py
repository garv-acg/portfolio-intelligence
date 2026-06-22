
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
import math

import pandas as pd
import requests


@dataclass(frozen=True)
class BacktestConfig:
    benchmark: str = "SPY"
    lookback_days: int = 180
    rebalance_frequency_days: int = 21
    transaction_cost_bps: float = 10.0
    initial_capital: float = 10000.0


def _download_prices(ticker: str, lookback_days: int = 365) -> pd.Series:
    end = int(datetime.now(timezone.utc).timestamp())
    start = int((datetime.now(timezone.utc) - timedelta(days=lookback_days + 10)).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

    try:
        response = requests.get(
            url,
            params={"period1": start, "period2": end, "interval": "1d", "events": "history"},
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

        idx = pd.to_datetime(timestamps, unit="s", utc=True).normalize()
        return pd.Series(closes, index=idx, dtype="float64").dropna().tail(lookback_days)

    except Exception:
        return pd.Series(dtype=float)


def _annualized_return(returns: pd.Series) -> float:
    returns = returns.dropna()
    if returns.empty:
        return 0.0
    cumulative = float((1 + returns).prod())
    years = len(returns) / 252
    if years <= 0 or cumulative <= 0:
        return 0.0
    return (cumulative ** (1 / years) - 1) * 100


def _annualized_volatility(returns: pd.Series) -> float:
    returns = returns.dropna()
    if len(returns) < 2:
        return 0.0
    return float(returns.std() * math.sqrt(252) * 100)


def _sharpe(returns: pd.Series) -> float:
    returns = returns.dropna()
    if len(returns) < 2 or returns.std() == 0:
        return 0.0
    return float((returns.mean() / returns.std()) * math.sqrt(252))


def _sortino(returns: pd.Series) -> float:
    returns = returns.dropna()
    downside = returns[returns < 0]
    if len(returns) < 2 or downside.std() == 0 or pd.isna(downside.std()):
        return 0.0
    return float((returns.mean() / downside.std()) * math.sqrt(252))


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    dd = equity / equity.cummax() - 1
    return float(dd.min() * 100)


def _beta_alpha(strategy_returns: pd.Series, benchmark_returns: pd.Series) -> tuple[float, float]:
    df = pd.concat([strategy_returns.rename("strategy"), benchmark_returns.rename("benchmark")], axis=1).dropna()
    if len(df) < 5 or df["benchmark"].var() == 0:
        return 0.0, 0.0
    beta = float(df["strategy"].cov(df["benchmark"]) / df["benchmark"].var())
    daily_alpha = float(df["strategy"].mean() - beta * df["benchmark"].mean())
    return beta, daily_alpha * 252 * 100


def _pct_change(series: pd.Series, periods: int) -> float:
    if len(series) <= periods:
        return 0.0
    try:
        return float((series.iloc[-1] / series.iloc[-periods - 1] - 1) * 100)
    except Exception:
        return 0.0


def _factor_scores(ticker: str, series: pd.Series, benchmark: pd.Series) -> dict[str, float | str]:
    returns = series.pct_change().dropna()
    mom21 = _pct_change(series, 21)
    mom63 = _pct_change(series, 63)
    bench21 = _pct_change(benchmark, 21)
    rel = mom21 - bench21
    vol = float(returns.tail(21).std() * math.sqrt(252) * 100) if len(returns) > 2 else 30.0

    high = series.tail(63).max() if not series.empty else 0
    dd = float((series.iloc[-1] / high - 1) * 100) if high and high > 0 else 0.0

    momentum_score = max(0, min(100, 50 + mom21 * 2 + mom63))
    volatility_score = max(0, min(100, 100 - vol))
    relative_strength_score = max(0, min(100, 50 + rel * 3))
    drawdown_score = max(0, min(100, 100 + dd * 4))

    composite = (
        momentum_score * 0.35
        + volatility_score * 0.20
        + relative_strength_score * 0.25
        + drawdown_score * 0.20
    )

    return {
        "ticker": ticker,
        "momentum_score": momentum_score,
        "volatility_score": volatility_score,
        "relative_strength_score": relative_strength_score,
        "drawdown_score": drawdown_score,
        "composite_score": composite,
    }


def _construct_weights(i: int, prices: pd.DataFrame, benchmark: pd.Series, tickers: list[str]) -> tuple[dict[str, float], list[dict[str, Any]]]:
    rows = []
    for ticker in tickers:
        history = prices[ticker].iloc[: i + 1].dropna()
        bench_history = benchmark.iloc[: i + 1].dropna()
        if len(history) < 30:
            row = {
                "ticker": ticker,
                "momentum_score": 50.0,
                "volatility_score": 50.0,
                "relative_strength_score": 50.0,
                "drawdown_score": 50.0,
                "composite_score": 50.0,
            }
        else:
            row = _factor_scores(ticker, history, bench_history)
        rows.append(row)

    df = pd.DataFrame(rows)
    df["target_weight"] = df["composite_score"].clip(lower=0)
    if df["target_weight"].sum() <= 0:
        df["target_weight"] = 1 / len(df)
    else:
        df["target_weight"] = df["target_weight"] / df["target_weight"].sum()

    max_weight = 0.22
    for _ in range(20):
        over = df["target_weight"] > max_weight
        if not over.any():
            break
        excess = (df.loc[over, "target_weight"] - max_weight).sum()
        df.loc[over, "target_weight"] = max_weight
        under = df["target_weight"] < max_weight
        under_total = df.loc[under, "target_weight"].sum()
        if under_total <= 0:
            break
        df.loc[under, "target_weight"] += df.loc[under, "target_weight"] / under_total * excess

    df["target_weight"] = df["target_weight"] / df["target_weight"].sum()
    weights = dict(zip(df["ticker"], df["target_weight"]))
    return weights, df.to_dict("records")


def run_backtest(tickers: list[str], config: BacktestConfig | None = None) -> dict[str, Any]:
    config = config or BacktestConfig()
    tickers = [t.upper().strip() for t in tickers if t]

    if not tickers:
        return {"status": "Unavailable", "message": "No tickers supplied."}

    price_map = {t: _download_prices(t, config.lookback_days) for t in tickers}
    price_map = {t: s for t, s in price_map.items() if not s.empty}
    benchmark = _download_prices(config.benchmark, config.lookback_days)

    if not price_map or benchmark.empty:
        return {"status": "Unavailable", "message": "Could not download price data."}

    prices = pd.DataFrame(price_map).dropna(how="all").ffill().dropna()
    benchmark = benchmark.reindex(prices.index).ffill().dropna()
    prices = prices.reindex(benchmark.index).ffill().dropna()

    tickers = list(prices.columns)
    if len(prices) < 40:
        return {"status": "Unavailable", "message": "Not enough observations."}

    returns = prices.pct_change().fillna(0.0)
    bench_returns = benchmark.pct_change().fillna(0.0)

    weights = {t: 1 / len(tickers) for t in tickers}
    strategy_value = config.initial_capital
    benchmark_value = config.initial_capital
    cost_rate = config.transaction_cost_bps / 10000

    equity_rows = []
    turnover_rows = []
    weight_rows = []
    factor_rows_all = []

    for i, date in enumerate(prices.index):
        if i > 0:
            daily_ret = sum(weights.get(t, 0) * returns.iloc[i].get(t, 0) for t in tickers)
            strategy_value *= 1 + daily_ret
            benchmark_value *= 1 + bench_returns.iloc[i]

        if i >= 30 and i % config.rebalance_frequency_days == 0:
            target_weights, factor_rows = _construct_weights(i, prices, benchmark, tickers)
            turnover = sum(abs(target_weights.get(t, 0) - weights.get(t, 0)) for t in tickers)
            cost = strategy_value * turnover * cost_rate
            strategy_value -= cost

            turnover_rows.append({
                "date": str(date.date()),
                "turnover_pct": turnover * 100,
                "transaction_cost_$": cost,
                "transaction_cost_bps": config.transaction_cost_bps,
            })

            for row in factor_rows:
                row["date"] = str(date.date())
                factor_rows_all.append(row)

            weights = target_weights

        for ticker, weight in weights.items():
            weight_rows.append({"date": str(date.date()), "ticker": ticker, "weight_pct": weight * 100})

        equity_rows.append({
            "date": str(date.date()),
            "strategy_value": strategy_value,
            "benchmark_value": benchmark_value,
        })

    equity = pd.DataFrame(equity_rows)
    equity["strategy_return"] = equity["strategy_value"].pct_change().fillna(0.0)
    equity["benchmark_return"] = equity["benchmark_value"].pct_change().fillna(0.0)
    equity["active_return"] = equity["strategy_return"] - equity["benchmark_return"]

    beta, alpha = _beta_alpha(equity["strategy_return"], equity["benchmark_return"])

    turnover_df = pd.DataFrame(turnover_rows)
    factor_df = pd.DataFrame(factor_rows_all)

    if not factor_df.empty:
        factor_contribution = factor_df.groupby("ticker", as_index=False).agg(
            avg_composite_score=("composite_score", "mean"),
            avg_momentum_score=("momentum_score", "mean"),
            avg_volatility_score=("volatility_score", "mean"),
            avg_relative_strength_score=("relative_strength_score", "mean"),
            avg_drawdown_score=("drawdown_score", "mean"),
        ).sort_values("avg_composite_score", ascending=False)
    else:
        factor_contribution = pd.DataFrame()

    metrics = {
        "strategy_total_return_pct": float((equity["strategy_value"].iloc[-1] / equity["strategy_value"].iloc[0] - 1) * 100),
        "benchmark_total_return_pct": float((equity["benchmark_value"].iloc[-1] / equity["benchmark_value"].iloc[0] - 1) * 100),
        "active_return_pct": float((equity["strategy_value"].iloc[-1] / equity["strategy_value"].iloc[0] - equity["benchmark_value"].iloc[-1] / equity["benchmark_value"].iloc[0]) * 100),
        "strategy_annualized_return_pct": _annualized_return(equity["strategy_return"]),
        "benchmark_annualized_return_pct": _annualized_return(equity["benchmark_return"]),
        "strategy_volatility_pct": _annualized_volatility(equity["strategy_return"]),
        "benchmark_volatility_pct": _annualized_volatility(equity["benchmark_return"]),
        "sharpe_ratio": _sharpe(equity["strategy_return"]),
        "sortino_ratio": _sortino(equity["strategy_return"]),
        "max_drawdown_pct": _max_drawdown(equity["strategy_value"]),
        "benchmark_max_drawdown_pct": _max_drawdown(equity["benchmark_value"]),
        "beta_to_benchmark": beta,
        "annualized_alpha_pct": alpha,
        "total_transaction_cost_$": float(turnover_df["transaction_cost_$"].sum()) if not turnover_df.empty else 0.0,
        "avg_turnover_pct": float(turnover_df["turnover_pct"].mean()) if not turnover_df.empty else 0.0,
        "rebalance_count": int(len(turnover_rows)),
    }

    return {
        "status": "Ready",
        "message": "Backtest completed.",
        "config": config.__dict__,
        "metrics": metrics,
        "equity_curve": equity[["date", "strategy_value", "benchmark_value"]].to_dict("records"),
        "returns": equity[["date", "strategy_return", "benchmark_return", "active_return"]].to_dict("records"),
        "turnover": turnover_rows,
        "weight_history": weight_rows,
        "factor_history": factor_rows_all,
        "factor_contribution": factor_contribution.to_dict("records"),
    }
