"""
Postgres (Neon) persistence for the Control Center web app.

Scope, deliberately narrow: only state that must survive across Render
deploys/restarts and be reachable from both this remote backend and (for
portfolio/transactions) the local Mac pipeline lives here:

  - portfolio_holdings / portfolio_transactions — shared source of truth with
    the local `overnight_runner.py` pipeline (see `portfolio_store.py`).
  - rebalance_recommendations / paper_trades / execution_audit /
    execution_state — the paper-trading execution ledger. This is new to
    this web app; the local Streamlit control center's own sqlite-backed
    `app/data/execution_engine.py` is untouched and keeps working exactly as
    it does today for anyone still using it locally.

Everything else this app shows (monitor, market workbench, factors,
construction previews, backtests, alerts) is recomputed live on each
request from the same `app/data/*` engines the email pipeline uses — no
database involved, so there's nothing to keep in sync for it.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get("DATABASE_URL", "")


class DatabaseUnavailable(RuntimeError):
    """Raised when DATABASE_URL isn't configured — callers decide the fallback."""


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    if not DATABASE_URL:
        raise DatabaseUnavailable("DATABASE_URL is not set")
    with psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=False) as conn:
        yield conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    ticker TEXT PRIMARY KEY,
    shares DOUBLE PRECISION NOT NULL,
    cost_basis DOUBLE PRECISION NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS portfolio_transactions (
    id SERIAL PRIMARY KEY,
    txn_date DATE NOT NULL,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL,
    shares DOUBLE PRECISION NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rebalance_recommendations (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_id TEXT,
    ticker TEXT,
    action TEXT,
    sector TEXT,
    current_weight_pct DOUBLE PRECISION,
    target_weight_pct DOUBLE PRECISION,
    weight_drift_pct DOUBLE PRECISION,
    current_value DOUBLE PRECISION,
    target_value DOUBLE PRECISION,
    trade_value DOUBLE PRECISION,
    composite_score DOUBLE PRECISION,
    signal_label TEXT,
    status TEXT NOT NULL DEFAULT 'Pending',
    decision_at TIMESTAMPTZ,
    decision_note TEXT,
    raw_json JSONB
);
CREATE INDEX IF NOT EXISTS idx_reco_status ON rebalance_recommendations(status);

CREATE TABLE IF NOT EXISTS paper_trades (
    id SERIAL PRIMARY KEY,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    recommendation_id INTEGER,
    ticker TEXT,
    action TEXT,
    trade_value DOUBLE PRECISION,
    simulated_price DOUBLE PRECISION,
    simulated_shares DOUBLE PRECISION,
    status TEXT,
    note TEXT,
    raw_json JSONB
);

CREATE TABLE IF NOT EXISTS execution_audit (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type TEXT,
    recommendation_id INTEGER,
    ticker TEXT,
    message TEXT,
    metadata_json JSONB
);

CREATE TABLE IF NOT EXISTS execution_state (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS pipeline_status (
    id SERIAL PRIMARY KEY,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    date TEXT NOT NULL,
    generate_ok BOOLEAN,
    send_ok BOOLEAN,
    deploy_ok BOOLEAN,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_pipeline_status_date ON pipeline_status(date);
"""


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(SCHEMA)
        conn.execute(
            "INSERT INTO execution_state (key, value) VALUES ('cash_balance', '0.0') "
            "ON CONFLICT (key) DO NOTHING"
        )
        conn.commit()


# ── Execution state (cash) ──────────────────────────────────────────────────

def get_cash_balance() -> float:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM execution_state WHERE key = 'cash_balance'").fetchone()
    try:
        return float(row["value"]) if row else 0.0
    except (TypeError, ValueError):
        return 0.0


def set_cash_balance(value: float) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO execution_state (key, value) VALUES ('cash_balance', %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (str(float(value)),),
        )
        conn.commit()


# ── Rebalance recommendations ───────────────────────────────────────────────

def save_rebalance_recommendations(recommendations: list[dict[str, Any]], run_id: str | None = None) -> int:
    saved = 0
    with get_conn() as conn:
        for r in recommendations:
            ticker = str(r.get("ticker", "")).strip()
            action = str(r.get("action", "")).strip().upper()
            if not ticker or action == "HOLD":
                continue
            existing = conn.execute(
                "SELECT id FROM rebalance_recommendations WHERE ticker=%s AND action=%s AND status='Pending'",
                (ticker, action),
            ).fetchone()
            if existing:
                continue
            conn.execute(
                """
                INSERT INTO rebalance_recommendations (
                    run_id, ticker, action, sector, current_weight_pct, target_weight_pct,
                    weight_drift_pct, current_value, target_value, trade_value,
                    composite_score, signal_label, raw_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    run_id, ticker, action, r.get("sector"),
                    r.get("current_weight_pct"), r.get("target_weight_pct"), r.get("weight_drift_pct"),
                    r.get("value") or r.get("current_value"), r.get("target_value"), r.get("trade_value"),
                    r.get("composite_score"), r.get("signal_label"), json.dumps(r),
                ),
            )
            saved += 1
        conn.commit()
    return saved


def latest_recommendations(status: str | None = None, limit: int = 250) -> list[dict[str, Any]]:
    sql = "SELECT * FROM rebalance_recommendations"
    params: list[Any] = []
    if status:
        sql += " WHERE status = %s"
        params.append(status)
    sql += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def approve_recommendation(recommendation_id: int, note: str = "", simulated_price: float | None = None) -> None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM rebalance_recommendations WHERE id = %s", (recommendation_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Recommendation {recommendation_id} not found")
        if row["status"] != "Pending":
            raise ValueError(f"Recommendation {recommendation_id} is not Pending (status={row['status']})")

        trade_value = float(row.get("trade_value") or 0)
        action = str(row.get("action") or "").upper()
        price = float(simulated_price) if simulated_price else None
        shares = abs(trade_value) / price if price and price > 0 else None

        conn.execute(
            "UPDATE rebalance_recommendations SET status='Approved', decision_at=now(), decision_note=%s WHERE id=%s",
            (note, recommendation_id),
        )
        conn.execute(
            """
            INSERT INTO paper_trades (recommendation_id, ticker, action, trade_value, simulated_price, simulated_shares, status, note, raw_json)
            VALUES (%s,%s,%s,%s,%s,%s,'Filled',%s,%s)
            """,
            (recommendation_id, row["ticker"], action, trade_value, price, shares, note, json.dumps(dict(row), default=str)),
        )
        cash = get_cash_balance()
        cash_after = cash - abs(trade_value) if action == "BUY" else cash + abs(trade_value)
        conn.execute(
            "INSERT INTO execution_state (key, value) VALUES ('cash_balance', %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (str(cash_after),),
        )
        conn.execute(
            "INSERT INTO execution_audit (event_type, recommendation_id, ticker, message, metadata_json) VALUES (%s,%s,%s,%s,%s)",
            ("Approved", recommendation_id, row["ticker"], f"Approved {action} {row['ticker']} (${trade_value:,.2f})", json.dumps({"note": note})),
        )
        conn.commit()


def reject_recommendation(recommendation_id: int, note: str = "") -> None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM rebalance_recommendations WHERE id = %s", (recommendation_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Recommendation {recommendation_id} not found")
        if row["status"] != "Pending":
            raise ValueError(f"Recommendation {recommendation_id} is not Pending (status={row['status']})")
        conn.execute(
            "UPDATE rebalance_recommendations SET status='Rejected', decision_at=now(), decision_note=%s WHERE id=%s",
            (note, recommendation_id),
        )
        conn.execute(
            "INSERT INTO execution_audit (event_type, recommendation_id, ticker, message, metadata_json) VALUES (%s,%s,%s,%s,%s)",
            ("Rejected", recommendation_id, row["ticker"], f"Rejected {row['action']} {row['ticker']}", json.dumps({"note": note})),
        )
        conn.commit()


def paper_trade_ledger(limit: int = 500) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM paper_trades ORDER BY executed_at DESC LIMIT %s", (limit,)).fetchall()
    return [dict(r) for r in rows]


def execution_audit_trail(limit: int = 500) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM execution_audit ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall()
    return [dict(r) for r in rows]


def execution_summary() -> dict[str, Any]:
    with get_conn() as conn:
        pending = conn.execute("SELECT COUNT(*) AS n FROM rebalance_recommendations WHERE status='Pending'").fetchone()["n"]
        approved = conn.execute("SELECT COUNT(*) AS n FROM rebalance_recommendations WHERE status='Approved'").fetchone()["n"]
        rejected = conn.execute("SELECT COUNT(*) AS n FROM rebalance_recommendations WHERE status='Rejected'").fetchone()["n"]
        trades = conn.execute("SELECT COUNT(*) AS n FROM paper_trades").fetchone()["n"]
        traded_value = conn.execute("SELECT COALESCE(SUM(ABS(trade_value)),0) AS v FROM paper_trades").fetchone()["v"]
    return {
        "pending_recommendations": pending,
        "approved_recommendations": approved,
        "rejected_recommendations": rejected,
        "paper_trades": trades,
        "total_paper_traded_value": float(traded_value or 0),
        "cash_balance": get_cash_balance(),
    }


# ── Portfolio holdings + transactions (shared with the local pipeline) ─────

def get_holdings() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT ticker, shares, cost_basis FROM portfolio_holdings ORDER BY ticker").fetchall()
    return [dict(r) for r in rows]


def replace_holdings(holdings: list[dict[str, Any]]) -> None:
    """Full replace — mirrors the Streamlit Portfolio page's editable-grid save."""
    with get_conn() as conn:
        conn.execute("DELETE FROM portfolio_holdings")
        for h in holdings:
            ticker = str(h.get("ticker", "")).strip().upper()
            if not ticker:
                continue
            conn.execute(
                "INSERT INTO portfolio_holdings (ticker, shares, cost_basis) VALUES (%s,%s,%s)",
                (ticker, float(h.get("shares", 0) or 0), float(h.get("cost_basis", 0) or 0)),
            )
        conn.commit()


def get_transactions(limit: int = 1000) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, txn_date, ticker, action, shares, price, notes FROM portfolio_transactions "
            "ORDER BY txn_date DESC, id DESC LIMIT %s", (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_transaction(txn_date: str, ticker: str, action: str, shares: float, price: float, notes: str = "") -> int:
    """`action` is lowercase 'buy'/'sell', matching data/transactions.csv's existing convention."""
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO portfolio_transactions (txn_date, ticker, action, shares, price, notes) "
            "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            (txn_date, ticker.strip().upper(), action.strip().lower(), float(shares), float(price), notes or ""),
        ).fetchone()
        conn.commit()
    return int(row["id"])


def delete_transaction(txn_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM portfolio_transactions WHERE id = %s", (txn_id,))
        conn.commit()


# ── Pipeline status (best-effort sync from overnight_runner.py) ────────────

def record_pipeline_status(date: str, generate_ok: bool | None, send_ok: bool | None,
                            deploy_ok: bool | None, error: str | None) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO pipeline_status (date, generate_ok, send_ok, deploy_ok, error) VALUES (%s,%s,%s,%s,%s)",
            (date, generate_ok, send_ok, deploy_ok, error),
        )
        conn.commit()


def latest_pipeline_status() -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM pipeline_status ORDER BY recorded_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None
