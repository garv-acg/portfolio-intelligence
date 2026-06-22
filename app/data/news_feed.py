from __future__ import annotations

from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse
import html
import xml.etree.ElementTree as ET

import requests


SOURCE_RANKS = {
    "Reuters": 100,
    "Associated Press": 96,
    "AP News": 96,
    "SEC": 96,
    "Federal Reserve": 96,
    "BLS": 96,
    "BEA": 96,
    "CNBC": 92,
    "Financial Times": 92,
    "The Wall Street Journal": 92,
    "Bloomberg": 92,
    "Nikkei Asia": 90,
    "The Economist": 90,
    "Barron's": 88,
    "MarketWatch": 84,
    "Yahoo Finance": 82,
    "Investing.com": 78,
    "Morningstar": 78,
    "S&P Global": 78,
    "The Economic Times": 76,
    "U.S. Bank": 74,
    "Morgan Stanley": 74,
    "Deloitte": 72,
    "The World Economic Forum": 70,
    "Anadolu Ajansı": 66,
    "Mexico Business News": 62,
}

DOMAIN_SOURCE_MAP = {
    "reuters.com": "Reuters",
    "apnews.com": "Associated Press",
    "cnbc.com": "CNBC",
    "ft.com": "Financial Times",
    "wsj.com": "The Wall Street Journal",
    "bloomberg.com": "Bloomberg",
    "barrons.com": "Barron's",
    "marketwatch.com": "MarketWatch",
    "finance.yahoo.com": "Yahoo Finance",
    "investing.com": "Investing.com",
    "morningstar.com": "Morningstar",
    "spglobal.com": "S&P Global",
    "federalreserve.gov": "Federal Reserve",
    "bls.gov": "BLS",
    "bea.gov": "BEA",
    "sec.gov": "SEC",
    "nikkei.com": "Nikkei Asia",
    "economist.com": "The Economist",
}

BLOCKED_SOURCES = {
    "Motley Fool", "The Motley Fool", "Zacks", "InvestorPlace", "Benzinga",
    "Seeking Alpha", "TheStreet", "247 Wall St.", "GuruFocus", "TipRanks",
    # Low-quality / unverified sources seen in feeds
    "Mshale", "Stock Titan", "simplywall.st", "Simply Wall St", "Let's Data Science",
    "MarketBeat", "StockAnalysis", "Stockanalysis", "Finbold", "Finviz",
    "The Fly", "Fly on the Wall", "MT Newswires", "Newsfilter", "GlobeNewswire",
    "PR Newswire", "Business Wire", "EIN Presswire", "AccessWire",
    "MSN", "AOL Finance", "24/7 Wall St",
}

BLOCKED_TERMS = [
    "should you buy",
    "should i buy",
    "stocks to buy",
    "buy these stocks",
    "market crash:",
    "without hesitation",
    "if you'd invested",
    "what you'd have today",
    "how much you'd need",
    "millionaire maker",
    "passive income",
    "generate $",
    "dividend stock",
    "dividend growth",
    "price target",
    "analyst",
    "rating",
    "upgrade",
    "downgrade",
    "bullish",
    "bearish",
    "underrated",
    "overrated",
    "red hot",
    "not touching",
    "fails to impress",
    "what you need to know",
    "here's why",
    "here's how",
    "is a buy",
    "is it a buy",
    "better buy",
    "trending stock",
    "show up in your portfolio",
    "trillion-dollar etf",
    "becomes the",
    "elon musk",
    "week ahead",
    "what to watch",
    "things to know",
    "morning briefing",
    "pre-bell",
    "market wrap",
    "market rally",
    "wall st week",
    "when will",
    "should investors",
    "time to buy",
    "time to sell",
    "jim cramer",
    "ken griffin",
    "in his portfolio",
    "top stock in",
    "top ai stock",
    "some facts to",
    "some facts about",
    "more room to run",
    "is it worth",
    "valuation debate",
    "valuation story",
    "which bet is",
    "feeds aws growth",
    "china shock",
    "trading in a range",
    "sets direction toward",
    "quick return",
    "path ahead",
    "what's the path",
    "priciest ai model",
    "anthropic",

    "respond to second",
    "spacex ipo",
    "trillion-dollar",
    "buys shares of",
    "sees a more significant dip",
    "ascends while market",
    "may shape",
    "investor perception",
    # Additional patterns seen in feeds
    "elevate its brand",
    "brand narrative",
    "ai strategy deepens",
    "still undervalued",
    "trading up today",
    "trading down today",
    "stock is trading",
    "stock slides as market",
    "facts to know before you trade",
    "harvard university",
    "university ai stock",
    "stock picks",
    "investment ideas feature",
    "seller sprite",
    "growth intelligence toolkit",
    "for sellers facing",
    "declines following",
    "surges following",
    "rises following",
    "drops following",
    "falls following",
    "zacks",
    "motley",
    "seeking alpha",
    "shapes investor",
    "could shape",
    "reframes long term",
    "reframes the",
    "adds new layer",
    # Valuation / opinion patterns
    "a good stock to buy",
    "good stock to buy",
    "valuation after",
    "pricing reflect",
    "share price volatility",
    "reflect its",
    "recent share performance",
    "streaming expansion",
    "a look at",
    "after recent",
    "is pricing",
    "stock to buy now",
    "worth buying",
    "worth watching",
    "is it the right",
    "now a good time",
    "overvalued or undervalued",
    "fairly valued",
]

# ── Recency windows ────────────────────────────────────────────────────────────
# Company news: only articles from last 3 days shown in the newsletter.
# A wider fallback window (7 days) is used if nothing is found in 3 days.
COMPANY_NEWS_PRIMARY_DAYS = 3
COMPANY_NEWS_FALLBACK_DAYS = 7

# Global developments: 7 days primary, 14 days fallback.
GLOBAL_NEWS_PRIMARY_DAYS = 7
GLOBAL_NEWS_FALLBACK_DAYS = 14

# Headline of the day: must be from last 2 days to be surfaced as "biggest".
HEADLINE_MAX_DAYS = 2


def _fix_encoding(text: str) -> str:
    if not isinstance(text, str):
        return text
    # First: fix double-encoded smart quotes BEFORE latin1 roundtrip destroys them
    second_pass = [
        ("â€˜", "‘"),
        ("â€™", "’"),
        ("â€œ", "“"),
        ("â€”", "”"),
        ("â€“", "–"),
        ("â€„", "—"),
    ]
    for bad, good in second_pass:
        text = text.replace(bad, good)
    # Then: byte-level replacements
    replacements = {
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
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    # Finally: latin1 roundtrip for any remaining garbled sequences
    try:
        if "â" in text or "Ã" in text:
            text = text.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
    except Exception:
        pass
    return text

def _domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _source_from_domain(url: str) -> str | None:
    domain = _domain_from_url(url)
    for known_domain, source in DOMAIN_SOURCE_MAP.items():
        if known_domain in domain:
            return source
    return None


def source_rank(source: str) -> int:
    return SOURCE_RANKS.get(source or "", 0)


def _clean_source(title: str, source: str, link: str = "") -> str:
    domain_source = _source_from_domain(link)
    if domain_source:
        return domain_source
    if source and source != "RSS":
        return source.strip()
    if " - " in title:
        possible = title.rsplit(" - ", 1)[-1].strip()
        if 2 <= len(possible) <= 80:
            return possible
    return "Unknown"


def _is_quality_headline(title: str, source: str, link: str = "") -> bool:
    low = title.lower().strip()
    src = source.strip()

    if len(low) < 18:
        return False
    if src in BLOCKED_SOURCES:
        return False
    if any(term in low for term in BLOCKED_TERMS):
        return False

    rank = source_rank(src)
    # Unknown sources (rank == 0) are blocked entirely.
    # Only recognised sources with rank >= 74 pass through.
    if rank == 0:
        return False
    return rank >= 74


def _is_recent_enough(published: str, max_age_days: int) -> bool:
    from datetime import datetime, timezone, timedelta
    try:
        dt = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= datetime.now(timezone.utc) - timedelta(days=max_age_days)
    except Exception:
        return True


def _fetch_rss(url: str, limit: int = 10) -> list[dict[str, Any]]:
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        rows = []
        for item in root.findall(".//item")[: limit * 5]:
            raw_title = _fix_encoding(html.unescape(item.findtext("title", default="").strip()))
            link      = item.findtext("link", default="").strip()
            pub_date  = item.findtext("pubDate", default="").strip()
            raw_source = item.findtext("source", default="").strip()
            source = _clean_source(raw_title, raw_source, link)
            if not raw_title or not _is_quality_headline(raw_title, source, link):
                continue
            try:
                published = parsedate_to_datetime(pub_date).astimezone(timezone.utc).isoformat()
            except Exception:
                published = pub_date
            rows.append({
                "title":       raw_title,
                "link":        link,
                "published":   published,
                "source":      source,
                "source_rank": source_rank(source),
            })
            if len(rows) >= limit:
                break
        rows.sort(key=lambda r: (r.get("source_rank", 0), r.get("published", "")), reverse=True)
        return rows
    except Exception:
        return []


# ── Company news ───────────────────────────────────────────────────────────────

TICKER_COMPANY_TERMS = {
    "SPOT": ["spotify", "spot"],
    "AVGO": ["broadcom", "avgo"],
    "AAPL": ["apple", "aapl"],
    "GE":   ["ge aerospace", "general electric", " ge "],
    "AMZN": ["amazon", "amzn"],
    "NVDA": ["nvidia", "nvda"],
}


def _matches_ticker(title: str, ticker: str) -> bool:
    low   = f" {title.lower()} "
    terms = TICKER_COMPANY_TERMS.get(ticker.upper().strip(), [ticker.lower()])
    return any(term.lower() in low for term in terms)


def company_news(tickers: list[str], per_ticker: int = 3) -> list[dict[str, Any]]:
    """
    Returns recent company news for each ticker.
    Primary window: last 3 days.
    Fallback window: last 7 days (used only if nothing found in 3 days).
    """
    rows = []

    for ticker in tickers:
        ticker = ticker.upper().strip()
        if not ticker:
            continue

        terms     = TICKER_COMPANY_TERMS.get(ticker, [ticker.lower()])
        main_term = terms[0].replace(" ", "+")

        feeds = [
            f"https://news.google.com/rss/search?q={main_term}+earnings+revenue+deal+contract+filing+when:3d&hl=en-US&gl=US&ceid=US:en",
            f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US",
        ]

        ticker_rows = []
        for feed in feeds:
            ticker_rows.extend(_fetch_rss(feed, limit=per_ticker * 6))

        # Try primary window first, fall back to wider window if empty
        for max_days in [COMPANY_NEWS_PRIMARY_DAYS, COMPANY_NEWS_FALLBACK_DAYS]:
            seen, selected = set(), []
            for row in sorted(ticker_rows, key=lambda r: r.get("published", ""), reverse=True):
                title     = row.get("title", "")
                published = row.get("published", "")
                if title in seen:
                    continue
                if not _matches_ticker(title, ticker):
                    continue
                if not _is_recent_enough(published, max_age_days=max_days):
                    continue
                seen.add(title)
                row["ticker"] = ticker
                selected.append(row)
                if len(selected) >= per_ticker:
                    break
            if selected:
                rows.extend(selected)
                break  # don't fall through to wider window if we found results

    return rows


# ── Market news ────────────────────────────────────────────────────────────────

def market_news(limit: int = 8) -> list[dict[str, Any]]:
    feeds = [
        # Wire-source specific queries get priority
        "https://news.google.com/rss/search?q=Reuters+markets+stocks+S%26P+500+Nasdaq+when:2d&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=CNBC+markets+stocks+Treasury+yields+Fed+when:2d&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=stock+market+S%26P+500+Treasury+yields+when:2d&hl=en-US&gl=US&ceid=US:en",
    ]
    rows = []
    for feed in feeds:
        rows.extend(_fetch_rss(feed, limit=limit))
    seen, out = set(), []
    for row in sorted(rows, key=lambda r: (r.get("source_rank", 0), r.get("published", "")), reverse=True):
        title = row.get("title")
        if title in seen:
            continue
        seen.add(title)
        out.append(row)
        if len(out) >= limit:
            break
    return out


# ── Global developments ────────────────────────────────────────────────────────

GLOBAL_TOPICS = {
    "China":               "Reuters China economy markets yuan exports stocks",
    "Semiconductors":      "Reuters semiconductors chips Nvidia TSMC AI export controls",
    "Oil / Energy":        "Reuters oil energy OPEC crude natural gas markets",
    "Geopolitics":         "Reuters geopolitics markets trade tariffs war",
    "Europe / EU":         "Reuters Europe EU economy ECB markets",
    "Rates / Central Banks": "Reuters central banks rates inflation bonds markets",
}


def global_development_news(limit: int = 8) -> list[dict[str, Any]]:
    """
    Returns the most recent global development headlines.
    Primary window: last 7 days.
    Fallback window: last 14 days.
    """
    rows = []
    per_topic = max(1, limit // len(GLOBAL_TOPICS))

    for category, query in GLOBAL_TOPICS.items():
        feed       = f"https://news.google.com/rss/search?q={query}+when:7d&hl=en-US&gl=US&ceid=US:en"
        topic_rows = _fetch_rss(feed, limit=per_topic * 3)

        for max_days in [GLOBAL_NEWS_PRIMARY_DAYS, GLOBAL_NEWS_FALLBACK_DAYS]:
            recent = [
                r for r in topic_rows
                if _is_recent_enough(r.get("published", ""), max_age_days=max_days)
            ]
            if recent:
                for r in recent[:per_topic]:
                    r["category"] = category
                rows.extend(recent[:per_topic])
                break
        else:
            # If nothing within fallback, include most recent regardless
            for r in topic_rows[:per_topic]:
                r["category"] = category
            rows.extend(topic_rows[:per_topic])

    seen, out = set(), []
    for row in sorted(rows, key=lambda r: r.get("published", ""), reverse=True):
        title = row.get("title")
        if title in seen:
            continue
        seen.add(title)
        out.append(row)
        if len(out) >= limit:
            break
    return out


# ── Biggest headline ───────────────────────────────────────────────────────────

def biggest_headline(
    company_rows: list[dict[str, Any]],
    market_rows:  list[dict[str, Any]],
) -> str:
    """
    Returns the top headline from the highest-ranked source.
    Prefers articles from last 2 days; falls back to any available.
    """
    all_rows = company_rows + market_rows

    # Prefer recent
    recent = [r for r in all_rows if _is_recent_enough(r.get("published", ""), HEADLINE_MAX_DAYS)]
    pool   = recent if recent else all_rows

    ranked = sorted(pool, key=lambda r: (r.get("source_rank", 0), r.get("published", "")), reverse=True)
    if ranked:
        first  = ranked[0]
        prefix = f"{first.get('ticker')}: " if first.get("ticker") else ""
        return f"{prefix}{first.get('title', '')}"

    return "No major headline found from approved sources."