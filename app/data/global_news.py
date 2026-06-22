from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import requests


@dataclass(frozen=True)
class GlobalDevelopment:
    category: str
    title: str
    source: str
    url: str
    published_at: str | None
    summary: str
    relevance_score: int
    confidence: str
    reason: str


RSS_FEEDS: dict[str, list[dict[str, str]]] = {
    "Fed / Rates": [
        {"source": "Federal Reserve", "url": "https://www.federalreserve.gov/feeds/press_all.xml"},
        {"source": "CNBC Economy", "url": "https://www.cnbc.com/id/20910258/device/rss/rss.html"},
        {"source": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex"},
    ],
    "China": [
        {"source": "CNBC World", "url": "https://www.cnbc.com/id/100727362/device/rss/rss.html"},
        {"source": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex"},
    ],
    "Europe / ECB": [
        {"source": "ECB Press Releases", "url": "https://www.ecb.europa.eu/rss/press.html"},
        {"source": "CNBC World", "url": "https://www.cnbc.com/id/100727362/device/rss/rss.html"},
    ],
    "Geopolitics": [
        {"source": "CNBC World", "url": "https://www.cnbc.com/id/100727362/device/rss/rss.html"},
        {"source": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex"},
    ],
    "Commodities": [
        {"source": "CNBC Markets", "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html"},
        {"source": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex"},
    ],
    "AI / Semiconductors": [
        {"source": "CNBC Technology", "url": "https://www.cnbc.com/id/19854910/device/rss/rss.html"},
        {"source": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex"},
    ],
}


CATEGORY_KEYWORDS: dict[str, dict[str, int]] = {
    "Fed / Rates": {
        "federal reserve": 40,
        "fed": 35,
        "fomc": 35,
        "powell": 30,
        "interest rate": 30,
        "rates": 20,
        "treasury": 20,
        "yield": 18,
        "inflation": 18,
        "cpi": 18,
        "pce": 18,
    },
    "China": {
        "china": 35,
        "beijing": 22,
        "pboc": 25,
        "yuan": 18,
        "tariff": 24,
        "trade": 18,
        "exports": 16,
        "property": 16,
        "stimulus": 20,
    },
    "Europe / ECB": {
        "ecb": 35,
        "european central bank": 35,
        "lagarde": 25,
        "eurozone": 24,
        "europe": 18,
        "germany": 14,
        "france": 14,
        "rates": 16,
        "inflation": 16,
    },
    "Geopolitics": {
        "war": 24,
        "conflict": 22,
        "sanctions": 24,
        "tariff": 24,
        "trade": 18,
        "russia": 18,
        "ukraine": 18,
        "middle east": 18,
        "israel": 16,
        "iran": 18,
        "oil": 12,
        "hormuz": 26,
    },
    "Commodities": {
        "oil": 35,
        "crude": 30,
        "opec": 30,
        "gold": 28,
        "copper": 24,
        "natural gas": 20,
        "commodities": 18,
        "supply": 14,
        "inventory": 14,
        "hormuz": 22,
    },
    "AI / Semiconductors": {
        "ai infrastructure": 40,
        "data center": 34,
        "semiconductor": 34,
        "chip": 28,
        "chips": 28,
        "nvidia": 28,
        "broadcom": 24,
        "amd": 20,
        "tsmc": 20,
        "asml": 20,
        "export controls": 30,
        "gpu": 30,
        "capex": 26,
        "hyperscaler": 24,
        "openai": 10,
        "microsoft": 12,
        "alphabet": 12,
        "amazon": 12,
        "artificial intelligence": 10,
        "ai": 6,
    },
}


GLOBAL_MARKET_TERMS = {
    "markets": 8,
    "stocks": 6,
    "futures": 6,
    "bond": 8,
    "yield": 8,
    "dollar": 8,
    "oil": 8,
    "gold": 8,
    "inflation": 8,
    "growth": 6,
    "recession": 8,
    "earnings": 6,
    "policy": 6,
    "central bank": 10,
}


LOW_SIGNAL_TERMS = [
    "watch live",
    "live updates",
    "what to watch",
    "photos",
    "video",
    "opinion",
    "personal finance",
    "retirement",
    "mortgage",
    "credit card",
    "lottery",
    "sports",
]


GLOBAL_HARD_BLOCK_TERMS = [
    "stocks to buy now",
    "best stocks to buy",
    "best fundamentally strong stocks",
    "buy now",
    "stock picks",
    "top stocks",
    "best ai stocks",
    "stock market week ahead",
    "week ahead",
    "stocks to watch",
    "not too late to buy",
    "own it, don't trade it",
    "own it, dont trade it",
    "jim cramer",
    "mad money",
    "price target",
    "analyst says",
    "wall street says",
    "why this stock",
    "bull case",
    "bear case",
]


GOSSIP_TERMS = [
    "besties",
    "rivals",
    "feud",
    "drama",
    "battle",
    "clash",
    "fight",
    "bitter",
    "court fight",
]


AI_MARKET_STRUCTURE_TERMS = [
    "data center",
    "semiconductor",
    "chip",
    "chips",
    "gpu",
    "capex",
    "hyperscaler",
    "infrastructure",
    "export controls",
    "nvidia",
    "broadcom",
    "amd",
    "tsmc",
    "asml",
    "earnings",
    "guidance",
    "demand",
    "supply",
]


INSTITUTIONAL_AI_TERMS = [
    "earnings",
    "guidance",
    "export controls",
    "data center",
    "gpu",
    "semiconductor",
    "hyperscaler",
    "capex",
    "demand",
    "supply chain",
    "enterprise ai",
    "cloud spending",
    "inference",
    "chip",
    "chips",
]


SOURCE_BOOST = {
    "Federal Reserve": 28,
    "ECB Press Releases": 24,
    "CNBC Markets": 14,
    "CNBC Economy": 14,
    "CNBC World": 12,
    "CNBC Technology": 12,
    "Yahoo Finance": 6,
}


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


def _is_recent(
    published_at: str | None,
    lookback_hours: int,
) -> bool:
    if not published_at:
        return True

    try:
        timestamp = datetime.fromisoformat(
            published_at.replace("Z", "+00:00")
        )

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        return timestamp >= datetime.now(timezone.utc) - timedelta(
            hours=lookback_hours
        )

    except Exception:
        return True


def _fetch_rss(
    source: str,
    url: str,
) -> list[dict[str, Any]]:
    try:
        response = requests.get(
            url,
            timeout=18,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()

        root = ET.fromstring(response.text)
        items: list[dict[str, Any]] = []

        for item in root.findall(".//item"):
            title = _clean(item.findtext("title"))
            link = _clean(item.findtext("link"))
            description = _clean(item.findtext("description"))
            published = _parse_date(item.findtext("pubDate"))

            if title and link:
                items.append(
                    {
                        "source": source,
                        "title": title,
                        "url": link,
                        "summary": description,
                        "published_at": published,
                    }
                )

        # Atom fallback
        if not items:
            namespace = {"atom": "http://www.w3.org/2005/Atom"}

            for entry in root.findall(".//atom:entry", namespace):
                title = _clean(
                    entry.findtext(
                        "atom:title",
                        default="",
                        namespaces=namespace,
                    )
                )

                link_element = entry.find("atom:link", namespace)
                link = (
                    link_element.attrib.get("href", "")
                    if link_element is not None
                    else ""
                )

                summary = _clean(
                    entry.findtext(
                        "atom:summary",
                        default="",
                        namespaces=namespace,
                    )
                )

                published = entry.findtext(
                    "atom:updated",
                    default="",
                    namespaces=namespace,
                )

                if title and link:
                    items.append(
                        {
                            "source": source,
                            "title": title,
                            "url": link,
                            "summary": summary,
                            "published_at": published,
                        }
                    )

        return items

    except Exception:
        return []


def _score_item(
    category: str,
    item: dict[str, Any],
) -> tuple[int, str, str, bool]:
    title = item.get("title", "")
    summary = item.get("summary", "")
    source = item.get("source", "Unknown")

    text = f"{title} {summary}".lower()

    score = SOURCE_BOOST.get(source, 0)
    reasons: list[str] = []
    reject = False

    if score:
        reasons.append(f"{source} source boost")

    if any(term in text for term in GLOBAL_HARD_BLOCK_TERMS):
        reject = True
        reasons.append("retail/investment-commentary suppression")

    for term, weight in CATEGORY_KEYWORDS.get(category, {}).items():
        if term in text:
            score += weight
            reasons.append(term)

    for term, weight in GLOBAL_MARKET_TERMS.items():
        if term in text:
            score += weight

    if any(term in text for term in LOW_SIGNAL_TERMS):
        score -= 25
        reasons.append("low-signal penalty")

    if category == "Fed / Rates" and source == "Federal Reserve":
        score += 20
        reasons.append("official Fed source")

    if category == "Europe / ECB" and source == "ECB Press Releases":
        score += 20
        reasons.append("official ECB source")

    if category == "AI / Semiconductors":
        if any(term in text for term in GOSSIP_TERMS):
            score -= 70
            reasons.append("AI/founder gossip penalty")

        if not any(term in text for term in AI_MARKET_STRUCTURE_TERMS):
            reject = True
            reasons.append("AI item lacked market-structure relevance")

        if not any(term in text for term in INSTITUTIONAL_AI_TERMS):
            reject = True
            reasons.append("AI item lacked institutional catalyst relevance")

    if score >= 55:
        confidence = "High"
    elif score >= 32:
        confidence = "Medium"
    else:
        confidence = "Low"

    return score, confidence, ", ".join(dict.fromkeys(reasons)), reject


def _dedupe(
    items: list[GlobalDevelopment],
) -> list[GlobalDevelopment]:
    seen: set[str] = set()
    out: list[GlobalDevelopment] = []

    for item in items:
        key = re.sub(r"\W+", "", item.title.lower())

        if not key or key in seen:
            continue

        seen.add(key)
        out.append(item)

    return out


def get_global_developments(
    lookback_hours: int = 24,
    max_per_category: int = 1,
) -> list[GlobalDevelopment]:
    results: list[GlobalDevelopment] = []
    effective_lookback = max(lookback_hours, 72)

    for category, feeds in RSS_FEEDS.items():
        candidates: list[GlobalDevelopment] = []

        for feed in feeds:
            raw_items = _fetch_rss(
                feed["source"],
                feed["url"],
            )

            for raw in raw_items:
                if not _is_recent(
                    raw.get("published_at"),
                    effective_lookback,
                ):
                    continue

                score, confidence, reason, reject = _score_item(
                    category,
                    raw,
                )

                if reject or score < 28:
                    continue

                candidates.append(
                    GlobalDevelopment(
                        category=category,
                        title=raw["title"],
                        source=raw["source"],
                        url=raw["url"],
                        published_at=raw.get("published_at"),
                        summary=raw.get("summary") or raw["title"],
                        relevance_score=score,
                        confidence=confidence,
                        reason=reason,
                    )
                )

        candidates = sorted(
            _dedupe(candidates),
            key=lambda item: (
                item.relevance_score,
                item.published_at or "",
            ),
            reverse=True,
        )

        results.extend(candidates[:max_per_category])

    return _dedupe(results)


def developments_as_dicts(
    items: list[GlobalDevelopment],
) -> list[dict[str, Any]]:
    return [item.__dict__ for item in items]
