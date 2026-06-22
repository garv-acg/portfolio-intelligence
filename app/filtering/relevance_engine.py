from __future__ import annotations

from app.data.news_fetcher import Article

HIGH_PRIORITY_TERMS = [
    "earnings",
    "guidance",
    "revenue",
    "profit",
    "sec",
    "filing",
    "federal reserve",
    "fed",
    "cpi",
    "inflation",
    "jobs",
    "tariff",
    "merger",
    "acquisition",
    "lawsuit",
    "regulator",
    "antitrust",
]


def score_article(article: Article) -> int:
    text = f"{article.title} {article.summary or ''}".lower()
    score = 0
    for term in HIGH_PRIORITY_TERMS:
        if term in text:
            score += 2
    if article.ticker and article.ticker.lower() in text:
        score += 1
    return score


def rank_articles(articles: list[Article]) -> list[Article]:
    return sorted(articles, key=score_article, reverse=True)
