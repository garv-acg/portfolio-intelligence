from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path("data/history.db")


def _json(value: Any) -> str:
    try:
        return json.dumps(value, default=str)
    except Exception:
        return json.dumps(str(value))


def _get(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_history_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                report_date TEXT,
                portfolio_value REAL,
                daily_pl REAL,
                weighted_move_pct REAL,
                holdings_count INTEGER,
                regime TEXT,
                regime_confidence TEXT,
                risk_score REAL,
                inflation_score REAL,
                growth_score REAL,
                liquidity_score REAL,
                raw_payload_json TEXT
            );

            CREATE TABLE IF NOT EXISTS portfolio_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                ticker TEXT,
                company TEXT,
                shares REAL,
                price REAL,
                move_pct REAL,
                daily_pl REAL,
                value REAL,
                sector TEXT,
                source TEXT,
                as_of TEXT
            );

            CREATE TABLE IF NOT EXISTS attribution (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                ticker TEXT,
                daily_pl REAL,
                move_pct REAL,
                contribution_pct REAL,
                value REAL,
                weight_pct REAL,
                sector TEXT
            );

            CREATE TABLE IF NOT EXISTS regimes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                regime TEXT,
                confidence TEXT,
                risk_score REAL,
                inflation_score REAL,
                growth_score REAL,
                liquidity_score REAL,
                drivers_json TEXT,
                confirmation_json TEXT,
                leadership_json TEXT,
                fragilities_json TEXT,
                narrative TEXT
            );

            CREATE TABLE IF NOT EXISTS sec_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                ticker TEXT,
                company TEXT,
                form_type TEXT,
                signal_type TEXT,
                signal_summary TEXT,
                items_detected_json TEXT,
                relevance_score REAL,
                confidence TEXT,
                filed_at TEXT,
                url TEXT,
                document_url TEXT,
                raw_document_url TEXT,
                reason TEXT
            );

            CREATE TABLE IF NOT EXISTS factor_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                ticker TEXT,
                signal_name TEXT,
                signal_value REAL,
                signal_score REAL,
                signal_direction TEXT,
                metadata_json TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at);
            CREATE INDEX IF NOT EXISTS idx_portfolio_values_run ON portfolio_values(run_id);
            CREATE INDEX IF NOT EXISTS idx_attribution_run ON attribution(run_id);
            CREATE INDEX IF NOT EXISTS idx_regimes_run ON regimes(run_id);
            CREATE INDEX IF NOT EXISTS idx_sec_events_run ON sec_events(run_id);
            CREATE INDEX IF NOT EXISTS idx_factor_signals_run ON factor_signals(run_id);
            """
        )


def save_history_snapshot(payload: dict[str, Any], db_path: Path = DEFAULT_DB_PATH) -> str:
    init_history_db(db_path)

    now = datetime.now(timezone.utc)
    report_date = str(payload.get("date") or now.date().isoformat())
    run_id = f"{report_date}_{now.strftime('%Y%m%dT%H%M%SZ')}"

    portfolio_summary = payload.get("portfolio_summary", {}) or {}
    portfolio_snapshot = payload.get("portfolio_snapshot", []) or []
    visual_analytics = payload.get("visual_analytics", {}) or {}
    attribution_rows = visual_analytics.get("daily_attribution", []) if isinstance(visual_analytics, dict) else []
    regime = payload.get("cross_asset_regime", {}) or {}
    sec_filings = payload.get("sec_filings", []) or []

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO runs (
                run_id, created_at, report_date, portfolio_value, daily_pl,
                weighted_move_pct, holdings_count, regime, regime_confidence,
                risk_score, inflation_score, growth_score, liquidity_score,
                raw_payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                now.isoformat(),
                report_date,
                _get(portfolio_summary, "portfolio_value", _get(portfolio_summary, "total_value")),
                _get(portfolio_summary, "daily_pl", _get(portfolio_summary, "total_daily_pl")),
                _get(portfolio_summary, "weighted_move_pct", _get(portfolio_summary, "weighted_move")),
                len(portfolio_snapshot),
                _get(regime, "regime"),
                _get(regime, "confidence"),
                _get(regime, "risk_score"),
                _get(regime, "inflation_score"),
                _get(regime, "growth_score"),
                _get(regime, "liquidity_score"),
                _json(payload),
            ),
        )

        for row in portfolio_snapshot:
            conn.execute(
                """
                INSERT INTO portfolio_values (
                    run_id, ticker, company, shares, price, move_pct,
                    daily_pl, value, sector, source, as_of
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    _get(row, "ticker"),
                    _get(row, "name", _get(row, "company")),
                    _get(row, "shares"),
                    _get(row, "price"),
                    _get(row, "day_change_pct", _get(row, "move_pct")),
                    _get(row, "daily_pl", _get(row, "day_pl")),
                    _get(row, "market_value", _get(row, "value")),
                    _get(row, "sector"),
                    _get(row, "source"),
                    _get(row, "as_of"),
                ),
            )

        for row in attribution_rows:
            conn.execute(
                """
                INSERT INTO attribution (
                    run_id, ticker, daily_pl, move_pct, contribution_pct,
                    value, weight_pct, sector
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    _get(row, "ticker"),
                    _get(row, "daily_pl"),
                    _get(row, "move_pct"),
                    _get(row, "contribution_pct"),
                    _get(row, "value"),
                    _get(row, "weight_pct"),
                    _get(row, "sector"),
                ),
            )

        if regime:
            conn.execute(
                """
                INSERT INTO regimes (
                    run_id, regime, confidence, risk_score, inflation_score,
                    growth_score, liquidity_score, drivers_json,
                    confirmation_json, leadership_json, fragilities_json, narrative
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    _get(regime, "regime"),
                    _get(regime, "confidence"),
                    _get(regime, "risk_score"),
                    _get(regime, "inflation_score"),
                    _get(regime, "growth_score"),
                    _get(regime, "liquidity_score"),
                    _json(_get(regime, "drivers", [])),
                    _json(_get(regime, "cross_asset_confirmation", [])),
                    _json(_get(regime, "leadership", [])),
                    _json(_get(regime, "fragilities", [])),
                    _get(regime, "narrative"),
                ),
            )

        for item in sec_filings:
            conn.execute(
                """
                INSERT INTO sec_events (
                    run_id, ticker, company, form_type, signal_type,
                    signal_summary, items_detected_json, relevance_score,
                    confidence, filed_at, url, document_url, raw_document_url, reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    _get(item, "ticker"),
                    _get(item, "company"),
                    _get(item, "form_type"),
                    _get(item, "signal_type"),
                    _get(item, "signal_summary"),
                    _json(_get(item, "items_detected", [])),
                    _get(item, "relevance_score"),
                    _get(item, "confidence"),
                    _get(item, "filed_at"),
                    _get(item, "url"),
                    _get(item, "document_url"),
                    _get(item, "raw_document_url"),
                    _get(item, "reason"),
                ),
            )

    return run_id


def latest_runs(limit: int = 20, db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    init_history_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def load_table(table_name: str, limit: int = 500, db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    allowed = {"runs", "portfolio_values", "attribution", "regimes", "sec_events", "factor_signals"}
    if table_name not in allowed:
        raise ValueError(f"Unsupported table: {table_name}")

    init_history_db(db_path)

    order_col = "created_at" if table_name == "runs" else "id"

    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM {table_name} ORDER BY {order_col} DESC LIMIT ?",
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]
