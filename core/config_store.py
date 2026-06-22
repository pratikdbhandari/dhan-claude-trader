"""User-editable settings store for the INSTALLED app (non-developer).

Keys entered in the Settings page are saved to ~/.dhan_claude_trader/settings.local.json
in the user's home directory — NOT to .env and NOT in the Git repo. This keeps the
installed PC's secrets separate from the developer/Git workflow.

Read precedence: settings.local.json  ->  os.environ (.env, for developers)  ->  default.

Security note: the file is PLAINTEXT, local-only, single-user. It is never synced to Git.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

SETTINGS_DIR = Path.home() / ".dhan_claude_trader"
SETTINGS_PATH = SETTINGS_DIR / "settings.local.json"

# the full set of settings the Settings page manages
KEYS = [
    "DHAN_CLIENT_ID", "DHAN_ACCESS_TOKEN",
    "ANTHROPIC_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY", "MISTRAL_API_KEY",
    "SIGNAL_SOURCE", "TRADE_MODE",
    "MAX_DAILY_LOSS", "MAX_RISK_PER_TRADE_PCT", "MAX_OPEN_POSITIONS", "ACCOUNT_CAPITAL",
]

SECRET_KEYS = {"DHAN_ACCESS_TOKEN", "ANTHROPIC_API_KEY", "GROQ_API_KEY",
               "CEREBRAS_API_KEY", "MISTRAL_API_KEY"}


def load(path: Path | str = SETTINGS_PATH) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save(settings: dict, path: Path | str = SETTINGS_PATH) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # merge with existing so partial saves don't wipe other keys
    current = load(p)
    current.update({k: v for k, v in settings.items() if v is not None})
    p.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return str(p)


def get_setting(key: str, default=None, path: Path | str = SETTINGS_PATH):
    """settings.local.json -> environment (.env) -> default."""
    stored = load(path).get(key)
    if stored not in (None, ""):
        return stored
    env = os.environ.get(key)
    if env not in (None, ""):
        return env
    return default
