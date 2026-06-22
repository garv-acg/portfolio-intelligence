from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MarketRegime:
    regime: str
    summary: str
    drivers: list[str]
    cross_asset_signals: list[str]
    leadership: list[str]
    risk_score: int


def _get(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _find_market(market_snapshot: dict[str, Any], name_contains: str) -> Any | None:
    needle = name_contains.lower()
    for name, row in market_snapshot.items():
        if needle in str(name).lower() or needle in str(_get(row, "ticker", "")).lower():
            return row
    return None


def build_market_regime(
    market_snapshot: dict[str, Any],
    macro_state: list[dict[str, Any]],
    global_developments: list[dict[str, Any]],
    portfolio_news: list[dict[str, Any]] | None = None,
) -> MarketRegime:
    portfolio_news = portfolio_news or []

    spx = _find_market(market_snapshot, "S&P 500")
    nasdaq = _find_market(market_snapshot, "Nasdaq")
    ten_year = _find_market(market_snapshot, "10-Year")
    oil = _find_market(market_snapshot, "WTI")
    gold = _find_market(market_snapshot, "Gold")
    dollar = _find_market(market_snapshot, "Dollar")

    spx_move = _to_float(_get(spx, "day_change_pct")) if spx else None
    nasdaq_move = _to_float(_get(nasdaq, "day_change_pct")) if nasdaq else None
    ten_year_move = _to_float(_get(ten_year, "day_change_pct")) if ten_year else None
    oil_move = _to_float(_get(oil, "day_change_pct")) if oil else None
    gold_move = _to_float(_get(gold, "day_change_pct")) if gold else None
    dollar_move = _to_float(_get(dollar, "day_change_pct")) if dollar else None

    global_text = " ".join(
        f"{_get(item, 'category', '')} {_get(item, 'title', '')} {_get(item, 'summary', '')}"
        for item in global_developments
    ).lower()

    news_text = " ".join(
        f"{_get(item, 'title', '')} {_get(item, 'description', '')}"
        for item in portfolio_news
    ).lower()

    risk_score = 50
    drivers: list[str] = []
    cross_asset_signals: list[str] = []
    leadership: list[str] = []

    if ten_year_move is not None:
        if ten_year_move > 0.25:
            risk_score += 12
            drivers.append("Rising Treasury yields")
            cross_asset_signals.append("Treasury yields higher")
        elif ten_year_move < -0.25:
            risk_score -= 8
            cross_asset_signals.append("Treasury yields lower")

    if any(word in global_text for word in ["inflation", "cpi", "ppi", "pce", "sticky prices", "bond vigilantes"]):
        risk_score += 10
        drivers.append("Sticky inflation concerns")

    if any(word in global_text for word in ["iran", "hormuz", "middle east", "war", "sanctions", "geopolitical", "conflict"]):
        risk_score += 10
        drivers.append("Middle East / geopolitical energy risk")

    if oil_move is not None:
        if oil_move > 1.0:
            risk_score += 8
            cross_asset_signals.append("Oil elevated")
            leadership.append("Energy likely supported")
        elif oil_move < -1.0:
            risk_score -= 3
            cross_asset_signals.append("Oil lower")

    if nasdaq_move is not None:
        if nasdaq_move < -0.25:
            risk_score += 8
            cross_asset_signals.append("Nasdaq under pressure")
            leadership.append("Growth and long-duration equities lagging")
        elif nasdaq_move > 0.25:
            risk_score -= 6
            cross_asset_signals.append("Nasdaq stronger")
            leadership.append("Growth leadership improving")

    if spx_move is not None:
        if spx_move < -0.25:
            risk_score += 6
            cross_asset_signals.append("S&P 500 lower")
        elif spx_move > 0.25:
            risk_score -= 5
            cross_asset_signals.append("S&P 500 firmer")

    if dollar_move is not None:
        if dollar_move > 0.10:
            risk_score += 5
            cross_asset_signals.append("Dollar stronger")
        elif dollar_move < -0.10:
            risk_score -= 2
            cross_asset_signals.append("Dollar softer")

    if gold_move is not None:
        if abs(gold_move) < 0.25:
            cross_asset_signals.append("Gold stable")
        elif gold_move > 0.25:
            risk_score += 4
            cross_asset_signals.append("Gold bid")
        else:
            cross_asset_signals.append("Gold lower")

    if "nvidia" in news_text or "semiconductor" in news_text or "ai chip" in news_text:
        leadership.append("Semiconductors remain a focal point")
    elif "ai" in global_text:
        leadership.append("AI-linked leadership remains in focus")

    if not drivers:
        drivers.append("Mixed macro and market signals")

    if not cross_asset_signals:
        cross_asset_signals.append("Cross-asset signals are mixed")

    if not leadership:
        if risk_score >= 60:
            leadership.append("Defensives likely stabilizing")
        elif risk_score <= 40:
            leadership.append("Risk assets showing healthier leadership")
        else:
            leadership.append("Market leadership remains mixed")

    risk_score = max(0, min(100, risk_score))

    if risk_score >= 65:
        regime = "Risk-Off"
        summary = "Defensive posture favored as macro or geopolitical stress is elevated."
    elif risk_score <= 40:
        regime = "Risk-On"
        summary = "Risk appetite is constructive as cross-asset pressure is limited."
    else:
        regime = "Mixed / Neutral"
        summary = "Signals are balanced; no single risk regime is dominant."

    return MarketRegime(
        regime=regime,
        summary=summary,
        drivers=list(dict.fromkeys(drivers))[:4],
        cross_asset_signals=list(dict.fromkeys(cross_asset_signals))[:5],
        leadership=list(dict.fromkeys(leadership))[:4],
        risk_score=risk_score,
    )
