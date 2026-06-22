from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote_plus, urlparse

import requests


@dataclass(frozen=True)
class Article:
    ticker: str | None
    title: str
    source: str
    url: str
    published_at: str | None = None
    description: str | None = None
    relevance_score: int = 0
    confidence: str = "Low"
    source_tier: str = "Tier 3"
    reason: str | None = None


COMPANY_ALIASES: dict[str, list[str]] = {
    "AAPL": ["AAPL", "Apple"],
    "MSFT": ["MSFT", "Microsoft"],
    "NVDA": ["NVDA", "Nvidia", "NVIDIA"],
    "AMZN": ["AMZN", "Amazon"],
    "GOOGL": ["GOOGL", "GOOG", "Alphabet", "Google"],
    "GOOG": ["GOOG", "GOOGL", "Alphabet", "Google"],
    "META": ["META", "Meta", "Facebook"],
    "TSLA": ["TSLA", "Tesla"],
    "SPOT": ["SPOT", "Spotify"],
    "AVGO": ["AVGO", "Broadcom"],
    "GE": ["GE", "GE Aerospace", "General Electric"],
}

TIER_1_DOMAINS = [
    "reuters.com",
    "bloomberg.com",
    "wsj.com",
    "ft.com",
    "sec.gov",
    "investor.",
    "ir.",
]

TIER_2_DOMAINS = [
    "finance.yahoo.com",
    "cnbc.com",
    "marketwatch.com",
    "barrons.com",
    "apnews.com",
]

TIER_3_DOMAINS = [
    "fool.com",
    "zacks.com",
    "investorplace.com",
    "insidermonkey.com",
    "stockstory.org",
    "simplywall.st",
    "benzinga.com",
]

BLOCKED_PUBLISHERS = [
    "zacks",
    "insidermonkey",
    "investorplace",
    "fool",
    "benzinga",
    "stockstory",
    "simplywall",
]

GOSSIP_TERMS = [
    "besties",
    "rivals",
    "feud",
    "drama",
    "battle",
    "clash",
    "fight",
]

POLITICAL_DISCLOSURE_TERMS = [
    "trading disclosure",
    "financial disclosure",
    "activity in",
    "stock trades",
    "portfolio disclosure",
]

HIGH_SIGNAL_TERMS = {
    "earnings": 34,
    "guidance": 32,
    "revenue": 18,
    "profit": 16,
    "eps": 16,
    "sec": 32,
    "filing": 32,
    "10-k": 32,
    "10-q": 32,
    "8-k": 36,
    "investor day": 30,
    "annual meeting": 18,
    "product": 20,
    "launch": 20,
    "unveils": 18,
    "partnership": 20,
    "contract": 18,
    "order": 16,
    "regulator": 34,
    "regulatory": 34,
    "antitrust": 34,
    "lawsuit": 28,
    "settlement": 28,
    "investigation": 28,
    "merger": 34,
    "acquisition": 34,
    "acquires": 34,
    "deal": 20,
    "ceo": 24,
    "cfo": 24,
    "management": 18,
    "resigns": 22,
    "appointed": 18,
    "buyback": 24,
    "dividend": 22,
    "forecast": 16,
    "outlook": 16,
    "data center": 22,
    "chip": 12,
    "semiconductor": 14,
    "ai infrastructure": 20,
}

SOFT_SIGNAL_TERMS = {
    "ai": 4,
    "cloud": 4,
    "valuation": 2,
    "fair value": 2,
    "stock": 1,
    "shares": 1,
}

ANALYST_TERMS = [
    "raises pt",
    "lowers pt",
    "price target",
    "keeps a buy",
    "keeps buy",
    "keeps overweight",
    "upgrade",
    "downgrade",
    "analyst",
    "td cowen",
    "morgan stanley",
    "goldman",
    "ubs",
    "jpmorgan",
    "bank of america",
    "bofa",
    "wedbush",
    "piper sandler",
    "cantor",
]

HARD_BLOCK_PATTERNS = [
    r"\bmarket chatter\b",
    r"\bdeclines more than market\b",
    r"\boutperforms market\b",
    r"\bunderperforms market\b",
    r"\bwhy .* stock is up today\b",
    r"\bwhy .* stock is down today\b",
    r"\bwhy .* stock is trading\b",
    r"\bforget .*\b",
    r"\bstock of the day\b",
    r"\bbuy now\b",
    r"\bbest .*stocks?\b",
    r"\bstocks? to buy\b",
    r"\bfastest growing\b",
    r"\btoo late to consider\b",
    r"\bwhat .* thinks\b",
    r"\bjim cramer\b",
    r"\bmark cuban\b",
    r"\bbullish in ai era\b",
    r"\bshares? skyrocket\b",
    r"\bcrushed it\b",
    r"\bwhat you need to know\b",
    r"\bwatchlist\b",
    r"\bfacing headwinds\b",
    r"\brecent share price slide\b",
    r"\btop analyst reports\b",
    r"\bbetter buy\b",
    r"\bbond fund\b",
    r"\bcrypto etf\b",
    r"\bvaluation as .*\b",
    r"\babove fair value\b",
    r"\btests valuation\b",
    r"\bwall street thinks\b",
]

WEAK_HEADLINE_PATTERNS = [
    r"\bdeclines\b",
    r"\brall(y|ies)\b",
    r"\bslips\b",
    r"\bgains\b",
    r"\bjumps\b",
    r"\bfalls\b",
    r"\btrading higher\b",
    r"\btrading lower\b",
    r"\bprice target\b",
    r"\braises pt\b",
    r"\blowers pt\b",
    r"\bkeeps a buy\b",
    r"\bkeeps buy\b",
]


def _clean(value: str | None) -> str:
    if not value:
        return ""
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except Exception:
        return value


def _is_recent(published_at: str | None, lookback_hours: int) -> bool:
    if not published_at:
        return True
    try:
        ts = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts >= datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    except Exception:
        return True


def _aliases(ticker: str) -> list[str]:
    return COMPANY_ALIASES.get(ticker.upper(), [ticker.upper()])


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _source_tier(source: str, url: str) -> str:
    combined = f"{source} {_domain(url)} {url}".lower()

    if any(domain in combined for domain in TIER_1_DOMAINS):
        return "Tier 1"
    if any(domain in combined for domain in TIER_2_DOMAINS):
        return "Tier 2"
    return "Tier 3"


def _has_exact_ticker(title: str, ticker: str) -> bool:
    return bool(re.search(rf"\b{re.escape(ticker.upper())}\b", title.upper()))


def _has_company(title: str, description: str, ticker: str) -> bool:
    combined = f"{title} {description}".lower()
    for alias in _aliases(ticker):
        alias_l = alias.lower()
        if len(alias_l) <= 2:
            if re.search(rf"\b{re.escape(alias_l)}\b", combined):
                return True
        elif alias_l in combined:
            return True
    return False


def _matches_any(patterns: list[str], text: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _score(ticker: str, title: str, description: str, source: str, url: str) -> tuple[int, str, str, str, bool]:
    title_l = title.lower()
    combined = f"{title} {description}".lower()
    combined_source = f"{source} {url}".lower()

    reasons: list[str] = []
    score = 0
    reject = False

    if any(pub in combined_source for pub in BLOCKED_PUBLISHERS):
        reject = True
        reasons.append("blocked low-signal publisher")

    if "market chatter" in combined:
        reject = True
        reasons.append("blocked market chatter rumor")

    tier = _source_tier(source, url)

    if tier == "Tier 1":
        score += 28
        reasons.append("tier 1 source")
    elif tier == "Tier 2":
        score += 8
        reasons.append("tier 2 source")
    else:
        score -= 18
        reasons.append("tier 3 source")

    if any(domain in combined_source for domain in TIER_3_DOMAINS):
        score -= 75
        reasons.append("tier 3 publisher penalty")

    if _has_exact_ticker(title, ticker):
        score += 28
        reasons.append("ticker in headline")

    for alias in _aliases(ticker):
        alias_l = alias.lower()
        if len(alias_l) > 2 and alias_l in title_l:
            score += 24
            reasons.append("company in headline")
            break

    if _has_company(title, description, ticker):
        score += 8
        reasons.append("company referenced")

    high_signal_hits = 0

    for term, weight in HIGH_SIGNAL_TERMS.items():
        if term in combined:
            score += weight
            high_signal_hits += 1
            reasons.append(term)

    for term, weight in SOFT_SIGNAL_TERMS.items():
        if term in combined:
            score += weight
            reasons.append(term)

    if any(term in combined for term in POLITICAL_DISCLOSURE_TERMS):
        score -= 45
        reasons.append("political disclosure penalty")
        if high_signal_hits == 0:
            score = min(score, 34)

    if _matches_any(HARD_BLOCK_PATTERNS, combined):
        if not any(term in combined for term in [
            "earnings",
            "guidance",
            "sec",
            "8-k",
            "lawsuit",
            "settlement",
            "regulatory",
            "antitrust",
            "merger",
            "acquisition",
            "investor day",
            "product launch",
            "partnership",
            "ceo",
            "cfo",
        ]):
            reject = True
            reasons.append("hard retail-filler block")
        else:
            score -= 45
            reasons.append("retail-filler penalty")

    if _matches_any(WEAK_HEADLINE_PATTERNS, title_l) and high_signal_hits == 0:
        reject = True
        reasons.append("weak price-action headline without hard-news signal")

    if any(term in combined for term in ANALYST_TERMS):
        score -= 45
        reasons.append("analyst chatter penalty")
        if high_signal_hits == 0:
            score = min(score, 34)

    if "valuation" in combined and high_signal_hits == 0:
        score -= 35
        reasons.append("valuation opinion penalty")

    if re.search(r"\b\d+\s+more\b", title_l):
        score -= 60
        reasons.append("multi-ticker roundup penalty")

    if " and " in title_l:
        score -= 15
        reasons.append("multi-company article penalty")

    if any(term in combined for term in GOSSIP_TERMS):
        score -= 50
        reasons.append("founder-drama / gossip penalty")

    if tier == "Tier 3":
        score = min(score, 34)

    if score >= 60:
        confidence = "High"
    elif score >= 38:
        confidence = "Medium"
    else:
        confidence = "Low"

    if tier == "Tier 3" and confidence == "High":
        confidence = "Medium"

    return score, confidence, tier, ", ".join(dict.fromkeys(reasons)), reject


def _fetch_yahoo_rss(ticker: str, lookback_hours: int) -> list[Article]:
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={quote_plus(ticker)}&region=US&lang=en-US"
    out: list[Article] = []

    try:
        response = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )

        response.raise_for_status()
        root = ET.fromstring(response.text)

        for item in root.findall(".//item"):
            title = _clean(item.findtext("title"))
            link = _clean(item.findtext("link"))
            description = _clean(item.findtext("description"))
            published = _parse_date(item.findtext("pubDate"))
            source = "Yahoo Finance"

            if not title or not link:
                continue

            if not _is_recent(published, lookback_hours):
                continue

            has_headline_match = (
                _has_exact_ticker(title, ticker)
                or any(
                    alias.lower() in title.lower()
                    for alias in _aliases(ticker)
                    if len(alias) > 2
                )
            )

            if not has_headline_match:
                continue

            score, confidence, tier, reason, reject = _score(
                ticker,
                title,
                description,
                source,
                link,
            )

            if reject:
                continue

            if score < 38:
                continue

            out.append(
                Article(
                    ticker=ticker,
                    title=title,
                    source=source,
                    url=link,
                    published_at=published,
                    description=description or None,
                    relevance_score=score,
                    confidence=confidence,
                    source_tier=tier,
                    reason=reason,
                )
            )

    except Exception:
        return []

    return out


def _dedupe(articles: list[Article]) -> list[Article]:
    seen: set[str] = set()
    out: list[Article] = []

    for article in articles:
        key = re.sub(r"\W+", "", article.title.lower())

        if not key or key in seen:
            continue

        seen.add(key)
        out.append(article)

    return out


def get_portfolio_news(
    tickers: list[str],
    max_articles_per_ticker: int = 2,
    newsapi_key: str | None = None,
    lookback_hours: int = 72,
) -> list[Article]:
    results: list[Article] = []

    for raw in tickers:
        ticker = raw.upper().strip()

        articles = _fetch_yahoo_rss(
            ticker,
            lookback_hours,
        )

        articles = _dedupe(articles)

        articles = sorted(
            articles,
            key=lambda a: (
                {"Tier 1": 3, "Tier 2": 2, "Tier 3": 1}.get(a.source_tier, 0),
                a.relevance_score,
                a.published_at or "",
            ),
            reverse=True,
        )

        results.extend(articles[:max_articles_per_ticker])

    return _dedupe(results)


def articles_as_dicts(
    articles: list[Article],
) -> list[dict[str, Any]]:
    return [article.__dict__ for article in articles]
