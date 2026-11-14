"""
Control Center API — FastAPI backend for the web rewrite of
newsletter_control_center.py. Deployed separately (Render) from the
newsletter send engine, same pattern as the_docket's web/app.py.

Local dev:
    cd /Users/aidangarver/Projects/newsletter_agent
    .venv/bin/uvicorn server.main:app --reload --port 8000

Every route that touches live market data recomputes it fresh on each
request (no caching, no background jobs) — these are personal-use,
low-traffic endpoints, and "stale until next poll" would be worse than a
slightly slower response. Only the execution ledger (server/db.py) and the
portfolio/transactions tables (portfolio_store.py) persist anything.
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.routers import (
    alerts,
    analytics,
    backtesting,
    construction,
    execution,
    factors,
    market,
    monitor,
    newsletter,
    portfolio,
)

app = FastAPI(title="Portfolio Control Center API")

# A shared-secret X-API-Key header was tried here as defense in depth against
# someone hitting the raw Render URL directly (CORS alone doesn't stop that).
# Dropped: baking that secret into the public webapp/ frontend (needed for it
# to actually send the header) is exactly the kind of "write a credential into
# a file that gets deployed publicly" action worth a human's eyes, not an
# agent's unilateral call — and the real access boundary was already Netlify's
# account-wide SSO gating who can load the frontend at all (see CLAUDE.md), so
# the extra layer wasn't worth that friction. CORS below is the only
# remaining restriction on which origins a browser can call this API from.

_allowed_origins = [
    o.strip() for o in os.environ.get(
        "ALLOWED_ORIGINS",
        # The webapp/ frontend now lives at /control-center/ under the same
        # Netlify site as the Daily Brief dashboard (merged 2026-11-14) —
        # CORS is origin-only (scheme+host+port), so the path doesn't matter.
        "https://portfolio-intelligence-brief.netlify.app",
    ).split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=r"http://localhost:\d+",  # any local dev port
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(monitor.router, prefix="/api/monitor", tags=["monitor"])
app.include_router(market.router, prefix="/api/market", tags=["market"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(factors.router, prefix="/api/factors", tags=["factors"])
app.include_router(construction.router, prefix="/api/construction", tags=["construction"])
app.include_router(execution.router, prefix="/api/execution", tags=["execution"])
app.include_router(backtesting.router, prefix="/api/backtesting", tags=["backtesting"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(newsletter.router, prefix="/api/newsletter", tags=["newsletter"])


@app.get("/api/health")
def health():
    db_configured = bool(os.environ.get("DATABASE_URL", "").strip())
    return {"status": "ok", "database_configured": db_configured}
