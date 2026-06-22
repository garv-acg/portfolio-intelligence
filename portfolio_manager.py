from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st


DEFAULT_PORTFOLIO_PATH = Path("portfolio.csv")


def find_portfolio_file() -> Path:
    candidates = [
        Path("portfolio.csv"),
        Path("data/portfolio.csv"),
        Path("app/config/portfolio.csv"),
        Path("app/data/portfolio.csv"),
    ]

    for path in candidates:
        if path.exists():
            return path

    return DEFAULT_PORTFOLIO_PATH


def normalize_portfolio(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    lower_map = {col.lower().strip(): col for col in df.columns}

    if "ticker" not in lower_map:
        df["ticker"] = ""
    else:
        df = df.rename(columns={lower_map["ticker"]: "ticker"})

    if "shares" not in lower_map:
        df["shares"] = 0.0
    else:
        df = df.rename(columns={lower_map["shares"]: "shares"})

    if "name" not in [c.lower() for c in df.columns]:
        df["name"] = ""

    if "cost_basis" not in [c.lower() for c in df.columns]:
        df["cost_basis"] = ""

    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    df["shares"] = pd.to_numeric(df["shares"], errors="coerce").fillna(0.0)

    preferred = ["ticker", "shares", "name", "cost_basis"]
    remaining = [col for col in df.columns if col not in preferred]

    return df[preferred + remaining]


def load_portfolio(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["ticker", "shares", "name", "cost_basis"])

    df = pd.read_csv(path)
    return normalize_portfolio(df)


def save_portfolio(path: Path, df: pd.DataFrame) -> None:
    df = normalize_portfolio(df)
    df = df[df["ticker"].astype(str).str.strip() != ""]
    df.to_csv(path, index=False)


def main() -> None:
    st.set_page_config(
        page_title="Portfolio Manager",
        page_icon="📊",
        layout="wide",
    )

    st.title("Portfolio Manager")
    st.caption("Edit holdings without touching code. Changes save directly to your portfolio CSV.")

    portfolio_path = find_portfolio_file()

    with st.sidebar:
        st.header("Settings")
        path_text = st.text_input("Portfolio CSV path", value=str(portfolio_path))
        portfolio_path = Path(path_text)

        st.divider()
        st.subheader("Workflow")
        st.write("1. Edit holdings")
        st.write("2. Save portfolio")
        st.write("3. Run newsletter")

    df = load_portfolio(portfolio_path)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Holdings", len(df[df["ticker"].astype(str).str.strip() != ""]))

    with col2:
        total_shares = pd.to_numeric(df["shares"], errors="coerce").fillna(0).sum() if "shares" in df else 0
        st.metric("Total Shares", f"{total_shares:,.3f}")

    with col3:
        st.metric("Portfolio File", str(portfolio_path))

    st.divider()
    st.subheader("Edit Holdings")

    edited = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "ticker": st.column_config.TextColumn(
                "Ticker",
                help="Stock ticker symbol",
                required=True,
            ),
            "shares": st.column_config.NumberColumn(
                "Shares",
                help="Number of shares owned",
                min_value=0.0,
                step=0.001,
                format="%.6f",
                required=True,
            ),
            "name": st.column_config.TextColumn(
                "Company Name",
                help="Optional display name",
            ),
            "cost_basis": st.column_config.TextColumn(
                "Cost Basis",
                help="Optional cost basis field",
            ),
        },
        hide_index=True,
    )

    st.divider()

    c1, c2, c3 = st.columns([1, 1, 2])

    with c1:
        if st.button("Save Portfolio", type="primary", use_container_width=True):
            save_portfolio(portfolio_path, edited)
            st.success(f"Saved portfolio to {portfolio_path}")

    with c2:
        if st.button("Reload", use_container_width=True):
            st.rerun()

    with c3:
        st.info("After saving, run `python main.py` to regenerate the newsletter with the updated portfolio.")

    st.divider()
    st.subheader("Preview Saved CSV")

    if portfolio_path.exists():
        st.code(portfolio_path.read_text(), language="csv")
    else:
        st.warning("Portfolio file does not exist yet. Save once to create it.")


if __name__ == "__main__":
    main()
