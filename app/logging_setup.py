"""Minimal logging configuration for AI Laptop Guardian.

Logs never contain credentials, OAuth tokens, client
secrets, or sensitive file contents.
"""

import logging
import os
import sys

_LOG_FORMAT = (
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)


def setup_logging(level=logging.INFO):
    """Configure root logger for the application.

    In source mode, logs go to ``logs/app.log``.
    In packaged mode, logs go to ``%LOCALAPPDATA%/AI-Laptop-Guardian/logs/app.log``.
    """
    from app.paths import user_data_dir

    log_dir = os.path.join(user_data_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "app.log")

    root = logging.getLogger()
    root.setLevel(level)

    if not root.handlers:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(logging.Formatter(_LOG_FORMAT))
        root.addHandler(fh)

        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(level)
        ch.setFormatter(logging.Formatter(_LOG_FORMAT))
        root.addHandler(ch)


def get_logger(name):
    """Return a child logger under the application namespace."""
    return logging.getLogger(f"ai_laptop_guardian.{name}")
