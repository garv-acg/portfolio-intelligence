from pathlib import Path

path = Path("main.py")
text = path.read_text(encoding="utf-8")

if "from app.data.regime_engine import infer_cross_asset_regime" not in text:
    text = text.replace(
        "from app.data.market_data import get_equity_snapshot, get_index_snapshot\n",
        "from app.data.market_data import get_equity_snapshot, get_index_snapshot\nfrom app.data.regime_engine import infer_cross_asset_regime\n",
    )

if "cross_asset_regime = infer_cross_asset_regime(" not in text:
    marker = "    briefing_data: dict[str, Any] = {\n"
    text = text.replace(marker, "    cross_asset_regime = infer_cross_asset_regime(\n        market_snapshot={name: to_dict(move) for name, move in market_snapshot.items()},\n        macro_state=to_dict_list(macro_state),\n        global_developments=global_developments,\n        portfolio_news=to_dict_list(portfolio_news),\n    )\n\n" + marker)

if '"cross_asset_regime": to_dict(cross_asset_regime),' not in text:
    text = text.replace(
        '        "global_developments": global_developments,\n',
        '        "global_developments": global_developments,\n        "cross_asset_regime": to_dict(cross_asset_regime),\n',
    )

path.write_text(text, encoding="utf-8")
print("Patched main.py with cross-asset regime intelligence.")
