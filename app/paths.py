"""Resource path resolution for source and packaged modes.

When running from source, paths resolve relative to the project root.
When running as a PyInstaller bundle, paths resolve relative to the
bundle's temporary directory.
"""

import sys
import os


def _is_frozen():
    """Return True when running inside a PyInstaller bundle."""
    return getattr(sys, "frozen", False) and hasattr(
        sys, "_MEIPASS"
    )


def app_root():
    """Return the application root directory.

    In source mode this is the project root (the directory
    containing the ``app/`` package).  In packaged mode it
    is the PyInstaller ``_MEIPASS`` temp directory.
    """
    if _is_frozen():
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(__file__))


def user_data_dir():
    """Return a writable directory for user-generated data.

    Tokens, account registries, and other mutable state are
    stored here rather than inside the bundled application.
    In source mode this defaults to ``<project_root>/cloud_data``.
    In packaged mode it defaults to ``%LOCALAPPDATA%/AI-Laptop-Guardian``.
    """
    if _is_frozen():
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return os.path.join(base, "AI-Laptop-Guardian")
    return os.path.join(app_root(), "cloud_data")


def ensure_user_data_dir():
    """Create the user data directory if it does not exist."""
    path = user_data_dir()
    os.makedirs(path, exist_ok=True)
    tokens = os.path.join(path, "tokens")
    os.makedirs(tokens, exist_ok=True)
    return path


def resource_path(relative):
    """Return the absolute path to a bundled resource.

    *relative* is a path relative to the application root.
    """
    return os.path.join(app_root(), relative)
