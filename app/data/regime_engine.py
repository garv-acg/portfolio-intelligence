from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CrossAssetRegime:
    regime: str
    confidence: str
    risk_score: int
    inflation_score: int
    growth_score: int
    liquidity_score: int
    drivers: list[str]
    cross_asset_confirmation: list[str]
    leadership: list[str]
    fragilities: list[str]
    narrative: str


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


def _find_market(market_snapshot: dict[str, Any], name_or_ticker: str) -> Any | None:
    needle = name_or_ticker.lower()

    for name, row in market_snapshot.items():
        name_text = str(name).lower()
        ticker_text = str(_get(row, "ticker", "")).lower()

        if needle in name_text or needle in ticker_text:
            return row

    return None


def _unique(items: list[str], limit: int = 6) -> list[str]:
    return list(dict.fromkeys([item for item in items if item]))[:limit]


def infer_cross_asset_regime(
    market_snapshot: dict[str, Any],
    macro_state: list[dict[str, Any]],
    global_developments: list[dict[str, Any]],
    portfolio_news: list[dict[str, Any]] | None = None,
) -> CrossAssetRegime:
    portfolio_news = portfolio_news or []

    spx = _find_market(market_snapshot, "S&P 500")
    nasdaq = _find_market(market_snapshot, "Nasdaq")
    dow = _find_market(market_snapshot, "Dow")
    ten_year = _find_market(market_snapshot, "10-Year")
    oil = _find_market(market_snapshot, "WTI")
    gold = _find_market(market_snapshot, "Gold")
    dollar = _find_market(market_snapshot, "Dollar")

    spx_move = _to_float(_get(spx, "day_change_pct")) if spx else None
    nasdaq_move = _to_float(_get(nasdaq, "day_change_pct")) if nasdaq else None
    dow_move = _to_float(_get(dow, "day_change_pct")) if dow else None
    ten_year_move = _to_float(_get(ten_year, "day_change_pct")) if ten_year else None
    oil_move = _to_float(_get(oil, "day_change_pct")) if oil else None
    gold_move = _to_float(_get(gold, "day_change_pct")) if gold else None
    dollar_move = _to_float(_get(dollar, "day_change_pct")) if dollar else None

    global_text = " ".join(
        f"{_get(item, 'category', '')} {_get(item, 'title', '')} {_get(item, 'summary', '')}"
        for item in global_developments
    ).lower()

    macro_text = " ".join(
        f"{_get(item, 'name', '')} {_get(item, 'note', '')} {_get(item, 'latest_display', '')} {_get(item, 'change_display', '')}"
        for item in macro_state
    ).lower()

    portfolio_text = " ".join(
        f"{_get(item, 'ticker', '')} {_get(item, 'title', '')} {_get(item, 'description', '')}"
        for item in portfolio_news
    ).lower()

    risk_score = 50
    inflation_score = 50
    growth_score = 50
    liquidity_score = 50

    drivers: list[str] = []
    cross_asset_confirmation: list[str] = []
    leadership: list[str] = []
    fragilities: list[str] = []

    if ten_year_move is not None:
        if ten_year_move > 0.25:
            risk_score += 12
            inflation_score += 8
            liquidity_score -= 10
            drivers.append("Rising Treasury yields")
            cross_asset_confirmation.append("Treasury yields higher")
            fragilities.append("Long-duration equities remain rate-sensitive")
        elif ten_year_move < -0.25:
            risk_score -= 6
            liquidity_score += 8
            cross_asset_confirmation.append("Treasury yields lower")

    if any(term in global_text or term in macro_text for term in ["inflation", "cpi", "ppi", "pce", "sticky", "bond vigilantes"]):
        risk_score += 8
        inflation_score += 12
        drivers.append("Sticky inflation concerns")

    if any(term in global_text for term in ["iran", "hormuz", "middle east", "war", "sanctions", "geopolitical", "conflict"]):
        risk_score += 10
        inflation_score += 6
        drivers.append("Middle East / geopolitical energy risk")
        fragilities.append("Energy supply risk remains a macro transmission channel")

    if oil_move is not None:
        if oil_move > 2.0:
            risk_score += 10
            inflation_score += 8
            drivers.append("Oil price pressure")
            cross_asset_confirmation.append("Oil elevated")
            leadership.append("Energy likely supported")
        elif oil_move > 0.75:
            risk_score += 5
            inflation_score += 4
            cross_asset_confirmation.append("Oil firmer")
        elif oil_move < -1.0:
            inflation_score -= 4
            cross_asset_confirmation.append("Oil lower")

    if nasdaq_move is not None:
        if nasdaq_move < -0.50:
            risk_score += 10
            growth_score -= 8
            cross_asset_confirmation.append("Nasdaq under pressure")
            leadership.append("Growth and long-duration equities lagging")
            fragilities.append("AI and mega-cap tech remain vulnerable to rates")
        elif nasdaq_move < -0.20:
            risk_score += 5
            growth_score -= 4
            cross_asset_confirmation.append("Nasdaq softer")
        elif nasdaq_move > 0.50:
            risk_score -= 8
            growth_score += 8
            leadership.append("Growth leadership improving")
            cross_asset_confirmation.append("Nasdaq stronger")

    if spx_move is not None:
        if spx_move < -0.30:
            risk_score += 6
            growth_score -= 5
            cross_asset_confirmation.append("S&P 500 lower")
        elif spx_move > 0.30:
            risk_score -= 6
            growth_score += 5
            cross_asset_confirmation.append("S&P 500 firmer")

    if dow_move is not None:
        if dow_move > 0.20 and nasdaq_move is not None and nasdaq_move < 0:
            leadership.append("Cyclical/defensive leadership outperforming growth")

    if dollar_move is not None:
        if dollar_move > 0.10:
            risk_score += 5
            liquidity_score -= 4
            cross_asset_confirmation.append("Dollar stronger")
        elif dollar_move < -0.10:
            liquidity_score += 3
            cross_asset_confirmation.append("Dollar softer")

    if gold_move is not None:
        if gold_move > 0.25:
            risk_score += 4
            cross_asset_confirmation.append("Gold bid")
            fragilities.append("Safe-haven demand visible")
        elif abs(gold_move) <= 0.25:
            cross_asset_confirmation.append("Gold stable")
        else:
            cross_asset_confirmation.append("Gold lower")

    if any(term in portfolio_text or term in global_text for term in ["nvidia", "semiconductor", "ai chip", "gpu", "data center"]):
        leadership.append("Semiconductors remain a focal point")

    if "earnings" in portfolio_text:
        fragilities.append("Upcoming earnings remain a single-name catalyst risk")

    risk_score = max(0, min(100, risk_score))
    inflation_score = max(0, min(100, inflation_score))
    growth_score = max(0, min(100, growth_score))
    liquidity_score = max(0, min(100, liquidity_score))

    if risk_score >= 68 and inflation_score >= 60:
        regime = "Risk-Off / Inflationary"
    elif risk_score >= 65:
        regime = "Risk-Off"
    elif inflation_score >= 65 and liquidity_score <= 45:
        regime = "Inflationary Tightening"
    elif risk_score <= 40 and growth_score >= 55:
        regime = "Risk-On"
    elif liquidity_score >= 60 and risk_score <= 50:
        regime = "Liquidity Supportive"
    else:
        regime = "Mixed / Transitional"

    confirmation_count = len(cross_asset_confirmation)
    if confirmation_count >= 4:
        confidence = "High"
    elif confirmation_count >= 2:
        confidence = "Medium"
    else:
        confidence = "Low"

    if not drivers:
        drivers.append("Mixed macro and market signals")
    if not cross_asset_confirmation:
        cross_asset_confirmation.append("Cross-asset signals are not yet decisive")
    if not leadership:
        leadership.append("Market leadership remains mixed")
    if not fragilities:
        fragilities.append("No single fragility dominates the current setup")

    narrative = (
        f"The inferred regime is {regime}. "
        f"Risk score is {risk_score}/100, with inflation pressure at {inflation_score}/100 "
        f"and liquidity support at {liquidity_score}/100. "
        f"The main drivers are {', '.join(_unique(drivers, 3)).lower()}."
    )

    return CrossAssetRegime(
        regime=regime,
        confidence=confidence,
        risk_score=risk_score,
        inflation_score=inflation_score,
        growth_score=growth_score,
        liquidity_score=liquidity_score,
        drivers=_unique(drivers),
        cross_asset_confirmation=_unique(cross_asset_confirmation),
        leadership=_unique(leadership),
        fragilities=_unique(fragilities),
        narrative=narrative,
    )


def regime_as_dict(regime: CrossAssetRegime) -> dict[str, Any]:
    return regime.__dict__
