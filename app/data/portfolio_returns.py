"""
portfolio_returns.py
────────────────────
Computes actual time-weighted returns (TWR) from a transaction log.

Transaction log: data/transactions.csv
  Columns: date, ticker, action (buy/sell), shares, price, notes

TWR algorithm:
  - At each period boundary (start, any mid-period trade date, end), compute
    portfolio market value using historical prices — never transaction prices.
  - Chain sub-period returns: TWR = (1+r1)×(1+r2)×…−1
  - This matches how Fidelity/Schwab compute time-weighted return.
"""
from __future__ import annotations

import math
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

TRANSACTIONS_FILE = Path(__file__).resolve().parents[2] / "data" / "transactions.csv"


# ── Price fetching ─────────────────────────────────────────────────────────────

def _fetch_prices_range(ticker: str, start: date, end: date) -> pd.Series:
    """Return a date-indexed Series of dividend-adjusted closing prices for ticker.

    Uses adjclose (adjusted close) so dividends and splits are automatically
    reflected — this matches how Fidelity computes total return.
    """
    try:
        s = int(pd.Timestamp(start).timestamp())
        e = int((pd.Timestamp(end) + timedelta(days=5)).timestamp())
        headers = {"User-Agent": "Mozilla/5.0"}
        for host in ["query1", "query2"]:
            url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{ticker}"
            r = requests.get(
                url,
                params={"period1": s, "period2": e, "interval": "1d", "events": "history"},
                timeout=20,
                headers=headers,
            )
            if r.status_code != 200:
                continue
            payload = r.json()["chart"]["result"][0]
            timestamps = payload["timestamp"]
            # Prefer adjclose (dividend/split adjusted); fall back to raw close
            adj = payload["indicators"].get("adjclose", [{}])
            adjclose = adj[0].get("adjclose") if adj else None
            closes = adjclose if adjclose else payload["indicators"]["quote"][0]["close"]
            series = pd.Series(
                closes,
                index=[pd.Timestamp(t, unit="s", tz="UTC").date() for t in timestamps],
            ).dropna()
            if not series.empty:
                return series
    except Exception:
        pass
    return pd.Series(dtype=float)


def _price_on_or_before(prices: pd.Series, d: date) -> Optional[float]:
    """Return the most recent close on or before date d."""
    candidates = prices[prices.index <= d]
    if candidates.empty:
        return None
    return float(candidates.iloc[-1])


# ── Transaction log ────────────────────────────────────────────────────────────

def load_transactions() -> pd.DataFrame:
    # Postgres is the source of truth once DATABASE_URL is configured (so
    # transactions added from the web Control Center feed this calculation
    # too) — any failure falls straight through to the original CSV read.
    df = None
    if os.environ.get("DATABASE_URL", "").strip():
        try:
            import portfolio_store
            rows = portfolio_store.load_transactions()
            if rows:
                df = pd.DataFrame(rows)
        except Exception as exc:
            print(f"[load_transactions] Postgres read failed, falling back to CSV: {exc}")

    if df is None:
        if not TRANSACTIONS_FILE.exists():
            return pd.DataFrame(columns=["date", "ticker", "action", "shares", "price", "notes"])
        df = pd.read_csv(TRANSACTIONS_FILE, parse_dates=["date"])

    df["date"]   = pd.to_datetime(df["date"]).dt.date
    df["shares"] = pd.to_numeric(df["shares"], errors="coerce").fillna(0.0)
    df["price"]  = pd.to_numeric(df["price"],  errors="coerce").fillna(0.0)
    df["action"] = df["action"].str.strip().str.lower()
    return df.sort_values("date").reset_index(drop=True)


def holdings_on(txns: pd.DataFrame, as_of: date) -> dict[str, float]:
    """Return {ticker: shares} held as of a given date (inclusive)."""
    subset = txns[txns["date"] <= as_of]
    holdings: dict[str, float] = {}
    for _, row in subset.iterrows():
        t = str(row["ticker"]).upper()
        s = float(row["shares"])
        if row["action"] == "buy":
            holdings[t] = holdings.get(t, 0.0) + s
        elif row["action"] == "sell":
            holdings[t] = holdings.get(t, 0.0) - s
    return {t: s for t, s in holdings.items() if s > 1e-9}


# ── Portfolio value using market prices only ───────────────────────────────────

def _portfolio_value(
    holdings: dict[str, float],
    price_cache: dict[str, pd.Series],
    d: date,
) -> Optional[float]:
    """Compute total portfolio market value at date d. Never uses transaction prices."""
    if not holdings:
        return None
    total = 0.0
    for ticker, shares in holdings.items():
        p = _price_on_or_before(price_cache.get(ticker, pd.Series(dtype=float)), d)
        if p is None:
            return None
        total += shares * p
    return total


# ── TWR computation ────────────────────────────────────────────────────────────

def _twr_for_period(
    txns: pd.DataFrame,
    price_cache: dict[str, pd.Series],
    start: date,
    end: date,
) -> Optional[float]:
    """
    Compute TWR from start to end using only market prices at boundaries.

    For each sub-period [s, e]:
      - holdings = what was held at s (after any buys/sells on s)
      - v_start  = market value of those holdings at close of s
      - v_end    = market value of those holdings at close of e
      - sub_return = v_end / v_start

    Sub-periods are split at every transaction date strictly between start and end.
    The start holdings and their market prices on the start date form the base —
    NEVER the transaction buy price — so this correctly mirrors Fidelity YTD.
    """
    # Boundary dates: start + every transaction mid-period + end
    mid_dates = sorted(set(
        txns[(txns["date"] > start) & (txns["date"] < end)]["date"].tolist()
    ))
    boundaries = [start] + mid_dates + [end]

    twr = 1.0
    for i in range(len(boundaries) - 1):
        s, e = boundaries[i], boundaries[i + 1]
        h = holdings_on(txns, s)
        if not h:
            continue
        v_s = _portfolio_value(h, price_cache, s)
        v_e = _portfolio_value(h, price_cache, e)
        if v_s is None or v_e is None or v_s <= 0:
            return None
        twr *= v_e / v_s

    return (twr - 1) * 100


# ── Main entry point ───────────────────────────────────────────────────────────

def compute_portfolio_returns(today: Optional[date] = None) -> dict[str, Optional[float]]:
    """
    Returns dict with keys: daily, weekly, monthly, ytd
    Values are % returns (e.g. 2.5 = +2.5%), or None if data unavailable.
    """
    today = today or date.today()
    txns  = load_transactions()

    if txns.empty:
        return {"daily": None, "weekly": None, "monthly": None, "ytd": None}

    all_tickers = txns["ticker"].str.upper().unique().tolist()

    # Fetch enough history to cover YTD start (Dec 31 of prior year)
    ytd_start   = date(today.year, 1, 1) - timedelta(days=1)  # Dec 31 prior year
    fetch_start = ytd_start - timedelta(days=10)               # buffer for holidays

    price_cache: dict[str, pd.Series] = {}
    for ticker in all_tickers:
        price_cache[ticker] = _fetch_prices_range(ticker, fetch_start, today)

    periods = {
        "ytd":     ytd_start,
        "monthly": today - timedelta(days=30),
        "weekly":  today - timedelta(days=7),
        "daily":   today - timedelta(days=1),
    }

    results: dict[str, Optional[float]] = {}
    for name, start in periods.items():
        try:
            # Check if we had holdings at the period start via market prices.
            # If the portfolio was initiated after start (e.g. all buys on Jan 2
            # but start = Dec 31), use the first transaction date as the sub-
            # period start — portfolio value there uses market price, not cost basis.
            h_at_start = holdings_on(txns, start)

            if not h_at_start:
                # No holdings at start — find the earliest buy within this period
                first_txn = txns[txns["date"] > start]
                if first_txn.empty:
                    results[name] = None
                    continue
                # Use the first buy date as the effective start for this period.
                # _twr_for_period will price holdings at market close that day,
                # NOT at the transaction price.
                effective_start = first_txn["date"].min() - timedelta(days=1)
            else:
                effective_start = start

            r = _twr_for_period(txns, price_cache, effective_start, today)
            if r is not None and (math.isnan(r) or math.isinf(r)):
                r = None
            results[name] = r

        except Exception:
            results[name] = None

    return results
