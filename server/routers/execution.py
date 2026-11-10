from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.db import DatabaseUnavailable

router = APIRouter()


def _ensure_db():
    from server.db import init_db

    try:
        init_db()
    except DatabaseUnavailable as exc:
        raise HTTPException(503, "DATABASE_URL is not configured on this deployment yet") from exc


@router.get("/summary")
def summary():
    from server.db import execution_summary

    _ensure_db()
    return execution_summary()


@router.get("/recommendations")
def recommendations(status: str | None = None):
    from server.db import latest_recommendations

    _ensure_db()
    return latest_recommendations(status=status)


class DecisionIn(BaseModel):
    note: str = ""
    simulated_price: float | None = None


@router.post("/recommendations/{recommendation_id}/approve")
def approve(recommendation_id: int, body: DecisionIn):
    from server.db import approve_recommendation

    _ensure_db()
    try:
        approve_recommendation(recommendation_id, note=body.note, simulated_price=body.simulated_price)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


@router.post("/recommendations/{recommendation_id}/reject")
def reject(recommendation_id: int, body: DecisionIn):
    from server.db import reject_recommendation

    _ensure_db()
    try:
        reject_recommendation(recommendation_id, note=body.note)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


@router.get("/ledger")
def ledger():
    from server.db import paper_trade_ledger

    _ensure_db()
    return paper_trade_ledger()


@router.get("/audit")
def audit():
    from server.db import execution_audit_trail

    _ensure_db()
    return execution_audit_trail()


class CashIn(BaseModel):
    value: float


@router.post("/cash")
def set_cash(body: CashIn):
    from server.db import set_cash_balance

    _ensure_db()
    set_cash_balance(body.value)
    return {"ok": True}
