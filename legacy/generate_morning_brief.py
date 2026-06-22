from pathlib import Path
import pandas as pd

from app.data.earnings import get_upcoming_earnings
from app.data.sec_filings import get_sec_filings
from app.data.alert_engine import latest_alerts
from app.data.market_workbench import macro_dashboard
from app.data.holdings_monitor import build_holdings_change_monitor
from app.data.morning_brief_engine import build_morning_brief, save_morning_brief_outputs


class Holding:
    def __init__(self, ticker, shares, cost_basis=0):
        self.ticker = str(ticker).upper()
        self.shares = float(shares or 0)
        self.cost_basis = float(cost_basis or 0)


def load_active_portfolio() -> list[Holding]:
    portfolio_path = Path("data/users/demo/portfolio.csv")

    if not portfolio_path.exists():
        portfolio_path = Path("portfolio.csv")

    df = pd.read_csv(portfolio_path)

    holdings = []
    for _, row in df.iterrows():
        holdings.append(
            Holding(
                ticker=row.get("ticker", ""),
                shares=row.get("shares", 0),
                cost_basis=row.get("cost_basis", 0),
            )
        )

    return holdings


def main() -> None:
    holdings = load_active_portfolio()
    tickers = [h.ticker for h in holdings]

    earnings = get_upcoming_earnings(tickers, days_ahead=30)
    sec = get_sec_filings(tickers, lookback_days=30, max_filings_per_ticker=3)
    alerts = latest_alerts(limit=25)
    macro = macro_dashboard()

    monitor = build_holdings_change_monitor(
        holdings,
        earnings_calendar=earnings,
        sec_filings=sec,
        benchmark="SPY",
    )

    brief = build_morning_brief(
        portfolio_rows=monitor.get("holdings", []),
        holdings_monitor_rows=monitor.get("holdings", []),
        earnings_calendar=earnings,
        sec_filings=sec,
        alerts=alerts,
        macro_data=macro,
    )

    paths = save_morning_brief_outputs(brief)

    # Also overwrite the legacy newsletter paths so send_newsletter.py emails this version.
    Path("output/latest_newsletter.html").write_text(
        Path(paths["html"]).read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    Path("output/latest_newsletter.txt").write_text(
        Path(paths["text"]).read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    print("Morning Brief generated.")
    print(f"HTML: {paths['html']}")
    print(f"Text: {paths['text']}")


if __name__ == "__main__":
    main()
