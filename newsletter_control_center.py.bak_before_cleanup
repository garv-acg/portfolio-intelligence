"""
newsletter_control_center.py
─────────────────────────────
Streamlit control centre for the Morning Portfolio Brief system.

Run:
    streamlit run newsletter_control_center.py

Pages
─────
  Overview          — holdings summary + workflow guide
  Portfolio         — editable holdings CSV
  Monitor           — diagnostics, exposure, surveillance
  Market Workbench  — catalysts, SEC diff, watchlist, macro
  Analytics         — equity curve, drawdown, attribution
  Factors           — factor signals + cumulative attribution
  Newsletter        — generate / send buttons
  Morning Brief     — modular brief builder
  Preferences       — section toggles
  Preview           — rendered HTML preview
  Files             — raw CSV / text view
  History           — run history
  Alerts            — alert engine dashboard
  Construction      — portfolio construction (advanced)
  Backtesting       — rolling backtest (advanced)
  Execution         — paper trade execution layer (advanced)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from app.config.user_profiles import ensure_default_profiles, get_user_profile, create_user_profile
from app.data.execution_engine import save_rebalance_recommendations
from app.data.alert_engine import latest_alerts, alert_summary
from app.data.factor_engine import cumulative_attribution, build_factor_signals


# ── Constants ──────────────────────────────────────────────────────────────────
DEFAULT_PORTFOLIO_PATH = Path("portfolio.csv")
NEWSLETTER_HTML_PATH   = Path("output/latest_newsletter.html")
NEWSLETTER_TEXT_PATH   = Path("output/latest_newsletter.txt")

# All navigable pages in sidebar order.
# Advanced pages appear at the bottom; they are fully functional.
NAV_PAGES = [
    "Overview",
    "Portfolio",
    "Monitor",
    "Market Workbench",
    "Analytics",
    "Factors",
    "Newsletter",
    "Morning Brief",
    "Preferences",
    "Preview",
    "Files",
    "History",
    "Alerts",
    "Construction",
    "Backtesting",
    "Execution",
]


# ── Styling ────────────────────────────────────────────────────────────────────
APP_CSS = """
<style>
:root {
    --bg-primary: #020617;
    --bg-secondary: #0f172a;
    --bg-card: #111827;
    --border: #1f2937;
    --text-primary: #f8fafc;
    --text-secondary: #cbd5e1;
    --text-muted: #94a3b8;
    --accent: #93c5fd;
    --positive: #86efac;
    --negative: #fca5a5;
}
.stApp {
    background: radial-gradient(circle at top left, #0f172a 0%, #020617 38%, #020617 100%);
    color: var(--text-primary);
}
.block-container { padding-top:1.4rem; padding-bottom:3rem; max-width:1400px; }
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg,#020617 0%,#0f172a 100%);
    border-right: 1px solid #1f2937;
}
[data-testid="stMetric"] {
    background: rgba(15,23,42,.88); border:1px solid #1f2937; border-radius:18px;
    padding:16px; box-shadow:0 18px 40px rgba(0,0,0,.22);
}
[data-testid="stMetricLabel"] { color:#94a3b8!important; font-size:.75rem!important;
                                 text-transform:uppercase; letter-spacing:.08em; }
[data-testid="stMetricValue"] { color:#f8fafc!important; font-weight:850; }
div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] {
    border:1px solid #1f2937; border-radius:18px; overflow:hidden;
}
.stButton > button {
    border-radius:14px; border:1px solid #334155; background:#0f172a; color:#f8fafc;
    font-weight:750; transition:all .18s ease-in-out;
}
.stButton > button:hover {
    border-color:#93c5fd; color:#dbeafe; transform:translateY(-1px);
    box-shadow:0 12px 24px rgba(147,197,253,.12);
}
.stDownloadButton > button {
    border-radius:14px; border:1px solid #334155; background:#0f172a; color:#f8fafc; font-weight:750;
}
hr { border-color:#1f2937; }
.card { background:rgba(15,23,42,.86); border:1px solid #1f2937; border-radius:22px;
        padding:18px; box-shadow:0 18px 40px rgba(0,0,0,.24); margin-bottom:14px; }
.section-title { color:#dbeafe; font-size:.78rem; font-weight:850; text-transform:uppercase;
                 letter-spacing:.08em; margin-bottom:8px; }
.muted { color:#94a3b8; font-size:.86rem; }
.big-title { font-size:2.15rem; font-weight:900; letter-spacing:-.04em; margin-bottom:.25rem; }
.status-pill { display:inline-block; padding:5px 10px; border-radius:999px;
               border:1px solid #1f2937; background:#020617; color:#cbd5e1;
               font-size:.75rem; font-weight:750; margin-right:6px; }
@media(max-width:768px) {
    .block-container { padding-left:.8rem; padding-right:.8rem; }
    .big-title { font-size:1.55rem; }
    [data-testid="stMetric"] { padding:12px; }
}
</style>
"""


# ── State ──────────────────────────────────────────────────────────────────────

def init_state() -> None:
    defaults = {
        "portfolio_path":    str(_find_portfolio_file()),
        "last_action_output": "",
        "last_action_ok":     None,
        "active_page":        "Overview",
        "active_user_id":     None,
        "portfolio_path_override": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _find_portfolio_file() -> Path:
    for p in [Path("portfolio.csv"), Path("data/portfolio.csv"),
              Path("app/config/portfolio.csv"), Path("app/data/portfolio.csv")]:
        if p.exists():
            return p
    return DEFAULT_PORTFOLIO_PATH


# ── Portfolio helpers ──────────────────────────────────────────────────────────

def normalize_portfolio(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    lower_map = {col.lower().strip(): col for col in df.columns}

    for field in ["ticker", "shares"]:
        if field not in lower_map:
            df[field] = "" if field == "ticker" else 0.0
        else:
            df = df.rename(columns={lower_map[field]: field})

    for field in ["name", "cost_basis"]:
        cols_lower = [c.lower().strip() for c in df.columns]
        if field not in cols_lower:
            df[field] = ""
        else:
            orig = next(c for c in df.columns if c.lower().strip() == field)
            if orig != field:
                df = df.rename(columns={orig: field})

    df["ticker"]     = df["ticker"].astype(str).str.upper().str.strip()
    df["shares"]     = pd.to_numeric(df["shares"],     errors="coerce").fillna(0.0)
    df["name"]       = df["name"].fillna("").astype("string")
    df["cost_basis"] = df["cost_basis"].fillna("").astype("string")

    preferred  = ["ticker", "shares", "name", "cost_basis"]
    remaining  = [c for c in df.columns if c not in preferred]
    return df[preferred + remaining]


def load_portfolio(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["ticker", "shares", "name", "cost_basis"])
    return normalize_portfolio(pd.read_csv(path))


def save_portfolio(path: Path, df: pd.DataFrame) -> None:
    df = normalize_portfolio(df)
    df = df[df["ticker"].astype(str).str.strip() != ""]
    df.to_csv(path, index=False)


# ── Shell command runner ───────────────────────────────────────────────────────

def run_command(command: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, cwd=Path.cwd(), capture_output=True, text=True, check=False)
        output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
        return result.returncode == 0, output.strip()
    except Exception as exc:
        return False, str(exc)


# ── Analytics helper ───────────────────────────────────────────────────────────

def try_load_visual_analytics(df: pd.DataFrame) -> dict[str, Any] | None:
    try:
        from app.config.portfolio import load_portfolio as lp
        from app.config.settings import settings
        from app.data.market_data import get_equity_snapshot
        from app.data.visual_analytics import build_visual_analytics
        holdings  = lp(settings.portfolio_file)
        snapshot  = get_equity_snapshot(holdings)
        analytics = build_visual_analytics(holdings, snapshot, lookback_days=120)
        return analytics.__dict__
    except Exception:
        return None


# ── Display formatting ─────────────────────────────────────────────────────────

_COLUMN_LABELS = {
    "ticker": "Ticker", "sector": "Sector", "signal_label": "Signal Label",
    "composite_score": "Composite Score (0-100)", "volatility_21d_pct": "21D Volatility (%)",
    "relative_strength_21d_pct": "21D Relative Strength (%)", "drawdown_pct": "Drawdown (%)",
    "current_weight_pct": "Current Weight (%)", "target_weight_pct": "Target Weight (%)",
    "weight_drift_pct": "Weight Drift (%)", "value": "Current Value ($)",
    "target_value": "Target Value ($)", "trade_value": "Trade Value ($)", "action": "Action",
    "cumulative_daily_pl": "Cumulative Daily P/L ($)", "avg_contribution_pct": "Avg Contribution (%)",
    "cumulative_contribution_pct": "Cumulative Contribution (%)", "avg_move_pct": "Avg Move (%)",
    "avg_weight_pct": "Avg Weight (%)", "best_daily_pl": "Best Daily P/L ($)",
    "worst_daily_pl": "Worst Daily P/L ($)", "observations": "Observations",
    "daily_pl": "Daily P/L ($)", "move_pct": "Move (%)", "contribution_pct": "Contribution (%)",
    "portfolio_value": "Portfolio Value ($)", "risk_score": "Risk Score (0-100)",
    "inflation_score": "Inflation Score (0-100)", "growth_score": "Growth Score (0-100)",
    "liquidity_score": "Liquidity Score (0-100)",
}


def _pretty(col: str) -> str:
    return _COLUMN_LABELS.get(str(col), str(col).replace("_", " ").title())


def _format_table(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    for col in out.columns:
        label = str(col).lower()
        def fmt(v, label=label):
            if pd.isna(v):
                return ""
            if isinstance(v, (int, float)):
                if "score" in label:
                    return f"{v:.1f}/100"
                if any(k in label for k in ["pct","weight","move","drawdown","volatility","contribution"]):
                    return f"{v:+.2f}%"
                if any(k in label for k in ["value","pl","trade","price"]):
                    return f"${v:,.2f}"
                return f"{v:,.2f}"
            return v
        out[col] = out[col].map(fmt)
    return out.rename(columns={c: _pretty(c) for c in out.columns})


def _format_chart(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    return df.rename(columns={c: _pretty(c) for c in df.columns})


# ── Header ─────────────────────────────────────────────────────────────────────

def render_header() -> None:
    st.markdown(
        """
        <div class="big-title">Daily Portfolio Brief</div>
        <div class="muted">Daily portfolio updates · factual monitoring · morning brief automation</div>
        <div style="margin-top:12px;">
            <span class="status-pill">Portfolio</span>
            <span class="status-pill">Morning Brief</span>
            <span class="status-pill">SEC Filings</span>
            <span class="status-pill">Market Monitor</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Sidebar ────────────────────────────────────────────────────────────────────

def render_sidebar() -> str:
    st.sidebar.markdown("## Control Center")
    st.sidebar.caption("Navigate your workflow from one interface.")

    active_page = st.session_state.get("active_page", "Overview")
    if active_page not in NAV_PAGES:
        active_page = "Overview"
        st.session_state["active_page"] = active_page

    page = st.sidebar.radio("Navigation", NAV_PAGES, index=NAV_PAGES.index(active_page))
    st.session_state["active_page"] = page

    st.sidebar.divider()
    st.sidebar.markdown("### Settings")

    # User profile selector
    profiles  = ensure_default_profiles()
    labels    = {f"{p.display_name} ({p.user_id})": p.user_id for p in profiles}
    label_list = list(labels.keys())

    current_user  = st.session_state.get("active_user_id")
    default_index = 0
    if current_user:
        for i, label in enumerate(label_list):
            if labels[label] == current_user:
                default_index = i
                break

    selected_label   = st.sidebar.selectbox("User Profile", label_list, index=default_index)
    selected_profile = get_user_profile(labels[selected_label])
    st.session_state["active_user_id"]        = selected_profile.user_id
    st.session_state["portfolio_path_override"] = str(selected_profile.portfolio_file)

    with st.sidebar.expander("Create User", expanded=False):
        new_name  = st.text_input("Display name", key="new_profile_display_name")
        new_email = st.text_input("Email",        key="new_profile_email")
        if st.button("Create User Profile"):
            if not new_name.strip():
                st.warning("Enter a display name first.")
            else:
                new_profile = create_user_profile(
                    display_name=new_name.strip(),
                    email=new_email.strip() or None,
                    copy_from=selected_profile.portfolio_file,
                )
                st.session_state["active_user_id"]          = new_profile.user_id
                st.session_state["portfolio_path_override"]  = str(new_profile.portfolio_file)
                st.success(f"Created profile: {new_profile.display_name}")
                st.rerun()

    st.sidebar.caption(f"Active portfolio: {selected_profile.portfolio_file}")
    return page


# ══ Page renderers ═════════════════════════════════════════════════════════════

def render_overview(df: pd.DataFrame, portfolio_path: Path) -> None:
    st.markdown("### Daily Portfolio Overview")
    st.info(
        "Facts-first daily portfolio update system. Monitors holdings, exposures, "
        "filings, catalysts, alerts, and newsletter output. "
        "Does not make investment decisions."
    )
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Holdings", len(df[df["ticker"].astype(str).str.strip() != ""]))
    with c2:
        total_shares = pd.to_numeric(df.get("shares", pd.Series()), errors="coerce").fillna(0).sum()
        st.metric("Total Shares", f"{total_shares:,.3f}")
    with c3:
        st.metric("Newsletter Exists", "Yes" if NEWSLETTER_HTML_PATH.exists() else "No")
    with c4:
        size = NEWSLETTER_HTML_PATH.stat().st_size if NEWSLETTER_HTML_PATH.exists() else 0
        st.metric("HTML Size", f"{size:,.0f} bytes")

    st.divider()
    left, right = st.columns([1.15, 0.85])
    with left:
        st.markdown('<div class="card"><div class="section-title">Current Holdings</div>', unsafe_allow_html=True)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown(
            f"""
            <div class="card">
                <div class="section-title">Workflow</div>
                <div class="muted">
                    1. Edit holdings in <strong>Portfolio</strong><br>
                    2. Generate the newsletter in <strong>Newsletter</strong><br>
                    3. Preview the HTML in <strong>Preview</strong><br>
                    4. Send via <strong>Newsletter → Send Email</strong>
                </div>
                <br>
                <div class="section-title">Active File</div>
                <div class="muted"><code>{portfolio_path}</code></div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_portfolio(df: pd.DataFrame, portfolio_path: Path) -> None:
    st.markdown("### Portfolio Editor")
    st.caption("Edit holdings directly. Save writes back to your portfolio CSV.")
    edited = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "ticker":     st.column_config.TextColumn("Ticker",       required=True),
            "shares":     st.column_config.NumberColumn("Shares",     min_value=0.0, step=0.001, format="%.6f", required=True),
            "name":       st.column_config.TextColumn("Company Name"),
            "cost_basis": st.column_config.TextColumn("Cost Basis"),
        },
        hide_index=True,
        key="portfolio_editor",
    )
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button("Save Portfolio", type="primary", use_container_width=True):
            save_portfolio(portfolio_path, edited)
            st.success(f"Saved to {portfolio_path}")
    with c2:
        if st.button("Reload Portfolio", use_container_width=True):
            st.rerun()
    with c3:
        st.info("After saving, generate the newsletter from the Newsletter page.")


def render_analytics(df: pd.DataFrame) -> None:
    st.markdown("### Portfolio Analytics")
    st.caption("In-app dashboard view of visual analytics.")
    analytics = try_load_visual_analytics(df)
    if not analytics:
        st.warning("Analytics unavailable. Generate the newsletter or check data dependencies.")
        return

    allocation  = pd.DataFrame(analytics.get("allocation", []))
    sectors     = pd.DataFrame(analytics.get("sector_exposure", []))
    attribution = pd.DataFrame(analytics.get("daily_attribution", []))
    rolling     = pd.DataFrame(analytics.get("rolling_returns", []))
    drawdown    = pd.DataFrame(analytics.get("drawdown", []))
    vol         = analytics.get("volatility_monitor", {}) or {}

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Latest Return",    f"{vol.get('latest_daily_return_pct', 0):+.2f}%")
    c2.metric("Annualized Vol",   f"{vol.get('annualized_volatility_pct', 0):+.2f}%")
    c3.metric("21D Realized Vol", f"{vol.get('realized_21d_volatility_pct', 0):+.2f}%")
    c4.metric("Vol Status",       str(vol.get("status", "N/A")))

    st.divider()
    left, right = st.columns(2)
    with left:
        st.markdown("#### Portfolio Equity Curve")
        if not rolling.empty and "date" in rolling and "portfolio_value" in rolling:
            st.line_chart(rolling.set_index("date")["portfolio_value"], height=260)
        else:
            st.info("No rolling return data available.")
    with right:
        st.markdown("#### Drawdown Monitor")
        if not drawdown.empty and "date" in drawdown and "drawdown_pct" in drawdown:
            st.area_chart(drawdown.set_index("date")["drawdown_pct"], height=260)
        else:
            st.info("No drawdown data available.")

    left, right = st.columns(2)
    with left:
        st.markdown("#### Allocation")
        if not allocation.empty and "ticker" in allocation and "weight_pct" in allocation:
            st.bar_chart(allocation.set_index("ticker")["weight_pct"], height=300)
            st.dataframe(allocation, use_container_width=True, hide_index=True)
        else:
            st.info("No allocation data.")
    with right:
        st.markdown("#### Sector Exposure")
        if not sectors.empty and "sector" in sectors and "weight_pct" in sectors:
            st.bar_chart(sectors.set_index("sector")["weight_pct"], height=300)
            st.dataframe(_format_table(sectors), use_container_width=True, hide_index=True)
        else:
            st.info("No sector data.")

    st.markdown("#### Daily Attribution")
    if not attribution.empty:
        st.dataframe(
            attribution.style.background_gradient(subset=["daily_pl","contribution_pct"], cmap="RdYlGn"),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("No attribution data.")


def render_factors() -> None:
    st.markdown("### Cumulative Attribution + Factor Engine")
    st.caption("Attribution from SQLite history. Factor scores use price history, benchmark relative strength, earnings dates, and SEC flags.")

    window = st.selectbox("Attribution window", ["All history","7 days","30 days","90 days"], index=0)
    days   = {"7 days": 7, "30 days": 30, "90 days": 90}.get(window)
    attr   = cumulative_attribution(days=days)

    st.markdown("#### Cumulative Attribution")
    if attr.empty:
        st.warning("No attribution history yet. Generate a few newsletters to build history.")
    else:
        c1, c2, c3 = st.columns(3)
        best  = attr.iloc[0]
        worst = attr.sort_values("cumulative_daily_pl").iloc[0]
        c1.metric("Top Creator",   best["ticker"],  f"${best['cumulative_daily_pl']:,.2f}")
        c2.metric("Top Destroyer", worst["ticker"], f"${worst['cumulative_daily_pl']:,.2f}")
        c3.metric("Tracked Holdings", len(attr))
        st.bar_chart(attr.set_index("ticker")[["cumulative_daily_pl"]].rename(columns={"cumulative_daily_pl": "Cumulative Daily P/L ($)"}), height=320)
        st.dataframe(_format_table(attr), use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("#### Current Factor Signals")
    try:
        from app.config.portfolio import load_portfolio
        from app.config.settings import settings
        from app.data.earnings import get_upcoming_earnings
        from app.data.sec_filings import get_sec_filings
        holdings = load_portfolio(settings.portfolio_file)
        tickers  = [h.ticker for h in holdings]
        earnings = get_upcoming_earnings(tickers, days_ahead=30)
        sec      = get_sec_filings(tickers, lookback_days=30, max_filings_per_ticker=3)
        signals  = build_factor_signals(tickers, earnings_calendar=earnings, sec_filings=sec)
        factor_df = pd.DataFrame([s.__dict__ for s in signals])
        if factor_df.empty:
            st.warning("No factor signals generated.")
        else:
            st.bar_chart(factor_df.set_index("ticker")[["composite_score"]].rename(columns={"composite_score": "Composite Score (0-100)"}), height=320)
            st.dataframe(_format_table(factor_df), use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(f"Factor engine failed: {exc}")


def render_alerts() -> None:
    st.markdown("### Alert Engine")
    st.caption("Alerts generated from drawdowns, SEC Item 5.02 filings, earnings proximity, regime shifts, and large position moves.")
    summary = alert_summary()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Alerts",   summary.get("total_alerts", 0))
    c2.metric("Unresolved",     summary.get("unresolved_alerts", 0))
    c3.metric("High Severity",  summary.get("high_severity_alerts", 0))
    c4.metric("Latest Alert",   summary.get("latest_alert_at") or "N/A")

    st.divider()
    unresolved_only = st.toggle("Show unresolved only", value=False)
    alerts = pd.DataFrame(latest_alerts(limit=250, unresolved_only=unresolved_only))
    if alerts.empty:
        st.warning("No alerts yet. Run the newsletter once to generate them.")
        return
    st.dataframe(_format_table(alerts), use_container_width=True, hide_index=True)
    st.divider()
    st.markdown("#### Alert Counts by Type")
    if "alert_type" in alerts.columns:
        counts = alerts.groupby("alert_type").size().reset_index(name="count")
        st.bar_chart(counts.set_index("alert_type")["count"], height=320)


def render_newsletter_actions() -> None:
    st.markdown("### Newsletter Actions")
    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("Generate Newsletter", type="primary", use_container_width=True):
            with st.spinner("Generating..."):
                ok, output = run_command([sys.executable, "main.py"])
            st.session_state["last_action_ok"]     = ok
            st.session_state["last_action_output"] = output
            st.success("Generated successfully.") if ok else st.error("Generation failed.")

    with c2:
        if st.button("Send Email", use_container_width=True):
            if not Path("send_newsletter.py").exists():
                st.error("send_newsletter.py not found in project root.")
            else:
                with st.spinner("Sending..."):
                    ok, output = run_command([sys.executable, "send_newsletter.py"])
                st.session_state["last_action_ok"]     = ok
                st.session_state["last_action_output"] = output
                st.success("Email sent.") if ok else st.error("Email failed.")

    with c3:
        if st.button("Generate + Send", use_container_width=True):
            with st.spinner("Generating..."):
                ok_gen, out_gen = run_command([sys.executable, "main.py"])
            if not ok_gen:
                st.session_state.update({"last_action_ok": False, "last_action_output": out_gen})
                st.error("Generation failed. Email not sent.")
            elif not Path("send_newsletter.py").exists():
                st.error("send_newsletter.py not found.")
            else:
                with st.spinner("Sending..."):
                    ok_send, out_send = run_command([sys.executable, "send_newsletter.py"])
                st.session_state.update({"last_action_ok": ok_send, "last_action_output": out_send})
                st.success("Generated and sent.") if ok_send else st.error("Generated, but send failed.")

    st.divider()
    st.dataframe(
        pd.DataFrame([
            {"File": str(NEWSLETTER_HTML_PATH), "Exists": NEWSLETTER_HTML_PATH.exists(),
             "Size (bytes)": NEWSLETTER_HTML_PATH.stat().st_size if NEWSLETTER_HTML_PATH.exists() else 0},
            {"File": str(NEWSLETTER_TEXT_PATH), "Exists": NEWSLETTER_TEXT_PATH.exists(),
             "Size (bytes)": NEWSLETTER_TEXT_PATH.stat().st_size if NEWSLETTER_TEXT_PATH.exists() else 0},
        ]),
        use_container_width=True, hide_index=True,
    )
    with st.expander("Last Command Output", expanded=st.session_state.get("last_action_ok") is False):
        st.code(st.session_state.get("last_action_output", "") or "No output yet.")


def render_preview() -> None:
    st.markdown("### HTML Preview")
    if NEWSLETTER_HTML_PATH.exists():
        content = NEWSLETTER_HTML_PATH.read_text(encoding="utf-8", errors="ignore")
        st.components.v1.html(content, height=920, scrolling=True)
        st.download_button("Download HTML", data=content,
                           file_name="latest_newsletter.html", mime="text/html",
                           use_container_width=True)
    else:
        st.warning("No HTML newsletter found. Generate the newsletter first.")


def render_files(portfolio_path: Path) -> None:
    st.markdown("### Files / CSV")
    st.markdown("#### Portfolio CSV")
    if portfolio_path.exists():
        st.code(portfolio_path.read_text(), language="csv")
    else:
        st.warning("Portfolio file does not exist yet.")
    st.divider()
    st.markdown("#### Text Newsletter")
    if NEWSLETTER_TEXT_PATH.exists():
        st.text_area("latest_newsletter.txt",
                     value=NEWSLETTER_TEXT_PATH.read_text(encoding="utf-8", errors="ignore"),
                     height=500)
    else:
        st.warning("No text newsletter found yet.")


def render_history() -> None:
    st.markdown("### Run History")
    st.caption("Historical newsletter runs saved to SQLite.")
    try:
        from app.data.history_db import get_history_runs
        runs = pd.DataFrame(get_history_runs())
        if runs.empty:
            st.info("No history yet. Generate a newsletter to start building history.")
        else:
            st.dataframe(runs, use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(f"History unavailable: {exc}")


def render_monitor() -> None:
    st.markdown("### Portfolio Diagnostics & Surveillance")
    st.caption("Market movements, exposures, catalysts, SEC filings, volume anomalies, and portfolio drift.")
    try:
        from app.config.portfolio import load_portfolio
        from app.config.settings import settings
        from app.data.earnings import get_upcoming_earnings
        from app.data.sec_filings import get_sec_filings
        from app.data.holdings_monitor import build_holdings_change_monitor

        holdings  = load_portfolio(settings.portfolio_file)
        tickers   = [h.ticker for h in holdings]
        benchmark = st.text_input("Benchmark", value="SPY").upper().strip()

        with st.spinner("Loading holdings monitor..."):
            earnings = get_upcoming_earnings(tickers, days_ahead=45)
            sec      = get_sec_filings(tickers, lookback_days=45, max_filings_per_ticker=3)
            result   = build_holdings_change_monitor(holdings, earnings_calendar=earnings,
                                                     sec_filings=sec, benchmark=benchmark)

        if result.get("status") != "Ready":
            st.warning(result.get("message", "Monitor unavailable."))
            return

        holdings_df = pd.DataFrame(result.get("holdings", []))
        exposure    = result.get("exposure", {})

        st.divider()
        st.markdown("#### Portfolio Exposure Dashboard")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Value",       f"${exposure.get('total_value', 0):,.2f}")
        c2.metric("Largest Position",  f"{exposure.get('single_name_concentration_pct', 0):.2f}%")
        c3.metric("Top 3 Concentration", f"{exposure.get('top_3_concentration_pct', 0):.2f}%")
        c4.metric("Portfolio Beta",    f"{exposure.get('portfolio_beta', 0):.2f}")

        for row_pair in [
            [("Sector Exposure", "sector"), ("Market Cap Exposure", "market_cap_tier")],
            [("Growth / Value Tilt", "style"), ("Geographic Exposure", "region")],
        ]:
            cols = st.columns(2)
            for col_widget, (label, key) in zip(cols, row_pair):
                with col_widget:
                    sub = pd.DataFrame(exposure.get(label.lower().replace(" ", "_").replace("/","").replace("  ","_"), []))
                    # fallback key variants
                    for variant in [label, label.replace(" ","_"), label.lower()]:
                        sub = pd.DataFrame(exposure.get(variant, []))
                        if not sub.empty:
                            break
                    st.markdown(f"##### {label}")
                    if not sub.empty:
                        idx = sub.columns[0]
                        if "weight_pct" in sub.columns:
                            st.bar_chart(sub.set_index(idx)[["weight_pct"]].rename(columns={"weight_pct": "Weight (%)"}), height=260)
                        st.dataframe(_format_table(sub), use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("#### Holdings Diagnostics")
        if holdings_df.empty:
            st.info("No holdings rows available.")
            return

        display_cols = [
            "ticker","sector","sector_etf","portfolio_weight_pct","latest_price","market_value",
            "daily_move_pct","weekly_move_pct","weekly_vs_spy_pct","weekly_vs_sector_etf_pct",
            "earnings_proximity","recent_sec_filing","volume_vs_30d_avg",
            "distance_from_52w_high_pct","drawdown_from_63d_high_pct",
            "market_cap_tier","style","beta","region",
        ]
        display_cols = [c for c in display_cols if c in holdings_df.columns]
        clean = holdings_df[display_cols].rename(columns={
            "ticker":"Ticker","sector":"Sector","sector_etf":"Sector ETF",
            "portfolio_weight_pct":"Portfolio Weight (%)","latest_price":"Latest Price ($)",
            "market_value":"Market Value ($)","daily_move_pct":"Daily Move (%)",
            "weekly_move_pct":"Weekly Move (%)","weekly_vs_spy_pct":"Weekly vs SPY (%)",
            "weekly_vs_sector_etf_pct":"Weekly vs Sector ETF (%)","earnings_proximity":"Earnings Proximity",
            "recent_sec_filing":"Recent SEC Filing","volume_vs_30d_avg":"Volume vs 30D Avg (x)",
            "distance_from_52w_high_pct":"Distance from 52W High (%)","drawdown_from_63d_high_pct":"Drawdown from 63D High (%)",
            "market_cap_tier":"Market Cap Tier","style":"Growth / Value","beta":"Beta","region":"Region",
        })
        for col in ["Portfolio Weight (%)","Daily Move (%)","Weekly Move (%)","Weekly vs SPY (%)",
                    "Weekly vs Sector ETF (%)","Distance from 52W High (%)","Drawdown from 63D High (%)"]:
            if col in clean.columns:
                clean[col] = clean[col].map(lambda x: "" if pd.isna(x) else f"{float(x):+.2f}%")
        for col in ["Latest Price ($)","Market Value ($)"]:
            if col in clean.columns:
                clean[col] = clean[col].map(lambda x: "" if pd.isna(x) else f"${float(x):,.2f}")
        if "Volume vs 30D Avg (x)" in clean.columns:
            clean["Volume vs 30D Avg (x)"] = clean["Volume vs 30D Avg (x)"].map(lambda x: "" if pd.isna(x) else f"{float(x):.2f}x")
        if "Beta" in clean.columns:
            clean["Beta"] = clean["Beta"].map(lambda x: "" if pd.isna(x) else f"{float(x):.2f}")
        st.dataframe(clean, use_container_width=True, hide_index=True)

    except Exception as exc:
        st.error(f"Holdings monitor failed: {exc}")


def render_market_workbench() -> None:
    st.markdown("### Market Workbench")
    st.caption("Catalysts, SEC filing changes, watchlist monitoring, portfolio drift, and macro dashboard.")
    try:
        from app.config.portfolio import load_portfolio
        from app.config.settings import settings
        from app.data.earnings import get_upcoming_earnings
        from app.data.sec_filings import get_sec_filings
        from app.data.market_workbench import (
            catalyst_calendar, sec_diff, watchlist_monitor,
            portfolio_drift, macro_dashboard, exposure_dashboard,
        )

        holdings      = load_portfolio(settings.portfolio_file)
        tickers       = [h.ticker for h in holdings]
        watchlist_raw = st.text_input("Watchlist tickers, comma-separated", value="MSFT, GOOGL, META, TSLA, JPM")
        watchlist     = [x.strip().upper() for x in watchlist_raw.split(",") if x.strip()]
        days          = st.slider("Catalyst Calendar Window (days)", 7, 45, 14, 1)

        with st.spinner("Loading market workbench..."):
            all_tickers = sorted(set(tickers + watchlist))
            earnings    = get_upcoming_earnings(all_tickers, days_ahead=45)
            sec         = get_sec_filings(all_tickers, lookback_days=45, max_filings_per_ticker=3)
            catalysts   = pd.DataFrame(catalyst_calendar(tickers, earnings, sec, days))
            sec_rows    = pd.DataFrame(sec_diff(sec))
            watch       = pd.DataFrame(watchlist_monitor(watchlist, earnings, sec))
            drift       = pd.DataFrame(portfolio_drift(holdings))
            macro       = macro_dashboard()
            exposure    = exposure_dashboard(holdings)

        tabs = st.tabs(["What Matters This Week","SEC Filing Diff","Watchlist","Portfolio Drift","Macro Dashboard","Exposure"])

        with tabs[0]:
            st.markdown("#### Catalyst Calendar")
            st.dataframe(_format_table(catalysts), use_container_width=True, hide_index=True)
        with tabs[1]:
            st.markdown("#### SEC Filing Diff Tracker")
            st.caption("Tracked factual language categories from recent filings.")
            st.dataframe(_format_table(sec_rows), use_container_width=True, hide_index=True)
        with tabs[2]:
            st.markdown("#### Watchlist Intelligence")
            st.dataframe(_format_table(watch), use_container_width=True, hide_index=True)
        with tabs[3]:
            st.markdown("#### Portfolio Drift Monitor")
            if not drift.empty and "Ticker" in drift.columns:
                st.bar_chart(drift.set_index("Ticker")[["Current Weight (%)","Target Weight (%)"]], height=320)
            st.dataframe(_format_table(drift), use_container_width=True, hide_index=True)
        with tabs[4]:
            st.markdown("#### Macro Dashboard")
            indicators = pd.DataFrame(macro.get("Indicators", []))
            sectors    = pd.DataFrame(macro.get("Sector Leadership", []))
            missing    = pd.DataFrame(macro.get("Not Yet Connected", []))
            st.markdown("##### Key Market Indicators")
            st.dataframe(_format_table(indicators), use_container_width=True, hide_index=True)
            st.markdown("##### Sector Leadership")
            if not sectors.empty and "Weekly Move (%)" in sectors.columns:
                st.bar_chart(sectors.set_index("Sector")[["Weekly Move (%)"]], height=320)
            st.dataframe(_format_table(sectors), use_container_width=True, hide_index=True)
            st.markdown("##### Not Yet Connected")
            st.dataframe(missing, use_container_width=True, hide_index=True)
        with tabs[5]:
            st.markdown("#### Portfolio Exposure Dashboard")
            if exposure:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Total Value",          f"${exposure.get('Total Value ($)', 0):,.2f}")
                c2.metric("Largest Position",     f"{exposure.get('Largest Position (%)', 0):.2f}%")
                c3.metric("Top 3 Concentration",  f"{exposure.get('Top 3 Concentration (%)', 0):.2f}%")
                c4.metric("Portfolio Beta",        f"{exposure.get('Portfolio Beta', 0):.2f}")
                for label in ["Sector Exposure","Market Cap Exposure","Style Exposure","Region Exposure"]:
                    st.markdown(f"##### {label}")
                    sub = pd.DataFrame(exposure.get(label, []))
                    if not sub.empty:
                        idx = sub.columns[0]
                        if "Weight (%)" in sub.columns:
                            st.bar_chart(sub.set_index(idx)[["Weight (%)"]], height=260)
                        st.dataframe(_format_table(sub), use_container_width=True, hide_index=True)

    except Exception as exc:
        st.error(f"Market Workbench failed: {exc}")


def render_morning_brief() -> None:
    st.markdown("### Morning Brief Engine")
    st.caption("Modular, facts-first daily newsletter builder.")
    try:
        from app.config.settings import settings
        from app.data.earnings import get_upcoming_earnings
        from app.data.sec_filings import get_sec_filings
        from app.data.alert_engine import latest_alerts
        from app.data.morning_brief_engine import build_morning_brief, save_morning_brief_outputs, render_brief_html
        from app.data.market_workbench import macro_dashboard
        from app.data.holdings_monitor import build_holdings_change_monitor

        portfolio_file = Path(st.session_state.get("portfolio_path_override", str(settings.portfolio_file)))
        section_options = {
            "Portfolio Snapshot": "portfolio_snapshot",
            "Top Movers":         "top_movers",
            "Earnings Calendar":  "earnings",
            "SEC Filings":        "sec_filings",
            "Alerts":             "alerts",
            "Macro Snapshot":     "macro",
        }
        selected_labels   = st.multiselect("Sections to include", list(section_options.keys()), default=list(section_options.keys()))
        enabled_sections  = [section_options[l] for l in selected_labels]
        st.caption(f"Active portfolio: {portfolio_file}")

        if st.button("Build Morning Brief", type="primary"):
            with st.spinner("Building facts-first morning brief..."):
                active_df = pd.read_csv(portfolio_file)
                holdings  = [
                    type("Holding", (), {
                        "ticker":     str(row.get("ticker", "")).upper(),
                        "shares":     float(row.get("shares", 0) or 0),
                        "cost_basis": float(row.get("cost_basis", 0) or 0),
                    })()
                    for _, row in active_df.iterrows()
                ]
                tickers  = [h.ticker for h in holdings]
                earnings = get_upcoming_earnings(tickers, days_ahead=30)
                sec      = get_sec_filings(tickers, lookback_days=30, max_filings_per_ticker=3)
                alerts   = latest_alerts(limit=25)
                macro    = macro_dashboard()
                monitor  = build_holdings_change_monitor(holdings, earnings_calendar=earnings,
                                                         sec_filings=sec, benchmark="SPY")
                brief    = build_morning_brief(
                    portfolio_rows=monitor.get("holdings", []),
                    holdings_monitor_rows=monitor.get("holdings", []),
                    earnings_calendar=earnings,
                    sec_filings=sec,
                    alerts=alerts,
                    macro_data=macro,
                    enabled_sections=enabled_sections,
                )
                paths = save_morning_brief_outputs(brief)
                st.session_state["latest_morning_brief"]       = brief
                st.session_state["latest_morning_brief_paths"] = paths
                st.success("Morning brief generated.")

        brief = st.session_state.get("latest_morning_brief")
        paths = st.session_state.get("latest_morning_brief_paths", {})
        if not brief:
            st.info("Click Build Morning Brief to generate the preview.")
            return

        st.divider()
        st.markdown("#### Generated Files")
        st.dataframe(pd.DataFrame([
            {"File": "HTML Brief", "Path": paths.get("html", "N/A")},
            {"File": "Text Brief", "Path": paths.get("text", "N/A")},
        ]), use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("#### Brief Preview")
        for section in (brief.get("sections", []) or []):
            if not isinstance(section, dict):
                section = {"title": "Section", "summary": str(section), "rows": []}
            with st.expander(section.get("title", "Section"), expanded=True):
                st.write(section.get("summary", ""))
                rows = [r if isinstance(r, dict) else {"Value": str(r)} for r in (section.get("rows", []) or [])]
                if rows:
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("#### HTML Preview")
        st.components.v1.html(render_brief_html(brief), height=800, scrolling=True)

    except Exception as exc:
        st.error(f"Morning Brief Engine failed: {exc}")


def render_newsletter_preferences() -> None:
    st.markdown("### Newsletter Preferences")
    st.caption("Turn daily brief sections on or off without editing code.")

    prefs_path = Path("data/users/demo/newsletter_preferences.json")
    defaults   = {
        "portfolio_snapshot": True, "visual_intelligence": True, "top_movers": True,
        "portfolio_news": True, "market_update": True, "macro_snapshot": True,
        "economic_calendar": True, "earnings_calendar": True, "sec_monitoring": True,
        "alerts": True, "global_developments": True,
    }
    if not prefs_path.exists():
        prefs_path.parent.mkdir(parents=True, exist_ok=True)
        prefs_path.write_text(json_dumps(defaults), encoding="utf-8")
    prefs = defaults.copy()
    try:
        import json
        prefs.update(json.loads(prefs_path.read_text(encoding="utf-8")))
    except Exception:
        pass

    labels = {
        "portfolio_snapshot": "Portfolio Snapshot", "visual_intelligence": "Visual Intelligence",
        "top_movers": "Top Movers", "portfolio_news": "Portfolio News",
        "market_update": "Market Update", "macro_snapshot": "Macro Snapshot",
        "economic_calendar": "Economic Calendar", "earnings_calendar": "Earnings Calendar",
        "sec_monitoring": "SEC Monitoring", "alerts": "Alerts",
        "global_developments": "Global Developments",
    }
    updated = {}
    c1, c2 = st.columns(2)
    for i, (key, label) in enumerate(labels.items()):
        with (c1 if i % 2 == 0 else c2):
            updated[key] = st.toggle(label, value=bool(prefs.get(key, True)))

    if st.button("Save Newsletter Preferences", type="primary"):
        import json
        prefs_path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
        st.success("Preferences saved.")

    st.divider()
    st.markdown("#### Preferences File")
    st.code(str(prefs_path))


def render_construction() -> None:
    st.markdown("### Portfolio Construction Engine")
    st.caption("Advanced: factor-driven target weight generation and rebalance suggestions.")
    try:
        from app.config.portfolio import load_portfolio
        from app.config.settings import settings
        from app.data.market_data import get_equity_snapshot
        from app.data.earnings import get_upcoming_earnings
        from app.data.sec_filings import get_sec_filings
        from app.data.factor_engine import build_factor_signals
        from app.data.portfolio_construction import build_portfolio_construction, ConstructionConfig

        holdings = load_portfolio(settings.portfolio_file)
        tickers  = [h.ticker for h in holdings]
        snapshot = [i.__dict__ if hasattr(i, "__dict__") else i for i in get_equity_snapshot(holdings)]
        earnings = get_upcoming_earnings(tickers, days_ahead=30)
        sec      = get_sec_filings(tickers, lookback_days=30, max_filings_per_ticker=3)
        factors  = build_factor_signals(tickers, earnings_calendar=earnings, sec_filings=sec)
        factor_dicts = [i.__dict__ for i in factors]

        st.markdown("#### Construction Settings")
        c1, c2, c3, c4 = st.columns(4)
        max_pos            = c1.slider("Max Position Weight",   5,  40, 22, 1) / 100.0
        max_sector         = c2.slider("Max Sector Weight",    20,  70, 40, 1) / 100.0
        min_pos            = c3.slider("Min Position Weight",   0,  10,  2, 1) / 100.0
        rebalance_threshold = c4.slider("Rebalance Threshold",  1,  10,  3, 1) / 100.0

        config       = ConstructionConfig(max_position_weight=max_pos, max_sector_weight=max_sector,
                                          min_position_weight=min_pos, rebalance_threshold=rebalance_threshold)
        construction = build_portfolio_construction(snapshot, factor_dicts, config=config)

        if construction.get("status") != "Ready":
            st.warning(construction.get("message", "Construction unavailable."))
            return

        summary = construction.get("summary", {})
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Portfolio Value",  f"${summary.get('portfolio_value', 0):,.2f}")
        m2.metric("Rebalance Trades", summary.get("rebalance_trades", 0))
        m3.metric("Est. Vol",         f"{summary.get('estimated_portfolio_volatility_pct', 0):.2f}%")
        m4.metric("Turnover",         f"{summary.get('turnover_pct', 0):.2f}%")

        targets = pd.DataFrame(construction.get("targets", []))
        trades  = pd.DataFrame(construction.get("trades",  []))
        sectors = pd.DataFrame(construction.get("sector_targets", []))

        st.divider()
        st.markdown("#### Current vs Target Weights")
        if not targets.empty:
            st.bar_chart(_format_chart(targets[["ticker","current_weight_pct","target_weight_pct"]].set_index("ticker")), height=340)
            st.dataframe(_format_table(targets), use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("#### Rebalance Suggestions")
        if trades.empty:
            st.success("No rebalance trades exceed the configured threshold.")
        else:
            st.dataframe(_format_table(trades), use_container_width=True, hide_index=True)
            if st.button("Save Rebalance Recommendations", type="primary"):
                saved = save_rebalance_recommendations(construction.get("trades", []))
                st.success(f"Saved {saved} recommendation(s).")

        st.divider()
        st.markdown("#### Sector Constraint View")
        if not sectors.empty:
            st.bar_chart(_format_chart(sectors[["sector","current_weight_pct","target_weight_pct"]].set_index("sector")), height=320)
            st.dataframe(_format_table(sectors), use_container_width=True, hide_index=True)

    except Exception as exc:
        st.error(f"Construction engine failed: {exc}")


def render_execution() -> None:
    st.markdown("### Execution Layer")
    st.caption("Advanced: approve/reject rebalance recommendations and view paper trade ledger.")
    try:
        from app.data.execution_engine import (
            init_execution_tables, execution_summary, latest_recommendations,
            approve_recommendation, reject_recommendation,
            paper_trade_ledger, execution_audit_trail, set_cash_balance,
        )
        init_execution_tables()
        summary = execution_summary()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Pending",          summary.get("pending_recommendations", 0))
        c2.metric("Paper Trades",     summary.get("paper_trades", 0))
        c3.metric("Traded Value",     f"${summary.get('total_paper_traded_value', 0):,.2f}")
        c4.metric("Simulated Cash",   f"${summary.get('cash_balance', 0):,.2f}")

        with st.expander("Cash Settings", expanded=False):
            new_cash = st.number_input("Set simulated cash balance",
                                       value=float(summary.get("cash_balance", 0.0)), step=100.0)
            if st.button("Update Cash Balance"):
                set_cash_balance(float(new_cash))
                st.success("Updated.")
                st.rerun()

        st.markdown("#### Pending Recommendations")
        pending = pd.DataFrame(latest_recommendations(status="Pending", limit=100))
        if pending.empty:
            st.info("No pending recommendations. Save from the Construction page first.")
        else:
            st.dataframe(_format_table(pending), use_container_width=True, hide_index=True)
            rec_ids     = pending["id"].astype(int).tolist()
            selected_id = st.selectbox("Recommendation ID", rec_ids)
            sel         = pending[pending["id"] == selected_id].iloc[0]
            action      = str(sel.get("action", "")).upper()
            trade_val   = float(sel.get("trade_value", 0) or 0)
            cash        = float(summary.get("cash_balance", 0.0) or 0.0)

            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Ticker",      sel.get("ticker", ""))
            s2.metric("Action",      action)
            s3.metric("Trade Value", f"${trade_val:,.2f}")
            cash_after = cash - abs(trade_val) if action == "BUY" else cash + abs(trade_val)
            s4.metric("Cash After",  f"${cash_after:,.2f}")

            if action == "BUY" and cash < abs(trade_val):
                st.warning("This BUY exceeds simulated cash.")

            note  = st.text_input("Decision note", value="")
            price = st.number_input("Optional simulated execution price", min_value=0.0, value=0.0, step=1.0)
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Approve", type="primary"):
                    approve_recommendation(int(selected_id), note=note,
                                           simulated_price=price if price > 0 else None)
                    st.success(f"Approved {selected_id}.")
                    st.rerun()
            with b2:
                if st.button("Reject"):
                    reject_recommendation(int(selected_id), note=note)
                    st.warning(f"Rejected {selected_id}.")
                    st.rerun()

        st.divider()
        st.markdown("#### Paper Trade Ledger")
        trades = pd.DataFrame(paper_trade_ledger(limit=250))
        st.dataframe(_format_table(trades), use_container_width=True, hide_index=True) if not trades.empty else st.info("No paper trades yet.")

        st.divider()
        st.markdown("#### Execution Audit Trail")
        audit = pd.DataFrame(execution_audit_trail(limit=250))
        st.dataframe(_format_table(audit), use_container_width=True, hide_index=True) if not audit.empty else st.info("No audit events yet.")

    except Exception as exc:
        st.error(f"Execution layer failed: {exc}")


def render_backtesting() -> None:
    st.markdown("### Backtesting Engine")
    st.caption("Advanced: rolling rebalance simulation against a benchmark.")
    try:
        from app.config.portfolio import load_portfolio
        from app.config.settings import settings
        from app.data.backtesting_engine import run_backtest, BacktestConfig

        holdings  = load_portfolio(settings.portfolio_file)
        tickers   = [h.ticker for h in holdings]

        st.markdown("#### Backtest Settings")
        c1, c2, c3, c4 = st.columns(4)
        benchmark           = c1.text_input("Benchmark", value="SPY")
        lookback_days       = c2.slider("Lookback Days", 90, 365, 180, 15)
        rebalance_frequency = c3.slider("Rebalance Frequency (Days)", 5, 63, 21, 1)
        transaction_cost    = c4.slider("Transaction Cost (bps)", 0, 50, 10, 1)
        initial_capital     = st.number_input("Initial Capital ($)", min_value=1000.0, value=10000.0, step=1000.0)

        config = BacktestConfig(
            benchmark=benchmark.upper().strip(),
            lookback_days=int(lookback_days),
            rebalance_frequency_days=int(rebalance_frequency),
            transaction_cost_bps=float(transaction_cost),
            initial_capital=float(initial_capital),
        )

        if st.button("Run Backtest", type="primary"):
            with st.spinner("Running backtest..."):
                st.session_state["latest_backtest"] = run_backtest(tickers, config=config)

        result = st.session_state.get("latest_backtest")
        if not result:
            st.info("Click Run Backtest to simulate the construction engine historically.")
            return
        if result.get("status") != "Ready":
            st.warning(result.get("message", "Backtest unavailable."))
            return

        metrics = result.get("metrics", {})
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Strategy Return",    f"{metrics.get('strategy_total_return_pct', 0):+.2f}%")
        m2.metric("Benchmark Return",   f"{metrics.get('benchmark_total_return_pct', 0):+.2f}%")
        m3.metric("Active Return",      f"{metrics.get('active_return_pct', 0):+.2f}%")
        m4.metric("Max Drawdown",       f"{metrics.get('max_drawdown_pct', 0):+.2f}%")

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Sharpe",             f"{metrics.get('sharpe_ratio', 0):.2f}")
        r2.metric("Sortino",            f"{metrics.get('sortino_ratio', 0):.2f}")
        r3.metric("Beta",               f"{metrics.get('beta_to_benchmark', 0):.2f}")
        r4.metric("Annualized Alpha",   f"{metrics.get('annualized_alpha_pct', 0):+.2f}%")

        t1, t2, t3 = st.columns(3)
        t1.metric("Avg Turnover",       f"{metrics.get('avg_turnover_pct', 0):.2f}%")
        t2.metric("Transaction Costs",  f"${metrics.get('total_transaction_cost_$', 0):,.2f}")
        t3.metric("Rebalances",         metrics.get("rebalance_count", 0))

        st.divider()
        equity = pd.DataFrame(result.get("equity_curve", []))
        if not equity.empty:
            st.markdown("#### Strategy vs Benchmark")
            chart = equity.set_index("date")[["strategy_value","benchmark_value"]].rename(columns={
                "strategy_value": "Strategy Value ($)", "benchmark_value": "Benchmark Value ($)"
            })
            st.line_chart(chart, height=360)
            st.dataframe(_format_table(equity), use_container_width=True, hide_index=True)

        turnover = pd.DataFrame(result.get("turnover", []))
        if not turnover.empty:
            st.divider()
            st.markdown("#### Turnover and Transaction Costs")
            st.bar_chart(turnover.set_index("date")[["turnover_pct"]].rename(columns={"turnover_pct": "Turnover (%)"}), height=300)
            st.dataframe(_format_table(turnover), use_container_width=True, hide_index=True)

        factor_contribution = pd.DataFrame(result.get("factor_contribution", []))
        if not factor_contribution.empty:
            st.divider()
            st.markdown("#### Factor Contribution Over Time")
            st.bar_chart(factor_contribution.set_index("ticker")[[
                "avg_composite_score","avg_momentum_score","avg_volatility_score",
                "avg_relative_strength_score","avg_drawdown_score",
            ]].rename(columns={
                "avg_composite_score": "Avg Composite (0-100)",
                "avg_momentum_score": "Avg Momentum (0-100)",
                "avg_volatility_score": "Avg Volatility (0-100)",
                "avg_relative_strength_score": "Avg Rel. Strength (0-100)",
                "avg_drawdown_score": "Avg Drawdown (0-100)",
            }), height=360)
            st.dataframe(_format_table(factor_contribution), use_container_width=True, hide_index=True)

    except Exception as exc:
        st.error(f"Backtesting engine failed: {exc}")


# ── App entry point ────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="Daily Portfolio Brief",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(APP_CSS, unsafe_allow_html=True)
    init_state()

    page = render_sidebar()

    portfolio_path = Path(
        st.session_state.get("portfolio_path_override")
        or st.session_state.get("portfolio_path")
        or str(DEFAULT_PORTFOLIO_PATH)
    )
    df = load_portfolio(portfolio_path)

    render_header()
    st.divider()

    dispatch = {
        "Overview":        lambda: render_overview(df, portfolio_path),
        "Portfolio":       lambda: render_portfolio(df, portfolio_path),
        "Monitor":         render_monitor,
        "Market Workbench": render_market_workbench,
        "Analytics":       lambda: render_analytics(df),
        "Factors":         render_factors,
        "Newsletter":      render_newsletter_actions,
        "Morning Brief":   render_morning_brief,
        "Preferences":     render_newsletter_preferences,
        "Preview":         render_preview,
        "Files":           lambda: render_files(portfolio_path),
        "History":         render_history,
        "Alerts":          render_alerts,
        "Construction":    render_construction,
        "Backtesting":     render_backtesting,
        "Execution":       render_execution,
    }

    renderer = dispatch.get(page)
    if renderer:
        renderer()
    else:
        st.error(f"Unknown page: {page}")


# Fix missing json import used in render_newsletter_preferences
import json
def json_dumps(obj): return json.dumps(obj, indent=2)


if __name__ == "__main__":
    main()