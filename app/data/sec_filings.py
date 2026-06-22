from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import requests


@dataclass(frozen=True)
class SecFiling:
    ticker: str
    company: str | None
    form_type: str
    title: str
    url: str
    document_url: str | None
    raw_document_url: str | None
    filed_at: str | None
    source: str
    relevance_score: int
    confidence: str
    category: str
    reason: str
    signal_type: str
    signal_summary: str
    items_detected: list[str]


TICKER_CIK_MAP: dict[str, str] = {
    "AAPL": "0000320193",
    "AMZN": "0001018724",
    "AVGO": "0001730168",
    "GE": "0000040545",
    "NVDA": "0001045810",
    "SPOT": "0001639920",
    "MSFT": "0000789019",
    "GOOGL": "0001652044",
    "GOOG": "0001652044",
    "META": "0001326801",
    "TSLA": "0001318605",
}


FORM_PRIORITY = {
    "8-K": 85,
    "10-Q": 75,
    "10-K": 75,
    "4": 60,
    "DEF 14A": 50,
    "S-3": 40,
    "S-8": 30,
}


FORM_CATEGORY = {
    "8-K": "Material Event",
    "10-Q": "Quarterly Filing",
    "10-K": "Annual Filing",
    "4": "Insider Transaction",
    "DEF 14A": "Proxy / Governance",
    "S-3": "Securities Registration",
    "S-8": "Equity Compensation",
}


SEC_ITEM_PATTERNS: dict[str, tuple[str, str, int]] = {
    "Item 1.01": ("Material Agreement", "entry into a material definitive agreement", 35),
    "Item 1.02": ("Material Agreement", "termination of a material definitive agreement", 28),
    "Item 2.02": ("Earnings / Results", "results of operations and financial condition", 30),
    "Item 2.05": ("Restructuring", "costs associated with exit or disposal activities", 30),
    "Item 2.06": ("Impairment", "material impairment disclosure", 26),
    "Item 3.01": ("Listing / Compliance", "exchange listing or compliance notice", 24),
    "Item 5.02": ("Leadership / Governance", "director or executive officer departure, appointment, or compensation update", 42),
    "Item 5.03": ("Governance", "articles of incorporation or bylaws update", 22),
    "Item 7.01": ("Regulation FD", "selective disclosure or investor presentation", 22),
    "Item 8.01": ("Other Event", "other material event disclosure", 18),
    "Item 9.01": ("Financial Exhibits", "financial statements or exhibits filed", 12),
}


KEYWORD_SIGNALS: dict[str, tuple[str, str, int]] = {
    "share repurchase": ("Capital Return", "share repurchase authorization or buyback-related disclosure", 38),
    "stock repurchase": ("Capital Return", "stock repurchase authorization or buyback-related disclosure", 38),
    "buyback": ("Capital Return", "buyback-related disclosure", 35),
    "dividend": ("Capital Return", "dividend-related disclosure", 24),
    "guidance": ("Guidance", "forward-looking guidance or outlook update", 34),
    "outlook": ("Guidance", "forward-looking outlook update", 26),
    "restructuring": ("Restructuring", "restructuring-related disclosure", 34),
    "workforce reduction": ("Restructuring", "workforce reduction disclosure", 34),
    "layoff": ("Restructuring", "workforce reduction disclosure", 26),
    "material agreement": ("Material Agreement", "material commercial or financing agreement disclosure", 32),
    "merger": ("M&A", "merger-related disclosure", 36),
    "acquisition": ("M&A", "acquisition-related disclosure", 34),
    "chief executive officer": ("Leadership / Governance", "chief executive officer change or related leadership disclosure", 36),
    "chief financial officer": ("Leadership / Governance", "chief financial officer change or related leadership disclosure", 36),
    "appointed": ("Leadership / Governance", "appointment-related leadership disclosure", 24),
    "resigned": ("Leadership / Governance", "resignation-related leadership disclosure", 28),
    "departure": ("Leadership / Governance", "departure-related leadership disclosure", 28),
    "director": ("Leadership / Governance", "board or director-related governance disclosure", 18),
    "officer": ("Leadership / Governance", "officer-related governance disclosure", 18),
    "insider": ("Insider Transaction", "insider transaction disclosure", 18),
    "beneficial ownership": ("Ownership", "beneficial ownership disclosure", 18),
}


GUIDANCE_CONTEXT_TERMS = [
    "item 2.02",
    "results of operations",
    "financial condition",
    "earnings release",
    "furnished guidance",
    "updated guidance",
    "financial outlook",
    "business outlook",
]


REQUEST_HEADERS = {
    "User-Agent": "MorningNewsletterAgent/1.0 contact@example.com",
    "Accept-Encoding": "gzip, deflate",
}


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None

    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except Exception:
        return value


def _is_recent(filed_at: str | None, lookback_days: int) -> bool:
    if not filed_at:
        return True

    try:
        timestamp = datetime.fromisoformat(filed_at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp >= datetime.now(timezone.utc) - timedelta(days=lookback_days)
    except Exception:
        return True


def _clean(text: str | None) -> str:
    if not text:
        return ""

    text = re.sub(r"<script.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)

    # Preserve item labels better before stripping tags.
    text = re.sub(r"<[^>]+>", " ", text)

    replacements = {
        "&nbsp;": " ",
        "&#160;": " ",
        "&amp;": "&",
        "&#xA0;": " ",
        "\xa0": " ",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return re.sub(r"\s+", " ", text).strip()


def _sec_atom_url(cik: str) -> str:
    return (
        "https://www.sec.gov/cgi-bin/browse-edgar"
        f"?CIK={cik}"
        "&owner=exclude"
        "&action=getcompany"
        "&count=40"
        "&output=atom"
    )


def _extract_form_type(title: str) -> str:
    title_upper = title.upper()

    for form in sorted(FORM_PRIORITY, key=len, reverse=True):
        if re.search(rf"\b{re.escape(form)}\b", title_upper):
            return form

    match = re.match(r"([A-Z0-9/-]+)\s+-", title_upper)
    if match:
        return match.group(1)

    return "UNKNOWN"


def _normalize_inline_viewer_url(url: str | None) -> str | None:
    """
    Converts SEC inline viewer URLs into raw archive document URLs.

    Example:
    https://www.sec.gov/ix?doc=/Archives/edgar/data/1045810/.../nvda-20260507.htm

    becomes:
    https://www.sec.gov/Archives/edgar/data/1045810/.../nvda-20260507.htm
    """
    if not url:
        return None

    parsed = urlparse(url)

    if parsed.path.rstrip("/") == "/ix":
        query = parse_qs(parsed.query)
        doc_values = query.get("doc")

        if doc_values:
            doc_path = doc_values[0]
            if doc_path.startswith("/"):
                return "https://www.sec.gov" + doc_path
            return "https://www.sec.gov/" + doc_path

    if "/ix?doc=" in url:
        raw = url.split("/ix?doc=", 1)[1]
        if raw.startswith("/"):
            return "https://www.sec.gov" + raw
        return "https://www.sec.gov/" + raw

    return url


def _normalize_sec_url(base_url: str, href: str) -> str:
    if href.startswith("ixviewer/doc/"):
        href = href.replace("ixviewer/doc/", "")

    full_url = urljoin(base_url, href)
    return _normalize_inline_viewer_url(full_url) or full_url


def _find_primary_document_url(index_url: str, html_text: str, form_type: str) -> str | None:
    candidates: list[tuple[int, str]] = []

    row_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
    href_pattern = re.compile(r'href="([^"]+)"', re.I)

    for row in row_pattern.findall(html_text):
        clean_row = _clean(row).upper()
        hrefs = href_pattern.findall(row)

        if not hrefs:
            continue

        for href in hrefs:
            href_lower = href.lower()

            if not any(ext in href_lower for ext in [".htm", ".html", ".txt"]):
                continue

            if any(skip in href_lower for skip in [
                "xslf345x",
                "xslform",
                ".xml",
                "_cal.",
                "_def.",
                "_lab.",
                "_pre.",
                "_htm.xml",
            ]):
                continue

            score = 0

            if form_type.upper() in clean_row:
                score += 100

            if "PRIMARY DOCUMENT" in clean_row:
                score += 75

            if "EX-" in clean_row or "EXHIBIT" in clean_row:
                score -= 60

            if href_lower.endswith((".htm", ".html")):
                score += 20

            if href_lower.endswith(".txt"):
                score += 5

            if "/archives/edgar/data/" in href_lower:
                score += 10

            candidates.append((score, _normalize_sec_url(index_url, href)))

    if candidates:
        candidates.sort(key=lambda row: row[0], reverse=True)
        return candidates[0][1]

    hrefs = href_pattern.findall(html_text)

    for href in hrefs:
        href_lower = href.lower()

        if not any(ext in href_lower for ext in [".htm", ".html", ".txt"]):
            continue

        if any(skip in href_lower for skip in [
            "xslf345x",
            "xslform",
            ".xml",
            "ex-",
            "exhibit",
            "_cal.",
            "_def.",
            "_lab.",
            "_pre.",
        ]):
            continue

        return _normalize_sec_url(index_url, href)

    return None


def _fetch_filing_text_and_document_url(index_url: str, form_type: str) -> tuple[str, str | None, str | None]:
    """
    Returns:
    - cleaned filing document text
    - display document URL
    - raw document URL actually used for parsing

    Important: SEC sometimes gives an inline viewer URL. We display the viewer
    URL if available, but parse the normalized raw archive URL.
    """
    try:
        response = requests.get(
            index_url,
            timeout=20,
            headers=REQUEST_HEADERS,
        )
        response.raise_for_status()
        detail_html = response.text

        document_url = _find_primary_document_url(index_url, detail_html, form_type)

        if not document_url:
            return _clean(detail_html)[:15000], None, None

        raw_document_url = _normalize_inline_viewer_url(document_url) or document_url

        doc_response = requests.get(
            raw_document_url,
            timeout=20,
            headers=REQUEST_HEADERS,
        )
        doc_response.raise_for_status()

        return _clean(doc_response.text)[:40000], document_url, raw_document_url

    except Exception:
        return "", None, None


def _detect_sec_items(text: str) -> list[str]:
    detected: list[str] = []

    # Normalize common SEC/iXBRL spacing variants before matching.
    normalized = text.lower()
    normalized = normalized.replace("\xa0", " ")
    normalized = re.sub(r"\s+", " ", normalized)

    for item_no in SEC_ITEM_PATTERNS:
        number = item_no.replace("Item ", "")
        escaped_number = re.escape(number)

        patterns = [
            rf"\bitem\s+{escaped_number}\b",
            rf"\bitem\s*{escaped_number}\s*\([a-z]\)",
            rf"\bitem\s+{escaped_number.replace(r'\.', r'\s*\.\s*')}\b",
            rf"\b{escaped_number}\s+[a-z ]{{0,50}}{re.escape(SEC_ITEM_PATTERNS[item_no][1].split()[0].lower())}",
        ]

        if any(re.search(pattern, normalized, flags=re.I) for pattern in patterns):
            detected.append(item_no)

    return detected


def _extract_signal(
    ticker: str,
    company: str | None,
    form_type: str,
    title: str,
    summary: str,
    filing_text: str,
) -> tuple[str, str, list[str], int, str]:
    combined = f"{title} {summary} {filing_text}".lower()
    company_name = company or ticker

    signal_type = FORM_CATEGORY.get(form_type, "SEC Filing")
    signal_summary = f"{ticker} filed {form_type} with the SEC."
    items_detected = _detect_sec_items(filing_text)
    score_bonus = 0
    reasons: list[str] = []

    for item_no in items_detected:
        item_signal_type, item_description, weight = SEC_ITEM_PATTERNS[item_no]

        if item_no != "Item 9.01" or signal_type == FORM_CATEGORY.get(form_type, "SEC Filing"):
            signal_type = item_signal_type

        score_bonus += weight
        reasons.append(f"{item_no}: {item_description}")

    keyword_hits: list[tuple[str, str, int]] = []

    for keyword, (keyword_type, keyword_description, weight) in KEYWORD_SIGNALS.items():
        if keyword in combined:
            keyword_hits.append((keyword_type, keyword_description, weight))

    if keyword_hits:
        keyword_hits = sorted(keyword_hits, key=lambda row: row[2], reverse=True)
        top_type, top_description, top_weight = keyword_hits[0]

        if not items_detected or top_weight >= 34:
            signal_type = top_type

        score_bonus += top_weight
        reasons.append(top_description)

    if signal_type == "Guidance" and not any(phrase in combined for phrase in GUIDANCE_CONTEXT_TERMS):
        signal_type = FORM_CATEGORY.get(form_type, "SEC Filing")
        score_bonus = max(0, score_bonus - 34)
        reasons.append("generic guidance term discounted")

    if form_type == "8-K":
        if "Item 5.02" in items_detected or signal_type == "Leadership / Governance":
            signal_summary = f"{company_name} disclosed executive leadership, board, or officer-related governance updates."
        elif "Item 2.02" in items_detected or signal_type == "Earnings / Results":
            signal_summary = f"{company_name} furnished results of operations or financial condition disclosure."
        elif "Item 1.01" in items_detected or signal_type == "Material Agreement":
            signal_summary = f"{company_name} disclosed a material agreement or contract-related event."
        elif "Item 2.05" in items_detected or signal_type == "Restructuring":
            signal_summary = f"{company_name} disclosed restructuring or exit-cost related information."
        elif signal_type == "Capital Return":
            signal_summary = f"{company_name} disclosed capital return activity such as buybacks or dividends."
        elif items_detected:
            signal_summary = f"{company_name} filed an 8-K current report with SEC items detected: {', '.join(items_detected)}."
        else:
            signal_summary = (
                f"{company_name} filed an 8-K current report. "
                f"The filing was flagged as material, but no specific SEC item was extracted from the available filing text."
            )

    elif form_type == "4":
        signal_type = "Insider Transaction"
        signal_summary = f"{company_name} reported insider transaction activity through a Form 4 filing."

    elif form_type in {"10-Q", "10-K"}:
        signal_type = FORM_CATEGORY.get(form_type, "Periodic Filing")
        signal_summary = f"{company_name} filed a {form_type} periodic report containing updated financial and risk disclosures."

    elif form_type == "DEF 14A":
        signal_type = "Proxy / Governance"
        signal_summary = f"{company_name} filed proxy materials with governance, compensation, and shareholder voting information."

    reason = ", ".join(dict.fromkeys(reasons))

    return signal_type, signal_summary, items_detected, score_bonus, reason


def _score_filing(
    form_type: str,
    signal_bonus: int,
    signal_reason: str,
) -> tuple[int, str, str, str]:
    score = FORM_PRIORITY.get(form_type, 20)
    reasons: list[str] = [f"{form_type} filing"]

    if signal_bonus:
        score += signal_bonus

    if signal_reason:
        reasons.append(signal_reason)

    category = FORM_CATEGORY.get(form_type, "SEC Filing")

    if form_type == "8-K":
        score += 15
        reasons.append("material-event filing")

    if form_type == "4":
        score += 8
        reasons.append("insider transaction filing")

    if score >= 90:
        confidence = "High"
    elif score >= 60:
        confidence = "Medium"
    else:
        confidence = "Low"

    return score, confidence, category, ", ".join(dict.fromkeys(reasons))


def _fetch_sec_atom(
    ticker: str,
    cik: str,
    lookback_days: int,
    fetch_full_text: bool = True,
) -> list[SecFiling]:
    url = _sec_atom_url(cik)
    out: list[SecFiling] = []

    try:
        response = requests.get(
            url,
            timeout=20,
            headers={**REQUEST_HEADERS, "Host": "www.sec.gov"},
        )
        response.raise_for_status()

        root = ET.fromstring(response.text)
        namespace = {"atom": "http://www.w3.org/2005/Atom"}

        company = None
        company_title = root.findtext("atom:title", default="", namespaces=namespace)
        if company_title:
            company = company_title.replace("Company Filings", "").strip(" -")

        for entry in root.findall("atom:entry", namespace):
            title = _clean(entry.findtext("atom:title", default="", namespaces=namespace))
            summary = _clean(entry.findtext("atom:summary", default="", namespaces=namespace))
            updated = _parse_date(entry.findtext("atom:updated", default="", namespaces=namespace))

            link = ""
            link_element = entry.find("atom:link", namespace)
            if link_element is not None:
                link = link_element.attrib.get("href", "")

            if not title or not link:
                continue

            if not _is_recent(updated, lookback_days):
                continue

            form_type = _extract_form_type(title)

            if form_type not in FORM_PRIORITY:
                continue

            filing_text = ""
            document_url: str | None = None
            raw_document_url: str | None = None

            if fetch_full_text and form_type in {"8-K", "4", "10-Q", "10-K", "DEF 14A"}:
                filing_text, document_url, raw_document_url = _fetch_filing_text_and_document_url(link, form_type)

            signal_type, signal_summary, items_detected, signal_bonus, signal_reason = _extract_signal(
                ticker=ticker,
                company=company,
                form_type=form_type,
                title=title,
                summary=summary,
                filing_text=filing_text,
            )

            score, confidence, category, reason = _score_filing(
                form_type=form_type,
                signal_bonus=signal_bonus,
                signal_reason=signal_reason,
            )

            if score < 45:
                continue

            out.append(
                SecFiling(
                    ticker=ticker,
                    company=company,
                    form_type=form_type,
                    title=title,
                    url=link,
                    document_url=document_url,
                    raw_document_url=raw_document_url,
                    filed_at=updated,
                    source="SEC EDGAR",
                    relevance_score=score,
                    confidence=confidence,
                    category=category,
                    reason=reason,
                    signal_type=signal_type,
                    signal_summary=signal_summary,
                    items_detected=items_detected,
                )
            )

    except Exception:
        return []

    return out


def get_sec_filings(
    tickers: list[str],
    lookback_days: int = 14,
    max_filings_per_ticker: int = 3,
    fetch_full_text: bool = True,
) -> list[SecFiling]:
    filings: list[SecFiling] = []

    for raw_ticker in tickers:
        ticker = raw_ticker.upper().strip()
        cik = TICKER_CIK_MAP.get(ticker)

        if not cik:
            continue

        ticker_filings = _fetch_sec_atom(
            ticker=ticker,
            cik=cik,
            lookback_days=lookback_days,
            fetch_full_text=fetch_full_text,
        )

        ticker_filings = sorted(
            ticker_filings,
            key=lambda item: (item.relevance_score, item.filed_at or ""),
            reverse=True,
        )

        filings.extend(ticker_filings[:max_filings_per_ticker])

    return sorted(
        filings,
        key=lambda item: (item.relevance_score, item.filed_at or ""),
        reverse=True,
    )


def sec_filings_as_dicts(items: list[SecFiling]) -> list[dict[str, Any]]:
    return [item.__dict__ for item in items]
