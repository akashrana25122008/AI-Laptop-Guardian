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
