"""
generate_hybrid_newsletter.py
─────────────────────────────
Single newsletter pipeline.  Run directly:
    python generate_hybrid_newsletter.py

Or called via the control centre "Generate Newsletter" button (which runs
main.py, which in turn calls build_and_save_newsletter() below).

Design rules
────────────
- source_rank is used INTERNALLY for headline selection only.
  It is NEVER rendered in any output table or paragraph.
- No analyst opinions, price targets, or valuation commentary.
- No AI-generated investment conclusions.
- Facts, filings, catalysts, macro releases only.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import json
import html
import pandas as pd

from app.data.earnings import get_upcoming_earnings
from app.data.sec_filings import get_sec_filings
from app.data.alert_engine import latest_alerts, build_alerts, save_alerts
from app.data.holdings_monitor import build_holdings_change_monitor
from app.data.regime_engine import infer_cross_asset_regime
from app.data.market_workbench import macro_dashboard
from app.data.morning_brief_engine import build_morning_brief
from app.data.news_feed import (
    company_news,
    market_news,
    global_development_news as fetch_global_development_news,
)

# ── Paths ──────────────────────────────────────────────────────────────────────
OUTPUT_DIR        = Path("output")
USER_PORTFOLIO    = Path("data/users/demo/portfolio.csv")
FALLBACK_PORTFOLIO = Path("portfolio.csv")
MACRO_EVENTS_FILE = Path("data/macro_events.csv")
PREFERENCES_FILE  = Path("data/users/demo/newsletter_preferences.json")

# Set True to skip live news fetches during local testing
FAST_TEST_MODE = False


# ── Preferences ────────────────────────────────────────────────────────────────

SECTION_DEFAULTS = {
    "portfolio_snapshot":  True,
    "visual_intelligence": True,
    "top_movers":          True,
    "portfolio_news":      True,
    "market_update":       True,
    "macro_snapshot":      True,
    "economic_calendar":   True,
    "earnings_calendar":   True,
    "sec_monitoring":      True,
    "alerts":              True,
    "global_developments": True,
}


def load_preferences() -> dict:
    prefs = SECTION_DEFAULTS.copy()
    if not PREFERENCES_FILE.exists():
        PREFERENCES_FILE.parent.mkdir(parents=True, exist_ok=True)
        PREFERENCES_FILE.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
        return prefs
    try:
        prefs.update(json.loads(PREFERENCES_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return prefs


def remove_disabled_sections(html_body: str, prefs: dict) -> str:
    """Strip entire card blocks for any section the user has toggled off."""
    section_headings = {
        "portfolio_snapshot":  "Portfolio Snapshot",
        "visual_intelligence": "Visual Intelligence",
        "top_movers":          "Top Movers",
        "portfolio_news":      "Portfolio News",
        "market_update":       "Market Update",
        "macro_snapshot":      "Macro Snapshot",
        "economic_calendar":   "Economic Calendar",
        "earnings_calendar":   "Earnings Calendar",
        "sec_monitoring":      "SEC Monitoring",
        "alerts":              "Alerts",
        "global_developments": "Global Developments",
    }
    for key, heading in section_headings.items():
        if prefs.get(key, True):
            continue
        marker      = f"<h2>{heading}</h2>"
        marker_idx  = html_body.find(marker)
        if marker_idx == -1:
            continue
        card_start  = html_body.rfind('<div class="card">', 0, marker_idx)
        next_card   = html_body.find('<div class="card">', marker_idx + len(marker))
        footer      = html_body.find('<div class="footer">', marker_idx + len(marker))
        ends        = [x for x in [next_card, footer] if x != -1]
        if card_start == -1 or not ends:
            continue
        html_body = html_body[:card_start] + html_body[min(ends):]
    return html_body


# ── Portfolio ──────────────────────────────────────────────────────────────────

class Holding:
    def __init__(self, ticker, shares, cost_basis=0):
        self.ticker     = str(ticker).upper().strip()
        self.shares     = float(shares or 0)
        self.cost_basis = float(cost_basis or 0)


def load_portfolio() -> list[Holding]:
    path = USER_PORTFOLIO if USER_PORTFOLIO.exists() else FALLBACK_PORTFOLIO
    df   = pd.read_csv(path)
    return [
        Holding(
            ticker=row.get("ticker", ""),
            shares=row.get("shares", 0),
            cost_basis=row.get("cost_basis", 0),
        )
        for _, row in df.iterrows()
    ]


# ── Macro events CSV ───────────────────────────────────────────────────────────

_MACRO_SAMPLE = [
    {"event": "CPI Inflation",        "release_date": "2026-06-10", "time": "8:30 AM ET",  "importance": "High",   "actual": "4.2%", "expected": "3.9%", "prior": "3.6%", "last_updated": "2026-06-10", "source": "BLS",           "source_url": "https://www.bls.gov/schedule/news_release/cpi.htm"},
    {"event": "FOMC Rate Decision",   "release_date": "2026-06-17", "time": "2:00 PM ET",  "importance": "High",   "actual": "",     "expected": "Hold", "prior": "5.25–5.50%", "last_updated": "", "source": "Federal Reserve", "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"},
    {"event": "Jobs Report",          "release_date": "2026-06-05", "time": "8:30 AM ET",  "importance": "High",   "actual": "139K", "expected": "155K", "prior": "177K", "last_updated": "2026-06-05", "source": "BLS",           "source_url": "https://www.bls.gov/schedule/news_release/empsit.htm"},
    {"event": "PCE Inflation",        "release_date": "2026-05-29", "time": "8:30 AM ET",  "importance": "High",   "actual": "2.1%", "expected": "2.2%", "prior": "2.3%", "last_updated": "2026-05-29", "source": "BEA",           "source_url": "https://www.bea.gov/news/schedule"},
    {"event": "Retail Sales",         "release_date": "2026-06-17", "time": "8:30 AM ET",  "importance": "Medium", "actual": "",     "expected": "+0.3%","prior": "-0.4%","last_updated": "",           "source": "Census Bureau", "source_url": "https://www.census.gov/economic-indicators/"},
    {"event": "Fed Funds Probability","release_date": "Daily",      "time": "Market hours","importance": "Medium", "actual": "",     "expected": "",     "prior": "",     "last_updated": "",           "source": "CME FedWatch",  "source_url": "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"},
]


def ensure_macro_events_file() -> None:
    MACRO_EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    sample = pd.DataFrame(_MACRO_SAMPLE)
    if not MACRO_EVENTS_FILE.exists():
        sample.to_csv(MACRO_EVENTS_FILE, index=False)
        return
    existing = pd.read_csv(MACRO_EVENTS_FILE).fillna("")
    changed  = False
    for col in sample.columns:
        if col not in existing.columns:
            existing[col] = ""
            changed = True
    existing_events = set(existing["event"].astype(str))
    missing = sample[~sample["event"].astype(str).isin(existing_events)]
    if not missing.empty:
        existing = pd.concat([existing, missing], ignore_index=True)
        changed  = True
    if changed:
        existing[list(sample.columns)].to_csv(MACRO_EVENTS_FILE, index=False)


def fetch_fred_latest(series_id: str) -> str:
    """
    Fetches the most recent observation for a FRED series.
    Returns formatted value string or empty string on failure.
    Requires no API key for recent public series.
    """
    try:
        import requests as _req
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        r = _req.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            lines = [l for l in r.text.strip().split("\n") if l and not l.startswith("DATE")]
            if lines:
                parts = lines[-1].split(",")
                if len(parts) >= 2 and parts[1].strip() not in {"", "."}:
                    return parts[1].strip()
    except Exception:
        pass
    return ""


# FRED series IDs for key macro events
_FRED_SERIES = {
    "CPI Inflation":  ("CPIAUCSL", lambda v: f"{float(v):.1f}"),
    "PCE Inflation":  ("PCEPI",    lambda v: f"{float(v):.1f}"),
    "Jobs Report":    ("PAYEMS",   lambda v: f"{int(float(v)):,}K"),
    # Retail Sales: month-over-month % change computed from two consecutive readings
    # RSXFS = advance retail sales ex autos (millions USD)
    # We store the MoM % change as the actual
    "Retail Sales":   ("RSXFS",    None),   # handled specially below
    # FOMC: FEDFUNDS gives the effective rate; we use it to populate the prior column
    "FOMC Rate Decision": ("FEDFUNDS", None),  # handled specially below
}


def _fred_mom_pct(series_id: str) -> str:
    """Fetch two consecutive FRED observations and return MoM % change."""
    try:
        from app.config.settings import settings as _settings
        import requests as _req
        api_key = getattr(_settings, "fred_api_key", None)
        if not api_key:
            return ""
        r = _req.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id":  series_id,
                "api_key":    api_key,
                "file_type":  "json",
                "sort_order": "desc",
                "limit":      2,
            },
            timeout=10,
        )
        obs = [o for o in r.json().get("observations", []) if o.get("value") not in (None, ".")]
        if len(obs) < 2:
            return ""
        latest = float(obs[0]["value"])
        prior  = float(obs[1]["value"])
        if prior == 0:
            return ""
        mom = (latest - prior) / prior * 100
        return f"{mom:+.1f}%"
    except Exception:
        return ""


def _fred_rate(series_id: str) -> str:
    """Fetch latest FRED rate observation."""
    try:
        val = fetch_fred_latest(series_id)
        if not val:
            return ""
        return f"{float(val):.2f}%"
    except Exception:
        return ""


def refresh_macro_calendar_from_fred() -> None:
    """
    Updates macro_events.csv with latest FRED actuals where available.
    Called once per newsletter run.
    """
    try:
        import pandas as _pd
        from pathlib import Path as _Path
        path = _Path(str(MACRO_EVENTS_FILE))
        if not path.exists():
            return
        df = _pd.read_csv(path).fillna("")
        changed = False
        for event, (series, fmt) in _FRED_SERIES.items():
            try:
                mask = df["event"] == event
                if not mask.any():
                    continue

                # Special handlers
                if event == "Retail Sales":
                    import datetime as _dt3
                    release = str(df.loc[mask, "release_date"].values[0])[:10]
                    try:
                        past = _dt3.date.today() >= _dt3.date.fromisoformat(release)
                    except Exception:
                        past = True
                    display = _fred_mom_pct(series) if past else ""
                elif event == "FOMC Rate Decision":
                    # Use FEDFUNDS to auto-populate the prior rate
                    rate = _fred_rate(series)
                    if rate and str(df.loc[mask, "prior"].values[0]) != rate:
                        df.loc[mask, "prior"] = rate
                        changed = True
                    continue
                else:
                    val = fetch_fred_latest(series)
                    if not val:
                        continue
                    display = fmt(val)

                if display and str(df.loc[mask, "actual"].values[0]) != display:
                    df.loc[mask, "actual"] = display
                    if event == "Retail Sales":
                        df.loc[mask, "last_updated"] = str(__import__("datetime").date.today())
                    changed = True
            except Exception:
                pass
        if changed:
            df.to_csv(path, index=False)
    except Exception:
        pass


def fetch_fed_funds_probability() -> str:
    """
    Fetches the current CME FedWatch no-change probability for the next FOMC meeting.
    Uses 30-day fed funds futures price from Yahoo Finance (ZQ contract).
    The implied rate = 100 - futures price.
    Probability of no-change is inferred by comparing implied rate to current rate bands.

    Falls back to a web search of growbeansprout.com if futures unavailable.
    Returns a display string like "96.5% no change" or "" if unavailable.
    """
    import re as _re

    # Method 1: Yahoo Finance fed funds futures
    # June 2026 contract = ZQM26=F, July = ZQN26=F
    try:
        import requests as _req
        from datetime import date as _date

        month_codes = {1:"F",2:"G",3:"H",4:"J",5:"K",6:"M",7:"N",8:"Q",9:"U",10:"V",11:"X",12:"Z"}
        today = _date.today()
        # Use next month's contract as proxy for next meeting
        next_month = today.month + 1 if today.month < 12 else 1
        next_year  = today.year if today.month < 12 else today.year + 1
        symbol = f"ZQ{month_codes[next_month]}{str(next_year)[2:]}=F"

        r = _req.get(
            f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}",
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code == 200:
            data  = r.json()
            price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
            implied_rate = round(100 - price, 3)
            # Current rate is 3.50-3.75%; midpoint 3.625%
            # If implied rate within 12.5bps of midpoint → likely no change
            current_mid = 3.625
            if abs(implied_rate - current_mid) < 0.125:
                prob = "~97% no change"
            elif implied_rate < current_mid - 0.125:
                prob = f"cut likely (implied {implied_rate:.2f}%)"
            else:
                prob = f"hike risk (implied {implied_rate:.2f}%)"
            return prob
    except Exception:
        pass

    # Method 2: Scrape growbeansprout.com
    try:
        import requests as _req
        r = _req.get(
            "https://growbeansprout.com/tools/fedwatch",
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code == 200:
            match = _re.search(r"(\d{2,3}\.?\d*)\s*%\s*probability.*?maintain", r.text, _re.I)
            if not match:
                match = _re.search(r"(\d{2,3}\.?\d*)%.*?no.change", r.text, _re.I)
            if match:
                return f"{match.group(1)}% no change"
    except Exception:
        pass

    return ""


def load_macro_events() -> list[dict]:
    ensure_macro_events_file()
    refresh_macro_calendar_from_fred()  # pull latest FRED actuals
    df    = pd.read_csv(MACRO_EVENTS_FILE).fillna("")
    today = date.today().isoformat()
    rows  = []

    for _, row in df.iterrows():
        release_date = str(row.get("release_date", ""))
        last_updated = str(row.get("last_updated", ""))
        changed_today = release_date[:10] == today or last_updated[:10] == today

        days_until = ""
        try:
            if release_date and release_date.lower() != "daily":
                delta = (date.fromisoformat(release_date[:10]) - date.today()).days
                if delta == 0:
                    days_until = "Today"
                elif delta > 0:
                    days_until = f"{delta}d"
                else:
                    days_until = f"{abs(delta)}d ago"
            elif release_date.lower() == "daily":
                days_until = "Daily"
        except Exception:
            pass

        rows.append({
            "event":        row.get("event", ""),
            "release_date": release_date or "Not set",
            "time":         row.get("time", ""),
            "days_until":   days_until,
            "importance":   row.get("importance", ""),
            "actual":       row.get("actual",   "N/A") or "N/A",
            "expected":     row.get("expected", "N/A") or "N/A",
            "prior":        row.get("prior",    "N/A") or "N/A",
            "source":       row.get("source", ""),
            "changed_today": changed_today,
        })

    # Inject live Fed Funds probability into the daily row
    fed_prob = fetch_fed_funds_probability()
    for row in rows:
        if row.get("event") == "Fed Funds Probability" and fed_prob:
            row["actual"]   = fed_prob
            row["expected"] = "Next FOMC: Jun 17"
            row["prior"]    = "3.50-3.75%"

    def _sort_key(item):
        # Daily items always last
        if item.get("release_date", "").lower() == "daily":
            return (2, 0)
        if item.get("days_until") == "Today":
            return (0, 0)
        try:
            d = (date.fromisoformat(item["release_date"][:10]) - date.today()).days
            if d > 0:
                return (0, d)       # upcoming: ascending
            else:
                return (1, -d)      # past: most recent first
        except Exception:
            return (2, 0)

    return sorted(rows, key=_sort_key)


# ── SEC normalisation ──────────────────────────────────────────────────────────

def _sec_get(row, key, default=""):
    return row.get(key, default) if isinstance(row, dict) else getattr(row, key, default)


def _normalize_sec_rows(sec_filings: list) -> list[dict]:
    cleaned, seen = [], set()
    for row in sec_filings:
        ticker = str(_sec_get(row, "ticker", "")).upper()
        form   = _sec_get(row, "form_type") or _sec_get(row, "form") or ""
        filed  = (
            _sec_get(row, "filing_date") or _sec_get(row, "filingDate")
            or _sec_get(row, "filed_at")  or _sec_get(row, "filedAt")
            or _sec_get(row, "accepted_at") or _sec_get(row, "acceptedAt")
            or _sec_get(row, "date") or _sec_get(row, "filed")
            or _sec_get(row, "period_of_report") or _sec_get(row, "periodOfReport")
            or ""
        )
        filing_date = str(filed)[:10] if filed else ""

        # Pull the richest available description in priority order:
        # 1. signal_summary (full sentence built from filing text)
        # 2. factual_note (legacy field)
        # 3. signal_type (category label — last resort)
        signal_summary = _sec_get(row, "signal_summary", "")
        factual_note   = _sec_get(row, "factual_note",   "")
        signal_type    = _sec_get(row, "signal_type",    "")
        note = signal_summary or factual_note or signal_type or ""

        # Items detected (e.g. ["Item 5.02", "Item 1.01"])
        items_raw = _sec_get(row, "items_detected", [])
        if isinstance(items_raw, str):
            # handle serialised list
            import ast
            try:
                items_raw = ast.literal_eval(items_raw)
            except Exception:
                items_raw = [items_raw] if items_raw else []
        items_str = ", ".join(items_raw) if items_raw else ""

        # Build the display note: items first, then the summary sentence
        if items_str and note:
            display_note = f"[{items_str}] {note}"
        elif items_str:
            display_note = f"[{items_str}]"
        else:
            display_note = note

        key = (ticker, form, filing_date, note)
        if key in seen:
            continue
        seen.add(key)
        url = (
            _sec_get(row, "document_url") or _sec_get(row, "url") or
            _sec_get(row, "raw_document_url") or ""
        )
        # Importance tier: High / Medium / Low
        high_items  = {"Item 2.02", "Item 5.02", "Item 1.01", "Item 2.05"}
        medium_items = {"Item 1.02", "Item 2.06", "Item 3.01", "Item 7.01", "Item 8.01"}
        if any(i in items_raw for i in high_items) or form in {"10-Q", "10-K"}:
            importance = "High"
        elif any(i in items_raw for i in medium_items) or form in {"DEF 14A"}:
            importance = "Medium"
        else:
            importance = "Low"

        cleaned.append({
            "Ticker":       ticker,
            "Form":         form,
            "Date":         filing_date,
            "Imp.":         importance,
            "Type":         signal_type or "",
            "Factual Note": display_note,
            "url":          url,
        })
    return sorted(cleaned, key=lambda r: r.get("Date", ""), reverse=True)


# ── Text utilities ─────────────────────────────────────────────────────────────

_MOJIBAKE = {
    "\xe2\x80\x99": "’",
    "\xe2\x80\x98": "‘",
    "\xe2\x80\x9c": "“",
    "\xe2\x80\x9d": "”",
    "\xe2\x80\x93": "–",
    "\xe2\x80\x94": "—",
    "\xe2\x80\xa2": "•",
    "\xe2\x82\xac": "€",
    "\xc2\xa0": " ",
    "\xc2": "",
}


def clean_text(value) -> str:
    text = str(value if value is not None else "")
    # Step 1: Unicode codepoint replacements for double-encoded sequences
    # Must run BEFORE latin1 roundtrip which would destroy these
    _SECOND_PASS = [
        ("\u00e2\u20ac\u02dc", "\u2018"),
        ("\u00e2\u20ac\u2122", "\u2019"),
        ("\u00e2\u20ac\u0153", "\u201c"),
        ("\u00e2\u20ac\u201d", "\u201d"),
        ("\u00e2\u20ac\u201c", "\u2013"),
        ("\u00e2\u20ac\u201e", "\u2014"),
        ("\xe2\x82\xac",   "\u20ac"),
    ]
    for bad, good in _SECOND_PASS:
        text = text.replace(bad, good)
    # Step 2: byte-level mojibake replacements
    for bad, good in _MOJIBAKE.items():
        text = text.replace(bad, good)
    # Step 3: latin1 roundtrip for any remaining garbled sequences
    try:
        if "\u00e2" in text or "\u00c3" in text:
            text = text.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
    except Exception:
        pass
    return text

def esc(value) -> str:
    return html.escape(clean_text(value))


def pct(value) -> str:
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return "N/A"


def money(value) -> str:
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "N/A"


def number(value) -> str:
    try:
        return f"{float(value):,.2f}"
    except Exception:
        return str(value)


# ── Headline selection (source_rank used internally only) ──────────────────────

def _select_headline_row(company_rows: list[dict], market_rows: list[dict]) -> dict:
    rows = company_rows + market_rows
    if not rows:
        return {"ticker": "", "title": "No major headline found from approved sources.", "source": "N/A"}
    return sorted(
        rows,
        key=lambda r: (int(r.get("source_rank", 0) or 0), str(r.get("published", ""))),
        reverse=True,
    )[0]


# ── HTML rendering helpers ─────────────────────────────────────────────────────

def render_move_pill(value: str) -> str:
    val = str(value)
    cls = "move-pill"
    if val.startswith("+"):
        cls += " move-positive"
    elif val.startswith("-"):
        cls += " move-negative"
    return f'<span class="{cls}">{esc(val)}</span>'


def visual_bar(label: str, value: float, max_value: float = 100.0) -> str:
    try:
        pct_w   = max(0, min(100, float(value) / float(max_value) * 100))
        display = f"{float(value):.2f}%"
    except Exception:
        pct_w, display = 0, "N/A"
    return f"""
    <div class="bar-row">
      <div class="bar-label">{esc(label)}</div>
      <div class="bar-track"><div class="bar-fill" style="width:{pct_w:.1f}%;"></div></div>
      <div class="bar-value">{esc(display)}</div>
    </div>"""


def table_html(rows: list[dict], columns: list[str]) -> str:
    if not rows:
        return "<p class='muted'>No data available.</p>"
    out = ["<table><thead><tr>"]
    for col in columns:
        out.append(f"<th>{esc(col)}</th>")
    out.append("</tr></thead><tbody>")
    for row in rows:
        cls = "changed-row" if row.get("changed_today") else ""
        out.append(f"<tr class='{cls}'>")
        for col in columns:
            value = row.get(col, row.get(col.lower().replace(" ", "_"), ""))
            link  = row.get("link", row.get("Link", row.get("url", "")))
            # Color columns: Daily Move and Daily Change (%) get green/red pills
            # Monthly Change (%) gets bold
            col_lower = col.lower()
            if col_lower in {"daily move", "daily change (%)"}:
                val_str = str(value)
                if val_str.startswith("+"):
                    out.append(f"<td><span class='move-pill move-positive'>{esc(value)}</span></td>")
                elif val_str.startswith("-"):
                    out.append(f"<td><span class='move-pill move-negative'>{esc(value)}</span></td>")
                else:
                    out.append(f"<td>{esc(value)}</td>")
            elif col_lower in {"monthly change (%)"}:
                out.append(f"<td><strong>{esc(value)}</strong></td>")
            elif col in {"title", "Title", "Form", "Detail"} and link:
                out.append(f"<td><a href='{esc(link)}' target='_blank' rel='noopener'>{esc(value)}</a></td>")
            else:
                out.append(f"<td>{esc(value)}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


# ── Section builders ───────────────────────────────────────────────────────────

def build_visual_intelligence(portfolio_snapshot: list[dict], top_movers: list[dict]) -> str:
    if not portfolio_snapshot:
        return "<p class='muted'>No portfolio visual data available.</p>"

    largest     = portfolio_snapshot[0]
    top_3_weight = 0.0
    for row in portfolio_snapshot[:3]:
        try:
            top_3_weight += float(str(row.get("Weight", "0")).replace("%", "").replace("+", ""))
        except Exception:
            pass

    sector_weights: dict[str, float] = {}
    for row in portfolio_snapshot:
        sector = row.get("Sector", "Unknown")
        try:
            w = float(str(row.get("Weight", "0")).replace("%", "").replace("+", ""))
        except Exception:
            w = 0.0
        sector_weights[sector] = sector_weights.get(sector, 0.0) + w

    top_move = top_movers[0] if top_movers else {}
    bars     = "".join(visual_bar(s, w) for s, w in sorted(sector_weights.items(), key=lambda x: x[1], reverse=True)[:5])

    return f"""
    <div class="visual-grid">
      <div class="visual-metric">
        <div class="metric-label">Largest Holding</div>
        <div class="metric-value">{esc(largest.get("Ticker", ""))}</div>
        <div class="metric-sub">{esc(largest.get("Weight", ""))} of portfolio</div>
      </div>
      <div class="visual-metric">
        <div class="metric-label">Top 3 Concentration</div>
        <div class="metric-value">{top_3_weight:.2f}%</div>
        <div class="metric-sub">combined portfolio weight</div>
      </div>
      <div class="visual-metric">
        <div class="metric-label">Largest Daily Mover</div>
        <div class="metric-value">{esc(top_move.get("Ticker", "N/A"))}</div>
        <div class="metric-sub">{render_move_pill(top_move.get("Daily Move", "N/A"))} today</div>
      </div>
    </div>
    <div class="mini-section-title">Sector Exposure</div>
    <div class="bar-card">{bars}</div>"""


def build_risk_notes(portfolio_snapshot: list[dict]) -> list[str]:
    notes = []
    if not portfolio_snapshot:
        return notes
    try:
        top3 = sum(
            float(str(r.get("Weight", "0")).replace("%", "").replace("+", ""))
            for r in portfolio_snapshot[:3]
        )
        notes.append(f"Top 3 holdings account for {top3:.2f}% of total portfolio exposure.")
    except Exception:
        pass
    sector_weights: dict[str, float] = {}
    for row in portfolio_snapshot:
        sector = row.get("Sector", "Unknown")
        try:
            w = float(str(row.get("Weight", "0")).replace("%", "").replace("+", ""))
        except Exception:
            w = 0.0
        sector_weights[sector] = sector_weights.get(sector, 0.0) + w
    if sector_weights:
        largest = max(sector_weights.items(), key=lambda x: x[1])
        notes.append(f"{largest[0]} represents the largest sector exposure at {largest[1]:.2f}%.")
        if largest[1] > 40:
            notes.append("Portfolio remains concentrated in a small number of sectors.")
    return notes


def build_overnight_changes(
    top_movers: list[dict],
    sec_rows: list[dict],
    macro_rows: list[dict],
    company_news_rows: list[dict],
) -> list[str]:
    changes = []
    if top_movers:
        m = top_movers[0]
        changes.append(f"{m.get('Ticker')} moved {m.get('Daily Move')} on the session.")
    oil = next((r for r in macro_rows if r.get("Indicator") == "Oil"), None)
    if oil:
        changes.append(f"Oil moved {oil.get('Daily Change (%)')} with crude volatility remaining elevated.")
    if sec_rows:
        changes.append(f"{len(sec_rows)} recent SEC filing(s) identified across portfolio holdings.")
    # Only surface overnight news if it's a hard fact (earnings, filing, deal)
    # not a speculative or opinion piece that slipped through
    factual_keywords = ["earnings", "revenue", "filing", "deal", "contract",
                        "agreement", "acquisition", "merger", "announces",
                        "launches", "approved", "ceasefire", "commences"]
    for h in company_news_rows[:5]:
        title_low = str(h.get("title", h.get("Title", ""))).lower()
        if any(kw in title_low for kw in factual_keywords):
            changes.append(f"{h.get('ticker', h.get('Ticker', ''))}: {h.get('title', h.get('Title', ''))}")
            break
    return changes[:4]


def build_market_themes(market_news_rows: list[dict]) -> list[str]:
    joined = " ".join(str(r.get("title", r.get("Title", ""))).lower() for r in market_news_rows)
    themes = []
    if "inflation" in joined or "yield" in joined:
        themes.append("Treasury yields and inflation expectations remained a primary market focus.")
    if "oil" in joined or "crude" in joined:
        themes.append("Energy markets remained volatile amid geopolitical and supply concerns.")
    if "nasdaq" in joined or "technology" in joined:
        themes.append("Technology leadership continued driving broader equity performance.")
    if "fed" in joined:
        themes.append("Markets continued recalibrating expectations around Federal Reserve policy.")
    return themes[:4]


def build_position_notes(
    top_movers: list[dict],
    sec_rows: list[dict],
    earnings_rows: list[dict],
) -> list[dict]:
    notes, tracked = [], set()
    for mover in top_movers[:3]:
        ticker = mover.get("Ticker")
        if ticker in tracked:
            continue
        tracked.add(ticker)
        sec_count = len([x for x in sec_rows if x.get("Ticker") == ticker])
        earnings   = next((x for x in earnings_rows if x.get("Ticker") == ticker), None)
        parts      = [f"Daily move: {mover.get('Daily Move')}"]
        if sec_count:
            parts.append(f"{sec_count} recent SEC filing(s)")
        if earnings:
            parts.append(f"Earnings scheduled {earnings.get('Date')}")
        notes.append({"Ticker": ticker, "Notes": " | ".join(parts)})
    return notes


# ── CSS ────────────────────────────────────────────────────────────────────────

_CSS = """
<style>
  body { margin:0; padding:0; background:#f1f5f9; color:#0f172a;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
  .container { max-width:980px; margin:0 auto; padding:28px; }
  .header { padding:34px; border-radius:24px;
            background:linear-gradient(135deg,#0f172a 0%,#172554 100%);
            color:white; border:1px solid #1e293b;
            box-shadow:0 10px 30px rgba(15,23,42,.15); }
  .eyebrow { color:#93c5fd; font-size:12px; text-transform:uppercase;
             letter-spacing:.14em; font-weight:700; margin-bottom:10px; }
  h1 { margin:0 0 14px; font-size:48px; line-height:1.05; font-weight:800; color:white; }
  .subtitle { color:#dbeafe; font-size:18px; line-height:1.6; max-width:760px; }
  .generated { margin-top:22px; color:#cbd5e1; font-size:14px; }
  .card { background:white; border:1px solid #e2e8f0; border-radius:22px;
          padding:24px; margin:22px 0; box-shadow:0 4px 18px rgba(15,23,42,.05); }
  .card h2 { margin:0 0 16px; font-size:24px; color:#0f172a; font-weight:750; }
  .muted { color:#64748b; line-height:1.6; }
  table { width:100%; border-collapse:collapse; font-size:13px;
          table-layout:fixed; word-wrap:break-word; }
  th { text-align:left; color:#475569; border-bottom:2px solid #e2e8f0;
       padding:10px 8px; font-size:11px; text-transform:uppercase; letter-spacing:.04em; }
  td { border-bottom:1px solid #f1f5f9; padding:10px 8px; color:#0f172a;
       vertical-align:top; line-height:1.4; }
  tr:hover td { background:#f8fafc; }
  .changed-row td { background:#fef3c7; }
  .tag { display:inline-block; padding:6px 10px; border-radius:999px;
         background:#eff6ff; color:#1d4ed8; font-size:12px; margin-right:8px; font-weight:600; }
  .visual-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin:10px 0 18px; }
  .visual-metric { background:#f8fafc; border:1px solid #e2e8f0; border-radius:16px; padding:16px; }
  .metric-label { color:#64748b; font-size:11px; text-transform:uppercase;
                  letter-spacing:.06em; font-weight:700; }
  .metric-value { color:#0f172a; font-size:24px; font-weight:800; margin-top:8px; }
  .metric-sub   { color:#64748b; font-size:13px; margin-top:4px; }
  .mini-section-title { font-size:13px; font-weight:800; color:#334155;
                        margin:18px 0 10px; text-transform:uppercase; letter-spacing:.06em; }
  .bar-card { background:#f8fafc; border:1px solid #e2e8f0; border-radius:16px; padding:14px; }
  .bar-row  { display:grid; grid-template-columns:150px 1fr 70px;
              align-items:center; gap:10px; margin:10px 0; }
  .bar-label { color:#334155; font-size:13px; font-weight:600; }
  .bar-track { height:10px; background:#e2e8f0; border-radius:999px; overflow:hidden; }
  .bar-fill  { height:10px; background:#2563eb; border-radius:999px; }
  .bar-value { color:#475569; font-size:12px; text-align:right; font-weight:700; }
  .move-pill     { display:inline-block; padding:4px 10px; border-radius:999px;
                   font-size:12px; font-weight:700; background:#e2e8f0; color:#0f172a; }
  .move-positive { background:#dcfce7; color:#166534; }
  .move-negative { background:#fee2e2; color:#991b1b; }
  .footer { color:#64748b; font-size:13px; margin-top:28px; text-align:center; }
  @media only screen and (max-width:700px) {
    h1 { font-size:34px; } .card { padding:18px; } table { font-size:12px; }
  }
</style>"""


# ── Main build function ────────────────────────────────────────────────────────


def _cal_actual_html(event, actual, expected):
    if not actual or actual in ('', 'N/A', 'nan', 'NaN'): return ''
    el = event.lower()
    if 'fomc' in el: return '<strong>' + actual + '</strong>'
    if 'fed funds' in el or 'probability' in el: return actual
    def n(v):
        try: return float(str(v).replace('%','').replace('K','').replace('+','').replace(',','').strip())
        except: return None
    a, e = n(actual), n(expected)
    if a is None or e is None: return actual
    if any(w in el for w in ['cpi','pce','inflation']):
        css = 'move-positive' if a <= e else 'move-negative'
    elif any(w in el for w in ['job','payroll','employment']):
        css = 'move-positive' if a >= e else 'move-negative'
    elif 'retail' in el:
        css = 'move-positive' if a >= e else 'move-negative'
    else: return actual
    return "<span class='move-pill " + css + "'>" + actual + '</span>'


def _render_cal(rows):
    hdrs = ['Event','Date','Time','Days','Imp.','Actual','Exp.','Prior','Source']
    out = ['<table><thead><tr>'] + [f'<th>{h}</th>' for h in hdrs] + ['</tr></thead><tbody>']
    for r in rows:
        cls = 'changed-row' if r.get('changed_today') else ''
        out.append(f"<tr class='{cls}'>")
        out += [
            f"<td>{esc(r.get('event',''))}</td>",
            f"<td>{esc(r.get('release_date',''))}</td>",
            f"<td>{esc(r.get('time',''))}</td>",
            f"<td>{esc(r.get('days_until',''))}</td>",
            f"<td>{esc(r.get('importance',''))}</td>",
            f"<td>{_cal_actual_html(r.get('event',''),r.get('actual',''),r.get('expected',''))}</td>",
            f"<td>{esc(r.get('expected',''))}</td>",
            f"<td>{esc(r.get('prior',''))}</td>",
            f"<td>{esc(r.get('source',''))}</td>",
            '</tr>',
        ]
    out.append('</tbody></table>')
    return ''.join(out)



def build_catalyst_timeline(earnings_rows, macro_events):
    from datetime import date as _date
    today = _date.today()
    items = []
    for e in earnings_rows:
        date_str = e.get('Date', '')
        try:
            d = _date.fromisoformat(date_str[:10])
            delta = (d - today).days
            if 0 <= delta <= 90:
                items.append({'Date': date_str[:10], 'Days': e.get('Days', f'{delta}d'), 'Type': 'Earnings', 'Event': f"{e.get('Ticker','')} Earnings", 'Note': ''})
        except Exception:
            pass
    for row in macro_events:
        date_str = row.get('release_date', '')
        if date_str.lower() == 'daily':
            continue
        try:
            d = _date.fromisoformat(date_str[:10])
            delta = (d - today).days
            if 0 <= delta <= 90:
                imp = row.get('importance', '')
                items.append({'Date': date_str[:10], 'Days': f'{delta}d' if delta > 0 else 'Today', 'Type': 'Macro', 'Event': row.get('event', ''), 'Note': f'[{imp}]' if imp else ''})
        except Exception:
            pass
    return sorted(items, key=lambda x: x.get('Date', ''))


def build_hybrid_newsletter() -> tuple[str, str]:
    prefs    = load_preferences()
    holdings = load_portfolio()
    tickers  = [h.ticker for h in holdings]

    # ── Fetch data ─────────────────────────────────────────────────────────────
    if FAST_TEST_MODE:
        company_news_rows = market_news_rows = global_news_rows = []
    else:
        company_news_rows = company_news(tickers, per_ticker=3)
        market_news_rows  = market_news(limit=8)
        global_news_rows  = fetch_global_development_news(limit=8)

    earnings  = list(get_upcoming_earnings(tickers, days_ahead=90))  # copy to prevent mutation
    sec       = get_sec_filings(tickers, lookback_days=30, max_filings_per_ticker=5)
    macro     = macro_dashboard()
    monitor   = build_holdings_change_monitor(
        holdings, earnings_calendar=earnings, sec_filings=sec, benchmark="SPY"
    )

    # Clear today's alerts and rebuild fresh from current data
    holdings_for_alerts = monitor.get("holdings", [])
    try:
        import sqlite3 as _sqlite3, pathlib as _pathlib
        for _db in ["data/history.db", "data/users/demo/history.db", "history.db"]:
            if _pathlib.Path(_db).exists():
                _conn = _sqlite3.connect(_db)
                _conn.execute("DELETE FROM alerts")
                _conn.commit()
                _conn.close()
                break
    except Exception:
        pass

    # Build cross-asset regime from live market data
    macro_rows_raw = macro.get("Indicators", macro.get("macro_indicators", [])) if isinstance(macro, dict) else []
    try:
        cross_asset_regime = infer_cross_asset_regime(
            market_snapshot={name: row for name, row in {
                "S&P 500": next((r for r in macro_rows_raw if r.get("Ticker") == "SPY"), {}),
                "Nasdaq":  next((r for r in macro_rows_raw if r.get("Ticker") == "QQQ"), {}),
                "10-Year": next((r for r in macro_rows_raw if "TNX" in str(r.get("Ticker",""))), {}),
                "WTI":     next((r for r in macro_rows_raw if r.get("Ticker") == "CL=F"), {}),
                "Gold":    next((r for r in macro_rows_raw if r.get("Ticker") == "GC=F"), {}),
                "Dollar":  next((r for r in macro_rows_raw if "DX" in str(r.get("Ticker",""))), {}),
            }.items()},
            macro_state=[],
            global_developments=global_news_rows,
            portfolio_news=company_news_rows,
        )
    except Exception:
        from app.data.regime_engine import CrossAssetRegime
        cross_asset_regime = CrossAssetRegime(
            regime="Mixed / Transitional", confidence="Low",
            risk_score=50, inflation_score=50, growth_score=50, liquidity_score=50,
            drivers=[], cross_asset_confirmation=[], leadership=[], fragilities=[],
            narrative="Regime data unavailable.",
        )

    alert_payload = {
        "portfolio_snapshot": [
            {
                "ticker":        row.get("ticker", ""),
                "day_change_pct": row.get("daily_move_pct"),
            }
            for row in holdings_for_alerts
        ],
        "earnings_calendar": earnings,
        "sec_filings":       sec,
        "cross_asset_regime": {"regime": cross_asset_regime.regime},
    }
    fresh_alerts = build_alerts(alert_payload)
    save_alerts(fresh_alerts)
    alerts = latest_alerts(limit=25)

    build_morning_brief(
        portfolio_rows=holdings_for_alerts,
        holdings_monitor_rows=holdings_for_alerts,
        earnings_calendar=earnings,
        sec_filings=sec,
        alerts=alerts,
        macro_data=macro,
    )

    holdings_rows = monitor.get("holdings", [])
    macro_events  = load_macro_events()

    # ── Top movers ─────────────────────────────────────────────────────────────
    def _is_valid_move(val: str) -> bool:
        """Return True if the value is a real number, not nan or N/A."""
        try:
            v = float(str(val).replace("%", "").replace("+", "").replace("x", ""))
            import math
            return not math.isnan(v) and not math.isinf(v)
        except Exception:
            return False

    top_movers = sorted(
        [
            {
                "Ticker":            row.get("ticker", ""),
                "Daily Move":        pct(row.get("daily_move_pct")),
                "Weekly Move":       pct(row.get("weekly_move_pct")),
                "Volume vs 30D Avg": (
                    f"{float(row.get('volume_vs_30d_avg')):.2f}x"
                    if row.get("volume_vs_30d_avg") is not None else "N/A"
                ),
            }
            for row in holdings_rows
            # Skip rows where price data failed to load
            if _is_valid_move(pct(row.get("daily_move_pct")))
        ],
        key=lambda r: abs(float(str(r["Daily Move"]).replace("%", "").replace("+", "") or 0))
            if r["Daily Move"] != "N/A" else 0,
        reverse=True,
    )[:5]

    # ── Portfolio snapshot ─────────────────────────────────────────────────────
    portfolio_snapshot = [
        {
            "Ticker":       row.get("ticker", ""),
            "Sector":       row.get("sector", ""),
            "Weight":       pct(row.get("portfolio_weight_pct")),
            "Market Value": money(row.get("market_value")),
            "Daily Move":   pct(row.get("daily_move_pct")),
        }
        for row in holdings_rows
        if _is_valid_move(pct(row.get("daily_move_pct")))
    ]

    # ── Earnings ───────────────────────────────────────────────────────────────
    from datetime import date as _date
    def _days_until(date_str):
        try:
            delta = (_date.fromisoformat(str(date_str)[:10]) - _date.today()).days
            if delta == 0: return "Today"
            if delta > 0:  return f"{delta}d"
            return f"{abs(delta)}d ago"
        except Exception:
            return ""

    earnings_rows = [
        {
            "Ticker": getattr(e, "ticker", "") if not isinstance(e, dict) else e.get("ticker", ""),
            "Date":   str(getattr(e, "date",   "") if not isinstance(e, dict) else e.get("date",   ""))[:10],
            "Days":   _days_until(getattr(e, "date", "") if not isinstance(e, dict) else e.get("date", "")),
            "Source": getattr(e, "source", "Yahoo Finance") if not isinstance(e, dict) else e.get("source", "Yahoo Finance"),
        }
        for e in (earnings or [])
    ]

    # Sort by proximity so nearest earnings is always first
    earnings_rows.sort(key=lambda r: int(r["Days"].replace("d","")) if r.get("Days","").endswith("d") and r["Days"] != "Today" else (0 if r.get("Days") == "Today" else 999))

    # ── SEC filings ────────────────────────────────────────────────────────────
    sec_rows = _normalize_sec_rows(sec or [])

    # ── Alerts ─────────────────────────────────────────────────────────────────
    seen_alerts, alert_rows = set(), []
    for a in (alerts or []):
        key = (a.get("alert_type", ""), a.get("ticker", ""), a.get("title", ""))
        if key in seen_alerts:
            continue
        seen_alerts.add(key)
        message = a.get("message", "")
        title   = a.get("title",   "")
        # Map severity to 3-tier hierarchy
        severity = a.get("severity", "")
        alert_type = a.get("alert_type", "")
        if severity == "High" or alert_type in {"SEC Item 5.02", "Regime Shift", "Drawdown"}:
            tier = "Critical"
        elif severity == "Medium" or alert_type in {"Earnings", "Large Move"}:
            tier = "Important"
        else:
            tier = "Informational"

        alert_rows.append({
            "Tier":     tier,
            "Type":     alert_type,
            "Ticker":   a.get("ticker",     ""),
            "Detail":   message if message else title,
            "url":      a.get("url", a.get("link", "")),
        })

    # ── Macro rows ─────────────────────────────────────────────────────────────
    macro_rows_raw = macro.get("Indicators", macro.get("macro_indicators", [])) if isinstance(macro, dict) else []
    macro_rows = []
    for row in macro_rows_raw:
        clean = {}
        for k, v in row.items():
            if "change" in str(k).lower():
                clean[k] = pct(v)
            elif isinstance(v, (float, int)):
                clean[k] = number(v)
            else:
                clean[k] = v
        macro_rows.append(clean)

    # ── Global developments (source_rank stripped from display) ────────────────
    global_development_rows = [
        {
            "Category":  row.get("category",  ""),
            "Title":     clean_text(row.get("title", "")),
            "Published": str(row.get("published", ""))[:10],
            "Source":    row.get("source",     ""),
            "link":      row.get("link",       ""),
        }
        for row in global_news_rows
        if row.get("title")
    ] or [{"Category": "", "Title": "No global development headlines found.", "Published": "", "Source": "", "link": ""}]

    # ── Headline (source_rank used for selection only, not rendered) ────────────
    headline_row    = _select_headline_row(company_news_rows, market_news_rows)
    headline_source = headline_row.get("source", "N/A")
    headline_ticker = headline_row.get("ticker", "")
    headline_title  = headline_row.get("title", "No major headline found from approved sources.")
    headline_pubdate = str(headline_row.get("published", ""))[:10] or "—"
    biggest_headline = f"{headline_ticker + ': ' if headline_ticker else ''}{headline_title}"

    # ── Overnight changes & executive summary ───────────────────────────────────
    overnight_changes = build_overnight_changes(top_movers, sec_rows, macro_rows, company_news_rows)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ── Executive summary — lead with market context, surface key signals ──────
    def _build_executive_summary() -> str:
        parts = []

        # 1. Market session context from biggest headline
        headline_title_low = headline_title.lower()
        if any(w in headline_title_low for w in ["ceasefire", "iran", "war", "peace", "deal"]):
            parts.append(f"Geopolitical developments drove market action today.")
        elif any(w in headline_title_low for w in ["fed", "rate hike", "rate cut", "inflation", "cpi", "fomc"]):
            parts.append(f"Rate and inflation concerns dominated market sentiment.")
        elif any(w in headline_title_low for w in ["rally", "gain", "jump", "surge", "advance", "rise"]):
            parts.append(f"Equities advanced on the session.")
        elif any(w in headline_title_low for w in ["fall", "drop", "decline", "slide", "sell", "plunge", "crash"]):
            parts.append(f"Equities sold off on the session.")
        else:
            parts.append(f"Markets were mixed on the session.")

        # 2. Portfolio movers — top 2 gainers and biggest loser
        gainers  = [m for m in top_movers if m.get("Daily Move", "").startswith("+")]
        losers   = [m for m in top_movers if m.get("Daily Move", "").startswith("-")]
        mover_parts = []
        for m in gainers[:2]:
            mover_parts.append(f"<span style='color:#16a34a;font-weight:600'>{m['Ticker']} {m['Daily Move']}</span>")
        for m in losers[:1]:
            mover_parts.append(f"<span style='color:#dc2626;font-weight:600'>{m['Ticker']} {m['Daily Move']}</span>")
        if mover_parts:
            parts.append(f"Portfolio movers: {', '.join(mover_parts)}.")

        # 3. Key macro signal — oil and yields
        oil_row = next((r for r in macro_rows if r.get("Indicator") == "Oil"), None)
        vix_row = next((r for r in macro_rows if r.get("Indicator") == "VIX"), None)
        macro_notes = []
        if oil_row:
            oil_move = oil_row.get("Daily Change (%)", "")
            if oil_move and oil_move != "N/A":
                oil_col = "#dc2626" if str(oil_move).startswith("-") else "#16a34a"
                macro_notes.append(f"Oil <span style='color:{oil_col};font-weight:600'>{oil_move}</span>")
        if vix_row:
            vix_val = vix_row.get("Latest", "")
            try:
                vix_float = float(str(vix_val).replace(",",""))
                if vix_float > 25:
                    macro_notes.append(f"VIX elevated at {vix_val}")
                elif vix_float < 15:
                    macro_notes.append(f"VIX low at {vix_val}")
            except Exception:
                pass
        if macro_notes:
            parts.append(f"{'; '.join(macro_notes)}.")

        # 4. Critical alerts
        critical = [a for a in alert_rows if a.get("Tier") == "Critical"]
        if critical:
            c = critical[0]
            parts.append(
                f"Critical alert: {c.get('Type','')} on {c.get('Ticker','')}."
                if c.get("Ticker") else
                f"Critical alert: {c.get('Type','')}."
            )

        # 5. Most urgent upcoming catalyst
        upcoming_macro = [
            row for row in macro_events
            if row.get("release_date","").lower() != "daily"
            and row.get("importance","") == "High"
            and row.get("days_until","").endswith("d")
            and not row.get("days_until","").endswith("ago")
        ]
        next_earnings = earnings_rows[0] if earnings_rows else None
        catalyst_parts = []
        if upcoming_macro:
            m = upcoming_macro[0]
            catalyst_parts.append(f"{m['event']} in {m['days_until']}")
        if next_earnings:
            catalyst_parts.append(
                f"{next_earnings.get('Ticker','')} earnings in {next_earnings.get('Days','')}"
            )
        if catalyst_parts:
            parts.append(f"Watch: {'; '.join(catalyst_parts)}.")

        return " ".join(parts)

    executive_summary = _build_executive_summary()

    # ── Portfolio news display columns (no source_rank) ────────────────────────
    # Deduplicate by normalised title (handles same story from different URLs)
    _seen_titles = set()
    portfolio_news_rows = []
    for r in company_news_rows[:20]:
        title = clean_text(r.get("title", r.get("Title", "")))
        # Normalise: lowercase, strip source suffix after " - "
        norm = title.lower().split(" - ")[0].strip()
        if norm in _seen_titles:
            continue
        _seen_titles.add(norm)
        portfolio_news_rows.append({
            "Ticker":    r.get("ticker",    r.get("Ticker", "")),
            "Title":     title,
            "Published": r.get("published", r.get("Published", ""))[:10] if r.get("published") or r.get("Published") else "",
            "Source":    r.get("source",    r.get("Source", "")),
            "link":      r.get("link",      r.get("Link",   "")),
        })
        if len(portfolio_news_rows) >= 12:
            break

    # ── HTML body ──────────────────────────────────────────────────────────────
    html_body = f"""
<html>
<head>{_CSS}</head>
<body>
  <div class="container">

    <div class="header">
      <div class="eyebrow">Daily Portfolio Brief</div>
      <h1>Morning Portfolio Update</h1>
      <div class="subtitle">Facts-first portfolio monitoring: market movement, catalysts, macro events, SEC filings, and alerts.</div>
      <p class="generated">Generated: {esc(generated_at)}</p>
    </div>

    <div class="card">
      <h2>Executive Summary</h2>
      <p>{executive_summary}</p>
    </div>


    <div class="card">
      <h2>Biggest Headline of the Day</h2>
      <p><strong>{"<a href='" + esc(headline_row.get("link","")) + "' target='_blank' rel='noopener'>" + esc(biggest_headline) + "</a>" if headline_row.get("link") else esc(biggest_headline)}</strong></p>
      <p class="muted">Source: {esc(headline_source)} &mdash; Published: {esc(headline_pubdate)}</p>
    </div>


    <div class="card">
      <h2>What Changed Overnight</h2>
      <ul>{"".join(f"<li>{esc(x)}</li>" for x in overnight_changes)}</ul>
    </div>


    <div class="card">
      <h2>Alerts</h2>
      <p class="muted">{len(alert_rows)} alert(s) | {len([a for a in alert_rows if a.get("Tier")=="Critical"])} critical, {len([a for a in alert_rows if a.get("Tier")=="Important"])} important.</p>
      {table_html(
          sorted(alert_rows, key=lambda a: {"Critical":0,"Important":1,"Informational":2}.get(a.get("Tier",""),3)),
          ["Tier","Type","Ticker","Detail"]
      )}
    </div>


    <div class="card">
      <h2>Market Regime</h2>
      {(lambda r: (
        f"<div style='display:flex;align-items:baseline;justify-content:space-between;margin-bottom:10px;'>"
        f"<span style='font-size:18px;font-weight:700;color:#0f172a;'>{esc(r.regime)}</span>"
        f"<span style='font-size:12px;color:#64748b;' title='High = 4+ cross-asset signals aligned. Medium = 2-3 signals. Low = fewer than 2 signals confirming the regime.'>"
        f"Confidence: {esc(r.confidence)}"
        f"{'  |  High = 4+ signals aligned' if r.confidence == 'High' else '  |  Medium = 2-3 signals aligned' if r.confidence == 'Medium' else '  |  Low = fewer than 2 signals aligned'}"
        f"</span>"
        f"</div>"
        f"<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px;'>"
        f"<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:10px 12px;'>"
        f"<div style='font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#64748b;margin-bottom:4px;'>Risk</div>"
        f"<div style='font-size:20px;font-weight:800;color:{'#dc2626' if r.risk_score >= 65 else '#16a34a' if r.risk_score <= 40 else '#d97706'};'>{r.risk_score}/100</div>"
        f"<div style='font-size:10px;color:#94a3b8;margin-top:3px;'>{'Elevated' if r.risk_score >= 65 else 'Low' if r.risk_score <= 40 else 'Moderate'}</div></div>"
        f"<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:10px 12px;'>"
        f"<div style='font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#64748b;margin-bottom:4px;'>Inflation</div>"
        f"<div style='font-size:20px;font-weight:800;color:{'#dc2626' if r.inflation_score >= 65 else '#16a34a' if r.inflation_score <= 40 else '#d97706'};'>{r.inflation_score}/100</div>"
        f"<div style='font-size:10px;color:#94a3b8;margin-top:3px;'>{'Hot — above target' if r.inflation_score >= 65 else 'Contained' if r.inflation_score <= 40 else 'Moderate'}</div></div>"
        f"<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:10px 12px;'>"
        f"<div style='font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#64748b;margin-bottom:4px;'>Growth</div>"
        f"<div style='font-size:20px;font-weight:800;color:{'#16a34a' if r.growth_score >= 55 else '#dc2626' if r.growth_score <= 40 else '#d97706'};'>{r.growth_score}/100</div>"
        f"<div style='font-size:10px;color:#94a3b8;margin-top:3px;'>{'Expanding' if r.growth_score >= 55 else 'Contracting' if r.growth_score <= 40 else 'Mixed signals'}</div></div>"
        f"<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:10px 12px;'>"
        f"<div style='font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#64748b;margin-bottom:4px;'>Liquidity</div>"
        f"<div style='font-size:20px;font-weight:800;color:{'#16a34a' if r.liquidity_score >= 60 else '#dc2626' if r.liquidity_score <= 40 else '#d97706'};'>{r.liquidity_score}/100</div>"
        f"<div style='font-size:10px;color:#94a3b8;margin-top:3px;'>{'Supportive' if r.liquidity_score >= 60 else 'Tightening' if r.liquidity_score <= 40 else 'Neutral'}</div></div>"
        f"</div>"
        f"<table style='width:100%;border-collapse:collapse;font-size:13px;margin-bottom:12px;'>"
        + "".join(
            f"<tr><td style='padding:6px 4px;color:#64748b;border-bottom:1px solid #f1f5f9;width:160px;font-size:12px;'>Drivers</td>"
            f"<td style='padding:6px 4px;border-bottom:1px solid #f1f5f9;font-size:12px;'>{esc(d)}</td></tr>"
            for d in r.drivers
        )
        + "".join(
            f"<tr><td style='padding:6px 4px;color:#64748b;border-bottom:1px solid #f1f5f9;font-size:12px;'>Leadership</td>"
            f"<td style='padding:6px 4px;border-bottom:1px solid #f1f5f9;font-size:12px;'>{esc(l)}</td></tr>"
            for l in r.leadership
        )
        + "".join(
            f"<tr><td style='padding:6px 4px;color:#64748b;border-bottom:1px solid #f1f5f9;font-size:12px;'>Fragility</td>"
            f"<td style='padding:6px 4px;border-bottom:1px solid #f1f5f9;font-size:12px;color:#dc2626;'>{esc(f)}</td></tr>"
            for f in r.fragilities
        )
        + f"</table>"
        + f"<p style='font-size:13px;line-height:1.7;color:#475569;background:#f8fafc;border-left:3px solid #e2e8f0;padding:10px 14px;border-radius:0 8px 8px 0;margin:0;'>{esc(r.narrative)}</p>"
      ))(cross_asset_regime)}
    </div>


    <div class="card">
      <h2>Portfolio Snapshot</h2>
      {table_html(portfolio_snapshot, ["Ticker","Sector","Weight","Market Value","Daily Move"])}
    </div>


    <div class="card">
      <h2>Visual Intelligence</h2>
      <p class="muted">Concentration, movement, and sector exposure at a glance.</p>
      {build_visual_intelligence(portfolio_snapshot, top_movers)}
    </div>


    <div class="card">
      <h2>Portfolio Risk Notes</h2>
      <ul>{"".join(f"<li>{esc(x)}</li>" for x in build_risk_notes(portfolio_snapshot))}</ul>
    </div>


    <div class="card">
      <h2>Top 5 Movers</h2>
      <p class="muted">Largest absolute daily moves across current holdings.</p>
      {table_html(top_movers, ["Ticker","Daily Move","Weekly Move","Volume vs 30D Avg"])}
    </div>


    <div class="card">
      <h2>Portfolio News</h2>
      {table_html(portfolio_news_rows, ["Ticker","Title","Published","Source"])}
    </div>


    <div class="card">
      <h2>Market Themes</h2>
      <ul>{"".join(f"<li>{esc(x)}</li>" for x in build_market_themes(market_news_rows))}</ul>
    </div>


    <div class="card">
      <h2>Macro Snapshot</h2>
      {table_html(macro_rows, list(macro_rows[0].keys()) if macro_rows else ["Indicator","Latest"])}
    </div>


    <div class="card">
      <h2>Economic Calendar</h2>
      <p class="muted">Rows highlighted when the event release date or last update is today.</p>
      {_render_cal(macro_events)}
    </div>


    <div class="card">
      <h2>Catalyst Timeline</h2>
      <p class="muted">Upcoming earnings and macro events combined, next 90 days.</p>
      {table_html(build_catalyst_timeline(earnings_rows, macro_events), ["Date","Days","Type","Event","Note"])}
    </div>


    <div class="card">
      <h2>SEC Monitoring</h2>
      {table_html(sec_rows, ["Ticker","Form","Date","Imp.","Type","Factual Note"])}
    </div>


    <div class="card">
      <h2>Global Developments</h2>
      {table_html(global_development_rows, ["Category","Title","Published","Source"])}
    </div>

    
    <div class="footer">
      This brief is factual monitoring only and does not provide investment recommendations.
    </div>
  </div>
</body>
</html>
"""

    html_body = remove_disabled_sections(html_body, prefs)

    # ── Plain-text fallback ────────────────────────────────────────────────────
    text_lines = [
        "Daily Portfolio Brief",
        f"Generated: {generated_at}",
        "",
        f"Biggest Headline: {biggest_headline}",
        f"Source: {headline_source}",
        "",
        "Top Movers:",
    ]
    for r in top_movers:
        text_lines.append(
            f"  {r['Ticker']}: {r['Daily Move']} today, "
            f"{r['Weekly Move']} weekly, {r['Volume vs 30D Avg']} volume"
        )
    text_body = "\n".join(text_lines)

    return html_body, text_body

def build_and_save_newsletter() -> None:
    """Alias for compatibility with main.py."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html_body, text_body = build_hybrid_newsletter()
    for bad, good in _MOJIBAKE.items():
        html_body = html_body.replace(bad, good)
        text_body = text_body.replace(bad, good)
    (OUTPUT_DIR / "hybrid_newsletter.html").write_text(html_body, encoding="utf-8")
    (OUTPUT_DIR / "hybrid_newsletter.txt").write_text(text_body, encoding="utf-8")
    (OUTPUT_DIR / "latest_newsletter.html").write_text(html_body, encoding="utf-8")
    (OUTPUT_DIR / "latest_newsletter.txt").write_text(text_body, encoding="utf-8")
    print("Newsletter generated.")
    print("  HTML → output/latest_newsletter.html")
    print("  Text → output/latest_newsletter.txt")
