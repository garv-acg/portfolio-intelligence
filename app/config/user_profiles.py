
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


USERS_ROOT = Path("data/users")
DEFAULT_USER_ID = "demo"


@dataclass(frozen=True)
class UserProfile:
    user_id: str
    display_name: str
    email: str | None
    user_dir: Path
    portfolio_file: Path
    settings_file: Path
    history_db: Path


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or DEFAULT_USER_ID


def ensure_users_root() -> None:
    USERS_ROOT.mkdir(parents=True, exist_ok=True)


def create_user_profile(display_name: str, email: str | None = None, user_id: str | None = None, copy_from_portfolio: Path | None = None) -> UserProfile:
    ensure_users_root()
    resolved_user_id = _slugify(user_id or display_name)
    user_dir = USERS_ROOT / resolved_user_id
    user_dir.mkdir(parents=True, exist_ok=True)

    portfolio_file = user_dir / "portfolio.csv"
    settings_file = user_dir / "settings.json"
    history_db = user_dir / "history.db"

    if copy_from_portfolio and copy_from_portfolio.exists() and not portfolio_file.exists():
        shutil.copy(copy_from_portfolio, portfolio_file)

    if not portfolio_file.exists():
        portfolio_file.write_text("ticker,shares,cost_basis\\nAAPL,1,0\\n", encoding="utf-8")

    settings = {
        "user_id": resolved_user_id,
        "display_name": display_name,
        "email": email,
        "portfolio_file": str(portfolio_file),
        "history_db": str(history_db),
        "morning_brief_enabled": True,
        "facts_only_mode": True,
    }

    if settings_file.exists():
        try:
            existing = json.loads(settings_file.read_text(encoding="utf-8"))
            settings.update(existing)
            settings["user_id"] = resolved_user_id
            settings["portfolio_file"] = str(portfolio_file)
            settings["history_db"] = str(history_db)
        except Exception:
            pass

    settings_file.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    return UserProfile(
        user_id=resolved_user_id,
        display_name=settings.get("display_name", display_name),
        email=settings.get("email"),
        user_dir=user_dir,
        portfolio_file=portfolio_file,
        settings_file=settings_file,
        history_db=history_db,
    )


def list_user_profiles() -> list[UserProfile]:
    ensure_users_root()
    profiles: list[UserProfile] = []

    for user_dir in sorted([p for p in USERS_ROOT.iterdir() if p.is_dir()]):
        settings_file = user_dir / "settings.json"
        settings: dict[str, Any] = {}

        if settings_file.exists():
            try:
                settings = json.loads(settings_file.read_text(encoding="utf-8"))
            except Exception:
                settings = {}

        user_id = settings.get("user_id", user_dir.name)
        display_name = settings.get("display_name", user_id.replace("_", " ").title())
        email = settings.get("email")

        profiles.append(
            UserProfile(
                user_id=user_id,
                display_name=display_name,
                email=email,
                user_dir=user_dir,
                portfolio_file=user_dir / "portfolio.csv",
                settings_file=settings_file,
                history_db=user_dir / "history.db",
            )
        )

    return profiles


def get_user_profile(user_id: str | None = None) -> UserProfile:
    ensure_users_root()
    profiles = list_user_profiles()

    if not profiles:
        return create_user_profile(
            display_name="Demo User",
            user_id=DEFAULT_USER_ID,
            copy_from_portfolio=_find_existing_portfolio(),
        )

    if user_id:
        for profile in profiles:
            if profile.user_id == user_id:
                return profile

    for profile in profiles:
        if profile.user_id == DEFAULT_USER_ID:
            return profile

    return profiles[0]


def _find_existing_portfolio() -> Path | None:
    for candidate in [
        Path("data/portfolio.csv"),
        Path("portfolio.csv"),
        Path("app/data/portfolio.csv"),
        Path("data/holdings.csv"),
    ]:
        if candidate.exists():
            return candidate
    return None


def ensure_default_profiles() -> list[UserProfile]:
    ensure_users_root()

    existing = list_user_profiles()
    if existing:
        return existing

    create_user_profile(
        display_name="Demo User",
        user_id=DEFAULT_USER_ID,
        copy_from_portfolio=_find_existing_portfolio(),
    )

    return list_user_profiles()
