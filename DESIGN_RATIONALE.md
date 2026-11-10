# Dashboard redesign — design rationale

Why the "Daily Portfolio Brief" looks the way it does now, and what it borrows
from where. Written alongside the Nov 2026 overhaul that replaced the
email-only HTML newsletter with a Netlify-hosted dashboard + the same email.

## The problem with the old output

The previous `output/latest_newsletter.html` was built as nested HTML tables
(for Gmail-client compatibility) with nine near-identical white cards, a blue
gradient header, uppercase micro-labels on everything, and colored `<span>`
text doing all the signaling. It was data-rich — genuinely good underlying
pipeline (performance attribution, regime scoring, alerts, SEC filings,
analyst activity) — but visually it read as a wall of generated text with no
hierarchy: every number got the same 13px treatment whether it was the
headline P&L figure or a footnote. That's the "AI slop" feeling: correct
content, no editorial judgment about what matters more.

## What was borrowed, and why

- **Notion** — generous whitespace, 1px hairline borders instead of heavy
  drop shadows, content-first cards with minimal chrome. Applied directly:
  the dashboard's `.card` style (`site/styles.css`) is a flat surface with a
  faint border and a soft shadow, never a loud gradient. Section headers are
  small, muted, uppercase — present but quiet, so the data is the loudest
  thing on the page, not the label above it.
- **Copilot Money** (2024 Apple Design Award finalist for personal finance
  UI) — reviews consistently praise restrained, considered color and
  information density over Spendee-style loud charts. Applied: the palette
  uses exactly one accent hue (blue) plus a small fixed status set
  (good/warning/serious/critical), never a rainbow of category colors for
  gains/losses. Numbers get color; everything else stays in ink.
- **Bloomberg Terminal** — official Bloomberg UX writing emphasizes *uniform
  color coding* across the whole product and reviewing color pairs for CVD
  (color-vision deficiency) accessibility before shipping. Applied directly:
  gain/loss pills use `▲`/`▼` glyphs *and* color (never color alone, per the
  CVD accessibility pattern Bloomberg's own team has written about), and all
  tabular numeric columns use `tabular-nums` so figures align vertically —
  the one place monospace-style rigor earns its keep on an otherwise
  proportional-type page.
- **Morning Brew** — a fixed, predictable grid and one-topic-per-card
  layout, so a daily reader always knows where to look. Applied: section
  order is fixed day to day (hero → headline → executive summary → holdings
  → sector exposure → trend → movers → risk notes → news, with alerts /
  catalysts / regime / rates / analyst activity / filings in a persistent
  right rail) — nothing reshuffles based on what has data today.

Robinhood, Personal Capital/Empower, and Sharesight/Snowball Analytics were
considered as reference points for the holdings-table + sparkline pattern
but didn't contribute anything not already covered by the above; account
aggregation / multi-portfolio chrome in those products is out of scope for a
single-portfolio personal tool.

## Concrete decisions

- **Color system** uses the validated default palette from Claude's `dataviz`
  skill (`references/palette.md`) rather than invented hex values: one
  accent hue (`#2a78d6` light / `#3987e5` dark) and a fixed, CVD-checked
  status set (`good` / `warning` / `serious` / `critical`) that's never
  reused for anything else. Light and dark mode are both first-class
  (`prefers-color-scheme` + a manual toggle persisted to `localStorage`),
  not an afterthought — this was a real gap in the old newsletter, which had
  dark-mode CSS but no way to force it outside an email client's own setting.
- **Sparklines** are a new capability the old newsletter never had. Each
  holding gets a 30-day price trend built from a small rolling history file
  (`site/data/history.json`) that the pipeline appends to once per day —
  there was no existing historical price store wired into the live pipeline
  (`data/history.db`'s `runs` table exists but hasn't been written to since
  May 2026 — see `app/data/history_db.py`, which is called from nowhere in
  the live path), so rather than resurrect unused, stale machinery this adds
  a minimal, purpose-built one.
- **The portfolio-value trend chart** is the one hero line chart on the page
  (hover tooltip, single series, sequential blue) — it's the "control
  center" element the old format had no equivalent for at all: every number
  in the old newsletter was a snapshot, nothing showed *shape* over time.
- **Numbers that are tables stay tables.** SEC filings, dividend calendar,
  analyst ratings, news — these are lists/tables in both the old and new
  format. The redesign didn't try to chart everything; per the dataviz
  skill's first rule, a lot of this data's "job" is lookup/reference, not
  magnitude comparison, so a chart would be decoration, not clarity.

## Architecture

```
overnight_runner.py (launchd, 16:30 daily)
  └─ main.py → generate_hybrid_newsletter.py
        ├─ writes output/latest_newsletter.html/.txt   (unchanged — email body)
        └─ writes site/data/latest.json + appends site/data/history.json
  └─ netlify deploy --prod --dir=site   (new — non-blocking; failure alerts
     the same way a generation/send failure does, but never stops the email)
  └─ send_newsletter.py                 (unchanged — Gmail SMTP)
```

`site/` is a plain static site: `index.html` + `styles.css` + `app.js`
(vanilla JS, no framework, no build step — it fetches the two JSON files at
page load and renders everything client-side). This was chosen over a
Netlify-Git-triggered build or Netlify Functions because the data already
exists as files on the local machine the moment `generate_hybrid_newsletter.py`
runs — the simplest correct architecture is "upload those files," not
"commit them somewhere and have a second system rebuild from them." There is
no server, no database, no API route; `netlify deploy --prod` from the CLI
(already authenticated on this machine) is the entire deploy mechanism.

`site/data/*.json` are gitignored (same pattern as `output/*.json`) — they're
build output, regenerated fresh every day, not source.

**Access:** the Netlify **Personal** account this site lives under has
account-wide visitor-access (SSO) enforcement on, so the live URL
(`https://portfolio-intelligence-brief.netlify.app`) requires a Netlify login
to view. Given this dashboard shows real holdings, cost basis, and P&L, this
was kept on deliberately (your call, asked and confirmed during the build)
rather than disabled — this is closer to "private page only you can open"
than "public dashboard," which fits actual portfolio data better than a
fully public page would.

## What's unchanged

- `send_newsletter.py` / Gmail delivery — untouched, still the same SMTP path.
- The underlying data pipeline (`app/data/*`, `portfolio_manager.py`,
  `generate_hybrid_newsletter.py`'s fetch logic) — untouched; the dashboard
  reads the *same* already-computed values the email does, via one new
  export function (`_write_dashboard_data`), not a second fetch pass.
- `healthcheck.py` and the Resend failure-alert path — untouched.

## Known follow-ups (not done in this pass)

- `data/history.db`'s `runs` table is stale (last write 2026-05-19) and the
  `app/data/history_db.py` module that would populate it isn't called from
  anywhere live — flagged in `CLAUDE.md` already as a future cleanup
  candidate; this pass intentionally didn't touch it.
- The old newsletter's yield-curve tile is labeled "3M Treasury" but reads
  `yield_curve["2y"]` (`generate_hybrid_newsletter.py`'s `_render_yield_vix`)
  — the dashboard sidesteps this by only surfacing the (correctly labeled)
  10-year yield and the spread, not the ambiguous short-end number. Worth a
  closer look at `app/data/market_workbench.py`'s yield-curve fetch in a
  future pass to confirm which tenor is actually being returned.
- No automated test suite covers `site/app.js` or `_write_dashboard_data`;
  verification so far is a manual run of `overnight_runner.py` plus visual
  review in the browser pane (desktop + mobile width, light + dark mode).
