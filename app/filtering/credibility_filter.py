from __future__ import annotations

from app.data.news_fetcher import APPROVED_DOMAINS, Article


def is_approved_source(article: Article) -> bool:
    if not article.url:
        # Keep Yahoo Finance-provided headlines in V1, but label source clearly.
        return article.source in {"Yahoo Finance", "Reuters", "Bloomberg", "The Wall Street Journal", "Financial Times"}
    return any(domain in article.url for domain in APPROVED_DOMAINS)


def filter_credible_articles(articles: list[Article]) -> list[Article]:
    return [article for article in articles if is_approved_source(article)]
