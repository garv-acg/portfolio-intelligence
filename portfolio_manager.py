"""
portfolio_manager.py
─────────────────────
Local Streamlit dashboard for managing your portfolio holdings and
transaction log without touching CSV files by hand.

Run:
    streamlit run portfolio_manager.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PORTFOLIO_PATH    = Path("data/users/demo/portfolio.csv")
TRANSACTIONS_PATH = Path("data/transactions.csv")


# ── Portfolio (holdings) ────────────────────────────────────────────────────────

def normalize_portfolio(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    lower_map = {col.lower().strip(): col for col in df.columns}

    for col, default in [("ticker", ""), ("shares", 0.0), ("name", ""), ("cost_basis", "")]:
        if col not in lower_map:
            df[col] = default
        else:
            df = df.rename(columns={lower_map[col]: col})

    df["ticker"]     = df["ticker"].astype(str).str.upper().str.strip()
    df["shares"]     = pd.to_numeric(df["shares"], errors="coerce").fillna(0.0)
    df["cost_basis"] = pd.to_numeric(df["cost_basis"], errors="coerce")

    preferred = ["ticker", "shares", "name", "cost_basis"]
    remaining = [c for c in df.columns if c not in preferred]
    return df[preferred + remaining]


def load_portfolio(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["ticker", "shares", "name", "cost_basis"])
    return normalize_portfolio(pd.read_csv(path))


def save_portfolio(path: Path, df: pd.DataFrame) -> None:
    df = normalize_portfolio(df)
    df = df[df["ticker"].astype(str).str.strip() != ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


# ── Transactions ────────────────────────────────────────────────────────────────

def normalize_transactions(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    lower_map = {col.lower().strip(): col for col in df.columns}

    for col, default in [("date", ""), ("ticker", ""), ("action", "buy"), ("shares", 0.0), ("price", 0.0), ("notes", "")]:
        if col not in lower_map:
            df[col] = default
        else:
            df = df.rename(columns={lower_map[col]: col})

    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    df["action"] = df["action"].astype(str).str.lower().str.strip()
    df["shares"] = pd.to_numeric(df["shares"], errors="coerce").fillna(0.0)
    df["price"]  = pd.to_numeric(df["price"],  errors="coerce").fillna(0.0)

    preferred = ["date", "ticker", "action", "shares", "price", "notes"]
    remaining = [c for c in df.columns if c not in preferred]
    return df[preferred + remaining]


def load_transactions(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["date", "ticker", "action", "shares", "price", "notes"])
    return normalize_transactions(pd.read_csv(path))


def save_transactions(path: Path, df: pd.DataFrame) -> None:
    df = normalize_transactions(df)
    df = df[df["ticker"].astype(str).str.strip() != ""]
    df = df.sort_values("date")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


# ── App ────────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(page_title="Portfolio Manager", page_icon="📊", layout="wide")
    st.title("Portfolio Manager")
    st.caption("Edit holdings and transactions without touching CSV files. Changes save directly to disk.")

    tab_holdings, tab_txns, tab_send = st.tabs(["Holdings", "Transactions", "Generate & Send"])

    # ── Holdings tab ─────────────────────────────────────────────────────────
    with tab_holdings:
        st.subheader("Current Holdings")
        st.caption(f"File: `{PORTFOLIO_PATH}`")

        df = load_portfolio(PORTFOLIO_PATH)

        c1, c2 = st.columns(2)
        with c1:
            st.metric("Holdings", len(df[df["ticker"].astype(str).str.strip() != ""]))
        with c2:
            total_shares = pd.to_numeric(df["shares"], errors="coerce").fillna(0).sum()
            st.metric("Total Shares", f"{total_shares:,.3f}")

        edited = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "ticker": st.column_config.TextColumn("Ticker", required=True),
                "shares": st.column_config.NumberColumn("Shares", min_value=0.0, step=0.001, format="%.6f", required=True),
                "name": st.column_config.TextColumn("Company Name"),
                "cost_basis": st.column_config.NumberColumn("Cost Basis ($/share)", min_value=0.0, step=0.01, format="%.2f"),
            },
            hide_index=True,
            key="holdings_editor",
        )

        c1, c2 = st.columns([1, 3])
        with c1:
            if st.button("Save Holdings", type="primary", use_container_width=True):
                save_portfolio(PORTFOLIO_PATH, edited)
                st.success(f"Saved to {PORTFOLIO_PATH}")
        with c2:
            if st.button("Reload Holdings", use_container_width=True):
                st.rerun()

    # ── Transactions tab ─────────────────────────────────────────────────────
    with tab_txns:
        st.subheader("Transaction Log")
        st.caption(
            f"File: `{TRANSACTIONS_PATH}` — used to compute your real time-weighted "
            "return (Daily / Weekly / Monthly / YTD). Add a row every time you buy or sell."
        )

        txns = load_transactions(TRANSACTIONS_PATH)

        edited_txns = st.data_editor(
            txns,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "date": st.column_config.TextColumn("Date (YYYY-MM-DD)", required=True),
                "ticker": st.column_config.TextColumn("Ticker", required=True),
                "action": st.column_config.SelectboxColumn("Action", options=["buy", "sell"], required=True),
                "shares": st.column_config.NumberColumn("Shares", min_value=0.0, step=0.001, format="%.6f", required=True),
                "price": st.column_config.NumberColumn("Price ($)", min_value=0.0, step=0.01, format="%.2f", required=True),
                "notes": st.column_config.TextColumn("Notes"),
            },
            hide_index=True,
            key="txns_editor",
        )

        c1, c2 = st.columns([1, 3])
        with c1:
            if st.button("Save Transactions", type="primary", use_container_width=True):
                try:
                    pd.to_datetime(edited_txns["date"])
                except Exception:
                    st.error("One or more dates are invalid. Use YYYY-MM-DD format.")
                else:
                    save_transactions(TRANSACTIONS_PATH, edited_txns)
                    st.success(f"Saved to {TRANSACTIONS_PATH}")
        with c2:
            if st.button("Reload Transactions", use_container_width=True):
                st.rerun()

        st.divider()
        st.caption("Tip: use the market price on the trade date, not your average cost basis — this is what drives accurate YTD vs SPY comparisons.")

    # ── Generate & Send tab ──────────────────────────────────────────────────
    with tab_send:
        st.subheader("Generate & Send Newsletter")
        st.caption("Run the pipeline directly from here instead of using the terminal.")

        mode = st.radio("Mode", ["Daily Brief", "Weekly Digest"], horizontal=True)
        weekly_flag = ["--weekly"] if mode == "Weekly Digest" else []

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Generate Only", use_container_width=True):
                with st.spinner("Generating newsletter..."):
                    result = subprocess.run(
                        [sys.executable, "main.py", *weekly_flag],
                        capture_output=True, text=True, cwd=Path(__file__).parent,
                    )
                if result.returncode == 0:
                    st.success("Generated successfully.")
                    st.code(result.stdout)
                else:
                    st.error("Generation failed.")
                    st.code(result.stdout + result.stderr)

        with c2:
            if st.button("Generate & Send", type="primary", use_container_width=True):
                with st.spinner("Generating and sending..."):
                    gen = subprocess.run(
                        [sys.executable, "main.py", *weekly_flag],
                        capture_output=True, text=True, cwd=Path(__file__).parent,
                    )
                    if gen.returncode != 0:
                        st.error("Generation failed.")
                        st.code(gen.stdout + gen.stderr)
                    else:
                        send = subprocess.run(
                            [sys.executable, "send_newsletter.py"],
                            capture_output=True, text=True, cwd=Path(__file__).parent,
                        )
                        if send.returncode == 0:
                            st.success("Sent successfully.")
                            st.code(gen.stdout + "\n" + send.stdout)
                        else:
                            st.error("Send failed.")
                            st.code(send.stdout + send.stderr)

        st.divider()
        output_html = Path("output/latest_newsletter.html")
        if output_html.exists():
            st.subheader("Last Generated Preview")
            st.components.v1.html(output_html.read_text(encoding="utf-8"), height=800, scrolling=True)


if __name__ == "__main__":
    main()
