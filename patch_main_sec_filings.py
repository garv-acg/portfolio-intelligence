from pathlib import Path

path = Path("main.py")
text = path.read_text(encoding="utf-8")

if "from app.data.sec_filings import get_sec_filings" not in text:
    if "from app.data.regime_engine import infer_cross_asset_regime\n" in text:
        text = text.replace(
            "from app.data.regime_engine import infer_cross_asset_regime\n",
            "from app.data.regime_engine import infer_cross_asset_regime\nfrom app.data.sec_filings import get_sec_filings\n",
        )
    else:
        text = text.replace(
            "from app.data.news_fetcher import get_portfolio_news\n",
            "from app.data.news_fetcher import get_portfolio_news\nfrom app.data.sec_filings import get_sec_filings\n",
        )

if "sec_filings = get_sec_filings(" not in text:
    marker = "    cross_asset_regime = infer_cross_asset_regime(\n"
    if marker in text:
        text = text.replace(marker, '    sec_filings = get_sec_filings(\n        tickers=tickers,\n        lookback_days=14,\n        max_filings_per_ticker=3,\n    )\n\n' + marker)
    else:
        marker = "    briefing_data: dict[str, Any] = {\n"
        text = text.replace(marker, '    sec_filings = get_sec_filings(\n        tickers=tickers,\n        lookback_days=14,\n        max_filings_per_ticker=3,\n    )\n\n' + marker)

if '"sec_filings": to_dict_list(sec_filings),' not in text:
    text = text.replace(
        '        "earnings_calendar": to_dict_list(earnings_calendar),\n',
        '        "earnings_calendar": to_dict_list(earnings_calendar),\n        "sec_filings": to_dict_list(sec_filings),\n',
    )

if '"SEC filings via SEC EDGAR Atom feeds."' not in text:
    text = text.replace(
        '            "Earnings dates via configured earnings provider.",\n',
        '            "Earnings dates via configured earnings provider.",\n            "SEC filings via SEC EDGAR Atom feeds.",\n',
    )

path.write_text(text, encoding="utf-8")
print("Patched main.py with SEC filing ingestion.")
