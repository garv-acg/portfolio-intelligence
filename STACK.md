# Design Stack — newsletter_agent

Installed and smoke-tested per the "Design Stack Installer" prompt. Scope:
Tier 1 (installed without asking) + Tier 2 (batched question, user chose all
three extra skills + ClickHouse as the brand anchor). Tier 3 skipped
entirely — not requested.

## Installed — Tier 1

### 1. `frontend-design` plugin (Anthropic, `claude-plugins-official`)
- **Command used** (confirmed against the marketplace's current README before
  running — matched the prompt's hint exactly): `claude plugin install
  frontend-design@claude-plugins-official`
- **Proof**: `claude plugin list` shows it `✔ enabled` at `Version: 1.1.1`,
  user scope.
- **Caveat**: user-scope plugins need a session restart before their bundled
  skill actually triggers — confirmed not yet present in this session's
  skill list (unlike the Tier 2 skills below, which *are* live — see why
  under "Anything unverifiable").

### 2. Impeccable (`pbakaus/impeccable`)
- **Command used**: `npx impeccable install --providers=claude
  --scope=project` (README-confirmed; ran non-interactively since the
  install prompts for scope otherwise). Installed: project skill at
  `.claude/skills/impeccable/`, the detector engine binary (darwin-arm64,
  v0.1.21), Claude Code agents, and a design hook in
  `.claude/settings.local.json`.
- **Proof (smoke test)**: created a deliberately bad fixture page (purple
  gradient hero, Inter, three identical icon-tile cards, low-contrast text,
  a skipped heading level, "Supercharge" buzzword copy) and ran the
  detector:
  ```
  npx impeccable detect <fixture>.html
  ```
  **9 anti-patterns found**: `low-contrast` (×2), `icon-tile-stack` (×3),
  `overused-font`, `skipped-heading`, `ai-color-palette`,
  `marketing-buzzword`.
- **Also proven live**: ran `/impeccable init` in this same session (the
  project-scope skill loaded without a restart) — it interviewed for
  product truth and wrote `PRODUCT.md` at the repo root.

### 3. Playwright MCP (`microsoft/playwright-mcp`)
- **Command used** (README-confirmed, matches the hint): `claude mcp add
  playwright -s user -- npx @playwright/mcp@latest`
- **Proof**: `claude mcp list` shows `playwright: npx @playwright/mcp@latest
  - ✔ Connected`.
- **Not verified this session**: newly added MCP servers aren't exposed as
  callable tools until the harness restarts, so I could not run the
  prompt's literal smoke test (navigate + screenshot + report the file
  path) through *this* server. I did the equivalent screenshot/navigate via
  the **built-in browser pane** (already available, Playwright-based under
  the hood) while researching this very stack — see the overlap note below.

### 4. Context7 MCP (`upstash/context7`)
- **Command used**: the hint's `claude mcp add` pattern no longer matches
  the project's current README — Context7 now recommends `npx ctx7 setup`,
  which does an **OAuth flow** to generate an API key. I didn't run that
  (account-linking isn't something I do on your behalf). Instead I used
  the documented manual-install path with no key: `claude mcp add
  --transport http context7 https://mcp.context7.com/mcp -s user`.
- **Proof**: `claude mcp list` shows `context7: https://mcp.context7.com/mcp
  (HTTP) - ✔ Connected` — working, unauthenticated (rate-limited) tier.
- **Not verified this session**: same restart caveat as Playwright — I
  couldn't call `resolve-library-id`/`query-docs` yet.
- **Optional upgrade you'd need to do**: get a free API key at
  context7.com/dashboard for higher rate limits, then add it with `claude
  mcp add context7 ... -H "Authorization: Bearer YOUR_KEY"` (I won't handle
  the key myself — see BROKEN/skipped below, it's the one secret-gated
  step in this whole install).

## Installed — Tier 2 (your choices)

### ClickHouse `DESIGN.md` (brand anchor)
- **Command used**: `npx getdesign@latest add clickhouse`
- **Proof**: `DESIGN.md` created at repo root (544 lines, ~26KB) — near-black
  canvas, electric-yellow (`#faff69`) as the sole accent voltage, white/gray
  typography. Chosen specifically *because* it's the one non-purple/violet
  option — Impeccable's own detector flagged purple/violet gradients
  (`ai-color-palette`) as a slop tell on the test fixture, so this gives a
  genuinely different anchor instead of a second cool-toned minimalist one.
  **Anchor, not a copy target** — nothing in this repo's actual UI (Notion
  + Bloomberg + Morning-Brew inspired, see `DESIGN_RATIONALE.md`) has been
  changed to match it; it's there for the next design pass to deviate from.

### vercel-labs/agent-skills (incl. `web-design-guidelines`)
- **Command used**: `npx skills@latest add vercel-labs/agent-skills`
- **Proof**: installed 9 skills, all confirmed live in this session's skill
  list (`web-design-guidelines`, `vercel-optimize`, `deploy-to-vercel`,
  `vercel-react-best-practices`, `vercel-react-native-skills`,
  `vercel-react-view-transitions`, `vercel-composition-patterns`,
  `vercel-cli-with-tokens`, `writing-guidelines`).
- 7 of the 9 (everything but `web-design-guidelines` and
  `writing-guidelines`) are Next.js/Vercel-deploy specific and won't
  trigger on this Python/vanilla-JS project — harmless, just unused here.

### Emil Kowalski skills (`emilkowalski/skills`)
- **Command used**: `npx skills@latest add emilkowalski/skills`
- **Proof**: installed 13 skills, confirmed live (`emil-design-eng`,
  `animate`, `choreograph`, `gestures`, `review-animations`,
  `improve-animations`, `find-animation-opportunities`,
  `remove-animations`, `animation-performance`, `animation-vocabulary`,
  `apple-design`, `ask-sonner`, `break-ui`, `mobile-native`,
  `pick-ui-library`, `prototype`, `write-swift`). Fully applicable — this
  project's pages are plain HTML/CSS/JS, which these skills support
  directly (no framework requirement).

### shadcn/ui official skill
- **Command used**: `npx skills@latest add shadcn/ui` (confirmed against
  `ui.shadcn.com/docs/skills`, which only lists the `pnpm dlx` form — the
  `npx` equivalent is the same underlying `skills` CLI already used above).
- **Proof**: installed `shadcn` + `migrate-radix-to-base`, confirmed live.
- **Dormant on this repo**: per shadcn's own docs, "the skill activates
  when it finds a `components.json` file" — this project has no React/
  shadcn setup at all, so it's installed but inert today. Keep it for any
  future React work; it does nothing here right now.

## BROKEN / skipped

- **Context7 API key** — needs your own OAuth login at context7.com (or
  `npx ctx7 setup`, which does the same OAuth flow) to get higher rate
  limits. Skipped per the rule against improvising secrets I haven't been
  given. Context7 works right now without it, just rate-limited.
- Nothing else failed. Everything in Tier 1 and Tier 2 installed cleanly.

## Overlap map

| Tool | Job | Notes |
|---|---|---|
| **Impeccable** | GENERATE + CRITIQUE + POLISH | The broadest tool installed — `new-work`/`shape` (generate), `critique`/`audit` (critique), `polish`/`bolder`/`quieter`/`distill`/`harden` (polish). Proven working this session (detector + `/impeccable init`). **Overlap winner** over `frontend-design` and `web-design-guidelines` below. |
| **frontend-design** (Anthropic) | GENERATE | Impeccable's own README says it "started from Anthropic's frontend-design skill" — direct lineage, direct overlap. **Disable in practice**: once a restart makes it active, if it and Impeccable ever give conflicting generation guidance on the same task, defer to Impeccable — it's project-aware (reads this repo's `PRODUCT.md`/`DESIGN.md`), frontend-design is generic. Not worth literally uninstalling (it's free, lightweight, and is Anthropic's own baseline if Impeccable's hook is ever disabled), just don't treat it as the primary voice. |
| **web-design-guidelines** (Vercel) | CRITIQUE (technical/accessibility) | Direct overlap with Impeccable's own `/impeccable audit` command, which the Impeccable README explicitly describes as covering "accessibility, performance, theming, and responsive behavior" — the same ground. **Overlap winner: `/impeccable audit`** — it's context-aware (reads `PRODUCT.md`/`DESIGN.md`) and produces ranked P0–P3 findings in the same system as everything else here. Treat `web-design-guidelines` as a redundant secondary cross-check, not a routine first stop. |
| **Emil Kowalski skills** | MOTION (+ POLISH for `emil-design-eng` specifically) | No real overlap — nothing else installed does motion/animation critique or implementation. `emil-design-eng` itself is broader UI-polish philosophy and does overlap conceptually with Impeccable's `polish`, but they're complementary angles (component/interaction feel vs. slop-pattern detection), not redundant — keep both. |
| **Playwright MCP** | INSPECT | **Directly redundant with the built-in browser pane** (`mcp__Claude_Browser__*`) already available in this Claude Code desktop session — same underlying engine, zero extra setup, and what I've been using all session. **Overlap winner: the built-in browser pane**, inside this app. Keep the standalone Playwright MCP registered anyway — it's the right tool for a plain `claude` terminal session (no desktop app, no browser pane) or for Impeccable's own `/impeccable live` mode, which expects a Playwright-attached dev server. |
| **Context7 MCP** | INSPECT (docs/reference, not UI) | No overlap with anything else here — nothing else fetches live library documentation. |
| **shadcn skill** | GENERATE (React-specific) | No overlap in practice — inert on this repo (no `components.json`), would only matter if a future React surface gets added here. |

## When-to-use-what cheat sheet

Day-to-day commands, once a session restart has made `frontend-design` and
the MCP servers fully live (the project-scope skills — Impeccable, Emil
Kowalski's, Vercel's — already work right now, no restart needed):

| You want to... | Run |
|---|---|
| Start a brand-new page/surface | `/impeccable shape <surface>` (plans first) or just describe it — `new-work` kicks in |
| Get a scored UX review of something that exists | `/impeccable critique <target>` |
| Check accessibility/perf/responsive/theming | `/impeccable audit <target>` |
| Final pass before shipping | `/impeccable polish <target>` |
| It's too safe/bland | `/impeccable bolder <target>` |
| It's too loud/busy | `/impeccable quieter <target>` |
| Add real animation | invoke the `animate` skill, or `/impeccable animate <target>` for a lighter touch |
| Audit *all* the motion in the app | invoke `improve-animations` (read-only, produces a prioritized plan) |
| Review one animation someone wrote | invoke `review-animations` |
| Pick a UI library for something new | invoke `pick-ui-library` |
| Look up current docs for a library | ask naturally with "use context7" in the prompt, once Context7 is live this session |
| Take a screenshot / drive a browser | use the **built-in browser pane** tools (`mcp__Claude_Browser__*`) — not the new Playwright MCP, inside this app |
| Iterate visually against a running dev server | `/impeccable live` (needs a runnable project — this one qualifies, it's plain HTML served locally) |

## Anything I couldn't verify

- `frontend-design` plugin's bundled skill triggering — needs a session
  restart (user-scope plugins don't hot-load the way project-scope skills
  did today).
- Playwright MCP's and Context7 MCP's own tool calls (screenshot, docs
  resolution) — same restart caveat; connectivity itself is proven
  (`claude mcp list` shows both `✔ Connected`), the actual tool invocation
  isn't, yet.
- Context7's authenticated (higher-rate-limit) tier — needs you to run
  `npx ctx7 setup` or get a key from context7.com/dashboard yourself.

## Files this created or touched

- `DESIGN.md`, `PRODUCT.md`, `STACK.md` (new, repo root)
- `.claude/skills/impeccable/` (Impeccable's engine + skill)
- `.claude/agents/` (Impeccable's bundled agents)
- `.claude/settings.local.json` (Impeccable's design hook — review before
  unattended runs; `/impeccable hooks status` shows what it does)
- `.agents/skills/` (all Tier 2 skills — Vercel's, Emil Kowalski's,
  shadcn's)
- `~/.claude.json` (user-scope: `frontend-design` plugin, `playwright` and
  `context7` MCP servers — not project-local, affects every project)
