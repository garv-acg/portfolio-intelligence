from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any

from app.ai.formatter import build_fallback_text_newsletter
from app.config.portfolio import load_portfolio
from app.config.settings import settings
from app.data.earnings import get_upcoming_earnings
from app.data.global_news import get_global_developments
from app.data.macro_data import get_macro_snapshot
from app.data.market_data import get_equity_snapshot, get_index_snapshot
from app.data.news_fetcher import get_portfolio_news
from app.email.html_builder import build_html_newsletter


def to_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    if is_dataclass(item):
        return asdict(item)
    if hasattr(item, "__dict__"):
        return dict(item.__dict__)
    return {"value": str(item)}


def to_dict_list(items: list[Any]) -> list[dict[str, Any]]:
    return [to_dict(item) for item in items]


def get_attr(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def main(send_email: bool = False) -> None:
    report_date = date.today().isoformat()

    holdings = load_portfolio(settings.portfolio_file)
    tickers = [holding.ticker for holding in holdings]

    portfolio_snapshot = get_equity_snapshot(holdings)
    market_snapshot = get_index_snapshot()

    portfolio_news = get_portfolio_news(
        tickers=tickers,
        max_articles_per_ticker=settings.max_articles_per_ticker,
        newsapi_key=settings.newsapi_key,
        lookback_hours=settings.lookback_hours,
    )

    global_developments_raw = get_global_developments(
        lookback_hours=settings.lookback_hours,
        max_per_category=1,
    )
    global_developments = to_dict_list(global_developments_raw)

    earnings_calendar = get_upcoming_earnings(
        tickers=tickers,
        days_ahead=60,
    )

    macro_snapshot = get_macro_snapshot()

    macro_state = get_attr(
        macro_snapshot,
        "macro_state",
        "state",
        "releases",
        default=[],
    )

    economic_calendar_today = get_attr(
        macro_snapshot,
        "economic_calendar_today",
        "calendar_today",
        default=[],
    )

    economic_calendar_tomorrow = get_attr(
        macro_snapshot,
        "economic_calendar_tomorrow",
        "calendar_tomorrow",
        default=[],
    )

    briefing_data: dict[str, Any] = {
        "date": report_date,
        "portfolio_snapshot": to_dict_list(portfolio_snapshot),
        "portfolio_news": to_dict_list(portfolio_news),
        "market_snapshot": {
            name: to_dict(move)
            for name, move in market_snapshot.items()
        },
        "macro_state": to_dict_list(macro_state),
        "economic_calendar_today": to_dict_list(economic_calendar_today),
        "economic_calendar_tomorrow": to_dict_list(economic_calendar_tomorrow),
        "fed_updates": get_attr(macro_snapshot, "fed_updates", default=[]),
        "macro_source_note": get_attr(macro_snapshot, "source_note", default=None),
        "global_developments": global_developments,
        "earnings_calendar": to_dict_list(earnings_calendar),
        "sources": [
            "Portfolio news via institutional relevance filtering engine.",
            "Global developments via Federal Reserve, ECB, CNBC, and Yahoo Finance RSS.",
            "Macro state via FRED.",
            "Earnings dates via configured earnings provider.",
        ],
    }

    print(f"Global developments loaded: {len(global_developments)}")

    newsletter_text = build_fallback_text_newsletter(briefing_data)

    settings.output_dir.mkdir(parents=True, exist_ok=True)

    text_path = settings.output_dir / "latest_newsletter.txt"
    text_path.write_text(newsletter_text, encoding="utf-8")

    html = build_html_newsletter(
        briefing_data,
        text_fallback=newsletter_text,
    )

    html_path = settings.output_dir / "latest_newsletter.html"
    html_path.write_text(html, encoding="utf-8")

    print(f"Saved text newsletter: {text_path}")
    print(f"Saved HTML newsletter: {html_path}")

    if send_email:
        print("Email delivery not configured in current V1.")


if __name__ == "__main__":
    main(send_email=False)
