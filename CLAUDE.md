# newsletter_agent

Personal automation tool, **separate from FieldSync**. Generates and emails a
daily "Daily Portfolio Brief" via a macOS `launchd` job. Do not work on this
from inside a FieldSync Claude Code session — this is its own environment.

## Live entry points (the only ones that matter)

```
overnight_runner.py → main.py → generate_hybrid_newsletter.py → send_newsletter.py
                     → netlify deploy --prod --dir=site   (dashboard)
```

- `overnight_runner.py` — orchestrator. Waits for network, runs generation,
  deploys the dashboard to Netlify, then sends the email, logs every step to
  `logs/overnight_runs.log`, writes one `logs/send_status.jsonl` line per
  run, and alerts on failure via Resend (falling back to a local macOS
  notification) — **not** Gmail, since Gmail being broken is the most likely
  failure mode. `--skip-deploy` skips the Netlify step; `--skip-email` skips
  the send. A dashboard deploy failure is logged/alerted but never blocks
  the email, and vice versa — they're independent.
- `main.py` — thin wrapper calling `generate_hybrid_newsletter.build_and_save_newsletter()`.
- `generate_hybrid_newsletter.py` — the actual pipeline. Pulls market/news/
  portfolio data (via `app/data/*` and `app/config/settings.py` — see below),
  writes `output/latest_newsletter.html` / `.txt` (the email body), **and**
  writes `site/data/latest.json` + appends `site/data/history.json` (the
  dashboard's data — see "Dashboard (Netlify)" below) via
  `_write_dashboard_data()`, called at the end of `build_hybrid_newsletter()`.
  Both reuse the same already-fetched data — there is no second fetch pass.
- `send_newsletter.py` — reads `.env` directly (manual parse, not
  `python-dotenv`, specifically to avoid `app/email/` shadowing stdlib
  `email` when run from inside `app/` — always run this from the project
  root), sends via Gmail SMTP (`smtp.gmail.com:465`, app password auth).
- `healthcheck.py` — independent watchdog (see below). Also flags (but does
  not treat as a hard failure) a day where the email sent fine but the
  Netlify deploy failed.

## Dashboard (Netlify)

Added Nov 2026 — see `DESIGN_RATIONALE.md` for the full design writeup
(what was borrowed from which competitor products and why) and architecture
notes. Short version:

- `site/` is a plain static site (`index.html` / `styles.css` / `app.js`,
  vanilla JS, no build step, no framework) that fetches
  `site/data/latest.json` + `site/data/history.json` client-side and renders
  the whole dashboard. Those two JSON files are gitignored — they're
  regenerated fresh by every run, not source.
- Deployed via `netlify deploy --prod --dir=site` (already linked/authed on
  this machine via `.netlify/state.json`, also gitignored) — **not** a
  Netlify-Git-triggered build. There is no server, database, or API route.
- Live at **https://portfolio-intelligence-brief.netlify.app** (Netlify
  project `portfolio-intelligence-brief`, under the **Personal** Netlify
  account/team, project id `1b6a2736-6d0a-4ce2-8603-543eb63d0073`).
- That Personal Netlify account has **account-wide SSO/visitor-access
  enforcement on** (`account_sso_login_context: all`), so the live URL
  requires a Netlify login to view — kept intentionally (real portfolio/P&L
  data, your own call) rather than made public. If you ever want it public,
  that's a Netlify dashboard change (Site configuration → Visitor access),
  not something in this repo.
- `history.json` is this project's own rolling 90-day snapshot store
  (portfolio value, daily %, regime, VIX, per-ticker price — enough for the
  dashboard's sparklines and trend chart). It is **not** the same thing as
  `data/history.db`'s `runs` table, which is unrelated and currently stale
  (see "Not yet investigated" below) — don't confuse the two.

Portfolio holdings for the live pipeline come from
`data/users/demo/portfolio.csv` (read by `portfolio_manager.py`) **unless**
`DATABASE_URL` is set, in which case Postgres is the source of truth — see
"Control Center" below. Either way, never the root `portfolio.yml`.

## Control Center (Render + Netlify)

Added Nov 2026 — a full rewrite of `newsletter_control_center.py` (the
Streamlit app) into a FastAPI backend + a second Netlify site. See
`CONTROL_CENTER.md` for the full design writeup, architecture, and the
remaining setup steps only you can do (Neon account, Render service). Short
version:

- `server/` — FastAPI backend. Deployed separately (Render) from the
  newsletter send engine, same pattern as `the_docket`'s `web/app.py`.
  Every "live data" route recomputes fresh from Yahoo/FRED/SEC on each
  request using the same `app/data/*` engines the email pipeline uses — no
  caching, no persistence for those. Only the execution ledger (paper
  trades, cash, approve/reject) and shared portfolio/transactions state
  live in Postgres (Neon, free tier) via `server/db.py`.
- `webapp/` — plain HTML/CSS/vanilla JS frontend (same design tokens as
  `site/styles.css`), 11 pages, published to Netlify separately from the
  Daily Brief dashboard: **https://portfolio-control-center.netlify.app**
  (project `portfolio-control-center`, same Personal Netlify account — same
  account-wide SSO gating applies).
- `portfolio_store.py` (repo root) — the shared read/write layer for
  holdings + transactions. With `DATABASE_URL` unset, byte-for-byte the old
  CSV-only behavior (verified via a full local `overnight_runner.py` run).
  With it set, Postgres is canonical, CSV becomes a fallback cache.
  `generate_hybrid_newsletter.py`'s `load_portfolio()` and
  `app/data/portfolio_returns.py`'s `load_transactions()` both go through
  this, so editing holdings from the web Control Center affects the real
  daily email too.
- `render.yaml` — Render Blueprint for the backend service
  (`portfolio-control-center-api`). Not yet deployed — needs you to connect
  the GitHub repo in Render's dashboard and set `DATABASE_URL`/`API_KEY`.
- API auth: a shared-secret `X-API-Key` header (`server/main.py`'s
  `require_api_key`), no-op if `API_KEY` env var isn't set. Defense in
  depth against the raw Render URL being hit directly (CORS alone doesn't
  stop that) — the real access boundary is Netlify's account-wide SSO.

## launchd jobs

Two jobs, both in `~/Library/LaunchAgents/` (the only place that matters —
anything outside it is not live):

- **`com.aidan.newsletteragent`** — runs `overnight_runner.py` daily at
  16:30 local (chosen so market data is fresh after the 4pm close).
- **`com.aidan.newsletteragent.healthcheck`** — runs `healthcheck.py` daily
  at 18:00 local (1.5h buffer). Checks whether `logs/send_status.jsonl`'s
  last entry is from today and `send_ok: true`. If the main job never ran at
  all (machine asleep, launchd misconfigured, process killed before it could
  alert), this is the only thing that will notice and alert — the main
  job's own alert can't cover its own non-execution.

Check both are loaded: `launchctl list | grep newsletter`.

## Tracking / logs

- `logs/overnight_runs.log` — full step-by-step log of every run (human-readable).
- `logs/send_status.jsonl` — one JSON line per day: `{date, timestamp, generate_ok, send_ok, alert_ok, error}`. Append-only; `tail -1` for today's state.
- `logs/healthcheck.log` — healthcheck's own OK/FAIL log.
- `logs/launchd_stdout.log` / `logs/launchd_stderr.log` — raw launchd output for the main job.
- `logs/healthcheck_stdout.log` / `logs/healthcheck_stderr.log` — same for the healthcheck job.

## Alerting path

Both `overnight_runner.py`'s failure alert and `healthcheck.py`'s alert use
**Resend** (`app/email/send_email.py:send_with_resend`), not Gmail — if
Gmail is the thing that's broken, the alert can't also depend on it. Falls
back to a local macOS notification (`osascript`) if Resend itself fails, so
there's no single point of failure.

Resend is in **sandbox mode** on the current account — it can only send to
the email the Resend account itself is registered under. `EMAIL_TO` in
`.env` is set accordingly; if alerts stop arriving, check that account's
mode at resend.com/domains before assuming something else broke.

## .env keys in use

- `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `NEWSLETTER_TO` — the actual newsletter send (Gmail SMTP).
- `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_TO` — failure/healthcheck alerts only (Resend).
- `ALPHAVANTAGE_API_KEY`, `FRED_API_KEY`, `FMP_API_KEY` — market/macro data sources.
- `OPENAI_API_KEY` (currently unset) — pipeline has a deterministic fallback when absent.
- `NEWSAPI_KEY` (currently unset) — optional news source.
- `NEWSLETTER_MAX_ARTICLES_PER_TICKER`, `NEWSLETTER_LOOKBACK_HOURS` — generation tuning.
- `DATABASE_URL` (currently unset locally) — once set, the local pipeline
  reads/writes portfolio holdings + transactions through Postgres instead
  of CSV (see "Control Center"); also used by `server/` on Render.
- `API_KEY` (currently unset) — only read by `server/`, not the local pipeline.

If a Gmail App Password stops working, generate a new one at
https://myaccount.google.com/apppasswords — 2FA re-enrollment, a password
reset, or signing in from a new device can all invalidate old app passwords.

## How to hand-test

```bash
cd /Users/aidangarver/Projects/newsletter_agent
.venv/bin/python overnight_runner.py --dry-run                     # print steps, do nothing
.venv/bin/python overnight_runner.py --skip-email --skip-deploy    # generate only
.venv/bin/python overnight_runner.py --skip-email                  # generate + deploy dashboard, no email
.venv/bin/python overnight_runner.py                                 # full run: generate + deploy + send + alert-on-fail
.venv/bin/python send_newsletter.py                                  # send only, from the last generated output
netlify deploy --prod --dir=site                                     # deploy the dashboard only
.venv/bin/python healthcheck.py                                      # check today's status, alert if unhealthy
```

`--skip-email` leaves `send_ok: null` in `send_status.jsonl` for that run —
expected for a manual generate-only test, but don't leave the daily launchd
job running with this flag or healthcheck will flag it as a failure.

## Retired / not live — don't resurrect without checking first

- `~/.Trash/newsletter_agent` — a stale duplicate repo that used to live at
  `~/Downloads/newsletter_agent`. Not loaded by any launchd job, nothing
  unique confirmed inside it. Moved to Trash 2026-11-10, not hard-deleted.
- `~/.Trash/com.newsletteragent.daily.plist` — a stray plist that used to
  sit in `~/Downloads/`, pointing at a path that doesn't exist. Never
  loaded. Moved to Trash 2026-11-10.
- `app/dashboard/streamlit_app.py` and the rest of `app/ai/`, `app/filtering/`,
  plus `app/overnight_runner.py`, `app/main.py`, `app/send_newsletter.py`,
  `app/newsletter_control_center.py`, `app/run_newsletter.py`,
  `app/patch_fomc_auto.py`, `app/macro_display.py`, `app/install_*.py`,
  `app/config/portfolio.py`, `app/config/user_profiles.py`,
  `app/com.aidan.newsletteragent.overnight.plist`, and a duplicate nested
  `app/.venv/` — all deleted 2026-11-10. These were a second, parallel
  implementation (including a Streamlit control center) that read portfolio
  holdings from the disconnected root `portfolio.yml`, not the live
  `data/users/demo/portfolio.csv`, and weren't referenced by anything in
  the live pipeline. Recoverable via git history if ever needed.
- Root-level `.bak_*` / `*_WORKING_BEFORE_*` files — deleted 2026-11-10
  (git has the history; these were just dead weight in the working tree).

**Still live, kept intentionally:** `app/email/` (used by
`overnight_runner.py` and `healthcheck.py` for the Resend alert path),
`app/data/*` and `app/config/settings.py` (imported directly by
`generate_hybrid_newsletter.py`).

**Not yet investigated — flagged for a future pass, not acted on:**
- `app/data/history.py` and `app/data/market_regime.py` look unreferenced
  by anything in the live pipeline, but this wasn't fully traced given how
  large `generate_hybrid_newsletter.py`'s import graph is — don't delete
  without re-checking.
- A number of root-level scripts (`install_*.py`, `patch_*.py`,
  `run_newsletter.py`, `test_newsletter_preferences.py`) look like
  one-off/legacy tooling not called by the live path, mirroring what was
  just removed from `app/`, but cleaning these up wasn't part of this pass —
  ask before touching them.
- `newsletter_control_center.py` and `portfolio_manager.py` (both root,
  Streamlit) are now **superseded** by `server/` + `webapp/` (see "Control
  Center" above) — every page/feature either got fixed-and-ported there or
  deliberately cut (see `CONTROL_CENTER.md`'s "Known gaps"). Left in place
  rather than deleted, since they still work standalone if you ever want a
  local-only fallback, but don't add new features to them — the web version
  is where ongoing work should go.
