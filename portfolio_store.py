"""
Shared portfolio/transactions source of truth, used by BOTH the local
`overnight_runner.py` pipeline and the remote Control Center web app
(`server/`), so editing holdings from the web actually affects your real
daily email — and vice versa.

Behavior, by design:
  - DATABASE_URL unset (the default, e.g. a fresh clone or no Neon wired up
    yet): everything here behaves EXACTLY like the old CSV-only code path —
    zero behavior change, zero new dependency risk, to the local pipeline.
  - DATABASE_URL set but unreachable (network hiccup, Neon down): reads
    fall back to the local CSV cache rather than crashing the newsletter
    generation; a write failure raises (the caller — a web request — should
    surface that, rather than silently losing an edit).
  - DATABASE_URL set and reachable: Postgres is the source of truth. Every
    write also refreshes the local CSV as a best-effort cache, so a later
    Postgres outage still has recent data to fall back to.

This module intentionally has no FastAPI dependency so the local pipeline
can import it without installing the web server's dependencies.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

PORTFOLIO_CSV = Path("data/users/demo/portfolio.csv")
TRANSACTIONS_CSV = Path("data/transactions.csv")


def _database_url() -> str:
    return os.environ.get("DATABASE_URL", "").strip()


def _db():
    """Lazily imports server.db only when actually configured, so a plain
    `pip install -r requirements.txt` (no psycopg) never breaks the pipeline
    for anyone who hasn't wired up DATABASE_URL."""
    import server.db as db  # noqa: PLC0415
    return db


# ── Holdings ─────────────────────────────────────────────────────────────

def load_holdings() -> list[dict[str, Any]]:
    """Returns [{ticker, shares, cost_basis}, ...]."""
    if _database_url():
        try:
            rows = _db().get_holdings()
            if rows:
                return rows
        except Exception as exc:
            print(f"[portfolio_store] Postgres read failed, falling back to CSV: {exc}")
    return _load_holdings_csv()


def _load_holdings_csv() -> list[dict[str, Any]]:
    if not PORTFOLIO_CSV.exists():
        return []
    df = pd.read_csv(PORTFOLIO_CSV)
    return [
        {
            "ticker": str(row.get("ticker", "")).upper().strip(),
            "shares": float(row.get("shares", 0) or 0),
            "cost_basis": float(row.get("cost_basis", 0) or 0),
        }
        for _, row in df.iterrows()
        if str(row.get("ticker", "")).strip()
    ]


def save_holdings(holdings: list[dict[str, Any]]) -> None:
    PORTFOLIO_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(holdings, columns=["ticker", "shares", "cost_basis"]).to_csv(PORTFOLIO_CSV, index=False)
    if _database_url():
        _db().replace_holdings(holdings)  # let this raise — a web write should surface failure


# ── Transactions ─────────────────────────────────────────────────────────

def load_transactions() -> list[dict[str, Any]]:
    """Returns [{date, ticker, action, shares, price, notes}, ...] newest first."""
    if _database_url():
        try:
            rows = _db().get_transactions()
            if rows:
                return [
                    {
                        "date": str(r["txn_date"]),
                        "ticker": r["ticker"],
                        "action": r["action"],
                        "shares": r["shares"],
                        "price": r["price"],
                        "notes": r.get("notes", ""),
                    }
                    for r in rows
                ]
        except Exception as exc:
            print(f"[portfolio_store] Postgres read failed, falling back to CSV: {exc}")
    return _load_transactions_csv()


def _load_transactions_csv() -> list[dict[str, Any]]:
    if not TRANSACTIONS_CSV.exists():
        return []
    df = pd.read_csv(TRANSACTIONS_CSV)
    return df.to_dict(orient="records")


def add_transaction(date: str, ticker: str, action: str, shares: float, price: float, notes: str = "") -> None:
    rows = _load_transactions_csv()
    rows.append({"date": date, "ticker": ticker.upper(), "action": action.lower(), "shares": shares, "price": price, "notes": notes})
    TRANSACTIONS_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["date", "ticker", "action", "shares", "price", "notes"]).to_csv(TRANSACTIONS_CSV, index=False)
    if _database_url():
        _db().add_transaction(date, ticker, action, shares, price, notes)
