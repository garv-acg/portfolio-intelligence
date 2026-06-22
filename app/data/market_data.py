from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests
import yfinance as yf

from app.config.settings import settings


@dataclass
class MarketMove:
    ticker: str
    name: str
    price: float | None
    previous_close: float | None
    day_change_pct: float | None
    status: str
    source: str
    as_of: str | None = None
    provider_symbol: str | None = None


CACHE_FILE = settings.project_root / "data_cache" / "price_cache.json"
CACHE_TTL_MINUTES = 60

TICKER_ALIASES: dict[str, list[str]] = {
    "BRK.B": ["BRK-B", "BRK.B"],
    "BRK-B": ["BRK-B", "BRK.B"],
    "BF.B": ["BF-B", "BF.B"],
    "BF-B": ["BF-B", "BF.B"],
    "GE": ["GE"],
    "GEHC": ["GEHC"],
    "GEV": ["GEV"],
    "SPOT": ["SPOT"],
    "AVGO": ["AVGO"],
    "GOOGL": ["GOOGL", "GOOG"],
    "GOOG": ["GOOG", "GOOGL"],
}

INDEX_TICKERS: dict[str, str] = {
    "^GSPC": "S&P 500",
    "^IXIC": "Nasdaq Composite",
    "^DJI": "Dow Jones Industrial Average",
    "^TNX": "10-Year Treasury Yield",
    "CL=F": "WTI Crude Oil",
    "GC=F": "Gold",
    "DX-Y.NYB": "US Dollar Index",
}


def normalize_ticker(ticker: str) -> str:
    ticker = str(ticker).strip().upper()
    ticker = ticker.replace("/", ".")
    return ticker


def candidate_tickers(ticker: str) -> list[str]:
    ticker = normalize_ticker(ticker)
    aliases = TICKER_ALIASES.get(ticker, [ticker])
    candidates: list[str] = []

    for item in [ticker, *aliases]:
        item = normalize_ticker(item)
        if item not in candidates:
            candidates.append(item)

    return candidates


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_cache_dir() -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_cache() -> dict[str, Any]:
    _ensure_cache_dir()
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache: dict[str, Any]) -> None:
    _ensure_cache_dir()
    CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _cache_is_fresh(as_of: str | None) -> bool:
    if not as_of:
        return False
    try:
        timestamp = datetime.fromisoformat(as_of)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - timestamp <= timedelta(minutes=CACHE_TTL_MINUTES)
    except Exception:
        return False


def _cache_keys_for_ticker(ticker: str) -> list[str]:
    keys = [normalize_ticker(ticker)]
    for candidate in candidate_tickers(ticker):
        if candidate not in keys:
            keys.append(candidate)
    return keys


def _get_cached_price(ticker: str, allow_stale: bool = False) -> dict[str, Any] | None:
    cache = _load_cache()

    for key in _cache_keys_for_ticker(ticker):
        item = cache.get(key)
        if not item:
            continue
        if not allow_stale and not _cache_is_fresh(item.get("as_of")):
            continue
        if item.get("price") is None:
            continue

        is_fresh = _cache_is_fresh(item.get("as_of"))
        return {
            "price": item.get("price"),
            "previous_close": item.get("previous_close"),
            "source": item.get("source", "Cache"),
            "provider_symbol": item.get("provider_symbol"),
            "as_of": item.get("as_of"),
            "is_cached": True,
            "is_stale": not is_fresh,
        }

    return None


def _write_cached_price(
    ticker: str,
    price: float | None,
    previous_close: float | None,
    source: str,
    provider_symbol: str | None = None,
) -> str | None:
    if price is None:
        return None

    cache = _load_cache()
    canonical = normalize_ticker(ticker)
    provider_symbol = normalize_ticker(provider_symbol or ticker)
    as_of = _now_iso()

    record = {
        "price": price,
        "previous_close": previous_close,
        "source": source,
        "provider_symbol": provider_symbol,
        "as_of": as_of,
    }

    cache[canonical] = record
    cache[provider_symbol] = record
    _save_cache(cache)
    return as_of


def _safe_pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return ((current - previous) / previous) * 100


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if hasattr(value, "iloc"):
            value = value.iloc[0]
        return float(value)
    except (TypeError, ValueError, IndexError):
        return None


def _fetch_yahoo(provider_symbol: str) -> tuple[float | None, float | None]:
    try:
        hist = yf.download(
            provider_symbol,
            period="5d",
            interval="1d",
            progress=False,
            auto_adjust=False,
            threads=False,
        )

        if hist is None or hist.empty:
            return None, None

        if isinstance(hist.columns, pd.MultiIndex):
            if "Close" not in hist.columns.get_level_values(0):
                return None, None
            closes = hist["Close"]
            if isinstance(closes, pd.DataFrame):
                closes = closes.iloc[:, 0]
        else:
            if "Close" not in hist.columns:
                return None, None
            closes = hist["Close"]

        closes = closes.dropna()
        if len(closes) < 2:
            return None, None

        return _to_float(closes.iloc[-1]), _to_float(closes.iloc[-2])

    except Exception:
        return None, None


def _fetch_alpha_vantage(provider_symbol: str) -> tuple[float | None, float | None]:
    api_key = settings.alphavantage_api_key
    if not api_key:
        return None, None

    if provider_symbol.startswith("^") or provider_symbol.endswith("=F") or provider_symbol == "DX-Y.NYB":
        return None, None

    try:
        response = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "TIME_SERIES_DAILY",
                "symbol": provider_symbol,
                "apikey": api_key,
                "outputsize": "compact",
            },
            timeout=15,
        )

        data = response.json()
        series = data.get("Time Series (Daily)")
        if not series:
            return None, None

        dates = sorted(series.keys(), reverse=True)
        if len(dates) < 2:
            return None, None

        return (
            _to_float(series[dates[0]].get("4. close")),
            _to_float(series[dates[1]].get("4. close")),
        )

    except Exception:
        return None, None


def _fetch_price_data(ticker: str) -> dict[str, Any]:
    ticker = normalize_ticker(ticker)

    cached = _get_cached_price(ticker, allow_stale=False)
    if cached:
        return cached

    candidates = candidate_tickers(ticker)

    for candidate in candidates:
        alpha_current, alpha_previous = _fetch_alpha_vantage(candidate)
        if alpha_current is not None:
            as_of = _write_cached_price(ticker, alpha_current, alpha_previous, "Alpha Vantage", candidate)
            return {
                "price": alpha_current,
                "previous_close": alpha_previous,
                "source": "Alpha Vantage",
                "provider_symbol": candidate,
                "as_of": as_of,
                "is_cached": False,
                "is_stale": False,
            }

    for candidate in candidates:
        yahoo_current, yahoo_previous = _fetch_yahoo(candidate)
        if yahoo_current is not None:
            as_of = _write_cached_price(ticker, yahoo_current, yahoo_previous, "Yahoo Finance", candidate)
            return {
                "price": yahoo_current,
                "previous_close": yahoo_previous,
                "source": "Yahoo Finance",
                "provider_symbol": candidate,
                "as_of": as_of,
                "is_cached": False,
                "is_stale": False,
            }

    stale_cached = _get_cached_price(ticker, allow_stale=True)
    if stale_cached:
        return stale_cached

    return {
        "price": None,
        "previous_close": None,
        "source": "Unavailable",
        "provider_symbol": None,
        "as_of": None,
        "is_cached": False,
        "is_stale": False,
    }


def get_equity_snapshot(holdings: list[Any]) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []

    for holding in holdings:
        ticker = normalize_ticker(holding.ticker)
        name = getattr(holding, "name", ticker)
        shares = getattr(holding, "shares", 0)

        data = _fetch_price_data(ticker)
        current_price = data["price"]
        previous_close = data["previous_close"]
        day_change_pct = _safe_pct_change(current_price, previous_close)
        daily_pl = (current_price - previous_close) * shares if current_price is not None and previous_close is not None else None

        snapshots.append(
            {
                "ticker": ticker,
                "name": name,
                "shares": shares,
                "price": current_price,
                "previous_close": previous_close,
                "day_change_pct": day_change_pct,
                "daily_pl": daily_pl,
                "market_value": current_price * shares if current_price is not None else None,
                "status": "OK" if current_price is not None else "Unavailable",
                "source": data["source"],
                "provider_symbol": data["provider_symbol"],
                "as_of": data["as_of"],
                "is_cached": data["is_cached"],
                "is_stale": data["is_stale"],
            }
        )

    total_value = sum(row["market_value"] or 0 for row in snapshots)
    for row in snapshots:
        row["portfolio_weight"] = (row["market_value"] or 0) / total_value if total_value else None

    return snapshots


def get_index_snapshot() -> dict[str, MarketMove]:
    snapshot: dict[str, MarketMove] = {}

    for ticker, name in INDEX_TICKERS.items():
        data = _fetch_price_data(ticker)
        current_price = data["price"]
        previous_close = data["previous_close"]

        source_label = data["source"]
        if data.get("is_stale"):
            source_label = f"{source_label} / stale cache"

        snapshot[name] = MarketMove(
            ticker=ticker,
            name=name,
            price=current_price,
            previous_close=previous_close,
            day_change_pct=_safe_pct_change(current_price, previous_close),
            status="OK" if current_price is not None else "Unavailable",
            source=source_label,
            as_of=data["as_of"],
            provider_symbol=data["provider_symbol"],
        )

    return snapshot


def snapshot_as_dataframe(snapshot: Any) -> pd.DataFrame:
    if isinstance(snapshot, dict):
        rows = []
        for name, move in snapshot.items():
            if hasattr(move, "__dict__"):
                row = move.__dict__.copy()
            else:
                row = dict(move)
            row["display_name"] = name
            rows.append(row)
        return pd.DataFrame(rows)

    return pd.DataFrame(snapshot)
