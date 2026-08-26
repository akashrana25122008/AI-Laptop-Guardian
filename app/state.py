"""First-run state management for AI Laptop Guardian.

Stores only non-sensitive UI preferences.  Never stores
OAuth tokens, client secrets, passwords, or cloud
credentials.

The state file is safe to be missing, malformed,
unreadable, or partially written — in all those cases
the application continues with defaults.
"""

import json
import os

from app.paths import user_data_dir

_STATE_VERSION = 1

_DEFAULT_STATE = {
    "state_version": _STATE_VERSION,
    "onboarding_completed": False,
    "onboarding_version": 0,
}


def _state_path():
    """Return the path to the preferences JSON file."""
    return os.path.join(user_data_dir(), "preferences.json")


def load():
    """Load the state from disk.

    Returns a dict.  On any failure returns a copy of the
    default state — never raises.
    """
    path = _state_path()

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError,
            OSError, ValueError):
        return dict(_DEFAULT_STATE)

    if not isinstance(data, dict):
        return dict(_DEFAULT_STATE)

    result = dict(_DEFAULT_STATE)
    result.update({
        k: v
        for k, v in data.items()
        if k in _DEFAULT_STATE
    })
    return result


def save(state):
    """Persist *state* to disk.

    Writes to a temporary file first, then replaces the
    original so a crash during write never leaves a
    corrupted file.

    Never raises — returns True on success, False on
    failure.
    """
    if not isinstance(state, dict):
        return False

    safe = {
        "state_version": _STATE_VERSION,
        "onboarding_completed": bool(
            state.get("onboarding_completed", False)
        ),
        "onboarding_version": int(
            state.get("onboarding_version", 0)
        ),
    }

    path = _state_path()
    tmp = path + ".tmp"

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(safe, fh, indent=2)

        if os.path.exists(path):
            os.replace(tmp, path)
        else:
            os.rename(tmp, path)

        return True
    except (OSError, ValueError):
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def mark_onboarding_completed(version=_STATE_VERSION):
    """Mark onboarding as done and persist."""
    state = load()
    state["onboarding_completed"] = True
    state["onboarding_version"] = version
    return save(state)


def is_onboarding_completed():
    """Return True if the user has finished onboarding."""
    state = load()
    return bool(state.get("onboarding_completed"))
