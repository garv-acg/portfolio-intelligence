
from __future__ import annotations
from pathlib import Path
import sys

ENGINE = "\nfrom __future__ import annotations\n\nfrom datetime import datetime, timezone\nfrom pathlib import Path\nfrom typing import Any\nimport pandas as pd\n\n\ndef _get(x: Any, key: str, default=None):\n    return x.get(key, default) if isinstance(x, dict) else getattr(x, key, default)\n\n\ndef _money(v):\n    try:\n        return f\"${float(v):,.2f}\"\n    except Exception:\n        return \"N/A\"\n\n\ndef _pct(v):\n    try:\n        return f\"{float(v):+.2f}%\"\n    except Exception:\n        return \"N/A\"\n\n\ndef _section(key: str, title: str, summary: str, rows: list[dict[str, Any]], priority: int):\n    return {\"key\": key, \"title\": title, \"summary\": summary, \"rows\": rows, \"priority\": priority}\n\n\ndef portfolio_snapshot(rows):\n    if not rows:\n        return _section(\"portfolio_snapshot\", \"Portfolio Snapshot\", \"No portfolio holdings found.\", [], 10)\n    df = pd.DataFrame(rows)\n    value_col = \"market_value\" if \"market_value\" in df.columns else \"value\" if \"value\" in df.columns else None\n    total = float(df[value_col].sum()) if value_col else 0.0\n    out = []\n    for _, r in df.iterrows():\n        val = float(r.get(value_col, 0) or 0) if value_col else 0\n        out.append({\n            \"Ticker\": r.get(\"ticker\", r.get(\"Ticker\", \"\")),\n            \"Sector\": r.get(\"sector\", r.get(\"Sector\", \"N/A\")),\n            \"Market Value\": _money(val),\n            \"Weight\": _pct((val / total * 100) if total else 0),\n        })\n    return _section(\"portfolio_snapshot\", \"Portfolio Snapshot\", f\"{len(out)} holding(s), estimated value {_money(total)}.\", out, 10)\n\n\ndef top_movers(rows):\n    if not rows:\n        return _section(\"top_movers\", \"Top Movers\", \"No holdings movement data available.\", [], 20)\n    df = pd.DataFrame(rows)\n    move_col = \"daily_move_pct\" if \"daily_move_pct\" in df.columns else \"Daily Move (%)\" if \"Daily Move (%)\" in df.columns else None\n    if not move_col:\n        return _section(\"top_movers\", \"Top Movers\", \"No daily movement field available.\", [], 20)\n    df[\"_abs\"] = df[move_col].apply(lambda x: abs(float(x)) if pd.notna(x) else 0)\n    df = df.sort_values(\"_abs\", ascending=False).head(5)\n    out = []\n    for _, r in df.iterrows():\n        out.append({\n            \"Ticker\": r.get(\"ticker\", r.get(\"Ticker\", \"\")),\n            \"Daily Move\": _pct(r.get(move_col)),\n            \"Weekly Move\": _pct(r.get(\"weekly_move_pct\", r.get(\"Weekly Move (%)\"))),\n            \"Volume vs 30D Avg\": f\"{float(r.get('volume_vs_30d_avg') or 0):.2f}x\" if r.get(\"volume_vs_30d_avg\") is not None else \"N/A\",\n        })\n    return _section(\"top_movers\", \"Top Movers\", \"Largest absolute daily moves across current holdings.\", out, 20)\n\n\ndef earnings_section(earnings):\n    rows = []\n    for e in earnings or []:\n        ticker = str(_get(e, \"ticker\", \"\")).upper()\n        if ticker:\n            rows.append({\"Ticker\": ticker, \"Date\": str(_get(e, \"date\", \"\"))[:10], \"Source\": _get(e, \"source\", \"Earnings Calendar\")})\n    return _section(\"earnings\", \"Earnings Calendar\", f\"{len(rows)} upcoming earnings event(s) found.\", rows[:10], 30)\n\n\ndef sec_section(filings):\n    rows = []\n    for f in filings or []:\n        ticker = str(_get(f, \"ticker\", \"\")).upper()\n        if ticker:\n            items = _get(f, \"items_detected\", []) or []\n            rows.append({\n                \"Ticker\": ticker,\n                \"Form\": _get(f, \"form_type\", \"\"),\n                \"Date\": str(_get(f, \"filing_date\", _get(f, \"accepted_at\", \"\")))[:10],\n                \"Items\": \", \".join(items) if items else \"N/A\",\n                \"Factual Note\": _get(f, \"signal_summary\", _get(f, \"signal_type\", \"Recent filing detected\")),\n            })\n    return _section(\"sec_filings\", \"SEC Filings\", f\"{len(rows)} recent SEC filing(s) found.\", rows[:10], 40)\n\n\ndef alerts_section(alerts):\n    rows = []\n    for a in alerts or []:\n        rows.append({\n            \"Type\": a.get(\"alert_type\", \"\"),\n            \"Severity\": a.get(\"severity\", \"\"),\n            \"Ticker\": a.get(\"ticker\", \"\"),\n            \"Title\": a.get(\"title\", \"\"),\n            \"Created\": str(a.get(\"created_at\", \"\"))[:19],\n        })\n    return _section(\"alerts\", \"Alerts\", f\"{len(rows)} alert(s) currently available.\", rows[:10], 50)\n\n\ndef macro_section(macro):\n    indicators = (macro or {}).get(\"Indicators\", (macro or {}).get(\"macro_indicators\", [])) or []\n    rows = []\n    for i in indicators:\n        rows.append({\n            \"Indicator\": i.get(\"Indicator\", i.get(\"indicator\", \"\")),\n            \"Latest\": i.get(\"Latest\", i.get(\"latest\", \"\")),\n            \"Daily Change\": _pct(i.get(\"Daily Change (%)\", i.get(\"daily_change_pct\"))),\n            \"Weekly Change\": _pct(i.get(\"Weekly Change (%)\", i.get(\"weekly_change_pct\"))),\n        })\n    return _section(\"macro\", \"Macro Snapshot\", f\"{len(rows)} macro indicator(s) loaded.\", rows[:10], 60)\n\n\ndef build_morning_brief(\n    portfolio_rows=None,\n    holdings_monitor_rows=None,\n    earnings_calendar=None,\n    sec_filings=None,\n    alerts=None,\n    macro_data=None,\n    enabled_sections=None,\n):\n    enabled_sections = enabled_sections or [\"portfolio_snapshot\", \"top_movers\", \"earnings\", \"sec_filings\", \"alerts\", \"macro\"]\n    sections = [\n        portfolio_snapshot(portfolio_rows or []),\n        top_movers(holdings_monitor_rows or []),\n        earnings_section(earnings_calendar or []),\n        sec_section(sec_filings or []),\n        alerts_section(alerts or []),\n        macro_section(macro_data or {}),\n    ]\n    sections = [s for s in sections if s[\"key\"] in enabled_sections]\n    sections = sorted(sections, key=lambda x: x[\"priority\"])\n    return {\n        \"generated_at\": datetime.now(timezone.utc).isoformat(),\n        \"title\": \"Daily Portfolio Brief\",\n        \"subtitle\": \"Facts-first morning portfolio update.\",\n        \"sections\": sections,\n    }\n\n\ndef render_brief_text(brief):\n    lines = [brief.get(\"title\", \"Daily Portfolio Brief\"), brief.get(\"subtitle\", \"\"), f\"Generated: {brief.get('generated_at', '')}\", \"\"]\n    for s in brief.get(\"sections\", []):\n        lines += [s.get(\"title\", \"\"), \"-\" * len(s.get(\"title\", \"\")), s.get(\"summary\", \"\")]\n        for row in s.get(\"rows\", [])[:8]:\n            lines.append(\" \u2022 \" + \" | \".join([f\"{k}: {v}\" for k, v in row.items()]))\n        lines.append(\"\")\n    return \"\\n\".join(lines)\n\n\ndef render_brief_html(brief):\n    css = \"\"\"\n    <style>\n      body { font-family: Arial, sans-serif; background:#0b1020; color:#f8fafc; margin:0; padding:24px; }\n      .brief { max-width: 920px; margin: 0 auto; }\n      .header { border-bottom:1px solid #334155; padding-bottom:18px; margin-bottom:22px; }\n      .title { font-size:28px; font-weight:800; margin:0; }\n      .subtitle { color:#94a3b8; margin-top:8px; }\n      .section { background:#111827; border:1px solid #243044; border-radius:16px; padding:18px; margin:16px 0; }\n      .section h2 { margin:0 0 8px 0; font-size:18px; }\n      .summary { color:#cbd5e1; margin-bottom:14px; }\n      table { width:100%; border-collapse: collapse; font-size:13px; }\n      th { text-align:left; color:#94a3b8; border-bottom:1px solid #334155; padding:8px; }\n      td { border-bottom:1px solid #1f2937; padding:8px; vertical-align:top; }\n      .meta { color:#64748b; font-size:12px; margin-top:8px; }\n    </style>\n    \"\"\"\n    html = [css, '<div class=\"brief\"><div class=\"header\">']\n    html.append(f'<h1 class=\"title\">{brief.get(\"title\", \"Daily Portfolio Brief\")}</h1>')\n    html.append(f'<div class=\"subtitle\">{brief.get(\"subtitle\", \"\")}</div>')\n    html.append(f'<div class=\"meta\">Generated: {brief.get(\"generated_at\", \"\")}</div></div>')\n    for s in brief.get(\"sections\", []):\n        html.append(f'<div class=\"section\"><h2>{s.get(\"title\", \"\")}</h2><div class=\"summary\">{s.get(\"summary\", \"\")}</div>')\n        rows = s.get(\"rows\", [])\n        if rows:\n            cols = list(rows[0].keys())\n            html.append(\"<table><thead><tr>\" + \"\".join(f\"<th>{c}</th>\" for c in cols) + \"</tr></thead><tbody>\")\n            for row in rows:\n                html.append(\"<tr>\" + \"\".join(f\"<td>{row.get(c, '')}</td>\" for c in cols) + \"</tr>\")\n            html.append(\"</tbody></table>\")\n        html.append(\"</div>\")\n    html.append(\"</div>\")\n    return \"\".join(html)\n\n\ndef save_morning_brief_outputs(brief, output_dir=Path(\"output\")):\n    output_dir.mkdir(parents=True, exist_ok=True)\n    text_path = output_dir / \"morning_brief_v2.txt\"\n    html_path = output_dir / \"morning_brief_v2.html\"\n    text_path.write_text(render_brief_text(brief), encoding=\"utf-8\")\n    html_path.write_text(render_brief_html(brief), encoding=\"utf-8\")\n    return {\"text\": str(text_path), \"html\": str(html_path)}\n"
PAGE = "\ndef render_morning_brief() -> None:\n    st.markdown(\"### Morning Brief Engine\")\n    st.caption(\"Modular, facts-first daily newsletter builder. The newsletter is the product; the app configures and reviews it.\")\n\n    try:\n        from app.config.portfolio import load_portfolio\n        from app.config.settings import settings\n        from app.data.earnings import get_upcoming_earnings\n        from app.data.sec_filings import get_sec_filings\n        from app.data.alert_engine import latest_alerts\n        from app.data.morning_brief_engine import build_morning_brief, save_morning_brief_outputs, render_brief_html\n        from app.data.market_workbench import macro_dashboard\n        from app.data.holdings_monitor import build_holdings_change_monitor\n\n        portfolio_file = Path(st.session_state.get(\"portfolio_path_override\", str(settings.portfolio_file)))\n\n        section_options = {\n            \"Portfolio Snapshot\": \"portfolio_snapshot\",\n            \"Top Movers\": \"top_movers\",\n            \"Earnings Calendar\": \"earnings\",\n            \"SEC Filings\": \"sec_filings\",\n            \"Alerts\": \"alerts\",\n            \"Macro Snapshot\": \"macro\",\n        }\n\n        selected_labels = st.multiselect(\"Sections to include\", list(section_options.keys()), default=list(section_options.keys()))\n        enabled_sections = [section_options[label] for label in selected_labels]\n        st.caption(f\"Active portfolio: {portfolio_file}\")\n\n        if st.button(\"Build Morning Brief\", type=\"primary\"):\n            with st.spinner(\"Building facts-first morning brief...\"):\n                holdings = load_portfolio(portfolio_file)\n                tickers = [holding.ticker for holding in holdings]\n                earnings = get_upcoming_earnings(tickers, days_ahead=30)\n                sec = get_sec_filings(tickers, lookback_days=30, max_filings_per_ticker=3)\n                alerts = latest_alerts(limit=25)\n                macro = macro_dashboard()\n                monitor = build_holdings_change_monitor(holdings, earnings_calendar=earnings, sec_filings=sec, benchmark=\"SPY\")\n\n                brief = build_morning_brief(\n                    portfolio_rows=monitor.get(\"holdings\", []),\n                    holdings_monitor_rows=monitor.get(\"holdings\", []),\n                    earnings_calendar=earnings,\n                    sec_filings=sec,\n                    alerts=alerts,\n                    macro_data=macro,\n                    enabled_sections=enabled_sections,\n                )\n\n                paths = save_morning_brief_outputs(brief)\n                st.session_state[\"latest_morning_brief\"] = brief\n                st.session_state[\"latest_morning_brief_paths\"] = paths\n                st.success(\"Morning brief generated.\")\n\n        brief = st.session_state.get(\"latest_morning_brief\")\n        paths = st.session_state.get(\"latest_morning_brief_paths\", {})\n\n        if not brief:\n            st.info(\"Click Build Morning Brief to generate the modular newsletter preview.\")\n            return\n\n        st.divider()\n        st.markdown(\"#### Generated Files\")\n        st.dataframe(pd.DataFrame([\n            {\"File\": \"HTML Brief\", \"Path\": paths.get(\"html\", \"N/A\")},\n            {\"File\": \"Text Brief\", \"Path\": paths.get(\"text\", \"N/A\")},\n        ]), use_container_width=True, hide_index=True)\n\n        st.divider()\n        st.markdown(\"#### Brief Preview\")\n        for section in brief.get(\"sections\", []):\n            with st.expander(section.get(\"title\", \"\"), expanded=True):\n                st.write(section.get(\"summary\", \"\"))\n                rows = section.get(\"rows\", [])\n                if rows:\n                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)\n\n        st.divider()\n        st.markdown(\"#### HTML Preview\")\n        st.components.v1.html(render_brief_html(brief), height=800, scrolling=True)\n\n    except Exception as exc:\n        st.error(f\"Morning Brief Engine failed: {exc}\")\n"

def backup(path: Path) -> None:
    if path.exists():
        path.with_suffix(path.suffix + ".bak_morning_brief_engine").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

def install_module() -> None:
    target = Path("app/data/morning_brief_engine.py")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(ENGINE, encoding="utf-8")
    print("OK | app/data/morning_brief_engine.py written")

def patch_control_center() -> None:
    path = Path("newsletter_control_center.py")
    if not path.exists():
        raise SystemExit("ERROR | newsletter_control_center.py not found")
    backup(path)
    text = path.read_text(encoding="utf-8")

    if "def render_morning_brief() -> None:" not in text:
        text = text.replace("\ndef main() -> None:", PAGE + "\ndef main() -> None:", 1)

    if '"Morning Brief",' not in text:
        for anchor in ['        "Newsletter",\n', '        "Overview",\n', '        "Portfolio",\n']:
            if anchor in text:
                text = text.replace(anchor, anchor + '        "Morning Brief",\n', 1)
                break
        else:
            raise SystemExit("ERROR | could not add Morning Brief to nav_pages")

    if 'elif page == "Morning Brief":' not in text:
        for old, new in [
            ('    elif page == "Newsletter":\n        render_newsletter()\n', '    elif page == "Newsletter":\n        render_newsletter()\n    elif page == "Morning Brief":\n        render_morning_brief()\n'),
            ('    elif page == "Overview":\n        render_overview(df, portfolio_path)\n', '    elif page == "Overview":\n        render_overview(df, portfolio_path)\n    elif page == "Morning Brief":\n        render_morning_brief()\n'),
            ('    elif page == "Portfolio":\n        render_portfolio(df, portfolio_path)\n', '    elif page == "Portfolio":\n        render_portfolio(df, portfolio_path)\n    elif page == "Morning Brief":\n        render_morning_brief()\n'),
        ]:
            if old in text:
                text = text.replace(old, new, 1)
                break
        else:
            raise SystemExit("ERROR | could not add Morning Brief route")

    path.write_text(text, encoding="utf-8")
    print("OK | newsletter_control_center.py patched")

def verify() -> bool:
    checks = {}
    checks["module exists"] = Path("app/data/morning_brief_engine.py").exists()
    text = Path("newsletter_control_center.py").read_text(encoding="utf-8")
    checks["Morning Brief nav"] = '"Morning Brief"' in text
    checks["render_morning_brief"] = "def render_morning_brief() -> None:" in text
    checks["Morning Brief route"] = 'elif page == "Morning Brief":' in text
    try:
        from app.data.morning_brief_engine import build_morning_brief, render_brief_html
        brief = build_morning_brief()
        render_brief_html(brief)
        checks["import works"] = True
    except Exception as exc:
        print(f"FAIL | import error: {exc}")
        checks["import works"] = False

    print("\nVERIFY")
    ok = True
    for name, passed in checks.items():
        print(("PASS" if passed else "FAIL") + f" | {name}")
        ok = ok and passed
    return ok

def main() -> None:
    if "--verify" in sys.argv:
        raise SystemExit(0 if verify() else 1)
    print("Installing Morning Brief Engine V1 from:", Path.cwd())
    install_module()
    patch_control_center()
    ok = verify()
    print("\nNEXT:")
    print("python install_morning_brief_engine.py --verify")
    print("python -m streamlit run newsletter_control_center.py")
    raise SystemExit(0 if ok else 1)

if __name__ == "__main__":
    main()
