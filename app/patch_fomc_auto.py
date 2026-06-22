"""
patch_fomc_auto.py — run once from project root:
    python3 patch_fomc_auto.py
"""
path = "generate_hybrid_newsletter.py"
content = open(path, encoding="utf-8").read()

# Add FOMC auto-detection to the refresh loop
# DFEDTARU and DFEDTARL are FRED series that update same day as FOMC decisions
old_fomc = (
    '                elif event == "FOMC Rate Decision":\n'
    '                    rate = _fred_rate(series)\n'
    '                    if rate and str(df.loc[mask, "prior"].values[0]) != rate:\n'
    '                        df.loc[mask, "prior"] = rate\n'
    '                        changed = True\n'
    '                    continue\n'
)

new_fomc = (
    '                elif event == "FOMC Rate Decision":\n'
    '                    # Fetch daily target range bounds — update same day as FOMC\n'
    '                    upper = fetch_fred_latest("DFEDTARU")\n'
    '                    lower = fetch_fred_latest("DFEDTARL")\n'
    '                    if upper and lower:\n'
    '                        try:\n'
    '                            u = float(upper)\n'
    '                            l = float(lower)\n'
    '                            rate_range = f"{l:.2f}-{u:.2f}%"\n'
    '                            # Prior = previous rate range (what it was before)\n'
    '                            current_prior = str(df.loc[mask, "prior"].values[0])\n'
    '                            if current_prior != rate_range:\n'
    '                                # Rate changed — old value becomes prior, new is actual\n'
    '                                df.loc[mask, "actual"] = rate_range\n'
    '                                df.loc[mask, "prior"]  = current_prior\n'
    '                                df.loc[mask, "last_updated"] = str(\n'
    '                                    __import__("datetime").date.today()\n'
    '                                )\n'
    '                                changed = True\n'
    '                            else:\n'
    '                                # No change — mark as confirmed hold\n'
    '                                current_actual = str(df.loc[mask, "actual"].values[0])\n'
    '                                if not current_actual or current_actual in ("", "nan", "NaN"):\n'
    '                                    df.loc[mask, "actual"] = "No change"\n'
    '                                    df.loc[mask, "last_updated"] = str(\n'
    '                                        __import__("datetime").date.today()\n'
    '                                    )\n'
    '                                    changed = True\n'
    '                        except Exception:\n'
    '                            pass\n'
    '                    continue\n'
)

if old_fomc in content:
    content = content.replace(old_fomc, new_fomc)
    print("FOMC auto-update: patched")
else:
    print("ERROR: FOMC block not found")
    idx = content.find("FOMC Rate Decision")
    print("Context:", repr(content[idx:idx+300]))

open(path, "w", encoding="utf-8").write(content)
print("Done.")
