
from __future__ import annotations

from pathlib import Path
import sys

USER_PROFILES_CODE = "\nfrom __future__ import annotations\n\nimport json\nimport re\nimport shutil\nfrom dataclasses import dataclass\nfrom pathlib import Path\nfrom typing import Any\n\n\nUSERS_ROOT = Path(\"data/users\")\nDEFAULT_USER_ID = \"demo\"\n\n\n@dataclass(frozen=True)\nclass UserProfile:\n    user_id: str\n    display_name: str\n    email: str | None\n    user_dir: Path\n    portfolio_file: Path\n    settings_file: Path\n    history_db: Path\n\n\ndef _slugify(value: str) -> str:\n    value = value.strip().lower()\n    value = re.sub(r\"[^a-z0-9_-]+\", \"_\", value)\n    value = re.sub(r\"_+\", \"_\", value).strip(\"_\")\n    return value or DEFAULT_USER_ID\n\n\ndef ensure_users_root() -> None:\n    USERS_ROOT.mkdir(parents=True, exist_ok=True)\n\n\ndef create_user_profile(display_name: str, email: str | None = None, user_id: str | None = None, copy_from_portfolio: Path | None = None) -> UserProfile:\n    ensure_users_root()\n    resolved_user_id = _slugify(user_id or display_name)\n    user_dir = USERS_ROOT / resolved_user_id\n    user_dir.mkdir(parents=True, exist_ok=True)\n\n    portfolio_file = user_dir / \"portfolio.csv\"\n    settings_file = user_dir / \"settings.json\"\n    history_db = user_dir / \"history.db\"\n\n    if copy_from_portfolio and copy_from_portfolio.exists() and not portfolio_file.exists():\n        shutil.copy(copy_from_portfolio, portfolio_file)\n\n    if not portfolio_file.exists():\n        portfolio_file.write_text(\"ticker,shares,cost_basis\\\\nAAPL,1,0\\\\n\", encoding=\"utf-8\")\n\n    settings = {\n        \"user_id\": resolved_user_id,\n        \"display_name\": display_name,\n        \"email\": email,\n        \"portfolio_file\": str(portfolio_file),\n        \"history_db\": str(history_db),\n        \"morning_brief_enabled\": True,\n        \"facts_only_mode\": True,\n    }\n\n    if settings_file.exists():\n        try:\n            existing = json.loads(settings_file.read_text(encoding=\"utf-8\"))\n            settings.update(existing)\n            settings[\"user_id\"] = resolved_user_id\n            settings[\"portfolio_file\"] = str(portfolio_file)\n            settings[\"history_db\"] = str(history_db)\n        except Exception:\n            pass\n\n    settings_file.write_text(json.dumps(settings, indent=2), encoding=\"utf-8\")\n\n    return UserProfile(\n        user_id=resolved_user_id,\n        display_name=settings.get(\"display_name\", display_name),\n        email=settings.get(\"email\"),\n        user_dir=user_dir,\n        portfolio_file=portfolio_file,\n        settings_file=settings_file,\n        history_db=history_db,\n    )\n\n\ndef list_user_profiles() -> list[UserProfile]:\n    ensure_users_root()\n    profiles: list[UserProfile] = []\n\n    for user_dir in sorted([p for p in USERS_ROOT.iterdir() if p.is_dir()]):\n        settings_file = user_dir / \"settings.json\"\n        settings: dict[str, Any] = {}\n\n        if settings_file.exists():\n            try:\n                settings = json.loads(settings_file.read_text(encoding=\"utf-8\"))\n            except Exception:\n                settings = {}\n\n        user_id = settings.get(\"user_id\", user_dir.name)\n        display_name = settings.get(\"display_name\", user_id.replace(\"_\", \" \").title())\n        email = settings.get(\"email\")\n\n        profiles.append(\n            UserProfile(\n                user_id=user_id,\n                display_name=display_name,\n                email=email,\n                user_dir=user_dir,\n                portfolio_file=user_dir / \"portfolio.csv\",\n                settings_file=settings_file,\n                history_db=user_dir / \"history.db\",\n            )\n        )\n\n    return profiles\n\n\ndef get_user_profile(user_id: str | None = None) -> UserProfile:\n    ensure_users_root()\n    profiles = list_user_profiles()\n\n    if not profiles:\n        return create_user_profile(\n            display_name=\"Demo User\",\n            user_id=DEFAULT_USER_ID,\n            copy_from_portfolio=_find_existing_portfolio(),\n        )\n\n    if user_id:\n        for profile in profiles:\n            if profile.user_id == user_id:\n                return profile\n\n    for profile in profiles:\n        if profile.user_id == DEFAULT_USER_ID:\n            return profile\n\n    return profiles[0]\n\n\ndef _find_existing_portfolio() -> Path | None:\n    for candidate in [\n        Path(\"data/portfolio.csv\"),\n        Path(\"portfolio.csv\"),\n        Path(\"app/data/portfolio.csv\"),\n        Path(\"data/holdings.csv\"),\n    ]:\n        if candidate.exists():\n            return candidate\n    return None\n\n\ndef ensure_default_profiles() -> list[UserProfile]:\n    ensure_users_root()\n\n    existing = list_user_profiles()\n    if existing:\n        return existing\n\n    create_user_profile(\n        display_name=\"Demo User\",\n        user_id=DEFAULT_USER_ID,\n        copy_from_portfolio=_find_existing_portfolio(),\n    )\n\n    return list_user_profiles()\n"
SELECTOR_CODE = "\ndef render_user_profile_selector() -> Path:\n    ensure_default_profiles()\n    profiles = ensure_default_profiles()\n\n    st.sidebar.markdown(\"### User Profile\")\n\n    profile_labels = {\n        f\"{profile.display_name} ({profile.user_id})\": profile.user_id\n        for profile in profiles\n    }\n\n    labels = list(profile_labels.keys())\n    current_user_id = st.session_state.get(\"active_user_id\")\n    default_index = 0\n\n    if current_user_id:\n        for i, label in enumerate(labels):\n            if profile_labels[label] == current_user_id:\n                default_index = i\n                break\n\n    selected_label = st.sidebar.selectbox(\"Active user\", labels, index=default_index)\n    selected_user_id = profile_labels[selected_label]\n    st.session_state[\"active_user_id\"] = selected_user_id\n\n    profile = get_user_profile(selected_user_id)\n    st.session_state[\"active_profile\"] = profile\n    st.session_state[\"portfolio_path_override\"] = str(profile.portfolio_file)\n\n    with st.sidebar.expander(\"Create User\", expanded=False):\n        new_name = st.text_input(\"Display name\", key=\"new_user_display_name\")\n        new_email = st.text_input(\"Email\", key=\"new_user_email\")\n        if st.button(\"Create Profile\"):\n            if not new_name.strip():\n                st.warning(\"Enter a display name first.\")\n            else:\n                new_profile = create_user_profile(\n                    display_name=new_name.strip(),\n                    email=new_email.strip() or None,\n                    copy_from_portfolio=Path(st.session_state.get(\"portfolio_path_override\", \"data/portfolio.csv\")),\n                )\n                st.session_state[\"active_user_id\"] = new_profile.user_id\n                st.session_state[\"portfolio_path_override\"] = str(new_profile.portfolio_file)\n                st.success(f\"Created profile: {new_profile.display_name}\")\n                st.rerun()\n\n    st.sidebar.caption(f\"Portfolio: {profile.portfolio_file}\")\n    return profile.portfolio_file\n\n"


def backup(path: Path) -> None:
    if path.exists():
        path.with_suffix(path.suffix + ".bak_user_profiles").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")


def install_module() -> None:
    target = Path("app/config/user_profiles.py")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(USER_PROFILES_CODE, encoding="utf-8")
    print("OK | app/config/user_profiles.py written")


def initialize_profiles() -> None:
    from app.config.user_profiles import ensure_default_profiles
    profiles = ensure_default_profiles()
    print(f"OK | user profiles ready: {len(profiles)}")
    for profile in profiles:
        print(f" - {profile.user_id} -> {profile.portfolio_file}")


def patch_control_center() -> None:
    path = Path("newsletter_control_center.py")
    if not path.exists():
        raise SystemExit("ERROR | newsletter_control_center.py not found")

    backup(path)
    text = path.read_text(encoding="utf-8")

    if "from app.config.user_profiles import" not in text:
        text = text.replace(
            "import streamlit as st\n",
            "import streamlit as st\n\nfrom app.config.user_profiles import ensure_default_profiles, get_user_profile, create_user_profile\n",
            1,
        )

    if "def render_user_profile_selector" not in text:
        text = text.replace("\ndef render_sidebar", SELECTOR_CODE + "\ndef render_sidebar", 1)

    if "portfolio_path = render_user_profile_selector()" not in text:
        text = text.replace(
            '    st.sidebar.markdown("### Navigation")',
            '    portfolio_path = render_user_profile_selector()\n\n    st.sidebar.markdown("### Navigation")',
            1,
        )

    # Replace common portfolio CSV path text input blocks with profile-driven path.
    text = text.replace(
        '    portfolio_path = Path(\n        st.sidebar.text_input(\n            "Portfolio CSV path",\n            value=str(DEFAULT_PORTFOLIO_PATH),\n        )\n    )',
        '    portfolio_path = Path(st.session_state.get("portfolio_path_override", str(DEFAULT_PORTFOLIO_PATH)))',
    )

    text = text.replace(
        '    portfolio_path = Path(st.sidebar.text_input(\n        "Portfolio CSV path",\n        value=str(DEFAULT_PORTFOLIO_PATH),\n    ))',
        '    portfolio_path = Path(st.session_state.get("portfolio_path_override", str(DEFAULT_PORTFOLIO_PATH)))',
    )

    path.write_text(text, encoding="utf-8")
    print("OK | newsletter_control_center.py patched")


def verify() -> bool:
    checks = {}
    checks["user_profiles module exists"] = Path("app/config/user_profiles.py").exists()
    checks["users directory exists"] = Path("data/users").exists()

    text = Path("newsletter_control_center.py").read_text(encoding="utf-8")
    checks["control imports user profiles"] = "from app.config.user_profiles import" in text
    checks["user selector exists"] = "def render_user_profile_selector" in text
    checks["portfolio override exists"] = "portfolio_path_override" in text

    try:
        from app.config.user_profiles import list_user_profiles, ensure_default_profiles
        ensure_default_profiles()
        profiles = list_user_profiles()
        checks["profile import works"] = len(profiles) >= 1
        print("INFO | profiles:", [p.user_id for p in profiles])
    except Exception as exc:
        print(f"FAIL | user profile import error: {exc}")
        checks["profile import works"] = False

    print("\nVERIFY")
    ok = True
    for name, passed in checks.items():
        print(("PASS" if passed else "FAIL") + f" | {name}")
        ok = ok and passed
    return ok


def main() -> None:
    if "--verify" in sys.argv:
        raise SystemExit(0 if verify() else 1)

    print("Installing Phase 2 user profiles from:", Path.cwd())
    install_module()
    initialize_profiles()
    patch_control_center()
    ok = verify()

    print("\nNEXT:")
    print("python install_user_profiles.py --verify")
    print("python -m streamlit run newsletter_control_center.py")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
