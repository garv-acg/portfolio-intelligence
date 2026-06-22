from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ConstructionConfig:
    max_position_weight: float = 0.22
    max_sector_weight: float = 0.40
    min_position_weight: float = 0.02
    rebalance_threshold: float = 0.025
    volatility_floor: float = 12.0
    volatility_cap: float = 65.0


def _clean_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _normalize_weights(df: pd.DataFrame, weight_col: str = "target_weight") -> pd.DataFrame:
    df = df.copy()
    total = df[weight_col].sum()
    if total <= 0:
        if len(df) > 0:
            df[weight_col] = 1.0 / len(df)
        return df
    df[weight_col] = df[weight_col] / total
    return df


def _apply_position_caps(df: pd.DataFrame, config: ConstructionConfig) -> pd.DataFrame:
    df = df.copy()
    if df.empty:
        return df

    for _ in range(25):
        over = df["target_weight"] > config.max_position_weight
        if not over.any():
            break

        excess = (df.loc[over, "target_weight"] - config.max_position_weight).sum()
        df.loc[over, "target_weight"] = config.max_position_weight

        under = df["target_weight"] < config.max_position_weight
        if not under.any() or excess <= 0:
            break

        under_total = df.loc[under, "target_weight"].sum()
        if under_total <= 0:
            break

        df.loc[under, "target_weight"] += (df.loc[under, "target_weight"] / under_total) * excess

    return _normalize_weights(df)


def _apply_sector_caps(df: pd.DataFrame, config: ConstructionConfig) -> pd.DataFrame:
    df = df.copy()
    if df.empty or "sector" not in df.columns:
        return df

    df["sector"] = df["sector"].fillna("Unclassified").astype(str)

    for _ in range(25):
        sector_weights = df.groupby("sector")["target_weight"].sum()
        over_sectors = sector_weights[sector_weights > config.max_sector_weight]

        if over_sectors.empty:
            break

        total_excess = 0.0

        for sector, sector_weight in over_sectors.items():
            sector_mask = df["sector"] == sector
            excess = sector_weight - config.max_sector_weight
            total_excess += excess
            scale = config.max_sector_weight / sector_weight
            df.loc[sector_mask, "target_weight"] *= scale

        under_mask = ~df["sector"].isin(over_sectors.index)
        if not under_mask.any() or total_excess <= 0:
            break

        under_total = df.loc[under_mask, "target_weight"].sum()
        if under_total <= 0:
            break

        df.loc[under_mask, "target_weight"] += (df.loc[under_mask, "target_weight"] / under_total) * total_excess
        df = _apply_position_caps(df, config)

    return _normalize_weights(df)


def _apply_min_weight(df: pd.DataFrame, config: ConstructionConfig) -> pd.DataFrame:
    df = df.copy()
    if df.empty:
        return df

    tiny = df["target_weight"] < config.min_position_weight
    if tiny.any() and len(df) > 1:
        removed = df.loc[tiny, "target_weight"].sum()
        df.loc[tiny, "target_weight"] = 0.0

        keep = df["target_weight"] > 0
        if keep.any():
            keep_total = df.loc[keep, "target_weight"].sum()
            if keep_total > 0:
                df.loc[keep, "target_weight"] += (df.loc[keep, "target_weight"] / keep_total) * removed

    return _normalize_weights(df)


def _sector_for_ticker(ticker: str, current_sector: str | None = None) -> str:
    fallback_sector_map = {
        "AAPL": "Information Technology",
        "MSFT": "Information Technology",
        "NVDA": "Information Technology",
        "AVGO": "Information Technology",
        "GOOGL": "Communication Services",
        "GOOG": "Communication Services",
        "META": "Communication Services",
        "SPOT": "Communication Services",
        "AMZN": "Consumer Discretionary",
        "TSLA": "Consumer Discretionary",
        "GE": "Industrials",
        "JPM": "Financials",
        "BAC": "Financials",
        "XOM": "Energy",
        "CVX": "Energy",
    }

    if current_sector is not None:
        sector = str(current_sector).strip()
        if sector and sector.lower() not in {"none", "nan", "unclassified"}:
            return sector

    return fallback_sector_map.get(str(ticker).upper().strip(), "Other")

def _extract_factor_df(factor_signals: list[dict[str, Any]]) -> pd.DataFrame:
    if not factor_signals:
        return pd.DataFrame()

    df = pd.DataFrame(factor_signals)
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    df["composite_score"] = df["composite_score"].apply(lambda x: _clean_float(x, 50.0))
    df["volatility_21d_pct"] = df["volatility_21d_pct"].apply(lambda x: _clean_float(x, 30.0))
    df["drawdown_pct"] = df["drawdown_pct"].apply(lambda x: _clean_float(x, 0.0))
    df["relative_strength_21d_pct"] = df["relative_strength_21d_pct"].apply(lambda x: _clean_float(x, 0.0))
    if "signal_label" not in df.columns:
        df["signal_label"] = "N/A"
    return df


def _extract_portfolio_df(portfolio_snapshot: list[dict[str, Any]]) -> pd.DataFrame:
    if not portfolio_snapshot:
        return pd.DataFrame()

    df = pd.DataFrame(portfolio_snapshot)
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()

    if "market_value" in df.columns:
        df["value"] = df["market_value"].apply(_clean_float)
    elif "value" in df.columns:
        df["value"] = df["value"].apply(_clean_float)
    else:
        df["value"] = 0.0

    if "sector" not in df.columns:
        df["sector"] = None

    fallback_sector_map = {
        "AAPL": "Information Technology",
        "MSFT": "Information Technology",
        "NVDA": "Information Technology",
        "AVGO": "Information Technology",
        "GOOGL": "Communication Services",
        "META": "Communication Services",
        "AMZN": "Consumer Discretionary",
        "TSLA": "Consumer Discretionary",
        "GE": "Industrials",
        "SPOT": "Communication Services",
        "JPM": "Financials",
        "XOM": "Energy",
    }

    df["sector"] = (
        df["sector"]
        .astype(str)
        .replace({"None": "", "nan": "", "": None})
    )

    df["sector"] = df.apply(
        lambda row: (
            row["sector"]
            if row["sector"] not in [None, "", "Unclassified"]
            else fallback_sector_map.get(row["ticker"], "Other")
        ),
        axis=1,
    )

    total = df["value"].sum()
    df["current_weight"] = df["value"] / total if total > 0 else 0.0

    return df[["ticker", "sector", "value", "current_weight"]]


def build_portfolio_construction(
    portfolio_snapshot: list[dict[str, Any]],
    factor_signals: list[dict[str, Any]],
    config: ConstructionConfig | None = None,
) -> dict[str, Any]:
    config = config or ConstructionConfig()

    portfolio = _extract_portfolio_df(portfolio_snapshot)
    factors = _extract_factor_df(factor_signals)

    if portfolio.empty or factors.empty:
        return {
            "status": "Unavailable",
            "message": "Portfolio construction requires both portfolio snapshot and factor signals.",
            "targets": [],
            "trades": [],
            "sector_targets": [],
            "summary": {},
        }

    df = portfolio.merge(factors, on="ticker", how="left")

    df["sector"] = df.apply(
        lambda row: _sector_for_ticker(row["ticker"], row.get("sector")),
        axis=1,
    )

    df["composite_score"] = df["composite_score"].fillna(50.0)
    df["volatility_21d_pct"] = df["volatility_21d_pct"].fillna(30.0)

    df["volatility_adjusted_score"] = df["composite_score"] / df["volatility_21d_pct"].clip(
        lower=config.volatility_floor,
        upper=config.volatility_cap,
    )

    df["target_weight"] = df["volatility_adjusted_score"].clip(lower=0.0)
    df = _normalize_weights(df, "target_weight")
    df = _apply_position_caps(df, config)
    df = _apply_sector_caps(df, config)
    df = _apply_min_weight(df, config)
    df = _apply_position_caps(df, config)
    df = _apply_sector_caps(df, config)

    portfolio_value = float(df["value"].sum())

    df["target_value"] = df["target_weight"] * portfolio_value
    df["trade_value"] = df["target_value"] - df["value"]
    df["weight_drift"] = df["target_weight"] - df["current_weight"]

    def action(row: pd.Series) -> str:
        drift = float(row["weight_drift"])
        if abs(drift) < config.rebalance_threshold:
            return "HOLD"
        return "BUY" if drift > 0 else "SELL"

    df["action"] = df.apply(action, axis=1)
    df["target_weight_pct"] = df["target_weight"] * 100.0
    df["current_weight_pct"] = df["current_weight"] * 100.0
    df["weight_drift_pct"] = df["weight_drift"] * 100.0

    trades = df[df["action"] != "HOLD"].copy()

    sector_targets = (
        df.groupby("sector", as_index=False)
        .agg(
            current_weight=("current_weight", "sum"),
            target_weight=("target_weight", "sum"),
            current_value=("value", "sum"),
            target_value=("target_value", "sum"),
        )
        .sort_values("target_weight", ascending=False)
    )

    sector_targets["current_weight_pct"] = sector_targets["current_weight"] * 100.0
    sector_targets["target_weight_pct"] = sector_targets["target_weight"] * 100.0
    sector_targets["weight_drift_pct"] = (sector_targets["target_weight"] - sector_targets["current_weight"]) * 100.0

    estimated_portfolio_vol = float((df["target_weight"] * df["volatility_21d_pct"]).sum())

    summary = {
        "portfolio_value": portfolio_value,
        "positions": int(len(df)),
        "rebalance_trades": int(len(trades)),
        "estimated_portfolio_volatility_pct": estimated_portfolio_vol,
        "max_position_weight_pct": float(df["target_weight_pct"].max()) if not df.empty else 0.0,
        "max_sector_weight_pct": float(sector_targets["target_weight_pct"].max()) if not sector_targets.empty else 0.0,
        "turnover_pct": float(trades["trade_value"].abs().sum() / portfolio_value * 100.0) if portfolio_value > 0 else 0.0,
    }

    target_cols = [
        "ticker",
        "sector",
        "signal_label",
        "composite_score",
        "volatility_21d_pct",
        "relative_strength_21d_pct",
        "drawdown_pct",
        "current_weight_pct",
        "target_weight_pct",
        "weight_drift_pct",
        "value",
        "target_value",
        "trade_value",
        "action",
    ]

    return {
        "status": "Ready",
        "message": "Signal-driven, volatility-scaled portfolio construction completed.",
        "targets": df[target_cols].sort_values("target_weight_pct", ascending=False).to_dict("records"),
        "trades": trades[target_cols].sort_values("trade_value", ascending=False).to_dict("records"),
        "sector_targets": sector_targets.to_dict("records"),
        "summary": summary,
        "config": config.__dict__,
    }
