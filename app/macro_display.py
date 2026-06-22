from pathlib import Path
import re

path = Path("app/email/html_builder.py")
text = path.read_text(encoding="utf-8")

pattern = re.compile(
    r"def _macro_state_table\(items: list\[Any\]\) -> str:.*?(?=\n\ndef _economic_calendar_table)",
    re.DOTALL,
)

new = 'def _macro_state_table(items: list[Any]) -> str:\n    if not items:\n        return \'<p style="margin:0;color:#cbd5e1;font-size:14px;">No macro state data retrieved. Check FRED_API_KEY.</p>\'\n\n    body = ""\n\n    for item in items:\n        name = escape(str(_get(item, "name", "N/A")))\n        latest = escape(str(_get(item, "latest_display") or _fmt_number(_get(item, "actual"))))\n        prior = escape(str(_get(item, "prior_display") or _fmt_number(_get(item, "prior"))))\n        change = escape(str(_get(item, "change_display") or "N/A"))\n        change_label = escape(str(_get(item, "change_label") or "Change"))\n        release_date = escape(str(_get(item, "date", "N/A")))\n        source = escape(str(_get(item, "source", "Unknown")))\n        note = escape(str(_get(item, "note", "")))\n\n        body += f"""<tr><td style="padding:13px 10px;border-top:1px solid #1f2937;"><div style="font-weight:750;color:#f8fafc;font-size:14px;">{name}</div><div style="color:#94a3b8;font-size:12px;margin-top:2px;">{release_date} - {source}</div></td><td align="right" style="padding:13px 10px;border-top:1px solid #1f2937;color:#f8fafc;font-size:13px;font-weight:750;">{latest}</td><td align="right" style="padding:13px 10px;border-top:1px solid #1f2937;color:#cbd5e1;font-size:13px;">{prior}</td><td align="right" style="padding:13px 10px;border-top:1px solid #1f2937;color:#94a3b8;font-size:12px;"><div>{change}</div><div style="font-size:10px;color:#64748b;margin-top:2px;">{change_label}</div></td></tr><tr><td colspan="4" style="padding:0 10px 12px;color:#94a3b8;font-size:12px;line-height:1.45;">{note}</td></tr>"""\n\n    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;"><thead><tr><th align="left" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Indicator</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Latest</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Prior</th><th align="right" style="padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Change</th></tr></thead><tbody>{body}</tbody></table>"""'

text, count = pattern.subn(new, text, count=1)

if count != 1:
    raise SystemExit("Could not patch _macro_state_table. Function signature not found.")

text = text.replace(
    "No free economic calendar events are currently available for today from configured sources.",
    "No free economic-calendar provider is currently configured for today. Consensus estimates require a paid or manually maintained calendar source.",
)

text = text.replace(
    "No free economic calendar events are currently available for tomorrow from configured sources.",
    "No free economic-calendar provider is currently configured for tomorrow. Consensus estimates require a paid or manually maintained calendar source.",
)

text = text.replace(
    "FMP economic calendar is used where available for today/tomorrow economic release context.",
    "Economic-calendar timing and consensus estimates are disabled until a paid or manually maintained calendar source is configured.",
)

path.write_text(text, encoding="utf-8")
print("Patched app/email/html_builder.py")
