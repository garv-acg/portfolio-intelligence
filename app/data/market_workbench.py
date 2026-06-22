
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any
import pandas as pd
import requests

SECTOR_MAP = {
    "AAPL": "Information Technology", "MSFT": "Information Technology", "NVDA": "Information Technology", "AVGO": "Information Technology",
    "AMZN": "Consumer Discretionary", "TSLA": "Consumer Discretionary", "SPOT": "Communication Services",
    "GOOGL": "Communication Services", "GOOG": "Communication Services", "META": "Communication Services",
    "GE": "Industrials", "JPM": "Financials", "BAC": "Financials", "XOM": "Energy", "CVX": "Energy",
}
SECTOR_ETFS = {
    "Information Technology": "XLK", "Communication Services": "XLC", "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP", "Financials": "XLF", "Health Care": "XLV", "Industrials": "XLI",
    "Energy": "XLE", "Utilities": "XLU", "Materials": "XLB", "Real Estate": "XLRE",
}
MACRO_TICKERS = {"SPY": "SPY", "QQQ": "QQQ", "10Y Yield Proxy": "^TNX", "Oil": "CL=F", "Dollar": "DX-Y.NYB", "VIX": "^VIX", "Gold": "GC=F"}

def _get(x: Any, key: str, default=None):
    return x.get(key, default) if isinstance(x, dict) else getattr(x, key, default)

def _chart(ticker: str, days: int = 400) -> pd.DataFrame:
    end = int(datetime.now(timezone.utc).timestamp())
    start = int((datetime.now(timezone.utc) - timedelta(days=days+10)).timestamp())
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
            params={"period1": start, "period2": end, "interval": "1d", "events": "history"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12,
        )
        r.raise_for_status()
        result = r.json().get("chart", {}).get("result", [])
        if not result:
            return pd.DataFrame()
        p = result[0]
        q = p.get("indicators", {}).get("quote", [{}])[0]
        df = pd.DataFrame({
            "date": pd.to_datetime(p.get("timestamp", []), unit="s", utc=True).normalize(),
            "close": q.get("close", []),
            "volume": q.get("volume", []),
        })
        return df.dropna(subset=["close"]).set_index("date").sort_index().tail(days)
    except Exception:
        return pd.DataFrame()

def _summary(ticker: str) -> dict[str, Any]:
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}",
            params={"modules": "assetProfile,summaryDetail,price,defaultKeyStatistics"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12,
        )
        r.raise_for_status()
        result = r.json().get("quoteSummary", {}).get("result", [])
        if not result:
            return {}
        root = result[0]
        prof = root.get("assetProfile", {}) or {}
        summ = root.get("summaryDetail", {}) or {}
        price = root.get("price", {}) or {}
        stats = root.get("defaultKeyStatistics", {}) or {}
        def raw(obj, key):
            v = obj.get(key)
            return v.get("raw") if isinstance(v, dict) else v
        return {
            "sector": prof.get("sector"),
            "country": prof.get("country"),
            "beta": raw(summ, "beta"),
            "forward_pe": raw(summ, "forwardPE"),
            "trailing_pe": raw(summ, "trailingPE"),
            "market_cap": raw(price, "marketCap"),
            "price_to_book": raw(stats, "priceToBook"),
        }
    except Exception:
        return {}

def _pct(s: pd.Series, n: int):
    try:
        if len(s) <= n:
            return None
        return float((s.iloc[-1] / s.iloc[-n-1] - 1) * 100)
    except Exception:
        return None

def _dist_high(s: pd.Series, n: int):
    try:
        high = s.tail(n).max()
        return float((s.iloc[-1] / high - 1) * 100) if high > 0 else None
    except Exception:
        return None

def _vol_ratio(df: pd.DataFrame):
    try:
        v = df["volume"].dropna()
        avg = v.tail(30).mean()
        return float(v.iloc[-1] / avg) if avg > 0 else None
    except Exception:
        return None

def _cap_tier(cap):
    try:
        cap = float(cap)
    except Exception:
        return "Unknown"
    if cap >= 200_000_000_000: return "Mega Cap"
    if cap >= 10_000_000_000: return "Large Cap"
    if cap >= 2_000_000_000: return "Mid Cap"
    return "Small Cap"

def _style(pe):
    try:
        pe = float(pe)
    except Exception:
        return "Unknown"
    if pe >= 30: return "Growth"
    if pe <= 18: return "Value"
    return "Blend"

def _region(country):
    if not country: return "Unknown"
    return "United States" if str(country).lower() in {"united states", "usa", "united states of america"} else "International"

def catalyst_calendar(tickers, earnings=None, sec_filings=None, days=14):
    rows, today = [], datetime.now().date()
    end = today + timedelta(days=days)
    for e in earnings or []:
        ticker, date_raw = str(_get(e, "ticker", "")).upper(), _get(e, "date")
        try: d = datetime.fromisoformat(str(date_raw)[:10]).date()
        except Exception: continue
        if today <= d <= end:
            rows.append({"Date": d.isoformat(), "Ticker": ticker, "Event Type": "Earnings", "Source": _get(e, "source", "Earnings Calendar"), "Details": f"In {(d-today).days} day(s)"})
    for f in sec_filings or []:
        rows.append({"Date": str(_get(f, "filing_date", _get(f, "accepted_at", today.isoformat())))[:10], "Ticker": str(_get(f, "ticker", "")).upper(), "Event Type": f"SEC {_get(f, 'form_type', '')}", "Source": "SEC EDGAR", "Details": _get(f, "signal_summary", _get(f, "signal_type", ""))})
    for name in ["CPI", "FOMC", "Jobs Report"]:
        rows.append({"Date": "Official calendar", "Ticker": "Market", "Event Type": name, "Source": "Official release calendar", "Details": "Add official calendar connector later"})
    return rows

def sec_diff(sec_filings=None):
    rows = []
    for f in sec_filings or []:
        text = " ".join([str(_get(f, "signal_summary", "")), str(_get(f, "signal_type", "")), " ".join(_get(f, "items_detected", []) or [])]).lower()
        flags = []
        if "risk" in text: flags.append("Risk language present")
        if "repurchase" in text or "buyback" in text: flags.append("Share repurchase language present")
        if "guidance" in text or "outlook" in text: flags.append("Guidance/outlook language present")
        if "5.02" in text or "executive" in text or "director" in text: flags.append("Executive/governance disclosure present")
        rows.append({"Ticker": str(_get(f, "ticker", "")).upper(), "Form": _get(f, "form_type", ""), "Items": ", ".join(_get(f, "items_detected", []) or []) or "None extracted", "Tracked Language": "; ".join(flags) or "No tracked category detected", "Summary": _get(f, "signal_summary", "")})
    return rows

def watchlist_monitor(watchlist, earnings=None, sec_filings=None, benchmark="SPY"):
    spy = _chart(benchmark, 120)
    spy21 = _pct(spy["close"], 21) if not spy.empty else None
    earn = {}
    today = datetime.now().date()
    for e in earnings or []:
        try:
            d = datetime.fromisoformat(str(_get(e, "date"))[:10]).date()
            if d >= today: earn[str(_get(e, "ticker", "")).upper()] = f"{(d-today).days} day(s)"
        except Exception: pass
    sec = {str(_get(f, "ticker", "")).upper(): _get(f, "form_type", "Recent filing") for f in sec_filings or []}
    rows = []
    for ticker in [x.upper().strip() for x in watchlist if x.strip()]:
        df = _chart(ticker, 400)
        close = df["close"] if not df.empty else pd.Series(dtype=float)
        q = _summary(ticker)
        monthly = _pct(close, 21)
        rows.append({"Ticker": ticker, "Latest Price ($)": float(close.iloc[-1]) if not close.empty else None, "Weekly Move (%)": _pct(close, 5), "Monthly Move (%)": monthly, "Relative Strength vs SPY 21D (%)": monthly - spy21 if monthly is not None and spy21 is not None else None, "Distance from 52W High (%)": _dist_high(close, 252), "Volume vs 30D Avg (x)": _vol_ratio(df), "Forward P/E": q.get("forward_pe"), "Trailing P/E": q.get("trailing_pe"), "Earnings Proximity": earn.get(ticker, "None found"), "Recent SEC Filing": sec.get(ticker, "None found")})
    return rows

def portfolio_drift(holdings, target_weights=None):
    vals = []
    for h in holdings:
        ticker = str(_get(h, "ticker", "")).upper()
        shares = float(_get(h, "shares", 0) or 0)
        df = _chart(ticker, 30)
        price = float(df["close"].iloc[-1]) if not df.empty else 0
        vals.append((ticker, shares * price))
    total = sum(v for _, v in vals) or 1
    n = len(vals) or 1
    rows = []
    for ticker, value in vals:
        current = value / total * 100
        target = float(target_weights[ticker]) * 100 if target_weights and ticker in target_weights else 100 / n
        rows.append({"Ticker": ticker, "Current Weight (%)": current, "Target Weight (%)": target, "Drift (%)": current - target, "Current Value ($)": value})
    return sorted(rows, key=lambda r: abs(r["Drift (%)"]), reverse=True)

def macro_dashboard():
    indicators = []
    for label, ticker in MACRO_TICKERS.items():
        df = _chart(ticker, 120)
        close = df["close"] if not df.empty else pd.Series(dtype=float)
        indicators.append({"Indicator": label, "Ticker": ticker, "Latest": float(close.iloc[-1]) if not close.empty else None, "Daily Change (%)": _pct(close, 1), "Weekly Change (%)": _pct(close, 5), "Monthly Change (%)": _pct(close, 21)})
    sectors = []
    for sector, etf in SECTOR_ETFS.items():
        df = _chart(etf, 120)
        close = df["close"] if not df.empty else pd.Series(dtype=float)
        sectors.append({"Sector": sector, "ETF": etf, "Weekly Move (%)": _pct(close, 5), "Monthly Move (%)": _pct(close, 21)})
    sectors = sorted(sectors, key=lambda x: x["Weekly Move (%)"] if x["Weekly Move (%)"] is not None else -999, reverse=True)
    missing = [{"Item": "CPI actual vs expected", "Status": "Official calendar/provider not connected"}, {"Item": "Fed funds probability", "Status": "CME/rates provider not connected"}, {"Item": "Market breadth", "Status": "Breadth provider not connected"}]
    return {"Indicators": indicators, "Sector Leadership": sectors, "Not Yet Connected": missing}

def exposure_dashboard(holdings):
    rows = []
    for h in holdings:
        ticker = str(_get(h, "ticker", "")).upper()
        shares = float(_get(h, "shares", 0) or 0)
        df = _chart(ticker, 30)
        q = _summary(ticker)
        price = float(df["close"].iloc[-1]) if not df.empty else 0
        sector = q.get("sector") or SECTOR_MAP.get(ticker, "Other")
        cap = q.get("market_cap")
        pe = q.get("forward_pe")
        value = shares * price
        rows.append({"Ticker": ticker, "Sector": sector, "Market Value ($)": value, "Market Cap Tier": _cap_tier(cap), "Growth / Value": _style(pe), "Beta": q.get("beta") or 1.0, "Region": _region(q.get("country"))})
    df = pd.DataFrame(rows)
    if df.empty: return {}
    total = df["Market Value ($)"].sum() or 1
    return {
        "Total Value ($)": float(total),
        "Largest Position (%)": float(df["Market Value ($)"].max() / total * 100),
        "Top 3 Concentration (%)": float(df.sort_values("Market Value ($)", ascending=False).head(3)["Market Value ($)"].sum() / total * 100),
        "Portfolio Beta": float((df["Market Value ($)"] / total * df["Beta"].astype(float)).sum()),
        "Sector Exposure": df.groupby("Sector", as_index=False)["Market Value ($)"].sum().assign(**{"Weight (%)": lambda x: x["Market Value ($)"] / total * 100}).to_dict("records"),
        "Market Cap Exposure": df.groupby("Market Cap Tier", as_index=False)["Market Value ($)"].sum().assign(**{"Weight (%)": lambda x: x["Market Value ($)"] / total * 100}).to_dict("records"),
        "Style Exposure": df.groupby("Growth / Value", as_index=False)["Market Value ($)"].sum().assign(**{"Weight (%)": lambda x: x["Market Value ($)"] / total * 100}).to_dict("records"),
        "Region Exposure": df.groupby("Region", as_index=False)["Market Value ($)"].sum().assign(**{"Weight (%)": lambda x: x["Market Value ($)"] / total * 100}).to_dict("records"),
    }
