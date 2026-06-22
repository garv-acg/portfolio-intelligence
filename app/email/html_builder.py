from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path
from typing import Any


def _get(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _fmt_price(value: Any) -> str:
    try:
        if value is None:
            return "N/A"
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_number(value: Any) -> str:
    try:
        if value is None:
            return "N/A"
        value = float(value)
        if abs(value) >= 1000:
            return f"{value:,.1f}"
        return f"{value:,.2f}"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_pct(value: Any) -> str:
    try:
        if value is None:
            return "N/A"
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_date_short(value: Any) -> str:
    if not value:
        return "N/A"
    text = str(value)
    return text.replace("T", " ")[:16] + " UTC" if "T" in text else text


def _move_color(value: Any) -> str:
    try:
        if value is None:
            return "#9ca3af"
        value = float(value)
        if value > 0:
            return "#34d399"
        if value < 0:
            return "#f87171"
        return "#d1d5db"
    except (TypeError, ValueError):
        return "#9ca3af"


def _status_badge(status: Any, is_stale: Any = False) -> str:
    if is_stale:
        return '<span style="display:inline-block;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:700;background:#422006;color:#fde68a;border:1px solid #92400e;">Cached</span>'

    status_text = escape(str(status or "Unknown"))
    if status_text == "OK":
        bg, color, border = "#064e3b", "#a7f3d0", "#065f46"
    else:
        bg, color, border = "#3f1d1d", "#fecaca", "#7f1d1d"

    return f'<span style="display:inline-block;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:700;background:{bg};color:{color};border:1px solid {border};">{status_text}</span>'


def _section_title(number: str, title: str) -> str:
    return f"""
    <tr>
      <td style="padding:22px 0 10px 0;">
        <div style="font-size:13px;letter-spacing:0.08em;text-transform:uppercase;color:#94a3b8;font-weight:700;">{escape(number)}</div>
        <div style="font-size:21px;line-height:1.25;color:#f8fafc;font-weight:750;margin-top:2px;">{escape(title)}</div>
      </td>
    </tr>
    """


def _card(inner_html: str) -> str:
    return f"""
    <tr>
      <td style="background:#111827;border:1px solid #243244;border-radius:16px;padding:18px 18px;">
        {inner_html}
      </td>
    </tr>
    """


def _portfolio_totals(rows: list[Any]) -> dict[str, Any]:
    total_value = 0.0
    total_daily_pl = 0.0
    weighted_sum = 0.0
    priced_rows = 0
    movers = []

    for row in rows:
        value = _get(row, "market_value")
        daily_pl = _get(row, "daily_pl")
        change = _get(row, "day_change_pct")
        if value is not None:
            total_value += float(value)
            priced_rows += 1
        if daily_pl is not None:
            total_daily_pl += float(daily_pl)
        if value is not None and change is not None:
            weighted_sum += float(value) * float(change)
        if change is not None:
            movers.append(row)

    weighted_move = weighted_sum / total_value if total_value else None
    movers = sorted(movers, key=lambda r: abs(float(_get(r, "day_change_pct") or 0)), reverse=True)
    top_mover = movers[0] if movers else None

    return {
        "total_value": total_value if priced_rows else None,
        "total_daily_pl": total_daily_pl if priced_rows else None,
        "weighted_move": weighted_move,
        "top_mover": top_mover,
        "priced_rows": priced_rows,
        "total_rows": len(rows),
    }


def _summary_cards(rows: list[Any]) -> str:
    totals = _portfolio_totals(rows)
    pl_color = _move_color(totals["total_daily_pl"])
    weighted_color = _move_color(totals["weighted_move"])
    top = totals["top_mover"]
    top_text = "N/A"
    if top:
        top_text = f"{escape(str(_get(top, 'ticker')))} {_fmt_pct(_get(top, 'day_change_pct'))}"

    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px;border-collapse:collapse;">
      <tr>
        <td style="background:#020617;border:1px solid #1f2937;border-radius:14px;padding:14px 16px;width:25%;"><div style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;font-weight:800;">Portfolio Value</div><div style="color:#f8fafc;font-size:22px;font-weight:800;margin-top:5px;">{_fmt_price(totals["total_value"])}</div></td>
        <td style="width:10px;"></td>
        <td style="background:#020617;border:1px solid #1f2937;border-radius:14px;padding:14px 16px;width:25%;"><div style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;font-weight:800;">Daily P/L</div><div style="color:{pl_color};font-size:22px;font-weight:800;margin-top:5px;">{_fmt_price(totals["total_daily_pl"])}</div></td>
        <td style="width:10px;"></td>
        <td style="background:#020617;border:1px solid #1f2937;border-radius:14px;padding:14px 16px;width:25%;"><div style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;font-weight:800;">Weighted Move</div><div style="color:{weighted_color};font-size:22px;font-weight:800;margin-top:5px;">{_fmt_pct(totals["weighted_move"])}</div></td>
        <td style="width:10px;"></td>
        <td style="background:#020617;border:1px solid #1f2937;border-radius:14px;padding:14px 16px;width:25%;"><div style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;font-weight:800;">Largest Mover</div><div style="color:#f8fafc;font-size:18px;font-weight:800;margin-top:7px;">{top_text}</div></td>
      </tr>
    </table>
    """


def _portfolio_table(rows: list[Any]) -> str:
    if not rows:
        return '<p style="margin:0;color:#cbd5e1;font-size:14px;">No portfolio holdings were found.</p>'

    body = ""
    for row in rows:
        ticker = escape(str(_get(row, "ticker", "N/A")))
        name = escape(str(_get(row, "name", ticker)))
        shares = escape(str(_get(row, "shares", "N/A")))
        price = _fmt_price(_get(row, "price"))
        change = _fmt_pct(_get(row, "day_change_pct"))
        market_value = _fmt_price(_get(row, "market_value"))
        daily_pl = _fmt_price(_get(row, "daily_pl"))
        source = escape(str(_get(row, "source", "Unknown")))
        status = _get(row, "status", "Unknown")
        is_stale = bool(_get(row, "is_stale", False)) or "stale cache" in source.lower()
        as_of = _fmt_date_short(_get(row, "as_of"))
        color = _move_color(_get(row, "day_change_pct"))
        pl_color = _move_color(_get(row, "daily_pl"))
        clean_source = source.replace(" / stale cache", "")

        body += f"""
        <tr>
          <td style="padding:13px 10px;border-top:1px solid #1f2937;"><div style="font-weight:750;color:#f8fafc;font-size:14px;">{ticker}</div><div style="color:#94a3b8;font-size:12px;margin-top:2px;">{name}</div></td>
          <td align="right" style="padding:13px 10px;border-top:1px solid #1f2937;color:#cbd5e1;font-size:13px;">{shares}</td>
          <td align="right" style="padding:13px 10px;border-top:1px solid #1f2937;color:#f8fafc;font-size:13px;">{price}</td>
          <td align="right" style="padding:13px 10px;border-top:1px solid #1f2937;color:{color};font-size:13px;font-weight:700;">{change}</td>
          <td align="right" style="padding:13px 10px;border-top:1px solid #1f2937;color:{pl_color};font-size:13px;font-weight:700;">{daily_pl}</td>
          <td align="right" style="padding:13px 10px;border-top:1px solid #1f2937;color:#f8fafc;font-size:13px;">{market_value}</td>
          <td align="right" style="padding:13px 10px;border-top:1px solid #1f2937;">{_status_badge(status, is_stale)}</td>
          <td align="right" style="padding:13px 10px;border-top:1px solid #1f2937;"><div style="color:#94a3b8;font-size:12px;">{clean_source}</div><div style="color:#64748b;font-size:11px;margin-top:3px;">{as_of}</div></td>
        </tr>
        """

    return _summary_cards(rows) + f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
      <thead><tr><th align="left" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Holding</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Shares</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Price</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Move</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Daily P/L</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Value</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Status</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Source / As of</th></tr></thead>
      <tbody>{body}</tbody>
    </table>
    """


def _market_table(snapshot: dict[str, Any]) -> str:
    if not snapshot:
        return '<p style="margin:0;color:#cbd5e1;font-size:14px;">Market snapshot unavailable.</p>'

    body = ""
    for name, row in snapshot.items():
        asset = escape(str(name))
        ticker = escape(str(_get(row, "ticker", "")))
        price = _fmt_price(_get(row, "price"))
        change = _fmt_pct(_get(row, "day_change_pct"))
        source = escape(str(_get(row, "source", "Unknown")))
        status = _get(row, "status", "Unknown")
        is_stale = "stale cache" in source.lower()
        as_of = _fmt_date_short(_get(row, "as_of"))
        color = _move_color(_get(row, "day_change_pct"))
        clean_source = source.replace(" / stale cache", "")
        body += f"""
        <tr>
          <td style="padding:13px 10px;border-top:1px solid #1f2937;"><div style="font-weight:750;color:#f8fafc;font-size:14px;">{asset}</div><div style="color:#94a3b8;font-size:12px;margin-top:2px;">{ticker}</div></td>
          <td align="right" style="padding:13px 10px;border-top:1px solid #1f2937;color:#f8fafc;font-size:13px;">{price}</td>
          <td align="right" style="padding:13px 10px;border-top:1px solid #1f2937;color:{color};font-size:13px;font-weight:700;">{change}</td>
          <td align="right" style="padding:13px 10px;border-top:1px solid #1f2937;">{_status_badge(status, is_stale)}</td>
          <td align="right" style="padding:13px 10px;border-top:1px solid #1f2937;"><div style="color:#94a3b8;font-size:12px;">{clean_source}</div><div style="color:#64748b;font-size:11px;margin-top:3px;">{as_of}</div></td>
        </tr>
        """

    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;"><thead><tr><th align="left" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Asset</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Latest</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Move</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Status</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Source / As of</th></tr></thead><tbody>{body}</tbody></table>"""


def _macro_state_table(items: list[Any]) -> str:
    if not items:
        return '<p style="margin:0;color:#cbd5e1;font-size:14px;">No macro state data retrieved. Check FRED_API_KEY.</p>'
    body = ""
    for item in items:
        name = escape(str(_get(item, "name", "N/A")))
        actual = _fmt_number(_get(item, "actual"))
        prior = _fmt_number(_get(item, "prior"))
        unit = escape(str(_get(item, "unit", "")))
        release_date = escape(str(_get(item, "date", "N/A")))
        source = escape(str(_get(item, "source", "Unknown")))
        note = escape(str(_get(item, "note", "")))
        body += f"""<tr><td style="padding:13px 10px;border-top:1px solid #1f2937;"><div style="font-weight:750;color:#f8fafc;font-size:14px;">{name}</div><div style="color:#94a3b8;font-size:12px;margin-top:2px;">{release_date} · {source}</div></td><td align="right" style="padding:13px 10px;border-top:1px solid #1f2937;color:#f8fafc;font-size:13px;">{actual}</td><td align="right" style="padding:13px 10px;border-top:1px solid #1f2937;color:#cbd5e1;font-size:13px;">{prior}</td><td align="right" style="padding:13px 10px;border-top:1px solid #1f2937;color:#94a3b8;font-size:12px;">{unit}</td></tr><tr><td colspan="4" style="padding:0 10px 12px;color:#94a3b8;font-size:12px;line-height:1.45;">{note}</td></tr>"""
    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;"><thead><tr><th align="left" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Indicator</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Latest</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Prior</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Unit</th></tr></thead><tbody>{body}</tbody></table>"""


def _economic_calendar_table(items: list[Any], empty_message: str) -> str:
    if not items:
        return f'<p style="margin:0;color:#cbd5e1;font-size:14px;">{escape(empty_message)}</p>'
    body = ""
    for item in items:
        name = escape(str(_get(item, "name", "N/A")))
        event_date = escape(str(_get(item, "date", "N/A")))
        actual = _fmt_number(_get(item, "actual"))
        consensus = _fmt_number(_get(item, "consensus")) if _get(item, "consensus") is not None else "Not available"
        prior = _fmt_number(_get(item, "prior"))
        note = escape(str(_get(item, "note", "")))
        body += f"""<tr><td style="padding:13px 10px;border-top:1px solid #1f2937;"><div style="font-weight:750;color:#f8fafc;font-size:14px;">{name}</div><div style="color:#94a3b8;font-size:12px;margin-top:2px;">{event_date}</div></td><td align="right" style="padding:13px 10px;border-top:1px solid #1f2937;color:#f8fafc;font-size:13px;">{actual}</td><td align="right" style="padding:13px 10px;border-top:1px solid #1f2937;color:#cbd5e1;font-size:13px;">{consensus}</td><td align="right" style="padding:13px 10px;border-top:1px solid #1f2937;color:#cbd5e1;font-size:13px;">{prior}</td></tr><tr><td colspan="4" style="padding:0 10px 12px;color:#94a3b8;font-size:12px;line-height:1.45;">{note}</td></tr>"""
    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;"><thead><tr><th align="left" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Event</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Actual</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Consensus</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Prior</th></tr></thead><tbody>{body}</tbody></table>"""


def _fed_updates(items: list[Any]) -> str:
    if not items:
        return ""
    lis = "".join(f'<li style="margin:0 0 6px;color:#cbd5e1;font-size:13px;line-height:1.5;">{escape(str(item))}</li>' for item in items)
    return f"""<div style="margin-top:16px;margin-bottom:8px;color:#dbeafe;font-size:14px;font-weight:800;text-transform:uppercase;letter-spacing:0.04em;">Federal Reserve Updates</div><ul style="margin:0;padding-left:20px;">{lis}</ul>"""


def _cross_asset_regime_section(regime: Any) -> str:
    if not regime:
        return '<p style="margin:0;color:#cbd5e1;font-size:14px;">Cross-asset regime engine is not available.</p>'

    regime_name = escape(str(_get(regime, "regime", "Mixed / Transitional")))
    confidence = escape(str(_get(regime, "confidence", "N/A")))
    narrative = escape(str(_get(regime, "narrative", "")))

    risk_score = escape(str(_get(regime, "risk_score", "N/A")))
    inflation_score = escape(str(_get(regime, "inflation_score", "N/A")))
    growth_score = escape(str(_get(regime, "growth_score", "N/A")))
    liquidity_score = escape(str(_get(regime, "liquidity_score", "N/A")))

    def bullets(items: list[Any]) -> str:
        if not items:
            return '<li style="margin:0 0 6px;color:#94a3b8;font-size:13px;">No clear signal.</li>'
        return "".join(
            f'<li style="margin:0 0 6px;color:#cbd5e1;font-size:13px;line-height:1.45;">{escape(str(item))}</li>'
            for item in items
        )

    drivers = _get(regime, "drivers", []) or []
    cross_asset = _get(regime, "cross_asset_confirmation", []) or []
    leadership = _get(regime, "leadership", []) or []
    fragilities = _get(regime, "fragilities", []) or []

    return f"""
    <div style="margin-bottom:16px;">
      <div style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;font-weight:800;">Model-Inferred Market Regime</div>
      <div style="color:#f8fafc;font-size:27px;font-weight:850;margin-top:4px;">{regime_name}</div>
      <div style="color:#94a3b8;font-size:13px;margin-top:4px;">Confidence: {confidence}</div>
      <div style="color:#cbd5e1;font-size:14px;line-height:1.55;margin-top:8px;">{narrative}</div>
    </div>

    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:14px;border-collapse:collapse;">
      <tr>
        <td style="background:#020617;border:1px solid #1f2937;border-radius:14px;padding:12px;width:25%;"><div style="color:#94a3b8;font-size:10px;text-transform:uppercase;letter-spacing:0.08em;font-weight:800;">Risk</div><div style="color:#f8fafc;font-size:20px;font-weight:800;margin-top:4px;">{risk_score}/100</div></td>
        <td style="width:8px;"></td>
        <td style="background:#020617;border:1px solid #1f2937;border-radius:14px;padding:12px;width:25%;"><div style="color:#94a3b8;font-size:10px;text-transform:uppercase;letter-spacing:0.08em;font-weight:800;">Inflation</div><div style="color:#f8fafc;font-size:20px;font-weight:800;margin-top:4px;">{inflation_score}/100</div></td>
        <td style="width:8px;"></td>
        <td style="background:#020617;border:1px solid #1f2937;border-radius:14px;padding:12px;width:25%;"><div style="color:#94a3b8;font-size:10px;text-transform:uppercase;letter-spacing:0.08em;font-weight:800;">Growth</div><div style="color:#f8fafc;font-size:20px;font-weight:800;margin-top:4px;">{growth_score}/100</div></td>
        <td style="width:8px;"></td>
        <td style="background:#020617;border:1px solid #1f2937;border-radius:14px;padding:12px;width:25%;"><div style="color:#94a3b8;font-size:10px;text-transform:uppercase;letter-spacing:0.08em;font-weight:800;">Liquidity</div><div style="color:#f8fafc;font-size:20px;font-weight:800;margin-top:4px;">{liquidity_score}/100</div></td>
      </tr>
    </table>

    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
      <tr>
        <td style="vertical-align:top;background:#020617;border:1px solid #1f2937;border-radius:14px;padding:14px;width:25%;">
          <div style="color:#dbeafe;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px;">Primary Signals Identified</div>
          <ul style="margin:0;padding-left:18px;">{bullets(drivers)}</ul>
        </td>
        <td style="width:8px;"></td>
        <td style="vertical-align:top;background:#020617;border:1px solid #1f2937;border-radius:14px;padding:14px;width:25%;">
          <div style="color:#dbeafe;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px;">Cross-Asset Confirmation</div>
          <ul style="margin:0;padding-left:18px;">{bullets(cross_asset)}</ul>
        </td>
        <td style="width:8px;"></td>
        <td style="vertical-align:top;background:#020617;border:1px solid #1f2937;border-radius:14px;padding:14px;width:25%;">
          <div style="color:#dbeafe;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px;">Observed Leadership Patterns</div>
          <ul style="margin:0;padding-left:18px;">{bullets(leadership)}</ul>
        </td>
        <td style="width:8px;"></td>
        <td style="vertical-align:top;background:#020617;border:1px solid #1f2937;border-radius:14px;padding:14px;width:25%;">
          <div style="color:#dbeafe;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px;">Model-Identified Vulnerabilities</div>
          <ul style="margin:0;padding-left:18px;">{bullets(fragilities)}</ul>
        </td>
      </tr>
    </table>

<div style="margin-top:14px;padding:12px 14px;border:1px solid #1f2937;border-radius:12px;background:#020617;color:#94a3b8;font-size:12px;line-height:1.6;">
This section represents systematic inference generated from observed cross-asset market movements, macroeconomic data, and news-flow analysis. It does not represent factual prediction or investment advice.
</div>

    """


def _portfolio_news(news: list[Any]) -> str:
    if not news:
        return '<p style="margin:0;color:#cbd5e1;font-size:14px;">No high-confidence portfolio-specific developments were found in the configured sources.</p>'
    items = []
    for raw in news:
        title = _get(raw, "title", "Untitled article")
        ticker = _get(raw, "ticker")
        source = _get(raw, "source") or _get(raw, "publisher") or "Unknown source"
        url = _get(raw, "url")
        score = _get(raw, "relevance_score")
        confidence = _get(raw, "confidence", "N/A")
        source_tier = _get(raw, "source_tier", "N/A")
        label = f"{ticker}: {title} ({source})" if ticker else f"{title} ({source})"
        meta = f'<span style="color:#64748b;"> · {escape(str(confidence))} confidence · {escape(str(source_tier))} · score {escape(str(score))}</span>' if score else ""
        if url:
            items.append(f'<li style="margin:0 0 10px;color:#cbd5e1;font-size:14px;line-height:1.55;"><a href="{escape(str(url))}" style="color:#93c5fd;text-decoration:none;">{escape(label)}</a>{meta}</li>')
        else:
            items.append(f'<li style="margin:0 0 10px;color:#cbd5e1;font-size:14px;line-height:1.55;">{escape(label)}{meta}</li>')
    return f'<ul style="margin:0;padding-left:20px;">{"".join(items)}</ul>'


def _global_developments(items: list[Any]) -> str:
    if not items:
        return '<p style="margin:0;color:#cbd5e1;font-size:14px;">No major global developments were retrieved from configured free sources.</p>'
    lis = ""
    for item in items:
        category = escape(str(_get(item, "category", "Global")))
        title = escape(str(_get(item, "title", "Untitled")))
        source = escape(str(_get(item, "source", "Unknown")))
        url = _get(item, "url")
        summary = escape(str(_get(item, "summary", "")))
        score = escape(str(_get(item, "relevance_score", "")))
        confidence = escape(str(_get(item, "confidence", "N/A")))
        title_html = f'<a href="{escape(str(url))}" style="color:#93c5fd;text-decoration:none;">{title}</a>' if url else title
        lis += f"""<li style="margin:0 0 13px;color:#cbd5e1;font-size:14px;line-height:1.55;"><div style="font-size:11px;color:#38bdf8;text-transform:uppercase;letter-spacing:0.05em;font-weight:800;">{category}</div><div>{title_html} <span style="color:#64748b;">({source} · {confidence} confidence · score {score})</span></div><div style="color:#94a3b8;font-size:12px;margin-top:2px;">{summary}</div></li>"""
    return f'<ul style="margin:0;padding-left:20px;">{lis}</ul>'


def _earnings_calendar(items: list[Any]) -> str:
    if not items:
        return '<p style="margin:0;color:#cbd5e1;font-size:14px;">No portfolio earnings dates were identified within the configured 60-day window.</p>'
    rows = ""
    for item in items:
        ticker = escape(str(_get(item, "ticker", "N/A")))
        earnings_date = escape(str(_get(item, "earnings_date") or _get(item, "date") or "N/A"))
        source = escape(str(_get(item, "source", "Unknown")))
        rows += f'<tr><td style="padding:12px 10px;border-top:1px solid #1f2937;color:#f8fafc;font-weight:750;font-size:14px;">{ticker}</td><td align="right" style="padding:12px 10px;border-top:1px solid #1f2937;color:#cbd5e1;font-size:14px;">{earnings_date}</td><td align="right" style="padding:12px 10px;border-top:1px solid #1f2937;color:#94a3b8;font-size:12px;">{source}</td></tr>'
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;"><thead><tr><th align="left" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Ticker</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Date</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Source</th></tr></thead><tbody>{rows}</tbody></table>'


def _bullet_list(items: list[str]) -> str:
    if not items:
        return '<p style="margin:0;color:#cbd5e1;font-size:14px;">No verified developments found.</p>'
    lis = "".join(f'<li style="margin:0 0 8px;color:#cbd5e1;font-size:14px;line-height:1.55;">{escape(str(item))}</li>' for item in items)
    return f'<ul style="margin:0;padding-left:20px;">{lis}</ul>'


def _mini_svg_line(points: list[Any], key: str, width: int = 520, height: int = 110) -> str:
    if not points:
        return '<div style="color:#64748b;font-size:12px;">No chart data available.</div>'

    vals = []
    labels = []

    for p in points:
        try:
            value = float(p.get(key))
            vals.append(value)
            labels.append(str(p.get("date", "")))
        except Exception:
            continue

    if len(vals) < 2:
        return '<div style="color:#64748b;font-size:12px;">Insufficient chart data.</div>'

    min_v = min(vals)
    max_v = max(vals)

    if max_v == min_v:
        max_v += 1
        min_v -= 1

    coords = []
    for i, v in enumerate(vals):
        x = (i / (len(vals) - 1)) * width
        y = height - ((v - min_v) / (max_v - min_v)) * height
        coords.append(f"{x:.1f},{y:.1f}")

    path_points = " ".join(coords)
    start_label = labels[0] if labels else ""
    end_label = labels[-1] if labels else ""
    latest = vals[-1]

    return f"""
    <div style="background:#020617;border:1px solid #1f2937;border-radius:14px;padding:12px;">
      <svg width="100%" viewBox="0 0 {width} {height + 26}" preserveAspectRatio="none" style="display:block;">
        <polyline points="{path_points}" fill="none" stroke="#93c5fd" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
        <line x1="0" y1="{height}" x2="{width}" y2="{height}" stroke="#1f2937" stroke-width="1"/>
        <text x="0" y="{height + 20}" fill="#64748b" font-size="11">{escape(start_label)}</text>
        <text x="{width}" y="{height + 20}" text-anchor="end" fill="#64748b" font-size="11">{escape(end_label)}</text>
      </svg>
      <div style="color:#94a3b8;font-size:11px;margin-top:4px;">Latest: {latest:,.2f}</div>
    </div>
    """


def _bar(width_pct: Any, label: str = "", value: str = "", tone: str = "default") -> str:
    try:
        width = max(0, min(100, float(width_pct)))
    except Exception:
        width = 0

    fill = "#93c5fd"
    if tone == "positive":
        fill = "#86efac"
    elif tone == "negative":
        fill = "#fca5a5"
    elif tone == "neutral":
        fill = "#cbd5e1"

    return f"""
    <div style="width:100%;">
      <div style="display:flex;justify-content:space-between;gap:10px;margin-bottom:5px;">
        <span style="color:#cbd5e1;font-size:12px;font-weight:700;">{escape(label)}</span>
        <span style="color:#94a3b8;font-size:12px;">{escape(value)}</span>
      </div>
      <div style="background:#1f2937;border-radius:999px;height:9px;width:100%;overflow:hidden;">
        <div style="background:{fill};height:9px;width:{width:.1f}%;border-radius:999px;"></div>
      </div>
    </div>
    """


def _visual_analytics_section(analytics: Any) -> str:
    if not analytics:
        return '<p style="margin:0;color:#cbd5e1;font-size:14px;">Visual analytics are not available.</p>'

    allocation = _get(analytics, "allocation", []) or []
    sector_exposure = _get(analytics, "sector_exposure", []) or []
    attribution = _get(analytics, "daily_attribution", []) or []
    top_contributors = _get(analytics, "top_contributors", []) or []
    rolling_returns = _get(analytics, "rolling_returns", []) or []
    volatility = _get(analytics, "volatility_monitor", {}) or {}
    drawdown = _get(analytics, "drawdown", []) or []

    latest_return = _get(volatility, "latest_daily_return_pct")
    ann_vol = _get(volatility, "annualized_volatility_pct")
    vol_status = escape(str(_get(volatility, "status", "N/A")))
    realized_21d = _get(volatility, "realized_21d_volatility_pct")
    latest_drawdown = drawdown[-1]["drawdown_pct"] if drawdown else None

    def fmt_pct(value: Any, signed: bool = True) -> str:
        try:
            if signed:
                return f"{float(value):+.2f}%"
            return f"{float(value):.2f}%"
        except Exception:
            return "N/A"

    def fmt_money(value: Any) -> str:
        try:
            return f"${float(value):,.2f}"
        except Exception:
            return "N/A"

    def metric_card(title: str, value: str, sub: str = "") -> str:
        return f"""
        <td style="background:#020617;border:1px solid #1f2937;border-radius:16px;padding:14px;width:25%;vertical-align:top;">
          <div style="color:#94a3b8;font-size:10px;text-transform:uppercase;letter-spacing:0.08em;font-weight:800;">{escape(title)}</div>
          <div style="color:#f8fafc;font-size:22px;font-weight:850;margin-top:5px;">{escape(value)}</div>
          <div style="color:#64748b;font-size:11px;margin-top:4px;">{escape(sub)}</div>
        </td>
        """

    allocation_cards = ""
    for row in allocation[:8]:
        ticker = str(row.get("ticker", ""))
        sector = str(row.get("sector", "Unclassified"))
        weight = row.get("weight_pct", 0)
        value = fmt_money(row.get("value", 0))
        allocation_cards += f"""
        <tr>
          <td style="padding:10px 0;border-top:1px solid #1f2937;">
            {_bar(weight, f"{ticker} · {sector}", f"{fmt_pct(weight, signed=False)} · {value}")}
          </td>
        </tr>
        """

    sector_cards = ""
    for row in sector_exposure[:6]:
        sector = str(row.get("sector", "Unclassified"))
        weight = row.get("weight_pct", 0)
        sector_cards += f"""
        <tr>
          <td style="padding:10px 0;border-top:1px solid #1f2937;">
            {_bar(weight, sector, fmt_pct(weight, signed=False))}
          </td>
        </tr>
        """

    attribution_rows = ""
    max_abs_pl = max([abs(float(row.get("daily_pl", 0))) for row in attribution] or [1])

    for row in attribution[:8]:
        ticker = escape(str(row.get("ticker", "")))
        daily_pl = float(row.get("daily_pl", 0) or 0)
        move = row.get("move_pct", 0)
        contribution = row.get("contribution_pct", 0)
        tone = "positive" if daily_pl >= 0 else "negative"
        heat_width = (abs(daily_pl) / max_abs_pl) * 100 if max_abs_pl else 0

        attribution_rows += f"""
        <tr>
          <td style="padding:10px;border-top:1px solid #1f2937;color:#f8fafc;font-size:13px;font-weight:800;">{ticker}</td>
          <td style="padding:10px;border-top:1px solid #1f2937;width:42%;">{_bar(heat_width, '', '', tone)}</td>
          <td align="right" style="padding:10px;border-top:1px solid #1f2937;color:#cbd5e1;font-size:13px;">{fmt_money(daily_pl)}</td>
          <td align="right" style="padding:10px;border-top:1px solid #1f2937;color:#94a3b8;font-size:12px;">{fmt_pct(move)}</td>
          <td align="right" style="padding:10px;border-top:1px solid #1f2937;color:#94a3b8;font-size:12px;">{fmt_pct(contribution)}</td>
        </tr>
        """

    contributor_tiles = ""
    for row in top_contributors[:5]:
        ticker = escape(str(row.get("ticker", "")))
        daily_pl = float(row.get("daily_pl", 0) or 0)
        contribution = row.get("contribution_pct", 0)
        tone_color = "#86efac" if daily_pl >= 0 else "#fca5a5"

        contributor_tiles += f"""
        <td style="background:#020617;border:1px solid #1f2937;border-radius:14px;padding:12px;vertical-align:top;">
          <div style="color:#f8fafc;font-size:14px;font-weight:850;">{ticker}</div>
          <div style="color:{tone_color};font-size:18px;font-weight:850;margin-top:5px;">{fmt_money(daily_pl)}</div>
          <div style="color:#94a3b8;font-size:11px;margin-top:4px;">Contribution {fmt_pct(contribution)}</div>
        </td>
        <td style="width:8px;"></td>
        """

    if contributor_tiles.endswith('<td style="width:8px;"></td>'):
        contributor_tiles = contributor_tiles.rsplit('<td style="width:8px;"></td>', 1)[0]

    equity_chart = _mini_svg_line(rolling_returns, "portfolio_value")
    drawdown_chart = _mini_svg_line(drawdown, "drawdown_pct")

    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:14px;border-collapse:separate;border-spacing:0;">
      <tr>
        {metric_card("Latest Return", fmt_pct(latest_return), "Most recent portfolio daily return")}
        <td style="width:8px;"></td>
        {metric_card("Annualized Vol", fmt_pct(ann_vol), vol_status)}
        <td style="width:8px;"></td>
        {metric_card("21D Realized Vol", fmt_pct(realized_21d), "Short-term realized risk")}
        <td style="width:8px;"></td>
        {metric_card("Current Drawdown", fmt_pct(latest_drawdown), "From recent portfolio high")}
      </tr>
    </table>

    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:separate;border-spacing:0;margin-bottom:14px;">
      <tr>
        <td style="width:50%;vertical-align:top;padding-right:7px;">
          <div style="color:#dbeafe;font-size:12px;font-weight:850;text-transform:uppercase;letter-spacing:0.06em;margin:0 0 8px;">Portfolio Equity Curve</div>
          {equity_chart}
        </td>
        <td style="width:50%;vertical-align:top;padding-left:7px;">
          <div style="color:#dbeafe;font-size:12px;font-weight:850;text-transform:uppercase;letter-spacing:0.06em;margin:0 0 8px;">Drawdown Monitor</div>
          {drawdown_chart}
        </td>
      </tr>
    </table>

    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:separate;border-spacing:0;margin-bottom:14px;">
      <tr>
        <td style="width:50%;vertical-align:top;background:#020617;border:1px solid #1f2937;border-radius:16px;padding:14px;">
          <div style="color:#dbeafe;font-size:12px;font-weight:850;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px;">Allocation Map</div>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">{allocation_cards}</table>
        </td>
        <td style="width:12px;"></td>
        <td style="width:50%;vertical-align:top;background:#020617;border:1px solid #1f2937;border-radius:16px;padding:14px;">
          <div style="color:#dbeafe;font-size:12px;font-weight:850;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px;">Sector Concentration</div>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">{sector_cards}</table>
        </td>
      </tr>
    </table>

    <div style="margin:14px 0 8px;color:#dbeafe;font-size:12px;font-weight:850;text-transform:uppercase;letter-spacing:0.06em;">Daily Attribution Heatmap</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-bottom:14px;background:#020617;border:1px solid #1f2937;border-radius:16px;overflow:hidden;">
      <thead><tr>
        <th align="left" style="padding:10px;color:#94a3b8;font-size:11px;text-transform:uppercase;">Ticker</th>
        <th align="left" style="padding:10px;color:#94a3b8;font-size:11px;text-transform:uppercase;">Impact</th>
        <th align="right" style="padding:10px;color:#94a3b8;font-size:11px;text-transform:uppercase;">Daily P/L</th>
        <th align="right" style="padding:10px;color:#94a3b8;font-size:11px;text-transform:uppercase;">Move</th>
        <th align="right" style="padding:10px;color:#94a3b8;font-size:11px;text-transform:uppercase;">Contribution</th>
      </tr></thead>
      <tbody>{attribution_rows}</tbody>
    </table>

    <div style="margin:14px 0 8px;color:#dbeafe;font-size:12px;font-weight:850;text-transform:uppercase;letter-spacing:0.06em;">Top Contributor Tiles</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:separate;border-spacing:0;">
      <tr>{contributor_tiles}</tr>
    </table>
    """


def _sec_filings_section(items: list[Any]) -> str:
    if not items:
        return '<p style="margin:0;color:#cbd5e1;font-size:14px;">No high-priority SEC filings were identified for current portfolio holdings within the configured lookback window.</p>'

    rows = ""

    for item in items:
        ticker = escape(str(_get(item, "ticker", "N/A")))
        form_type = escape(str(_get(item, "form_type", "N/A")))
        signal_type = escape(str(_get(item, "signal_type", _get(item, "category", "SEC Filing"))))
        signal_summary = escape(str(_get(item, "signal_summary", _get(item, "title", "Untitled filing"))))
        source = escape(str(_get(item, "source", "SEC EDGAR")))
        filed_at = escape(str(_get(item, "filed_at", "N/A"))[:16].replace("T", " "))
        score = escape(str(_get(item, "relevance_score", "N/A")))
        confidence = escape(str(_get(item, "confidence", "N/A")))
        reason = escape(str(_get(item, "reason", "")))
        items_detected = _get(item, "items_detected", []) or []
        items_label = escape(", ".join(items_detected)) if items_detected else "No specific SEC item extracted"
        url = _get(item, "url")

        filing_link = (
            f'<a href="{escape(str(url))}" style="color:#93c5fd;text-decoration:none;">Open SEC filing</a>'
            if url
            else ""
        )

        rows += f"""
        <tr>
          <td style="padding:13px 10px;border-top:1px solid #1f2937;vertical-align:top;">
            <div style="font-weight:750;color:#f8fafc;font-size:14px;">{ticker} · {form_type}</div>
            <div style="color:#94a3b8;font-size:12px;margin-top:2px;">{signal_type} · {source} · {filed_at}</div>
            <div style="color:#64748b;font-size:11px;margin-top:4px;">{items_label}</div>
          </td>
          <td style="padding:13px 10px;border-top:1px solid #1f2937;color:#cbd5e1;font-size:13px;line-height:1.45;vertical-align:top;">
            <div style="color:#f8fafc;font-weight:650;">{signal_summary}</div>
            <div style="color:#64748b;font-size:11px;margin-top:5px;">{confidence} confidence · score {score} · {reason}</div>
            <div style="font-size:11px;margin-top:6px;">{filing_link}</div>
          </td>
        </tr>
        """

    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
      <thead>
        <tr>
          <th align="left" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Filing</th>
          <th align="left" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Primary-Source Signal Extraction</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    """

def _sources_section(payload: dict[str, Any]) -> str:
    sources = payload.get("sources", [])
    portfolio_snapshot = payload.get("portfolio_snapshot", [])
    market_snapshot = payload.get("market_snapshot", {})
    visual_analytics = payload.get("visual_analytics")
    source_lines = [str(source) for source in sources]
    detected = set()
    for item in portfolio_snapshot:
        source = _get(item, "source")
        if source and source != "Unavailable":
            detected.add(str(source).replace(" / stale cache", ""))
    if isinstance(market_snapshot, dict):
        for item in market_snapshot.values():
            source = _get(item, "source")
            if source and source != "Unavailable":
                detected.add(str(source).replace(" / stale cache", ""))
    if detected:
        source_lines.append(f"Market data via {', '.join(sorted(detected))}.")
    if not source_lines:
        source_lines.append("Configured sources returned no verified links.")
    return _bullet_list(source_lines)


def _headline_priority(item: Any, kind: str) -> int:
    title = str(_get(item, "title", "")).lower()
    score = int(_get(item, "relevance_score", 0) or 0)
    base = score

    if kind == "global":
        base += 35

    macro_terms = ["fed", "fomc", "powell", "rates", "treasury", "yield", "inflation", "cpi", "oil", "china", "ecb", "geopolitical", "iran", "tariff", "semiconductor", "ai"]
    if any(term in title for term in macro_terms):
        base += 25

    analyst_terms = ["raises pt", "price target", "keeps a buy", "analyst", "upgrade", "downgrade"]
    if any(term in title for term in analyst_terms):
        base -= 50

    return base


def _biggest_headline(portfolio_news: list[Any], global_developments: list[Any]) -> str:
    candidates: list[tuple[int, Any, str]] = []

    for item in portfolio_news:
        candidates.append((_headline_priority(item, "portfolio"), item, "portfolio"))

    for item in global_developments:
        candidates.append((_headline_priority(item, "global"), item, "global"))

    if not candidates:
        return '<p style="margin:0;color:#cbd5e1;font-size:14px;">No single verified headline was identified from the configured sources.</p>'

    _, top, kind = sorted(candidates, key=lambda row: row[0], reverse=True)[0]
    title = escape(str(_get(top, "title", "No title available")))
    source = escape(str(_get(top, "source", "Unknown source")))
    confidence = escape(str(_get(top, "confidence", "N/A")))
    category = escape(str(_get(top, "category", "Portfolio") if kind == "global" else _get(top, "ticker", "Portfolio")))
    url = _get(top, "url")

    title_html = f'<a href="{escape(str(url))}" style="color:#93c5fd;text-decoration:none;">{title}</a>' if url else title

    return f'<p style="margin:0;color:#cbd5e1;font-size:14px;line-height:1.6;">{title_html} <span style="color:#94a3b8;">({category} · {source} · {confidence} confidence)</span></p>'


def build_html_newsletter(payload: dict[str, Any], text_fallback: str | None = None) -> str:
    report_date = payload.get("date") or date.today().isoformat()
    portfolio_snapshot = payload.get("portfolio_snapshot", [])
    portfolio_news = payload.get("portfolio_news", [])
    market_snapshot = payload.get("market_snapshot", {})
    visual_analytics = payload.get("visual_analytics")
    macro_state = payload.get("macro_state", [])
    economic_calendar_today = payload.get("economic_calendar_today", [])
    economic_calendar_tomorrow = payload.get("economic_calendar_tomorrow", [])
    fed_updates = payload.get("fed_updates", [])
    macro_source_note = payload.get("macro_source_note")
    global_developments = payload.get("global_developments", [])
    cross_asset_regime = payload.get("cross_asset_regime")
    earnings_calendar = payload.get("earnings_calendar", [])
    sec_filings = payload.get("sec_filings", [])
    totals = _portfolio_totals(portfolio_snapshot)
    populated_count = totals["priced_rows"]
    total_count = totals["total_rows"]
    source_set = sorted({str(_get(item, "source")).replace(" / stale cache", "") for item in portfolio_snapshot if _get(item, "source") and _get(item, "source") != "Unavailable"})
    source_label = ", ".join(source_set) if source_set else "No verified prices"
    biggest_headline_html = _biggest_headline(portfolio_news, global_developments)
    macro_note_html = f'<div style="margin-top:14px;color:#64748b;font-size:12px;line-height:1.45;">{escape(str(macro_source_note))}</div>' if macro_source_note else ""
    economic_calendar_html = (
        '<div style="margin-bottom:16px;color:#dbeafe;font-size:14px;font-weight:800;text-transform:uppercase;letter-spacing:0.04em;">Today</div>'
        + _economic_calendar_table(economic_calendar_today, "No free economic calendar events are currently available for today from configured sources.")
        + '<div style="margin-top:18px;margin-bottom:16px;color:#dbeafe;font-size:14px;font-weight:800;text-transform:uppercase;letter-spacing:0.04em;">Tomorrow</div>'
        + _economic_calendar_table(economic_calendar_tomorrow, "No free economic calendar events are currently available for tomorrow from configured sources.")
        + _fed_updates(fed_updates)
        + macro_note_html
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Daily Market Brief</title></head>
<body style="margin:0;padding:0;background:#020617;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#020617;margin:0;padding:0;"><tr><td align="center" style="padding:28px 14px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:920px;width:100%;border-collapse:collapse;">
<tr><td style="padding:26px;border:1px solid #1e293b;border-radius:22px;background:linear-gradient(135deg,#0f172a 0%,#111827 52%,#020617 100%);"><div style="font-size:12px;letter-spacing:0.14em;text-transform:uppercase;color:#38bdf8;font-weight:800;">Daily Market Brief</div><div style="font-size:34px;line-height:1.12;color:#f8fafc;font-weight:800;margin-top:8px;">Institutional Portfolio Monitor</div><div style="font-size:14px;line-height:1.55;color:#cbd5e1;margin-top:10px;max-width:650px;">Factual market briefing for {escape(str(report_date))}. No investment advice, recommendations, forecasts, or trading instructions.</div><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:22px;border-collapse:collapse;"><tr><td style="background:#020617;border:1px solid #1f2937;border-radius:14px;padding:14px 16px;width:33%;"><div style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;font-weight:800;">Holdings Priced</div><div style="color:#f8fafc;font-size:24px;font-weight:800;margin-top:4px;">{populated_count}/{total_count}</div></td><td style="width:12px;"></td><td style="background:#020617;border:1px solid #1f2937;border-radius:14px;padding:14px 16px;width:33%;"><div style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;font-weight:800;">Market Data</div><div style="color:#f8fafc;font-size:15px;font-weight:750;margin-top:8px;">{escape(source_label)}</div></td><td style="width:12px;"></td><td style="background:#020617;border:1px solid #1f2937;border-radius:14px;padding:14px 16px;width:33%;"><div style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;font-weight:800;">Portfolio Value</div><div style="color:#f8fafc;font-size:22px;font-weight:800;margin-top:5px;">{_fmt_price(totals["total_value"])}</div></td></tr></table></td></tr>
{_section_title("01", "Portfolio Snapshot")}{_card(_portfolio_table(portfolio_snapshot))}
{_section_title("02", "Visual Intelligence")}{_card(_visual_analytics_section(visual_analytics))}
{_section_title("03", "Portfolio News")}{_card(_portfolio_news(portfolio_news))}
{_section_title("04", "US Market Update")}{_card(_market_table(market_snapshot))}
{_section_title("05", "Cross-Asset Regime")}{_card(_cross_asset_regime_section(cross_asset_regime))}
{_section_title("06", "Macro State Snapshot")}{_card(_macro_state_table(macro_state))}
{_section_title("07", "Economic Calendar")}{_card(economic_calendar_html)}
{_section_title("08", "Biggest Headline of the Day")}{_card(biggest_headline_html)}
{_section_title("09", "Global Developments")}{_card(_global_developments(global_developments))}
{_section_title("10", "Earnings Calendar")}{_card(_earnings_calendar(earnings_calendar))}
{_section_title("11", "SEC Filings Monitor")}{_card(_sec_filings_section(sec_filings))}
{_section_title("12", "Sources")}{_card(_sources_section(payload))}
<tr><td style="padding:22px 4px 0;color:#64748b;font-size:12px;line-height:1.6;text-align:center;">Factual market brief only. No investment advice, recommendations, forecasts, or trading instructions.</td></tr>
</table></td></tr></table></body></html>"""


def save_html_newsletter(payload: dict[str, Any], output_path: str | Path, text_fallback: str | None = None) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_html_newsletter(payload, text_fallback=text_fallback), encoding="utf-8")
    return output_path


def render_html_newsletter(payload: dict[str, Any], text_fallback: str | None = None) -> str:
    return build_html_newsletter(payload, text_fallback=text_fallback)


def build_html(payload: dict[str, Any], text_fallback: str | None = None) -> str:
    return build_html_newsletter(payload, text_fallback=text_fallback)


def build_email_html(payload: dict[str, Any], text_fallback: str | None = None) -> str:
    return build_html_newsletter(payload, text_fallback=text_fallback)
