# newsletter_agent

Personal automation tool, **separate from FieldSync**. Generates and emails a
daily "Daily Portfolio Brief" via a macOS `launchd` job. Do not work on this
from inside a FieldSync Claude Code session — this is its own environment.

## Live entry points (the only ones that matter)

```
overnight_runner.py → main.py → generate_hybrid_newsletter.py → send_newsletter.py
```

- `overnight_runner.py` — orchestrator. Waits for network, runs generation,
  then sends, logs every step to `logs/overnight_runs.log`, writes one
  `logs/send_status.jsonl` line per run, and alerts on failure via Resend
  (falling back to a local macOS notification) — **not** Gmail, since Gmail
  being broken is the most likely failure mode.
- `main.py` — thin wrapper calling `generate_hybrid_newsletter.build_and_save_newsletter()`.
- `generate_hybrid_newsletter.py` — the actual pipeline. Pulls market/news/
  portfolio data (via `app/data/*` and `app/config/settings.py` — see below)
  and writes `output/latest_newsletter.html` / `.txt`.
- `send_newsletter.py` — reads `.env` directly (manual parse, not
  `python-dotenv`, specifically to avoid `app/email/` shadowing stdlib
  `email` when run from inside `app/` — always run this from the project
  root), sends via Gmail SMTP (`smtp.gmail.com:465`, app password auth).
- `healthcheck.py` — independent watchdog (see below).

Portfolio holdings for the live pipeline come from
`data/users/demo/portfolio.csv` (read by `portfolio_manager.py`), **not**
the root `portfolio.yml`.

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

If a Gmail App Password stops working, generate a new one at
https://myaccount.google.com/apppasswords — 2FA re-enrollment, a password
reset, or signing in from a new device can all invalidate old app passwords.

## How to hand-test

```bash
cd /Users/aidangarver/Projects/newsletter_agent
.venv/bin/python overnight_runner.py --dry-run     # print steps, do nothing
.venv/bin/python overnight_runner.py --skip-email   # generate only
.venv/bin/python overnight_runner.py                 # full run: generate + send + alert-on-fail
.venv/bin/python send_newsletter.py                  # send only, from the last generated output
.venv/bin/python healthcheck.py                      # check today's status, alert if unhealthy
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
  `newsletter_control_center.py`, `run_newsletter.py`,
  `test_newsletter_preferences.py`) look like one-off/legacy tooling not
  called by the live path, mirroring what was just removed from `app/`, but
  cleaning these up wasn't part of this pass — ask before touching them.
