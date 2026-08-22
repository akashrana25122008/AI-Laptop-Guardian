"""
Lightweight result contract shared by tools, ToolRouter,
and AIAgent.

Contract:

    {
        "success": bool,
        "tool": str,
        "data": ...      # tool-specific payload
        "error": str     # present on failure
        "message": str   # optional human-readable text
    }

Rules:

    - Well-formed results are passed through UNCHANGED so
      existing behavior is preserved.
    - Malformed or non-dict results are wrapped as explicit
      failures instead of flowing into the AI layer.
    - A failed call is NEVER converted into a fake success.
"""

MAX_ERROR_LENGTH = 300


def sanitize_error(error):
    """
    Convert any exception or value into a short, single-line
    error string safe for user-facing results and logs.
    """

    if isinstance(error, BaseException):
        error = f"{type(error).__name__}: {error}"

    text = str(error).strip()

    # Collapse internal newlines so one error is always
    # exactly one line.
    text = " ".join(text.split())

    if len(text) > MAX_ERROR_LENGTH:
        text = text[: MAX_ERROR_LENGTH - 3] + "..."

    return text or "Unknown error."


def is_successful_result(result):
    """
    True only when the result is a dict explicitly marked
    as successful.
    """

    return (
        isinstance(result, dict)
        and result.get("success") is True
    )


def ensure_result(result, tool_name):
    """
    Normalize any tool/provider return value into the
    contract without touching already-valid results.

    - dict with a "success" key  -> returned unchanged
    - dict without "success"     -> explicit failure that
      preserves the original payload under "data"
    - anything else              -> explicit failure
    """

    if isinstance(result, dict) and "success" in result:
        return result

    if isinstance(result, dict):
        return {
            "success": False,
            "tool": tool_name,
            "error": (
                "Tool did not report success or failure."
            ),
            "data": result,
        }

    return {
        "success": False,
        "tool": tool_name,
        "error": (
            "Tool returned an unexpected "
            f"{type(result).__name__} instead of a result."
        ),
    }
