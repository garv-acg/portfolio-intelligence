# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary user is the tool's owner/operator — an individual managing their own real brokerage-style portfolio. Currently single-user/solo (one portfolio file, one email recipient), but the owner may eventually share this with other people, so multi-person use shouldn't be designed out of future work even though nothing here is multi-tenant today.

## Product Purpose

Two linked surfaces built from one data pipeline:
1. **Daily Portfolio Brief** — a morning-brief control center: daily email + a published dashboard (site/) showing portfolio performance, macro regime, alerts, catalysts, and news. Read-only, generated once a day on a local schedule.
2. **Control Center** (server/ + site/control-center/, merged under the same site/URL as the dashboard above) — an editable workbench: edit holdings/transactions, run factor-driven portfolio construction with live constraint sliders, backtest strategies against a benchmark, and run a paper-trading execution blotter (approve/reject recommended trades, track simulated cash and a trade ledger).

Success means the owner can check real portfolio state from anywhere, and practice/test rebalancing decisions without risking real capital, without either surface ever showing or implying fabricated data.

## Positioning

Not a commercial product and not competing with Bloomberg/Composer/Portfolio Visualizer/etc. on breadth — it's a single-owner tool built around one real portfolio's actual holdings/transactions, factual monitoring over the look of sophistication, and interoperable with a daily automated local pipeline that nothing else needs to replicate.

## Operating Context

- Daily automation: a macOS `launchd` job (`overnight_runner.py`) generates the brief, deploys the dashboard, and sends the email every day without supervision; failures alert via a separate channel (Resend/local notification) so a broken step is never silent.
- The owner checks the Daily Brief dashboard passively (any device, no login friction beyond the existing Netlify account gate) and uses the Control Center actively (editing, running backtests, approving trades) in focused sessions.
- Real holdings/transactions/cash are shared state: edited from the web Control Center or the local machine, both must reflect the same numbers (Postgres-backed once configured; CSV fallback locally).
- Paper trading is a practice/analysis layer — "approve" never places a real order, only records a simulated one.

## Capabilities and Constraints

- Every number shown must trace to real data (live market data, the owner's actual transaction log, or computed metrics) — no placeholder, sample, or illustrative figures anywhere in either surface.
- "Factual monitoring only. No investment advice or recommendations." is an existing, load-bearing product principle (already in the email's own footer) — construction/backtesting output are mechanical calculations against the owner's stated constraints, never a recommendation framed as advice.
- The Control Center's execution ledger is explicitly simulated/paper; this must stay visually and textually unambiguous from anything that could be mistaken for live order execution.
- Backend (server/) recomputes live market/fundamental data per request — no stale cache presented as current.
- Frontend is currently plain HTML/CSS/vanilla JS (no framework) across both surfaces — a deliberate low-dependency choice for a personal tool, not an irreversible constraint if a framework rewrite is explicitly requested later.

## Brand Commitments

None — no existing name/logo/voice commitments beyond the working titles "Daily Portfolio Brief" and "Control Center." `DESIGN.md` (ClickHouse-anchored) is a deviate-from reference for the next visual pass, not a locked identity.

## Evidence on Hand

- Real portfolio holdings: `data/users/demo/portfolio.csv` (or Postgres once configured).
- Real transaction log: `data/transactions.csv` — drives actual time-weighted return calculations.
- No fabricated testimonials, benchmarks, or case studies exist or should be invented; this is operator-only software with no audience-facing marketing surface today.

## Product Principles

1. Never show a number that isn't real or a label that implies it's something it isn't (live vs. paper, fact vs. recommendation).
2. The daily pipeline's reliability is sacred — any Control Center or dashboard change must be verified not to break `overnight_runner.py`'s local run before shipping.
3. Solo-use today, but don't design in assumptions (hardcoded single-user state, no auth seams) that would make sharing this with someone else later a rewrite rather than an extension.
4. Prefer precision and restraint over decoration — this is an Operate-mode tool the owner trusts with real financial decisions, not a showcase.
