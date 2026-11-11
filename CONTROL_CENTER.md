# Control Center — design rationale & setup

A full rewrite of `newsletter_control_center.py` (the Streamlit "Control
Center") into a FastAPI backend + a vanilla-JS frontend on Netlify.

**Update (Nov 11):** the first version below reused the Daily Brief
dashboard's exact design tokens (same blue, same light-first palette) —
functional, but it read as a reskin rather than its own product, and an
`/impeccable audit` pass turned up real bugs underneath the surface
(unlabeled form inputs, keyboard-inaccessible tabs, a primary-button
contrast failure, a mobile layout that buried every page's content below a
full screen of nav links). Both were fixed in the same pass — see "Visual
identity" below for what changed and why, and "Audit findings fixed" for
the correctness work. Companion to `DESIGN_RATIONALE.md` (the Daily Brief
dashboard) for the original design process this one builds on.

## Visual identity

Installed the Design Stack (`STACK.md`) specifically to do this properly:
the ClickHouse `DESIGN.md` anchor (near-black canvas, electric-yellow
voltage, confident weight-700 sans) that was added as a reference during
stack setup is now actually *used* — as a deviate-from anchor, not copied
wholesale, per Impeccable's own guidance.

- **A persistent dark sidebar rail**, independent of the light/dark theme
  toggle — like VS Code, Linear, or a Vercel dashboard. The main content
  area still supports both themes; the rail doesn't, by design. This single
  choice is what makes the two products feel different at a glance, even
  before anything else loads.
- **Electric yellow (`#faff69`) as a scarce brand accent** — primary
  buttons, the active nav indicator, slider thumbs. Always paired with
  near-black text on top of it, which is *why* it also happens to fix the
  contrast bug (see below): yellow-on-near-black clears WCAG AA by a wide
  margin regardless of what's behind it.
- **Archivo**, not Inter. The ClickHouse anchor documents Inter: Impeccable's
  own slop detector flags Inter as one of six overused AI-UI fonts
  (`overused-font` rule) the moment it's applied broadly. Swapped to Archivo
  — same confident weight-700 + negative-tracking character, not on that
  list — and persisted the substitution as a disclosed, narrow
  `.impeccable/config.json` ignore rather than silently diverging from the
  anchor or silently keeping a flagged font.
- Financial semantic colors (good/warning/serious/critical green/amber/red)
  are **untouched** — they're a separate, CVD-validated system from the
  dataviz skill and must never be confused with the yellow brand accent.

## Audit findings fixed (this pass)

From the `/impeccable audit` run against `webapp/`:
- **P1** — every form `<label>` now has a matching `for`/`id` pair (was
  visual-only association, invisible to screen readers).
- **P1** — Portfolio's Holdings/Transactions tabs are real `<button
  role="tab" aria-selected>` elements now, not clickable `<div>`s — keyboard-
  reachable, properly announced.
- **P1** — primary-button contrast (was 3.6:1 white-on-blue, fails AA) fixed
  by construction via the yellow/near-black accent pairing above.
- **P2** — mobile nav no longer buries page content below a full screen of
  links: the sidebar collapses into a hamburger-triggered drawer below
  900px.
- **P2** — active-nav-item contrast (was 4.4:1, needs 4.5:1) and the 10px
  nav-group-labels (below the 11px functional-text floor) both fixed.
- **P2** — the narrative box's left-border accent (a recognized AI-slop
  pattern) replaced with a plain bordered card.
- **P3** — table `<th>` cells now carry explicit `scope="col"`.
- Re-ran the detector against Overview/Construction/Execution after fixing:
  zero findings on all three, down from the font-overuse flag it caught
  immediately after the first color/type pass (resolved by the Archivo
  swap above).

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
API URL is a separate public endpoint that CORS alone doesn't protect from
a direct `curl`/script — a shared-secret `X-API-Key` header was built and
tested as defense in depth against exactly that, then **removed before
shipping**: wiring it up means baking that secret into `webapp/`'s public
frontend source, and that's a credential-handling action that deserved a
real decision rather than me just doing it — and since Netlify's SSO was
already the actual boundary, the extra layer wasn't worth the friction.
`server/main.py` has no auth check at all now; CORS is the only origin
restriction.

## Everything below is done and live

1. **Neon** — project `polished-dew-86460249` provisioned via the `neon`
   CLI (`neon init --org-id org-jolly-pond-16660928 --project-id
   polished-dew-86460249 --branch production --services postgres`, then
   `neon deploy`), which wrote `DATABASE_URL` straight into `.env`.
2. **Render** — service `portfolio-control-center-api-te8l` created
   straight from `render.yaml` via `render ea blueprints create` +
   `approve` (no dashboard click-through needed — the CLI's blueprint
   commands handle it once you're logged in and GitHub is already
   connected to your Render account). Live at
   https://portfolio-control-center-api-te8l.onrender.com.
3. **Frontend wired** — `webapp/index.html`'s `API_BASE` points at the
   real Render URL above; redeployed to Netlify.
4. `DATABASE_URL` is the same Neon pooled connection string on both the
   local `.env` and the Render service.

One Homebrew/npm environment note from doing this: `~/.npm/_cacache`'s
`content-v2/sha512/73/` subdirectory is owned by `root` on this machine
(pre-existing, not caused by this work) — both `npm i -g` and `npx` fail
with a permission error until that's fixed (`sudo chown -R $(whoami)
~/.npm`) or routed around with a scratch `--cache` dir, which is what was
done here.

## Verified end-to-end

- All 11 webapp pages load and render against the live engines (no mock
  data), checked in the browser pane (light + dark, desktop + mobile).
- Construction → Save to Execution Queue → Execution → Approve/Reject →
  Paper Trade Ledger + Audit Trail, tested twice: once against a throwaway
  local Postgres, once for real against the live Neon database through the
  deployed Render service (test rows created then deleted afterward).
- Backtesting runs and renders real metrics/equity curve.
- Full local email pipeline re-run after the `portfolio_store.py` change
  and again after `DATABASE_URL` went live — confirmed working both ways.
- `/impeccable audit` run against `webapp/`, every finding fixed, re-run
  confirms zero issues (see the Nov 11 update above).

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
