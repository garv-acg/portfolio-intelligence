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

import hmac
import os

from fastapi import Depends, FastAPI, HTTPException, Request
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

API_KEY = os.environ.get("API_KEY", "").strip()


async def require_api_key(request: Request) -> None:
    """The real access boundary is Netlify's account-wide SSO gating who can
    even load the frontend page at all (see CLAUDE.md) — this shared-secret
    header is defense in depth against someone hitting the raw Render URL
    directly, which bypasses CORS entirely (CORS only restricts browser
    fetches, not curl/Postman/another script). If API_KEY isn't set, this is
    a no-op — makes local dev work without any setup."""
    if not API_KEY:
        return
    provided = request.headers.get("x-api-key", "")
    if not hmac.compare_digest(provided, API_KEY):
        raise HTTPException(401, "Missing or invalid API key")

_allowed_origins = [
    o.strip() for o in os.environ.get(
        "ALLOWED_ORIGINS",
        "https://portfolio-control-center.netlify.app",
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

_auth = [Depends(require_api_key)]
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"], dependencies=_auth)
app.include_router(monitor.router, prefix="/api/monitor", tags=["monitor"], dependencies=_auth)
app.include_router(market.router, prefix="/api/market", tags=["market"], dependencies=_auth)
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"], dependencies=_auth)
app.include_router(factors.router, prefix="/api/factors", tags=["factors"], dependencies=_auth)
app.include_router(construction.router, prefix="/api/construction", tags=["construction"], dependencies=_auth)
app.include_router(execution.router, prefix="/api/execution", tags=["execution"], dependencies=_auth)
app.include_router(backtesting.router, prefix="/api/backtesting", tags=["backtesting"], dependencies=_auth)
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"], dependencies=_auth)
app.include_router(newsletter.router, prefix="/api/newsletter", tags=["newsletter"], dependencies=_auth)


@app.get("/api/health")
def health():
    db_configured = bool(os.environ.get("DATABASE_URL", "").strip())
    return {"status": "ok", "database_configured": db_configured}
