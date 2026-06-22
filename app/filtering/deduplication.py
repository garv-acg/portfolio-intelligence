from __future__ import annotations

from app.data.news_fetcher import Article


def deduplicate_articles(articles: list[Article]) -> list[Article]:
    seen: set[str] = set()
    unique: list[Article] = []

    for article in articles:
        key = (article.url or article.title).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(article)

    return unique
