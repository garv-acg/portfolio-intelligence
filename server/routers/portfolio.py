from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import portfolio_store
from server.shared import get_holdings

router = APIRouter()


class HoldingIn(BaseModel):
    ticker: str
    shares: float
    cost_basis: float = 0.0


class TransactionIn(BaseModel):
    date: str
    ticker: str
    action: str  # "buy" / "sell"
    shares: float
    price: float
    notes: str = ""


@router.get("/overview")
def overview():
    holdings = get_holdings()
    html_out = Path("output/latest_newsletter.html")
    return {
        "holdings_count": len(holdings),
        "total_shares": round(sum(h.shares for h in holdings), 3),
        "newsletter_exists": html_out.exists(),
        "newsletter_html_size": html_out.stat().st_size if html_out.exists() else 0,
        "holdings": [h.__dict__ for h in holdings],
    }


@router.get("/holdings")
def list_holdings():
    return portfolio_store.load_holdings()


@router.put("/holdings")
def replace_holdings(holdings: list[HoldingIn]):
    rows = [h.model_dump() for h in holdings]
    seen = set()
    for r in rows:
        t = r["ticker"].strip().upper()
        if not t:
            raise HTTPException(400, "Every holding needs a ticker")
        if t in seen:
            raise HTTPException(400, f"Duplicate ticker: {t}")
        seen.add(t)
    try:
        portfolio_store.save_holdings(rows)
    except Exception as exc:
        raise HTTPException(500, f"Failed to save holdings: {exc}") from exc
    return {"saved": len(rows)}


@router.get("/transactions")
def list_transactions():
    return portfolio_store.load_transactions()


@router.post("/transactions")
def create_transaction(txn: TransactionIn):
    if txn.action.strip().lower() not in ("buy", "sell"):
        raise HTTPException(400, "action must be 'buy' or 'sell'")
    try:
        from datetime import date as _date
        _date.fromisoformat(txn.date)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")
    try:
        portfolio_store.add_transaction(txn.date, txn.ticker, txn.action, txn.shares, txn.price, txn.notes)
    except Exception as exc:
        raise HTTPException(500, f"Failed to save transaction: {exc}") from exc
    return {"ok": True}
