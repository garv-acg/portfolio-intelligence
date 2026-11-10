# Control Center — design rationale & setup

A full rewrite of `newsletter_control_center.py` (the Streamlit "Control
Center") into a FastAPI backend + a Notion-styled vanilla-JS frontend on
Netlify. Companion to `DESIGN_RATIONALE.md` (the Daily Brief dashboard) —
same design system, different product: that one is a read-only morning
brief, this one is an editable workbench (edit holdings, run backtests,
approve paper trades).

## Why a full rewrite, not a restyle

The Streamlit app is interactive in a way the Daily Brief never was: sliders
that re-run the factor/construction engine, an approve/reject execution
blotter with a real paper-trade ledger, a backtester. That needs a running
Python process, which Netlify can't provide — it only serves static files
and small serverless functions. Given that hard constraint, the options were
(a) restyle Streamlit and host it somewhere that runs Python (Render,
Streamlit Community Cloud), or (b) rewrite it as a real web app: FastAPI
backend on Render + a hand-built frontend on Netlify. You chose (b) for
full design control and to genuinely satisfy "Netlify-linked."

## What was broken, and got fixed for free by this rewrite

Investigation before writing any code turned up real, pre-existing bugs in
the Streamlit app, unrelated to its looks:

- **5 of 11 pages were dead on arrival** — Monitor, Market Workbench,
  Analytics, Construction, and Backtesting all imported `app.config.portfolio`,
  a module deleted in the Nov 10 cleanup pass and never updated. They were
  silently showing error banners. The new backend reads holdings through
  `server/shared.py` → `portfolio_store.py`, not that dead import.
- Those same five pages read portfolio holdings from a stale root
  `portfolio.yml` via `app.config.settings`, not the real file the daily
  email uses (`data/users/demo/portfolio.csv`). Every endpoint in `server/`
  now goes through one shared resolution path.
- A second, undiscovered Streamlit app (`portfolio_manager.py`) edited the
  transaction log — folded into the new Portfolio page's Transactions tab.
- A second, duplicate newsletter builder (`app/data/morning_brief_engine.py`)
  existed alongside the one real pipeline — not carried into the rewrite;
  the new Newsletter page links to the live dashboard instead.

## Competitor research — what was borrowed

- **Composer.trade** — weighting/construction UI (custom weight vs.
  inverse-vol vs. equal weight) confirmed the slider-driven constraint model
  (max position/sector weight, rebalance threshold) was the right shape for
  the Construction page; kept the same four controls the Streamlit version
  had rather than adding more.
- **QuantConnect's backtest report** — a runtime-stats banner above an
  equity curve (strategy vs. benchmark, one in the accent hue, the other in
  a muted ink — the dataviz skill's "emphasis" pattern: one series is the
  point, the other is context) is the Backtesting page's layout: stat tiles
  first, equity curve table second.
- **Portfolio Visualizer** — confirmed drift-based (vs. calendar) rebalance
  thresholds are the standard mental model; the existing rebalance-threshold
  slider already matched this, so no change there beyond fixing the broken
  import.
- **Interactive Brokers' TWS blotter** — a lifecycle-aware blotter (pending
  → filled, with a visible pending state) and "never execute by accident"
  guardrails (a confirm note + optional simulated price per trade, no
  one-click silent fills) shaped the Execution page's approve/reject flow.

## Architecture

```
webapp/ (Netlify: portfolio-control-center.netlify.app)
  vanilla HTML/CSS/JS, same design tokens as site/styles.css.
  11 pages, client-side router (#hash), fetches server/ as a JSON API.
       │
       ▼ fetch (x-api-key header, defense in depth — see below)
server/ (Render: portfolio-control-center-api.onrender.com)
  FastAPI. Every "live data" route (Monitor, Market Workbench, Analytics,
  Factors, Construction, Backtesting, Alerts) recomputes fresh from Yahoo/
  FRED/SEC on each request — no caching, no persistence, same engines
  generate_hybrid_newsletter.py already uses.
       │
       ▼ only for: holdings, transactions, execution ledger, pipeline status
Neon Postgres (free tier)
```

**What's shared with the local email pipeline, and how:**
`portfolio_store.py` (repo root) is a dual-mode adapter. With `DATABASE_URL`
unset (the default), it's byte-for-byte the old CSV behavior — zero risk to
the pipeline you depend on daily. With it set, Postgres becomes the source
of truth for holdings/transactions (read-through with a CSV fallback on any
Postgres hiccup, write-through to both). `generate_hybrid_newsletter.py`'s
`load_portfolio()` and `app/data/portfolio_returns.py`'s `load_transactions()`
were given the same three-line pattern: try Postgres if configured, fall
back to the exact original CSV code on any failure. **Verified**: ran the
full local pipeline (`overnight_runner.py`, no skip flags) after this change
with `DATABASE_URL` unset — identical output to before.

**What's new, used only by this app** (no bearing on the email pipeline):
the execution ledger (`rebalance_recommendations`, `paper_trades`,
`execution_audit`, `execution_state` for cash) and `pipeline_status` (a
one-row-per-run mirror so this app can show "last run" without needing
access to the local machine's log files).

**Why alerts aren't read from a log here**: the local Streamlit app reads a
daily sqlite alert log the email pipeline writes locally. Render can't see
that file, so `/api/alerts` recomputes the same categories of alert live on
every request from the same `build_alerts()` function — with one
intentional gap: regime-shift detection needs yesterday's regime value
(local-only history), so that one alert type never fires here (it still
fires in the daily email).

## Auth

Netlify's **account-wide SSO/visitor-access is on** for this Personal
account (same as the Daily Brief dashboard — see `CLAUDE.md`), so the
frontend itself requires your Netlify login to view at all. The raw Render
API URL, though, is a separate public endpoint — CORS restricts which web
origins a *browser* can call it from, but does nothing against a direct
`curl`/script hitting that URL. `server/main.py` adds a shared-secret
`X-API-Key` header check (`require_api_key`), a no-op if `API_KEY` isn't
set (so local dev needs no setup) but enforced once it is. This is defense
in depth, not real secrecy — the key would be visible to anyone who opens
dev tools on the (already SSO-gated) frontend — but it closes the "URL
guessing" gap for the unauthenticated public internet.

## What you still need to do (things only you can do)

1. **Create a Neon project** (neon.tech, free tier) for this app's execution
   ledger + shared portfolio state. Copy its connection string.
2. **Create the Render web service** from `render.yaml` in this repo
   (Render → New → Blueprint → connect `garv-acg/portfolio-intelligence`).
   In Render's dashboard, set the env vars it created as `sync: false`
   placeholders: `DATABASE_URL` (from step 1) and `API_KEY` (any random
   string you pick).
3. Once Render gives you the live URL, tell me — if it's not exactly
   `https://portfolio-control-center-api.onrender.com`, I need to update
   `webapp/index.html`'s `API_BASE` and redeploy.
4. Pick the same `API_KEY` value and I'll bake it into `webapp/index.html`'s
   `window.API_KEY` and redeploy — until then the API has no auth enforced
   (fine for initial testing, not for leaving it running long-term).
5. Optional: set `DATABASE_URL` in this repo's local `.env` too, so the
   local pipeline starts reading/writing the same Postgres holdings table
   the web app uses, instead of the local CSV.

## Verified locally before hand-off

- All 11 pages load and render against the live engines (no mock data).
- Construction → Save to Execution Queue → Execution → Approve/Reject →
  Paper Trade Ledger + Audit Trail, tested end-to-end against a throwaway
  local Postgres database (not Neon — that still needs your account).
- Backtesting runs and renders real metrics/equity curve.
- Light/dark mode both verified.
- Full local email pipeline re-run after the `portfolio_store.py` change,
  confirmed byte-identical behavior with `DATABASE_URL` unset.
- `API_KEY` enforcement verified: unset → open, set → 401 without the
  header, 200 with the correct one.

## Known gaps / deliberate v1 cuts

- Multi-profile switching (the Streamlit app's user-profile selector) isn't
  rebuilt — only the one portfolio you actually use is wired up. The
  underlying `app/config/user_profiles.py` system is untouched if you want
  this back later.
- No "Preferences" page (the 11 newsletter-section toggles) — local-only
  for now; lower value than the pages that were actually broken.
- No "Generate Now" button on the Newsletter page — triggering the real
  pipeline (and a real Gmail send) from a public web app risks a duplicate
  send and needs every local secret duplicated on Render. Generation stays
  on the local machine's schedule; this page just shows whether it last
  succeeded.
- `cumulative_attribution` (Factors page's second tab) will show "no data"
  — it reads a table nothing in the live pipeline populates (pre-existing,
  not introduced by this rewrite).
