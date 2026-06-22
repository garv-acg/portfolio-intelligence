from pathlib import Path

path = Path("app/email/html_builder.py")
text = path.read_text(encoding="utf-8")

func = "def _sec_filings_section(items: list[Any]) -> str:\n    if not items:\n        return '<p style=\"margin:0;color:#cbd5e1;font-size:14px;\">No high-priority SEC filings were identified for current portfolio holdings within the configured lookback window.</p>'\n\n    rows = \"\"\n\n    for item in items:\n        ticker = escape(str(_get(item, \"ticker\", \"N/A\")))\n        form_type = escape(str(_get(item, \"form_type\", \"N/A\")))\n        category = escape(str(_get(item, \"category\", \"SEC Filing\")))\n        title = escape(str(_get(item, \"title\", \"Untitled filing\")))\n        source = escape(str(_get(item, \"source\", \"SEC EDGAR\")))\n        filed_at = escape(str(_get(item, \"filed_at\", \"N/A\"))[:16].replace(\"T\", \" \"))\n        score = escape(str(_get(item, \"relevance_score\", \"N/A\")))\n        confidence = escape(str(_get(item, \"confidence\", \"N/A\")))\n        reason = escape(str(_get(item, \"reason\", \"\")))\n        url = _get(item, \"url\")\n\n        title_html = (\n            f'<a href=\"{escape(str(url))}\" style=\"color:#93c5fd;text-decoration:none;\">{title}</a>'\n            if url\n            else title\n        )\n\n        rows += f\"\"\"\n        <tr>\n          <td style=\"padding:13px 10px;border-top:1px solid #1f2937;\">\n            <div style=\"font-weight:750;color:#f8fafc;font-size:14px;\">{ticker} \u00b7 {form_type}</div>\n            <div style=\"color:#94a3b8;font-size:12px;margin-top:2px;\">{category} \u00b7 {source} \u00b7 {filed_at}</div>\n          </td>\n          <td style=\"padding:13px 10px;border-top:1px solid #1f2937;color:#cbd5e1;font-size:13px;line-height:1.45;\">\n            <div>{title_html}</div>\n            <div style=\"color:#64748b;font-size:11px;margin-top:4px;\">{confidence} confidence \u00b7 score {score} \u00b7 {reason}</div>\n          </td>\n        </tr>\n        \"\"\"\n\n    return f\"\"\"\n    <table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"border-collapse:collapse;\">\n      <thead>\n        <tr>\n          <th align=\"left\" style=\"padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;\">Filing</th>\n          <th align=\"left\" style=\"padding:0 10px 10px;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;\">Signal</th>\n        </tr>\n      </thead>\n      <tbody>{rows}</tbody>\n    </table>\n    \"\"\"\n"

if "def _sec_filings_section(" not in text:
    marker = "\n\ndef _sources_section"
    text = text.replace(marker, "\n\n" + func + marker)

if 'sec_filings = payload.get("sec_filings", [])' not in text:
    text = text.replace(
        '    earnings_calendar = payload.get("earnings_calendar", [])\n',
        '    earnings_calendar = payload.get("earnings_calendar", [])\n    sec_filings = payload.get("sec_filings", [])\n',
    )

# Insert before Sources. Handle both current numbering schemes.
if '_sec_filings_section(sec_filings)' not in text:
    target_10 = '{_section_title("10", "Sources")}{_card(_sources_section(payload))}'
    repl_10 = '{_section_title("10", "SEC Filings Monitor")}{_card(_sec_filings_section(sec_filings))}\n{_section_title("11", "Sources")}{_card(_sources_section(payload))}'

    target_9 = '{_section_title("09", "Sources")}{_card(_sources_section(payload))}'
    repl_9 = '{_section_title("09", "SEC Filings Monitor")}{_card(_sec_filings_section(sec_filings))}\n{_section_title("10", "Sources")}{_card(_sources_section(payload))}'

    if target_10 in text:
        text = text.replace(target_10, repl_10)
    elif target_9 in text:
        text = text.replace(target_9, repl_9)
    else:
        print("Warning: could not find Sources section for SEC insertion.")

path.write_text(text, encoding="utf-8")
print("Patched html_builder.py with SEC filings monitor.")
