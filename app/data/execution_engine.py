
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.data.history_db import connect, init_history_db


DB_PATH = Path("data/history.db")


def _json(value: Any) -> str:
    try:
        return json.dumps(value, default=str)
    except Exception:
        return json.dumps(str(value))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_execution_tables(db_path: Path = DB_PATH) -> None:
    init_history_db(db_path)

    with connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS rebalance_recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                run_id TEXT,
                ticker TEXT NOT NULL,
                action TEXT NOT NULL,
                sector TEXT,
                current_weight_pct REAL,
                target_weight_pct REAL,
                weight_drift_pct REAL,
                current_value REAL,
                target_value REAL,
                trade_value REAL,
                composite_score REAL,
                signal_label TEXT,
                status TEXT DEFAULT 'Pending',
                decision_at TEXT,
                decision_note TEXT,
                raw_json TEXT
            );

            CREATE TABLE IF NOT EXISTS paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                executed_at TEXT NOT NULL,
                recommendation_id INTEGER,
                ticker TEXT NOT NULL,
                action TEXT NOT NULL,
                trade_value REAL,
                simulated_price REAL,
                simulated_shares REAL,
                status TEXT DEFAULT 'Executed',
                note TEXT,
                raw_json TEXT
            );

            CREATE TABLE IF NOT EXISTS execution_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                recommendation_id INTEGER,
                ticker TEXT,
                message TEXT,
                metadata_json TEXT
            );

            CREATE TABLE IF NOT EXISTS execution_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_rebalance_status ON rebalance_recommendations(status);
            CREATE INDEX IF NOT EXISTS idx_rebalance_created_at ON rebalance_recommendations(created_at);
            CREATE INDEX IF NOT EXISTS idx_paper_trades_executed_at ON paper_trades(executed_at);
        """)

        row = conn.execute("SELECT value FROM execution_state WHERE key = 'cash_balance'").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO execution_state (key, value, updated_at) VALUES ('cash_balance', '0.0', ?)",
                (_now(),),
            )


def get_cash_balance(db_path: Path = DB_PATH) -> float:
    init_execution_tables(db_path)
    with connect(db_path) as conn:
        row = conn.execute("SELECT value FROM execution_state WHERE key = 'cash_balance'").fetchone()

    if row is None:
        return 0.0

    try:
        return float(row["value"])
    except Exception:
        return 0.0


def set_cash_balance(value: float, db_path: Path = DB_PATH) -> None:
    init_execution_tables(db_path)
    with connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO execution_state (key, value, updated_at) VALUES ('cash_balance', ?, ?)",
            (str(float(value)), _now()),
        )


def save_rebalance_recommendations(
    recommendations: list[dict[str, Any]],
    run_id: str | None = None,
    db_path: Path = DB_PATH,
) -> int:
    init_execution_tables(db_path)

    saved = 0
    created_at = _now()

    with connect(db_path) as conn:
        for rec in recommendations:
            action = str(rec.get("action", "")).upper()
            ticker = str(rec.get("ticker", "")).upper()

            if not ticker or action == "HOLD":
                continue

            existing = conn.execute(
                """
                SELECT id
                FROM rebalance_recommendations
                WHERE ticker = ?
                  AND action = ?
                  AND status = 'Pending'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (ticker, action),
            ).fetchone()

            if existing:
                continue

            conn.execute(
                """
                INSERT INTO rebalance_recommendations (
                    created_at, run_id, ticker, action, sector,
                    current_weight_pct, target_weight_pct, weight_drift_pct,
                    current_value, target_value, trade_value,
                    composite_score, signal_label, status, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?)
                """,
                (
                    created_at,
                    run_id,
                    ticker,
                    action,
                    rec.get("sector"),
                    rec.get("current_weight_pct"),
                    rec.get("target_weight_pct"),
                    rec.get("weight_drift_pct"),
                    rec.get("value"),
                    rec.get("target_value"),
                    rec.get("trade_value"),
                    rec.get("composite_score"),
                    rec.get("signal_label"),
                    _json(rec),
                ),
            )
            saved += 1

    return saved


def latest_recommendations(status: str | None = None, limit: int = 250, db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    init_execution_tables(db_path)

    sql = "SELECT * FROM rebalance_recommendations"
    params: list[Any] = []

    if status:
        sql += " WHERE status = ?"
        params.append(status)

    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()

    return [dict(row) for row in rows]


def approve_recommendation(
    recommendation_id: int,
    note: str = "",
    simulated_price: float | None = None,
    db_path: Path = DB_PATH,
) -> None:
    init_execution_tables(db_path)

    with connect(db_path) as conn:
        rec = conn.execute(
            "SELECT * FROM rebalance_recommendations WHERE id = ?",
            (recommendation_id,),
        ).fetchone()

        if rec is None:
            raise ValueError(f"Recommendation not found: {recommendation_id}")

        if rec["status"] != "Pending":
            raise ValueError(f"Recommendation is not pending: {recommendation_id}")

        trade_value = float(rec["trade_value"] or 0.0)
        action = str(rec["action"]).upper()
        ticker = str(rec["ticker"]).upper()

        price = float(simulated_price or 0.0)
        simulated_shares = abs(trade_value) / price if price > 0 else None

        cash = get_cash_balance(db_path)

        if action == "BUY":
            cash_after = cash - abs(trade_value)
        elif action == "SELL":
            cash_after = cash + abs(trade_value)
        else:
            cash_after = cash

        conn.execute(
            """
            UPDATE rebalance_recommendations
            SET status = 'Approved',
                decision_at = ?,
                decision_note = ?
            WHERE id = ?
            """,
            (_now(), note, recommendation_id),
        )

        conn.execute(
            """
            INSERT INTO paper_trades (
                executed_at, recommendation_id, ticker, action,
                trade_value, simulated_price, simulated_shares,
                status, note, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Executed', ?, ?)
            """,
            (
                _now(),
                recommendation_id,
                ticker,
                action,
                trade_value,
                price if price > 0 else None,
                simulated_shares,
                note,
                _json(dict(rec)),
            ),
        )

        conn.execute(
            "INSERT OR REPLACE INTO execution_state (key, value, updated_at) VALUES ('cash_balance', ?, ?)",
            (str(float(cash_after)), _now()),
        )

        conn.execute(
            """
            INSERT INTO execution_audit (
                created_at, event_type, recommendation_id, ticker, message, metadata_json
            )
            VALUES (?, 'Approved', ?, ?, ?, ?)
            """,
            (
                _now(),
                recommendation_id,
                ticker,
                f"Approved {action} recommendation for {ticker}.",
                _json({"note": note, "cash_before": cash, "cash_after": cash_after}),
            ),
        )


def reject_recommendation(recommendation_id: int, note: str = "", db_path: Path = DB_PATH) -> None:
    init_execution_tables(db_path)

    with connect(db_path) as conn:
        rec = conn.execute(
            "SELECT * FROM rebalance_recommendations WHERE id = ?",
            (recommendation_id,),
        ).fetchone()

        if rec is None:
            raise ValueError(f"Recommendation not found: {recommendation_id}")

        conn.execute(
            """
            UPDATE rebalance_recommendations
            SET status = 'Rejected',
                decision_at = ?,
                decision_note = ?
            WHERE id = ?
            """,
            (_now(), note, recommendation_id),
        )

        conn.execute(
            """
            INSERT INTO execution_audit (
                created_at, event_type, recommendation_id, ticker, message, metadata_json
            )
            VALUES (?, 'Rejected', ?, ?, ?, ?)
            """,
            (
                _now(),
                recommendation_id,
                rec["ticker"],
                f"Rejected {rec['action']} recommendation for {rec['ticker']}.",
                _json({"note": note}),
            ),
        )


def paper_trade_ledger(limit: int = 500, db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    init_execution_tables(db_path)

    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM paper_trades ORDER BY executed_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def execution_audit_trail(limit: int = 500, db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    init_execution_tables(db_path)

    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM execution_audit ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def execution_summary(db_path: Path = DB_PATH) -> dict[str, Any]:
    init_execution_tables(db_path)

    with connect(db_path) as conn:
        pending = conn.execute("SELECT COUNT(*) FROM rebalance_recommendations WHERE status = 'Pending'").fetchone()[0]
        approved = conn.execute("SELECT COUNT(*) FROM rebalance_recommendations WHERE status = 'Approved'").fetchone()[0]
        rejected = conn.execute("SELECT COUNT(*) FROM rebalance_recommendations WHERE status = 'Rejected'").fetchone()[0]
        trades = conn.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
        traded_value = conn.execute("SELECT COALESCE(SUM(ABS(trade_value)), 0) FROM paper_trades").fetchone()[0]

    return {
        "pending_recommendations": pending,
        "approved_recommendations": approved,
        "rejected_recommendations": rejected,
        "paper_trades": trades,
        "total_paper_traded_value": float(traded_value or 0.0),
        "cash_balance": get_cash_balance(db_path),
    }
