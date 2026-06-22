from __future__ import annotations

from datetime import date
from typing import Any


def _fmt_price(value: Any) -> str:
    try:
        if value is None:
            return "N/A"
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_pct(value: Any) -> str:
    try:
        if value is None:
            return "N/A"
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_date(value: Any) -> str:
    if value is None:
        return "N/A"
    return str(value)


def _get_item_value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _normalize_article(article: Any) -> dict[str, Any]:
    if isinstance(article, dict):
        return article
    if hasattr(article, "__dict__"):
        return article.__dict__
    return {"title": str(article), "source": "Unknown"}


def build_fallback_newsletter(payload: dict[str, Any]) -> str:
    """
    Deterministic, non-AI newsletter formatter.

    This function intentionally does not provide investment advice,
    trading recommendations, forecasts, or subjective opinions.
    """

    report_date = payload.get("date") or date.today().isoformat()
    portfolio_snapshot = payload.get("portfolio_snapshot", [])
    portfolio_news = payload.get("portfolio_news", [])
    market_snapshot = payload.get("market_snapshot", {})
    earnings_calendar = payload.get("earnings_calendar", [])
    sources = payload.get("sources", [])

    lines: list[str] = []

    lines.append(f"Daily Market Brief — {report_date}")
    lines.append("")

    lines.append("1. Portfolio Snapshot")

    if not portfolio_snapshot:
        lines.append("- No portfolio holdings were found.")
    else:
        for item in portfolio_snapshot:
            ticker = _get_item_value(item, "ticker", "N/A")
            price = _get_item_value(item, "price")
            change = _get_item_value(item, "day_change_pct")
            source = _get_item_value(item, "source", "Unknown")
            status = _get_item_value(item, "status", "Unavailable")

            if price is None:
                lines.append(f"- {ticker}: N/A; last price N/A. Source: {source}. Status: {status}.")
            else:
                lines.append(
                    f"- {ticker}: {_fmt_pct(change)}; last price {_fmt_price(price)}. Source: {source}."
                )

    lines.append("")

    lines.append("2. Portfolio News")

    if not portfolio_news:
        lines.append("- No verified portfolio-specific developments were found in the configured sources.")
    else:
        for raw_article in portfolio_news:
            article = _normalize_article(raw_article)
            ticker = article.get("ticker")
            title = article.get("title") or "Untitled article"
            source = article.get("source") or article.get("publisher") or "Unknown source"

            if ticker:
                lines.append(f"- {ticker}: {title} ({source})")
            else:
                lines.append(f"- {title} ({source})")

    lines.append("")

    lines.append("3. US Market & Macro Update")

    if not market_snapshot:
        lines.append("- Market snapshot unavailable.")
    else:
        for name, item in market_snapshot.items():
            price = _get_item_value(item, "price")
            change = _get_item_value(item, "day_change_pct")
            source = _get_item_value(item, "source", "Unknown")
            status = _get_item_value(item, "status", "Unavailable")

            if price is None:
                lines.append(f"- {name}: N/A; latest N/A. Source: {source}. Status: {status}.")
            else:
                lines.append(
                    f"- {name}: {_fmt_pct(change)}; latest {_fmt_price(price)}. Source: {source}."
                )

    lines.append("- Macro calendar check: No official macro calendar API is configured in V1.")
    lines.append("")

    lines.append("4. Biggest Headline of the Day")

    if portfolio_news:
        first_article = _normalize_article(portfolio_news[0])
        title = first_article.get("title") or "No title available"
        source = first_article.get("source") or first_article.get("publisher") or "Unknown source"
        lines.append(f"- {title} ({source})")
    else:
        lines.append("- No single verified headline was identified from the configured sources.")

    lines.append("")

    lines.append("5. Global Developments")
    lines.append("- Global macro/news integrations are not yet configured in V1.")
    lines.append("")

    lines.append("6. Earnings Calendar")

    if not earnings_calendar:
        lines.append("- No portfolio earnings dates were verified within the configured 14-day window.")
    else:
        for item in earnings_calendar:
            ticker = _get_item_value(item, "ticker", "N/A")
            earnings_date = _get_item_value(item, "earnings_date") or _get_item_value(item, "date")
            source = _get_item_value(item, "source", "Unknown")
            lines.append(f"- {ticker}: upcoming earnings date listed as {_fmt_date(earnings_date)} ({source}).")

    lines.append("")

    lines.append("7. Sources")

    source_lines: list[str] = []

    if sources:
        for source in sources:
            if isinstance(source, dict):
                label = source.get("source") or source.get("name") or "Source"
                url = source.get("url")
                if url:
                    source_lines.append(f"- {label}: {url}")
                else:
                    source_lines.append(f"- {label}")
            else:
                source_lines.append(f"- {source}")

    detected_sources = set()

    for item in portfolio_snapshot:
        source = _get_item_value(item, "source")
        if source and source != "Unavailable":
            detected_sources.add(str(source))

    if isinstance(market_snapshot, dict):
        for item in market_snapshot.values():
            source = _get_item_value(item, "source")
            if source and source != "Unavailable":
                detected_sources.add(str(source))

    if detected_sources:
        source_lines.append(f"- Market data via {', '.join(sorted(detected_sources))}.")
    else:
        source_lines.append("- Configured market data sources returned no verified prices.")

    if not portfolio_news:
        source_lines.append("- Configured article sources returned no verified links.")

    lines.extend(source_lines)

    lines.append("")
    lines.append("Factual market brief only. No investment advice, recommendations, forecasts, or trading instructions.")

    return "\n".join(lines)


def format_newsletter(payload: dict[str, Any]) -> str:
    """
    Public formatter entrypoint used by main.py.
    """
    return build_fallback_newsletter(payload)

def build_fallback_text_newsletter(payload: dict) -> str:
    return build_fallback_newsletter(payload)
