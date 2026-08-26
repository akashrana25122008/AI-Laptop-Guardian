"""
Reusable display helpers shared across views.

No application logic lives here.
"""


def safe_text(value, fallback="Unknown"):
    """Render any backend value as a display string."""

    if value is None:
        return fallback

    text = str(value).strip()

    return text if text else fallback


def format_bytes_short(size_bytes):
    """Render a byte count to a short human string."""

    if size_bytes is None:
        return "Unavailable"

    try:
        size_bytes = float(size_bytes)
    except (TypeError, ValueError):
        return "Unavailable"

    if size_bytes < 1024:
        return f"{size_bytes:.0f} B"

    if size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"

    if size_bytes < 1024 ** 3:
        return (
            f"{size_bytes / (1024 ** 2):.1f} MB"
        )

    return (
        f"{size_bytes / (1024 ** 3):.2f} GB"
    )


def status_label(score):
    """Deterministic label from a 0-100 health score."""

    if score is None:
        return "Unknown"

    try:
        score = float(score)
    except (TypeError, ValueError):
        return "Unknown"

    if score >= 80:
        return "Protected"

    if score >= 60:
        return "Healthy"

    return "Attention Needed"


# =========================================================
# SAFE USER-FACING MESSAGES (M15)
# =========================================================


def safe_backend_message(exc, fallback="Something went wrong. Please try again."):
    """Convert a backend exception to a safe UI string.

    Never exposes raw exception details, stack traces,
    file paths, or credentials to the user.
    """

    if exc is None:
        return fallback

    return fallback


def safe_account_count(accounts):
    """Return a friendly string for connected account count."""

    if not accounts:
        return "No Google accounts connected"

    count = len(accounts)

    if count == 1:
        return "1 Google account connected"

    return f"{count} Google accounts connected"


def safe_ollama_message(status):
    """Return a user-friendly Ollama status string."""

    if status is None:
        return "AI assistant status is unknown"

    status = str(status).strip()

    mapping = {
        "Ready": "Ollama is available and ready",
        "Unavailable": "Ollama is not available",
        "Running (no local models found)": (
            "Ollama is running but no AI models are installed"
        ),
    }

    if status in mapping:
        return mapping[status]

    if status.startswith("Available"):
        return f"Ollama is available ({status})"

    if "unavailable" in status.lower():
        return "Ollama is not available"

    return f"Ollama status: {status}"


def safe_cloud_message(result):
    """Return a safe user message for cloud operation failures."""

    if result is None:
        return "Cloud data is temporarily unavailable."

    if not isinstance(result, dict):
        return "Cloud data is temporarily unavailable."

    if result.get("success"):
        return ""

    error = result.get("error", "")

    if "auth" in str(error).lower():
        return (
            "Google Drive connection could not be "
            "completed. No account was added."
        )

    if error:
        return (
            "Cloud account information is temporarily "
            "unavailable."
        )

    return "Cloud data is temporarily unavailable."


def safe_connect_message(result):
    """Return a safe user message for connect results."""

    if not isinstance(result, dict):
        return "Connection did not complete."

    if result.get("success"):
        account = result.get("account") or {}
        email = account.get("email")
        if email:
            return f"Connected: {email}"
        return "Connected successfully."

    return (
        "Google Drive connection could not be completed. "
        "No account was added."
    )
