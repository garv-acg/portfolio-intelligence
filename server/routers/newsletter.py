from __future__ import annotations

from fastapi import APIRouter

from server.db import DatabaseUnavailable

router = APIRouter()

DASHBOARD_URL = "https://portfolio-intelligence-brief.netlify.app"


@router.get("/status")
def status():
    """Last known run status, mirrored from the local overnight_runner.py.
    Generation/sending itself only happens on the local machine's launchd
    schedule — there's no "generate now" button here, since triggering the
    real pipeline (and a real Gmail send) from a public web app risks
    duplicate sends and needs every local secret duplicated on Render."""
    from server.db import latest_pipeline_status

    try:
        last = latest_pipeline_status()
    except DatabaseUnavailable:
        last = None
    return {
        "last_run": last,
        "dashboard_url": DASHBOARD_URL,
    }
