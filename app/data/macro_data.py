from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from app.config.settings import settings


@dataclass(frozen=True)
class MacroStateItem:
    name: str
    actual: float | None
    prior: float | None
    unit: str
    date: str | None
    source: str
    note: str
    latest_display: str | None = None
    prior_display: str | None = None
    change_display: str | None = None
    change_label: str | None = None
    latest_label: str | None = None
    prior_label: str | None = None


@dataclass(frozen=True)
class EconomicCalendarEvent:
    name: str
    country: str
    date: str | None
    actual: float | None
    consensus: float | None
    prior: float | None
    unit: str | None
    importance: str | None
    source: str
    note: str


@dataclass(frozen=True)
class MacroSnapshot:
    macro_state: list[MacroStateItem]
    economic_calendar_today: list[EconomicCalendarEvent]
    economic_calendar_tomorrow: list[EconomicCalendarEvent]
    fed_updates: list[str]
    source_note: str


FRED_SERIES = {
    "CPI": {"series_id": "CPIAUCSL", "name": "Consumer Price Index", "unit": "index", "display_type": "monthly_index"},
    "PPI": {"series_id": "PPIACO", "name": "Producer Price Index", "unit": "index", "display_type": "monthly_index"},
    "PAYROLLS": {"series_id": "PAYEMS", "name": "Nonfarm Payrolls", "unit": "thousands", "display_type": "payrolls"},
    "RETAIL_SALES": {"series_id": "RSXFS", "name": "Retail Sales", "unit": "millions USD", "display_type": "monthly_level"},
    "GDP": {"series_id": "GDP", "name": "Gross Domestic Product", "unit": "billions USD", "display_type": "quarterly_level"},
    "CONSUMER_SENTIMENT": {"series_id": "UMCSENT", "name": "University of Michigan Consumer Sentiment", "unit": "index", "display_type": "survey_index"},
    "FED_FUNDS": {"series_id": "FEDFUNDS", "name": "Effective Federal Funds Rate", "unit": "percent", "display_type": "rate"},
}


def _fred_api_key() -> str | None:
    return getattr(settings, "fred_api_key", None)


def _to_float(value: Any) -> float | None:
    try:
        if value in (None, ".", "", "NA", "N/A"):
            return None
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", "").strip()
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.2f}%"


def _fmt_rate(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}%"


def _fmt_level(value: float | None) -> str:
    if value is None:
        return "N/A"
    if abs(value) >= 1000:
        return f"{value:,.1f}"
    return f"{value:.2f}"


def _fmt_jobs(value: float | None) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(value):,.0f}K"


def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return ((current / previous) - 1.0) * 100.0


def _fetch_fred_observations(series_id: str, limit: int = 18) -> list[dict[str, Any]]:
    api_key = _fred_api_key()
    if not api_key:
        return []

    try:
        response = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": limit,
            },
            timeout=15,
        )
        data = response.json()
        observations = data.get("observations", [])
        return [obs for obs in observations if obs.get("value") not in (None, ".")]
    except Exception:
        return []


def _build_display(
    display_type: str,
    values: list[float | None],
) -> tuple[str | None, str | None, str | None, str | None, str, str, str]:
    actual = values[0] if len(values) > 0 else None
    prior = values[1] if len(values) > 1 else None

    if display_type == "monthly_index":
        mom = _pct_change(actual, prior)
        yoy = _pct_change(actual, values[12] if len(values) > 12 else None)
        prior_yoy = _pct_change(prior, values[13] if len(values) > 13 else None)
        latest_display = _fmt_pct(yoy)
        prior_display = _fmt_pct(prior_yoy)
        change_display = _fmt_pct(mom)
        note = f"Latest reading implies {latest_display} year-over-year change; month-over-month change was {change_display}."
        return latest_display, prior_display, change_display, "MoM", note, "Latest YoY", "Prior YoY"

    if display_type == "monthly_level":
        mom = _pct_change(actual, prior)
        yoy = _pct_change(actual, values[12] if len(values) > 12 else None)
        prior_yoy = _pct_change(prior, values[13] if len(values) > 13 else None)
        latest_display = _fmt_pct(yoy)
        prior_display = _fmt_pct(prior_yoy)
        change_display = _fmt_pct(mom)
        note = f"Latest level implies {latest_display} year-over-year change; sequential change was {change_display}."
        return latest_display, prior_display, change_display, "MoM", note, "Latest YoY", "Prior YoY"

    if display_type == "payrolls":
        payrolls_added = actual - prior if actual is not None and prior is not None else None
        prior_payrolls_added = None
        if len(values) > 2 and values[1] is not None and values[2] is not None:
            prior_payrolls_added = values[1] - values[2]
        latest_display = _fmt_jobs(payrolls_added)
        prior_display = _fmt_jobs(prior_payrolls_added)
        change_vs_prior = None
        if payrolls_added is not None and prior_payrolls_added is not None:
            change_vs_prior = payrolls_added - prior_payrolls_added
        change_display = _fmt_jobs(change_vs_prior)
        note = f"Nonfarm payroll employment increased by {latest_display} jobs in the latest reading; the prior monthly gain was {prior_display}."
        return latest_display, prior_display, change_display, "vs Prior", note, "Jobs Added", "Prior Added"

    if display_type == "quarterly_level":
        qoq = _pct_change(actual, prior)
        annualized = None if qoq is None else (((1 + qoq / 100.0) ** 4) - 1) * 100.0
        yoy = _pct_change(actual, values[4] if len(values) > 4 else None)
        prior_yoy = _pct_change(prior, values[5] if len(values) > 5 else None)
        latest_display = _fmt_pct(yoy)
        prior_display = _fmt_pct(prior_yoy)
        change_display = _fmt_pct(annualized)
        note = f"Latest GDP level implies {latest_display} year-over-year change; quarter-over-quarter annualized change was {change_display}."
        return latest_display, prior_display, change_display, "QoQ Ann.", note, "Latest YoY", "Prior YoY"

    if display_type == "rate":
        bp_change = (actual - prior) * 100.0 if actual is not None and prior is not None else None
        latest_display = _fmt_rate(actual)
        prior_display = _fmt_rate(prior)
        change_display = "N/A" if bp_change is None else f"{bp_change:+.0f} bps"
        note = f"Effective federal funds rate was {latest_display}; change versus prior reading was {change_display}."
        return latest_display, prior_display, change_display, "Change", note, "Latest", "Prior"

    latest_display = _fmt_level(actual)
    prior_display = _fmt_level(prior)
    point_change = None if actual is None or prior is None else actual - prior
    change_display = "N/A" if point_change is None else f"{point_change:+.1f} pts"
    direction = "increased" if point_change and point_change > 0 else "declined" if point_change and point_change < 0 else "was unchanged"
    note = f"{latest_display} latest reading; sentiment {direction} versus the prior reported reading."
    return latest_display, prior_display, change_display, "Change", note, "Latest", "Prior"


def get_macro_state_snapshot() -> list[MacroStateItem]:
    state: list[MacroStateItem] = []

    for config in FRED_SERIES.values():
        observations = _fetch_fred_observations(config["series_id"], limit=18)
        if not observations:
            continue

        values = [_to_float(obs.get("value")) for obs in observations]
        latest = observations[0]
        actual = values[0] if len(values) > 0 else None
        prior = values[1] if len(values) > 1 else None

        latest_display, prior_display, change_display, change_label, note, latest_label, prior_label = _build_display(
            config["display_type"], values
        )

        state.append(
            MacroStateItem(
                name=config["name"],
                actual=actual,
                prior=prior,
                unit=config["unit"],
                date=latest.get("date"),
                source=f"FRED ({config['series_id']})",
                note=note,
                latest_display=latest_display,
                prior_display=prior_display,
                change_display=change_display,
                change_label=change_label,
                latest_label=latest_label,
                prior_label=prior_label,
            )
        )

    return state


def get_economic_calendar() -> tuple[list[EconomicCalendarEvent], list[EconomicCalendarEvent]]:
    return [], []


def get_macro_snapshot() -> MacroSnapshot:
    macro_state = get_macro_state_snapshot()
    today_events, tomorrow_events = get_economic_calendar()

    fed_updates = [
        "Federal Reserve policy-rate proxy included via FRED effective federal funds rate.",
        "Institutional macro-calendar integrations are not configured in the current version; event timing and consensus estimates are disabled.",
    ]

    if not _fred_api_key():
        fed_updates.append("FRED_API_KEY is not configured; official macro actuals may be incomplete.")

    source_note = "Macro state via FRED. Economic-calendar timing and consensus estimates require a paid or manually maintained calendar source."

    return MacroSnapshot(
        macro_state=macro_state,
        economic_calendar_today=today_events,
        economic_calendar_tomorrow=tomorrow_events,
        fed_updates=fed_updates,
        source_note=source_note,
    )


def get_macro_calendar_stub() -> list[dict[str, Any]]:
    snapshot = get_macro_snapshot()
    return [event.__dict__ for event in snapshot.economic_calendar_today]
