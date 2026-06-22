
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pandas as pd



def _safe_row(row):
    if isinstance(row, dict):
        return row
    return {"Value": str(row)}

def _get(x: Any, key: str, default=None):
    return x.get(key, default) if isinstance(x, dict) else getattr(x, key, default)


def _money(v):
    try:
        return f"${float(v):,.2f}"
    except Exception:
        return "N/A"


def _pct(v):
    try:
        return f"{float(v):+.2f}%"
    except Exception:
        return "N/A"


def _section(key: str, title: str, summary: str, rows: list[dict[str, Any]], priority: int):
    return {"key": key, "title": title, "summary": summary, "rows": rows, "priority": priority}


def portfolio_snapshot(rows):
    if not rows:
        return _section("portfolio_snapshot", "Portfolio Snapshot", "No portfolio holdings found.", [], 10)
    df = pd.DataFrame(rows)
    value_col = "market_value" if "market_value" in df.columns else "value" if "value" in df.columns else None
    total = float(df[value_col].sum()) if value_col else 0.0
    out = []
    for _, r in df.iterrows():
        val = float(r.get(value_col, 0) or 0) if value_col else 0
        out.append({
            "Ticker": r.get("ticker", r.get("Ticker", "")),
            "Sector": r.get("sector", r.get("Sector", "N/A")),
            "Market Value": _money(val),
            "Weight": _pct((val / total * 100) if total else 0),
        })
    return _section("portfolio_snapshot", "Portfolio Snapshot", f"{len(out)} holding(s), estimated value {_money(total)}.", out, 10)


def top_movers(rows):
    if not rows:
        return _section("top_movers", "Top Movers", "No holdings movement data available.", [], 20)
    df = pd.DataFrame(rows)
    move_col = "daily_move_pct" if "daily_move_pct" in df.columns else "Daily Move (%)" if "Daily Move (%)" in df.columns else None
    if not move_col:
        return _section("top_movers", "Top Movers", "No daily movement field available.", [], 20)
    df["_abs"] = df[move_col].apply(lambda x: abs(float(x)) if pd.notna(x) else 0)
    df = df.sort_values("_abs", ascending=False).head(5)
    out = []
    for _, r in df.iterrows():
        out.append({
            "Ticker": r.get("ticker", r.get("Ticker", "")),
            "Daily Move": _pct(r.get(move_col)),
            "Weekly Move": _pct(r.get("weekly_move_pct", r.get("Weekly Move (%)"))),
            "Volume vs 30D Avg": f"{float(r.get('volume_vs_30d_avg') or 0):.2f}x" if r.get("volume_vs_30d_avg") is not None else "N/A",
        })
    return _section("top_movers", "Top Movers", "Largest absolute daily moves across current holdings.", out, 20)


def earnings_section(earnings):
    rows = []
    for e in earnings or []:
        ticker = str(_get(e, "ticker", "")).upper()
        if ticker:
            rows.append({"Ticker": ticker, "Date": str(_get(e, "date", ""))[:10], "Source": _get(e, "source", "Earnings Calendar")})
    return _section("earnings", "Earnings Calendar", f"{len(rows)} upcoming earnings event(s) found.", rows[:10], 30)


def sec_section(filings):
    rows = []
    for f in filings or []:
        ticker = str(_get(f, "ticker", "")).upper()
        if ticker:
            items = _get(f, "items_detected", []) or []
            rows.append({
                "Ticker": ticker,
                "Form": _get(f, "form_type", ""),
                "Date": str(_get(f, "filing_date", _get(f, "accepted_at", "")))[:10],
                "Items": ", ".join(items) if items else "N/A",
                "Factual Note": _get(f, "signal_summary", _get(f, "signal_type", "Recent filing detected")),
            })
    return _section("sec_filings", "SEC Filings", f"{len(rows)} recent SEC filing(s) found.", rows[:10], 40)


def alerts_section(alerts):
    rows = []
    for a in alerts or []:
        rows.append({
            "Type": a.get("alert_type", ""),
            "Severity": a.get("severity", ""),
            "Ticker": a.get("ticker", ""),
            "Title": a.get("title", ""),
            "Created": str(a.get("created_at", ""))[:19],
        })
    return _section("alerts", "Alerts", f"{len(rows)} alert(s) currently available.", rows[:10], 50)


def macro_section(macro):
    indicators = (macro or {}).get("Indicators", (macro or {}).get("macro_indicators", [])) or []
    rows = []
    for i in indicators:
        rows.append({
            "Indicator": i.get("Indicator", i.get("indicator", "")),
            "Latest": i.get("Latest", i.get("latest", "")),
            "Daily Change": _pct(i.get("Daily Change (%)", i.get("daily_change_pct"))),
            "Weekly Change": _pct(i.get("Weekly Change (%)", i.get("weekly_change_pct"))),
        })
    return _section("macro", "Macro Snapshot", f"{len(rows)} macro indicator(s) loaded.", rows[:10], 60)


def build_morning_brief(
    portfolio_rows=None,
    holdings_monitor_rows=None,
    earnings_calendar=None,
    sec_filings=None,
    alerts=None,
    macro_data=None,
    enabled_sections=None,
):
    enabled_sections = enabled_sections or ["portfolio_snapshot", "top_movers", "earnings", "sec_filings", "alerts", "macro"]
    sections = [
        portfolio_snapshot(portfolio_rows or []),
        top_movers(holdings_monitor_rows or []),
        earnings_section(earnings_calendar or []),
        sec_section(sec_filings or []),
        alerts_section(alerts or []),
        macro_section(macro_data or {}),
    ]
    sections = [s for s in sections if s["key"] in enabled_sections]
    sections = sorted(sections, key=lambda x: x["priority"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "title": "Daily Portfolio Brief",
        "subtitle": "Facts-first morning portfolio update.",
        "sections": sections,
    }


def render_brief_text(brief):
    lines = [brief.get("title", "Daily Portfolio Brief"), brief.get("subtitle", ""), f"Generated: {brief.get('generated_at', '')}", ""]
    for s in brief.get("sections", []):
        lines += [s.get("title", ""), "-" * len(s.get("title", "")), s.get("summary", "")]
        for row in s.get("rows", [])[:8]:
            lines.append(" • " + " | ".join([f"{k}: {v}" for k, v in row.items()]))
        lines.append("")
    return "\n".join(lines)



def _safe_dict(value):
    if isinstance(value, dict):
        return value
    return {"Value": str(value)}


def render_brief_html(brief):
    brief = _safe_dict(brief)

    css = """
    <style>
      body { font-family: Arial, sans-serif; background:#0b1020; color:#f8fafc; margin:0; padding:24px; }
      .brief { max-width: 920px; margin: 0 auto; }
      .header { border-bottom:1px solid #334155; padding-bottom:18px; margin-bottom:22px; }
      .title { font-size:28px; font-weight:800; margin:0; }
      .subtitle { color:#94a3b8; margin-top:8px; }
      .section { background:#111827; border:1px solid #243044; border-radius:16px; padding:18px; margin:16px 0; }
      .section h2 { margin:0 0 8px 0; font-size:18px; }
      .summary { color:#cbd5e1; margin-bottom:14px; }
      table { width:100%; border-collapse: collapse; font-size:13px; }
      th { text-align:left; color:#94a3b8; border-bottom:1px solid #334155; padding:8px; }
      td { border-bottom:1px solid #1f2937; padding:8px; vertical-align:top; }
      .meta { color:#64748b; font-size:12px; margin-top:8px; }
    </style>
    """

    html = [css, '<div class="brief"><div class="header">']
    html.append(f'<h1 class="title">{brief.get("title", "Daily Portfolio Brief")}</h1>')
    html.append(f'<div class="subtitle">{brief.get("subtitle", "")}</div>')
    html.append(f'<div class="meta">Generated: {brief.get("generated_at", "")}</div></div>')

    sections = brief.get("sections", [])
    if not isinstance(sections, list):
        sections = []

    for section in sections:
        section = _safe_dict(section)
        html.append(f'<div class="section"><h2>{section.get("title", "")}</h2>')
        html.append(f'<div class="summary">{section.get("summary", "")}</div>')

        rows = section.get("rows", [])
        if not isinstance(rows, list):
            rows = []

        rows = [_safe_dict(row) for row in rows]

        if rows:
            cols = list(rows[0].keys())
            html.append("<table><thead><tr>")
            html.append("".join(f"<th>{c}</th>" for c in cols))
            html.append("</tr></thead><tbody>")

            for row in rows:
                html.append("<tr>")
                html.append("".join(f"<td>{row.get(c, '')}</td>" for c in cols))
                html.append("</tr>")

            html.append("</tbody></table>")

        html.append("</div>")

    html.append("</div>")
    return "".join(html)

def save_morning_brief_outputs(brief, output_dir=Path("output")):
    output_dir.mkdir(parents=True, exist_ok=True)
    text_path = output_dir / "morning_brief_v2.txt"
    html_path = output_dir / "morning_brief_v2.html"
    text_path.write_text(render_brief_text(brief), encoding="utf-8")
    html_path.write_text(render_brief_html(brief), encoding="utf-8")
    return {"text": str(text_path), "html": str(html_path)}
