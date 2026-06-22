from pathlib import Path

path = Path("main.py")
text = path.read_text(encoding="utf-8")

if "from app.data.visual_analytics import build_visual_analytics" not in text:
    if "from app.data.sec_filings import get_sec_filings\n" in text:
        text = text.replace(
            "from app.data.sec_filings import get_sec_filings\n",
            "from app.data.sec_filings import get_sec_filings\nfrom app.data.visual_analytics import build_visual_analytics\n",
        )
    else:
        text = text.replace(
            "from app.data.market_data import get_equity_snapshot, get_index_snapshot\n",
            "from app.data.market_data import get_equity_snapshot, get_index_snapshot\nfrom app.data.visual_analytics import build_visual_analytics\n",
        )

if "visual_analytics = build_visual_analytics(" not in text:
    marker = "    cross_asset_regime = infer_cross_asset_regime(\n"
    if marker in text:
        text = text.replace(marker, '    visual_analytics = build_visual_analytics(\n        holdings=holdings,\n        portfolio_snapshot=portfolio_snapshot,\n        lookback_days=120,\n    )\n\n' + marker)
    else:
        marker = "    briefing_data: dict[str, Any] = {\n"
        text = text.replace(marker, '    visual_analytics = build_visual_analytics(\n        holdings=holdings,\n        portfolio_snapshot=portfolio_snapshot,\n        lookback_days=120,\n    )\n\n' + marker)

if '"visual_analytics": to_dict(visual_analytics),' not in text:
    text = text.replace(
        '        "market_snapshot": {name: to_dict(move) for name, move in market_snapshot.items()},\n',
        '        "market_snapshot": {name: to_dict(move) for name, move in market_snapshot.items()},\n        "visual_analytics": to_dict(visual_analytics),\n',
    )

if '"Visual analytics from Yahoo Finance historical prices."' not in text:
    text = text.replace(
        '            "SEC filings via SEC EDGAR Atom feeds.",\n',
        '            "SEC filings via SEC EDGAR Atom feeds.",\n            "Visual analytics from Yahoo Finance historical prices.",\n',
    )

path.write_text(text, encoding="utf-8")
print("Patched main.py with Tier 3 visual analytics.")
