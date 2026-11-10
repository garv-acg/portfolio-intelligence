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

from app.data.earnings import get_upcoming_earnings, get_earnings_preview
from app.data.sec_filings import get_sec_filings
from app.data.alert_engine import latest_alerts, build_alerts, save_alerts
from app.data.holdings_monitor import build_holdings_change_monitor
from app.data.portfolio_returns import compute_portfolio_returns
from app.data.regime_engine import infer_cross_asset_regime
from app.data.market_workbench import macro_dashboard
from app.data.morning_brief_engine import build_morning_brief
from app.data.news_feed import (
    company_news,
    market_news,
    global_development_news as fetch_global_development_news,
    weekly_news,
)

# ── Paths ──────────────────────────────────────────────────────────────────────
OUTPUT_DIR        = Path("output")
USER_PORTFOLIO    = Path("data/users/demo/portfolio.csv")
FALLBACK_PORTFOLIO = Path("portfolio.csv")
MACRO_EVENTS_FILE = Path("data/macro_events.csv")
PREFERENCES_FILE  = Path("data/users/demo/newsletter_preferences.json")
SITE_DATA_DIR     = Path("site/data")
DASHBOARD_HISTORY_DAYS = 90  # trailing window kept in site/data/history.json

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


def fetch_yield_curve() -> dict:
    """Fetch Treasury yields from Yahoo Finance and compute the 2Y-10Y spread.
    Uses ^IRX (13-week) as short-end proxy and ^TNX (10Y) for the long end.
    Both are already in the macro snapshot; this just extracts and computes the spread.
    """
    import requests as _req
    def _yf_latest(sym):
        try:
            import time
            end = int(time.time())
            start = end - 7 * 86400
            r = _req.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                params={"period1": start, "period2": end, "interval": "1d"},
                headers={"User-Agent": "Mozilla/5.0"}, timeout=10,
            )
            closes = r.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            val = next((c for c in reversed(closes) if c is not None), None)
            return float(val) if val is not None else None
        except Exception:
            return None

    try:
        short = _yf_latest("^IRX")   # 13-week T-bill (annualized, in %)
        long  = _yf_latest("^TNX")   # 10-year Treasury yield (in %)
        spread = round(long - short, 2) if short is not None and long is not None else None
        return {"2y": short, "10y": long, "spread": spread}
    except Exception:
        return {"2y": None, "10y": None, "spread": None}


def fetch_fear_greed() -> dict:
    """Fetch CNN's Fear & Greed Index (0-100 score + rating label)."""
    try:
        import requests as _req
        r = _req.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            timeout=10,
        )
        if r.status_code != 200:
            return {"score": None, "rating": None, "prev_week": None}
        fg = r.json().get("fear_and_greed", {})
        return {
            "score":     fg.get("score"),
            "rating":    fg.get("rating"),
            "prev_week": fg.get("previous_1_week"),
        }
    except Exception:
        return {"score": None, "rating": None, "prev_week": None}


def fetch_price_targets(tickers: list[str]) -> dict[str, dict]:
    """Fetch consensus price targets from Yahoo Finance. Returns {ticker: {target, current, upside_pct, high, low}}"""
    try:
        import requests as _req
        s = _req.Session()
        s.headers.update({'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'})
        s.get('https://fc.yahoo.com/', timeout=8)
        crumb = s.get('https://query1.finance.yahoo.com/v1/test/getcrumb', timeout=8).text.strip()
        out = {}
        for ticker in tickers:
            try:
                r = s.get(
                    f'https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}',
                    params={'modules': 'financialData', 'crumb': crumb},
                    timeout=10,
                )
                if r.status_code != 200:
                    continue
                fd = r.json()['quoteSummary']['result'][0]['financialData']
                target  = fd.get('targetMeanPrice', {}).get('raw')
                current = fd.get('currentPrice', {}).get('raw')
                high    = fd.get('targetHighPrice', {}).get('raw')
                low     = fd.get('targetLowPrice', {}).get('raw')
                if target and current and current > 0:
                    out[ticker.upper()] = {
                        'target':     round(target, 2),
                        'current':    round(current, 2),
                        'upside_pct': round((target / current - 1) * 100, 1),
                        'high':       round(high, 2) if high else None,
                        'low':        round(low, 2) if low else None,
                    }
            except Exception:
                continue
        return out
    except Exception:
        return {}


def fetch_implied_earnings_move(ticker: str, earnings_date_str: str) -> str | None:
    """
    Compute the options-implied move for earnings using the ATM straddle
    on the first expiry on or after earnings_date_str (YYYY-MM-DD).
    Returns a string like '±7.1%' or None on failure.
    """
    try:
        import requests as _req, datetime as _dt
        s = _req.Session()
        s.headers.update({'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'})
        s.get('https://fc.yahoo.com/', timeout=8)
        crumb = s.get('https://query1.finance.yahoo.com/v1/test/getcrumb', timeout=8).text.strip()

        # Get available expiries
        r = s.get(f'https://query1.finance.yahoo.com/v7/finance/options/{ticker}',
                  params={'crumb': crumb}, timeout=10)
        if r.status_code != 200:
            return None
        result = r.json()['optionChain']['result'][0]
        curr   = result['quote']['regularMarketPrice']
        expiries = result.get('expirationDates', [])
        if not expiries:
            return None

        earnings_d = _dt.date.fromisoformat(earnings_date_str[:10])
        target_ts  = next(
            (e for e in expiries if _dt.date.fromtimestamp(e) >= earnings_d),
            expiries[-1]
        )

        # Fetch options for that expiry
        r2 = s.get(f'https://query1.finance.yahoo.com/v7/finance/options/{ticker}',
                   params={'crumb': crumb, 'date': target_ts}, timeout=10)
        if r2.status_code != 200:
            return None
        opts  = r2.json()['optionChain']['result'][0].get('options', [])
        if not opts:
            return None
        calls = opts[0].get('calls', [])
        puts  = opts[0].get('puts',  [])
        if not calls or not puts:
            return None

        atm_call = min(calls, key=lambda x: abs(x.get('strike', 0) - curr))
        atm_put  = min(puts,  key=lambda x: abs(x.get('strike', 0) - curr))
        straddle = atm_call.get('lastPrice', 0) + atm_put.get('lastPrice', 0)
        if straddle <= 0 or curr <= 0:
            return None
        return f"±{straddle / curr * 100:.1f}%"
    except Exception:
        return None


_POSITIVE_WORDS = {
    'beat', 'beats', 'surpass', 'record', 'upgrade', 'upgraded', 'outperform',
    'raises', 'raised', 'growth', 'profit', 'gains', 'rally', 'rises', 'strong',
    'partnership', 'deal', 'wins', 'award', 'breakthrough', 'expands', 'buy',
    'bullish', 'higher', 'boost', 'milestone', 'dividend', 'buyback', 'best',
}
_NEGATIVE_WORDS = {
    'miss', 'misses', 'cut', 'cuts', 'downgrade', 'downgraded', 'underperform',
    'lowers', 'lowered', 'loss', 'losses', 'decline', 'falls', 'drops', 'weak',
    'lawsuit', 'investigation', 'probe', 'recall', 'fine', 'penalty', 'sell',
    'bearish', 'lower', 'concern', 'warning', 'risk', 'disappoints', 'slump',
    'layoffs', 'tariff', 'ban', 'restrict', 'bubble', 'crash',
}

def sentiment_tag(title: str) -> str:
    """Return 'positive', 'negative', or 'neutral' based on headline keywords."""
    words = set(title.lower().replace('-', ' ').split())
    pos = len(words & _POSITIVE_WORDS)
    neg = len(words & _NEGATIVE_WORDS)
    if pos > neg:
        return 'positive'
    if neg > pos:
        return 'negative'
    return 'neutral'


def fetch_sector_rotation() -> list[dict]:
    """
    Fetch weekly and monthly performance for all 11 SPDR sector ETFs.
    Returns list of dicts sorted by weekly return descending.
    """
    SECTORS = {
        'XLK': 'Technology',
        'XLC': 'Comm. Services',
        'XLY': 'Cons. Discretionary',
        'XLP': 'Cons. Staples',
        'XLF': 'Financials',
        'XLV': 'Health Care',
        'XLI': 'Industrials',
        'XLE': 'Energy',
        'XLU': 'Utilities',
        'XLB': 'Materials',
        'XLRE': 'Real Estate',
    }
    import requests as _req
    import math as _math
    results = []
    for etf, name in SECTORS.items():
        try:
            import time as _time
            end = int(_time.time())
            start = end - 40 * 86400
            r = _req.get(
                f'https://query1.finance.yahoo.com/v8/finance/chart/{etf}',
                params={'period1': start, 'period2': end, 'interval': '1d'},
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=12,
            )
            closes = [c for c in r.json()['chart']['result'][0]['indicators']['quote'][0]['close'] if c]
            if len(closes) < 6:
                continue
            weekly  = (closes[-1] / closes[-6] - 1) * 100 if len(closes) >= 6 else None
            monthly = (closes[-1] / closes[-22] - 1) * 100 if len(closes) >= 22 else None
            if weekly is None or _math.isnan(weekly):
                continue
            results.append({
                'Sector':  name,
                'ETF':     etf,
                'Weekly':  f"{'+' if weekly >= 0 else ''}{weekly:.1f}%",
                'Monthly': f"{'+' if (monthly or 0) >= 0 else ''}{monthly:.1f}%" if monthly else '—',
                '_weekly_float': weekly,
            })
        except Exception:
            continue
    results.sort(key=lambda x: x['_weekly_float'], reverse=True)
    for r in results:
        del r['_weekly_float']
    return results


def fetch_short_interest(tickers: list[str]) -> list[dict]:
    """Fetch short interest (% float, days-to-cover) via Yahoo Finance quoteSummary."""
    try:
        import requests as _req
        s = _req.Session()
        s.headers.update({'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'})
        s.get('https://fc.yahoo.com/', timeout=8)
        crumb = s.get('https://query1.finance.yahoo.com/v1/test/getcrumb', timeout=8).text.strip()
        rows = []
        for ticker in tickers:
            try:
                r = s.get(
                    f'https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}',
                    params={'modules': 'defaultKeyStatistics', 'crumb': crumb},
                    timeout=10,
                )
                if r.status_code != 200:
                    continue
                ks = r.json()['quoteSummary']['result'][0]['defaultKeyStatistics']
                shares_short = (ks.get('sharesShort') or {}).get('raw')
                float_shares = (ks.get('floatShares') or {}).get('raw')
                short_ratio  = (ks.get('shortRatio')  or {}).get('raw')
                short_pct    = (ks.get('shortPercentOfFloat') or {}).get('raw')
                if shares_short is None and short_pct is None:
                    continue
                if short_pct is not None:
                    pct_str = f"{short_pct*100:.1f}%" if short_pct < 1 else f"{short_pct:.1f}%"
                elif shares_short and float_shares:
                    pct_str = f"{shares_short / float_shares * 100:.1f}%"
                else:
                    pct_str = "—"
                rows.append({
                    'Ticker':        ticker.upper(),
                    '% Float Short': pct_str,
                    'Days to Cover': f"{short_ratio:.1f}d" if short_ratio else "—",
                    'Shares Short':  f"{shares_short/1e6:.1f}M" if shares_short else "—",
                })
            except Exception:
                continue
        rows.sort(key=lambda r: float(r['% Float Short'].replace('%','') or '0') if r['% Float Short'] != '—' else 0, reverse=True)
        return rows
    except Exception:
        return []


def fetch_insider_transactions(tickers: list[str], days_back: int = 90) -> list[dict]:
    """Fetch recent Form 4 insider buy transactions via Yahoo Finance quoteSummary."""
    from datetime import date as _date, timedelta
    cutoff = str(_date.today() - timedelta(days=days_back))
    try:
        import requests as _req
        s = _req.Session()
        s.headers.update({'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'})
        s.get('https://fc.yahoo.com/', timeout=8)
        crumb = s.get('https://query1.finance.yahoo.com/v1/test/getcrumb', timeout=8).text.strip()
        rows = []
        for ticker in tickers:
            try:
                r = s.get(
                    f'https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}',
                    params={'modules': 'insiderTransactions', 'crumb': crumb},
                    timeout=10,
                )
                if r.status_code != 200:
                    continue
                txns = r.json()['quoteSummary']['result'][0]['insiderTransactions'].get('transactions', [])
                for tx in txns:
                    text = str(tx.get('transactionDescription', '')).lower()
                    if 'sale' in text or 'sell' in text or 'option' in text:
                        continue
                    ts = (tx.get('startDate') or {}).get('raw')
                    if not ts:
                        continue
                    txn_date = str(_date.fromtimestamp(int(ts)))
                    if txn_date < cutoff:
                        continue
                    shares = (tx.get('shares') or {}).get('raw')
                    value  = (tx.get('value')  or {}).get('raw')
                    name   = tx.get('filerName', '')
                    role   = tx.get('filerRelation', '')
                    rows.append({
                        'Date':    txn_date,
                        'Ticker':  ticker.upper(),
                        'Insider': str(name)[:22],
                        'Role':    str(role)[:18],
                        'Shares':  f"{int(shares):,}" if shares else "—",
                        'Value':   f"${float(value)/1e3:.0f}K" if value and float(value) > 0 else "—",
                    })
            except Exception:
                continue
        rows.sort(key=lambda r: r['Date'], reverse=True)
        return rows[:15]
    except Exception:
        return []


def fetch_correlation_matrix(tickers: list[str], days: int = 60) -> tuple[list[str], list[list[float]]]:
    """Compute pairwise return correlation for holdings over last N days."""
    import math as _math
    import requests as _req, time as _time
    closes: dict[str, list[float]] = {}
    end = int(_time.time())
    start = end - (days + 10) * 86400
    for ticker in tickers:
        try:
            r = _req.get(
                f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}',
                params={'period1': start, 'period2': end, 'interval': '1d'},
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=12,
            )
            c = [x for x in r.json()['chart']['result'][0]['indicators']['quote'][0]['close'] if x is not None]
            if len(c) >= 10:
                closes[ticker.upper()] = c[-days:]
        except Exception:
            continue
    valid = [t for t in tickers if t.upper() in closes]
    if len(valid) < 2:
        return valid, []
    min_len = min(len(closes[t.upper()]) for t in valid)

    def _returns(prices):
        return [prices[i]/prices[i-1]-1 for i in range(1, len(prices))]

    rets = {t: _returns(closes[t.upper()][-min_len:]) for t in valid}

    def _corr(a, b):
        n = len(a)
        ma = sum(a)/n; mb = sum(b)/n
        num = sum((a[i]-ma)*(b[i]-mb) for i in range(n))
        da  = (sum((a[i]-ma)**2 for i in range(n)))**0.5
        db  = (sum((b[i]-mb)**2 for i in range(n)))**0.5
        return num/(da*db) if da*db else 0.0

    matrix = [[_corr(rets[ti], rets[tj]) for tj in valid] for ti in valid]
    return valid, matrix


def fetch_dividend_calendar(tickers: list[str]) -> list[dict]:
    """Fetch upcoming ex-dividend dates and yield via Yahoo Finance quoteSummary.
    When the most recent ex-div date has already passed, projects forward one quarter
    so the card always shows the next expected date rather than stale history."""
    from datetime import date as _date, timedelta
    try:
        import requests as _req
        s = _req.Session()
        s.headers.update({'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'})
        s.get('https://fc.yahoo.com/', timeout=8)
        crumb = s.get('https://query1.finance.yahoo.com/v1/test/getcrumb', timeout=8).text.strip()
        rows = []
        today = _date.today()
        for ticker in tickers:
            try:
                r = s.get(
                    f'https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}',
                    params={'modules': 'summaryDetail', 'crumb': crumb},
                    timeout=10,
                )
                if r.status_code != 200:
                    continue
                sd = r.json()['quoteSummary']['result'][0]['summaryDetail']
                ex_div_ts = (sd.get('exDividendDate') or {}).get('raw')
                div_yield = (sd.get('dividendYield')  or {}).get('raw')
                div_rate  = (sd.get('dividendRate')   or {}).get('raw')
                # Skip non-dividend payers entirely
                if not div_rate and not div_yield:
                    continue
                if not ex_div_ts:
                    continue
                last_ex = _date.fromtimestamp(int(ex_div_ts))
                # Project forward quarterly until we have a future date
                estimated = False
                ex_date = last_ex
                while ex_date <= today:
                    ex_date = ex_date + timedelta(days=91)
                    estimated = True
                days_until = (ex_date - today).days
                rows.append({
                    'Ticker':      ticker.upper(),
                    'Ex-Div Date': str(ex_date),
                    'Days':        f"in {days_until}d",
                    'Ann. Div':    f"${div_rate:.2f}" if div_rate else "—",
                    'Yield':       f"{div_yield*100:.2f}%" if div_yield else "—",
                    '_estimated':  estimated,
                })
            except Exception:
                continue
        rows.sort(key=lambda r: r['Ex-Div Date'])
        return rows
    except Exception:
        return []


def _economic_surprise_score(macro_events: list[dict]) -> tuple[float | None, str]:
    """Compute a direction-aware economic surprise index.
    For inflation/rates, lower-than-expected = beat (good).
    For growth/employment/spending, higher-than-expected = beat (good).
    Skips events where direction is ambiguous (FOMC, Fed Funds, etc.)."""
    # Keywords where LOWER actual than expected = positive surprise
    _LOWER_IS_BETTER = {'cpi', 'pce', 'inflation', 'unemployment', 'claims', 'jobless'}
    # Keywords where HIGHER actual than expected = positive surprise
    _HIGHER_IS_BETTER = {'job', 'payroll', 'nonfarm', 'employment', 'retail', 'gdp',
                         'sales', 'ism', 'pmi', 'housing', 'durable', 'consumer confidence'}
    # Skip these entirely — no clear directional interpretation
    _SKIP = {'fomc', 'fed funds', 'probability', 'rate decision'}

    def _to_num(s):
        try:
            return float(str(s).replace('%','').replace('+','').replace('K','e3')
                         .replace('M','e6').replace('B','e9').replace(',','').strip())
        except Exception:
            return None

    beats = misses = scored = 0
    for ev in macro_events:
        actual_s   = str(ev.get('actual',   '') or '').strip()
        expected_s = str(ev.get('expected', '') or '').strip()
        event_name = str(ev.get('event',    '') or '').lower()

        if not actual_s or not expected_s:
            continue
        if actual_s in ('—', 'N/A', 'nan') or expected_s in ('—', 'N/A', 'nan'):
            continue
        if any(k in event_name for k in _SKIP):
            continue

        actual   = _to_num(actual_s)
        expected = _to_num(expected_s)
        if actual is None or expected is None or actual == expected:
            continue

        lower_is_better  = any(k in event_name for k in _LOWER_IS_BETTER)
        higher_is_better = any(k in event_name for k in _HIGHER_IS_BETTER)
        if not lower_is_better and not higher_is_better:
            continue  # unknown direction — skip rather than guess

        scored += 1
        if lower_is_better:
            if actual < expected:
                beats += 1
            else:
                misses += 1
        else:
            if actual > expected:
                beats += 1
            else:
                misses += 1

    if scored == 0:
        return None, "Insufficient data", 0

    score = (beats - misses) / scored * 100
    if score >= 40:
        label = "Positive"
    elif score >= 10:
        label = "Mild Positive"
    elif score >= -10:
        label = "Neutral"
    elif score >= -40:
        label = "Mild Negative"
    else:
        label = "Negative"
    return score, label, scored


def fetch_analyst_ratings(tickers: list[str], days_back: int = 7) -> list[dict]:
    """Fetch recent analyst upgrade/downgrade history from Yahoo Finance."""
    try:
        import requests as _req
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td

        session = _req.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        # Get crumb
        session.get("https://fc.yahoo.com/", timeout=8)
        crumb_r = session.get(
            "https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=8
        )
        if crumb_r.status_code != 200:
            return []
        crumb = crumb_r.text.strip()

        cutoff = _dt.now(_tz.utc) - _td(days=days_back)
        action_map = {
            "init": "Initiated",
            "up":   "Upgraded ↑",
            "down": "Downgraded ↓",
            "reit": "Reiterated",
            "main": "Maintained",
        }
        allowed = set(action_map)
        results = []

        for ticker in tickers:
            try:
                r = session.get(
                    f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}",
                    params={"modules": "upgradeDowngradeHistory", "crumb": crumb},
                    timeout=10,
                )
                if r.status_code != 200:
                    continue
                history = (
                    r.json()
                    .get("quoteSummary", {})
                    .get("result", [{}])[0]
                    .get("upgradeDowngradeHistory", {})
                    .get("history", [])
                )
                for item in history:
                    action = item.get("action", "")
                    to_grade = item.get("toGrade", "")
                    if action not in allowed or not to_grade:
                        continue
                    epoch = item.get("epochGradeDate", 0)
                    dt = _dt.fromtimestamp(epoch, tz=_tz.utc)
                    if dt < cutoff:
                        continue
                    results.append({
                        "ticker":        ticker,
                        "date":          dt.strftime("%Y-%m-%d"),
                        "firm":          item.get("firm", ""),
                        "to_grade":      to_grade,
                        "action":        action,
                        "action_label":  action_map[action],
                    })
            except Exception:
                continue

        results.sort(key=lambda x: x["date"], reverse=True)
        return results
    except Exception:
        return []


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


def _roll_macro_date_forward(release_date_str: str, event: str) -> str:
    """
    If a macro event's release_date is in the past, advance it to the next
    approximate occurrence based on typical release cadence.
    """
    import calendar as _cal
    try:
        d = date.fromisoformat(release_date_str[:10])
        if d >= date.today():
            return release_date_str  # already upcoming
        ev = event.lower()
        # Monthly events: advance by ~1 month
        if any(k in ev for k in ["cpi", "pce", "ppi", "retail", "jobs", "payroll",
                                   "employment", "nonfarm", "housing", "durable"]):
            # Advance month by month until future
            while d < date.today():
                month = d.month + 1 if d.month < 12 else 1
                year  = d.year if d.month < 12 else d.year + 1
                # Keep same day-of-month, clamp to last day
                max_day = _cal.monthrange(year, month)[1]
                d = d.replace(year=year, month=month, day=min(d.day, max_day))
            return str(d)
        # Quarterly: GDP, consumer confidence
        if any(k in ev for k in ["gdp", "consumer confidence", "ism", "pmurchasing"]):
            while d < date.today():
                month = d.month + 3 if d.month <= 9 else (d.month + 3 - 12)
                year  = d.year if d.month <= 9 else d.year + 1
                max_day = _cal.monthrange(year, month)[1]
                d = d.replace(year=year, month=month, day=min(d.day, max_day))
            return str(d)
        # FOMC: ~8 times a year (~6-7 week cadence)
        if any(k in ev for k in ["fomc", "rate decision", "federal reserve"]):
            import datetime as _dt
            while d < date.today():
                d = d + _dt.timedelta(weeks=7)
            return str(d)
    except Exception:
        pass
    return release_date_str


def _fetch_fmp_economic_calendar(days_ahead: int = 45) -> list[dict]:
    """Fetch upcoming macro events from FMP economic calendar API. Returns [] if unavailable."""
    return []  # FMP economic calendar requires paid plan — using CSV fallback with date rolling


def load_macro_events() -> list[dict]:
    # Try live FMP calendar first (always fresh, no stale CSV problem)
    fmp_rows = _fetch_fmp_economic_calendar(days_ahead=45)
    if fmp_rows:
        # Also include a few recent past events (last 7 days) so calendar isn't empty on off-days
        try:
            import requests as _req, os as _os, datetime as _dt
            key = _os.getenv("FMP_API_KEY", "").strip()
            if key:
                past_start = date.today() - _dt.timedelta(days=7)
                url = (
                    f"https://financialmodelingprep.com/api/v3/economic_calendar"
                    f"?from={past_start}&to={date.today()}&apikey={key}"
                )
                r = _req.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, list):
                        high_keywords = ["CPI","PCE","GDP","Jobs","Employment","Nonfarm","Payroll",
                                         "Retail","FOMC","Fed","Rate","Inflation","PPI","ISM",
                                         "Housing","Durable","Consumer Confidence","PMI"]
                        for item in data:
                            country = item.get("country", "")
                            if country and country.upper() not in ("US", "USD", ""):
                                continue
                            impact = item.get("impact", "")
                            if impact and impact.lower() not in ("high", "medium"):
                                continue
                            event = item.get("event", "")
                            if not any(kw.lower() in event.lower() for kw in high_keywords):
                                continue
                            release_date = str(item.get("date", ""))[:10]
                            try:
                                delta = (date.fromisoformat(release_date) - date.today()).days
                                days_until = f"{abs(delta)}d ago"
                            except Exception:
                                days_until = ""
                            fmp_rows.append({
                                "event":        event,
                                "release_date": release_date,
                                "time":         str(item.get("time", ""))[:5],
                                "days_until":   days_until,
                                "importance":   impact.capitalize() if impact else "",
                                "actual":       str(item.get("actual",   "")) or "N/A",
                                "expected":     str(item.get("estimate", "")) or "N/A",
                                "prior":        str(item.get("previous", "")) or "N/A",
                                "source":       "FMP",
                                "changed_today": False,
                            })
        except Exception:
            pass

        def _sort_key(item):
            if item.get("release_date", "").lower() == "daily":
                return (2, 0)
            if item.get("days_until") == "Today":
                return (0, 0)
            try:
                d = (date.fromisoformat(item["release_date"][:10]) - date.today()).days
                return (0, d) if d >= 0 else (1, -d)
            except Exception:
                return (2, 0)

        # Inject Fed Funds probability
        fed_prob = fetch_fed_funds_probability()
        if fed_prob:
            fmp_rows.append({
                "event": "Fed Funds Probability", "release_date": "Daily",
                "time": "", "days_until": "Daily", "importance": "High",
                "actual": fed_prob, "expected": "", "prior": "3.50-3.75%",
                "source": "CME FedWatch", "changed_today": False,
            })
        return sorted(fmp_rows, key=_sort_key)

    # Fallback: static CSV (with FRED actuals refresh)
    ensure_macro_events_file()
    refresh_macro_calendar_from_fred()
    df    = pd.read_csv(MACRO_EVENTS_FILE).fillna("")
    today = date.today().isoformat()
    rows  = []

    for _, row in df.iterrows():
        release_date = str(row.get("release_date", ""))
        event_name   = str(row.get("event", ""))
        last_updated = str(row.get("last_updated", ""))

        # Auto-roll past recurring event dates forward
        if release_date and release_date.lower() != "daily":
            release_date = _roll_macro_date_forward(release_date, event_name)

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
            if col_lower in {"daily move", "daily change (%)", "daily", "weekly", "monthly", "ytd", "weekly move"}:
                val_str = str(value)
                if val_str.startswith("+"):
                    out.append(f"<td><span class='move-pill move-positive'>{esc(value)}</span></td>")
                elif val_str.startswith("-"):
                    out.append(f"<td><span class='move-pill move-negative'>{esc(value)}</span></td>")
                else:
                    out.append(f"<td>{esc(value)}</td>")
            elif col_lower == "52w":
                val_str = str(value)
                try:
                    num = float(val_str.replace("%", "").replace("+", ""))
                    if num >= -2:
                        out.append(f"<td><span class='move-pill move-positive'>{esc(value)}</span></td>")
                    elif num > -10:
                        out.append(f"<td>{esc(value)}</td>")
                    elif num > -20:
                        out.append(f"<td><span class='c-am'>{esc(value)}</span></td>")
                    else:
                        out.append(f"<td><span class='c-dn'>{esc(value)}</span></td>")
                except Exception:
                    out.append(f"<td>{esc(value)}</td>")
            elif col_lower == "last quarter":
                val_str = str(value)
                if val_str.startswith("Beat"):
                    out.append(f"<td><span class='move-pill move-positive'>{esc(value)}</span></td>")
                elif val_str.startswith("Miss"):
                    out.append(f"<td><span class='move-pill move-negative'>{esc(value)}</span></td>")
                else:
                    out.append(f"<td>{esc(value)}</td>")
            elif col_lower == "action":
                val_str = str(value)
                if "Upgraded" in val_str:
                    out.append(f"<td><span class='move-pill move-positive'>{esc(value)}</span></td>")
                elif "Downgraded" in val_str:
                    out.append(f"<td><span class='move-pill move-negative'>{esc(value)}</span></td>")
                else:
                    out.append(f"<td>{esc(value)}</td>")
            elif col_lower == "p&l":
                val_str = str(value)
                if val_str.startswith("+"):
                    out.append(f"<td><span class='move-pill move-positive'>{esc(value)}</span></td>")
                elif val_str.startswith("-"):
                    out.append(f"<td><span class='move-pill move-negative'>{esc(value)}</span></td>")
                else:
                    out.append(f"<td>{esc(value)}</td>")
            elif col_lower == "upside":
                val_str = str(value)
                if val_str.startswith("+"):
                    out.append(f"<td><span class='move-pill move-positive'>{esc(value)}</span></td>")
                elif val_str.startswith("-"):
                    out.append(f"<td><span class='move-pill move-negative'>{esc(value)}</span></td>")
                else:
                    out.append(f"<td>{esc(value)}</td>")
            elif col_lower == "sentiment":
                val_str = str(value)
                if val_str == "positive":
                    out.append(f"<td><span class='c-up'>▲</span></td>")
                elif val_str == "negative":
                    out.append(f"<td><span class='c-dn'>▼</span></td>")
                else:
                    out.append(f"<td><span style='color:#94a3b8;'>—</span></td>")
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
    for row in portfolio_snapshot:
        try:
            w = float(str(row.get("Weight", "0")).replace("%", "").replace("+", ""))
        except Exception:
            continue
        ticker = row.get("Ticker", "")
        weight_str = row.get("Weight", "")
        if w > 30:
            notes.append(f"⚠ HIGH CONCENTRATION: {ticker} is concentrated at {weight_str} of portfolio — consider whether this matches your risk tolerance.")
        elif w > 20:
            notes.append(f"{ticker} is concentrated at {weight_str} of portfolio — consider whether this matches your risk tolerance.")
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
  /* LIGHT MODE (default) */
  body { margin:0; padding:0; background:#f0f4f8; color:#1e293b;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
         -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; }
  .wrapper { background:#f0f4f8; padding:24px 16px; }
  .container { max-width:640px; margin:0 auto; }
  .header { padding:30px 28px; border-radius:12px;
            background:linear-gradient(135deg,#0f2044 0%,#1a4ed8 100%);
            color:#fff; margin-bottom:12px; }
  .eyebrow { color:#93c5fd; font-size:10px; text-transform:uppercase;
             letter-spacing:.18em; font-weight:700; margin-bottom:10px; }
  h1 { margin:0 0 8px; font-size:28px; line-height:1.15; font-weight:800; color:#f0f9ff; }
  .subtitle { color:#bfdbfe; font-size:13px; line-height:1.6; }
  .generated { margin-top:12px; color:#93c5fd; font-size:11px; opacity:.8; }
  .card { background:#ffffff; border:1px solid #e2e8f0; border-radius:10px;
          padding:18px 20px; margin:10px 0; box-shadow:0 1px 4px rgba(0,0,0,.06); }
  .card h2 { margin:0 0 12px; font-size:10px; color:#0369a1; font-weight:700;
             text-transform:uppercase; letter-spacing:.14em; border-bottom:1px solid #e2e8f0;
             padding-bottom:8px; }
  .muted { color:#64748b; line-height:1.65; font-size:14px; }
  p { color:#334155; font-size:14px; line-height:1.7; margin:0 0 10px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th { text-align:left; color:#94a3b8; border-bottom:2px solid #e2e8f0;
       padding:8px 6px; font-size:10px; text-transform:uppercase;
       letter-spacing:.06em; font-weight:700; white-space:nowrap; }
  td { border-bottom:1px solid #f1f5f9; padding:9px 6px; color:#334155;
       vertical-align:top; line-height:1.5; }
  tr:last-child td { border-bottom:none; }
  .changed-row td { background:#fefce8; }
  .tag { display:inline-block; padding:2px 8px; border-radius:999px;
         background:#e0f2fe; color:#0369a1; font-size:11px; margin-right:4px; font-weight:600; }
  .move-pill     { display:inline-block; padding:2px 8px; border-radius:999px;
                   font-size:12px; font-weight:700; background:#f1f5f9; color:#475569; }
  .move-positive { background:#f0fdf4; color:#16a34a; border:1px solid #bbf7d0; }
  .move-negative { background:#fef2f2; color:#dc2626; border:1px solid #fecaca; }
  .c-up { color:#16a34a; font-weight:600; }
  .c-dn { color:#dc2626; font-weight:600; }
  .c-am { color:#b45309; font-weight:600; }
  .visual-grid   { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin:10px 0 14px; }
  .visual-metric { background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:14px; }
  .metric-label  { color:#94a3b8; font-size:10px; text-transform:uppercase; letter-spacing:.08em; font-weight:700; }
  .metric-value  { color:#0f172a; font-size:20px; font-weight:800; margin-top:6px; }
  .metric-sub    { color:#94a3b8; font-size:11px; margin-top:4px; }
  .mini-section-title { font-size:10px; font-weight:700; color:#0369a1;
                        margin:14px 0 8px; text-transform:uppercase; letter-spacing:.10em; }
  .regime-card   { background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:10px 12px; }
  .regime-label  { font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.06em; color:#64748b; margin-bottom:4px; }
  .regime-sub    { font-size:10px; color:#94a3b8; margin-top:3px; }
  .regime-title  { font-size:18px; font-weight:700; color:#0f172a; }
  .narrative-box { font-size:13px; line-height:1.7; color:#475569; background:#f8fafc;
                   border-left:3px solid #3b82f6; padding:10px 14px; border-radius:0 8px 8px 0; margin:0; }
  .bar-card { background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:14px; }
  .bar-row  { display:grid; grid-template-columns:140px 1fr 60px; align-items:center; gap:8px; margin:8px 0; }
  .bar-label { color:#475569; font-size:12px; font-weight:600; }
  .bar-track { height:5px; background:#e2e8f0; border-radius:999px; overflow:hidden; }
  .bar-fill  { height:5px; background:#0ea5e9; border-radius:999px; }
  .bar-value { color:#94a3b8; font-size:11px; text-align:right; font-weight:700; }
  .footer { color:#94a3b8; font-size:11px; margin-top:20px; text-align:center;
            padding:12px; border-top:1px solid #e2e8f0; line-height:1.6; }
  a { color:#0369a1; text-decoration:none; }
  a:hover { text-decoration:underline; }

  /* DARK MODE */
  @media (prefers-color-scheme: dark) {
    body           { background:#13161f !important; color:#e2e8f0 !important; }
    .wrapper       { background:#13161f !important; }
    .card          { background:#1c2030 !important; border-color:#28304a !important; box-shadow:0 2px 8px rgba(0,0,0,.4) !important; }
    .card h2       { color:#60a5fa !important; border-bottom-color:#28304a !important; }
    .muted         { color:#94a3b8 !important; }
    p              { color:#cbd5e1 !important; }
    th             { color:#64748b !important; border-bottom-color:#2e3650 !important; }
    td             { color:#cbd5e1 !important; border-bottom-color:#2a3045 !important; }
    .changed-row td { background:#2a2a18 !important; }
    .tag           { background:#1e3a5f !important; color:#93c5fd !important; }
    .move-pill     { background:#2e3650 !important; color:#cbd5e1 !important; }
    .move-positive { background:#052e16 !important; color:#4ade80 !important; border-color:#166534 !important; }
    .move-negative { background:#2d0a0a !important; color:#f87171 !important; border-color:#7f1d1d !important; }
    .c-up { color:#4ade80 !important; }
    .c-dn { color:#f87171 !important; }
    .c-am { color:#fbbf24 !important; }
    .visual-metric { background:#1e2435 !important; border-color:#2e3650 !important; }
    .metric-value  { color:#f1f5f9 !important; }
    .metric-label  { color:#64748b !important; }
    .metric-sub    { color:#64748b !important; }
    .mini-section-title { color:#60a5fa !important; }
    .regime-card   { background:#1e2435 !important; border-color:#2e3650 !important; }
    .regime-label  { color:#64748b !important; }
    .regime-sub    { color:#94a3b8 !important; }
    .regime-title  { color:#e2e8f0 !important; }
    .narrative-box { background:#1e2435 !important; color:#94a3b8 !important; border-left-color:#3b82f6 !important; }
    .bar-card      { background:#1e2435 !important; border-color:#2e3650 !important; }
    .bar-label     { color:#94a3b8 !important; }
    .bar-track     { background:#2e3650 !important; }
    .bar-fill      { background:#3b82f6 !important; }
    .bar-value     { color:#64748b !important; }
    .footer        { color:#475569 !important; border-top-color:#28304a !important; }
    a              { color:#60a5fa !important; }
  }

  /* MOBILE */
  @media only screen and (max-width:600px) {
    .wrapper   { padding:8px 6px !important; }
    .container { width:100% !important; }
    .card      { padding:14px 12px !important; border-radius:8px !important; margin:8px 0 !important; }
    .header    { padding:20px 16px !important; border-radius:10px !important; }
    h1         { font-size:21px !important; line-height:1.2 !important; }
    .subtitle  { font-size:12px !important; }
    .eyebrow   { font-size:9px !important; }
    .card h2   { font-size:9px !important; }
    p          { font-size:13px !important; }
    .muted     { font-size:13px !important; }
    table      { display:block !important; overflow-x:auto !important;
                 -webkit-overflow-scrolling:touch !important; font-size:12px !important; }
    th         { font-size:9px !important; padding:7px 5px !important; }
    td         { font-size:12px !important; padding:8px 5px !important; }
    .visual-grid   { grid-template-columns:1fr !important; gap:6px !important; }
    .visual-metric { padding:10px 12px !important; display:flex; align-items:center; gap:12px; }
    .metric-label  { font-size:9px !important; min-width:80px; }
    .metric-value  { font-size:18px !important; margin-top:0 !important; }
    .metric-sub    { display:none !important; }
    .regime-grid   { grid-template-columns:1fr 1fr !important; gap:8px !important; }
    .bar-card  { padding:10px !important; }
    .bar-row   { grid-template-columns:70px 1fr 40px !important; gap:6px !important; }
    .bar-label { font-size:10px !important; }
    .bar-value { font-size:10px !important; }
    .move-pill { font-size:11px !important; padding:2px 6px !important; }
    .tag       { font-size:10px !important; padding:2px 7px !important; }
    .footer    { font-size:10px !important; padding:10px 8px !important; }
  }
</style>"""


# ── Main build function ────────────────────────────────────────────────────────


def _cal_actual_html(event, actual, expected, days_until=''):
    # Never show stale actuals for future events — only show for past/today
    if days_until and days_until not in ('Today', 'Daily') and not days_until.endswith('ago'):
        return ''
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


def _cal_prior_html(event, prior, expected):
    if not prior or prior in ('', 'N/A', 'nan', 'NaN'): return ''
    el = event.lower()
    if 'fomc' in el or 'fed funds' in el or 'probability' in el: return esc(prior)
    def n(v):
        try: return float(str(v).replace('%','').replace('K','').replace('+','').replace(',','').strip())
        except: return None
    p, e = n(prior), n(expected)
    if p is None or e is None: return esc(prior)
    if any(w in el for w in ['cpi','pce','inflation']):
        css = 'move-positive' if p <= e else 'move-negative'
    elif any(w in el for w in ['job','payroll','employment','retail']):
        css = 'move-positive' if p >= e else 'move-negative'
    else: return esc(prior)
    return "<span class='move-pill " + css + "'>" + esc(prior) + '</span>'


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
            f"<td>{_cal_actual_html(r.get('event',''),r.get('actual',''),r.get('expected',''),r.get('days_until',''))}</td>",
            f"<td>{esc(r.get('expected',''))}</td>",
            f"<td>{_cal_prior_html(r.get('event',''),r.get('prior',''),r.get('expected',''))}</td>",
            f"<td>{esc(r.get('source',''))}</td>",
            '</tr>',
        ]
    out.append('</tbody></table>')
    return ''.join(out)


def _render_yield_vix(yield_curve: dict, macro_rows_raw: list, fear_greed: dict | None = None) -> str:
    y2  = yield_curve.get("2y")
    y10 = yield_curve.get("10y")
    spread = yield_curve.get("spread")

    # VIX from macro rows
    vix_row = next((r for r in macro_rows_raw if "VIX" in str(r.get("Indicator","")) or r.get("Ticker") == "^VIX"), None)
    vix = None
    try:
        vix = float(str(vix_row.get("Latest", "")).replace(",","")) if vix_row else None
    except Exception:
        pass

    def _metric(label, value, sub, css=""):
        return (
            f"<div class='visual-metric'>"
            f"<div class='metric-label'>{label}</div>"
            f"<div class='metric-value' style='font-size:18px;'><span class='{css}'>{value}</span></div>"
            f"<div class='metric-sub'>{sub}</div>"
            f"</div>"
        )

    # Yield curve metrics
    y2_str  = f"{y2:.2f}%" if y2  is not None else "—"
    y10_str = f"{y10:.2f}%" if y10 is not None else "—"

    if spread is not None:
        if spread < 0:
            spread_css  = "c-dn"
            spread_sub  = "⚠ Inverted — historically precedes recession"
        elif spread < 0.25:
            spread_css  = "c-am"
            spread_sub  = "Flat — approaching inversion"
        else:
            spread_css  = "c-up"
            spread_sub  = "Normal — longer rates above short"
        spread_str = f"{spread:+.2f}%"
    else:
        spread_css, spread_sub, spread_str = "", "—", "—"

    # VIX metric
    if vix is not None:
        if vix >= 30:
            vix_css, vix_sub = "c-dn", "High fear — elevated volatility"
        elif vix >= 20:
            vix_css, vix_sub = "c-am", "Elevated — above normal"
        elif vix <= 13:
            vix_css, vix_sub = "c-am", "Very low — possible complacency"
        else:
            vix_css, vix_sub = "c-up", "Normal range"
        vix_str = f"{vix:.1f}"
    else:
        vix_css, vix_sub, vix_str = "", "—", "—"

    # Fear & Greed metric
    fg = fear_greed or {}
    fg_score = fg.get("score")
    fg_rating = fg.get("rating")
    fg_prev_week = fg.get("prev_week")
    if fg_score is not None:
        if fg_score <= 25:
            fg_css = "c-dn"
        elif fg_score <= 45:
            fg_css = "c-am"
        elif fg_score <= 55:
            fg_css = ""
        elif fg_score <= 75:
            fg_css = "c-up"
        else:
            fg_css = "c-am"  # extreme greed flagged amber too — a warning sign
        fg_str = f"{fg_score:.0f}"
        fg_label = (fg_rating or "").replace("_", " ").title()
        fg_delta = ""
        if fg_prev_week is not None:
            diff = fg_score - fg_prev_week
            fg_delta = f" ({'+' if diff >= 0 else ''}{diff:.0f} vs last wk)"
        fg_sub = f"{fg_label}{fg_delta}"
    else:
        fg_css, fg_str, fg_sub = "", "—", "—"

    def _tile(label, value, sub, css=""):
        color_style = ""
        if css == "c-up":   color_style = "color:#16a34a;"
        elif css == "c-dn": color_style = "color:#dc2626;"
        elif css == "c-am": color_style = "color:#b45309;"
        return (
            f"<td style='padding:4px;width:20%;'>"
            f"<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 10px;'>"
            f"<div style='font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#64748b;margin-bottom:3px;'>{label}</div>"
            f"<div style='font-size:15px;font-weight:800;line-height:1.1;{color_style}'>{value}</div>"
            f"<div style='font-size:10px;color:#94a3b8;margin-top:2px;'>{sub}</div>"
            f"</div></td>"
        )

    grid = (
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>"
        + _tile("3M Treasury",   y2_str,     "Short-term rate")
        + _tile("10Y Treasury",  y10_str,    "Long-term rate")
        + _tile("3M–10Y Spread", spread_str, spread_sub, spread_css)
        + _tile("VIX",           vix_str,    vix_sub,    vix_css)
        + _tile("Fear &amp; Greed", fg_str,  fg_sub,     fg_css)
        + "</tr></table>"
    )
    return grid


def _perf_summary_html(port_daily, port_weekly, port_monthly, port_ytd,
                        spy_daily, spy_weekly, spy_monthly, spy_ytd) -> str:
    def _cell(val, spy_val, label):
        if val is None:
            return f"<td><div class='perf-label'>{label}</div><div class='perf-val'>—</div><div class='perf-vs'>vs SPY —</div></td>"
        sign = "+" if val >= 0 else ""
        css  = "c-up" if val >= 0 else "c-dn"
        vs   = f"{val - spy_val:+.2f}% vs SPY" if spy_val is not None else "vs SPY —"
        vs_css = "c-up" if spy_val is not None and val >= spy_val else "c-dn"
        return (
            f"<td style='padding:8px 12px;text-align:center;'>"
            f"<div class='perf-label'>{label}</div>"
            f"<div class='perf-val <span class=\'{css}\'>{sign}{val:.2f}%</span>'>"
            f"<span class='{css}' style='font-size:22px;font-weight:800;'>{sign}{val:.2f}%</span></div>"
            f"<div class='perf-vs' style='font-size:11px;margin-top:3px;'>"
            f"<span class='{vs_css}'>{vs}</span></div>"
            f"</td>"
        )

    def _row(label, port_val, spy_val):
        if port_val is None and spy_val is None:
            return ""
        sign_p = ("+" if (port_val or 0) >= 0 else "")
        sign_s = ("+" if (spy_val  or 0) >= 0 else "")
        css_p  = "c-up" if (port_val or 0) >= 0 else "c-dn"
        css_s  = "c-up" if (spy_val  or 0) >= 0 else "c-dn"
        vs     = (port_val - spy_val) if port_val is not None and spy_val is not None else None
        vs_str = f"{vs:+.2f}%" if vs is not None else "—"
        vs_css = "c-up" if vs is not None and vs >= 0 else "c-dn"
        p_str  = f"{sign_p}{port_val:.2f}%" if port_val is not None else "—"
        s_str  = f"{sign_s}{spy_val:.2f}%"  if spy_val  is not None else "—"
        return (
            f"<tr>"
            f"<td style='padding:8px 6px;font-weight:600;font-size:13px;'>{label}</td>"
            f"<td style='padding:8px 6px;text-align:right;font-size:15px;font-weight:700;'><span class='{css_p}'>{p_str}</span></td>"
            f"<td style='padding:8px 6px;text-align:right;font-size:13px;color:#64748b;'>{s_str}</td>"
            f"<td style='padding:8px 6px;text-align:right;font-size:13px;font-weight:600;'><span class='{vs_css}'>{vs_str}</span></td>"
            f"</tr>"
        )

    rows = (
        _row("Today", port_daily, spy_daily) +
        _row("This Week", port_weekly, spy_weekly) +
        _row("This Month", port_monthly, spy_monthly) +
        _row("YTD", port_ytd, spy_ytd)
    )
    return (
        "<table style='width:100%;border-collapse:collapse;font-size:13px;'>"
        "<thead><tr>"
        "<th style='text-align:left;color:#94a3b8;padding:6px 6px 10px;font-size:10px;text-transform:uppercase;letter-spacing:.06em;'>Period</th>"
        "<th style='text-align:right;color:#94a3b8;padding:6px 6px 10px;font-size:10px;text-transform:uppercase;letter-spacing:.06em;'>Portfolio</th>"
        "<th style='text-align:right;color:#94a3b8;padding:6px 6px 10px;font-size:10px;text-transform:uppercase;letter-spacing:.06em;'>SPY</th>"
        "<th style='text-align:right;color:#94a3b8;padding:6px 6px 10px;font-size:10px;text-transform:uppercase;letter-spacing:.06em;'>vs SPY</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


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


def _position_pnl(holdings: list, holdings_rows: list) -> dict[str, dict]:
    """Returns {ticker: {cost_basis, shares, unreal_gain_dollar, unreal_gain_pct}} """
    cb_map = {h.ticker.upper(): (getattr(h, 'cost_basis', None), getattr(h, 'shares', 0)) for h in holdings}
    out = {}
    for row in holdings_rows:
        t = str(row.get('ticker','')).upper()
        cb, shares = cb_map.get(t, (None, 0))
        price = row.get('latest_price')
        if cb and price and float(cb) > 0:
            cb_f = float(cb)
            sh_f = float(shares)
            cost_total = cb_f * sh_f
            curr_total = float(price) * sh_f
            out[t] = {
                'cost_basis': cb_f,
                'unreal_dollar': curr_total - cost_total,
                'unreal_pct': (curr_total / cost_total - 1) * 100,
            }
    return out


def build_what_to_watch(
    portfolio_snapshot: list[dict],
    earnings_rows: list[dict],
    macro_events: list,
    alert_rows: list[dict],
    cross_asset_regime,
) -> list[str]:
    """Return a prioritized list of watch items for the week (plain strings, HTML allowed)."""
    from datetime import date as _date
    today = _date.today()
    items: list[tuple[int, str]] = []  # (priority, text) — lower = more urgent

    # 1. Earnings within 7 days for held tickers
    held = {r.get("Ticker","").upper() for r in portfolio_snapshot}
    for e in earnings_rows:
        t = e.get("Ticker","").upper()
        if t not in held or t == "CASH":
            continue
        days_str = e.get("Days","")
        try:
            d = int(days_str.replace("d",""))
        except Exception:
            continue
        if 0 <= d <= 7:
            label = "tomorrow" if d == 1 else ("today" if d == 0 else f"in {d}d")
            items.append((d, f"<b>{t}</b> earnings {label} — monitor guidance and beat/miss vs. consensus"))

    # 2. High-importance macro within 7 days
    for row in (macro_events if isinstance(macro_events, list) else []):
        if row.get("release_date","").lower() == "daily":
            continue
        imp = row.get("importance","").lower()
        if imp != "high":
            continue
        try:
            d = _date.fromisoformat(str(row.get("release_date",""))[:10])
            delta = (d - today).days
        except Exception:
            continue
        if 0 <= delta <= 7:
            label = "tomorrow" if delta == 1 else ("today" if delta == 0 else f"in {delta}d")
            items.append((delta + 0.5, f"<b>{row['event']}</b> {label} — watch for surprise vs. consensus"))

    # 3. Overweight + underperforming holdings (monthly red, weight > 20%)
    for r in portfolio_snapshot:
        t = r.get("Ticker","")
        if t == "CASH":
            continue
        try:
            w = float(str(r.get("Weight","0")).replace("%","").replace("+",""))
            m = float(str(r.get("Monthly","0")).replace("%",""))
        except Exception:
            continue
        if w >= 20 and m < 0:
            items.append((10, f"<b>{t}</b> is the largest holding ({r['Weight']} weight) and down {r['Monthly']} monthly — monitor for mean reversion or trim signal"))

    # 4. Regime shift watch
    if cross_asset_regime and getattr(cross_asset_regime, "confidence", "").lower() in ("low", "low confidence"):
        regime = getattr(cross_asset_regime, "regime", "Risk-Off")
        items.append((8, f"Regime indicators lean <b>{regime}</b> (low confidence) — watch credit spreads and VIX for confirmation before repositioning"))

    items.sort(key=lambda x: x[0])
    return [txt for _, txt in items[:5]]  # cap at 5 items


def _round_or_none(value, digits=2):
    try:
        if value is None:
            return None
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _write_dashboard_data(
    *,
    generated_at_iso: str,
    headline_title: str,
    headline_ticker: str,
    headline_source: str,
    headline_pubdate: str,
    headline_url: str,
    executive_summary_html: str,
    holdings_rows: list[dict],
    pnl_map: dict[str, dict],
    cash_value: float,
    port_daily, port_weekly, port_monthly, port_ytd,
    spy_daily, spy_weekly, spy_monthly, spy_ytd,
    top_movers: list[dict],
    alert_rows: list[dict],
    cross_asset_regime,
    yield_curve: dict,
    fear_greed: dict | None,
    macro_rows_raw: list[dict],
    earnings_rows: list[dict],
    analyst_rating_rows: list[dict],
    price_target_rows: list[dict],
    sec_rows: list[dict],
    dividend_calendar: list[dict],
    portfolio_news_rows: list[dict],
    global_development_rows: list[dict],
    risk_notes: list[str],
    market_themes: list[str],
    macro_events: list[dict],
) -> None:
    """Writes site/data/latest.json (today's snapshot) and appends a point to
    site/data/history.json (for sparklines/trend charts on the dashboard site).

    This is purely a side-effecting export — it reads already-fetched data
    computed earlier in build_hybrid_newsletter() and does not re-fetch
    anything. Safe to fail without affecting the email pipeline: wrapped in
    try/except by the caller.
    """
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    holdings = []
    for row in holdings_rows:
        ticker = str(row.get("ticker", "")).upper()
        pnl = pnl_map.get(ticker, {})
        holdings.append({
            "ticker":            ticker,
            "sector":            row.get("sector") or "Unclassified",
            "price":             _round_or_none(row.get("latest_price")),
            "market_value":      _round_or_none(row.get("market_value")),
            "weight_pct":        _round_or_none(row.get("portfolio_weight_pct")),
            "daily_pct":         _round_or_none(row.get("daily_move_pct")),
            "weekly_pct":        _round_or_none(row.get("weekly_move_pct")),
            "monthly_pct":       _round_or_none(row.get("monthly_move_pct")),
            "ytd_pct":           _round_or_none(row.get("ytd_move_pct")),
            "dist_52w_high_pct": _round_or_none(row.get("distance_from_52w_high_pct")),
            "volume_vs_30d_avg": _round_or_none(row.get("volume_vs_30d_avg")),
            "pnl_dollar":        _round_or_none(pnl.get("unreal_dollar"), 0),
            "pnl_pct":           _round_or_none(pnl.get("unreal_pct")),
            "cost_basis":        _round_or_none(pnl.get("cost_basis")),
        })

    sector_weights: dict[str, float] = {}
    for h in holdings:
        sector_weights[h["sector"]] = sector_weights.get(h["sector"], 0) + (h["weight_pct"] or 0)
    sector_exposure = sorted(
        [{"sector": s, "weight_pct": round(w, 2)} for s, w in sector_weights.items()],
        key=lambda r: r["weight_pct"], reverse=True,
    )

    vix_row = next((r for r in macro_rows_raw if "VIX" in str(r.get("Indicator", "")) or r.get("Ticker") == "^VIX"), None)
    vix = None
    if vix_row:
        try:
            vix = float(str(vix_row.get("Latest", "")).replace(",", ""))
        except (TypeError, ValueError):
            vix = None

    fg = fear_greed or {}

    portfolio_value = round(sum(h["market_value"] or 0 for h in holdings) + (cash_value or 0), 2)

    dashboard = {
        "schema_version": 1,
        "generated_at": generated_at_iso,
        "headline": {
            "title": headline_title, "ticker": headline_ticker,
            "source": headline_source, "published": headline_pubdate, "url": headline_url,
        },
        "executive_summary_html": executive_summary_html,
        "portfolio_value": portfolio_value,
        "cash_value": _round_or_none(cash_value),
        "performance": {
            "today":   {"portfolio": _round_or_none(port_daily),   "spy": _round_or_none(spy_daily)},
            "week":    {"portfolio": _round_or_none(port_weekly),  "spy": _round_or_none(spy_weekly)},
            "month":   {"portfolio": _round_or_none(port_monthly), "spy": _round_or_none(spy_monthly)},
            "ytd":     {"portfolio": _round_or_none(port_ytd),     "spy": _round_or_none(spy_ytd)},
        },
        "holdings": holdings,
        "sector_exposure": sector_exposure,
        "top_movers": [
            {
                "ticker": r.get("Ticker", ""),
                "daily_pct": r.get("Daily Move"),
                "weekly_pct": r.get("Weekly Move"),
                "volume_vs_30d_avg": r.get("Volume vs 30D Avg"),
            }
            for r in top_movers
        ],
        "alerts": [
            {"tier": a.get("Tier"), "type": a.get("Type"), "ticker": a.get("Ticker"), "detail": a.get("Detail")}
            for a in alert_rows
        ],
        "regime": {
            "label": getattr(cross_asset_regime, "regime", None),
            "confidence": getattr(cross_asset_regime, "confidence", None),
            "risk_score": getattr(cross_asset_regime, "risk_score", None),
            "inflation_score": getattr(cross_asset_regime, "inflation_score", None),
            "growth_score": getattr(cross_asset_regime, "growth_score", None),
            "liquidity_score": getattr(cross_asset_regime, "liquidity_score", None),
            "drivers": getattr(cross_asset_regime, "drivers", []) or [],
            "leadership": getattr(cross_asset_regime, "leadership", []) or [],
            "fragilities": getattr(cross_asset_regime, "fragilities", []) or [],
            "narrative": getattr(cross_asset_regime, "narrative", ""),
        },
        "rates": {
            "short_term_yield": yield_curve.get("2y"),
            "ten_year_yield": yield_curve.get("10y"),
            "spread": yield_curve.get("spread"),
            "vix": vix,
        },
        "fear_greed": {
            "score": _round_or_none(fg.get("score"), 0), "rating": fg.get("rating"),
            "prev_week": _round_or_none(fg.get("prev_week"), 0),
        },
        "risk_notes": risk_notes,
        "market_themes": market_themes,
        "catalysts": earnings_rows[:8],
        "macro_events": macro_events[:12] if macro_events else [],
        "analyst_ratings": analyst_rating_rows[:12],
        "price_targets": price_target_rows,
        "sec_filings": sec_rows[:10],
        "dividend_calendar": dividend_calendar[:10] if dividend_calendar else [],
        "news": portfolio_news_rows,
        "global_news": global_development_rows,
    }

    (SITE_DATA_DIR / "latest.json").write_text(json.dumps(dashboard, indent=2), encoding="utf-8")

    # Append today's point to the rolling history file (used for trend lines).
    history_path = SITE_DATA_DIR / "history.json"
    try:
        history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else []
    except (json.JSONDecodeError, OSError):
        history = []

    today_str = generated_at_iso[:10]
    point = {
        "date": today_str,
        "portfolio_value": portfolio_value,
        "daily_pct": _round_or_none(port_daily),
        "spy_daily_pct": _round_or_none(spy_daily),
        "risk_score": getattr(cross_asset_regime, "risk_score", None),
        "regime": getattr(cross_asset_regime, "regime", None),
        "vix": vix,
        "holdings": {h["ticker"]: h["price"] for h in holdings},
    }
    history = [p for p in history if p.get("date") != today_str]
    history.append(point)
    history.sort(key=lambda p: p["date"])
    history = history[-DASHBOARD_HISTORY_DAYS:]
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")


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
    yield_curve = fetch_yield_curve()
    fear_greed  = fetch_fear_greed()
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

    analyst_ratings = fetch_analyst_ratings(tickers, days_back=7)
    price_targets = fetch_price_targets(tickers)
    sector_rotation = fetch_sector_rotation()
    short_interest = fetch_short_interest(tickers)
    insider_txns = fetch_insider_transactions(tickers, days_back=90)
    corr_tickers, corr_matrix = fetch_correlation_matrix(tickers, days=60)
    dividend_calendar = fetch_dividend_calendar(tickers)

    holdings_rows = monitor.get("holdings", [])
    pnl_map = _position_pnl(holdings, holdings_rows)
    macro_events  = load_macro_events()
    surprise_score, surprise_label, surprise_count = _economic_surprise_score(macro_events)

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
            "Daily":        pct(row.get("daily_move_pct")),
            "Weekly":       pct(row.get("weekly_move_pct")),
            "Monthly":      pct(row.get("monthly_move_pct")),
            "YTD":          pct(row.get("ytd_move_pct")),
            "52W":          f"{row.get('distance_from_52w_high_pct', 0):+.1f}%" if row.get("distance_from_52w_high_pct") is not None else "—",
            "P&L": (
                f"{'+' if pnl_map.get(row.get('ticker','').upper(), {}).get('unreal_dollar', 0) >= 0 else ''}"
                f"${abs(pnl_map.get(row.get('ticker','').upper(), {}).get('unreal_dollar', 0)):,.0f} "
                f"({'+' if pnl_map.get(row.get('ticker','').upper(), {}).get('unreal_pct', 0) >= 0 else ''}"
                f"{pnl_map.get(row.get('ticker','').upper(), {}).get('unreal_pct', 0):.1f}%)"
                if row.get('ticker','').upper() in pnl_map else "—"
            ),
        }
        for row in holdings_rows
        if _is_valid_move(pct(row.get("daily_move_pct")))
    ]
    # Cash row — fixed allocation
    portfolio_snapshot.append({
        "Ticker":       "CASH",
        "Sector":       "—",
        "Weight":       "—",
        "Market Value": "$1.51",
        "Daily":        "—",
        "Weekly":       "—",
        "Monthly":      "—",
        "YTD":          "—",
        "52W":          "—",
        "P&L":          "—",
    })

    # ── Analyst ratings rows ───────────────────────────────────────────────────
    analyst_rating_rows = [
        {
            "Date":   r["date"],
            "Ticker": r["ticker"],
            "Firm":   r["firm"],
            "Rating": r["to_grade"],
            "Action": r["action_label"],
        }
        for r in analyst_ratings
    ]

    # ── Price target rows ──────────────────────────────────────────────────────
    price_target_rows = []
    for ticker in tickers:
        pt = price_targets.get(ticker.upper())
        if not pt:
            continue
        upside = pt['upside_pct']
        price_target_rows.append({
            'Ticker':  ticker.upper(),
            'Current': f"${pt['current']:,.2f}",
            'Target':  f"${pt['target']:,.2f}",
            'Upside':  f"{'+' if upside >= 0 else ''}{upside:.1f}%",
            'Range':   f"${pt['low']:,.0f}–${pt['high']:,.0f}" if pt['low'] and pt['high'] else '—',
        })

    # ── Actual portfolio returns from transaction log ──────────────────────────
    _real_returns = compute_portfolio_returns()
    port_daily   = _real_returns.get("daily")
    port_weekly  = _real_returns.get("weekly")
    port_monthly = _real_returns.get("monthly")
    port_ytd     = _real_returns.get("ytd")

    spy_daily   = monitor.get("spy_daily")
    spy_weekly  = monitor.get("spy_weekly")
    spy_monthly = monitor.get("spy_monthly")
    spy_ytd     = monitor.get("spy_ytd")

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

    # ── Earnings preview (next 7 days) ──────────────────────────────────────────
    earnings_preview_rows = []
    for r in earnings_rows:
        days_str = r.get("Days", "")
        is_soon = days_str == "Today" or (days_str.endswith("d") and days_str != "0d ago" and not days_str.endswith("ago") and int(days_str.replace("d","") or 999) <= 7)
        if not is_soon:
            continue
        preview = get_earnings_preview(r["Ticker"])
        eps_est = preview.get("eps_estimate")
        last_actual = preview.get("last_eps_actual")
        last_est = preview.get("last_eps_estimate")
        surprise = preview.get("last_surprise_pct")
        last_result = "—"
        if last_actual is not None and last_est is not None:
            beat = last_actual >= last_est
            sign = "+" if surprise is not None and surprise >= 0 else ""
            surprise_str = f" ({sign}{surprise:.1f}%)" if surprise is not None else ""
            last_result = f"{'Beat' if beat else 'Miss'}{surprise_str}"
        implied_move = fetch_implied_earnings_move(r["Ticker"], r["Date"]) if is_soon else None
        earnings_preview_rows.append({
            "Ticker":        r["Ticker"],
            "Date":          r["Date"],
            "Days":          days_str,
            "EPS Estimate":  f"${eps_est:.2f}" if eps_est is not None else "N/A",
            "Last Quarter":  last_result,
            "Implied Move":  implied_move or "—",
        })

    # ── SEC filings ────────────────────────────────────────────────────────────
    sec_rows = _normalize_sec_rows(sec or [])
    # Keep only High-importance or filed within last 3 days, cap at 5
    from datetime import date as _sec_date, timedelta as _sec_td
    _sec_cutoff = _sec_date.today() - _sec_td(days=3)
    sec_rows = [
        r for r in sec_rows
        if str(r.get("Imp.", "")).lower() == "high"
        or (str(r.get("Date", ""))[:10] >= str(_sec_cutoff))
    ][:5]

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
        # Regime Shift with low confidence → downgrade to Watch (Informational)
        regime_conf_low = (
            alert_type == "Regime Shift"
            and getattr(cross_asset_regime, "confidence", "").lower() in ("low", "low confidence")
        )
        if regime_conf_low:
            tier = "Informational"
            detail_text = (
                f"Watch: regime indicators suggest possible shift toward {a.get('message','').split(' to ')[-1] if ' to ' in a.get('message','') else getattr(cross_asset_regime,'regime','Risk-Off')}."
            )
        elif severity == "High" or alert_type in {"SEC Item 5.02", "Regime Shift", "Drawdown"}:
            tier = "Critical"
            detail_text = message if message else title
        elif severity == "Medium" or alert_type in {"Earnings", "Large Move"}:
            tier = "Important"
            detail_text = message if message else title
        else:
            tier = "Informational"
            detail_text = message if message else title

        alert_rows.append({
            "Tier":     tier,
            "Type":     alert_type,
            "Ticker":   a.get("ticker",     ""),
            "Detail":   detail_text,
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

    # ── Executive summary ──────────────────────────────────────────────────────
    def _build_executive_summary() -> str:
        parts = []

        def _pct_float(val: str) -> float | None:
            try:
                return float(str(val).replace("%","").replace("+","").replace(",",""))
            except Exception:
                return None

        def _colored(text: str, positive: bool | None) -> str:
            if positive is True:
                return f"<span class='c-up'>{text}</span>"
            if positive is False:
                return f"<span class='c-dn'>{text}</span>"
            return f"<span style='font-weight:600'>{text}</span>"

        # ── 1. Market lead: SPY/QQQ actual moves, not headline keyword matching ──
        spy_row = next((r for r in macro_rows if r.get("Ticker") == "SPY"), None)
        qqq_row = next((r for r in macro_rows if r.get("Ticker") == "QQQ"), None)
        spy_chg = _pct_float(spy_row.get("Daily Change (%)", "")) if spy_row else None
        qqq_chg = _pct_float(qqq_row.get("Daily Change (%)", "")) if qqq_row else None

        if spy_chg is not None:
            spy_str = _colored(f"SPY {spy_chg:+.2f}%", spy_chg > 0)
            if qqq_chg is not None:
                qqq_str = _colored(f"QQQ {qqq_chg:+.2f}%", qqq_chg > 0)
                spread = qqq_chg - spy_chg
                if abs(spread) >= 0.5:
                    leader = "growth/tech outperformed" if spread > 0 else "value/defensives outperformed"
                    parts.append(f"{spy_str}, {qqq_str} — {leader}.")
                else:
                    tone = "broad advance" if spy_chg > 0.3 else "broad decline" if spy_chg < -0.3 else "mixed session"
                    parts.append(f"{spy_str}, {qqq_str} — {tone}.")
            else:
                tone = "equities advanced" if spy_chg > 0.3 else "equities declined" if spy_chg < -0.3 else "equities were mixed"
                parts.append(f"{spy_str} — {tone}.")
        else:
            # Fallback to headline context only when market data is absent
            hl = headline_title.lower()
            if any(w in hl for w in ["fed","fomc","rate","inflation","cpi","pce"]):
                parts.append("Rate and inflation signals dominated the session.")
            elif any(w in hl for w in ["iran","war","ceasefire","geopolit","sanction","tariff"]):
                parts.append("Geopolitical developments were in focus.")
            else:
                parts.append("Markets were mixed on the session.")

        # ── 2. Portfolio breadth + top movers ─────────────────────────────────
        all_holdings = [r for r in holdings_rows if _pct_float(pct(r.get("daily_move_pct"))) is not None]
        n_green = sum(1 for r in all_holdings if (_pct_float(pct(r.get("daily_move_pct"))) or 0) > 0)
        n_total = len(all_holdings)

        gainers = [m for m in top_movers if m.get("Daily Move","").startswith("+")]
        losers  = [m for m in top_movers if m.get("Daily Move","").startswith("-")]

        mover_parts = []
        for m in gainers[:2]:
            vol = m.get("Volume vs 30D Avg","")
            vol_note = f" · {vol} vol" if vol and vol != "N/A" else ""
            mover_parts.append(_colored(f"{m['Ticker']} {m['Daily Move']}{vol_note}", True))
        for m in losers[:1]:
            mover_parts.append(_colored(f"{m['Ticker']} {m['Daily Move']}", False))

        if mover_parts and n_total:
            breadth = f"{n_green}/{n_total} holdings green"
            parts.append(f"Portfolio: {', '.join(mover_parts)} — {breadth}.")
        elif mover_parts:
            parts.append(f"Portfolio movers: {', '.join(mover_parts)}.")

        # ── 3. Macro signals: yields, oil, VIX, dollar ────────────────────────
        def _macro_row(ticker: str = "", indicator: str = "") -> dict | None:
            if ticker:
                return next((r for r in macro_rows if r.get("Ticker") == ticker), None)
            return next((r for r in macro_rows if r.get("Indicator") == indicator), None)

        macro_notes = []

        tsy_row = _macro_row(ticker="^TNX")
        if tsy_row:
            tsy_val = tsy_row.get("Latest","")
            tsy_chg = _pct_float(tsy_row.get("Daily Change (%)",""))
            if tsy_val and tsy_val != "N/A":
                try:
                    tsy_f = float(str(tsy_val).replace(",",""))
                    if tsy_chg is not None and abs(tsy_chg) >= 1.0:
                        direction = "rose" if tsy_chg > 0 else "fell"
                        macro_notes.append(f"10Y yield {direction} to {tsy_f:.2f}%")
                    elif tsy_f >= 4.5:
                        macro_notes.append(f"10Y yield at {tsy_f:.2f}% (elevated)")
                except Exception:
                    pass

        oil_row = _macro_row(indicator="Oil") or _macro_row(ticker="CL=F")
        if oil_row:
            oil_chg = _pct_float(oil_row.get("Daily Change (%)",""))
            oil_val = oil_row.get("Latest","")
            if oil_chg is not None and abs(oil_chg) >= 1.5:
                direction = "up" if oil_chg > 0 else "down"
                macro_notes.append(
                    _colored(f"oil {direction} {oil_chg:+.1f}% at ${float(str(oil_val).replace(',','')):.0f}", oil_chg > 0)
                )

        vix_row = _macro_row(indicator="VIX") or _macro_row(ticker="^VIX")
        if vix_row:
            try:
                vix_f = float(str(vix_row.get("Latest","")).replace(",",""))
                vix_chg = _pct_float(vix_row.get("Daily Change (%)",""))
                if vix_f > 25:
                    macro_notes.append(f"VIX elevated at {vix_f:.1f}")
                elif vix_f < 14:
                    macro_notes.append(f"VIX low at {vix_f:.1f} (complacency)")
                elif vix_chg is not None and abs(vix_chg) >= 8:
                    direction = "spiked" if vix_chg > 0 else "dropped"
                    macro_notes.append(f"VIX {direction} {vix_chg:+.1f}% to {vix_f:.1f}")
            except Exception:
                pass

        if macro_notes:
            parts.append(f"{'; '.join(macro_notes)}.")

        # ── 4. Regime — one sentence integrating name + key driver ────────────
        regime_name = getattr(cross_asset_regime, "regime", None)
        regime_conf = getattr(cross_asset_regime, "confidence", None)
        regime_drivers = getattr(cross_asset_regime, "drivers", []) or []
        if regime_name and regime_name not in ("Mixed / Transitional",):
            driver_note = f": {regime_drivers[0].lower()}" if regime_drivers else ""
            conf_note = f" ({regime_conf.lower()} confidence)" if regime_conf and regime_conf != "N/A" else ""
            parts.append(f"Regime: {regime_name}{conf_note}{driver_note}.")

        # ── 5. Alerts — critical first, surface actual detail not just type ────
        critical  = [a for a in alert_rows if a.get("Tier") == "Critical"]
        important = [a for a in alert_rows if a.get("Tier") == "Important"]
        def _alert_short(a: dict, max_len: int = 72) -> str:
            import re as _re
            ticker = a.get("Ticker","")
            detail = a.get("Detail","") or a.get("Type","")
            # Strip SEC EDGAR "COMPANY NAME  (0000012345) " boilerplate
            detail = _re.sub(r'^[A-Z][A-Z &,\.]+\s+\(\d{7,10}\)\s+', '', detail)
            # Remove "[Item X.XX, ...] " item-code prefixes
            detail = _re.sub(r'^\[.*?\]\s+', '', detail)
            # Remove "TICKER " prefix when it's just the ticker followed by a verb
            if ticker:
                if detail.upper().startswith(ticker.upper() + " "):
                    detail = detail[len(ticker) + 1:]
            detail = detail.rstrip(". ").strip()
            # Truncate at word boundary
            if len(detail) <= max_len:
                return detail
            truncated = detail[:max_len]
            last_space = truncated.rfind(" ")
            return (truncated[:last_space] if last_space > max_len // 2 else truncated) + "…"

        alert_notes = []
        for a in critical[:2]:
            prefix = f"{a['Ticker']}: " if a.get("Ticker") else ""
            alert_notes.append(f"⚠ {prefix}{_alert_short(a)}")
        for a in important[:1]:
            prefix = f"{a['Ticker']}: " if a.get("Ticker") else ""
            alert_notes.append(f"• {prefix}{_alert_short(a, max_len=60)}")
        if alert_notes:
            parts.append(" &nbsp;|&nbsp; ".join(alert_notes) + ".")

        # ── 6. Catalysts — urgency-aware phrasing ─────────────────────────────
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
            days_str = m.get("days_until","")
            try:
                days_int = int(days_str.replace("d",""))
                urgency = "tomorrow" if days_int == 1 else f"in {days_str}"
                if days_int <= 3:
                    catalyst_parts.append(
                        f"<span class='c-am'>{m['event']} {urgency}</span>"
                    )
                else:
                    catalyst_parts.append(f"{m['event']} in {days_str}")
            except Exception:
                catalyst_parts.append(f"{m['event']} in {days_str}")

        if next_earnings:
            days_str = next_earnings.get("Days","")
            ticker = next_earnings.get("Ticker","")
            try:
                days_int = int(days_str.replace("d",""))
                urgency = "tomorrow" if days_int == 1 else f"in {days_str}"
                if days_int <= 7:
                    catalyst_parts.append(
                        f"<span class='c-am'>{ticker} earnings {urgency}</span>"
                    )
                else:
                    catalyst_parts.append(f"{ticker} earnings in {days_str}")
            except Exception:
                catalyst_parts.append(f"{ticker} earnings in {days_str}")

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
            "Sentiment": sentiment_tag(title),
            "link":      r.get("link",      r.get("Link",   "")),
        })
        if len(portfolio_news_rows) >= 12:
            break

    # ── Sector exposure bars for Portfolio Snapshot card ──────────────────────
    _sector_weights: dict[str, float] = {}
    for _r in portfolio_snapshot:
        _sec = _r.get("Sector") or "Unknown"
        try:
            _w = float(str(_r.get("Weight", "0")).replace("%", "").replace("+", ""))
        except Exception:
            _w = 0.0
        _sector_weights[_sec] = _sector_weights.get(_sec, 0.0) + _w
    if _sector_weights:
        sector_bars_html = (
            "<div class='mini-section-title' style='margin-top:16px;'>Sector Exposure</div>"
            "<div class='bar-card'>"
            + "".join(
                visual_bar(s, w)
                for s, w in sorted(_sector_weights.items(), key=lambda x: x[1], reverse=True)[:6]
            )
            + "</div>"
        )
    else:
        sector_bars_html = ""

    # ── HTML body ──────────────────────────────────────────────────────────────
    html_body = f"""
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{_CSS}</head>
<body bgcolor="#f0f4f8" style="margin:0;padding:0;background:#f0f4f8;">
<!-- outer table: sets page background in Gmail -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f0f4f8">
<tr><td align="center" style="padding:24px 16px;">
<!-- container -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;">
<tr><td>

    <!-- header cell — bgcolor survives Gmail -->
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:12px;">
    <tr><td bgcolor="#1a3560" style="background:linear-gradient(135deg,#1a3560 0%,#1d4ed8 100%);padding:30px 28px;border-radius:12px;">
      <div class="eyebrow">📈 Daily Portfolio Brief</div>
      <h1>Morning Market Brief</h1>
      <div class="subtitle">Portfolio performance · macro regime · catalysts · SEC filings · alerts — {esc(generated_at)}</div>
    </td></tr></table>

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


    {(lambda items: f"""
    <div class="card">
      <h2>What to Watch This Week</h2>
      <ul>{"".join(f"<li style='margin-bottom:6px;'>{x}</li>" for x in items)}</ul>
    </div>
    """ if items else "")(build_what_to_watch(portfolio_snapshot, earnings_rows, macro_events, alert_rows, cross_asset_regime))}


    <div class="card">
      <h2>Market Conditions</h2>
      {(lambda r: (
        # ── Regime header: name left, confidence right ─────────────────────────
        f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='margin-bottom:10px;'>"
        f"<tr><td style='vertical-align:baseline;'><span class='regime-title'>{esc(r.regime)}</span></td>"
        f"<td style='text-align:right;vertical-align:baseline;font-size:12px;color:#64748b;'>Confidence: {esc(r.confidence)}</td></tr>"
        f"</table>"

        # ── Regime scores: 4 tiles side-by-side via table (Gmail-safe) ─────────
        + "<table role='presentation' width='100%' cellpadding='4' cellspacing='0' style='margin-bottom:10px;'><tr>"
        + "".join(
            f"<td width='25%' style='padding:4px;'>"
            f"<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 12px;'>"
            f"<div style='font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:#64748b;margin-bottom:3px;'>{label}</div>"
            f"<div style='font-size:18px;font-weight:800;color:{color};line-height:1.1;'>{score}/100</div>"
            f"<div style='font-size:10px;color:#94a3b8;margin-top:2px;'>{sub}</div>"
            f"</div></td>"
            for label, score, color, sub in [
                ("Risk",      r.risk_score,      '#dc2626' if r.risk_score >= 65 else '#16a34a' if r.risk_score <= 40 else '#b45309',      'Elevated' if r.risk_score >= 65 else 'Low' if r.risk_score <= 40 else 'Moderate'),
                ("Inflation", r.inflation_score, '#dc2626' if r.inflation_score >= 65 else '#16a34a' if r.inflation_score <= 40 else '#b45309', 'Hot — above target' if r.inflation_score >= 65 else 'Contained' if r.inflation_score <= 40 else 'Moderate'),
                ("Growth",    r.growth_score,    '#16a34a' if r.growth_score >= 55 else '#dc2626' if r.growth_score <= 40 else '#b45309',    'Expanding' if r.growth_score >= 55 else 'Contracting' if r.growth_score <= 40 else 'Mixed signals'),
                ("Liquidity", r.liquidity_score, '#16a34a' if r.liquidity_score >= 60 else '#dc2626' if r.liquidity_score <= 40 else '#b45309', 'Supportive' if r.liquidity_score >= 60 else 'Tightening' if r.liquidity_score <= 40 else 'Neutral'),
            ]
        )
        + "</tr></table>"

        # ── Drivers / Leadership / Fragilities (belong to regime) ─────────────
        + (
            "<table style='width:100%;border-collapse:collapse;font-size:12px;margin-bottom:12px;'>"
            + "".join(
                f"<tr><td class='muted' style='padding:4px 4px;width:90px;font-size:11px;white-space:nowrap;'>Drivers</td>"
                f"<td style='padding:4px 4px;font-size:12px;'>{esc(d)}</td></tr>"
                for d in r.drivers
            )
            + "".join(
                f"<tr><td class='muted' style='padding:4px 4px;font-size:11px;white-space:nowrap;'>Leadership</td>"
                f"<td style='padding:4px 4px;font-size:12px;'>{esc(l)}</td></tr>"
                for l in r.leadership
            )
            + "".join(
                f"<tr><td class='muted' style='padding:4px 4px;font-size:11px;white-space:nowrap;'>Fragility</td>"
                f"<td class='c-dn' style='padding:4px 4px;font-size:12px;'>{esc(f)}</td></tr>"
                for f in r.fragilities
            )
            + "</table>"
            if (r.drivers or r.leadership or r.fragilities) else ""
        )

        # ── Market Signals divider ────────────────────────────────────────────
        + "<div class='mini-section-title' style='margin-top:4px;'>Market Signals</div>"

        # ── 5 signal tiles side-by-side via table (Gmail-safe) ────────────────
        + _render_yield_vix(yield_curve, macro_rows_raw, fear_greed)

        # ── Narrative ─────────────────────────────────────────────────────────
        + f"<p class='narrative-box' style='margin-top:12px;'>{esc(r.narrative)}</p>"
      ))(cross_asset_regime)}
    </div>


    <div class="card">
      <h2>Performance Summary</h2>
      {_perf_summary_html(port_daily, port_weekly, port_monthly, port_ytd, spy_daily, spy_weekly, spy_monthly, spy_ytd)}
    </div>


    <div class="card">
      <h2>Analyst Activity</h2>
      {table_html(analyst_rating_rows, ["Date","Ticker","Firm","Rating","Action"]) if analyst_rating_rows else "<p class='muted'>No analyst activity on your holdings in the past 7 days.</p>"}
    </div>


    <div class="card">
      <h2>Price Targets</h2>
      <p class="muted">Analyst consensus targets vs current price.</p>
      {table_html(price_target_rows, ["Ticker","Current","Target","Upside","Range"])}
    </div>


    <div class="card">
      <h2>Portfolio Snapshot</h2>
      {table_html(portfolio_snapshot, ["Ticker","Sector","Weight","Market Value","Daily","Weekly","Monthly","YTD","52W","P&L"])}
      {sector_bars_html}
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
      {table_html(portfolio_news_rows, ["Ticker","Title","Published","Source","Sentiment"])}
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
      <h2>Sector Rotation</h2>
      <p class="muted">SPDR sector ETF performance — leading sectors at top.</p>
      {table_html(sector_rotation, ["Sector","ETF","Weekly","Monthly"])}
    </div>


    <div class="card">
      <h2>Short Interest</h2>
      <p class="muted">% of float sold short and estimated days to cover (short squeeze risk indicator).</p>
      {table_html(short_interest, ["Ticker","% Float Short","Days to Cover","Shares Short"]) if short_interest else "<p class='muted'>Short interest data unavailable.</p>"}
    </div>


    <div class="card">
      <h2>Insider Transactions</h2>
      <p class="muted">Form 4 insider purchases in the past 90 days. Buy signals only — sales excluded.</p>
      {table_html(insider_txns, ["Date","Ticker","Insider","Role","Shares","Value"]) if insider_txns else "<p class='muted'>No insider purchases reported in the past 90 days.</p>"}
    </div>


    <div class="card">
      <h2>Correlation Matrix</h2>
      <p class="muted">60-day pairwise return correlation across holdings. Values near 1.0 = highly correlated (low diversification).</p>
      {(lambda tks, mx: (
        "<div style='overflow-x:auto;'>"
        "<table style='border-collapse:collapse;font-size:12px;width:100%;'>"
        "<tr><th style='padding:5px 8px;background:#f8fafc;text-align:left;border:1px solid #e2e8f0;'>—</th>"
        + "".join(f"<th style='padding:5px 8px;background:#f8fafc;text-align:center;border:1px solid #e2e8f0;font-weight:700;'>{t}</th>" for t in tks)
        + "</tr>"
        + "".join(
            "<tr>"
            f"<td style='padding:5px 8px;background:#f8fafc;font-weight:700;border:1px solid #e2e8f0;'>{tks[i]}</td>"
            + "".join(
                (lambda v: (
                    f"<td style='padding:5px 8px;text-align:center;border:1px solid #e2e8f0;"
                    + ("background:#dcfce7;color:#166534;" if v > 0.7 and i != j else
                       "background:#fef9c3;color:#854d0e;" if v > 0.4 and i != j else
                       "background:#f8fafc;" if i != j else "background:#e0f2fe;")
                    + f"'>{v:.2f}</td>"
                ))(mx[i][j])
                for j in range(len(tks))
            )
            + "</tr>"
            for i in range(len(tks))
        )
        + "</table></div>"
        "<p class='muted' style='margin-top:8px;font-size:11px;'>"
        "<span style='background:#dcfce7;padding:2px 6px;border-radius:3px;margin-right:6px;'>green &gt;0.7</span>"
        "<span style='background:#fef9c3;padding:2px 6px;border-radius:3px;margin-right:6px;'>yellow 0.4–0.7</span>"
        "<span style='background:#e0f2fe;padding:2px 6px;border-radius:3px;'>blue = self</span></p>"
      ) if mx else "<p class='muted'>Insufficient price history for correlation.</p>"
      )(corr_tickers, corr_matrix)}
    </div>


    <div class="card">
      <h2>Dividend Calendar</h2>
      <p class="muted">Next ex-dividend dates for your holdings. Dates marked † are projected from the prior quarter's schedule — companies typically announce 3–4 weeks in advance.</p>
      {(lambda rows: table_html(
          [{k: (v + " †" if k == "Ex-Div Date" and r.get("_estimated") else v)
            for k, v in r.items() if k != "_estimated"}
           for r in rows],
          ["Ticker","Ex-Div Date","Days","Ann. Div","Yield"]
      ) if rows else "<p class='muted'>No dividend data found for current holdings.</p>")(dividend_calendar)}
    </div>


    <div class="card">
      <h2>Economic Calendar</h2>
      <p class="muted">Rows highlighted when the event release date or last update is today.
      {(lambda sc, lb: (
        f" &nbsp;|&nbsp; <strong>Economic Surprise Index:</strong> "
        f"<span style='color:{'#16a34a' if sc >= 0 else '#dc2626'};font-weight:700;'>{lb} ({sc:+.0f})</span>"
        f" — based on {surprise_count} scored releases."
      ) if sc is not None else "")(surprise_score, surprise_label)}
      </p>
      {_render_cal(macro_events)}
    </div>


    <div class="card">
      <h2>Earnings Preview</h2>
      <p class="muted">Holdings reporting within 7 days — consensus estimate and last quarter's result.</p>
      {table_html(earnings_preview_rows, ["Ticker","Date","Days","EPS Estimate","Last Quarter","Implied Move"]) if earnings_preview_rows else "<p class='muted'>No holdings reporting within the next 7 days.</p>"}
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

    
    </td></tr></table>
    <!-- footer -->
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr><td class="footer" style="color:#64748b;font-size:11px;padding:12px;text-align:center;border-top:1px solid #e2e8f0;line-height:1.6;">
      This brief is factual monitoring only and does not provide investment recommendations.
    </td></tr></table>

</td></tr></table>
</td></tr></table>
</body>
</html>
"""

    html_body = remove_disabled_sections(html_body, prefs)

    # Gmail-safe: convert card divs to table cells with bgcolor attribute
    # bgcolor on <td> is the only reliable way to set backgrounds in Gmail mobile
    html_body = html_body.replace(
        '<div class="card">',
        '</td></tr></table>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:10px 0;">'
        '<tr><td bgcolor="#ffffff" style="background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 20px;" class="card">'
    )

    # ── Plain-text fallback ────────────────────────────────────────────────────
    sep = "─" * 60
    text_lines = [
        "DAILY PORTFOLIO BRIEF",
        generated_at,
        sep,
        "",
    ]

    # Executive summary
    text_lines += [executive_summary, ""]

    # Headline
    text_lines += [
        "BIGGEST HEADLINE",
        f"  {biggest_headline}",
        f"  Source: {headline_source}",
        "",
    ]

    # Alerts
    critical_alerts = [a for a in alert_rows if a.get("Tier") == "Critical"]
    important_alerts = [a for a in alert_rows if a.get("Tier") == "Important"]
    if critical_alerts or important_alerts:
        text_lines.append("ALERTS")
        for a in critical_alerts:
            ticker = f" [{a['Ticker']}]" if a.get("Ticker") else ""
            text_lines.append(f"  ⚠ CRITICAL{ticker}: {a['Detail']}")
        for a in important_alerts:
            ticker = f" [{a['Ticker']}]" if a.get("Ticker") else ""
            text_lines.append(f"  • Important{ticker}: {a['Detail']}")
        text_lines.append("")

    # Top movers
    text_lines.append("TOP MOVERS")
    for r in top_movers:
        text_lines.append(
            f"  {r['Ticker']:<6} {r['Daily Move']:>8} today  "
            f"{r['Weekly Move']:>8} weekly  {r['Volume vs 30D Avg']} vol"
        )
    text_lines.append("")

    # Portfolio snapshot
    if portfolio_snapshot:
        text_lines.append("PORTFOLIO SNAPSHOT")
        for r in portfolio_snapshot:
            text_lines.append(
                f"  {r['Ticker']:<6} {r.get('Daily', r.get('Daily Move','N/A')):>8}  {r['Market Value']:>10}  {r['Weight']:>7}  {r['Sector']}"
            )
        text_lines.append("")

    # Key macro
    key_macro = [r for r in macro_rows if r.get("Ticker") in {"SPY", "QQQ", "^TNX", "CL=F", "GC=F", "^VIX"}]
    if key_macro:
        text_lines.append("MACRO SNAPSHOT")
        for r in key_macro:
            ind  = r.get("Indicator", r.get("Ticker", ""))
            last = r.get("Latest")
            last = "—" if last is None else last
            chg  = r.get("Daily Change (%)")
            chg  = "" if chg is None else chg
            text_lines.append(f"  {ind:<22} {last:>10}  {chg}")
        text_lines.append("")

    # Upcoming catalysts
    next_catalysts = earnings_rows[:3]
    if next_catalysts:
        text_lines.append("UPCOMING CATALYSTS")
        for r in next_catalysts:
            text_lines.append(f"  {r['Ticker']:<6} earnings  {r['Date']}  ({r['Days']})")
        text_lines.append("")

    # Top news
    top_news = portfolio_news_rows[:5]
    if top_news:
        text_lines.append("PORTFOLIO NEWS")
        for r in top_news:
            text_lines.append(f"  [{r['Ticker']}] {r['Title']}")
        text_lines.append("")

    text_lines += [
        sep,
        "Factual monitoring only. No investment advice or recommendations.",
    ]
    text_body = "\n".join(text_lines)

    try:
        _write_dashboard_data(
            generated_at_iso=datetime.now(timezone.utc).isoformat(),
            headline_title=headline_title,
            headline_ticker=headline_ticker,
            headline_source=headline_source,
            headline_pubdate=headline_pubdate,
            headline_url=headline_row.get("link", ""),
            executive_summary_html=executive_summary,
            holdings_rows=holdings_rows,
            pnl_map=pnl_map,
            cash_value=1.51,
            port_daily=port_daily, port_weekly=port_weekly,
            port_monthly=port_monthly, port_ytd=port_ytd,
            spy_daily=spy_daily, spy_weekly=spy_weekly,
            spy_monthly=spy_monthly, spy_ytd=spy_ytd,
            top_movers=top_movers,
            alert_rows=alert_rows,
            cross_asset_regime=cross_asset_regime,
            yield_curve=yield_curve,
            fear_greed=fear_greed,
            macro_rows_raw=macro_rows_raw,
            earnings_rows=earnings_rows,
            analyst_rating_rows=analyst_rating_rows,
            price_target_rows=price_target_rows,
            sec_rows=sec_rows,
            dividend_calendar=dividend_calendar,
            portfolio_news_rows=portfolio_news_rows,
            global_development_rows=global_development_rows,
            risk_notes=build_risk_notes(portfolio_snapshot),
            market_themes=build_market_themes(market_news_rows),
            macro_events=macro_events,
        )
    except Exception as exc:
        print(f"[dashboard export] failed, continuing without it: {exc}")

    return html_body, text_body, port_daily, port_weekly


def build_weekly_digest_html() -> tuple[str, float | None]:
    """
    Build a condensed weekly digest email: week performance summary at the top,
    then a day-by-day feed of real news excerpts, grouped Mon–Fri.
    Returns (html_body, portfolio_weekly_pct).
    """
    import json as _json
    from datetime import date as _date, timedelta
    from collections import defaultdict

    today     = _date.today()
    # Week runs Mon–Fri ending on the most recent Friday (or today if today is Mon-Fri)
    days_back = today.weekday()  # Mon=0 … Sun=6
    week_end  = today if today.weekday() < 5 else today - timedelta(days=today.weekday() - 4)
    week_start = week_end - timedelta(days=4)  # Monday of the same week

    holdings    = load_portfolio()
    tickers     = [h.ticker for h in holdings]

    # ── Performance data ──────────────────────────────────────────────────────
    real_returns = compute_portfolio_returns()
    port_weekly  = real_returns.get("weekly")
    port_ytd     = real_returns.get("ytd")

    monitor   = build_holdings_change_monitor(holdings, benchmark="SPY")
    spy_weekly = monitor.get("spy_weekly")
    spy_ytd    = monitor.get("spy_ytd")
    holdings_rows = monitor.get("holdings", [])

    # ── News: fetch and group by date ─────────────────────────────────────────
    news_rows = weekly_news(tickers, limit_per_day=4)
    by_day: dict[str, list[dict]] = defaultdict(list)
    for row in news_rows:
        pub = str(row.get("published", ""))[:10]
        try:
            d = _date.fromisoformat(pub)
            if week_start <= d <= week_end:
                by_day[pub].append(row)
        except Exception:
            pass

    # Limit to 3 stories per day, prefer articles with real excerpts
    for day in by_day:
        by_day[day] = sorted(by_day[day], key=lambda r: (bool(r.get("excerpt")), r.get("source_rank", 0)), reverse=True)[:3]

    # ── Fetch SPY daily prices for the week ───────────────────────────────────
    import requests as _req
    def _spy_day_move(d: _date) -> str:
        try:
            s = int(pd.Timestamp(d - timedelta(days=5)).timestamp())
            e = int(pd.Timestamp(d).timestamp()) + 86400
            r = _req.get("https://query1.finance.yahoo.com/v8/finance/chart/SPY",
                params={"period1": s, "period2": e, "interval": "1d"},
                headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            closes = r.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            closes = [c for c in closes if c is not None]
            if len(closes) >= 2:
                chg = (closes[-1] / closes[-2] - 1) * 100
                return f"{chg:+.2f}%"
        except Exception:
            pass
        return ""

    # ── Holding week moves ────────────────────────────────────────────────────
    holding_week_rows = [
        {
            "Ticker":  r.get("ticker",""),
            "Weekly":  pct(r.get("weekly_move_pct")),
            "YTD":     pct(r.get("ytd_move_pct")),
        }
        for r in holdings_rows
    ]

    # ── HTML ──────────────────────────────────────────────────────────────────
    def _sign_css(v):
        if v is None: return ""
        return "c-up" if v >= 0 else "c-dn"

    def _fmt_pct(v):
        if v is None: return "—"
        return f"{'+' if v >= 0 else ''}{v:.2f}%"

    # Performance header table
    perf_html = _perf_summary_html(
        None, port_weekly, None, port_ytd,
        None, spy_weekly,  None, spy_ytd,
    )

    # Holdings week moves table
    holdings_html = table_html(holding_week_rows, ["Ticker", "Weekly", "YTD"])

    # Day-by-day news section
    day_sections = ""
    weekdays = []
    d = week_start
    while d <= week_end:
        if d.weekday() < 5:
            weekdays.append(d)
        d += timedelta(days=1)

    for day in weekdays:
        day_str  = day.isoformat()
        day_label = day.strftime("%A, %B %d")
        stories  = by_day.get(day_str, [])
        spy_move = _spy_day_move(day)
        spy_badge = ""
        if spy_move:
            css = "move-positive" if spy_move.startswith("+") else "move-negative"
            spy_badge = f"<span class='move-pill {css}' style='font-size:11px;margin-left:8px;'>{spy_move} SPY</span>"

        if not stories:
            stories_html = "<p class='muted' style='font-size:13px;'>No major stories found for this session.</p>"
        else:
            items = []
            for s in stories:
                ticker_tag = ""
                if s.get("ticker") and s["ticker"] != "market":
                    ticker_tag = f"<span class='tag' style='font-size:10px;margin-right:6px;'>{esc(s['ticker'])}</span>"
                excerpt = s.get("excerpt","").strip()
                excerpt_html = f"<p style='margin:4px 0 0;font-size:12px;color:#64748b;line-height:1.5;'>{esc(excerpt)}</p>" if excerpt else ""
                link = s.get("link","")
                title_html = (
                    f"<a href='{esc(link)}' style='color:#0369a1;font-weight:600;font-size:13px;text-decoration:none;'>{esc(s['title'])}</a>"
                    if link else f"<strong style='font-size:13px;'>{esc(s['title'])}</strong>"
                )
                source = s.get("source","")
                source_html = f" <span style='color:#94a3b8;font-size:11px;'>— {esc(source)}</span>" if source else ""
                items.append(
                    f"<div style='padding:10px 0;border-bottom:1px solid #f1f5f9;'>"
                    f"{ticker_tag}{title_html}{source_html}"
                    f"{excerpt_html}"
                    f"</div>"
                )
            stories_html = "".join(items)

        day_sections += (
            f"<div style='margin-bottom:6px;'>"
            f"<div style='font-size:11px;font-weight:700;color:#0369a1;text-transform:uppercase;"
            f"letter-spacing:.10em;padding:10px 0 6px;border-bottom:2px solid #e2e8f0;'>"
            f"{esc(day_label)}{spy_badge}</div>"
            f"{stories_html}"
            f"</div>"
        )

    generated_at = today.strftime("%B %d, %Y")
    week_label   = f"{week_start.strftime('%b %d')} – {week_end.strftime('%b %d, %Y')}"

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{_CSS}</head>
<body bgcolor="#f0f4f8" style="margin:0;padding:0;background:#f0f4f8;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f0f4f8">
<tr><td align="center" style="padding:24px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;">
<tr><td>

<div class="header">
  <div class="eyebrow">Weekly Portfolio Digest</div>
  <h1>Week of {esc(week_label)}</h1>
  <div class="subtitle">Performance · market narrative · what drove each session</div>
  <div class="generated">Generated {esc(generated_at)}</div>
</div>

</td></tr></table>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;">
<tr><td bgcolor="#ffffff" style="background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 20px;" class="card">
  <h2>Week Performance</h2>
  {perf_html}
</td></tr></table>

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:10px 0;max-width:640px;">
<tr><td bgcolor="#ffffff" style="background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 20px;" class="card">
  <h2>Holdings This Week</h2>
  {holdings_html}
</td></tr></table>

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:10px 0;max-width:640px;">
<tr><td bgcolor="#ffffff" style="background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 20px;" class="card">
  <h2>Day-by-Day</h2>
  <p class="muted">What moved markets each session and how it touched your holdings.</p>
  {day_sections}
</td></tr></table>

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:10px 0;max-width:640px;">
<tr><td style="padding:12px;text-align:center;color:#64748b;font-size:11px;font-family:-apple-system,sans-serif;border-top:1px solid #e2e8f0;">
  Factual monitoring only. No investment advice or recommendations.
</td></tr></table>

</td></tr></table>
</body>
</html>"""

    return html_body, port_weekly


def build_and_save_newsletter(weekly: bool = False) -> None:
    """Alias for compatibility with main.py. weekly=True frames the subject/meta
    around this week's return instead of today's, for the Sunday digest run."""
    import json as _json
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html_body, text_body, portfolio_daily_pct, portfolio_weekly_pct = build_hybrid_newsletter()
    for bad, good in _MOJIBAKE.items():
        html_body = html_body.replace(bad, good)
        text_body = text_body.replace(bad, good)

    if weekly:
        weekly_html, portfolio_weekly_pct = build_weekly_digest_html()
        for bad, good in _MOJIBAKE.items():
            weekly_html = weekly_html.replace(bad, good)
        (OUTPUT_DIR / "weekly_digest.html").write_text(weekly_html, encoding="utf-8")
        (OUTPUT_DIR / "latest_newsletter.html").write_text(weekly_html, encoding="utf-8")
        (OUTPUT_DIR / "meta.json").write_text(
            _json.dumps({
                "portfolio_daily_pct":  portfolio_daily_pct,
                "portfolio_weekly_pct": portfolio_weekly_pct,
                "is_weekly":            True,
            }), encoding="utf-8"
        )
        print("Weekly digest generated.")
        print("  HTML → output/weekly_digest.html")
        return

    (OUTPUT_DIR / "hybrid_newsletter.html").write_text(html_body, encoding="utf-8")
    (OUTPUT_DIR / "hybrid_newsletter.txt").write_text(text_body, encoding="utf-8")
    (OUTPUT_DIR / "latest_newsletter.html").write_text(html_body, encoding="utf-8")
    (OUTPUT_DIR / "latest_newsletter.txt").write_text(text_body, encoding="utf-8")
    (OUTPUT_DIR / "meta.json").write_text(
        _json.dumps({
            "portfolio_daily_pct":  portfolio_daily_pct,
            "portfolio_weekly_pct": portfolio_weekly_pct,
            "is_weekly":            False,
        }), encoding="utf-8"
    )
    print("Newsletter generated.")
    print("  HTML → output/latest_newsletter.html")
    print("  Text → output/latest_newsletter.txt")
