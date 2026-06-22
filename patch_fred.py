"""
patch_fred.py  —  run once from project root:
    python3 patch_fred.py
"""
path = "generate_hybrid_newsletter.py"
content = open(path, encoding="utf-8").read()

# ── 1. Expand _FRED_SERIES ────────────────────────────────────────────────────
old_series = (
    '_FRED_SERIES = {\n'
    '    "CPI Inflation":   ("CPIAUCSL", lambda v: f"{float(v):.1f}"),   # CPI index level\n'
    '    "PCE Inflation":   ("PCEPI",    lambda v: f"{float(v):.1f}"),   # PCE index level\n'
    '    "Jobs Report":     ("PAYEMS",   lambda v: f"{int(float(v)):,}K"), # Nonfarm payrolls (thousands)\n'
    '}'
)

new_series = (
    '_FRED_SERIES = {\n'
    '    "CPI Inflation":      ("CPIAUCSL", lambda v: f"{float(v):.1f}"),\n'
    '    "PCE Inflation":      ("PCEPI",    lambda v: f"{float(v):.1f}"),\n'
    '    "Jobs Report":        ("PAYEMS",   lambda v: f"{int(float(v)):,}K"),\n'
    '    "Retail Sales":       ("RSXFS",    None),\n'
    '    "FOMC Rate Decision": ("FEDFUNDS", None),\n'
    '}\n'
    '\n'
    '\n'
    'def _fred_mom_pct(series_id: str) -> str:\n'
    '    """MoM % change from two consecutive FRED observations."""\n'
    '    try:\n'
    '        from app.config.settings import settings as _s\n'
    '        import requests as _req\n'
    '        api_key = getattr(_s, "fred_api_key", None)\n'
    '        if not api_key:\n'
    '            return ""\n'
    '        r = _req.get(\n'
    '            "https://api.stlouisfed.org/fred/series/observations",\n'
    '            params={"series_id": series_id, "api_key": api_key,\n'
    '                    "file_type": "json", "sort_order": "desc", "limit": 2},\n'
    '            timeout=10,\n'
    '        )\n'
    '        obs = [o for o in r.json().get("observations", [])\n'
    '               if o.get("value") not in (None, ".")]\n'
    '        if len(obs) < 2:\n'
    '            return ""\n'
    '        latest = float(obs[0]["value"])\n'
    '        prior  = float(obs[1]["value"])\n'
    '        if prior == 0:\n'
    '            return ""\n'
    '        return f"{(latest - prior) / prior * 100:+.1f}%"\n'
    '    except Exception:\n'
    '        return ""\n'
    '\n'
    '\n'
    'def _fred_rate(series_id: str) -> str:\n'
    '    """Latest FRED rate observation as formatted string."""\n'
    '    try:\n'
    '        val = fetch_fred_latest(series_id)\n'
    '        return f"{float(val):.2f}%" if val else ""\n'
    '    except Exception:\n'
    '        return ""\n'
)

if old_series in content:
    content = content.replace(old_series, new_series)
    print("_FRED_SERIES: patched")
else:
    print("ERROR: _FRED_SERIES not found — searching for partial match")
    idx = content.find("_FRED_SERIES")
    print(repr(content[idx:idx+200]))

# ── 2. Update the refresh loop ────────────────────────────────────────────────
old_loop = (
    '        for event, (series, fmt) in _FRED_SERIES.items():\n'
    '            val = fetch_fred_latest(series)\n'
    '            if val:\n'
    '                try:\n'
    '                    display = fmt(val)\n'
    '                    mask = df["event"] == event\n'
    '                    if mask.any() and str(df.loc[mask, "actual"].values[0]) != display:\n'
    '                        df.loc[mask, "actual"] = display\n'
    '                        changed = True\n'
    '                except Exception:\n'
    '                    pass'
)

new_loop = (
    '        for event, (series, fmt) in _FRED_SERIES.items():\n'
    '            try:\n'
    '                mask = df["event"] == event\n'
    '                if not mask.any():\n'
    '                    continue\n'
    '                if event == "Retail Sales":\n'
    '                    display = _fred_mom_pct(series)\n'
    '                elif event == "FOMC Rate Decision":\n'
    '                    rate = _fred_rate(series)\n'
    '                    if rate and str(df.loc[mask, "prior"].values[0]) != rate:\n'
    '                        df.loc[mask, "prior"] = rate\n'
    '                        changed = True\n'
    '                    continue\n'
    '                else:\n'
    '                    val = fetch_fred_latest(series)\n'
    '                    if not val:\n'
    '                        continue\n'
    '                    display = fmt(val)\n'
    '                if display and str(df.loc[mask, "actual"].values[0]) != display:\n'
    '                    df.loc[mask, "actual"] = display\n'
    '                    changed = True\n'
    '            except Exception:\n'
    '                pass'
)

if old_loop in content:
    content = content.replace(old_loop, new_loop)
    print("refresh loop: patched")
else:
    print("ERROR: refresh loop not found")

open(path, "w", encoding="utf-8").write(content)
print("Done.")
