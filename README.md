<div align="center">
  <h1>Portfolio Intelligence Automation System</h1>
  <p><strong>A daily investing briefing that runs itself — built with Claude Sonnet 4.6</strong></p>
  <p>
    <img src="https://img.shields.io/badge/Status-Live-brightgreen?style=flat-square" />
    <img src="https://img.shields.io/badge/Runs-Every%20Morning-blue?style=flat-square" />
    <img src="https://img.shields.io/badge/Data%20Sources-5%2B-blue?style=flat-square" />
    <img src="https://img.shields.io/badge/Built%20with-Claude%20Sonnet%204.6-blueviolet?style=flat-square" />
    <img src="https://img.shields.io/badge/Stack-Python%20%7C%20Jinja2%20%7C%20Streamlit-orange?style=flat-square" />
  </p>
</div>

---

Most investing tools give you noise — analyst price targets, sentiment scores, and AI-generated market takes. This system doesn't.

It wakes up every morning before market open, pulls verified data from 5+ sources, filters it down to what's actually relevant to *your* portfolio, and delivers a clean institutional-style briefing to your inbox. No opinions. No AI conclusions. Just the facts that move markets: earnings, filings, macro releases, and price action — organized so you can read it in five minutes.

Built end-to-end with **Claude Sonnet 4.6** in VS Code. Fully autonomous once deployed — scheduled via macOS `launchd`, runs overnight, arrives before the open bell.

---

## The Briefing

The output is a single polished HTML email — dark-themed, mobile-responsive, structured like an institutional morning note. Every section filters to your actual holdings.

<img src="https://img.shields.io/badge/Output-HTML%20Email-1c2030?style=flat-square&logoColor=white" />

| Section | What it covers |
|---|---|
| **Portfolio Snapshot** | Live prices, daily P&L, position-level change across all holdings |
| **Top Movers** | Biggest gainers and losers with context |
| **Alerts** | Price, volume, and momentum flags — things that actually warrant attention |
| **Portfolio News** | Real headlines filtered to your holdings — no general market chatter |
| **SEC Filings Monitor** | 8-K, 10-Q, 13-F activity for every company you own |
| **Earnings Calendar** | Upcoming dates for holdings and watchlist names |
| **Market Update** | Broad market summary across equities, fixed income, and commodities |
| **Macro Snapshot** | Cross-asset regime inference — risk-on, risk-off, or transitional |
| **Economic Calendar** | Upcoming releases with consensus estimates |
| **Global Developments** | Macro and geopolitical headlines with market relevance |

### What it deliberately excludes
- No analyst price targets or buy/sell ratings
- No AI-generated investment conclusions
- No sentiment scores or social media signals
- No paywalled content

The pipeline surfaces *what happened* — filings filed, numbers released, rates moved. What you do with it is up to you.

---

## How It Works

```
overnight_runner.py        runs on a launchd schedule (macOS daemon)
       ↓
generate_hybrid_newsletter.py   fetches all data sources in parallel
       ↓
  app/data/
    news_feed.py           company + market + global news, deduplicated by source rank
    sec_filings.py         SEC EDGAR API — filters to portfolio companies
    earnings.py            earnings calendar data
    alert_engine.py        price/volume/momentum alert detection
    holdings_monitor.py    tracks position changes vs. prior day
    regime_engine.py       cross-asset regime inference
    market_workbench.py    macro dashboard data
    morning_brief_engine.py  top-of-briefing synthesis
       ↓
templates/                 Jinja2 HTML templates — dark theme, mobile-responsive
       ↓
send_newsletter.py         Resend API → your inbox before market open
```

**User preferences** (`data/users/demo/newsletter_preferences.json`) let you toggle any section on or off. Everything except your `.env` and output files is committed — the system is fully reproducible.

---

## Architecture

```
portfolio-intelligence/
  main.py                        — single entry point
  generate_hybrid_newsletter.py  — full pipeline
  send_newsletter.py             — email delivery
  overnight_runner.py            — daemon entry point
  portfolio.yml                  — your holdings
  requirements.txt
  templates/                     — Jinja2 HTML email templates
  app/
    data/                        — all data source modules
    dashboard/
      streamlit_app.py           — local control center (optional)
```

---

## Setup

```bash
git clone https://github.com/garv-acg/portfolio-intelligence.git
cd portfolio-intelligence
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add your API keys
```

Edit `portfolio.yml` with your tickers, then:

```bash
python main.py
# → output/latest_newsletter.html
```

### API Keys

| Key | Purpose | Required? |
|---|---|---|
| `RESEND_API_KEY` | Email delivery | For automated delivery |
| `NEWSAPI_KEY` | Broader news coverage | Recommended |
| `OPENAI_API_KEY` | Improved summarization | Optional |

Runs without any keys using Yahoo Finance data and deterministic fallbacks.

### Automated Scheduling (macOS)

```bash
python install_morning_brief_engine.py
# Installs a launchd plist → ~/Library/LaunchAgents/
# Runs overnight. Briefing arrives before market open.
```

### Local Dashboard

```bash
streamlit run app/dashboard/streamlit_app.py
```

Generate on-demand briefings, toggle sections, manage your portfolio, and review alert history from a local control center UI.

---

<div align="center">
  <sub>Built with Claude Sonnet 4.6 · Facts only, no opinions · Fully autonomous</sub>
</div>
