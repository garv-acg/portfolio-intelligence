from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.portfolio import load_portfolio
from app.config.settings import settings
from app.data.market_data import (
    get_equity_snapshot,
    get_index_snapshot,
    snapshot_as_dataframe,
)

try:
    import plotly.graph_objects as go
except ImportError:
    go = None


st.set_page_config(
    page_title="Daily Market Brief",
    page_icon="📈",
    layout="wide",
)

st.markdown(
    """
    <style>
        .stApp {
            background: #070b12;
            color: #e5e7eb;
        }

        [data-testid="stHeader"] {
            background: rgba(7, 11, 18, 0);
        }

        .block-container {
            padding-top: 1.1rem;
            padding-bottom: 2rem;
            max-width: 1450px;
        }

        /* ── Header bar ── */
        .header-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: .65rem;
        }
        .dashboard-title {
            font-size: 1rem;
            letter-spacing: .10em;
            text-transform: uppercase;
            color: #60a5fa;
            font-weight: 850;
        }
        .dashboard-meta {
            color: #64748b;
            font-size: .78rem;
        }
        .freshness-dot {
            display: inline-block;
            width: 7px; height: 7px;
            border-radius: 50%;
            margin-right: 5px;
            vertical-align: middle;
        }
        .dot-live  { background: #22c55e; box-shadow: 0 0 5px #22c55e88; }
        .dot-stale { background: #f59e0b; }
        .dot-dead  { background: #ef4444; }

        /* ── Index ticker strip ── */
        .ticker-strip {
            display: flex;
            gap: 20px;
            align-items: center;
            background: linear-gradient(90deg, #0d1827 0%, #0a1220 100%);
            border: 1px solid #1e3a5f;
            border-radius: 10px;
            padding: 7px 14px;
            margin-bottom: .65rem;
            flex-wrap: wrap;
        }
        .ticker-strip-label {
            font-size: .68rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .09em;
            color: #475569;
            margin-right: 4px;
        }
        .ticker-item {
            display: flex;
            align-items: baseline;
            gap: 5px;
        }
        .ticker-sym {
            font-size: .78rem;
            font-weight: 700;
            color: #cbd5e1;
        }
        .ticker-price {
            font-size: .76rem;
            color: #94a3b8;
        }
        .ticker-chg {
            font-size: .76rem;
            font-weight: 700;
        }

        /* ── KPI cards ── */
        .kpi-card {
            background: linear-gradient(135deg, #111827 0%, #132238 100%);
            border: 1px solid #253246;
            border-radius: 14px;
            padding: 15px 16px;
            box-shadow: 0 12px 28px rgba(0,0,0,.22);
            min-height: 104px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .kpi-label {
            color: #cbd5e1;
            font-size: .70rem;
            font-weight: 850;
            text-transform: uppercase;
            letter-spacing: .045em;
            line-height: 1.25;
        }
        .kpi-value {
            font-size: 1.42rem;
            font-weight: 850;
            color: #f8fafc;
            line-height: 1.12;
            margin-top: .35rem;
        }
        .kpi-note {
            color: #94a3b8;
            font-size: .74rem;
            margin-top: .35rem;
            line-height: 1.25;
            min-height: 16px;
        }

        .positive { color: #22c55e !important; }
        .negative { color: #ef4444 !important; }
        .neutral  { color: #cbd5e1 !important; }

        /* ── Chart headers ── */
        .chart-title {
            color: #dbeafe;
            font-size: .82rem;
            font-weight: 850;
            text-transform: uppercase;
            letter-spacing: .04em;
            margin-bottom: .10rem;
        }
        .chart-subtitle {
            color: #64748b;
            font-size: .72rem;
            margin-bottom: .45rem;
        }

        /* ── Macro pulse ── */
        .macro-strip {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            margin-bottom: .65rem;
        }
        .macro-cell {
            flex: 1;
            min-width: 130px;
            background: linear-gradient(135deg, #12100a 0%, #1a1500 100%);
            border: 1px solid #3d2e0044;
            border-radius: 12px;
            padding: 11px 14px;
        }
        .macro-cell-label {
            font-size: .67rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .08em;
            color: #92400e;
            margin-bottom: 4px;
        }
        .macro-cell-value {
            font-size: 1.05rem;
            font-weight: 800;
            color: #fcd34d;
        }
        .macro-cell-note {
            font-size: .68rem;
            color: #78716c;
            margin-top: 3px;
        }

        /* ── Newsletter preview ── */
        .nl-preview {
            background: #0a0f1a;
            border: 1px solid #1e293b;
            border-radius: 12px;
            padding: 14px 16px;
            font-size: .80rem;
            color: #94a3b8;
            line-height: 1.6;
            white-space: pre-wrap;
            max-height: 320px;
            overflow-y: auto;
        }
        .nl-preview-title {
            font-size: .80rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .07em;
            color: #60a5fa;
            margin-bottom: 8px;
        }

        .section-gap { height: .65rem; }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: linear-gradient(135deg, #0f172a 0%, #101b2b 100%);
            border: 1px solid #26364d !important;
            border-radius: 16px !important;
            box-shadow: 0 12px 28px rgba(0,0,0,.22);
            padding: 0 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            padding: 14px 16px 10px 16px !important;
        }
        div[data-testid="stDataFrame"] {
            border: 1px solid #26364d;
            border-radius: 12px;
            overflow: hidden;
        }
        .footer-note {
            color: #64748b;
            font-size: .76rem;
            margin-top: .5rem;
        }
        [data-testid="stPlotlyChart"] { margin-top: -2px; }
        .stDataFrame { font-size: .82rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt_money(value: Any) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"${float(value):,.2f}"


def _fmt_pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):+.2f}%"


def _class_for_value(value: Any) -> str:
    if value is None or pd.isna(value):
        return "neutral"
    value = float(value)
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


def _round_column(df: pd.DataFrame, column: str, decimals: int = 2) -> pd.DataFrame:
    if column in df.columns:
        df[column] = df[column].map(lambda x: None if pd.isna(x) else round(float(x), decimals))
    return df


def _holding_attr_map(holdings: list[Any]) -> dict[str, dict[str, Any]]:
    data: dict[str, dict[str, Any]] = {}
    for holding in holdings:
        ticker = str(getattr(holding, "ticker", "")).upper()
        data[ticker] = {
            "sector": getattr(holding, "sector", "Unclassified"),
            "asset_class": getattr(holding, "asset_class", "Equity"),
        }
    return data


def _infer_sector(ticker: str, existing: str | None = None) -> str:
    if existing and existing != "Unclassified":
        return existing
    fallback = {
        "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology",
        "AVGO": "Technology", "AMZN": "Consumer Discretionary",
        "GOOGL": "Communication Services", "GOOG": "Communication Services",
        "META": "Communication Services", "SPOT": "Communication Services",
        "GE": "Industrials", "JPM": "Financials", "V": "Financials",
        "MA": "Financials", "TSLA": "Consumer Discretionary",
    }
    return fallback.get(str(ticker).upper(), "Unclassified")


def _prepare_portfolio_df(portfolio_df: pd.DataFrame, holdings: list[Any]) -> pd.DataFrame:
    if portfolio_df.empty:
        return portfolio_df

    df = portfolio_df.copy()
    attr_map = _holding_attr_map(holdings)

    if "sector" not in df.columns:
        df["sector"] = df["ticker"].map(lambda t: attr_map.get(str(t).upper(), {}).get("sector", "Unclassified"))
    df["sector"] = df.apply(lambda row: _infer_sector(row.get("ticker"), row.get("sector")), axis=1)

    if "asset_class" not in df.columns:
        df["asset_class"] = df["ticker"].map(lambda t: attr_map.get(str(t).upper(), {}).get("asset_class", "Equity"))

    if "market_value" in df.columns:
        total_value = df["market_value"].dropna().sum()
        df["portfolio_weight"] = df["market_value"].map(
            lambda x: None if pd.isna(x) or total_value == 0 else float(x) / float(total_value)
        )

    if "daily_pl" not in df.columns and {"price", "previous_close", "shares"}.issubset(df.columns):
        df["daily_pl"] = df.apply(
            lambda row: None
            if pd.isna(row.get("price")) or pd.isna(row.get("previous_close")) or pd.isna(row.get("shares"))
            else (float(row["price"]) - float(row["previous_close"])) * float(row["shares"]),
            axis=1,
        )

    return df


def _plotly_layout(fig, height: int = 315, showlegend: bool = True):
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#dbeafe", size=11),
        margin=dict(l=8, r=8, t=10, b=8),
        showlegend=showlegend,
        legend=dict(
            orientation="v", yanchor="middle", y=0.5,
            xanchor="left", x=1.02,
            font=dict(size=11, color="#cbd5e1"),
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    return fig


def _bar_color_series(values: pd.Series) -> list[str]:
    return [
        "#64748b" if pd.isna(v) else ("#22c55e" if float(v) >= 0 else "#ef4444")
        for v in values
    ]


def _kpi_card(label: str, value: str, note: str = "", value_class: str = "neutral") -> None:
    st.markdown(
        f"""
        <div class="kpi-card">
            <div>
                <div class="kpi-label">{label}</div>
                <div class="kpi-value {value_class}">{value}</div>
            </div>
            <div class="kpi-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _chart_header(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="chart-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="chart-subtitle">{subtitle}</div>', unsafe_allow_html=True)


# ── Load data ─────────────────────────────────────────────────────────────────

holdings = load_portfolio(settings.portfolio_file)
portfolio_moves = get_equity_snapshot(holdings)
portfolio_df = snapshot_as_dataframe(portfolio_moves)
portfolio_df = _prepare_portfolio_df(portfolio_df, holdings)

total_value = portfolio_df["market_value"].dropna().sum() if "market_value" in portfolio_df.columns and not portfolio_df.empty else None
daily_pl = portfolio_df["daily_pl"].dropna().sum() if "daily_pl" in portfolio_df.columns and not portfolio_df.empty else None

weighted_move = None
if not portfolio_df.empty and "market_value" in portfolio_df.columns and "day_change_pct" in portfolio_df.columns and total_value:
    priced = portfolio_df.dropna(subset=["market_value", "day_change_pct"])
    if not priced.empty:
        weighted_move = (priced["market_value"] * priced["day_change_pct"]).sum() / total_value

best = worst = None
if not portfolio_df.empty and "day_change_pct" in portfolio_df.columns:
    movers = portfolio_df.dropna(subset=["day_change_pct"]).copy()
    if not movers.empty:
        best = movers.sort_values("day_change_pct", ascending=False).iloc[0]
        worst = movers.sort_values("day_change_pct", ascending=True).iloc[0]

index_snapshot = get_index_snapshot()

# Freshness: check most recent as_of across portfolio
freshness_times = [r.get("as_of") for r in portfolio_moves if r.get("as_of")]
most_recent_as_of = max(freshness_times) if freshness_times else None
data_age_min = None
if most_recent_as_of:
    try:
        ts = datetime.fromisoformat(most_recent_as_of)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        data_age_min = (datetime.now(timezone.utc) - ts).total_seconds() / 60
    except Exception:
        pass

# ── Rec 6: Header bar ─────────────────────────────────────────────────────────

now_str = datetime.now().strftime("%a %b %-d, %Y · %-I:%M %p")
if data_age_min is None:
    dot_cls, freshness_label = "dot-dead", "No data"
elif data_age_min < 15:
    dot_cls, freshness_label = "dot-live", f"Live · {int(data_age_min)}m ago"
elif data_age_min < 120:
    dot_cls, freshness_label = "dot-stale", f"Cached · {int(data_age_min)}m ago"
else:
    dot_cls, freshness_label = "dot-dead", f"Stale · {int(data_age_min // 60)}h ago"

hdr_left, hdr_right = st.columns([5, 1])
with hdr_left:
    st.markdown(
        f"""
        <div class="header-bar">
            <div class="dashboard-title">📈 Daily Market Brief</div>
            <div class="dashboard-meta">
                {now_str} &nbsp;·&nbsp;
                <span class="freshness-dot {dot_cls}"></span>{freshness_label}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with hdr_right:
    if st.button("⚡ Send Newsletter", use_container_width=True, type="primary"):
        with st.spinner("Sending…"):
            try:
                result = subprocess.run(
                    [sys.executable, str(PROJECT_ROOT / "send_newsletter.py")],
                    capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=60,
                )
                if result.returncode == 0:
                    st.success("Sent!")
                else:
                    st.error(f"Send failed:\n{result.stderr[:400]}")
            except Exception as e:
                st.error(f"Error: {e}")

# ── Rec 1: Index ticker strip ─────────────────────────────────────────────────

INDEX_DISPLAY = {
    "^GSPC": "S&P 500",
    "^IXIC": "Nasdaq",
    "^DJI": "Dow",
    "^TNX": "10Y Yld",
    "CL=F": "WTI Oil",
    "GC=F": "Gold",
    "DX-Y.NYB": "DXY",
}

ticker_cells = []
for ticker, label in INDEX_DISPLAY.items():
    move = index_snapshot.get(
        next((name for name, m in index_snapshot.items() if m.ticker == ticker), None), None
    )
    # look up by ticker directly
    move = next((m for m in index_snapshot.values() if m.ticker == ticker), None)
    if move is None:
        continue
    price_str = f"{move.price:,.2f}" if move.price else "—"
    if move.day_change_pct is not None:
        cls = "positive" if move.day_change_pct >= 0 else "negative"
        chg_str = f"{move.day_change_pct:+.2f}%"
    else:
        cls = "neutral"
        chg_str = "—"
    ticker_cells.append(
        f'<div class="ticker-item">'
        f'<span class="ticker-sym">{label}</span>'
        f'<span class="ticker-price">{price_str}</span>'
        f'<span class="ticker-chg {cls}">{chg_str}</span>'
        f'</div>'
    )

st.markdown(
    '<div class="ticker-strip">'
    '<span class="ticker-strip-label">Markets</span>'
    + "".join(ticker_cells)
    + "</div>",
    unsafe_allow_html=True,
)

# ── Rec 3: KPI cards (4, merged P/L + move) ──────────────────────────────────

# Build a 5th KPI: VIX from index snapshot
vix_move = next((m for m in index_snapshot.values() if "VIX" in m.ticker.upper()), None)
# Fallback: show portfolio beta placeholder text
fifth_label = "VIX" if vix_move and vix_move.price else "Holdings"
fifth_value = f"{vix_move.price:.2f}" if vix_move and vix_move.price else str(len(holdings))
fifth_note = _fmt_pct(vix_move.day_change_pct) if vix_move and vix_move.price else "positions"
fifth_class = _class_for_value(vix_move.day_change_pct if vix_move else None) if vix_move and vix_move.price else "neutral"

k1, k2, k3, k4, k5 = st.columns(5, gap="medium")
with k1:
    _kpi_card("Portfolio Value", _fmt_money(total_value), "Priced holdings")
with k2:
    # Merged P/L card: $ + %
    pl_str = _fmt_money(daily_pl)
    pct_str = _fmt_pct(weighted_move)
    _kpi_card("Today's P/L", pl_str, pct_str, _class_for_value(daily_pl))
with k3:
    if best is not None:
        _kpi_card("Best Today", str(best["ticker"]), _fmt_pct(best["day_change_pct"]), "positive")
    else:
        _kpi_card("Best Today", "N/A")
with k4:
    if worst is not None:
        _kpi_card("Worst Today", str(worst["ticker"]), _fmt_pct(worst["day_change_pct"]), "negative")
    else:
        _kpi_card("Worst Today", "N/A")
with k5:
    _kpi_card(fifth_label, fifth_value, fifth_note, fifth_class)

st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)

# ── Charts ────────────────────────────────────────────────────────────────────

if go is None:
    st.warning("Install Plotly for charts: python -m pip install plotly")
else:
    row1_left, row1_right = st.columns([1, 1.15], gap="medium")

    with row1_left:
        with st.container(border=True):
            _chart_header("Allocation by Holding", "Market value by position")
            allocation_df = (
                portfolio_df.dropna(subset=["market_value"]).copy()
                if not portfolio_df.empty and "market_value" in portfolio_df.columns
                else pd.DataFrame()
            )

            if allocation_df.empty:
                st.info("No market values available.")
            else:
                allocation_df = allocation_df.sort_values("market_value", ascending=False)
                allocation_df["weight_pct"] = allocation_df["market_value"] / allocation_df["market_value"].sum() * 100

                fig = go.Figure(data=[go.Pie(
                    labels=allocation_df["ticker"],
                    values=allocation_df["market_value"],
                    hole=0.58,
                    textinfo="percent",
                    textposition="inside",
                    hovertemplate="%{label}<br>$%{value:,.2f}<br>%{percent}<extra></extra>",
                )])
                fig = _plotly_layout(fig, height=268, showlegend=True)
                fig.update_traces(
                    marker=dict(line=dict(color="#0f172a", width=2)),
                    textfont=dict(color="#ffffff", size=11),
                )
                st.plotly_chart(fig, use_container_width=True, key="allocation_donut")

                table_df = allocation_df[["ticker", "market_value", "weight_pct"]].copy()
                table_df["market_value"] = table_df["market_value"].map(_fmt_money)
                table_df["weight_pct"] = table_df["weight_pct"].map(lambda x: f"{x:.1f}%")
                st.dataframe(
                    table_df.rename(columns={"ticker": "Holding", "market_value": "Market Value", "weight_pct": "Weight"}),
                    use_container_width=True, hide_index=True, height=152,
                )

    with row1_right:
        with st.container(border=True):
            _chart_header("Sector Exposure", "% of market value")
            sector_df = (
                portfolio_df.dropna(subset=["market_value"]).copy()
                if not portfolio_df.empty and "market_value" in portfolio_df.columns
                else pd.DataFrame()
            )

            if sector_df.empty:
                st.info("No market values available.")
            else:
                sector_grouped = (
                    sector_df.groupby("sector", dropna=False)["market_value"]
                    .sum().reset_index()
                    .sort_values("market_value", ascending=True)
                )
                sector_grouped["weight_pct"] = sector_grouped["market_value"] / sector_grouped["market_value"].sum() * 100

                fig = go.Figure(go.Bar(
                    x=sector_grouped["weight_pct"],
                    y=sector_grouped["sector"],
                    orientation="h",
                    text=sector_grouped["weight_pct"].map(lambda x: f"{x:.1f}%"),
                    textposition="outside",
                    hovertemplate="%{y}<br>%{x:.1f}% of portfolio<extra></extra>",
                    marker=dict(color="#3b82f6"),
                    cliponaxis=False,
                ))
                fig = _plotly_layout(fig, height=405, showlegend=False)
                fig.update_xaxes(
                    title=None, gridcolor="#1f2937", zerolinecolor="#334155",
                    ticksuffix="%",
                    range=[0, max(60, sector_grouped["weight_pct"].max() * 1.18)],
                )
                fig.update_yaxes(title=None)
                st.plotly_chart(fig, use_container_width=True, key="sector_exposure")

    st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)

    # ── Rec 2: Merged performance chart with USD/% toggle ────────────────────

    with st.container(border=True):
        _chart_header("Performance by Holding", "Daily change per position")

        perf_mode = st.radio(
            "View",
            ["USD ($)", "Percent (%)"],
            horizontal=True,
            label_visibility="collapsed",
            key="perf_toggle",
        )

        if perf_mode == "USD ($)":
            perf_df = portfolio_df.dropna(subset=["daily_pl"]).copy() if not portfolio_df.empty and "daily_pl" in portfolio_df.columns else pd.DataFrame()
            if perf_df.empty:
                st.info("No daily P/L data available.")
            else:
                perf_df = perf_df.sort_values("daily_pl")
                max_abs = max(abs(perf_df["daily_pl"].min()), abs(perf_df["daily_pl"].max()))
                fig = go.Figure(go.Bar(
                    x=perf_df["ticker"], y=perf_df["daily_pl"],
                    text=perf_df["daily_pl"].map(lambda x: f"${x:,.2f}"),
                    textposition="outside",
                    marker=dict(color=_bar_color_series(perf_df["daily_pl"])),
                    hovertemplate="%{x}<br>$%{y:,.2f}<extra></extra>",
                    cliponaxis=False,
                ))
                fig = _plotly_layout(fig, height=290, showlegend=False)
                fig.update_yaxes(title=None, gridcolor="#1f2937", zerolinecolor="#64748b",
                                  range=[-max_abs * 1.35, max_abs * 1.35] if max_abs else None)
                fig.update_xaxes(title=None)
                st.plotly_chart(fig, use_container_width=True, key="perf_usd")
        else:
            perf_df = portfolio_df.dropna(subset=["day_change_pct"]).copy() if not portfolio_df.empty and "day_change_pct" in portfolio_df.columns else pd.DataFrame()
            if perf_df.empty:
                st.info("No daily move data available.")
            else:
                perf_df = perf_df.sort_values("day_change_pct")
                max_abs = max(abs(perf_df["day_change_pct"].min()), abs(perf_df["day_change_pct"].max()))
                fig = go.Figure(go.Bar(
                    x=perf_df["ticker"], y=perf_df["day_change_pct"],
                    text=perf_df["day_change_pct"].map(lambda x: f"{x:+.2f}%"),
                    textposition="outside",
                    marker=dict(color=_bar_color_series(perf_df["day_change_pct"])),
                    hovertemplate="%{x}<br>%{y:+.2f}%<extra></extra>",
                    cliponaxis=False,
                ))
                fig = _plotly_layout(fig, height=290, showlegend=False)
                fig.update_yaxes(title=None, gridcolor="#1f2937", zerolinecolor="#64748b",
                                  range=[-max_abs * 1.35, max_abs * 1.35] if max_abs else None)
                fig.update_xaxes(title=None)
                st.plotly_chart(fig, use_container_width=True, key="perf_pct")

st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)

# ── Rec 5: Holdings table — slim columns with colored P/L ─────────────────────

with st.container(border=True):
    _chart_header("Holdings", "Position-level pricing and performance")

    show_all = st.toggle("Show all columns", value=False, key="show_all_cols")

    if portfolio_df.empty:
        st.info("No holdings found. Edit portfolio.yml.")
    else:
        display_df = portfolio_df.copy()
        for col in ["day_change_pct", "price", "previous_close", "market_value", "daily_pl", "portfolio_weight"]:
            display_df = _round_column(display_df, col)

        default_columns = ["ticker", "name", "sector", "shares", "price", "daily_pl", "day_change_pct", "market_value", "portfolio_weight"]
        all_columns = ["ticker", "name", "sector", "shares", "price", "daily_pl", "day_change_pct", "market_value", "portfolio_weight", "status", "source", "as_of"]

        chosen = all_columns if show_all else default_columns
        visible = [c for c in chosen if c in display_df.columns]
        table = display_df[visible].copy()

        rename_map = {
            "ticker": "Ticker", "name": "Company", "sector": "Sector",
            "shares": "Shares", "price": "Price", "daily_pl": "1-Day P/L ($)",
            "day_change_pct": "1-Day %", "market_value": "Mkt Value",
            "portfolio_weight": "Weight", "status": "Status",
            "source": "Source", "as_of": "Last Updated",
        }
        table = table.rename(columns=rename_map)

        # Color the P/L columns
        def _style_pl(df: pd.DataFrame) -> pd.DataFrame:
            styled = pd.DataFrame("", index=df.index, columns=df.columns)
            for col in ["1-Day P/L ($)", "1-Day %"]:
                if col in df.columns:
                    styled[col] = df[col].map(
                        lambda v: (
                            "color: #22c55e" if isinstance(v, (int, float)) and v > 0
                            else "color: #ef4444" if isinstance(v, (int, float)) and v < 0
                            else ""
                        )
                    )
            return styled

        st.dataframe(
            table.style.apply(_style_pl, axis=None),
            use_container_width=True, hide_index=True, height=275,
        )

    st.markdown(
        '<div class="footer-note">Prices may be delayed. Currency in USD. Holdings without price data are excluded from totals.</div>',
        unsafe_allow_html=True,
    )

st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)

# ── Rec 4: Macro pulse strip ──────────────────────────────────────────────────

# Pull values from index_snapshot where available
def _macro_val(ticker: str) -> tuple[str, str]:
    move = next((m for m in index_snapshot.values() if m.ticker == ticker), None)
    if move and move.price is not None:
        chg = f"{move.day_change_pct:+.2f}%" if move.day_change_pct is not None else ""
        return f"{move.price:,.2f}", chg
    return "—", ""

sp500_val, sp500_chg   = _macro_val("^GSPC")
tsy10_val, tsy10_chg   = _macro_val("^TNX")
oil_val, oil_chg       = _macro_val("CL=F")
gold_val, gold_chg     = _macro_val("GC=F")

macro_cells = [
    ("S&P 500", sp500_val, sp500_chg),
    ("10Y Treasury", tsy10_val, tsy10_chg),
    ("WTI Crude", oil_val, oil_chg),
    ("Gold", gold_val, gold_chg),
]

cells_html = "".join(
    f'<div class="macro-cell">'
    f'<div class="macro-cell-label">{label}</div>'
    f'<div class="macro-cell-value">{value}</div>'
    f'<div class="macro-cell-note">{note}</div>'
    f'</div>'
    for label, value, note in macro_cells
)

st.markdown(
    f'<div class="macro-strip">{cells_html}</div>',
    unsafe_allow_html=True,
)

st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)

# ── Rec 7: Newsletter preview — inline, not buried ────────────────────────────

latest_txt  = settings.output_dir / "latest_newsletter.txt"
latest_html = settings.output_dir / "latest_newsletter.html"

st.markdown('<div class="nl-preview-title">Latest Newsletter</div>', unsafe_allow_html=True)

if latest_txt.exists():
    content = latest_txt.read_text(encoding="utf-8")
    # Show first ~60 lines inline, rest in expander
    lines = content.splitlines()
    preview_lines = lines[:60]
    rest_lines = lines[60:]

    st.markdown(
        f'<div class="nl-preview">{chr(10).join(preview_lines)}</div>',
        unsafe_allow_html=True,
    )
    if rest_lines:
        with st.expander("Show full newsletter"):
            st.text("\n".join(rest_lines))
elif latest_html.exists():
    st.info("HTML newsletter found. Open output/latest_newsletter.html to view it in a browser.")
else:
    st.info("No newsletter generated yet. Run `python main.py` first.")
