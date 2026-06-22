from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import math
import pandas as pd
import requests


SECTOR_ETF_MAP = {
    "Information Technology": "XLK",
    "Communication Services": "XLC",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Energy": "XLE",
    "Utilities": "XLU",
    "Materials": "XLB",
    "Real Estate": "XLRE",
}


FALLBACK_METADATA = {
    "AAPL": {"sector": "Information Technology", "market_cap_tier": "Mega Cap", "style": "Growth", "region": "United States", "beta": 1.20},
    "NVDA": {"sector": "Information Technology", "market_cap_tier": "Mega Cap", "style": "Growth", "region": "United States", "beta": 1.75},
    "AVGO": {"sector": "Information Technology", "market_cap_tier": "Mega Cap", "style": "Growth", "region": "United States", "beta": 1.15},
    "AMZN": {"sector": "Consumer Discretionary", "market_cap_tier": "Mega Cap", "style": "Growth", "region": "United States", "beta": 1.30},
    "SPOT": {"sector": "Communication Services", "market_cap_tier": "Large Cap", "style": "Growth", "region": "International", "beta": 1.60},
    "GE":   {"sector": "Industrials",            "market_cap_tier": "Large Cap", "style": "Value / Cyclical", "region": "United States", "beta": 1.20},
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _download_chart(ticker: str, lookback_days: int = 400) -> pd.DataFrame:
    end   = int(datetime.now(timezone.utc).timestamp())
    start = int((datetime.now(timezone.utc) - timedelta(days=lookback_days + 10)).timestamp())
    params = {
        "period1":  start,
        "period2":  end,
        "interval": "1d",
        "events":   "history",
    }
    headers = {"User-Agent": "Mozilla/5.0"}

    # Try query1 first, fall back to query2 on any failure or rate-limit
    hosts = [
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
        f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}",
    ]

    for url in hosts:
        try:
            r = requests.get(url, params=params, timeout=25, headers=headers)
            if r.status_code != 200:
                continue

            data   = r.json()
            result = data.get("chart", {}).get("result", [])
            if not result:
                continue

            payload    = result[0]
            timestamps = payload.get("timestamp", [])
            quote      = payload.get("indicators", {}).get("quote", [{}])[0]

            if not timestamps:
                continue

            df = pd.DataFrame({
                "date":   pd.to_datetime(timestamps, unit="s", utc=True).normalize(),
                "open":   quote.get("open",   []),
                "high":   quote.get("high",   []),
                "low":    quote.get("low",    []),
                "close":  quote.get("close",  []),
                "volume": quote.get("volume", []),
            })

            df = df.dropna(subset=["close"]).set_index("date").sort_index()
            result_df = df.tail(lookback_days)

            # Validate we got real, non-NaN close data
            if result_df.empty or result_df["close"].isna().all():
                continue

            return result_df

        except Exception:
            continue

    return pd.DataFrame()


def _download_quote_summary(ticker: str) -> dict[str, Any]:
    hosts = [
        f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}",
        f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}",
    ]

    for url in hosts:
        try:
            r = requests.get(
                url,
                params={"modules": "assetProfile,summaryDetail,price,defaultKeyStatistics"},
                timeout=15,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if r.status_code != 200:
                continue

            data   = r.json()
            result = data.get("quoteSummary", {}).get("result", [])
            if not result:
                continue

            root    = result[0]
            profile = root.get("assetProfile", {}) or {}
            summary = root.get("summaryDetail", {}) or {}
            price   = root.get("price", {}) or {}
            stats   = root.get("defaultKeyStatistics", {}) or {}

            def raw(obj: dict[str, Any], key: str, default: Any = None) -> Any:
                value = obj.get(key, default)
                if isinstance(value, dict) and "raw" in value:
                    return value["raw"]
                return value

            return {
                "sector":      profile.get("sector"),
                "industry":    profile.get("industry"),
                "country":     profile.get("country"),
                "market_cap":  raw(price, "marketCap"),
                "beta":        raw(summary, "beta"),
                "forward_pe":  raw(summary, "forwardPE"),
                "trailing_pe": raw(summary, "trailingPE"),
                "price_to_book": raw(stats, "priceToBook"),
            }

        except Exception:
            continue

    return {}


def _market_cap_tier(market_cap: float | None) -> str:
    if market_cap is None or market_cap <= 0:
        return "Unknown"
    if market_cap >= 200_000_000_000:
        return "Mega Cap"
    if market_cap >= 10_000_000_000:
        return "Large Cap"
    if market_cap >= 2_000_000_000:
        return "Mid Cap"
    return "Small Cap"


def _style_bucket(forward_pe: float | None, price_to_book: float | None, fallback: str = "Unknown") -> str:
    if forward_pe is None or forward_pe <= 0:
        return fallback
    if forward_pe >= 30:
        return "Growth"
    if forward_pe <= 18:
        return "Value"
    return "Blend"


def _pct_change(close: pd.Series, periods: int) -> float | None:
    if close is None or len(close) <= periods:
        return None
    try:
        result = float((close.iloc[-1] / close.iloc[-periods - 1] - 1) * 100)
        # Guard against NaN or Inf from bad price data
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except Exception:
        return None


def _distance_from_high(close: pd.Series, window: int) -> float | None:
    if close.empty:
        return None
    recent = close.tail(window)
    high = recent.max()
    if high <= 0:
        return None
    result = float((close.iloc[-1] / high - 1) * 100)
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _volume_ratio(df: pd.DataFrame, window: int = 30) -> float | None:
    if df.empty or "volume" not in df.columns or len(df) < 5:
        return None
    volume = df["volume"].dropna()
    if len(volume) < 5:
        return None
    latest = volume.iloc[-1]
    avg = volume.tail(window).mean()
    if avg <= 0:
        return None
    result = float(latest / avg)
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _get_item(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _earnings_days_map(earnings_calendar: list[Any]) -> dict[str, str]:
    out = {}
    today = datetime.now().date()
    for item in earnings_calendar or []:
        ticker   = str(_get_item(item, "ticker", "")).upper()
        date_raw = _get_item(item, "date")
        if not ticker or not date_raw:
            continue
        try:
            event_date = datetime.fromisoformat(str(date_raw)[:10]).date()
            days = (event_date - today).days
            if days >= 0:
                out[ticker] = f"{days}d"
        except Exception:
            continue
    return out


def _sec_filings_map(sec_filings: list[Any]) -> dict[str, str]:
    out = {}
    for filing in sec_filings or []:
        ticker = str(_get_item(filing, "ticker", "")).upper()
        if not ticker:
            continue
        form   = str(_get_item(filing, "form_type", "") or "")
        signal = str(_get_item(filing, "signal_type", "") or "")
        items  = _get_item(filing, "items_detected", []) or []
        if items:
            label = f"{form} / {', '.join(items)}"
        elif signal:
            label = f"{form} / {signal}"
        else:
            label = form or "Recent filing"
        if ticker not in out:
            out[ticker] = label
    return out


def build_holdings_change_monitor(
    holdings: list[Any],
    earnings_calendar: list[Any] | None = None,
    sec_filings: list[Any] | None = None,
    benchmark: str = "SPY",
) -> dict[str, Any]:
    earnings_map = _earnings_days_map(earnings_calendar or [])
    sec_map      = _sec_filings_map(sec_filings or [])

    spy_chart  = _download_chart(benchmark, lookback_days=400)
    spy_close  = spy_chart["close"] if not spy_chart.empty else pd.Series(dtype=float)
    spy_daily  = _pct_change(spy_close, 1)
    spy_weekly = _pct_change(spy_close, 5)

    rows = []

    for holding in holdings:
        ticker = str(_get_item(holding, "ticker", "")).upper().strip()
        shares = _safe_float(_get_item(holding, "shares", 0.0))

        if not ticker:
            continue

        fallback = FALLBACK_METADATA.get(ticker, {})
        chart    = _download_chart(ticker, lookback_days=400)
        quote    = _download_quote_summary(ticker)

        close        = chart["close"] if not chart.empty else pd.Series(dtype=float)
        latest_price = float(close.iloc[-1]) if not close.empty else None

        # If price data is completely unavailable, skip rather than emit NaN rows
        if latest_price is None or math.isnan(latest_price):
            latest_price = None

        sector     = quote.get("sector") or fallback.get("sector") or "Other"
        sector_etf = SECTOR_ETF_MAP.get(sector)
        sector_weekly = None

        if sector_etf:
            sector_chart = _download_chart(sector_etf, lookback_days=30)
            if not sector_chart.empty:
                sector_weekly = _pct_change(sector_chart["close"], 5)

        daily  = _pct_change(close, 1)
        weekly = _pct_change(close, 5)

        market_cap      = quote.get("market_cap")
        market_cap_tier = _market_cap_tier(_safe_float(market_cap, 0.0)) if market_cap else fallback.get("market_cap_tier", "Unknown")

        beta  = quote.get("beta") or fallback.get("beta")
        style = _style_bucket(quote.get("forward_pe"), quote.get("price_to_book"), fallback=fallback.get("style", "Unknown"))

        country = quote.get("country") or fallback.get("region") or "Unknown"
        region  = "United States" if str(country).lower() in {"united states", "united states of america", "usa"} else "International"

        value = shares * latest_price if latest_price is not None else 0.0

        rows.append({
            "ticker":                    ticker,
            "sector":                    sector,
            "sector_etf":                sector_etf or "N/A",
            "latest_price":              latest_price,
            "shares":                    shares,
            "market_value":              value,
            "daily_move_pct":            daily,
            "weekly_move_pct":           weekly,
            "weekly_vs_spy_pct":         weekly - spy_weekly if weekly is not None and spy_weekly is not None else None,
            "weekly_vs_sector_etf_pct":  weekly - sector_weekly if weekly is not None and sector_weekly is not None else None,
            "earnings_proximity":        earnings_map.get(ticker, "None found"),
            "recent_sec_filing":         sec_map.get(ticker, "None found"),
            "volume_vs_30d_avg":         _volume_ratio(chart, 30),
            "distance_from_52w_high_pct": _distance_from_high(close, 252),
            "drawdown_from_63d_high_pct": _distance_from_high(close, 63),
            "market_cap_tier":           market_cap_tier,
            "style":                     style,
            "beta":                      beta,
            "region":                    region,
            "country":                   country,
        })

    df = pd.DataFrame(rows)

    if df.empty:
        return {"status": "Unavailable", "message": "No holdings data available.", "holdings": [], "exposure": {}}

    total_value = df["market_value"].sum()
    df["portfolio_weight_pct"] = df["market_value"] / total_value * 100 if total_value > 0 else 0.0

    exposure = build_portfolio_exposure_dashboard(df)

    return {
        "status":    "Ready",
        "message":   "Holdings change monitor completed.",
        "benchmark": benchmark,
        "holdings":  df.sort_values("portfolio_weight_pct", ascending=False).to_dict("records"),
        "exposure":  exposure,
    }


def build_portfolio_exposure_dashboard(holdings_df: pd.DataFrame) -> dict[str, Any]:
    df          = holdings_df.copy()
    total_value = df["market_value"].sum()
    if total_value <= 0:
        total_value = 1.0

    def weighted(col: str) -> pd.DataFrame:
        return (
            df.groupby(col, as_index=False)["market_value"]
            .sum()
            .assign(weight_pct=lambda x: x["market_value"] / total_value * 100)
            .sort_values("weight_pct", ascending=False)
        )

    top_3_weight   = float(df.sort_values("market_value", ascending=False).head(3)["market_value"].sum() / total_value * 100)
    max_single     = float(df["market_value"].max() / total_value * 100)
    df["beta_num"] = df["beta"].apply(lambda x: _safe_float(x, 1.0))
    port_beta      = float((df["market_value"] / total_value * df["beta_num"]).sum())

    return {
        "total_value":                float(total_value),
        "cash_pct":                   0.0,
        "single_name_concentration_pct": max_single,
        "top_3_concentration_pct":    top_3_weight,
        "portfolio_beta":             port_beta,
        "sector_exposure":            weighted("sector").to_dict("records"),
        "market_cap_exposure":        weighted("market_cap_tier").to_dict("records"),
        "style_exposure":             weighted("style").to_dict("records"),
        "region_exposure":            weighted("region").to_dict("records"),
    }