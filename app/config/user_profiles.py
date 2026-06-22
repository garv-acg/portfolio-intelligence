
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


USERS_ROOT = Path("data/users")


@dataclass(frozen=True)
class UserProfile:
    user_id: str
    display_name: str
    email: str | None
    user_dir: Path
    portfolio_file: Path
    settings_file: Path


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "_", value)
    return value.strip("_") or "demo"


def _find_existing_portfolio() -> Path | None:
    for candidate in [
        Path("portfolio.csv"),
        Path("data/portfolio.csv"),
        Path("app/data/portfolio.csv"),
    ]:
        if candidate.exists():
            return candidate
    return None


def create_user_profile(display_name: str, email: str | None = None, user_id: str | None = None, copy_from: Path | None = None) -> UserProfile:
    USERS_ROOT.mkdir(parents=True, exist_ok=True)

    uid = _slugify(user_id or display_name)
    user_dir = USERS_ROOT / uid
    user_dir.mkdir(parents=True, exist_ok=True)

    portfolio_file = user_dir / "portfolio.csv"
    settings_file = user_dir / "settings.json"

    if copy_from and copy_from.exists() and not portfolio_file.exists():
        shutil.copy(copy_from, portfolio_file)

    if not portfolio_file.exists():
        portfolio_file.write_text("ticker,shares,cost_basis\nAAPL,1,0\n", encoding="utf-8")

    settings = {
        "user_id": uid,
        "display_name": display_name,
        "email": email,
        "portfolio_file": str(portfolio_file),
        "facts_only_mode": True,
    }

    settings_file.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    return UserProfile(uid, display_name, email, user_dir, portfolio_file, settings_file)


def list_user_profiles() -> list[UserProfile]:
    USERS_ROOT.mkdir(parents=True, exist_ok=True)

    profiles: list[UserProfile] = []

    for user_dir in sorted(p for p in USERS_ROOT.iterdir() if p.is_dir()):
        settings_file = user_dir / "settings.json"

        if settings_file.exists():
            try:
                settings = json.loads(settings_file.read_text(encoding="utf-8"))
            except Exception:
                settings = {}
        else:
            settings = {}

        uid = settings.get("user_id", user_dir.name)
        display_name = settings.get("display_name", uid.replace("_", " ").title())
        email = settings.get("email")

        profiles.append(
            UserProfile(
                uid,
                display_name,
                email,
                user_dir,
                user_dir / "portfolio.csv",
                settings_file,
            )
        )

    return profiles


def ensure_default_profiles() -> list[UserProfile]:
    USERS_ROOT.mkdir(parents=True, exist_ok=True)

    profiles = list_user_profiles()
    if profiles:
        return profiles

    create_user_profile(
        display_name="Demo User",
        user_id="demo",
        copy_from=_find_existing_portfolio(),
    )

    return list_user_profiles()


def get_user_profile(user_id: str | None = None) -> UserProfile:
    profiles = ensure_default_profiles()

    if user_id:
        for profile in profiles:
            if profile.user_id == user_id:
                return profile

    for profile in profiles:
        if profile.user_id == "demo":
            return profile

    return profiles[0]
