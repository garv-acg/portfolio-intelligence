from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.data.history_db import connect, init_history_db


@dataclass(frozen=True)
class Alert:
    alert_type: str
    severity: str
    title: str
    message: str
    ticker: str | None = None
    value: float | None = None
    threshold: float | None = None
    source: str = "Alert Engine"


def _get(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def init_alerts_table(db_path: Path = Path("data/history.db")) -> None:
    init_history_db(db_path)
    with connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                run_id TEXT,
                alert_type TEXT,
                severity TEXT,
                ticker TEXT,
                title TEXT,
                message TEXT,
                value REAL,
                threshold REAL,
                source TEXT,
                is_resolved INTEGER DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(alert_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_ticker ON alerts(ticker)")


def _previous_regime(current_run_id: str | None = None) -> str | None:
    init_history_db()
    with connect() as conn:
        if current_run_id:
            row = conn.execute(
                "SELECT regime FROM runs WHERE run_id != ? AND regime IS NOT NULL ORDER BY created_at DESC LIMIT 1",
                (current_run_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT regime FROM runs WHERE regime IS NOT NULL ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
    return row["regime"] if row else None


def build_alerts(
    payload: dict[str, Any],
    run_id: str | None = None,
    drawdown_threshold_pct: float = -5.0,
    large_move_threshold_pct: float = 3.0,
    earnings_days_threshold: int = 7,
) -> list[Alert]:
    alerts: list[Alert] = []

    portfolio_snapshot = payload.get("portfolio_snapshot", []) or []
    visual_analytics = payload.get("visual_analytics", {}) or {}
    drawdown = visual_analytics.get("drawdown", []) if isinstance(visual_analytics, dict) else []
    earnings_calendar = payload.get("earnings_calendar", []) or []
    sec_filings = payload.get("sec_filings", []) or []
    regime = payload.get("cross_asset_regime", {}) or {}

    if drawdown:
        try:
            latest_drawdown = float(drawdown[-1].get("drawdown_pct"))
            if latest_drawdown <= drawdown_threshold_pct:
                alerts.append(Alert(
                    alert_type="Drawdown",
                    severity="High" if latest_drawdown <= drawdown_threshold_pct * 1.5 else "Medium",
                    title="Portfolio drawdown threshold breached",
                    message=f"Current portfolio drawdown is {latest_drawdown:.2f}%, below threshold {drawdown_threshold_pct:.2f}%.",
                    value=latest_drawdown,
                    threshold=drawdown_threshold_pct,
                ))
        except Exception:
            pass

    for row in portfolio_snapshot:
        ticker = str(_get(row, "ticker", "")).upper()
        raw_move = _get(row, "day_change_pct", _get(row, "move_pct"))
        try:
            move_pct = float(raw_move)
        except Exception:
            continue
        if abs(move_pct) >= large_move_threshold_pct:
            alerts.append(Alert(
                alert_type="Large Move",
                severity="High" if abs(move_pct) >= large_move_threshold_pct * 1.75 else "Medium",
                ticker=ticker,
                title=f"{ticker} large position move",
                message=f"{ticker} moved {move_pct:+.2f}% today, exceeding threshold {large_move_threshold_pct:.2f}%.",
                value=move_pct,
                threshold=large_move_threshold_pct,
            ))

    for filing in sec_filings:
        ticker = str(_get(filing, "ticker", "")).upper()
        items = _get(filing, "items_detected", []) or []
        if "Item 5.02" in items:
            alerts.append(Alert(
                alert_type="SEC Item 5.02",
                severity="High",
                ticker=ticker,
                title=f"{ticker} SEC Item 5.02 detected",
                message=_get(filing, "signal_summary", "") or f"{ticker} filed an Item 5.02 disclosure.",
                source="SEC EDGAR",
            ))

    today = datetime.now().date()
    for item in earnings_calendar:
        ticker = str(_get(item, "ticker", "")).upper()
        date_raw = _get(item, "date")
        if not ticker or not date_raw:
            continue
        try:
            event_date = datetime.fromisoformat(str(date_raw)[:10]).date()
            days = (event_date - today).days
        except Exception:
            continue
        if 0 <= days <= earnings_days_threshold:
            alerts.append(Alert(
                alert_type="Earnings",
                severity="High" if days <= 1 else "Medium",
                ticker=ticker,
                title=f"{ticker} earnings approaching",
                message=f"{ticker} has earnings in {days} day(s): {event_date.isoformat()}.",
                value=float(days),
                threshold=float(earnings_days_threshold),
                source=_get(item, "source", "Earnings Calendar"),
            ))

    current_regime = _get(regime, "regime")
    prev = _previous_regime(run_id)
    if current_regime and prev and current_regime != prev:
        alerts.append(Alert(
            alert_type="Regime Shift",
            severity="High",
            title="Market regime shift detected",
            message=f"Market regime changed from {prev} to {current_regime}.",
            source="Cross-Asset Regime Engine",
        ))

    return alerts


def save_alerts(alerts: list[Alert], run_id: str | None = None) -> int:
    init_alerts_table()
    created_at = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        for alert in alerts:
            conn.execute("""
                INSERT INTO alerts (
                    created_at, run_id, alert_type, severity, ticker, title,
                    message, value, threshold, source, is_resolved
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                created_at, run_id, alert.alert_type, alert.severity, alert.ticker,
                alert.title, alert.message, alert.value, alert.threshold, alert.source
            ))
    return len(alerts)


def latest_alerts(limit: int = 100, unresolved_only: bool = False) -> list[dict[str, Any]]:
    init_alerts_table()
    sql = "SELECT * FROM alerts"
    params: list[Any] = []
    if unresolved_only:
        sql += " WHERE is_resolved = 0"
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def alert_summary() -> dict[str, Any]:
    init_alerts_table()
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        unresolved = conn.execute("SELECT COUNT(*) FROM alerts WHERE is_resolved = 0").fetchone()[0]
        high = conn.execute("SELECT COUNT(*) FROM alerts WHERE severity = 'High'").fetchone()[0]
        latest = conn.execute("SELECT created_at FROM alerts ORDER BY created_at DESC LIMIT 1").fetchone()
    return {
        "total_alerts": total,
        "unresolved_alerts": unresolved,
        "high_severity_alerts": high,
        "latest_alert_at": latest[0] if latest else None,
    }
