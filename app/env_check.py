"""First-run environment validation.

Checks that the runtime environment can support the
application.  Returns structured results; never raises.
"""

import importlib
import os
import sys

from app.version import __version__


def _check_import(module_name, extra_msg=""):
    """Try importing *module_name*. Return (ok, detail)."""
    try:
        importlib.import_module(module_name)
        return True, ""
    except ImportError as exc:
        detail = str(exc)
        if extra_msg:
            detail = f"{detail}. {extra_msg}"
        return False, detail


def check_python():
    ok = sys.version_info >= (3, 9)
    detail = (
        ""
        if ok
        else f"Python {sys.version_info.major}.{sys.version_info.minor} "
        f"is below the minimum (3.9)"
    )
    return {
        "name": "Python",
        "ok": ok,
        "detail": detail or f"{sys.version}",
    }


def check_customtkinter():
    ok, detail = _check_import(
        "customtkinter",
        "Install with: pip install customtkinter",
    )
    return {
        "name": "CustomTkinter",
        "ok": ok,
        "detail": detail or "Available",
    }


def check_psutil():
    ok, detail = _check_import("psutil")
    return {
        "name": "psutil",
        "ok": ok,
        "detail": detail or "Available",
    }


def check_ollama():
    ok, detail = _check_import(
        "ollama",
        "Optional. Install with: pip install ollama",
    )
    return {
        "name": "Ollama client",
        "ok": True,
        "detail": (
            "Available"
            if ok
            else "Not installed (optional — local AI features disabled)"
        ),
        "optional": True,
    }


def check_google_deps():
    ok, detail = _check_import(
        "google.auth",
        "Optional. Install with: pip install google-auth google-auth-oauthlib "
        "google-auth-httplib2 google-api-python-client",
    )
    return {
        "name": "Google Drive deps",
        "ok": True,
        "detail": (
            "Available"
            if ok
            else "Not installed (optional — cloud features disabled)"
        ),
        "optional": True,
    }


def check_user_data_dir():
    from app.paths import ensure_user_data_dir

    try:
        path = ensure_user_data_dir()
        return {
            "name": "User data dir",
            "ok": True,
            "detail": path,
        }
    except OSError as exc:
        return {
            "name": "User data dir",
            "ok": False,
            "detail": str(exc),
        }


ALL_CHECKS = [
    check_python,
    check_customtkinter,
    check_psutil,
    check_ollama,
    check_google_deps,
    check_user_data_dir,
]


def run_all_checks():
    """Run every check and return a list of result dicts."""
    return [fn() for fn in ALL_CHECKS]


def summary():
    """Return a human-readable multi-line summary."""
    lines = [f"AI Laptop Guardian {__version__} — Environment"]
    lines.append("=" * 50)
    for check in run_all_checks():
        status = "OK" if check["ok"] else "FAIL"
        if check.get("optional") and check["ok"]:
            status = "OPT"
        lines.append(f"  [{status}] {check['name']}: {check['detail']}")
    return "\n".join(lines)
